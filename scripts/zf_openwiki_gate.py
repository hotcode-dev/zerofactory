#!/usr/bin/env python3
"""ZeroFactory OpenWiki Pre-Screen & Wake-Gate.

Runs locally in the target repository workdir before the Hermes OpenWiki cron fires:
1. Verifies that `openwiki/` documentation directory exists for the board.
   If missing: outputs `{"wakeAgent": false}` (skips run until openwiki is initialized).
2. Checks git working tree cleanliness.
   If uncommitted changes exist: outputs `{"wakeAgent": false}` (prevents conflicts).
3. Compares HEAD against the last docs sync point (the conventional
   `docs(openwiki): sync ...` commit, falling back to state / the newest
   openwiki-touching commit). If NO new non-openwiki commits exist:
   outputs `{"wakeAgent": false}`. (0 LLM tokens!).
4. If branch updates exist (new commits landed on the default branch):
   deterministically creates the single OpenWiki update task for zf-builder.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any

# Ensure ZeroFactory root is in sys.path
SCRIPT_DIR = Path(__file__).resolve().parent
candidate_roots = [
    SCRIPT_DIR.parent,
    Path.home() / ".hermes" / "plugins" / "zerofactory",
    Path.home() / "git" / "hotcode-dev" / "zerofactory",
]
if os.environ.get("ZEROFACTORY_ROOT"):
    candidate_roots.insert(0, Path(os.environ["ZEROFACTORY_ROOT"]))

for candidate in candidate_roots:
    try:
        resolved = candidate.resolve()
        if resolved.is_dir() and str(resolved) not in sys.path:
            sys.path.insert(0, str(resolved))
    except Exception:
        pass

STATE_FILE = Path.home() / ".hermes" / "openwiki_state.json"
DEFAULT_DB_PATH = Path.home() / ".hermes" / "zerofactory.db"


def create_openwiki_task(
    board_slug: str, diff_log: str, repo_dir: Path, repo_alias: str | None = None
) -> dict[str, Any] | None:
    """Deterministically create a documentation sync task on the Kanban board for zf-builder."""
    target_str = f" for repository `{repo_alias}`" if repo_alias else ""
    task_desc = f"""Sync OpenWiki architecture documentation (`openwiki/`){target_str} with recent merged commits on the default branch.

## Key Recent Commits:
{diff_log.strip() if diff_log.strip() else "(Check git log since last OpenWiki commit)"}

## Instructions for zf-builder:
1. Inspect recent commits and identify changes to public interfaces and architecture.
2. Use the OpenWiki MCP server lifecycle tools to update relevant markdown pages:
   - Call `openwiki_begin({{"root": ".", "mode": "update"}})`
   - Call `openwiki_next_page`, update the relevant Markdown pages with valid frontmatter, and submit page decisions via `openwiki_submit_page`.
   - When all pages are updated, call `openwiki_finish`.
3. If OpenWiki created `.github/workflows/openwiki-update.yml` or `CLAUDE.md`, remove them:
   `rm -rf .github/workflows/openwiki-update.yml CLAUDE.md`
4. Stage and commit updated documentation directly on the default branch:
   `git add openwiki/ AGENTS.md`
   `git commit -m "docs(openwiki): sync architecture documentation with recent changes"`
