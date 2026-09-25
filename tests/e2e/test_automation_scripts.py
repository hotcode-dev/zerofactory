"""End-to-End validation of standalone background automation scripts."""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from typing import Dict, List, Optional

from dashboard.plugin_api import (
    BoardCreate,
    CommentCreate,
    TaskCreate,
    add_comment,
    create_board,
    create_task,
    get_task,
    init_db,
)

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class TestAutomationScriptsE2E(unittest.TestCase):
    """End-to-End validation of standalone background automation scripts."""

    def setUp(self):
        self.td = tempfile.mkdtemp(prefix="zf-scripts-e2e-")
        self.db_path = Path(self.td) / "scripts_test.db"
        self.lock_path = Path(self.td) / "scripts_lock.lock"
        self.fake_home = Path(self.td) / "home"
        self.fake_home.mkdir(parents=True)
        self.repo_dir = Path(self.td) / "repo"
        self.repo_dir.mkdir()

        self.orig_env = {
            "ZEROFACTORY_DB": os.environ.get("ZEROFACTORY_DB"),
            "ZEROFACTORY_LOCK_PATH": os.environ.get("ZEROFACTORY_LOCK_PATH"),
            "ZEROFACTORY_SKIP_GIT": os.environ.get("ZEROFACTORY_SKIP_GIT"),
            "ZEROFACTORY_SKIP_WORKER_SPAWN": os.environ.get("ZEROFACTORY_SKIP_WORKER_SPAWN"),
            "ZEROFACTORY_DISABLE_DISPATCHER": os.environ.get("ZEROFACTORY_DISABLE_DISPATCHER"),
            "HOME": os.environ.get("HOME"),
        }

        os.environ["ZEROFACTORY_DB"] = str(self.db_path)
        os.environ["ZEROFACTORY_LOCK_PATH"] = str(self.lock_path)
        os.environ["ZEROFACTORY_DISABLE_DISPATCHER"] = "1"
        os.environ["ZEROFACTORY_SKIP_GIT"] = "1"
        os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = "1"
        os.environ["HOME"] = str(self.fake_home)
        init_db(force=True)

        self.scripts_dir = REPO_ROOT / "scripts"

    def tearDown(self):
        for k, v in self.orig_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
        shutil.rmtree(self.td, ignore_errors=True)

    def _run_script(self, script_name: str, args: List[str] = None, cwd: Optional[Path] = None, extra_env: Dict[str, str] = None) -> tuple[int, str]:
        cmd = [sys.executable, str(self.scripts_dir / script_name)] + (args or [])
        python_path = os.pathsep.join([str(REPO_ROOT)] + sys.path)
        env = {
            **os.environ,
            "HOME": str(self.fake_home),
            "PYTHONPATH": python_path,
            "ZEROFACTORY_DB": str(self.db_path),
            "ZEROFACTORY_LOCK_PATH": str(self.lock_path),
            "ZEROFACTORY_DISABLE_DISPATCHER": "1",
            "ZEROFACTORY_SKIP_WORKER_SPAWN": "1",
            **(extra_env or {})
        }
        res = subprocess.run(cmd, cwd=str(cwd or self.scripts_dir), capture_output=True, text=True, env=env, timeout=20)
        return res.returncode, res.stdout.strip()

    def test_01_queue_watchdog_healthy_vs_stuck_alerts(self):
        """zf_queue_watchdog: healthy queue emits 0-token wakeAgent:false; stuck queue alerts."""
        create_board(BoardCreate(git_url="https://github.com/example/watchdog.git"))

        # 1. Healthy queue
        rc, out = self._run_script("zf_queue_watchdog.py")
        self.assertEqual(rc, 0)
        self.assertIn('"wakeagent": false', out.lower())

        # 2. Add stuck running task
        now = int(time.time())
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO tasks (id, board_slug, title, status, assignee, priority, metadata, created_at, updated_at)
                VALUES ('zf-hung', 'example-watchdog', 'Hung Worker Task', 'running', 'zf-builder', 'P1',
                        '{"worker_pid": 9999999, "running_since": 1000}', 1000, 1000)
            """)
            conn.commit()

        # Run watchdog with short timeout
        rc2, out2 = self._run_script(
            "zf_queue_watchdog.py",
            extra_env={"ZEROFACTORY_TASK_TIMEOUT_SECONDS": "60", "ZEROFACTORY_INACTIVITY_TIMEOUT_SECONDS": "60"}
        )
        self.assertEqual(rc2, 0)
        self.assertIn("ZeroFactory Queue Watchdog Alert", out2)
        self.assertIn("zf-hung", out2)

        # Verify task is now blocked in DB
        self.assertEqual(get_task("zf-hung")["task"]["status"], "blocked")

    def test_02_scanner_gate_suppression_and_wake(self):
        """zf_scanner_gate: unchanged repo suppresses (wakeAgent:false); new commits wake agent."""
        subprocess.run(["git", "init", "-b", "main"], cwd=str(self.repo_dir), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Scanner E2E"], cwd=str(self.repo_dir), check=True)
        subprocess.run(["git", "config", "user.email", "scanner@zerofactory.ai"], cwd=str(self.repo_dir), check=True)
        (self.repo_dir / "index.py").write_text("print('hello')\n")
        subprocess.run(["git", "add", "."], cwd=str(self.repo_dir), check=True)
        subprocess.run(["git", "commit", "-m", "chore: initial commit"], cwd=str(self.repo_dir), check=True)

        create_board(BoardCreate(git_url=str(self.repo_dir)))

        # 1. First run on commit: records state and wakes agent
        rc1, out1 = self._run_script("zf_scanner_gate.py", cwd=self.repo_dir)
        self.assertEqual(rc1, 0)
        self.assertIn("Pre-Screen Intelligence Package", out1)
        self.assertIn('"wakeAgent": true', out1)

        # 2. Second run without changes: suppresses with wakeAgent: false
        rc2, out2 = self._run_script("zf_scanner_gate.py", cwd=self.repo_dir)
        self.assertEqual(rc2, 0)
        self.assertIn('"wakeagent": false', out2.lower())

        # 3. Add new commit: wakes agent again
        (self.repo_dir / "feature.py").write_text("def new_feature(): pass\n")
        subprocess.run(["git", "add", "."], cwd=str(self.repo_dir), check=True)
        subprocess.run(["git", "commit", "-m", "feat: new feature"], cwd=str(self.repo_dir), check=True)

        rc3, out3 = self._run_script("zf_scanner_gate.py", cwd=self.repo_dir)
        self.assertEqual(rc3, 0)
        self.assertIn("feat: new feature", out3)

    def test_03_daily_stats_single_turn_synthesis(self):
        """zf_daily_stats computes 24h metrics, velocity, and cycle time directly to context."""
        create_board(BoardCreate(git_url="https://github.com/example/stats-demo.git"))

        # Create tasks across various columns
        t1 = create_task(TaskCreate(board_slug="example-stats-demo", title="Task 1", status="done"))["id"]
        t2 = create_task(TaskCreate(board_slug="example-stats-demo", title="Task 2", status="running"))["id"]
        t3 = create_task(TaskCreate(board_slug="example-stats-demo", title="Task 3", status="blocked"))["id"]

        add_comment(t1, CommentCreate(author="zf-builder", body="Implemented and tested"))

        rc, out = self._run_script("zf_daily_stats.py")
        self.assertEqual(rc, 0)
        self.assertIn("Pre-Calculated ZeroFactory Daily Metrics", out)
        self.assertIn("Column Distribution:", out)
        self.assertIn("| `done` | 1 |", out)
        self.assertIn("| `running` | 1 |", out)
        self.assertIn("| `blocked` | 1 |", out)
        self.assertIn("Tasks Completed in Last 24h", out)
        self.assertIn("Active Blockers (1 tasks)", out)


if __name__ == "__main__":
    unittest.main()
