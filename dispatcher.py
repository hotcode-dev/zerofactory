"""Zero Factory Kanban Dispatcher Engine.

Handles:
1. Parent-child dependency resolution (auto-unblocking).
2. Work-in-Progress (WIP) limits and promotion (todo -> ready).
3. Automatic specialist assignment (builder / reviewer / orchestrator).
4. Git worktree provisioning and isolated branching.
5. GitHub Pull Request lifecycle and reviewer feedback loop.
"""

from __future__ import annotations

from contextlib import closing
import json
import logging
import os
import re
import signal
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_log = logging.getLogger("zerofactory.kanban.dispatcher")

MAX_ACTIVE_TASKS = 3
MAX_CONCURRENT_WORKERS = int(os.environ.get("ZEROFACTORY_MAX_RUNNING_WORKERS", "1"))
DEFAULT_TASK_TIMEOUT_SECONDS = 3600  # 1 hour max running time
DEFAULT_INACTIVITY_TIMEOUT_SECONDS = 900  # 15 mins with no log/session update
DISPATCH_INTERVAL_SECONDS = 30
_dispatcher_thread: Optional[threading.Thread] = None
_dispatcher_lock = threading.Lock()
_active_workers: Dict[str, subprocess.Popen] = {}

PROFILE_MAP = {
    "builder": "zf-builder",
    "zf-builder": "zf-builder",
    "reviewer": "zf-reviewer",
    "zf-reviewer": "zf-reviewer",
    "orchestrator": "zf-orchestrator",
    "zf-orchestrator": "zf-orchestrator",
}

VALID_PROFILES = ("zf-builder", "zf-reviewer", "zf-orchestrator", "builder", "reviewer", "orchestrator")


def normalize_assignee(assignee: Optional[str]) -> str:
    """Normalize assignee to canonical zf-* namespaced profile."""
    if not assignee or assignee == "unassigned":
        return "unassigned"
    return PROFILE_MAP.get(assignee, assignee)


def get_task_timeout_seconds() -> int:
    """Return maximum allowed running duration before worker is considered stuck."""
    return int(os.environ.get("ZEROFACTORY_TASK_TIMEOUT_SECONDS", str(DEFAULT_TASK_TIMEOUT_SECONDS)))


def get_inactivity_timeout_seconds() -> int:
    """Return maximum allowed inactivity before worker is considered hung."""
    return int(os.environ.get("ZEROFACTORY_INACTIVITY_TIMEOUT_SECONDS", str(DEFAULT_INACTIVITY_TIMEOUT_SECONDS)))


def get_db_path() -> Path:
    env_path = os.environ.get("ZEROFACTORY_DB")
    if env_path:
        return Path(env_path)
    return Path.home() / ".hermes" / "zerofactory.db"


