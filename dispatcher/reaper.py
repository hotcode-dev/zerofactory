"""Worker process reaping, stuck task detection, and recovery for Zero Factory."""

from __future__ import annotations

import json
import sqlite3
import time
from pathlib import Path
from typing import Any

from .config import (
    _active_workers,
    _d,
    _dispatcher_lock,
    _log,
    log_step_state,
)


def _worker_log_path(task_id: str) -> Path:
    """Return the canonical worker log path for a task."""
    return Path.home() / ".hermes" / "logs" / f"worker_{task_id}.log"


# Ad-hoc reaper DB connections match the dispatcher convention
# (dispatcher/scheduler.py run_dispatch_cycle uses busy_timeout=15000): a WAL
# database can be briefly held by the dashboard process (many open connections
# plus an active writer), and a plain connect() with no busy window aborts the
# watchdog tick with sqlite3.OperationalError "database is locked".
_BUSY_TIMEOUT_MS = 15000


def _open_reaper_conn(db_path: Path) -> sqlite3.Connection:
    """Open a reaper DB connection with a WAL-tolerant busy timeout."""
    conn = sqlite3.connect(str(db_path), timeout=15.0)
    conn.execute(f"PRAGMA busy_timeout={_BUSY_TIMEOUT_MS};")
    return conn


def _compute_stuck_state(
    now: int,
    started_at: Any,
    log_path: Path,
    task_timeout: int,
    inactivity_timeout: int,
    is_dead: bool | None = None,
    pid: int | None = None,
) -> tuple[bool, str | None, int]:
    """Compute (is_stuck, stuck_reason, idle_seconds) for a running task.

    Single source of truth for stuck-worker semantics, shared by
    ``reap_active_workers()`` (the only path that kills processes) and
    ``check_stuck_tasks()`` (the reporting/manual-reap detector) so the two
    gates cannot drift apart.
    """
    running_seconds = max(0, now - int(started_at))

    idle_seconds: int | None = None
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
        is_dead = not _d().is_pid_alive(int(pid))

    if is_dead:
        is_stuck = True
        stuck_reason = (
            f"Worker process PID {pid} is dead/not found"
            if pid
            else "Worker process not found / session lost"
        )
    elif running_seconds > task_timeout:
        is_stuck = True
        stuck_reason = (
            f"Exceeded running timeout ({running_seconds}s > {task_timeout}s)"
        )
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


