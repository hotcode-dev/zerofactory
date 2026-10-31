"""Unit tests for dispatcher/reaper.py: stuck state computation, active worker reaping, and recovery."""

import json
import os
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

from dispatcher.reaper import (
    _compute_stuck_state,
    _mark_task_session_ended,
    reap_active_workers,
    reap_stuck_tasks,
)


def test_compute_stuck_state_dead_worker(tmp_path: Path):
    """Dead worker process is immediately flagged stuck."""
    log_file = tmp_path / "worker.log"
    is_stuck, reason, idle = _compute_stuck_state(
        now=1000,
        started_at=900,
        log_path=log_file,
        task_timeout=3600,
        inactivity_timeout=600,
        is_dead=True,
        pid=12345,
    )
    assert is_stuck is True
    assert "dead/not found" in reason


def test_compute_stuck_state_exceeded_task_timeout(tmp_path: Path):
    """Worker running beyond task_timeout is flagged stuck."""
    log_file = tmp_path / "worker.log"
    is_stuck, reason, idle = _compute_stuck_state(
        now=5000,
        started_at=1000,
        log_path=log_file,
        task_timeout=3600,
        inactivity_timeout=600,
        is_dead=False,
    )
    assert is_stuck is True
    assert "Exceeded running timeout" in reason


def test_compute_stuck_state_inactive_log(tmp_path: Path):
    """Worker with mtime older than inactivity_timeout is flagged stuck."""
    log_file = tmp_path / "worker.log"
    log_file.write_text("progress\n")
    # Set log mtime to 800s ago
    now = 2000
    os.utime(str(log_file), (1200, 1200))

    is_stuck, reason, idle = _compute_stuck_state(
        now=now,
        started_at=1000,
        log_path=log_file,
        task_timeout=3600,
        inactivity_timeout=600,
        is_dead=False,
    )
    assert is_stuck is True
    assert "inactive with no updates" in reason
    assert idle == 800


def test_compute_stuck_state_active_healthy(tmp_path: Path):
    """Worker with recent log activity is healthy and not stuck."""
    log_file = tmp_path / "worker.log"
    log_file.write_text("working\n")
    now = 1200
    os.utime(str(log_file), (1150, 1150))

    is_stuck, reason, idle = _compute_stuck_state(
        now=now,
        started_at=1000,
        log_path=log_file,
        task_timeout=3600,
        inactivity_timeout=600,
        is_dead=False,
    )
    assert is_stuck is False
    assert reason is None
    assert idle == 50


def test_mark_task_session_ended():
    """Helper marks ongoing sessions with terminal status and timestamp."""
    meta = {
        "sessions": [
            {"session_id": "s1", "status": "ongoing", "started_at": 100},
            {
                "session_id": "s0",
                "status": "completed",
                "started_at": 50,
                "ended_at": 90,
            },
        ]
    }
    updated = _mark_task_session_ended(meta, now=200, final_status="aborted")
    s1 = next(s for s in updated["sessions"] if s["session_id"] == "s1")
    s0 = next(s for s in updated["sessions"] if s["session_id"] == "s0")

    assert s1["status"] == "aborted"
    assert s1["ended_at"] == 200
    assert s0["status"] == "completed"
    assert s0["ended_at"] == 90


def test_reap_active_workers_transitions_stuck_task(tmp_path: Path):
    """Stuck running task is stopped and queued for retry (claimable 'todo')
    while its failure budget lasts."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            title TEXT,
            status TEXT,
            assignee TEXT,
            metadata TEXT,
            updated_at INTEGER,
            created_at INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE task_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            actor TEXT,
            action TEXT,
            details TEXT,
            created_at INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE task_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            author TEXT,
            body TEXT,
            created_at INTEGER
        )
        """
    )

    now = 5000
    started_at = now - 4000  # Exceeded default timeout (3600s)
    meta = json.dumps(
        {
            "started_at": started_at,
            "worker_pid": 1111,
            "sessions": [
                {"session_id": "s1", "status": "ongoing", "started_at": started_at}
            ],
        }
    )
    conn.execute(
        "INSERT INTO tasks VALUES ('t-stuck', 'Stuck Task', 'running', 'zf-builder', ?, ?, ?)",
        (meta, started_at, started_at),
    )
    conn.commit()

    from dispatcher.config import _active_workers

    mock_proc = MagicMock()
    mock_proc.pid = 1111
    mock_proc.poll.return_value = None
    _active_workers["t-stuck"] = mock_proc

    import dispatcher

    with patch.object(dispatcher, "terminate_worker_process") as mock_term:
        reaped = reap_active_workers(conn.cursor(), now=now)
        conn.commit()

    assert reaped == 1
    mock_term.assert_called_once_with(mock_proc, 1111)

    row = conn.execute(
        "SELECT status, metadata FROM tasks WHERE id = 't-stuck'"
    ).fetchone()
    assert row["status"] == "todo"
    saved_meta = json.loads(row["metadata"])
    assert "blocked_reason" in saved_meta
    assert saved_meta["worker_failure_retries"] == 1
    assert not saved_meta.get("permanently_blocked")

    comments = conn.execute(
        "SELECT body FROM task_comments WHERE task_id = 't-stuck'"
    ).fetchall()
    assert any(c[0].startswith("Retrying:") for c in comments)


