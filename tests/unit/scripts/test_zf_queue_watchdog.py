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
from unittest.mock import MagicMock

from dashboard.plugin_api import (
    BoardCreate,
    TaskCreate,
    create_board,
    create_task,
    get_db_conn,
    get_task,
    init_db,
    list_boards,
)
from dispatcher import _active_workers, reap_stuck_tasks

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
            "ZEROFACTORY_SKIP_WORKER_SPAWN": os.environ.get("ZEROFACTORY_SKIP_WORKER_SPAWN"),
            "ZEROFACTORY_SKIP_GIT": os.environ.get("ZEROFACTORY_SKIP_GIT"),
            "ZEROFACTORY_DISABLE_DISPATCHER": os.environ.get("ZEROFACTORY_DISABLE_DISPATCHER"),
        }
        os.environ["ZEROFACTORY_DB"] = str(self.db_path)
        os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = "1"
        os.environ["ZEROFACTORY_SKIP_GIT"] = "1"
        init_db(force=True)

        create_board(BoardCreate(
            git_url="https://github.com/hotcode-dev/zerofactory",
            description="AI workflow",
        ))

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
        t_id = create_task(TaskCreate(
            title="Watchdog Stuck Task",
            status="running",
            priority="P0",
            assignee="zf-builder",
        ))["id"]

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


if __name__ == "__main__":
    unittest.main()
