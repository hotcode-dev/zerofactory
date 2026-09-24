"""Zero Factory Dashboard — Agent execution session telemetry, progress, and stuck status."""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import sys
import time
from contextlib import closing
from pathlib import Path
from typing import Any, Dict, List, Optional

_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)
_DASHBOARD_ROOT = str(Path(__file__).resolve().parent)
if _DASHBOARD_ROOT not in sys.path:
    sys.path.insert(0, _DASHBOARD_ROOT)

try:
    from ..paths import normalize_assignee, resolve_profile_state_db  # type: ignore
except (ImportError, ValueError):
    from paths import normalize_assignee, resolve_profile_state_db  # type: ignore

try:
    from .db import get_db_conn
except (ImportError, ValueError):
    from db import get_db_conn  # type: ignore

_log = logging.getLogger(__name__)


def _d():
    return sys.modules.get("dashboard.plugin_api") or sys.modules.get("plugin_api")


def get_profile_state_db(assignee: str) -> Optional[Path]:
    """Find the SQLite state.db for an agent profile."""
    return resolve_profile_state_db(assignee)


def _resolve_profile_state_db_dyn(prof: str) -> Optional[Path]:
    disp = _d()
    if disp is not None:
        target = getattr(disp, "resolve_profile_state_db", None)
        if target is not None and target is not get_profile_state_db and target is not _resolve_profile_state_db_dyn:
            return target(prof)
    return resolve_profile_state_db(prof)


AGENT_LABELS = {
    "zf-orchestrator": "Orchestrator",
    "zf-builder": "Builder",
    "zf-reviewer": "Reviewer",
    "unassigned": "Agent",
}

AGENT_ICONS = {
    "zf-orchestrator": "🧭",
    "zf-builder": "🔨",
    "zf-reviewer": "🔍",
    "unassigned": "🤖",
}


def _compute_stuck_status(
    task: Dict[str, Any],
    is_alive: bool,
    worker_pid: Optional[int],
    started_at: Optional[float],
    last_active: Optional[float],
    log_path: Path
) -> tuple[int, int, bool, Optional[str]]:
    """Compute running/idle duration and stuck status for a task."""
    now = int(time.time())
    meta = task.get("metadata") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}

    started = meta.get("started_at") or task.get("updated_at") or task.get("created_at") or now
    running_seconds = max(0, now - int(started)) if task.get("status") == "running" else 0

    log_idle = None
    if log_path.exists():
        try:
            log_idle = max(0, now - int(log_path.stat().st_mtime))
        except Exception:
            pass
    sess_idle = max(0, now - int(last_active)) if last_active else None

    if log_idle is not None and sess_idle is not None:
        idle_seconds = min(log_idle, sess_idle)
    elif log_idle is not None:
        idle_seconds = log_idle
    elif sess_idle is not None:
        idle_seconds = sess_idle
    else:
        idle_seconds = running_seconds

    if task.get("status") != "running":
        return running_seconds, idle_seconds, False, None

    try:
        from ..dispatcher import get_task_timeout_seconds, get_inactivity_timeout_seconds
    except Exception:
        try:
            from dispatcher import get_task_timeout_seconds, get_inactivity_timeout_seconds
        except Exception:
            get_task_timeout_seconds = lambda: 3600
            get_inactivity_timeout_seconds = lambda: 900

    task_to = get_task_timeout_seconds()
    inact_to = get_inactivity_timeout_seconds()

    is_stuck = False
    stuck_reason = None

    if not is_alive and worker_pid:
        is_stuck = True
        stuck_reason = f"Worker process PID {worker_pid} is dead/not found"
    elif running_seconds > task_to:
        is_stuck = True
        stuck_reason = f"Exceeded running timeout ({running_seconds}s > {task_to}s)"
    elif idle_seconds > inact_to:
        is_stuck = True
        stuck_reason = f"Worker inactive with no updates for {idle_seconds}s (limit {inact_to}s)"

    return running_seconds, idle_seconds, is_stuck, stuck_reason


