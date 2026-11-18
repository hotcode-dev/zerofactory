"""Unit tests for dispatcher.scanner.reap_active_scanners."""

from unittest.mock import MagicMock, patch

from dispatcher import scanner
from dispatcher.config import _active_scanners
from dispatcher.process_manager import ProcessState


def test_reap_active_scanners_keeps_running_scanner(tmp_path):
    """Running scanner processes stay in _active_scanners without raising."""
    _active_scanners.clear()
    proc = MagicMock()
    proc.pid = 424242
    proc.poll.return_value = None
    _active_scanners["board-a"] = proc

    try:
        with (
            patch.object(scanner, "get_hermes_home", return_value=tmp_path),
            patch.object(
                scanner,
                "get_process_exit_code",
                return_value=(ProcessState.RUNNING, None),
            ) as mock_exit,
        ):
            reaped = scanner.reap_active_scanners()

        assert reaped == 0
        assert "board-a" in _active_scanners
        mock_exit.assert_called_once_with("scanner_board-a", 424242)
    finally:
        _active_scanners.clear()


def test_reap_active_scanners_reaps_completed_scanner(tmp_path):
    """Completed scanner processes are popped and their artifacts cleaned up."""
    _active_scanners.clear()
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir(parents=True)
    pid_file = logs_dir / "scanner_board-b.pid"
    pid_file.write_text("515151")

    proc = MagicMock()
    proc.pid = 515151
    proc.poll.return_value = 0
    _active_scanners["board-b"] = proc

    try:
        with (
            patch.object(scanner, "get_hermes_home", return_value=tmp_path),
            patch.object(
                scanner,
                "get_process_exit_code",
                return_value=(ProcessState.COMPLETED, 0),
            ) as mock_exit,
            patch.object(scanner, "cleanup_process_artifacts") as mock_cleanup,
        ):
            reaped = scanner.reap_active_scanners()

        assert reaped == 1
        assert "board-b" not in _active_scanners
        assert not pid_file.exists()
        mock_exit.assert_called_once_with("scanner_board-b", 515151)
        mock_cleanup.assert_called_once_with("scanner_board-b")
    finally:
        _active_scanners.clear()
