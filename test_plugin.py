"""Tests for Zero Factory plugin backend and database."""

import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

# Set up test database path before importing
test_dir = tempfile.TemporaryDirectory()
os.environ["ZEROFACTORY_DB"] = str(Path(test_dir.name) / "test.db")
os.environ["ZEROFACTORY_SKIP_GIT"] = "1"
os.environ["ZEROFACTORY_SKIP_CRON_SYNC"] = "1"

from fastapi.testclient import TestClient
from dashboard.plugin_api import (
    router, init_db, get_db_conn,
    BoardCreate, BoardUpdate, TaskCreate, TaskUpdate, TaskMove, CommentCreate, DependencyLink,
    list_boards, create_board, list_tasks, create_task, get_task, get_task_session, update_task, move_task,
    add_comment, add_dependency, remove_dependency, get_stats, get_activities, trigger_dispatch
)
from fastapi import FastAPI

app = FastAPI()
app.include_router(router, prefix="/api/plugins/zerofactory")
client = TestClient(app)


class TestZeroFactory(unittest.TestCase):

    def setUp(self):
        init_db()

    def test_01_init_and_boards(self):
        req = BoardCreate(git_url="https://github.com/hotcode-dev/zerofactory", description="AI workflow")
        res = create_board(req)
        self.assertTrue(res["ok"])
        self.assertEqual(res["slug"], "hotcode-dev-zerofactory")

        list_res = list_boards()
        self.assertTrue(list_res["ok"])
        boards = list_res["boards"]
        self.assertGreaterEqual(len(boards), 1)
        slugs = [b["slug"] for b in boards]
        self.assertIn("hotcode-dev-zerofactory", slugs)

    def test_02_create_board(self):
        req = BoardCreate(git_url="https://github.com/example/zerohub.git", description="Hub project")
        res = create_board(req)
        self.assertTrue(res["ok"])
        self.assertEqual(res["slug"], "example-zerohub")

        # Verify listed
        boards = list_boards()["boards"]
        slugs = [b["slug"] for b in boards]
        self.assertIn("example-zerohub", slugs)

    def test_03_task_crud_and_transitions(self):
        # 1. Create Task
        req = TaskCreate(
            title="Implement OAuth Login",
            description="Add GitHub and Google OAuth2 providers",
            board_slug="hotcode-dev-zerofactory",
            status="triage",
            priority="P1",
            assignee="zf-builder",
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
        self.assertEqual(details["assignee"], "zf-builder")

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
        c_res = add_comment(task_id, CommentCreate(author="zf-reviewer", body="Please add unit tests."))
        self.assertTrue(c_res["ok"])

        # Check task details for comment and activity
        details = get_task(task_id)["task"]
        self.assertEqual(len(details["comments"]), 1)
        self.assertEqual(details["comments"][0]["body"], "Please add unit tests.")
        self.assertEqual(details["comments"][0]["author"], "zf-reviewer")

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
        resp = client.get("/api/plugins/zerofactory/boards")
        self.assertEqual(resp.status_code, 200)
        self.assertTrue(resp.json()["ok"])

        # Create task via HTTP
        resp = client.post("/api/plugins/zerofactory/tasks", json={
            "title": "HTTP Task",
            "priority": "P2",
            "status": "todo"
        })
        self.assertEqual(resp.status_code, 200)
        t_id = resp.json()["id"]

        # Move task via HTTP
        resp = client.post(f"/api/plugins/zerofactory/tasks/{t_id}/move", json={
            "status": "ready"
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ready")

        # Get stats
        resp = client.get("/api/plugins/zerofactory/stats")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("columns", resp.json())
        self.assertIn("ready", resp.json()["columns"])

    def test_07_builtin_cron(self):
        # 1. Test GET /cron
        resp = client.get("/api/plugins/zerofactory/cron")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        job_ids = [j["id"] for j in data["jobs"]]
        self.assertIn("zero-factory-task-queue-check", job_ids)
        self.assertIn("zero-factory-daily-report", job_ids)
        self.assertIn("zero-factory-improvement-scanner-hotcode-dev-zerofactory", job_ids)
        self.assertTrue(any(j.startswith("zero-factory-improvement-scanner") for j in job_ids))

        # Verify workdir is resolved for hotcode-dev-zerofactory board
        zf_job = next(j for j in data["jobs"] if j["id"] == "zero-factory-improvement-scanner-hotcode-dev-zerofactory")
        self.assertIsNotNone(zf_job.get("workdir"))
        self.assertTrue(os.path.isdir(zf_job["workdir"]))

        # 2. Test POST /cron/sync
        sync_resp = client.post("/api/plugins/zerofactory/cron/sync")
        self.assertEqual(sync_resp.status_code, 200)
        self.assertTrue(sync_resp.json()["ok"])

        # 3. Test dynamic board scanner lifecycle (creation & deletion)
        # Create board
        res_cb = client.post("/api/plugins/zerofactory/boards", json={
            "git_url": "https://github.com/example/test-dynamic-cron.git"
        })
        self.assertEqual(res_cb.status_code, 200)
        self.assertEqual(res_cb.json()["slug"], "example-test-dynamic-cron")

        # Check job is now present
        resp_after_create = client.get("/api/plugins/zerofactory/cron")
        ids_after_create = [j["id"] for j in resp_after_create.json()["jobs"]]
        self.assertIn("zero-factory-improvement-scanner-example-test-dynamic-cron", ids_after_create)

        # Delete board
        res_del = client.delete("/api/plugins/zerofactory/boards/example-test-dynamic-cron")
        self.assertEqual(res_del.status_code, 200)

        # Check job is pruned
        resp_after_del = client.get("/api/plugins/zerofactory/cron")
        ids_after_del = [j["id"] for j in resp_after_del.json()["jobs"]]
        self.assertNotIn("zero-factory-improvement-scanner-example-test-dynamic-cron", ids_after_del)

    def test_08_dispatcher_worker_execution(self):
        from dispatcher import _active_workers

        # Ensure no leftover running tasks from previous tests
        with get_db_conn() as conn:
            conn.execute("UPDATE tasks SET status = 'done' WHERE status = 'running'")
            conn.commit()

        # 1. Create a task in 'ready'
        t_id = create_task(TaskCreate(
            title="Implement Builder Task",
            status="ready",
            priority="P0",
            assignee="zf-builder"
        ))["id"]

        # Run dispatch with worker spawn skipped (simulated spawn)
        os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = "1"
        res = trigger_dispatch()
        self.assertTrue(res["ok"])
        self.assertGreaterEqual(res.get("dispatched", 0), 1)

        # Check task moved to 'running'
        t_data = get_task(t_id)["task"]
        self.assertEqual(t_data["status"], "running")

        # 2. Simulate worker completion (exit 0)
        from unittest.mock import MagicMock
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 0
        _active_workers[t_id] = mock_proc

        # Trigger dispatch to reap
        res2 = trigger_dispatch()
        self.assertTrue(res2["ok"])
        self.assertGreaterEqual(res2.get("reaped", 0), 1)

        t_data2 = get_task(t_id)["task"]
        self.assertEqual(t_data2["status"], "done")

        # 3. Simulate worker failure (exit 1)
        t_id_fail = create_task(TaskCreate(
            title="Failing Task",
            status="running",
            priority="P1",
            assignee="zf-builder"
        ))["id"]

        mock_fail_proc = MagicMock()
        mock_fail_proc.poll.return_value = 1
        _active_workers[t_id_fail] = mock_fail_proc

        res3 = trigger_dispatch()
        self.assertTrue(res3["ok"])
        t_data_fail = get_task(t_id_fail)["task"]
        self.assertEqual(t_data_fail["status"], "blocked")

        os.environ.pop("ZEROFACTORY_SKIP_WORKER_SPAWN", None)

    def test_09_session_progress_resolution(self):
        # 1. Create board with omitted optional description (tests None coalesce)
        res_b = client.post("/api/plugins/zerofactory/boards", json={
            "git_url": "https://github.com/example/test-omitted-fields"
        })
        self.assertEqual(res_b.status_code, 200)

        # 2. Create a running task with metadata containing session and pid
        t_id = create_task(TaskCreate(
            title="Session Progress Test Task",
            status="running",
            priority="P0",
            assignee="zf-builder"
        ))["id"]

        # 3. Query session endpoint
        res = client.get(f"/api/plugins/zerofactory/tasks/{t_id}/session")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        prog = data["session_progress"]
        self.assertIn("has_session", prog)
        self.assertIn("is_alive", prog)
        self.assertIn("turn_count", prog)
        self.assertIn("message_count", prog)
        self.assertIn("recent_steps", prog)
        self.assertIn("log_tail", prog)

        # 4. Verify get_task also includes session_progress
        res_task = client.get(f"/api/plugins/zerofactory/tasks/{t_id}")
        self.assertEqual(res_task.status_code, 200)
        task_data = res_task.json()["task"]
        self.assertIn("session_progress", task_data)

        # 5. Verify list_tasks includes compact session_progress for running task
        res_list = client.get("/api/plugins/zerofactory/tasks?status=running")
        self.assertEqual(res_list.status_code, 200)
        tasks = res_list.json()["tasks"]
        target = next((t for t in tasks if t["id"] == t_id), None)
        self.assertIsNotNone(target)
        self.assertIn("session_progress", target)

    def test_10_multi_file_fingerprint_deduplication(self):
        # 1. Create task with multiple files in random order
        t1 = create_task(TaskCreate(
            title="Fix login auth null check",
            board_slug="hotcode-dev-zerofactory",
            files=["src/user.py", "src/auth.py"],
            category="bug-fix",
            status="todo"
        ))
        self.assertTrue(t1["ok"])
        t1_id = t1["id"]
        self.assertFalse(t1.get("duplicate", False))

        # Check metadata and tags
        t1_data = get_task(t1_id)["task"]
        self.assertEqual(t1_data["metadata"]["files"], ["src/auth.py", "src/user.py"])
        self.assertEqual(t1_data["metadata"]["dedup_key"], "src/auth.py,src/user.py:bug-fix")
        self.assertIn("file:src/auth.py", t1_data["tags"])
        self.assertIn("file:src/user.py", t1_data["tags"])
        self.assertIn("cat:bug-fix", t1_data["tags"])

        # 2. Attempt to create second task with reversed file order and different title
        t2 = create_task(TaskCreate(
            title="Resolve authentication error in user session",
            board_slug="hotcode-dev-zerofactory",
            files=["src/auth.py", "src/user.py"],
            category="bug-fix",
            status="todo"
        ))
        self.assertTrue(t2["ok"])
        self.assertTrue(t2.get("duplicate"))
        self.assertEqual(t2["id"], t1_id)

        # 3. Test exact title deduplication when no files specified
        t3 = create_task(TaskCreate(
            title="Standalone Unique Bug",
            board_slug="hotcode-dev-zerofactory",
            status="todo"
        ))
        self.assertTrue(t3["ok"])
        self.assertFalse(t3.get("duplicate", False))

        t4 = create_task(TaskCreate(
            title=" standalone unique bug ",
            board_slug="hotcode-dev-zerofactory",
            status="todo"
        ))
        self.assertTrue(t4.get("duplicate"))
        self.assertEqual(t4["id"], t3["id"])

        # 4. Move t1 to 'done' -> new task with same files should now be allowed
        move_task(t1_id, TaskMove(status="done"))
        t5 = create_task(TaskCreate(
            title="Future refactor of auth and user",
            board_slug="hotcode-dev-zerofactory",
            files=["src/auth.py", "src/user.py"],
            category="bug-fix",
            status="todo"
        ))
        self.assertTrue(t5["ok"])
        self.assertFalse(t5.get("duplicate", False))
        self.assertNotEqual(t5["id"], t1_id)

    def test_11_prune_orphan_board_scanners(self):
        from builtin_cron import ensure_builtin_cron_jobs, load_jobs_from_file, save_jobs_to_file
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as tf:
            test_jobs_path = Path(tf.name)
        try:
            # Seed with an active board job and orphan board jobs
            initial_jobs = [
                {"id": "zero-factory-task-queue-check", "origin": "zerofactory"},
                {"id": "zero-factory-improvement-scanner-hotcode-dev-zerofactory", "origin": "zerofactory"},
                {"id": "zero-factory-improvement-scanner-deleted-board", "origin": "zerofactory"},
                {"id": "zero-factory-improvement-scanner-orphan-slug", "origin": "zerofactory"},
                {"id": "custom-unrelated-cron-job"}
            ]
            save_jobs_to_file(test_jobs_path, initial_jobs)

            import builtin_cron
            orig_targets = builtin_cron.get_target_jobs_files
            builtin_cron.get_target_jobs_files = lambda: [test_jobs_path]

            os.environ.pop("ZEROFACTORY_SKIP_CRON_SYNC", None)
            try:
                ensure_builtin_cron_jobs()
            finally:
                os.environ["ZEROFACTORY_SKIP_CRON_SYNC"] = "1"
                builtin_cron.get_target_jobs_files = orig_targets

            synced = load_jobs_from_file(test_jobs_path)
            synced_ids = [j["id"] for j in synced]
            self.assertIn("zero-factory-task-queue-check", synced_ids)
            self.assertIn("zero-factory-improvement-scanner-hotcode-dev-zerofactory", synced_ids)
            self.assertIn("custom-unrelated-cron-job", synced_ids)
            self.assertNotIn("zero-factory-improvement-scanner-deleted-board", synced_ids)
            self.assertNotIn("zero-factory-improvement-scanner-orphan-slug", synced_ids)
        finally:
            if test_jobs_path.exists():
                test_jobs_path.unlink()

    def test_12_delete_board_and_clear_cron(self):
        from builtin_cron import load_jobs_from_file, save_jobs_to_file
        # 1. Create a board to delete
        res_create = client.post("/api/plugins/zerofactory/boards", json={
            "git_url": "https://github.com/test-org/board-to-remove.git"
        })
        self.assertEqual(res_create.status_code, 200)
        self.assertEqual(res_create.json()["slug"], "test-org-board-to-remove")

        # 2. Setup mock target jobs file with its scanner job
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as tf:
            test_jobs_path = Path(tf.name)
        try:
            initial_jobs = [
                {"id": "zero-factory-improvement-scanner-test-org-board-to-remove", "origin": "zerofactory"},
                {"id": "zero-factory-improvement-scanner-hotcode-dev-zerofactory", "origin": "zerofactory"}
            ]
            save_jobs_to_file(test_jobs_path, initial_jobs)

            import builtin_cron
            orig_targets = builtin_cron.get_target_jobs_files
            builtin_cron.get_target_jobs_files = lambda: [test_jobs_path]

            os.environ.pop("ZEROFACTORY_SKIP_CRON_SYNC", None)
            try:
                # 3. Call DELETE /boards/test-org-board-to-remove
                res_del = client.delete("/api/plugins/zerofactory/boards/test-org-board-to-remove")
                self.assertEqual(res_del.status_code, 200)
                self.assertTrue(res_del.json()["ok"])
            finally:
                os.environ["ZEROFACTORY_SKIP_CRON_SYNC"] = "1"
                builtin_cron.get_target_jobs_files = orig_targets

            # 4. Verify board is removed from list_boards()
            boards = list_boards()["boards"]
            slugs = [b["slug"] for b in boards]
            self.assertNotIn("test-org-board-to-remove", slugs)

            # 5. Verify cron job is cleared from jobs.json
            synced = load_jobs_from_file(test_jobs_path)
            synced_ids = [j["id"] for j in synced]
            self.assertNotIn("zero-factory-improvement-scanner-test-org-board-to-remove", synced_ids)
            self.assertIn("zero-factory-improvement-scanner-hotcode-dev-zerofactory", synced_ids)

            # 6. Delete again returns 404
            res_del_404 = client.delete("/api/plugins/zerofactory/boards/test-org-board-to-remove")
            self.assertEqual(res_del_404.status_code, 404)
        finally:
            if test_jobs_path.exists():
                test_jobs_path.unlink()

    def test_13_update_board(self):
        # 1. Update existing board
        res = client.patch("/api/plugins/zerofactory/boards/hotcode-dev-zerofactory", json={
            "description": "Updated description for AI core",
            "git_url": "https://github.com/hotcode-dev/zerofactory-core.git"
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["ok"])

        # 2. Verify in list_boards
        boards = list_boards()["boards"]
        zf = next(b for b in boards if b["slug"] == "hotcode-dev-zerofactory")
        self.assertEqual(zf["description"], "Updated description for AI core")
        self.assertEqual(zf["git_url"], "https://github.com/hotcode-dev/zerofactory-core.git")

        # 3. Update non-existent board returns 404
        res_404 = client.patch("/api/plugins/zerofactory/boards/non-existent-slug", json={
            "description": "Should Fail"
        })
        self.assertEqual(res_404.status_code, 404)


    def test_14_stuck_task_detection_and_reap(self):
        import json, time, subprocess
        from dispatcher import check_stuck_tasks, reap_stuck_tasks, reap_active_workers

        # Spawn a dummy worker process
        dummy_proc = subprocess.Popen(["sleep", "60"])
        try:
            now = int(time.time())
            started_time = now - 4000
            t_res = create_task(TaskCreate(
                title="Stuck Long Running Task",
                description="Simulated stuck task",
                board_slug="hotcode-dev-zerofactory",
                priority="P1",
                status="running",
                assignee="zf-builder"
            ))
            t_id = t_res["id"]

            with get_db_conn() as conn:
                conn.execute(
                    "UPDATE tasks SET updated_at = ?, metadata = ? WHERE id = ?",
                    (started_time, json.dumps({"started_at": started_time, "worker_pid": dummy_proc.pid}), t_id)
                )
                conn.commit()

            # 2. Verify check_stuck_tasks flags it as stuck with timeout reason
            stuck_info = check_stuck_tasks()
            target = next((item for item in stuck_info if item["id"] == t_id), None)
            self.assertIsNotNone(target)
            self.assertTrue(target["is_stuck"])
            self.assertIn("timeout", target["stuck_reason"].lower())

            # 3. Test GET /health/stuck-tasks endpoint
            res = client.get("/api/plugins/zerofactory/health/stuck-tasks")
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["ok"])
            stuck_ids = [t["id"] for t in data["stuck_tasks"]]
            self.assertIn(t_id, stuck_ids)

            # 4. Test POST /tasks/{task_id}/reap endpoint
            res_reap = client.post(f"/api/plugins/zerofactory/tasks/{t_id}/reap")
            self.assertEqual(res_reap.status_code, 200)
            self.assertTrue(res_reap.json()["ok"])

            # 5. Verify task is moved to 'blocked'
            t_after = get_task(t_id)["task"]
            self.assertEqual(t_after["status"], "blocked")

            # 6. Verify dummy worker process was terminated
            time.sleep(0.6)
            self.assertIsNotNone(dummy_proc.poll())
        finally:
            if dummy_proc.poll() is None:
                dummy_proc.kill()

    def test_15_conventional_commit_formatting(self):
        from dispatcher import format_conventional_message

        cases = [
            (
                "REFACTOR: Extract shared reverseMap + regex encode/decode helpers (9x duplicated reverse-map construction, 3x duplicated global-regex substitution pairs) in src/dict.ts",
                "zf-fb4215f1",
                "refactor(dict): extract shared reverseMap + regex encode/decode helpers",
            ),
            (
                "BUG FIX [P0] dispatcher promote/spawn ignore parent dependencies: task dispatched before its prerequisites are done",
                "zf-86d5c7f5",
                "fix(dispatcher): promote/spawn ignore parent dependencies: task dispatched before its prerequisites are done",
            ),
            (
                "SECURITY: Remove committed API gateway secrets (.env) from git history",
                "zf-9493d068",
                "fix(security): remove committed API gateway secrets from git history",
            ),
            (
                "feat: implement base92 encoding",
                "zf-123",
                "feat: implement base92 encoding",
            ),
            (
                "Add unit tests for stuck task reaper in test_plugin.py",
                "zf-456",
                "test(test_plugin): add unit tests for stuck task reaper",
            ),
        ]

        for title, task_id, expected_subj in cases:
            subj, body = format_conventional_message(title, task_id)
            self.assertEqual(subj, expected_subj)
            self.assertIn(f"Task: {task_id}", body)

    def test_16_cron_config_endpoints(self):
        import builtin_cron
        from builtin_cron import save_jobs_to_file, load_jobs_from_file, ensure_builtin_cron_jobs

        with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as tf:
            test_jobs_path = Path(tf.name)

        orig_targets = builtin_cron.get_target_jobs_files
        builtin_cron.get_target_jobs_files = lambda: [test_jobs_path]

        try:
            # 1. Initialize test jobs in target file
            initial_jobs = [
                {
                    "id": "zero-factory-task-queue-check",
                    "name": "Zero Factory task queue check",
                    "schedule": {"kind": "interval", "minutes": 120, "display": "every 120m"},
                    "schedule_display": "every 120m",
                    "enabled": True,
                    "state": "scheduled",
                    "prompt": "Initial prompt",
                    "model": "test-model",
                    "origin": "zerofactory"
                }
            ]
            save_jobs_to_file(test_jobs_path, initial_jobs)

            # 2. GET /cron
            res = client.get("/api/plugins/zerofactory/cron")
            self.assertEqual(res.status_code, 200)
            data = res.json()
            self.assertTrue(data["ok"])
            jobs = data["jobs"]
            self.assertGreater(len(jobs), 0)

            # Verify rich metadata
            target_job = next((j for j in jobs if j["id"] == "zero-factory-task-queue-check"), None)
            self.assertIsNotNone(target_job)
            self.assertIn("prompt", target_job)
            self.assertIn("schedule", target_job)
            self.assertIn("enabled", target_job)

            # 3. POST /cron/{job_id}/toggle
            initial_enabled = target_job["enabled"]
            res_toggle = client.post("/api/plugins/zerofactory/cron/zero-factory-task-queue-check/toggle")
            self.assertEqual(res_toggle.status_code, 200)
            self.assertTrue(res_toggle.json()["ok"])

            # Verify toggled
            res_after = client.get("/api/plugins/zerofactory/cron")
            toggled_job = next(j for j in res_after.json()["jobs"] if j["id"] == "zero-factory-task-queue-check")
            self.assertEqual(toggled_job["enabled"], not initial_enabled)
            self.assertEqual(toggled_job["state"], "paused" if initial_enabled else "scheduled")

            # 4. PUT /cron/{job_id} (update minutes and prompt)
            res_put = client.put(
                "/api/plugins/zerofactory/cron/zero-factory-task-queue-check",
                json={
                    "minutes": 45,
                    "prompt": "Custom queue check prompt",
                    "model": "custom-test-model"
                }
            )
            self.assertEqual(res_put.status_code, 200)
            self.assertTrue(res_put.json()["ok"])

            # Verify in GET /cron
            res_updated = client.get("/api/plugins/zerofactory/cron")
            updated_job = next(j for j in res_updated.json()["jobs"] if j["id"] == "zero-factory-task-queue-check")
            self.assertEqual(updated_job["schedule"]["minutes"], 45)
            self.assertEqual(updated_job["schedule_display"], "every 45m")
            self.assertEqual(updated_job["prompt"], "Custom queue check prompt")
            self.assertEqual(updated_job["model"], "custom-test-model")
            self.assertTrue(updated_job["custom_config"])

            # 5. Verify ensure_builtin_cron_jobs preserves custom_config
            ensure_builtin_cron_jobs()
            persisted = load_jobs_from_file(test_jobs_path)
            persisted_job = next(j for j in persisted if j["id"] == "zero-factory-task-queue-check")
            self.assertEqual(persisted_job["schedule"]["minutes"], 45)
            self.assertEqual(persisted_job["prompt"], "Custom queue check prompt")

            # 6. POST /cron/{job_id}/reset restores defaults
            res_reset = client.post("/api/plugins/zerofactory/cron/zero-factory-task-queue-check/reset")
            self.assertEqual(res_reset.status_code, 200)
            self.assertTrue(res_reset.json()["ok"])

            res_after_reset = client.get("/api/plugins/zerofactory/cron")
            reset_job = next(j for j in res_after_reset.json()["jobs"] if j["id"] == "zero-factory-task-queue-check")
            self.assertEqual(reset_job["schedule"]["minutes"], 120)
            self.assertFalse(reset_job["custom_config"])
        finally:
            builtin_cron.get_target_jobs_files = orig_targets
            if test_jobs_path.exists():
                test_jobs_path.unlink()

    def test_17_profile_manager(self):
        from profile_manager import ensure_zf_profiles, ZF_PROFILES, get_hermes_home
        res = ensure_zf_profiles()
        self.assertIsInstance(res, dict)
        profiles_found = set(res["created"] + res["existing"] + res["updated"])
        for p in ZF_PROFILES:
            self.assertIn(p, profiles_found)
            p_dir = get_hermes_home() / "profiles" / p
            self.assertTrue(p_dir.exists())
            self.assertTrue((p_dir / "SOUL.md").exists())
            self.assertTrue((p_dir / "config.yaml").exists())

    def test_18_assignee_normalization(self):
        from dispatcher import normalize_assignee, PROFILE_MAP
        self.assertEqual(normalize_assignee("zf-builder"), "zf-builder")
        self.assertEqual(normalize_assignee("zf-reviewer"), "zf-reviewer")
        self.assertEqual(normalize_assignee("zf-orchestrator"), "zf-orchestrator")
        self.assertEqual(normalize_assignee("unassigned"), "unassigned")
        self.assertEqual(normalize_assignee(None), "unassigned")

    def test_19_plugin_symlinks(self):
        from profile_manager import ensure_plugin_symlinks, get_hermes_home
        res = ensure_plugin_symlinks()
        self.assertIsInstance(res, dict)
        hermes_home = get_hermes_home()
        # Verify symlinks in root plugins dir
        root_plugins = hermes_home / "plugins"
        self.assertTrue((root_plugins / "zerofactory").is_symlink())

    def test_20_worker_spawn_cmd_and_env(self):
        from dispatcher import spawn_agent_worker
        from unittest.mock import patch, MagicMock

        with patch("subprocess.Popen") as mock_popen:
            mock_proc = MagicMock()
            mock_proc.pid = 99999
            mock_popen.return_value = mock_proc

            with patch.dict(os.environ, {}, clear=False):
                os.environ.pop("ZEROFACTORY_SKIP_WORKER_SPAWN", None)
                pid, sess = spawn_agent_worker(
                    task_id="zf-testspawn",
                    title="Test Worker Spawn",
                    assignee="zf-builder",
                    priority="P0",
                    description="Test spawn",
                    workspace_path="/tmp",
                    branch_name="task/zf-testspawn"
                )
                self.assertEqual(pid, 99999)
                self.assertTrue(mock_popen.called)
                args, kwargs = mock_popen.call_args
                cmd = args[0]
                env = kwargs.get("env", {})
                self.assertIn("--yolo", cmd)
                self.assertEqual(env.get("HERMES_PROFILE"), "zf-builder")
                profile_dir = Path.home() / ".hermes" / "profiles" / "zf-builder"
                if profile_dir.exists():
                    self.assertEqual(env.get("HERMES_HOME"), str(profile_dir))

    def test_21_zerofactory_api_route(self):
        # Verify /api/plugins/zerofactory works directly
        resp = client.get("/api/plugins/zerofactory/boards")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("boards", resp.json())
        resp_stats = client.get("/api/plugins/zerofactory/stats")
        self.assertEqual(resp_stats.status_code, 200)
        self.assertIn("total", resp_stats.json())

    def test_22_script_deployment(self):
        from profile_manager import ensure_script_files, get_hermes_home, ZF_PROFILES
        res = ensure_script_files()
        self.assertIsInstance(res, dict)
        copied = res.get("copied", [])
        self.assertGreater(len(copied), 0)

        hermes_home = get_hermes_home()
        expected_scripts = ["zf_queue_watchdog.py", "zf_scanner_gate.py", "zf_daily_stats.py"]
        for s in expected_scripts:
            # Check in root ~/.hermes/scripts/
            root_s = hermes_home / "scripts" / s
            self.assertTrue(root_s.exists(), f"Missing {root_s}")
            self.assertTrue(root_s.is_file())
            # Ensure it is a real file, NOT a symlink (to comply with Hermes path.relative_to security check)
            self.assertFalse(root_s.is_symlink(), f"{root_s} should not be a symlink")

            # Check in profile directories
            for role in ZF_PROFILES:
                prof_s = hermes_home / "profiles" / role / "scripts" / s
                self.assertTrue(prof_s.exists(), f"Missing {prof_s}")
                self.assertFalse(prof_s.is_symlink())

    def test_23_noagent_and_chained_cron_definitions(self):
        from builtin_cron import get_all_builtin_cron_jobs, CORE_CRON_JOBS

        # 1. Queue watchdog: No-Agent mode
        queue_job = CORE_CRON_JOBS["zero-factory-task-queue-check"]
        self.assertTrue(queue_job["no_agent"])
        self.assertEqual(queue_job["script"], "zf_queue_watchdog.py")
        self.assertIsNone(queue_job["context_from"])

        # 2. Daily report: Chained LLM Job
        daily_job = CORE_CRON_JOBS["zero-factory-daily-report"]
        self.assertFalse(daily_job["no_agent"])
        self.assertEqual(daily_job["script"], "zf_daily_stats.py")
        self.assertEqual(daily_job["context_from"], ["zero-factory-task-queue-check"])

        # 3. Dynamic board scanner: Wake-gate + stateless (continuity=False to prevent context bloating)
        all_jobs = get_all_builtin_cron_jobs()
        scanner_jobs = [j for jid, j in all_jobs.items() if jid.startswith("zero-factory-improvement-scanner-")]
        self.assertGreater(len(scanner_jobs), 0)
        for sj in scanner_jobs:
            self.assertEqual(sj["script"], "zf_scanner_gate.py")
            self.assertFalse(sj["no_agent"])
            self.assertIn(sj["context_from"], (None, ["self"]))
            self.assertFalse(sj["continuity"])

    def test_24_script_execution_and_wakegate(self):
        import subprocess
        import json
        from profile_manager import get_hermes_home
        hermes_home = get_hermes_home()
        scripts_dir = hermes_home / "scripts"

        # 1. Test zf_queue_watchdog.py
        proc = subprocess.run(
            [sys.executable, str(scripts_dir / "zf_queue_watchdog.py")],
            capture_output=True,
            text=True,
            timeout=15,
            env={**os.environ, "ZEROFACTORY_DB": str(Path(test_dir.name) / "test.db")}
        )
        self.assertEqual(proc.returncode, 0, f"Error: {proc.stderr}")
        # Parse last line as wake-gate JSON
        last_line = proc.stdout.strip().splitlines()[-1]
        data = json.loads(last_line)
        self.assertIn("wakeAgent", data)
        self.assertFalse(data["wakeAgent"])  # Clean board should suppress wake

        # 2. Test zf_daily_stats.py
        proc_stats = subprocess.run(
            [sys.executable, str(scripts_dir / "zf_daily_stats.py")],
            capture_output=True,
            text=True,
            timeout=15,
            env={**os.environ, "ZEROFACTORY_DB": str(Path(test_dir.name) / "test.db")}
        )
        self.assertEqual(proc_stats.returncode, 0, f"Error: {proc_stats.stderr}")
        self.assertIn("Pre-Calculated ZeroFactory Daily Metrics", proc_stats.stdout)
        self.assertIn("Column Distribution", proc_stats.stdout)

    def test_25_hermes_script_sandbox_compliance(self):
        """Verify compliance with Hermes _script_health_issue path sandbox."""
        from profile_manager import get_hermes_home
        from builtin_cron import get_all_builtin_cron_jobs
        scripts_dir = (get_hermes_home() / "scripts").resolve()

        all_jobs = get_all_builtin_cron_jobs()
        for jid, job in all_jobs.items():
            script_name = job.get("script")
            if not script_name:
                continue
            raw = Path(script_name).expanduser()
            resolved = raw.resolve() if raw.is_absolute() else (scripts_dir / raw).resolve()
            # Must be strictly within scripts_dir
            try:
                rel = resolved.relative_to(scripts_dir)
                self.assertEqual(str(rel), script_name)
            except ValueError as e:
                self.fail(f"Job {jid} script {script_name} fails Hermes sandbox check: {e}")
            self.assertTrue(resolved.exists())
            self.assertTrue(resolved.is_file())

    def test_25a_scanner_gate_unchanged_suppresses(self):
        """Regression: an already-scanned, unchanged, clean board must emit
        wakeAgent=false (0 tokens) EVEN WHEN IT HAS 0 OPEN TASKS.

        The old gate suppressed only when the board had >0 open tasks and instead
        re-fired a full LLM "baseline scan" on every 60m tick for any 0-task board —
        draining tokens on unchanged code and defeating the "0 Tokens on Idle" pillar.
        Suppression must now depend only on whether the exact commit was already
        scanned (last_scanned_sha is not None), never on open-task count.
        """
        import contextlib
        import importlib.util
        import io
        import json
        import sqlite3
        import subprocess

        # Load the script from THIS repo (the source of truth we are testing), NOT the
        # deployed copy under the Hermes home (which may be a stale pre-fix snapshot).
        gate_path = (Path(__file__).resolve().parent / "scripts" / "zf_scanner_gate.py").resolve()
        self.assertTrue(gate_path.is_file(), f"missing {gate_path}")

        def git(repo, *args):
            subprocess.run(
                ["git", *args], cwd=str(repo), check=True,
                capture_output=True, text=True,
                env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"},
            )

        def load_gate():
            spec = importlib.util.spec_from_file_location("zf_scanner_gate_under_test", gate_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            slug = "gate-test-board"

            # 1. Fresh git repo with a single commit.
            repo = td / "repo"
            repo.mkdir()
            git(repo, "init", "-q")
            git(repo, "config", "user.email", "scan@test.local")
            git(repo, "config", "user.name", "Scan Test")
            (repo / "a.py").write_text("x = 1\n", encoding="utf-8")
            git(repo, "add", ".")
            git(repo, "commit", "-qm", "initial")

            # 2. Temp zerofactory.db with the minimal boards/tasks schema.
            db_path = td / "gate.db"
            conn = sqlite3.connect(str(db_path))
            conn.executescript(
                "CREATE TABLE boards ("
                " slug TEXT PRIMARY KEY, description TEXT DEFAULT '', git_url TEXT DEFAULT '',"
                " created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);"
                "CREATE TABLE tasks ("
                " id TEXT PRIMARY KEY, board_slug TEXT NOT NULL DEFAULT '', title TEXT NOT NULL,"
                " description TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'triage',"
                " assignee TEXT NOT NULL DEFAULT 'unassigned', priority TEXT NOT NULL DEFAULT 'P2',"
                " workspace_path TEXT, workspace_kind TEXT DEFAULT 'worktree', branch_name TEXT,"
                " pr_url TEXT, tenant TEXT DEFAULT '', skills TEXT DEFAULT '[]',"
                " tags TEXT DEFAULT '[]', metadata TEXT DEFAULT '{}',"
                " created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);"
            )
            conn.execute(
                "INSERT INTO boards (slug, created_at, updated_at) VALUES (?, 1, 1)",
                (slug,),
            )
            conn.commit()
            conn.close()

            state_path = td / "scanner_state.json"

            def run_gate():
                mod = load_gate()
                mod.STATE_FILE = state_path  # isolate the persisted scan state
                old_argv, old_cwd = sys.argv, os.getcwd()
                old_db = os.environ.get("ZEROFACTORY_DB")
                sys.argv = [gate_path.name, slug]  # board slug via argv[1]
                os.chdir(str(repo))
                os.environ["ZEROFACTORY_DB"] = str(db_path)
                os.environ.pop("ZEROFACTORY_FORCE_SCAN", None)
                buf = io.StringIO()
                try:
                    with contextlib.redirect_stdout(buf):
                        rc = mod.run_scanner_gate()
                finally:
                    sys.argv = old_argv
                    os.chdir(old_cwd)
                    if old_db is None:
                        os.environ.pop("ZEROFACTORY_DB", None)
                    else:
                        os.environ["ZEROFACTORY_DB"] = old_db
                    os.environ.pop("ZEROFACTORY_FORCE_SCAN", None)
                out = buf.getvalue()
                wake = json.loads(out.strip().splitlines()[-1])
                return rc, wake.get("wakeAgent"), out

            def add_open_task():
                c = sqlite3.connect(str(db_path))
                c.execute(
                    "INSERT INTO tasks (id, board_slug, title, status, created_at, updated_at)"
                    " VALUES (?, ?, ?, 'todo', 1, 1)",
                    (slug + "-t1", slug, "Open task"),
                )
                c.commit()
                c.close()

            # --- Run 1: brand-new board (no last_scanned_sha) -> one-time baseline.
            rc, wake1, _ = run_gate()
            self.assertEqual(rc, 0)
            self.assertTrue(wake1, "first-ever board must fire a baseline scan")

            # --- Run 2: same HEAD + clean worktree + 0 open tasks -> SUPPRESS (0 tokens).
            # This is the exact steady state that used to re-wake the LLM every tick.
            rc, wake2, out2 = run_gate()
            self.assertEqual(rc, 0)
            self.assertFalse(
                wake2,
                "unchanged + already-scanned board with 0 open tasks must suppress; got:\n" + out2,
            )
            self.assertIn("wakeAgent", out2.strip().splitlines()[-1])

            # --- Run 3: same HEAD + clean worktree but now WITH an open task -> STILL SUPPRESS.
            # Proves suppression no longer depends on open-task count (the root cause).
            add_open_task()
            rc, wake3, _ = run_gate()
            self.assertEqual(rc, 0)
            self.assertFalse(wake3, "suppression must be independent of open-task count")

            # --- Run 4: a new commit lands -> re-wake for a scan.
            (repo / "b.py").write_text("y = 2\n", encoding="utf-8")
            git(repo, "add", ".")
            git(repo, "commit", "-qm", "second")
            rc, wake4, _ = run_gate()
            self.assertEqual(rc, 0)
            self.assertTrue(wake4, "a new commit must re-trigger the scanner")

            # --- Run 5: same (new) HEAD + clean worktree -> suppress again.
            rc, wake5, _ = run_gate()
            self.assertEqual(rc, 0)
            self.assertFalse(wake5, "after the new commit is scanned, an unchanged run suppresses")

            # --- Run 6: dirty worktree (modified tracked file) -> re-wake.
            (repo / "a.py").write_text("x = 1  # tweak\n", encoding="utf-8")
            rc, wake6, _ = run_gate()
            self.assertEqual(rc, 0)
            self.assertTrue(wake6, "a dirty worktree must re-trigger the scanner")

    def test_25b_scanner_gate_auto_pull_remote(self):
        """Verify that zf_scanner_gate automatically fast-forwards clean tracking branch
        when remote origin has new commits, waking the agent.
        """
        import contextlib
        import importlib.util
        import io
        import json
        import sqlite3
        import subprocess

        gate_path = (Path(__file__).resolve().parent / "scripts" / "zf_scanner_gate.py").resolve()

        def git(repo, *args):
            return subprocess.run(
                ["git", *args], cwd=str(repo), check=True,
                capture_output=True, text=True,
                env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"},
            )

        def load_gate():
            spec = importlib.util.spec_from_file_location("zf_scanner_gate_under_test", gate_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            slug = "gate-remote-test-board"

            # 1. Bare remote repository
            remote_repo = td / "remote.git"
            remote_repo.mkdir()
            git(remote_repo, "init", "--bare", "-b", "main")

            # 2. Local clone
            local_repo = td / "local_repo"
            git(td, "clone", str(remote_repo), str(local_repo))
            git(local_repo, "config", "user.email", "scan@test.local")
            git(local_repo, "config", "user.name", "Scan Test")
            (local_repo / "main.py").write_text("print('v1')\n", encoding="utf-8")
            git(local_repo, "add", ".")
            git(local_repo, "commit", "-qm", "initial commit")
            git(local_repo, "push", "-u", "origin", "main")

            # 3. Temp zerofactory.db
            db_path = td / "gate.db"
            conn = sqlite3.connect(str(db_path))
            conn.executescript(
                "CREATE TABLE boards ("
                " slug TEXT PRIMARY KEY, description TEXT DEFAULT '', git_url TEXT DEFAULT '',"
                " created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);"
                "CREATE TABLE tasks ("
                " id TEXT PRIMARY KEY, board_slug TEXT NOT NULL DEFAULT '', title TEXT NOT NULL,"
                " description TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'triage',"
                " assignee TEXT NOT NULL DEFAULT 'unassigned', priority TEXT NOT NULL DEFAULT 'P2',"
                " workspace_path TEXT, workspace_kind TEXT DEFAULT 'worktree', branch_name TEXT,"
                " pr_url TEXT, tenant TEXT DEFAULT '', skills TEXT DEFAULT '[]',"
                " tags TEXT DEFAULT '[]', metadata TEXT DEFAULT '{}',"
                " created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);"
            )
            conn.execute(
                "INSERT INTO boards (slug, created_at, updated_at) VALUES (?, 1, 1)",
                (slug,),
            )
            conn.commit()
            conn.close()

            state_path = td / "scanner_state.json"

            def run_gate():
                mod = load_gate()
                mod.STATE_FILE = state_path
                old_argv, old_cwd = sys.argv, os.getcwd()
                old_db = os.environ.get("ZEROFACTORY_DB")
                sys.argv = [gate_path.name, slug]
                os.chdir(str(local_repo))
                os.environ["ZEROFACTORY_DB"] = str(db_path)
                os.environ.pop("ZEROFACTORY_FORCE_SCAN", None)
                buf = io.StringIO()
                try:
                    with contextlib.redirect_stdout(buf):
                        rc = mod.run_scanner_gate()
                finally:
                    sys.argv = old_argv
                    os.chdir(old_cwd)
                    if old_db is None:
                        os.environ.pop("ZEROFACTORY_DB", None)
                    else:
                        os.environ["ZEROFACTORY_DB"] = old_db
                    os.environ.pop("ZEROFACTORY_FORCE_SCAN", None)
                out = buf.getvalue()
                wake = json.loads(out.strip().splitlines()[-1])
                return rc, wake.get("wakeAgent"), out

            # Baseline scan
            rc1, wake1, _ = run_gate()
            self.assertEqual(rc1, 0)
            self.assertTrue(wake1)

            # Steady state scan -> suppressed (0 tokens)
            rc2, wake2, _ = run_gate()
            self.assertEqual(rc2, 0)
            self.assertFalse(wake2)

            # Push a new commit to remote from a secondary clone
            worker_repo = td / "worker_repo"
            git(td, "clone", str(remote_repo), str(worker_repo))
            git(worker_repo, "config", "user.email", "remote@test.local")
            git(worker_repo, "config", "user.name", "Remote Worker")
            (worker_repo / "main.py").write_text("print('v2-merged-pr')\n", encoding="utf-8")
            git(worker_repo, "commit", "-am", "merged PR into main")
            git(worker_repo, "push", "origin", "main")
            remote_sha = git(worker_repo, "rev-parse", "HEAD").stdout.strip()

            # Verify local_repo is initially behind before gate runs
            local_sha_before = git(local_repo, "rev-parse", "HEAD").stdout.strip()
            self.assertNotEqual(local_sha_before, remote_sha)

            # Gate runs on local_repo: should auto-pull remote and wake agent
            rc3, wake3, out3 = run_gate()
            self.assertEqual(rc3, 0)
            self.assertTrue(wake3, "auto-pulling new remote commit should wake agent")

            # Verify local_repo HEAD was fast-forwarded to remote_sha
            local_sha_after = git(local_repo, "rev-parse", "HEAD").stdout.strip()
            self.assertEqual(local_sha_after, remote_sha)

            # Next run without new remote commits suppresses again
            rc4, wake4, _ = run_gate()
            self.assertEqual(rc4, 0)
            self.assertFalse(wake4)

    def test_26_task_pr_url_and_stats(self):
        """Verify task pr_url persistence, update, and get_stats pr_count metric."""
        # 1. Create task with pr_url
        req = TaskCreate(
            title="Task with Pull Request",
            description="Testing PR integration",
            board_slug="hotcode-dev-zerofactory",
            pr_url="https://github.com/hotcode-dev/zerofactory/pull/42"
        )
        task_id = create_task(req)["id"]
        
        # 2. Verify pr_url in get_task
        task = get_task(task_id)["task"]
        self.assertEqual(task["pr_url"], "https://github.com/hotcode-dev/zerofactory/pull/42")

        # 3. Verify get_stats pr_count
        stats = get_stats(board="hotcode-dev-zerofactory")
        self.assertTrue(stats["ok"])
        self.assertIn("pr_count", stats)
        self.assertGreaterEqual(stats["pr_count"], 1)
        initial_pr_count = stats["pr_count"]

        # 4. Update pr_url
        up_res = update_task(task_id, TaskUpdate(pr_url="https://github.com/hotcode-dev/zerofactory/pull/99"))
        self.assertTrue(up_res["ok"])
        updated_task = get_task(task_id)["task"]
        self.assertEqual(updated_task["pr_url"], "https://github.com/hotcode-dev/zerofactory/pull/99")

        # 5. Clear pr_url and verify pr_count reflects it
        clear_res = update_task(task_id, TaskUpdate(pr_url=""))
        self.assertTrue(clear_res["ok"])
        cleared_task = get_task(task_id)["task"]
        self.assertEqual(cleared_task["pr_url"], "")

        stats_after = get_stats(board="hotcode-dev-zerofactory")
        self.assertEqual(stats_after["pr_count"], initial_pr_count - 1)

    def test_27_no_board_cron_generation(self):
        """Verify that when no boards exist, no improvement scanner jobs are generated."""
        from builtin_cron import get_all_builtin_cron_jobs
        import sqlite3

        with tempfile.TemporaryDirectory() as empty_td:
            empty_db = Path(empty_td) / "empty.db"
            with sqlite3.connect(str(empty_db)) as conn:
                conn.execute("CREATE TABLE boards (id INTEGER PRIMARY KEY, slug TEXT UNIQUE, description TEXT, git_url TEXT, created_at REAL, updated_at REAL)")
                conn.commit()

            import builtin_cron
            orig_get_db_path = builtin_cron.get_db_path
            builtin_cron.get_db_path = lambda: empty_db
            try:
                jobs = get_all_builtin_cron_jobs()
                scanner_jobs = [jid for jid in jobs if jid.startswith("zero-factory-improvement-scanner-")]
                self.assertEqual(scanner_jobs, [])
                self.assertIn("zero-factory-task-queue-check", jobs)
                self.assertIn("zero-factory-daily-report", jobs)
            finally:
                builtin_cron.get_db_path = orig_get_db_path

    def test_28_git_url_ssh_and_http_resolution(self):
        """Verify that resolve_board_repo_path correctly parses both HTTP and SSH git URLs."""
        from builtin_cron import resolve_board_repo_path

        # 1. HTTP URL
        b_http = {"slug": "test-repo", "git_url": "https://github.com/hotcode-dev/zerofactory.git"}
        # 2. SSH URL
        b_ssh = {"slug": "test-repo", "git_url": "git@github.com:hotcode-dev/zerofactory.git"}
        # 3. SSH protocol URL
        b_ssh_proto = {"slug": "test-repo", "git_url": "ssh://git@github.com/hotcode-dev/zerofactory.git"}
        # 4. Description fallback with SSH
        b_desc_ssh = {"slug": "test-repo", "description": "Project at git@github.com:hotcode-dev/zerofactory.git"}

        # Current workspace is zerofactory, which should resolve for all of these
        resolved_http = resolve_board_repo_path(b_http)
        resolved_ssh = resolve_board_repo_path(b_ssh)
        resolved_ssh_proto = resolve_board_repo_path(b_ssh_proto)
        resolved_desc = resolve_board_repo_path(b_desc_ssh)

        self.assertIsNotNone(resolved_http)
        self.assertEqual(resolved_http, resolved_ssh)
        self.assertEqual(resolved_http, resolved_ssh_proto)
        self.assertEqual(resolved_http, resolved_desc)

    def test_29_cron_profile_targeting_and_description_file(self):
        """Validate that trigger_builtin_job runs with -p zf-orchestrator and --description-file is supported."""
        import subprocess
        from unittest.mock import patch
        from builtin_cron import trigger_builtin_job, get_all_builtin_cron_jobs
        import tempfile

        # 1. trigger_builtin_job targets profile
        all_jobs = get_all_builtin_cron_jobs()
        job_id = "zero-factory-task-queue-check"
        self.assertIn(job_id, all_jobs)

        captured_cmd = []
        with patch("subprocess.Popen") as mock_popen:
            mock_proc = mock_popen.return_value
            mock_proc.pid = 99999
            res = trigger_builtin_job(job_id)
            self.assertTrue(res.get("ok"))
            self.assertEqual(res.get("pid"), 99999)
            call_args = mock_popen.call_args[0][0]
            self.assertIn("-p", call_args)
            self.assertIn("zf-orchestrator", call_args)
            self.assertIn(job_id, call_args)

        # 2. --description-file support in CLI parser and handler
        from __init__ import register
        import argparse
        parser = argparse.ArgumentParser()
        # Create a mock ctx to capture setup_fn and handler_fn
        class MockCtx:
            def register_cli_command(self, name, help, setup_fn, handler_fn):
                self.setup_fn = setup_fn
                self.handler_fn = handler_fn

        ctx = MockCtx()
        register(ctx)

        cmd_parser = argparse.ArgumentParser()
        ctx.setup_fn(cmd_parser)

        with tempfile.NamedTemporaryFile("w", delete=False) as tf:
            tf.write("Detailed context from file with `code` and (parentheses)\nLine 2")
            tf_path = tf.name

        try:
            parsed = cmd_parser.parse_args(["create", "Test Task", "--description-file", tf_path, "--status", "todo"])
            self.assertEqual(parsed.description_file, tf_path)
        finally:
            if os.path.exists(tf_path):
                os.unlink(tf_path)

    def test_30_reap_stuck_tasks_contract(self):
        """Validate that reap_stuck_tasks provides both reaped_tasks and reaped for watchdog compatibility."""
        from dispatcher import reap_stuck_tasks
        res = reap_stuck_tasks()
        self.assertTrue(res.get("ok"))
        self.assertIn("reaped_tasks", res)
        self.assertIn("reaped", res)
        self.assertEqual(res["reaped_tasks"], res["reaped"])

    def test_31_watchdog_reaped_alert_rendering(self):
        """Regression: watchdog's 'Reaped Stuck Tasks' alert actually renders.

        The key contract (test_30) guarantees reap_stuck_tasks exposes the keys
        the watchdog reads, but it never exercises run_watchdog() end-to-end.
        Before the fix, run_watchdog() consumed a key that was never populated,
        so reaped_count stayed 0, the has_bottleneck gate could only trip via
        the blocked>10 fallback, and a single reaped worker was silently
        swallowed behind {"wakeAgent": false}.
        """
        import io
        import contextlib
        import importlib.util
        from pathlib import Path as _Path
        from unittest.mock import MagicMock
        from dispatcher import _active_workers
        from dashboard.plugin_api import get_db_conn, get_task

        # Ensure the default board exists (this test can run in isolation).
        existing = [b["slug"] for b in list_boards()["boards"]]
        if "hotcode-dev-zerofactory" not in existing:
            create_board(BoardCreate(
                git_url="https://github.com/hotcode-dev/zerofactory",
                description="AI workflow",
            ))

        # Clean slate so run_dispatch_cycle() inside run_watchdog() doesn't
        # re-dispatch leftover tasks from earlier tests.
        with get_db_conn() as conn:
            conn.execute("UPDATE tasks SET status = 'done' WHERE status IN ('running', 'ready')")
            conn.commit()

        # Seed a stuck running task: registered worker already exited (poll() -> 1),
        # so check_stuck_tasks flags "Worker process PID is dead/not found".
        t_id = create_task(TaskCreate(
            title="Watchdog Stuck Task",
            status="running",
            priority="P0",
            assignee="zf-builder",
        ))["id"]
        dead_proc = MagicMock()
        dead_proc.poll.return_value = 1
        dead_proc.pid = 12346
        _active_workers[t_id] = dead_proc

        wd_path = _Path(__file__).resolve().parent / "scripts" / "zf_queue_watchdog.py"
        spec = importlib.util.spec_from_file_location("zf_queue_watchdog_test", wd_path)
        self.assertIsNotNone(spec)
        wd = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(wd)

        # Prevent run_dispatch_cycle() from spawning a real worker subprocess.
        os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = "1"
        buf = io.StringIO()
        try:
            with contextlib.redirect_stdout(buf):
                rc = wd.run_watchdog()
        finally:
            os.environ.pop("ZEROFACTORY_SKIP_WORKER_SPAWN", None)

        out = buf.getvalue()
        self.assertEqual(rc, 0)
        # The alert section rendered (dead code before the fix):
        self.assertIn("Reaped Stuck Tasks", out)
        self.assertIn(t_id, out)
        # A single reaped worker tripped the bottleneck gate via reaped_count > 0
        # (blocked count is well under 10), so the operator alert fired instead
        # of the silent {"wakeAgent": false} gate.
        self.assertIn("Current Board State", out)
        self.assertNotIn("wakeAgent", out)
        # And the reaped task was actually moved to 'blocked'.
        self.assertEqual(get_task(t_id)["task"]["status"], "blocked")

    def test_32_pull_main_and_pr_conflict_guardrail(self):
        """Validate that dispatcher pulls main branch, detects merge conflicts, and routes back to zf-builder."""
        import tempfile
        import subprocess
        import sqlite3
        import json
        from unittest.mock import patch, MagicMock
        from dispatcher import (
            get_default_branch,
            sync_repo_main,
            check_unresolved_conflicts,
            pull_and_merge_main,
            spawn_agent_worker,
            run_dispatch_cycle,
        )

        import shutil
        orig_skip_git = os.environ.pop("ZEROFACTORY_SKIP_GIT", None)
        td = tempfile.mkdtemp()
        try:
            repo_path = Path(td) / "test_repo"
            repo_path.mkdir()

            # Initialize git repository
            subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_path), check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo_path), check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_path), check=True)

            readme = repo_path / "README.md"
            readme.write_text("# Test Repo\nLine 1\n")
            subprocess.run(["git", "add", "."], cwd=str(repo_path), check=True)
            subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_path), check=True, capture_output=True)

            # 1. Test get_default_branch and sync_repo_main
            self.assertEqual(get_default_branch(repo_path), "main")
            self.assertEqual(sync_repo_main(repo_path), "main")

            # 2. Test check_unresolved_conflicts on clean repo
            self.assertEqual(check_unresolved_conflicts(repo_path), [])

            # Write conflict markers and verify detection
            conflict_file = repo_path / "conflict.txt"
            conflict_file.write_text(f"{'<' * 7} HEAD\nLocal Change\n{'=' * 7}\nMain Change\n{'>' * 7} main\n")
            self.assertIn("conflict.txt", check_unresolved_conflicts(repo_path))
            conflict_file.unlink()
            self.assertEqual(check_unresolved_conflicts(repo_path), [])

            # 3. Create a worktree for a task branch
            worktree_dir = Path(td) / "worktree_task_1"
            subprocess.run(
                ["git", "worktree", "add", str(worktree_dir), "-b", "task/task-1"],
                cwd=str(repo_path), check=True, capture_output=True
            )

            # Initially up-to-date with main
            ok, conflicts, msg = pull_and_merge_main(worktree_dir, repo_path, "main")
            self.assertTrue(ok)
            self.assertEqual(conflicts, [])
            self.assertIn("already up to date", msg)

            # Modify README in main
            readme.write_text("# Test Repo\nLine 1\nMain change A\n")
            subprocess.run(["git", "commit", "-am", "Main update"], cwd=str(repo_path), check=True, capture_output=True)

            # Fast-forward / clean merge in worktree
            ok, conflicts, msg = pull_and_merge_main(worktree_dir, repo_path, "main")
            self.assertTrue(ok)
            self.assertEqual(conflicts, [])

            # Now create a conflict: main modifies line 3 to X, worktree modifies line 3 to Y
            readme.write_text("# Test Repo\nLine 1\nMain change X\n")
            subprocess.run(["git", "commit", "-am", "Main conflict commit"], cwd=str(repo_path), check=True, capture_output=True)

            wt_readme = worktree_dir / "README.md"
            wt_readme.write_text("# Test Repo\nLine 1\nWorktree change Y\n")
            subprocess.run(["git", "commit", "-am", "Task commit with conflict"], cwd=str(worktree_dir), check=True, capture_output=True)

            # pull_and_merge_main should detect conflict
            ok, conflicts, err = pull_and_merge_main(worktree_dir, repo_path, "main")
            self.assertFalse(ok)
            self.assertIn("README.md", conflicts)

            # Verify prompt generation detects merge conflict
            orig_popen = subprocess.Popen
            captured_cmd = []

            def fake_popen(cmd, *args, **kwargs):
                if isinstance(cmd, list) and len(cmd) > 0 and "chat" in cmd:
                    captured_cmd.append(cmd)
                    m = MagicMock()
                    m.pid = 12345
                    return m
                return orig_popen(cmd, *args, **kwargs)

            with patch("subprocess.Popen", side_effect=fake_popen):
                pid, sid = spawn_agent_worker(
                    "task-1",
                    "Implement feature [PR Conflict]",
                    "Desc",
                    "P1",
                    "zf-builder",
                    str(worktree_dir),
                    "task/task-1"
                )
                self.assertEqual(pid, 12345)
                self.assertTrue(captured_cmd)
                call_args = captured_cmd[0]
                q_idx = call_args.index("-q")
                prompt_text = call_args[q_idx + 1]
                self.assertIn("CRITICAL: MERGE CONFLICT DETECTED WITH MAIN BRANCH", prompt_text)
                self.assertIn("README.md", prompt_text)
                self.assertIn("fix(merge): resolve merge conflicts with main", prompt_text)

            # 4. Dispatcher Step 3 conflict guardrail in SQLite
            db_file = Path(td) / "test_zf.db"
            with sqlite3.connect(str(db_file)) as conn:
                conn.execute("""
                    CREATE TABLE tasks (
                        id TEXT PRIMARY KEY,
                        title TEXT,
                        description TEXT,
                        priority TEXT,
                        status TEXT,
                        assignee TEXT,
                        skills TEXT,
                        workspace_kind TEXT,
                        workspace_path TEXT,
                        branch_name TEXT,
                        pr_url TEXT,
                        metadata TEXT,
                        tenant TEXT,
                        board_slug TEXT,
                        created_at REAL,
                        updated_at REAL
                    )
                """)
                conn.execute("""
                    CREATE TABLE task_activity (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id TEXT,
                        actor TEXT,
                        action TEXT,
                        details TEXT,
                        created_at REAL
                    )
                """)
                conn.execute("""
                    CREATE TABLE task_comments (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        task_id TEXT,
                        author TEXT,
                        body TEXT,
                        created_at REAL
                    )
                """)
                conn.execute("CREATE TABLE task_links (id INTEGER PRIMARY KEY, parent_id TEXT, child_id TEXT, link_type TEXT)")
                conn.execute("CREATE TABLE boards (id INTEGER PRIMARY KEY, slug TEXT UNIQUE, description TEXT, git_url TEXT, created_at REAL, updated_at REAL)")

                # Insert a task that is blocked and author finished, but has conflict in worktree
                conn.execute("""
                    INSERT INTO tasks (id, title, status, assignee, workspace_path, branch_name, created_at, updated_at)
                    VALUES ('task-1', 'Implement feature', 'blocked', 'zf-builder', ?, 'task/task-1', 1000, 1000)
                """, (str(worktree_dir),))
                conn.commit()

            # Run dispatch cycle
            cycle_res = run_dispatch_cycle(db_file)
            self.assertTrue(cycle_res["ok"])

            # Verify task was rerouted to zf-builder with [PR Conflict] in title
            with sqlite3.connect(str(db_file)) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("SELECT * FROM tasks WHERE id = 'task-1'")
                t_row = cur.fetchone()
                self.assertEqual(t_row["status"], "ready")
                self.assertEqual(t_row["assignee"], "zf-builder")
                self.assertIn("[PR Conflict]", t_row["title"])
                # Worktree should NOT be deleted
                self.assertTrue(worktree_dir.exists())

                # Verify task activity recorded pr_conflict
                cur.execute("SELECT * FROM task_activity WHERE task_id = 'task-1' AND action = 'pr_conflict'")
                act_row = cur.fetchone()
                self.assertIsNotNone(act_row)
                self.assertIn("README.md", act_row["details"])

                # Verify task comment recorded
                cur.execute("SELECT * FROM task_comments WHERE task_id = 'task-1'")
                cmt_row = cur.fetchone()
                self.assertIsNotNone(cmt_row)
                self.assertIn("Merge Conflict Detected", cmt_row["body"])

            # 5. Test Reviewer GitHub CONFLICTING status detection
            with sqlite3.connect(str(db_file)) as conn:
                # Set up task as under review with PR
                conn.execute("""
                    UPDATE tasks SET status = 'blocked', assignee = 'zf-reviewer', pr_url = 'https://github.com/hotcode-dev/zerofactory/pull/99', title = 'Task 2 [PR Opened by zf-builder]'
                    WHERE id = 'task-1'
                """)
                conn.commit()

            # Mock gh pr view returning CONFLICTING
            fake_pr_json = json.dumps({
                "state": "OPEN",
                "reviewDecision": None,
                "url": "https://github.com/hotcode-dev/zerofactory/pull/99",
                "mergeable": "CONFLICTING"
            })

            orig_run = subprocess.run

            def fake_run(cmd, *args, **kwargs):
                if len(cmd) >= 3 and cmd[0] == "gh" and cmd[1] == "pr" and cmd[2] == "view":
                    res = MagicMock()
                    res.returncode = 0
                    res.stdout = fake_pr_json
                    return res
                return orig_run(cmd, *args, **kwargs)

            with patch("subprocess.run", side_effect=fake_run):
                run_dispatch_cycle(db_file)

            with sqlite3.connect(str(db_file)) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("SELECT * FROM tasks WHERE id = 'task-1'")
                t_row = cur.fetchone()
                self.assertEqual(t_row["status"], "ready")
                self.assertEqual(t_row["assignee"], "zf-builder")
                self.assertIn("[PR Conflict]", t_row["title"])
        finally:
            shutil.rmtree(td, ignore_errors=True)
            if orig_skip_git is not None:
                os.environ["ZEROFACTORY_SKIP_GIT"] = orig_skip_git

    def test_32b_conflict_check_fail_closed(self):
        """check_unresolved_conflicts must FAIL CLOSED when the authoritative git
        unmerged-index or status-porcelain query raises (transient git failure,
        locked index, half-broken repo). It must NOT silently return [] on a
        worktree that actually has an unresolved conflict, and pull_and_merge_main
        must not auto-merge / claim-clean an unverifiable worktree.

        Regression guard for dispatcher.py:260 (previously `except Exception: pass`
        swallowed the error and returned an empty conflict list -> unsafe auto-merge).
        """
        import tempfile
        import shutil
        import subprocess
        from unittest.mock import patch
        from dispatcher import (
            check_unresolved_conflicts,
            check_unresolved_conflicts_safe,
            pull_and_merge_main,
            GitConflictCheckError,
        )

        td = tempfile.mkdtemp()
        try:
            repo_path = Path(td) / "repo"
            repo_path.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_path), check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "T"], cwd=str(repo_path), check=True)
            subprocess.run(["git", "config", "user.email", "t@e.com"], cwd=str(repo_path), check=True)
            (repo_path / "README.md").write_text("# repo\n")
            subprocess.run(["git", "add", "."], cwd=str(repo_path), check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo_path), check=True, capture_output=True)
            wt = Path(td) / "wt"
            subprocess.run(["git", "worktree", "add", str(wt), "-b", "task/wt"], cwd=str(repo_path), check=True, capture_output=True)

            orig_run = subprocess.run

            # --- Case A: unmerged-index query (step 1, diff-filter=U) raises ---
            def fail_unmerged(cmd, *a, **k):
                if isinstance(cmd, list) and any("--diff-filter=U" in c for c in cmd):
                    raise OSError("index.lock held / transient git failure")
                return orig_run(cmd, *a, **k)

            with patch("subprocess.run", side_effect=fail_unmerged):
                # raw function must RAISE, not silently return []
                with self.assertRaises(GitConflictCheckError):
                    check_unresolved_conflicts(wt)
                # safe wrapper must report "could not verify" (verified=False)
                ok, files, err = check_unresolved_conflicts_safe(wt)
                self.assertFalse(ok)
                self.assertEqual(files, [])
                self.assertIn("could not verify", err)
                # pull_and_merge_main must NOT auto-merge / claim a clean merge
                ok2, files2, msg2 = pull_and_merge_main(wt, repo_path, "main")
                self.assertFalse(ok2)
                self.assertEqual(files2, ["(unverifiable)"])
                self.assertIn("fail-closed", msg2)

            # --- Case B: status-porcelain query (step 2) raises ---
            def fail_porcelain(cmd, *a, **k):
                if isinstance(cmd, list) and cmd[0] == "git" and "status" in cmd:
                    raise OSError("status query failed")
                return orig_run(cmd, *a, **k)

            with patch("subprocess.run", side_effect=fail_porcelain):
                with self.assertRaises(GitConflictCheckError):
                    check_unresolved_conflicts(wt)
                ok, _files, err = check_unresolved_conflicts_safe(wt)
                self.assertFalse(ok)
                self.assertIn("status --porcelain", err)

            # --- Case C: healthy path still reports verified-clean (no regression) ---
            ok, files, err = check_unresolved_conflicts_safe(repo_path)
            self.assertTrue(ok)
            self.assertEqual(files, [])
            self.assertEqual(err, "")
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_32c_dispatch_pre_implement_fail_closed_skips_auto_merge(self):
        """Dispatch-level fail-closed: a ready zf-builder task whose worktree
        conflict state CANNOT be verified must NOT be auto-merged via
        pull_and_merge_main (the unsafe advance). The task is still dispatched so
        the builder can sync with main itself and resolve any real conflict it
        encounters; the post-worker guardrail is the final safety net before push.
        """
        from dispatcher import run_dispatch_cycle
        import json
        import shutil
        import sqlite3
        import tempfile
        from unittest.mock import patch

        orig_skip_git = os.environ.pop("ZEROFACTORY_SKIP_GIT", None)
        td = tempfile.mkdtemp(prefix="zf-fail-closed-pre-")
        try:
            db_file = Path(td) / "fail_closed.db"
            self._create_conflict_test_db(db_file)
            repo_dir = Path(td) / "main_repo"
            repo_dir.mkdir()
            ws_dir = Path(td) / "ws_task_unverifiable"
            ws_dir.mkdir()

            with sqlite3.connect(str(db_file)) as conn:
                conn.execute("""
                    INSERT INTO tasks (id, title, status, assignee, workspace_path, branch_name, created_at, updated_at)
                    VALUES ('task-fc-1', 'Build feature Z', 'ready', 'zf-builder', ?, 'task/task-fc-1', 1000, 1000)
                """, (str(ws_dir),))
                conn.commit()

            # check_unresolved_conflicts_safe reports the worktree as UNVERIFIABLE
            with patch("dispatcher.reap_active_workers", return_value=0), \
                 patch("dispatcher.resolve_task_repo_path", return_value=repo_dir), \
                 patch("dispatcher.check_unresolved_conflicts_safe", return_value=(False, [], "simulated git error")) as mock_safe, \
                 patch("dispatcher.pull_and_merge_main", return_value=(True, [], "ok")) as mock_pull, \
                 patch("dispatcher.spawn_agent_worker", return_value=(99903, "sess-fc")) as mock_spawn:
                res = run_dispatch_cycle(db_file)
                self.assertTrue(res.get("ok"))
                mock_safe.assert_called_once()
                # The critical assertion: the worktree was NOT auto-merged.
                mock_pull.assert_not_called()
                # The task was still dispatched (builder syncs/itself resolves).
                mock_spawn.assert_called_once()

            with sqlite3.connect(str(db_file)) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute("SELECT status, metadata FROM tasks WHERE id = 'task-fc-1'").fetchone()
                self.assertEqual(row["status"], "running")
                meta = json.loads(row["metadata"])
                self.assertEqual(meta["worker_pid"], 99903)
        finally:
            shutil.rmtree(td, ignore_errors=True)
            if orig_skip_git is not None:
                os.environ["ZEROFACTORY_SKIP_GIT"] = orig_skip_git

    def test_33_worktree_symlink_guardrail_and_resolution(self):
        """Verify that get_plugin_root() resolves main repo from inside worktrees and ensure_plugin_symlinks cleans up worktree symlinks."""
        from profile_manager import get_plugin_root, ensure_plugin_symlinks
        import shutil
        import tempfile
        from unittest.mock import patch

        canonical_repo = Path(__file__).resolve().parent

        # 1. Normal resolution from main repo
        self.assertEqual(get_plugin_root(), canonical_repo)

        # 2. Simulated worktree directory with .git pointer file
        td = tempfile.mkdtemp(prefix="zf-worktree-test-")
        try:
            worktree_dir = Path(td) / "zerofactory-worktrees" / "zf-test123"
            worktree_dir.mkdir(parents=True, exist_ok=True)
            # Create a .git file mimicking git worktree pointer
            git_file = worktree_dir / ".git"
            dummy_gitdir = canonical_repo / ".git" / "worktrees" / "zf-test123"
            git_file.write_text(f"gitdir: {dummy_gitdir}\n", encoding="utf-8")

            # Patch __file__ to simulate executing from inside the worktree
            fake_pm_file = str(worktree_dir / "profile_manager.py")
            with patch("profile_manager.__file__", fake_pm_file):
                resolved = get_plugin_root()
                self.assertEqual(resolved, canonical_repo)

            # 3. Guardrail: ensure_plugin_symlinks unlinks any worktree link
            hermes_fake = Path(td) / "fake_hermes"
            hermes_fake.mkdir(parents=True, exist_ok=True)
            fake_plugins = hermes_fake / "plugins"
            fake_plugins.mkdir(parents=True, exist_ok=True)
            bad_link = fake_plugins / "zerofactory"
            bad_target = worktree_dir
            bad_link.symlink_to(bad_target, target_is_directory=True)
            self.assertTrue(bad_link.is_symlink())
            self.assertIn("worktrees", str(bad_link.resolve()))

            with patch("profile_manager.get_hermes_home", return_value=hermes_fake):
                ensure_plugin_symlinks()
                # Must have replaced the bad worktree link with canonical repo
                self.assertTrue(bad_link.is_symlink())
                self.assertEqual(bad_link.resolve(), canonical_repo)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_34_stop_task_worker(self):
        """Verify stop_task_worker terminates active worker and removes it from tracking."""
        from dispatcher import stop_task_worker, _active_workers
        from unittest.mock import MagicMock, patch

        mock_proc = MagicMock()
        mock_proc.pid = 88888
        _active_workers["task-test-stop"] = mock_proc

        with patch("dispatcher.terminate_worker_process") as mock_term:
            stop_task_worker("task-test-stop")
            self.assertNotIn("task-test-stop", _active_workers)
            mock_term.assert_called_once_with(mock_proc, 88888)
    def _create_conflict_test_db(self, db_file: Path) -> None:
        """Create the scratch SQLite schema used by the conflict-handling tests."""
        import sqlite3
        with sqlite3.connect(str(db_file)) as conn:
            conn.execute("""
                CREATE TABLE tasks (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    description TEXT,
                    priority TEXT,
                    status TEXT,
                    assignee TEXT,
                    skills TEXT,
                    workspace_kind TEXT,
                    workspace_path TEXT,
                    branch_name TEXT,
                    pr_url TEXT,
                    metadata TEXT,
                    tenant TEXT,
                    board_slug TEXT,
                    created_at REAL,
                    updated_at REAL
                )
            """)
            conn.execute("""
                CREATE TABLE task_activity (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT,
                    actor TEXT,
                    action TEXT,
                    details TEXT,
                    created_at REAL
                )
            """)
            conn.execute("""
                CREATE TABLE task_comments (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    task_id TEXT,
                    author TEXT,
                    body TEXT,
                    created_at REAL
                )
            """)
            conn.execute("CREATE TABLE task_links (id INTEGER PRIMARY KEY, parent_id TEXT, child_id TEXT, link_type TEXT)")
            conn.execute("CREATE TABLE boards (id INTEGER PRIMARY KEY, slug TEXT UNIQUE, description TEXT, git_url TEXT, created_at REAL, updated_at REAL)")
            conn.commit()

    def test_35_handle_local_merge_conflict_direct(self):
        """Directly unit-test _handle_local_merge_conflict: title tag, assignee, status,
        activity + comment rows, and [PR Conflict] idempotency on repeated calls."""
        from dispatcher import _handle_local_merge_conflict
        import shutil
        import sqlite3
        import time

        td = tempfile.mkdtemp()
        try:
            db_file = Path(td) / "conflict_local.db"
            self._create_conflict_test_db(db_file)
            ws_dir = Path(td) / "ws_local"
            ws_dir.mkdir()

            with sqlite3.connect(str(db_file)) as conn:
                conn.execute("""
                    INSERT INTO tasks (id, title, status, assignee, workspace_path, branch_name, created_at, updated_at)
                    VALUES ('task-lc', 'Fix bug', 'running', 'zf-builder', ?, 'task/task-lc', 1000, 1000)
                """, (str(ws_dir),))
                conn.commit()

            now = int(time.time())
            with sqlite3.connect(str(db_file)) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()

                # First call: appends [PR Conflict] and records side effects
                _handle_local_merge_conflict(cur, "task-lc", "Fix bug", str(ws_dir), ["a.txt", "b.txt"], now, "merge failed")
                conn.commit()

                row = cur.execute("SELECT title, assignee, status FROM tasks WHERE id = 'task-lc'").fetchone()
                self.assertEqual(row["title"], "Fix bug [PR Conflict]")
                self.assertEqual(row["assignee"], "zf-builder")
                self.assertEqual(row["status"], "ready")

                act = cur.execute("SELECT actor, action, details FROM task_activity WHERE task_id = 'task-lc' AND action = 'pr_conflict'").fetchone()
                self.assertIsNotNone(act)
                self.assertEqual(act["actor"], "dispatcher")
                self.assertIn("a.txt", act["details"])
                self.assertIn("b.txt", act["details"])

                cmt = cur.execute("SELECT author, body FROM task_comments WHERE task_id = 'task-lc'").fetchone()
                self.assertIsNotNone(cmt)
                self.assertEqual(cmt["author"], "dispatcher")
                self.assertIn("Merge Conflict Detected", cmt["body"])

                # Second call on the already-tagged title: tag must NOT be duplicated
                _handle_local_merge_conflict(cur, "task-lc", "Fix bug [PR Conflict]", str(ws_dir), [], now, "merge failed")
                conn.commit()

                row2 = cur.execute("SELECT title, assignee, status FROM tasks WHERE id = 'task-lc'").fetchone()
                self.assertEqual(row2["title"], "Fix bug [PR Conflict]")
                self.assertNotIn("[PR Conflict] [PR Conflict]", row2["title"])
                self.assertEqual(row2["assignee"], "zf-builder")
                self.assertEqual(row2["status"], "ready")
                # Two activity rows, two comment rows (idempotency covers the title only)
                self.assertEqual(cur.execute("SELECT COUNT(*) FROM task_activity WHERE task_id = 'task-lc' AND action = 'pr_conflict'").fetchone()[0], 2)
                self.assertEqual(cur.execute("SELECT COUNT(*) FROM task_comments WHERE task_id = 'task-lc'").fetchone()[0], 2)

            # Title that already carries [Merge Conflict] must not gain a second tag either
            with sqlite3.connect(str(db_file)) as conn:
                conn.row_factory = sqlite3.Row
                conn.execute("UPDATE tasks SET title = 'Fix bug [Merge Conflict]', status = 'running' WHERE id = 'task-lc'")
                conn.commit()
                cur = conn.cursor()
                _handle_local_merge_conflict(cur, "task-lc", "Fix bug [Merge Conflict]", str(ws_dir), [], now)
                conn.commit()
                row3 = cur.execute("SELECT title FROM tasks WHERE id = 'task-lc'").fetchone()
                self.assertEqual(row3["title"], "Fix bug [Merge Conflict]")
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_36_github_conflicting_pr_routes_to_builder(self):
        """Unit-test the GitHub-CONFLICTING branch: a reviewer task whose PR is
        mergeable == 'CONFLICTING' is re-routed to the author with [PR Conflict] tag,
        status 'ready', and pr_conflict activity + comment rows."""
        from dispatcher import run_dispatch_cycle
        import json
        import shutil
        import sqlite3
        import subprocess
        from unittest.mock import patch, MagicMock

        orig_skip_git = os.environ.pop("ZEROFACTORY_SKIP_GIT", None)
        td = tempfile.mkdtemp()
        try:
            # Build a real git repo + worktree so the dispatcher can resolve
            # the repository root via `git rev-parse --git-common-dir`.
            repo_path = Path(td) / "test_repo"
            repo_path.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_path), check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo_path), check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_path), check=True)
            (repo_path / "README.md").write_text("# Test Repo\n")
            subprocess.run(["git", "add", "."], cwd=str(repo_path), check=True)
            subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_path), check=True, capture_output=True)

            reviewer_ws = Path(td) / "ws_reviewer"
            subprocess.run(
                ["git", "worktree", "add", str(reviewer_ws), "-b", "task/task-gh"],
                cwd=str(repo_path), check=True, capture_output=True
            )
            self.assertTrue(reviewer_ws.exists())

            db_file = Path(td) / "conflict_gh.db"
            self._create_conflict_test_db(db_file)

            with sqlite3.connect(str(db_file)) as conn:
                conn.execute("""
                    INSERT INTO tasks (id, title, status, assignee, workspace_path, branch_name, pr_url, created_at, updated_at)
                    VALUES ('task-gh', 'Fix bug [PR Opened by zf-builder]', 'blocked', 'zf-reviewer', ?, 'task/task-gh',
                            'https://github.com/hotcode-dev/zerofactory/pull/123', 1000, 1000)
                """, (str(reviewer_ws),))
                conn.commit()

            orig_run = subprocess.run
            captured_gh = []

            def fake_run(cmd, *args, **kwargs):
                if len(cmd) >= 3 and cmd[0] == "gh" and cmd[1] == "pr" and cmd[2] == "view":
                    captured_gh.append(list(cmd))
                    res = MagicMock()
                    res.returncode = 0
                    res.stdout = json.dumps({
                        "state": "OPEN",
                        "reviewDecision": None,
                        "url": "https://github.com/hotcode-dev/zerofactory/pull/123",
                        "mergeable": "CONFLICTING",
                    })
                    return res
                return orig_run(cmd, *args, **kwargs)

            # Stub worktree setup + conflict detection so no real git operations run
            with patch("dispatcher.setup_worktree", return_value=None) as mock_setup_wt, \
                 patch("dispatcher.check_unresolved_conflicts", return_value=[]):
                with patch("subprocess.run", side_effect=fake_run):
                    res = run_dispatch_cycle(db_file)

            self.assertTrue(res.get("ok"))
            self.assertTrue(captured_gh)
            self.assertIn("mergeable", " ".join(captured_gh[0]))
            mock_setup_wt.assert_called_once()
            # setup_worktree must be called with the re-routed author (zf-builder)
            self.assertEqual(mock_setup_wt.call_args[0][3], "zf-builder")

            with sqlite3.connect(str(db_file)) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()

                row = cur.execute("SELECT title, assignee, status FROM tasks WHERE id = 'task-gh'").fetchone()
                self.assertEqual(row["status"], "ready")
                self.assertEqual(row["assignee"], "zf-builder")
                self.assertIn("[PR Conflict]", row["title"])
                self.assertEqual(row["title"].count("[PR Conflict]"), 1)

                acts = cur.execute("SELECT details FROM task_activity WHERE task_id = 'task-gh' AND action = 'pr_conflict'").fetchall()
                self.assertEqual(len(acts), 1)
                self.assertIn("conflicting", acts[0]["details"])
                self.assertIn("zf-builder", acts[0]["details"])

                cmts = cur.execute("SELECT body FROM task_comments WHERE task_id = 'task-gh'").fetchall()
                self.assertEqual(len(cmts), 1)
                self.assertIn("PR Conflict Detected", cmts[0]["body"])

                # Reviewer worktree was force-removed before re-setup
                self.assertFalse(reviewer_ws.exists())
        finally:
            shutil.rmtree(td, ignore_errors=True)
            if orig_skip_git is not None:
                os.environ["ZEROFACTORY_SKIP_GIT"] = orig_skip_git

    def test_37_pre_implement_pull_guardrail(self):
        """Verify that run_dispatch_cycle pulls latest main before implementing,
        and routes to conflict handling if merge fails."""
        from dispatcher import run_dispatch_cycle
        import json
        import shutil
        import sqlite3
        import tempfile
        from unittest.mock import patch

        orig_skip_git = os.environ.pop("ZEROFACTORY_SKIP_GIT", None)
        td = tempfile.mkdtemp(prefix="zf-pre-implement-")
        try:
            db_file = Path(td) / "pre_implement.db"
            self._create_conflict_test_db(db_file)
            repo_dir = Path(td) / "main_repo"
            repo_dir.mkdir()
            ws_dir = Path(td) / "ws_task_builder"
            ws_dir.mkdir()

            # Case 1: Clean pull & merge before builder starts
            with sqlite3.connect(str(db_file)) as conn:
                conn.execute("""
                    INSERT INTO tasks (id, title, status, assignee, workspace_path, branch_name, created_at, updated_at)
                    VALUES ('task-pre-1', 'Build feature X', 'ready', 'zf-builder', ?, 'task/task-pre-1', 1000, 1000)
                """, (str(ws_dir),))
                conn.commit()

            with patch("dispatcher.reap_active_workers", return_value=0), \
                 patch("dispatcher.resolve_task_repo_path", return_value=repo_dir), \
                 patch("dispatcher.pull_and_merge_main", return_value=(True, [], "Already up to date")) as mock_pull, \
                 patch("dispatcher.spawn_agent_worker", return_value=(99901, "sess-1")) as mock_spawn:
                res = run_dispatch_cycle(db_file)
                self.assertTrue(res.get("ok"))
                mock_pull.assert_called_once_with(ws_dir, repo_dir)
                mock_spawn.assert_called_once()

            with sqlite3.connect(str(db_file)) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute("SELECT status, metadata FROM tasks WHERE id = 'task-pre-1'").fetchone()
                self.assertEqual(row["status"], "running")
                meta = json.loads(row["metadata"])
                self.assertEqual(meta["worker_pid"], 99901)
                conn.execute("DELETE FROM tasks WHERE id = 'task-pre-1'")
                conn.commit()

            # Case 2: Merge conflict before implement routes task to conflict handling
            ws_dir_conflict = Path(td) / "ws_task_conflict"
            ws_dir_conflict.mkdir()
            with sqlite3.connect(str(db_file)) as conn:
                conn.execute("""
                    INSERT INTO tasks (id, title, status, assignee, workspace_path, branch_name, created_at, updated_at)
                    VALUES ('task-pre-conflict', 'Implement feature Y', 'ready', 'zf-builder', ?, 'task/task-pre-conflict', 1000, 1000)
                """, (str(ws_dir_conflict),))
                conn.commit()

            with patch("dispatcher.reap_active_workers", return_value=0), \
                 patch("dispatcher.resolve_task_repo_path", return_value=repo_dir), \
                 patch("dispatcher.pull_and_merge_main", return_value=(False, ["config.py"], "Merge conflict")) as mock_pull_conflict, \
                 patch("dispatcher.spawn_agent_worker") as mock_spawn_conflict:
                res = run_dispatch_cycle(db_file)
                self.assertTrue(res.get("ok"))
                mock_pull_conflict.assert_called_once_with(ws_dir_conflict, repo_dir)
                mock_spawn_conflict.assert_not_called()

            with sqlite3.connect(str(db_file)) as conn:
                conn.row_factory = sqlite3.Row
                row_c = conn.execute("SELECT title, status, assignee FROM tasks WHERE id = 'task-pre-conflict'").fetchone()
                self.assertIn("[PR Conflict]", row_c["title"])
                self.assertEqual(row_c["status"], "ready")
                self.assertEqual(row_c["assignee"], "zf-builder")

                act = conn.execute("SELECT action, details FROM task_activity WHERE task_id = 'task-pre-conflict'").fetchone()
                self.assertEqual(act["action"], "pr_conflict")
                self.assertIn("config.py", act["details"])
                conn.execute("DELETE FROM tasks WHERE id = 'task-pre-conflict'")
                conn.commit()

            # Case 3: Non-builder (e.g. zf-reviewer) does not invoke pre-implement pull
            ws_dir_rev = Path(td) / "ws_task_rev"
            ws_dir_rev.mkdir()
            with sqlite3.connect(str(db_file)) as conn:
                conn.execute("""
                    INSERT INTO tasks (id, title, status, assignee, workspace_path, branch_name, created_at, updated_at)
                    VALUES ('task-pre-rev', 'Review PR 123', 'ready', 'zf-reviewer', ?, 'task/task-pre-rev', 1000, 1000)
                """, (str(ws_dir_rev),))
                conn.commit()

            with patch("dispatcher.reap_active_workers", return_value=0), \
                 patch("dispatcher.resolve_task_repo_path", return_value=repo_dir), \
                 patch("dispatcher.pull_and_merge_main") as mock_pull_rev, \
                 patch("dispatcher.spawn_agent_worker", return_value=(99902, "sess-rev")):
                res = run_dispatch_cycle(db_file)
                self.assertTrue(res.get("ok"))
                mock_pull_rev.assert_not_called()
        finally:
            shutil.rmtree(td, ignore_errors=True)
            if orig_skip_git is not None:
                os.environ["ZEROFACTORY_SKIP_GIT"] = orig_skip_git

    def test_38_setup_worktree_builder_merge_sync(self):
        """Verify setup_worktree syncs zf-builder worktrees with the latest default
        branch via pull_and_merge_main on BOTH the existing-branch path
        (dispatcher.py:959-961) and the new-branch path (dispatcher.py:968-970),
        and never invokes the sync for non-builder assignees. Because
        setup_worktree swallows all exceptions and returns None on failure,
        assertions check post-merge HEAD / worktree state, not just the return value."""
        import subprocess
        import sqlite3
        import tempfile
        import shutil
        from unittest.mock import patch
        from dispatcher import setup_worktree

        orig_skip_git = os.environ.pop("ZEROFACTORY_SKIP_GIT", None)
        td = tempfile.mkdtemp(prefix="zf-wt-sync-")
        try:
            repo_path = Path(td) / "test_repo"
            repo_path.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_path), check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo_path), check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_path), check=True)
            (repo_path / "README.md").write_text("# Sync Test Repo\nLine 1\n")
            subprocess.run(["git", "add", "."], cwd=str(repo_path), check=True)
            subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_path), check=True, capture_output=True)

            db_file = Path(td) / "wt_sync.db"
            self._create_conflict_test_db(db_file)

            def insert_task(task_id, assignee):
                with sqlite3.connect(str(db_file)) as conn:
                    conn.execute(
                        "INSERT INTO tasks (id, title, status, assignee, created_at, updated_at) "
                        "VALUES (?, ?, 'ready', ?, 1000, 1000)",
                        (task_id, f"Task {task_id}", assignee),
                    )
                    conn.commit()

            def head_of(cwd):
                return subprocess.run(
                    ["git", "rev-parse", "HEAD"], cwd=str(cwd), check=True, capture_output=True, text=True
                ).stdout.strip()

            # --- 1. Existing-branch path: worktree exists and main has advanced past it ---
            insert_task("sync-1", "zf-builder")
            wt1 = Path(td) / "test_repo-worktrees" / "sync-1"
            subprocess.run(
                ["git", "worktree", "add", str(wt1), "-b", "task/sync-1"],
                cwd=str(repo_path), check=True, capture_output=True,
            )
            self.assertEqual(head_of(wt1), head_of(repo_path))
            # Advance main so it is no longer an ancestor of the worktree HEAD
            (repo_path / "README.md").write_text("# Sync Test Repo\nLine 1\nMain advance\n")
            subprocess.run(["git", "commit", "-am", "Advance main"], cwd=str(repo_path), check=True, capture_output=True)
            main_tip = head_of(repo_path)
            self.assertNotEqual(head_of(wt1), main_tip)

            with sqlite3.connect(str(db_file)) as conn:
                res = setup_worktree(conn.cursor(), "sync-1", "Task sync-1", "zf-builder", None, db_file, repo_path=repo_path)
                conn.commit()
            # setup_worktree returned the worktree dir (no swallowed exception)
            self.assertEqual(res, str(wt1))
            # Real pull_and_merge_main ran: post-merge HEAD moved to the latest main tip
            self.assertEqual(head_of(wt1), main_tip)
            with sqlite3.connect(str(db_file)) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute(
                    "SELECT workspace_path, branch_name, workspace_kind FROM tasks WHERE id = 'sync-1'"
                ).fetchone()
                self.assertEqual(row["workspace_path"], str(wt1))
                self.assertEqual(row["branch_name"], "task/sync-1")
                self.assertEqual(row["workspace_kind"], "dir")

            # --- 2. New-branch path: branch/worktree do not exist yet ---
            insert_task("sync-2", "zf-builder")
            wt2 = Path(td) / "test_repo-worktrees" / "sync-2"
            with sqlite3.connect(str(db_file)) as conn:
                res2 = setup_worktree(conn.cursor(), "sync-2", "Task sync-2", "zf-builder", None, db_file, repo_path=repo_path)
                conn.commit()
            self.assertEqual(res2, str(wt2))
            self.assertTrue(wt2.exists())
            subprocess.run(
                ["git", "show-ref", "--verify", "refs/heads/task/sync-2"],
                cwd=str(repo_path), check=True, capture_output=True,
            )
            # Fresh branch cut from main must contain the latest main tip
            self.assertEqual(head_of(wt2), main_tip)
            with sqlite3.connect(str(db_file)) as conn:
                conn.row_factory = sqlite3.Row
                row2 = conn.execute("SELECT workspace_path, branch_name FROM tasks WHERE id = 'sync-2'").fetchone()
                self.assertEqual(row2["workspace_path"], str(wt2))
                self.assertEqual(row2["branch_name"], "task/sync-2")

            # --- 3. Mock assertion: builder sync invoked with exact args (existing-branch path) ---
            with patch("dispatcher.pull_and_merge_main", return_value=(True, [], "ok")) as mock_pull:
                with sqlite3.connect(str(db_file)) as conn:
                    res3 = setup_worktree(
                        conn.cursor(), "sync-1", "Task sync-1", "zf-builder", None, db_file, repo_path=repo_path
                    )
                self.assertEqual(res3, str(wt1))
                mock_pull.assert_called_once_with(wt1, repo_path, "main")

            # --- 4. Non-builder assignee (new-branch path) must NOT trigger the merge sync ---
            insert_task("sync-3", "zf-reviewer")
            wt3 = Path(td) / "test_repo-worktrees" / "sync-3"
            with patch("dispatcher.pull_and_merge_main", return_value=(True, [], "ok")) as mock_pull_rev:
                with sqlite3.connect(str(db_file)) as conn:
                    res4 = setup_worktree(
                        conn.cursor(), "sync-3", "Review task", "zf-reviewer", None, db_file, repo_path=repo_path
                    )
                self.assertEqual(res4, str(wt3))
                mock_pull_rev.assert_not_called()
        finally:
            shutil.rmtree(td, ignore_errors=True)
            if orig_skip_git is not None:
                os.environ["ZEROFACTORY_SKIP_GIT"] = orig_skip_git


    def test_39_reviewer_git_predigest(self):
        from dispatcher import digest_reviewer_git_context, spawn_agent_worker
        import subprocess
        import tempfile
        import shutil
        from unittest.mock import patch, MagicMock

        td = tempfile.mkdtemp()
        try:
            repo_dir = Path(td) / "repo"
            repo_dir.mkdir()

            # Initialize git repo with main branch
            subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_dir), check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "TestUser"], cwd=str(repo_dir), check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_dir), check=True)

            (repo_dir / "README.md").write_text("# Initial Repo\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True)
            subprocess.run(["git", "commit", "-m", "chore: initial commit"], cwd=str(repo_dir), check=True, capture_output=True)

            # Create a feature branch with changes
            subprocess.run(["git", "checkout", "-b", "task/zf-testrev"], cwd=str(repo_dir), check=True, capture_output=True)
            (repo_dir / "feature.py").write_text("def hello():\n    return 'world'\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True)
            subprocess.run(["git", "commit", "-m", "feat: add hello function"], cwd=str(repo_dir), check=True, capture_output=True)

            # 1. Test digest_reviewer_git_context directly
            digest = digest_reviewer_git_context(repo_dir, "task/zf-testrev")
            self.assertIn("Pre-Digested PR Changes", digest)
            self.assertIn("feat: add hello function", digest)
            self.assertIn("feature.py", digest)
            self.assertIn("def hello():", digest)

            # 2. Test non-git directory returns empty string gracefully
            non_git = Path(td) / "non_git"
            non_git.mkdir()
            self.assertEqual(digest_reviewer_git_context(non_git), "")

            # 3. Test spawn_agent_worker embeds pre-digested git context for zf-reviewer
            captured_prompts = []
            orig_popen = subprocess.Popen

            def mock_popen(cmd, *args, **kwargs):
                if isinstance(cmd, list) and any("hermes" in str(c) for c in cmd):
                    if "-q" in cmd:
                        idx = cmd.index("-q")
                        captured_prompts.append(cmd[idx + 1])
                    m = MagicMock()
                    m.pid = 99123
                    return m
                return orig_popen(cmd, *args, **kwargs)

            with patch("subprocess.Popen", side_effect=mock_popen):
                with patch.dict(os.environ, {}, clear=False):
                    os.environ.pop("ZEROFACTORY_SKIP_WORKER_SPAWN", None)
                    pid, sid = spawn_agent_worker(
                        task_id="zf-revtest1",
                        title="Review feature.py implementation",
                        description="Review new feature",
                        priority="P1",
                        assignee="zf-reviewer",
                        workspace_path=str(repo_dir),
                        branch_name="task/zf-testrev"
                    )
                    self.assertEqual(pid, 99123)
                    self.assertTrue(captured_prompts)
                    prompt_text = captured_prompts[0]
                    self.assertIn("Pre-Digested PR Changes", prompt_text)
                    self.assertIn("feat: add hello function", prompt_text)
                    self.assertIn("feature.py", prompt_text)
                    self.assertIn("Your goal as Reviewer:", prompt_text)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_40_move_blocked_with_reason_cli(self):
        """Regression: `hermes zerofactory move <id> blocked --reason "review-required"`
        (the documented zf-builder handoff command in templates/zf-builder/SOUL.md line 21
        and the dispatcher builder prompts at dispatcher.py:589 and :608) must be accepted
        by argparse and must move the task to 'blocked' while recording the reason as a
        'Blocked: ...' comment.

        Before the fix the `move` subparser only registered `task_id` + `status` with no
        `--reason` flag, so the command failed with
        `hermes: error: unrecognized arguments: --reason ...` (exit 2) and the TaskMove
        schema rejected a `reason` field. This broke the builder -> blocked(review-required)
        -> PR -> zf-reviewer handoff loop for any builder following the SOUL.md instruction.
        """
        import argparse
        from unittest.mock import patch
        from __init__ import register

        # Build the CLI parser + handler the same way the real `hermes zerofactory`
        # plugin registration does (same pattern as test_29).
        class _MockCtx:
            def register_cli_command(self, name, help, setup_fn, handler_fn):
                self.setup_fn = setup_fn
                self.handler_fn = handler_fn

        ctx = _MockCtx()
        register(ctx)
        cmd_parser = argparse.ArgumentParser()
        ctx.setup_fn(cmd_parser)

        # Create a running builder task to hand off. Ensure the default board
        # exists first so create_task's board_slug FK constraint is satisfied
        # (this test must also pass in isolation).
        existing_boards = [b["slug"] for b in list_boards()["boards"]]
        if "hotcode-dev-zerofactory" not in existing_boards:
            create_board(BoardCreate(
                git_url="https://github.com/hotcode-dev/zerofactory",
                description="AI workflow",
            ))

        t_id = create_task(TaskCreate(
            title="Builder Handoff Regression Task",
            status="running",
            priority="P0",
            assignee="zf-builder",
            board_slug="hotcode-dev-zerofactory",
        ))["id"]

        # 1. The exact documented handoff command must parse (previously exit 2).
        parsed = cmd_parser.parse_args(
            ["move", t_id, "blocked", "--reason", "review-required"]
        )
        self.assertEqual(parsed.task_id, t_id)
        self.assertEqual(parsed.status, "blocked")
        self.assertEqual(parsed.reason, "review-required")

        # 2. Running the handler moves the task to 'blocked' and records the reason.
        with patch.dict(os.environ, {"HERMES_PROFILE": "zf-builder"}, clear=False):
            ctx.handler_fn(parsed)

        t_data = get_task(t_id)["task"]
        self.assertEqual(t_data["status"], "blocked")
        # The reason is recorded as a comment, mirroring the `block` command behaviour.
        blocked_comments = [
            c for c in t_data["comments"] if c["body"] == "Blocked: review-required"
        ]
        self.assertEqual(len(blocked_comments), 1)
        self.assertEqual(blocked_comments[0]["author"], "zf-builder")

        # 3. The TaskMove schema now accepts a `reason` field via the HTTP endpoint
        #    (the model no longer rejects it), and a non-blocked move still works.
        resp = client.post(f"/api/plugins/zerofactory/tasks/{t_id}/move", json={
            "status": "ready",
            "reason": "unblocked",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "ready")
        self.assertEqual(get_task(t_id)["task"]["status"], "ready")

        # 4. A `move ... blocked` WITHOUT a reason must NOT record a comment
        #    (reason is optional; only a provided reason is recorded).
        resp2 = client.post(f"/api/plugins/zerofactory/tasks/{t_id}/move", json={
            "status": "blocked",
        })
        self.assertEqual(resp2.status_code, 200)
        comments_after = get_task(t_id)["task"]["comments"]
        self.assertEqual(
            len([c for c in comments_after if c["body"] == "Blocked: "]), 0
        )

    def test_41_block_command_shares_move_path_and_dedups(self):
        """Regression: `block <id> --reason "X"` and
        `move <id> blocked --reason "X"` must both yield exactly one identical
        "Blocked: X" comment produced by a single shared code path in
        `move_task` (dashboard/plugin_api.py). The `block` CLI handler no
        longer inserts a comment manually — it delegates via
        TaskMove(reason=...) — and re-issuing a blocked -> blocked move with
        the same reason must not append a duplicate comment (no-op guard).
        """
        import argparse
        from unittest.mock import patch
        from __init__ import register

        # Build the CLI parser + handler the same way the real
        # `hermes zerofactory` plugin registration does (same pattern as
        # test_40).
        class _MockCtx:
            def register_cli_command(self, name, help, setup_fn, handler_fn):
                self.setup_fn = setup_fn
                self.handler_fn = handler_fn

        ctx = _MockCtx()
        register(ctx)
        cmd_parser = argparse.ArgumentParser()
        ctx.setup_fn(cmd_parser)

        existing_boards = [b["slug"] for b in list_boards()["boards"]]
        if "hotcode-dev-zerofactory" not in existing_boards:
            create_board(BoardCreate(
                git_url="https://github.com/hotcode-dev/zerofactory",
                description="AI workflow",
            ))

        def _new_task():
            return create_task(TaskCreate(
                title="Block Dedup Regression Task",
                status="running",
                priority="P1",
                assignee="zf-builder",
                board_slug="hotcode-dev-zerofactory",
            ))["id"]

        # 1. `block <id> --reason X` must produce exactly ONE
        #    "Blocked: X" comment (same single shared write path as
        #    `move ... blocked --reason`).
        t_block = _new_task()
        parsed = cmd_parser.parse_args(
            ["block", t_block, "--reason", "review-required"]
        )
        with patch.dict(os.environ, {"HERMES_PROFILE": "zf-builder"}, clear=False):
            ctx.handler_fn(parsed)
        t_data = get_task(t_block)["task"]
        self.assertEqual(t_data["status"], "blocked")
        block_comments = [
            c for c in t_data["comments"] if c["body"] == "Blocked: review-required"
        ]
        self.assertEqual(len(block_comments), 1)
        self.assertEqual(block_comments[0]["author"], "zf-builder")

        # 2. Re-issuing a blocked -> blocked move with the SAME reason must
        #    NOT append a second identical comment (no-op guard in move_task).
        resp = client.post(f"/api/plugins/zerofactory/tasks/{t_block}/move", json={
            "status": "blocked",
            "reason": "review-required",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["prev_status"], "blocked")
        comments_after = get_task(t_block)["task"]["comments"]
        self.assertEqual(
            len([c for c in comments_after if c["body"] == "Blocked: review-required"]),
            1,
            "blocked -> blocked re-handoff must not duplicate the comment",
        )

        # 3. The `block` command and `move ... blocked --reason` must yield
        #    identical single comments (same body, same author) — proof they
        #    go through one shared code path.
        t_move = _new_task()
        parsed_move = cmd_parser.parse_args(
            ["move", t_move, "blocked", "--reason", "review-required"]
        )
        with patch.dict(os.environ, {"HERMES_PROFILE": "zf-builder"}, clear=False):
            ctx.handler_fn(parsed_move)
        move_comments = [
            c for c in get_task(t_move)["task"]["comments"]
            if c["body"] == "Blocked: review-required"
        ]
        self.assertEqual(len(move_comments), 1)
        self.assertEqual(move_comments[0]["author"], block_comments[0]["author"])

    def test_42_block_and_move_deduplication(self):
        """Verify that repeated block or move calls with the same reason are idempotent
        and do not create duplicate comments in task_comments."""
        from __init__ import register
        import argparse
        from unittest.mock import patch

        class _MockCtx:
            def register_cli_command(self, name, help, setup_fn, handler_fn):
                self.setup_fn = setup_fn
                self.handler_fn = handler_fn

        ctx = _MockCtx()
        register(ctx)
        cmd_parser = argparse.ArgumentParser()
        ctx.setup_fn(cmd_parser)

        existing_boards = [b["slug"] for b in list_boards()["boards"]]
        if "hotcode-dev-zerofactory" not in existing_boards:
            create_board(BoardCreate(
                git_url="https://github.com/hotcode-dev/zerofactory",
                description="AI workflow",
            ))

        t_id = create_task(TaskCreate(
            title="Idempotency Deduplication Task",
            status="running",
            priority="P0",
            assignee="zf-reviewer",
            board_slug="hotcode-dev-zerofactory",
        ))["id"]

        # 1. Block with "Human Review & Merge" via CLI
        parsed_block1 = cmd_parser.parse_args(["block", t_id, "--reason", "Human Review & Merge"])
        with patch.dict(os.environ, {"HERMES_PROFILE": "zf-reviewer"}, clear=False):
            ctx.handler_fn(parsed_block1)

        t_data = get_task(t_id)["task"]
        self.assertEqual(t_data["status"], "blocked")
        comments = [c for c in t_data["comments"] if c["body"] == "Blocked: Human Review & Merge"]
        self.assertEqual(len(comments), 1)

        # 2. Block again with the exact same reason -> should be deduplicated (no duplicate comment)
        parsed_block2 = cmd_parser.parse_args(["block", t_id, "--reason", "Human Review & Merge"])
        with patch.dict(os.environ, {"HERMES_PROFILE": "zf-reviewer"}, clear=False):
            ctx.handler_fn(parsed_block2)

        t_data = get_task(t_id)["task"]
        comments = [c for c in t_data["comments"] if c["body"] == "Blocked: Human Review & Merge"]
        self.assertEqual(len(comments), 1, "Duplicate comment should not have been created")

        # 3. Move again with the exact same reason -> still deduplicated
        parsed_move = cmd_parser.parse_args(["move", t_id, "blocked", "--reason", "Human Review & Merge"])
        with patch.dict(os.environ, {"HERMES_PROFILE": "zf-reviewer"}, clear=False):
            ctx.handler_fn(parsed_move)

        t_data = get_task(t_id)["task"]
        comments = [c for c in t_data["comments"] if c["body"] == "Blocked: Human Review & Merge"]
        self.assertEqual(len(comments), 1, "Duplicate comment should not have been created on move")

        # 4. Block with a DIFFERENT reason -> should add the new reason
        parsed_diff = cmd_parser.parse_args(["block", t_id, "--reason", "changes-requested"])
        with patch.dict(os.environ, {"HERMES_PROFILE": "zf-reviewer"}, clear=False):
            ctx.handler_fn(parsed_diff)

        t_data = get_task(t_id)["task"]
        comments_all = [c["body"] for c in t_data["comments"]]
        self.assertIn("Blocked: Human Review & Merge", comments_all)
        self.assertIn("Blocked: changes-requested", comments_all)
        self.assertEqual(comments_all[-1], "Blocked: changes-requested")

    def test_43_worker_env_and_atomic_claim(self):
        """Verify that spawned workers have HERMES_KANBAN_STOP_NUDGE=0 and no
        HERMES_KANBAN_TASK in their env, preventing protocol violation nudge loops."""
        from dispatcher import spawn_agent_worker
        from unittest.mock import patch, MagicMock

        captured_env = {}
        def mock_popen(cmd, **kwargs):
            nonlocal captured_env
            captured_env = kwargs.get("env", {})
            mock_proc = MagicMock()
            mock_proc.pid = 99999
            return mock_proc

        with patch("subprocess.Popen", side_effect=mock_popen):
            with patch.dict(os.environ, {"HERMES_KANBAN_TASK": "parent-task-id"}, clear=False):
                pid, sess = spawn_agent_worker(
                    task_id="zf-testenv",
                    title="Test Env Task",
                    description="Test",
                    priority="P0",
                    assignee="zf-reviewer",
                    workspace_path=None,
                    branch_name="main",
                )

        self.assertEqual(pid, 99999)
        self.assertEqual(captured_env.get("HERMES_KANBAN_STOP_NUDGE"), "0")
        self.assertNotIn("HERMES_KANBAN_TASK", captured_env)

    def test_44_dispatch_cycle_survives_subprocess_timeout(self):
        """A hung network step (git push / gh) in the author-handoff path must not
        stall the dispatch cycle or leave the task in a half-committed state:
        the cycle completes, the task stays in its pre-PR status, and a warning
        is logged so the next cycle retries idempotently."""
        import shutil
        import subprocess
        import tempfile
        import sqlite3
        from unittest.mock import patch
        from dispatcher import run_dispatch_cycle

        orig_skip_git = os.environ.pop("ZEROFACTORY_SKIP_GIT", None)
        td = tempfile.mkdtemp()
        try:
            # Real repo + worktree so git rev-parse / merge-base work for real
            repo_path = Path(td) / "timeout_repo"
            repo_path.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_path), check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo_path), check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_path), check=True)
            (repo_path / "README.md").write_text("# Timeout Test\n")
            subprocess.run(["git", "add", "."], cwd=str(repo_path), check=True)
            subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_path), check=True, capture_output=True)

            worktree_dir = Path(td) / "worktree_timeout"
            subprocess.run(
                ["git", "worktree", "add", str(worktree_dir), "-b", "task/to-1"],
                cwd=str(repo_path), check=True, capture_output=True
            )
            # Clean worktree (no uncommitted changes -> add/commit steps are skipped)

            # Dedicated task DB so no other tasks interfere
            db_file = Path(td) / "timeout_test.db"
            with sqlite3.connect(str(db_file)) as conn:
                conn.execute("""
                    CREATE TABLE tasks (
                        id TEXT PRIMARY KEY, title TEXT, description TEXT, priority TEXT,
                        status TEXT, assignee TEXT, skills TEXT, workspace_kind TEXT,
                        workspace_path TEXT, branch_name TEXT, pr_url TEXT, metadata TEXT,
                        tenant TEXT, board_slug TEXT, created_at REAL, updated_at REAL
                    )
                """)
                conn.execute("""
                    CREATE TABLE task_activity (
                        id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT,
                        actor TEXT, action TEXT, details TEXT, created_at REAL
                    )
                """)
                conn.execute("CREATE TABLE task_comments (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, author TEXT, body TEXT, created_at REAL)")
                conn.execute("CREATE TABLE task_links (id INTEGER PRIMARY KEY, parent_id TEXT, child_id TEXT, link_type TEXT)")
                conn.execute("CREATE TABLE boards (id INTEGER PRIMARY KEY, slug TEXT UNIQUE, description TEXT, git_url TEXT, created_at REAL, updated_at REAL)")
                conn.execute("""
                    INSERT INTO tasks (id, title, status, assignee, workspace_path, branch_name, created_at, updated_at)
                    VALUES ('to-1', 'Timed out push task', 'blocked', 'zf-builder', ?, 'task/to-1', 1000, 1000)
                """, (str(worktree_dir),))
                conn.commit()

            orig_run = subprocess.run
            push_calls = []

            def fake_run(cmd, *args, **kwargs):
                # Simulate a hung remote: git push raises TimeoutExpired
                if isinstance(cmd, list) and len(cmd) >= 2 and cmd[0] == "git" and cmd[1] == "push":
                    push_calls.append(cmd)
                    raise subprocess.TimeoutExpired(cmd=cmd, timeout=180)
                return orig_run(cmd, *args, **kwargs)

            with patch("subprocess.run", side_effect=fake_run), \
                 self.assertLogs("zerofactory.kanban.dispatcher", level="WARNING") as log_cm:
                # The cycle must not raise despite the timed-out push
                cycle_res = run_dispatch_cycle(db_file)

            self.assertTrue(cycle_res["ok"], f"Dispatch cycle should survive the timeout, got: {cycle_res}")
            self.assertGreaterEqual(len(push_calls), 1, "git push should have been attempted")

            with sqlite3.connect(str(db_file)) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("SELECT * FROM tasks WHERE id = 'to-1'")
                t_row = cur.fetchone()
                # Task must NOT be marked done and must not be routed to the reviewer
                self.assertNotEqual(t_row["status"], "done", "Task must not be marked done on push timeout")
                self.assertNotEqual(t_row["assignee"], "zf-reviewer", "Task must not be handed to reviewer on push timeout")
                self.assertIsNone(t_row["pr_url"], "No PR URL should be recorded on push timeout")
                # Task stays in its pre-PR status so the next cycle retries idempotently
                self.assertEqual(t_row["status"], "blocked")
                self.assertEqual(t_row["assignee"], "zf-builder")

            # A warning including the task id and the timeout was logged
            matched = [line for line in log_cm.output if "to-1" in line and "timed out" in line]
            self.assertTrue(matched, f"Expected a timeout warning for task to-1, got: {log_cm.output}")
        finally:
            shutil.rmtree(td, ignore_errors=True)
            if orig_skip_git is not None:
                os.environ["ZEROFACTORY_SKIP_GIT"] = orig_skip_git

    def test_45_board_max_concurrent_running_api(self):
        """The per-board max_concurrent_running setting round-trips through the
        create + update API, defaults to 1 on fresh boards and on existing rows,
        and is migrated into pre-existing boards tables."""
        import sqlite3
        import shutil

        # --- Fresh DB: column present, default 1 ---
        with get_db_conn() as conn:
            cols = [r[1] for r in conn.execute("PRAGMA table_info(boards)").fetchall()]
        self.assertIn("max_concurrent_running", cols, "boards table must expose max_concurrent_running")

        # --- Create with an explicit value ---
        res = create_board(BoardCreate(git_url="https://github.com/mcr/explicit.git", max_concurrent_running=3))
        self.assertTrue(res["ok"])
        mcr_board = next(b for b in list_boards()["boards"] if b["slug"] == "mcr-explicit")
        self.assertEqual(mcr_board["max_concurrent_running"], 3)

        # --- Create with default (no value) -> 1 ---
        create_board(BoardCreate(git_url="https://github.com/mcr/default.git"))
        def_board = next(b for b in list_boards()["boards"] if b["slug"] == "mcr-default")
        self.assertEqual(def_board["max_concurrent_running"], 1)

        # --- Update via PATCH ---
        res_up = client.patch("/api/plugins/zerofactory/boards/mcr-explicit", json={"max_concurrent_running": 2})
        self.assertEqual(res_up.status_code, 200)
        self.assertTrue(res_up.json()["ok"])
        after = next(b for b in list_boards()["boards"] if b["slug"] == "mcr-explicit")
        self.assertEqual(after["max_concurrent_running"], 2)

        # --- Update only the value (description/git_url omitted) still works ---
        res_only = client.patch("/api/plugins/zerofactory/boards/mcr-default", json={"max_concurrent_running": 5})
        self.assertEqual(res_only.status_code, 200)
        after2 = next(b for b in list_boards()["boards"] if b["slug"] == "mcr-default")
        self.assertEqual(after2["max_concurrent_running"], 5)

        # --- Validation: below-1 rejected (422) ---
        res_bad = client.patch("/api/plugins/zerofactory/boards/mcr-explicit", json={"max_concurrent_running": 0})
        self.assertEqual(res_bad.status_code, 422)

        # --- Migration path: an OLD boards table without the column gains it on init_db() ---
        old_db = os.environ.get("ZEROFACTORY_DB")
        td = tempfile.mkdtemp(prefix="zf-mcr-migrate-")
        old_path = Path(td) / "old.db"
        try:
            conn = sqlite3.connect(str(old_path))
            conn.execute("CREATE TABLE boards (slug TEXT PRIMARY KEY, description TEXT DEFAULT '', git_url TEXT DEFAULT '', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)")
            conn.execute("INSERT INTO boards (slug, created_at, updated_at) VALUES ('legacy-board', 1, 1)")
            conn.commit()
            conn.close()
            os.environ["ZEROFACTORY_DB"] = str(old_path)
            try:
                init_db()  # must migrate the legacy table in place
            finally:
                if old_db is None:
                    os.environ.pop("ZEROFACTORY_DB", None)
                else:
                    os.environ["ZEROFACTORY_DB"] = old_db
            conn = sqlite3.connect(str(old_path))
            cols = [r[1] for r in conn.execute("PRAGMA table_info(boards)").fetchall()]
            conn.close()
            self.assertIn("max_concurrent_running", cols, "legacy boards table must be migrated")
            # Row retains its original data with the new default applied
            conn = sqlite3.connect(str(old_path))
            row = conn.execute("SELECT slug, max_concurrent_running FROM boards WHERE slug = 'legacy-board'").fetchone()
            conn.close()
            self.assertEqual(row, ("legacy-board", 1))
        finally:
            shutil.rmtree(td, ignore_errors=True)
            if old_db is None:
                os.environ.pop("ZEROFACTORY_DB", None)
            else:
                os.environ["ZEROFACTORY_DB"] = old_db

    def test_46_board_max_concurrent_running_dispatch(self):
        """The dispatch cycle caps concurrent 'running' tasks per board at the
        board's max_concurrent_running (default 1). With cap 1 and three ready
        tasks only one runs; raising the board cap to 2 lets a second start."""
        import tempfile
        import shutil
        import sqlite3
        from dispatcher import run_dispatch_cycle

        orig_skip_git = os.environ.get("ZEROFACTORY_SKIP_GIT")
        orig_skip_spawn = os.environ.get("ZEROFACTORY_SKIP_WORKER_SPAWN")
        os.environ["ZEROFACTORY_SKIP_GIT"] = "1"
        os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = "1"
        td = tempfile.mkdtemp(prefix="zf-mcr-dispatch-")
        ws = Path(td) / "ws"
        ws.mkdir()
        db_file = Path(td) / "mcr_dispatch.db"
        try:
            conn = sqlite3.connect(str(db_file))
            conn.execute("CREATE TABLE boards (slug TEXT PRIMARY KEY, description TEXT DEFAULT '', git_url TEXT DEFAULT '', max_concurrent_running INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)")
            conn.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, board_slug TEXT NOT NULL DEFAULT '', title TEXT NOT NULL, description TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'triage', assignee TEXT NOT NULL DEFAULT 'unassigned', priority TEXT NOT NULL DEFAULT 'P2', workspace_path TEXT, branch_name TEXT, metadata TEXT DEFAULT '{}', tenant TEXT DEFAULT '', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)")
            conn.execute("CREATE TABLE task_activity (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, actor TEXT, action TEXT, details TEXT DEFAULT '', created_at INTEGER NOT NULL)")
            conn.execute("CREATE TABLE task_comments (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, author TEXT, body TEXT, created_at INTEGER NOT NULL)")
            conn.execute("CREATE TABLE task_links (id INTEGER PRIMARY KEY, parent_id TEXT, child_id TEXT, link_type TEXT)")
            conn.execute("INSERT INTO boards (slug, max_concurrent_running, created_at, updated_at) VALUES ('b1', 1, 1, 1)")
            for i in range(1, 4):
                conn.execute(
                    "INSERT INTO tasks (id, board_slug, title, status, assignee, priority, workspace_path, created_at, updated_at) VALUES (?, 'b1', ?, 'ready', 'zf-builder', 'P2', ?, 1000, 1000)",
                    (f"mcr-{i}", f"Task {i}", str(ws)),
                )
            conn.commit()
            conn.close()

            # Cycle 1: cap 1 -> exactly one running, two still ready
            res = run_dispatch_cycle(db_file)
            self.assertTrue(res["ok"], f"dispatch cycle should succeed: {res}")
            conn = sqlite3.connect(str(db_file))
            conn.row_factory = sqlite3.Row
            running = conn.execute("SELECT id FROM tasks WHERE status = 'running'").fetchall()
            ready = conn.execute("SELECT id FROM tasks WHERE status = 'ready'").fetchall()
            conn.close()
            self.assertEqual(len(running), 1, f"expected exactly 1 running under cap 1, got {len(running)}")
            self.assertEqual(len(ready), 2, f"expected 2 ready to remain, got {len(ready)}")

            # Raise the board cap to 2, run again -> a second task starts
            conn = sqlite3.connect(str(db_file))
            conn.execute("UPDATE boards SET max_concurrent_running = 2 WHERE slug = 'b1'")
            conn.commit()
            conn.close()
            res2 = run_dispatch_cycle(db_file)
            self.assertTrue(res2["ok"], f"second dispatch cycle should succeed: {res2}")
            conn = sqlite3.connect(str(db_file))
            running2 = conn.execute("SELECT id FROM tasks WHERE status = 'running'").fetchall()
            ready2 = conn.execute("SELECT id FROM tasks WHERE status = 'ready'").fetchall()
            conn.close()
            self.assertEqual(len(running2), 2, f"expected 2 running under cap 2, got {len(running2)}")
            self.assertEqual(len(ready2), 1, f"expected 1 ready to remain, got {len(ready2)}")
        finally:
            shutil.rmtree(td, ignore_errors=True)
            if orig_skip_git is None:
                os.environ.pop("ZEROFACTORY_SKIP_GIT", None)
            else:
                os.environ["ZEROFACTORY_SKIP_GIT"] = orig_skip_git
            if orig_skip_spawn is None:
                os.environ.pop("ZEROFACTORY_SKIP_WORKER_SPAWN", None)
            else:
                os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = orig_skip_spawn

    def test_47_global_settings_api(self):
        """Global settings API supports GET and PATCH with validation."""
        # 1. GET returns defaults
        res = client.get("/api/plugins/zerofactory/settings")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        self.assertIn("max_active_tasks", data["settings"])
        self.assertIn("default_max_concurrent_workers", data["settings"])
        self.assertIn("scan_on_idle", data["settings"])
        self.assertIn("idle_scan_active_threshold", data["settings"])
        self.assertIn("idle_scan_cooldown_minutes", data["settings"])
        self.assertIn("idle_scan_max_todo", data["settings"])
        self.assertTrue(data["settings"]["scan_on_idle"])
        self.assertEqual(data["settings"]["idle_scan_active_threshold"], 2)
        self.assertEqual(data["settings"]["idle_scan_cooldown_minutes"], 15)
        self.assertEqual(data["settings"]["idle_scan_max_todo"], 2)

        # 2. PATCH updates settings
        res_patch = client.patch(
            "/api/plugins/zerofactory/settings",
            json={
                "max_active_tasks": 12,
                "default_max_concurrent_workers": 2,
                "scan_on_idle": False,
                "idle_scan_active_threshold": 1,
                "idle_scan_cooldown_minutes": 30,
                "idle_scan_max_todo": 3,
            }
        )
        self.assertEqual(res_patch.status_code, 200)
        settings = res_patch.json()["settings"]
        self.assertEqual(settings["max_active_tasks"], 12)
        self.assertEqual(settings["default_max_concurrent_workers"], 2)
        self.assertFalse(settings["scan_on_idle"])
        self.assertEqual(settings["idle_scan_active_threshold"], 1)
        self.assertEqual(settings["idle_scan_cooldown_minutes"], 30)
        self.assertEqual(settings["idle_scan_max_todo"], 3)

        # Verify GET returns updated values
        res_after = client.get("/api/plugins/zerofactory/settings")
        self.assertEqual(res_after.json()["settings"]["max_active_tasks"], 12)
        self.assertEqual(res_after.json()["settings"]["default_max_concurrent_workers"], 2)
        self.assertFalse(res_after.json()["settings"]["scan_on_idle"])
        self.assertEqual(res_after.json()["settings"]["idle_scan_active_threshold"], 1)
        self.assertEqual(res_after.json()["settings"]["idle_scan_cooldown_minutes"], 30)
        self.assertEqual(res_after.json()["settings"]["idle_scan_max_todo"], 3)

        # 3. Validation: values < 1 are rejected with 422
        res_bad = client.patch(
            "/api/plugins/zerofactory/settings",
            json={"max_active_tasks": 0}
        )
        self.assertEqual(res_bad.status_code, 422)

        res_bad_threshold = client.patch(
            "/api/plugins/zerofactory/settings",
            json={"idle_scan_active_threshold": 0}
        )
        self.assertEqual(res_bad_threshold.status_code, 422)

        # Reset back to default
        client.patch(
            "/api/plugins/zerofactory/settings",
            json={
                "max_active_tasks": 10,
                "default_max_concurrent_workers": 1,
                "scan_on_idle": True,
                "idle_scan_active_threshold": 2,
                "idle_scan_cooldown_minutes": 15,
                "idle_scan_max_todo": 2,
            }
        )

    def test_48_dynamic_max_active_tasks_dispatch(self):
        """Dispatcher dynamically respects max_active_tasks from settings table."""
        import tempfile
        import shutil
        import sqlite3
        from dispatcher import run_dispatch_cycle

        orig_skip_git = os.environ.get("ZEROFACTORY_SKIP_GIT")
        orig_skip_spawn = os.environ.get("ZEROFACTORY_SKIP_WORKER_SPAWN")
        os.environ["ZEROFACTORY_SKIP_GIT"] = "1"
        os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = "1"
        td = tempfile.mkdtemp(prefix="zf-max-active-")
        ws = Path(td) / "ws"
        ws.mkdir()
        db_file = Path(td) / "max_active.db"
        try:
            conn = sqlite3.connect(str(db_file))
            conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at INTEGER NOT NULL)")
            conn.execute("CREATE TABLE boards (slug TEXT PRIMARY KEY, description TEXT DEFAULT '', git_url TEXT DEFAULT '', max_concurrent_running INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)")
            conn.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, board_slug TEXT NOT NULL DEFAULT '', title TEXT NOT NULL, description TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'triage', assignee TEXT NOT NULL DEFAULT 'unassigned', priority TEXT NOT NULL DEFAULT 'P2', workspace_path TEXT, branch_name TEXT, metadata TEXT DEFAULT '{}', tenant TEXT DEFAULT '', skills TEXT DEFAULT '[]', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)")
            conn.execute("CREATE TABLE task_activity (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, actor TEXT, action TEXT, details TEXT DEFAULT '', created_at INTEGER NOT NULL)")
            conn.execute("CREATE TABLE task_comments (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, author TEXT, body TEXT, created_at INTEGER NOT NULL)")
            conn.execute("CREATE TABLE task_links (id INTEGER PRIMARY KEY, parent_id TEXT, child_id TEXT, link_type TEXT)")

            conn.execute("INSERT INTO boards (slug, max_concurrent_running, created_at, updated_at) VALUES ('b1', 10, 1, 1)")
            # Set max_active_tasks limit to 2
            conn.execute("INSERT INTO settings (key, value, updated_at) VALUES ('max_active_tasks', '2', 1)")
            # Create 5 tasks in 'todo'
            for i in range(1, 6):
                conn.execute(
                    "INSERT INTO tasks (id, board_slug, title, status, assignee, priority, workspace_path, created_at, updated_at) VALUES (?, 'b1', ?, 'todo', 'unassigned', 'P2', ?, 1000, 1000)",
                    (f"task-{i}", f"Task {i}", str(ws)),
                )
            conn.commit()
            conn.close()

            # Cycle 1: with max_active_tasks = 2, only 2 tasks should be promoted from todo to ready
            res = run_dispatch_cycle(db_file)
            self.assertTrue(res["ok"])
            conn = sqlite3.connect(str(db_file))
            todo_count = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'todo'").fetchone()[0]
            # Since board max_concurrent_running is 10 and worker spawn is skipped,
            # the 2 promoted tasks will move to ready and then running
            active_count = conn.execute("SELECT COUNT(*) FROM tasks WHERE status IN ('ready', 'running')").fetchone()[0]
            conn.close()
            self.assertEqual(active_count, 2, f"expected exactly 2 active tasks promoted, got {active_count}")
            self.assertEqual(todo_count, 3, f"expected 3 tasks to remain in todo, got {todo_count}")

            # Raise max_active_tasks to 4 in settings
            conn = sqlite3.connect(str(db_file))
            conn.execute("UPDATE settings SET value = '4' WHERE key = 'max_active_tasks'")
            conn.commit()
            conn.close()

            # Cycle 2: 2 more tasks should be promoted from todo
            res2 = run_dispatch_cycle(db_file)
            self.assertTrue(res2["ok"])
            conn = sqlite3.connect(str(db_file))
            active_count2 = conn.execute("SELECT COUNT(*) FROM tasks WHERE status IN ('ready', 'running')").fetchone()[0]
            todo_count2 = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'todo'").fetchone()[0]
            conn.close()
            self.assertEqual(active_count2, 4, f"expected 4 active tasks under limit 4, got {active_count2}")
            self.assertEqual(todo_count2, 1, f"expected 1 task to remain in todo, got {todo_count2}")

        finally:
            shutil.rmtree(td, ignore_errors=True)
            if orig_skip_git is None:
                os.environ.pop("ZEROFACTORY_SKIP_GIT", None)
            else:
                os.environ["ZEROFACTORY_SKIP_GIT"] = orig_skip_git
            if orig_skip_spawn is None:
                os.environ.pop("ZEROFACTORY_SKIP_WORKER_SPAWN", None)
            else:
                os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = orig_skip_spawn

    def test_49_idle_improvement_scan_dispatch(self):
        """Dispatcher triggers improvement scan on idle and respects threshold, cooldown, and limits."""
        import time
        import tempfile
        import shutil
        import sqlite3
        from unittest.mock import patch, MagicMock
        from dispatcher import run_dispatch_cycle, reset_idle_scanner_state, _active_scanners, _last_idle_scan_times

        orig_skip_git = os.environ.get("ZEROFACTORY_SKIP_GIT")
        orig_skip_spawn = os.environ.get("ZEROFACTORY_SKIP_WORKER_SPAWN")
        os.environ["ZEROFACTORY_SKIP_GIT"] = "1"
        os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = "1"

        td = tempfile.mkdtemp(prefix="zf-idle-scan-")
        ws = Path(td) / "ws"
        ws.mkdir()
        db_file = Path(td) / "idle_scan.db"

        try:
            conn = sqlite3.connect(str(db_file))
            conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at INTEGER NOT NULL)")
            conn.execute("CREATE TABLE boards (slug TEXT PRIMARY KEY, description TEXT DEFAULT '', git_url TEXT DEFAULT '', max_concurrent_running INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)")
            conn.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, board_slug TEXT NOT NULL DEFAULT '', title TEXT NOT NULL, description TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'triage', assignee TEXT NOT NULL DEFAULT 'unassigned', priority TEXT NOT NULL DEFAULT 'P2', workspace_path TEXT, branch_name TEXT, metadata TEXT DEFAULT '{}', tenant TEXT DEFAULT '', skills TEXT DEFAULT '[]', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)")
            conn.execute("CREATE TABLE task_activity (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, actor TEXT, action TEXT, details TEXT DEFAULT '', created_at INTEGER NOT NULL)")
            conn.execute("CREATE TABLE task_comments (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, author TEXT, body TEXT, created_at INTEGER NOT NULL)")
            conn.execute("CREATE TABLE task_links (id INTEGER PRIMARY KEY, parent_id TEXT, child_id TEXT, link_type TEXT)")

            conn.execute("INSERT INTO boards (slug, max_concurrent_running, created_at, updated_at) VALUES ('b1', 5, 1, 1)")
            conn.execute("INSERT INTO settings (key, value, updated_at) VALUES ('scan_on_idle', 'true', 1)")
            conn.execute("INSERT INTO settings (key, value, updated_at) VALUES ('idle_scan_active_threshold', '2', 1)")
            conn.execute("INSERT INTO settings (key, value, updated_at) VALUES ('idle_scan_cooldown_minutes', '15', 1)")
            conn.execute("INSERT INTO settings (key, value, updated_at) VALUES ('idle_scan_max_todo', '2', 1)")
            conn.commit()
            conn.close()

            # 1. Idle condition met: 0 running workers < threshold 2, 0 todo < max_todo 2 -> triggers scan
            reset_idle_scanner_state()
            with patch("dispatcher.spawn_board_scanner", return_value=9999) as mock_spawn:
                res1 = run_dispatch_cycle(db_file)
                self.assertTrue(res1["ok"])
                self.assertEqual(res1["scans_triggered"], 1)
                mock_spawn.assert_called_once()
                self.assertEqual(mock_spawn.call_args[0][0], "b1")

            # 2. Cooldown suppression: immediately running cycle 2 should NOT trigger another scan
            with patch("dispatcher.spawn_board_scanner", return_value=9999) as mock_spawn2:
                res2 = run_dispatch_cycle(db_file)
                self.assertTrue(res2["ok"])
                self.assertEqual(res2["scans_triggered"], 0)
                mock_spawn2.assert_not_called()

            # 3. Active running worker suppression: running count = 2 >= threshold 2
            reset_idle_scanner_state()
            now_ts = int(time.time())
            conn = sqlite3.connect(str(db_file))
            conn.execute(
                "INSERT INTO tasks (id, board_slug, title, status, assignee, priority, workspace_path, created_at, updated_at) VALUES ('r1', 'b1', 'Run 1', 'running', 'zf-builder', 'P2', ?, ?, ?)",
                (str(ws), now_ts, now_ts)
            )
            conn.execute(
                "INSERT INTO tasks (id, board_slug, title, status, assignee, priority, workspace_path, created_at, updated_at) VALUES ('r2', 'b1', 'Run 2', 'running', 'zf-builder', 'P2', ?, ?, ?)",
                (str(ws), now_ts, now_ts)
            )
            conn.commit()
            conn.close()

            with patch("dispatcher.spawn_board_scanner", return_value=9999) as mock_spawn3:
                res3 = run_dispatch_cycle(db_file)
                self.assertTrue(res3["ok"])
                self.assertEqual(res3["scans_triggered"], 0)
                mock_spawn3.assert_not_called()

            # 4. Todo backlog suppression: 3 tasks in todo with max_active_tasks=1 leaves 2 in todo (>= max_todo 2)
            reset_idle_scanner_state()
            now_ts = int(time.time())
            conn = sqlite3.connect(str(db_file))
            conn.execute("DELETE FROM tasks")
            conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('max_active_tasks', '1', ?)", (now_ts,))
            conn.execute("INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('idle_scan_max_todo', '2', ?)", (now_ts,))
            for i in range(1, 4):
                conn.execute(
                    "INSERT INTO tasks (id, board_slug, title, status, assignee, priority, workspace_path, created_at, updated_at) VALUES (?, 'b1', ?, 'todo', 'unassigned', 'P2', ?, ?, ?)",
                    (f"t{i}", f"Todo {i}", str(ws), now_ts, now_ts)
                )
            conn.commit()
            conn.close()

            with patch("dispatcher.spawn_board_scanner", return_value=9999) as mock_spawn4:
                # 1 task promoted to running, 2 tasks remain in todo (>= max_todo 2) -> scan suppressed
                res4 = run_dispatch_cycle(db_file)
                self.assertEqual(res4["scans_triggered"], 0)
                mock_spawn4.assert_not_called()

            # 5. In-flight scanner lock suppression
            reset_idle_scanner_state()
            conn = sqlite3.connect(str(db_file))
            conn.execute("DELETE FROM tasks")
            conn.execute("UPDATE settings SET value = '2' WHERE key = 'idle_scan_max_todo'")
            conn.commit()
            conn.close()

            # Place a dummy active process in _active_scanners
            mock_proc = MagicMock()
            mock_proc.poll.return_value = None
            _active_scanners["b1"] = mock_proc

            with patch("dispatcher.spawn_board_scanner", return_value=9999) as mock_spawn5:
                res5 = run_dispatch_cycle(db_file)
                self.assertEqual(res5["scans_triggered"], 0)
                mock_spawn5.assert_not_called()

            # Now let the mock proc finish: poll returns 0
            mock_proc.poll.return_value = 0
            with patch("dispatcher.spawn_board_scanner", return_value=9999) as mock_spawn6:
                res6 = run_dispatch_cycle(db_file)
                self.assertEqual(res6["scans_triggered"], 1)
                mock_spawn6.assert_called_once()

            # 6. Disabled scan_on_idle setting
            reset_idle_scanner_state()
            conn = sqlite3.connect(str(db_file))
            conn.execute("UPDATE settings SET value = 'false' WHERE key = 'scan_on_idle'")
            conn.commit()
            conn.close()

            with patch("dispatcher.spawn_board_scanner", return_value=9999) as mock_spawn7:
                res7 = run_dispatch_cycle(db_file)
                self.assertEqual(res7["scans_triggered"], 0)
                mock_spawn7.assert_not_called()

            # 7. Failed spawn (returns None) must NOT consume the cooldown or count as triggered
            reset_idle_scanner_state()
            conn = sqlite3.connect(str(db_file))
            conn.execute("DELETE FROM tasks")
            conn.execute("UPDATE settings SET value = 'true' WHERE key = 'scan_on_idle'")
            conn.execute("UPDATE settings SET value = '2' WHERE key = 'idle_scan_max_todo'")
            conn.commit()
            conn.close()

            with patch("dispatcher.spawn_board_scanner", return_value=None) as mock_spawn8:
                res8 = run_dispatch_cycle(db_file)
                self.assertTrue(res8["ok"])
                self.assertEqual(res8["scans_triggered"], 0)
                # Spawn was attempted (idle conditions met) but failed: cooldown must be untouched
                mock_spawn8.assert_called_once()
                self.assertNotIn("b1", _last_idle_scan_times)

            # 8. Next cycle (still within the nominal cooldown window): successful spawn IS triggered
            with patch("dispatcher.spawn_board_scanner", return_value=9999) as mock_spawn9:
                res9 = run_dispatch_cycle(db_file)
                self.assertEqual(res9["scans_triggered"], 1)
                mock_spawn9.assert_called_once()
                self.assertIn("b1", _last_idle_scan_times)

        finally:
            reset_idle_scanner_state()
            shutil.rmtree(td, ignore_errors=True)
            if orig_skip_git is None:
                os.environ.pop("ZEROFACTORY_SKIP_GIT", None)
            else:
                os.environ["ZEROFACTORY_SKIP_GIT"] = orig_skip_git
            if orig_skip_spawn is None:
                os.environ.pop("ZEROFACTORY_SKIP_WORKER_SPAWN", None)
            else:
                os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = orig_skip_spawn

    def test_51_cross_process_dispatcher_lock(self):
        """Verify cross-process fcntl.flock prevents concurrent run_dispatch_cycle cycles."""
        import fcntl
        import shutil
        import sqlite3
        from dispatcher import run_dispatch_cycle, get_dispatcher_lock_path
        td = tempfile.mkdtemp()
        orig_lock_env = os.environ.get("ZEROFACTORY_LOCK_PATH")
        lock_file = Path(td) / "test_dispatcher.lock"
        os.environ["ZEROFACTORY_LOCK_PATH"] = str(lock_file)
        db_file = Path(td) / "test.db"

        try:
            # Initialize minimal DB
            conn = sqlite3.connect(str(db_file))
            conn.execute("""
                CREATE TABLE tasks (
                    id TEXT PRIMARY KEY, board_slug TEXT, title TEXT, description TEXT,
                    status TEXT, assignee TEXT, priority TEXT, workspace_path TEXT,
                    tenant TEXT, branch_name TEXT, metadata TEXT, created_at INTEGER, updated_at INTEGER
                )
            """)
            conn.execute("CREATE TABLE task_links (parent_id TEXT, child_id TEXT)")
            conn.execute("CREATE TABLE task_activity (id INTEGER PRIMARY KEY, task_id TEXT, actor TEXT, action TEXT, details TEXT, created_at INTEGER)")
            conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("CREATE TABLE boards (slug TEXT PRIMARY KEY, max_concurrent_running INTEGER)")
            conn.close()

            # 1. Acquire the lock externally as if another process holds it
            external_fd = os.open(str(lock_file), os.O_CREAT | os.O_RDWR, 0o666)
            fcntl.flock(external_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

            # 2. Call run_dispatch_cycle; it should detect the lock and skip immediately
            res = run_dispatch_cycle(db_file)
            self.assertTrue(res.get("ok"))
            self.assertTrue(res.get("skipped"))
            self.assertEqual(res.get("reason"), "concurrent_cycle_active")

            # 3. Release the external lock
            fcntl.flock(external_fd, fcntl.LOCK_UN)
            os.close(external_fd)

            # 4. Now run_dispatch_cycle should successfully acquire the lock and execute
            res2 = run_dispatch_cycle(db_file)
            self.assertTrue(res2.get("ok"))
            self.assertFalse(res2.get("skipped", False))
        finally:
            if orig_lock_env is None:
                os.environ.pop("ZEROFACTORY_LOCK_PATH", None)
            else:
                os.environ["ZEROFACTORY_LOCK_PATH"] = orig_lock_env
            shutil.rmtree(td, ignore_errors=True)

    def test_52_atomic_cas_task_promotion(self):
        """Verify atomic CAS prevents concurrent dispatchers from resetting a running task to ready."""
        import shutil
        import sqlite3
        import time
        from dispatcher import run_dispatch_cycle
        td = tempfile.mkdtemp()
        orig_skip = os.environ.get("ZEROFACTORY_SKIP_WORKER_SPAWN")
        os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = "1"
        db_file = Path(td) / "test.db"

        try:
            now_ts = int(time.time())
            conn = sqlite3.connect(str(db_file))
            conn.execute("""
                CREATE TABLE tasks (
                    id TEXT PRIMARY KEY, board_slug TEXT, title TEXT, description TEXT,
                    status TEXT, assignee TEXT, priority TEXT, workspace_path TEXT,
                    tenant TEXT, branch_name TEXT, metadata TEXT, created_at INTEGER, updated_at INTEGER
                )
            """)
            conn.execute("CREATE TABLE task_links (parent_id TEXT, child_id TEXT)")
            conn.execute("CREATE TABLE task_activity (id INTEGER PRIMARY KEY, task_id TEXT, actor TEXT, action TEXT, details TEXT, created_at INTEGER)")
            conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
            conn.execute("CREATE TABLE boards (slug TEXT PRIMARY KEY, max_concurrent_running INTEGER)")

            # Insert task in 'running' state (as if another process already dispatched it)
            conn.execute(
                "INSERT INTO tasks (id, board_slug, title, status, assignee, priority, created_at, updated_at) VALUES ('t1', 'b1', 'Task 1', 'running', 'zf-builder', 'P0', ?, ?)",
                (now_ts, now_ts)
            )
            conn.commit()
            conn.close()

            # Direct atomic CAS update check: if a second dispatcher tries to promote 't1' assuming it's in 'todo'
            conn = sqlite3.connect(str(db_file))
            cur = conn.cursor()
            cur.execute(
                "UPDATE tasks SET status = 'ready', updated_at = ? WHERE id = 't1' AND (status = 'todo' OR (status = 'ready' AND assignee = 'unassigned'))",
                (now_ts,)
            )
            self.assertEqual(cur.rowcount, 0, "Atomic CAS must reject promoting a task that is already running")

            # Verify task remains in 'running'
            cur.execute("SELECT status FROM tasks WHERE id = 't1'")
            self.assertEqual(cur.fetchone()[0], "running")
            conn.close()
        finally:
            if orig_skip is None:
                os.environ.pop("ZEROFACTORY_SKIP_WORKER_SPAWN", None)
            else:
                os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = orig_skip
            shutil.rmtree(td, ignore_errors=True)

    def test_53_is_worker_or_child_process(self):
        """Verify is_worker_or_child_process correctly suppresses dispatcher startup in workers."""
        from dispatcher import is_worker_or_child_process
        orig_prof = os.environ.get("HERMES_PROFILE")
        orig_dis = os.environ.get("ZEROFACTORY_DISABLE_DISPATCHER")
        orig_task = os.environ.get("HERMES_KANBAN_TASK")

        try:
            # Normal profile
            os.environ.pop("HERMES_PROFILE", None)
            os.environ.pop("ZEROFACTORY_DISABLE_DISPATCHER", None)
            os.environ.pop("HERMES_KANBAN_TASK", None)
            self.assertFalse(is_worker_or_child_process())

            # Worker profiles
            os.environ["HERMES_PROFILE"] = "zf-builder"
            self.assertTrue(is_worker_or_child_process())

            os.environ["HERMES_PROFILE"] = "zf-reviewer"
            self.assertTrue(is_worker_or_child_process())

            # Explicit disable flag
            os.environ["HERMES_PROFILE"] = "default"
            os.environ["ZEROFACTORY_DISABLE_DISPATCHER"] = "1"
            self.assertTrue(is_worker_or_child_process())

            # In task env
            os.environ.pop("ZEROFACTORY_DISABLE_DISPATCHER", None)
            os.environ["HERMES_KANBAN_TASK"] = "task-1"
            self.assertTrue(is_worker_or_child_process())
        finally:
            if orig_prof is not None:
                os.environ["HERMES_PROFILE"] = orig_prof
            else:
                os.environ.pop("HERMES_PROFILE", None)
            if orig_dis is not None:
                os.environ["ZEROFACTORY_DISABLE_DISPATCHER"] = orig_dis
            else:
                os.environ.pop("ZEROFACTORY_DISABLE_DISPATCHER", None)
            if orig_task is not None:
                os.environ["HERMES_KANBAN_TASK"] = orig_task
            else:
                os.environ.pop("HERMES_KANBAN_TASK", None)

    def test_54_spawn_board_scanner_syncs_repo_main(self):
        """Verify that spawn_board_scanner automatically syncs and pulls the repository default branch."""
        from unittest.mock import patch, MagicMock
        from dispatcher import spawn_board_scanner
        with tempfile.TemporaryDirectory() as td:
            repo_path = Path(td) / "test_repo"
            repo_path.mkdir()
            with patch("dispatcher.sync_repo_main") as mock_sync, \
                 patch("subprocess.Popen") as mock_popen, \
                 patch("builtin_cron.toggle_builtin_job"):
                mock_proc = MagicMock()
                mock_proc.pid = 4321
                mock_popen.return_value = mock_proc
                pid = spawn_board_scanner("test-slug", repo_path)
                self.assertEqual(pid, 4321)
                mock_sync.assert_called_once_with(repo_path)

    def test_55_activities_endpoint(self):
        """Verify GET /activities returns unified activity log, filtering, agent summaries and stats."""
        # 1. Ensure board exists, create a task and generate some activity
        try:
            create_board(BoardCreate(git_url="https://github.com/hotcode-dev/zerofactory", description="AI workflow"))
        except Exception:
            pass
        t_req = TaskCreate(
            board_slug="hotcode-dev-zerofactory",
            title="Activity Test Task",
            description="Testing activities endpoint",
            assignee="zf-builder",
            priority="P1"
        )
        t_res = create_task(t_req)
        self.assertTrue(t_res["ok"])
        task_id = t_res["id"]

        # 2. Add comment, move task, log custom activity
        with get_db_conn() as conn:
            conn.execute(
                "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'start', 'Spawned worker zf-builder (PID 9999)', ?)",
                (task_id, 1726000000)
            )
            conn.execute(
                "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'zf-builder', 'worker_done', 'Finished coding changes', ?)",
                (task_id, 1726000010)
            )
            conn.commit()

        # 3. Test direct call
        act_res = get_activities(limit=20)
        self.assertTrue(act_res["ok"])
        self.assertGreaterEqual(act_res["total"], 2)
        self.assertIn("agents", act_res)
        self.assertIn("stats", act_res)
        self.assertIn("filter_options", act_res)

        # 4. Test HTTP client endpoint
        resp = client.get("/api/plugins/zerofactory/activities?limit=10")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        self.assertIsInstance(data["activities"], list)

        # 5. Test actor filter
        resp_actor = client.get("/api/plugins/zerofactory/activities?actor=zf-builder")
        self.assertEqual(resp_actor.status_code, 200)
        actor_acts = resp_actor.json()["activities"]
        for a in actor_acts:
            self.assertEqual(a["actor"], "zf-builder")

        # 6. Test action filter
        resp_action = client.get("/api/plugins/zerofactory/activities?action=worker_done")
        self.assertEqual(resp_action.status_code, 200)
        action_acts = resp_action.json()["activities"]
        for a in action_acts:
            self.assertEqual(a["action"], "worker_done")

        # 7. Test search filter
        resp_search = client.get("/api/plugins/zerofactory/activities?search=Finished coding")
        self.assertEqual(resp_search.status_code, 200)
        self.assertGreaterEqual(len(resp_search.json()["activities"]), 1)

        # 8. Test board filter
        resp_board = client.get("/api/plugins/zerofactory/activities?board_slug=hotcode-dev-zerofactory")
        self.assertEqual(resp_board.status_code, 200)
        for a in resp_board.json()["activities"]:
            if a.get("board_slug"):
                self.assertEqual(a["board_slug"], "hotcode-dev-zerofactory")

        # 9. Test pagination
        resp_paged = client.get("/api/plugins/zerofactory/activities?limit=1&offset=0")
        self.assertEqual(resp_paged.status_code, 200)
        self.assertEqual(len(resp_paged.json()["activities"]), 1)
        self.assertEqual(resp_paged.json()["limit"], 1)
        self.assertEqual(resp_paged.json()["offset"], 0)

        # 10. Verify agent profiles presence in response
        agents_dict = {a["id"]: a for a in act_res["agents"]}
        for expected_id in ("zf-orchestrator", "zf-builder", "zf-reviewer", "dispatcher"):
            self.assertIn(expected_id, agents_dict)
            self.assertIn("status", agents_dict[expected_id])
            self.assertIn("role", agents_dict[expected_id])

        # 11. Test running task prioritization with board scoping
        with get_db_conn() as conn:
            conn.execute("UPDATE tasks SET status = 'running', updated_at = 2000000000 WHERE id = ?", (task_id,))
            conn.commit()

        scoped_res = get_activities(board_slug="hotcode-dev-zerofactory")
        self.assertTrue(scoped_res["ok"])
        builder_agent = next(a for a in scoped_res["agents"] if a["id"] == "zf-builder")
        self.assertIn(builder_agent["status"], ("active", "stuck"))
        self.assertIsNotNone(builder_agent["current_task"])
        self.assertEqual(builder_agent["current_task"]["id"], task_id)
        self.assertEqual(builder_agent["current_task"]["board_slug"], "hotcode-dev-zerofactory")

        # 12. Test task creation actor attribution (scanner tasks vs explicit actor)
        t_orch = create_task(TaskCreate(
            board_slug="hotcode-dev-zerofactory",
            title="Orchestrator Scanner Issue",
            status="todo",
            dedup_key="test_file.py:bug-fix",
            category="bug-fix"
        ))
        orch_acts = client.get("/api/plugins/zerofactory/activities?actor=zf-orchestrator").json()["activities"]
        self.assertTrue(any(a["task_id"] == t_orch["id"] and a["actor"] == "zf-orchestrator" for a in orch_acts))

        t_explicit = create_task(TaskCreate(
            board_slug="hotcode-dev-zerofactory",
            title="Explicit Actor Task",
            actor="zf-orchestrator",
            status="todo"
        ))
        with get_db_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT actor FROM task_activity WHERE task_id = ? AND action = 'create'", (t_explicit["id"],))
            self.assertEqual(c.fetchone()["actor"], "zf-orchestrator")
    def _make_reviewer_test_repo(self, td: str):
        """Create a real git repo + a reviewer worktree so the dispatcher can
        resolve the repo root via `git rev-parse --git-common-dir`."""
        import subprocess
        repo_path = Path(td) / "wt_repo"
        repo_path.mkdir()
        subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_path), check=True, capture_output=True)
        subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo_path))
        subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_path))
        (repo_path / "README.md").write_text("# Worktree Cleanup Test\n")
        subprocess.run(["git", "add", "."], cwd=str(repo_path), check=True)
        subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_path), check=True, capture_output=True)
        reviewer_ws = Path(td) / "ws_reviewer"
        subprocess.run(
            ["git", "worktree", "add", str(reviewer_ws), "-b", "task/wt-clean"],
            cwd=str(repo_path), check=True, capture_output=True
        )
        self.assertTrue(reviewer_ws.exists())
        return repo_path, reviewer_ws

    def _run_reviewer_pr_cycle(self, db_file: Path, gh_payload: dict, task_id: str = "wt-clean"):
        """Run one dispatch cycle against a reviewer task, faking the GitHub PR
        state via `gh pr view` and stubbing the worktree cleanup helper."""
        import json
        import subprocess
        import sqlite3
        from unittest.mock import patch, MagicMock
        from dispatcher import run_dispatch_cycle

        orig_skip_git = os.environ.pop("ZEROFACTORY_SKIP_GIT", None)
        orig_run = subprocess.run
        captured_gh = []

        def fake_run(cmd, *args, **kwargs):
            if len(cmd) >= 3 and cmd[0] == "gh" and cmd[1] == "pr" and cmd[2] == "view":
                captured_gh.append(list(cmd))
                res = MagicMock()
                res.returncode = 0
                res.stdout = json.dumps(gh_payload)
                return res
            return orig_run(cmd, *args, **kwargs)

        res = None
        try:
            with patch("dispatcher._remove_worktree") as mock_remove, \
                 patch("dispatcher.setup_worktree", return_value=None), \
                 patch("dispatcher.check_unresolved_conflicts", return_value=[]), \
                 patch("fcntl.flock", return_value=0), \
                 patch("subprocess.run", side_effect=fake_run):
                res = run_dispatch_cycle(db_file)
        finally:
            if orig_skip_git is not None:
                os.environ["ZEROFACTORY_SKIP_GIT"] = orig_skip_git

        def fetch(query):
            with sqlite3.connect(str(db_file)) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                return cur.execute(query).fetchall()

        return res, captured_gh, mock_remove, fetch, task_id

    def test_55_remove_worktree_missing_path_noops(self):
        """(a) _remove_worktree returns cleanly (no git subprocess, no logs) when
        the worktree path doesn't exist or is None/empty."""
        import subprocess
        from unittest.mock import patch
        from dispatcher import _remove_worktree

        td = tempfile.mkdtemp()
        try:
            repo_path = Path(td) / "repo"
            repo_path.mkdir()
            with patch("subprocess.run") as mock_run:
                # Missing path: pure no-op, no git invocation
                _remove_worktree(str(Path(td) / "does_not_exist"), repo_path)
                mock_run.assert_not_called()
                # None / empty path: pure no-op as well
                _remove_worktree(None, repo_path)
                _remove_worktree("", repo_path)
                mock_run.assert_not_called()
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_56_remove_worktree_survives_hanging_remove(self):
        """(b) _remove_worktree survives a hanging `git worktree remove`:
        subprocess.TimeoutExpired is caught, a warning is logged, the bounded
        `git worktree prune` fallback is attempted, and no exception escapes."""
        import shutil
        import subprocess
        from unittest.mock import patch
        from dispatcher import _remove_worktree

        orig_skip_git = os.environ.pop("ZEROFACTORY_SKIP_GIT", None)
        td = tempfile.mkdtemp()
        try:
            repo_path, worktree_ws = self._make_reviewer_test_repo(td)

            prune_calls = []

            def fake_run(cmd, *args, **kwargs):
                if isinstance(cmd, list) and cmd[:3] == ["git", "worktree", "remove"]:
                    self.assertIsNotNone(kwargs.get("timeout"), "worktree remove must be bounded by a timeout")
                    raise subprocess.TimeoutExpired(cmd=cmd, timeout=30)
                if isinstance(cmd, list) and cmd[:3] == ["git", "worktree", "prune"]:
                    prune_calls.append((cmd, kwargs))
                    self.assertIsNotNone(kwargs.get("timeout"), "worktree prune fallback must be bounded by a timeout")
                return orig_run(cmd, *args, **kwargs)

            # Capture the real subprocess.run BEFORE patching: inside the
            # patch context, `subprocess.run` is the mock itself.
            orig_run = subprocess.run

            with patch("subprocess.run", side_effect=fake_run), \
                 self.assertLogs("zerofactory.kanban.dispatcher", level="WARNING") as log_cm:
                # Must NOT raise despite the hung remove
                _remove_worktree(str(worktree_ws), repo_path)

            self.assertEqual(len(prune_calls), 1, "prune fallback should run exactly once on remove timeout")
            matched = [line for line in log_cm.output if "timed out" in line and str(worktree_ws) in line]
            self.assertTrue(matched, f"Expected a remove-timeout warning for {worktree_ws}, got: {log_cm.output}")
        finally:
            shutil.rmtree(td, ignore_errors=True)
            if orig_skip_git is not None:
                os.environ["ZEROFACTORY_SKIP_GIT"] = orig_skip_git

    def test_57_pr_lifecycle_survives_with_mocked_cleanup(self):
        """(c) The PR-lifecycle paths still complete and record their
        task_activity rows when the worktree cleanup helper is mocked:
        merged -> done, approved -> blocked, changes-requested -> ready,
        and the conflict path re-routes to the author."""
        import json
        import shutil
        import sqlite3
        from unittest.mock import patch

        td = tempfile.mkdtemp()
        try:
            # --- MERGED ---
            repo_path, reviewer_ws = self._make_reviewer_test_repo(td)
            db_file = Path(td) / "merged.db"
            self._create_conflict_test_db(db_file)
            with sqlite3.connect(str(db_file)) as conn:
                conn.execute("""
                    INSERT INTO tasks (id, title, status, assignee, workspace_path, branch_name, pr_url, created_at, updated_at)
                    VALUES ('wt-merged', 'Merged task', 'blocked', 'zf-reviewer', ?, 'task/wt-merged',
                            'https://github.com/hotcode-dev/zerofactory/pull/901', 1000, 1000)
                """, (str(reviewer_ws),))
                conn.commit()
            res, captured_gh, mock_remove, fetch, _ = self._run_reviewer_pr_cycle(
                db_file, {"state": "MERGED", "reviewDecision": None,
                          "url": "https://github.com/hotcode-dev/zerofactory/pull/901",
                          "mergeable": "MERGEABLE"}, task_id="wt-merged"
            )
            self.assertTrue(res.get("ok"), f"merged cycle should succeed: {res}")
            self.assertTrue(captured_gh, "gh pr view should have been called")
            mock_remove.assert_called()
            t_row = fetch("SELECT status, assignee, pr_url FROM tasks WHERE id = 'wt-merged'")[0]
            self.assertEqual(t_row["status"], "done")
            acts = fetch("SELECT action FROM task_activity WHERE task_id = 'wt-merged' AND action = 'merged'")
            self.assertEqual(len(acts), 1, "merged activity row missing")
            self.assertEqual(acts[0][0], "merged")

            # --- APPROVED ---
            td2 = tempfile.mkdtemp()
            try:
                repo_path2, reviewer_ws2 = self._make_reviewer_test_repo(td2)
                db_file2 = Path(td2) / "approved.db"
                self._create_conflict_test_db(db_file2)
                with sqlite3.connect(str(db_file2)) as conn:
                    conn.execute("""
                        INSERT INTO tasks (id, title, status, assignee, workspace_path, branch_name, pr_url, created_at, updated_at)
                        VALUES ('wt-approved', 'Approved task [PR Opened by zf-builder]', 'blocked', 'zf-reviewer', ?, 'task/wt-approved',
                                'https://github.com/hotcode-dev/zerofactory/pull/902', 1000, 1000)
                    """, (str(reviewer_ws2),))
                    conn.commit()
                res, captured_gh, mock_remove, fetch2, _ = self._run_reviewer_pr_cycle(
                    db_file2, {"state": "OPEN", "reviewDecision": "APPROVED",
                               "url": "https://github.com/hotcode-dev/zerofactory/pull/902",
                               "mergeable": "MERGEABLE"}, task_id="wt-approved"
                )
                self.assertTrue(res.get("ok"), f"approved cycle should succeed: {res}")
                mock_remove.assert_called()
                t_row = fetch2("SELECT title, status, assignee FROM tasks WHERE id = 'wt-approved'")[0]
                self.assertEqual(t_row["status"], "blocked")
                self.assertIn("[Human Review]", t_row["title"])
                acts = fetch2("SELECT action FROM task_activity WHERE task_id = 'wt-approved' AND action = 'approved'")
                self.assertEqual(len(acts), 1, "approved activity row missing")
                self.assertEqual(acts[0][0], "approved")
            finally:
                shutil.rmtree(td2, ignore_errors=True)

            # --- CHANGES_REQUESTED ---
            td3 = tempfile.mkdtemp()
            try:
                repo_path3, reviewer_ws3 = self._make_reviewer_test_repo(td3)
                db_file3 = Path(td3) / "changes.db"
                self._create_conflict_test_db(db_file3)
                with sqlite3.connect(str(db_file3)) as conn:
                    conn.execute("""
                        INSERT INTO tasks (id, title, status, assignee, workspace_path, branch_name, pr_url, created_at, updated_at)
                        VALUES ('wt-changes', 'Changes task [PR Opened by zf-builder]', 'blocked', 'zf-reviewer', ?, 'task/wt-changes',
                                'https://github.com/hotcode-dev/zerofactory/pull/903', 1000, 1000)
                    """, (str(reviewer_ws3),))
                    conn.commit()
                res, captured_gh, mock_remove, fetch3, _ = self._run_reviewer_pr_cycle(
                    db_file3, {"state": "OPEN", "reviewDecision": "CHANGES_REQUESTED",
                               "url": "https://github.com/hotcode-dev/zerofactory/pull/903",
                               "mergeable": "MERGEABLE"}, task_id="wt-changes"
                )
                self.assertTrue(res.get("ok"), f"changes-requested cycle should succeed: {res}")
                mock_remove.assert_called()
                t_row = fetch3("SELECT status, assignee FROM tasks WHERE id = 'wt-changes'")[0]
                self.assertEqual(t_row["status"], "ready")
                self.assertEqual(t_row["assignee"], "zf-builder")
                acts = fetch3("SELECT action FROM task_activity WHERE task_id = 'wt-changes' AND action = 'changes_requested'")
                self.assertEqual(len(acts), 1, "changes_requested activity row missing")
                self.assertEqual(acts[0][0], "changes_requested")
            finally:
                shutil.rmtree(td3, ignore_errors=True)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_58_pr_conflict_path_survives_with_mocked_cleanup(self):
        """(c, continued) The GitHub-CONFLICTING path re-routes to the author,
        records the pr_conflict activity row, and invokes the cleanup helper
        (mocked) without stalling the cycle."""
        import json
        import shutil
        import sqlite3
        from unittest.mock import patch, MagicMock

        td = tempfile.mkdtemp()
        try:
            repo_path, reviewer_ws = self._make_reviewer_test_repo(td)
            db_file = Path(td) / "conflict_wt.db"
            self._create_conflict_test_db(db_file)
            with sqlite3.connect(str(db_file)) as conn:
                conn.execute("""
                    INSERT INTO tasks (id, title, status, assignee, workspace_path, branch_name, pr_url, created_at, updated_at)
                    VALUES ('wt-conflict', 'Conflict task [PR Opened by zf-builder]', 'blocked', 'zf-reviewer', ?, 'task/wt-conflict',
                            'https://github.com/hotcode-dev/zerofactory/pull/904', 1000, 1000)
                """, (str(reviewer_ws),))
                conn.commit()

            res, captured_gh, mock_remove, fetch, _ = self._run_reviewer_pr_cycle(
                db_file, {"state": "OPEN", "reviewDecision": None,
                          "url": "https://github.com/hotcode-dev/zerofactory/pull/904",
                          "mergeable": "CONFLICTING"}, task_id="wt-conflict"
            )
            self.assertTrue(res.get("ok"), f"conflict cycle should succeed: {res}")
            self.assertTrue(captured_gh)
            mock_remove.assert_called()
            t_row = fetch("SELECT title, status, assignee FROM tasks WHERE id = 'wt-conflict'")[0]
            self.assertEqual(t_row["status"], "ready")
            self.assertEqual(t_row["assignee"], "zf-builder")
            self.assertIn("[PR Conflict]", t_row["title"])
            acts = fetch("SELECT details FROM task_activity WHERE task_id = 'wt-conflict' AND action = 'pr_conflict'")
            self.assertEqual(len(acts), 1)
            self.assertIn("conflicting", acts[0][0].lower())
        finally:
            shutil.rmtree(td, ignore_errors=True)


