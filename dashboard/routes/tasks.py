"""Zero Factory Dashboard — Task management routes (/tasks)."""

from __future__ import annotations

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Any

_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)
_DASHBOARD_ROOT = str(Path(__file__).resolve().parent.parent)
if _DASHBOARD_ROOT not in sys.path:
    sys.path.insert(0, _DASHBOARD_ROOT)

from fastapi import APIRouter, HTTPException, Query

try:
    from ..db import (
        _mark_scanner_task_created,
        generate_task_id,
        get_db_conn,
        get_db_path,
        init_db,
        log_activity,
        row_to_dict,
    )
    from ..memory_service import (
        compute_dedup_key,
        extract_and_record_memory,
        normalize_file_path,
    )
    from ..models import (
        VALID_ASSIGNEES,
        VALID_PRIORITIES,
        VALID_STATUSES,
        CommentCreate,
        DependencyLink,
        InterviewReply,
        TaskCreate,
        TaskMove,
        TaskUpdate,
        normalize_assignee,
        normalize_blocked_reason_type,
    )
    from ..session_service import resolve_task_session_progress
except (ImportError, ValueError):
    from db import (  # type: ignore
        _mark_scanner_task_created,
        generate_task_id,
        get_db_conn,
        get_db_path,
        init_db,
        log_activity,
        row_to_dict,
    )
    from memory_service import (  # type: ignore
        compute_dedup_key,
        extract_and_record_memory,
        normalize_file_path,
    )
    from models import (  # type: ignore
        VALID_ASSIGNEES,
        VALID_PRIORITIES,
        VALID_STATUSES,
        CommentCreate,
        DependencyLink,
        InterviewReply,
        TaskCreate,
        TaskMove,
        TaskUpdate,
        normalize_assignee,
        normalize_blocked_reason_type,
    )
    from session_service import resolve_task_session_progress  # type: ignore

_log = logging.getLogger(__name__)

router = APIRouter()


def _trigger_async_dispatch(log_context: str) -> None:
    """Spawn a daemon thread running one dispatch cycle (best-effort, silent on failure)."""
    try:
        import threading

        try:
            from ...dispatcher import run_dispatch_cycle
        except Exception:
            from dispatcher import run_dispatch_cycle  # type: ignore
        threading.Thread(
            target=run_dispatch_cycle, args=(get_db_path(),), daemon=True
        ).start()
    except Exception as disp_err:
        _log.debug("Async dispatch trigger after %s failed: %s", log_context, disp_err)