"""
    task_title = (
        f"docs(openwiki): sync architecture documentation for {repo_alias}"
        if repo_alias
        else "docs(openwiki): sync architecture documentation with recent changes"
    )
    try:
        from dashboard.plugin_api import TaskCreate, create_task

        task = create_task(
            TaskCreate(
                board_slug=board_slug,
                repo_alias=repo_alias,
                title=task_title,
                category="documentation",
                priority="P2",
                status="todo",
                assignee="zf-builder",
                description=task_desc,
            )
        )
        return task
    except Exception:
        # Fallback to direct SQLite insertion if plugin_api unavailable
        db_path = Path(os.environ.get("ZEROFACTORY_DB") or DEFAULT_DB_PATH)
        if db_path.exists():
            try:
                from dashboard.db import generate_task_id

                task_id = generate_task_id(board_slug)
            except Exception:
                task_id = f"zf-{uuid.uuid4().hex[:8]}"
            now_ts = int(time.time())
            try:
                with sqlite3.connect(str(db_path), timeout=5.0) as conn:
                    cursor = conn.cursor()
                    cursor.execute("PRAGMA table_info(tasks)")
                    cols = {row[1] for row in cursor.fetchall()}
                    if "repo_alias" in cols and repo_alias:
                        conn.execute(
                            """
                            INSERT INTO tasks (id, board_slug, repo_alias, title, description, status, assignee, priority, created_at, updated_at)
                            VALUES (?, ?, ?, ?, ?, 'todo', 'zf-builder', 'P2', ?, ?)
                            """,
                            (
                                task_id,
                                board_slug,
                                repo_alias,
                                task_title,
                                task_desc,
                                now_ts,
                                now_ts,
                            ),
                        )
                    else:
                        conn.execute(
                            """
                            INSERT INTO tasks (id, board_slug, title, description, status, assignee, priority, created_at, updated_at)
                            VALUES (?, ?, ?, ?, 'todo', 'zf-builder', 'P2', ?, ?)
                            """,
                            (
                                task_id,
                                board_slug,
                                task_title,
                                task_desc,
                                now_ts,
                                now_ts,
                            ),
                        )
                    conn.commit()
                    return {"id": task_id}
            except Exception:
                pass
    return None


def _run_cmd(cmd: list[str], cwd: Path | None = None) -> str:
    try:
        res = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10,
        )
        return res.stdout.strip() if res.returncode == 0 else ""
    except Exception:
        return ""


def get_state_file() -> Path:
    env_override = os.environ.get("ZEROFACTORY_OPENWIKI_STATE")
    return Path(env_override) if env_override else STATE_FILE


def load_state() -> dict[str, Any]:
    sf = get_state_file()
    if sf.exists():
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def save_state(state: dict[str, Any]) -> None:
    sf = get_state_file()
    try:
        sf.parent.mkdir(parents=True, exist_ok=True)
        tmp = sf.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        tmp.replace(sf)
    except Exception:
        pass


def resolve_board_slug(repo_dir: Path) -> str:
    """Infer board slug from argv or database."""
    for arg in sys.argv[1:]:
        if not arg.startswith("-"):
            return arg

    db_path = Path(os.environ.get("ZEROFACTORY_DB") or DEFAULT_DB_PATH)
    if db_path.exists():
        try:
            with sqlite3.connect(str(db_path), timeout=5.0) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT b.slug, br.git_url FROM boards b LEFT JOIN board_repositories br ON b.slug = br.board_slug"
                )
                for row in cursor.fetchall():
                    slug, git_url = row[0], row[1] or ""
                    if slug and (
                        slug.lower() in repo_dir.name.lower()
                        or repo_dir.name.lower() in slug.lower()
                    ):
                        return slug
                    if git_url and (
                        repo_dir.name in git_url or str(repo_dir) in git_url
                    ):
                        return slug
        except Exception:
            pass

    return repo_dir.name


def resolve_repo_path(
    board_slug: str, repo_alias: str, git_url: str = "", current_dir: Path | None = None
) -> Path | None:
    """Resolve the local checkout directory for a board repository."""
    # 0. Check current working directory if matching alias or remote
    if current_dir and (current_dir / ".git").exists():
        if current_dir.name == repo_alias:
            return current_dir
        if git_url:
            remote = _run_cmd(
                ["git", "config", "--get", "remote.origin.url"], cwd=current_dir
            )
            if remote and (git_url in remote or remote in git_url):
                return current_dir

    # 1. Local path if git_url is an existing directory
    if git_url:
        try:
            local_p = Path(git_url)
            if local_p.is_dir() and (local_p / ".git").exists():
                return local_p.resolve()
        except Exception:
            pass

    # 2. Check ~/.zerofactory/workspaces/<board_slug>/repos/<alias>
    try:
        from paths import get_board_repos_dir  # type: ignore
    except Exception:
        try:
            from ..paths import get_board_repos_dir  # type: ignore
        except Exception:
            get_board_repos_dir = lambda b: Path.home() / ".zerofactory" / "workspaces" / b / "repos"  # type: ignore

    b_repos = get_board_repos_dir(board_slug)
    candidates: list[Path] = [
        b_repos / repo_alias,
    ]

    if git_url:
        cleaned_url = re.sub(r"\.git$", "", git_url.strip().rstrip("/"))
        parts = cleaned_url.replace(":", "/").split("/")
        if len(parts) >= 1:
            repo_name = parts[-1]
            candidates.append(b_repos / repo_name)

    for cand in candidates:
        if cand.is_dir() and (cand / ".git").exists():
            return cand.resolve()

    if current_dir and (current_dir / ".git").exists():
        return current_dir

    return None


def has_active_openwiki_task(
    board_slug: str, repo_alias: str | None = None
) -> tuple[bool, str]:
    """Check if an OpenWiki setup or update task is already active on the board."""
    db_path = Path(os.environ.get("ZEROFACTORY_DB") or DEFAULT_DB_PATH)
    if not db_path.exists():
        return False, ""
    try:
        with sqlite3.connect(str(db_path), timeout=5.0) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            query = """
                SELECT id, title, status FROM tasks
                WHERE board_slug = ?
                  AND status IN ('todo', 'running', 'blocked', 'triage')
                  AND LOWER(title) LIKE '%openwiki%'
            """
            params: list[Any] = [board_slug]
            if repo_alias:
                query += " AND (repo_alias = ? OR repo_alias IS NULL)"
                params.append(repo_alias)
            query += " ORDER BY created_at DESC LIMIT 1"
            cursor.execute(query, params)
            row = cursor.fetchone()
            if row:
                target_str = f" for '{repo_alias}'" if repo_alias else ""
                return (
                    True,
                    f"Board '{board_slug}' already has an active OpenWiki task{target_str} '{row['id']}' ({row['title']}) in status '{row['status']}'; skipping.",
                )
    except Exception:
        pass
    return False, ""


def evaluate_single_repo_openwiki(
    repo_dir: Path,
    slug: str,
    repo_alias: str | None = None,
    force_update: bool = False,
    auto_create_task: bool = True,
) -> tuple[bool, str]:
    """Evaluate a single repository directory for OpenWiki documentation updates."""
    alias_label = f" ({repo_alias})" if repo_alias else ""

    # 1. Check if git repo
    git_dir = repo_dir / ".git"
    if not git_dir.exists():
        return False, f"Not a git repository at {repo_dir}; skipping."

    # 2. Check if openwiki/ directory exists
    openwiki_dir = repo_dir / "openwiki"
    if not openwiki_dir.is_dir():
        return (
            False,
            f"OpenWiki not initialized for board '{slug}'{alias_label} (no openwiki/ directory found); skipping.",
        )

    # 3. Check if active OpenWiki task already exists
    if not force_update:
        has_active, active_reason = has_active_openwiki_task(slug, repo_alias=repo_alias)
        if has_active:
            return False, active_reason

    if force_update:
        if auto_create_task:
            task = create_openwiki_task(
                slug,
                f"Force OpenWiki documentation sync requested{alias_label}",
                repo_dir,
                repo_alias=repo_alias,
            )
            if task and task.get("id"):
                return (
                    False,
                    f"Force update requested; created task '{task['id']}' in 'todo' for zf-builder{alias_label}.",
                )
        return True, f"Force update requested for board '{slug}'{alias_label}."

    # 4. Check git working tree cleanliness
    status_porcelain = _run_cmd(["git", "status", "--porcelain"], cwd=repo_dir)
    if status_porcelain:
        return (
            False,
            f"Working tree at {repo_dir} has uncommitted changes; skipping OpenWiki update to avoid conflicts.",
        )

    # 5. Get current HEAD
    head_sha = _run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_dir)
    if not head_sha:
        return False, f"Unable to resolve git HEAD at {repo_dir}; skipping."

    # 6. Resolve the last docs sync point
    sync_commit = ""
    marker_log = _run_cmd(
        ["git", "log", "-n", "200", "--format=%H%x09%s"],
        cwd=repo_dir,
    )
    for line in marker_log.splitlines():
        sha, _, subject = line.partition("\t")
        if subject.startswith("docs(openwiki): sync"):
            sync_commit = sha
            break
    last_openwiki_commit = _run_cmd(
        ["git", "log", "-1", "--format=%H", "--", "openwiki"],
        cwd=repo_dir,
    )

    state = load_state()
    board_state = state.get(slug, {})
    repo_state = board_state.get("repos", {}).get(repo_alias, {}) if repo_alias else {}
    last_scanned_sha = (
        repo_state.get("last_scanned_sha")
        or state.get(f"{slug}:{repo_alias}", {}).get("last_scanned_sha")
        or board_state.get("last_scanned_sha")
    )
    base_commit = sync_commit or last_scanned_sha or last_openwiki_commit

    if not base_commit:
        if auto_create_task:
            task = create_openwiki_task(
                slug, "Initial OpenWiki documentation sync", repo_dir, repo_alias=repo_alias
            )
            if task and task.get("id"):
                return (
                    False,
                    f"No previous openwiki commit history found; created task '{task['id']}' in 'todo' for zf-builder{alias_label}.",
                )
        return (
            True,
            f"No previous openwiki commit history found; documentation sync required{alias_label}.",
        )

    if head_sha == base_commit:
        return (
            False,
            f"No new commits on branch (HEAD={head_sha[:8]}); OpenWiki is up to date{alias_label}.",
        )

    diff_log = _run_cmd(
        [
            "git",
            "log",
            f"{base_commit}..HEAD",
            "--oneline",
            "--",
            ".",
            ":(exclude)openwiki",
        ],
        cwd=repo_dir,
    )
    if not diff_log:
        return (
            False,
            f"No code changes since last OpenWiki commit ({base_commit[:8]}); OpenWiki is up to date{alias_label}.",
        )

    commit_count = len(diff_log.splitlines())
    if auto_create_task:
        task = create_openwiki_task(slug, diff_log, repo_dir, repo_alias=repo_alias)
        if task and task.get("id"):
            return (
                False,
                f"Detected {commit_count} branch update(s) since {base_commit[:8]}; created task '{task['id']}' in 'todo' for zf-builder{alias_label}.",
            )
        else:
            return (
                False,
                f"Detected {commit_count} branch update(s) since {base_commit[:8]}; failed to create task on board{alias_label}.",
            )

    return (
        True,
        f"Detected {commit_count} branch update(s) since {base_commit[:8]}; documentation sync required{alias_label}.",
    )


def check_openwiki_gate(
    repo_dir: Path, board_slug: str | None = None, auto_create_task: bool = True
) -> tuple[bool, str]:
    """Evaluate whether OpenWiki update is needed across repositories on the board.

    Returns:
        (wake_agent, reason_message)
    """
    slug = board_slug or resolve_board_slug(repo_dir)

    force_update = "--force" in sys.argv or os.environ.get(
        "ZEROFACTORY_FORCE_OPENWIKI_UPDATE", ""
    ).lower() in ("1", "true", "yes")

    # Sync workspace registry so all repos on the board are linked in OpenWiki
    try:
        from dashboard.openwiki_service import sync_board_openwiki_workspace

        sync_board_openwiki_workspace(slug)
    except Exception:
        pass

    db_path = Path(os.environ.get("ZEROFACTORY_DB") or DEFAULT_DB_PATH)
    board_repos: list[dict[str, Any]] = []
    if db_path.exists():
        try:
            with sqlite3.connect(str(db_path), timeout=5.0) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT repo_alias, git_url FROM board_repositories WHERE board_slug = ? ORDER BY id ASC",
                    (slug,),
                )
                board_repos = [dict(r) for r in cursor.fetchall()]
        except Exception:
            pass

    if len(board_repos) > 1:
        # Evaluate all linked repositories on this board
        reasons = []
        any_wake = False
        tasks_created = 0

        for r in board_repos:
            alias = r["repo_alias"]
            r_path = resolve_repo_path(slug, alias, r.get("git_url", ""), repo_dir)
            if not r_path or not (r_path / "openwiki").is_dir():
                continue

            wake, reason = evaluate_single_repo_openwiki(
                r_path, slug, repo_alias=alias, force_update=force_update, auto_create_task=auto_create_task
            )
            reasons.append(f"[{alias}] {reason}")
            if wake:
                any_wake = True
            if "created task" in reason:
                tasks_created += 1

        summary = "\n".join(reasons) if reasons else f"No initialized openwiki/ repositories found on board '{slug}'."
        return any_wake, summary

    # Single-repo or test fallback
    first_alias = board_repos[0]["repo_alias"] if board_repos else None
    return evaluate_single_repo_openwiki(
        repo_dir, slug, repo_alias=first_alias, force_update=force_update, auto_create_task=auto_create_task
    )


def main() -> int:
    repo_dir = Path.cwd()
    wake, reason = check_openwiki_gate(repo_dir)
    print(reason)
    print(json.dumps({"wakeAgent": wake}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