def resolve_task_all_sessions(task: Dict[str, Any], backfill: bool = True) -> List[Dict[str, Any]]:
    """Extract all execution sessions (finished and ongoing) for a task across all agent profiles."""
    meta = task.get("metadata") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}

    task_id = str(task.get("id") or "")
    task_title = str(task.get("title") or "")
    task_status = str(task.get("status") or "")
    assignee = normalize_assignee(task.get("assignee"))
    worker_pid = meta.get("worker_pid")
    active_sess_id = meta.get("session_id")
    recorded_sessions = meta.get("sessions") or []

    is_alive = False
    if worker_pid:
        try:
            os.kill(int(worker_pid), 0)
            is_alive = True
        except (OSError, ValueError):
            is_alive = False

    recorded_ids = set()
    if isinstance(recorded_sessions, list):
        for s in recorded_sessions:
            if isinstance(s, dict) and s.get("session_id"):
                recorded_ids.add(str(s["session_id"]))
    if active_sess_id:
        recorded_ids.add(str(active_sess_id))

    sessions_found = []
    seen_ids = set()

    profile_roles = ["zf-builder", "zf-reviewer", "zf-orchestrator"]

    for prof in profile_roles:
        state_db_path = _resolve_profile_state_db_dyn(prof)
        if not state_db_path or not state_db_path.exists():
            continue

        try:
            resolved_state = state_db_path.resolve()
            uri = resolved_state.as_uri() + "?mode=ro"
            try:
                s_conn = sqlite3.connect(uri, uri=True, timeout=2.0)
            except Exception:
                s_conn = sqlite3.connect(str(resolved_state), timeout=2.0)

            with closing(s_conn) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                cursor.execute("""
                    SELECT id, model, started_at, ended_at, last_activity_at, last_activity_description,
                           message_count, tool_call_count, cwd, title, profile_name
                    FROM sessions
                    ORDER BY started_at ASC
                """)
                all_s_rows = cursor.fetchall()

                for r in all_s_rows:
                    sid = str(r["id"])
                    is_match = False

                    if sid in recorded_ids:
                        is_match = True
                    elif task_id and r["cwd"] and task_id in str(r["cwd"]):
                        is_match = True
                    elif task_id and r["title"] and task_id in str(r["title"]):
                        is_match = True
                    elif task_title and len(task_title) > 8 and r["title"] and task_title.lower() in str(r["title"]).lower():
                        is_match = True

                    if not is_match:
                        continue

                    r_title = str(r["title"] or "")
                    r_cwd = str(r["cwd"] or "")
                    if task_id:
                        if "Task ID: zf-" in r_title and task_id not in r_title:
                            continue
                        if "/zf-" in r_cwd and task_id not in r_cwd:
                            continue

                    if sid in seen_ids:
                        continue
                    seen_ids.add(sid)

                    turn_count = 0
                    recent_steps = []
                    last_action = r["last_activity_description"] or None
                    try:
                        cursor.execute("SELECT COUNT(*) as cnt FROM messages WHERE session_id = ? AND role = 'assistant'", (sid,))
                        turn_count = cursor.fetchone()["cnt"]

                        cursor.execute("""
                            SELECT id, role, tool_name, tool_calls, content, reasoning_content, timestamp
                            FROM messages
                            WHERE session_id = ?
                            ORDER BY timestamp DESC, id DESC
                            LIMIT 8
                        """, (sid,))
                        recent_rows = cursor.fetchall()
                        for msg in reversed(recent_rows):
                            r_role = msg["role"]
                            r_tool = msg["tool_name"]
                            snippet = ""
                            if r_tool:
                                snippet = f"tool: {r_tool}"
                            elif r_role == "assistant":
                                if msg["tool_calls"]:
                                    try:
                                        tc = json.loads(msg["tool_calls"])
                                        if isinstance(tc, list) and tc:
                                            fn_name = tc[0].get("function", {}).get("name") or tc[0].get("name", "tool")
                                            snippet = f"executing {fn_name}"
                                        elif isinstance(tc, dict):
                                            fn_name = tc.get("function", {}).get("name") or tc.get("name", "tool")
                                            snippet = f"executing {fn_name}"
                                    except Exception:
                                        snippet = "tool calling"
                                elif msg["reasoning_content"]:
                                    snippet = (msg["reasoning_content"][:90] + "...") if len(msg["reasoning_content"]) > 90 else msg["reasoning_content"]
                                elif msg["content"]:
                                    snippet = (msg["content"][:90] + "...") if len(msg["content"]) > 90 else msg["content"]
                                else:
                                    snippet = "thinking..."
                            elif r_role == "tool":
                                cnt = msg["content"] or ""
                                snippet = (cnt[:120] + "...") if len(cnt) > 120 else cnt
                            elif r_role == "user":
                                snippet = "user prompt"

                            if not last_action and snippet:
                                last_action = snippet

                            recent_steps.append({
                                "id": msg["id"],
                                "role": r_role,
                                "tool_name": r_tool,
                                "snippet": snippet,
                                "timestamp": msg["timestamp"]
                            })
                    except Exception:
                        pass

                    is_active_session = False
                    started = r["started_at"]
                    ended = r["ended_at"]
                    task_started_at = meta.get("started_at")
                    is_stale_start = bool(task_started_at and started and started < (task_started_at - 60))
                    if is_alive and not is_stale_start and (sid == active_sess_id or r["ended_at"] is None) and task_status in ("running", "todo"):
                        is_active_session = True
                    elif r["ended_at"] is None and not is_stale_start and task_status == "running" and (time.time() - (r["last_activity_at"] or r["started_at"] or 0)) < 300:
                        is_active_session = True

                    sess_status = "ongoing" if is_active_session else "finished"
                    duration = None
                    if started and ended:
                        duration = max(0, int(ended - started))
                    elif started and is_active_session:
                        duration = max(0, int(time.time() - started))

                    agent_role = prof
                    if r["profile_name"] and r["profile_name"] in profile_roles:
                        agent_role = r["profile_name"]

                    sessions_found.append({
                        "session_id": sid,
                        "agent": agent_role,
                        "agent_label": AGENT_LABELS.get(agent_role, agent_role.replace("zf-", "").capitalize()),
                        "agent_icon": AGENT_ICONS.get(agent_role, "🤖"),
                        "status": sess_status,
                        "is_active": is_active_session,
                        "model": r["model"],
                        "started_at": started,
                        "ended_at": ended,
                        "last_activity_at": r["last_activity_at"],
                        "duration_seconds": duration,
                        "message_count": r["message_count"] or 0,
                        "turn_count": turn_count or r["tool_call_count"] or 0,
                        "tool_calls_count": r["tool_call_count"] or 0,
                        "title": r["title"],
                        "last_action": last_action or (f"Turn {turn_count}" if turn_count else "Active"),
                        "recent_steps": recent_steps,
                        "cwd": r["cwd"]
                    })
        except Exception as e:
            _log.debug("Error checking profile %s state DB: %s", prof, e)

    if isinstance(recorded_sessions, list):
        for s in recorded_sessions:
            if not isinstance(s, dict):
                continue
            s_id = s.get("session_id")
            if s_id and s_id not in seen_ids:
                seen_ids.add(s_id)
                s_agent = s.get("agent") or assignee
                s_status = s.get("status") or "finished"
                if is_alive and s_id == active_sess_id and task_status == "running":
                    s_status = "ongoing"
                elif task_status != "running":
                    s_status = "finished"
                sessions_found.append({
                    "session_id": s_id,
                    "agent": s_agent,
                    "agent_label": AGENT_LABELS.get(s_agent, s_agent.replace("zf-", "").capitalize()),
                    "agent_icon": AGENT_ICONS.get(s_agent, "🤖"),
                    "status": s_status,
                    "is_active": (s_status == "ongoing"),
                    "model": s.get("model"),
                    "started_at": s.get("started_at"),
                    "ended_at": s.get("ended_at"),
                    "last_activity_at": s.get("last_activity_at") or s.get("started_at"),
                    "duration_seconds": None,
                    "message_count": s.get("message_count", 0),
                    "turn_count": s.get("turn_count", 0),
                    "tool_calls_count": s.get("tool_calls_count", 0),
                    "title": s.get("title", task_title),
                    "last_action": s.get("last_action", "Active" if s_status == "ongoing" else "Completed"),
                    "recent_steps": s.get("recent_steps", []),
                    "cwd": task.get("workspace_path")
                })

    sessions_found.sort(key=lambda s: s.get("started_at") or 0)
    return sessions_found


