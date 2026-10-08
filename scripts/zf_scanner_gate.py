#!/usr/bin/env python3
"""ZeroFactory Codebase Scanner Pre-Screen & Wake-Gate.

Runs locally in the target repository workdir before the Hermes LLM scanner fires:
1. Compares current Git HEAD & working tree against `~/.hermes/scanner_state.json`.
2. If NO new commits or working tree modifications exist:
   Outputs `{"wakeAgent": false}`.
   Hermes detects this and SKIPS the LLM run entirely (0 tokens used!).
3. If new changes exist:
   Extracts recent git log, diffstat, modified file snippets, and existing task list.
   Outputs `{"wakeAgent": true}`.
   Hermes injects the pre-computed findings directly into prompt context, enabling
   single-turn task creation without multi-turn tool loops.
"""

from __future__ import annotations

import fcntl
import json
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any

STATE_FILE = Path.home() / ".hermes" / "scanner_state.json"
DEFAULT_DB_PATH = Path.home() / ".hermes" / "zerofactory.db"


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


def scan_code_markers(repo_dir: Path) -> str:
    """Scan tracked source files for real TODO/FIXME/HACK debt markers.

    The pattern is word-boundary anchored and case-sensitive so identifiers
    (e.g. ``DEFAULT_IDLE_SCAN_MAX_TODO``) and prose can never match, while
    genuine comments like ``# TODO:`` / ``// FIXME:`` / ``/* HACK */`` do.
    Returns the git grep output (file:line:match per line) or "" when clean.
    """
    return _run_cmd(
        [
            "git",
            "grep",
            "-n",
            "-E",
            r"\bTODO\b|\bFIXME\b|\bHACK\b",
            "--",
            "*.py",
            "*.ts",
            "*.js",
            "*.go",
            "*.rs",
        ],
        cwd=repo_dir,
    )


def get_state_file() -> Path:
    env_override = os.environ.get("ZEROFACTORY_SCANNER_STATE")
    return Path(env_override) if env_override else STATE_FILE


def _state_lock_path(state_file: Path) -> Path:
    """Sidecar lock file path for atomic read-modify-write of the state file.

    The lock is a separate file (not the state file itself) so `os.replace` of
    the state file never invalidates a lock held on it mid-write.
    """
    return state_file.with_name(state_file.name + ".lock")


def load_state() -> dict[str, Any]:
    # The state file is only ever published atomically (write_state_atomic ->
    # os.replace), so a reader can never observe a torn/partial JSON document.
    sf = get_state_file()
    if sf.exists():
        try:
            data = json.loads(sf.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}
    return {}


def _atomic_write_json(sf: Path, data: dict[str, Any]) -> None:
    """Write ``data`` to ``sf`` atomically: temp file + fsync + os.replace.

    Same pattern as ``builtin_cron.save_jobs_to_file`` — the target is replaced
    (renamed) rather than overwritten in place, so a concurrent reader can
    never observe a torn/partial JSON document.
    """
    sf.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2)
    temp_fd, temp_path = tempfile.mkstemp(
        dir=str(sf.parent), prefix="scanner_state_", suffix=".tmp"
    )
    try:
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            f.write(payload)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, str(sf))
    except BaseException:
        try:
            os.unlink(temp_path)
        except OSError:
            pass
        raise


def write_state_atomic(state: dict[str, Any]) -> bool:
    """Atomically persist the full state dict (temp file + os.replace)."""
    try:
        _atomic_write_json(get_state_file(), state)
        return True
    except Exception:
        return False


def save_state(state: dict[str, Any]) -> None:
    write_state_atomic(state)


def _locked_state_rmw(mutate: Any) -> bool:
    """Read-modify-write the state file under an exclusive sidecar flock.

    ``mutate`` receives the parsed state dict (freshly loaded under the lock)
    and may mutate it in place; the result is then published atomically. The
    lock is a SEPARATE sidecar file because the state file itself is replaced
    via os.replace — locking the state file would not protect across the
    rename. Returns True on success.
    """
    sf = get_state_file()
    lock_path = _state_lock_path(sf)
    with open(str(lock_path), "a+", encoding="utf-8") as lock_f:
        fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
        try:
            data = {}
            if sf.exists():
                try:
                    parsed = json.loads(sf.read_text(encoding="utf-8"))
                    if isinstance(parsed, dict):
                        data = parsed
                except Exception:
                    data = {}
            mutate(data)
            _atomic_write_json(sf, data)
        finally:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
    return True


