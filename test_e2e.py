"""Comprehensive End-to-End (E2E) Test Suite for Zero Factory.

Validates the full autonomous multi-agent software factory across all subsystems:
1. TestZeroFactoryCLIE2E: Complete hermes zerofactory CLI command workflows.
2. TestMultiAgentLifecycleE2E: Autonomous multi-agent pipeline (builder worktree,
   PR lifecycle, 3-round reviews, changes requested, merge conflicts, approvals, done).
3. TestAutomationScriptsE2E: Standalone background scripts (watchdog, scanner gate, daily stats).
4. TestPluginAPIE2E: Full REST API surface, dependencies DAG, strict activity actors, retention.
5. TestConcurrencyAndResilienceE2E: Concurrency limits, flock locks, atomic CAS, hung timeouts.
"""

from __future__ import annotations

import argparse
import fcntl
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, patch

# Configure hermetic test environment before importing plugin modules
_test_root = tempfile.TemporaryDirectory(prefix="zf-e2e-root-")
_test_db_path = Path(_test_root.name) / "e2e_zerofactory.db"
_test_lock_path = Path(_test_root.name) / "e2e_dispatcher.lock"

os.environ["ZEROFACTORY_DB"] = str(_test_db_path)
os.environ["ZEROFACTORY_LOCK_PATH"] = str(_test_lock_path)
os.environ["ZEROFACTORY_SKIP_GIT"] = "1"
os.environ["ZEROFACTORY_SKIP_CRON_SYNC"] = "1"
os.environ["ZEROFACTORY_DISABLE_DISPATCHER"] = "1"
os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = "1"

from fastapi import FastAPI
from fastapi.testclient import TestClient

import __init__ as zf_cli
import builtin_cron
import dispatcher
import paths
import profile_manager
import settings
from dashboard.plugin_api import (
    ACTIVITY_ACTORS,
    DEFAULT_ACTIVITY_RETENTION_DAYS,
    BoardCreate,
    BoardUpdate,
    CommentCreate,
    DependencyLink,
    TaskCreate,
    TaskMove,
    TaskUpdate,
    add_comment,
    add_dependency,
    create_board,
    create_task,
    delete_board,
    get_activities,
    get_db_conn,
    get_db_path,
    get_stats,
    get_task,
    get_task_session,
    init_db,
    list_boards,
    list_tasks,
    move_task,
    prune_old_activity,
    remove_dependency,
    router,
    trigger_dispatch,
    update_task,
)

# Shared FastAPI test client
api_app = FastAPI()
api_app.include_router(router, prefix="/api/plugins/zerofactory")
client = TestClient(api_app)


# ============================================================================
# 1. CLI End-to-End Tests
# ============================================================================

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
            "HOME": os.environ.get("HOME"),
            "HERMES_PROFILE": os.environ.get("HERMES_PROFILE"),
        }

        os.environ["ZEROFACTORY_DB"] = str(self.db_path)
        os.environ["ZEROFACTORY_LOCK_PATH"] = str(self.lock_path)
        os.environ["ZEROFACTORY_DISABLE_DISPATCHER"] = "1"
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
        out_move = self._run_cli(["move", task_id, "ready", "--actor", "zf-orchestrator"])
        self.assertIn(f"Moved task {task_id} to ready", out_move)

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
        self.assertIn("zero-factory-daily-report", out_cron)

        # Cron sync
        out_sync = self._run_cli(["cron", "sync"])
        self.assertIn("Synced builtin cron jobs", out_sync)

        # Dispatch command
        out_disp = self._run_cli(["dispatch"])
        self.assertIn("Dispatch result", out_disp)


# ============================================================================
# 2. Multi-Agent Lifecycle & Git Worktrees E2E Tests
# ============================================================================