def _mark_task_session_ended(
    meta: dict[str, Any], now: int, final_status: str = "finished"
) -> dict[str, Any]:
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
    cursor.execute(
        "SELECT id, title, status, metadata, updated_at, created_at FROM tasks WHERE status = 'running' OR (status = 'triage' AND metadata LIKE '%\"status\": \"ongoing\"%')"
    )
    running_rows = cursor.fetchall()
    reaped = 0

    task_timeout = _d().get_task_timeout_seconds(cursor)
    inactivity_timeout = _d().get_inactivity_timeout_seconds(cursor)

    for row in running_rows:
        task_id = str(row["id"])
        row_status = str(row["status"]) if "status" in row.keys() else "running"
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
                    cursor.execute(
                        "SELECT assignee, status, title FROM tasks WHERE id = ?",
                        (task_id,),
                    )
                    t_check = cursor.fetchone()
                    curr_asgn = t_check["assignee"] if t_check else ""
                    curr_stat = t_check["status"] if t_check else ""
                    _curr_title = (
                        t_check["title"]
                        if (t_check and "title" in t_check.keys())
                        else ""
                    )

                    meta = _d()._mark_task_session_ended(meta, now, "finished")
                    meta.pop("worker_failure_retries", None)
                    meta.pop("last_worker_failure", None)
                    # The LLM worker is finished; clear its live identity so the
                    # next reaper pass cannot misfire the dead-PID branch on the
                    # stale PID and loop the task into a fresh respawn. Packaging
                    # is deterministic (dispatcher step 3), not a live worker.
                    meta.pop("worker_pid", None)
                    meta.pop("session_id", None)
                    meta.pop("started_at", None)

                    is_triage_task = (
                        curr_stat == "triage" or curr_asgn == "zf-orchestrator"
                    )
                    blocked_reason = str(meta.get("blocked_reason") or "").lower()
                    if is_triage_task and (
                        "grill" in blocked_reason
                        or "interview" in blocked_reason
                        or "human" in blocked_reason
                        or curr_stat == "triage"
                    ):
                        target_status = "triage"
                        meta.pop("blocked_reason", None)
                        meta["awaiting_interview"] = True
                        cursor.execute(
                            "UPDATE tasks SET assignee = 'human' WHERE id = ? AND assignee != 'human'",
                            (task_id,),
                        )
                    elif curr_stat in ("blocked", "todo", "triage"):
                        target_status = curr_stat
                    elif is_triage_task:
                        target_status = "triage"
                    else:
                        # Builder/reviewer work finished: the task stays
                        # 'running' while the deterministic pipeline packages
                        # the worktree (precommit -> commit -> push -> PR ->
                        # reviewer). 'done' is strictly terminal and only set
                        # after merge/close/human close; the awaiting_pr flag
                        # marks the packaging phase for the dispatcher.
                        target_status = "running"
                        meta["awaiting_pr"] = True

                    cursor.execute(
                        "UPDATE tasks SET status = ?, metadata = ?, updated_at = ? WHERE id = ?",
                        (target_status, json.dumps(meta), now, task_id),
                    )
                    cursor.execute(
                        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_done', ?, ?)",
                        (
                            task_id,
                            f"Worker process completed successfully (exit 0); status set to {target_status}",
                            now,
                        ),
                    )
                    _log.info(
                        "Worker for task %s finished successfully (exit 0); moved to %s",
                        task_id,
                        target_status,
                    )
                else:
                    cursor.execute(
                        "SELECT assignee, status, title FROM tasks WHERE id = ?",
                        (task_id,),
                    )
                    t_check = cursor.fetchone()
                    curr_stat = t_check["status"] if t_check else ""
                    if curr_stat in ("todo", "done"):
                        meta = _d()._mark_task_session_ended(meta, now, "finished")
                        cursor.execute(
                            "UPDATE tasks SET metadata = ?, updated_at = ? WHERE id = ?",
                            (json.dumps(meta), now, task_id),
                        )
                        _log.info(
                            "Worker for task %s exited with code %d but task is already in %s; keeping %s",
                            task_id,
                            retcode,
                            curr_stat,
                            curr_stat,
                        )
                        reaped += 1
                        continue

                    meta = _d()._mark_task_session_ended(meta, now, "failed")
                    fail_retries = int(meta.get("worker_failure_retries", 0)) + 1
                    meta["worker_failure_retries"] = fail_retries
                    meta["last_worker_failure"] = {"retcode": retcode, "failed_at": now}
                    max_worker_retries = _d().get_max_worker_retries()
                    if fail_retries >= max_worker_retries:
                        meta["permanently_blocked"] = True
                        meta["blocked_reason"] = (
                            f"Worker process failed {fail_retries} times (limit {max_worker_retries})"
                        )
                        meta["blocked_reason_type"] = "stuck"
                        cursor.execute(
                            "UPDATE tasks SET status = 'blocked', metadata = ?, updated_at = ? WHERE id = ?",
                            (json.dumps(meta), now, task_id),
                        )
                        cursor.execute(
                            "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, 'dispatcher', ?, ?)",
                            (task_id, f"Blocked: {meta['blocked_reason']}", now),
                        )
                        cursor.execute(
                            "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_failed_permanently', ?, ?)",
                            (
                                task_id,
                                f"Worker process failed with exit code {retcode} ({fail_retries}/{max_worker_retries} retries exceeded); task permanently blocked",
                                now,
                            ),
                        )
                        _log.warning(
                            "Worker for task %s permanently blocked after %d failures (code %d)",
                            task_id,
                            fail_retries,
                            retcode,
                        )
                    else:
                        meta["blocked_reason"] = (
                            f"Worker process exited with code {retcode} (attempt {fail_retries}/{max_worker_retries})"
                        )
                        retry_status = "todo" if row_status == "running" else "blocked"
                        cursor.execute(
                            "UPDATE tasks SET status = ?, metadata = ?, updated_at = ? WHERE id = ?",
                            (retry_status, json.dumps(meta), now, task_id),
                        )
                        cursor.execute(
                            "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, 'dispatcher', ?, ?)",
                            (task_id, f"Retrying: {meta['blocked_reason']}", now),
                        )
                        cursor.execute(
                            "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_failed', ?, ?)",
                            (
                                task_id,
                                f"Worker process exited with code {retcode} (attempt {fail_retries}/{max_worker_retries}); queued for retry",
                                now,
                            ),
                        )
                        _log.warning(
                            "Worker for task %s failed with exit code %d; queued for retry",
                            task_id,
                            retcode,
                        )
                reaped += 1
                continue
        elif pid:
            if row_status == "running" and meta.get("awaiting_pr"):
                # Deterministic packaging phase that still carries a stale
                # worker_pid in metadata: the LLM worker is done and the
                # dispatcher's step-3 owns precommit->commit->push->PR. Never
                # treat this as a lost worker or bump the failure budget.
                continue
            if not _d().is_pid_alive(int(pid)):
                meta = _d()._mark_task_session_ended(meta, now, "lost")
                fail_retries = int(meta.get("worker_failure_retries", 0)) + 1
                meta["worker_failure_retries"] = fail_retries
                meta["last_worker_failure"] = {
                    "retcode": -1,
                    "reason": "PID not found",
                    "failed_at": now,
                }
                max_worker_retries = _d().get_max_worker_retries()
                if fail_retries >= max_worker_retries:
                    meta["permanently_blocked"] = True
                    meta["blocked_reason"] = (
                        f"Worker lost {fail_retries} times (limit {max_worker_retries})"
                    )
                    meta["blocked_reason_type"] = "stuck"
                    cursor.execute(
                        "UPDATE tasks SET status = 'blocked', metadata = ?, updated_at = ? WHERE id = ?",
                        (json.dumps(meta), now, task_id),
                    )
                    cursor.execute(
                        "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, 'dispatcher', ?, ?)",
                        (task_id, f"Blocked: {meta['blocked_reason']}", now),
                    )
                    cursor.execute(
                        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_failed_permanently', ?, ?)",
                        (
                            task_id,
                            f"Worker process PID {pid} not found ({fail_retries}/{max_worker_retries} retries exceeded); task permanently blocked",
                            now,
                        ),
                    )
                else:
                    meta["blocked_reason"] = (
                        f"Worker process PID {pid} not found (attempt {fail_retries}/{max_worker_retries})"
                    )
                    retry_status = "todo" if row_status == "running" else "blocked"
                    cursor.execute(
                        "UPDATE tasks SET status = ?, metadata = ?, updated_at = ? WHERE id = ?",
                        (retry_status, json.dumps(meta), now, task_id),
                    )
                    cursor.execute(
                        "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, 'dispatcher', ?, ?)",
                        (task_id, f"Retrying: {meta['blocked_reason']}", now),
                    )
                    cursor.execute(
                        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_lost', ?, ?)",
                        (
                            task_id,
                            f"Worker process PID {pid} not found (attempt {fail_retries}/{max_worker_retries}); queued for retry",
                            now,
                        ),
                    )
                _log.warning(
                    "Worker PID %d for task %s not found; moved to blocked",
                    pid,
                    task_id,
                )
                reaped += 1
                continue
        elif row_status == "running" and meta.get("awaiting_pr"):
            # Deterministic packaging phase (LLM finished; precommit/commit/PR
            # pipeline active in the dispatcher) — not an orphan. Step 3 of the
            # dispatch cycle owns this task until it routes onward.
            continue
        elif row_status == "running" and not has_ongoing_session:
            # Task is marked 'running' but has no active process, PID, or ongoing session
            claim_age = max(0, now - int(row["updated_at"] or now))
            spawning_at = meta.get("spawning_at")
            spawn_age = max(0, now - int(spawning_at)) if spawning_at else claim_age
            if spawn_age < _d().get_spawn_grace_seconds():
                # A spawn is (or may still be) in flight: the claim stamped
                # `spawning_at`, and worker_pid / session rows are written only
                # after hermes finishes starting. Recovering inside this window
                # double-dispatched the builder on zf-hdz-4dc03cee — two
                # concurrent sessions sharing one worktree.
                log_step_state(
                    "reap",
                    task_id,
                    "spawning",
                    f"spawn in flight for {spawn_age}s (grace {_d().get_spawn_grace_seconds()}s); not an orphan yet",
                )
                continue
            cursor.execute(
                "UPDATE tasks SET status = 'todo', updated_at = ? WHERE id = ?",
                (now, task_id),
            )
            cursor.execute(
                "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_recovered', 'Orphaned running task (no active worker process or session) recovered to todo', ?)",
                (task_id, now),
            )
            _log.warning(
                "Recovered orphaned running task %s to todo (no active worker or session, age %ds)",
                task_id,
                claim_age,
            )
            reaped += 1
            continue

        started_at = (
            meta.get("started_at") or row["updated_at"] or row["created_at"] or now
        )
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
            meta["last_worker_failure"] = {
                "retcode": -9,
                "reason": stuck_reason,
                "failed_at": now,
            }
            max_worker_retries = _d().get_max_worker_retries()
            if fail_retries >= max_worker_retries:
                meta["permanently_blocked"] = True
                meta["blocked_reason"] = (
                    f"Worker timeout/inactivity {fail_retries} times (limit {max_worker_retries}): {stuck_reason}"
                )
                meta["blocked_reason_type"] = "stuck"
                cursor.execute(
                    "UPDATE tasks SET status = 'blocked', metadata = ?, updated_at = ? WHERE id = ?",
                    (json.dumps(meta), now, task_id),
                )
                cursor.execute(
                    "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, 'dispatcher', ?, ?)",
                    (task_id, f"Blocked: {meta['blocked_reason']}", now),
                )
                cursor.execute(
                    "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_timeout_permanently', ?, ?)",
                    (
                        task_id,
                        f"Task exceeded timeout/inactivity limit ({fail_retries}/{max_worker_retries}): {stuck_reason}; task permanently blocked",
                        now,
                    ),
                )
            else:
                meta["blocked_reason"] = (
                    f"{stuck_reason} (attempt {fail_retries}/{max_worker_retries})"
                )
                retry_status = "todo" if row_status == "running" else "blocked"
                cursor.execute(
                    "UPDATE tasks SET status = ?, metadata = ?, updated_at = ? WHERE id = ?",
                    (retry_status, json.dumps(meta), now, task_id),
                )
                cursor.execute(
                    "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, 'dispatcher', ?, ?)",
                    (task_id, f"Retrying: {meta['blocked_reason']}", now),
                )
                cursor.execute(
                    "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_timeout', ?, ?)",
                    (
                        task_id,
                        f"{stuck_reason} (attempt {fail_retries}/{max_worker_retries}); queued for retry",
                        now,
                    ),
                )
            _log.warning(
                "Task %s reaped due to timeout/inactivity: %s; moved to blocked",
                task_id,
                stuck_reason,
            )
            reaped += 1

    return reaped


