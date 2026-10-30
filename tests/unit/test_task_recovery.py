"""Unit tests for task recovery, bug reporting, and guardrails."""

import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from fastapi import HTTPException

from dashboard.db import init_db
from dashboard.models import TaskCreate, TaskRecoverRequest, TaskReportBugRequest
from dashboard.routes.tasks import create_task, recover_task, report_task_bug
from paths import ZEROFACTORY_REPO, ZEROFACTORY_GITHUB_URL, ZEROFACTORY_ISSUES_URL
from cron.definitions import CORE_CRON_JOBS, get_all_builtin_cron_jobs


class TestTaskRecovery(unittest.TestCase):
    def setUp(self):
        self.tf = tempfile.NamedTemporaryFile(suffix=".db", delete=False)
        self.db_path = Path(self.tf.name)
        os.environ["ZEROFACTORY_DB"] = str(self.db_path)
        os.environ["ZEROFACTORY_SKIP_DISPATCHER"] = "1"
        init_db(force=True)

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT INTO boards (slug, description, created_at, updated_at) VALUES ('test-board', 'Test Board', 1, 1)"
            )
            conn.execute(
                "INSERT INTO board_repositories (board_slug, repo_alias, git_url, created_at, updated_at) VALUES ('test-board', 'default', 'https://github.com/example/test.git', 1, 1)"
            )
            conn.commit()

    def tearDown(self):
        if self.db_path.exists():
            try:
                self.db_path.unlink()
            except Exception:
                pass

    def test_constants_defined(self):
        """Verify repository constants are canonical."""
        self.assertEqual(ZEROFACTORY_REPO, "hotcode-dev/zerofactory")
        self.assertEqual(ZEROFACTORY_GITHUB_URL, "https://github.com/hotcode-dev/zerofactory")
        self.assertEqual(ZEROFACTORY_ISSUES_URL, "https://github.com/hotcode-dev/zerofactory/issues")

    def test_cron_definition_has_queue_watchdog(self):
        """Verify zero-factory-task-queue-check is registered in CORE_CRON_JOBS."""
        self.assertIn("zero-factory-task-queue-check", CORE_CRON_JOBS)
        job = CORE_CRON_JOBS["zero-factory-task-queue-check"]
        self.assertEqual(job["script"], "zf_queue_watchdog.py")
        self.assertEqual(job["profile"], "zf-orchestrator")
        self.assertTrue(job["enabled"])
        self.assertFalse(job["no_agent"])
        self.assertFalse(job["continuity"])
        self.assertEqual(job["schedule"]["minutes"], 15)

    def test_recover_task_happy_path(self):
        """Orchestrator recovers a stuck task to todo, resets counters, and injects guidance."""
        # 1. Create a task with failure counters and permanently_blocked
        req = TaskCreate(
            title="Stuck Precommit Task",
            description="Failing test",
            board_slug="test-board",
            status="blocked",
            priority="P1",
        )
        task_id = create_task(req)["id"]

        with sqlite3.connect(str(self.db_path)) as conn:
            meta = {
                "blocked_reason_type": "stuck",
                "blocked_reason": "Deterministic precommit failed 3 times",
                "precommit_retries": 3,
                "worker_failure_retries": 2,
                "permanently_blocked": True,
                "awaiting_pr": True,
                "last_precommit_error": "AssertionError: expected 1 got 2",
            }
            conn.execute(
                "UPDATE tasks SET metadata = ? WHERE id = ?",
                (json.dumps(meta), task_id),
            )
            conn.commit()

        # 2. Recover as zf-orchestrator
        res = recover_task(
            task_id,
            TaskRecoverRequest(
                guidance="Please update the test mock return value to 2 in test_auth.py",
                actor="zf-orchestrator",
            ),
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "todo")
        self.assertEqual(res["assignee"], "zf-builder")
        self.assertEqual(res["orchestrator_recovery_count"], 1)

        # 3. Verify DB state
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            self.assertEqual(row["status"], "todo")
            self.assertEqual(row["assignee"], "zf-builder")
            saved_meta = json.loads(row["metadata"])
            self.assertNotIn("precommit_retries", saved_meta)
            self.assertNotIn("worker_failure_retries", saved_meta)
            self.assertNotIn("permanently_blocked", saved_meta)
            self.assertNotIn("awaiting_pr", saved_meta)
            self.assertEqual(saved_meta.get("orchestrator_recovery_count"), 1)
            self.assertEqual(saved_meta.get("recovered_by"), "zf-orchestrator")

            # Verify guidance comment was posted
            comments = conn.execute("SELECT * FROM task_comments WHERE task_id = ?", (task_id,)).fetchall()
            self.assertEqual(len(comments), 1)
            self.assertIn("Task Recovery", comments[0]["body"])
            self.assertIn("test_auth.py", comments[0]["body"])

    def test_recover_task_guardrail_exceeded(self):
        """Second autonomous recovery attempt by zf-orchestrator is rejected."""
        req = TaskCreate(
            title="Repeat Failure Task",
            board_slug="test-board",
            status="blocked",
            priority="P1",
        )
        task_id = create_task(req)["id"]

        with sqlite3.connect(str(self.db_path)) as conn:
            meta = {
                "blocked_reason_type": "stuck",
                "orchestrator_recovery_count": 1,
            }
            conn.execute(
                "UPDATE tasks SET metadata = ? WHERE id = ?",
                (json.dumps(meta), task_id),
            )
            conn.commit()

        # Orchestrator recovery attempt should raise HTTPException 400
        with self.assertRaises(HTTPException) as ctx:
            recover_task(
                task_id,
                TaskRecoverRequest(
                    guidance="Trying again",
                    actor="zf-orchestrator",
                ),
            )
        self.assertEqual(ctx.exception.status_code, 400)
        self.assertIn("maximum orchestrator recovery limit", ctx.exception.detail)

    def test_recover_task_human_override_allowed(self):
        """A human developer can recover a task even if orchestrator recovery limit was reached."""
        req = TaskCreate(
            title="Human Recover Task",
            board_slug="test-board",
            status="blocked",
            priority="P1",
        )
        task_id = create_task(req)["id"]

        with sqlite3.connect(str(self.db_path)) as conn:
            meta = {
                "blocked_reason_type": "stuck",
                "orchestrator_recovery_count": 1,
            }
            conn.execute(
                "UPDATE tasks SET metadata = ? WHERE id = ?",
                (json.dumps(meta), task_id),
            )
            conn.commit()

        # Human recovery succeeds
        res = recover_task(
            task_id,
            TaskRecoverRequest(
                guidance="Human fixed the environment",
                actor="user",
            ),
        )
        self.assertTrue(res["ok"])
        self.assertEqual(res["status"], "todo")

    @patch("subprocess.run")
    def test_report_task_bug_duplicate_detection(self, mock_run):
        """Detects existing open issue on hotcode-dev/zerofactory and avoids duplicate creation."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout=json.dumps([
                {
                    "number": 105,
                    "title": "SQLite operational error database is locked",
                    "url": "https://github.com/hotcode-dev/zerofactory/issues/105",
                }
            ]),
        )

        req = TaskCreate(
            title="Database Locked Crash",
            board_slug="test-board",
            status="running",
        )
        task_id = create_task(req)["id"]

        res = report_task_bug(
            task_id,
            TaskReportBugRequest(
                title="SQLite operational error database is locked",
                body="Database lock during concurrent dispatch tick",
                actor="zf-orchestrator",
                create_issue=True,
            ),
        )

        self.assertTrue(res["ok"])
        self.assertTrue(res.get("duplicate"))
        self.assertEqual(res["issue_url"], "https://github.com/hotcode-dev/zerofactory/issues/105")

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            self.assertEqual(row["status"], "blocked")
            meta = json.loads(row["metadata"])
            self.assertEqual(meta["blocked_reason_type"], "human-gate")
            self.assertIn("105", meta["blocked_reason"])

    @patch("subprocess.run")
    def test_report_task_bug_create_success(self, mock_run):
        """Creates new issue on hotcode-dev/zerofactory when no duplicate exists."""
        # 1. First run: check existing issues (empty)
        list_res = MagicMock(returncode=0, stdout="[]")
        # 2. Second run: create issue
        create_res = MagicMock(
            returncode=0,
            stdout="https://github.com/hotcode-dev/zerofactory/issues/120\n",
        )
        mock_run.side_effect = [list_res, create_res]

        req = TaskCreate(
            title="Worktree isolation error",
            board_slug="test-board",
            status="running",
        )
        task_id = create_task(req)["id"]

        res = report_task_bug(
            task_id,
            TaskReportBugRequest(
                title="Git worktree add failed with exit code 128",
                body="Fatal: cannot create worktree directory",
                actor="zf-orchestrator",
                create_issue=True,
            ),
        )

        self.assertTrue(res["ok"])
        self.assertFalse(res.get("duplicate", False))
        self.assertEqual(res["issue_url"], "https://github.com/hotcode-dev/zerofactory/issues/120")

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            self.assertEqual(row["status"], "blocked")
            meta = json.loads(row["metadata"])
            self.assertEqual(meta["zf_bug_report"]["issue_url"], "https://github.com/hotcode-dev/zerofactory/issues/120")

    @patch("subprocess.run")
    def test_report_task_bug_optional_local_recording_default(self, mock_run):
        """When issue creation is not requested (default False), records defect locally without calling gh."""
        req = TaskCreate(
            title="Internal deadlock error",
            board_slug="test-board",
            status="running",
        )
        task_id = create_task(req)["id"]

        res = report_task_bug(
            task_id,
            TaskReportBugRequest(
                title="Internal dispatcher threading exception",
                body="Thread deadlocked on lock acquisition",
                actor="zf-orchestrator",
            ),
        )

        mock_run.assert_not_called()
        self.assertTrue(res["ok"])
        self.assertFalse(res.get("issue_created", True))
        self.assertIsNone(res.get("issue_url"))
        self.assertIn("skipped", res["message"])

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            self.assertEqual(row["status"], "blocked")
            meta = json.loads(row["metadata"])
            self.assertFalse(meta["zf_bug_report"]["issue_created"])
            self.assertEqual(meta["zf_bug_report"]["title"], "Internal dispatcher threading exception")
            self.assertIn("Internal dispatcher threading exception", meta["blocked_reason"])

    @patch("subprocess.run")
    def test_report_task_bug_explicit_no_issue(self, mock_run):
        """When create_issue=False is passed explicitly, skips gh even if global setting is enabled."""
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('auto_create_github_issues', 'true', 100)"
            )
            conn.commit()

        req = TaskCreate(
            title="Internal hook error",
            board_slug="test-board",
            status="running",
        )
        task_id = create_task(req)["id"]

        res = report_task_bug(
            task_id,
            TaskReportBugRequest(
                title="Hook callback raised exception",
                body="Error in on_dispatch_tick",
                actor="user",
                create_issue=False,
            ),
        )

        mock_run.assert_not_called()
        self.assertTrue(res["ok"])
        self.assertFalse(res.get("issue_created", True))

    def test_cli_recover_command(self):
        """CLI recover subcommand invokes _recover_task and prints confirmation."""
        import io
        import contextlib
        import argparse
        import __init__ as zf_cli

        fake_ctx = MagicMock()
        zf_cli.register(fake_ctx)
        cmd_runner = fake_ctx.register_cli_command.call_args[1]["handler_fn"]

        req = TaskCreate(
            title="CLI Recover Task",
            board_slug="test-board",
            status="blocked",
            priority="P1",
        )
        task_id = create_task(req)["id"]

        args = argparse.Namespace(
            action="recover",
            task_id=task_id,
            guidance="Fix syntax on line 10",
            actor="zf-orchestrator",
        )

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cmd_runner(args)

        out = buf.getvalue()
        self.assertIn("Recovered task", out)
        self.assertIn(task_id, out)
        self.assertIn("Fix syntax on line 10", out)

    @patch("subprocess.run")
    def test_cli_report_bug_command(self, mock_run):
        """CLI report-bug subcommand invokes _report_task_bug and prints issue URL."""
        import io
        import contextlib
        import argparse
        import __init__ as zf_cli

        fake_ctx = MagicMock()
        zf_cli.register(fake_ctx)
        cmd_runner = fake_ctx.register_cli_command.call_args[1]["handler_fn"]

        list_res = MagicMock(returncode=0, stdout="[]")
        create_res = MagicMock(
            returncode=0,
            stdout="https://github.com/hotcode-dev/zerofactory/issues/130\n",
        )
        mock_run.side_effect = [list_res, create_res]

        req = TaskCreate(
            title="CLI Report Bug Task",
            board_slug="test-board",
            status="running",
            priority="P1",
        )
        task_id = create_task(req)["id"]

        args = argparse.Namespace(
            action="report-bug",
            task_id=task_id,
            title="Subprocess deadlock in git worktree add",
            body="Deadlock trace in git_ops.py",
            actor="zf-orchestrator",
            create_issue=True,
        )

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cmd_runner(args)

        out = buf.getvalue()
        self.assertIn("Zero Factory defect reported to hotcode-dev/zerofactory", out)
        self.assertIn("issues/130", out)

    @patch("subprocess.run")
    def test_cli_report_bug_no_issue_command(self, mock_run):
        """CLI report-bug with --no-issue records defect locally without calling gh."""
        import io
        import contextlib
        import argparse
        import __init__ as zf_cli

        fake_ctx = MagicMock()
        zf_cli.register(fake_ctx)
        cmd_runner = fake_ctx.register_cli_command.call_args[1]["handler_fn"]

        req = TaskCreate(
            title="CLI Report Bug No Issue Task",
            board_slug="test-board",
            status="running",
            priority="P1",
        )
        task_id = create_task(req)["id"]

        args = argparse.Namespace(
            action="report-bug",
            task_id=task_id,
            title="Worker crash on invalid json",
            body="Syntax error trace",
            actor="user",
            create_issue=False,
        )

        buf = io.StringIO()
        with contextlib.redirect_stdout(buf):
            cmd_runner(args)

        gh_calls = [c for c in mock_run.call_args_list if c.args and c.args[0] and c.args[0][0] == "gh"]
        self.assertEqual(len(gh_calls), 0)
        out = buf.getvalue()
        self.assertIn("Zero Factory defect recorded locally", out)
        self.assertIn("GitHub issue creation skipped", out)

    def test_sanitize_defect_body(self):
        """Sanitizer redacts home dir, API keys, and session tokens."""
        from dashboard.routes.tasks import _sanitize_defect_body
        from pathlib import Path

        home = str(Path.home())
        raw_text = f"Crash at {home}/git/myrepo with key sk-12345678901234567890 and token ghp_abcdefghijklmnopqrstu"
        sanitized = _sanitize_defect_body(raw_text)

        self.assertNotIn(home, sanitized)
        self.assertIn("~/git/myrepo", sanitized)
        self.assertNotIn("sk-12345678901234567890", sanitized)
        self.assertIn("sk-***REDACTED***", sanitized)
        self.assertNotIn("ghp_abcdefghijklmnopqrstu", sanitized)
        self.assertIn("ghp_***REDACTED***", sanitized)
