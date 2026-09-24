"""Zero Factory Dashboard — Metrics, Stats, and Activities Routes (/stats, /activities)."""

from __future__ import annotations

import logging
import os
import sqlite3
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)
_DASHBOARD_ROOT = str(Path(__file__).resolve().parent.parent)
if _DASHBOARD_ROOT not in sys.path:
    sys.path.insert(0, _DASHBOARD_ROOT)

from fastapi import APIRouter, Query

try:
    from ..db import get_db_conn, init_db, row_to_dict
    from ..models import ACTIVITY_ACTORS
    from ..session_service import resolve_task_session_progress
except (ImportError, ValueError):
    from db import get_db_conn, init_db, row_to_dict  # type: ignore
    from models import ACTIVITY_ACTORS  # type: ignore
    from session_service import resolve_task_session_progress  # type: ignore

_log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/stats")
def get_stats(board: Optional[str] = None):
    """Get board metrics and task distribution."""
    init_db()
    with get_db_conn() as conn:
        cursor = conn.cursor()
        base_filter = " WHERE 1=1"
        params: List[Any] = []
        if board:
            base_filter += " AND board_slug = ?"
            params.append(board)

        # Status breakdown
        cursor.execute(f"SELECT status, COUNT(*) as count FROM tasks{base_filter} GROUP BY status", params)
        status_counts = {r["status"]: r["count"] for r in cursor.fetchall()}

        # Priority breakdown
        cursor.execute(f"SELECT priority, COUNT(*) as count FROM tasks{base_filter} GROUP BY priority", params)
        priority_counts = {r["priority"]: r["count"] for r in cursor.fetchall()}

        # Assignee breakdown
        cursor.execute(f"SELECT assignee, COUNT(*) as count FROM tasks{base_filter} GROUP BY assignee", params)
        assignee_counts = {r["assignee"]: r["count"] for r in cursor.fetchall()}

        # Total tasks
        cursor.execute(f"SELECT COUNT(*) as count FROM tasks{base_filter}", params)
        total_tasks = cursor.fetchone()["count"]

        # Active worktrees count
        cursor.execute(f"SELECT COUNT(*) as count FROM tasks{base_filter} AND workspace_path IS NOT NULL AND status IN ('running')", params)
        active_worktrees = cursor.fetchone()["count"]

        # Pull requests count
        cursor.execute(f"SELECT COUNT(*) as count FROM tasks{base_filter} AND pr_url IS NOT NULL AND pr_url != ''", params)
        pr_count = cursor.fetchone()["count"]

        return {
            "ok": True,
            "total": total_tasks,
            "columns": {
                "triage": status_counts.get("triage", 0),
                "todo": status_counts.get("todo", 0),
                "running": status_counts.get("running", 0),
                "blocked": status_counts.get("blocked", 0),
                "done": status_counts.get("done", 0),
            },
            "priorities": priority_counts,
            "assignees": assignee_counts,
            "active_worktrees": active_worktrees,
            "pr_count": pr_count
        }


def get_orchestrator_scan_activities(board_slug: Optional[str] = None, limit: int = 20) -> List[Dict[str, Any]]:
    db_path = os.path.expanduser("~/.hermes/profiles/zf-orchestrator/cron/executions.db")
    if not os.path.exists(db_path):
        return []
    try:
        with sqlite3.connect(db_path) as conn:
            conn.row_factory = sqlite3.Row
            q = "SELECT * FROM executions WHERE job_id LIKE '%scanner%' "
            p: List[Any] = []
            if board_slug and board_slug != "all":
                q += "AND job_id LIKE ? "
                p.append(f"%{board_slug}%")
            q += "ORDER BY claimed_at DESC LIMIT ?"
            p.append(limit)
            rows = conn.execute(q, p).fetchall()
            res = []
            for r in rows:
                try:
                    ts = int(datetime.fromisoformat(r["claimed_at"]).timestamp())
                except Exception:
                    ts = int(time.time())
                b_slug = r["job_id"].replace("zero-factory-improvement-scanner-", "")
                res.append({
                    "id": f"scan-{r['id'][:8]}",
                    "task_id": None,
                    "actor": "zf-orchestrator",
                    "action": "scan",
                    "details": f"Codebase Improvement Scan ({r['status']}): inspected repository for tech debt, bugs & test gaps",
                    "created_at": ts,
                    "task_title": "Codebase Improvement Scanner",
                    "board_slug": b_slug,
                    "task_status": "completed",
                    "task_priority": "P0",
                    "task_assignee": "zf-orchestrator"
                })
            return res
    except Exception:
        return []


