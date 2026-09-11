"""Tests for Zero Factory Kanban plugin backend and database."""

import os
import sys
import json
import tempfile
import unittest
from unittest import mock
from pathlib import Path

# Set up test database path before importing
test_dir = tempfile.TemporaryDirectory()
os.environ["ZEROFACTORY_KANBAN_DB"] = str(Path(test_dir.name) / "test_kanban.db")
os.environ["ZEROFACTORY_KANBAN_SKIP_GIT"] = "1"

from fastapi.testclient import TestClient
from dashboard.plugin_api import (
    router, init_db, get_db_conn,
    BoardCreate, TaskCreate, TaskUpdate, TaskMove, CommentCreate, DependencyLink,
    list_boards, create_board, list_tasks, create_task, get_task, update_task, move_task,
    add_comment, add_dependency, remove_dependency, get_stats, trigger_dispatch
)
from fastapi import FastAPI

# Import the dispatcher engine directly (module, not the package __init__) so the
# regression test can drive run_dispatch_cycle with a mocked git/gh layer.
import dispatcher  # noqa: E402
from dispatcher import run_dispatch_cycle  # noqa: E402

app = FastAPI()
app.include_router(router, prefix="/api/plugins/zerofactory-kanban")
client = TestClient(app)


class TestZeroFactoryKanban(unittest.TestCase):

    def setUp(self):
        init_db()

    def test_01_init_and_boards(self):
        req = BoardCreate(slug="zerofactory", name="ZeroFactory", description="AI workflow", git_url="https://github.com/hotcode-dev/zerofactory")
        create_board(req)
        res = list_boards()
        self.assertTrue(res["ok"])
        boards = res["boards"]
        self.assertGreaterEqual(len(boards), 1)
        slugs = [b["slug"] for b in boards]
        self.assertIn("zerofactory", slugs)

    def test_02_create_board(self):
        req = BoardCreate(slug="zerohub", name="ZeroHub Project", description="Hub project", git_url="https://github.com/example/zerohub")
        res = create_board(req)
        self.assertTrue(res["ok"])
        self.assertEqual(res["slug"], "zerohub")

        # Verify listed
        boards = list_boards()["boards"]
        slugs = [b["slug"] for b in boards]
        self.assertIn("zerohub", slugs)

    def test_03_task_crud_and_transitions(self):
        # 1. Create Task
        req = TaskCreate(
            title="Implement OAuth Login",
            description="Add GitHub and Google OAuth2 providers",
            board_slug="zerofactory",
            status="triage",
            priority="P1",
            assignee="builder",
            tenant="zerofactory"
        )
        created = create_task(req)
        task_id = created["id"]
        self.assertTrue(task_id.startswith("zf-"))

        # 2. Get Task
        details = get_task(task_id)["task"]
        self.assertEqual(details["title"], "Implement OAuth Login")
        self.assertEqual(details["status"], "triage")
        self.assertEqual(details["priority"], "P1")
        self.assertEqual(details["assignee"], "builder")

        # 3. Move Task
        move_res = move_task(task_id, TaskMove(status="running", actor="test"))
        self.assertTrue(move_res["ok"])
        self.assertEqual(move_res["status"], "running")
        self.assertEqual(move_res["prev_status"], "triage")

        # 4. Update Task
        up_res = update_task(task_id, TaskUpdate(title="Implement OAuth2 Login (Updated)", priority="P0"))
        self.assertTrue(up_res["ok"])
        updated = get_task(task_id)["task"]
        self.assertEqual(updated["title"], "Implement OAuth2 Login (Updated)")
        self.assertEqual(updated["priority"], "P0")

        # 5. List with filters
        filtered = list_tasks(status="running", priority="P0")
        self.assertEqual(filtered["count"], 1)
        self.assertEqual(filtered["tasks"][0]["id"], task_id)

    def test_04_comments_and_activity(self):
        created = create_task(TaskCreate(title="Test Commenting Task"))
        task_id = created["id"]

        # Add comment
        c_res = add_comment(task_id, CommentCreate(author="reviewer", body="Please add unit tests."))
        self.assertTrue(c_res["ok"])

        # Check task details for comment and activity
        details = get_task(task_id)["task"]
        self.assertEqual(len(details["comments"]), 1)
        self.assertEqual(details["comments"][0]["body"], "Please add unit tests.")
        self.assertEqual(details["comments"][0]["author"], "reviewer")

        # Check activity
        activities = details["activity"]
        self.assertGreaterEqual(len(activities), 2)  # create + comment

    def test_05_dependencies_and_unblocking(self):
        # Parent task
        parent = create_task(TaskCreate(title="Parent DB Schema", status="todo"))["id"]
        # Child task
        child = create_task(TaskCreate(title="Child API Endpoints", status="blocked"))["id"]

        # Link parent -> child
        link_res = add_dependency(child, DependencyLink(parent_id=parent, child_id=child))
        self.assertTrue(link_res["ok"])

        child_details = get_task(child)["task"]
        self.assertEqual(len(child_details["parents"]), 1)
        self.assertEqual(child_details["parents"][0]["id"], parent)

        # Dispatch when parent is still 'todo' -> child stays 'blocked'
        d_res = trigger_dispatch()
        self.assertTrue(d_res["ok"])
        self.assertEqual(get_task(child)["task"]["status"], "blocked")

        # Mark parent 'done'
        move_task(parent, TaskMove(status="done"))

        # Dispatch again -> child should unblock to 'ready'
        d_res2 = trigger_dispatch()
        self.assertTrue(d_res2["ok"])
        self.assertEqual(get_task(child)["task"]["status"], "ready")

    def test_06_fastapi_endpoints(self):
        # Test HTTP endpoints via TestClient
        resp = client.get("/api/plugins/zerofactory-kanban/boards")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])

        # Create task via HTTP
        resp = client.post("/api/plugins/zerofactory-kanban/tasks", json={
            "title": "HTTP Task",
            "priority": "P2",
            "status": "todo"
        })
        self.assertEqual(resp.status_code, 200)
        t_id = resp.json()["id"]

        # Move task via HTTP
        resp = client.post(f"/api/plugins/zerofactory-kanban/tasks/{t_id}/move", json={
            "status": "ready"
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ready")

        # Get stats
        resp = client.get("/api/plugins/zerofactory-kanban/stats")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("columns", resp.json())
        self.assertIn("ready", resp.json()["columns"])

    def test_07_builtin_cron(self):
        # 1. Test GET /cron
        resp = client.get("/api/plugins/zerofactory-kanban/cron")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        job_ids = [j["id"] for j in data["jobs"]]
        self.assertIn("zero-factory-task-queue-check", job_ids)
        self.assertIn("zero-factory-daily-report", job_ids)
        self.assertIn("zero-factory-improvement-scanner", job_ids)

        # 2. Test POST /cron/sync
        sync_resp = client.post("/api/plugins/zerofactory-kanban/cron/sync")
        self.assertEqual(sync_resp.status_code, 200)
        self.assertTrue(sync_resp.json()["ok"])

    # ------------------------------------------------------------------
    # Regression: PR lifecycle must not stall a task in 'ready'
    # (dispatcher.py: the PR-handling SELECT previously only matched
    #  status IN ('blocked','done'), so a task the builder finished and
    #  the dispatcher set to status='ready' for the reviewer was never
    #  re-polled -- MERGED was never detected and the task starved a WIP slot.)
    # ------------------------------------------------------------------
    def test_08_pr_lifecycle_ready_to_done(self):
        """A builder task -> PR opened -> routed to reviewer -> MERGED -> done."""
        # Use the plugin's canonical DB path (set by ZEROFACTORY_KANBAN_DB env at import).
        from dashboard.plugin_api import get_db_path as _gp
        db_path = _gp()

        # Self-contained: create a dedicated board so this test does not rely on
        # test_01 having created 'zerofactory' (tests share one temp DB).
        create_board(BoardCreate(
            slug="prlifecycle", name="PR Lifecycle", description="regression board",
        ))

        # Build a fake repo + worktree layout the dispatcher inspects:
        #   workspace_path = <root>/<reponame>-worktrees/<task_id>
        #   dispatcher sets repo_path = workspace_path.parent.parent = <root>
        # and requires (repo_path / ".git") to exist, so we place the .git marker at
        # <root> to keep the test fully self-contained (no os.getcwd() fallback).
        workdir = tempfile.TemporaryDirectory()
        root = Path(workdir.name)
        reponame = "prlifecycle"
        (root / ".git").mkdir()

        # 1. Create a builder task in 'running' with a worktree already provisioned.
        #    (Mirrors a real builder mid-flight before it signals 'review-required'.)
        created = create_task(TaskCreate(
            title="Implement payment retry",
            status="running",
            assignee="builder",
            priority="P1",
            board_slug="prlifecycle",
        ))
        task_id = created["id"]
        ws = str(root / f"{reponame}-worktrees" / task_id)
        Path(ws).mkdir(parents=True)
        with get_db_conn() as conn:
            conn.execute(
                "UPDATE tasks SET workspace_path = ?, branch_name = ? WHERE id = ?",
                (ws, f"task/{task_id}", task_id)
            )
            conn.commit()

        # Builder signals "review-required" -> task goes to 'blocked' (per SOUL/AGENTS
        # convention), still assigned to the builder.
        move_task(task_id, TaskMove(status="blocked"))

        gh_pr_url = f"https://github.com/hotcode-dev/{reponame}/pull/42"

        class _Result:
            """Deterministic fake for subprocess.run output."""
            returncode = 0
            stdout = ""
            stderr = ""

        def fake_run(cmd, *a, **kw):
            """Route the dispatcher's git/gh calls to deterministic fakes."""
            argv = [str(x) for x in cmd]
            if argv and argv[0] == "gh":
                if "pr" in argv and "create" in argv:
                    r = _Result(); r.stdout = gh_pr_url + "\n"
                    return r
                if "pr" in argv and "view" in argv:
                    # Simulate the human having merged the PR.
                    r = _Result()
                    r.stdout = json.dumps(
                        {"state": "MERGED", "reviewDecision": "APPROVED", "url": gh_pr_url}
                    )
                    return r
            return _Result()

        # --- Cycle 1: author handoff (builder, blocked) -> open PR, route to reviewer.
        #     The module sets ZEROFACTORY_KANBAN_SKIP_GIT=1 at import; override it so the
        #     PR-handling step (step 3) actually runs in this cycle.
        with mock.patch.dict(os.environ, {"ZEROFACTORY_KANBAN_SKIP_GIT": ""}), \
             mock.patch.object(dispatcher.subprocess, "run", side_effect=fake_run), \
             mock.patch.object(dispatcher, "setup_worktree", return_value=None):
            res1 = run_dispatch_cycle(db_path)
        self.assertTrue(res1["ok"])
        self.assertEqual(res1["prs_opened"], 1, "author handoff should open exactly one PR")
        t1 = get_task(task_id)["task"]
        self.assertEqual(t1["assignee"], "reviewer", "task routed to reviewer after PR opened")
        self.assertEqual(t1["status"], "ready", "PR handoff sets task to 'ready'")
        self.assertEqual(t1["pr_url"], gh_pr_url)

        # --- Cycle 2 (the regression): after the handoff the task sits in 'ready'
        #     (assignee=reviewer, pr_url set) while the reviewer works and the human
        #     merges the PR. Before the fix the PR query only matched
        #     status IN ('blocked','done'), so this 'ready' reviewer task was NEVER
        #     re-polled -- MERGED was undetected and the task starved a WIP slot forever.
        #     The fix adds 'ready' to the query, so the dispatcher now inspects the PR
        #     and auto-completes the task when it is MERGED.
        self.assertEqual(get_task(task_id)["task"]["status"], "ready",
                         "handoff leaves the task in 'ready' for the reviewer")
        with mock.patch.dict(os.environ, {"ZEROFACTORY_KANBAN_SKIP_GIT": ""}), \
             mock.patch.object(dispatcher.subprocess, "run", side_effect=fake_run), \
             mock.patch.object(dispatcher, "setup_worktree", return_value=None):
            res2 = run_dispatch_cycle(db_path)
        self.assertTrue(res2["ok"])
        t2 = get_task(task_id)["task"]
        self.assertEqual(t2["status"], "done", "MERGED PR must auto-complete the task to 'done'")
        self.assertIsNone(t2["workspace_path"], "worktree cleared on merge")
        workdir.cleanup()

    def test_09_plain_ready_task_not_mishandled(self):
        """A plain 'ready' task (awaiting its agent) must NOT be treated as an author."""
        from dashboard.plugin_api import get_db_path as _gp
        db_path = _gp()

        # Self-contained: dedicated board so FK succeeds without test_01.
        create_board(BoardCreate(
            slug="plainready", name="Plain Ready", description="regression board",
        ))

        # Same layout rule as test_08: .git marker at repo_path
        # (workspace_path.parent.parent) so the dispatcher's repo resolution is deterministic.
        workdir = tempfile.TemporaryDirectory()
        root = Path(workdir.name)
        reponame = "plainready"
        (root / ".git").mkdir()

        created = create_task(TaskCreate(
            title="Fresh ready task",
            status="ready",
            assignee="builder",
            priority="P2",
            board_slug="plainready",
        ))
        task_id = created["id"]
        ws = str(root / f"{reponame}-worktrees" / task_id)
        Path(ws).mkdir(parents=True)
        with get_db_conn() as conn:
            conn.execute(
                "UPDATE tasks SET workspace_path = ?, branch_name = ? WHERE id = ?",
                (ws, f"task/{task_id}", task_id)
            )
            conn.commit()

        # No PR exists yet, builder is on it, status 'ready' -> must be left alone.
        with mock.patch.object(dispatcher.subprocess, "run", autospec=True) as mock_run, \
             mock.patch.object(dispatcher, "setup_worktree", return_value=None):
            res = run_dispatch_cycle(db_path)
        self.assertTrue(res["ok"])
        self.assertEqual(res["prs_opened"], 0, "a plain ready task must not open a PR")
        # No git/gh subprocess should have been attempted for this task.
        self.assertFalse(any("gh" in str(c.args) for c in mock_run.call_args_list),
                         "no gh command should run for a plain ready task")
        t = get_task(task_id)["task"]
        self.assertEqual(t["status"], "ready", "plain ready task unchanged")
        self.assertIsNone(t["pr_url"], "no PR assigned to a plain ready task")
        workdir.cleanup()


if __name__ == "__main__":
    unittest.main()
