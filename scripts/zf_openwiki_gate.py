#!/usr/bin/env python3
"""ZeroFactory OpenWiki Pre-Screen & Wake-Gate.

Runs locally in the target repository workdir before the Hermes OpenWiki cron fires:
1. Verifies that `openwiki/` documentation directory exists for the board.
   If missing: outputs `{"wakeAgent": false}` (skips run until openwiki is initialized).
2. Checks git working tree cleanliness.
   If uncommitted changes exist: outputs `{"wakeAgent": false}` (prevents conflicts).
3. Compares HEAD commit against the last OpenWiki commit / state.
   If NO new non-openwiki commits exist on the branch:
   Outputs `{"wakeAgent": false}`. (0 LLM tokens!).
4. If branch updates exist (new commits landed on the default branch):
   Outputs `{"wakeAgent": true}` to wake the agent for doc synchronization.
"""

from __future__ import annotations

import json
import os
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
    board_slug: str, diff_log: str, repo_dir: Path
) -> dict[str, Any] | None:
    """Deterministically create a documentation sync task on the Kanban board for zf-builder."""
    task_desc = f"""Sync OpenWiki architecture documentation (`openwiki/`) with recent merged commits on the default branch.

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
    try:
        from dashboard.plugin_api import TaskCreate, create_task

        task = create_task(
            TaskCreate(
                board_slug=board_slug,
                title="docs(openwiki): sync architecture documentation with recent changes",
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
            task_id = f"zf-{board_slug[:3]}-{uuid.uuid4().hex[:8]}"
            now_ts = int(time.time())
            try:
                with sqlite3.connect(str(db_path), timeout=5.0) as conn:
                    conn.execute(
                        """
                        INSERT INTO tasks (id, board_slug, title, description, status, assignee, priority, created_at, updated_at)
                        VALUES (?, ?, ?, ?, 'todo', 'zf-builder', 'P2', ?, ?)
                        """,
                        (
                            task_id,
                            board_slug,
                            "docs(openwiki): sync architecture documentation with recent changes",
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
                cursor.execute("SELECT slug, git_url FROM boards")
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


def has_active_openwiki_task(board_slug: str) -> tuple[bool, str]:
    """Check if an OpenWiki setup or update task is already active on the board."""
    db_path = Path(os.environ.get("ZEROFACTORY_DB") or DEFAULT_DB_PATH)
    if not db_path.exists():
        return False, ""
    try:
        with sqlite3.connect(str(db_path), timeout=5.0) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT id, title, status FROM tasks
                WHERE board_slug = ?
                  AND status IN ('todo', 'ready', 'running', 'blocked', 'triage')
                  AND LOWER(title) LIKE '%openwiki%'
                ORDER BY created_at DESC LIMIT 1
                """,
                (board_slug,),
            )
            row = cursor.fetchone()
            if row:
                return (
                    True,
                    f"Board '{board_slug}' already has an active OpenWiki task '{row['id']}' ({row['title']}) in status '{row['status']}'; skipping.",
                )
    except Exception:
        pass
    return False, ""


def check_openwiki_gate(
    repo_dir: Path, board_slug: str | None = None, auto_create_task: bool = True
) -> tuple[bool, str]:
    """Evaluate whether OpenWiki update is needed and deterministically create task.

    Returns:
        (wake_agent, reason_message)
    """
    slug = board_slug or resolve_board_slug(repo_dir)

    # 1. Force check
    force_update = "--force" in sys.argv or os.environ.get(
        "ZEROFACTORY_FORCE_OPENWIKI_UPDATE", ""
    ).lower() in ("1", "true", "yes")

    # 2. Check if git repo
    git_dir = repo_dir / ".git"
    if not git_dir.exists():
        return False, f"Not a git repository at {repo_dir}; skipping."

    # 3. Check if openwiki/ directory exists
    openwiki_dir = repo_dir / "openwiki"
    if not openwiki_dir.is_dir():
        return (
            False,
            f"OpenWiki not initialized for board '{slug}' (no openwiki/ directory found); skipping.",
        )

    # 4. Check if active OpenWiki task already exists on the board (TODO, Running, Blocked, Ready, Triage)
    if not force_update:
        has_active, active_reason = has_active_openwiki_task(slug)
        if has_active:
            return False, active_reason

    if force_update:
        if auto_create_task:
            task = create_openwiki_task(
                slug, "Force OpenWiki documentation sync requested", repo_dir
            )
            if task and task.get("id"):
                return (
                    False,
                    f"Force update requested; created task '{task['id']}' in 'todo' for zf-builder.",
                )
        return True, f"Force update requested for board '{slug}'."

    # 5. Check git working tree cleanliness
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

    # 6. Check last openwiki commit from git log (or state fallback)
    last_openwiki_commit = _run_cmd(
        ["git", "log", "-1", "--format=%H", "--", "openwiki"],
        cwd=repo_dir,
    )

    state = load_state()
    board_state = state.get(slug, {})
    last_scanned_sha = board_state.get("last_scanned_sha")
    base_commit = last_openwiki_commit or last_scanned_sha

    if not base_commit:
        if auto_create_task:
            task = create_openwiki_task(
                slug, "Initial OpenWiki documentation sync", repo_dir
            )
            if task and task.get("id"):
                return (
                    False,
                    f"No previous openwiki commit history found; created task '{task['id']}' in 'todo' for zf-builder.",
                )
        return (
            True,
            "No previous openwiki commit history found; documentation sync required.",
        )

    if head_sha == base_commit:
        return (
            False,
            f"No new commits on branch (HEAD={head_sha[:8]}); OpenWiki is up to date.",
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
            f"No code changes since last OpenWiki commit ({base_commit[:8]}); OpenWiki is up to date.",
        )

    commit_count = len(diff_log.splitlines())
    if auto_create_task:
        task = create_openwiki_task(slug, diff_log, repo_dir)
        if task and task.get("id"):
            return (
                False,
                f"Detected {commit_count} branch update(s) since {base_commit[:8]}; created task '{task['id']}' in 'todo' for zf-builder.",
            )
        else:
            return (
                False,
                f"Detected {commit_count} branch update(s) since {base_commit[:8]}; failed to create task on board.",
            )

    return (
        True,
        f"Detected {commit_count} branch update(s) since {base_commit[:8]}; documentation sync required.",
    )


def main() -> int:
    repo_dir = Path.cwd()
    wake, reason = check_openwiki_gate(repo_dir)
    print(reason)
    print(json.dumps({"wakeAgent": wake}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