# ---------------------------------------------------------------------------
# Hermetic mock helpers for the repo auto-sync / fast-forward guard tests.
# These pin the guard behavior of dispatcher.sync_repo_main,
# dispatcher.get_default_branch, and zf_scanner_gate._auto_sync_repo without
# touching the real network or any git remotes.
# ---------------------------------------------------------------------------

from unittest.mock import MagicMock  # noqa: E402


class _ProcRecorder:
    """Stands in for subprocess.run.

    Keyed on the argv tuple. Canned results are returned for known commands;
    unknown commands return a success MagicMock (returncode 0). A canned value
    that is an Exception instance is raised instead of returned. Every call
    (including raised ones) is recorded in ``calls``.
    """

    def __init__(self, results=None, default_rc=0, default_stdout=""):
        self.results = dict(results or {})
        self.calls = []
        self.default_rc = default_rc
        self.default_stdout = default_stdout

    def __call__(self, cmd, *args, **kwargs):
        key = tuple(cmd)
        self.calls.append(key)
        if key in self.results:
            res = self.results[key]
            if isinstance(res, BaseException):
                raise res
            return res
        m = MagicMock()
        m.returncode = self.default_rc
        m.stdout = self.default_stdout
        m.stderr = ""
        return m


class _StrRecorder:
    """Stands in for zf_scanner_gate._run_cmd (returns a stripped str).

    Same keying/raise semantics as _ProcRecorder but yields strings.
    """

    def __init__(self, results=None, default=""):
        self.results = dict(results or {})
        self.calls = []
        self.default = default

    def __call__(self, cmd, cwd=None):
        key = tuple(cmd)
        self.calls.append(key)
        if key in self.results:
            res = self.results[key]
            if isinstance(res, BaseException):
                raise res
            return res
        return self.default