class TestMultiAgentLifecycleE2E(unittest.TestCase):
    """End-to-End validation of the autonomous multi-agent pipeline and Git worktrees."""

    def setUp(self):
        self.td = tempfile.mkdtemp(prefix="zf-lifecycle-e2e-")
        self.db_path = Path(self.td) / "lifecycle.db"
        self.lock_path = Path(self.td) / "lifecycle_lock.lock"
        self.fake_home = Path(self.td) / "home"
        self.fake_home.mkdir(parents=True)

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
        os.environ["HOME"] = str(self.fake_home)
        os.environ.pop("ZEROFACTORY_SKIP_GIT", None)  # Enable real git operations
        os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = "1"  # Workers driven deterministically
        init_db(force=True)

        # Initialize real git test repository under fake home
        self.repo_dir = self.fake_home / "git" / "main_repo"
        self.repo_dir.mkdir(parents=True)
        self._git(self.repo_dir, "init", "-b", "main")
        self._git(self.repo_dir, "config", "user.name", "ZeroFactory E2E")
        self._git(self.repo_dir, "config", "user.email", "e2e@zerofactory.ai")
        (self.repo_dir / "README.md").write_text("# Zero Factory E2E Repo\n")
        self._git(self.repo_dir, "add", "README.md")
        self._git(self.repo_dir, "commit", "-m", "chore: initial commit")

        # Create Kanban board pointing to this local git repository
        b_res = create_board(BoardCreate(
            git_url=str(self.repo_dir),
            description="E2E Lifecycle Repository"
        ))
        self.board_slug = b_res["slug"]

    def tearDown(self):
        for k, v in self.orig_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
        shutil.rmtree(self.td, ignore_errors=True)

    def _git(self, cwd: Path, *args: str) -> str:
        res = subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)
        return res.stdout.strip()

    def test_01_full_delivery_cycle_builder_review_rounds_approval_and_merge(self):
        """Complete E2E autonomous delivery flow:
        Triage -> Todo -> Ready -> Running (Builder) -> PR -> 3 Review Rounds -> Approved -> Merged -> Done.
        """
        # Step 1: Create goal task in 'ready'
        t_res = create_task(TaskCreate(
            board_slug=self.board_slug,
            title="Implement User Authentication",
            description="Add JWT token generation and validation tests",
            status="ready",
            assignee="zf-builder",
            priority="P1"
        ))
        task_id = t_res["id"]

        # Step 2: Dispatcher Promotion Cycle -> ready -> running with worktree
        disp_res1 = dispatcher.run_dispatch_cycle(self.db_path)
        self.assertTrue(disp_res1["ok"])

        # Verify task is running and worktree was created
        t_info1 = get_task(task_id)["task"]
        self.assertEqual(t_info1["status"], "running")
        self.assertEqual(t_info1["assignee"], "zf-builder")
        self.assertIsNotNone(t_info1.get("workspace_path"))
        worktree_path = Path(t_info1["workspace_path"])
        self.assertTrue(worktree_path.exists())
        self.assertTrue((worktree_path / ".git").exists())

        # Step 3: zf-builder commits code and tests in worktree
        (worktree_path / "auth.py").write_text("def generate_jwt(): return 'token-123'\n")
        (worktree_path / "test_auth.py").write_text("from auth import generate_jwt\ndef test(): assert generate_jwt()\n")
        self._git(worktree_path, "add", ".")
        self._git(worktree_path, "commit", "-m", "feat(auth): add JWT token generator and tests")

        # Builder completes implementation and marks done for packaging
        move_task(task_id, TaskMove(status="done", actor="zf-builder"))

        # Step 4: Dispatcher packages work and opens PR
        pr_url = "https://github.com/example/repo/pull/101"
        fake_gh_state = {"state": "OPEN", "reviewDecision": None, "mergeable": "MERGEABLE", "url": pr_url}
        orig_run = subprocess.run

        def mock_gh_run(cmd, *args, **kwargs):
            if isinstance(cmd, (list, tuple)):
                if len(cmd) >= 2 and cmd[0] == "git" and cmd[1] == "push":
                    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
                if len(cmd) >= 1 and cmd[0] == "gh":
                    if "create" in cmd:
                        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=pr_url, stderr="")
                    elif "view" in cmd:
                        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=json.dumps(fake_gh_state), stderr="")
                    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
            return orig_run(cmd, *args, **kwargs)

        with patch("subprocess.run", side_effect=mock_gh_run):
            disp_res2 = dispatcher.run_dispatch_cycle(self.db_path)
            self.assertTrue(disp_res2["ok"])

        # Task has PR and is routed to zf-reviewer
        t_info2 = get_task(task_id)["task"]
        self.assertEqual(t_info2["assignee"], "zf-reviewer")
        self.assertEqual(t_info2["pr_url"], pr_url)

        # Step 5: Review Rounds 1, 2, 3
        # Round 1: Correctness / Tests
        add_comment(task_id, CommentCreate(author="zf-reviewer", body="Round 1 Review: Test coverage is sufficient. Edge cases validated."))
        # Round 2: Performance
        add_comment(task_id, CommentCreate(author="zf-reviewer", body="Round 2 Review: Token generation performance verified."))
        # Round 3: Clean code & approval
        add_comment(task_id, CommentCreate(author="zf-reviewer", body="Round 3 Review: Code clean and formatted. Ready for human merge."))

        # Reviewer submits review, waiting for approval
        move_task(task_id, TaskMove(status="blocked", actor="zf-reviewer"))

        # Step 6: PR is Approved
        fake_gh_state["reviewDecision"] = "APPROVED"
        with patch("subprocess.run", side_effect=mock_gh_run):
            disp_res3 = dispatcher.run_dispatch_cycle(self.db_path)
            self.assertTrue(disp_res3["ok"])

        t_info3 = get_task(task_id)["task"]
        self.assertEqual(t_info3["status"], "blocked")
        self.assertIn("[Human Review]", t_info3["title"])

        # Step 7: PR is Merged
        fake_gh_state["state"] = "MERGED"
        with patch("subprocess.run", side_effect=mock_gh_run):
            disp_res4 = dispatcher.run_dispatch_cycle(self.db_path)
            self.assertTrue(disp_res4["ok"])

        # Task is done and worktree is cleaned up
        t_info4 = get_task(task_id)["task"]
        self.assertEqual(t_info4["status"], "done")
        self.assertFalse(worktree_path.exists(), "Worktree directory must be cleaned up on merge")

        # Verify activity timeline records full history
        acts = get_activities(limit=50)["activities"]
        actions = [a["action"] for a in acts if a["task_id"] == task_id]
        self.assertIn("start", actions)
        self.assertIn("comment", actions)
        self.assertIn("approved", actions)
        self.assertIn("merged", actions)

    def test_02_reviewer_changes_requested_loop(self):
        """Reviewer requests changes -> routes back to zf-builder -> builder fixes -> re-submits."""
        t_res = create_task(TaskCreate(
            board_slug=self.board_slug,
            title="Refactor Cache Layer",
            status="ready",
            assignee="zf-builder"
        ))
        task_id = t_res["id"]

        # Run cycle to promote to running and setup worktree
        dispatcher.run_dispatch_cycle(self.db_path)
        t_info = get_task(task_id)["task"]
        worktree_path = Path(t_info["workspace_path"])
        (worktree_path / "cache.py").write_text("class Cache: pass\n")
        self._git(worktree_path, "add", ".")
        self._git(worktree_path, "commit", "-m", "feat: initial cache")

        # Builder finishes initial implementation
        move_task(task_id, TaskMove(status="done", actor="zf-builder"))

        # Open PR -> moves to reviewer
        pr_url = "https://github.com/example/repo/pull/102"
        gh_state = {"state": "OPEN", "reviewDecision": "CHANGES_REQUESTED", "mergeable": "MERGEABLE", "url": pr_url}
        orig_run = subprocess.run

        def mock_gh(cmd, *a, **kw):
            if isinstance(cmd, (list, tuple)):
                if len(cmd) >= 2 and cmd[0] == "git" and cmd[1] == "push":
                    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
                if len(cmd) >= 1 and cmd[0] == "gh":
                    if "view" in cmd:
                        return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=json.dumps(gh_state), stderr="")
                    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=pr_url, stderr="")
            return orig_run(cmd, *a, **kw)

        with patch("subprocess.run", side_effect=mock_gh):
            # First cycle opens PR and routes to reviewer
            dispatcher.run_dispatch_cycle(self.db_path)
            # Reviewer requests changes while in blocked
            move_task(task_id, TaskMove(status="blocked", actor="zf-reviewer"))
            # Second cycle detects CHANGES_REQUESTED and routes back to builder
            dispatcher.run_dispatch_cycle(self.db_path)

        t_after_changes = get_task(task_id)["task"]
        self.assertEqual(t_after_changes["status"], "ready")
        self.assertEqual(t_after_changes["assignee"], "zf-builder")

        # Builder pushes update
        (worktree_path / "cache.py").write_text("class Cache:\n    def get(self): return None\n")
        self._git(worktree_path, "add", ".")
        self._git(worktree_path, "commit", "-m", "fix: implement get method")
        move_task(task_id, TaskMove(status="done", actor="zf-builder"))

        # Next cycle routes back to reviewer
        gh_state["reviewDecision"] = None
        with patch("subprocess.run", side_effect=mock_gh):
            dispatcher.run_dispatch_cycle(self.db_path)

        t_rerouted = get_task(task_id)["task"]
        self.assertEqual(t_rerouted["assignee"], "zf-reviewer")

    def test_03_merge_conflict_detection_and_builder_reroute(self):
        """PR merge conflict routes task back to zf-builder with [PR Conflict] tag."""
        # Create a worktree for reviewer task
        rev_ws = self.fake_home / "git" / "main_repo-worktrees" / "ws_conf"
        rev_ws.parent.mkdir(parents=True, exist_ok=True)
        subprocess.run(
            ["git", "worktree", "add", str(rev_ws), "-b", "task/conf"],
            cwd=str(self.repo_dir), check=True, capture_output=True
        )

        pr_url = "https://github.com/example/repo/pull/103"
        t_res = create_task(TaskCreate(
            board_slug=self.board_slug,
            title="Add Config Parser [PR Opened by zf-builder]",
            status="blocked",
            assignee="zf-reviewer"
        ))
        task_id = t_res["id"]

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "UPDATE tasks SET pr_url = ?, branch_name = 'task/conf', workspace_path = ? WHERE id = ?",
                (pr_url, str(rev_ws), task_id)
            )
            conn.commit()

        gh_state = {"state": "OPEN", "reviewDecision": None, "mergeable": "CONFLICTING", "url": pr_url}
        orig_run = subprocess.run

        def mock_gh(cmd, *a, **kw):
            if isinstance(cmd, (list, tuple)):
                if len(cmd) >= 3 and cmd[0] == "gh" and cmd[1] == "pr" and cmd[2] == "view":
                    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout=json.dumps(gh_state), stderr="")
                if len(cmd) >= 2 and cmd[0] == "git" and cmd[1] == "push":
                    return subprocess.CompletedProcess(args=cmd, returncode=0, stdout="", stderr="")
            return orig_run(cmd, *a, **kw)

        with patch("subprocess.run", side_effect=mock_gh):
            dispatcher.run_dispatch_cycle(self.db_path)

        t_conf = get_task(task_id)["task"]
        self.assertEqual(t_conf["status"], "ready")
        self.assertEqual(t_conf["assignee"], "zf-builder")
        self.assertIn("[PR Conflict]", t_conf["title"])

    def test_04_dependency_dag_blocking_and_cascading_unblock(self):
        """Parent task completion unblocks dependent child task."""
        # Parent task
        t_parent = create_task(TaskCreate(
            board_slug=self.board_slug,
            title="Database Schema Setup",
            status="running",
            assignee="zf-builder"
        ))["id"]

        # Child task blocked on parent
        t_child = create_task(TaskCreate(
            board_slug=self.board_slug,
            title="API Endpoints Setup",
            status="blocked",
            assignee="zf-builder"
        ))["id"]

        add_dependency(t_parent, DependencyLink(parent_id=t_parent, child_id=t_child, link_type="blocks"))

        # While parent is running, dispatch does not unblock child
        dispatcher.run_dispatch_cycle(self.db_path)
        self.assertEqual(get_task(t_child)["task"]["status"], "blocked")

        # Mark parent as done
        move_task(t_parent, TaskMove(status="done", actor="user"))

        # Next dispatch automatically unblocks child
        res = dispatcher.run_dispatch_cycle(self.db_path)
        self.assertTrue(res["ok"])
        self.assertEqual(res.get("unblocked"), 1)
        # Child is unblocked and promoted/dispatched
        self.assertIn(get_task(t_child)["task"]["status"], ("ready", "running"))
        acts = get_activities(limit=20)["activities"]
        self.assertTrue(any(a["action"] == "unblock" for a in acts))