def check_stuck_tasks(
    cursor: sqlite3.Cursor | None = None,
    db_path: Path | None = None,
    include_blocked: bool = False,
) -> list[dict[str, Any]]:
    """Inspect tasks and identify any that are stuck, inactive, or exhausted."""
    if db_path is None:
        db_path = _d().get_db_path()

    if not db_path.exists():
        return []

    close_conn = False
    if cursor is None:
        conn = _open_reaper_conn(db_path)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        close_conn = True

    now = int(time.time())
    task_timeout = _d().get_task_timeout_seconds(cursor)
    inactivity_timeout = _d().get_inactivity_timeout_seconds(cursor)

    results = []
    try:
        cursor.execute(
            "SELECT id, title, status, assignee, workspace_path, metadata, created_at, updated_at, board_slug FROM tasks WHERE status = 'running'"
        )
        col_names = [d[0] for d in cursor.description] if cursor.description else []
        for raw_row in cursor.fetchall():
            row = (
                dict(zip(col_names, raw_row))
                if not hasattr(raw_row, "keys")
                else raw_row
            )
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
                is_alive = _d().is_pid_alive(int(pid))

            started_at = (
                meta.get("started_at") or row["updated_at"] or row["created_at"] or now
            )
            running_seconds = max(0, now - int(started_at))

            is_dead = (not is_alive) and bool(pid)
            if proc is None and not pid and not meta.get("awaiting_pr"):
                sessions = meta.get("sessions")
                has_ongoing = isinstance(sessions, list) and any(
                    isinstance(s, dict) and s.get("status") == "ongoing"
                    for s in sessions
                )
                claim_age = max(0, now - int(row["updated_at"] or now))
                if not has_ongoing and claim_age > _d().get_spawn_grace_seconds():
                    is_dead = True

            is_stuck, stuck_reason, idle_seconds = _d()._compute_stuck_state(
                now=now,
                started_at=started_at,
                log_path=_d()._worker_log_path(task_id),
                task_timeout=task_timeout,
                inactivity_timeout=inactivity_timeout,
                is_dead=is_dead,
                pid=pid,
            )

            stuck_state = None
            if meta.get("awaiting_pr"):
                # State 3: Stuck PR packaging
                pack_age = max(0, now - int(row["updated_at"] or started_at))
                if pack_age > task_timeout:
                    is_stuck = True
                    stuck_reason = f"PR packaging phase timed out after {pack_age}s (limit {task_timeout}s)"
                    stuck_state = "stuck_packaging"
            elif is_stuck:
                if is_dead:
                    stuck_state = "dead_worker"
                else:
                    stuck_state = "timeout_inactivity"

            results.append(
                {
                    "id": task_id,
                    "title": row["title"],
                    "board_slug": row["board_slug"]
                    if "board_slug" in row.keys()
                    else None,
                    "assignee": row["assignee"] or "zf-builder",
                    "status": "running",
                    "worker_pid": pid,
                    "is_alive": is_alive,
                    "started_at": started_at,
                    "running_seconds": running_seconds,
                    "idle_seconds": idle_seconds,
                    "is_stuck": is_stuck,
                    "stuck_reason": stuck_reason,
                    "stuck_state": stuck_state,
                    "orchestrator_recovery_count": int(
                        meta.get("orchestrator_recovery_count", 0)
                    ),
                    "timeout_limit": task_timeout,
                    "inactivity_limit": inactivity_timeout,
                }
            )

        if include_blocked:
            cursor.execute(
                "SELECT id, title, status, assignee, workspace_path, metadata, created_at, updated_at, board_slug FROM tasks WHERE status = 'blocked'"
            )
            b_col_names = (
                [d[0] for d in cursor.description] if cursor.description else []
            )
            for raw_row in cursor.fetchall():
                row = (
                    dict(zip(b_col_names, raw_row))
                    if not hasattr(raw_row, "keys")
                    else raw_row
                )
                task_id = str(row["id"])
                meta = {}
                try:
                    meta = json.loads(row["metadata"] or "{}")
                except Exception:
                    meta = {}

                # State 4: Failure exhausted stuck tasks eligible for orchestrator recovery
                b_type = str(meta.get("blocked_reason_type") or "").strip().lower()
                is_perm = bool(meta.get("permanently_blocked"))
                if b_type == "stuck" or is_perm:
                    recovery_count = int(meta.get("orchestrator_recovery_count", 0))
                    if recovery_count < 1:
                        reason = (
                            meta.get("blocked_reason")
                            or "Failure retry budget exhausted; task permanently blocked"
                        )
                        results.append(
                            {
                                "id": task_id,
                                "title": row["title"],
                                "board_slug": row["board_slug"]
                                if "board_slug" in row.keys()
                                else None,
                                "assignee": row["assignee"] or "human",
                                "status": "blocked",
                                "worker_pid": None,
                                "is_alive": False,
                                "started_at": row["updated_at"]
                                or row["created_at"]
                                or now,
                                "running_seconds": max(
                                    0, now - int(row["updated_at"] or now)
                                ),
                                "idle_seconds": max(
                                    0, now - int(row["updated_at"] or now)
                                ),
                                "is_stuck": True,
                                "stuck_reason": reason,
                                "stuck_state": "failure_exhausted",
                                "orchestrator_recovery_count": recovery_count,
                                "timeout_limit": task_timeout,
                                "inactivity_limit": inactivity_timeout,
                            }
                        )

        return results
    finally:
        if close_conn:
            try:
                conn.close()
            except Exception:
                pass