def mark_task_created(board_slug: str, repo_alias: str | None = None) -> bool:
    """Atomically flag that a task was created for ``board_slug`` (and optional ``repo_alias``).

    Called by the dashboard after task creation. The entire read-modify-write
    happens under an exclusive ``fcntl.flock``, so concurrent writers (this
    dashboard handler and the scanner gate cron) can never lose each other's
    updates. Returns True when the flag was recorded.
    """
    if not board_slug:
        return False

    def _mutate(data: dict[str, Any]) -> None:
        board_state = data.setdefault(board_slug, {})
        if isinstance(board_state, dict):
            board_state["task_created"] = True
            board_state["scan_attempts"] = 0
            if repo_alias:
                repos_state = board_state.setdefault("repos", {})
                r_state = repos_state.setdefault(repo_alias, {})
                r_state["task_created"] = True
                r_state["scan_attempts"] = 0

    try:
        return _locked_state_rmw(_mutate)
    except Exception:
        return False


def is_llm_reachable(timeout: float = 2.0) -> bool:
    """Quick probe to verify LLM inference server is reachable before waking agent."""
    if os.environ.get("ZEROFACTORY_SKIP_LLM_PROBE"):
        return True

    import urllib.request

    base_url = os.environ.get("OPENAI_BASE_URL")
    if not base_url:
        for cfg_path in [
            Path.home() / ".hermes" / "profiles" / "zf-orchestrator" / "config.yaml",
            Path.home() / ".hermes" / "config.yaml",
        ]:
            if cfg_path.exists():
                try:
                    for line in cfg_path.read_text(encoding="utf-8").splitlines():
                        if "base_url:" in line:
                            base_url = line.split(":", 1)[1].strip().strip("\"'")
                            break
                    if base_url:
                        break
                except Exception:
                    pass
    if not base_url:
        return True

    probe_url = base_url.rstrip("/") + "/models"
    try:
        req = urllib.request.Request(probe_url, headers={"User-Agent": "zf-gate-probe"})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.status < 500
    except Exception:
        return False


def _auto_sync_repo(repo_dir: Path) -> None:
    """Safely fetch and fast-forward pull the default branch if worktree is clean."""
    try:
        # 1. Check if git remote origin exists
        remotes = _run_cmd(["git", "remote"], cwd=repo_dir).split()
        if "origin" not in remotes:
            return

        # 2. Check worktree cleanliness - never auto-pull if uncommitted changes exist
        status = _run_cmd(["git", "status", "--porcelain"], cwd=repo_dir)
        if status.strip():
            return

        # 3. Detect default branch: try origin/HEAD symbolic ref, fallback to checking main/master
        default_branch = ""
        sym_ref = _run_cmd(
            ["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=repo_dir
        )
        if sym_ref and "/" in sym_ref:
            default_branch = sym_ref.split("/", 1)[1].strip()

        if not default_branch:
            for cand in ("main", "master"):
                check_branch = subprocess.run(
                    [
                        "git",
                        "show-ref",
                        "--verify",
                        "--quiet",
                        f"refs/remotes/origin/{cand}",
                    ],
                    cwd=str(repo_dir),
                    timeout=3,
                )
                if check_branch.returncode == 0:
                    default_branch = cand
                    break

        if not default_branch:
            default_branch = "main"

        # 4. Check currently checked out branch - only sync if on the default branch
        curr_branch = _run_cmd(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir
        ).strip()
        if curr_branch != default_branch:
            return

        # 5. Fetch from origin for default branch (bounded 10s timeout)
        fetch_res = subprocess.run(
            ["git", "fetch", "origin", default_branch],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=10,
        )
        if fetch_res.returncode != 0:
            return

        # 6. Fast-forward merge origin/<default_branch> (bounded 5s timeout)
        subprocess.run(
            ["git", "merge", "--ff-only", f"origin/{default_branch}"],
            cwd=str(repo_dir),
            capture_output=True,
            text=True,
            timeout=5,
        )
    except Exception:
        pass


def get_active_pipeline_task_count(board_slug: str) -> int:
    """Count tasks that actively occupy the builder pipeline (running, todo).

    Blocked tasks (e.g. PRs awaiting human review) and done tasks do not occupy
    builder worker capacity, so they do not block idle improvement scanning.
    """
    db_path = Path(os.environ.get("ZEROFACTORY_DB") or DEFAULT_DB_PATH)
    if not db_path.exists():
        return 0
    try:
        with sqlite3.connect(str(db_path), timeout=5.0) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT COUNT(*) FROM tasks WHERE board_slug = ? AND status IN ('running', 'todo')",
                (board_slug,),
            )
            row = cursor.fetchone()
            return int(row[0]) if row else 0
    except Exception:
        return 0


