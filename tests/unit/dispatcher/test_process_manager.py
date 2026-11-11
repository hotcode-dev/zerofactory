"""Unit tests for dispatcher/process_manager.py: process group termination and worker cleanup."""

import json
import os
import signal
import sqlite3
import subprocess
from unittest.mock import MagicMock, patch

from dispatcher.config import _active_workers
from dispatcher.process_manager import (
    ProcessState,
    build_shell_wrapper,
    cleanup_process_artifacts,
    get_exit_file_path,
    get_process_exit_code,
    is_pid_alive,
    stop_task_worker,
    terminate_process_group,
    terminate_task_worker,
)


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

    with (
        patch.object(dispatcher.os, "getpgid", return_value=1234),
        patch.object(dispatcher.os, "killpg", side_effect=mock_killpg),
        patch.object(dispatcher.time, "sleep", return_value=None),
    ):
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

    with patch("dispatcher.process_manager.terminate_worker_process") as mock_term:
        stop_task_worker("task-test-1")
        assert "task-test-1" not in _active_workers
        mock_term.assert_called_once_with(mock_proc, 4321)


def test_stop_task_worker_falls_back_to_db_metadata():
    """When not in memory, reads worker_pid from tasks table metadata."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, metadata TEXT)")
    conn.execute(
        "INSERT INTO tasks VALUES ('t-meta', ?)", (json.dumps({"worker_pid": 8888}),)
    )
    conn.commit()

    with patch("dispatcher.process_manager.terminate_worker_process") as mock_term:
        stop_task_worker("t-meta", cursor=conn.cursor())
        mock_term.assert_called_once_with(None, 8888)


def test_build_shell_wrapper():
    """Verify build_shell_wrapper sets up POSIX script, shift, and exit code trapping."""
    cmd = ["hermes", "-p", "zf-builder", "chat"]
    exit_prefix = "/tmp/test_exit"
    wrapped = build_shell_wrapper(cmd, exit_prefix)

    assert wrapped[0] == "sh"
    assert wrapped[1] == "-c"
    assert 'prefix="$1"; shift;' in wrapped[2]
    assert "printf" in wrapped[2]
    assert "${prefix}.exit" in wrapped[2]
    assert wrapped[3] == "zf-runner"
    assert wrapped[4] == exit_prefix
    assert wrapped[5:] == cmd


def test_get_process_exit_code_completed(tmp_path):
    """Verify COMPLETED status when .exit file exists."""
    task_id = "task-completed-123"
    exit_file = tmp_path / f"worker_{task_id}.exit"
    exit_file.write_text("0\n")

    with patch("dispatcher.process_manager.get_exit_file_path", return_value=exit_file):
        state, rc = get_process_exit_code(task_id, pid=99999)
        assert state == ProcessState.COMPLETED
        assert rc == 0

    exit_file.write_text("143\n")
    with patch("dispatcher.process_manager.get_exit_file_path", return_value=exit_file):
        state, rc = get_process_exit_code(task_id, pid=99999)
        assert state == ProcessState.COMPLETED
        assert rc == 143


def test_get_process_exit_code_running(tmp_path):
    """Verify RUNNING status when .exit file absent and PID is alive."""
    task_id = "task-running-123"
    exit_file = tmp_path / f"worker_{task_id}.exit"

    with (
        patch("dispatcher.process_manager.get_exit_file_path", return_value=exit_file),
        patch("dispatcher.process_manager.is_pid_alive", return_value=True),
        patch("pathlib.Path.exists", return_value=False),
    ):
        state, rc = get_process_exit_code(task_id, pid=12345)
        assert state == ProcessState.RUNNING
        assert rc is None


def test_get_process_exit_code_crashed(tmp_path):
    """Verify CRASHED status when .exit file absent and PID is dead."""
    task_id = "task-crashed-123"
    exit_file = tmp_path / f"worker_{task_id}.exit"

    with (
        patch("dispatcher.process_manager.get_exit_file_path", return_value=exit_file),
        patch("dispatcher.process_manager.is_pid_alive", return_value=False),
    ):
        state, rc = get_process_exit_code(task_id, pid=12345)
        assert state == ProcessState.CRASHED
        assert rc == -1


def test_cleanup_process_artifacts(tmp_path):
    """Verify cleanup_process_artifacts removes both .exit and .exit.tmp."""
    task_id = "task-cleanup-123"
    exit_file = tmp_path / f"worker_{task_id}.exit"
    tmp_file = tmp_path / f"worker_{task_id}.exit.tmp"
    exit_file.write_text("0")
    tmp_file.write_text("0")

    with patch("pathlib.Path.home", return_value=tmp_path.parent):
        logs_dir = tmp_path.parent / ".hermes" / "logs"
        logs_dir.mkdir(parents=True, exist_ok=True)
        (logs_dir / f"worker_{task_id}.exit").write_text("0")
        (logs_dir / f"worker_{task_id}.exit.tmp").write_text("0")

        cleanup_process_artifacts(task_id)
        assert not (logs_dir / f"worker_{task_id}.exit").exists()
        assert not (logs_dir / f"worker_{task_id}.exit.tmp").exists()


def test_terminate_task_worker():
    """Verify terminate_task_worker calls process group termination and artifact cleanup."""
    with (
        patch("dispatcher.process_manager.is_pid_alive", return_value=True),
        patch("dispatcher.process_manager.terminate_process_group") as mock_term,
        patch("dispatcher.process_manager.cleanup_process_artifacts") as mock_cleanup,
    ):
        terminate_task_worker("task-xyz", 9876)
        mock_term.assert_called_once_with(None, 9876)
        mock_cleanup.assert_called_once_with("task-xyz")
