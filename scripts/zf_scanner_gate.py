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
from typing import Any, Dict, List, Optional

STATE_FILE = Path.home() / ".hermes" / "scanner_state.json"
DEFAULT_DB_PATH = Path.home() / ".hermes" / "zerofactory.db"


def _run_cmd(cmd: List[str], cwd: Optional[Path] = None) -> str:
    try:
        res = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )
        return res.stdout.strip() if res.returncode == 0 else ""
    except Exception:
        return ""


def get_state_file() -> Path:
    env_override = os.environ.get("ZEROFACTORY_SCANNER_STATE")
    return Path(env_override) if env_override else STATE_FILE


def _state_lock_path(state_file: Path) -> Path:
    """Sidecar lock file path for atomic read-modify-write of the state file.

    The lock is a separate file (not the state file itself) so `os.replace` of
    the state file never invalidates a lock held on it mid-write.
    """
    return state_file.with_name(state_file.name + ".lock")


def load_state() -> Dict[str, Any]:
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


def _atomic_write_json(sf: Path, data: Dict[str, Any]) -> None:
    """Write ``data`` to ``sf`` atomically: temp file + fsync + os.replace.

    Same pattern as ``builtin_cron.save_jobs_to_file`` — the target is replaced
    (renamed) rather than overwritten in place, so a concurrent reader can
    never observe a torn/partial JSON document.
    """
    sf.parent.mkdir(parents=True, exist_ok=True)
    payload = json.dumps(data, indent=2)
    temp_fd, temp_path = tempfile.mkstemp(dir=str(sf.parent), prefix="scanner_state_", suffix=".tmp")
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


def write_state_atomic(state: Dict[str, Any]) -> bool:
    """Atomically persist the full state dict (temp file + os.replace)."""
    try:
        _atomic_write_json(get_state_file(), state)
        return True
    except Exception:
        return False


def save_state(state: Dict[str, Any]) -> None:
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


def mark_task_created(board_slug: str) -> bool:
    """Atomically flag that a task was created for ``board_slug``.

    Called by the dashboard after task creation. The entire read-modify-write
    happens under an exclusive ``fcntl.flock``, so concurrent writers (this
    dashboard handler and the scanner gate cron) can never lose each other's
    updates. Returns True when the flag was recorded.
    """
    if not board_slug:
        return False

    def _mutate(data: Dict[str, Any]) -> None:
        board_state = data.setdefault(board_slug, {})
        if isinstance(board_state, dict):
            board_state["task_created"] = True
            board_state["scan_attempts"] = 0

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
        sym_ref = _run_cmd(["git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"], cwd=repo_dir)
        if sym_ref and "/" in sym_ref:
            default_branch = sym_ref.split("/", 1)[1].strip()

        if not default_branch:
            for cand in ("main", "master"):
                check_branch = subprocess.run(
                    ["git", "show-ref", "--verify", "--quiet", f"refs/remotes/origin/{cand}"],
                    cwd=str(repo_dir), timeout=3
                )
                if check_branch.returncode == 0:
                    default_branch = cand
                    break

        if not default_branch:
            default_branch = "main"

        # 4. Check currently checked out branch - only sync if on the default branch
        curr_branch = _run_cmd(["git", "rev-parse", "--abbrev-ref", "HEAD"], cwd=repo_dir).strip()
        if curr_branch != default_branch:
            return

        # 5. Fetch from origin for default branch (bounded 10s timeout)
        fetch_res = subprocess.run(
            ["git", "fetch", "origin", default_branch],
            cwd=str(repo_dir), capture_output=True, text=True, timeout=10
        )
        if fetch_res.returncode != 0:
            return

        # 6. Fast-forward merge origin/<default_branch> (bounded 5s timeout)
        subprocess.run(
            ["git", "merge", "--ff-only", f"origin/{default_branch}"],
            cwd=str(repo_dir), capture_output=True, text=True, timeout=5
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
                (board_slug,)
            )
            row = cursor.fetchone()
            return int(row[0]) if row else 0
    except Exception:
        return 0