def resolve_task_session_progress(task: Dict[str, Any], backfill: bool = True) -> Dict[str, Any]:
    """Extract real-time execution progress, turn counts, tool calls, and all historical/ongoing sessions for a task."""
    meta = task.get("metadata") or {}
    if isinstance(meta, str):
        try:
            meta = json.loads(meta)
        except Exception:
            meta = {}

    assignee = task.get("assignee") or "zf-builder"
    task_id = task.get("id") or ""
    worker_pid = meta.get("worker_pid")
    session_id = meta.get("session_id")

    is_alive = False
    if worker_pid:
        try:
            os.kill(int(worker_pid), 0)
            is_alive = True
        except (OSError, ValueError):
            is_alive = False

    log_tail = ""
    log_path = Path.home() / ".hermes" / "logs" / f"worker_{task_id}.log"
    if log_path.exists():
        try:
            with open(log_path, "r", encoding="utf-8", errors="replace") as lf:
                lines = lf.readlines()
                log_tail = "".join(lines[-30:])
        except Exception:
            pass

    sessions = resolve_task_all_sessions(task, backfill=backfill)

    ongoing_sessions = [s for s in sessions if s.get("status") == "ongoing"]
    if ongoing_sessions:
        active_session = ongoing_sessions[-1]
    elif sessions:
        active_session = sessions[-1]
    else:
        active_session = None

    if active_session:
        s_id = active_session.get("session_id")
        if s_id and s_id != session_id and backfill and task_id:
            try:
                with get_db_conn() as k_conn:
                    meta["session_id"] = s_id
                    k_conn.execute("UPDATE tasks SET metadata = ? WHERE id = ?", (json.dumps(meta), task_id))
                    k_conn.commit()
            except Exception:
                pass

        last_active_ts = active_session.get("last_activity_at") or active_session.get("started_at")
        r_sec, i_sec, stuck, reason = _compute_stuck_status(
            task, is_alive, worker_pid,
            active_session.get("started_at"),
            last_active_ts,
            log_path
        )

        return {
            "has_session": True,
            "session_id": s_id,
            "assignee": active_session.get("agent") or assignee,
            "worker_pid": worker_pid,
            "is_alive": is_alive,
            "model": active_session.get("model"),
            "started_at": active_session.get("started_at"),
            "last_active": (
                active_session.get("last_activity_at")
                or active_session.get("ended_at")
                or active_session.get("started_at")
            ),
            "message_count": active_session.get("message_count", 0),
            "turn_count": active_session.get("turn_count", 0),
            "tool_calls_count": active_session.get("tool_calls_count", 0),
            "last_action": active_session.get("last_action", "Active"),
            "recent_steps": active_session.get("recent_steps", []),
            "log_tail": log_tail,
            "running_seconds": r_sec,
            "idle_seconds": i_sec,
            "is_stuck": stuck,
            "stuck_reason": reason,
            "sessions": sessions
        }

    r_sec, i_sec, stuck, reason = _compute_stuck_status(task, is_alive, worker_pid, None, None, log_path)
    return {
        "has_session": bool(session_id),
        "session_id": session_id,
        "assignee": assignee,
        "worker_pid": worker_pid,
        "is_alive": is_alive,
        "model": None,
        "started_at": None,
        "last_active": None,
        "message_count": 0,
        "turn_count": 0,
        "tool_calls_count": 0,
        "last_action": "Agent active" if is_alive else None,
        "recent_steps": [],
        "log_tail": log_tail,
        "running_seconds": r_sec,
        "idle_seconds": i_sec,
        "is_stuck": stuck,
        "stuck_reason": reason,
        "sessions": sessions
    }