def test_reap_active_workers_parks_exhausted_stuck_task(tmp_path: Path):
    """Once the failure budget is exhausted, the stuck task is parked in
    'blocked' for a human (permanently_blocked)."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            title TEXT,
            status TEXT,
            assignee TEXT,
            metadata TEXT,
            updated_at INTEGER,
            created_at INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE task_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            actor TEXT,
            action TEXT,
            details TEXT,
            created_at INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE task_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            author TEXT,
            body TEXT,
            created_at INTEGER
        )
        """
    )

    now = 5000
    started_at = now - 4000  # Exceeded default timeout (3600s)
    meta = json.dumps(
        {
            "started_at": started_at,
            "worker_pid": 2222,
            "worker_failure_retries": 2,
            "sessions": [
                {"session_id": "s1", "status": "ongoing", "started_at": started_at}
            ],
        }
    )
    conn.execute(
        "INSERT INTO tasks VALUES ('t-stuck2', 'Stuck Task', 'running', 'zf-builder', ?, ?, ?)",
        (meta, started_at, started_at),
    )
    conn.commit()

    from dispatcher.config import _active_workers

    mock_proc = MagicMock()
    mock_proc.pid = 2222
    mock_proc.poll.return_value = None
    _active_workers["t-stuck2"] = mock_proc

    import dispatcher

    with patch.object(dispatcher, "terminate_worker_process") as mock_term:
        reaped = reap_active_workers(conn.cursor(), now=now)
        conn.commit()

    assert reaped == 1
    mock_term.assert_called_once_with(mock_proc, 2222)

    row = conn.execute(
        "SELECT status, assignee, metadata FROM tasks WHERE id = 't-stuck2'"
    ).fetchone()
    assert row["status"] == "blocked"
    assert row["assignee"] == "zf-builder"
    saved_meta = json.loads(row["metadata"])
    assert saved_meta["permanently_blocked"] is True
    assert saved_meta["worker_failure_retries"] == 3
    assert saved_meta["blocked_reason_type"] == "stuck"


def _spawn_grace_conn(task_id: str, meta: dict, now: int) -> sqlite3.Connection:
    """Minimal running-task harness for orphan-recovery tests."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            title TEXT,
            status TEXT,
            assignee TEXT,
            metadata TEXT,
            updated_at INTEGER,
            created_at INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE task_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            actor TEXT,
            action TEXT,
            details TEXT,
            created_at INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE task_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            author TEXT,
            body TEXT,
            created_at INTEGER
        )
        """
    )
    conn.execute(
        "INSERT INTO tasks VALUES (?, 'Spawning Task', 'running', 'zf-builder', ?, ?, ?)",
        (task_id, json.dumps(meta), now, now),
    )
    conn.commit()
    return conn


def test_reaper_respects_spawn_grace_window():
    """A freshly-claimed task whose worker is still spawning is NOT recovered.

    Regression for the zf-hdz-4dc03cee duplicate-worker race: orphan recovery
    fired mid-spawn (age 33s) and double-dispatched the builder onto one
    worktree. The claim stamps `spawning_at`; recovery must wait out the grace.
    """
    now = 5000
    meta = {"spawning_at": now - 33}
    conn = _spawn_grace_conn("t-spawning", meta, now)

    reaped = reap_active_workers(conn.cursor(), now=now)
    conn.commit()

    assert reaped == 0
    row = conn.execute("SELECT status FROM tasks WHERE id = 't-spawning'").fetchone()
    assert row["status"] == "running"
    activity = conn.execute(
        "SELECT COUNT(*) FROM task_activity WHERE task_id = 't-spawning' AND action = 'worker_recovered'"
    ).fetchone()[0]
    assert activity == 0


