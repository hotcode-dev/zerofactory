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
DISPATCH_INTERVAL_SECONDS = 30
_dispatcher_thread: Optional[threading.Thread] = None
_dispatcher_lock = threading.Lock()


def get_db_path() -> Path:
    env_path = os.environ.get("ZEROFACTORY_KANBAN_DB")
    if env_path:
        return Path(env_path)
    return Path.home() / ".hermes" / "zerofactory_kanban.db"


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
    prs_opened = 0
    now = int(time.time())

    with _dispatcher_lock:
        try:
            with sqlite3.connect(db_path) as conn:
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

                # 3. Handle PR lifecycle (author handoff -> PR creation; reviewer handoff -> PR state)
                #
                # The author branch moves a finished task to status='ready' (assigned to the
                # reviewer) after opening the PR, so the reviewer handoff must also be
                # reachable from 'ready' -- otherwise a task the builder finishes stalls in
                # 'ready' forever, its PR is never checked for MERGED, and it starves a WIP slot.
                if not os.environ.get("ZEROFACTORY_KANBAN_SKIP_GIT"):
                    cursor.execute("""
                        SELECT id, title, workspace_path, assignee, tenant, branch_name, pr_url, status FROM tasks
                        WHERE status IN ('blocked', 'done', 'ready') AND workspace_path IS NOT NULL
                    """)
                    for row in cursor.fetchall():
                        task_id = str(row["id"])
                        status = row["status"]
                        assignee = row["assignee"]
                        pr_url_existing = (row["pr_url"] or "").strip()
                        has_pr = bool(pr_url_existing)

                        # Only reconcile tasks that actually have PR work to do:
                        #  - reviewer handoff: the reviewer is on it, a PR exists, and the
                        #    task is not already 'done' (avoids re-polling merged tasks); or
                        #  - author handoff: a non-reviewer agent finished (moved the task to
                        #    'blocked' for review or 'done') so we commit/push/open the PR.
                        # A plain 'ready' task still waiting for its agent is intentionally
                        # skipped so it is never mis-handled as an author who just finished.
                        is_reviewer_handoff = (assignee == "reviewer") and has_pr and status != "done"
                        is_author_handoff = (assignee != "reviewer") and status in ("blocked", "done")

                        if not (is_reviewer_handoff or is_author_handoff):
                            continue

                        title = row["title"]
                        workspace_path = row["workspace_path"]
                        tenant = row["tenant"] if "tenant" in row.keys() else None

                        if not workspace_path or not Path(workspace_path).exists():
                            continue

                        # Determine repository root
                        repo_path = Path(workspace_path).parent.parent
                        if not (repo_path / ".git").exists():
                            repo_path = Path(os.getcwd())

                        if is_reviewer_handoff:
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
                        else:
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
                                    pr_url = pr_url_existing or ""

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

                conn.commit()

            return {
                "ok": True,
                "unblocked": unblocked,
                "promoted": promoted,
                "prs_opened": prs_opened,
                "message": f"Dispatch cycle complete: {unblocked} unblocked, {promoted} promoted, {prs_opened} PRs opened."
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
