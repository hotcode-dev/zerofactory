"""Unit tests for dispatcher/reaper.py: stuck state computation, active worker reaping, and recovery."""

import json
import os
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from dispatcher.reaper import (
    _compute_stuck_state,
    _mark_task_session_ended,
    reap_active_workers,
    check_stuck_tasks,
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
            {"session_id": "s0", "status": "completed", "started_at": 50, "ended_at": 90},
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
    """reap_active_workers identifies stuck running task, stops worker, and blocks task."""
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
    meta = json.dumps({
        "started_at": started_at,
        "worker_pid": 1111,
        "sessions": [{"session_id": "s1", "status": "ongoing", "started_at": started_at}],
    })
    conn.execute(
        "INSERT INTO tasks VALUES ('t-stuck', 'Stuck Task', 'running', 'zf-builder', ?, ?, ?)",
        (meta, started_at, started_at)
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

    row = conn.execute("SELECT status, metadata FROM tasks WHERE id = 't-stuck'").fetchone()
    assert row["status"] == "blocked"
    saved_meta = json.loads(row["metadata"])
    assert "blocked_reason" in saved_meta
