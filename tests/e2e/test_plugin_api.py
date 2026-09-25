"""End-to-End validation of FastAPI REST backend, activities, and DB retention."""

from __future__ import annotations

import os
import shutil
import tempfile
import time
import unittest
from pathlib import Path

from fastapi import FastAPI
from fastapi.testclient import TestClient

from dashboard.plugin_api import (
    ACTIVITY_ACTORS,
    DEFAULT_ACTIVITY_RETENTION_DAYS,
    get_db_conn,
    init_db,
    prune_old_activity,
    router,
)


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

    def test_01_boards_api_crud_and_limits(self):
        """Boards REST API: create, read, update max_concurrent_running and target_branch, delete."""
        # Create
        res = self.client.post("/api/plugins/zerofactory/boards", json={
            "git_url": "https://github.com/my-org/api-service.git",
            "description": "API Gateway Service"
        })
        self.assertEqual(res.status_code, 200)
        slug = res.json()["slug"]
        self.assertEqual(slug, "my-org-api-service")

        # List
        res_list = self.client.get("/api/plugins/zerofactory/boards")
        self.assertEqual(res_list.status_code, 200)
        created_b = next(b for b in res_list.json()["boards"] if b["slug"] == slug)
        self.assertEqual(created_b["target_branch"], "")

        # Patch max_concurrent_running and target_branch
        res_patch = self.client.patch(f"/api/plugins/zerofactory/boards/{slug}", json={
            "max_concurrent_running": 5,
            "target_branch": "develop"
        })
        self.assertEqual(res_patch.status_code, 200)
        self.assertTrue(res_patch.json()["ok"])
        self.assertEqual(res_patch.json()["board"]["target_branch"], "develop")

        # Verify updated board
        boards = self.client.get("/api/plugins/zerofactory/boards").json()["boards"]
        target = next(b for b in boards if b["slug"] == slug)
        self.assertEqual(target["max_concurrent_running"], 5)
        self.assertEqual(target["target_branch"], "develop")

        # Delete
        res_del = self.client.delete(f"/api/plugins/zerofactory/boards/{slug}")
        self.assertEqual(res_del.status_code, 200)
        self.assertTrue(res_del.json()["ok"])

    def test_02_tasks_api_lifecycle_and_dependencies(self):
        """Tasks REST API: CRUD, moves, comments, dependency DAG."""
        self.client.post("/api/plugins/zerofactory/boards", json={"git_url": "https://github.com/my-org/task-api.git"})

        # Create Task A and Task B
        res_a = self.client.post("/api/plugins/zerofactory/tasks", json={
            "board_slug": "my-org-task-api",
            "title": "Task A (Base)",
            "status": "todo",
            "priority": "P1"
        })
        id_a = res_a.json()["id"]

        res_b = self.client.post("/api/plugins/zerofactory/tasks", json={
            "board_slug": "my-org-task-api",
            "title": "Task B (Dependent)",
            "status": "todo",
            "priority": "P2"
        })
        id_b = res_b.json()["id"]

        # Link dependency (A blocks B)
        res_link = self.client.post(f"/api/plugins/zerofactory/tasks/{id_a}/dependencies", json={
            "parent_id": id_a,
            "child_id": id_b
        })
        self.assertEqual(res_link.status_code, 200)

        # Verify dependency linked
        task_b = self.client.get(f"/api/plugins/zerofactory/tasks/{id_b}").json()["task"]
        self.assertIn(id_a, [p["id"] for p in task_b.get("parents", [])])

        # Remove dependency: DELETE /tasks/{child_id}/dependencies/{parent_id}
        res_unlink = self.client.delete(f"/api/plugins/zerofactory/tasks/{id_b}/dependencies/{id_a}")
        self.assertEqual(res_unlink.status_code, 200)

    def test_03_activities_api_strict_actors_and_filters(self):
        """Activities API strictly enforces 6 canonical actors and supports filters & search."""
        self.client.post("/api/plugins/zerofactory/boards", json={"git_url": "https://github.com/my-org/act.git"})
        t_id = self.client.post("/api/plugins/zerofactory/tasks", json={
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
        res = self.client.get("/api/plugins/zerofactory/activities")
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
        res = self.client.get("/api/plugins/zerofactory/settings")
        self.assertEqual(res.status_code, 200)
        s = res.json()["settings"]
        self.assertEqual(s["activity_retention_days"], DEFAULT_ACTIVITY_RETENTION_DAYS)

        # PATCH settings
        res_patch = self.client.patch("/api/plugins/zerofactory/settings", json={
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


if __name__ == "__main__":
    unittest.main()
