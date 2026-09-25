"""End-to-End validation of the autonomous multi-agent pipeline and Git worktrees."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import dispatcher
from dashboard.plugin_api import (
    BoardCreate,
    CommentCreate,
    DependencyLink,
    TaskCreate,
    TaskMove,
    add_comment,
    add_dependency,
    create_board,
    create_task,
    get_activities,
    get_task,
    init_db,
    move_task,
)


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
        Triage -> Todo -> Running (Builder) -> PR -> 3 Review Rounds -> Approved -> Merged -> Done.
        """
        # Step 1: Create goal task in 'todo'
        t_res = create_task(TaskCreate(
            board_slug=self.board_slug,
            title="Implement User Authentication",
            description="Add JWT token generation and validation tests",
            status="todo",
            assignee="zf-builder",
            priority="P1"
        ))
        task_id = t_res["id"]

        # Step 2: Dispatcher dispatch cycle -> todo -> running with worktree
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
            status="todo",
            assignee="zf-builder"
        ))
        task_id = t_res["id"]

        # Run cycle to dispatch to running and setup worktree
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
        self.assertEqual(t_after_changes["status"], "todo")
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
        self.assertEqual(t_conf["status"], "todo")
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
        self.assertIn(get_task(t_child)["task"]["status"], ("todo", "running"))
        acts = get_activities(limit=20)["activities"]
        self.assertTrue(any(a["action"] == "unblock" for a in acts))


if __name__ == "__main__":
    unittest.main()