def get_board_pipeline_capacity(board_slug: str) -> dict[str, Any]:
    """Get active pipeline task counts and capacity-driven idle scan settings."""
    db_path = Path(os.environ.get("ZEROFACTORY_DB") or DEFAULT_DB_PATH)
    res = {
        "running": 0,
        "todo": 0,
        "max_concurrent_running": 1,
        "scan_on_idle": False,
        "idle_scan_cooldown_minutes": 15,
        "idle_scan_max_todo": 2,
    }
    if db_path.exists():
        try:
            with sqlite3.connect(str(db_path), timeout=5.0) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT max_concurrent_running FROM boards WHERE slug = ?",
                    (board_slug,),
                )
                b_row = cursor.fetchone()
                if b_row and b_row[0]:
                    res["max_concurrent_running"] = max(1, int(b_row[0]))
                cursor.execute(
                    "SELECT status, COUNT(*) FROM tasks WHERE board_slug = ? AND status IN ('running', 'todo') GROUP BY status",
                    (board_slug,),
                )
                for row in cursor.fetchall():
                    if row[0] == "running":
                        res["running"] = int(row[1])
                    elif row[0] == "todo":
                        res["todo"] = int(row[1])
        except Exception:
            pass

    try:
        from cron.definitions import get_scanner_cron_config

        cron_cfg = get_scanner_cron_config(board_slug)
        res["scan_on_idle"] = bool(cron_cfg.get("scan_on_idle", False))
        res["idle_scan_cooldown_minutes"] = int(
            cron_cfg.get("idle_scan_cooldown_minutes", 15)
        )
        res["idle_scan_max_todo"] = int(cron_cfg.get("idle_scan_max_todo", 2))
    except Exception:
        pass

    return res


def get_existing_task_titles(board_slug: str) -> list[str]:
    db_path = Path(os.environ.get("ZEROFACTORY_DB") or DEFAULT_DB_PATH)
    if not db_path.exists():
        return []
    try:
        with sqlite3.connect(str(db_path), timeout=5.0) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT title FROM tasks WHERE board_slug = ? AND status != 'done' ORDER BY created_at DESC LIMIT 25",
                (board_slug,),
            )
            return [row[0] for row in cursor.fetchall()]
    except Exception:
        return []


def has_task_on_or_after_commit(
    board_slug: str, commit_time: int, repo_alias: str | None = None
) -> bool:
    """Check if any task was created for this board on or after the commit timestamp."""
    if commit_time <= 0:
        return False
    db_path = Path(os.environ.get("ZEROFACTORY_DB") or DEFAULT_DB_PATH)
    if not db_path.exists():
        return False
    try:
        with sqlite3.connect(str(db_path), timeout=5.0) as conn:
            cursor = conn.cursor()
            if repo_alias:
                cursor.execute(
                    "SELECT 1 FROM tasks WHERE board_slug = ? AND (repo_alias = ? OR repo_alias IS NULL) AND created_at >= ? LIMIT 1",
                    (board_slug, repo_alias, commit_time),
                )
            else:
                cursor.execute(
                    "SELECT 1 FROM tasks WHERE board_slug = ? AND created_at >= ? LIMIT 1",
                    (board_slug, commit_time),
                )
            return cursor.fetchone() is not None
    except Exception:
        return False