def _proc_result(rc=0, stdout=""):
    m = MagicMock()
    m.returncode = rc
    m.stdout = stdout
    m.stderr = ""
    return m


def _merge_cmds(rec):
    return [c for c in rec.calls if c[:2] == ("git", "merge")]


class TestSyncRepoMainGuards(unittest.TestCase):
    """Pin the guard logic of dispatcher.sync_repo_main / get_default_branch."""

    def _call_sync(self, default_branch, proc_results):
        from unittest.mock import patch
        import dispatcher

        rec = _ProcRecorder(proc_results)
        with patch.object(dispatcher, "get_default_branch", return_value=default_branch), \
             patch.object(dispatcher.subprocess, "run", new=rec):
            out = dispatcher.sync_repo_main(Path("/tmp/fake_repo"))
        return out, rec

    def test_55_merge_skipped_when_not_on_default_branch(self):
        rec_results = {
            ("git", "fetch", "origin", "main"): _proc_result(),
            ("git", "status", "--porcelain"): _proc_result(0, ""),
            ("git", "rev-parse", "--abbrev-ref", "HEAD"): _proc_result(0, "feature-x\n"),
        }
        out, rec = self._call_sync("main", rec_results)
        self.assertEqual(out, "main")
        self.assertEqual(_merge_cmds(rec), [], "merge must not run when off the default branch")

    def test_56_merge_skipped_when_worktree_dirty(self):
        rec_results = {
            ("git", "fetch", "origin", "main"): _proc_result(),
            ("git", "status", "--porcelain"): _proc_result(0, " M dirty.txt\n"),
            ("git", "rev-parse", "--abbrev-ref", "HEAD"): _proc_result(0, "main\n"),
        }
        out, rec = self._call_sync("main", rec_results)
        self.assertEqual(out, "main")
        self.assertEqual(_merge_cmds(rec), [], "merge must not run on a dirty worktree")

    def test_57_merge_uses_origin_default_branch_ref(self):
        rec_results = {
            ("git", "fetch", "origin", "main"): _proc_result(),
            ("git", "status", "--porcelain"): _proc_result(0, ""),
            ("git", "rev-parse", "--abbrev-ref", "HEAD"): _proc_result(0, "main\n"),
            ("git", "merge", "--ff-only", "origin/main"): _proc_result(),
        }
        out, rec = self._call_sync("main", rec_results)
        self.assertEqual(out, "main")
        self.assertIn(("git", "merge", "--ff-only", "origin/main"), rec.calls)

    def test_58_merge_ref_uses_resolved_default_branch_master(self):
        rec_results = {
            ("git", "fetch", "origin", "master"): _proc_result(),
            ("git", "status", "--porcelain"): _proc_result(0, ""),
            ("git", "rev-parse", "--abbrev-ref", "HEAD"): _proc_result(0, "master\n"),
            ("git", "merge", "--ff-only", "origin/master"): _proc_result(),
        }
        out, rec = self._call_sync("master", rec_results)
        self.assertEqual(out, "master")
        self.assertIn(("git", "merge", "--ff-only", "origin/master"), rec.calls)

    def test_59_returns_branch_when_fetch_times_out(self):
        import subprocess as sp
        rec_results = {
            ("git", "fetch", "origin", "main"): sp.TimeoutExpired(cmd="git", timeout=10),
        }
        out, rec = self._call_sync("main", rec_results)
        self.assertEqual(out, "main", "sync_repo_main must return the branch even when fetch raises")
        self.assertEqual(_merge_cmds(rec), [])

    # --- get_default_branch fallback chain ---

    def _call_default_branch(self, results):
        from unittest.mock import patch
        import dispatcher

        rec = _ProcRecorder(results)
        with patch.object(dispatcher.subprocess, "run", new=rec):
            out = dispatcher.get_default_branch(Path("/tmp/fake_repo"))
        return out, rec

    def test_60_default_branch_origin_head_hit(self):
        out, rec = self._call_default_branch({
            ("git", "symbolic-ref", "refs/remotes/origin/HEAD"): _proc_result(0, "refs/remotes/origin/main"),
        })
        self.assertEqual(out, "main")
        self.assertIn(("git", "symbolic-ref", "refs/remotes/origin/HEAD"), rec.calls)

    def test_61_default_branch_origin_main_showref(self):
        out, rec = self._call_default_branch({
            ("git", "symbolic-ref", "refs/remotes/origin/HEAD"): _proc_result(1, ""),
            ("git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/main"): _proc_result(0, ""),
        })
        self.assertEqual(out, "main")

    def test_62_default_branch_origin_master_showref(self):
        out, rec = self._call_default_branch({
            ("git", "symbolic-ref", "refs/remotes/origin/HEAD"): _proc_result(1, ""),
            ("git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/main"): _proc_result(1, ""),
            ("git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/master"): _proc_result(0, ""),
        })
        self.assertEqual(out, "master")

    def test_63_default_branch_fallback_literal_main(self):
        out, rec = self._call_default_branch({
            ("git", "symbolic-ref", "refs/remotes/origin/HEAD"): _proc_result(1, ""),
            ("git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/main"): _proc_result(1, ""),
            ("git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/master"): _proc_result(1, ""),
            ("git", "show-ref", "--verify", "--quiet", "refs/heads/main"): _proc_result(1, ""),
            ("git", "show-ref", "--verify", "--quiet", "refs/heads/master"): _proc_result(1, ""),
        })
        self.assertEqual(out, "main")