def _load_task_board_map() -> tuple[Dict[str, Dict[str, Any]], Dict[str, Dict[str, Any]], set[str]]:
    """Loads a mapping of task_id -> task info, session_id -> task info, and known board_slugs."""
    task_map: Dict[str, Dict[str, Any]] = {}
    session_to_task: Dict[str, Dict[str, Any]] = {}
    board_slugs: set[str] = set()
    try:
        with get_db_conn() as conn:
            cur = conn.cursor()
            cur.execute("SELECT id, board_slug, title, workspace_path, metadata FROM tasks")
            for row in cur.fetchall():
                tid = str(row[0])
                bslug = str(row[1] or "")
                task_info = {
                    "id": tid,
                    "board_slug": bslug,
                    "title": row[2] or "",
                    "workspace_path": row[3] or "",
                }
                task_map[tid.lower()] = task_info
                if bslug:
                    board_slugs.add(bslug)
                meta_raw = row[4]
                if meta_raw:
                    try:
                        mdict = json.loads(meta_raw) if isinstance(meta_raw, str) else meta_raw
                        if isinstance(mdict, dict):
                            msid = mdict.get("session_id")
                            if msid:
                                session_to_task[str(msid)] = task_info
                    except Exception:
                        pass
    except Exception as e:
        _log.debug("Error querying tasks for session-board mapping: %s", e)
    return task_map, session_to_task, board_slugs