def reap_stuck_tasks(
    task_id: str | None = None, db_path: Path | None = None
) -> dict[str, Any]:
    """Manually or programmatically reap stuck tasks or a specific running task.

    Tolerates a WAL database that is briefly locked by another process (the
    dashboard holds many connections plus an active writer). The connection
    sets ``busy_timeout`` (matching the dispatcher convention) and the write
    section retries on ``sqlite3.OperationalError`` "database is locked" with
    exponential backoff, capped at ~30s total. On final failure it logs a
    warning and returns a clean failure dict instead of raising, so a busy DB
    can never abort the watchdog tick again.
    """
    db: Path = db_path if db_path is not None else _d().get_db_path()

    now = int(time.time())
    max_wait = 30.0
    deadline = time.monotonic() + max_wait
    attempt = 0
    base_delay = 0.5

    with _dispatcher_lock:
        while True:
            attempt += 1
            reaped_tasks = []
            try:
                with _open_reaper_conn(db) as conn:
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

                            reason = (
                                item["stuck_reason"]
                                or f"Manually reaped after running {item['running_seconds']}s"
                            )
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
                            _meta["blocked_reason_type"] = "stuck"
                            _meta = _d()._mark_task_session_ended(
                                _meta, now, "aborted" if task_id else "timed_out"
                            )
                            _meta.pop("worker_pid", None)
                            cursor.execute(
                                "UPDATE tasks SET assignee = 'human', status = 'blocked', metadata = ?, updated_at = ? WHERE id = ?",
                                (json.dumps(_meta), now, t_id),
                            )
                            cursor.execute(
                                "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_timeout', ?, ?)",
                                (t_id, reason, now),
                            )
                            reaped_tasks.append(
                                {"id": t_id, "title": item["title"], "reason": reason}
                            )

                    conn.commit()
                break
            except sqlite3.OperationalError as e:
                if "database is locked" not in str(e).lower():
                    raise
                remaining = deadline - time.monotonic()
                if remaining <= 0:
                    _log.warning(
                        "reap_stuck_tasks: database locked after %d attempts "
                        "(~%ds total); leaving reaping to the next watchdog tick",
                        attempt,
                        int(max_wait),
                    )
                    return {
                        "ok": False,
                        "reason": "database locked",
                        "reaped_count": 0,
                        "reaped_tasks": [],
                        "reaped": [],
                    }
                delay = min(base_delay * (2 ** (attempt - 1)), 5.0, remaining)
                time.sleep(delay)

    return {
        "ok": True,
        "reaped_count": len(reaped_tasks),
        "reaped_tasks": reaped_tasks,
        "reaped": reaped_tasks,
    }


