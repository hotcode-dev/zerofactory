"""Unit tests for dashboard/session_service.py worker-log tailing.

Covers the bounded (64KB) tail read in
``resolve_task_session_progress``: correctness of the last-30-lines tail on
both small and large logs, and that the full file is NOT slurped into memory
for large logs.
"""

from __future__ import annotations

import builtins
from pathlib import Path

import pytest

from dashboard import session_service

TAIL_LIMIT = 64 * 1024


def _make_log(log_path: Path, total_lines: int, line_size: int) -> list[str]:
    """Write a log of ``total_lines`` lines each ~``line_size`` chars; return them."""
    lines = [
        f"line {i:05d} " + "x" * (line_size - len(f"line {i:05d} "))
        for i in range(total_lines)
    ]
    log_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return lines


@pytest.fixture
def hermes_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch):
    """Redirect Path.home() (and os.path.expanduser) to a fake home."""
    fake_home = tmp_path / "home"
    (fake_home / ".hermes" / "logs").mkdir(parents=True)
    monkeypatch.setattr(Path, "home", staticmethod(lambda: fake_home))
    monkeypatch.setenv("HOME", str(fake_home))
    return fake_home


@pytest.fixture
def no_sessions(monkeypatch: pytest.MonkeyPatch):
    """Short-circuit session discovery so the test only exercises log tailing."""
    monkeypatch.setattr(
        session_service, "resolve_task_all_sessions", lambda task, backfill=True: []
    )


def _call_progress(task_id: str) -> dict:
    return session_service.resolve_task_session_progress(
        {"id": task_id, "status": "done"}
    )


def test_log_tail_small_file(hermes_home: Path, no_sessions):
    log_path = hermes_home / ".hermes" / "logs" / "worker_t-small.log"
    lines = _make_log(log_path, total_lines=40, line_size=20)
    tail = _call_progress("t-small")["log_tail"]
    assert tail.endswith("\n".join(lines[-30:]))
    assert len(tail.splitlines()) == 30


def test_log_tail_large_file(hermes_home: Path, no_sessions):
    log_path = hermes_home / ".hermes" / "logs" / "worker_t-big.log"
    lines = _make_log(log_path, total_lines=5000, line_size=60)
    assert log_path.stat().st_size > TAIL_LIMIT
    tail = _call_progress("t-big")["log_tail"]
    assert tail.endswith("\n".join(lines[-30:]))
    assert len(tail.splitlines()) == 30


def test_log_tail_large_file_does_not_read_full_file(
    hermes_home: Path, no_sessions, monkeypatch: pytest.MonkeyPatch
):
    log_path = hermes_home / ".hermes" / "logs" / "worker_t-bounded.log"
    _make_log(log_path, total_lines=5000, line_size=60)
    expected = TAIL_LIMIT  # file is larger than the tail window

    reads: list[int] = []
    real_open = builtins.open

    def spy_open(file, mode="r", *args, **kwargs):
        f = real_open(file, mode, *args, **kwargs)
        if str(file) == str(log_path):
            original_read = f.read

            def tracked_read(size=-1):
                data = original_read(size)
                reads.append(len(data))
                return data

            f.read = tracked_read
        return f

    monkeypatch.setattr(builtins, "open", spy_open)
    tail = _call_progress("t-bounded")["log_tail"]

    assert reads, "expected the log to be opened and read"
    assert sum(reads) <= expected, (
        f"read {sum(reads)} bytes; expected bounded tail <= {expected}"
    )
    assert len(tail.splitlines()) == 30


def test_log_tail_missing_file(hermes_home: Path, no_sessions):
    assert _call_progress("t-missing")["log_tail"] == ""