def get_board_pipeline_capacity(board_slug: str) -> Dict[str, Any]:
    """Get active pipeline task counts and capacity-driven idle scan settings."""
    db_path = Path(os.environ.get("ZEROFACTORY_DB") or DEFAULT_DB_PATH)
    res = {
        "running": 0,
        "todo": 0,
        "scan_on_idle": False,
        "idle_scan_active_threshold": 2,
        "idle_scan_cooldown_minutes": 15,
        "idle_scan_max_todo": 2,
    }
    if not db_path.exists():
        return res
    try:
        with sqlite3.connect(str(db_path), timeout=5.0) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT status, COUNT(*) FROM tasks WHERE board_slug = ? AND status IN ('running', 'todo') GROUP BY status",
                (board_slug,)
            )
            for row in cursor.fetchall():
                if row[0] == "running":
                    res["running"] = int(row[1])
                elif row[0] == "todo":
                    res["todo"] = int(row[1])

            try:
                cursor.execute(
                    "SELECT key, value FROM settings WHERE key IN ('scan_on_idle', 'idle_scan_active_threshold', 'idle_scan_cooldown_minutes', 'idle_scan_max_todo')"
                )
                for key, val in cursor.fetchall():
                    if key == "scan_on_idle":
                        res["scan_on_idle"] = str(val).strip().lower() in ("true", "1", "yes")
                    elif key == "idle_scan_active_threshold":
                        try:
                            res["idle_scan_active_threshold"] = max(1, int(val))
                        except ValueError:
                            pass
                    elif key == "idle_scan_cooldown_minutes":
                        try:
                            res["idle_scan_cooldown_minutes"] = max(1, int(val))
                        except ValueError:
                            pass
                    elif key == "idle_scan_max_todo":
                        try:
                            res["idle_scan_max_todo"] = max(0, int(val))
                        except ValueError:
                            pass
            except Exception:
                pass
    except Exception:
        pass
    return res


def get_existing_task_titles(board_slug: str) -> List[str]:
    db_path = Path(os.environ.get("ZEROFACTORY_DB") or DEFAULT_DB_PATH)
    if not db_path.exists():
        return []
    try:
        with sqlite3.connect(str(db_path), timeout=5.0) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT title FROM tasks WHERE board_slug = ? AND status != 'done' ORDER BY created_at DESC LIMIT 25",
                (board_slug,)
            )
            return [row[0] for row in cursor.fetchall()]
    except Exception:
        return []


def has_task_on_or_after_commit(board_slug: str, commit_time: int) -> bool:
    """Check if any task was created for this board on or after the commit timestamp."""
    if commit_time <= 0:
        return False
    db_path = Path(os.environ.get("ZEROFACTORY_DB") or DEFAULT_DB_PATH)
    if not db_path.exists():
        return False
    try:
        with sqlite3.connect(str(db_path), timeout=5.0) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT 1 FROM tasks WHERE board_slug = ? AND created_at >= ? LIMIT 1",
                (board_slug, commit_time)
            )
            return cursor.fetchone() is not None
    except Exception:
        return False


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
                cursor.execute("SELECT slug, git_url FROM boards")
                rows = cursor.fetchall()
                # 1. Match by slug == repo name or slug ends with repo name
                for slug, _ in rows:
                    if repo_dir.name.lower() in (slug.lower(), slug.split("-")[-1].lower()):
                        return slug
                # 2. Match by git remote origin url (supports both HTTPS and SSH)
                remote_url = _run_cmd(["git", "config", "--get", "remote.origin.url"], cwd=repo_dir)
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
                            if norm_remote == norm_board_git or norm_remote in git_url.lower():
                                return slug
                # Fallback to first board if available
                if rows:
                    return rows[0][0]
        except Exception:
            pass

    return repo_dir.name if repo_dir.name else "zerofactory"


