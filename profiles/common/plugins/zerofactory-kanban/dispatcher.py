"""Zero Factory Kanban Dispatcher Engine.

Handles:
1. Parent-child dependency resolution (auto-unblocking).
2. Work-in-Progress (WIP) limits and promotion (todo -> ready).
3. Automatic specialist assignment (builder / reviewer / orchestrator).
4. Git worktree provisioning and isolated branching.
5. GitHub Pull Request lifecycle and reviewer feedback loop.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_log = logging.getLogger("zerofactory.kanban.dispatcher")

MAX_ACTIVE_TASKS = 3
MAX_CONCURRENT_WORKERS = int(os.environ.get("ZEROFACTORY_MAX_RUNNING_WORKERS", "1"))
DISPATCH_INTERVAL_SECONDS = 30
_dispatcher_thread: Optional[threading.Thread] = None
_dispatcher_lock = threading.Lock()
_active_workers: Dict[str, subprocess.Popen] = {}


def get_db_path() -> Path:
    env_path = os.environ.get("ZEROFACTORY_KANBAN_DB")
    if env_path:
        return Path(env_path)
    return Path.home() / ".hermes" / "zerofactory_kanban.db"


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
    if os.environ.get("ZEROFACTORY_KANBAN_SKIP_WORKER_SPAWN"):
        return None, None

    import shutil
    hermes_bin = shutil.which("hermes") or "/home/ntsd/.local/bin/hermes"

    workdir = workspace_path if (workspace_path and Path(workspace_path).exists()) else os.getcwd()

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
        f"   hermes zerofactory-kanban move {task_id} done\n"
        f"   (or if human review or external dependencies are required, run:\n"
        f"   hermes zerofactory-kanban move {task_id} blocked --reason \"review-required\")\n"
        f"5. Provide a summary of your changes.\n"
    )

    cmd = [
        hermes_bin,
        "-p", assignee,
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
    env["PYTHONUNBUFFERED"] = "1"

    try:
        log_f = open(log_file_path, "ab")
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

        # Detect session_id from profile's state.db
        session_id = None
        state_db_path = Path.home() / ".hermes" / "profiles" / assignee / "state.db"
        if not state_db_path.exists():
            try:
                resolved_parents = Path(__file__).resolve().parents
                if len(resolved_parents) > 3:
                    p_repo = resolved_parents[3] / assignee / "state.db"
                    if p_repo.exists():
                        state_db_path = p_repo
            except Exception:
                pass
        if not state_db_path.exists():
            state_db_path = Path(__file__).resolve().parent.parent.parent / assignee / "state.db"
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
                    s_cur.execute("SELECT id FROM sessions ORDER BY started_at DESC LIMIT 1")
                    s_row = s_cur.fetchone()
                    if s_row:
                        session_id = s_row[0]
            except Exception:
                pass

        return proc.pid, session_id
    except Exception as e:
        _log.error("Failed to spawn %s worker for task %s: %s", assignee, task_id, e)
        return None, None


def reap_active_workers(cursor: sqlite3.Cursor, now: int) -> int:
    """Check running tasks and reap finished/crashed worker processes."""
    cursor.execute("SELECT id, title, metadata FROM tasks WHERE status = 'running'")
    running_rows = cursor.fetchall()
    reaped = 0

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

    return reaped


def setup_worktree(cursor: sqlite3.Cursor, task_id: str, title: str, assignee: str, tenant: Optional[str], db_path: Path) -> Optional[str]:
    """Ensure git worktree and branch exist for task execution."""
    valid_profiles = ("builder", "reviewer", "orchestrator")
    if not assignee or assignee == "unassigned" or assignee not in valid_profiles:
        if "[reviewer]" in title:
            assignee = "reviewer"
        elif "[builder]" in title:
            assignee = "builder"
        elif "[orchestrator]" in title:
            assignee = "orchestrator"
        else:
            assignee = "builder"
        cursor.execute("UPDATE tasks SET assignee = ?, skills = '[]' WHERE id = ?", (assignee, task_id))

    if os.environ.get("ZEROFACTORY_KANBAN_SKIP_GIT"):
        return None

    # Resolve repo path
    if tenant:
        tenant_path = Path(os.path.expanduser(tenant))
        if tenant_path.is_absolute():
            repo_path = tenant_path
            reponame = tenant_path.name
        else:
            reponame = tenant
            repo_path = Path(os.getcwd()).parent / reponame
    else:
        repo_path = Path(os.getcwd())
        reponame = repo_path.name

    if not repo_path.exists():
        git_dir = Path.home() / "git" / reponame
        if git_dir.exists():
            repo_path = git_dir
        else:
            repo_path = Path(os.getcwd())
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
                        SELECT id, title, workspace_path, assignee, tenant FROM tasks
                        WHERE status = 'todo' OR (status = 'ready' AND assignee = 'unassigned')
                        ORDER BY CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 WHEN 'P3' THEN 3 ELSE 4 END
                        LIMIT ?
                    """, (limit,))
                    for row in cursor.fetchall():
                        task_id = str(row["id"])
                        assignee = row["assignee"]
                        title = row["title"] or ""
                        tenant = row["tenant"] if "tenant" in row.keys() else None

                        setup_worktree(cursor, task_id, title, assignee, tenant, db_path)
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
                        SELECT id, title, description, priority, workspace_path, assignee, tenant, branch_name, metadata FROM tasks
                        WHERE status = 'ready' AND assignee != 'reviewer'
                        ORDER BY CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 WHEN 'P3' THEN 3 ELSE 4 END, created_at ASC
                        LIMIT ?
                    """, (spawn_limit,))
                    for row in cursor.fetchall():
                        task_id = str(row["id"])
                        assignee = row["assignee"] or "builder"
                        title = row["title"] or ""
                        description = row["description"] or ""
                        priority = row["priority"] or "P2"
                        tenant = row["tenant"] if "tenant" in row.keys() else None
                        workspace_path = row["workspace_path"]
                        branch_name = row["branch_name"] if "branch_name" in row.keys() else None

                        if not workspace_path or not Path(workspace_path).exists():
                            wt = setup_worktree(cursor, task_id, title, assignee, tenant, db_path)
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
                if not os.environ.get("ZEROFACTORY_KANBAN_SKIP_GIT"):
                    cursor.execute("""
                        SELECT id, title, workspace_path, assignee, tenant, branch_name, pr_url FROM tasks
                        WHERE (status IN ('blocked', 'done') AND workspace_path IS NOT NULL AND (pr_url IS NULL OR pr_url = ''))
                           OR (pr_url IS NOT NULL AND pr_url != '' AND assignee = 'reviewer')
                    """)
                    for row in cursor.fetchall():
                        task_id = str(row["id"])
                        title = row["title"]
                        workspace_path = row["workspace_path"]
                        assignee = row["assignee"]
                        tenant = row["tenant"] if "tenant" in row.keys() else None

                        if not workspace_path or not Path(workspace_path).exists():
                            continue

                        # Determine repository root
                        repo_path = Path(workspace_path).parent.parent
                        if not (repo_path / ".git").exists():
                            repo_path = Path(os.getcwd())

                        if assignee != "reviewer":
                            # Author finished work -> git commit, push, create PR, hand off to reviewer
                            try:
                                subprocess.run(["git", "add", "."], check=True, cwd=workspace_path, capture_output=True)
                                subprocess.run(["git", "commit", "-m", f"Complete task {task_id}: {title}"], check=True, cwd=workspace_path, capture_output=True)
                                subprocess.run(["git", "push", "-u", "origin", f"task/{task_id}"], check=True, cwd=workspace_path, capture_output=True)

                                if "[PR Opened" not in title:
                                    pr_title = f"Task {task_id}: {title}"
                                    pr_body = f"Automated PR for task {task_id}\n\nCompleted by: @{assignee}"
                                    pr_res = subprocess.run(["gh", "pr", "create", "--title", pr_title, "--body", pr_body], check=True, cwd=workspace_path, capture_output=True, text=True)
                                    pr_url = pr_res.stdout.strip()
                                else:
                                    pr_url = row["pr_url"] or ""

                                # Cleanup author worktree
                                subprocess.run(["git", "worktree", "remove", workspace_path, "--force"], check=False, cwd=repo_path, capture_output=True)

                                new_title = title
                                if not re.search(r"\[PR Opened by .*?\]", title):
                                    new_title = f"{title} [PR Opened by {assignee}]"

                                cursor.execute(
                                    "UPDATE tasks SET title = ?, assignee = 'reviewer', pr_url = ?, status = 'ready', updated_at = ? WHERE id = ?",
                                    (new_title, pr_url, now, task_id)
                                )
                                setup_worktree(cursor, task_id, new_title, "reviewer", tenant, db_path)
                                cursor.execute(
                                    "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'pr_opened', ?, ?)",
                                    (task_id, f"PR created, routed to reviewer: {pr_url}", now)
                                )
                                prs_opened += 1
                            except Exception as e:
                                _log.info("Task %s commit/PR skipped: %s", task_id, e)
                        else:
                            # Reviewer finished review -> inspect GitHub PR state
                            try:
                                subprocess.run(["git", "worktree", "remove", workspace_path, "--force"], check=False, cwd=repo_path, capture_output=True)
                                res = subprocess.run(
                                    ["gh", "pr", "view", f"task/{task_id}", "--json", "reviewDecision,state,url"],
                                    capture_output=True, text=True, cwd=repo_path
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
                                        author = match.group(1) if match else "builder"
                                        cursor.execute(
                                            "UPDATE tasks SET assignee = ?, status = 'ready', updated_at = ? WHERE id = ?",
                                            (author, now, task_id)
                                        )
                                        setup_worktree(cursor, task_id, title, author, tenant, db_path)
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