def get_board_repositories(board_slug: str) -> list[dict[str, Any]]:
    """Fetch all repositories associated with a board."""
    db_path = Path(os.environ.get("ZEROFACTORY_DB") or DEFAULT_DB_PATH)
    if not db_path.exists():
        return []
    try:
        with sqlite3.connect(str(db_path), timeout=5.0) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, board_slug, repo_alias, git_url, target_branch FROM board_repositories WHERE board_slug = ? ORDER BY id ASC",
                (board_slug,),
            )
            return [dict(r) for r in cursor.fetchall()]
    except Exception:
        return []


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

    # 2. Check standard ~/git directories
    home = Path.home()
    candidates: list[Path] = [
        home / "git" / repo_alias,
        home / "git" / board_slug / repo_alias,
    ]

    owner, repo_name = "", ""
    if git_url:
        cleaned_url = re.sub(r"\.git$", "", git_url.strip().rstrip("/"))
        parts = cleaned_url.replace(":", "/").split("/")
        if len(parts) >= 1:
            repo_name = parts[-1]
            candidates.append(home / "git" / repo_name)
        if len(parts) >= 2:
            owner = parts[-2]
            candidates.append(home / "git" / owner / repo_name)
            candidates.append(home / "git" / f"{owner}-{repo_name}")

    git_root = home / "git"
    if git_root.is_dir():
        try:
            for child in git_root.iterdir():
                if child.is_dir():
                    sub = child / repo_alias
                    if sub not in candidates:
                        candidates.append(sub)
                    if repo_name:
                        sub_repo = child / repo_name
                        if sub_repo not in candidates:
                            candidates.append(sub_repo)
        except Exception:
            pass

    for cand in candidates:
        if cand.is_dir() and (cand / ".git").exists():
            return cand.resolve()

    if current_dir and (current_dir / ".git").exists():
        return current_dir

    return None


def resolve_board_slug(repo_dir: Path) -> str:
    # The first positional arg is the board slug. Skip flag tokens such as
    # `--force` (or any `-`-prefixed arg) so a flag is never mistaken for a slug;
    # the flag falls through to the ZEROFACTORY_BOARD env / DB / repo-name fallback.
    for arg in sys.argv[1:]:
        if not arg.startswith("-") and arg.strip():
            return arg.strip()
    if os.environ.get("ZEROFACTORY_BOARD"):
        return os.environ["ZEROFACTORY_BOARD"].strip()

    # Match repo directory against registered boards in zerofactory.db
    db_path = Path(os.environ.get("ZEROFACTORY_DB") or DEFAULT_DB_PATH)
    if db_path.exists():
        try:
            with sqlite3.connect(str(db_path), timeout=5.0) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    "SELECT b.slug, br.git_url FROM boards b LEFT JOIN board_repositories br ON b.slug = br.board_slug"
                )
                rows = cursor.fetchall()
                # 1. Match by slug == repo name or slug ends with repo name
                for slug, _ in rows:
                    if slug and repo_dir.name.lower() in (
                        slug.lower(),
                        slug.split("-")[-1].lower(),
                    ):
                        return slug
                # 2. Match by git remote origin url (supports both HTTPS and SSH)
                remote_url = _run_cmd(
                    ["git", "config", "--get", "remote.origin.url"], cwd=repo_dir
                )
                if remote_url:

                    def _normalize_repo_slug(url_str: str) -> str:
                        cleaned = re.sub(r"\.git$", "", url_str.strip().rstrip("/"))
                        parts = cleaned.replace(":", "/").split("/")
                        if len(parts) >= 2:
                            return f"{parts[-2]}/{parts[-1]}".lower()
                        return cleaned.lower()

                    norm_remote = _normalize_repo_slug(remote_url)
                    for slug, git_url in rows:
                        if git_url:
                            norm_board_git = _normalize_repo_slug(git_url)
                            if (
                                norm_remote == norm_board_git
                                or norm_remote in git_url.lower()
                            ):
                                return slug
                # Fallback to first board if available
                if rows and rows[0][0]:
                    return rows[0][0]
        except Exception:
            pass

    return repo_dir.name if repo_dir.name else "zerofactory"