# ============================================================================
# 3. Background Automation Scripts E2E Tests
# ============================================================================

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

        self.scripts_dir = Path(__file__).resolve().parent / "scripts"

    def tearDown(self):
        for k, v in self.orig_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
        shutil.rmtree(self.td, ignore_errors=True)

    def _run_script(self, script_name: str, args: List[str] = None, cwd: Optional[Path] = None, extra_env: Dict[str, str] = None) -> tuple[int, str]:
        cmd = [sys.executable, str(self.scripts_dir / script_name)] + (args or [])
        python_path = os.pathsep.join([str(Path(__file__).resolve().parent)] + sys.path)
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


# ============================================================================
# 4. REST API & Storage Engine E2E Tests
# ============================================================================

class TestPluginAPIE2E(unittest.TestCase):
    """End-to-End validation of FastAPI REST backend, activities, and DB retention."""

    def setUp(self):
        self.td = tempfile.mkdtemp(prefix="zf-api-e2e-")
        self.db_path = Path(self.td) / "api_test.db"
        self.lock_path = Path(self.td) / "api_lock.lock"

        self.orig_env = {
            "ZEROFACTORY_DB": os.environ.get("ZEROFACTORY_DB"),
            "ZEROFACTORY_LOCK_PATH": os.environ.get("ZEROFACTORY_LOCK_PATH"),
            "ZEROFACTORY_DISABLE_DISPATCHER": os.environ.get("ZEROFACTORY_DISABLE_DISPATCHER"),
        }

        os.environ["ZEROFACTORY_DB"] = str(self.db_path)
        os.environ["ZEROFACTORY_LOCK_PATH"] = str(self.lock_path)
        os.environ["ZEROFACTORY_DISABLE_DISPATCHER"] = "1"
        init_db(force=True)

    def tearDown(self):
        for k, v in self.orig_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
        shutil.rmtree(self.td, ignore_errors=True)

    def test_01_boards_api_crud_and_limits(self):
        """Boards REST API: create, read, update max_concurrent_running, delete."""
        # Create
        res = client.post("/api/plugins/zerofactory/boards", json={
            "git_url": "https://github.com/my-org/api-service.git",
            "description": "API Gateway Service"
        })
        self.assertEqual(res.status_code, 200)
        slug = res.json()["slug"]
        self.assertEqual(slug, "my-org-api-service")

        # List
        res_list = client.get("/api/plugins/zerofactory/boards")
        self.assertEqual(res_list.status_code, 200)
        self.assertTrue(any(b["slug"] == slug for b in res_list.json()["boards"]))

        # Patch max_concurrent_running
        res_patch = client.patch(f"/api/plugins/zerofactory/boards/{slug}", json={
            "max_concurrent_running": 5
        })
        self.assertEqual(res_patch.status_code, 200)
        self.assertTrue(res_patch.json()["ok"])

        # Verify updated board
        boards = client.get("/api/plugins/zerofactory/boards").json()["boards"]
        target = next(b for b in boards if b["slug"] == slug)
        self.assertEqual(target["max_concurrent_running"], 5)

        # Delete
        res_del = client.delete(f"/api/plugins/zerofactory/boards/{slug}")
        self.assertEqual(res_del.status_code, 200)
        self.assertTrue(res_del.json()["ok"])

    def test_02_tasks_api_lifecycle_and_dependencies(self):
        """Tasks REST API: CRUD, moves, comments, dependency DAG."""
        client.post("/api/plugins/zerofactory/boards", json={"git_url": "https://github.com/my-org/task-api.git"})

        # Create Task A and Task B
        res_a = client.post("/api/plugins/zerofactory/tasks", json={
            "board_slug": "my-org-task-api",
            "title": "Task A (Base)",
            "status": "todo",
            "priority": "P1"
        })
        id_a = res_a.json()["id"]

        res_b = client.post("/api/plugins/zerofactory/tasks", json={
            "board_slug": "my-org-task-api",
            "title": "Task B (Dependent)",
            "status": "todo",
            "priority": "P2"
        })
        id_b = res_b.json()["id"]

        # Link dependency (A blocks B)
        res_link = client.post(f"/api/plugins/zerofactory/tasks/{id_a}/dependencies", json={
            "parent_id": id_a,
            "child_id": id_b
        })
        self.assertEqual(res_link.status_code, 200)

        # Verify dependency linked
        task_b = client.get(f"/api/plugins/zerofactory/tasks/{id_b}").json()["task"]
        self.assertIn(id_a, [p["id"] for p in task_b.get("parents", [])])

        # Remove dependency: DELETE /tasks/{child_id}/dependencies/{parent_id}
        res_unlink = client.delete(f"/api/plugins/zerofactory/tasks/{id_b}/dependencies/{id_a}")
        self.assertEqual(res_unlink.status_code, 200)

    def test_03_activities_api_strict_actors_and_filters(self):
        """Activities API strictly enforces 6 canonical actors and supports filters & search."""
        client.post("/api/plugins/zerofactory/boards", json={"git_url": "https://github.com/my-org/act.git"})
        t_id = client.post("/api/plugins/zerofactory/tasks", json={
            "board_slug": "my-org-act",
            "title": "Activity Test"
        }).json()["id"]

        now = int(time.time())
        # Log activities with various actors and recent timestamps
        with get_db_conn() as conn:
            conn.execute("INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'start', 'Worker dispatched', ?)", (t_id, now - 40))
            conn.execute("INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'zf-builder', 'worker_done', 'Finished coding', ?)", (t_id, now - 30))
            conn.execute("INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'zf-reviewer', 'approved', 'PR approved', ?)", (t_id, now - 20))
            conn.execute("INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'user', 'comment', 'Manual test passed', ?)", (t_id, now - 10))
            conn.execute("INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'custom-bot', 'sync', 'Webhook fired', ?)", (t_id, now))
            conn.commit()

        # Query all activities
        res = client.get("/api/plugins/zerofactory/activities")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertEqual(data["filter_options"]["actors"], ACTIVITY_ACTORS)

        # Every returned activity has actor strictly in ACTIVITY_ACTORS
        for act in data["activities"]:
            self.assertIn(act["actor"], ACTIVITY_ACTORS)

        # Custom-bot should map to 'other'
        other_acts = [a for a in data["activities"] if a["action"] == "sync"]
        self.assertTrue(len(other_acts) >= 1)
        self.assertEqual(other_acts[0]["actor"], "other")

    def test_04_global_settings_and_retention_prune(self):
        """Settings API GET/PATCH and database retention prune."""
        # GET settings
        res = client.get("/api/plugins/zerofactory/settings")
        self.assertEqual(res.status_code, 200)
        s = res.json()["settings"]
        self.assertEqual(s["activity_retention_days"], DEFAULT_ACTIVITY_RETENTION_DAYS)

        # PATCH settings
        res_patch = client.patch("/api/plugins/zerofactory/settings", json={
            "max_active_tasks": 15,
            "activity_retention_days": 7
        })
        self.assertEqual(res_patch.status_code, 200)
        self.assertEqual(res_patch.json()["settings"]["activity_retention_days"], 7)

        # Test activity retention prune
        now = int(time.time())
        old_time = now - (10 * 86400)  # 10 days ago (past 7 days retention)
        recent_time = now - (2 * 86400) # 2 days ago

        with get_db_conn() as conn:
            conn.execute("INSERT OR IGNORE INTO boards (slug, created_at, updated_at) VALUES ('b-ret', 1, 1)")
            conn.execute("INSERT OR IGNORE INTO tasks (id, board_slug, title, created_at, updated_at) VALUES ('t-ret', 'b-ret', 'Ret Task', 1, 1)")
            conn.execute("INSERT INTO task_activity (task_id, actor, action, created_at) VALUES ('t-ret', 'user', 'old_action', ?)", (old_time,))
            conn.execute("INSERT INTO task_activity (task_id, actor, action, created_at) VALUES ('t-ret', 'user', 'recent_action', ?)", (recent_time,))
            conn.commit()

        # Run prune
        deleted = prune_old_activity(retention_days=7)
        self.assertEqual(deleted, 1)

        with get_db_conn() as conn:
            acts = conn.execute("SELECT action FROM task_activity WHERE task_id = 't-ret'").fetchall()
            actions = [r[0] for r in acts]
            self.assertIn("recent_action", actions)
            self.assertNotIn("old_action", actions)


# ============================================================================
# 5. Concurrency, Limits & Fault Tolerance E2E Tests
# ============================================================================

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
        client.patch("/api/plugins/zerofactory/boards/example-cap", json={"max_concurrent_running": 2})

        # Create 4 tasks in ready
        for i in range(1, 5):
            create_task(TaskCreate(
                board_slug="example-cap",
                title=f"Parallel Task {i}",
                status="ready",
                assignee="zf-builder"
            ))

        # Run dispatch cycle
        res = dispatcher.run_dispatch_cycle(self.db_path)
        self.assertTrue(res["ok"])

        # Exactly 2 should be running, 2 remain in ready
        running_tasks = list_tasks(board="example-cap", status="running")["tasks"]
        ready_tasks = list_tasks(board="example-cap", status="ready")["tasks"]
        self.assertEqual(len(running_tasks), 2)
        self.assertEqual(len(ready_tasks), 2)

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


if __name__ == "__main__":
    unittest.main()
