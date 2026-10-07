"""Unit tests for scripts/zf_queue_watchdog.py."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import tempfile
import unittest
from pathlib import Path
from unittest import mock
from unittest.mock import MagicMock

from dashboard.plugin_api import (
    BoardCreate,
    TaskCreate,
    create_board,
    create_task,
    get_task,
    init_db,
)
from dispatcher import _active_workers, reap_stuck_tasks
import issues.github
import issues.importer

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class TestZfQueueWatchdogUnit(unittest.TestCase):
    """Test stuck task reaping contract and watchdog alert rendering."""

    @classmethod
    def setUpClass(cls):
        wd_path = REPO_ROOT / "scripts" / "zf_queue_watchdog.py"
        spec = importlib.util.spec_from_file_location("zf_queue_watchdog_test", wd_path)
        cls.wd = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.wd)

    def setUp(self):
        self.td = tempfile.mkdtemp(prefix="zf-watchdog-unit-")
        self.db_path = Path(self.td) / "watchdog.db"
        self.orig_env = {
            "ZEROFACTORY_DB": os.environ.get("ZEROFACTORY_DB"),
            "ZEROFACTORY_SKIP_WORKER_SPAWN": os.environ.get(
                "ZEROFACTORY_SKIP_WORKER_SPAWN"
            ),
            "ZEROFACTORY_SKIP_GIT": os.environ.get("ZEROFACTORY_SKIP_GIT"),
            "ZEROFACTORY_DISABLE_DISPATCHER": os.environ.get(
                "ZEROFACTORY_DISABLE_DISPATCHER"
            ),
        }
        os.environ["ZEROFACTORY_DB"] = str(self.db_path)
        os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = "1"
        os.environ["ZEROFACTORY_SKIP_GIT"] = "1"
        init_db(force=True)

        create_board(
            BoardCreate(
                git_url="https://github.com/hotcode-dev/zerofactory",
                description="AI workflow",
            )
        )

    def tearDown(self):
        for k, v in self.orig_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
        shutil.rmtree(self.td, ignore_errors=True)
        _active_workers.clear()

    def test_reap_stuck_tasks_contract(self):
        """reap_stuck_tasks provides both reaped_tasks and reaped for watchdog compatibility."""
        res = reap_stuck_tasks(self.db_path)
        self.assertTrue(res.get("ok"))
        self.assertIn("reaped_tasks", res)
        self.assertIn("reaped", res)
        self.assertEqual(res["reaped_tasks"], res["reaped"])

    def test_watchdog_clean_queue_suppresses(self):
        """On a healthy board with 0 stuck tasks, watchdog emits wakeAgent: false."""
        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = self.wd.run_watchdog()
        self.assertEqual(rc, 0)
        out = buf.getvalue().strip()
        last_line = out.splitlines()[-1]
        data = json.loads(last_line)
        self.assertIn("wakeAgent", data)
        self.assertFalse(data["wakeAgent"])

    def test_watchdog_reaped_alert_rendering(self):
        """When a stuck worker is reaped, watchdog prints alert and does not suppress."""
        t_id = create_task(
            TaskCreate(
                title="Watchdog Stuck Task",
                status="running",
                priority="P0",
                assignee="zf-builder",
            )
        )["id"]

        dead_proc = MagicMock()
        dead_proc.poll.return_value = 1
        dead_proc.pid = 12346
        _active_workers[t_id] = dead_proc

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            rc = self.wd.run_watchdog()

        out = buf.getvalue()
        self.assertEqual(rc, 0)
        self.assertIn("Reaped Stuck Tasks", out)
        self.assertIn(t_id, out)
        self.assertIn("Current Board State", out)
        self.assertNotIn("wakeAgent", out)
        self.assertEqual(get_task(t_id)["task"]["status"], "blocked")


class TestZfQueueWatchdogGithubSync(unittest.TestCase):
    """GitHub issue auto-sync: cooldown stamping, failure handling, atomic cache writes."""

    REPO = "hotcode-dev/zerofactory"

    @classmethod
    def setUpClass(cls):
        wd_path = REPO_ROOT / "scripts" / "zf_queue_watchdog.py"
        spec = importlib.util.spec_from_file_location("zf_queue_watchdog_sync", wd_path)
        cls.wd = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.wd)

    def setUp(self):
        self.td = Path(tempfile.mkdtemp(prefix="zf-watchdog-sync-"))
        self.db_path = self.td / "watchdog.db"
        self.cache_file = self.td / ".hermes" / "gh_issues_sync_cache.json"
        self.orig_env = {
            "ZEROFACTORY_DB": os.environ.get("ZEROFACTORY_DB"),
            "ZEROFACTORY_SKIP_WORKER_SPAWN": os.environ.get(
                "ZEROFACTORY_SKIP_WORKER_SPAWN"
            ),
            "ZEROFACTORY_SKIP_GIT": os.environ.get("ZEROFACTORY_SKIP_GIT"),
            "ZEROFACTORY_AUTO_SYNC_GH_ISSUES": os.environ.get(
                "ZEROFACTORY_AUTO_SYNC_GH_ISSUES"
            ),
        }
        os.environ["ZEROFACTORY_DB"] = str(self.db_path)
        os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = "1"
        os.environ["ZEROFACTORY_SKIP_GIT"] = "1"
        os.environ["ZEROFACTORY_AUTO_SYNC_GH_ISSUES"] = "1"
        init_db(force=True)

        create_board(
            BoardCreate(
                git_url=f"https://github.com/{self.REPO}",
                description="AI workflow",
            )
        )

    def tearDown(self):
        for k, v in self.orig_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
        shutil.rmtree(self.td, ignore_errors=True)
        _active_workers.clear()

    def _sync_client(self, fetch_return=None, fetch_side_effect=None):
        """Return a MagicMock client_cls whose instance is a wired-up client."""
        client_cls = mock.MagicMock()
        client = client_cls.return_value
        client.test_connection.return_value = True
        if fetch_side_effect is not None:
            client.fetch_investigation_issues.side_effect = fetch_side_effect
        else:
            client.fetch_investigation_issues.return_value = fetch_return or []
        return client_cls, client

    def test_failed_fetch_does_not_stamp_cooldown_cache(self):
        """A failed fetch must NOT write the cache entry (no cooldown burned)."""
        client_cls, client = self._sync_client(
            fetch_side_effect=RuntimeError("GitHub CLI rate limited")
        )
        with (
            mock.patch("pathlib.Path.home", return_value=self.td),
            mock.patch.object(issues.github, "GitHubIssueClient", client_cls),
            self.assertLogs(self.wd.__name__, level="WARNING") as cm,
        ):
            res = self.wd.sync_open_github_issues()

        self.assertEqual(res, [])
        self.assertFalse(self.cache_file.exists(), "failed sync must not stamp cache")
        self.assertTrue(
            any(
                "GitHub issue sync failed for hotcode-dev/zerofactory" in line
                for line in cm.output
            ),
            f"expected per-board failure warning, got: {cm.output}",
        )

        # No stamp written -> the next tick must retry immediately (cooldown
        # must not apply to the failed board).
        with (
            mock.patch("pathlib.Path.home", return_value=self.td),
            mock.patch.object(issues.github, "GitHubIssueClient", client_cls),
        ):
            self.wd.sync_open_github_issues()
        self.assertEqual(client.fetch_investigation_issues.call_count, 2)

    def test_failed_import_does_not_stamp_cooldown_cache(self):
        """A failing import_external_issue must NOT write the cache entry either."""
        client_cls, _ = self._sync_client(fetch_return=[MagicMock()])
        with (
            mock.patch("pathlib.Path.home", return_value=self.td),
            mock.patch.object(issues.github, "GitHubIssueClient", client_cls),
            mock.patch.object(
                issues.importer,
                "import_external_issue",
                side_effect=RuntimeError("db unavailable"),
            ),
        ):
            res = self.wd.sync_open_github_issues()

        self.assertEqual(res, [])
        self.assertFalse(self.cache_file.exists(), "failed import must not stamp cache")

    def test_successful_sync_updates_cooldown_cache(self):
        """A clean sync DOES stamp the cache, and the next tick skips the fetch."""
        client_cls, client = self._sync_client(fetch_return=[MagicMock()])
        with (
            mock.patch("pathlib.Path.home", return_value=self.td),
            mock.patch.object(issues.github, "GitHubIssueClient", client_cls),
            mock.patch.object(
                issues.importer,
                "import_external_issue",
                return_value={"duplicate": False, "id": "zf-test"},
            ),
        ):
            res = self.wd.sync_open_github_issues()

        self.assertEqual(len(res), 1)
        self.assertTrue(self.cache_file.exists(), "successful sync must stamp cache")
        cache = json.loads(self.cache_file.read_text(encoding="utf-8"))
        self.assertIn(self.REPO, cache)
        self.assertIsInstance(cache[self.REPO], float)
        # Atomic write leaves no temp file behind.
        self.assertFalse(
            self.cache_file.with_name(self.cache_file.name + ".tmp").exists()
        )

        # Second tick inside the cooldown window -> fetch skipped entirely.
        with (
            mock.patch("pathlib.Path.home", return_value=self.td),
            mock.patch.object(issues.github, "GitHubIssueClient", client_cls),
        ):
            self.wd.sync_open_github_issues()
        self.assertEqual(client.fetch_investigation_issues.call_count, 1)

    def test_cache_write_is_atomic_on_mid_write_failure(self):
        """If the rename fails, the cache file must not be published and no .tmp lingers."""
        client_cls, _ = self._sync_client(fetch_return=[])
        with (
            mock.patch("pathlib.Path.home", return_value=self.td),
            mock.patch.object(issues.github, "GitHubIssueClient", client_cls),
            mock.patch("os.replace", side_effect=OSError("simulated crash mid-rename")),
        ):
            res = self.wd.sync_open_github_issues()

        self.assertEqual(res, [])
        self.assertFalse(self.cache_file.exists(), "rename failed -> no publish")
        self.assertFalse(
            self.cache_file.with_name(self.cache_file.name + ".tmp").exists(),
            "temp file must be cleaned up on write failure",
        )


if __name__ == "__main__":
    unittest.main()