def spawn_agent_worker(
    task_id: str,
    title: str,
    description: str,
    priority: str,
    assignee: str,
    workspace_path: Optional[str],
    branch_name: Optional[str]
) -> tuple[Optional[int], Optional[str]]:
    """Spawn an isolated hermes worker subprocess for the assigned specialist agent."""
    if os.environ.get("ZEROFACTORY_SKIP_WORKER_SPAWN"):
        return None, None

    assignee = normalize_assignee(assignee)
    import shutil
    local_hermes = Path.home() / ".local" / "bin" / "hermes"
    hermes_bin = (
        os.environ.get("HERMES_BIN")
        or shutil.which("hermes")
        or (str(local_hermes) if local_hermes.exists() else "hermes")
    )

    workdir = workspace_path if (workspace_path and Path(workspace_path).exists()) else os.getcwd()

    if assignee in ("reviewer", "zf-reviewer"):
        prompt = (
            f"Task ID: {task_id}\n"
            f"Title: {title}\n"
            f"Priority: {priority}\n"
            f"Assigned Role: {assignee}\n\n"
            f"Description:\n{description or 'No description provided.'}\n\n"
            f"Workspace: {workdir}\n"
            f"Git Branch: {branch_name or 'main'}\n\n"
            f"Your goal as Reviewer:\n"
            f"1. Examine the Pull Request branch changes ({branch_name or 'main'}) for correctness, test coverage, and security.\n"
            f"2. Run automated test suites and linters in your workspace ({workdir}).\n"
            f"3. Submit your review decision on GitHub (`gh pr review --approve` or `gh pr review --request-changes`).\n"
            f"4. When finished, mark the task complete using `hermes zerofactory move {task_id} done` or `hermes zerofactory block {task_id} --reason 'changes-requested'`.\n"
            f"5. Provide a clear review summary.\n"
        )
    else:
        prompt = (
            f"Task ID: {task_id}\n"
            f"Title: {title}\n"
            f"Priority: {priority}\n"
            f"Assigned Role: {assignee}\n\n"
            f"Description:\n{description or 'No description provided.'}\n\n"
            f"Workspace: {workdir}\n"
            f"Git Branch: {branch_name or 'main'}\n\n"
            f"Your goal:\n"
            f"1. Read the task requirements and explore the codebase in your workspace ({workdir}).\n"
            f"2. Implement the required changes cleanly, adhering to repository patterns.\n"
            f"3. Verify your changes with tests, linters, or typechecks.\n"
            f"4. When finished, mark the task as complete using:\n"
            f"   hermes zerofactory move {task_id} done\n"
            f"   (or if human review or external dependencies are required, run:\n"
            f"   hermes zerofactory move {task_id} blocked --reason \"review-required\")\n"
            f"5. Provide a summary of your changes.\n"
        )

    cmd = [
        hermes_bin,
        "-p", assignee,
        "--yolo",
        "--cli",
        "--accept-hooks",
        "chat",
        "-q", prompt
    ]

    log_dir = Path.home() / ".hermes" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file_path = log_dir / f"worker_{task_id}.log"

    env = os.environ.copy()
    env["HERMES_KANBAN_TASK"] = task_id
    env["HERMES_KANBAN_WORKSPACE"] = str(workdir)
    env["TERMINAL_CWD"] = str(workdir)
    env["HERMES_PROFILE"] = assignee
    profile_home = Path.home() / ".hermes" / "profiles" / assignee
    if profile_home.exists():
        env["HERMES_HOME"] = str(profile_home)
    env["PYTHONUNBUFFERED"] = "1"

    try:
        log_f = open(log_file_path, "ab")
        spawn_time = time.time()
        proc = subprocess.Popen(
            cmd,
            cwd=str(workdir),
            stdin=subprocess.DEVNULL,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
        log_f.close()
        _active_workers[task_id] = proc
        _log.info("Spawned %s worker for task %s (PID: %d, cwd: %s)", assignee, task_id, proc.pid, workdir)

        # Detect session_id from profile's state.db (only if started around this spawn)
        session_id = None
        state_db_path = Path.home() / ".hermes" / "profiles" / assignee / "state.db"
        if not state_db_path.exists():
            unprefixed = assignee.replace("zf-", "")
            alt_path = Path.home() / ".hermes" / "profiles" / unprefixed / "state.db"
            if alt_path.exists():
                state_db_path = alt_path
            else:
                p_root = Path.home() / ".hermes" / "state.db"
                if p_root.exists():
                    state_db_path = p_root
        if state_db_path.exists():
            try:
                resolved_state = state_db_path.resolve()
                uri = resolved_state.as_uri() + "?mode=ro"
                try:
                    s_conn = sqlite3.connect(uri, uri=True, timeout=2.0)
                except Exception:
                    s_conn = sqlite3.connect(str(resolved_state), timeout=2.0)
                with closing(s_conn) as s_conn:
                    s_cur = s_conn.cursor()
                    s_cur.execute(
                        "SELECT id FROM sessions WHERE started_at >= ? ORDER BY started_at DESC LIMIT 1",
                        (spawn_time - 2.0,)
                    )
                    s_row = s_cur.fetchone()
                    if s_row:
                        session_id = s_row[0]
            except Exception:
                pass

        return proc.pid, session_id
    except Exception as e:
        _log.error("Failed to spawn %s worker for task %s: %s", assignee, task_id, e)
        return None, None


def terminate_worker_process(proc: Optional[subprocess.Popen], pid: Optional[int]) -> None:
    """Safely terminate a worker process with SIGTERM then SIGKILL."""
    if proc is not None:
        try:
            proc.terminate()
            try:
                proc.wait(timeout=2)
            except subprocess.TimeoutExpired:
                proc.kill()
        except Exception:
            pass
    elif pid:
        try:
            os.kill(pid, signal.SIGTERM)
            time.sleep(0.5)
            try:
                os.kill(pid, 0)
                os.kill(pid, signal.SIGKILL)
            except OSError:
                pass
        except OSError:
            pass


def reap_active_workers(cursor: sqlite3.Cursor, now: int) -> int:
    """Check running tasks and reap finished, crashed, or stuck worker processes."""
    cursor.execute("SELECT id, title, metadata, updated_at, created_at FROM tasks WHERE status = 'running'")
    running_rows = cursor.fetchall()
    reaped = 0

    task_timeout = get_task_timeout_seconds()
    inactivity_timeout = get_inactivity_timeout_seconds()

    for row in running_rows:
        task_id = str(row["id"])
        meta = {}
        try:
            meta = json.loads(row["metadata"] or "{}")
        except Exception:
            pass

        proc = _active_workers.get(task_id)
        pid = meta.get("worker_pid") or (proc.pid if proc else None)

        if proc is not None:
            retcode = proc.poll()
            if retcode is not None:
                _active_workers.pop(task_id, None)
                if retcode == 0:
                    cursor.execute("UPDATE tasks SET status = 'done', updated_at = ? WHERE id = ?", (now, task_id))
                    cursor.execute(
                        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_done', 'Worker process completed successfully (exit 0)', ?)",
                        (task_id, now)
                    )
                    _log.info("Worker for task %s finished successfully (exit 0); moved to done", task_id)
                else:
                    cursor.execute("UPDATE tasks SET status = 'blocked', updated_at = ? WHERE id = ?", (now, task_id))
                    cursor.execute(
                        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_failed', ?, ?)",
                        (task_id, f"Worker process exited with code {retcode}", now)
                    )
                    _log.warning("Worker for task %s failed with exit code %d; moved to blocked", task_id, retcode)
                reaped += 1
                continue
        elif pid:
            try:
                os.kill(pid, 0)
            except OSError:
                cursor.execute("UPDATE tasks SET status = 'blocked', updated_at = ? WHERE id = ?", (now, task_id))
                cursor.execute(
                    "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_lost', ?, ?)",
                    (task_id, f"Worker process PID {pid} not found; moved to blocked", now)
                )
                _log.warning("Worker PID %d for task %s not found; moved to blocked", pid, task_id)
                reaped += 1
                continue

        # Check if running task exceeded overall timeout or inactivity threshold
        started_at = meta.get("started_at") or row["updated_at"] or row["created_at"] or now
        running_time = max(0, now - int(started_at))

        is_stuck = False
        stuck_reason = ""

        if running_time > task_timeout:
            is_stuck = True
            stuck_reason = f"Worker exceeded running timeout ({running_time}s > {task_timeout}s)"
        else:
            idle_time = None
            log_path = Path.home() / ".hermes" / "logs" / f"worker_{task_id}.log"
            if log_path.exists():
                try:
                    idle_time = max(0, now - int(log_path.stat().st_mtime))
                except Exception:
                    pass
            if idle_time is not None and idle_time > inactivity_timeout:
                is_stuck = True
                stuck_reason = f"Worker inactive with no updates for {idle_time}s (limit {inactivity_timeout}s)"

        if is_stuck:
            terminate_worker_process(proc, pid)
            _active_workers.pop(task_id, None)
            cursor.execute("UPDATE tasks SET status = 'blocked', updated_at = ? WHERE id = ?", (now, task_id))
            cursor.execute(
                "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_timeout', ?, ?)",
                (task_id, stuck_reason, now)
            )
            _log.warning("Task %s reaped due to timeout/inactivity: %s; moved to blocked", task_id, stuck_reason)
            reaped += 1

    return reaped


def check_stuck_tasks(cursor: Optional[sqlite3.Cursor] = None, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Inspect all currently running tasks and return health & stuckness metrics."""
    close_conn = False
    if cursor is None:
        if db_path is None:
            db_path = get_db_path()
        conn = sqlite3.connect(str(db_path), timeout=5.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        close_conn = True

    try:
        now = int(time.time())
        cursor.execute("SELECT id, title, status, updated_at, created_at, metadata, assignee, board_slug FROM tasks WHERE status = 'running'")
        running_rows = cursor.fetchall()

        task_timeout = get_task_timeout_seconds()
        inactivity_timeout = get_inactivity_timeout_seconds()
        results = []

        for row in running_rows:
            task_id = str(row["id"])
            meta = {}
            try:
                meta = json.loads(row["metadata"] or "{}")
            except Exception:
                pass

            proc = _active_workers.get(task_id)
            pid = meta.get("worker_pid") or (proc.pid if proc else None)

            is_alive = False
            if proc is not None:
                is_alive = proc.poll() is None
            elif pid:
                try:
                    os.kill(int(pid), 0)
                    is_alive = True
                except (OSError, ValueError):
                    is_alive = False

            started_at = meta.get("started_at") or row["updated_at"] or row["created_at"] or now
            running_seconds = max(0, now - int(started_at))

            idle_seconds = running_seconds
            log_path = Path.home() / ".hermes" / "logs" / f"worker_{task_id}.log"
            if log_path.exists():
                try:
                    idle_seconds = max(0, now - int(log_path.stat().st_mtime))
                except Exception:
                    pass

            is_stuck = False
            stuck_reason = None

            if not is_alive and pid:
                is_stuck = True
                stuck_reason = f"Worker process PID {pid} is dead/not found"
            elif running_seconds > task_timeout:
                is_stuck = True
                stuck_reason = f"Exceeded running timeout ({running_seconds}s > {task_timeout}s)"
            elif idle_seconds > inactivity_timeout:
                is_stuck = True
                stuck_reason = f"Worker inactive with no updates for {idle_seconds}s (limit {inactivity_timeout}s)"

            results.append({
                "id": task_id,
                "title": row["title"],
                "board_slug": row["board_slug"] if "board_slug" in row.keys() else None,
                "assignee": row["assignee"] or "builder",
                "worker_pid": pid,
                "is_alive": is_alive,
                "started_at": started_at,
                "running_seconds": running_seconds,
                "idle_seconds": idle_seconds,
                "is_stuck": is_stuck,
                "stuck_reason": stuck_reason,
                "timeout_limit": task_timeout,
                "inactivity_limit": inactivity_timeout
            })

        return results
    finally:
        if close_conn:
            try:
                conn.close()
            except Exception:
                pass


def reap_stuck_tasks(task_id: Optional[str] = None, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Manually or programmatically reap stuck tasks or a specific running task."""
    if db_path is None:
        db_path = get_db_path()

    now = int(time.time())
    reaped_tasks = []

    with _dispatcher_lock:
        with sqlite3.connect(str(db_path), timeout=10.0) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            stuck_list = check_stuck_tasks(cursor=cursor)
            for item in stuck_list:
                t_id = item["id"]
                if task_id and t_id != task_id:
                    continue
                if task_id or item["is_stuck"]:
                    proc = _active_workers.pop(t_id, None)
                    pid = item["worker_pid"]
                    terminate_worker_process(proc, pid)

                    reason = item["stuck_reason"] or f"Manually reaped after running {item['running_seconds']}s"
                    cursor.execute("UPDATE tasks SET status = 'blocked', updated_at = ? WHERE id = ?", (now, t_id))
                    cursor.execute(
                        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_timeout', ?, ?)",
                        (t_id, reason, now)
                    )
                    reaped_tasks.append({"id": t_id, "title": item["title"], "reason": reason})

            conn.commit()

    return {
        "ok": True,
        "reaped_count": len(reaped_tasks),
        "reaped_tasks": reaped_tasks
    }


def resolve_task_repo_path(cursor: Optional[sqlite3.Cursor], board_slug: Optional[str], tenant: Optional[str]) -> Path:
    """Resolve the git repository root for a task given its board_slug and tenant."""
    # 1. If board_slug is provided, query boards table and resolve repo path
    if board_slug and cursor:
        try:
            cursor.execute("SELECT slug, name, description, git_url FROM boards WHERE slug = ?", (board_slug,))
            b_row = cursor.fetchone()
            if b_row:
                b_dict = dict(b_row)
                try:
                    from .builtin_cron import resolve_board_repo_path
                except Exception:
                    from builtin_cron import resolve_board_repo_path
                resolved_b = resolve_board_repo_path(b_dict)
                if resolved_b and resolved_b.exists():
                    return resolved_b
        except Exception:
            pass

    # 2. If tenant path is provided
    if tenant:
        t_path = Path(os.path.expanduser(tenant))
        if t_path.is_absolute() and t_path.exists():
            return t_path
        g_tenant = Path.home() / "git" / tenant
        if g_tenant.exists():
            return g_tenant

    # 3. Check ~/git/<board_slug> if board_slug provided
    if board_slug:
        g_board = Path.home() / "git" / board_slug
        if g_board.exists():
            return g_board
        for sub in (Path.home() / "git").glob(f"*/{board_slug}"):
            if sub.is_dir():
                return sub

def format_conventional_message(title: str, task_id: str = "") -> tuple[str, str]:
    """Format task title into Conventional Commits subject and body.

    Output format:
      subject: <type>(<scope>)?: <description>
      body: Task: <task_id>\\n\\n<title>
    """
    raw_title = title
    # 1. Strip role and priority badges
    cleaned = re.sub(r"\[(?:zf-builder|zf-reviewer|zf-orchestrator|builder|reviewer|orchestrator|PR Opened by .*?|P[0-3]|p[0-3])\]", "", title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # 2. Check if already conventional
    m = re.match(r"^(feat|fix|refactor|perf|test|docs|style|chore|ci|build)(\([^)]+\))?(!)?:\s*(.*)$", cleaned, re.IGNORECASE)
    if m:
        c_type = m.group(1).lower()
        c_scope = m.group(2) or ""
        c_desc = m.group(4).strip()
    else:
        # Check common prefixes
        prefix_rules = [
            (r"^(?:BUG\s*FIX|BUGFIX|HOTFIX)[:\s-]+(.*)$", "fix", ""),
            (r"^(?:FIX|BUG):\s*(.*)$", "fix", ""),
            (r"^(?:SECURITY|SEC)[:\s-]+(.*)$", "fix", "(security)"),
            (r"^(?:REFACTOR(?:ING)?|CLEANUP|DEDUP(?:LICATE)?)[:\s-]+(.*)$", "refactor", ""),
            (r"^(?:FEAT(?:URE)?|NEW)[:\s-]+(.*)$", "feat", ""),
            (r"^(?:ADD):\s*(.*)$", "feat", ""),
            (r"^(?:PERF(?:ORMANCE)?|OPTIMIZE|OPTIMIZATION)[:\s-]+(.*)$", "perf", ""),
            (r"^(?:TEST(?:S|ING)?)[:\s-]+(.*)$", "test", ""),
            (r"^(?:DOCS?|DOCUMENTATION)[:\s-]+(.*)$", "docs", ""),
            (r"^(?:CHORE|MAINTENANCE|DEPS|DEPENDENCIES)[:\s-]+(.*)$", "chore", ""),
            (r"^(?:CI|WORKFLOW|PIPELINE)[:\s-]+(.*)$", "ci", ""),
            (r"^(?:BUILD|RELEASE)[:\s-]+(.*)$", "build", ""),
        ]
        c_type, c_scope, c_desc = "chore", "", cleaned
        for pattern, t, s in prefix_rules:
            match = re.match(pattern, cleaned, re.IGNORECASE)
            if match:
                c_type = t
                c_scope = s
                c_desc = match.group(1).strip()
                break
        else:
            lower_cleaned = cleaned.lower()
            if re.search(r"\b(?:unit[\s_-]?tests?|e2e|integration[\s_-]?tests?|tests?)\b", lower_cleaned) and not any(lower_cleaned.startswith(p) for p in ("fix ", "patch ")):
                c_type = "test"
            elif any(lower_cleaned.startswith(p) for p in ("add ", "create ", "implement ", "support ", "introduce ", "integrate ")):
                c_type = "feat"
            elif any(lower_cleaned.startswith(p) for p in ("fix ", "resolve ", "patch ", "correct ", "prevent ", "handle ")):
                c_type = "fix"
            elif any(lower_cleaned.startswith(p) for p in ("refactor ", "extract ", "reorganize ", "simplify ", "deduplicate ", "clean ")):
                c_type = "refactor"
            elif any(lower_cleaned.startswith(p) for p in ("optimize ", "speed ", "accelerate ", "reduce ")):
                c_type = "perf"
            elif any(lower_cleaned.startswith(p) for p in ("doc ", "document ", "readme")):
                c_type = "docs"

    # 3. Infer scope if not provided
    if not c_scope:
        file_m = re.search(r"(?:in\s+)?(?:[\w\-]+/)*([a-zA-Z0-9_\-]+)\.(?:ts|js|py|go|rs|json|jsx|tsx|svelte|vue|md)\b", c_desc)
        if file_m:
            c_scope = f"({file_m.group(1)})"
        else:
            mod_m = re.match(r"^([a-zA-Z0-9_\-]+)\s+", c_desc)
            if mod_m and mod_m.group(1).lower() in ("dispatcher", "cron", "dashboard", "api", "auth", "worker", "agent"):
                c_scope = f"({mod_m.group(1).lower()})"

    # 4. Clean description
    if c_scope:
        scope_name = c_scope.strip("()")
        c_desc = re.sub(rf"\s*in\s+(?:[\w\-]+/)*{re.escape(scope_name)}\.[a-zA-Z0-9]+\b", "", c_desc, flags=re.IGNORECASE)
        c_desc = re.sub(rf"^{re.escape(scope_name)}[:\s]+", "", c_desc, flags=re.IGNORECASE)

    if len(c_desc) > 1 and c_desc[0].isupper() and not c_desc[1].isupper():
        c_desc = c_desc[0].lower() + c_desc[1:]

    c_desc = c_desc.rstrip(".").strip()

    subject_desc = c_desc
    if len(f"{c_type}{c_scope}: {c_desc}") > 72:
        no_parens = re.sub(r"\s*\([^)]*\)", "", c_desc).strip()
        if no_parens and len(f"{c_type}{c_scope}: {no_parens}") <= 80:
            subject_desc = no_parens

    subject = f"{c_type}{c_scope}: {subject_desc}".strip()

    body_lines = []
    if task_id:
        body_lines.append(f"Task: {task_id}")
    if raw_title.strip() != subject:
        body_lines.append(raw_title.strip())
    body = "\n\n".join(body_lines)

    return subject, body


def setup_worktree(
    cursor: sqlite3.Cursor,
    task_id: str,
    title: str,
    assignee: str,
    tenant: Optional[str],
    db_path: Path,
    board_slug: Optional[str] = None
) -> Optional[str]:
    """Ensure git worktree and branch exist for task execution."""
    valid_profiles = VALID_PROFILES
    if not assignee or assignee == "unassigned" or assignee not in valid_profiles:
        if "[reviewer]" in title or "[zf-reviewer]" in title:
            assignee = "zf-reviewer"
        elif "[builder]" in title or "[zf-builder]" in title:
            assignee = "zf-builder"
        elif "[orchestrator]" in title or "[zf-orchestrator]" in title:
            assignee = "zf-orchestrator"
        else:
            assignee = "zf-builder"
        cursor.execute("UPDATE tasks SET assignee = ?, skills = '[]' WHERE id = ?", (assignee, task_id))
    else:
        norm_assignee = normalize_assignee(assignee)
        if norm_assignee != assignee:
            assignee = norm_assignee
            cursor.execute("UPDATE tasks SET assignee = ? WHERE id = ?", (assignee, task_id))
        else:
            assignee = norm_assignee

    if os.environ.get("ZEROFACTORY_SKIP_GIT"):
        return None

    # Resolve repo path
    repo_path = resolve_task_repo_path(cursor, board_slug, tenant)
    reponame = repo_path.name

    worktree_dir = repo_path.parent / f"{reponame}-worktrees" / str(task_id)
    worktree_dir.parent.mkdir(parents=True, exist_ok=True)

    branch_name = f"task/{task_id}"
    try:
        res = subprocess.run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"], cwd=repo_path, timeout=5)
        if res.returncode == 0:
            if not worktree_dir.exists():
                subprocess.run(["git", "worktree", "add", str(worktree_dir), branch_name], check=True, cwd=repo_path, timeout=5)
        else:
            if not worktree_dir.exists():
                # Try origin/main first, then fallback to HEAD
                try:
                    subprocess.run(["git", "worktree", "add", str(worktree_dir), "-b", branch_name, "origin/main"], check=True, cwd=repo_path, timeout=5)
                except Exception:
                    subprocess.run(["git", "worktree", "add", str(worktree_dir), "-b", branch_name, "HEAD"], check=True, cwd=repo_path, timeout=5)
        cursor.execute(
            "UPDATE tasks SET workspace_kind = 'dir', workspace_path = ?, branch_name = ? WHERE id = ?",
            (str(worktree_dir), branch_name, task_id)
        )
        return str(worktree_dir)
    except Exception as e:
        _log.warning("Worktree setup skipped or failed for task %s (%s): %s", task_id, repo_path, e)
        return None


def run_dispatch_cycle(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Execute one full dispatch cycle."""
    if db_path is None:
        db_path = get_db_path()

    if not db_path.exists():
        return {"ok": False, "message": f"Database not found: {db_path}"}

    unblocked = 0
    promoted = 0
    dispatched = 0
    prs_opened = 0
    reaped = 0
    now = int(time.time())

    with _dispatcher_lock:
        try:
            with sqlite3.connect(str(db_path), timeout=15.0) as conn:
                conn.execute("PRAGMA busy_timeout=15000;")
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # 1. Unblock tasks whose parent dependencies are all done
                cursor.execute("""
                    SELECT id, title FROM tasks
                    WHERE status = 'blocked'
                    AND id IN (SELECT child_id FROM task_links)
                    AND NOT EXISTS (
                        SELECT 1 FROM task_links tl
                        JOIN tasks pt ON pt.id = tl.parent_id
                        WHERE tl.child_id = tasks.id AND pt.status != 'done'
                    )
                """)
                for row in cursor.fetchall():
                    cursor.execute("UPDATE tasks SET status = 'ready', updated_at = ? WHERE id = ?", (now, row["id"]))
                    cursor.execute(
                        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'unblock', 'All parent dependencies satisfied', ?)",
                        (row["id"], now)
                    )
                    unblocked += 1

                # 2. Promote Todo to Ready respecting WIP Limit
                cursor.execute("SELECT COUNT(*) FROM tasks WHERE status IN ('ready', 'running')")
                active_count = cursor.fetchone()[0]

                if active_count < MAX_ACTIVE_TASKS:
                    limit = MAX_ACTIVE_TASKS - active_count
                    cursor.execute("""
                        SELECT id, title, workspace_path, assignee, tenant, board_slug FROM tasks
                        WHERE status = 'todo' OR (status = 'ready' AND assignee = 'unassigned')
                        ORDER BY CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 WHEN 'P3' THEN 3 ELSE 4 END
                        LIMIT ?
                    """, (limit,))
                    for row in cursor.fetchall():
                        task_id = str(row["id"])
                        assignee = row["assignee"]
                        title = row["title"] or ""
                        tenant = row["tenant"] if "tenant" in row.keys() else None
                        board_slug = row["board_slug"] if "board_slug" in row.keys() else None

                        setup_worktree(cursor, task_id, title, assignee, tenant, db_path, board_slug=board_slug)
                        cursor.execute("UPDATE tasks SET status = 'ready', updated_at = ? WHERE id = ?", (now, task_id))
                        cursor.execute(
                            "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'promote', 'Promoted to ready (WIP slot available)', ?)",
                            (task_id, now)
                        )
                        promoted += 1

                # 2.5. Reap finished workers and dispatch Ready tasks to Running
                reaped = reap_active_workers(cursor, now)

                cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'running'")
                running_count = cursor.fetchone()[0]

                if running_count < MAX_CONCURRENT_WORKERS:
                    spawn_limit = MAX_CONCURRENT_WORKERS - running_count
                    cursor.execute("""
                        SELECT id, title, description, priority, workspace_path, assignee, tenant, branch_name, metadata, board_slug FROM tasks
                        WHERE status = 'ready'
                        ORDER BY CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 WHEN 'P3' THEN 3 ELSE 4 END, created_at ASC
                        LIMIT ?
                    """, (spawn_limit,))
                    for row in cursor.fetchall():
                        task_id = str(row["id"])
                        assignee = normalize_assignee(row["assignee"] or "zf-builder")
                        title = row["title"] or ""
                        description = row["description"] or ""
                        priority = row["priority"] or "P2"
                        tenant = row["tenant"] if "tenant" in row.keys() else None
                        workspace_path = row["workspace_path"]
                        branch_name = row["branch_name"] if "branch_name" in row.keys() else None
                        board_slug = row["board_slug"] if "board_slug" in row.keys() else None

                        if not workspace_path or not Path(workspace_path).exists():
                            wt = setup_worktree(cursor, task_id, title, assignee, tenant, db_path, board_slug=board_slug)
                            if wt:
                                workspace_path = wt

                        pid, session_id = spawn_agent_worker(task_id, title, description, priority, assignee, workspace_path, branch_name)

                        meta = {}
                        try:
                            meta = json.loads(row["metadata"] or "{}")
                        except Exception:
                            pass
                        if pid:
                            meta["worker_pid"] = pid
                        if session_id:
                            meta["session_id"] = session_id
                        meta["started_at"] = now

                        cursor.execute(
                            "UPDATE tasks SET status = 'running', metadata = ?, updated_at = ? WHERE id = ?",
                            (json.dumps(meta), now, task_id)
                        )
                        cursor.execute(
                            "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'start', ?, ?)",
                            (task_id, f"Agent {assignee} dispatched to work on task (PID: {pid or 'skipped'}, Session: {session_id or 'auto'})", now)
                        )
                        dispatched += 1

                # 3. Handle Blocked / Completed Tasks (PR generation & Reviewer handoff)
                if not os.environ.get("ZEROFACTORY_SKIP_GIT"):
                    cursor.execute("""
                        SELECT id, title, workspace_path, assignee, tenant, branch_name, pr_url, board_slug FROM tasks
                        WHERE (status IN ('blocked', 'done') AND (pr_url IS NULL OR pr_url = ''))
                           OR (pr_url IS NOT NULL AND pr_url != '' AND assignee IN ('reviewer', 'zf-reviewer'))
                    """)
                    for row in cursor.fetchall():
                        task_id = str(row["id"])
                        title = row["title"]
                        workspace_path = row["workspace_path"]
                        assignee = row["assignee"]
                        tenant = row["tenant"] if "tenant" in row.keys() else None
                        board_slug = row["board_slug"] if "board_slug" in row.keys() else None

                        if not workspace_path or not Path(workspace_path).exists():
                            repo_for_task = resolve_task_repo_path(cursor, board_slug, tenant)
                            cand_wt = repo_for_task.parent / f"{repo_for_task.name}-worktrees" / task_id
                            if cand_wt.exists():
                                workspace_path = str(cand_wt)
                                cursor.execute("UPDATE tasks SET workspace_path = ? WHERE id = ?", (workspace_path, task_id))

                        if not workspace_path or not Path(workspace_path).exists():
                            continue

                        # Determine repository root reliably from git worktree
                        repo_path = None
                        try:
                            rev_res = subprocess.run(
                                ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                cwd=workspace_path, capture_output=True, text=True, timeout=5
                            )
                            if rev_res.returncode == 0:
                                common_git = Path(rev_res.stdout.strip())
                                repo_path = common_git.parent if common_git.name == ".git" else common_git
                        except Exception:
                            pass

                        if not repo_path or not repo_path.exists():
                            repo_path = resolve_task_repo_path(cursor, board_slug, tenant)

                        if assignee not in ("reviewer", "zf-reviewer"):
                            # Author finished work -> git commit, push, create PR, hand off to reviewer
                            try:
                                subject, commit_body = format_conventional_message(title, task_id)
                                status_res = subprocess.run(["git", "status", "--porcelain"], cwd=workspace_path, capture_output=True, text=True)
                                if status_res.stdout.strip():
                                    subprocess.run(["git", "add", "."], check=True, cwd=workspace_path, capture_output=True)
                                    subprocess.run(["git", "commit", "-m", subject, "-m", commit_body], check=True, cwd=workspace_path, capture_output=True)

                                subprocess.run(["git", "push", "-u", "origin", f"task/{task_id}"], check=True, cwd=workspace_path, capture_output=True)

                                pr_url = row["pr_url"] or ""
                                if not pr_url:
                                    gh_view = subprocess.run(["gh", "pr", "view", f"task/{task_id}", "--json", "url"], cwd=workspace_path, capture_output=True, text=True)
                                    if gh_view.returncode == 0:
                                        try:
                                            pr_url = json.loads(gh_view.stdout).get("url") or ""
                                        except Exception:
                                            pr_url = ""
                                    else:
                                        pr_title = subject
                                        pr_body = f"{commit_body}\n\nAutomated PR for task {task_id}\n\nCompleted by: @{assignee}"
                                        pr_res = subprocess.run(["gh", "pr", "create", "--title", pr_title, "--body", pr_body], check=True, cwd=workspace_path, capture_output=True, text=True)
                                        pr_url = pr_res.stdout.strip()

                                # Cleanup author worktree
                                subprocess.run(["git", "worktree", "remove", workspace_path, "--force"], check=False, cwd=str(repo_path), capture_output=True)

                                new_title = title
                                if not re.search(r"\[PR Opened by .*?\]", title):
                                    new_title = f"{title} [PR Opened by {assignee}]"

                                cursor.execute(
                                    "UPDATE tasks SET title = ?, assignee = 'zf-reviewer', pr_url = ?, status = 'ready', updated_at = ? WHERE id = ?",
                                    (new_title, pr_url, now, task_id)
                                )
                                setup_worktree(cursor, task_id, new_title, "zf-reviewer", tenant, db_path, board_slug=board_slug)
                                cursor.execute(
                                    "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'pr_opened', ?, ?)",
                                    (task_id, f"PR created, routed to reviewer: {pr_url}", now)
                                )
                                prs_opened += 1
                            except subprocess.CalledProcessError as e:
                                err_msg = (e.stderr or "").strip() or str(e)
                                _log.warning("Task %s commit/PR command failed: %s", task_id, err_msg)
                            except Exception as e:
                                _log.warning("Task %s commit/PR failed: %s", task_id, e)
                        else:
                            # Reviewer finished review -> inspect GitHub PR state
                            try:
                                subprocess.run(["git", "worktree", "remove", workspace_path, "--force"], check=False, cwd=str(repo_path), capture_output=True)
                                res = subprocess.run(
                                    ["gh", "pr", "view", f"task/{task_id}", "--json", "reviewDecision,state,url"],
                                    capture_output=True, text=True, cwd=str(repo_path)
                                )
                                if res.returncode == 0:
                                    pr_data = json.loads(res.stdout)
                                    pr_state = pr_data.get("state")
                                    decision = pr_data.get("reviewDecision")

                                    if pr_state == "MERGED":
                                        cursor.execute(
                                            "UPDATE tasks SET status = 'done', workspace_path = NULL, updated_at = ? WHERE id = ?",
                                            (now, task_id)
                                        )
                                        cursor.execute(
                                            "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'merged', 'PR merged by human, task completed', ?)",
                                            (task_id, now)
                                        )
                                    elif decision == "CHANGES_REQUESTED":
                                        match = re.search(r"\[PR Opened by (.*?)\]", title)
                                        author = match.group(1) if match else "zf-builder"
                                        author = normalize_assignee(author)
                                        cursor.execute(
                                            "UPDATE tasks SET assignee = ?, status = 'ready', updated_at = ? WHERE id = ?",
                                            (author, now, task_id)
                                        )
                                        setup_worktree(cursor, task_id, title, author, tenant, db_path, board_slug=board_slug)
                                        cursor.execute(
                                            "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'changes_requested', 'Changes requested by reviewer, routed back to author', ?)",
                                            (task_id, now)
                                        )
                                    elif decision == "APPROVED":
                                        new_title = f"{title} [Human Review]" if "[Human Review]" not in title else title
                                        cursor.execute(
                                            "UPDATE tasks SET title = ?, status = 'blocked', updated_at = ? WHERE id = ?",
                                            (new_title, now, task_id)
                                        )
                                        cursor.execute(
                                            "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'approved', 'Reviewer approved, waiting for human merge', ?)",
                                            (task_id, now)
                                        )
                            except Exception as e:
                                _log.info("Reviewer PR check skipped for task %s: %s", task_id, e)

                conn.commit()

            return {
                "ok": True,
                "unblocked": unblocked,
                "promoted": promoted,
                "dispatched": dispatched,
                "reaped": reaped,
                "prs_opened": prs_opened,
                "message": f"Dispatch cycle complete: {unblocked} unblocked, {promoted} promoted, {dispatched} dispatched to running, {reaped} reaped, {prs_opened} PRs opened."
            }
        except Exception as e:
            _log.error("Error during dispatch cycle: %s", e)
            return {"ok": False, "error": str(e)}


def _dispatcher_loop():
    """Background polling daemon thread for Kanban dispatch and periodic cron ticks."""
    while True:
        try:
            run_dispatch_cycle()
        except Exception as e:
            _log.error("Unexpected error in background dispatcher loop: %s", e)

        try:
            try:
                from .builtin_cron import tick_builtin_cron
            except ImportError:
                from builtin_cron import tick_builtin_cron  # type: ignore
            tick_builtin_cron()
        except Exception as e:
            _log.debug("Builtin cron tick check: %s", e)

        time.sleep(DISPATCH_INTERVAL_SECONDS)


def start_background_dispatcher():
    """Start background dispatcher daemon thread if not already running."""
    global _dispatcher_thread
    with _dispatcher_lock:
        if _dispatcher_thread is None or not _dispatcher_thread.is_alive():
            _dispatcher_thread = threading.Thread(target=_dispatcher_loop, name="ZeroFactoryKanbanDispatcher", daemon=True)
            _dispatcher_thread.start()
            _log.info("Zero Factory Kanban background dispatcher started (interval: %ss)", DISPATCH_INTERVAL_SECONDS)