def test_reaper_recovers_orphan_after_spawn_grace_expires():
    """Once the grace window passes with no worker/session registered, the task
    is genuinely orphaned and is recovered to todo."""
    now = 5000
    meta = {"spawning_at": now - 400}  # grace default 180s
    conn = _spawn_grace_conn("t-orphan", meta, now)

    reaped = reap_active_workers(conn.cursor(), now=now)
    conn.commit()

    assert reaped == 1
    row = conn.execute("SELECT status FROM tasks WHERE id = 't-orphan'").fetchone()
    assert row["status"] == "todo"
    activity = conn.execute(
        "SELECT COUNT(*) FROM task_activity WHERE task_id = 't-orphan' AND action = 'worker_recovered'"
    ).fetchone()[0]
    assert activity == 1


def test_reaper_spawn_grace_env_override(monkeypatch):
    """ZEROFACTORY_SPAWN_GRACE_SECONDS tunes the grace window."""
    import dispatcher

    monkeypatch.setenv("ZEROFACTORY_SPAWN_GRACE_SECONDS", "600")
    assert dispatcher.get_spawn_grace_seconds() == 600

    now = 5000
    meta = {"spawning_at": now - 400}  # within the 600s override
    conn = _spawn_grace_conn("t-long-grace", meta, now)
    reaped = reap_active_workers(conn.cursor(), now=now)
    conn.commit()

    assert reaped == 0


def test_get_task_timeout_seconds_db_fallback(tmp_path: Path, monkeypatch):
    """get_task_timeout_seconds reads settings table from DB even without explicit conn."""
    from dispatcher.config import (
        get_task_timeout_seconds,
        get_inactivity_timeout_seconds,
    )
    import sqlite3

    db_file = tmp_path / "test_zerofactory.db"
    monkeypatch.setenv("ZEROFACTORY_DB", str(db_file))
    monkeypatch.delenv("ZEROFACTORY_TASK_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("ZEROFACTORY_INACTIVITY_TIMEOUT_SECONDS", raising=False)

    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
    conn.execute("INSERT INTO settings VALUES ('task_timeout_seconds', '7200')")
    conn.execute("INSERT INTO settings VALUES ('inactivity_timeout_seconds', '1800')")
    conn.commit()

    # Call with conn
    assert get_task_timeout_seconds(conn) == 7200
    assert get_inactivity_timeout_seconds(conn) == 1800

    # Call without conn (should open DB automatically)
    assert get_task_timeout_seconds() == 7200
    assert get_inactivity_timeout_seconds() == 1800

    # Env var override takes precedence
    monkeypatch.setenv("ZEROFACTORY_TASK_TIMEOUT_SECONDS", "9999")
    assert get_task_timeout_seconds() == 9999
    conn.close()


def test_check_stuck_tasks_all_4_states(tmp_path: Path, monkeypatch):
    """check_stuck_tasks accurately identifies the 4 distinct stuck states."""
    import sqlite3
    import json
    from dispatcher.reaper import check_stuck_tasks, build_stuck_task_context

    db_file = tmp_path / "test_stuck_states.db"
    monkeypatch.setenv("ZEROFACTORY_DB", str(db_file))

    conn = sqlite3.connect(str(db_file))
    conn.execute("""
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            title TEXT,
            status TEXT,
            assignee TEXT,
            workspace_path TEXT,
            metadata TEXT,
            created_at INTEGER,
            updated_at INTEGER,
            board_slug TEXT,
            repo_alias TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE task_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            author TEXT,
            body TEXT,
            created_at INTEGER
        )
    """)

    now = 10000

    # State 1: Dead worker / orphan running task
    conn.execute(
        "INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "t-orphan",
            "Orphan Task",
            "running",
            "zf-builder",
            None,
            json.dumps({"sessions": []}),
            now - 500,
            now - 500,
            "default",
            "api",
        ),
    )

    # State 2: Worker timeout / inactivity in running
    conn.execute(
        "INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "t-timeout",
            "Timeout Task",
            "running",
            "zf-builder",
            None,
            json.dumps({"worker_pid": 999999, "started_at": now - 7200}),
            now - 7200,
            now - 7200,
            "default",
            "api",
        ),
    )

    # State 3: Stuck PR packaging
    conn.execute(
        "INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "t-packaging",
            "Packaging Hang",
            "running",
            "zf-builder",
            None,
            json.dumps({"awaiting_pr": True, "started_at": now - 4000}),
            now - 4000,
            now - 4000,
            "default",
            "api",
        ),
    )

    # State 4: Failure exhausted in blocked
    conn.execute(
        "INSERT INTO tasks VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (
            "t-exhausted",
            "Exhausted Task",
            "blocked",
            "human",
            None,
            json.dumps(
                {
                    "blocked_reason_type": "stuck",
                    "blocked_reason": "Deterministic precommit failed after 3 attempts",
                    "precommit_retries": 3,
                    "orchestrator_recovery_count": 0,
                    "last_precommit_error": "SyntaxError on line 42",
                }
            ),
            now - 1000,
            now - 1000,
            "default",
            "api",
        ),
    )
    conn.commit()

    # 1. Calling with include_blocked=False returns only running stuck tasks
    running_stuck = check_stuck_tasks(
        conn.cursor(), db_path=db_file, include_blocked=False
    )
    stuck_ids = {t["id"]: t for t in running_stuck if t.get("is_stuck")}
    assert "t-orphan" in stuck_ids
    assert stuck_ids["t-orphan"]["stuck_state"] == "dead_worker"
    assert "t-timeout" in stuck_ids
    assert stuck_ids["t-timeout"]["stuck_state"] in (
        "dead_worker",
        "timeout_inactivity",
    )
    assert "t-packaging" in stuck_ids
    assert stuck_ids["t-packaging"]["stuck_state"] == "stuck_packaging"
    assert "t-exhausted" not in stuck_ids

    # 2. Calling with include_blocked=True includes State 4
    all_stuck = check_stuck_tasks(conn.cursor(), db_path=db_file, include_blocked=True)
    all_stuck_map = {t["id"]: t for t in all_stuck if t.get("is_stuck")}
    assert "t-exhausted" in all_stuck_map
    assert all_stuck_map["t-exhausted"]["stuck_state"] == "failure_exhausted"

    # 3. Test build_stuck_task_context
    ctx = build_stuck_task_context("t-exhausted", db_path=db_file)
    assert ctx["id"] == "t-exhausted"
    assert ctx["precommit_retries"] == 3
    assert "SyntaxError" in ctx["last_precommit_error"]

    conn.close()