def run_scanner_gate() -> int:
    repo_dir = Path.cwd()
    board_slug = resolve_board_slug(repo_dir)

    # Auto-sync/pull default branch from remote before evaluating commit SHA
    _auto_sync_repo(repo_dir)

    # Check if this is a git repo
    head_sha = _run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_dir)
    status_porcelain = _run_cmd(["git", "status", "--porcelain", "-uno"], cwd=repo_dir)

    if not head_sha:
        # Not a git repo or git failed — allow normal run
        print(f"Warning: Not a valid git repository at {repo_dir}. Running standard inspection.")
        print(json.dumps({"wakeAgent": True}))
        return 0

    # Fetch active pipeline tasks (running, todo) to determine if pipeline is busy
    active_in_flight = get_active_pipeline_task_count(board_slug)

    # Fetch existing task titles to prevent duplicate suggestions
    existing_tasks = get_existing_task_titles(board_slug)

    # Fetch capacity-driven idle scan settings and task breakdown
    capacity = get_board_pipeline_capacity(board_slug)

    # Check for forced or idle scan
    force_scan = (
        "--force" in sys.argv
        or os.environ.get("ZEROFACTORY_FORCE_SCAN", "").lower() in ("1", "true", "yes")
    )
    is_idle_scan = (
        "--idle" in sys.argv
        or os.environ.get("ZEROFACTORY_IDLE_SCAN", "").lower() in ("1", "true", "yes")
    )

    state = load_state()
    board_state = state.get(board_slug, {})
    last_sha = board_state.get("last_scanned_sha")
    last_status = board_state.get("last_status")

    is_same_commit = (head_sha == last_sha)
    is_same_status = (status_porcelain == last_status)

    now_ts = int(time.time())
    retry_cooldown = int(os.environ.get("ZEROFACTORY_SCAN_RETRY_COOLDOWN", "1800"))
    max_attempts = int(os.environ.get("ZEROFACTORY_SCAN_MAX_ATTEMPTS", "3"))
    reset_cooldown = int(os.environ.get("ZEROFACTORY_SCAN_RESET_COOLDOWN", "7200"))

    # Check for unchanged steady state
    if is_same_commit and is_same_status and not force_scan:
        if last_sha is not None:
            # Check for capacity-driven idle scanning
            scan_on_idle = capacity.get("scan_on_idle", False)
            running_count = capacity.get("running", 0)
            todo_count = capacity.get("todo", 0)
            idle_threshold = capacity.get("idle_scan_active_threshold", 2)
            max_todo = capacity.get("idle_scan_max_todo", 2)
            idle_cooldown = capacity.get("idle_scan_cooldown_minutes", 15) * 60

            if is_idle_scan:
                print(f"CAPACITY_DRIVEN_SCAN_TRIGGERED: Dispatcher authorized idle scan for board '{board_slug}' (active running={running_count} < {idle_threshold}).")
            elif scan_on_idle:
                # Capacity-driven idle scanning is enabled in settings
                if running_count >= idle_threshold or todo_count >= max_todo:
                    print(
                        f"NO_CHANGES_DETECTED: Repository at {head_sha[:8]} unchanged; "
                        f"pipeline busy on board '{board_slug}' (running={running_count}/{idle_threshold}, todo={todo_count}/{max_todo})."
                    )
                    print(json.dumps({"wakeAgent": False}))
                    return 0

                last_scan_at = int(board_state.get("last_scan_at", 0))
                if (now_ts - last_scan_at) < idle_cooldown:
                    print(
                        f"SCAN_COOLDOWN_ACTIVE: Board '{board_slug}' is idle (running={running_count} < {idle_threshold}), "
                        f"but cooldown active ({now_ts - last_scan_at}s < {idle_cooldown}s); waiting."
                    )
                    print(json.dumps({"wakeAgent": False}))
                    return 0

                print(
                    f"CAPACITY_DRIVEN_SCAN_TRIGGERED: Board '{board_slug}' is idle "
                    f"(running={running_count} < {idle_threshold}, todo={todo_count} < {max_todo}); "
                    f"cooldown elapsed ({now_ts - last_scan_at}s >= {idle_cooldown}s). Initiating idle improvement scan."
                )
            else:
                # Idle scanning disabled — fall back to strict commit-change suppression
                # 1. If active in-flight tasks exist in the pipeline, definitely suppress (pipeline busy)
                if active_in_flight > 0:
                    print(f"NO_CHANGES_DETECTED: Repository at {head_sha[:8]} unchanged since last scan; active pipeline tasks ({active_in_flight}) on board '{board_slug}'.")
                    print(json.dumps({"wakeAgent": False}))
                    return 0

                # 2. If no active tasks exist, check if a task was ever created for this commit
                commit_time_str = _run_cmd(["git", "log", "-1", "--format=%ct", head_sha], cwd=repo_dir)
                commit_time = int(commit_time_str) if commit_time_str.isdigit() else 0
                has_tasks = board_state.get("task_created") or has_task_on_or_after_commit(board_slug, commit_time)

                if has_tasks:
                    # Successfully produced tasks for this commit (which are now completed/closed)
                    print(f"NO_CHANGES_DETECTED: Repository at {head_sha[:8]} unchanged since last scan; board '{board_slug}' already scanned.")
                    print(json.dumps({"wakeAgent": False}))
                    return 0

                # 3. No tasks were produced on this commit (potential premature suppression due to failed scan).
                # Enforce retry cooldown and max attempts before giving up.
                last_scan_at = int(board_state.get("last_scan_at", 0))
                attempts = int(board_state.get("scan_attempts", 1))

                if (now_ts - last_scan_at) < retry_cooldown:
                    print(f"SCAN_COOLDOWN_ACTIVE: Scan on commit {head_sha[:8]} recently attempted ({now_ts - last_scan_at}s ago < {retry_cooldown}s); waiting for cooldown.")
                    print(json.dumps({"wakeAgent": False}))
                    return 0

                if attempts >= max_attempts:
                    if (now_ts - last_scan_at) >= reset_cooldown:
                        # Outage recovery: after reset_cooldown (default 2h), reset attempts and retry
                        attempts = 0
                        board_state["scan_attempts"] = 0
                    else:
                        print(f"NO_CHANGES_DETECTED: Repository at {head_sha[:8]} unchanged after {attempts} scan attempts without tasks; suppressing.")
                        print(json.dumps({"wakeAgent": False}))
                        return 0

                # Allow retry! Fall through to wake the agent
                print(f"RETRY_SCAN_TRIGGERED: Previous scan on {head_sha[:8]} produced no tasks and board has 0 active tasks (attempt {attempts + 1}/{max_attempts}). Initiating re-scan.")
        else:
            print(f"BASELINE_SCAN_TRIGGERED: Board '{board_slug}' has never been scanned. Initiating baseline codebase inspection.")

    # Pre-flight LLM probe: verify inference endpoint is reachable before committing state and waking agent
    if not is_llm_reachable():
        print("LLM_UNREACHABLE: Inference endpoint is unreachable; deferring scan without consuming attempts.")
        print(json.dumps({"wakeAgent": False}))
        return 0

    # Changes detected or baseline/retry scan required! Update state
    new_attempts = (int(board_state.get("scan_attempts", 0)) + 1) if is_same_commit else 1
    board_state["last_scanned_sha"] = head_sha
    board_state["last_status"] = status_porcelain
    board_state["last_scan_at"] = now_ts
    board_state["scan_attempts"] = new_attempts
    if not is_same_commit:
        board_state.pop("task_created", None)
    state[board_slug] = board_state
    save_state(state)

    # Collect pre-digested intelligence to pass to the LLM
    excluded_diff_pathspecs = [":!*.lock", ":!*package-lock.json", ":!*pnpm-lock.yaml", ":!*yarn.lock", ":!*.min.*", ":!*.map"]
    log_summary = _run_cmd(["git", "log", "-n", "5", "--oneline"], cwd=repo_dir)
    diffstat = _run_cmd(["git", "diff", "--stat", "HEAD~1..HEAD", "--", *excluded_diff_pathspecs], cwd=repo_dir)
    raw_diff = _run_cmd(["git", "diff", "-U2", "HEAD~1..HEAD", "--", *excluded_diff_pathspecs], cwd=repo_dir)

    # Cap diff to prevent prompt overflow
    diff_lines = raw_diff.splitlines()[:80]
    truncated_diff = "\n".join(diff_lines)
    if len(diff_lines) == 80:
        truncated_diff += "\n... [diff truncated for token efficiency]"

    # Check for uncommitted files
    is_worktree_clean = len(status_porcelain.strip()) == 0
    uncommitted_summary = ""
    if not is_worktree_clean:
        uncommitted_summary = f"### Uncommitted Changes:\n```\n{status_porcelain[:1000]}\n```\n"

    # Search for new TODO / FIXME in tracked files
    todo_matches = _run_cmd(["git", "grep", "-n", "-E", "TODO|FIXME|HACK", "--", "*.py", "*.ts", "*.js", "*.go", "*.rs"], cwd=repo_dir)
    todo_sample = "\n".join(todo_matches.splitlines()[:15]) if todo_matches else "None"

    tasks_block = "\n".join([f"- {t}" for t in existing_tasks]) if existing_tasks else "(No active tasks)"

    print("### 🔍 Pre-Screen Intelligence Package (Zero-Token Ingested)")
    print(f"**Repository:** `{repo_dir.name}` (Commit: `{head_sha[:8]}`)")
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
        candidate_files = _run_cmd(["git", "ls-files", "*.py", "*.ts", "*.js", "*.mjs"], cwd=repo_dir)
        files_sample = "\n".join([f"- `{f}`" for f in candidate_files.splitlines()[:20]]) if candidate_files else "(None)"
        print("#### Baseline Codebase Source Files to Inspect:")
        print(files_sample)
        print()
        print("---")
        print(f"Instructions for Agent: Baseline scan for board '{board_slug}' (0 active tasks). Inspect candidate source files above for genuine bugs, missing tests, or error-handling debt. Create exactly 1 task using `hermes zerofactory create \"<issue title>\" --description \"<details>\" --board \"{board_slug}\" --files \"<files>\" --category \"<category>\" --priority P0 --status todo --assignee zf-builder`.")
    else:
        print("---")
        print(f"Instructions for Agent: Review the codebase for board '{board_slug}' for genuine code quality improvements, refactoring, performance, architecture, or test debt. If warranted, create AT MOST 1 task in Kanban and finish. Do NOT duplicate open tasks.")
    print()

    # Emit wakeAgent: true to invoke LLM with this rich context
    print(json.dumps({"wakeAgent": True}))
    return 0


if __name__ == "__main__":
    sys.exit(run_scanner_gate())