def build_stuck_task_context(
    task_id: str, db_path: Path | None = None
) -> dict[str, Any]:
    """Gather diagnostic logs, error snippets, and worktree info for a stuck task."""
    if db_path is None:
        db_path = _d().get_db_path()

    result = {
        "id": task_id,
        "title": "",
        "board_slug": "",
        "repo_alias": "",
        "status": "",
        "assignee": "",
        "stuck_reason": "",
        "worker_failure_retries": 0,
        "precommit_retries": 0,
        "orchestrator_recovery_count": 0,
        "last_worker_failure": None,
        "last_precommit_error": None,
        "worker_log_tail": None,
        "comments": [],
    }

    if not db_path.exists():
        return result

    try:
        with _open_reaper_conn(db_path) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
            t_row = cur.fetchone()
            if not t_row:
                return result

            t = dict(t_row)
            result["title"] = t.get("title", "")
            result["board_slug"] = t.get("board_slug", "default")
            result["repo_alias"] = t.get("repo_alias", "default")
            result["status"] = t.get("status", "")
            result["assignee"] = t.get("assignee", "")

            meta = {}
            try:
                meta = json.loads(t.get("metadata") or "{}")
            except Exception:
                meta = {}

            result["stuck_reason"] = meta.get("blocked_reason") or ""
            result["worker_failure_retries"] = int(
                meta.get("worker_failure_retries", 0)
            )
            result["precommit_retries"] = int(meta.get("precommit_retries", 0))
            result["orchestrator_recovery_count"] = int(
                meta.get("orchestrator_recovery_count", 0)
            )
            result["last_worker_failure"] = meta.get("last_worker_failure")
            result["last_precommit_error"] = meta.get("last_precommit_error")

            cur.execute(
                "SELECT author, body, created_at FROM task_comments WHERE task_id = ? ORDER BY created_at DESC LIMIT 5",
                (task_id,),
            )
            result["comments"] = [dict(c) for c in cur.fetchall()]
    except Exception as e:
        _log.warning(
            "Failed querying db in build_stuck_task_context for %s: %s", task_id, e
        )

    # Tail worker log if available
    log_path = _worker_log_path(task_id)
    if log_path.exists():
        try:
            lines = log_path.read_text(encoding="utf-8", errors="replace").splitlines()
            result["worker_log_tail"] = "\n".join(lines[-40:])
        except Exception as e:
            _log.debug("Failed reading worker log for %s: %s", task_id, e)

    return result
