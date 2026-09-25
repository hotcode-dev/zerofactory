"""Unit tests for cron/manager.py."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cron.store import load_jobs_from_file, save_jobs_to_file
from cron.manager import (
    ensure_builtin_cron_jobs,
    list_builtin_jobs,
    prune_board_cron_job,
    reset_builtin_job,
    toggle_builtin_job,
    update_builtin_job,
)


class TestCronManagerUnit(unittest.TestCase):
    """Test job persistence, orphan pruning, board deletion cleanup, and field update semantics."""

    def test_load_and_save_jobs_to_file_atomic(self):
        """save_jobs_to_file writes atomically and load_jobs_from_file reads it back."""
        with tempfile.TemporaryDirectory() as td:
            jobs_file = Path(td) / "jobs.json"
            sample = [
                {"id": "job-1", "name": "First Job", "enabled": True},
                {"id": "job-2", "name": "Second Job", "enabled": False},
            ]
            save_jobs_to_file(jobs_file, sample)
            self.assertTrue(jobs_file.exists())
            loaded = load_jobs_from_file(jobs_file)
            self.assertEqual(len(loaded), 2)
            self.assertEqual(loaded[0]["id"], "job-1")
            self.assertEqual(loaded[1]["id"], "job-2")

    def test_ensure_builtin_cron_jobs_prunes_orphans(self):
        """ensure_builtin_cron_jobs prunes orphan board scanners from jobs.json."""
        with tempfile.TemporaryDirectory() as td:
            jobs_file = Path(td) / "jobs.json"
            initial_jobs = [
                {"id": "zero-factory-task-queue-check", "origin": "zerofactory"},
                {"id": "zero-factory-improvement-scanner-active-board", "origin": "zerofactory"},
                {"id": "zero-factory-improvement-scanner-orphan-board", "origin": "zerofactory"},
                {"id": "user-custom-cron-job"},
            ]
            save_jobs_to_file(jobs_file, initial_jobs)

            db_path = Path(td) / "test.db"
            with sqlite3.connect(str(db_path)) as conn:
                conn.execute(
                    "CREATE TABLE boards (slug TEXT PRIMARY KEY, description TEXT, git_url TEXT, created_at REAL, updated_at REAL)"
                )
                conn.execute(
                    "INSERT INTO boards (slug, description, git_url, created_at, updated_at) VALUES ('active-board', 'Main', '', 1, 1)"
                )
                conn.commit()

            with patch.dict(os.environ, {
                "ZEROFACTORY_DB": str(db_path),
                "ZEROFACTORY_CRON_JOBS_FILE": str(jobs_file),
            }):
                os.environ.pop("ZEROFACTORY_SKIP_CRON_SYNC", None)
                try:
                    ensure_builtin_cron_jobs()
                finally:
                    os.environ["ZEROFACTORY_SKIP_CRON_SYNC"] = "1"

            remaining = load_jobs_from_file(jobs_file)
            remaining_ids = [j["id"] for j in remaining]
            self.assertIn("zero-factory-task-queue-check", remaining_ids)
            self.assertIn("zero-factory-improvement-scanner-active-board", remaining_ids)
            self.assertIn("user-custom-cron-job", remaining_ids)
            self.assertNotIn("zero-factory-improvement-scanner-orphan-board", remaining_ids)

    def test_prune_board_cron_job(self):
        """prune_board_cron_job removes only the specified board's scanner job."""
        with tempfile.TemporaryDirectory() as td:
            jobs_file = Path(td) / "jobs.json"
            initial_jobs = [
                {"id": "zero-factory-improvement-scanner-board-to-delete", "origin": "zerofactory"},
                {"id": "zero-factory-improvement-scanner-other-board", "origin": "zerofactory"},
                {"id": "zero-factory-task-queue-check", "origin": "zerofactory"},
            ]
            save_jobs_to_file(jobs_file, initial_jobs)

            with patch.dict(os.environ, {"ZEROFACTORY_CRON_JOBS_FILE": str(jobs_file)}):
                prune_board_cron_job("board-to-delete")

            remaining = load_jobs_from_file(jobs_file)
            remaining_ids = [j["id"] for j in remaining]
            self.assertNotIn("zero-factory-improvement-scanner-board-to-delete", remaining_ids)
            self.assertIn("zero-factory-improvement-scanner-other-board", remaining_ids)
            self.assertIn("zero-factory-task-queue-check", remaining_ids)

    def test_update_builtin_job_semantics(self):
        """Updating job fields flags custom_config and survives sync until reset."""
        with tempfile.TemporaryDirectory() as td:
            jobs_file = Path(td) / "jobs.json"
            job_id = "zero-factory-task-queue-check"
            initial_jobs = [
                {
                    "id": job_id,
                    "name": "Zero Factory task queue check",
                    "schedule": {"kind": "interval", "minutes": 120, "display": "every 120m"},
                    "enabled": True,
                    "state": "scheduled",
                    "origin": "zerofactory",
                }
            ]
            save_jobs_to_file(jobs_file, initial_jobs)

            orig_override = os.environ.get("ZEROFACTORY_CRON_JOBS_FILE")
            os.environ["ZEROFACTORY_CRON_JOBS_FILE"] = str(jobs_file)
            try:
                # 1. Update minutes
                res = update_builtin_job(job_id, {"minutes": 60})
                self.assertTrue(res["ok"])
                jobs = load_jobs_from_file(jobs_file)
                self.assertEqual(jobs[0]["schedule"]["minutes"], 60)
                self.assertTrue(jobs[0]["custom_config"])

                # 2. Toggle enabled to False -> state=paused
                res_toggle = update_builtin_job(job_id, {"enabled": False})
                self.assertTrue(res_toggle["ok"])
                jobs_toggle = load_jobs_from_file(jobs_file)
                self.assertFalse(jobs_toggle[0]["enabled"])
                self.assertEqual(jobs_toggle[0]["state"], "paused")
                self.assertIsNotNone(jobs_toggle[0]["paused_at"])

                # 3. Reset job restores canonical definitions
                res_reset = reset_builtin_job(job_id)
                self.assertTrue(res_reset["ok"])
                jobs_reset = load_jobs_from_file(jobs_file)
                self.assertEqual(jobs_reset[0]["schedule"]["minutes"], 120)
                self.assertTrue(jobs_reset[0]["enabled"])
                self.assertEqual(jobs_reset[0]["state"], "scheduled")
                self.assertFalse(jobs_reset[0].get("custom_config", False))
            finally:
                if orig_override is not None:
                    os.environ["ZEROFACTORY_CRON_JOBS_FILE"] = orig_override
                else:
                    os.environ.pop("ZEROFACTORY_CRON_JOBS_FILE", None)


if __name__ == "__main__":
    unittest.main()
