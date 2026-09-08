"""Tests for Zero Factory Kanban plugin backend and database."""

import os
import sys
import tempfile
import unittest
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


if __name__ == "__main__":
    unittest.main()
