"""Regression tests for dispatcher/scanner.py: gateway-side cron LLM occupancy counting."""

import os
from pathlib import Path

from dispatcher.scanner import _running_cron_llm_jobs

_STUB_SCHEDULER = """
def get_running_job_ids() -> frozenset:
    return {
        "zero-factory-improvement-scanner-board-a",
        "zero-factory-task-queue-check",
        "other-job",
    }
"""


def test_counts_only_scanner_prefix(monkeypatch, tmp_path: Path):
    """Only zero-factory-improvement-scanner-* jobs count; queue-check excluded."""
    fake_agent = tmp_path / "fake-hermes-agent"
    (fake_agent / "cron").mkdir(parents=True)
    (fake_agent / "cron" / "scheduler.py").write_text(_STUB_SCHEDULER, encoding="utf-8")
    monkeypatch.setenv("HERMES_AGENT_DIR", str(fake_agent))
    assert _running_cron_llm_jobs() == 1


def test_returns_zero_when_hermes_agent_dir_missing(monkeypatch, tmp_path: Path):
    """Unavailable gateway dir (no scheduler.py) → 0, no raise."""
    empty = tmp_path / "empty-agent"
    empty.mkdir()
    monkeypatch.setenv("HERMES_AGENT_DIR", str(empty))
    assert _running_cron_llm_jobs() == 0


def test_returns_zero_when_function_missing(monkeypatch, tmp_path: Path):
    """scheduler.py present but without get_running_job_ids → 0, no raise."""
    fake_agent = tmp_path / "partial-hermes-agent"
    (fake_agent / "cron").mkdir(parents=True)
    (fake_agent / "cron" / "scheduler.py").write_text(
        "def tick():\n    return None\n", encoding="utf-8"
    )
    monkeypatch.setenv("HERMES_AGENT_DIR", str(fake_agent))
    assert _running_cron_llm_jobs() == 0


def test_returns_zero_when_get_running_job_ids_raises(monkeypatch, tmp_path: Path):
    """Scheduler state mid-initialization (raising) → 0, no raise."""
    fake_agent = tmp_path / "flaky-hermes-agent"
    (fake_agent / "cron").mkdir(parents=True)
    (fake_agent / "cron" / "scheduler.py").write_text(
        "def get_running_job_ids():\n"
        "    raise RuntimeError('scheduler mid-initialization')\n",
        encoding="utf-8",
    )
    monkeypatch.setenv("HERMES_AGENT_DIR", str(fake_agent))
    assert _running_cron_llm_jobs() == 0


def test_default_hermes_agent_dir_resolves_without_error():
    """With no HERMES_AGENT_DIR override, the function degrades gracefully
    (0 if the gateway dir is absent on this machine, real count otherwise)."""
    saved = os.environ.get("HERMES_AGENT_DIR")
    os.environ.pop("HERMES_AGENT_DIR", None)
    try:
        count = _running_cron_llm_jobs()
    finally:
        if saved is not None:
            os.environ["HERMES_AGENT_DIR"] = saved
    assert isinstance(count, int) and count >= 0
