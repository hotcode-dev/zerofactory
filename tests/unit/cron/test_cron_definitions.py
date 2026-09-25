"""Unit tests for cron/definitions.py."""

from __future__ import annotations

import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from cron.definitions import (
    CORE_CRON_JOBS,
    build_board_scanner_prompt,
    get_all_builtin_cron_jobs,
    resolve_board_repo_path,
)


class TestCronDefinitionsUnit(unittest.TestCase):
    """Test core cron definitions and dynamic board scanner generation."""

    def test_core_cron_jobs_schema(self):
        """Queue watchdog operates in No-Agent mode with correct script."""
        queue_job = CORE_CRON_JOBS["zero-factory-task-queue-check"]
        self.assertTrue(queue_job["no_agent"])
        self.assertEqual(queue_job["script"], "zf_queue_watchdog.py")
        self.assertEqual(queue_job["profile"], "zf-orchestrator")
        self.assertEqual(queue_job["schedule"]["kind"], "interval")

    def test_build_board_scanner_prompt(self):
        """Prompt contains board slug, pre-flight checks, and safety rules."""
        board = {"slug": "my-service", "description": "Backend API"}
        prompt = build_board_scanner_prompt(board, workdir="/tmp/repo")
        self.assertIn("my-service", prompt)
        self.assertIn("/tmp/repo", prompt)
        self.assertIn("hermes zerofactory create", prompt)
        self.assertIn("Fingerprint Safeguard", prompt)

    def test_resolve_board_repo_path_http_and_ssh(self):
        """resolve_board_repo_path handles HTTP, SSH, and description fallbacks."""
        # Current workspace is zerofactory, which should resolve
        b_http = {"slug": "zerofactory", "git_url": "https://github.com/hotcode-dev/zerofactory.git"}
        b_ssh = {"slug": "zerofactory", "git_url": "git@github.com:hotcode-dev/zerofactory.git"}
        b_proto = {"slug": "zerofactory", "git_url": "ssh://git@github.com/hotcode-dev/zerofactory.git"}
        b_desc = {"slug": "zerofactory", "description": "Project at git@github.com:hotcode-dev/zerofactory.git"}

        res_http = resolve_board_repo_path(b_http)
        res_ssh = resolve_board_repo_path(b_ssh)
        res_proto = resolve_board_repo_path(b_proto)
        res_desc = resolve_board_repo_path(b_desc)

        self.assertIsNotNone(res_http)
        self.assertEqual(res_http, res_ssh)
        self.assertEqual(res_http, res_proto)
        self.assertEqual(res_http, res_desc)

    def test_no_board_cron_generation(self):
        """When database has no boards, only core cron jobs are returned."""
        with tempfile.TemporaryDirectory() as td:
            empty_db = Path(td) / "empty.db"
            with sqlite3.connect(str(empty_db)) as conn:
                conn.execute(
                    "CREATE TABLE boards (slug TEXT PRIMARY KEY, description TEXT, git_url TEXT, created_at REAL, updated_at REAL)"
                )
                conn.commit()

            import builtin_cron
            with patch.dict(os.environ, {"ZEROFACTORY_DB": str(empty_db)}):
                orig_bc = getattr(builtin_cron, "get_db_path", None)
                builtin_cron.get_db_path = lambda: empty_db
                try:
                    jobs = get_all_builtin_cron_jobs()
                    scanners = [jid for jid in jobs if jid.startswith("zero-factory-improvement-scanner-")]
                    self.assertEqual(scanners, [])
                    self.assertIn("zero-factory-task-queue-check", jobs)
                finally:
                    if orig_bc:
                        builtin_cron.get_db_path = orig_bc


if __name__ == "__main__":
    unittest.main()