def test_reap_active_workers_exit0_clears_worker_pid(tmp_path: Path):
    """Exit-0 builder transition moves the task to the deterministic
    packaging phase and clears the live worker identity (worker_pid /
    session_id / started_at) so the dead-PID branch has nothing to misfire on.
    Regression for the GitHub #84 3-day PR-packaging respawn loop."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            title TEXT,
            status TEXT,
            assignee TEXT,
            metadata TEXT,
            updated_at INTEGER,
            created_at INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE task_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            actor TEXT,
            action TEXT,
            details TEXT,
            created_at INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE task_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            author TEXT,
            body TEXT,
            created_at INTEGER
        )
        """
    )

    now = 5000
    meta = json.dumps(
        {
            "worker_pid": 4242,
            "session_id": "sess-abc",
            "started_at": now - 100,
            "sessions": [
                {
                    "session_id": "sess-abc",
                    "status": "ongoing",
                    "started_at": now - 100,
                }
            ],
        }
    )
    conn.execute(
        "INSERT INTO tasks VALUES ('t-exit0', 'Done Task', 'running', 'zf-builder', ?, ?, ?)",
        (meta, now - 100, now - 100),
    )
    conn.commit()

    from dispatcher.config import _active_workers

    mock_proc = MagicMock()
    mock_proc.pid = 4242
    mock_proc.poll.return_value = 0
    _active_workers["t-exit0"] = mock_proc
    try:
        reaped = reap_active_workers(conn.cursor(), now=now)
        conn.commit()
    finally:
        _active_workers.pop("t-exit0", None)

    assert reaped == 1
    row = conn.execute(
        "SELECT status, metadata FROM tasks WHERE id = 't-exit0'"
    ).fetchone()
    assert row["status"] == "running"
    saved_meta = json.loads(row["metadata"])
    assert saved_meta.get("awaiting_pr") is True
    assert "worker_pid" not in saved_meta
    assert "session_id" not in saved_meta
    assert "started_at" not in saved_meta
    assert saved_meta.get("worker_failure_retries") in (None, 0)