@router.get("/tasks")
def list_tasks(
    board: str | None = Query(None, description="Board slug filter"),
    repo: str | None = Query(None, description="Repository alias filter"),
    status: str | None = Query(None, description="Status column filter"),
    assignee: str | None = Query(None, description="Assignee filter"),
    priority: str | None = Query(None, description="Priority filter"),
    search: str | None = Query(None, description="Search term in title or description"),
):
    """List tasks with flexible filtering."""
    init_db()

    # Normalize if invoked directly in python with default Query descriptors
    if not isinstance(board, str):
        board = None
    if not isinstance(repo, str):
        repo = None
    if not isinstance(status, str):
        status = None
    if not isinstance(assignee, str):
        assignee = None
    if not isinstance(priority, str):
        priority = None
    if not isinstance(search, str):
        search = None

    query = "SELECT * FROM tasks WHERE 1=1"
    params: list[Any] = []

    if board and board != "all":
        query += " AND board_slug = ?"
        params.append(board)
    if repo:
        query += " AND repo_alias = ?"
        params.append(repo)
    if status:
        query += " AND status = ?"
        params.append(status)
    if assignee:
        query += " AND assignee = ?"
        params.append(assignee)
    if priority:
        query += " AND priority = ?"
        params.append(priority)
    if search:
        query += " AND (title LIKE ? OR description LIKE ? OR id LIKE ?)"
        s = f"%{search}%"
        params.extend([s, s, s])

    query += " ORDER BY CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 WHEN 'P3' THEN 3 ELSE 4 END, created_at DESC"

    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        tasks = [row_to_dict(r) for r in rows]

        task_ids = [t["id"] for t in tasks]
        if task_ids:
            placeholders = ",".join("?" for _ in task_ids)
            cursor.execute(
                f"SELECT child_id, COUNT(*) as count FROM task_links WHERE child_id IN ({placeholders}) GROUP BY child_id",
                task_ids,
            )
            parent_counts = {r["child_id"]: r["count"] for r in cursor.fetchall()}

            cursor.execute(
                f"""
                SELECT tl.child_id, COUNT(*) as count
                FROM task_links tl
                JOIN tasks pt ON pt.id = tl.parent_id
                WHERE tl.child_id IN ({placeholders}) AND pt.status != 'done'
                GROUP BY tl.child_id
            """,
                task_ids,
            )
            blocking_counts = {r["child_id"]: r["count"] for r in cursor.fetchall()}

            cursor.execute(
                f"SELECT parent_id, COUNT(*) as count FROM task_links WHERE parent_id IN ({placeholders}) GROUP BY parent_id",
                task_ids,
            )
            child_counts = {r["parent_id"]: r["count"] for r in cursor.fetchall()}

            cursor.execute(
                f"SELECT task_id, COUNT(*) as count FROM task_comments WHERE task_id IN ({placeholders}) GROUP BY task_id",
                task_ids,
            )
            comment_counts = {r["task_id"]: r["count"] for r in cursor.fetchall()}

            for t in tasks:
                t_id = t["id"]
                t["parent_count"] = parent_counts.get(t_id, 0)
                t["blocking_parent_count"] = blocking_counts.get(t_id, 0)
                t["child_count"] = child_counts.get(t_id, 0)
                t["comment_count"] = comment_counts.get(t_id, 0)
                meta_obj = {}
                raw_meta = t.get("metadata")
                if raw_meta:
                    try:
                        meta_obj = (
                            json.loads(raw_meta)
                            if isinstance(raw_meta, str)
                            else (raw_meta or {})
                        )
                    except Exception:
                        meta_obj = {}
                meta_sessions = meta_obj.get("sessions") or []

                if t.get("status") == "running":
                    prog = resolve_task_session_progress(t, backfill=False)
                    t["session_progress"] = {
                        "has_session": prog["has_session"],
                        "session_id": prog.get("session_id"),
                        "is_alive": prog.get("is_alive", False),
                        "turn_count": prog.get("turn_count", 0),
                        "message_count": prog.get("message_count", 0),
                        "last_action": prog.get("last_action"),
                        "is_stuck": prog.get("is_stuck", False),
                        "stuck_reason": prog.get("stuck_reason"),
                        "running_seconds": prog.get("running_seconds", 0),
                        "idle_seconds": prog.get("idle_seconds", 0),
                        "sessions": prog.get("sessions", []),
                    }
                elif meta_sessions:
                    clean_sessions = []
                    for s in meta_sessions:
                        if isinstance(s, dict):
                            s_copy = dict(s)
                            if s_copy.get("status") == "ongoing":
                                s_copy["status"] = "finished"
                            s_copy["is_active"] = False
                            clean_sessions.append(s_copy)
                    t["session_progress"] = {
                        "has_session": True,
                        "session_id": meta_obj.get("session_id"),
                        "is_alive": False,
                        "turn_count": sum(
                            s.get("turn_count", 0) for s in clean_sessions
                        ),
                        "message_count": sum(
                            s.get("message_count", 0) for s in clean_sessions
                        ),
                        "sessions": clean_sessions,
                    }

        return {"ok": True, "tasks": tasks, "count": len(tasks)}