def list_all_sessions(
    role: Optional[str] = None,
    status: Optional[str] = None,
    board_slug: Optional[str] = None,
    limit: int = 50
) -> Dict[str, Any]:
    """List recent and active AI agent sessions across Orchestrator, Builder, and Reviewer."""
    profiles = ["zf-builder", "zf-reviewer", "zf-orchestrator"]
    if role and role in profiles:
        profiles = [role]

    task_map, session_to_task, known_board_slugs = _load_task_board_map()

    all_sessions = []
    seen = set()
    fetch_limit = limit * 3 if (board_slug and board_slug != "all") else limit
    for prof in profiles:
        sdb = _resolve_profile_state_db_dyn(prof)
        if not sdb or not sdb.exists():
            continue
        try:
            conn = sqlite3.connect(f"file:{sdb.resolve()}?mode=ro", uri=True, timeout=2.0)
            conn.row_factory = sqlite3.Row
            with closing(conn):
                cur = conn.cursor()
                rows = cur.execute("""
                    SELECT id, model, started_at, ended_at, last_activity_at, last_activity_description,
                           message_count, tool_call_count, cwd, title, profile_name
                    FROM sessions
                    ORDER BY started_at DESC
                    LIMIT ?
                """, (fetch_limit,)).fetchall()
                for r in rows:
                    sid = str(r["id"])
                    if sid in seen:
                        continue
                    seen.add(sid)
                    ended = r["ended_at"]
                    is_ongoing = (ended is None and (time.time() - (r["last_activity_at"] or r["started_at"] or 0)) < 300)
                    sess_status = "ongoing" if is_ongoing else "finished"
                    if status and sess_status != status:
                        continue

                    # Correlate session with task and board
                    matched_task_id = None
                    matched_board_slug = None
                    if sid in session_to_task:
                        matched_task_id = session_to_task[sid]["id"]
                        matched_board_slug = session_to_task[sid]["board_slug"]
                    else:
                        cwd_or_title = f"{r['cwd'] or ''} {r['title'] or ''}"
                        m_task = re.search(r"\b(zf-[a-z0-9_-]+|task-[a-z0-9_-]+)\b", cwd_or_title, re.I)
                        if m_task:
                            tid_candidate = m_task.group(1).lower()
                            if tid_candidate in task_map:
                                matched_task_id = task_map[tid_candidate]["id"]
                                matched_board_slug = task_map[tid_candidate]["board_slug"]
                            else:
                                matched_task_id = m_task.group(1)
                        if not matched_board_slug:
                            for b in known_board_slugs:
                                if b in cwd_or_title or b.replace("-", "/") in cwd_or_title:
                                    matched_board_slug = b
                                    break

                    if board_slug and board_slug != "all":
                        if matched_board_slug != board_slug:
                            continue

                    started = r["started_at"]
                    duration = max(0, int(ended - started)) if (started and ended) else (max(0, int(time.time() - started)) if (started and is_ongoing) else None)

                    # Compute turn count if possible
                    turn_cnt = r["tool_call_count"] or 0
                    try:
                        cur2 = conn.cursor()
                        cur2.execute("SELECT COUNT(*) as cnt FROM messages WHERE session_id = ? AND role = 'assistant'", (sid,))
                        m_res = cur2.fetchone()
                        if m_res and m_res[0]:
                            turn_cnt = m_res[0]
                    except Exception:
                        pass

                    all_sessions.append({
                        "session_id": sid,
                        "agent": prof,
                        "agent_label": AGENT_LABELS.get(prof, prof.replace("zf-", "").capitalize()),
                        "agent_icon": AGENT_ICONS.get(prof, "🤖"),
                        "status": sess_status,
                        "is_active": is_ongoing,
                        "model": r["model"],
                        "started_at": started,
                        "ended_at": ended,
                        "last_activity_at": r["last_activity_at"],
                        "duration_seconds": duration,
                        "message_count": r["message_count"] or 0,
                        "turn_count": turn_cnt,
                        "tool_calls_count": r["tool_call_count"] or 0,
                        "title": r["title"],
                        "last_action": r["last_activity_description"] or "Active",
                        "cwd": r["cwd"],
                        "task_id": matched_task_id,
                        "board_slug": matched_board_slug
                    })
        except Exception as e:
            _log.debug("Error reading sessions for profile %s: %s", prof, e)

    all_sessions.sort(key=lambda s: s.get("started_at") or 0, reverse=True)
    return {"ok": True, "sessions": all_sessions[:limit]}
