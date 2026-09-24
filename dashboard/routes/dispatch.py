"""Zero Factory Dashboard — Dispatcher Controls, Stuck Task Health, and Legacy Import."""

from __future__ import annotations

import logging
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)
_DASHBOARD_ROOT = str(Path(__file__).resolve().parent.parent)
if _DASHBOARD_ROOT not in sys.path:
    sys.path.insert(0, _DASHBOARD_ROOT)

from fastapi import APIRouter, HTTPException

try:
    from ..db import get_db_conn, get_db_path
    from ..models import VALID_ASSIGNEES, VALID_STATUSES, normalize_assignee
except (ImportError, ValueError):
    from db import get_db_conn, get_db_path  # type: ignore
    from models import VALID_ASSIGNEES, VALID_STATUSES, normalize_assignee  # type: ignore

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
        "stuck_tasks": stuck_tasks
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
        raise HTTPException(status_code=404, detail=f"Task {task_id} is not currently running or could not be reaped")
    return {"ok": True, "reaped": True, "task": res["reaped_tasks"][0]}


@router.post("/import-legacy")
def import_legacy():
    """Import tasks from legacy ~/.hermes/kanban.db into Zero Factory Kanban."""
    legacy_db = Path.home() / ".hermes" / "kanban.db"
    if not legacy_db.exists():
        return {"ok": False, "message": "Legacy database ~/.hermes/kanban.db does not exist."}

    imported_tasks = 0
    imported_links = 0
    imported_comments = 0

    try:
        with sqlite3.connect(f"file:{legacy_db.resolve()}?mode=ro", uri=True, timeout=5.0) as leg_conn:
            leg_conn.row_factory = sqlite3.Row
            leg_cur = leg_conn.cursor()

            leg_cur.execute("SELECT * FROM tasks")
            legacy_tasks = leg_cur.fetchall()

            leg_cur.execute("SELECT * FROM task_links")
            legacy_links = leg_cur.fetchall()

            leg_cur.execute("SELECT * FROM task_comments")
            legacy_comments = leg_cur.fetchall()

        now = int(time.time())
        with get_db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT slug FROM boards ORDER BY created_at ASC LIMIT 1")
            target_board_row = cursor.fetchone()
            target_board = target_board_row[0] if target_board_row else "zerofactory"

            for t in legacy_tasks:
                keys = t.keys()
                t_id = t["id"]
                cursor.execute("SELECT 1 FROM tasks WHERE id = ?", (t_id,))
                if cursor.fetchone():
                    continue

                raw_prio = t["priority"] if "priority" in keys else 1
                prio_str = "P2"
                if isinstance(raw_prio, int):
                    if raw_prio >= 3:
                        prio_str = "P0"
                    elif raw_prio == 2:
                        prio_str = "P1"
                    elif raw_prio == 1:
                        prio_str = "P2"
                    else:
                        prio_str = "P3"
                elif isinstance(raw_prio, str):
                    if raw_prio in ("P0", "P1", "P2", "P3"):
                        prio_str = raw_prio

                raw_status = t["status"] if "status" in keys else "triage"
                status_val = raw_status if raw_status in VALID_STATUSES else "triage"

                raw_asgn = t["assignee"] if "assignee" in keys else "unassigned"
                assignee_val = normalize_assignee(raw_asgn) if raw_asgn in VALID_ASSIGNEES else "unassigned"

                desc_val = (t["description"] if "description" in keys else None) or (t["body"] if "body" in keys else None) or ""

                cursor.execute("""
                    INSERT OR IGNORE INTO tasks (
                        id, board_slug, title, description, status, assignee, priority,
                        workspace_path, workspace_kind, branch_name, pr_url, tenant,
                        skills, tags, metadata, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', '[]', '{}', ?, ?)
                """, (
                    t_id,
                    target_board,
                    (t["title"] if "title" in keys else None) or "Untitled Task",
                    desc_val,
                    status_val,
                    assignee_val,
                    prio_str,
                    t["workspace_path"] if "workspace_path" in keys else None,
                    t["workspace_kind"] if "workspace_kind" in keys else "worktree",
                    f"task/{t_id}",
                    None,
                    t["tenant"] if "tenant" in keys and t["tenant"] else "",
                    t["created_at"] if "created_at" in keys and t["created_at"] else now,
                    t["updated_at"] if "updated_at" in keys and t["updated_at"] else now
                ))
                imported_tasks += 1

            for l in legacy_links:
                cursor.execute(
                    "INSERT OR IGNORE INTO task_links (parent_id, child_id, created_at) VALUES (?, ?, ?)",
                    (l["parent_id"], l["child_id"], now)
                )
                imported_links += 1

            for c in legacy_comments:
                cursor.execute(
                    "INSERT OR IGNORE INTO task_comments (task_id, author, body, created_at) VALUES (?, ?, ?, ?)",
                    (c["task_id"], c["author"] or "agent", c["body"] or "", c["created_at"] if "created_at" in c.keys() and c["created_at"] else now)
                )
                imported_comments += 1

            conn.commit()

        return {
            "ok": True,
            "imported_tasks": imported_tasks,
            "imported_links": imported_links,
            "imported_comments": imported_comments,
            "message": f"Successfully imported {imported_tasks} tasks from legacy Kanban."
        }
    except Exception as e:
        _log.error("Failed to import legacy kanban tasks: %s", e)
        return {"ok": False, "error": str(e)}
