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
            "ZEROFACTORY_SKIP_WORKER_SPAWN": os.environ.get(
                "ZEROFACTORY_SKIP_WORKER_SPAWN"
            ),
            "ZEROFACTORY_DISABLE_DISPATCHER": os.environ.get(
                "ZEROFACTORY_DISABLE_DISPATCHER"
            ),
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

    def _run_script(
        self,
        script_name: str,
        args: list[str] = None,
        cwd: Path | None = None,
        extra_env: dict[str, str] = None,
    ) -> tuple[int, str]:
        cmd = [sys.executable, str(self.scripts_dir / script_name)] + (args or [])
        python_path = os.pathsep.join([str(REPO_ROOT)] + sys.path)
        # Scrub scanner-gate control vars inherited from the parent (e.g. an
        # idle-scan cron worker exports ZEROFACTORY_IDLE_SCAN=1) so the
        # subprocess runs hermetically; tests opt back in via extra_env.
        scanner_gate_env = {**os.environ}
        for leaked in (
            "ZEROFACTORY_IDLE_SCAN",
            "ZEROFACTORY_FORCE_SCAN",
            "ZEROFACTORY_SCANNER_STATE",
        ):
            scanner_gate_env.pop(leaked, None)
        env = {
            **scanner_gate_env,
            "HOME": str(self.fake_home),
            "PYTHONPATH": python_path,
            "ZEROFACTORY_DB": str(self.db_path),
            "ZEROFACTORY_LOCK_PATH": str(self.lock_path),
            "ZEROFACTORY_DISABLE_DISPATCHER": "1",
            "ZEROFACTORY_SKIP_WORKER_SPAWN": "1",
            **(extra_env or {}),
        }
        res = subprocess.run(
            cmd,
            cwd=str(cwd or self.scripts_dir),
            capture_output=True,
            text=True,
            env=env,
            timeout=20,
        )
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
            extra_env={
                "ZEROFACTORY_TASK_TIMEOUT_SECONDS": "60",
                "ZEROFACTORY_INACTIVITY_TIMEOUT_SECONDS": "60",
            },
        )
        self.assertEqual(rc2, 0)
        self.assertIn("ZeroFactory Queue Watchdog Alert", out2)
        self.assertIn("zf-hung", out2)

        # Verify task is now blocked in DB
        self.assertEqual(get_task("zf-hung")["task"]["status"], "blocked")

    def test_02_scanner_gate_suppression_and_wake(self):
        """zf_scanner_gate: unchanged repo suppresses (wakeAgent:false); new commits wake agent."""
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=str(self.repo_dir),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Scanner E2E"],
            cwd=str(self.repo_dir),
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "scanner@zerofactory.ai"],
            cwd=str(self.repo_dir),
            check=True,
        )
        (self.repo_dir / "index.py").write_text("print('hello')\n")
        subprocess.run(["git", "add", "."], cwd=str(self.repo_dir), check=True)
        subprocess.run(
            ["git", "commit", "-m", "chore: initial commit"],
            cwd=str(self.repo_dir),
            check=True,
        )

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
        subprocess.run(
            ["git", "commit", "-m", "feat: new feature"],
            cwd=str(self.repo_dir),
            check=True,
        )

        rc3, out3 = self._run_script("zf_scanner_gate.py", cwd=self.repo_dir)
        self.assertEqual(rc3, 0)
        self.assertIn("feat: new feature", out3)

    def test_03_daily_stats_single_turn_synthesis(self):
        """zf_daily_stats computes 24h metrics, velocity, and cycle time directly to context."""
        create_board(BoardCreate(git_url="https://github.com/example/stats-demo.git"))

        # Create tasks across various columns
        t1 = create_task(
            TaskCreate(board_slug="example-stats-demo", title="Task 1", status="done")
        )["id"]
        t2 = create_task(
            TaskCreate(
                board_slug="example-stats-demo", title="Task 2", status="running"
            )
        )["id"]
        t3 = create_task(
            TaskCreate(
                board_slug="example-stats-demo", title="Task 3", status="blocked"
            )
        )["id"]

        add_comment(
            t1, CommentCreate(author="zf-builder", body="Implemented and tested")
        )

        rc, out = self._run_script("zf_daily_stats.py")
        self.assertEqual(rc, 0)
        self.assertIn("Pre-Calculated ZeroFactory Daily Metrics", out)
        self.assertIn("Column Distribution:", out)
        self.assertIn("| `done` | 1 |", out)
        self.assertIn("| `running` | 1 |", out)
        self.assertIn("| `blocked` | 1 |", out)
        self.assertIn("Tasks Completed in Last 24h", out)
        self.assertIn("Active Blockers (1 tasks)", out)

    def test_04_openwiki_gate_suppression_and_wake(self):
        """zf_openwiki_gate: missing openwiki/ or dirty tree or unchanged repo suppresses; new commits wake agent."""
        wiki_repo = Path(self.td) / "wiki_repo"
        wiki_repo.mkdir()
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=str(wiki_repo),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Wiki E2E"],
            cwd=str(wiki_repo),
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "wiki@zerofactory.ai"],
            cwd=str(wiki_repo),
            check=True,
        )
        (wiki_repo / "README.md").write_text("# Wiki Repo\n")
        subprocess.run(["git", "add", "."], cwd=str(wiki_repo), check=True)
        subprocess.run(
            ["git", "commit", "-m", "chore: initial commit"],
            cwd=str(wiki_repo),
            check=True,
        )

        create_board(BoardCreate(git_url=str(wiki_repo)))

        # 1. Missing openwiki/ dir: suppresses with wakeAgent: false
        rc1, out1 = self._run_script("zf_openwiki_gate.py", cwd=wiki_repo)
        self.assertEqual(rc1, 0)
        self.assertIn("OpenWiki not initialized", out1)
        self.assertIn('"wakeagent": false', out1.lower())

        # 2. Add openwiki/ dir with docs and commit
        (wiki_repo / "openwiki").mkdir()
        (wiki_repo / "openwiki" / "architecture.md").write_text("# Arch\n")
        subprocess.run(["git", "add", "."], cwd=str(wiki_repo), check=True)
        subprocess.run(
            ["git", "commit", "-m", "docs(openwiki): initialize architecture"],
            cwd=str(wiki_repo),
            check=True,
        )

        # 3. Clean repo with no non-openwiki changes: suppresses with wakeAgent: false
        rc2, out2 = self._run_script("zf_openwiki_gate.py", cwd=wiki_repo)
        self.assertEqual(rc2, 0)
        self.assertIn('"wakeagent": false', out2.lower())
        self.assertIn("OpenWiki is up to date", out2)

        # 4. Dirty working tree: suppresses with wakeAgent: false
        (wiki_repo / "uncommitted.txt").write_text("wip\n")
        rc3, out3 = self._run_script("zf_openwiki_gate.py", cwd=wiki_repo)
        self.assertEqual(rc3, 0)
        self.assertIn("has uncommitted changes", out3)
        self.assertIn('"wakeagent": false', out3.lower())

        # Remove uncommitted file
        (wiki_repo / "uncommitted.txt").unlink()

        # 5. Add new non-openwiki code commit: wakes agent with wakeAgent: true
        (wiki_repo / "app.py").write_text("def run(): pass\n")
        subprocess.run(["git", "add", "."], cwd=str(wiki_repo), check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: core app runner"],
            cwd=str(wiki_repo),
            check=True,
        )

        rc4, out4 = self._run_script("zf_openwiki_gate.py", cwd=wiki_repo)
        self.assertEqual(rc4, 0)
        self.assertIn("branch update(s)", out4)
        self.assertIn("created task", out4)
        self.assertIn('"wakeagent": false', out4.lower())

        # 6. Run again without new changes: suppresses with wakeAgent: false
        rc5, out5 = self._run_script("zf_openwiki_gate.py", cwd=wiki_repo)
        self.assertEqual(rc5, 0)
        self.assertIn('"wakeagent": false', out5.lower())

        # 7. Add new code commit, but create an active OpenWiki task on the board
        (wiki_repo / "service.py").write_text("class Service: pass\n")
        subprocess.run(["git", "add", "."], cwd=str(wiki_repo), check=True)
        subprocess.run(
            ["git", "commit", "-m", "feat: add service layer"],
            cwd=str(wiki_repo),
            check=True,
        )

        slug = wiki_repo.name
        t = create_task(
            TaskCreate(
                board_slug=slug,
                title="docs(openwiki): sync architecture documentation with recent changes",
                status="todo",
                assignee="zf-builder",
            )
        )
        task_id = t["id"]

        # In 'todo': suppressed without waking the agent
        rc6, out6 = self._run_script("zf_openwiki_gate.py", cwd=wiki_repo)
        self.assertEqual(rc6, 0)
        self.assertIn("already has an active OpenWiki task", out6)
        self.assertIn('"wakeagent": false', out6.lower())

        # In 'running': still suppressed
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("UPDATE tasks SET status = 'running' WHERE id = ?", (task_id,))
            conn.commit()
        rc7, out7 = self._run_script("zf_openwiki_gate.py", cwd=wiki_repo)
        self.assertEqual(rc7, 0)
        self.assertIn("already has an active OpenWiki task", out7)
        self.assertIn('"wakeagent": false', out7.lower())

        # In 'blocked': still suppressed
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("UPDATE tasks SET status = 'blocked' WHERE id = ?", (task_id,))
            conn.commit()
        rc8, out8 = self._run_script("zf_openwiki_gate.py", cwd=wiki_repo)
        self.assertEqual(rc8, 0)
        self.assertIn("already has an active OpenWiki task", out8)
        self.assertIn('"wakeagent": false', out8.lower())

        # Move to 'done': now unblocked, automatically creates the new task on board for zf-builder!
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("UPDATE tasks SET status = 'done' WHERE id = ?", (task_id,))
            conn.commit()
        rc9, out9 = self._run_script("zf_openwiki_gate.py", cwd=wiki_repo)
        self.assertEqual(rc9, 0)
        self.assertIn("branch update(s)", out9)
        self.assertIn("created task", out9)
        self.assertIn('"wakeagent": false', out9.lower())


if __name__ == "__main__":
    unittest.main()

