"""End-to-End validation of concurrency guards, flock, and failure recovery."""

from __future__ import annotations

import fcntl
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import FastAPI
from fastapi.testclient import TestClient

import dispatcher
import profile_manager
from dashboard.plugin_api import (
    BoardCreate,
    TaskCreate,
    create_board,
    create_task,
    init_db,
    list_tasks,
    router,
)


class TestConcurrencyAndResilienceE2E(unittest.TestCase):
    """End-to-End validation of concurrency guards, flock, and failure recovery."""

    def setUp(self):
        self.td = tempfile.mkdtemp(prefix="zf-resilience-e2e-")
        self.db_path = Path(self.td) / "resilience.db"
        self.lock_path = Path(self.td) / "resilience_lock.lock"

        self.orig_env = {
            "ZEROFACTORY_DB": os.environ.get("ZEROFACTORY_DB"),
            "ZEROFACTORY_LOCK_PATH": os.environ.get("ZEROFACTORY_LOCK_PATH"),
            "ZEROFACTORY_DISABLE_DISPATCHER": os.environ.get("ZEROFACTORY_DISABLE_DISPATCHER"),
            "ZEROFACTORY_SKIP_WORKER_SPAWN": os.environ.get("ZEROFACTORY_SKIP_WORKER_SPAWN"),
        }

        os.environ["ZEROFACTORY_DB"] = str(self.db_path)
        os.environ["ZEROFACTORY_LOCK_PATH"] = str(self.lock_path)
        os.environ["ZEROFACTORY_DISABLE_DISPATCHER"] = "1"
        os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = "1"
        init_db(force=True)

        app = FastAPI()
        app.include_router(router, prefix="/api/plugins/zerofactory")
        self.client = TestClient(app)

    def tearDown(self):
        for k, v in self.orig_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
        shutil.rmtree(self.td, ignore_errors=True)

    def test_01_cross_process_flock_concurrency_guard(self):
        """fcntl.flock lock skips concurrent dispatch cycles cleanly with concurrent_cycle_active."""
        # Hold the lock externally as if another process is running dispatch
        external_fd = os.open(str(self.lock_path), os.O_CREAT | os.O_RDWR, 0o666)
        fcntl.flock(external_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

        try:
            res = dispatcher.run_dispatch_cycle(self.db_path)
            self.assertTrue(res.get("ok"))
            self.assertTrue(res.get("skipped"))
            self.assertEqual(res.get("reason"), "concurrent_cycle_active")
        finally:
            fcntl.flock(external_fd, fcntl.LOCK_UN)
            os.close(external_fd)

        # Once released, cycle executes normally
        res2 = dispatcher.run_dispatch_cycle(self.db_path)
        self.assertTrue(res2.get("ok"))
        self.assertFalse(res2.get("skipped", False))

    def test_02_board_max_concurrent_running_enforcement(self):
        """Dispatcher strictly respects board max_concurrent_running cap."""
        create_board(BoardCreate(git_url="https://github.com/example/cap.git"))
        self.client.patch("/api/plugins/zerofactory/boards/example-cap", json={"max_concurrent_running": 2})

        # Create 4 tasks in todo
        for i in range(1, 5):
            create_task(TaskCreate(
                board_slug="example-cap",
                title=f"Parallel Task {i}",
                status="todo",
                assignee="zf-builder"
            ))

        # Run dispatch cycle
        res = dispatcher.run_dispatch_cycle(self.db_path)
        self.assertTrue(res["ok"])

        # Exactly 2 should be running, 2 remain in todo
        running_tasks = list_tasks(board="example-cap", status="running")["tasks"]
        todo_tasks = list_tasks(board="example-cap", status="todo")["tasks"]
        self.assertEqual(len(running_tasks), 2)
        self.assertEqual(len(todo_tasks), 2)

    def test_03_hanging_worktree_cleanup_timeout_resilience(self):
        """Hung git worktree remove does not crash dispatcher; triggers bounded prune fallback."""
        fake_ws = Path(self.td) / "fake_worktree"
        fake_ws.mkdir()
        fake_repo = Path(self.td) / "fake_repo"
        fake_repo.mkdir()

        prune_calls = []

        def fake_run(cmd, *a, **kw):
            if isinstance(cmd, list) and cmd[:3] == ["git", "worktree", "remove"]:
                raise subprocess.TimeoutExpired(cmd=cmd, timeout=30)
            if isinstance(cmd, list) and cmd[:3] == ["git", "worktree", "prune"]:
                prune_calls.append(cmd)
                m = MagicMock()
                m.returncode = 0
                return m
            return subprocess.run(cmd, *a, **kw)

        with patch("subprocess.run", side_effect=fake_run):
            # Must complete cleanly without raising TimeoutExpired
            dispatcher._remove_worktree(str(fake_ws), fake_repo)

        self.assertEqual(len(prune_calls), 1, "Worktree prune must be called on remove timeout")

    def test_20_langfuse_settings_and_test_connection(self):
        """Verify Langfuse settings lifecycle and /settings/langfuse/test endpoint."""
        # 1. Update settings
        patch_res = self.client.patch("/api/plugins/zerofactory/settings", json={
            "langfuse_enabled": True,
            "langfuse_base_url": "https://cloud.langfuse.com",
            "langfuse_public_key": "pk-lf-test-e2e",
            "langfuse_secret_key": "sk-lf-test-e2e",
            "langfuse_capture_mode": "metadata",
            "langfuse_env": "e2e-test"
        })
        self.assertEqual(patch_res.status_code, 200)
        st = patch_res.json()["settings"]
        self.assertTrue(st["langfuse_enabled"])
        self.assertEqual(st["langfuse_public_key"], "pk-lf-test-e2e")
        self.assertEqual(st["langfuse_capture_mode"], "metadata")

        # 2. Test endpoint validation
        test_res = self.client.post("/api/plugins/zerofactory/settings/langfuse/test", json={
            "base_url": "https://cloud.langfuse.com",
            "public_key": "invalid_key_prefix",
            "secret_key": "sk-lf-123"
        })
        self.assertEqual(test_res.status_code, 200)
        self.assertFalse(test_res.json()["ok"])
        self.assertIn("Invalid key format", test_res.json()["error"])

        # 3. Regression (hermetic, temp home): disabling must scrub every
        #    HERMES_LANGFUSE_* key from .env files — no stale secrets left.
        with tempfile.TemporaryDirectory() as tmp_hermes:
            hermes_fake = Path(tmp_hermes)
            profiles_dir = hermes_fake / "profiles" / "zf-builder"
            profiles_dir.mkdir(parents=True)
            enable_settings = {
                "langfuse_enabled": True,
                "langfuse_base_url": "https://cloud.langfuse.com",
                "langfuse_public_key": "«redacted:pk-lf-…»",
                "langfuse_secret_key": "«redacted:sk-…»",
                "langfuse_capture_mode": "metadata",
                "langfuse_env": "e2e-test",
            }
            with patch.object(profile_manager, "get_hermes_home", return_value=hermes_fake):
                profile_manager.sync_langfuse_profiles(enable_settings)
                self.assertIn(
                    "HERMES_LANGFUSE_SECRET_KEY=«redacted:sk-…»",
                    (hermes_fake / ".env").read_text(encoding="utf-8"),
                )
                profile_manager.sync_langfuse_profiles(dict(enable_settings, langfuse_enabled=False))
                for d in (hermes_fake, profiles_dir):
                    env_text = (d / ".env").read_text(encoding="utf-8")
                    for k in ("HERMES_LANGFUSE_SECRET_KEY", "HERMES_LANGFUSE_PUBLIC_KEY",
                              "HERMES_LANGFUSE_BASE_URL", "HERMES_LANGFUSE_CAPTURE",
                              "HERMES_LANGFUSE_ENV"):
                        self.assertNotIn(k, env_text, f"stale {k} left in {d / '.env'}")


if __name__ == "__main__":
    unittest.main()