class TestAutoSyncRepoGuards(unittest.TestCase):
    """Pin the six guard/exit branches of zf_scanner_gate._auto_sync_repo."""

    def _load_gate(self):
        import importlib.util

        gate_path = (Path(__file__).resolve().parent / "scripts" / "zf_scanner_gate.py").resolve()
        spec = importlib.util.spec_from_file_location("zf_scanner_gate_guard_test", gate_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod

    def _call_gate(self, str_results, proc_results):
        from unittest.mock import patch

        mod = self._load_gate()
        str_rec = _StrRecorder(str_results)
        proc_rec = _ProcRecorder(proc_results)
        with patch.object(mod, "_run_cmd", new=str_rec), \
             patch.object(mod.subprocess, "run", new=proc_rec):
            out = mod._auto_sync_repo(Path("/tmp/fake_repo"))
        return out, str_rec, proc_rec

    def test_64_no_origin_early_return(self):
        out, str_rec, proc_rec = self._call_gate({("git", "remote"): "upstream"}, {})
        self.assertIsNone(out)
        self.assertEqual(str_rec.calls, [("git", "remote")])
        self.assertEqual(proc_rec.calls, [], "no fetch/show-ref/merge when origin is absent")

    def test_65_dirty_worktree_early_return(self):
        out, str_rec, proc_rec = self._call_gate(
            {("git", "remote"): "origin",
             ("git", "status", "--porcelain"): " M dirty.txt\n"},
            {},
        )
        self.assertIsNone(out)
        self.assertNotIn(("git", "fetch", "origin", "main"), proc_rec.calls)
        self.assertNotIn(("git", "merge", "--ff-only", "origin/main"), proc_rec.calls)

    def test_66_symbolic_ref_preferred(self):
        out, str_rec, proc_rec = self._call_gate(
            {("git", "remote"): "origin",
             ("git", "status", "--porcelain"): "",
             ("git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"): "origin/feature-x",
             ("git", "rev-parse", "--abbrev-ref", "HEAD"): "feature-x\n"},
            {("git", "fetch", "origin", "feature-x"): _proc_result(0, ""),
             ("git", "merge", "--ff-only", "origin/feature-x"): _proc_result(0, "")},
        )
        self.assertIsNone(out)
        self.assertIn(("git", "merge", "--ff-only", "origin/feature-x"), proc_rec.calls)

    def test_67_fallback_main_showref(self):
        out, str_rec, proc_rec = self._call_gate(
            {("git", "remote"): "origin",
             ("git", "status", "--porcelain"): "",
             ("git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"): "",
             ("git", "rev-parse", "--abbrev-ref", "HEAD"): "main\n"},
            {("git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/main"): _proc_result(0, ""),
             ("git", "fetch", "origin", "main"): _proc_result(0, ""),
             ("git", "merge", "--ff-only", "origin/main"): _proc_result(0, "")},
        )
        self.assertIsNone(out)
        self.assertIn(("git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/main"), proc_rec.calls)
        self.assertIn(("git", "merge", "--ff-only", "origin/main"), proc_rec.calls)

    def test_68_fallback_master_showref(self):
        out, str_rec, proc_rec = self._call_gate(
            {("git", "remote"): "origin",
             ("git", "status", "--porcelain"): "",
             ("git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"): "",
             ("git", "rev-parse", "--abbrev-ref", "HEAD"): "master\n"},
            {("git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/main"): _proc_result(1, ""),
             ("git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/master"): _proc_result(0, ""),
             ("git", "fetch", "origin", "master"): _proc_result(0, ""),
             ("git", "merge", "--ff-only", "origin/master"): _proc_result(0, "")},
        )
        self.assertIsNone(out)
        self.assertIn(("git", "merge", "--ff-only", "origin/master"), proc_rec.calls)

    def test_69_default_literal_main_when_no_remote_refs(self):
        out, str_rec, proc_rec = self._call_gate(
            {("git", "remote"): "origin",
             ("git", "status", "--porcelain"): "",
             ("git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"): "",
             ("git", "rev-parse", "--abbrev-ref", "HEAD"): "main\n"},
            {("git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/main"): _proc_result(1, ""),
             ("git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/master"): _proc_result(1, ""),
             ("git", "fetch", "origin", "main"): _proc_result(0, ""),
             ("git", "merge", "--ff-only", "origin/main"): _proc_result(0, "")},
        )
        self.assertIsNone(out)
        self.assertIn(("git", "merge", "--ff-only", "origin/main"), proc_rec.calls)

    def test_70_not_on_default_branch_early_return(self):
        out, str_rec, proc_rec = self._call_gate(
            {("git", "remote"): "origin",
             ("git", "status", "--porcelain"): "",
             ("git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"): "origin/main",
             ("git", "rev-parse", "--abbrev-ref", "HEAD"): "feature\n"},
            {},
        )
        self.assertIsNone(out)
        self.assertNotIn(("git", "fetch", "origin", "main"), proc_rec.calls)
        self.assertNotIn(("git", "merge", "--ff-only", "origin/main"), proc_rec.calls)

    def test_71_fetch_nonzero_aborts_before_merge(self):
        out, str_rec, proc_rec = self._call_gate(
            {("git", "remote"): "origin",
             ("git", "status", "--porcelain"): "",
             ("git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"): "origin/main",
             ("git", "rev-parse", "--abbrev-ref", "HEAD"): "main\n"},
            {("git", "fetch", "origin", "main"): _proc_result(1, "")},
        )
        self.assertIsNone(out)
        self.assertIn(("git", "fetch", "origin", "main"), proc_rec.calls)
        self.assertNotIn(("git", "merge", "--ff-only", "origin/main"), proc_rec.calls)

    def test_72_exceptions_swallowed(self):
        out, str_rec, proc_rec = self._call_gate(
            {("git", "remote"): RuntimeError("boom")}, {},
        )
        self.assertIsNone(out, "_auto_sync_repo must swallow exceptions and return cleanly")


if __name__ == "__main__":
    unittest.main()