def run_scanner_gate() -> int:
    repo_dir = Path.cwd()
    board_slug = resolve_board_slug(repo_dir)

    # Sync OpenWiki workspace registry so sibling repositories are unified
    try:
        from dashboard.openwiki_service import sync_board_openwiki_workspace

        sync_board_openwiki_workspace(board_slug)
    except Exception:
        pass

    db_repos = get_board_repositories(board_slug)
    repo_entries: list[dict[str, Any]] = []

    if db_repos:
        for r in db_repos:
            alias = r["repo_alias"]
            r_url = r.get("git_url", "")
            r_path = resolve_repo_path(board_slug, alias, r_url, repo_dir)
            if r_path and (r_path / ".git").exists():
                repo_entries.append(
                    {
                        "repo_alias": alias,
                        "path": r_path,
                        "git_url": r_url,
                    }
                )

    if not repo_entries:
        # Fallback to current directory as the single repo
        alias = repo_dir.name if repo_dir.name else "default"
        repo_entries = [{"repo_alias": alias, "path": repo_dir, "git_url": ""}]

    now_ts = int(time.time())
    retry_cooldown = int(os.environ.get("ZEROFACTORY_SCAN_RETRY_COOLDOWN", "1800"))
    max_attempts = int(os.environ.get("ZEROFACTORY_SCAN_MAX_ATTEMPTS", "3"))
    reset_cooldown = int(os.environ.get("ZEROFACTORY_SCAN_RESET_COOLDOWN", "7200"))

    state = load_state()
    board_state = state.get(board_slug, {})
    repos_state = board_state.get("repos", {})

    inspected_repos: list[dict[str, Any]] = []
    for r in repo_entries:
        r_path = r["path"]
        alias = r["repo_alias"]
        _auto_sync_repo(r_path)

        head_sha = _run_cmd(["git", "rev-parse", "HEAD"], cwd=r_path)
        status_porcelain = _run_cmd(
            ["git", "status", "--porcelain", "-uno"], cwd=r_path
        )

        if not head_sha:
            continue

        r_state = repos_state.get(alias, {})
        last_sha = (
            r_state["last_scanned_sha"]
            if "last_scanned_sha" in r_state
            else (
                board_state.get("last_scanned_sha")
                if len(repo_entries) == 1
                else None
            )
        )
        last_status = (
            r_state["last_status"]
            if "last_status" in r_state
            else (
                board_state.get("last_status")
                if len(repo_entries) == 1
                else None
            )
        )

        is_same_commit = head_sha == last_sha
        is_same_status = status_porcelain == last_status
        has_changes = not (is_same_commit and is_same_status)
        is_baseline = last_sha is None

        commit_time_str = _run_cmd(
            ["git", "log", "-1", "--format=%ct", head_sha], cwd=r_path
        )
        commit_time = int(commit_time_str) if commit_time_str.isdigit() else 0

        inspected_repos.append(
            {
                "repo_alias": alias,
                "path": r_path,
                "git_url": r["git_url"],
                "head_sha": head_sha,
                "status_porcelain": status_porcelain,
                "r_state": r_state,
                "last_sha": last_sha,
                "last_status": last_status,
                "is_same_commit": is_same_commit,
                "is_same_status": is_same_status,
                "has_changes": has_changes,
                "is_baseline": is_baseline,
                "commit_time": commit_time,
                "last_scan_at": int(
                    r_state.get(
                        "last_scan_at",
                        board_state.get("last_scan_at", 0)
                        if len(repo_entries) == 1
                        else 0,
                    )
                ),
                "scan_attempts": int(
                    r_state.get(
                        "scan_attempts",
                        board_state.get("scan_attempts", 1)
                        if len(repo_entries) == 1
                        else 1,
                    )
                ),
            }
        )

    if not inspected_repos:
        print(
            f"Warning: Not a valid git repository at {repo_dir}. Running standard inspection."
        )
        print(json.dumps({"wakeAgent": True}))
        return 0

    # Fetch active pipeline tasks (running, todo) to determine if pipeline is busy
    active_in_flight = get_active_pipeline_task_count(board_slug)

    # Fetch existing task titles to prevent duplicate suggestions
    existing_tasks = get_existing_task_titles(board_slug)

    # Fetch capacity-driven idle scan settings and task breakdown
    capacity = get_board_pipeline_capacity(board_slug)

    # Check for forced or idle scan
    force_scan = "--force" in sys.argv or os.environ.get(
        "ZEROFACTORY_FORCE_SCAN", ""
    ).lower() in ("1", "true", "yes")
    is_idle_scan = "--idle" in sys.argv or os.environ.get(
        "ZEROFACTORY_IDLE_SCAN", ""
    ).lower() in ("1", "true", "yes")

    target_repo = None
    trigger_reason = ""

    # Decision tree:
    # 1. Force scan
    if force_scan:
        target_repo = inspected_repos[0]
        trigger_reason = f"FORCE_SCAN_TRIGGERED: Force scan requested for board '{board_slug}' (targeting '{target_repo['repo_alias']}')."

    # 2. Baseline or newly changed repositories
    if not target_repo:
        changed = [r for r in inspected_repos if r["has_changes"] or r["is_baseline"]]
        if changed:
            baseline = [r for r in changed if r["is_baseline"]]
            if baseline:
                target_repo = baseline[0]
                trigger_reason = f"BASELINE_SCAN_TRIGGERED: Board '{board_slug}' repository '{target_repo['repo_alias']}' has never been scanned. Initiating baseline codebase inspection."
            else:
                target_repo = max(changed, key=lambda r: r["commit_time"])
                trigger_reason = f"CHANGES_DETECTED: Repository '{target_repo['repo_alias']}' has updates ({target_repo['head_sha'][:8]})."

    # 3. Steady state (all repos unchanged)
    if not target_repo:
        scan_on_idle = capacity.get("scan_on_idle", False)
        running_count = capacity.get("running", 0)
        todo_count = capacity.get("todo", 0)
        max_concurrent = capacity.get("max_concurrent_running", 1)
        max_todo = capacity.get("idle_scan_max_todo", 2)
        idle_cooldown = capacity.get("idle_scan_cooldown_minutes", 15) * 60

        if is_idle_scan:
            target_repo = min(inspected_repos, key=lambda r: r["last_scan_at"])
            trigger_reason = f"CAPACITY_DRIVEN_SCAN_TRIGGERED: Dispatcher authorized idle scan for board '{board_slug}' (active running={running_count} < {max_concurrent}, targeting '{target_repo['repo_alias']}')."
        elif scan_on_idle:
            if running_count >= max_concurrent or todo_count >= max_todo:
                print(
                    f"NO_CHANGES_DETECTED: Repositories unchanged; pipeline busy on board '{board_slug}' (running={running_count}/{max_concurrent}, todo={todo_count}/{max_todo})."
                )
                print(json.dumps({"wakeAgent": False}))
                return 0

            last_board_scan_at = int(board_state.get("last_scan_at", 0))
            if (now_ts - last_board_scan_at) < idle_cooldown:
                print(
                    f"SCAN_COOLDOWN_ACTIVE: Board '{board_slug}' is idle (running={running_count} < {max_concurrent}), "
                    f"but cooldown active ({now_ts - last_board_scan_at}s < {idle_cooldown}s); waiting."
                )
                print(json.dumps({"wakeAgent": False}))
                return 0

            target_repo = min(inspected_repos, key=lambda r: r["last_scan_at"])
            trigger_reason = (
                f"CAPACITY_DRIVEN_SCAN_TRIGGERED: Board '{board_slug}' is idle "
                f"(running={running_count} < {max_concurrent}, todo={todo_count} < {max_todo}); "
                f"cooldown elapsed ({now_ts - last_board_scan_at}s >= {idle_cooldown}s). Initiating idle improvement scan on '{target_repo['repo_alias']}'."
            )
        else:
            if active_in_flight > 0:
                print(
                    f"NO_CHANGES_DETECTED: Repositories unchanged since last scan; active pipeline tasks ({active_in_flight}) on board '{board_slug}'."
                )
                print(json.dumps({"wakeAgent": False}))
                return 0

            all_had_tasks = True
            retry_candidates = []
            for r in inspected_repos:
                has_tasks = (
                    bool(r["r_state"].get("task_created"))
                    or bool(board_state.get("task_created"))
                    or has_task_on_or_after_commit(
                        board_slug, r["commit_time"], repo_alias=r["repo_alias"]
                    )
                )
                if not has_tasks:
                    all_had_tasks = False
                    retry_candidates.append(r)

            if all_had_tasks:
                print(
                    f"NO_CHANGES_DETECTED: Repositories on board '{board_slug}' unchanged since last scan; board already scanned."
                )
                print(json.dumps({"wakeAgent": False}))
                return 0

            r_candidate = retry_candidates[0]
            last_scan_at = r_candidate["last_scan_at"]
            attempts = r_candidate["scan_attempts"]

            if (now_ts - last_scan_at) < retry_cooldown:
                print(
                    f"SCAN_COOLDOWN_ACTIVE: Scan on '{r_candidate['repo_alias']}' ({r_candidate['head_sha'][:8]}) recently attempted ({now_ts - last_scan_at}s ago < {retry_cooldown}s); waiting for cooldown."
                )
                print(json.dumps({"wakeAgent": False}))
                return 0

            if attempts >= max_attempts:
                if (now_ts - last_scan_at) >= reset_cooldown:
                    attempts = 0
                    r_candidate["r_state"]["scan_attempts"] = 0
                else:
                    print(
                        f"NO_CHANGES_DETECTED: Repository '{r_candidate['repo_alias']}' at {r_candidate['head_sha'][:8]} unchanged after {attempts} scan attempts without tasks; suppressing."
                    )
                    print(json.dumps({"wakeAgent": False}))
                    return 0

            target_repo = r_candidate
            trigger_reason = f"RETRY_SCAN_TRIGGERED: Previous scan on '{target_repo['repo_alias']}' ({target_repo['head_sha'][:8]}) produced no tasks and board has 0 active tasks (attempt {attempts + 1}/{max_attempts}). Initiating re-scan."

    if not target_repo:
        print(json.dumps({"wakeAgent": False}))
        return 0

    # Pre-flight LLM probe: verify inference endpoint is reachable before committing state and waking agent
    if not is_llm_reachable():
        print(
            "LLM_UNREACHABLE: Inference endpoint is unreachable; deferring scan without consuming attempts."
        )
        print(json.dumps({"wakeAgent": False}))
        return 0

    t_alias = target_repo["repo_alias"]
    t_path = target_repo["path"]
    t_head = target_repo["head_sha"]
    t_status = target_repo["status_porcelain"]
    t_is_same = target_repo["is_same_commit"]

    new_attempts = (int(target_repo["r_state"].get("scan_attempts", 0)) + 1) if t_is_same else 1
    target_r_state = repos_state.setdefault(t_alias, {})
    target_r_state["last_scanned_sha"] = t_head
    target_r_state["last_status"] = t_status
    target_r_state["last_scan_at"] = now_ts
    target_r_state["scan_attempts"] = new_attempts
    if not t_is_same:
        target_r_state.pop("task_created", None)

    board_state["repos"] = repos_state
    board_state["last_scanned_sha"] = t_head
    board_state["last_status"] = t_status
    board_state["last_scan_at"] = now_ts
    board_state["scan_attempts"] = new_attempts
    if not t_is_same:
        board_state.pop("task_created", None)

    state[board_slug] = board_state
    save_state(state)

    # Collect pre-digested intelligence to pass to the LLM
    excluded_diff_pathspecs = [
        ":!*.lock",
        ":!*package-lock.json",
        ":!*pnpm-lock.yaml",
        ":!*yarn.lock",
        ":!*.min.*",
        ":!*.map",
    ]
    log_summary = _run_cmd(["git", "log", "-n", "5", "--oneline"], cwd=t_path)
    diffstat = _run_cmd(
        ["git", "diff", "--stat", "HEAD~1..HEAD", "--", *excluded_diff_pathspecs],
        cwd=t_path,
    )
    raw_diff = _run_cmd(
        ["git", "diff", "-U2", "HEAD~1..HEAD", "--", *excluded_diff_pathspecs],
        cwd=t_path,
    )

    # Cap diff to prevent prompt overflow
    diff_lines = raw_diff.splitlines()[:80]
    truncated_diff = "\n".join(diff_lines)
    if len(diff_lines) == 80:
        truncated_diff += "\n... [diff truncated for token efficiency]"

    # Check for uncommitted files
    is_worktree_clean = len(t_status.strip()) == 0
    uncommitted_summary = ""
    if not is_worktree_clean:
        uncommitted_summary = (
            f"### Uncommitted Changes:\n```\n{t_status[:1000]}\n```\n"
        )

    # Search for new TODO / FIXME in tracked files
    todo_matches = scan_code_markers(t_path)
    todo_sample = "\n".join(todo_matches.splitlines()[:15]) if todo_matches else "None"

    tasks_block = (
        "\n".join([f"- {t}" for t in existing_tasks])
        if existing_tasks
        else "(No active tasks)"
    )

    if trigger_reason:
        print(f"[{trigger_reason}]")
    print("### 🔍 Pre-Screen Intelligence Package (Zero-Token Ingested)")
    print(f"**Board:** `{board_slug}` | **Target Repository:** `{t_alias}` (`{t_path.name}`) (Commit: `{t_head[:8]}`)")
    print()
    print("#### Recent Commits:")
    print(f"```\n{log_summary}\n```")
    print()
    if uncommitted_summary:
        print(uncommitted_summary)
    if diffstat:
        print("#### Recent Diff Stat:")
        print(f"```\n{diffstat}\n```")
        print()
    if truncated_diff:
        print("#### Recent Code Changes:")
        print(f"```diff\n{truncated_diff}\n```")
        print()
    if todo_matches:
        print("#### Code Marker Warnings (TODO/FIXME):")
        print(f"```\n{todo_sample}\n```")
        print()
    print("#### Currently Open Kanban Tasks (DO NOT DUPLICATE THESE):")
    print(tasks_block)
    print()

    if not existing_tasks:
        candidate_files = _run_cmd(
            ["git", "ls-files", "*.py", "*.ts", "*.js", "*.mjs"], cwd=t_path
        )
        files_sample = (
            "\n".join([f"- `{f}`" for f in candidate_files.splitlines()[:20]])
            if candidate_files
            else "(None)"
        )
        print("#### Baseline Codebase Source Files to Inspect:")
        print(files_sample)
        print()
        print("---")
        print(
            f'Instructions for Agent: Baseline scan for board \'{board_slug}\' repository \'{t_alias}\' (0 active tasks). Inspect candidate source files above for genuine bugs, missing tests, or error-handling debt. Create exactly 1 task using `hermes zerofactory create "<issue title>" --description "<details>" --board "{board_slug}" --repo "{t_alias}" --files "<files>" --category "<category>" --priority P0 --status todo --assignee zf-builder`.'
        )
    else:
        print("---")
        print(
            f'Instructions for Agent: Review the codebase for board \'{board_slug}\' repository \'{t_alias}\' for genuine code quality improvements, refactoring, performance, architecture, or test debt. If warranted, create AT MOST 1 task targeting this repository using `hermes zerofactory create "<issue title>" --description "<details>" --board "{board_slug}" --repo "{t_alias}" --files "<files>" --category "<category>" --priority P0 --status todo --assignee zf-builder` and finish. Do NOT duplicate open tasks.'
        )
    print()

    # Emit wakeAgent: true to invoke LLM with this rich context
    print(json.dumps({"wakeAgent": True}))
    return 0


if __name__ == "__main__":
    sys.exit(run_scanner_gate())
