"""Tests for cron/store.py: persistence, target resolution, and duplicate pruning."""

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

from cron.store import (
    compute_job_next_run,
    cleanup_duplicate_root_jobs,
    get_target_jobs_files,
    load_jobs_from_file,
    save_jobs_to_file,
)


def test_compute_job_next_run():
    """Verify next run time calculation for interval and cron schedules."""
    # Interval
    interval_sched = {"kind": "interval", "minutes": 30}
    next_run = compute_job_next_run(interval_sched)
    assert next_run is not None
    assert "T" in next_run

    # Cron
    cron_sched = {"kind": "cron", "expr": "0 * * * *"}
    next_run_cron = compute_job_next_run(cron_sched)
    assert next_run_cron is not None

    # Invalid / empty
    assert compute_job_next_run({}) is None
    assert compute_job_next_run(None) is None


def test_load_and_save_jobs_formats():
    """Verify loading from both list format and dict with 'jobs' key."""
    with tempfile.NamedTemporaryFile(suffix=".json") as jf:
        p = Path(jf.name)

        # Dict format
        p.write_text(json.dumps({"jobs": [{"id": "j1"}]}), encoding="utf-8")
        assert load_jobs_from_file(p) == [{"id": "j1"}]

        # List format
        p.write_text(json.dumps([{"id": "j2"}]), encoding="utf-8")
        assert load_jobs_from_file(p) == [{"id": "j2"}]

        # Non-existent or empty
        p_nonexistent = Path(tempfile.gettempdir()) / "nonexistent_jobs.json"
        assert load_jobs_from_file(p_nonexistent) == []

        # Atomic save
        assert save_jobs_to_file(p, [{"id": "j3"}]) is True
        assert load_jobs_from_file(p) == [{"id": "j3"}]


def test_cleanup_duplicate_root_jobs():
    """Verify root jobs file has duplicate Zero Factory jobs pruned."""
    with tempfile.TemporaryDirectory() as td:
        hermes_dir = Path(td) / ".hermes"
        root_jobs = hermes_dir / "cron" / "jobs.json"
        root_jobs.parent.mkdir(parents=True, exist_ok=True)

        initial = [
            {"id": "zero-factory-task-queue-check", "name": "ZF Queue"},
            {"id": "user-custom-job", "name": "User Custom"},
            {"id": "other-zf", "origin": "zerofactory"},
        ]
        save_jobs_to_file(root_jobs, initial)

        with patch("pathlib.Path.home", return_value=Path(td)), \
             patch("os.path.expanduser", side_effect=lambda p: str(hermes_dir) if "~/.hermes" in p else p):
            cleanup_duplicate_root_jobs()

        remaining = load_jobs_from_file(root_jobs)
        assert len(remaining) == 1
        assert remaining[0]["id"] == "user-custom-job"


def test_get_target_jobs_files_resolution():
    """Verify target jobs file resolution precedence."""
    with tempfile.TemporaryDirectory() as td:
        custom_file = Path(td) / "custom_jobs.json"

        # 1. Environment variable override
        with patch.dict(os.environ, {"ZEROFACTORY_CRON_JOBS_FILE": str(custom_file)}):
            targets = get_target_jobs_files()
            assert targets == [custom_file]

        # 2. Test DB safeguard: when ZEROFACTORY_DB points away from default, returns []
        test_db = Path(td) / "test.db"
        with patch.dict(os.environ, {"ZEROFACTORY_DB": str(test_db)}, clear=False):
            os.environ.pop("ZEROFACTORY_CRON_JOBS_FILE", None)
            targets = get_target_jobs_files()
            assert targets == []