def test_reaper_does_not_reap_awaiting_pr_stale_pid(tmp_path: Path):
    """A running task in the deterministic packaging phase (awaiting_pr) that
    still carries a stale worker_pid is left alone: no worker_lost activity,
    no failure-budget increment, no route to todo/blocked. Regression for
    GitHub #84 (dead-PID branch misfiring on the packaging phase)."""
    conn = _spawn_grace_conn(
        "t-packaged",
        {
            "awaiting_pr": True,
            "worker_pid": 999999,  # stale; no live _active_workers entry
            "worker_failure_retries": 1,
        },
        now=5000,
    )

    reaped = reap_active_workers(conn.cursor(), now=5000)
    conn.commit()

    assert reaped == 0
    row = conn.execute(
        "SELECT status, metadata FROM tasks WHERE id = 't-packaged'"
    ).fetchone()
    assert row["status"] == "running"
    saved_meta = json.loads(row["metadata"])
    assert saved_meta.get("worker_failure_retries") == 1
    lost = conn.execute(
        "SELECT COUNT(*) FROM task_activity "
        "WHERE task_id = 't-packaged' AND action = 'worker_lost'"
    ).fetchone()[0]
    assert lost == 0


def _reaper_db_file(tmp_path: Path) -> Path:
    """Minimal on-disk DB for reap_stuck_tasks (no stuck tasks)."""
    db_file = tmp_path / "reaper.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            title TEXT,
            status TEXT,
            assignee TEXT,
            workspace_path TEXT,
            metadata TEXT,
            created_at INTEGER,
            updated_at INTEGER,
            board_slug TEXT,
            repo_alias TEXT
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE task_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            actor TEXT,
            action TEXT,
            details TEXT,
            created_at INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE task_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT,
            author TEXT,
            body TEXT,
            created_at INTEGER
        )
        """
    )
    conn.commit()
    conn.close()
    return db_file


def test_reap_stuck_tasks_locked_db_returns_not_ok(tmp_path: Path, monkeypatch):
    """A 'database is locked' OperationalError on the first connect attempt is
    retried with backoff; the call never propagates OperationalError — it
    either succeeds after backoff or returns a clean failure dict. Regression
    for GitHub #84 (watchdog tick aborted on a WAL-locked kanban.db)."""
    import dispatcher.reaper as reaper_mod

    db_file = _reaper_db_file(tmp_path)

    real_connect = sqlite3.connect
    connect_calls = {"n": 0}

    def flaky_connect(*args, **kwargs):
        connect_calls["n"] += 1
        if connect_calls["n"] == 1:
            raise sqlite3.OperationalError("database is locked")
        return real_connect(*args, **kwargs)

    monkeypatch.setattr(reaper_mod.sqlite3, "connect", flaky_connect)
    sleeps = []
    monkeypatch.setattr(reaper_mod.time, "sleep", lambda s: sleeps.append(s))

    res = reap_stuck_tasks(db_path=db_file)

    # No exception propagated; DB unlock was waited out and reaping succeeded.
    assert connect_calls["n"] == 2
    assert sleeps, "expected a backoff sleep between attempts"
    assert res.get("ok") is True
    assert res.get("reaped_count") == 0
    assert res.get("reaped_tasks") == []
    assert res.get("reaped") == []


def test_reap_stuck_tasks_persistently_locked_db_fails_clean(
    tmp_path: Path, monkeypatch
):
    """When the DB stays locked past the retry budget, reap_stuck_tasks logs a
    warning and returns a clean failure dict instead of raising."""
    import dispatcher.reaper as reaper_mod

    db_file = _reaper_db_file(tmp_path)

    def always_locked(*args, **kwargs):
        raise sqlite3.OperationalError("database is locked")

    monkeypatch.setattr(reaper_mod.sqlite3, "connect", always_locked)
    monkeypatch.setattr(reaper_mod.time, "sleep", lambda s: None)
    # Advance the monotonic clock past the 30s budget on each poll so the
    # retry loop exhausts quickly instead of looping forever.
    clock = [0.0]

    def fake_monotonic():
        clock[0] += 10.0
        return clock[0]

    monkeypatch.setattr(reaper_mod.time, "monotonic", fake_monotonic)

    res = reap_stuck_tasks(db_path=db_file)

    assert res.get("ok") is False
    assert res.get("reason") == "database locked"
    assert res.get("reaped_count") == 0
    assert res.get("reaped_tasks") == []
    assert res.get("reaped") == []