@router.post("/tasks")
def create_task(req: TaskCreate):
    """Create a new task."""
    init_db()
    now = int(time.time())
    status_val = req.status if req.status in VALID_STATUSES else "triage"
    priority_val = req.priority if req.priority in VALID_PRIORITIES else "P2"
    assignee_val = (
        normalize_assignee(req.assignee)
        if req.assignee in VALID_ASSIGNEES
        else "unassigned"
    )
    tags_json = json.dumps(req.tags or [])
    metadata_json = "{}"

    with get_db_conn() as conn:
        cursor = conn.cursor()
        board_slug = req.board_slug
        if board_slug and board_slug != "all":
            cursor.execute("SELECT slug FROM boards WHERE slug = ?", (board_slug,))
            if not cursor.fetchone():
                board_slug = None
        else:
            board_slug = None
        if not board_slug:
            cursor.execute("SELECT slug FROM boards ORDER BY created_at ASC LIMIT 1")
            row = cursor.fetchone()
            board_slug = row[0] if row else ""

        task_id = req.task_id or generate_task_id(board_slug)
        branch_name = req.branch_name or f"task/{task_id}"

        if req.task_id:
            cursor.execute(
                "SELECT id, title, status FROM tasks WHERE id = ?", (req.task_id,)
            )
            existing_row = cursor.fetchone()
            if existing_row:
                return {
                    "ok": True,
                    "id": existing_row["id"],
                    "duplicate": True,
                    "message": f"Task already exists ({existing_row['id']}) in status '{existing_row['status']}': {existing_row['title']}",
                }

        dedup_key = req.dedup_key or compute_dedup_key(req.files, req.category)
        cursor.execute(
            """
            SELECT id, title, status, metadata FROM tasks 
            WHERE board_slug = ? AND status IN ('triage', 'todo', 'running')
        """,
            (board_slug,),
        )
        active_tasks = cursor.fetchall()

        norm_title = req.title.strip().lower()
        for row in active_tasks:
            m = row["metadata"]
            if isinstance(m, str):
                try:
                    m = json.loads(m)
                except Exception:
                    m = {}
            existing_key = m.get("dedup_key") if isinstance(m, dict) else None
            if dedup_key and existing_key == dedup_key:
                return {
                    "ok": True,
                    "id": row["id"],
                    "duplicate": True,
                    "message": f"Task already exists ({row['id']}) with matching file fingerprint in status '{row['status']}': {row['title']}",
                }
            elif not dedup_key and row["title"].strip().lower() == norm_title:
                return {
                    "ok": True,
                    "id": row["id"],
                    "duplicate": True,
                    "message": f"Task already exists ({row['id']}) with identical title in status '{row['status']}'",
                }

        meta: dict[str, Any] = {}
        if req.metadata:
            meta.update(req.metadata)
        if dedup_key:
            meta["dedup_key"] = dedup_key
        if req.files:
            cleaned_files = []
            for f in req.files:
                if isinstance(f, str):
                    for part in f.split(","):
                        norm = normalize_file_path(part)
                        if norm:
                            cleaned_files.append(norm)
            if cleaned_files:
                meta["files"] = sorted(set(cleaned_files))
        if req.category:
            meta["category"] = req.category.strip().lower()

        tags = list(req.tags or [])
        if meta.get("category") and f"cat:{meta['category']}" not in tags:
            tags.append(f"cat:{meta['category']}")
        for f in meta.get("files", []):
            t = f"file:{f}"
            if t not in tags:
                tags.append(t)

        tags_json = json.dumps(tags)
        metadata_json = json.dumps(meta)

        repo_alias_val = (req.repo_alias or "").strip() or None
        if not repo_alias_val and board_slug:
            cursor.execute(
                "SELECT repo_alias FROM board_repositories WHERE board_slug = ? ORDER BY id ASC LIMIT 1",
                (board_slug,),
            )
            r_row = cursor.fetchone()
            if r_row:
                repo_alias_val = r_row[0]

        cursor.execute(
            """
            INSERT INTO tasks (
                id, board_slug, repo_alias, title, description, status, assignee, priority,
                workspace_path, workspace_kind, branch_name, pr_url, tenant,
                tags, metadata, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
            (
                task_id,
                board_slug,
                repo_alias_val,
                req.title.strip(),
                req.description or "",
                status_val,
                assignee_val,
                priority_val,
                req.workspace_path,
                req.workspace_kind or "worktree",
                branch_name,
                req.pr_url,
                req.tenant or "",
                tags_json,
                metadata_json,
                now,
                now,
            ),
        )

        if req.parent_id:
            cursor.execute("SELECT id FROM tasks WHERE id = ?", (req.parent_id,))
            if cursor.fetchone():
                cursor.execute(
                    "INSERT OR IGNORE INTO task_links (parent_id, child_id, created_at) VALUES (?, ?, ?)",
                    (req.parent_id, task_id, now),
                )

        creator_actor = req.actor
        if not creator_actor and (
            req.dedup_key
            or (req.tags and any(t.startswith("cat:") for t in req.tags))
            or meta.get("dedup_key")
        ):
            creator_actor = "zf-orchestrator"
        if not creator_actor:
            creator_actor = os.environ.get("HERMES_PROFILE") or "user"

        log_activity(
            conn, task_id, creator_actor, "create", f"Task created in {status_val}"
        )
        conn.commit()

        if board_slug:
            _mark_scanner_task_created(board_slug, repo_alias=req.repo_alias)

    return {"ok": True, "id": task_id}


@router.get("/tasks/{task_id}")
def get_task(task_id: str):
    """Get full task details including dependencies, comments, and activity."""
    init_db()
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task_row = cursor.fetchone()
        if not task_row:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

        task = row_to_dict(task_row)

        cursor.execute(
            """
            SELECT t.id, t.title, t.status, t.assignee, t.priority, t.repo_alias, tl.link_type
            FROM task_links tl
            JOIN tasks t ON t.id = tl.parent_id
            WHERE tl.child_id = ?
        """,
            (task_id,),
        )
        task["parents"] = [dict(r) for r in cursor.fetchall()]

        cursor.execute(
            """
            SELECT t.id, t.title, t.status, t.assignee, t.priority, t.repo_alias, tl.link_type
            FROM task_links tl
            JOIN tasks t ON t.id = tl.child_id
            WHERE tl.parent_id = ?
        """,
            (task_id,),
        )
        task["children"] = [dict(r) for r in cursor.fetchall()]

        cursor.execute(
            "SELECT * FROM task_comments WHERE task_id = ? ORDER BY created_at ASC",
            (task_id,),
        )
        task["comments"] = [dict(r) for r in cursor.fetchall()]

        cursor.execute(
            "SELECT * FROM task_activity WHERE task_id = ? ORDER BY created_at DESC LIMIT 50",
            (task_id,),
        )
        task["activity"] = [dict(r) for r in cursor.fetchall()]

        task["session_progress"] = resolve_task_session_progress(task, backfill=True)

        return {"ok": True, "task": task}


@router.get("/tasks/{task_id}/session")
def get_task_session(task_id: str):
    """Get real-time agent session execution progress, turns, active tool calls, and logs."""
    init_db()
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task_row = cursor.fetchone()
        if not task_row:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        task = row_to_dict(task_row)
        prog = resolve_task_session_progress(task, backfill=True)
        return {
            "ok": True,
            "session_progress": prog,
            "sessions": prog.get("sessions", []),
        }


@router.get("/tasks/{task_id}/sessions")
def get_task_sessions(task_id: str):
    """Get all historical and ongoing execution sessions for a task across all agents."""
    init_db()
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task_row = cursor.fetchone()
        if not task_row:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        task = row_to_dict(task_row)
        prog = resolve_task_session_progress(task, backfill=True)
        return {
            "ok": True,
            "sessions": prog.get("sessions", []),
            "session_progress": prog,
        }


@router.post("/tasks/{task_id}/stop")
def stop_task_session(task_id: str, to_status: str | None = "blocked"):
    """Safely terminate any running AI session / worker for the task and update status."""
    init_db()
    now = int(time.time())
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task_row = cursor.fetchone()
        if not task_row:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        task = row_to_dict(task_row)

        raw_meta = task.get("metadata") or "{}"
        try:
            meta = json.loads(raw_meta) if isinstance(raw_meta, str) else dict(raw_meta)
        except Exception:
            meta = {}

        # Safely terminate active worker process group via dispatcher
        try:
            from ...dispatcher import _mark_task_session_ended, stop_task_worker
        except Exception:
            try:
                from dispatcher import (  # type: ignore
                    _mark_task_session_ended,
                    stop_task_worker,
                )
            except Exception:
                stop_task_worker = None
                _mark_task_session_ended = None

        if stop_task_worker is not None:
            try:
                stop_task_worker(task_id, cursor=cursor)
            except Exception as e:
                _log.warning("stop_task_worker failed for %s: %s", task_id, e)
        else:
            wpid = meta.get("worker_pid")
            if wpid:
                try:
                    os.killpg(int(wpid), 15)
                except Exception:
                    try:
                        os.kill(int(wpid), 15)
                    except Exception:
                        pass

        # Finalize ongoing sessions in metadata
        if _mark_task_session_ended is not None:
            meta = _mark_task_session_ended(meta, now, "aborted")
        else:
            sessions = meta.get("sessions")
            if isinstance(sessions, list):
                for s in sessions:
                    if isinstance(s, dict) and s.get("status") == "ongoing":
                        s["status"] = "aborted"
                        if not s.get("ended_at"):
                            s["ended_at"] = now

        active_sid = meta.get("session_id")
        meta["blocked_reason"] = "AI session stopped by user"
        meta["blocked_reason_type"] = "human-gate"
        meta.pop("worker_pid", None)
        meta.pop("session_id", None)
        meta.pop("started_at", None)

        target_status = to_status if to_status in ["blocked", "todo"] else "blocked"
        if target_status == "todo":
            meta.pop("blocked_reason", None)
            meta.pop("blocked_reason_type", None)

        # 'blocked' is the human gate: parked tasks belong to the human queue.
        assignee_set = ", assignee = 'human'" if target_status == "blocked" else ""
        cursor.execute(
            f"UPDATE tasks SET status = ?{assignee_set}, metadata = ?, updated_at = ? WHERE id = ?",
            (target_status, json.dumps(meta), now, task_id),
        )

        cursor.execute(
            "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'user', 'session_aborted', 'AI session stopped by user', ?)",
            (task_id, now),
        )
        cursor.execute(
            "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, 'user', '⏹ AI session manually stopped by user.', ?)",
            (task_id, now),
        )

        # Mark ended_at in profile state.db if session_id is active
        if active_sid:
            for prof in ["zf-builder", "zf-reviewer", "zf-orchestrator"]:
                try:
                    from ...paths import resolve_profile_state_db
                except Exception:
                    try:
                        from paths import resolve_profile_state_db  # type: ignore
                    except Exception:
                        resolve_profile_state_db = None
                if resolve_profile_state_db:
                    sdb = resolve_profile_state_db(prof)
                    if sdb and sdb.exists():
                        try:
                            import sqlite3 as _sqlite3

                            with _sqlite3.connect(str(sdb), timeout=2.0) as pconn:
                                pcur = pconn.cursor()
                                pcur.execute(
                                    "UPDATE sessions SET ended_at = ? WHERE id = ? AND ended_at IS NULL",
                                    (now, active_sid),
                                )
                                pconn.commit()
                        except Exception:
                            pass

        conn.commit()

        if (
            target_status == "todo"
            and not os.environ.get("ZEROFACTORY_SKIP_DISPATCHER")
            and not os.environ.get("ZEROFACTORY_DISABLE_DISPATCHER")
        ):
            _trigger_async_dispatch("stop_task_session")

        return {
            "ok": True,
            "stopped": True,
            "task_id": task_id,
            "status": target_status,
            "message": f"AI session for task {task_id} successfully stopped.",
        }


@router.patch("/tasks/{task_id}")
def update_task(task_id: str, req: TaskUpdate):
    """Update task fields."""
    init_db()
    now = int(time.time())
    updates: list[str] = []
    params: list[Any] = []
    changes: list[str] = []

    if req.title is not None:
        updates.append("title = ?")
        params.append(req.title.strip())
        changes.append("title updated")
    if req.description is not None:
        updates.append("description = ?")
        params.append(req.description)
        changes.append("description updated")
    if req.board_slug is not None:
        updates.append("board_slug = ?")
        params.append(req.board_slug)
        changes.append(f"moved to board {req.board_slug}")
    if req.repo_alias is not None:
        updates.append("repo_alias = ?")
        params.append(req.repo_alias.strip() or None)
        changes.append(f"repo_alias set to {req.repo_alias}")
    if req.status is not None:
        # Status is a lifecycle TRANSITION with side effects (worker stop, flags,
        # marker cleanup, dispatch trigger) — always applied by /move so exactly
        # one code path owns status changes.
        raise HTTPException(
            status_code=400,
            detail=(
                "Status cannot be changed via PATCH; use "
                f"POST /tasks/{task_id}/move (or `hermes zerofactory move`) "
                "so lifecycle side effects are applied"
            ),
        )
    if req.assignee is not None:
        asgn = normalize_assignee(req.assignee)
        updates.append("assignee = ?")
        params.append(asgn)
        changes.append(f"assignee changed to {asgn}")
    if req.priority is not None:
        if req.priority not in VALID_PRIORITIES:
            raise HTTPException(
                status_code=400, detail=f"Invalid priority: {req.priority}"
            )
        updates.append("priority = ?")
        params.append(req.priority)
        changes.append(f"priority changed to {req.priority}")
    if req.workspace_path is not None:
        updates.append("workspace_path = ?")
        params.append(req.workspace_path)
    if req.workspace_kind is not None:
        updates.append("workspace_kind = ?")
        params.append(req.workspace_kind)
    if req.branch_name is not None:
        updates.append("branch_name = ?")
        params.append(req.branch_name)
    if req.pr_url is not None:
        updates.append("pr_url = ?")
        params.append(req.pr_url)
    if req.tenant is not None:
        updates.append("tenant = ?")
        params.append(req.tenant)
    if req.tags is not None:
        updates.append("tags = ?")
        params.append(json.dumps(req.tags))
    if req.metadata is not None:
        updates.append("metadata = ?")
        params.append(json.dumps(req.metadata))

    if not updates:
        return {"ok": True, "message": "No changes requested"}

    updates.append("updated_at = ?")
    params.append(now)
    params.append(task_id)

    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params)
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

        log_activity(conn, task_id, "user", "update", "; ".join(changes))
        conn.commit()

    return {"ok": True, "id": task_id}


@router.post("/tasks/{task_id}/move")
def move_task(task_id: str, req: TaskMove):
    """Move a task to another status / column (e.g. via Drag and Drop)."""
    init_db()
    if req.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {req.status}")

    now = int(time.time())
    try:
        from ...dispatcher import log_step_end, log_step_start, log_step_state
    except (ImportError, ValueError):
        try:
            from dispatcher import (  # type: ignore
                log_step_end,
                log_step_start,
                log_step_state,
            )
        except (ImportError, ValueError):

            def log_step_start(*_a, **_kw):
                return 0.0

            def log_step_end(*_a, **_kw):
                return None

            def log_step_state(*_a, **_kw):
                return None

    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT status, metadata, board_slug, title, pr_url FROM tasks WHERE id = ?",
            (task_id,),
        )
        curr = cursor.fetchone()
        if not curr:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

        prev_status = curr["status"]
        move_t0 = log_step_start(
            "move",
            task_id,
            f"{prev_status} -> {req.status} by {req.actor or 'user'}",
            logger=_log,
        )
        meta_raw = curr["metadata"] if "metadata" in curr.keys() else "{}"
        meta = {}
        try:
            meta = json.loads(meta_raw or "{}")
        except Exception:
            pass

        meta_updated = False
        is_agent_actor = bool(req.actor and req.actor.startswith("zf-"))
        is_orchestrator_actor = req.actor == "zf-orchestrator"

        # 'done' is strictly terminal. An agent reporting completion (builder/
        # reviewer) means "work finished — package it": the task stays 'running'
        # and the dispatcher runs precommit -> commit -> push -> PR -> reviewer,
        # marked via 'awaiting_pr'. Humans (and the orchestrator closing tickets)
        # close tasks terminally; any open PR/remote branch is archived via
        # 'close_pr' so GitHub matches the board.
        wants_packaging = is_agent_actor and not is_orchestrator_actor

        # A completion report from a stale/zombie worker must never clobber a
        # parked state: 'done' is strictly terminal and 'blocked' is a
        # human/reviewer gate. The sole builder-bound exception is
        # 'changes-requested', where finishing the fix is the desired outcome
        # (zf-hdz-4dc03cee: a zombie builder's `move done` flipped an
        # approved-for-merge task back to running and wiped its blocked_reason).
        if (
            wants_packaging
            and req.status == "done"
            and (
                prev_status == "done"
                or (
                    prev_status == "blocked"
                    and str(meta.get("blocked_reason_type") or "human-gate")
                    != "changes-requested"
                )
            )
        ):
            park_reason = (
                "task is already done (terminal)"
                if prev_status == "done"
                else f"task is blocked for {str(meta.get('blocked_reason_type') or 'human-gate')}"
            )
            log_step_state(
                "move",
                task_id,
                "stale_completion_ignored",
                f"{park_reason}; keeping {prev_status}",
                logger=_log,
            )
            log_step_end("move", move_t0, task_id, "skipped", park_reason, logger=_log)
            log_activity(
                conn,
                task_id,
                req.actor or "user",
                "move_rejected",
                f"Stale completion report ignored: {park_reason}",
            )
            conn.commit()
            return {
                "ok": True,
                "id": task_id,
                "status": prev_status,
                "prev_status": prev_status,
                "ignored": True,
                "reason": f"Completion ignored: {park_reason}",
            }

        new_status = (
            "running" if (req.status == "done" and wants_packaging) else req.status
        )
        if req.status == "done":
            if wants_packaging:
                if not meta.get("awaiting_pr"):
                    meta["awaiting_pr"] = True
                    meta_updated = True
                if "close_pr" in meta:
                    meta.pop("close_pr", None)
                    meta_updated = True
            else:
                if "awaiting_pr" in meta:
                    meta.pop("awaiting_pr", None)
                    meta_updated = True
                existing_pr = curr["pr_url"] if "pr_url" in curr.keys() else None
                if prev_status != "done" and existing_pr:
                    meta["close_pr"] = True
                    meta_updated = True
        elif "awaiting_pr" in meta or "close_pr" in meta:
            meta.pop("awaiting_pr", None)
            meta.pop("close_pr", None)
            meta_updated = True

        if req.status == "blocked" and req.reason:
            # The pair: free text for humans, canonical code for deterministic
            # routing (agents emit one of BLOCKED_REASON_TYPES verbatim via
            # `block --reason <code>`; other prose classifies as human-gate).
            meta["blocked_reason"] = req.reason
            meta["blocked_reason_type"] = normalize_blocked_reason_type(req.reason)
            meta_updated = True

        if req.status in ("todo", "running", "done"):
            if "last_worker_failure" in meta:
                meta.pop("last_worker_failure", None)
                meta_updated = True
            if req.status in ("todo", "running", "done"):
                if "permanently_blocked" in meta:
                    meta.pop("permanently_blocked", None)
                    meta_updated = True
                if "worker_failure_retries" in meta:
                    meta.pop("worker_failure_retries", None)
                    meta_updated = True
                if "blocked_reason" in meta or "blocked_reason_type" in meta:
                    meta.pop("blocked_reason", None)
                    meta.pop("blocked_reason_type", None)
                    meta_updated = True
                if "conflict_retries" in meta:
                    meta.pop("conflict_retries", None)
                    meta_updated = True
            if req.status == "todo" or (req.status == "done" and not is_agent_actor):
                if "worker_pid" in meta or "session_id" in meta or "started_at" in meta:
                    meta.pop("worker_pid", None)
                    meta.pop("session_id", None)
                    meta.pop("started_at", None)
                    meta_updated = True
                sessions = meta.get("sessions")
                if isinstance(sessions, list):
                    for s in sessions:
                        if isinstance(s, dict) and s.get("status") == "ongoing":
                            s["status"] = "aborted"
                            if not s.get("ended_at"):
                                s["ended_at"] = now
                            meta_updated = True
                try:
                    from ...dispatcher import stop_task_worker
                except Exception:
                    try:
                        from dispatcher import stop_task_worker  # type: ignore
                    except Exception:
                        stop_task_worker = None
                if stop_task_worker is not None and not is_agent_actor:
                    try:
                        stop_task_worker(task_id, cursor=cursor)
                    except Exception as _stw_err:
                        _log.debug(
                            "stop_task_worker in move_task failed for %s: %s",
                            task_id,
                            _stw_err,
                        )

        new_assignee = getattr(req, "assignee", None)
        # 'blocked' is the human gate: every parked task belongs to the human
        # queue (approved merges, escalations, manual gates). The sole exception
        # is 'changes-requested', which is builder-bound feedback.
        if (
            not new_assignee
            and req.status == "blocked"
            and meta.get("blocked_reason_type") != "changes-requested"
        ):
            new_assignee = "human"

        if prev_status != req.status or meta_updated or new_assignee:
            if new_assignee:
                cursor.execute(
                    "UPDATE tasks SET status = ?, assignee = ?, metadata = ?, updated_at = ? WHERE id = ?",
                    (new_status, new_assignee, json.dumps(meta), now, task_id),
                )
            else:
                cursor.execute(
                    "UPDATE tasks SET status = ?, metadata = ?, updated_at = ? WHERE id = ?",
                    (new_status, json.dumps(meta), now, task_id),
                )
            if prev_status != req.status:
                move_actor = req.actor or "user"
                move_detail = (
                    "Agent reported completion; awaiting PR packaging"
                    if new_status != req.status
                    else f"Moved from {prev_status} to {req.status}"
                )
                log_activity(
                    conn,
                    task_id,
                    move_actor,
                    "move",
                    move_detail,
                )

        if req.status == "blocked" and req.reason:
            actor = req.actor or "user"
            comment_body = f"Blocked: {req.reason}"
            cursor.execute(
                "SELECT body FROM task_comments WHERE task_id = ? ORDER BY created_at DESC, id DESC LIMIT 1",
                (task_id,),
            )
            last_comment = cursor.fetchone()
            if not last_comment or last_comment["body"] != comment_body:
                cursor.execute(
                    "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, ?, ?, ?)",
                    (task_id, actor, comment_body, now),
                )
                comment_id = cursor.lastrowid
                log_activity(
                    conn, task_id, actor, "comment", f"Added comment #{comment_id}"
                )

            b_slug = curr["board_slug"] if "board_slug" in curr.keys() else ""
            if b_slug:
                try:
                    extract_and_record_memory(
                        conn,
                        board_slug=b_slug,
                        text=req.reason,
                        task_id=task_id,
                        author=actor,
                    )
                except Exception as _mem_err:
                    _log.debug(
                        "Auto-record memory from move_task reason failed: %s", _mem_err
                    )

        conn.commit()
        log_step_end(
            "move",
            move_t0,
            task_id,
            "ok",
            f"{prev_status} -> {new_status} assignee={new_assignee or '-'}",
            logger=_log,
        )

        if (
            req.status in ("todo", "done")
            and not os.environ.get("ZEROFACTORY_SKIP_DISPATCHER")
            and not os.environ.get("ZEROFACTORY_DISABLE_DISPATCHER")
        ):
            _trigger_async_dispatch("move_task")

    return {
        "ok": True,
        "id": task_id,
        "status": new_status,
        "prev_status": prev_status,
        "reason": req.reason,
    }


@router.delete("/tasks/{task_id}")
def delete_task(task_id: str):
    """Delete a task and all associated comments, links, and activity."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        conn.commit()
    return {"ok": True, "deleted": task_id}


@router.get("/tasks/{task_id}/comments")
def get_comments(task_id: str):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT * FROM task_comments WHERE task_id = ? ORDER BY created_at ASC",
            (task_id,),
        )
        return {"ok": True, "comments": [dict(r) for r in cursor.fetchall()]}


