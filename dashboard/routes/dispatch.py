"""Zero Factory Dashboard — Dispatcher Controls and Stuck Task Health."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)
_DASHBOARD_ROOT = str(Path(__file__).resolve().parent.parent)
if _DASHBOARD_ROOT not in sys.path:
    sys.path.insert(0, _DASHBOARD_ROOT)

from fastapi import APIRouter, HTTPException

try:
    from ..db import get_db_conn, get_db_path
except (ImportError, ValueError):
    from db import get_db_conn, get_db_path  # type: ignore

_log = logging.getLogger(__name__)

router = APIRouter()


@router.post("/dispatch/run")
def trigger_dispatch():
    """Trigger atomic dependency unblocking, WIP promotion, worktree setup, and PR review routing."""
    try:
        from ...dispatcher import run_dispatch_cycle
    except Exception:
        import sys

        parent_dir = str(Path(__file__).resolve().parent.parent.parent)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        from dispatcher import run_dispatch_cycle  # type: ignore

    return run_dispatch_cycle(get_db_path())


@router.get("/dispatch/status")
def get_dispatch_status():
    """Get active worktree directories and dispatcher status."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, assignee, status, workspace_path, branch_name, pr_url, updated_at
            FROM tasks
            WHERE status IN ('running', 'blocked')
            ORDER BY updated_at DESC
        """)
        in_flight = [dict(r) for r in cursor.fetchall()]
        return {"ok": True, "in_flight": in_flight, "count": len(in_flight)}


@router.get("/health/stuck-tasks")
def get_stuck_tasks():
    """Inspect all currently running tasks and report running/idle duration and stuckness."""
    try:
        from ...dispatcher import check_stuck_tasks
    except Exception:
        import sys

        parent_dir = str(Path(__file__).resolve().parent.parent.parent)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        from dispatcher import check_stuck_tasks  # type: ignore

    tasks = check_stuck_tasks(db_path=get_db_path())
    stuck_tasks = [t for t in tasks if t["is_stuck"]]
    return {
        "ok": True,
        "running_count": len(tasks),
        "stuck_count": len(stuck_tasks),
        "tasks": tasks,
        "stuck_tasks": stuck_tasks,
    }


@router.post("/health/reap-stuck")
def reap_all_stuck_tasks():
    """Reap all stuck running tasks, terminating processes and moving tasks to blocked."""
    try:
        from ...dispatcher import reap_stuck_tasks
    except Exception:
        import sys

        parent_dir = str(Path(__file__).resolve().parent.parent.parent)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        from dispatcher import reap_stuck_tasks  # type: ignore

    return reap_stuck_tasks(db_path=get_db_path())


@router.post("/tasks/{task_id}/reap")
def reap_single_task(task_id: str):
    """Manually reap/terminate a specific running task and move it to blocked."""
    try:
        from ...dispatcher import reap_stuck_tasks
    except Exception:
        import sys

        parent_dir = str(Path(__file__).resolve().parent.parent.parent)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        from dispatcher import reap_stuck_tasks  # type: ignore

    res = reap_stuck_tasks(task_id=task_id, db_path=get_db_path())
    if not res.get("reaped_tasks"):
        raise HTTPException(
            status_code=404,
            detail=f"Task {task_id} is not currently running or could not be reaped",
        )
    return {"ok": True, "reaped": True, "task": res["reaped_tasks"][0]}
