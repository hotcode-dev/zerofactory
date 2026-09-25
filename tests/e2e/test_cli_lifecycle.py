"""End-to-End validation of all Zero Factory CLI commands."""

from __future__ import annotations

import argparse
import io
import os
import shutil
import sqlite3
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import List

import __init__ as zf_cli
from dashboard.plugin_api import init_db


class TestZeroFactoryCLIE2E(unittest.TestCase):
    """End-to-End validation of all Zero Factory CLI commands."""

    def setUp(self):
        self.td = tempfile.mkdtemp(prefix="zf-cli-e2e-")
        self.db_path = Path(self.td) / "cli_test.db"
        self.lock_path = Path(self.td) / "cli_lock.lock"
        self.fake_home = Path(self.td) / "home"
        self.fake_home.mkdir(parents=True)

        self.orig_env = {
            "ZEROFACTORY_DB": os.environ.get("ZEROFACTORY_DB"),
            "ZEROFACTORY_LOCK_PATH": os.environ.get("ZEROFACTORY_LOCK_PATH"),
            "ZEROFACTORY_DISABLE_DISPATCHER": os.environ.get("ZEROFACTORY_DISABLE_DISPATCHER"),
            "ZEROFACTORY_SKIP_WORKER_SPAWN": os.environ.get("ZEROFACTORY_SKIP_WORKER_SPAWN"),
            "ZEROFACTORY_SKIP_GIT": os.environ.get("ZEROFACTORY_SKIP_GIT"),
            "HOME": os.environ.get("HOME"),
            "HERMES_PROFILE": os.environ.get("HERMES_PROFILE"),
        }

        os.environ["ZEROFACTORY_DB"] = str(self.db_path)
        os.environ["ZEROFACTORY_LOCK_PATH"] = str(self.lock_path)
        os.environ["ZEROFACTORY_DISABLE_DISPATCHER"] = "1"
        os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = "1"
        os.environ["ZEROFACTORY_SKIP_GIT"] = "1"
        os.environ["HOME"] = str(self.fake_home)
        init_db(force=True)

        # Build real CLI parser via __init__.register
        self.parser = argparse.ArgumentParser(prog="hermes zerofactory")
        self.cli_handler = None

        class MockCtx:
            def register_cli_command(ctx_self, name, help, setup_fn, handler_fn):
                setup_fn(self.parser)
                self.cli_handler = handler_fn

        zf_cli.register(MockCtx())
        self.assertIsNotNone(self.cli_handler, "CLI handler must be registered")

    def tearDown(self):
        for k, v in self.orig_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
        shutil.rmtree(self.td, ignore_errors=True)

    def _run_cli(self, args_list: List[str]) -> str:
        """Parse arguments and execute the CLI handler, returning captured stdout."""
        args = self.parser.parse_args(args_list)
        buf = io.StringIO()
        with redirect_stdout(buf):
            self.cli_handler(args)
        return buf.getvalue()

    def test_01_cli_setup_and_sync_profiles(self):
        """CLI setup bootstraps profiles and sync-profiles updates templates."""
        # 1. Setup profiles
        out = self._run_cli(["setup"])
        self.assertIn("Zero Factory Profiles Setup", out)
        profiles_dir = self.fake_home / ".hermes" / "profiles"
        self.assertTrue(profiles_dir.exists())
        for prof in ("zf-orchestrator", "zf-builder", "zf-reviewer"):
            self.assertTrue((profiles_dir / prof).is_dir())
            self.assertTrue((profiles_dir / prof / "SOUL.md").is_file())
            self.assertTrue((profiles_dir / prof / "config.yaml").is_file())

        # 2. Sync profiles
        out_sync = self._run_cli(["sync-profiles"])
        self.assertIn("Zero Factory Profiles Synced", out_sync)

    def test_02_cli_board_crud(self):
        """CLI board create, list, and delete workflow."""
        # Create board
        out_create = self._run_cli([
            "board", "create", "https://github.com/example/cli-demo.git",
            "--description", "Demo Board"
        ])
        self.assertIn("Created board: example-cli-demo", out_create)

        # List boards
        out_list = self._run_cli(["board", "list"])
        self.assertIn("example-cli-demo", out_list)
        self.assertIn("https://github.com/example/cli-demo.git", out_list)

        # Delete board
        out_delete = self._run_cli(["board", "delete", "example-cli-demo"])
        self.assertIn("Deleted board 'example-cli-demo'", out_delete)

        # Verify board is gone
        out_list2 = self._run_cli(["board", "list"])
        self.assertNotIn("example-cli-demo", out_list2)

    def test_03_cli_task_lifecycle_create_move_block_comment(self):
        """CLI task lifecycle: create with description-file & dedup, move, block, comment, list, stats."""
        # Setup board first
        self._run_cli(["board", "create", "https://github.com/example/workflow.git"])

        # 1. Create with description file
        desc_file = Path(self.td) / "task_desc.md"
        desc_file.write_text("Detailed multi-line\ntask description with 'quotes' and $special chars.\n", encoding="utf-8")

        out_create = self._run_cli([
            "create", "CLI Feature Task",
            "--board", "example-workflow",
            "--description-file", str(desc_file),
            "--priority", "P1",
            "--status", "triage",
            "--assignee", "zf-builder",
            "--files", "app/main.py,app/test.py",
            "--category", "bug-fix",
            "--actor", "test-engineer"
        ])
        self.assertIn("Created task zf-", out_create)
        task_id = [part for part in out_create.split() if part.startswith("zf-")][0].rstrip(":")

        # 2. Deduplication check: re-creating identical fingerprint is skipped
        out_dup = self._run_cli([
            "create", "CLI Feature Task Duplicate",
            "--board", "example-workflow",
            "--files", "app/main.py,app/test.py",
            "--category", "bug-fix"
        ])
        self.assertIn("[Duplicate Skipped]", out_dup)

        # 3. List tasks
        out_list = self._run_cli(["list", "--board", "example-workflow", "--status", "triage"])
        self.assertIn(task_id, out_list)
        self.assertIn("CLI Feature Task", out_list)

        # 4. Move task
        out_move = self._run_cli(["move", task_id, "todo", "--actor", "zf-orchestrator"])
        self.assertIn(f"Moved task {task_id} to todo", out_move)

        # 5. Block task with reason
        out_block = self._run_cli(["block", task_id, "--reason", "Waiting on Database Migration", "--actor", "user"])
        self.assertIn(f"Task {task_id} marked as BLOCKED (Waiting on Database Migration)", out_block)

        # 6. Add comment
        out_comment = self._run_cli(["comment", task_id, "Database migration has landed", "--author", "dba-team"])
        self.assertIn(f"Added comment to task {task_id}", out_comment)

        # 7. Check stats
        out_stats = self._run_cli(["stats"])
        self.assertIn("Zero Factory Kanban Statistics", out_stats)
        self.assertIn("Total Tasks:     1", out_stats)
        self.assertIn("Blocked   : 1", out_stats)

    def test_04_cli_check_stuck_and_reap(self):
        """CLI check-stuck audits hung workers and --reap terminates them."""
        self._run_cli(["board", "create", "https://github.com/example/stuck.git"])

        now_ts = int(time.time())
        # Insert a simulated stuck task (running for 3600 seconds with dead PID)
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute("""
                INSERT INTO tasks (id, board_slug, title, status, assignee, priority, metadata, created_at, updated_at)
                VALUES ('zf-stuck-1', 'example-stuck', 'Hung Task Test', 'running', 'zf-builder', 'P1',
                        '{"worker_pid": 9999999, "running_since": 1000}', 1000, 1000)
            """)
            conn.commit()

        # check-stuck inspection
        out_check = self._run_cli(["check-stuck", "--timeout", "60", "--inactivity", "60"])
        self.assertIn("zf-stuck-1", out_check)
        self.assertIn("STUCK", out_check)

        # check-stuck with reap
        out_reap = self._run_cli(["check-stuck", "--timeout", "60", "--inactivity", "60", "--reap"])
        self.assertIn("Reaped 1 stuck task", out_reap)
        self.assertIn("zf-stuck-1", out_reap)

        # Verify task is now blocked in DB
        with sqlite3.connect(str(self.db_path)) as conn:
            status = conn.execute("SELECT status FROM tasks WHERE id = 'zf-stuck-1'").fetchone()[0]
            self.assertEqual(status, "blocked")

    def test_05_cli_cron_and_dispatch(self):
        """CLI cron commands and dispatch trigger."""
        # Cron list
        out_cron = self._run_cli(["cron", "list"])
        self.assertIn("zero-factory-task-queue-check", out_cron)

        # Cron sync
        out_sync = self._run_cli(["cron", "sync"])
        self.assertIn("Synced builtin cron jobs", out_sync)

        # Dispatch command
        out_disp = self._run_cli(["dispatch"])
        self.assertIn("Dispatch result", out_disp)


if __name__ == "__main__":
    unittest.main()