@router.post("/tasks/{task_id}/comments")
def add_comment(task_id: str, req: CommentCreate):
    now = int(time.time())
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, board_slug FROM tasks WHERE id = ?", (task_id,))
        task_row = cursor.fetchone()
        if not task_row:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

        body_str = req.body.strip()
        if req.author:
            author_val = req.author
        elif os.environ.get("HERMES_PROFILE"):
            author_val = os.environ.get("HERMES_PROFILE")
        else:
            author_val = "user"

        cursor.execute(
            "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, ?, ?, ?)",
            (task_id, author_val, body_str, now),
        )
        comment_id = cursor.lastrowid
        first_line = body_str.split("\n")[0][:60]
        details_str = (
            f"Added comment #{comment_id}: {first_line}"
            if first_line
            else f"Added comment #{comment_id}"
        )
        log_activity(conn, task_id, author_val, "comment", details_str)

        b_slug = task_row["board_slug"] if "board_slug" in task_row.keys() else ""
        if b_slug:
            try:
                extract_and_record_memory(
                    conn,
                    board_slug=b_slug,
                    text=body_str,
                    task_id=task_id,
                    author=author_val,
                )
            except Exception as _mem_err:
                _log.debug("Auto-record memory from comment failed: %s", _mem_err)

        conn.commit()

    return {"ok": True, "id": comment_id}


