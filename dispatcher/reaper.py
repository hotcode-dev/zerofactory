"""Worker process reaping, stuck task detection, and recovery for Zero Factory."""

from __future__ import annotations

import json
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import (
    _active_workers,
    _d,
    _dispatcher_lock,
    _log,
    get_db_path,
    get_inactivity_timeout_seconds,
    get_max_worker_retries,
    get_task_timeout_seconds,
)


def _worker_log_path(task_id: str) -> Path:
    """Return the canonical worker log path for a task."""
    return Path.home() / ".hermes" / "logs" / f"worker_{task_id}.log"


def _compute_stuck_state(
    now: int,
    started_at: Any,
    log_path: Path,
    task_timeout: int,
    inactivity_timeout: int,
    is_dead: Optional[bool] = None,
    pid: Optional[int] = None,
) -> Tuple[bool, Optional[str], int]:
    """Compute (is_stuck, stuck_reason, idle_seconds) for a running task.

    Single source of truth for stuck-worker semantics, shared by
    ``reap_active_workers()`` (the only path that kills processes) and
    ``check_stuck_tasks()`` (the reporting/manual-reap detector) so the two
    gates can no longer drift apart.
    """
    running_seconds = max(0, now - int(started_at))

    idle_seconds: Optional[int] = None
    if log_path.exists():
        try:
            mtime = int(log_path.stat().st_mtime)
            if mtime > int(started_at):
                # Fresh mtime: authoritative evidence of the last write.
                idle_seconds = max(0, now - mtime)
        except Exception:
            idle_seconds = None

    is_stuck = False
    stuck_reason = None

    if is_dead is None and pid:
        try:
            os.kill(int(pid), 0)
            is_dead = False
        except (OSError, ValueError):
            is_dead = True

    if is_dead:
        is_stuck = True
        stuck_reason = f"Worker process PID {pid} is dead/not found"
    elif running_seconds > task_timeout:
        is_stuck = True
        stuck_reason = f"Exceeded running timeout ({running_seconds}s > {task_timeout}s)"
    elif (
        running_seconds > inactivity_timeout
        and idle_seconds is not None
        and idle_seconds > inactivity_timeout
    ):
        is_stuck = True
        stuck_reason = f"Worker inactive with no updates for {idle_seconds}s (limit {inactivity_timeout}s)"

    # Report a display-safe int: a stale/absent log has no inactivity evidence,
    # so surface the running time, but the inactivity gate above has already refused to fire on it.
    reported_idle = running_seconds if idle_seconds is None else idle_seconds
    return is_stuck, stuck_reason, reported_idle


def _mark_task_session_ended(meta: Dict[str, Any], now: int, final_status: str = "finished") -> Dict[str, Any]:
    """Helper to finalize the ongoing session entry in task metadata."""
    sessions = meta.get("sessions")
    if isinstance(sessions, list):
        for s in sessions:
            if isinstance(s, dict) and s.get("status") == "ongoing":
                s["status"] = final_status
                if not s.get("ended_at"):
                    s["ended_at"] = now
    return meta


