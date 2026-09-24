"""Zero Factory Dashboard — Agent Telemetry and Sessions Routes (/agents, /sessions)."""

from __future__ import annotations

import logging
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path
from typing import Optional

_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)
_DASHBOARD_ROOT = str(Path(__file__).resolve().parent.parent)
if _DASHBOARD_ROOT not in sys.path:
    sys.path.insert(0, _DASHBOARD_ROOT)

from fastapi import APIRouter

try:
    from ..db import get_db_conn, init_db
    from ..session_service import (
        AGENT_ICONS,
        AGENT_LABELS,
        _resolve_profile_state_db_dyn,
        list_all_sessions as _list_all_sessions,
    )
except (ImportError, ValueError):
    from db import get_db_conn, init_db  # type: ignore
    from session_service import (  # type: ignore
        AGENT_ICONS,
        AGENT_LABELS,
        _resolve_profile_state_db_dyn,
        list_all_sessions as _list_all_sessions,
    )

_log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/sessions")
def list_all_sessions(
    role: Optional[str] = None,
    status: Optional[str] = None,
    board_slug: Optional[str] = None,
    limit: int = 50
):
    """List recent and active AI agent sessions across Orchestrator, Builder, and Reviewer."""
    return _list_all_sessions(role=role, status=status, board_slug=board_slug, limit=limit)


@router.get("/agents")
def get_agents_status(board_slug: Optional[str] = None):
    """Retrieve real-time status and telemetry for the 3 Zero Factory specialist agents."""
    init_db()
    profiles = ["zf-orchestrator", "zf-builder", "zf-reviewer"]
    role_descriptions = {
        "zf-orchestrator": "Backlog planning, triage, workflow coordination & improvement scans",
        "zf-builder": "Autonomous code implementation, bug fixing, test writing & pull requests",
        "zf-reviewer": "Automated pull request review, edge case verification & test suite execution"
    }

    running_tasks_by_assignee = {}
    with get_db_conn() as conn:
        cursor = conn.cursor()
        query = "SELECT id, title, board_slug, assignee, workspace_path, updated_at FROM tasks WHERE status = 'running'"
        params = []
        if board_slug and board_slug != "all":
            query += " AND board_slug = ?"
            params.append(board_slug)
        cursor.execute(query, params)
        for row in cursor.fetchall():
            asgn = row[3]
            if asgn:
                running_tasks_by_assignee[asgn] = {
                    "id": row[0],
                    "title": row[1],
                    "board_slug": row[2],
                    "workspace_path": row[4],
                    "updated_at": row[5]
                }

    agents_data = []
    for prof in profiles:
        active_sess = None
        total_sessions = 0
        total_tool_calls = 0
        last_active_at = None

        sdb = _resolve_profile_state_db_dyn(prof)
        if sdb and sdb.exists():
            try:
                conn = sqlite3.connect(f"file:{sdb.resolve()}?mode=ro", uri=True, timeout=2.0)
                conn.row_factory = sqlite3.Row
                with closing(conn):
                    cur = conn.cursor()
                    rows = cur.execute("""
                        SELECT id, model, started_at, ended_at, last_activity_at, last_activity_description,
                               message_count, tool_call_count, cwd, title
                        FROM sessions
                        ORDER BY started_at DESC
                        LIMIT 100
                    """).fetchall()

                    total_sessions = len(rows)
                    for r in rows:
                        total_tool_calls += (r["tool_call_count"] or 0)
                        act_ts = r["last_activity_at"] or r["started_at"]
                        if act_ts and (last_active_at is None or act_ts > last_active_at):
                            last_active_at = act_ts

                        ended = r["ended_at"]
                        is_ongoing = (ended is None and (time.time() - (r["last_activity_at"] or r["started_at"] or 0)) < 300)
                        if is_ongoing and active_sess is None:
                            started = r["started_at"]
                            duration = max(0, int(time.time() - started)) if started else None
                            active_sess = {
                                "session_id": str(r["id"]),
                                "model": r["model"],
                                "started_at": started,
                                "duration_seconds": duration,
                                "message_count": r["message_count"] or 0,
                                "tool_calls_count": r["tool_call_count"] or 0,
                                "title": r["title"],
                                "last_action": r["last_activity_description"] or "Active",
                                "cwd": r["cwd"]
                            }
            except Exception as e:
                _log.debug("Error checking agent status for %s: %s", prof, e)

        current_task = running_tasks_by_assignee.get(prof)
        is_active = (active_sess is not None) or (current_task is not None)

        agents_data.append({
            "name": prof,
            "label": AGENT_LABELS.get(prof, prof.replace("zf-", "").capitalize()),
            "icon": AGENT_ICONS.get(prof, "🤖"),
            "description": role_descriptions.get(prof, ""),
            "status": "active" if is_active else "idle",
            "is_active": is_active,
            "active_session": active_sess,
            "current_task": current_task,
            "stats": {
                "total_sessions": total_sessions,
                "total_tool_calls": total_tool_calls,
                "last_active_at": last_active_at
            }
        })

    return {"ok": True, "agents": agents_data}
