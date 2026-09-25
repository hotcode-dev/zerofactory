"""Unit tests for dispatcher/process_manager.py: process group termination and worker cleanup."""

import json
import os
import signal
import sqlite3
import subprocess
import time
from unittest.mock import patch, MagicMock
import pytest

from dispatcher.process_manager import (
    is_pid_alive,
    terminate_process_group,
    terminate_worker_process,
    stop_task_worker,
)
from dispatcher.config import _active_workers


def test_is_pid_alive():
    """Verify alive check for valid, non-existent, and invalid PIDs."""
    # Invalid PIDs
    assert is_pid_alive(None) is False
    assert is_pid_alive(0) is False
    assert is_pid_alive(-1) is False
    assert is_pid_alive("invalid") is False  # type: ignore

    # Current process PID must be alive
    assert is_pid_alive(os.getpid()) is True

    # High non-existent PID
    assert is_pid_alive(9999999) is False


def test_terminate_process_group_with_dead_group():
    """Calling terminate_process_group on dead or non-existent group does not raise."""
    # Should safely return without error
    terminate_process_group(None, 9999999, grace=0.1)


def test_terminate_process_group_kills_session_group():
    """Verify SIGTERM followed by SIGKILL to the process group."""
    mock_proc = MagicMock()
    mock_proc.pid = 1234
    mock_proc.wait.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=0.1)

    calls = []

    def mock_killpg(pgid, sig):
        calls.append((pgid, sig))

    import dispatcher
    with patch.object(dispatcher.os, "getpgid", return_value=1234), \
         patch.object(dispatcher.os, "killpg", side_effect=mock_killpg), \
         patch.object(dispatcher.time, "sleep", return_value=None):
        terminate_process_group(mock_proc, 1234, grace=0.1)

    # Pre-flight probe (signal 0), then SIGTERM, then SIGKILL
    assert (1234, 0) in calls
    assert (1234, signal.SIGTERM) in calls
    assert (1234, signal.SIGKILL) in calls


def test_stop_task_worker_in_memory_and_db():
    """Verify stop_task_worker pops from _active_workers and terminates."""
    mock_proc = MagicMock()
    mock_proc.pid = 4321
    _active_workers["task-test-1"] = mock_proc

    import dispatcher
    with patch.object(dispatcher, "terminate_worker_process") as mock_term:
        stop_task_worker("task-test-1")
        assert "task-test-1" not in _active_workers
        mock_term.assert_called_once_with(mock_proc, 4321)


def test_stop_task_worker_falls_back_to_db_metadata():
    """When not in memory, reads worker_pid from tasks table metadata."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, metadata TEXT)")
    conn.execute(
        "INSERT INTO tasks VALUES ('t-meta', ?)",
        (json.dumps({"worker_pid": 8888}),)
    )
    conn.commit()

    import dispatcher
    with patch.object(dispatcher, "terminate_worker_process") as mock_term:
        stop_task_worker("t-meta", cursor=conn.cursor())
        mock_term.assert_called_once_with(None, 8888)