@router.post("/tasks/{task_id}/dependencies")
def add_dependency(task_id: str, link: DependencyLink):
    """Add a dependency link between parent and child."""
    parent_id = link.parent_id or (task_id if link.child_id else None)
    child_id = link.child_id or (task_id if link.parent_id else None)
    if not parent_id or not child_id:
        parent_id = link.parent_id or task_id
        child_id = link.child_id or task_id

    now = int(time.time())
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM tasks WHERE id = ?", (parent_id,))
        if not cursor.fetchone():
            raise HTTPException(
                status_code=404, detail=f"Parent task '{parent_id}' not found"
            )
        cursor.execute("SELECT id FROM tasks WHERE id = ?", (child_id,))
        if not cursor.fetchone():
            raise HTTPException(
                status_code=404, detail=f"Child task '{child_id}' not found"
            )

        if parent_id == child_id:
            raise HTTPException(status_code=400, detail="Task cannot depend on itself")

        link_type_val = (link.link_type or "blocks").strip().lower()
        if link_type_val not in ("blocks", "relates_to"):
            link_type_val = "blocks"

        cursor.execute(
            """INSERT INTO task_links (parent_id, child_id, link_type, created_at)
               VALUES (?, ?, ?, ?)
               ON CONFLICT(parent_id, child_id) DO UPDATE SET link_type = excluded.link_type""",
            (parent_id, child_id, link_type_val, now),
        )
        log_activity(
            conn, child_id, "user", "link", f"Added {link_type_val} dependency #{parent_id}"
        )
        conn.commit()

        return {"ok": True, "parent_id": parent_id, "child_id": child_id, "link_type": link_type_val}