def reap_active_workers(cursor: sqlite3.Cursor, now: int) -> int:
    """Check running tasks and reap finished, crashed, or stuck worker processes."""
    cursor.execute("SELECT id, title, metadata, updated_at, created_at FROM tasks WHERE status = 'running'")
    running_rows = cursor.fetchall()
    reaped = 0

    task_timeout = _d().get_task_timeout_seconds()
    inactivity_timeout = _d().get_inactivity_timeout_seconds()

    for row in running_rows:
        task_id = str(row["id"])
        meta = {}
        try:
            meta = json.loads(row["metadata"] or "{}")
        except Exception:
            pass

        proc = _active_workers.get(task_id)
        pid = meta.get("worker_pid") or (proc.pid if proc else None)

        sessions = meta.get("sessions")
        has_ongoing_session = isinstance(sessions, list) and any(
            isinstance(session, dict) and session.get("status") == "ongoing"
            for session in sessions
        )
        if proc is None and pid and not has_ongoing_session:
            meta.pop("worker_pid", None)
            meta.pop("session_id", None)
            meta.pop("started_at", None)
            pid = None
            cursor.execute(
                "UPDATE tasks SET metadata = ? WHERE id = ?",
                (json.dumps(meta), task_id),
            )

        if proc is not None:
            retcode = proc.poll()
            if retcode is not None:
                _active_workers.pop(task_id, None)
                if retcode == 0:
                    meta = _d()._mark_task_session_ended(meta, now, "finished")
                    meta.pop("worker_failure_retries", None)
                    meta.pop("last_worker_failure", None)
                    cursor.execute("UPDATE tasks SET status = 'done', metadata = ?, updated_at = ? WHERE id = ?", (json.dumps(meta), now, task_id))
                    cursor.execute(
                        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_done', 'Worker process completed successfully (exit 0)', ?)",
                        (task_id, now)
                    )
                    _log.info("Worker for task %s finished successfully (exit 0); moved to done", task_id)
                else:
                    meta = _d()._mark_task_session_ended(meta, now, "failed")
                    fail_retries = int(meta.get("worker_failure_retries", 0)) + 1
                    meta["worker_failure_retries"] = fail_retries
                    meta["last_worker_failure"] = {"retcode": retcode, "failed_at": now}
                    max_worker_retries = _d().get_max_worker_retries()
                    if fail_retries >= max_worker_retries:
                        meta["permanently_blocked"] = True
                        meta["blocked_reason"] = f"Worker process failed {fail_retries} times (limit {max_worker_retries})"
                        cursor.execute("UPDATE tasks SET status = 'blocked', metadata = ?, updated_at = ? WHERE id = ?", (json.dumps(meta), now, task_id))
                        cursor.execute(
                            "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, 'dispatcher', ?, ?)",
                            (task_id, f"Blocked: {meta['blocked_reason']}", now)
                        )
                        cursor.execute(
                            "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_failed_permanently', ?, ?)",
                            (task_id, f"Worker process failed with exit code {retcode} ({fail_retries}/{max_worker_retries} retries exceeded); task permanently blocked", now)
                        )
                        _log.warning("Worker for task %s permanently blocked after %d failures (code %d)", task_id, fail_retries, retcode)
                    else:
                        meta["blocked_reason"] = f"Worker process exited with code {retcode} (attempt {fail_retries}/{max_worker_retries})"
                        cursor.execute("UPDATE tasks SET status = 'blocked', metadata = ?, updated_at = ? WHERE id = ?", (json.dumps(meta), now, task_id))
                        cursor.execute(
                            "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, 'dispatcher', ?, ?)",
                            (task_id, f"Blocked: {meta['blocked_reason']}", now)
                        )
                        cursor.execute(
                            "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_failed', ?, ?)",
                            (task_id, f"Worker process exited with code {retcode} (attempt {fail_retries}/{max_worker_retries})", now)
                        )
                        _log.warning("Worker for task %s failed with exit code %d; moved to blocked", task_id, retcode)
                reaped += 1
                continue
        elif pid:
            try:
                os.kill(pid, 0)
            except OSError:
                meta = _d()._mark_task_session_ended(meta, now, "lost")
                fail_retries = int(meta.get("worker_failure_retries", 0)) + 1
                meta["worker_failure_retries"] = fail_retries
                meta["last_worker_failure"] = {"retcode": -1, "reason": "PID not found", "failed_at": now}
                max_worker_retries = _d().get_max_worker_retries()
                if fail_retries >= max_worker_retries:
                    meta["permanently_blocked"] = True
                    meta["blocked_reason"] = f"Worker lost {fail_retries} times (limit {max_worker_retries})"
                    cursor.execute("UPDATE tasks SET status = 'blocked', metadata = ?, updated_at = ? WHERE id = ?", (json.dumps(meta), now, task_id))
                    cursor.execute(
                        "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, 'dispatcher', ?, ?)",
                        (task_id, f"Blocked: {meta['blocked_reason']}", now)
                    )
                    cursor.execute(
                        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_failed_permanently', ?, ?)",
                        (task_id, f"Worker process PID {pid} not found ({fail_retries}/{max_worker_retries} retries exceeded); task permanently blocked", now)
                    )
                else:
                    meta["blocked_reason"] = f"Worker process PID {pid} not found (attempt {fail_retries}/{max_worker_retries})"
                    cursor.execute("UPDATE tasks SET status = 'blocked', metadata = ?, updated_at = ? WHERE id = ?", (json.dumps(meta), now, task_id))
                    cursor.execute(
                        "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, 'dispatcher', ?, ?)",
                        (task_id, f"Blocked: {meta['blocked_reason']}", now)
                    )
                    cursor.execute(
                        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_lost', ?, ?)",
                        (task_id, f"Worker process PID {pid} not found (attempt {fail_retries}/{max_worker_retries}); moved to blocked", now)
                    )
                _log.warning("Worker PID %d for task %s not found; moved to blocked", pid, task_id)
                reaped += 1
                continue
        elif not has_ongoing_session:
            # Task is marked 'running' but has no active process, PID, or ongoing session
            claim_age = max(0, now - int(row["updated_at"] or now))
            if claim_age >= 30:
                cursor.execute(
                    "UPDATE tasks SET status = 'todo', updated_at = ? WHERE id = ?",
                    (now, task_id)
                )
                cursor.execute(
                    "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_recovered', 'Orphaned running task (no active worker process or session) recovered to todo', ?)",
                    (task_id, now)
                )
                _log.warning("Recovered orphaned running task %s to todo (no active worker or session, age %ds)", task_id, claim_age)
                reaped += 1
                continue

        started_at = meta.get("started_at") or row["updated_at"] or row["created_at"] or now
        is_stuck, stuck_reason, _idle = _d()._compute_stuck_state(
            now=now,
            started_at=started_at,
            log_path=_d()._worker_log_path(task_id),
            task_timeout=task_timeout,
            inactivity_timeout=inactivity_timeout,
            is_dead=False,
        )

        if is_stuck:
            _d().terminate_worker_process(proc, pid)
            _active_workers.pop(task_id, None)
            meta = _d()._mark_task_session_ended(meta, now, "timed_out")
            fail_retries = int(meta.get("worker_failure_retries", 0)) + 1
            meta["worker_failure_retries"] = fail_retries
            meta["last_worker_failure"] = {"retcode": -9, "reason": stuck_reason, "failed_at": now}
            max_worker_retries = _d().get_max_worker_retries()
            if fail_retries >= max_worker_retries:
                meta["permanently_blocked"] = True
                meta["blocked_reason"] = f"Worker timeout/inactivity {fail_retries} times (limit {max_worker_retries}): {stuck_reason}"
                cursor.execute("UPDATE tasks SET status = 'blocked', metadata = ?, updated_at = ? WHERE id = ?", (json.dumps(meta), now, task_id))
                cursor.execute(
                    "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, 'dispatcher', ?, ?)",
                    (task_id, f"Blocked: {meta['blocked_reason']}", now)
                )
                cursor.execute(
                    "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_timeout_permanently', ?, ?)",
                    (task_id, f"Task exceeded timeout/inactivity limit ({fail_retries}/{max_worker_retries}): {stuck_reason}; task permanently blocked", now)
                )
            else:
                meta["blocked_reason"] = f"{stuck_reason} (attempt {fail_retries}/{max_worker_retries})"
                cursor.execute("UPDATE tasks SET status = 'blocked', metadata = ?, updated_at = ? WHERE id = ?", (json.dumps(meta), now, task_id))
                cursor.execute(
                    "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, 'dispatcher', ?, ?)",
                    (task_id, f"Blocked: {meta['blocked_reason']}", now)
                )
                cursor.execute(
                    "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_timeout', ?, ?)",
                    (task_id, f"{stuck_reason} (attempt {fail_retries}/{max_worker_retries})", now)
                )
            _log.warning("Task %s reaped due to timeout/inactivity: %s; moved to blocked", task_id, stuck_reason)
            reaped += 1

    return reaped


