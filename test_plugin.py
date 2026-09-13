"""Tests for Zero Factory plugin backend and database."""

import os
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
    BoardCreate, TaskCreate, TaskUpdate, TaskMove, CommentCreate, DependencyLink,
    list_boards, create_board, list_tasks, create_task, get_task, get_task_session, update_task, move_task,
    add_comment, add_dependency, remove_dependency, get_stats, trigger_dispatch
)
from fastapi import FastAPI

app = FastAPI()
app.include_router(router, prefix="/api/plugins/zerofactory")
client = TestClient(app)


class TestZeroFactory(unittest.TestCase):

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
        self.assertIn("zero-factory-improvement-scanner-zerofactory", job_ids)
        self.assertTrue(any(j.startswith("zero-factory-improvement-scanner") for j in job_ids))

        # Verify workdir is resolved for zerofactory board
        zf_job = next(j for j in data["jobs"] if j["id"] == "zero-factory-improvement-scanner-zerofactory")
        self.assertIsNotNone(zf_job.get("workdir"))
        self.assertTrue(os.path.isdir(zf_job["workdir"]))

        # 2. Test POST /cron/sync
        sync_resp = client.post("/api/plugins/zerofactory/cron/sync")
        self.assertEqual(sync_resp.status_code, 200)
        self.assertTrue(sync_resp.json()["ok"])

        # 3. Test dynamic board scanner lifecycle (creation & deletion)
        # Create board
        res_cb = client.post("/api/plugins/zerofactory/boards", json={
            "slug": "test-dynamic-cron",
            "name": "Dynamic Cron Test",
            "git_url": "https://github.com/example/test-dynamic-cron.git"
        })
        self.assertEqual(res_cb.status_code, 200)

        # Check job is now present
        resp_after_create = client.get("/api/plugins/zerofactory/cron")
        ids_after_create = [j["id"] for j in resp_after_create.json()["jobs"]]
        self.assertIn("zero-factory-improvement-scanner-test-dynamic-cron", ids_after_create)

        # Delete board
        res_del = client.delete("/api/plugins/zerofactory/boards/test-dynamic-cron")
        self.assertEqual(res_del.status_code, 200)

        # Check job is pruned
        resp_after_del = client.get("/api/plugins/zerofactory/cron")
        ids_after_del = [j["id"] for j in resp_after_del.json()["jobs"]]
        self.assertNotIn("zero-factory-improvement-scanner-test-dynamic-cron", ids_after_del)

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
        # 1. Create board with omitted optional description/git_url (tests None coalesce)
        res_b = client.post("/api/plugins/zerofactory/boards", json={
            "slug": "test-omitted-fields",
            "name": "Omitted Fields Board"
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
            board_slug="zerofactory",
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
            board_slug="zerofactory",
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
            board_slug="zerofactory",
            status="todo"
        ))
        self.assertTrue(t3["ok"])
        self.assertFalse(t3.get("duplicate", False))

        t4 = create_task(TaskCreate(
            title=" standalone unique bug ",
            board_slug="zerofactory",
            status="todo"
        ))
        self.assertTrue(t4.get("duplicate"))
        self.assertEqual(t4["id"], t3["id"])

        # 4. Move t1 to 'done' -> new task with same files should now be allowed
        move_task(t1_id, TaskMove(status="done"))
        t5 = create_task(TaskCreate(
            title="Future refactor of auth and user",
            board_slug="zerofactory",
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
                {"id": "zero-factory-improvement-scanner-zerofactory", "origin": "zerofactory"},
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
            self.assertIn("zero-factory-improvement-scanner-zerofactory", synced_ids)
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
            "slug": "board-to-remove",
            "name": "Board To Remove"
        })
        self.assertEqual(res_create.status_code, 200)

        # 2. Setup mock target jobs file with its scanner job
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as tf:
            test_jobs_path = Path(tf.name)
        try:
            initial_jobs = [
                {"id": "zero-factory-improvement-scanner-board-to-remove", "origin": "zerofactory"},
                {"id": "zero-factory-improvement-scanner-zerofactory", "origin": "zerofactory"}
            ]
            save_jobs_to_file(test_jobs_path, initial_jobs)

            import builtin_cron
            orig_targets = builtin_cron.get_target_jobs_files
            builtin_cron.get_target_jobs_files = lambda: [test_jobs_path]

            os.environ.pop("ZEROFACTORY_SKIP_CRON_SYNC", None)
            try:
                # 3. Call DELETE /boards/board-to-remove
                res_del = client.delete("/api/plugins/zerofactory/boards/board-to-remove")
                self.assertEqual(res_del.status_code, 200)
                self.assertTrue(res_del.json()["ok"])
            finally:
                os.environ["ZEROFACTORY_SKIP_CRON_SYNC"] = "1"
                builtin_cron.get_target_jobs_files = orig_targets

            # 4. Verify board is removed from list_boards()
            boards = list_boards()["boards"]
            slugs = [b["slug"] for b in boards]
            self.assertNotIn("board-to-remove", slugs)

            # 5. Verify cron job is cleared from jobs.json
            synced = load_jobs_from_file(test_jobs_path)
            synced_ids = [j["id"] for j in synced]
            self.assertNotIn("zero-factory-improvement-scanner-board-to-remove", synced_ids)
            self.assertIn("zero-factory-improvement-scanner-zerofactory", synced_ids)

            # 6. Delete again returns 404
            res_del_404 = client.delete("/api/plugins/zerofactory/boards/board-to-remove")
            self.assertEqual(res_del_404.status_code, 404)
        finally:
            if test_jobs_path.exists():
                test_jobs_path.unlink()

    def test_13_update_board(self):
        # 1. Update existing board
        res = client.patch("/api/plugins/zerofactory/boards/zerofactory", json={
            "name": "ZeroFactory AI Core",
            "description": "Updated description for AI core",
            "git_url": "https://github.com/hotcode-dev/zerofactory-core.git"
        })
        self.assertEqual(res.status_code, 200)
        self.assertTrue(res.json()["ok"])

        # 2. Verify in list_boards
        boards = list_boards()["boards"]
        zf = next(b for b in boards if b["slug"] == "zerofactory")
        self.assertEqual(zf["name"], "ZeroFactory AI Core")
        self.assertEqual(zf["description"], "Updated description for AI core")
        self.assertEqual(zf["git_url"], "https://github.com/hotcode-dev/zerofactory-core.git")

        # 3. Update non-existent board returns 404
        res_404 = client.patch("/api/plugins/zerofactory/boards/non-existent-slug", json={
            "name": "Should Fail"
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
                board_slug="zerofactory",
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

        # 3. Dynamic board scanner: Wake-gate + continuity
        all_jobs = get_all_builtin_cron_jobs()
        scanner_jobs = [j for jid, j in all_jobs.items() if jid.startswith("zero-factory-improvement-scanner-")]
        self.assertGreater(len(scanner_jobs), 0)
        for sj in scanner_jobs:
            self.assertEqual(sj["script"], "zf_scanner_gate.py")
            self.assertFalse(sj["no_agent"])
            self.assertIn(sj["context_from"], (None, ["self"]))
            self.assertTrue(sj["continuity"])

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

    def test_26_task_pr_url_and_stats(self):
        """Verify task pr_url persistence, update, and get_stats pr_count metric."""
        # 1. Create task with pr_url
        req = TaskCreate(
            title="Task with Pull Request",
            description="Testing PR integration",
            board_slug="zerofactory",
            pr_url="https://github.com/hotcode-dev/zerofactory/pull/42"
        )
        task_id = create_task(req)["id"]
        
        # 2. Verify pr_url in get_task
        task = get_task(task_id)["task"]
        self.assertEqual(task["pr_url"], "https://github.com/hotcode-dev/zerofactory/pull/42")

        # 3. Verify get_stats pr_count
        stats = get_stats(board="zerofactory")
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

        stats_after = get_stats(board="zerofactory")
        self.assertEqual(stats_after["pr_count"], initial_pr_count - 1)

    def test_27_no_board_cron_generation(self):
        """Verify that when no boards exist, no improvement scanner jobs are generated."""
        from builtin_cron import get_all_builtin_cron_jobs
        import sqlite3

        with tempfile.TemporaryDirectory() as empty_td:
            empty_db = Path(empty_td) / "empty.db"
            with sqlite3.connect(str(empty_db)) as conn:
                conn.execute("CREATE TABLE boards (id INTEGER PRIMARY KEY, slug TEXT UNIQUE, name TEXT, description TEXT, git_url TEXT, created_at REAL, updated_at REAL)")
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
        if "zerofactory" not in existing:
            create_board(BoardCreate(
                slug="zerofactory",
                name="ZeroFactory",
                description="AI workflow",
                git_url="https://github.com/hotcode-dev/zerofactory",
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
            conflict_file.write_text("<<<<<<< HEAD\nLocal Change\n=======\nMain Change\n>>>>>>> main\n")
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
                conn.execute("CREATE TABLE boards (id INTEGER PRIMARY KEY, slug TEXT UNIQUE, name TEXT, description TEXT, git_url TEXT, created_at REAL, updated_at REAL)")

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
            conn.execute("CREATE TABLE boards (id INTEGER PRIMARY KEY, slug TEXT UNIQUE, name TEXT, description TEXT, git_url TEXT, created_at REAL, updated_at REAL)")
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


if __name__ == "__main__":
    unittest.main()