@router.delete("/tasks/{task_id}/dependencies/{parent_id}")
def remove_dependency(task_id: str, parent_id: str):
    """Remove a dependency link."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM task_links WHERE parent_id = ? AND child_id = ?",
            (parent_id, task_id),
        )
        log_activity(
            conn, task_id, "user", "unlink", f"Removed parent dependency #{parent_id}"
        )
        conn.commit()
    return {"ok": True, "removed": f"{parent_id} -> {task_id}"}


@router.post("/tasks/{task_id}/triage")
def triage_task(task_id: str):
    """Trigger Grill-with-Docs triage dispatch for a task by zf-orchestrator."""
    init_db()
    now = int(time.time())
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task_row = cursor.fetchone()
        if not task_row:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        task = row_to_dict(task_row)

        raw_meta = task.get("metadata") or "{}"
        try:
            meta = json.loads(raw_meta) if isinstance(raw_meta, str) else dict(raw_meta)
        except Exception:
            meta = {}

        meta.pop("blocked_reason", None)
        target_status = "triage"
        assignee = "zf-orchestrator"

        cursor.execute(
            "UPDATE tasks SET status = ?, assignee = ?, metadata = ?, updated_at = ? WHERE id = ?",
            (target_status, assignee, json.dumps(meta), now, task_id),
        )
        log_activity(
            conn,
            task_id,
            "user",
            "triage_dispatched",
            "Dispatched task to zf-orchestrator for Grill-with-Docs triage",
        )
        conn.commit()

        if not os.environ.get("ZEROFACTORY_SKIP_DISPATCHER") and not os.environ.get(
            "ZEROFACTORY_DISABLE_DISPATCHER"
        ):
            _trigger_async_dispatch("triage_task")

    return {
        "ok": True,
        "task_id": task_id,
        "status": target_status,
        "assignee": assignee,
        "message": "Task queued for Grill-with-Docs triage by zf-orchestrator.",
    }


@router.post("/tasks/{task_id}/interview-reply")
def reply_interview(task_id: str, req: InterviewReply):
    """Submit human reply / option selection for a Grill-with-Docs interview question."""
    init_db()
    now = int(time.time())
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task_row = cursor.fetchone()
        if not task_row:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        task = row_to_dict(task_row)

        reply_lines = [
            f"🎯 **[Grill-with-Docs Human Response]**\n**Selection:** {req.selection.strip()}"
        ]
        if req.notes and req.notes.strip():
            reply_lines.append(
                f"**Additional Notes / Constraints:**\n{req.notes.strip()}"
            )
        comment_body = "\n\n".join(reply_lines)

        author_val = os.environ.get("HERMES_PROFILE") or "human"
        cursor.execute(
            "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, ?, ?, ?)",
            (task_id, author_val, comment_body, now),
        )
        comment_id = cursor.lastrowid
        log_activity(
            conn,
            task_id,
            author_val,
            "interview_reply",
            f"Submitted interview response: {req.selection[:60]}",
        )

        raw_meta = task.get("metadata") or "{}"
        try:
            meta = json.loads(raw_meta) if isinstance(raw_meta, str) else dict(raw_meta)
        except Exception:
            meta = {}

        meta["last_interview_reply"] = {
            "selection": req.selection.strip(),
            "notes": (req.notes or "").strip(),
            "replied_at": now,
        }
        meta.pop("blocked_reason", None)

        target_status = "triage"
        assignee = "zf-orchestrator"
        cursor.execute(
            "UPDATE tasks SET status = ?, assignee = ?, metadata = ?, updated_at = ? WHERE id = ?",
            (target_status, assignee, json.dumps(meta), now, task_id),
        )
        conn.commit()

        if (
            req.advance
            and not os.environ.get("ZEROFACTORY_SKIP_DISPATCHER")
            and not os.environ.get("ZEROFACTORY_DISABLE_DISPATCHER")
        ):
            _trigger_async_dispatch("interview_reply")

    return {
        "ok": True,
        "task_id": task_id,
        "comment_id": comment_id,
        "status": target_status,
        "message": "Interview response recorded. Triage resuming with zf-orchestrator.",
    }