def check_stuck_tasks(cursor: Optional[sqlite3.Cursor] = None, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Inspect all running tasks and identify any that are stuck or inactive."""
    if db_path is None:
        db_path = _d().get_db_path()

    if not db_path.exists():
        return []

    close_conn = False
    if cursor is None:
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        close_conn = True

    now = int(time.time())
    task_timeout = _d().get_task_timeout_seconds()
    inactivity_timeout = _d().get_inactivity_timeout_seconds()

    results = []
    try:
        cursor.execute("SELECT id, title, status, assignee, workspace_path, metadata, created_at, updated_at, board_slug FROM tasks WHERE status = 'running'")
        for row in cursor.fetchall():
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

            is_dead = (not is_alive) and bool(pid)
            is_stuck, stuck_reason, idle_seconds = _d()._compute_stuck_state(
                now=now,
                started_at=started_at,
                log_path=_d()._worker_log_path(task_id),
                task_timeout=task_timeout,
                inactivity_timeout=inactivity_timeout,
                is_dead=is_dead,
                pid=pid,
            )

            results.append({
                "id": task_id,
                "title": row["title"],
                "board_slug": row["board_slug"] if "board_slug" in row.keys() else None,
                "assignee": row["assignee"] or "zf-builder",
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
        db_path = _d().get_db_path()

    now = int(time.time())
    reaped_tasks = []

    with _dispatcher_lock:
        with sqlite3.connect(str(db_path), timeout=10.0) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            stuck_list = _d().check_stuck_tasks(cursor=cursor)
            for item in stuck_list:
                t_id = item["id"]
                if task_id and t_id != task_id:
                    continue
                if task_id or item["is_stuck"]:
                    proc = _active_workers.pop(t_id, None)
                    pid = item["worker_pid"]
                    _d().terminate_worker_process(proc, pid)

                    reason = item["stuck_reason"] or f"Manually reaped after running {item['running_seconds']}s"
                    _meta = {}
                    _row = cursor.execute(
                        "SELECT metadata FROM tasks WHERE id = ?", (t_id,)
                    ).fetchone()
                    if _row is not None:
                        try:
                            _meta = json.loads(_row["metadata"] or "{}")
                        except Exception:
                            _meta = {}
                    _meta["blocked_reason"] = reason
                    cursor.execute(
                        "UPDATE tasks SET status = 'blocked', metadata = ?, updated_at = ? WHERE id = ?",
                        (json.dumps(_meta), now, t_id)
                    )
                    cursor.execute(
                        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_timeout', ?, ?)",
                        (t_id, reason, now)
                    )
                    reaped_tasks.append({"id": t_id, "title": item["title"], "reason": reason})

            conn.commit()

    return {
        "ok": True,
        "reaped_count": len(reaped_tasks),
        "reaped_tasks": reaped_tasks,
        "reaped": reaped_tasks
    }