def count_orchestrator_scans_today(board_slug: Optional[str] = None) -> int:
    db_path = os.path.expanduser("~/.hermes/profiles/zf-orchestrator/cron/executions.db")
    if not os.path.exists(db_path):
        return 0
    try:
        with sqlite3.connect(db_path) as conn:
            one_day_ago_ts = time.time() - 86400
            q = "SELECT claimed_at FROM executions WHERE job_id LIKE '%scanner%'"
            p: List[Any] = []
            if board_slug and board_slug != "all":
                q += " AND job_id LIKE ?"
                p.append(f"%{board_slug}%")
            rows = conn.execute(q, p).fetchall()
            count = 0
            for r in rows:
                claimed = r[0]
                if not claimed:
                    continue
                try:
                    dt = datetime.fromisoformat(claimed)
                    if dt.timestamp() >= one_day_ago_ts:
                        count += 1
                except Exception:
                    pass
            return count
    except Exception:
        return 0


@router.get("/activities")
def get_activities(
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    actor: Optional[str] = None,
    assignee: Optional[str] = None,
    action: Optional[str] = None,
    board_slug: Optional[str] = None,
    search: Optional[str] = None,
):
    try:
        init_db()
    except Exception:
        pass
    with get_db_conn() as conn:
        cursor = conn.cursor()

        where_clauses = ["1=1"]
        params: List[Any] = []

        if actor and actor != "all":
            if actor in ("zf-orchestrator", "zf-builder", "zf-reviewer", "dispatcher", "user"):
                where_clauses.append("a.actor = ?")
                params.append(actor)
            elif actor == "other":
                where_clauses.append("""(
                    a.actor NOT IN ('zf-orchestrator', 'zf-builder', 'zf-reviewer', 'dispatcher', 'user')
                )""")
            else:
                where_clauses.append("a.actor = ?")
                params.append(actor)

        if assignee and assignee != "all":
            where_clauses.append("(t.assignee = ? OR a.actor = ?)")
            params.extend([assignee, assignee])

        if action and action != "all":
            where_clauses.append("a.action = ?")
            params.append(action)

        if board_slug and board_slug != "all":
            where_clauses.append("t.board_slug = ?")
            params.append(board_slug)

        if search and search.strip():
            term = f"%{search.strip()}%"
            where_clauses.append("(a.details LIKE ? OR a.actor LIKE ? OR a.action LIKE ? OR t.title LIKE ? OR a.task_id LIKE ?)")
            params.extend([term, term, term, term, term])

        where_str = " AND ".join(where_clauses)

        count_sql = f"""
            SELECT COUNT(*) as cnt
            FROM task_activity a
            LEFT JOIN tasks t ON a.task_id = t.id
            WHERE {where_str}
        """
        cursor.execute(count_sql, params)
        total_count = cursor.fetchone()["cnt"]

        query_sql = f"""
            SELECT 
                a.id,
                a.task_id,
                CASE 
                    WHEN a.actor = 'zf-orchestrator' THEN 'zf-orchestrator' 
                    WHEN a.actor = 'zf-builder' THEN 'zf-builder' 
                    WHEN a.actor = 'zf-reviewer' THEN 'zf-reviewer' 
                    WHEN a.actor = 'dispatcher' THEN 'dispatcher' 
                    WHEN a.actor = 'user' THEN 'user'
                    ELSE 'other' 
                END AS actor,
                a.action,
                a.details,
                a.created_at,
                t.title AS task_title,
                t.board_slug,
                t.status AS task_status,
                t.priority AS task_priority,
                t.assignee AS task_assignee
            FROM task_activity a
            LEFT JOIN tasks t ON a.task_id = t.id
            WHERE {where_str}
            ORDER BY a.created_at DESC, a.id DESC
            LIMIT ? OFFSET ?
        """
        try:
            actual_limit = int(getattr(limit, "default", limit) if hasattr(limit, "default") else limit)
        except Exception:
            actual_limit = 50
        try:
            actual_offset = int(getattr(offset, "default", offset) if hasattr(offset, "default") else offset)
        except Exception:
            actual_offset = 0

        query_params = list(params) + [actual_limit, actual_offset]
        cursor.execute(query_sql, query_params)
        activities = [dict(r) for r in cursor.fetchall()]

        if (not actor or actor in ("all", "zf-orchestrator")) and (not action or action in ("all", "scan")):
            scan_acts = get_orchestrator_scan_activities(board_slug, limit=actual_limit)
            if scan_acts:
                activities = sorted(activities + scan_acts, key=lambda x: x.get("created_at", 0), reverse=True)[:actual_limit]
                total_count += len(scan_acts)

        cursor.execute("SELECT DISTINCT action FROM task_activity WHERE action != '' ORDER BY action ASC")
        actions = [r["action"] for r in cursor.fetchall()]

        cursor.execute("SELECT DISTINCT board_slug FROM tasks WHERE board_slug != '' ORDER BY board_slug ASC")
        boards = [r["board_slug"] for r in cursor.fetchall()]

        cursor.execute("SELECT DISTINCT assignee FROM tasks WHERE assignee != '' AND assignee != 'unassigned' ORDER BY assignee ASC")
        assignees = [r["assignee"] for r in cursor.fetchall()]

        known_agents = [
            ("zf-orchestrator", "Orchestrator", "Decomposes goals, designs architecture, coordinates board"),
            ("zf-builder", "Builder", "Executes tasks, tests code, creates PRs in Git worktrees"),
            ("zf-reviewer", "Reviewer", "Performs thematic 3-round reviews, approves or requests changes"),
            ("dispatcher", "Dispatcher Engine", "Supervises process lifecycle, auto-unblocks and dispatches workers"),
        ]

        now = int(time.time())
        one_day_ago = now - 86400

        agents_data = []
        for agent_id, agent_name, agent_role in known_agents:
            agent_status = "idle"
            current_task = None
            session_prog = None
            last_activity = None
            actions_today_cnt = 0

            if agent_id == "dispatcher":
                agent_status = "active"
                cursor.execute("SELECT * FROM task_activity WHERE actor = 'dispatcher' ORDER BY created_at DESC LIMIT 1")
                last_act_row = cursor.fetchone()
                last_activity = dict(last_act_row) if last_act_row else None
                cursor.execute("SELECT COUNT(*) as cnt FROM task_activity WHERE actor = 'dispatcher' AND created_at >= ?", (one_day_ago,))
                actions_today_cnt = cursor.fetchone()["cnt"]
            else:
                running_task_row = None
                if board_slug and board_slug != "all":
                    cursor.execute("""
                        SELECT * FROM tasks 
                        WHERE (assignee = ? OR assignee LIKE ?) 
                          AND status = 'running' AND board_slug = ?
                        ORDER BY updated_at DESC LIMIT 1
                    """, (agent_id, f"%{agent_id}%", board_slug))
                    running_task_row = cursor.fetchone()

                if not running_task_row:
                    cursor.execute("""
                        SELECT * FROM tasks 
                        WHERE (assignee = ? OR assignee LIKE ?) 
                          AND status = 'running'
                        ORDER BY updated_at DESC LIMIT 1
                    """, (agent_id, f"%{agent_id}%"))
                    running_task_row = cursor.fetchone()

                if running_task_row:
                    t_dict = row_to_dict(running_task_row)
                    prog = resolve_task_session_progress(t_dict, backfill=False)
                    session_prog = prog
                    if prog.get("is_stuck"):
                        agent_status = "stuck"
                    elif prog.get("is_alive") or prog.get("running_seconds", 0) > 0:
                        agent_status = "active"
                    else:
                        agent_status = "active"

                    current_task = {
                        "id": t_dict["id"],
                        "title": t_dict["title"],
                        "board_slug": t_dict["board_slug"],
                        "priority": t_dict["priority"],
                        "running_seconds": prog.get("running_seconds", 0)
                    }
                else:
                    agent_status = "idle"

                if agent_id == "zf-orchestrator":
                    cursor.execute("""
                        SELECT a.*, t.title as task_title, t.board_slug
                        FROM task_activity a
                        LEFT JOIN tasks t ON a.task_id = t.id
                        WHERE a.actor = 'zf-orchestrator'
                        ORDER BY a.created_at DESC, a.id DESC LIMIT 1
                    """)
                    last_act_row = cursor.fetchone()
                    last_activity = dict(last_act_row) if last_act_row else None

                    scan_acts = get_orchestrator_scan_activities(board_slug, limit=1)
                    if scan_acts:
                        if not last_activity or scan_acts[0]["created_at"] > last_activity.get("created_at", 0):
                            last_activity = scan_acts[0]

                    cursor.execute("""
                        SELECT COUNT(*) as cnt FROM task_activity a
                        LEFT JOIN tasks t ON a.task_id = t.id
                        WHERE a.actor = 'zf-orchestrator'
                          AND a.created_at >= ?
                    """, (one_day_ago,))
                    actions_today_cnt = cursor.fetchone()["cnt"] + count_orchestrator_scans_today(board_slug)

                elif agent_id == "zf-builder":
                    cursor.execute("""
                        SELECT a.*, t.title as task_title, t.board_slug
                        FROM task_activity a
                        LEFT JOIN tasks t ON a.task_id = t.id
                        WHERE a.actor = 'zf-builder'
                           OR (a.actor = 'dispatcher' AND (a.details LIKE '%zf-builder%' OR a.action IN ('worker_done', 'worker_failed')))
                        ORDER BY a.created_at DESC, a.id DESC LIMIT 1
                    """)
                    last_act_row = cursor.fetchone()
                    last_activity = dict(last_act_row) if last_act_row else None

                    cursor.execute("""
                        SELECT COUNT(*) as cnt FROM task_activity a
                        LEFT JOIN tasks t ON a.task_id = t.id
                        WHERE (a.actor = 'zf-builder'
                           OR (a.actor = 'dispatcher' AND (a.details LIKE '%zf-builder%' OR a.action IN ('worker_done', 'worker_failed'))))
                          AND a.created_at >= ?
                    """, (one_day_ago,))
                    actions_today_cnt = cursor.fetchone()["cnt"]

                elif agent_id == "zf-reviewer":
                    cursor.execute("""
                        SELECT a.*, t.title as task_title, t.board_slug
                        FROM task_activity a
                        LEFT JOIN tasks t ON a.task_id = t.id
                        WHERE a.actor = 'zf-reviewer'
                           OR (a.actor = 'dispatcher' AND (a.details LIKE '%zf-reviewer%' OR a.action IN ('merged', 'approved')))
                        ORDER BY a.created_at DESC, a.id DESC LIMIT 1
                    """)
                    last_act_row = cursor.fetchone()
                    last_activity = dict(last_act_row) if last_act_row else None

                    cursor.execute("""
                        SELECT COUNT(*) as cnt FROM task_activity a
                        LEFT JOIN tasks t ON a.task_id = t.id
                        WHERE (a.actor = 'zf-reviewer'
                           OR (a.actor = 'dispatcher' AND (a.details LIKE '%zf-reviewer%' OR a.action IN ('merged', 'approved'))))
                          AND a.created_at >= ?
                    """, (one_day_ago,))
                    actions_today_cnt = cursor.fetchone()["cnt"]

                else:
                    cursor.execute("""
                        SELECT a.*, t.title as task_title, t.board_slug
                        FROM task_activity a
                        LEFT JOIN tasks t ON a.task_id = t.id
                        WHERE a.actor = ? OR (t.assignee = ? AND a.actor = 'dispatcher')
                        ORDER BY a.created_at DESC, a.id DESC LIMIT 1
                    """, (agent_id, agent_id))
                    last_act_row = cursor.fetchone()
                    last_activity = dict(last_act_row) if last_act_row else None

                    cursor.execute("""
                        SELECT COUNT(*) as cnt FROM task_activity a
                        LEFT JOIN tasks t ON a.task_id = t.id
                        WHERE (a.actor = ? OR (t.assignee = ? AND a.actor = 'dispatcher'))
                          AND a.created_at >= ?
                    """, (agent_id, agent_id, one_day_ago))
                    actions_today_cnt = cursor.fetchone()["cnt"]

            agents_data.append({
                "id": agent_id,
                "name": agent_name,
                "role": agent_role,
                "status": agent_status,
                "current_task": current_task,
                "session_progress": session_prog,
                "last_activity": last_activity,
                "actions_today": actions_today_cnt
            })

        cursor.execute("SELECT COUNT(*) as cnt FROM task_activity")
        overall_total = cursor.fetchone()["cnt"]

        cursor.execute("SELECT COUNT(*) as cnt FROM task_activity WHERE created_at >= ?", (one_day_ago,))
        overall_today = cursor.fetchone()["cnt"]

        cursor.execute("SELECT action, COUNT(*) as cnt FROM task_activity GROUP BY action ORDER BY cnt DESC")
        action_breakdown = {r["action"]: r["cnt"] for r in cursor.fetchall()}

        total_scans = count_orchestrator_scans_today()
        overall_total += total_scans
        overall_today += total_scans
        if total_scans > 0:
            action_breakdown["scan"] = total_scans

        active_agents_count = sum(1 for a in agents_data if a["status"] == "active" and a["id"] != "dispatcher")

        return {
            "ok": True,
            "activities": activities,
            "total": total_count,
            "limit": limit,
            "offset": offset,
            "filter_options": {
                "actors": ACTIVITY_ACTORS,
                "actions": sorted(list(set(actions + ["scan"]))),
                "boards": boards,
                "assignees": sorted(list(set(assignees + ["zf-orchestrator", "zf-builder", "zf-reviewer"])))
            },
            "agents": agents_data,
            "stats": {
                "total_activities": overall_total,
                "active_agents": active_agents_count,
                "actions_today": overall_today,
                "action_breakdown": action_breakdown
            }
        }
