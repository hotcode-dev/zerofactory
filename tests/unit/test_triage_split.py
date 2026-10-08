import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path

from dashboard.db import init_db
from dashboard.models import TaskCreate, TaskSplitRequest, TaskUpdate
from dashboard.routes.tasks import create_task, split_task, update_task


class TestTriageSplit(unittest.TestCase):
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
                "INSERT INTO board_repositories (board_slug, repo_alias, git_url, created_at, updated_at) VALUES ('test-board', 'frontend', 'https://github.com/org/front', 1, 1)"
            )
            conn.execute(
                "INSERT INTO board_repositories (board_slug, repo_alias, git_url, created_at, updated_at) VALUES ('test-board', 'backend', 'https://github.com/org/back', 1, 1)"
            )
            conn.commit()

    def tearDown(self):
        if self.db_path.exists():
            try:
                self.db_path.unlink()
            except Exception:
                pass

    def test_create_triage_task_with_target_repos(self):
        req = TaskCreate(
            title="[Triage] [Bug] Auth token mismatch across frontend and backend",
            description="Client sends JWT format not accepted by server",
            board_slug="test-board",
            status="triage",
            priority="P1",
            target_repos=["frontend", "backend"],
        )
        res = create_task(req)
        self.assertTrue(res["ok"])
        task_id = res["id"]

        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            self.assertEqual(row["status"], "triage")
            meta = json.loads(row["metadata"])
            self.assertEqual(meta.get("target_repos"), ["frontend", "backend"])

    def test_split_triage_task_into_todo_tasks(self):
        # 1. Create parent triage task
        req = TaskCreate(
            title="[Triage] [Bug] #42 WebRTC handshake failing between client and server",
            description="Signaling protocol payload format changed",
            board_slug="test-board",
            status="triage",
            priority="P0",
            target_repos=["frontend", "backend"],
        )
        parent_res = create_task(req)
        parent_id = parent_res["id"]

        # 2. Split task
        split_res = split_task(parent_id)
        self.assertTrue(split_res["ok"])
        self.assertEqual(split_res["parent_task_id"], parent_id)
        created = split_res["created_tasks"]
        self.assertEqual(len(created), 2)

        front_task = next(c for c in created if c["repo_alias"] == "frontend")
        back_task = next(c for c in created if c["repo_alias"] == "backend")

        self.assertEqual(front_task["status"], "todo")
        self.assertEqual(front_task["assignee"], "zf-builder")
        self.assertIn("frontend", front_task["title"])

        self.assertEqual(back_task["status"], "todo")
        self.assertEqual(back_task["assignee"], "zf-builder")
        self.assertIn("backend", back_task["title"])

        # 3. Verify parent transitioned to done with metadata and comment
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            p_row = conn.execute("SELECT * FROM tasks WHERE id = ?", (parent_id,)).fetchone()
            self.assertEqual(p_row["status"], "done")
            self.assertEqual(p_row["assignee"], "zf-orchestrator")
            p_meta = json.loads(p_row["metadata"])
            self.assertEqual(len(p_meta.get("decomposed_into", [])), 2)

            # Check task_links
            links = conn.execute(
                "SELECT * FROM task_links WHERE parent_id = ? ORDER BY child_id ASC",
                (parent_id,),
            ).fetchall()
            self.assertEqual(len(links), 2)
            self.assertEqual(links[0]["link_type"], "relates_to")

            # Check comments recorded
            cmts = conn.execute("SELECT * FROM task_comments WHERE task_id = ?", (parent_id,)).fetchall()
            self.assertGreaterEqual(len(cmts), 1)
            self.assertIn("Triage Decomposition Complete", cmts[0]["body"])

    def test_split_explicit_repos(self):
        req = TaskCreate(
            title="General bug in triage",
            board_slug="test-board",
            status="triage",
        )
        res = create_task(req)

        # Split with explicit repos
        split_res = split_task(res["id"], TaskSplitRequest(repos=["backend", "frontend"]))
        self.assertTrue(split_res["ok"])
        self.assertEqual(len(split_res["created_tasks"]), 2)


if __name__ == "__main__":
    unittest.main()
