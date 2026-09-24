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
os.environ["ZEROFACTORY_SKIP_DISPATCHER"] = "1"
os.environ["ZEROFACTORY_DISABLE_DISPATCHER"] = "1"
os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = "1"
os.environ["ZEROFACTORY_CRON_JOBS_FILE"] = str(Path(test_dir.name) / "test_jobs.json")
if "ZEROFACTORY_LOCK_PATH" not in os.environ:
    os.environ["ZEROFACTORY_LOCK_PATH"] = str(Path(test_dir.name) / "test_dispatcher.lock")

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


def _make_fake_state_db(td: str, profile: str, session_rows) -> Path:
    """Create a fake per-profile ``state.db`` (sessions + messages tables) so
    ``resolve_profile_state_db``-driven lookups in the dashboard return the
    given session rows without touching a real Hermes state DB.

    ``session_rows`` is a list of tuples:
        (id, model, started_at, ended_at, last_activity_at,
         last_activity_description, message_count, tool_call_count,
         cwd, title, profile_name)
    """
    import sqlite3

    prof_dir = Path(td) / ".hermes" / "profiles" / profile
    prof_dir.mkdir(parents=True, exist_ok=True)
    db_path = prof_dir / "state.db"
    conn = sqlite3.connect(str(db_path))
    cur = conn.cursor()
    cur.execute("""
        CREATE TABLE sessions (
            id TEXT PRIMARY KEY,
            model TEXT,
            started_at REAL,
            ended_at REAL,
            last_activity_at REAL,
            last_activity_description TEXT,
            message_count INTEGER,
            tool_call_count INTEGER,
            cwd TEXT,
            title TEXT,
            profile_name TEXT
        )
    """)
    cur.execute("""
        CREATE TABLE messages (
            id INTEGER PRIMARY KEY,
            session_id TEXT,
            role TEXT,
            tool_name TEXT,
            tool_calls TEXT,
            content TEXT,
            reasoning_content TEXT,
            timestamp REAL
        )
    """)
    cur.executemany(
        "INSERT INTO sessions (id, model, started_at, ended_at, last_activity_at,"
        " last_activity_description, message_count, tool_call_count, cwd, title, profile_name)"
        " VALUES (?,?,?,?,?,?,?,?,?,?,?)",
        session_rows,
    )
    conn.commit()
    conn.close()
    return db_path


class TestZeroFactory(unittest.TestCase):

    def setUp(self):
        init_db()
        os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = "1"

    def tearDown(self):
        os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = "1"

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

        # Dispatch again -> child should unblock to 'todo'
        d_res2 = trigger_dispatch()
        self.assertTrue(d_res2["ok"])
        self.assertEqual(get_task(child)["task"]["status"], "todo")

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
            "status": "running"
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "running")

        # Get stats
        resp = client.get("/api/plugins/zerofactory/stats")
        self.assertEqual(resp.status_code, 200)
        self.assertIn("columns", resp.json())
        self.assertIn("running", resp.json()["columns"])

    def test_07_builtin_cron(self):
        # 1. Test GET /cron
        resp = client.get("/api/plugins/zerofactory/cron")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertTrue(data["ok"])
        job_ids = [j["id"] for j in data["jobs"]]
        self.assertIn("zero-factory-task-queue-check", job_ids)
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

        # 1. Create a task in 'todo'
        t_id = create_task(TaskCreate(
            title="Implement Builder Task",
            status="todo",
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

        os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = "1"

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

    def test_09b_ai_sessions_exclude_dispatcher(self):
        from dashboard.plugin_api import resolve_task_all_sessions, list_all_sessions, AGENT_LABELS, AGENT_ICONS

        # 1. Verify AGENT_LABELS and AGENT_ICONS do not include dispatcher
        self.assertNotIn("dispatcher", AGENT_LABELS)
        self.assertNotIn("dispatcher", AGENT_ICONS)

        # 2. Verify /sessions API endpoint does not include dispatcher in profile inspection
        res = client.get("/api/plugins/zerofactory/sessions")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        sessions = data["sessions"]
        for s in sessions:
            self.assertNotEqual(s.get("agent"), "dispatcher")

        # 3. Test resolve_task_all_sessions does not inspect dispatcher
        task = {
            "id": "zf-mock-session-test",
            "title": "Mock Session Test",
            "status": "running",
            "assignee": "zf-builder",
            "metadata": {
                "session_id": "sess-test-123",
                "sessions": [
                    {"session_id": "sess-test-123", "agent": "zf-builder", "status": "ongoing"}
                ]
            }
        }
        resolved = resolve_task_all_sessions(task, backfill=False)
        self.assertTrue(all(s.get("agent") != "dispatcher" for s in resolved))

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

            import sqlite3
            import builtin_cron
            conn = sqlite3.connect(str(builtin_cron.get_db_path()))
            conn.execute("INSERT OR IGNORE INTO boards (slug, description, git_url, created_at, updated_at) VALUES ('hotcode-dev-zerofactory', 'Main', '', 1, 1)")
            conn.commit()
            conn.close()

            orig_targets = builtin_cron.get_target_jobs_files
            builtin_cron.get_target_jobs_files = lambda: [test_jobs_path]
            orig_cron_override = os.environ.get("ZEROFACTORY_CRON_JOBS_FILE")
            os.environ["ZEROFACTORY_CRON_JOBS_FILE"] = str(test_jobs_path)

            os.environ.pop("ZEROFACTORY_SKIP_CRON_SYNC", None)
            try:
                ensure_builtin_cron_jobs()
            finally:
                os.environ["ZEROFACTORY_SKIP_CRON_SYNC"] = "1"
                if orig_cron_override:
                    os.environ["ZEROFACTORY_CRON_JOBS_FILE"] = orig_cron_override
                else:
                    os.environ.pop("ZEROFACTORY_CRON_JOBS_FILE", None)
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
            orig_cron_override = os.environ.get("ZEROFACTORY_CRON_JOBS_FILE")
            os.environ["ZEROFACTORY_CRON_JOBS_FILE"] = str(test_jobs_path)

            os.environ.pop("ZEROFACTORY_SKIP_CRON_SYNC", None)
            try:
                # 3. Call DELETE /boards/test-org-board-to-remove
                res_del = client.delete("/api/plugins/zerofactory/boards/test-org-board-to-remove")
                self.assertEqual(res_del.status_code, 200)
                self.assertTrue(res_del.json()["ok"])
            finally:
                os.environ["ZEROFACTORY_SKIP_CRON_SYNC"] = "1"
                if orig_cron_override:
                    os.environ["ZEROFACTORY_CRON_JOBS_FILE"] = orig_cron_override
                else:
                    os.environ.pop("ZEROFACTORY_CRON_JOBS_FILE", None)
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
            try:
                dummy_proc.wait(timeout=2)
            except Exception:
                pass

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
        orig_cron_override = os.environ.get("ZEROFACTORY_CRON_JOBS_FILE")
        os.environ["ZEROFACTORY_CRON_JOBS_FILE"] = str(test_jobs_path)

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

            # 7. POST /cron/scheduler/toggle (master scheduler engine toggle)
            # Toggle OFF
            res_sched_off = client.post("/api/plugins/zerofactory/cron/scheduler/toggle", json={"enabled": False})
            self.assertEqual(res_sched_off.status_code, 200)
            self.assertFalse(res_sched_off.json()["scheduler_enabled"])

            # Verify all ZF jobs in jobs.json are paused when scheduler is disabled
            jobs_paused = load_jobs_from_file(test_jobs_path)
            for j in jobs_paused:
                if j["id"].startswith("zero-factory-"):
                    self.assertFalse(j["enabled"])
                    self.assertEqual(j["state"], "paused")

            # GET /cron reflects scheduler_enabled: false and paused jobs
            res_cron_paused = client.get("/api/plugins/zerofactory/cron")
            self.assertFalse(res_cron_paused.json()["scheduler_enabled"])
            self.assertFalse(next(j for j in res_cron_paused.json()["jobs"] if j["id"] == "zero-factory-task-queue-check")["enabled"])

            # Toggle ON
            res_sched_on = client.post("/api/plugins/zerofactory/cron/scheduler/toggle", json={"enabled": True})
            self.assertEqual(res_sched_on.status_code, 200)
            self.assertTrue(res_sched_on.json()["scheduler_enabled"])

            # Verify ZF jobs are resumed
            jobs_resumed = load_jobs_from_file(test_jobs_path)
            for j in jobs_resumed:
                if j["id"].startswith("zero-factory-"):
                    self.assertTrue(j["enabled"])
                    self.assertEqual(j["state"], "scheduled")

            # 8. PATCH /settings with enable_cron_scheduler: false
            res_patch = client.patch("/api/plugins/zerofactory/settings", json={"enable_cron_scheduler": False})
            self.assertEqual(res_patch.status_code, 200)
            self.assertFalse(res_patch.json()["settings"]["enable_cron_scheduler"])

            # Verify jobs in jobs.json are paused by PATCH /settings
            jobs_settings_paused = load_jobs_from_file(test_jobs_path)
            for j in jobs_settings_paused:
                if j["id"].startswith("zero-factory-"):
                    self.assertFalse(j["enabled"])
                    self.assertEqual(j["state"], "paused")

            # Restore scheduler to enabled
            client.patch("/api/plugins/zerofactory/settings", json={"enable_cron_scheduler": True})
        finally:
            if orig_cron_override:
                os.environ["ZEROFACTORY_CRON_JOBS_FILE"] = orig_cron_override
            else:
                os.environ.pop("ZEROFACTORY_CRON_JOBS_FILE", None)
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

    def test_20b_worker_spawn_session_isolation(self):
        """Worker spawn must only match sessions corresponding to its own task_id to prevent cross-contamination."""
        import tempfile
        import sqlite3
        import time
        from dispatcher import spawn_agent_worker
        from unittest.mock import patch, MagicMock

        with tempfile.NamedTemporaryFile(suffix=".db") as tmp_db:
            conn = sqlite3.connect(tmp_db.name)
            conn.execute("""
                CREATE TABLE sessions (
                    id TEXT PRIMARY KEY,
                    title TEXT,
                    cwd TEXT,
                    started_at REAL
                )
            """)
            now = time.time()
            # Session from concurrent task under same profile
            conn.execute("INSERT INTO sessions (id, title, cwd, started_at) VALUES ('sess-other', 'Task ID: zf-other', '/worktrees/zf-other', ?)", (now + 0.1,))
            # Session from our task
            conn.execute("INSERT INTO sessions (id, title, cwd, started_at) VALUES ('sess-mine', 'Task ID: zf-mine', '/worktrees/zf-mine', ?)", (now,))
            conn.commit()
            conn.close()

            with patch("dispatcher.resolve_profile_state_db", return_value=Path(tmp_db.name)), \
                 patch("subprocess.Popen") as mock_popen, \
                 patch.dict(os.environ, {}, clear=False):
                os.environ.pop("ZEROFACTORY_SKIP_WORKER_SPAWN", None)
                mock_proc = MagicMock()
                mock_proc.pid = 99999
                mock_proc.poll.return_value = None
                mock_popen.return_value = mock_proc

                pid, sess = spawn_agent_worker(
                    task_id="zf-mine",
                    title="My Task",
                    assignee="zf-reviewer",
                    priority="P0",
                    description="Test isolation",
                    workspace_path="/worktrees/zf-mine",
                    branch_name="task/zf-mine"
                )
                self.assertEqual(sess, "sess-mine")

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

        # 2. Dynamic board scanner: Wake-gate + stateless (continuity=False to prevent context bloating)
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

    def test_24a_daily_stats_inflight_duration_uses_started_at(self):
        """Regression (zf-40aec377): the daily report's "Currently In-Flight"
        duration must be derived from ``metadata.started_at`` (the authoritative
        dispatch time the dispatcher records at spawn), NOT from
        ``tasks.updated_at`` — which is written exactly once at claim/spawn and
        never refreshed while a worker runs, so ``now - updated_at`` permanently
        reports ~0-1m for the whole lifetime of a build.

        Behavior contract:
          * A task that has been running N minutes (``metadata.started_at =
            now - N*60``) but whose ``updated_at`` is seconds old must report
            ~N minutes, never ~0m.
          * If clock skew puts ``started_at`` slightly ahead of ``now``, the
            elapsed is clamped with ``max(0, ...)`` — the report never shows a
            negative duration.
        """
        import importlib.util
        import json
        import io
        import contextlib
        import sqlite3
        import time as _time
        import re

        scripts_dir = Path(__file__).resolve().parent / "scripts"
        spec = importlib.util.spec_from_file_location(
            "zf_daily_stats_under_test", scripts_dir / "zf_daily_stats.py"
        )
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        # --- Helper-level contract: started_at wins, then updated_at, then created_at.
        now = 2_000_000_000
        # started_at (recent) must beat a stale updated_at.
        rt_a = {
            "id": "t", "updated_at": now - 10, "created_at": now - 999,
            "metadata": json.dumps({"started_at": now - 47 * 60}),
        }
        self.assertEqual(mod._resolve_running_since(rt_a, now), now - 47 * 60)
        # No started_at -> fall back to updated_at.
        rt_b = {
            "id": "t", "updated_at": now - 120, "created_at": now - 999, "metadata": "{}",
        }
        self.assertEqual(mod._resolve_running_since(rt_b, now), now - 120)
        # No started_at and no updated_at (0/unset) -> fall back to created_at.
        rt_c = {
            "id": "t", "updated_at": 0, "created_at": now - 999, "metadata": "not-json",
        }
        self.assertEqual(mod._resolve_running_since(rt_c, now), now - 999)

        # --- End-to-end: run the report against a temp DB and assert the printed
        # in-flight line reflects started_at (not the stale updated_at) and is clamped.
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "stats.db"
            conn = sqlite3.connect(str(db_path))
            conn.executescript(
                "CREATE TABLE boards ("
                " slug TEXT PRIMARY KEY, description TEXT DEFAULT '', git_url TEXT DEFAULT '',"
                " created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);"
                "CREATE TABLE tasks ("
                " id TEXT PRIMARY KEY, board_slug TEXT NOT NULL DEFAULT '', title TEXT NOT NULL,"
                " description TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'triage', assignee TEXT NOT NULL DEFAULT 'unassigned',"
                " priority TEXT NOT NULL DEFAULT 'P2', workspace_path TEXT, workspace_kind TEXT DEFAULT 'worktree', branch_name TEXT,"
                " pr_url TEXT, tenant TEXT DEFAULT '', skills TEXT DEFAULT '[]', tags TEXT DEFAULT '[]', metadata TEXT DEFAULT '{}',"
                " created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);"
            )
            real_now = int(_time.time())
            conn.execute("INSERT INTO boards (slug, created_at, updated_at) VALUES (?,1,1)", ("stats-board",))
            # Task A: running ~47 min per metadata.started_at, but updated_at is seconds old
            # (the stale-0m bug: old code would have printed ~0m).
            conn.execute(
                "INSERT INTO tasks (id, board_slug, title, status, assignee, metadata, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                ("zf-run-a", "stats-board", "Long build", "running", "zf-builder",
                 json.dumps({"started_at": real_now - 47 * 60, "worker_pid": 1234}),
                 real_now - 47 * 60, real_now - 5),
            )
            # Task B: clock skew — started_at in the future; must clamp to 0m (never negative).
            conn.execute(
                "INSERT INTO tasks (id, board_slug, title, status, assignee, metadata, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                ("zf-run-b", "stats-board", "Skewed task", "running", "zf-builder",
                 json.dumps({"started_at": real_now + 600}), real_now - 5, real_now - 5),
            )
            conn.commit()
            conn.close()

            old_db = os.environ.get("ZEROFACTORY_DB")
            os.environ["ZEROFACTORY_DB"] = str(db_path)
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    rc = mod.run_daily_stats()
            finally:
                if old_db is None:
                    os.environ.pop("ZEROFACTORY_DB", None)
                else:
                    os.environ["ZEROFACTORY_DB"] = old_db
            out = buf.getvalue()
            self.assertEqual(rc, 0)

            # Task A: active for ~47m (derived from started_at, NOT the stale updated_at).
            m = re.search(r"`zf-run-a`.*active for (-?\d+)m", out)
            self.assertIsNotNone(m, f"missing in-flight line for zf-run-a in:\n{out}")
            mins_a = int(m.group(1))
            self.assertGreaterEqual(mins_a, 45,
                "in-flight duration must reflect metadata.started_at (~47m), not the stale updated_at (~0m)")
            self.assertLess(mins_a, 60, f"expected ~47m, got {mins_a}m")

            # Task B: clamped to 0m, never negative (clock skew).
            m2 = re.search(r"`zf-run-b`.*active for (-?\d+)m", out)
            self.assertIsNotNone(m2, f"missing in-flight line for zf-run-b in:\n{out}")
            self.assertGreaterEqual(int(m2.group(1)), 0, "in-flight duration must never be negative (clock-skew clamp)")
            self.assertNotIn("active for -", out, "report must never show a negative elapsed duration")

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

    def test_25b_scanner_gate_force_flag_not_slug(self):
        """Regression: `resolve_board_slug` must NOT capture the `--force` CLI flag
        as the board slug. The first positional arg is the slug; any `-`-prefixed
        flag token (e.g. `--force`) is skipped so the call falls through to the
        ZEROFACTORY_BOARD env / DB / repo-name fallback.

        The bug: `sys.argv[1]` was treated as the slug unconditionally, so a
        `python3 zf_scanner_gate.py --force` invocation returned the literal string
        `--force` as the board slug, silently disabling the duplicate-task safeguard
        and defeating the 0-token wake-gate suppression."""
        import importlib.util

        # Load the script from THIS repo (the source of truth we are testing), NOT the
        # deployed copy under the Hermes home (which may be a stale pre-fix snapshot).
        gate_path = (Path(__file__).resolve().parent / "scripts" / "zf_scanner_gate.py").resolve()
        self.assertTrue(gate_path.is_file(), f"missing {gate_path}")
        spec = importlib.util.spec_from_file_location("zf_scanner_gate_slug_test", gate_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)

        old_argv = sys.argv
        old_board = os.environ.get("ZEROFACTORY_BOARD")
        try:
            repo_dir = Path("myrepo")
            # Deterministic env fallback to fall through to when a flag is skipped.
            os.environ["ZEROFACTORY_BOARD"] = "env-fallback-board"

            # 1. A real positional slug arg still wins (and beats the env fallback).
            sys.argv = [gate_path.name, "my-real-board"]
            self.assertEqual(mod.resolve_board_slug(repo_dir), "my-real-board")

            # 2. `--force` must NOT be captured as the slug — it falls through to env.
            sys.argv = [gate_path.name, "--force"]
            self.assertEqual(mod.resolve_board_slug(repo_dir), "env-fallback-board")
            self.assertNotEqual(mod.resolve_board_slug(repo_dir), "--force")

            # 3. A flag before the positional slug: the slug is still resolved.
            sys.argv = [gate_path.name, "--force", "my-real-board"]
            self.assertEqual(mod.resolve_board_slug(repo_dir), "my-real-board")

            # 4. Only flags / no positional args -> falls through to the env fallback.
            sys.argv = [gate_path.name]
            self.assertEqual(mod.resolve_board_slug(repo_dir), "env-fallback-board")
        finally:
            sys.argv = old_argv
            if old_board is None:
                os.environ.pop("ZEROFACTORY_BOARD", None)
            else:
                os.environ["ZEROFACTORY_BOARD"] = old_board
    def test_25c_scanner_gate_auto_pull_remote(self):
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

    def test_25c_scanner_gate_retries_if_no_task_created_after_cooldown(self):
        """Verify that when a scan completes without producing any tasks, the scanner gate
        suppresses during retry cooldown, retries after cooldown expires if 0 tasks exist,
        caps retries at max_attempts, and permanently suppresses once a task is produced.
        """
        import contextlib
        import importlib.util
        import io
        import json
        import sqlite3
        import subprocess
        import time

        gate_path = (Path(__file__).resolve().parent / "scripts" / "zf_scanner_gate.py").resolve()

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
            slug = "gate-retry-test-board"

            # 1. Fresh git repo with a single commit.
            repo = td / "repo"
            repo.mkdir()
            git(repo, "init", "-q")
            git(repo, "config", "user.email", "scan@test.local")
            git(repo, "config", "user.name", "Scan Test")
            (repo / "main.py").write_text("print('hello')\n", encoding="utf-8")
            git(repo, "add", ".")
            git(repo, "commit", "-qm", "initial commit")

            # 2. Temp zerofactory.db
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

            def run_gate(extra_env=None):
                mod = load_gate()
                mod.STATE_FILE = state_path
                old_argv, old_cwd = sys.argv, os.getcwd()
                old_db = os.environ.get("ZEROFACTORY_DB")
                old_state = os.environ.get("ZEROFACTORY_SCANNER_STATE")
                sys.argv = [gate_path.name, slug]
                os.chdir(str(repo))
                os.environ["ZEROFACTORY_DB"] = str(db_path)
                os.environ["ZEROFACTORY_SCANNER_STATE"] = str(state_path)
                os.environ.pop("ZEROFACTORY_FORCE_SCAN", None)
                if extra_env:
                    for k, v in extra_env.items():
                        os.environ[k] = str(v)
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
                    if old_state is None:
                        os.environ.pop("ZEROFACTORY_SCANNER_STATE", None)
                    else:
                        os.environ["ZEROFACTORY_SCANNER_STATE"] = old_state
                    os.environ.pop("ZEROFACTORY_FORCE_SCAN", None)
                    if extra_env:
                        for k in extra_env:
                            os.environ.pop(k, None)
                out = buf.getvalue()
                wake = json.loads(out.strip().splitlines()[-1])
                return rc, wake.get("wakeAgent"), out

            # Run 1: Baseline scan fires
            rc1, wake1, out1 = run_gate()
            self.assertEqual(rc1, 0)
            self.assertTrue(wake1, "baseline scan must wake agent")

            # Run 2: Immediate check -> cooldown active, suppresses (wakeAgent=False)
            rc2, wake2, out2 = run_gate()
            self.assertEqual(rc2, 0)
            self.assertFalse(wake2, "cooldown must suppress immediate re-check")
            self.assertIn("SCAN_COOLDOWN_ACTIVE", out2)

            # Advance state timestamp to simulate cooldown expired (no tasks created)
            st = json.loads(state_path.read_text(encoding="utf-8"))
            st[slug]["last_scan_at"] = int(time.time()) - 2000
            state_path.write_text(json.dumps(st), encoding="utf-8")

            # Run 3: Cooldown expired and 0 tasks created -> RETRY scan wakes agent (attempt 2)
            rc3, wake3, out3 = run_gate()
            self.assertEqual(rc3, 0)
            self.assertTrue(wake3, "expired cooldown without tasks must wake agent for retry")
            self.assertIn("RETRY_SCAN_TRIGGERED", out3)

            # Verify scan_attempts incremented to 2
            st = json.loads(state_path.read_text(encoding="utf-8"))
            self.assertEqual(st[slug]["scan_attempts"], 2)

            # Advance timestamp again, but set max attempts to 2
            st[slug]["last_scan_at"] = int(time.time()) - 2000
            state_path.write_text(json.dumps(st), encoding="utf-8")

            # Run 4: Max attempts reached -> suppresses permanently
            rc4, wake4, out4 = run_gate(extra_env={"ZEROFACTORY_SCAN_MAX_ATTEMPTS": "2"})
            self.assertEqual(rc4, 0)
            self.assertFalse(wake4, "max attempts reached must suppress")
            self.assertIn("unchanged after 2 scan attempts", out4)

            # Run 5: If a task WAS created (task_created=True or db task created_at >= commit),
            # gate suppresses permanently even if board currently has 0 open tasks.
            st[slug]["last_scan_at"] = int(time.time()) - 2000
            st[slug]["task_created"] = True
            st[slug]["scan_attempts"] = 0
            state_path.write_text(json.dumps(st), encoding="utf-8")

            rc5, wake5, out5 = run_gate()
            self.assertEqual(rc5, 0)
            self.assertFalse(wake5, "board that already produced tasks must suppress")
            self.assertIn("NO_CHANGES_DETECTED", out5)

    def test_25d_scanner_gate_blocked_tasks_do_not_suppress_and_outage_recovery(self):
        """Verify that tasks in 'blocked' status (e.g. human PR review) do NOT suppress
        the scanner gate, active pipeline tasks (running/todo) DO suppress, and
        the outage recovery reset cooldown clears attempts after a long pause.
        """
        import contextlib
        import importlib.util
        import io
        import json
        import sqlite3
        import subprocess
        import time

        gate_path = (Path(__file__).resolve().parent / "scripts" / "zf_scanner_gate.py").resolve()

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
            slug = "gate-blocked-test-board"

            repo = td / "repo"
            repo.mkdir()
            git(repo, "init", "-q")
            git(repo, "config", "user.email", "scan@test.local")
            git(repo, "config", "user.name", "Scan Test")
            (repo / "main.py").write_text("x = 1\n", encoding="utf-8")
            git(repo, "add", ".")
            git(repo, "commit", "-qm", "initial commit")

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
            # Insert a BLOCKED task (waiting for human review)
            conn.execute(
                "INSERT INTO tasks (id, board_slug, title, status, created_at, updated_at)"
                " VALUES (?, ?, ?, 'blocked', 1, 1)",
                (slug + "-b1", slug, "PR opened waiting for human review"),
            )
            conn.commit()
            conn.close()

            state_path = td / "scanner_state.json"

            def run_gate(extra_env=None):
                mod = load_gate()
                mod.STATE_FILE = state_path
                old_argv, old_cwd = sys.argv, os.getcwd()
                old_db = os.environ.get("ZEROFACTORY_DB")
                old_state = os.environ.get("ZEROFACTORY_SCANNER_STATE")
                sys.argv = [gate_path.name, slug]
                os.chdir(str(repo))
                os.environ["ZEROFACTORY_DB"] = str(db_path)
                os.environ["ZEROFACTORY_SCANNER_STATE"] = str(state_path)
                os.environ.pop("ZEROFACTORY_FORCE_SCAN", None)
                if extra_env:
                    for k, v in extra_env.items():
                        os.environ[k] = str(v)
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
                    if old_state is None:
                        os.environ.pop("ZEROFACTORY_SCANNER_STATE", None)
                    else:
                        os.environ["ZEROFACTORY_SCANNER_STATE"] = old_state
                    os.environ.pop("ZEROFACTORY_FORCE_SCAN", None)
                    if extra_env:
                        for k in extra_env:
                            os.environ.pop(k, None)
                out = buf.getvalue()
                wake = json.loads(out.strip().splitlines()[-1])
                return rc, wake.get("wakeAgent"), out

            # Baseline scan fires despite blocked task existing
            rc1, wake1, out1 = run_gate()
            self.assertEqual(rc1, 0)
            self.assertTrue(wake1, "blocked task must not prevent baseline scan")

            # Fast-forward past retry cooldown without tasks created
            st = json.loads(state_path.read_text(encoding="utf-8"))
            st[slug]["last_scan_at"] = int(time.time()) - 2000
            state_path.write_text(json.dumps(st), encoding="utf-8")

            # Retry scan should wake because pipeline in-flight tasks is 0 (only blocked tasks exist)
            rc2, wake2, out2 = run_gate()
            self.assertEqual(rc2, 0)
            self.assertTrue(wake2, "retry scan must wake when only blocked tasks exist")
            self.assertIn("RETRY_SCAN_TRIGGERED", out2)

            # Now add a RUNNING task
            conn = sqlite3.connect(str(db_path))
            conn.execute(
                "INSERT INTO tasks (id, board_slug, title, status, created_at, updated_at)"
                " VALUES (?, ?, ?, 'running', 2, 2)",
                (slug + "-r1", slug, "Active task in pipeline"),
            )
            conn.commit()
            conn.close()

            # Advance time again
            st = json.loads(state_path.read_text(encoding="utf-8"))
            st[slug]["last_scan_at"] = int(time.time()) - 2000
            state_path.write_text(json.dumps(st), encoding="utf-8")

            # Running task should now suppress as active pipeline tasks
            rc3, wake3, out3 = run_gate()
            self.assertEqual(rc3, 0)
            self.assertFalse(wake3, "running task must suppress scan")
            self.assertIn("active pipeline tasks (1)", out3)

            # Test outage recovery: remove running task, set attempts=3 and last_scan_at to 3 hours ago
            conn = sqlite3.connect(str(db_path))
            conn.execute("DELETE FROM tasks WHERE status = 'running'")
            conn.commit()
            conn.close()

            st[slug]["scan_attempts"] = 3
            st[slug]["last_scan_at"] = int(time.time()) - 10000
            state_path.write_text(json.dumps(st), encoding="utf-8")

            # Outage recovery should reset attempts and wake agent
            rc4, wake4, out4 = run_gate(extra_env={"ZEROFACTORY_SCAN_RESET_COOLDOWN": "7200"})
            self.assertEqual(rc4, 0)
            self.assertTrue(wake4, "outage recovery after reset cooldown must reset attempts and wake")
            self.assertIn("RETRY_SCAN_TRIGGERED", out4)

    def test_25e_scanner_state_atomic_write(self):
        """Regression: the wake-gate state file must be written atomically.

        `save_state` / `write_state_atomic` must publish via a temp file +
        `os.replace` (same pattern as `builtin_cron.save_jobs_to_file`), NOT a
        bare in-place `write_text`. A non-atomic in-place overwrite lets a
        concurrent reader observe a torn/partial JSON document, which the old
        `except: pass` silently swallowed (state reset to {} -> lost
        `last_scanned_sha` -> LLM re-fires; lost `task_created` -> duplicates).

        We point ZEROFACTORY_SCANNER_STATE at a tmp path, then patch
        `os.replace` to record that the atomic publish was actually used and
        verify the final file parses and matches what we saved.
        """
        import importlib.util
        import json

        gate_path = (Path(__file__).resolve().parent / "scripts" / "zf_scanner_gate.py").resolve()
        self.assertTrue(gate_path.is_file(), f"missing {gate_path}")

        def load_gate():
            spec = importlib.util.spec_from_file_location("zf_scanner_gate_atomic", gate_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod

        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "scanner_state.json"
            mod = load_gate()

            old_env = os.environ.get("ZEROFACTORY_SCANNER_STATE")
            os.environ["ZEROFACTORY_SCANNER_STATE"] = str(state_path)
            replaced = []
            real_replace = os.replace
            try:
                # Confirm get_state_file() honors the env override.
                self.assertEqual(mod.get_state_file(), state_path)

                # 1. save_state() must route through the atomic writer:
                #    it must call os.replace exactly once (temp file -> target),
                #    NOT write_text in place.
                def _record_replace(src, dst):
                    replaced.append((str(src), str(dst)))
                    return real_replace(src, dst)

                # write_state_atomic returns a bool; save_state routes through
                # it but returns None, so we assert on the os.replace side
                # effect (the atomic publish), not the return value.
                self.assertTrue(mod.write_state_atomic({"board-a": {"last_scanned_sha": "abc"}}))
                os.replace = _record_replace
                try:
                    mod.save_state({"board-b": {"task_created": True}})
                finally:
                    os.replace = real_replace

                self.assertEqual(len(replaced), 1, "save_state must publish via os.replace exactly once")
                src, dst = replaced[0]
                # The source of the replace is a temp file in the SAME dir as the
                # target (rename within one filesystem is what makes it atomic).
                self.assertTrue(src.startswith(str(state_path.parent)),
                                "temp file must live in the state file's directory")
                self.assertNotEqual(src, str(state_path), "must replace a temp file, not the target in place")
                self.assertEqual(dst, str(state_path))

                # 2. Final JSON parses and carries exactly what we saved.
                self.assertTrue(state_path.exists())
                data = json.loads(state_path.read_text(encoding="utf-8"))
                self.assertEqual(data, {"board-b": {"task_created": True}})

                # 3. No partial / leftover temp files remain after a clean write.
                leftovers = [p for p in state_path.parent.iterdir()
                             if p.suffix == ".tmp" or p.name.endswith(".tmp")]
                self.assertEqual(leftovers, [], "no temp files may be left behind")

                # 4. load_state round-trips the atomic write.
                self.assertEqual(mod.load_state(), data)
            finally:
                if old_env is None:
                    os.environ.pop("ZEROFACTORY_SCANNER_STATE", None)
                else:
                    os.environ["ZEROFACTORY_SCANNER_STATE"] = old_env

    def test_25f_scanner_state_concurrent_read_modify_write(self):
        """Regression: N concurrent atomic read-modify-writes must not lose updates.

        The dashboard POST /tasks handler and the scanner-gate cron are two
        independent writers of the shared state file. `mark_task_created` runs
        the read-modify-write under an exclusive flock, so no board's
        `task_created` / `scan_attempts` can be clobbered by another writer.
        Hammer the shared ZEROFACTORY_SCANNER_STATE tmp file from many threads
        and assert the final document parses and contains EVERY key written
        (no lost update).
        """
        import importlib.util
        import json
        import threading

        gate_path = (Path(__file__).resolve().parent / "scripts" / "zf_scanner_gate.py").resolve()
        self.assertTrue(gate_path.is_file(), f"missing {gate_path}")

        def load_gate():
            spec = importlib.util.spec_from_file_location("zf_scanner_gate_conc", gate_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod

        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "scanner_state.json"
            mod = load_gate()

            old_env = os.environ.get("ZEROFACTORY_SCANNER_STATE")
            os.environ["ZEROFACTORY_SCANNER_STATE"] = str(state_path)
            try:
                n_boards = 12
                boards = [f"board-{i}" for i in range(n_boards)]

                # Pre-seed a few distinct per-board keys that must survive.
                seed = {b: {"last_scanned_sha": f"sha-{i}", "scan_attempts": i % 3}
                        for i, b in enumerate(boards)}
                self.assertTrue(mod.write_state_atomic(seed))

                barrier = threading.Barrier(n_boards)
                errors = []

                def worker(slug):
                    try:
                        barrier.wait()
                        # mark_task_created sets task_created=True and resets
                        # scan_attempts=0 for its own board under the flock.
                        if not mod.mark_task_created(slug):
                            errors.append(f"mark_task_created({slug!r}) returned False")
                    except Exception as e:  # pragma: no cover - defensive
                        errors.append(f"worker {slug!r} raised {e!r}")

                threads = [threading.Thread(target=worker, args=(b,)) for b in boards]
                for t in threads:
                    t.start()
                for t in threads:
                    t.join()

                self.assertEqual(errors, [], f"concurrent writes reported errors: {errors}")

                # Final document must parse ...
                raw = state_path.read_text(encoding="utf-8")
                data = json.loads(raw)
                # ... and every board's key must be present with no lost update.
                self.assertEqual(len(data), n_boards,
                                 f"lost board entries; got {sorted(data)} expected {n_boards}")
                for i, b in enumerate(boards):
                    entry = data.get(b)
                    self.assertIsInstance(entry, dict, f"missing/corrupt entry for {b}")
                    # task_created + reset attempts recorded by the concurrent RMW ...
                    self.assertTrue(entry.get("task_created"), f"{b}: task_created lost")
                    self.assertEqual(entry.get("scan_attempts"), 0, f"{b}: scan_attempts not reset")
                    # ... AND the pre-seeded last_scanned_sha survived (not clobbered).
                    self.assertEqual(entry.get("last_scanned_sha"), f"sha-{i}",
                                     f"{b}: pre-seeded last_scanned_sha clobbered")
            finally:
                if old_env is None:
                    os.environ.pop("ZEROFACTORY_SCANNER_STATE", None)
                else:
                    os.environ["ZEROFACTORY_SCANNER_STATE"] = old_env

    def test_25g_dashboard_create_task_marks_scanner_state_atomic(self):
        """Regression: POST /tasks must atomically flag `task_created` in the
        shared scanner state file via the flock-guarded helper (not a bare
        read_text/write_text). Point the state file at a tmp path, create a
        task for a board, and assert the flag landed and the file stays valid
        JSON (no torn write).
        """
        import json

        from dashboard import plugin_api

        with tempfile.TemporaryDirectory() as td:
            # Create a dedicated board so the task FK is satisfied and the
            # board entry does not collide with other tests' state.
            board_res = create_board(BoardCreate(
                git_url="https://github.com/example/dash-rmw-state.git",
                description="Regression: atomic scanner-state RMW",
            ))
            self.assertTrue(board_res.get("ok"))
            slug = board_res["slug"]

            state_path = Path(td) / "scanner_state.json"
            # Seed an existing state entry for the board.
            state_path.write_text(json.dumps(
                {slug: {"last_scanned_sha": "seed-sha", "scan_attempts": 4}}),
                encoding="utf-8")

            old_env = os.environ.get("ZEROFACTORY_SCANNER_STATE")
            os.environ["ZEROFACTORY_SCANNER_STATE"] = str(state_path)
            try:
                created = create_task(TaskCreate(
                    title="Task that flags scanner state",
                    description="Regression: atomic scanner-state RMW",
                    board_slug=slug,
                    status="todo",
                ))
                self.assertTrue(created.get("ok"))

                data = json.loads(state_path.read_text(encoding="utf-8"))
                self.assertIn(slug, data, "board entry missing from scanner state")
                self.assertTrue(data[slug].get("task_created"), "task_created not recorded")
                self.assertEqual(data[slug].get("scan_attempts"), 0, "scan_attempts not reset")
                # Pre-seeded last_scanned_sha must survive the read-modify-write.
                self.assertEqual(data[slug].get("last_scanned_sha"), "seed-sha",
                                 "last_scanned_sha clobbered by dashboard RMW")
                # The dashboard must have routed through the shared flock helper.
                self.assertTrue(hasattr(plugin_api, "_mark_scanner_task_created"))
            finally:
                if old_env is None:
                    os.environ.pop("ZEROFACTORY_SCANNER_STATE", None)
                else:
                    os.environ["ZEROFACTORY_SCANNER_STATE"] = old_env

    def test_25h_scanner_gate_capacity_driven_idle_scanning(self):
        """Verify that when scan_on_idle is enabled, the scanner gate wakes the agent
        on unchanged commits when active running workers < threshold and cooldown elapsed,
        suppresses when pipeline is busy, and honors ZEROFACTORY_IDLE_SCAN.
        """
        import contextlib
        import importlib.util
        import io
        import json
        import sqlite3
        import subprocess
        import time

        gate_path = (Path(__file__).resolve().parent / "scripts" / "zf_scanner_gate.py").resolve()

        def git(repo, *args):
            subprocess.run(
                ["git", *args], cwd=str(repo), check=True,
                capture_output=True, text=True,
                env={**os.environ, "GIT_CONFIG_GLOBAL": "/dev/null", "GIT_CONFIG_SYSTEM": "/dev/null"},
            )

        def load_gate():
            spec = importlib.util.spec_from_file_location("zf_scanner_gate_idle_test", gate_path)
            mod = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(mod)
            return mod

        with tempfile.TemporaryDirectory() as td:
            td = Path(td)
            slug = "gate-idle-capacity-test"

            repo = td / "repo"
            repo.mkdir()
            git(repo, "init", "-q")
            git(repo, "config", "user.email", "scan@test.local")
            git(repo, "config", "user.name", "Scan Test")
            (repo / "main.py").write_text("x = 1\n", encoding="utf-8")
            git(repo, "add", ".")
            git(repo, "commit", "-qm", "initial commit")

            db_path = td / "gate.db"
            conn = sqlite3.connect(str(db_path))
            conn.executescript(
                "CREATE TABLE boards (slug TEXT PRIMARY KEY, description TEXT DEFAULT '', git_url TEXT DEFAULT '', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);"
                "CREATE TABLE tasks (id TEXT PRIMARY KEY, board_slug TEXT NOT NULL DEFAULT '', title TEXT NOT NULL, description TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'triage', assignee TEXT NOT NULL DEFAULT 'unassigned', priority TEXT NOT NULL DEFAULT 'P2', workspace_path TEXT, workspace_kind TEXT DEFAULT 'worktree', branch_name TEXT, pr_url TEXT, tenant TEXT DEFAULT '', skills TEXT DEFAULT '[]', tags TEXT DEFAULT '[]', metadata TEXT DEFAULT '{}', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);"
                "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at INTEGER NOT NULL);"
                "INSERT INTO boards (slug, created_at, updated_at) VALUES ('gate-idle-capacity-test', 1, 1);"
                "INSERT INTO settings (key, value, updated_at) VALUES ('scan_on_idle', 'true', 1);"
                "INSERT INTO settings (key, value, updated_at) VALUES ('idle_scan_active_threshold', '2', 1);"
                "INSERT INTO settings (key, value, updated_at) VALUES ('idle_scan_cooldown_minutes', '15', 1);"
                "INSERT INTO settings (key, value, updated_at) VALUES ('idle_scan_max_todo', '2', 1);"
            )
            conn.commit()
            conn.close()

            state_path = td / "scanner_state.json"

            def run_gate(extra_env=None):
                mod = load_gate()
                mod.STATE_FILE = state_path
                old_argv, old_cwd = sys.argv, os.getcwd()
                old_db = os.environ.get("ZEROFACTORY_DB")
                old_state = os.environ.get("ZEROFACTORY_SCANNER_STATE")
                sys.argv = [gate_path.name, slug]
                os.chdir(str(repo))
                os.environ["ZEROFACTORY_DB"] = str(db_path)
                os.environ["ZEROFACTORY_SCANNER_STATE"] = str(state_path)
                os.environ.pop("ZEROFACTORY_FORCE_SCAN", None)
                os.environ.pop("ZEROFACTORY_IDLE_SCAN", None)
                if extra_env:
                    for k, v in extra_env.items():
                        os.environ[k] = str(v)
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
                    if old_state is None:
                        os.environ.pop("ZEROFACTORY_SCANNER_STATE", None)
                    else:
                        os.environ["ZEROFACTORY_SCANNER_STATE"] = old_state
                    os.environ.pop("ZEROFACTORY_FORCE_SCAN", None)
                    os.environ.pop("ZEROFACTORY_IDLE_SCAN", None)
                    if extra_env:
                        for k in extra_env:
                            os.environ.pop(k, None)
                out = buf.getvalue()
                wake = json.loads(out.strip().splitlines()[-1])
                return rc, wake.get("wakeAgent"), out

            # 1. Baseline scan fires
            rc1, wake1, out1 = run_gate()
            self.assertEqual(rc1, 0)
            self.assertTrue(wake1, "baseline scan must wake agent")

            # 2. Advance time past 15m cooldown, simulate task_created=True on unchanged commit
            st = json.loads(state_path.read_text(encoding="utf-8"))
            st[slug]["last_scan_at"] = int(time.time()) - 1000
            st[slug]["task_created"] = True
            state_path.write_text(json.dumps(st), encoding="utf-8")

            # Capacity-driven idle scan should wake agent because running=0 < 2 and todo=0 < 2
            rc2, wake2, out2 = run_gate()
            self.assertEqual(rc2, 0)
            self.assertTrue(wake2, "capacity-driven idle scan must wake agent on unchanged commit when idle")
            self.assertIn("CAPACITY_DRIVEN_SCAN_TRIGGERED", out2)

            # 3. Running task count at or above threshold (2 >= 2) suppresses
            conn = sqlite3.connect(str(db_path))
            conn.execute("INSERT INTO tasks (id, board_slug, title, status, created_at, updated_at) VALUES ('t1', 'gate-idle-capacity-test', 'Task 1', 'running', 1, 1)")
            conn.execute("INSERT INTO tasks (id, board_slug, title, status, created_at, updated_at) VALUES ('t2', 'gate-idle-capacity-test', 'Task 2', 'running', 1, 1)")
            conn.commit()
            conn.close()

            st = json.loads(state_path.read_text(encoding="utf-8"))
            st[slug]["last_scan_at"] = int(time.time()) - 1000
            state_path.write_text(json.dumps(st), encoding="utf-8")

            rc3, wake3, out3 = run_gate()
            self.assertEqual(rc3, 0)
            self.assertFalse(wake3, "busy pipeline must suppress idle scan")
            self.assertIn("pipeline busy", out3)

            # 4. Dispatcher-invoked scan with ZEROFACTORY_IDLE_SCAN=1 wakes agent
            rc4, wake4, out4 = run_gate(extra_env={"ZEROFACTORY_IDLE_SCAN": "1"})
            self.assertEqual(rc4, 0)
            self.assertTrue(wake4, "dispatcher-authorized idle scan must wake agent")
            self.assertIn("Dispatcher authorized idle scan", out4)

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
            mock_proc.returncode = 0
            res = trigger_builtin_job(job_id)
            self.assertTrue(res.get("ok"))
            self.assertEqual(res.get("pid"), 99999)
            # Real completion feedback: the synchronous wait reports the exit
            # status to the caller (acceptance criteria: success/failure signal).
            self.assertEqual(res.get("returncode"), 0)
            self.assertTrue(res.get("message"))
            call_args = mock_popen.call_args[0][0]
            self.assertIn("-p", call_args)
            self.assertIn("zf-orchestrator", call_args)
            self.assertIn(job_id, call_args)
            # The spawn must not use an un-drained PIPE: stdout is a log file
            # (a real file object) or DEVNULL, and stderr is redirected to it.
            kwargs = mock_popen.call_args[1]
            self.assertNotEqual(kwargs.get("stdout"), subprocess.PIPE,
                                "stdout must not be an un-drained PIPE")
            self.assertNotEqual(kwargs.get("stderr"), subprocess.PIPE,
                                "stderr must not be an un-drained PIPE")
            self.assertIn(kwargs.get("stderr"), (subprocess.STDOUT, subprocess.DEVNULL))
            self.assertIn(kwargs.get("stdin"), (subprocess.DEVNULL, None))
            # The handle must be waited on so the child is reaped (no zombie).
            self.assertTrue(mock_proc.wait.called)

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

    def test_29b_trigger_builtin_job_large_output_no_deadlock(self):
        """Regression: a `hermes cron run` child that writes far more than the
        OS pipe buffer (~64KB) to stdout AND stderr must NOT deadlock the parent
        (the original bug) and the caller must receive a real exit-status signal.

        Runs against a real child process (a fake `hermes` executable that
        writes >64KB to each stream) — so it would genuinely hang/pipe-block
        under the old un-drained-PIPE implementation.
        """
        import os as _os
        import shutil
        import subprocess as _subprocess
        import tempfile
        import time

        import builtin_cron
        from builtin_cron import trigger_builtin_job

        job_id = "zero-factory-task-queue-check"
        fake_dir = tempfile.mkdtemp(prefix="fake_hermes_")
        fake_hermes = str(Path(fake_dir) / "hermes")
        path_was_prepended = False
        try:
            with open(fake_hermes, "w") as f:
                f.write(
                    "#!/bin/sh\n"
                    "# Fake `hermes cron run` child that writes >64KB to stdout\n"
                    "# AND >64KB to stderr — enough to overflow an un-drained pipe.\n"
                    "head -c 204800 /dev/zero | tr '\\0' 'A'\n"
                    "head -c 204800 /dev/zero | tr '\\0' 'B' 1>&2\n"
                    "echo 'BOOM-SENTINEL'\n"
                    "exit 3\n"
                )
            _os.chmod(fake_hermes, 0o755)

            # Ensure our fake `hermes` resolves before any real one on PATH.
            real = shutil.which("hermes")
            if real is None or Path(real).parent.resolve() != Path(fake_dir).resolve():
                _os.environ["PATH"] = fake_dir + _os.pathsep + _os.environ.get("PATH", "")
                path_was_prepended = True

            # Sanity: the fake child really does emit >64KB on each stream.
            env = dict(_os.environ)
            big = _subprocess.run(
                ["hermes", "-p", "zf-orchestrator", "cron", "run", "probe"],
                capture_output=True, text=True, env=env,
            )
            self.assertGreaterEqual(len(big.stdout), 100 * 1024)
            self.assertGreaterEqual(len(big.stderr), 100 * 1024)

            start = time.monotonic()
            res = trigger_builtin_job(job_id)
            elapsed = time.monotonic() - start

            # Must return promptly — no pipe deadlock (old code would hang).
            self.assertLess(elapsed, 120, "trigger_builtin_job appears to have deadlocked")
            # The child has exited and been reaped — not left registered.
            self.assertNotIn(job_id, builtin_cron._active_cron_runs)
            # Real completion feedback: non-zero child exit is reported.
            self.assertFalse(res.get("ok"))
            self.assertEqual(res.get("returncode"), 3)
            self.assertIn("exited with code 3", res.get("message", ""))
            # The large output reached the log (proving it was drained via a
            # file, not an un-drained pipe) and surfaced to the caller.
            self.assertIn("BOOM-SENTINEL", res.get("output_tail", ""))
        finally:
            shutil.rmtree(fake_dir, ignore_errors=True)
            if path_was_prepended:
                # Restore PATH: drop the leading fake dir.
                parts = _os.environ["PATH"].split(_os.pathsep)
                if parts and Path(parts[0]).resolve() == Path(fake_dir).resolve():
                    parts.pop(0)
                _os.environ["PATH"] = _os.pathsep.join(parts)

    def test_29c_trigger_builtin_job_source_has_no_undrained_pipe(self):
        """Source-level guard: trigger_builtin_job must never spawn with an
        un-drained PIPE, must register the Popen handle, and must wait on it.
        (Catches regressions even if the mock-based test above were weakened.)
        """
        import inspect

        import builtin_cron
        src = inspect.getsource(builtin_cron.trigger_builtin_job)

        # No PIPE is used anywhere in the spawn.
        self.assertNotIn("subprocess.PIPE", src,
                         "trigger_builtin_job must not use subprocess.PIPE")
        # The child is drained via a log file / DEVNULL and stderr is merged.
        self.assertIn("stderr=subprocess.STDOUT", src)
        self.assertIn("stdin=subprocess.DEVNULL", src)
        # The handle is registered (reapable) and awaited (reaped, not orphaned).
        self.assertIn("_active_cron_runs[", src)
        self.assertIn("proc.wait(", src)

    def test_29d_reap_active_cron_runs_reaps_finished_children(self):
        """reap_active_cron_runs reaps exited children and returns the count,
        leaving only the still-running ones registered (no zombie accumulation).
        """
        from unittest import mock

        import builtin_cron
        from builtin_cron import reap_active_cron_runs

        def make_proc(retcode):
            p = mock.Mock()
            p.returncode = retcode
            p.poll.return_value = retcode
            return p

        done_a = make_proc(0)
        done_b = make_proc(1)
        still_running = make_proc(None)
        # Point the module registry at a local dict for the duration of the call
        # so the assertions observe the exact post-reap state (no env restore
        # surprises).
        reg = {"job-a": done_a, "job-b": done_b, "job-c": still_running}
        with mock.patch.object(builtin_cron, "_active_cron_runs", reg):
            reaped = reap_active_cron_runs()
        self.assertEqual(reaped, 2)
        self.assertNotIn("job-a", reg)
        self.assertNotIn("job-b", reg)
        self.assertIn("job-c", reg)
        # Finished children were polled (reaped); the running one was left alone.
        done_a.poll.assert_called()
        done_b.poll.assert_called()
        still_running.poll.assert_called()

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
            conn.execute("UPDATE tasks SET status = 'done' WHERE status IN ('running', 'todo')")
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
            os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = "1"

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

            with patch("subprocess.Popen", side_effect=fake_popen), \
                 patch.dict(os.environ, {"ZEROFACTORY_SKIP_WORKER_SPAWN": ""}):
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
                self.assertEqual(t_row["status"], "todo")
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
                self.assertEqual(t_row["status"], "todo")
                self.assertEqual(t_row["assignee"], "zf-builder")
                self.assertIn("[PR Conflict]", t_row["title"])
        finally:
            shutil.rmtree(td, ignore_errors=True)
            if orig_skip_git is not None:
                os.environ["ZEROFACTORY_SKIP_GIT"] = orig_skip_git
            os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = "1"

    def test_32a_non_ff_merge_succeeds_no_false_conflict(self):
        """Regression: pull_and_merge_main() must perform a NON-fast-forward
        merge cleanly (return (True, [], "Successfully merged ...")) and leave a
        real merge commit on the task branch.

        Context (task zf-8fe05f6a): the merge command was built with BOTH
        ``--no-edit`` and ``-m <msg>``. The fix keeps only ``-m <msg>`` (the
        deterministic, documented way to supply a draft merge message) and drops
        ``--no-edit`` so the command does not depend on the version-specific
        interplay between the editor/``--no-edit`` handling and ``-m``. If that
        flag pairing ever misbehaves on a given git, a non-fast-forward merge
        would fail before it runs, leaving the worktree unchanged (no MERGE_HEAD,
        no conflict markers); this function would then misread it as a false
        "not a conflict" error and the dispatcher would misroute a clean
        diverged branch to _handle_local_merge_conflict(), bumping
        conflict_retries and eventually blocking the task.

        NOTE on verification: on this environment's git (2.39.5) the ``--no-edit``
        + ``-m`` combination does NOT abort -- git merges successfully (RC=0) and
        its own documentation describes the pairing as valid. This test therefore
        primarily guards the non-fast-forward merge path (merge actually happens,
        real merge commit exists, main becomes an ancestor, the deterministic
        -m message is used, and the worktree is left clean); on a git version
        that rejects the flag pairing it additionally catches the regression.

        Setup (hermetic, offline, local repo + worktree under a tempdir):
          * base commit on main
          * task worktree branches from base and commits file "task.txt"
          * main then commits a DIFFERENT file "main.txt"
          => the branches genuinely diverge, so a non-fast-forward (3-way)
             merge is required.
        """
        import tempfile
        import shutil
        import subprocess
        from dispatcher import pull_and_merge_main, check_unresolved_conflicts

        orig_skip_git = os.environ.pop("ZEROFACTORY_SKIP_GIT", None)
        td = tempfile.mkdtemp()
        try:
            repo_path = Path(td) / "repo"
            repo_path.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_path), check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo_path), check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_path), check=True)

            # Base commit on main.
            (repo_path / "base.txt").write_text("base\n")
            subprocess.run(["git", "add", "."], cwd=str(repo_path), check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "base"], cwd=str(repo_path), check=True, capture_output=True)

            # Task worktree branching from base; commit a change to a file that
            # main will NOT touch (so the real merge is clean).
            worktree_dir = Path(td) / "wt"
            subprocess.run(
                ["git", "worktree", "add", str(worktree_dir), "-b", "task/nff"],
                cwd=str(repo_path), check=True, capture_output=True,
            )
            (worktree_dir / "task.txt").write_text("task change\n")
            subprocess.run(["git", "add", "."], cwd=str(worktree_dir), check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "task commit"], cwd=str(worktree_dir), check=True, capture_output=True)

            # Advance main with a different file so the branches diverge and a
            # non-fast-forward merge is genuinely required.
            (repo_path / "main.txt").write_text("main change\n")
            subprocess.run(["git", "add", "."], cwd=str(repo_path), check=True, capture_output=True)
            subprocess.run(["git", "commit", "-m", "main commit"], cwd=str(repo_path), check=True, capture_output=True)

            # Sanity: main is NOT yet an ancestor of the task branch HEAD.
            not_ancestor = subprocess.run(
                ["git", "merge-base", "--is-ancestor", "main", "HEAD"],
                cwd=str(worktree_dir), capture_output=True, text=True,
            )
            self.assertNotEqual(not_ancestor.returncode, 0, "test must start from a diverged branch (non-ff)")

            # The fix under test: a clean non-fast-forward merge.
            ok, conflicts, msg = pull_and_merge_main(worktree_dir, repo_path, "main")
            self.assertTrue(ok, f"expected clean merge, got conflicts={conflicts!r} msg={msg!r}")
            self.assertEqual(conflicts, [])
            self.assertIn("Successfully merged", msg)
            # No conflict markers left anywhere in the worktree.
            self.assertEqual(check_unresolved_conflicts(worktree_dir), [])

            # A real merge commit exists on the task branch.
            merges = subprocess.run(
                ["git", "log", "--merges", "--oneline", "-1"],
                cwd=str(worktree_dir), capture_output=True, text=True, check=True,
            )
            self.assertGreater(len(merges.stdout.strip()), 0, "expected a merge commit on the task branch")

            # main is now an ancestor of the task branch HEAD (the merge happened).
            is_ancestor = subprocess.run(
                ["git", "merge-base", "--is-ancestor", "main", "HEAD"],
                cwd=str(worktree_dir), capture_output=True, text=True,
            )
            self.assertEqual(is_ancestor.returncode, 0, "main must be an ancestor after the merge")

            # The deterministic -m message was actually used for the merge commit
            # (guards against silently dropping the commit message).
            subject = subprocess.run(
                ["git", "log", "-1", "--format=%s"],
                cwd=str(worktree_dir), capture_output=True, text=True, check=True,
            ).stdout.strip()
            self.assertIn("into task branch", subject)

            # Worktree is clean after the merge.
            status = subprocess.run(
                ["git", "status", "--porcelain"],
                cwd=str(worktree_dir), capture_output=True, text=True, check=True,
            ).stdout.strip()
            self.assertEqual(status, "")
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
        """Dispatch-level fail-closed: a todo zf-builder task whose worktree
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
                    VALUES ('task-fc-1', 'Build feature Z', 'todo', 'zf-builder', ?, 'task/task-fc-1', 1000, 1000)
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

    def test_32d_dispatcher_auto_stages_clean_conflict_resolution(self):
        """Dispatcher must automatically stage and commit resolved conflicts on handoff.

        When a builder resolves conflict markers in an in-progress merge (UU index
        state) but does not run `git add` (per prompt instructions), the
        dispatcher must detect that all markers are removed, deterministically
        stage the files with `git add .`, verify clean status, and complete the
        merge commit `fix(merge): resolve merge conflicts with main`.
        """
        import shutil
        import sqlite3
        import subprocess
        import tempfile
        from unittest.mock import patch
        from dispatcher import (
            run_dispatch_cycle,
            get_unmerged_status_files,
            check_files_for_conflict_markers,
        )

        orig_skip_git = os.environ.pop("ZEROFACTORY_SKIP_GIT", None)
        td = tempfile.mkdtemp()
        try:
            repo_dir = Path(td) / "repo"
            repo_dir.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_dir), check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Tester"], cwd=str(repo_dir), check=True)
            subprocess.run(["git", "config", "user.email", "tester@test.com"], cwd=str(repo_dir), check=True)

            f = repo_dir / "target.py"
            f.write_text("line_1 = 'base'\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo_dir), check=True, capture_output=True)

            ws_dir = Path(td) / "wt"
            subprocess.run(["git", "worktree", "add", str(ws_dir), "-b", "task/task-cr-1"], cwd=str(repo_dir), check=True, capture_output=True)

            # Commit A on main
            f.write_text("line_1 = 'from_main'\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=str(repo_dir), check=True)
            subprocess.run(["git", "commit", "-m", "main edit"], cwd=str(repo_dir), check=True, capture_output=True)

            # Commit B on task branch in worktree
            wt_f = ws_dir / "target.py"
            wt_f.write_text("line_1 = 'from_branch'\n", encoding="utf-8")
            subprocess.run(["git", "add", "."], cwd=str(ws_dir), check=True)
            subprocess.run(["git", "commit", "-m", "branch edit"], cwd=str(ws_dir), check=True, capture_output=True)

            # Trigger merge conflict in worktree
            merge_res = subprocess.run(["git", "merge", "main"], cwd=str(ws_dir), capture_output=True, text=True)
            self.assertNotEqual(merge_res.returncode, 0)
            self.assertTrue((ws_dir / ".git").is_file() or (repo_dir / ".git" / "worktrees" / "wt" / "MERGE_HEAD").exists())

            # 1. Verify helper detects unmerged UU file
            unmerged = get_unmerged_status_files(ws_dir)
            self.assertEqual(unmerged, ["target.py"])

            # 2. Verify helper detects conflict markers before resolution
            markers = check_files_for_conflict_markers(ws_dir, unmerged)
            self.assertEqual(markers, ["target.py"])

            # 3. Simulate builder resolving markers without running git add
            wt_f.write_text("line_1 = 'reconciled_code'\n", encoding="utf-8")
            # Index is still UU, but file has zero conflict markers
            self.assertEqual(check_files_for_conflict_markers(ws_dir, unmerged), [])

            # 4. Set up database with task in blocked (review-required handoff)
            db_file = Path(td) / "zf.db"
            orig_db = os.environ.get("ZEROFACTORY_DB")
            os.environ["ZEROFACTORY_DB"] = str(db_file)
            init_db(force=True)
            with sqlite3.connect(str(db_file)) as conn:
                conn.execute("""
                    INSERT INTO tasks (id, title, status, assignee, workspace_path, branch_name, pr_url, metadata, created_at, updated_at)
                    VALUES ('task-cr-1', 'Bug: merge conflict task [PR Conflict]', 'blocked', 'zf-builder', ?, 'task/task-cr-1', 'https://github.com/example/pr/1', '{}', 1000, 1000)
                """, (str(ws_dir),))
                conn.commit()

            # 5. Run dispatch cycle. It should auto-stage, commit the merge, and hand off to reviewer.
            orig_run = subprocess.run
            def safe_run(cmd, *args, **kwargs):
                if isinstance(cmd, list) and len(cmd) >= 2 and cmd[0] == "git" and cmd[1] == "push":
                    return subprocess.CompletedProcess(cmd, 0, stdout="", stderr="")
                if isinstance(cmd, list) and len(cmd) >= 2 and cmd[0] == "gh" and cmd[1] == "pr":
                    fake_pr = json.dumps({"reviewDecision": None, "state": "OPEN", "url": "https://github.com/example/pr/1", "mergeable": "UNKNOWN"})
                    return subprocess.CompletedProcess(cmd, 0, stdout=fake_pr, stderr="")
                return orig_run(cmd, *args, **kwargs)

            with patch("dispatcher.reap_active_workers", return_value=0), \
                 patch("dispatcher.resolve_task_repo_path", return_value=repo_dir), \
                 patch("dispatcher.pull_and_merge_main", return_value=(True, [], "ok")), \
                 patch("dispatcher.subprocess.run", side_effect=safe_run):
                res = run_dispatch_cycle(db_file)
                self.assertTrue(res.get("ok"))

            # 6. Verify worktree was committed and merge commit exists on branch
            log_res = subprocess.run(["git", "log", "-1", "--format=%s", "task/task-cr-1"], cwd=str(repo_dir), capture_output=True, text=True, check=True)
            self.assertEqual(log_res.stdout.strip(), "fix(merge): resolve merge conflicts with main")

            # 7. Verify task was transitioned to zf-reviewer
            with sqlite3.connect(str(db_file)) as conn:
                conn.row_factory = sqlite3.Row
                row = conn.execute("SELECT status, assignee FROM tasks WHERE id = 'task-cr-1'").fetchone()
                self.assertEqual(row["assignee"], "zf-reviewer")
        finally:
            shutil.rmtree(td, ignore_errors=True)
            if orig_skip_git is not None:
                os.environ["ZEROFACTORY_SKIP_GIT"] = orig_skip_git
            else:
                os.environ.pop("ZEROFACTORY_SKIP_GIT", None)
            if orig_db is not None:
                os.environ["ZEROFACTORY_DB"] = orig_db
            else:
                os.environ.pop("ZEROFACTORY_DB", None)

    def test_33_worktree_symlink_guardrail_and_resolution(self):
        """Verify that get_plugin_root() resolves main repo from inside worktrees and ensure_plugin_symlinks cleans up worktree symlinks."""
        from profile_manager import get_plugin_root, ensure_plugin_symlinks
        import shutil
        import subprocess
        import tempfile
        from unittest.mock import patch

        # Resolve the canonical (main) repo root via git so the ground-truth
        # holds both when the suite runs from the main repo AND from an
        # isolated git worktree (where Path(__file__) lives in the worktree,
        # not the main repo). `--git-common-dir` returns the main repo's .git
        # directory in either case.
        test_dir = Path(__file__).resolve().parent

        def _canonical_repo() -> Path:
            try:
                res = subprocess.run(
                    ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                    cwd=str(test_dir),
                    capture_output=True,
                    text=True,
                    timeout=5,
                )
                if res.returncode == 0:
                    common_git = Path(res.stdout.strip()).resolve()
                    if (common_git.parent / "plugin.yaml").exists():
                        return common_git.parent
            except Exception:
                pass
            return test_dir

        canonical_repo = _canonical_repo()

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

    # -- test_89: worker termination signals the whole process group --------
    # All spawn sites use start_new_session=True (new session, PGID == child
    # PID). Signalling only the direct hermes child left the descendant tree
    # (agent loop, git, npm, network) orphaned. These tests pin the group
    # termination contract.

    def test_89a_terminate_worker_process_signals_process_group(self):
        """Group path: os.killpg SIGTERM then SIGKILL (pgid == child PID);
        child-only proc.terminate()/proc.kill() must NOT be used."""
        import signal as signal_mod
        import subprocess as subprocess_mod
        from unittest.mock import MagicMock, patch
        from dispatcher import terminate_worker_process

        mock_proc = MagicMock()
        mock_proc.pid = 12345
        # Simulate the child ignoring SIGTERM: the grace wait expires.
        mock_proc.wait.side_effect = subprocess_mod.TimeoutExpired(cmd="hermes", timeout=2.0)

        with patch("dispatcher.os.getpgid", return_value=12345) as mock_getpgid, \
             patch("dispatcher.os.killpg") as mock_killpg:
            terminate_worker_process(mock_proc, 12345)

        mock_getpgid.assert_called_once_with(12345)
        # Probe (signal 0), SIGTERM, SIGKILL — all against the GROUP.
        signals = [c.args for c in mock_killpg.call_args_list]
        self.assertIn((12345, 0), signals)
        self.assertIn((12345, signal_mod.SIGTERM), signals)
        self.assertIn((12345, signal_mod.SIGKILL), signals)
        self.assertEqual(signals[0], (12345, 0))  # liveness probe first
        self.assertEqual(signals[1], (12345, signal_mod.SIGTERM))
        self.assertEqual(signals[-1], (12345, signal_mod.SIGKILL))
        # Child-only signalling must NOT happen on the group path.
        mock_proc.terminate.assert_not_called()
        mock_proc.kill.assert_not_called()

    def test_89b_terminate_worker_process_pid_only_uses_killpg(self):
        """PID-only fallback (metadata path, no live handle): killpg via
        pgid == child PID since start_new_session=True guarantees it."""
        import signal as signal_mod
        import subprocess as subprocess_mod
        from unittest.mock import patch
        from dispatcher import terminate_worker_process

        with patch("dispatcher.os.killpg", side_effect=lambda g, s: None) as mock_killpg, \
             patch("dispatcher.time.sleep"):
            terminate_worker_process(None, 4321)

        signals = [c.args for c in mock_killpg.call_args_list]
        self.assertEqual(signals, [(4321, 0), (4321, signal_mod.SIGTERM), (4321, signal_mod.SIGKILL)])

    def test_89c_terminate_worker_process_dead_group_swallows_error(self):
        """killpg of a dead/unknown group raises ProcessLookupError -> the
        helper swallows it (fail-open), logs, and never raises."""
        from unittest.mock import MagicMock, patch
        from dispatcher import terminate_worker_process

        mock_proc = MagicMock()
        mock_proc.pid = 999
        with patch("dispatcher.os.getpgid", return_value=999), \
             patch("dispatcher.os.killpg", side_effect=ProcessLookupError(3, "No such process")):
            terminate_worker_process(mock_proc, 999)  # must not raise
        mock_proc.terminate.assert_not_called()
        mock_proc.kill.assert_not_called()

        # Same for the PID-only fallback path.
        with patch("dispatcher.os.killpg", side_effect=ProcessLookupError(3, "No such process")):
            terminate_worker_process(None, 999)  # must not raise

    def test_89d_stop_task_worker_reaps_descendants_integration(self):
        """Integration (real processes, Linux): a worker spawned in its own
        session with a live descendant is fully reaped by
        stop_task_worker — no orphaned processes survive.

        The worker is ``sh -c 'sleep 300 & sleep 300'`` in a new session: the
        sh process is the group leader and the backgrounded sleep is a
        descendant in the SAME group (the exact shape of a hermes wrapper +
        its agent loop). The old child-only SIGTERM/SIGKILL would have left
        the descendant group member orphaned.
        """
        import os as os_mod
        import subprocess
        import time
        from dispatcher import stop_task_worker, _active_workers

        if not hasattr(os_mod, "killpg"):
            self.skipTest("os.killpg unavailable (non-POSIX platform)")

        worker = None
        pgid = None
        try:
            worker = subprocess.Popen(
                ["sh", "-c", "sleep 300 & sleep 300"],
                start_new_session=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            time.sleep(0.4)
            worker_pid = worker.pid
            pgid = os_mod.getpgid(worker_pid)
            self.assertEqual(pgid, worker_pid, "worker must lead its own session")

            # Confirm a descendant really exists in the group before we stop
            # it (the backgrounded sleep), so the test guards the actual
            # orphan scenario.
            descendant = False
            for entry in os_mod.listdir("/proc"):
                if not entry.isdigit():
                    continue
                try:
                    with open(f"/proc/{entry}/stat") as st:
                        raw = st.read()
                    # comm is wrapped in parentheses and may contain spaces;
                    # anchor on the LAST ')' so the numeric fields align:
                    # rest = [state, ppid, pgrp, session, ...]
                    rest = raw[raw.rindex(")") + 1:].split()
                    if int(rest[2]) == pgid and int(entry) != worker_pid:
                        descendant = True
                except (OSError, ValueError):
                    continue
            self.assertTrue(descendant, "setup: expected a descendant inside the worker group")

            _active_workers["task-89d"] = worker
            try:
                stop_task_worker("task-89d")
                # The WHOLE group (leader + descendant) must be gone after the
                # grace window + SIGKILL.
                deadline = time.monotonic() + 15.0
                group_alive = True
                while time.monotonic() < deadline:
                    try:
                        os_mod.killpg(pgid, 0)
                        time.sleep(0.1)
                    except ProcessLookupError:
                        group_alive = False
                        break
                self.assertFalse(group_alive, "worker process group survived stop_task_worker")
            finally:
                _active_workers.pop("task-89d", None)
        finally:
            # Best-effort sweep of the whole group in case of partial teardown.
            if pgid is not None:
                try:
                    os_mod.killpg(pgid, 9)
                except OSError:
                    pass
            if worker is not None:
                try:
                    worker.wait(timeout=5)
                except Exception:
                    pass

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
                self.assertEqual(row["status"], "todo")

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
                self.assertEqual(row2["status"], "todo")
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

    def test_35c_stale_git_lock_cleanup_and_conclude_merge(self):
        """Verify that clean_stale_git_locks removes stale index.lock files and that
        pull_and_merge_main automatically concludes an in-progress merge when conflict
        markers are already resolved."""
        from dispatcher import clean_stale_git_locks, get_git_dir, pull_and_merge_main
        import subprocess
        import time

        td = tempfile.mkdtemp()
        try:
            repo = Path(td) / "main_repo"
            repo.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=str(repo), check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test"], cwd=str(repo), check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True)
            (repo / "f.txt").write_text("v1\n")
            subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
            subprocess.run(["git", "commit", "-m", "init"], cwd=str(repo), check=True)

            wt_dir = Path(td) / "wt"
            subprocess.run(["git", "worktree", "add", str(wt_dir), "-b", "task/t1"], cwd=str(repo), check=True)

            # 1. Stale lock cleanup test
            git_dir = get_git_dir(wt_dir)
            self.assertIsNotNone(git_dir)
            stale_lock = git_dir / "index.lock"
            stale_lock.write_text("")
            old_time = time.time() - 60
            os.utime(str(stale_lock), (old_time, old_time))

            removed = clean_stale_git_locks(wt_dir, max_age_seconds=15)
            self.assertEqual(len(removed), 1)
            self.assertFalse(stale_lock.exists())

            # Fresh lock (< 15s) should NOT be removed
            fresh_lock = git_dir / "index.lock"
            fresh_lock.write_text("")
            removed_fresh = clean_stale_git_locks(wt_dir, max_age_seconds=15)
            self.assertEqual(len(removed_fresh), 0)
            self.assertTrue(fresh_lock.exists())
            fresh_lock.unlink()

            # 2. Conclude in-progress merge test
            # Advance main
            (repo / "f.txt").write_text("v2\n")
            subprocess.run(["git", "commit", "-am", "v2 on main"], cwd=str(repo), check=True)

            # In worktree, edit f.txt to v3 and commit
            (wt_dir / "f.txt").write_text("v3\n")
            subprocess.run(["git", "commit", "-am", "v3 on branch"], cwd=str(wt_dir), check=True)

            # Merge main into worktree -> encounters conflict
            subprocess.run(["git", "merge", "main"], cwd=str(wt_dir), capture_output=True)
            self.assertTrue((git_dir / "MERGE_HEAD").exists())

            # Resolve conflict in f.txt and stage it
            (wt_dir / "f.txt").write_text("v2+v3 resolved\n")
            subprocess.run(["git", "add", "."], cwd=str(wt_dir), check=True)
            self.assertTrue((git_dir / "MERGE_HEAD").exists())

            # Now pull_and_merge_main should conclude the merge rather than failing with "MERGE_HEAD exists"
            ok, conflicts, msg = pull_and_merge_main(wt_dir, repo, "main")
            self.assertTrue(ok)
            self.assertEqual(conflicts, [])
            self.assertFalse((git_dir / "MERGE_HEAD").exists())
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_35d_merge_conflict_retry_limit_blocks_infinite_loop(self):
        """Verify that _handle_local_merge_conflict limits retries to MAX_CONFLICT_RETRIES
        and moves the task to 'blocked' status, preventing infinite dispatch loops."""
        from dispatcher import _handle_local_merge_conflict
        import json
        import sqlite3
        import time

        td = tempfile.mkdtemp()
        try:
            db_file = Path(td) / "conflict_retry.db"
            self._create_conflict_test_db(db_file)
            ws_dir = Path(td) / "ws"
            ws_dir.mkdir()

            with sqlite3.connect(str(db_file)) as conn:
                conn.execute("""
                    INSERT INTO tasks (id, title, status, assignee, workspace_path, branch_name, created_at, updated_at)
                    VALUES ('task-retry', 'Feature X', 'running', 'zf-builder', ?, 'task/task-retry', 1000, 1000)
                """, (str(ws_dir),))
                conn.commit()

            now = int(time.time())
            with sqlite3.connect(str(db_file)) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()

                # Calls 1, 2, 3 should keep status 'todo' and increment retries
                for i in range(1, 4):
                    _handle_local_merge_conflict(cur, "task-retry", "Feature X", str(ws_dir), ["conflict.txt"], now, "conflict")
                    conn.commit()
                    row = cur.execute("SELECT status, metadata FROM tasks WHERE id = 'task-retry'").fetchone()
                    self.assertEqual(row["status"], "todo")
                    meta = json.loads(row["metadata"] or "{}")
                    self.assertEqual(meta.get("conflict_retries"), i)

                # Call 4 should exceed max_retries (3) and move to 'blocked'
                _handle_local_merge_conflict(cur, "task-retry", "Feature X", str(ws_dir), ["conflict.txt"], now, "conflict")
                conn.commit()
                row = cur.execute("SELECT status, metadata FROM tasks WHERE id = 'task-retry'").fetchone()
                self.assertEqual(row["status"], "blocked")
                meta = json.loads(row["metadata"] or "{}")
                self.assertEqual(meta.get("conflict_retries"), 4)

                # Verify failure activity and comment
                act = cur.execute("SELECT action, details FROM task_activity WHERE task_id = 'task-retry' AND action = 'pr_conflict_failed'").fetchone()
                self.assertIsNotNone(act)
                self.assertIn("exceeded 3 attempts", act["details"])

                cmt = cur.execute("SELECT body FROM task_comments WHERE task_id = 'task-retry' ORDER BY id DESC LIMIT 1").fetchone()
                self.assertIsNotNone(cmt)
                self.assertIn("Merge Conflict Resolution Failed", cmt["body"])

                # Call 5 (subsequent call after exceeding limit) must be a no-op
                _handle_local_merge_conflict(cur, "task-retry", "Feature X", str(ws_dir), ["conflict.txt"], now, "conflict")
                conn.commit()
                row = cur.execute("SELECT status, metadata FROM tasks WHERE id = 'task-retry'").fetchone()
                self.assertEqual(row["status"], "blocked")
                meta = json.loads(row["metadata"] or "{}")
                self.assertEqual(meta.get("conflict_retries"), 4)
                act_count = cur.execute("SELECT count(*) FROM task_activity WHERE task_id = 'task-retry' AND action = 'pr_conflict_failed'").fetchone()[0]
                self.assertEqual(act_count, 1)
                cmt_count = cur.execute("SELECT count(*) FROM task_comments WHERE task_id = 'task-retry'").fetchone()[0]
                self.assertEqual(cmt_count, 4)
                failed_cmt_count = cur.execute("SELECT count(*) FROM task_comments WHERE task_id = 'task-retry' AND body LIKE '%Resolution Failed%'").fetchone()[0]
                self.assertEqual(failed_cmt_count, 1)
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_36_github_conflicting_pr_routes_to_builder(self):
        """Unit-test the GitHub-CONFLICTING branch: a reviewer task whose PR is
        mergeable == 'CONFLICTING' is re-routed to the author with [PR Conflict] tag,
        status 'todo', and pr_conflict activity + comment rows."""
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
                self.assertEqual(row["status"], "todo")
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

    def test_36b_github_conflicting_pr_suppresses_flooding_when_blocked(self):
        """Verify that a task that is already blocked and exceeded conflict retries
        does NOT flood comments, activity, or increment retries when gh reports CONFLICTING."""
        from dispatcher import run_dispatch_cycle
        import json
        import shutil
        import sqlite3
        import subprocess
        from unittest.mock import patch, MagicMock

        orig_skip_git = os.environ.pop("ZEROFACTORY_SKIP_GIT", None)
        td = tempfile.mkdtemp()
        try:
            repo_path = Path(td) / "test_repo"
            repo_path.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_path), check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo_path), check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_path), check=True)
            (repo_path / "README.md").write_text("# Test Repo\n")
            subprocess.run(["git", "add", "."], cwd=str(repo_path), check=True)
            subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_path), check=True, capture_output=True)

            db_file = Path(td) / "conflict_gh_flood.db"
            self._create_conflict_test_db(db_file)

            with sqlite3.connect(str(db_file)) as conn:
                conn.execute("""
                    INSERT INTO tasks (id, title, status, assignee, workspace_path, branch_name, pr_url, metadata, created_at, updated_at)
                    VALUES ('task-blocked-conflict', 'Fix bug [PR Opened by zf-builder] [PR Conflict]', 'blocked', 'zf-builder', NULL, 'task/task-blocked-conflict',
                            'https://github.com/hotcode-dev/zerofactory/pull/123', '{"conflict_retries": 4}', 1000, 1000)
                """)
                conn.commit()

            orig_run = subprocess.run
            def fake_run(cmd, *args, **kwargs):
                if len(cmd) >= 3 and cmd[0] == "gh" and cmd[1] == "pr" and cmd[2] == "view":
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

            with patch("dispatcher.setup_worktree") as mock_setup_wt, \
                 patch("subprocess.run", side_effect=fake_run):
                res = run_dispatch_cycle(db_file)

            self.assertTrue(res.get("ok"))
            mock_setup_wt.assert_not_called()

            with sqlite3.connect(str(db_file)) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                row = cur.execute("SELECT status, metadata FROM tasks WHERE id = 'task-blocked-conflict'").fetchone()
                self.assertEqual(row["status"], "blocked")
                meta = json.loads(row["metadata"] or "{}")
                self.assertEqual(meta.get("conflict_retries"), 4)

                acts = cur.execute("SELECT count(*) FROM task_activity WHERE task_id = 'task-blocked-conflict'").fetchone()[0]
                self.assertEqual(acts, 0)
                cmts = cur.execute("SELECT count(*) FROM task_comments WHERE task_id = 'task-blocked-conflict'").fetchone()[0]
                self.assertEqual(cmts, 0)
        finally:
            shutil.rmtree(td, ignore_errors=True)
            if orig_skip_git is not None:
                os.environ["ZEROFACTORY_SKIP_GIT"] = orig_skip_git

    def test_36c_author_handoff_with_existing_pr_url(self):
        """Verify that when an author resolves conflicts on an existing PR, the dispatcher
        commits and pushes changes instead of bypassing handoff."""
        from dispatcher import run_dispatch_cycle
        import json
        import shutil
        import sqlite3
        import subprocess
        from unittest.mock import patch, MagicMock

        orig_skip_git = os.environ.pop("ZEROFACTORY_SKIP_GIT", None)
        td = tempfile.mkdtemp()
        try:
            repo_path = Path(td) / "test_repo"
            repo_path.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_path), check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo_path), check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_path), check=True)
            (repo_path / "README.md").write_text("# Test Repo\n")
            subprocess.run(["git", "add", "."], cwd=str(repo_path), check=True)
            subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_path), check=True, capture_output=True)

            ws_dir = Path(td) / "ws_author"
            subprocess.run(
                ["git", "worktree", "add", str(ws_dir), "-b", "task/author-handoff"],
                cwd=str(repo_path), check=True, capture_output=True
            )
            # Author makes a fix
            (ws_dir / "fix.txt").write_text("fixed conflict\n")

            db_file = Path(td) / "author_handoff.db"
            self._create_conflict_test_db(db_file)

            with sqlite3.connect(str(db_file)) as conn:
                conn.execute("""
                    INSERT INTO tasks (id, title, status, assignee, workspace_path, branch_name, pr_url, created_at, updated_at)
                    VALUES ('task-author-handoff', 'Fix PR conflict [PR Opened by zf-builder]', 'blocked', 'zf-builder', ?, 'task/author-handoff',
                            'https://github.com/hotcode-dev/zerofactory/pull/999', 1000, 1000)
                """, (str(ws_dir),))
                conn.commit()

            orig_run = subprocess.run
            pushed_calls = []

            def fake_run(cmd, *args, **kwargs):
                if isinstance(cmd, list) and len(cmd) >= 2 and cmd[0] == "git" and cmd[1] == "push":
                    pushed_calls.append(cmd)
                    res = MagicMock()
                    res.returncode = 0
                    res.stdout = ""
                    return res
                return orig_run(cmd, *args, **kwargs)

            with patch("subprocess.run", side_effect=fake_run):
                res = run_dispatch_cycle(db_file)

            self.assertTrue(res.get("ok"))
            self.assertGreaterEqual(len(pushed_calls), 1)

            with sqlite3.connect(str(db_file)) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                row = cur.execute("SELECT status, assignee FROM tasks WHERE id = 'task-author-handoff'").fetchone()
                self.assertEqual(row["status"], "todo")
                self.assertEqual(row["assignee"], "zf-reviewer")
        finally:
            shutil.rmtree(td, ignore_errors=True)
            if orig_skip_git is not None:
                os.environ["ZEROFACTORY_SKIP_GIT"] = orig_skip_git

    def test_36d_author_handoff_with_done_status_and_existing_pr_url(self):
        """Verify that when an author marks work done on an existing PR, the dispatcher
        commits, pushes, and routes to zf-reviewer instead of skipping."""
        from dispatcher import run_dispatch_cycle
        import json
        import shutil
        import sqlite3
        import subprocess
        from unittest.mock import patch, MagicMock

        orig_skip_git = os.environ.pop("ZEROFACTORY_SKIP_GIT", None)
        td = tempfile.mkdtemp()
        try:
            repo_path = Path(td) / "test_repo"
            repo_path.mkdir()
            subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_path), check=True, capture_output=True)
            subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo_path), check=True)
            subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_path), check=True)
            (repo_path / "README.md").write_text("# Test Repo\n")
            subprocess.run(["git", "add", "."], cwd=str(repo_path), check=True)
            subprocess.run(["git", "commit", "-m", "Initial commit"], cwd=str(repo_path), check=True, capture_output=True)

            ws_dir = Path(td) / "ws_author"
            subprocess.run(
                ["git", "worktree", "add", str(ws_dir), "-b", "task/author-handoff-done"],
                cwd=str(repo_path), check=True, capture_output=True
            )
            (ws_dir / "fix2.txt").write_text("fixed review feedback\n")

            db_file = Path(td) / "author_handoff_done.db"
            self._create_conflict_test_db(db_file)

            with sqlite3.connect(str(db_file)) as conn:
                conn.execute("""
                    INSERT INTO tasks (id, title, status, assignee, workspace_path, branch_name, pr_url, created_at, updated_at)
                    VALUES ('task-author-done', 'Fix review feedback [PR Opened by zf-builder]', 'done', 'zf-builder', ?, 'task/author-handoff-done',
                            'https://github.com/hotcode-dev/zerofactory/pull/999', 1000, 1000)
                """, (str(ws_dir),))
                conn.commit()

            orig_run = subprocess.run
            pushed_calls = []

            def fake_run(cmd, *args, **kwargs):
                if isinstance(cmd, list) and len(cmd) >= 2 and cmd[0] == "git" and cmd[1] == "push":
                    pushed_calls.append(cmd)
                    res = MagicMock()
                    res.returncode = 0
                    res.stdout = ""
                    return res
                return orig_run(cmd, *args, **kwargs)

            with patch("subprocess.run", side_effect=fake_run):
                res = run_dispatch_cycle(db_file)

            self.assertTrue(res.get("ok"))
            self.assertGreaterEqual(len(pushed_calls), 1)

            with sqlite3.connect(str(db_file)) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                row = cur.execute("SELECT status, assignee FROM tasks WHERE id = 'task-author-done'").fetchone()
                self.assertEqual(row["status"], "todo")
                self.assertEqual(row["assignee"], "zf-reviewer")
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
                    VALUES ('task-pre-1', 'Build feature X', 'todo', 'zf-builder', ?, 'task/task-pre-1', 1000, 1000)
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
                    VALUES ('task-pre-conflict', 'Implement feature Y', 'todo', 'zf-builder', ?, 'task/task-pre-conflict', 1000, 1000)
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
                self.assertEqual(row_c["status"], "todo")
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
                    VALUES ('task-pre-rev', 'Review PR 123', 'todo', 'zf-reviewer', ?, 'task/task-pre-rev', 1000, 1000)
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
                        "VALUES (?, ?, 'todo', ?, 1000, 1000)",
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
            "status": "todo",
            "reason": "unblocked",
        })
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(resp.json()["status"], "todo")
        self.assertEqual(get_task(t_id)["task"]["status"], "todo")

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
            with patch.dict(os.environ, {"HERMES_KANBAN_TASK": "parent-task-id", "ZEROFACTORY_SKIP_WORKER_SPAWN": ""}, clear=False):
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
        board's max_concurrent_running (default 1). With cap 1 and three todo
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
                    "INSERT INTO tasks (id, board_slug, title, status, assignee, priority, workspace_path, created_at, updated_at) VALUES (?, 'b1', ?, 'todo', 'zf-builder', 'P2', ?, 1000, 1000)",
                    (f"mcr-{i}", f"Task {i}", str(ws)),
                )
            conn.commit()
            conn.close()

            # Cycle 1: cap 1 -> exactly one running, two still todo
            res = run_dispatch_cycle(db_file)
            self.assertTrue(res["ok"], f"dispatch cycle should succeed: {res}")
            conn = sqlite3.connect(str(db_file))
            conn.row_factory = sqlite3.Row
            running = conn.execute("SELECT id FROM tasks WHERE status = 'running'").fetchall()
            todo = conn.execute("SELECT id FROM tasks WHERE status = 'todo'").fetchall()
            conn.close()
            self.assertEqual(len(running), 1, f"expected exactly 1 running under cap 1, got {len(running)}")
            self.assertEqual(len(todo), 2, f"expected 2 todo to remain, got {len(todo)}")

            # Raise the board cap to 2, run again -> a second task starts
            conn = sqlite3.connect(str(db_file))
            conn.execute("UPDATE boards SET max_concurrent_running = 2 WHERE slug = 'b1'")
            conn.commit()
            conn.close()
            res2 = run_dispatch_cycle(db_file)
            self.assertTrue(res2["ok"], f"second dispatch cycle should succeed: {res2}")
            conn = sqlite3.connect(str(db_file))
            running2 = conn.execute("SELECT id FROM tasks WHERE status = 'running'").fetchall()
            todo2 = conn.execute("SELECT id FROM tasks WHERE status = 'todo'").fetchall()
            conn.close()
            self.assertEqual(len(running2), 2, f"expected 2 running under cap 2, got {len(running2)}")
            self.assertEqual(len(todo2), 1, f"expected 1 todo to remain, got {len(todo2)}")
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
        self.assertIn("max_concurrent_llm_workers", data["settings"])
        self.assertNotIn("default_max_concurrent_workers", data["settings"])
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
                "max_concurrent_llm_workers": 3,
                "scan_on_idle": False,
                "idle_scan_active_threshold": 1,
                "idle_scan_cooldown_minutes": 30,
                "idle_scan_max_todo": 3,
            }
        )
        self.assertEqual(res_patch.status_code, 200)
        settings = res_patch.json()["settings"]
        self.assertEqual(settings["max_active_tasks"], 12)
        self.assertEqual(settings["max_concurrent_llm_workers"], 3)
        self.assertFalse(settings["scan_on_idle"])
        self.assertEqual(settings["idle_scan_active_threshold"], 1)
        self.assertEqual(settings["idle_scan_cooldown_minutes"], 30)
        self.assertEqual(settings["idle_scan_max_todo"], 3)

        # Verify GET returns updated values
        res_after = client.get("/api/plugins/zerofactory/settings")
        self.assertEqual(res_after.json()["settings"]["max_active_tasks"], 12)
        self.assertEqual(res_after.json()["settings"]["max_concurrent_llm_workers"], 3)
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

        self.assertEqual(client.patch(
            "/api/plugins/zerofactory/settings",
            json={"max_concurrent_llm_workers": 0}
        ).status_code, 422)

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
                "max_concurrent_llm_workers": 10,
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
        import time
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
            now = int(time.time())
            # Create 5 tasks in 'todo'
            for i in range(1, 6):
                conn.execute(
                    "INSERT INTO tasks (id, board_slug, title, status, assignee, priority, workspace_path, created_at, updated_at) VALUES (?, 'b1', ?, 'todo', 'unassigned', 'P2', ?, ?, ?)",
                    (f"task-{i}", f"Task {i}", str(ws), now, now),
                )
            conn.commit()
            conn.close()

            # Cycle 1: with max_active_tasks = 2, only 2 tasks should be promoted from todo to running
            res = run_dispatch_cycle(db_file)
            self.assertTrue(res["ok"])
            conn = sqlite3.connect(str(db_file))
            todo_count = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'todo'").fetchone()[0]
            active_count = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'running'").fetchone()[0]
            conn.close()
            self.assertEqual(active_count, 2, f"expected exactly 2 active tasks promoted, got {active_count}")
            self.assertEqual(todo_count, 3, f"expected 3 tasks to remain in todo, got {todo_count}")

            # Raise max_active_tasks to 4 in settings
            conn = sqlite3.connect(str(db_file))
            conn.execute("UPDATE settings SET value = '4' WHERE key = 'max_active_tasks'")
            conn.commit()
            conn.close()

            # Cycle 2: 2 more tasks should be dispatched from todo
            res2 = run_dispatch_cycle(db_file)
            self.assertTrue(res2["ok"])
            conn = sqlite3.connect(str(db_file))
            active_count2 = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'running'").fetchone()[0]
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

    def test_48b_wip_budget_does_not_starve_other_boards(self):
        """The global WIP budget must not truncate the todo candidate set
        before the per-board cap check runs (regression from the ready-removal
        refactor). With max_active_tasks=2, two empty boards of cap 1, and 4
        todo tasks on b1 (older) + 2 on b2 (newer): the old `LIMIT 2` SELECT
        returned only b1's rows, so one b1 task dispatched, the second was
        rejected by b1's per-board cap, and b2 never entered the candidate
        set — a WIP slot left unused while b2 starves. The fixed dispatch
        fetches the full candidate set and enforces the global budget in the
        loop, so both boards get a worker and the budget (2) is still capped."""
        import tempfile
        import shutil
        import sqlite3
        import time
        from dispatcher import run_dispatch_cycle

        orig_skip_git = os.environ.get("ZEROFACTORY_SKIP_GIT")
        orig_skip_spawn = os.environ.get("ZEROFACTORY_SKIP_WORKER_SPAWN")
        os.environ["ZEROFACTORY_SKIP_GIT"] = "1"
        os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = "1"
        td = tempfile.mkdtemp(prefix="zf-wip-starve-")
        ws = Path(td) / "ws"
        ws.mkdir()
        db_file = Path(td) / "wip_starve.db"
        try:
            conn = sqlite3.connect(str(db_file))
            conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at INTEGER NOT NULL)")
            conn.execute("CREATE TABLE boards (slug TEXT PRIMARY KEY, description TEXT DEFAULT '', git_url TEXT DEFAULT '', max_concurrent_running INTEGER NOT NULL DEFAULT 1, created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)")
            conn.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, board_slug TEXT NOT NULL DEFAULT '', title TEXT NOT NULL, description TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'triage', assignee TEXT NOT NULL DEFAULT 'unassigned', priority TEXT NOT NULL DEFAULT 'P2', workspace_path TEXT, branch_name TEXT, metadata TEXT DEFAULT '{}', tenant TEXT DEFAULT '', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)")
            conn.execute("CREATE TABLE task_activity (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, actor TEXT, action TEXT, details TEXT DEFAULT '', created_at INTEGER NOT NULL)")
            conn.execute("CREATE TABLE task_comments (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, author TEXT, body TEXT, created_at INTEGER NOT NULL)")
            conn.execute("CREATE TABLE task_links (id INTEGER PRIMARY KEY, parent_id TEXT, child_id TEXT, link_type TEXT)")
            conn.execute("INSERT INTO settings (key, value, updated_at) VALUES ('max_active_tasks', '2', 1)")
            conn.execute("INSERT INTO settings (key, value, updated_at) VALUES ('scan_on_idle', 'false', 1)")
            # Both boards at the default per-board cap of 1.
            conn.execute("INSERT INTO boards (slug, max_concurrent_running, created_at, updated_at) VALUES ('b1', 1, 1, 1)")
            conn.execute("INSERT INTO boards (slug, max_concurrent_running, created_at, updated_at) VALUES ('b2', 1, 1, 1)")
            now = int(time.time())
            # b1 holds the OLDER backlog (4 tasks) and would exhaust the
            # WIP-sized LIMIT first; b2's tasks are newer.
            for i in range(1, 5):
                conn.execute(
                    "INSERT INTO tasks (id, board_slug, title, status, assignee, priority, workspace_path, created_at, updated_at) VALUES (?, 'b1', ?, 'todo', 'zf-builder', 'P2', ?, ?, ?)",
                    (f"b1-{i}", f"B1 task {i}", str(ws), now + i, now + i),
                )
            for i in range(1, 3):
                conn.execute(
                    "INSERT INTO tasks (id, board_slug, title, status, assignee, priority, workspace_path, created_at, updated_at) VALUES (?, 'b2', ?, 'todo', 'zf-builder', 'P2', ?, ?, ?)",
                    (f"b2-{i}", f"B2 task {i}", str(ws), now + 10 + i, now + 10 + i),
                )
            conn.commit()
            conn.close()

            res = run_dispatch_cycle(db_file)
            self.assertTrue(res["ok"], f"dispatch cycle should succeed: {res}")
            self.assertEqual(res["dispatched"], 2, f"global WIP budget 2 must be used fully: {res}")

            conn = sqlite3.connect(str(db_file))
            conn.row_factory = sqlite3.Row
            by_board = {r["board_slug"]: r["cnt"] for r in conn.execute(
                "SELECT board_slug, COUNT(*) AS cnt FROM tasks WHERE status = 'running' GROUP BY board_slug"
            ).fetchall()}
            todo_count = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'todo'").fetchone()[0]
            total_running = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'running'").fetchone()[0]
            conn.close()

            self.assertEqual(by_board.get("b1", 0), 1, "b1 should run exactly one task under its cap 1")
            self.assertEqual(by_board.get("b2", 0), 1, "b2 must NOT be starved: a free WIP slot must flow to it")
            self.assertEqual(total_running, 2, "global WIP budget (max_active_tasks=2) must still be enforced")
            self.assertEqual(todo_count, 4, "the remaining 4 tasks stay in todo for the next cycle")
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

    def test_48c_global_llm_capacity_counts_tasks_and_scans(self):
        """Across boards, tasks and in-flight scanners share one worker budget."""
        import sqlite3
        import tempfile
        from unittest.mock import MagicMock, patch
        from dispatcher import run_dispatch_cycle, reset_idle_scanner_state, _active_scanners

        with tempfile.TemporaryDirectory() as td:
            db_file = Path(td) / "global_workers.db"
            self._create_conflict_test_db(db_file)
            with sqlite3.connect(db_file) as conn:
                conn.execute("ALTER TABLE boards ADD COLUMN max_concurrent_running INTEGER DEFAULT 1")
                conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at INTEGER)")
                for key, value in (("max_concurrent_llm_workers", "3"), ("scan_on_idle", "false")):
                    conn.execute("INSERT INTO settings VALUES (?, ?, 1)", (key, value))
                for slug in ("one", "two", "three"):
                    conn.execute("INSERT INTO boards (slug, max_concurrent_running) VALUES (?, 4)", (slug,))
                for task_id, board, status in (
                    ("one-a", "one", "running"), ("one-b", "one", "running"),
                    ("two-a", "two", "running"), ("two-next", "two", "todo"),
                    ("three-next", "three", "todo"),
                ):
                    conn.execute("""INSERT INTO tasks (id, board_slug, title, status, assignee, created_at)
                                    VALUES (?, ?, ?, ?, 'zf-builder', 1)""", (task_id, board, task_id, status))

            with patch("dispatcher.reap_active_workers", return_value=0), \
                 patch("dispatcher.spawn_agent_worker", return_value=(None, None)) as spawn:
                self.assertEqual(run_dispatch_cycle(db_file)["dispatched"], 0)
                spawn.assert_not_called()

                with sqlite3.connect(db_file) as conn:
                    conn.execute("UPDATE tasks SET status = 'done' WHERE id = 'one-b'")
                self.assertEqual(run_dispatch_cycle(db_file)["dispatched"], 1)
                self.assertEqual(spawn.call_args.args[0], "two-next")

                with sqlite3.connect(db_file) as conn:
                    conn.execute("UPDATE tasks SET status = 'done' WHERE id = 'one-a'")
                mock_proc = MagicMock()
                mock_proc.poll.return_value = None
                _active_scanners["other-board"] = mock_proc
                try:
                    self.assertEqual(run_dispatch_cycle(db_file)["dispatched"], 0)
                finally:
                    _active_scanners.pop("other-board", None)

                self.assertEqual(run_dispatch_cycle(db_file)["dispatched"], 1)
                self.assertEqual(spawn.call_args.args[0], "three-next")

    def test_48d_global_llm_capacity_limits_scans_and_reclaims_slots(self):
        """Only remaining slots may scan, and a completed scan releases its slot."""
        import sqlite3
        import tempfile
        from unittest.mock import MagicMock, patch
        from dispatcher import run_dispatch_cycle, reset_idle_scanner_state, _active_scanners

        with tempfile.TemporaryDirectory() as td:
            db_file = Path(td) / "global_scan_workers.db"
            self._create_conflict_test_db(db_file)
            with sqlite3.connect(db_file) as conn:
                conn.execute("ALTER TABLE boards ADD COLUMN max_concurrent_running INTEGER DEFAULT 1")
                conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at INTEGER)")
                for key, value in (("max_concurrent_llm_workers", "3"), ("scan_on_idle", "true"),
                                   ("idle_scan_max_todo", "2")):
                    conn.execute("INSERT INTO settings VALUES (?, ?, 1)", (key, value))
                for slug in ("one", "two", "three"):
                    conn.execute("INSERT INTO boards (slug, max_concurrent_running) VALUES (?, 4)", (slug,))
                for task_id, board in (("one-a", "one"), ("one-b", "one")):
                    conn.execute("""INSERT INTO tasks (id, board_slug, title, status, assignee, created_at)
                                    VALUES (?, ?, ?, 'running', 'zf-builder', 1)""", (task_id, board, task_id))

            reset_idle_scanner_state()
            with patch("dispatcher.reap_active_workers", return_value=0), \
                 patch("dispatcher.spawn_board_scanner", return_value=1234) as scan:
                self.assertEqual(run_dispatch_cycle(db_file)["scans_triggered"], 1)
                scan.assert_called_once()
                scan.reset_mock()
                mock_proc = MagicMock()
                mock_proc.poll.return_value = None
                _active_scanners["one"] = mock_proc
                try:
                    self.assertEqual(run_dispatch_cycle(db_file)["scans_triggered"], 0)
                    scan.assert_not_called()
                    mock_proc.poll.return_value = 0
                    self.assertEqual(run_dispatch_cycle(db_file)["scans_triggered"], 1)
                    self.assertNotEqual(scan.call_args.args[0], "one")
                finally:
                    reset_idle_scanner_state()

    def test_48e_global_llm_capacity_counts_cron_and_defers_tick(self):
        """Manual and in-process cron LLM work also occupies global slots."""
        import sqlite3
        import tempfile
        from unittest.mock import MagicMock, patch
        import builtin_cron
        from dispatcher import _global_llm_occupancy

        active_cron = MagicMock()
        active_cron.poll.return_value = None
        with patch("dispatcher._running_cron_llm_jobs", return_value=1), patch.object(
            builtin_cron, "_active_cron_runs", {"zero-factory-improvement-scanner-b1": active_cron}
        ):
            self.assertEqual(_global_llm_occupancy(1), 3)

        with tempfile.TemporaryDirectory() as td:
            db_file = Path(td) / "cron_capacity.db"
            with sqlite3.connect(db_file) as conn:
                conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at INTEGER)")
                conn.execute("CREATE TABLE boards (slug TEXT PRIMARY KEY, description TEXT, git_url TEXT, created_at INTEGER, updated_at INTEGER)")
                conn.execute("CREATE TABLE tasks (id TEXT, status TEXT)")
                conn.execute("INSERT INTO boards VALUES ('b1', '', '', 1, 1)")
                conn.execute("INSERT INTO settings VALUES ('max_concurrent_llm_workers', '3', 1)")
                for i in range(3):
                    conn.execute("INSERT INTO tasks VALUES (?, 'running')", (str(i),))
            with patch.dict(os.environ, {"ZEROFACTORY_DB": str(db_file), "ZEROFACTORY_LOCK_PATH": str(Path(td) / "lock")}), \
                 patch("builtin_cron.is_cron_scheduler_enabled", return_value=True), \
                 patch("builtin_cron.ensure_builtin_cron_jobs"), \
                 patch("builtin_cron.subprocess.Popen") as popen:
                self.assertEqual(builtin_cron.tick_builtin_cron(), 0)
                result = builtin_cron.trigger_builtin_job("zero-factory-improvement-scanner-b1")
                self.assertFalse(result["ok"])
                self.assertIn("limit", result["error"].lower())
                popen.assert_not_called()

                # No-Agent queue watchdog is exempt, even at full LLM capacity.
                proc = MagicMock()
                proc.returncode = 0
                proc.pid = 123
                popen.return_value = proc
                self.assertTrue(builtin_cron.trigger_builtin_job("zero-factory-task-queue-check")["ok"])

    def test_48f_trigger_builtin_job_does_not_block_on_dispatcher_lock(self):
        """Manual LLM cron runs must NOT serialize behind a running dispatch cycle.

        Regression (commit 7fcc087, global LLM-worker limit): the capacity gate
        in trigger_builtin_job() took a BLOCKING fcntl.flock on the shared
        dispatcher lock file, so a dashboard/CLI `cron run` while a dispatch
        cycle was in progress stalled for the full cycle duration (minutes,
        when opening PRs over a slow network). The gate is best-effort and the
        occupancy figure is a WAL-safe COUNT(*) + in-process counters, so it
        must fail fast, never block behind the dispatch cycle.
        """
        import fcntl
        import sqlite3
        import tempfile
        import threading
        import time
        from unittest.mock import MagicMock, patch
        import builtin_cron

        with tempfile.TemporaryDirectory() as td:
            db_file = Path(td) / "lock_hold.db"
            lock_path = Path(td) / "dispatch.lock"
            with sqlite3.connect(db_file) as conn:
                conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at INTEGER)")
                conn.execute("CREATE TABLE tasks (id TEXT, status TEXT)")
                conn.execute("INSERT INTO settings VALUES ('max_concurrent_llm_workers', '3', 1)")
                # Spare capacity: trigger should proceed, not be rejected.

            # Simulate another process (a running dispatch cycle) holding the
            # shared dispatcher flock for the full duration of the trigger call.
            released = threading.Event()

            def hold_lock():
                fh = open(lock_path, "a+b")
                fcntl.flock(fh, fcntl.LOCK_EX)
                time.sleep(3.0)
                fcntl.flock(fh, fcntl.LOCK_UN)
                fh.close()
                released.set()

            holder = threading.Thread(target=hold_lock)
            holder.start()

            # Wait until the holder actually owns the lock (probe with LOCK_NB),
            # so the "cycle in progress" precondition is real, not raced.
            deadline = time.monotonic() + 5.0
            probe = open(lock_path, "a+b")
            while time.monotonic() < deadline:
                try:
                    fcntl.flock(probe, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    fcntl.flock(probe, fcntl.LOCK_UN)
                except BlockingIOError:
                    break
                time.sleep(0.02)
            else:
                probe.close()
                self.fail("Could not confirm the dispatcher lock is held by the simulating process")
            probe.close()

            jobs = {
                "zero-factory-improvement-scanner-b1": {"no_agent": False, "profile": "zf-orchestrator"},
                "zero-factory-task-queue-check": {"no_agent": True, "profile": "zf-orchestrator"},
            }
            proc = MagicMock()
            proc.returncode = 0
            proc.pid = 456
            with patch.dict(os.environ, {"ZEROFACTORY_DB": str(db_file), "ZEROFACTORY_LOCK_PATH": str(lock_path)}), \
                 patch.object(builtin_cron, "get_all_builtin_cron_jobs", return_value=jobs), \
                 patch.object(builtin_cron, "ensure_builtin_cron_jobs"), \
                 patch.object(builtin_cron, "subprocess", create=True) as sub:
                sub.Popen.return_value = proc
                sub.DEVNULL = -3

                # LLM job while the dispatch cycle holds the lock: must return
                # quickly (< 2s) with a clean success result, not stall ~3s.
                started = time.monotonic()
                result = builtin_cron.trigger_builtin_job("zero-factory-improvement-scanner-b1")
                elapsed = time.monotonic() - started
                self.assertTrue(result["ok"], f"unexpected trigger result: {result}")
                self.assertLess(
                    elapsed, 2.0,
                    f"trigger_blocked behind dispatcher lock for {elapsed:.1f}s; "
                    "capacity gate must not serialize behind the dispatch cycle",
                )
                sub.Popen.assert_called_once()

                # No-Agent queue watchdog is exempt and also unaffected.
                sub.Popen.reset_mock()
                started = time.monotonic()
                result = builtin_cron.trigger_builtin_job("zero-factory-task-queue-check")
                elapsed = time.monotonic() - started
                self.assertTrue(result["ok"], f"unexpected trigger result: {result}")
                self.assertLess(elapsed, 2.0)
                sub.Popen.assert_called_once()

            self.assertTrue(released.wait(10))
            holder.join(10)

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
        """Verify the atomic dispatch claim prevents concurrent dispatchers from re-claiming a running task."""
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

            # Direct atomic claim check: if a second dispatcher tries to claim 't1' assuming it's in 'todo',
            # the claim must be rejected because the task is already running
            conn = sqlite3.connect(str(db_file))
            cur = conn.cursor()
            cur.execute(
                "UPDATE tasks SET status = 'running', updated_at = ? WHERE id = 't1' AND status = 'todo'",
                (now_ts,)
            )
            self.assertEqual(cur.rowcount, 0, "Atomic CAS must reject claiming a task that is already running")

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
        orig_skip = os.environ.get("ZEROFACTORY_SKIP_DISPATCHER")
        orig_task = os.environ.get("HERMES_KANBAN_TASK")

        try:
            # Normal profile
            os.environ.pop("HERMES_PROFILE", None)
            os.environ.pop("ZEROFACTORY_DISABLE_DISPATCHER", None)
            os.environ.pop("ZEROFACTORY_SKIP_DISPATCHER", None)
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
            if orig_skip is not None:
                os.environ["ZEROFACTORY_SKIP_DISPATCHER"] = orig_skip
            else:
                os.environ.pop("ZEROFACTORY_SKIP_DISPATCHER", None)
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
                 patch("builtin_cron.toggle_builtin_job"), \
                 patch.dict(os.environ, {"ZEROFACTORY_SKIP_WORKER_SPAWN": "", "ZEROFACTORY_SKIP_SCANNER_SPAWN": ""}):
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
            if len(cmd) >= 2 and cmd[0] == "gh" and cmd[1] == "api":
                res = MagicMock()
                res.returncode = 0
                res.stdout = json.dumps([])
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
        merged -> done, approved -> blocked, changes-requested -> todo,
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

            # Subsequent dispatch cycle must not re-process the done task or flood task_activity
            res2, captured_gh2, _, fetch2, _ = self._run_reviewer_pr_cycle(
                db_file, {"state": "MERGED", "reviewDecision": None,
                          "url": "https://github.com/hotcode-dev/zerofactory/pull/901",
                          "mergeable": "MERGEABLE"}, task_id="wt-merged"
            )
            self.assertTrue(res2.get("ok"))
            self.assertEqual(len(captured_gh2), 0, "Subsequent cycle should not query GitHub for completed task")
            acts2 = fetch2("SELECT action FROM task_activity WHERE task_id = 'wt-merged' AND action = 'merged'")
            self.assertEqual(len(acts2), 1, "merged activity must not be duplicated on subsequent cycles")

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

                # Subsequent cycle before merge should not re-insert approved activity
                res_app2, _, _, fetch_app2, _ = self._run_reviewer_pr_cycle(
                    db_file2, {"state": "OPEN", "reviewDecision": "APPROVED",
                               "url": "https://github.com/hotcode-dev/zerofactory/pull/902",
                               "mergeable": "MERGEABLE"}, task_id="wt-approved"
                )
                self.assertTrue(res_app2.get("ok"))
                acts_app2 = fetch_app2("SELECT action FROM task_activity WHERE task_id = 'wt-approved' AND action = 'approved'")
                self.assertEqual(len(acts_app2), 1, "approved activity row must not be duplicated")
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
                self.assertEqual(t_row["status"], "todo")
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
            self.assertEqual(t_row["status"], "todo")
            self.assertEqual(t_row["assignee"], "zf-builder")
            self.assertIn("[PR Conflict]", t_row["title"])
            acts = fetch("SELECT details FROM task_activity WHERE task_id = 'wt-conflict' AND action = 'pr_conflict'")
            self.assertEqual(len(acts), 1)
            self.assertIn("conflicting", acts[0][0].lower())
        finally:
            shutil.rmtree(td, ignore_errors=True)

    def test_58b_pr_closed_archives_task(self):
        """When a GitHub PR is closed without merging, Zero Factory must automatically
        archive/complete the task (status='done'), prune the worktree, and record a
        'closed' activity entry ('PR closed on GitHub, task archived'). This must
        work for tasks assigned to zf-reviewer as well as tasks assigned to zf-builder
        with conflict/failure metadata (e.g. zf-f5f3b8d0)."""
        import json
        import shutil
        import sqlite3

        # Case 1: Reviewer task with closed PR
        td1 = tempfile.mkdtemp()
        try:
            repo_path1, reviewer_ws1 = self._make_reviewer_test_repo(td1)
            db_file1 = Path(td1) / "closed_rev.db"
            self._create_conflict_test_db(db_file1)
            with sqlite3.connect(str(db_file1)) as conn:
                conn.execute("""
                    INSERT INTO tasks (id, title, status, assignee, workspace_path, branch_name, pr_url, created_at, updated_at)
                    VALUES ('wt-closed-rev', 'Closed PR task', 'blocked', 'zf-reviewer', ?, 'task/wt-closed-rev',
                            'https://github.com/hotcode-dev/zerofactory/pull/905', 1000, 1000)
                """, (str(reviewer_ws1),))
                conn.commit()

            res, captured_gh, mock_remove, fetch1, _ = self._run_reviewer_pr_cycle(
                db_file1, {"state": "CLOSED", "reviewDecision": None,
                           "url": "https://github.com/hotcode-dev/zerofactory/pull/905",
                           "mergeable": "MERGEABLE"}, task_id="wt-closed-rev"
            )
            self.assertTrue(res.get("ok"), f"closed PR cycle should succeed: {res}")
            self.assertTrue(captured_gh, "gh pr view should have been called")
            mock_remove.assert_called()
            t_row = fetch1("SELECT status, assignee, pr_url FROM tasks WHERE id = 'wt-closed-rev'")[0]
            self.assertEqual(t_row["status"], "done")
            acts = fetch1("SELECT action, details FROM task_activity WHERE task_id = 'wt-closed-rev' AND action = 'closed'")
            self.assertEqual(len(acts), 1, "closed activity row missing")
            self.assertEqual(acts[0][0], "closed")
            self.assertIn("archived", acts[0][1].lower())

            # Subsequent dispatch cycle must not re-process the done task or flood task_activity
            res2, captured_gh2, _, fetch2, _ = self._run_reviewer_pr_cycle(
                db_file1, {"state": "CLOSED", "reviewDecision": None,
                           "url": "https://github.com/hotcode-dev/zerofactory/pull/905",
                           "mergeable": "MERGEABLE"}, task_id="wt-closed-rev"
            )
            self.assertTrue(res2.get("ok"))
            self.assertEqual(len(captured_gh2), 0, "Subsequent cycle should not query GitHub for completed task")
            acts2 = fetch2("SELECT action FROM task_activity WHERE task_id = 'wt-closed-rev' AND action = 'closed'")
            self.assertEqual(len(acts2), 1, "closed activity must not be duplicated on subsequent cycles")
        finally:
            shutil.rmtree(td1, ignore_errors=True)

        # Case 2: Builder task with worker failure / conflict metadata and closed PR (matching zf-f5f3b8d0)
        td2 = tempfile.mkdtemp()
        try:
            repo_path2, builder_ws2 = self._make_reviewer_test_repo(td2)
            db_file2 = Path(td2) / "closed_builder.db"
            self._create_conflict_test_db(db_file2)
            meta_json = json.dumps({
                "last_worker_failure": {"retcode": -1, "reason": "PID not found"},
                "conflict_retries": 2,
                "blocked_reason": "Worker process PID not found"
            })
            with sqlite3.connect(str(db_file2)) as conn:
                conn.execute("""
                    INSERT INTO tasks (id, title, status, assignee, workspace_path, branch_name, pr_url, metadata, created_at, updated_at)
                    VALUES ('zf-test-closed', 'Bug: memory leak [PR Conflict]', 'blocked', 'zf-builder', ?, 'task/zf-test-closed',
                            'https://github.com/hotcode-dev/zerofactory/pull/906', ?, 1000, 1000)
                """, (str(builder_ws2), meta_json))
                conn.commit()

            res3, captured_gh3, mock_remove3, fetch3, _ = self._run_reviewer_pr_cycle(
                db_file2, {"state": "CLOSED", "reviewDecision": "",
                           "url": "https://github.com/hotcode-dev/zerofactory/pull/906",
                           "mergeable": "CONFLICTING"}, task_id="zf-test-closed"
            )
            self.assertTrue(res3.get("ok"), f"closed PR builder cycle should succeed: {res3}")
            self.assertTrue(captured_gh3, "gh pr view should have been called")
            mock_remove3.assert_called()
            t_row3 = fetch3("SELECT status, assignee, pr_url, workspace_path FROM tasks WHERE id = 'zf-test-closed'")[0]
            self.assertEqual(t_row3["status"], "done")
            self.assertIsNone(t_row3["workspace_path"])
            acts3 = fetch3("SELECT action, details FROM task_activity WHERE task_id = 'zf-test-closed' AND action = 'closed'")
            self.assertEqual(len(acts3), 1, "closed activity row missing for builder task")
            self.assertEqual(acts3[0][0], "closed")
            self.assertIn("archived", acts3[0][1].lower())
        finally:
            shutil.rmtree(td2, ignore_errors=True)

    def test_58c_merged_closed_pr_deletes_remote_branch(self):
        """The MERGED and CLOSED PR archive paths must best-effort delete the
        remote `task/<id>` branch on origin (`git push origin --delete task/<id>`).
        A failing delete (non-zero rc, already-gone branch, raised exception)
        must NOT raise, must not abort the dispatch cycle, and must not affect
        the task archive outcome (status='done')."""
        import json
        import shutil
        import sqlite3
        import subprocess
        from unittest.mock import patch, MagicMock
        from dispatcher import run_dispatch_cycle, _delete_remote_branch

        def run_archive_cycle(td, db_file, gh_payload, task_id, delete_rc=0, delete_raises=False):
            repo_path, reviewer_ws = self._make_reviewer_test_repo(td)
            self._create_conflict_test_db(db_file)
            with sqlite3.connect(str(db_file)) as conn:
                conn.execute("""
                    INSERT INTO tasks (id, title, status, assignee, workspace_path, branch_name, pr_url, created_at, updated_at)
                    VALUES (?, ?, 'blocked', 'zf-reviewer', ?, ?, 'https://github.com/hotcode-dev/zerofactory/pull/907', 1000, 1000)
                """, (task_id, f"Archive {gh_payload['state']} task", str(reviewer_ws), f"task/{task_id}"))
                conn.commit()

            orig_skip_git = os.environ.pop("ZEROFACTORY_SKIP_GIT", None)
            orig_run = subprocess.run
            delete_cmds = []

            def fake_run(cmd, *args, **kwargs):
                if len(cmd) >= 3 and cmd[0] == "gh" and cmd[1] == "pr" and cmd[2] == "view":
                    res = MagicMock()
                    res.returncode = 0
                    res.stdout = json.dumps(gh_payload)
                    return res
                if len(cmd) >= 2 and cmd[0] == "gh" and cmd[1] == "api":
                    res = MagicMock()
                    res.returncode = 0
                    res.stdout = json.dumps([])
                    return res
                if cmd[:4] == ["git", "push", "origin", "--delete"]:
                    delete_cmds.append(list(cmd))
                    if delete_raises:
                        raise RuntimeError("simulated network failure")
                    res = MagicMock()
                    res.returncode = delete_rc
                    res.stdout = ""
                    res.stderr = "" if delete_rc == 0 else "fatal: unable to delete 'task/x' (no such ref)"
                    return res
                return orig_run(cmd, *args, **kwargs)

            try:
                with patch("dispatcher._remove_worktree"), \
                     patch("dispatcher.setup_worktree", return_value=None), \
                     patch("dispatcher.check_unresolved_conflicts", return_value=[]), \
                     patch("fcntl.flock", return_value=0), \
                     patch("subprocess.run", side_effect=fake_run):
                    res = run_dispatch_cycle(db_file)
            finally:
                if orig_skip_git is not None:
                    os.environ["ZEROFACTORY_SKIP_GIT"] = orig_skip_git

            with sqlite3.connect(str(db_file)) as conn:
                conn.row_factory = sqlite3.Row
                t_row = conn.execute("SELECT status, workspace_path FROM tasks WHERE id = ?", (task_id,)).fetchone()
            return res, delete_cmds, t_row

        # --- Case 1: MERGED PR -> remote branch delete attempted, task archived.
        td1 = tempfile.mkdtemp()
        try:
            res, delete_cmds, t_row = run_archive_cycle(
                td1, Path(td1) / "rb_merged.db",
                {"state": "MERGED", "reviewDecision": None,
                 "url": "https://github.com/hotcode-dev/zerofactory/pull/907",
                 "mergeable": "MERGEABLE"},
                task_id="wt-rb-merged",
            )
            self.assertTrue(res.get("ok"), f"merged cycle should succeed: {res}")
            self.assertEqual(
                delete_cmds, [["git", "push", "origin", "--delete", "task/wt-rb-merged"]],
                f"expected exactly one remote-branch delete, got: {delete_cmds}",
            )
            self.assertEqual(t_row["status"], "done", "merged archive outcome must be unaffected by delete")
            self.assertIsNone(t_row["workspace_path"])
        finally:
            shutil.rmtree(td1, ignore_errors=True)

        # --- Case 2: CLOSED PR -> delete attempted; a FAILING delete (non-zero
        # rc, e.g. branch already gone) must not raise and must not affect
        # the archive outcome.
        td2 = tempfile.mkdtemp()
        try:
            res, delete_cmds, t_row = run_archive_cycle(
                td2, Path(td2) / "rb_closed.db",
                {"state": "CLOSED", "reviewDecision": None,
                 "url": "https://github.com/hotcode-dev/zerofactory/pull/908",
                 "mergeable": "MERGEABLE"},
                task_id="wt-rb-closed",
                delete_rc=1,
            )
            self.assertTrue(res.get("ok"), f"closed cycle with failing delete should still succeed: {res}")
            self.assertEqual(len(delete_cmds), 1, "closed archive must still attempt the remote delete")
            self.assertEqual(delete_cmds[0][4], "task/wt-rb-closed")
            self.assertEqual(t_row["status"], "done", "failing delete must not prevent task archival")
        finally:
            shutil.rmtree(td2, ignore_errors=True)

        # --- Case 3: _delete_remote_branch is exception-safe: a raised
        # subprocess error or TimeoutExpired must be swallowed (warning only),
        # and a missing repo path / empty task id is a clean no-op.
        td3 = tempfile.mkdtemp()
        try:
            repo_path3 = Path(td3) / "repo"
            repo_path3.mkdir()
            with patch("subprocess.run", side_effect=RuntimeError("boom")):
                _delete_remote_branch("wt-rb-boom", repo_path3)  # must not raise
            with self.assertLogs("zerofactory.kanban.dispatcher", level="WARNING") as log_cm:
                with patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd=["git"], timeout=30)):
                    _delete_remote_branch("wt-rb-timeout", repo_path3)  # must not raise
            self.assertTrue(any("timed out" in line for line in log_cm.output),
                            f"expected a timeout warning, got: {log_cm.output}")
            with patch("subprocess.run") as mock_run:
                _delete_remote_branch("", repo_path3)
                _delete_remote_branch("wt-rb-norepo", Path(td3) / "does_not_exist")
                mock_run.assert_not_called()
        finally:
            shutil.rmtree(td3, ignore_errors=True)

    def test_59_init_db_path_keyed_flag(self):
        """init_db() must re-initialize when ZEROFACTORY_DB changes to a new
        path within the same process (regression: a bare global boolean flag
        made init_db() path-blind, silently skipping table creation and the
        legacy-boards migration for the new file)."""
        import sqlite3

        td = tempfile.mkdtemp(prefix="zf-init-path-")
        old_db = os.environ.get("ZEROFACTORY_DB")
        path_a = Path(td) / "a.db"
        path_b = Path(td) / "b.db"
        try:
            # --- Step 1: initialize DB at path A.
            os.environ["ZEROFACTORY_DB"] = str(path_a)
            init_db()
            self.assertTrue(path_a.exists(), "init_db() must create DB file A")
            with sqlite3.connect(str(path_a)) as conn:
                tables_a = {r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            self.assertIn("boards", tables_a)
            self.assertIn("tasks", tables_a)

            # --- Step 2: point ZEROFACTORY_DB at a NEW, empty path and
            # initialize again. Before the fix this was a silent no-op.
            os.environ["ZEROFACTORY_DB"] = str(path_b)
            init_db()
            self.assertTrue(path_b.exists(), "init_db() must create DB file B after ZEROFACTORY_DB change")
            with sqlite3.connect(str(path_b)) as conn:
                tables_b = {r[0] for r in conn.execute(
                    "SELECT name FROM sqlite_master WHERE type='table'").fetchall()}
            self.assertIn("boards", tables_b, "tables must exist in the new DB path B")
            self.assertIn("tasks", tables_b)

            # --- Step 3: the same legacy-schema migration must run in-place
            # for a pre-created legacy boards table at a third path.
            path_c = Path(td) / "legacy.db"
            conn = sqlite3.connect(str(path_c))
            conn.execute(
                "CREATE TABLE boards (slug TEXT PRIMARY KEY, description TEXT DEFAULT '', "
                "git_url TEXT DEFAULT '', created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL)"
            )
            conn.execute("INSERT INTO boards (slug, created_at, updated_at) VALUES ('legacy-board', 1, 1)")
            conn.commit()
            conn.close()
            os.environ["ZEROFACTORY_DB"] = str(path_c)
            init_db()
            conn = sqlite3.connect(str(path_c))
            cols = [r[1] for r in conn.execute("PRAGMA table_info(boards)").fetchall()]
            row = conn.execute(
                "SELECT slug, max_concurrent_running FROM boards WHERE slug = 'legacy-board'").fetchone()
            conn.close()
            self.assertIn("max_concurrent_running", cols, "legacy boards table must be migrated in place")
            self.assertEqual(row, ("legacy-board", 1))

            # --- Step 4: force still works as an escape hatch.
            os.environ["ZEROFACTORY_DB"] = str(path_a)
            init_db(force=True)  # must not raise and must re-run idempotently
        finally:
            if old_db is None:
                os.environ.pop("ZEROFACTORY_DB", None)
            else:
                os.environ["ZEROFACTORY_DB"] = old_db
            shutil.rmtree(td, ignore_errors=True)

    def test_pr_review_comments_parsing_and_formatting(self):
        """Verify fetch_pr_review_comments parses all types of GitHub review comments
        (inline diff comments, review summaries, issue comments, suggestions) and filters bots."""
        import json
        from unittest.mock import patch, MagicMock
        from dispatcher import (
            extract_gh_repo_info,
            fetch_pr_review_comments,
            format_task_comment_body,
        )

        orig_skip_git = os.environ.pop("ZEROFACTORY_SKIP_GIT", None)
        try:
            # 1. extract_gh_repo_info
            info = extract_gh_repo_info("https://github.com/hotcode-dev/zerofactory/pull/35")
            self.assertEqual(info, ("hotcode-dev", "zerofactory", 35))
            self.assertIsNone(extract_gh_repo_info("not-a-url"))
            self.assertIsNone(extract_gh_repo_info(""))

            # 2. Mock gh api calls returning all review comment types
            inline_payload = [
                {
                    "id": 4055542985,
                    "path": "dispatcher.py",
                    "line": 531,
                    "start_line": 522,
                    "diff_hunk": "@@ -517,14 +517,24 @@",
                    "user": {"login": "ntsd"},
                    "author_association": "MEMBER",
                    "body": "the comment is too long\n```suggestion\n# Short comment\n```",
                    "created_at": "2026-09-20T01:26:50Z",
                },
                {
                    "id": 999999,
                    "path": "dispatcher.py",
                    "line": 10,
                    "user": {"login": "github-actions[bot]"},
                    "body": "bot comment should be excluded",
                    "created_at": "2026-09-20T01:20:00Z",
                },
            ]
            reviews_payload = [
                {
                    "id": 5258780352,
                    "user": {"login": "alice"},
                    "state": "CHANGES_REQUESTED",
                    "body": "Please address performance and shorten comments.",
                    "author_association": "MEMBER",
                    "submitted_at": "2026-09-20T01:25:00Z",
                }
            ]
            issues_payload = [
                {
                    "id": 88888,
                    "user": {"login": "bob"},
                    "body": "Can you also check test coverage?",
                    "author_association": "MEMBER",
                    "created_at": "2026-09-20T01:24:00Z",
                },
                {
                    "id": 99998,
                    "user": {"login": "cloudflare-workers-and-pages[bot]"},
                    "body": "Deployment successful.",
                    "created_at": "2026-09-20T01:26:00Z",
                }
            ]

            def fake_run(cmd, *args, **kwargs):
                res = MagicMock()
                res.returncode = 0
                if len(cmd) >= 3 and "pulls/35/comments" in cmd[2]:
                    res.stdout = json.dumps(inline_payload)
                elif len(cmd) >= 3 and "pulls/35/reviews" in cmd[2]:
                    res.stdout = json.dumps(reviews_payload)
                elif len(cmd) >= 3 and "issues/35/comments" in cmd[2]:
                    res.stdout = json.dumps(issues_payload)
                else:
                    res.stdout = json.dumps([])
                return res

            td = tempfile.mkdtemp()
            try:
                repo_path = Path(td)
                with patch("dispatcher.subprocess.run", side_effect=fake_run):
                    comments = fetch_pr_review_comments(
                        repo_path=repo_path,
                        pr_url="https://github.com/hotcode-dev/zerofactory/pull/35",
                    )

                self.assertFalse(
                    any(c["author"] == "cloudflare-workers-and-pages[bot]" for c in comments),
                    "deployment bot comments must not be routed as actionable review feedback",
                )

                # Bot comment filtered, 3 valid comments remain
                self.assertEqual(len(comments), 3)

                # Check inline comment
                inline_cmt = next(c for c in comments if c["type"] == "inline_review")
                self.assertEqual(inline_cmt["author"], "ntsd")
                self.assertEqual(inline_cmt["path"], "dispatcher.py")
                self.assertEqual(inline_cmt["line"], 531)
                self.assertEqual(inline_cmt["suggestion"], "# Short comment")
                formatted_inline = format_task_comment_body(inline_cmt)
                self.assertIn("GitHub Review Comment on `dispatcher.py:L522-531`", formatted_inline)
                self.assertIn("the comment is too long", formatted_inline)
                self.assertIn("```suggestion", formatted_inline)

                # Check review summary
                rev_cmt = next(c for c in comments if c["type"] == "review_summary")
                self.assertEqual(rev_cmt["author"], "alice")
                self.assertEqual(rev_cmt["state"], "CHANGES_REQUESTED")
                formatted_rev = format_task_comment_body(rev_cmt)
                self.assertIn("GitHub PR Review (CHANGES_REQUESTED)", formatted_rev)

                # Check PR issue comment
                iss_cmt = next(c for c in comments if c["type"] == "pr_comment")
                self.assertEqual(iss_cmt["author"], "bob")
                formatted_iss = format_task_comment_body(iss_cmt)
                self.assertIn("GitHub PR Comment", formatted_iss)
            finally:
                shutil.rmtree(td, ignore_errors=True)
        finally:
            if orig_skip_git is not None:
                os.environ["ZEROFACTORY_SKIP_GIT"] = orig_skip_git

    def test_pr_review_comments_allowlist_external_reviewer(self):
        """External PR feedback is ignored unless its username is approved by
        the board-level additional reviewer allowlist."""
        import json
        from unittest.mock import MagicMock, patch
        from dispatcher import fetch_pr_review_comments

        old_skip_git = os.environ.pop("ZEROFACTORY_SKIP_GIT", None)
        try:
            payload = [{
                "id": 12345,
                "user": {"login": "outside-reviewer"},
                "author_association": "CONTRIBUTOR",
                "body": "Please add coverage for the error path.",
                "created_at": "2026-09-20T01:24:00Z",
            }]

            def fake_run(cmd, *_args, **_kwargs):
                result = MagicMock()
                result.returncode = 0
                result.stdout = json.dumps(payload if "issues/35/comments" in cmd[2] else [])
                return result

            with patch("dispatcher.subprocess.run", side_effect=fake_run):
                ignored = fetch_pr_review_comments(
                    Path(tempfile.mkdtemp()),
                    pr_url="https://github.com/hotcode-dev/zerofactory/pull/35",
                )
                allowed = fetch_pr_review_comments(
                    Path(tempfile.mkdtemp()),
                    pr_url="https://github.com/hotcode-dev/zerofactory/pull/35",
                    additional_reviewer_usernames={"outside-reviewer"},
                )

            self.assertEqual(ignored, [])
            self.assertEqual(len(allowed), 1)
            self.assertEqual(allowed[0]["author"], "outside-reviewer")
        finally:
            if old_skip_git is not None:
                os.environ["ZEROFACTORY_SKIP_GIT"] = old_skip_git

    def test_format_inline_comment_line_range_handles_null_line(self):
        """Regression: format_task_comment_body() must not interpolate a None
        ``line`` into the inline-review anchor. GitHub leaves ``line`` null
        (keeping only ``start_line``/``start_side``) for comments anchored to
        lines no longer present in the diff, so the header must degrade to a
        plain ``:L<start_line>`` instead of a literal ``:L<start>-None``."""
        from dispatcher import format_task_comment_body

        # start_line set, line is None (GitHub's line-no-longer-in-diff case)
        null_line = format_task_comment_body({
            "type": "inline_review",
            "path": "dispatcher.py",
            "line": None,
            "start_line": 522,
            "body": "anchored to a line no longer in the diff",
        })
        self.assertNotIn("None", null_line)
        self.assertIn("GitHub Review Comment on `dispatcher.py:L522`", null_line)

        # start_line set, line set and equal -> single-line anchor
        same_line = format_task_comment_body({
            "type": "inline_review",
            "path": "dispatcher.py",
            "line": 531,
            "start_line": 531,
            "body": "single-line anchor",
        })
        self.assertNotIn("None", same_line)
        self.assertIn("GitHub Review Comment on `dispatcher.py:L531`", same_line)

        # start_line and line both set and different -> range anchor (unchanged)
        range_lines = format_task_comment_body({
            "type": "inline_review",
            "path": "dispatcher.py",
            "line": 531,
            "start_line": 522,
            "body": "range anchor",
        })
        self.assertIn("GitHub Review Comment on `dispatcher.py:L522-531`", range_lines)

        # neither line nor start_line -> no anchor suffix
        no_anchor = format_task_comment_body({
            "type": "inline_review",
            "path": "dispatcher.py",
            "line": None,
            "start_line": None,
            "body": "file-level comment",
        })
        self.assertNotIn("None", no_anchor)
        self.assertIn("GitHub Review Comment on `dispatcher.py`", no_anchor)

    def test_review_comment_routes_to_builder_and_is_idempotent(self):
        """When a review comment is added to a PR on GitHub (even with state COMMENTED),
        the dispatcher must record it in task_comments, route the task to zf-builder,
        and subsequent dispatch cycles must be idempotent."""
        import sqlite3
        from unittest.mock import patch, MagicMock
        from dispatcher import run_dispatch_cycle

        orig_skip_git = os.environ.pop("ZEROFACTORY_SKIP_GIT", None)
        td = tempfile.mkdtemp()
        try:
            repo_path, reviewer_ws = self._make_reviewer_test_repo(td)
            db_file = Path(td) / "rev_comment.db"
            self._create_conflict_test_db(db_file)

            with sqlite3.connect(str(db_file)) as conn:
                conn.execute("""
                    INSERT INTO tasks (id, title, status, assignee, workspace_path, branch_name, pr_url, created_at, updated_at)
                    VALUES ('zf-rev-test', 'Fix merge args [PR Opened by zf-builder]', 'blocked', 'zf-reviewer', ?, 'task/zf-rev-test',
                            'https://github.com/hotcode-dev/zerofactory/pull/35', 1000, 1000)
                """, (str(reviewer_ws),))
                conn.commit()

            fake_inline_comments = [
                {
                    "id": 4055542985,
                    "path": "dispatcher.py",
                    "line": 531,
                    "start_line": 522,
                    "diff_hunk": "@@ -517,14 +517,24 @@",
                    "user": {"login": "ntsd"},
                    "author_association": "MEMBER",
                    "body": "the comment is too long",
                    "created_at": "2026-09-20T01:26:50Z",
                }
            ]

            import json
            import subprocess as real_subprocess
            orig_run = real_subprocess.run

            def fake_run(cmd, *args, **kwargs):
                if len(cmd) >= 3 and cmd[0] == "gh" and cmd[1] == "pr" and cmd[2] == "view":
                    res = MagicMock()
                    res.returncode = 0
                    res.stdout = json.dumps({
                        "state": "OPEN",
                        "reviewDecision": None,
                        "mergeable": "MERGEABLE",
                        "url": "https://github.com/hotcode-dev/zerofactory/pull/35"
                    })
                    return res
                if len(cmd) >= 3 and cmd[0] == "gh" and cmd[1] == "api":
                    res = MagicMock()
                    res.returncode = 0
                    if "pulls/35/comments" in cmd[2]:
                        res.stdout = json.dumps(fake_inline_comments)
                    else:
                        res.stdout = json.dumps([])
                    return res
                return orig_run(cmd, *args, **kwargs)

            with patch("dispatcher._remove_worktree") as mock_remove, \
                 patch("dispatcher.setup_worktree", return_value=None), \
                 patch("dispatcher.check_unresolved_conflicts", return_value=[]), \
                 patch("fcntl.flock", return_value=0), \
                 patch("dispatcher.subprocess.run", side_effect=fake_run):
                # First cycle: should detect comment and route to zf-builder
                res1 = run_dispatch_cycle(db_file)
                self.assertTrue(res1.get("ok"))

                with sqlite3.connect(str(db_file)) as conn:
                    conn.row_factory = sqlite3.Row
                    cur = conn.cursor()
                    t_row = cur.execute("SELECT status, assignee, metadata FROM tasks WHERE id = 'zf-rev-test'").fetchone()
                    self.assertEqual(t_row["status"], "todo")
                    self.assertEqual(t_row["assignee"], "zf-builder")

                    meta = json.loads(t_row["metadata"] or "{}")
                    self.assertIn("inline_4055542985", meta.get("processed_review_comment_ids", []))

                    # Verify comment in task_comments
                    cmts = cur.execute("SELECT author, body FROM task_comments WHERE task_id = 'zf-rev-test'").fetchall()
                    self.assertEqual(len(cmts), 1)
                    self.assertEqual(cmts[0]["author"], "ntsd")
                    self.assertIn("the comment is too long", cmts[0]["body"])

                    # Verify task_activity
                    acts = cur.execute("SELECT action, details FROM task_activity WHERE task_id = 'zf-rev-test' ORDER BY id ASC").fetchall()
                    actions = [a["action"] for a in acts]
                    self.assertIn("review_comment", actions)
                    self.assertIn("changes_requested", actions)

                # Second cycle: idempotent, comment must not be re-inserted and task remains in todo
                res2 = run_dispatch_cycle(db_file)
                self.assertTrue(res2.get("ok"))

                with sqlite3.connect(str(db_file)) as conn:
                    cur = conn.cursor()
                    cmts2 = cur.execute("SELECT count(*) FROM task_comments WHERE task_id = 'zf-rev-test'").fetchone()
                    self.assertEqual(cmts2[0], 1, "comments must not be duplicated")
        finally:
            shutil.rmtree(td, ignore_errors=True)
            if orig_skip_git is not None:
                os.environ["ZEROFACTORY_SKIP_GIT"] = orig_skip_git

    def test_builder_prompt_embeds_review_comments(self):
        """When task has review comments in task_comments, spawn_agent_worker embeds them
        prominently in the builder prompt."""
        import sqlite3
        from unittest.mock import patch, MagicMock
        from dispatcher import spawn_agent_worker

        td = tempfile.mkdtemp()
        try:
            db_file = Path(td) / "test_prompt.db"
            self._create_conflict_test_db(db_file)

            with sqlite3.connect(str(db_file)) as conn:
                conn.execute("""
                    INSERT INTO tasks (id, title, status, assignee, created_at, updated_at)
                    VALUES ('t-prompt', 'My Task', 'todo', 'zf-builder', 1000, 1000)
                """)
                conn.execute("""
                    INSERT INTO task_comments (task_id, author, body, created_at)
                    VALUES ('t-prompt', 'ntsd', '**[GitHub Review Comment on `dispatcher.py:L522`]**\nthe comment is too long', 1000)
                """)
                conn.commit()

            captured_cmds = []

            def fake_popen(cmd, *args, **kwargs):
                captured_cmds.append(cmd)
                proc = MagicMock()
                proc.pid = 99999
                proc.poll.return_value = None
                return proc

            with patch.dict(os.environ, {"ZEROFACTORY_DB": str(db_file), "ZEROFACTORY_SKIP_WORKER_SPAWN": ""}), \
                 patch("dispatcher.check_unresolved_conflicts_safe", return_value=(True, [], "")), \
                 patch("subprocess.Popen", side_effect=fake_popen):
                pid, sid = spawn_agent_worker(
                    task_id="t-prompt",
                    title="My Task",
                    description="Desc",
                    priority="P0",
                    assignee="zf-builder",
                    workspace_path=td,
                    branch_name="task/t-prompt"
                )

            self.assertEqual(len(captured_cmds), 1)
            cmd = captured_cmds[0]
            # The prompt is passed after -q
            q_idx = cmd.index("-q")
            prompt = cmd[q_idx + 1]

            self.assertIn("🚨 CRITICAL: PULL REQUEST REVIEW COMMENTS TO ADDRESS", prompt)
            self.assertIn("Review Comment #1 (by @ntsd):", prompt)
            self.assertIn("the comment is too long", prompt)
            self.assertIn("Your goal as Builder (Fix Review Comments):", prompt)
        finally:
            shutil.rmtree(td, ignore_errors=True)
            os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = "1"

    def test_60_reap_active_workers_stale_log_mtime_not_reaped(self):
        """Regression (P0): reap_active_workers must NOT kill a LIVE worker whose
        log mtime predates task start.

        Before the fix, the inactivity branch only guarded on
        ``running_time > inactivity_timeout`` and silently degraded
        ``idle_time`` to ``running_time`` whenever the log mtime was stale
        (``mtime <= started_at`` — a reused log, or a spawn-time utime the
        worker never wrote past). That turned any long-running worker into a
        false-positive reap, corrupting in-flight work.

        The fix routes both detection paths through the shared
        ``_compute_stuck_state`` double-gate, so a stale/absent log mtime
        carries no inactivity evidence and cannot alone trigger a reap.
        """
        import time as _time
        import subprocess as _subprocess
        from unittest.mock import MagicMock, patch
        from dispatcher import reap_active_workers, _active_workers
        from dashboard.plugin_api import get_db_conn

        inactivity = 60
        task_timeout = 100000  # effectively disabled; only inactivity matters
        old_inactivity = os.environ.get("ZEROFACTORY_INACTIVITY_TIMEOUT_SECONDS")
        old_task_timeout = os.environ.get("ZEROFACTORY_TASK_TIMEOUT_SECONDS")

        # Ensure a board exists so create_task succeeds in isolation.
        existing = [b["slug"] for b in list_boards()["boards"]]
        if "hotcode-dev-zerofactory" not in existing:
            create_board(BoardCreate(
                git_url="https://github.com/hotcode-dev/zerofactory",
                description="AI workflow",
            ))

        t1 = t2 = t3 = None
        log_dir = Path.home() / ".hermes" / "logs"
        log_dir.mkdir(parents=True, exist_ok=True)

        def _make_running_task(title):
            t_res = create_task(TaskCreate(
                title=title,
                description="reap regression harness",
                board_slug="hotcode-dev-zerofactory",
                priority="P1",
                status="running",
                assignee="zf-builder",
            ))
            return t_res["id"]

        def _set_started_and_pid(t_id, started_at, worker_pid, ongoing_session=None):
            import json as _json
            meta = {"started_at": started_at, "worker_pid": worker_pid}
            # Real dispatch always records an ongoing session in task metadata
            # (spawn_agent_worker). Without one, a dead-pid task with no
            # _active_workers entry falls into the reaper's orphan-recovery
            # path (back to 'todo') instead of the worker_lost -> blocked
            # path this harness pins, so mirror the real shape.
            if ongoing_session is not None:
                meta["sessions"] = [ongoing_session]
            with get_db_conn() as conn:
                conn.execute(
                    "UPDATE tasks SET updated_at = ?, metadata = ? WHERE id = ?",
                    (started_at, _json.dumps(meta), t_id),
                )
                conn.commit()

        try:
            os.environ["ZEROFACTORY_INACTIVITY_TIMEOUT_SECONDS"] = str(inactivity)
            os.environ["ZEROFACTORY_TASK_TIMEOUT_SECONDS"] = str(task_timeout)

            now = int(_time.time())

            def _run_reap(t_id):
                """Run reap_active_workers with terminate_worker_process recorded.

                First mark every OTHER running task 'done' so the reaper sees
                only our harness task — otherwise leftover running tasks from
                earlier tests would make the global ``reaped`` count flaky.
                """
                terminate_calls = []

                def _record_terminate(proc, pid, *args, **kwargs):
                    terminate_calls.append((proc, pid))

                with get_db_conn() as conn:
                    conn.execute(
                        "UPDATE tasks SET status = 'done' WHERE status = 'running' AND id != ?",
                        (t_id,),
                    )
                    conn.commit()
                    cursor = conn.cursor()
                    with patch("dispatcher.terminate_worker_process", side_effect=_record_terminate):
                        reaped = reap_active_workers(cursor, now)
                    status = conn.execute("SELECT status FROM tasks WHERE id = ?", (t_id,)).fetchone()[0]
                    timeout_rows = conn.execute(
                        "SELECT COUNT(*) FROM task_activity WHERE task_id = ? AND action = 'worker_timeout'",
                        (t_id,),
                    ).fetchone()[0]
                    activity_actions = {r[0] for r in conn.execute(
                        "SELECT action FROM task_activity WHERE task_id = ?", (t_id,)
                    ).fetchall()}
                    conn.commit()
                return reaped, status, timeout_rows, activity_actions, terminate_calls

            # --- Case 1 (THE BUG): live worker + STALE log mtime -> NOT reaped.
            t1 = _make_running_task("Stale Mtime Live Worker")
            started1 = now - (inactivity + 60)  # running_time = inactivity + 60 > inactivity
            log1 = log_dir / f"worker_{t1}.log"
            log1.write_text("seed\n")
            stale_mtime = started1 - 30  # < started_at: a reused/stale log
            os.utime(log1, (stale_mtime, stale_mtime))

            live_proc = MagicMock()
            live_proc.poll.return_value = None  # alive
            live_proc.pid = os.getpid()
            _active_workers[t1] = live_proc
            _set_started_and_pid(t1, started1, live_proc.pid)

            reaped1, status1, timeout_rows1, _acts1, term1 = _run_reap(t1)

            self.assertEqual(status1, "running", "live worker with stale log mtime must NOT be reaped")
            self.assertEqual(len(term1), 0, "terminate_worker_process must not run for a live stale-mtime worker")
            self.assertEqual(timeout_rows1, 0, "no worker_timeout activity row for the stale-mtime worker")
            self.assertEqual(reaped1, 0)

            # --- Case 2 (regression guard): LIVE worker + FRESH (post-start) mtime,
            # idle longer than the threshold -> reaped via the inactivity gate.
            t2 = _make_running_task("Fresh Mtime Idle Worker")
            started2 = now - (inactivity + 300)  # running_time well over threshold
            log2 = log_dir / f"worker_{t2}.log"
            log2.write_text("last write\n")
            fresh_mtime = started2 + 60  # > started_at, but idle = now - fresh_mtime >> threshold
            os.utime(log2, (fresh_mtime, fresh_mtime))
            live_proc2 = MagicMock()
            live_proc2.poll.return_value = None
            live_proc2.pid = os.getpid()
            _active_workers[t2] = live_proc2
            _set_started_and_pid(t2, started2, live_proc2.pid)

            reaped2, status2, timeout_rows2, _acts2, term2 = _run_reap(t2)

            self.assertEqual(status2, "blocked", "genuinely idle live worker must still be reaped")
            self.assertGreaterEqual(timeout_rows2, 1, "inactivity reap must emit a worker_timeout row")
            self.assertGreaterEqual(reaped2, 1)
            self.assertEqual(len(term2), 1, "idle worker process must be terminated exactly once")

            # --- Case 3 (regression guard, literal requirement): DEAD pid -> reaped.
            t3 = _make_running_task("Dead Pid Worker")
            _proc = _subprocess.Popen(["sleep", "0.05"])
            _proc.wait()
            dead_pid = _proc.pid
            started3 = now - (inactivity + 60)
            log3 = log_dir / f"worker_{t3}.log"
            log3.write_text("died after write\n")
            os.utime(log3, (now, now))  # fresh mtime, then the process died
            _set_started_and_pid(
                t3, started3, dead_pid,
                ongoing_session={
                    "session_id": "dead-pid-case",
                    "status": "ongoing",
                    "started_at": started3,
                },
            )  # NOT registered in _active_workers; ongoing session mirrors real dispatch

            reaped3, status3, _to3, acts3, term3 = _run_reap(t3)

            self.assertEqual(status3, "blocked", "a dead worker process must be reaped")
            self.assertTrue(
                acts3 & {"worker_lost", "worker_timeout"},
                f"dead worker reap must emit an activity row, got {acts3}",
            )
            self.assertGreaterEqual(reaped3, 1)

            # Cleanup the harness tasks so they don't leak into other tests.
            with get_db_conn() as conn:
                conn.execute("UPDATE tasks SET status = 'done' WHERE id IN (?, ?, ?)", (t1, t2, t3))
                conn.commit()
        finally:
            for k, v in (
                ("ZEROFACTORY_INACTIVITY_TIMEOUT_SECONDS", old_inactivity),
                ("ZEROFACTORY_TASK_TIMEOUT_SECONDS", old_task_timeout),
            ):
                if v is None:
                    os.environ.pop(k, None)
                else:
                    os.environ[k] = v
            for t in (t1, t2, t3):
                if t:
                    _active_workers.pop(t, None)
                    try:
                        (log_dir / f"worker_{t}.log").unlink(missing_ok=True)
                    except Exception:
                        pass



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

    def test_73_strict_activity_actors(self):
        """Activity actor must strictly only be one of the 6 canonical actors:
        zf-orchestrator, zf-builder, zf-reviewer, dispatcher, user, other."""
        from dashboard.plugin_api import (
            ACTIVITY_ACTORS,
            log_activity,
            get_db_conn,
        )

        expected_actors = [
            "zf-orchestrator",
            "zf-builder",
            "zf-reviewer",
            "dispatcher",
            "user",
            "other",
        ]
        self.assertEqual(ACTIVITY_ACTORS, expected_actors)

        with get_db_conn() as conn:
            # Create a board and task to satisfy FK
            conn.execute("INSERT OR IGNORE INTO boards (slug, description, max_concurrent_running, created_at, updated_at) VALUES ('b-actor-test', 'test', 1, 1, 1)")
            conn.execute("INSERT OR IGNORE INTO tasks (id, board_slug, title, status, created_at, updated_at) VALUES ('t-actor-1', 'b-actor-test', 'Actor Test', 'todo', 1, 1)")
            
            log_activity(conn, "t-actor-1", "user", "move", "Moved via UI drag")
            log_activity(conn, "t-actor-1", "user", "comment", "Added via CLI")
            log_activity(conn, "t-actor-1", "dispatcher", "start", "Dispatched task")
            log_activity(conn, "t-actor-1", "zf-builder", "worker_done", "Built feature")
            log_activity(conn, "t-actor-1", "zf-reviewer", "approved", "Review passed")
            log_activity(conn, "t-actor-1", "custom-script", "fix", "Custom agent action")
            conn.commit()

            c = conn.cursor()
            c.execute("SELECT actor, COUNT(*) FROM task_activity WHERE task_id = 't-actor-1' GROUP BY actor")
            actor_counts = dict(c.fetchall())
            self.assertEqual(actor_counts.get("user"), 2)
            self.assertEqual(actor_counts.get("dispatcher"), 1)
            self.assertEqual(actor_counts.get("zf-builder"), 1)
            self.assertEqual(actor_counts.get("zf-reviewer"), 1)
            self.assertEqual(actor_counts.get("custom-script"), 1)

        # Verify API /activities returns filter_options['actors'] with strict list
        res = client.get("/api/plugins/zerofactory/activities").json()
        self.assertTrue(res["ok"])
        self.assertEqual(res["filter_options"]["actors"], expected_actors)

        # Verify all activities returned in the list have actor strictly in ACTIVITY_ACTORS
        for act in res["activities"]:
            self.assertIn(act["actor"], expected_actors, f"Activity actor {act['actor']} is not in strict set")

        # Verify filtering by 'other' and 'user'
        other_res = client.get("/api/plugins/zerofactory/activities?actor=other").json()
        self.assertTrue(other_res["ok"])
        for act in other_res["activities"]:
            self.assertEqual(act["actor"], "other")

        # Verify comment attribution: explicit author="user" stays user even with agent-like prefixes
        c_user = client.post("/api/plugins/zerofactory/tasks/t-actor-1/comments", json={
            "author": "user",
            "body": "Round 2 review complete: human operator verified manual test"
        }).json()
        self.assertTrue(c_user["ok"])
        with get_db_conn() as conn:
            c = conn.cursor()
            c.execute("SELECT author FROM task_comments WHERE id = ?", (c_user["id"],))
            self.assertEqual(c.fetchone()["author"], "user")
            c.execute("SELECT actor FROM task_activity WHERE task_id = 't-actor-1' AND action = 'comment' ORDER BY id DESC LIMIT 1")
            self.assertEqual(c.fetchone()["actor"], "user")

        # Verify comment attribution: omitted author with HERMES_PROFILE=zf-builder credits zf-builder
        orig_prof = os.environ.get("HERMES_PROFILE")
        try:
            os.environ["HERMES_PROFILE"] = "zf-builder"
            c_builder = client.post("/api/plugins/zerofactory/tasks/t-actor-1/comments", json={
                "body": "Implemented unit tests and validated"
            }).json()
            self.assertTrue(c_builder["ok"])
            with get_db_conn() as conn:
                c = conn.cursor()
                c.execute("SELECT author FROM task_comments WHERE id = ?", (c_builder["id"],))
                self.assertEqual(c.fetchone()["author"], "zf-builder")
                c.execute("SELECT actor FROM task_activity WHERE task_id = 't-actor-1' AND action = 'comment' ORDER BY id DESC LIMIT 1")
                self.assertEqual(c.fetchone()["actor"], "zf-builder")
        finally:
            if orig_prof is not None:
                os.environ["HERMES_PROFILE"] = orig_prof
            else:
                os.environ.pop("HERMES_PROFILE", None)


class TestSharedProfilePathResolution(unittest.TestCase):
    """Dedup + correctness tests for the shared profile-path / assignee helpers
    (``paths.py``) and that both the dispatcher and the dashboard consume the
    SAME single source of truth (no more divergent copies).

    These tests exercise the resolution strategy hermetically by pointing
    ``Path.home()`` and the plugin-relative profiles root at a controlled temp
    tree, so each branch (per-profile -> legacy-un-prefixed -> plugin-relative
    -> global -> None) is asserted in isolation.
    """

    def _mk(self, base: Path, *parts: str) -> Path:
        """Create ``base/parts...`` (parents included) and return the file path."""
        p = base.joinpath(*parts)
        p.parent.mkdir(parents=True, exist_ok=True)
        p.touch(exist_ok=True)
        return p

    def _with_fake_home(self, home_root: Path, plugin_root):
        """Context manager that points ``paths.Path.home`` at ``home_root`` and
        the plugin-relative root at ``plugin_root`` (which may be ``None``).
        Returns two context managers that the caller enters with ``with``."""
        import paths as P
        from unittest import mock
        return (
            mock.patch("pathlib.Path.home", return_value=home_root),
            mock.patch.object(P, "_plugin_profiles_root", return_value=plugin_root),
        )

    # --- state.db resolution strategy --------------------------------------

    def test_74_state_db_per_profile(self):
        """Per-profile path wins when it exists (primary layout)."""
        from unittest import mock
        import paths as P
        with tempfile.TemporaryDirectory() as td:
            home_root = Path(td) / "home"
            self._mk(home_root, ".hermes", "profiles", "zf-builder", "state.db")
            home_ctx, plug_ctx = self._with_fake_home(home_root, plugin_root=None)
            with home_ctx, plug_ctx:
                self.assertEqual(
                    P.resolve_profile_state_db("zf-builder"),
                    home_root / ".hermes" / "profiles" / "zf-builder" / "state.db",
                )

    def test_75_state_db_plugin_relative_fallback(self):
        """Plugin-relative fallback is returned when ONLY that exists — the
        exact case the old dispatcher's inline copy silently missed (it skipped
        straight to the global ~/.hermes/state.db and read the wrong DB)."""
        from unittest import mock
        import paths as P
        with tempfile.TemporaryDirectory() as td:
            home_root = Path(td) / "home"
            plugin_root = Path(td) / "plugin_profiles"
            # No per-profile, no legacy, no global; only the plugin-relative one.
            self._mk(plugin_root, "zf-builder", "state.db")
            home_ctx, plug_ctx = self._with_fake_home(home_root, plugin_root=plugin_root)
            with home_ctx, plug_ctx:
                self.assertEqual(
                    P.resolve_profile_state_db("zf-builder"),
                    plugin_root / "zf-builder" / "state.db",
                )

    def test_76_state_db_global_fallback_and_none(self):
        """Global ~/.hermes/state.db is the last resort, and None when nothing
        exists anywhere."""
        from unittest import mock
        import paths as P
        with tempfile.TemporaryDirectory() as td:
            home_root = Path(td) / "home"
            self._mk(home_root, ".hermes", "state.db")
            home_ctx, plug_ctx = self._with_fake_home(home_root, plugin_root=None)
            with home_ctx, plug_ctx:
                self.assertEqual(
                    P.resolve_profile_state_db("zf-builder"),
                    home_root / ".hermes" / "state.db",
                )

        # Nothing present -> None.
        with tempfile.TemporaryDirectory() as td:
            home_root = Path(td) / "home"  # empty
            home_ctx, plug_ctx = self._with_fake_home(home_root, plugin_root=None)
            with home_ctx, plug_ctx:
                self.assertIsNone(P.resolve_profile_state_db("zf-builder"))

    def test_77_state_db_legacy_unprefixed_and_priority(self):
        """Legacy un-prefixed profile dir is honored, and priority is
        per-profile > legacy > plugin-relative > global."""
        from unittest import mock
        import paths as P
        # Legacy un-prefixed "builder" is used when canonical "zf-builder" absent.
        with tempfile.TemporaryDirectory() as td:
            home_root = Path(td) / "home"
            self._mk(home_root, ".hermes", "profiles", "builder", "state.db")
            home_ctx, plug_ctx = self._with_fake_home(home_root, plugin_root=None)
            with home_ctx, plug_ctx:
                self.assertEqual(
                    P.resolve_profile_state_db("zf-builder"),
                    home_root / ".hermes" / "profiles" / "builder" / "state.db",
                )

        # Priority: canonical beats plugin-relative beats global.
        with tempfile.TemporaryDirectory() as td:
            home_root = Path(td) / "home"
            plugin_root = Path(td) / "plugin_profiles"
            self._mk(home_root, ".hermes", "state.db")
            self._mk(plugin_root, "zf-builder", "state.db")
            self._mk(home_root, ".hermes", "profiles", "zf-builder", "state.db")
            home_ctx, plug_ctx = self._with_fake_home(home_root, plugin_root=plugin_root)
            with home_ctx, plug_ctx:
                self.assertEqual(
                    P.resolve_profile_state_db("zf-builder"),
                    home_root / ".hermes" / "profiles" / "zf-builder" / "state.db",
                )
            # Remove the canonical one; plugin-relative now wins over global.
            (home_root / ".hermes" / "profiles" / "zf-builder" / "state.db").unlink()
            with home_ctx, plug_ctx:
                self.assertEqual(
                    P.resolve_profile_state_db("zf-builder"),
                    plugin_root / "zf-builder" / "state.db",
                )

    # --- assignee normalization --------------------------------------------

    def test_78_normalize_assignee_roundtrip_and_unknown(self):
        """Round-trips the three profiles, maps unassigned/None/empty to
        unassigned, and maps UNKNOWN assignees to unassigned (single source)."""
        import paths as P
        self.assertEqual(P.normalize_assignee("zf-builder"), "zf-builder")
        self.assertEqual(P.normalize_assignee("zf-reviewer"), "zf-reviewer")
        self.assertEqual(P.normalize_assignee("zf-orchestrator"), "zf-orchestrator")
        self.assertEqual(P.normalize_assignee("unassigned"), "unassigned")
        self.assertEqual(P.normalize_assignee(None), "unassigned")
        self.assertEqual(P.normalize_assignee(""), "unassigned")
        # Unknown assignees are not valid specialist profiles -> unassigned.
        self.assertEqual(P.normalize_assignee("antigravity"), "unassigned")
        self.assertEqual(P.normalize_assignee("some-custom-tool"), "unassigned")

    def test_79_dispatcher_and_dashboard_agree(self):
        """The dispatcher's spawn-path resolver and the dashboard's
        get_profile_state_db agree on the SAME fixture layout (single source of
        truth)."""
        from unittest import mock
        import paths as P
        import dispatcher as D
        from dashboard.plugin_api import get_profile_state_db
        with tempfile.TemporaryDirectory() as td:
            home_root = Path(td) / "home"
            plugin_root = Path(td) / "plugin_profiles"
            self._mk(plugin_root, "zf-reviewer", "state.db")
            home_ctx, plug_ctx = self._with_fake_home(home_root, plugin_root=plugin_root)
            with home_ctx, plug_ctx:
                expected = plugin_root / "zf-reviewer" / "state.db"
                self.assertEqual(D.resolve_profile_state_db("zf-reviewer"), expected)
                self.assertEqual(get_profile_state_db("zf-reviewer"), expected)
                # The two surfaces must return the identical path.
                self.assertEqual(
                    D.resolve_profile_state_db("zf-reviewer"),
                    get_profile_state_db("zf-reviewer"),
                )
                # And the dashboard wrapper must BE the shared helper (not a
                # re-implemented copy).
                self.assertIs(D.resolve_profile_state_db, P.resolve_profile_state_db)
                self.assertEqual(get_profile_state_db("zf-reviewer"), P.resolve_profile_state_db("zf-reviewer"))

    def test_80_single_source_of_truth_identity(self):
        """dispatcher and dashboard re-export the SAME objects from paths.py —
        no duplicated PROFILE_MAP / normalize_assignee to drift apart."""
        import paths as P
        import dispatcher as D
        from dashboard.plugin_api import (
            PROFILE_MAP as PA_PROFILE_MAP,
            VALID_ASSIGNEES as PA_VALID_ASSIGNEES,
            normalize_assignee as PA_normalize_assignee,
        )
        self.assertIs(D.PROFILE_MAP, P.PROFILE_MAP)
        self.assertIs(PA_PROFILE_MAP, P.PROFILE_MAP)
        self.assertIs(D.normalize_assignee, P.normalize_assignee)
        self.assertIs(PA_normalize_assignee, P.normalize_assignee)
        self.assertIs(PA_VALID_ASSIGNEES, P.VALID_ASSIGNEES)
        self.assertCountEqual(
            PA_VALID_ASSIGNEES,
            {"unassigned", "zf-builder", "zf-reviewer", "zf-orchestrator"},
        )
        self.assertCountEqual(
            D.VALID_PROFILES,
            {"zf-builder", "zf-reviewer", "zf-orchestrator"},
        )
        self.assertNotIn("unassigned", D.VALID_PROFILES)

    def test_81_cron_scheduler_disabled_in_config(self):
        """Verify that the cron scheduler can be disabled via config.yaml, settings table, and env."""
        import tempfile
        import sqlite3
        import yaml
        from unittest.mock import patch, MagicMock
        from builtin_cron import (
            is_cron_scheduler_enabled,
            tick_builtin_cron,
            toggle_builtin_job,
            ensure_builtin_cron_jobs,
            load_jobs_from_file,
            save_jobs_to_file,
        )
        from dispatcher import spawn_board_scanner
        import settings

        # 1. Verify default is enabled
        with patch.dict(os.environ, {}, clear=False):
            os.environ.pop("ZEROFACTORY_ENABLE_CRON_SCHEDULER", None)
            os.environ.pop("ZEROFACTORY_DISABLE_CRON_SCHEDULER", None)
            os.environ.pop("HERMES_CRON_ENABLED", None)
            os.environ.pop("ZEROFACTORY_CONFIG_FILE", None)
            self.assertTrue(is_cron_scheduler_enabled())

        # 2. Environment variable overrides
        with patch.dict(os.environ, {"ZEROFACTORY_ENABLE_CRON_SCHEDULER": "0"}):
            self.assertFalse(is_cron_scheduler_enabled())
        with patch.dict(os.environ, {"ZEROFACTORY_ENABLE_CRON_SCHEDULER": "false"}):
            self.assertFalse(is_cron_scheduler_enabled())
        with patch.dict(os.environ, {"ZEROFACTORY_DISABLE_CRON_SCHEDULER": "1"}):
            self.assertFalse(is_cron_scheduler_enabled())
        with patch.dict(os.environ, {"HERMES_CRON_ENABLED": "0"}):
            self.assertFalse(is_cron_scheduler_enabled())

        # 3. Settings table in DB
        with tempfile.NamedTemporaryFile(suffix=".db") as tf:
            with sqlite3.connect(tf.name) as conn:
                conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT, updated_at INTEGER)")
                conn.execute("INSERT INTO settings VALUES ('enable_cron_scheduler', 'false', 1000)")
                conn.commit()
                self.assertFalse(is_cron_scheduler_enabled(conn))

                # Verify settings module parses it
                loaded = settings.load_settings(conn)
                self.assertFalse(loaded["enable_cron_scheduler"])

                # Update to true
                conn.execute("UPDATE settings SET value = 'true' WHERE key = 'enable_cron_scheduler'")
                conn.commit()
                self.assertTrue(is_cron_scheduler_enabled(conn))

        # 4. config.yaml variations
        configs_to_test = [
            {"cron": {"enabled": False}},
            {"cron": {"scheduler": False}},
            {"cron": {"scheduler": {"enabled": False}}},
            {"cron": False},
            {"plugins": {"entries": {"zerofactory": {"cron_scheduler": False}}}},
            {"plugins": {"entries": {"zerofactory": {"enable_cron_scheduler": False}}}},
        ]
        for cfg_data in configs_to_test:
            with tempfile.NamedTemporaryFile(mode="w+", suffix=".yaml") as yf:
                yaml.dump(cfg_data, yf)
                yf.flush()
                with patch.dict(os.environ, {"ZEROFACTORY_CONFIG_FILE": yf.name}):
                    self.assertFalse(is_cron_scheduler_enabled(), f"Failed for config: {cfg_data}")

        # 5. tick_builtin_cron skips execution when disabled
        mock_cron_mod = MagicMock()
        with patch.dict(sys.modules, {"cron": MagicMock(), "cron.scheduler": mock_cron_mod}):
            with patch("builtin_cron.is_cron_scheduler_enabled", return_value=False):
                result = tick_builtin_cron()
                self.assertEqual(result, 0)
                mock_cron_mod.tick.assert_not_called()

            with patch("builtin_cron.is_cron_scheduler_enabled", return_value=True):
                mock_cron_mod.tick.return_value = 2
                result = tick_builtin_cron()
                self.assertEqual(result, 2)
                mock_cron_mod.tick.assert_called()

        # 6. spawn_board_scanner returns None when disabled
        with patch.dict(os.environ, {"ZEROFACTORY_SKIP_WORKER_SPAWN": "", "ZEROFACTORY_SKIP_SCANNER_SPAWN": ""}):
            with patch("builtin_cron.is_cron_scheduler_enabled", return_value=False):
                with patch("subprocess.Popen") as mock_popen:
                    pid = spawn_board_scanner("test-board")
                    self.assertIsNone(pid)
                    mock_popen.assert_not_called()

        # 7. Preserving custom_config when toggling job enabled status
        with tempfile.NamedTemporaryFile(suffix=".json") as jf:
            jobs_path = Path(jf.name)
            initial_jobs = [
                {
                    "id": "zero-factory-task-queue-check",
                    "name": "Queue Check",
                    "schedule": {"kind": "interval", "minutes": 120},
                    "enabled": True,
                    "state": "scheduled",
                    "custom_config": False,
                }
            ]
            save_jobs_to_file(jobs_path, initial_jobs)
            with patch("builtin_cron.get_target_jobs_files", return_value=[jobs_path]), \
                 patch.dict(os.environ, {"ZEROFACTORY_CRON_JOBS_FILE": str(jobs_path)}):
                # Toggle to disabled
                res = toggle_builtin_job("zero-factory-task-queue-check", enabled=False)
                self.assertTrue(res["ok"])
                saved = load_jobs_from_file(jobs_path)
                self.assertFalse(saved[0]["enabled"])
                self.assertEqual(saved[0]["state"], "paused")
                self.assertTrue(saved[0]["custom_config"])

                # ensure_builtin_cron_jobs should preserve the paused state because custom_config is True
                ensure_builtin_cron_jobs()
                saved_after_sync = load_jobs_from_file(jobs_path)
                self.assertFalse(saved_after_sync[0]["enabled"])
                self.assertEqual(saved_after_sync[0]["state"], "paused")

    def test_82_settings_api_enable_cron_scheduler(self):
        """Verify GET /settings and PATCH /settings handle enable_cron_scheduler."""
        # 1. Update setting via PATCH
        resp = client.patch("/api/plugins/zerofactory/settings", json={"enable_cron_scheduler": False})
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertFalse(data["settings"]["enable_cron_scheduler"])

        # 2. Verify via GET
        resp_get = client.get("/api/plugins/zerofactory/settings")
        self.assertEqual(resp_get.status_code, 200)
        self.assertFalse(resp_get.json()["settings"]["enable_cron_scheduler"])

        # 3. Restore to True
        resp_restore = client.patch("/api/plugins/zerofactory/settings", json={"enable_cron_scheduler": True})
        self.assertEqual(resp_restore.status_code, 200)
        self.assertTrue(resp_restore.json()["settings"]["enable_cron_scheduler"])

    def test_83_cron_config_ui_scheduler_toggle_and_job_pause(self):
        """Verify scheduler toggle endpoint and that paused jobs remain paused across sync and dispatcher."""
        from unittest.mock import patch
        from builtin_cron import get_target_jobs_files, ensure_builtin_cron_jobs, load_jobs_from_file
        from dispatcher import spawn_board_scanner

        # 1. GET /cron returns scheduler_enabled
        resp = client.get("/api/plugins/zerofactory/cron")
        self.assertEqual(resp.status_code, 200)
        data = resp.json()
        self.assertIn("scheduler_enabled", data)
        self.assertTrue(data["scheduler_enabled"])

        # 2. Toggle scheduler off via POST /cron/scheduler/toggle
        resp_toggle_off = client.post("/api/plugins/zerofactory/cron/scheduler/toggle", json={"enabled": False})
        self.assertEqual(resp_toggle_off.status_code, 200)
        self.assertFalse(resp_toggle_off.json()["scheduler_enabled"])

        # Verify reflected in GET /cron
        resp2 = client.get("/api/plugins/zerofactory/cron")
        self.assertFalse(resp2.json()["scheduler_enabled"])

        # Toggle scheduler back on
        resp_toggle_on = client.post("/api/plugins/zerofactory/cron/scheduler/toggle", json={"enabled": True})
        self.assertEqual(resp_toggle_on.status_code, 200)
        self.assertTrue(resp_toggle_on.json()["scheduler_enabled"])

        # 3. Test job pause persistence in cron jobs file
        with tempfile.NamedTemporaryFile(suffix=".json") as jf:
            jobs_path = Path(jf.name)
            with patch("builtin_cron.get_target_jobs_files", return_value=[jobs_path]), \
                 patch.dict(os.environ, {"ZEROFACTORY_CRON_JOBS_FILE": str(jobs_path)}):
                # Ensure jobs are registered
                ensure_builtin_cron_jobs()

                # Toggle zero-factory-task-queue-check to disabled
                resp_job_toggle = client.post(
                    "/api/plugins/zerofactory/cron/zero-factory-task-queue-check/toggle",
                    json={"enabled": False}
                )
                self.assertEqual(resp_job_toggle.status_code, 200)
                self.assertTrue(resp_job_toggle.json()["ok"])

                # Verify GET /cron still shows it as paused (ensure_builtin_cron_jobs called inside GET /cron must not re-enable it!)
                resp_after_get = client.get("/api/plugins/zerofactory/cron")
                job_state = next(j for j in resp_after_get.json()["jobs"] if j["id"] == "zero-factory-task-queue-check")
                self.assertFalse(job_state["enabled"])
                self.assertEqual(job_state["state"], "paused")

                # Verify scanner job pause prevents spawn_board_scanner without re-enabling
                # First pause scanner job
                scanner_id = "zero-factory-improvement-scanner-test-board"
                from builtin_cron import update_builtin_job
                update_builtin_job(scanner_id, {"enabled": False})
                with patch.dict(os.environ, {"ZEROFACTORY_SKIP_WORKER_SPAWN": "", "ZEROFACTORY_SKIP_SCANNER_SPAWN": ""}):
                    with patch("subprocess.Popen") as mock_popen:
                        pid = spawn_board_scanner("test-board")
                        self.assertIsNone(pid)
                        mock_popen.assert_not_called()

                # Verify scanner job is STILL paused and was NOT force-unpaused by spawn_board_scanner
                saved_jobs = load_jobs_from_file(jobs_path)
                scanner_saved = next((j for j in saved_jobs if j.get("id") == scanner_id), None)
                if scanner_saved:
                    self.assertFalse(scanner_saved["enabled"])
                    self.assertEqual(scanner_saved["state"], "paused")

    def test_84_set_cron_scheduler_enabled_persists_to_conn(self):
        """Regression: set_cron_scheduler_enabled(...) with a caller-provided
        connection must COMMIT so the setting is durable on disk.

        Prior to the fix, the ``conn is not None`` branch executed the
        ``INSERT OR REPLACE`` but never called ``conn.commit()``, so the write
        only survived if the caller happened to commit its own connection (the
        dashboard endpoints do). Any other caller — or any read of the on-disk
        state through a fresh connection — would still see the previous value.
        The ``db_path`` branch and the function's documented "persist the
        scheduler enabled state to database settings" contract both require the
        commit, so this test pins the durable-write behavior.
        """
        import sqlite3
        from unittest.mock import patch
        from builtin_cron import set_cron_scheduler_enabled

        with tempfile.NamedTemporaryFile(suffix=".db") as tf:
            dbfile = Path(tf.name)
            conn = sqlite3.connect(str(dbfile))
            conn.execute(
                "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT, updated_at INTEGER)"
            )
            # Seed the default (enabled) state and flush it to disk.
            conn.execute(
                "INSERT INTO settings VALUES ('enable_cron_scheduler', 'true', 1000)"
            )
            conn.commit()

            # Point the module at hermetic targets so the jobs-file sync loop
            # (which runs after the DB write) never touches live profile stores.
            with tempfile.NamedTemporaryFile(suffix=".json") as jf:
                jobs_path = Path(jf.name)
                with patch.dict(
                    os.environ,
                    {
                        "ZEROFACTORY_DB": str(dbfile),
                        "ZEROFACTORY_CRON_JOBS_FILE": str(jobs_path),
                    },
                ):
                    # Disable via the caller-provided-connection branch. Crucially we
                    # do NOT commit ourselves here — the function is responsible for
                    # persisting the write.
                    res = set_cron_scheduler_enabled(False, conn=conn)
                    self.assertTrue(res["ok"])
                    self.assertFalse(res["scheduler_enabled"])

                    # A fresh, independent connection (what the rest of the system
                    # sees) must observe the new on-disk value. This is the
                    # RED->GREEN discriminator: with the missing commit, this read
                    # returned the stale 'true' (or None) instead of 'false'.
                    conn2 = sqlite3.connect(str(dbfile))
                    try:
                        row = conn2.execute(
                            "SELECT value FROM settings WHERE key='enable_cron_scheduler'"
                        ).fetchone()
                    finally:
                        conn2.close()
                    self.assertIsNotNone(row, "enable_cron_scheduler row must exist on disk")
                    self.assertEqual(row[0], "false")

                    # Re-enable and confirm it persists again through the same branch.
                    res_on = set_cron_scheduler_enabled(True, conn=conn)
                    self.assertTrue(res_on["ok"])
                    self.assertTrue(res_on["scheduler_enabled"])
                    conn3 = sqlite3.connect(str(dbfile))
                    try:
                        row_on = conn3.execute(
                            "SELECT value FROM settings WHERE key='enable_cron_scheduler'"
                        ).fetchone()
                    finally:
                        conn3.close()
                    self.assertIsNotNone(row_on)
                    self.assertEqual(row_on[0], "true")

            conn.close()

    def test_85_update_builtin_job_field_update_semantics(self):
        """update_builtin_job field-update semantics live in a single helper
        shared by both the existing-job and new-job branches."""
        import builtin_cron
        from builtin_cron import (
            update_builtin_job, save_jobs_to_file, load_jobs_from_file,
        )
        import builtin_cron as _bc
        _ensure_builtin_cron_jobs = _bc.ensure_builtin_cron_jobs
        _reset_builtin_job = _bc.reset_builtin_job

        job_id = "zero-factory-task-queue-check"

        with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as tf:
            existing_target = Path(tf.name)
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as tf:
            new_job_target = Path(tf.name)

        orig_override = os.environ.get("ZEROFACTORY_CRON_JOBS_FILE")
        try:
            # ---- Existing-job branch ------------------------------------
            os.environ["ZEROFACTORY_CRON_JOBS_FILE"] = str(existing_target)
            base = {
                "id": job_id,
                "name": "Zero Factory task queue check",
                "schedule": {"kind": "interval", "minutes": 120, "display": "every 120m"},
                "schedule_display": "every 120m",
                "enabled": True,
                "state": "scheduled",
                "model": "orig-model",
                "prompt": "Original prompt",
            }

            # Interval via minutes sets schedule, display and custom_config
            save_jobs_to_file(existing_target, [dict(base)])
            res = update_builtin_job(job_id, {"minutes": 45})
            self.assertTrue(res["ok"])
            j = load_jobs_from_file(existing_target)[0]
            self.assertEqual(j["schedule"], {"kind": "interval", "minutes": 45, "display": "every 45m"})
            self.assertEqual(j["schedule_display"], "every 45m")
            self.assertTrue(j["custom_config"])

            # Cron via cron_expr (whitespace stripped)
            res = update_builtin_job(job_id, {"cron_expr": "  */15 * * * *  "})
            self.assertTrue(res["ok"])
            j = load_jobs_from_file(existing_target)[0]
            self.assertEqual(j["schedule"], {"kind": "cron", "expr": "*/15 * * * *", "display": "*/15 * * * *"})
            self.assertEqual(j["schedule_display"], "*/15 * * * *")
            self.assertTrue(j["custom_config"])

            # Invalid minutes value is ignored: schedule untouched,
            # no custom_config flagging from the bad update
            save_jobs_to_file(existing_target, [dict(base)])
            res = update_builtin_job(job_id, {"minutes": "not-a-number"})
            self.assertTrue(res["ok"])
            j = load_jobs_from_file(existing_target)[0]
            self.assertEqual(j["schedule"], base["schedule"])
            self.assertFalse(j.get("custom_config"))

            # context_from: str is normalized to a single-element list
            res = update_builtin_job(job_id, {"context_from": "upstream-job"})
            j = load_jobs_from_file(existing_target)[0]
            self.assertEqual(j["context_from"], ["upstream-job"])
            self.assertTrue(j["custom_config"])

            # context_from: list passthrough with strip and empty-drop
            res = update_builtin_job(job_id, {"context_from": ["  a  ", "", "b"]})
            j = load_jobs_from_file(existing_target)[0]
            self.assertEqual(j["context_from"], ["a", "b"])
            self.assertTrue(j["custom_config"])

            # context_from: empty list normalizes to None
            res = update_builtin_job(job_id, {"context_from": []})
            j = load_jobs_from_file(existing_target)[0]
            self.assertIsNone(j["context_from"])
            self.assertTrue(j["custom_config"])

            # Each remaining field sets custom_config when applied
            save_jobs_to_file(existing_target, [dict(base)])
            res = update_builtin_job(job_id, {
                "model": " new-model ",
                "workdir": "/tmp/zf-test-workdir",
                "prompt": "New prompt",
                "no_agent": True,
                "continuity": True,
            })
            self.assertTrue(res["ok"])
            j = load_jobs_from_file(existing_target)[0]
            self.assertEqual(j["model"], "new-model")
            self.assertEqual(j["workdir"], "/tmp/zf-test-workdir")
            self.assertEqual(j["prompt"], "New prompt")
            self.assertIs(j["no_agent"], True)
            self.assertIs(j["continuity"], True)
            self.assertTrue(j["custom_config"])

            # name is applied and sets custom_config so a custom rename
            # survives periodic ensure_builtin_cron_jobs() syncs
            save_jobs_to_file(existing_target, [dict(base)])
            res = update_builtin_job(job_id, {"name": "Renamed job"})
            j = load_jobs_from_file(existing_target)[0]
            self.assertEqual(j["name"], "Renamed job")
            self.assertTrue(j.get("custom_config"))

            # enabled toggle drives state + paused_at both directions
            res = update_builtin_job(job_id, {"enabled": False})
            j = load_jobs_from_file(existing_target)[0]
            self.assertFalse(j["enabled"])
            self.assertEqual(j["state"], "paused")
            self.assertIsNotNone(j["paused_at"])
            res = update_builtin_job(job_id, {"enabled": True})
            j = load_jobs_from_file(existing_target)[0]
            self.assertTrue(j["enabled"])
            self.assertEqual(j["state"], "scheduled")
            self.assertIsNone(j["paused_at"])

            # ---- Sync-survival regression: a custom rename must not be
            # reverted by the periodic ensure_builtin_cron_jobs() sync
            # (rename flags custom_config; sync skips customised fields).
            with tempfile.NamedTemporaryFile(mode="w+", suffix=".json", delete=False) as tf:
                sync_target = Path(tf.name)
            orig_targets = builtin_cron.get_target_jobs_files
            builtin_cron.get_target_jobs_files = lambda: [sync_target]
            orig_skip = os.environ.pop("ZEROFACTORY_SKIP_CRON_SYNC", None)
            orig_cjf = os.environ.pop("ZEROFACTORY_CRON_JOBS_FILE", None)
            try:
                # Fresh store: sync instantiates the job from builtin_def
                _ensure_builtin_cron_jobs()
                j = load_jobs_from_file(sync_target)[0]
                self.assertEqual(j["name"], "Zero Factory task queue check")
                self.assertFalse(j.get("custom_config"))

                # User renames the job via the update endpoint
                res = update_builtin_job(job_id, {"name": "My renamed queue check"})
                j = load_jobs_from_file(sync_target)[0]
                self.assertEqual(j["name"], "My renamed queue check")
                self.assertTrue(j.get("custom_config"))

                # Next periodic sync keeps the custom name
                _ensure_builtin_cron_jobs()
                j = load_jobs_from_file(sync_target)[0]
                self.assertEqual(j["name"], "My renamed queue check")
                self.assertTrue(j.get("custom_config"))

                # Reset restores the canonical name and clears custom_config
                res = _reset_builtin_job(job_id)
                self.assertTrue(res["ok"])
                j = load_jobs_from_file(sync_target)[0]
                self.assertEqual(j["name"], "Zero Factory task queue check")
                self.assertFalse(j.get("custom_config"))
            finally:
                if orig_skip is not None:
                    os.environ["ZEROFACTORY_SKIP_CRON_SYNC"] = orig_skip
                if orig_cjf is not None:
                    os.environ["ZEROFACTORY_CRON_JOBS_FILE"] = orig_cjf
                builtin_cron.get_target_jobs_files = orig_targets
                if sync_target.exists():
                    sync_target.unlink()

            # ---- New-job branch (instantiate from builtin_def) ----------
            os.environ["ZEROFACTORY_CRON_JOBS_FILE"] = str(new_job_target)
            save_jobs_to_file(new_job_target, [])  # exists, but job absent
            res = update_builtin_job(job_id, {
                "minutes": 30,
                "context_from": "upstream-job",
                "model": "new-model",
                "enabled": False,
            })
            self.assertTrue(res["ok"])
            jobs = load_jobs_from_file(new_job_target)
            self.assertEqual(len(jobs), 1)
            j = jobs[0]
            self.assertEqual(j["id"], job_id)
            self.assertIn("created_at", j)
            # Same semantics as the existing-job branch
            self.assertEqual(j["schedule"], {"kind": "interval", "minutes": 30, "display": "every 30m"})
            self.assertEqual(j["schedule_display"], "every 30m")
            self.assertEqual(j["context_from"], ["upstream-job"])
            self.assertEqual(j["model"], "new-model")
            self.assertFalse(j["enabled"])
            self.assertEqual(j["state"], "paused")
            self.assertIsNotNone(j["paused_at"])
            self.assertTrue(j["custom_config"])
        finally:
            if orig_override is not None:
                os.environ["ZEROFACTORY_CRON_JOBS_FILE"] = orig_override
            else:
                os.environ.pop("ZEROFACTORY_CRON_JOBS_FILE", None)
            for p in (existing_target, new_job_target):
                if p.exists():
                    p.unlink()

    # ---- Dashboard stylesheet: portability & CSS/JS class agreement --------

    @staticmethod
    def _zf_css_selectors(tokens):
        """Render the escaped class-selector strings a build would emit.

        Mirrors the escaping Tailwind v4 applies when turning a class into a
        selector (e.g. hover:bg-slate-800 -> .hover\\:bg-slate-800).
        """
        out = []
        for tok in tokens:
            esc = "."
            for ch in tok:
                if ch in ":/.[]":
                    esc += "\\" + ch
                else:
                    esc += ch
            out.append(esc)
        return out

    @staticmethod
    def _zf_js_class_tokens(source):
        """Extract the utility class tokens referenced in dashboard JS source.

        Character-level lexer (mirrors dashboard/build_css.mjs's
        extractCandidates): skips line/block comments and only honours quote
        characters in code position, with backslash escapes. This matters
        because dist/index.js contains a line comment with an embedded
        apostrophe (``// Bottom row: Today's actions``) — a naive
        ``[^"]*``/``[^']*`` quote regex starts a phantom string at that
        apostrophe, swallows ~140KB of source, and silently drops every
        className literal after it (e.g. hover:bg-slate-800/80).
        """
        import re
        token_charset = re.compile(r"[A-Za-z0-9_:\[\]/%#!.-]+")
        strings = []
        i = 0
        n = len(source)
        while i < n:
            ch = source[i]
            if ch == "/" and i + 1 < n and source[i + 1] == "/":  # line comment
                e = source.find("\n", i)
                i = n if e == -1 else e + 1
            elif ch == "/" and i + 1 < n and source[i + 1] == "*":  # block comment
                e = source.find("*/", i + 2)
                i = n if e == -1 else e + 2
            elif ch in ("'", '"', "`"):
                j = i + 1
                while j < n:
                    if source[j] == "\\":
                        j += 2
                        continue
                    if source[j] == ch:
                        j += 1
                        break
                    j += 1
                strings.append(source[i + 1 : j - 1])
                i = j
            else:
                i += 1
        tokens = set()
        for s in strings:
            for tok in s.split():
                if len(tok) >= 2 and re.fullmatch(token_charset, tok) and re.search(
                    r"[a-z]", tok
                ) and not tok.startswith("//"):
                    tokens.add(tok)
        return tokens

    def test_86_dashboard_css_is_portable_and_in_sync_with_js(self):
        """The committed dashboard stylesheet must (a) contain no
        machine-specific absolute paths, (b) carry selectors for every
        variant-prefixed class the UI JS references, and (c) reproduce
        byte-identically under `node dashboard/build_css.mjs` when node +
        tailwindcss are available.

        Regression for the stale-stylesheet bug: hover/focus-within/active/
        disabled variant classes were used by dist/index.js but silently
        absent from the committed dist/style.css.
        """
        import re
        import shutil
        import subprocess

        dash = Path(__file__).resolve().parent / "dashboard"
        input_css = (dash / "input.css").read_text()
        style_css = (dash / "dist" / "style.css").read_text()
        js_src = (dash / "dist" / "index.js").read_text()

        # (a) No machine-specific absolute paths anywhere in the sources.
        for label, text in (("input.css", input_css), ("style.css", style_css)):
            self.assertNotRegex(
                text, r"/home/|/Users/|C:\\",
                f"{label} must not hard-code absolute machine-specific paths",
            )

        # (b) Every variant-prefixed class token used by the UI JS has a
        #     selector in the committed stylesheet.
        # (b0) Extraction regression: dist/index.js contains a line comment
        #      with an embedded apostrophe ("// Bottom row: Today's actions").
        #      A naive [^"]*/[^']* quote scan starts a phantom single-quoted
        #      string at that apostrophe that runs to the next bare apostrophe
        #      in the file, swallowing the className literals in between
        #      (their surrounding double quotes become part of the phantom
        #      string content, polluting every token — e.g.
        #      hover:bg-slate-800/80" is no longer a valid candidate). The
        #      lexer must skip line comments and find the className literal.
        synth = (
            "// Bottom row: Today's actions & quick filter\n"
            'React.createElement("div", { className: '
            '"text-slate-400 hover:bg-slate-800/80" });\n'
            "// don't forget to verify the hover state\n"
        )
        self.assertIn("hover:bg-slate-800/80", self._zf_js_class_tokens(synth))
        variant_stack = re.compile(
            r"^(?:hover|focus|focus-within|active|disabled|group-hover|md|lg|sm|xl|2xl):"
        )
        tokens = self._zf_js_class_tokens(js_src)
        variant_tokens = [t for t in tokens if variant_stack.match(t)]
        self.assertGreaterEqual(
            len(variant_tokens), 10,
            "expected the UI to reference many variant classes; extraction "
            "looks broken",
        )
        missing = [t for t in sorted(variant_tokens)
                   if self._zf_css_selectors((t,))[0] not in style_css]
        self.assertEqual(
            missing, [],
            "dist/style.css is missing selectors for UI-referenced variant "
            "classes (run `node dashboard/build_css.mjs` to rebuild): "
            f"{missing[:10]}",
        )
        # Smoke: each interaction state family must be present at least once.
        for family in (r"\.hover\\:", r"\.focus-within\\:", r"\.active\\:",
                       r"\.disabled\\:"):
            self.assertRegex(
                style_css, family,
                f"committed stylesheet has no {family} selector",
            )

        # (c) Reproducibility: a fresh build must reproduce the committed file.
        node = shutil.which("node")
        if node is None:
            self.skipTest("node not on PATH; cannot verify CSS build "
                          "reproducibility")
        import importlib.util
        build_mjs = dash / "build_css.mjs"
        spec = importlib.util.find_spec("dashboard")  # repo root on sys.path?
        repo_root = Path(__file__).resolve().parent
        env = dict(os.environ)
        env["ZEROFACTORY_SKIP_DISPATCHER"] = "1"
        try:
            r = subprocess.run(
                [node, str(build_mjs)],
                cwd=str(repo_root), env=env,
                capture_output=True, text=True, timeout=180,
            )
        except (OSError, subprocess.SubprocessError) as e:
            self.skipTest(f"cannot run node build ({e}); skipping")
        if r.returncode != 0:
            # Build failed — if tailwindcss is simply not installed this is a
            # fresh-clone-without-npm state, which the build script reports
            # clearly. Treat a 'Cannot locate the tailwindcss package' failure
            # as an environment skip; any other failure is a real regression.
            if "Cannot locate the tailwindcss package" in (r.stderr or ""):
                self.skipTest("tailwindcss not installed; run `npm install` "
                              "to verify build reproducibility")
            self.fail(f"dashboard/build_css.mjs failed:\n{r.stdout}\n{r.stderr}")
        rebuilt = (dash / "dist" / "style.css").read_text()
        # The rebuild wrote over the committed file; compare against a pristine
        # re-read is not possible, so instead assert the rebuilt file still
        # passes (b) and that the committed content (read earlier) matches the
        # rebuild, proving the committed file IS the build output.
        self.assertEqual(
            rebuilt,
            style_css,
            "committed dist/style.css does not match the output of "
            "`node dashboard/build_css.mjs` (run the build and commit the "
            "result)",
        )
        # Final agreement check against the rebuilt file as well.
        missing2 = [t for t in sorted(variant_tokens)
                    if self._zf_css_selectors((t,))[0] not in rebuilt]
        self.assertEqual(missing2, [])

    def test_reviewer_approval_comment_classification(self):
        from dispatcher import is_reviewer_approval_comment

        # Case 1: Approval verdict from Round 1 / 2 review summaries
        r1 = (
            "[Reviewer Feedback] Round 1 (Correctness & Tests): APPROVED for human review.\n\n"
            "**Verdict: approve.** The PR systematically removes all ready-status references..."
        )
        self.assertTrue(is_reviewer_approval_comment(r1, state="COMMENTED"))

        r2 = (
            "[Reviewer Feedback] Round 2 (Performance & Edge Cases): APPROVED — no changes requested.\n\n"
            "Verdict: approve. No performance or edge-case issues found in Round 2."
        )
        self.assertTrue(is_reviewer_approval_comment(r2, state="COMMENTED"))

        # Case 2: Explicit GitHub review state APPROVED
        self.assertTrue(is_reviewer_approval_comment("Looks good", state="APPROVED"))

        # Case 3: Reviewer requesting changes
        r3 = (
            "[Reviewer Feedback] Round 1: CHANGES REQUESTED.\n\n"
            "Please fix the null pointer exception on line 45."
        )
        self.assertFalse(is_reviewer_approval_comment(r3, state="COMMENTED"))

        # Case 4: Normal human review comment
        r4 = "Could you add more comments to clarify this algorithm?"
        self.assertFalse(is_reviewer_approval_comment(r4, state="COMMENTED"))

    def test_worker_failure_retry_limit_permanently_blocks(self):
        import json, time
        from dispatcher import reap_active_workers, _active_workers
        from unittest.mock import MagicMock

        now = int(time.time())
        created = create_task(TaskCreate(title="Test Worker Failure Retries", assignee="zf-builder"))
        task_id = created["id"]

        with get_db_conn() as conn:
            conn.execute(
                "UPDATE tasks SET status = 'running', metadata = ? WHERE id = ?",
                (json.dumps({"worker_pid": 999999, "started_at": now - 10}), task_id)
            )
            conn.commit()

        # Mock a failing worker process with exit code 1
        mock_proc = MagicMock()
        mock_proc.poll.return_value = 1
        mock_proc.pid = 999999
        _active_workers[task_id] = mock_proc

        with get_db_conn() as conn:
            cur = conn.cursor()
            # Attempt 1: should move to blocked with fail_retries = 1
            reaped = reap_active_workers(cur, now)
            conn.commit()
            self.assertEqual(reaped, 1)

            row = conn.execute("SELECT status, metadata FROM tasks WHERE id = ?", (task_id,)).fetchone()
            self.assertEqual(row["status"], "blocked")
            meta = json.loads(row["metadata"])
            self.assertEqual(meta.get("worker_failure_retries"), 1)
            self.assertFalse(meta.get("permanently_blocked", False))
            self.assertIn("last_worker_failure", meta)

            # Verify task comment was added
            cmts = conn.execute("SELECT body FROM task_comments WHERE task_id = ?", (task_id,)).fetchall()
            self.assertTrue(any("Blocked:" in c["body"] for c in cmts))

            # Attempt 2: simulate another failure
            meta["worker_pid"] = 999998
            conn.execute("UPDATE tasks SET status = 'running', metadata = ? WHERE id = ?", (json.dumps(meta), task_id))
            conn.commit()

        mock_proc2 = MagicMock()
        mock_proc2.poll.return_value = 1
        _active_workers[task_id] = mock_proc2

        with get_db_conn() as conn:
            cur = conn.cursor()
            reaped = reap_active_workers(cur, now + 1)
            conn.commit()
            meta = json.loads(conn.execute("SELECT metadata FROM tasks WHERE id = ?", (task_id,)).fetchone()["metadata"])
            self.assertEqual(meta.get("worker_failure_retries"), 2)
            self.assertFalse(meta.get("permanently_blocked", False))

            # Attempt 3: reached max retries (3) -> permanently blocked!
            meta["worker_pid"] = 999997
            conn.execute("UPDATE tasks SET status = 'running', metadata = ? WHERE id = ?", (json.dumps(meta), task_id))
            conn.commit()

        mock_proc3 = MagicMock()
        mock_proc3.poll.return_value = 1
        _active_workers[task_id] = mock_proc3

        with get_db_conn() as conn:
            cur = conn.cursor()
            reaped = reap_active_workers(cur, now + 2)
            conn.commit()
            row = conn.execute("SELECT status, metadata FROM tasks WHERE id = ?", (task_id,)).fetchone()
            self.assertEqual(row["status"], "blocked")
            meta = json.loads(row["metadata"])
            self.assertEqual(meta.get("worker_failure_retries"), 3)
            self.assertTrue(meta.get("permanently_blocked"))

            # Verify activity row for permanent block
            act = conn.execute("SELECT action FROM task_activity WHERE task_id = ? AND action = 'worker_failed_permanently'", (task_id,)).fetchone()
            self.assertIsNotNone(act)

    def test_reaper_ignores_stale_builder_pid_before_reviewer_dispatch(self):
        """A builder -> reviewer handoff must not be blocked by the stopped
        builder PID persisted in legacy task metadata."""
        import json
        import time
        from unittest.mock import patch
        from dispatcher import reap_active_workers, _active_workers

        now = int(time.time())
        board_slug = "reviewer-handoff-regression"
        with get_db_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO boards (slug, description, git_url, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (board_slug, "Regression test board", "https://example.test/reviewer-handoff.git", now, now),
            )
            conn.commit()
        task_id = create_task(TaskCreate(
            title="Review stale worker handoff",
            assignee="zf-reviewer",
            board_slug=board_slug,
        ))["id"]
        stale_pid = 987654321
        metadata = {
            "worker_pid": stale_pid,
            "session_id": "builder-session",
            "started_at": now - 60,
            "sessions": [{
                "agent": "zf-builder",
                "status": "finished",
                "started_at": now - 120,
                "ended_at": now - 60,
                "pid": stale_pid,
            }],
        }

        with get_db_conn() as conn:
            conn.execute(
                "UPDATE tasks SET status = 'running', metadata = ? WHERE id = ?",
                (json.dumps(metadata), task_id),
            )
            conn.commit()

            _active_workers.pop(task_id, None)
            with patch("dispatcher.os.kill") as mock_kill:
                self.assertEqual(reap_active_workers(conn.cursor(), now), 0)
                mock_kill.assert_not_called()
            conn.commit()

            row = conn.execute(
                "SELECT status, metadata FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()

        self.assertEqual(row["status"], "running")
        metadata = json.loads(row["metadata"])
        self.assertNotIn("worker_pid", metadata)
        self.assertNotIn("session_id", metadata)
        self.assertNotIn("started_at", metadata)

    def test_reaper_recovers_orphaned_running_task_without_worker_or_session(self):
        """Tasks left in 'running' with no active process or ongoing session
        (e.g. daemon restarted during/after claim) must be recovered to 'todo'
        after the grace period rather than waiting 30 minutes."""
        import json, time
        from dispatcher import reap_active_workers, _active_workers

        now = int(time.time())
        board_slug = "reaper-orphan-recovery"
        with get_db_conn() as conn:
            conn.execute(
                "INSERT OR IGNORE INTO boards (slug, description, git_url, created_at, updated_at) VALUES (?, ?, ?, ?, ?)",
                (board_slug, "Recovery test board", "https://example.test/repo.git", now, now),
            )
            conn.commit()
        created = create_task(TaskCreate(title="Orphaned running task", assignee="zf-reviewer", board_slug=board_slug))
        task_id = created["id"]

        with get_db_conn() as conn:
            conn.execute(
                "UPDATE tasks SET status = 'running', updated_at = ?, metadata = ? WHERE id = ?",
                (now - 10, json.dumps({"sessions": []}), task_id)
            )
            conn.commit()

            _active_workers.pop(task_id, None)

            # Within grace period (< 30s): not reaped yet
            reaped = reap_active_workers(conn.cursor(), now)
            conn.commit()
            self.assertEqual(reaped, 0)
            row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
            self.assertEqual(row["status"], "running")

            # Past grace period (>= 30s): recovered to 'todo'
            reaped = reap_active_workers(conn.cursor(), now + 35)
            conn.commit()
            self.assertGreaterEqual(reaped, 1)

            row = conn.execute("SELECT status FROM tasks WHERE id = ?", (task_id,)).fetchone()
            self.assertEqual(row["status"], "todo")

            act = conn.execute(
                "SELECT action FROM task_activity WHERE task_id = ? AND action = 'worker_recovered'",
                (task_id,)
            ).fetchone()
            self.assertIsNotNone(act)

    def test_move_task_clears_failure_metadata(self):
        import json, time
        now = int(time.time())
        created = create_task(TaskCreate(title="Test Move Clears Failure", assignee="zf-builder"))
        task_id = created["id"]

        meta = {
            "worker_failure_retries": 3,
            "permanently_blocked": True,
            "blocked_reason": "Worker failed 3 times",
            "last_worker_failure": {"retcode": 1, "failed_at": now}
        }
        with get_db_conn() as conn:
            conn.execute(
                "UPDATE tasks SET status = 'blocked', metadata = ? WHERE id = ?",
                (json.dumps(meta), task_id)
            )
            conn.commit()

        # Move to todo
        res = move_task(task_id, TaskMove(status="todo", actor="user"))
        self.assertTrue(res["ok"])

        with get_db_conn() as conn:
            row = conn.execute("SELECT status, metadata FROM tasks WHERE id = ?", (task_id,)).fetchone()
            self.assertEqual(row["status"], "todo")
            new_meta = json.loads(row["metadata"])
            self.assertNotIn("last_worker_failure", new_meta)
            self.assertNotIn("permanently_blocked", new_meta)
            self.assertNotIn("worker_failure_retries", new_meta)
            self.assertNotIn("blocked_reason", new_meta)

    def test_resolve_task_session_progress_picks_latest_ongoing(self):
        import time
        from dashboard.plugin_api import resolve_task_session_progress

        now = int(time.time())
        task = {
            "id": "test-latest-session",
            "title": "Test Latest Session",
            "status": "running",
            "assignee": "zf-builder",
            "metadata": {
                "worker_pid": None,
                "started_at": now - 60,
                "sessions": [
                    {
                        "session_id": "old_sess_12h_ago",
                        "agent": "zf-builder",
                        "status": "ongoing",
                        "started_at": now - 43200,
                        "ended_at": None,
                    },
                    {
                        "session_id": "new_sess_now",
                        "agent": "zf-builder",
                        "status": "ongoing",
                        "started_at": now - 60,
                        "ended_at": None,
                    }
                ]
            }
        }

        progress = resolve_task_session_progress(task, backfill=False)
        self.assertEqual(progress["session_id"], "new_sess_now")

    # --- Regression: last_activity_at must drive stuck/idle detection --------

    def _session_progress_fixture(self, last_activity_at, worker_pid=None):
        """Build a running task + a fake state.db session row to isolate the
        inactivity (idle) computation in ``_compute_stuck_status``.

        The *session* row started 2h ago (``now - 7200``) with a configurable
        ``last_activity_at`` — this is the value the (buggy) refactor used as
        ``last_active`` (session start), which made any >15min session look
        stuck. The *task* metadata started_at is kept recent (``now - 60``) so
        the separate "exceeded running timeout" branch (default 3600s) does not
        fire and the test isolates the inactivity branch the bug actually broke.

        Returns ``(task, now, session_started, sid, last_activity_at)``.
        """
        import time
        if worker_pid is None:
            worker_pid = os.getpid()
        now = int(time.time())
        session_started = now - 7200  # session row: started 2h ago
        task = {
            "id": "zf-stuck-regression",
            "title": "Stuck Regression Task",
            "status": "running",
            "assignee": "zf-builder",
            "metadata": {
                "worker_pid": worker_pid,
                "started_at": now - 60,  # task-level start: recent (< running timeout)
                "session_id": "sess-stuck-reg",
            },
        }
        return task, now, session_started, "sess-stuck-reg", last_activity_at

    def _patch_state_db(self, db_path):
        """Patch ``resolve_profile_state_db`` in the dashboard to return the
        fake state.db for every profile, and the worker_pid liveness so a
        dead-but-existing PID still looks alive (os.kill(pid,0) on our own
        process succeeds)."""
        from unittest import mock
        import dashboard.plugin_api as D
        return mock.patch.object(D, "resolve_profile_state_db", return_value=db_path)

    def test_stuck_detection_recent_activity_not_stuck(self):
        """A session running for 2h whose last activity was 60s ago must NOT
        be classified stuck, and idle_seconds must reflect real activity."""
        import time
        from dashboard.plugin_api import resolve_task_session_progress

        now = int(time.time())
        task, now, session_started, sid, last_active = self._session_progress_fixture(now - 60)
        with tempfile.TemporaryDirectory() as td:
            db = _make_fake_state_db(
                td, "zf-builder",
                [(sid, "gpt-4", session_started, None, last_active, "active", 3, 2, "", task["title"], "zf-builder")],
            )
            with self._patch_state_db(db):
                progress = resolve_task_session_progress(task, backfill=False)

        self.assertEqual(progress["session_id"], sid)
        self.assertFalse(progress["is_stuck"], f"unexpectedly stuck: {progress.get('stuck_reason')}")
        # idle_seconds must be derived from last_activity_at (60s), not started (7200s)
        self.assertLess(progress["idle_seconds"], 120, f"idle={progress['idle_seconds']}s")
        # last_active reported to UI must be the real activity, not session start
        self.assertEqual(progress["last_active"], last_active)
        # The session dicts under sessions[] must carry last_activity_at
        for s in progress["sessions"]:
            self.assertIn("last_activity_at", s, "session dict missing last_activity_at")
        active = next(s for s in progress["sessions"] if s["session_id"] == sid)
        self.assertEqual(active["last_activity_at"], last_active)

    def test_stuck_detection_stale_activity_is_stuck(self):
        """Same session but last activity 1h ago (older than the 900s
        inactivity timeout) must be classified stuck with the inactive reason."""
        import time
        from dashboard.plugin_api import resolve_task_session_progress

        now = int(time.time())
        task, now, session_started, sid, last_active = self._session_progress_fixture(now - 3600)
        with tempfile.TemporaryDirectory() as td:
            db = _make_fake_state_db(
                td, "zf-builder",
                [(sid, "gpt-4", session_started, None, last_active, "active", 3, 2, "", task["title"], "zf-builder")],
            )
            with self._patch_state_db(db):
                progress = resolve_task_session_progress(task, backfill=False)

        self.assertEqual(progress["session_id"], sid)
        self.assertTrue(progress["is_stuck"], f"expected stuck (stale activity), got {progress.get('stuck_reason')}")
        self.assertIn("inactive", (progress.get("stuck_reason") or "").lower())

    def test_list_all_sessions_includes_last_activity_at(self):
        """``list_all_sessions`` must expose last_activity_at on each session."""
        import time
        from dashboard.plugin_api import list_all_sessions

        now = int(time.time())
        with tempfile.TemporaryDirectory() as td:
            db = _make_fake_state_db(
                td, "zf-builder",
                [("sess-list-1", "gpt-4", now - 300, None, now - 10, "active", 1, 1, "", "List Task", "zf-builder")],
            )
            with self._patch_state_db(db):
                res = list_all_sessions()

        self.assertTrue(res["ok"])
        self.assertTrue(res["sessions"], "no sessions returned")
        for s in res["sessions"]:
            self.assertIn("last_activity_at", s, "list_all_sessions session missing last_activity_at")
            self.assertEqual(s["last_activity_at"], now - 10)

    def test_88_settings_langfuse_observability(self):
        """Verify Langfuse settings lifecycle, multi-profile sync, and test connection endpoint."""
        import tempfile
        import yaml
        from profile_manager import update_env_file, update_config_yaml_plugins, sync_langfuse_profiles
        from dispatcher import _inject_langfuse_env

        # 1. Verify GET /settings includes Langfuse keys
        resp_get = client.get("/api/plugins/zerofactory/settings")
        self.assertEqual(resp_get.status_code, 200)
        s = resp_get.json()["settings"]
        self.assertIn("langfuse_enabled", s)
        self.assertIn("langfuse_base_url", s)
        self.assertIn("langfuse_public_key", s)
        self.assertIn("langfuse_secret_key", s)
        self.assertIn("langfuse_capture_mode", s)
        self.assertIn("langfuse_env", s)

        # 2. Verify PATCH /settings updates Langfuse keys
        resp_patch = client.patch("/api/plugins/zerofactory/settings", json={
            "langfuse_enabled": True,
            "langfuse_base_url": "https://test.langfuse.com",
            "langfuse_public_key": "pk-lf-unit-test",
            "langfuse_secret_key": "sk-lf-unit-test",
            "langfuse_capture_mode": "metadata",
            "langfuse_env": "test-env"
        })
        self.assertEqual(resp_patch.status_code, 200)
        s_updated = resp_patch.json()["settings"]
        self.assertTrue(s_updated["langfuse_enabled"])
        self.assertEqual(s_updated["langfuse_base_url"], "https://test.langfuse.com")
        self.assertEqual(s_updated["langfuse_public_key"], "pk-lf-unit-test")
        self.assertEqual(s_updated["langfuse_secret_key"], "sk-lf-unit-test")
        self.assertEqual(s_updated["langfuse_capture_mode"], "metadata")
        self.assertEqual(s_updated["langfuse_env"], "test-env")

        # 3. Test update_env_file preserves unrelated keys and comments
        with tempfile.TemporaryDirectory() as tmp_dir:
            env_p = Path(tmp_dir) / ".env"
            env_p.write_text("# Custom comment\nOPENROUTER_API_KEY=existing-key\nOTHER_VAR=123\n", encoding="utf-8")
            updates = {
                "HERMES_LANGFUSE_PUBLIC_KEY": "pk-lf-sample",
                "HERMES_LANGFUSE_SECRET_KEY": "sk-lf-sample",
            }
            update_env_file(env_p, updates)
            lines = env_p.read_text(encoding="utf-8").splitlines()
            self.assertIn("# Custom comment", lines)
            self.assertIn("OPENROUTER_API_KEY=existing-key", lines)
            self.assertIn("OTHER_VAR=123", lines)
            self.assertIn("HERMES_LANGFUSE_PUBLIC_KEY=pk-lf-sample", lines)
            self.assertIn("HERMES_LANGFUSE_SECRET_KEY=sk-lf-sample", lines)

            # Update in-place
            update_env_file(env_p, {"HERMES_LANGFUSE_PUBLIC_KEY": "pk-lf-modified"})
            lines2 = env_p.read_text(encoding="utf-8").splitlines()
            self.assertIn("HERMES_LANGFUSE_PUBLIC_KEY=pk-lf-modified", lines2)
            self.assertNotIn("HERMES_LANGFUSE_PUBLIC_KEY=pk-lf-sample", lines2)
            self.assertIn("OPENROUTER_API_KEY=existing-key", lines2)

        # 4. Test update_config_yaml_plugins adds and removes langfuse cleanly
        with tempfile.TemporaryDirectory() as tmp_dir:
            cfg_p = Path(tmp_dir) / "config.yaml"
            cfg_p.write_text(yaml.dump({"plugins": {"enabled": ["zerofactory"]}, "model": {"default": "test"}}, sort_keys=False), encoding="utf-8")
            
            # Enable langfuse
            update_config_yaml_plugins(cfg_p, enable_plugin="langfuse")
            loaded = yaml.safe_load(cfg_p.read_text(encoding="utf-8"))
            self.assertIn("langfuse", loaded["plugins"]["enabled"])
            self.assertIn("zerofactory", loaded["plugins"]["enabled"])

            # Disable langfuse
            update_config_yaml_plugins(cfg_p, disable_plugin="langfuse")
            loaded_after = yaml.safe_load(cfg_p.read_text(encoding="utf-8"))
            self.assertNotIn("langfuse", loaded_after["plugins"]["enabled"])
            self.assertIn("zerofactory", loaded_after["plugins"]["enabled"])

        # 5. Test _inject_langfuse_env
        test_env = {}
        _inject_langfuse_env(test_env)
        self.assertEqual(test_env.get("HERMES_LANGFUSE_PUBLIC_KEY"), "pk-lf-unit-test")
        self.assertEqual(test_env.get("HERMES_LANGFUSE_BASE_URL"), "https://test.langfuse.com")
        self.assertEqual(test_env.get("HERMES_LANGFUSE_CAPTURE"), "metadata")
        self.assertEqual(test_env.get("HERMES_LANGFUSE_ENV"), "test-env")

        # Disable in settings and test removal from env
        client.patch("/api/plugins/zerofactory/settings", json={"langfuse_enabled": False})
        _inject_langfuse_env(test_env)
        self.assertNotIn("HERMES_LANGFUSE_PUBLIC_KEY", test_env)

        # 6. Test POST /settings/langfuse/test endpoint validation
        bad_key_res = client.post("/api/plugins/zerofactory/settings/langfuse/test", json={
            "base_url": "https://cloud.langfuse.com",
            "public_key": "wrong-prefix",
            "secret_key": "sk-lf-valid"
        })
        self.assertEqual(bad_key_res.status_code, 200)
        self.assertFalse(bad_key_res.json()["ok"])
        self.assertIn("Invalid key format", bad_key_res.json()["error"])

        unreachable_res = client.post("/api/plugins/zerofactory/settings/langfuse/test", json={
            "base_url": "http://127.0.0.1:59998",
            "public_key": "",
            "secret_key": ""
        })
        self.assertEqual(unreachable_res.status_code, 200)
        self.assertFalse(unreachable_res.json()["ok"])

        # 7. Regression: disabling Langfuse must scrub ALL HERMES_LANGFUSE_* keys
        #    from every target .env file and drop `langfuse` from every
        #    config.yaml plugins.enabled list (stale-secret hygiene).
        with tempfile.TemporaryDirectory() as tmp_hermes:
            import profile_manager as _pm
            from unittest.mock import patch
            hermes_fake = Path(tmp_hermes)
            profiles_dir = hermes_fake / "profiles" / "zf-builder"
            profiles_dir.mkdir(parents=True)
            # Pre-existing unrelated keys + comments that must survive scrubbing
            for d in (hermes_fake, profiles_dir):
                (d / ".env").write_text(
                    "# keep me\nOPENROUTER_API_KEY=«redacted:existing-…»\n",
                    encoding="utf-8",
                )
                (d / "config.yaml").write_text(
                    yaml.dump({"plugins": {"enabled": ["zerofactory"]}}, sort_keys=False),
                    encoding="utf-8",
                )

            enable_settings = {
                "langfuse_enabled": True,
                "langfuse_base_url": "https://test.langfuse.com",
                "langfuse_public_key": "«redacted:pk-lf-…»",
                "langfuse_secret_key": "«redacted:sk-…»",
                "langfuse_capture_mode": "metadata",
                "langfuse_env": "test-env",
            }
            with patch.object(_pm, "get_hermes_home", return_value=hermes_fake):
                result = _pm.sync_langfuse_profiles(enable_settings)
                self.assertTrue(result["enabled"])
                # Enable: keys present in both .env files, plugin enabled
                for d in (hermes_fake, profiles_dir):
                    env_text = (d / ".env").read_text(encoding="utf-8")
                    self.assertIn("HERMES_LANGFUSE_SECRET_KEY=«redacted:sk-…»", env_text)
                    self.assertIn("HERMES_LANGFUSE_PUBLIC_KEY=«redacted:pk-lf-…»", env_text)
                    self.assertIn("HERMES_LANGFUSE_BASE_URL=https://test.langfuse.com", env_text)
                    self.assertIn("HERMES_LANGFUSE_CAPTURE=metadata", env_text)
                    self.assertIn("HERMES_LANGFUSE_ENV=test-env", env_text)
                    cfg_loaded = yaml.safe_load((d / "config.yaml").read_text(encoding="utf-8"))
                    self.assertIn("langfuse", cfg_loaded["plugins"]["enabled"])

                # Disable: every HERMES_LANGFUSE_* key GONE, plugin removed
                disable_settings = dict(enable_settings, langfuse_enabled=False)
                result = _pm.sync_langfuse_profiles(disable_settings)
                self.assertFalse(result["enabled"])
                for d in (hermes_fake, profiles_dir):
                    env_text = (d / ".env").read_text(encoding="utf-8")
                    for k in ("HERMES_LANGFUSE_SECRET_KEY", "HERMES_LANGFUSE_PUBLIC_KEY",
                              "HERMES_LANGFUSE_BASE_URL", "HERMES_LANGFUSE_CAPTURE",
                              "HERMES_LANGFUSE_ENV"):
                        self.assertNotIn(k, env_text,
                                         f"stale {k} left in {d / '.env'} after disable")
                    # Unrelated keys and comments preserved
                    self.assertIn("OPENROUTER_API_KEY=«redacted:existing-…»", env_text)
                    self.assertIn("# keep me", env_text)
                    cfg_loaded = yaml.safe_load((d / "config.yaml").read_text(encoding="utf-8"))
                    self.assertNotIn("langfuse", cfg_loaded["plugins"]["enabled"])
                    self.assertIn("zerofactory", cfg_loaded["plugins"]["enabled"])

                # Idempotency: disabling again with no .env keys present is a no-op
                _pm.sync_langfuse_profiles(disable_settings)
                for d in (hermes_fake, profiles_dir):
                    self.assertNotIn("HERMES_LANGFUSE_SECRET_KEY",
                                     (d / ".env").read_text(encoding="utf-8"))

    def test_55_native_board_memories_crud_and_cascade(self):
        """Test Native kanban.db Memory CRUD, category filtering, search, and board cascade deletion."""
        # 1. Ensure board exists
        b_res = create_board(BoardCreate(git_url="https://github.com/example/test-mem.git", description="Memory test board"))
        b_slug = b_res["slug"]

        # 2. Create memories
        c_res = client.post(f"/api/plugins/zerofactory/boards/{b_slug}/memories", json={
            "category": "convention",
            "content": "Always run linters before creating PRs",
            "tags": ["lint", "python", "flake8"],
            "author": "zf-builder"
        })
        self.assertEqual(c_res.status_code, 200)
        c_data = c_res.json()
        self.assertTrue(c_data["ok"])
        mem1 = c_data["memory"]
        self.assertEqual(mem1["category"], "convention")
        self.assertIn("Always run linters", mem1["content"])
        self.assertIn("flake8", mem1["tags"])
        self.assertEqual(mem1["author"], "zf-builder")
        mem1_id = mem1["id"]

        # Create second memory: gotcha
        c_res2 = client.post(f"/api/plugins/zerofactory/boards/{b_slug}/memories", json={
            "category": "gotcha",
            "content": "SQLite WAL mode requires busy_timeout under high concurrency",
            "tags": ["sqlite", "concurrency"],
            "author": "zf-reviewer"
        })
        self.assertEqual(c_res2.status_code, 200)
        mem2_id = c_res2.json()["memory"]["id"]

        # 3. List memories
        list_res = client.get(f"/api/plugins/zerofactory/boards/{b_slug}/memories")
        self.assertEqual(list_res.status_code, 200)
        list_data = list_res.json()
        self.assertTrue(list_data["ok"])
        self.assertEqual(list_data["total"], 2)
        self.assertEqual(len(list_data["memories"]), 2)

        # 4. Filter by category
        cat_res = client.get(f"/api/plugins/zerofactory/boards/{b_slug}/memories?category=gotcha")
        self.assertEqual(cat_res.status_code, 200)
        cat_data = cat_res.json()
        self.assertEqual(cat_data["total"], 1)
        self.assertEqual(cat_data["memories"][0]["id"], mem2_id)

        # 5. Search by query
        search_res = client.get(f"/api/plugins/zerofactory/boards/{b_slug}/memories?q=busy_timeout")
        self.assertEqual(search_res.status_code, 200)
        search_data = search_res.json()
        self.assertEqual(search_data["total"], 1)
        self.assertEqual(search_data["memories"][0]["id"], mem2_id)

        search_tag_res = client.get(f"/api/plugins/zerofactory/boards/{b_slug}/memories?q=flake8")
        self.assertEqual(search_tag_res.status_code, 200)
        self.assertEqual(search_tag_res.json()["total"], 1)

        # 6. Update memory
        up_res = client.put(f"/api/plugins/zerofactory/memories/{mem1_id}", json={
            "content": "Always run linters and pytest before creating PRs",
            "tags": ["lint", "python", "pytest"]
        })
        self.assertEqual(up_res.status_code, 200)
        up_data = up_res.json()
        self.assertTrue(up_data["ok"])
        self.assertEqual(up_data["memory"]["content"], "Always run linters and pytest before creating PRs")
        self.assertIn("pytest", up_data["memory"]["tags"])

        # 7. Delete single memory
        del_res = client.delete(f"/api/plugins/zerofactory/memories/{mem1_id}")
        self.assertEqual(del_res.status_code, 200)
        self.assertTrue(del_res.json()["ok"])

        # Verify it's gone
        list_after = client.get(f"/api/plugins/zerofactory/boards/{b_slug}/memories")
        self.assertEqual(list_after.json()["total"], 1)

        # 8. Test 404s
        bad_board = client.get("/api/plugins/zerofactory/boards/non-existent-board/memories")
        self.assertEqual(bad_board.status_code, 404)

        bad_del = client.delete("/api/plugins/zerofactory/memories/non-existent-mem")
        self.assertEqual(bad_del.status_code, 404)

        # 9. Test cascade delete on board deletion
        del_board_res = client.delete(f"/api/plugins/zerofactory/boards/{b_slug}")
        self.assertEqual(del_board_res.status_code, 200)

        # Verify board_memories table has no rows for b_slug
        with get_db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM board_memories WHERE board_slug = ?", (b_slug,))
            self.assertEqual(cursor.fetchone()[0], 0)

    def test_56_agents_status_endpoint(self):
        """Test GET /agents endpoint returning status for the 3 specialist agents."""
        res = client.get("/api/plugins/zerofactory/agents")
        self.assertEqual(res.status_code, 200)
        data = res.json()
        self.assertTrue(data["ok"])
        agents = data["agents"]
        self.assertEqual(len(agents), 3)
        agent_names = [a["name"] for a in agents]
        self.assertIn("zf-orchestrator", agent_names)
        self.assertIn("zf-builder", agent_names)
        self.assertIn("zf-reviewer", agent_names)

        for a in agents:
            self.assertIn(a["status"], ("active", "idle"))
            self.assertIn("label", a)
            self.assertIn("icon", a)
            self.assertIn("description", a)
            self.assertIn("stats", a)

    def test_57_dispatcher_memories_digest(self):
        """Test digest_board_memories_context and worker prompt injection."""
        from dispatcher import digest_board_memories_context

        b_res = create_board(BoardCreate(git_url="https://github.com/example/digest-board.git"))
        b_slug = b_res["slug"]

        # When no memories exist, returns empty string
        empty_digest = digest_board_memories_context(b_slug)
        self.assertEqual(empty_digest, "")

        # Add memories
        client.post(f"/api/plugins/zerofactory/boards/{b_slug}/memories", json={
            "category": "convention",
            "content": "Follow PEP 8 naming conventions",
            "tags": ["style", "pep8"]
        })
        client.post(f"/api/plugins/zerofactory/boards/{b_slug}/memories", json={
            "category": "gotcha",
            "content": "Beware of circular imports between plugin_api and dispatcher",
            "tags": ["imports", "architecture"]
        })

        digest = digest_board_memories_context(b_slug)
        self.assertIn("REPOSITORY KNOWLEDGE & CONVENTIONS", digest)
        self.assertIn("[convention] Follow PEP 8 naming conventions", digest)
        self.assertIn("[gotcha] Beware of circular imports", digest)
        self.assertIn("tags: style, pep8", digest)

    def test_58_cli_memory_commands(self):
        """Test CLI memory subcommands: add, list, delete."""
        import argparse
        import io
        from contextlib import redirect_stdout
        from __init__ import register

        b_res = create_board(BoardCreate(git_url="https://github.com/example/cli-mem-board.git"))
        b_slug = b_res["slug"]

        class DummyCtx:
            def __init__(self):
                self.commands = {}
            def register_cli_command(self, name, help, setup_fn, handler_fn):
                self.commands[name] = (setup_fn, handler_fn)

        ctx = DummyCtx()
        register(ctx)
        self.assertIn("zerofactory", ctx.commands)
        setup_fn, handler_fn = ctx.commands["zerofactory"]

        parser = argparse.ArgumentParser()
        setup_fn(parser)

        # 1. Add memory via CLI
        args_add = parser.parse_args([
            "memory", "add",
            "--board", b_slug,
            "Always mock external network requests in tests",
            "--category", "convention",
            "--tags", "test, network"
        ])
        f = io.StringIO()
        with redirect_stdout(f):
            handler_fn(args_add)
        out_add = f.getvalue()
        self.assertIn("Added memory", out_add)
        self.assertIn("[convention]", out_add)

        # 2. List memory via CLI
        args_list = parser.parse_args([
            "memory", "list",
            "--board", b_slug
        ])
        f_list = io.StringIO()
        with redirect_stdout(f_list):
            handler_fn(args_list)
        out_list = f_list.getvalue()
        self.assertIn("Always mock external network", out_list)
        self.assertIn("convention", out_list)

        # 3. Delete memory via CLI
        list_res = client.get(f"/api/plugins/zerofactory/boards/{b_slug}/memories")
        mem_id = list_res.json()["memories"][0]["id"]

        args_del = parser.parse_args([
            "memory", "delete",
            mem_id
        ])
        f_del = io.StringIO()
        with redirect_stdout(f_del):
            handler_fn(args_del)
        out_del = f_del.getvalue()
        self.assertIn("Deleted memory", out_del)

        # Verify deleted
        list_res_after = client.get(f"/api/plugins/zerofactory/boards/{b_slug}/memories")
        self.assertEqual(list_res_after.json()["total"], 0)

    def test_59_auto_record_memory_settings_and_board_override(self):
        """Test global auto_record_memory setting and per-board override flag."""
        from dashboard.plugin_api import SettingsUpdate

        # 1. Global setting defaults to True
        s_res = client.get("/api/plugins/zerofactory/settings").json()
        self.assertTrue(s_res["settings"]["auto_record_memory"])

        # 2. Toggle global setting to False
        patch_res = client.patch(
            "/api/plugins/zerofactory/settings",
            json={"auto_record_memory": False}
        ).json()
        self.assertFalse(patch_res["settings"]["auto_record_memory"])

        # Re-enable global setting
        client.patch(
            "/api/plugins/zerofactory/settings",
            json={"auto_record_memory": True}
        )
        s_res_after = client.get("/api/plugins/zerofactory/settings").json()
        self.assertTrue(s_res_after["settings"]["auto_record_memory"])

        # 3. Create board with default auto_record_memory (True)
        b1 = client.post(
            "/api/plugins/zerofactory/boards",
            json={"git_url": "https://github.com/example/arm-b1.git"}
        ).json()
        b1_slug = b1["slug"]

        boards_list = client.get("/api/plugins/zerofactory/boards").json()["boards"]
        b1_data = next(b for b in boards_list if b["slug"] == b1_slug)
        self.assertTrue(b1_data["auto_record_memory"])

        # 4. Create board with auto_record_memory disabled (False)
        b2 = client.post(
            "/api/plugins/zerofactory/boards",
            json={"git_url": "https://github.com/example/arm-b2.git", "auto_record_memory": False}
        ).json()
        b2_slug = b2["slug"]

        boards_list2 = client.get("/api/plugins/zerofactory/boards").json()["boards"]
        b2_data = next(b for b in boards_list2 if b["slug"] == b2_slug)
        self.assertFalse(b2_data["auto_record_memory"])

        # 5. Toggle board auto_record_memory via PATCH
        client.patch(
            f"/api/plugins/zerofactory/boards/{b2_slug}",
            json={"auto_record_memory": True}
        )
        boards_list3 = client.get("/api/plugins/zerofactory/boards").json()["boards"]
        b2_data_after = next(b for b in boards_list3 if b["slug"] == b2_slug)
        self.assertTrue(b2_data_after["auto_record_memory"])

    def test_60_auto_record_memory_extraction(self):
        """Test extract_and_record_memory extraction, deduplication, and suppression when disabled."""
        from dashboard.plugin_api import extract_and_record_memory, get_db_conn

        b_res = client.post(
            "/api/plugins/zerofactory/boards",
            json={"git_url": "https://github.com/example/arm-extract.git"}
        ).json()
        b_slug = b_res["slug"]

        text_feedback = (
            "Code review feedback:\n"
            "- **GOTCHA:** Always run db migrations before seeding test data\n"
            "- **CONVENTION:** PascalCase should be used for React component files\n"
            "- Some non-rule review comment without a tag\n"
            "- REJECTED_PATH: Avoid using global mutable singletons for configuration\n"
            "- DECISION: Standardized on pytest-mock for test mocks"
        )

        with get_db_conn() as conn:
            # 1. Extraction with auto_record_memory enabled
            recorded = extract_and_record_memory(conn, board_slug=b_slug, text=text_feedback, author="zf-reviewer")
            conn.commit()

            self.assertEqual(len(recorded), 4)
            categories = [r["category"] for r in recorded]
            self.assertIn("gotcha", categories)
            self.assertIn("convention", categories)
            self.assertIn("rejected_path", categories)
            self.assertIn("decision", categories)

            # 2. Deduplication: run exact same extraction again
            recorded_dupes = extract_and_record_memory(conn, board_slug=b_slug, text=text_feedback, author="zf-reviewer")
            conn.commit()
            self.assertEqual(len(recorded_dupes), 0)

            # 3. Suppression when board auto_record_memory is disabled
            client.patch(f"/api/plugins/zerofactory/boards/{b_slug}", json={"auto_record_memory": False})
            conn.commit()

            new_feedback = "GOTCHA: Never run git push --force on shared branch"
            recorded_suppressed = extract_and_record_memory(conn, board_slug=b_slug, text=new_feedback, author="zf-reviewer")
            self.assertEqual(len(recorded_suppressed), 0)

            # Re-enable board
            client.patch(f"/api/plugins/zerofactory/boards/{b_slug}", json={"auto_record_memory": True})
            conn.commit()

            # 4. Suppression when global auto_record_memory is disabled
            client.patch("/api/plugins/zerofactory/settings", json={"auto_record_memory": False})
            conn.commit()

            recorded_globally_suppressed = extract_and_record_memory(conn, board_slug=b_slug, text=new_feedback, author="zf-reviewer")
            self.assertEqual(len(recorded_globally_suppressed), 0)

            # Restore global setting
            client.patch("/api/plugins/zerofactory/settings", json={"auto_record_memory": True})
            conn.commit()

    def test_61_move_task_auto_record_gotcha(self):
        """Test auto-recording gotcha when task is moved to blocked with structured rule reason."""
        from dashboard.plugin_api import TaskCreate

        b_res = client.post(
            "/api/plugins/zerofactory/boards",
            json={"git_url": "https://github.com/example/arm-move.git"}
        ).json()
        b_slug = b_res["slug"]

        # Create task
        t_res = client.post(
            "/api/plugins/zerofactory/tasks",
            json={"title": "Test memory move", "board_slug": b_slug, "status": "running"}
        ).json()
        t_id = t_res["id"]

        # Move to blocked with GOTCHA in reason
        move_res = client.post(
            f"/api/plugins/zerofactory/tasks/{t_id}/move",
            json={
                "status": "blocked",
                "actor": "zf-reviewer",
                "reason": "changes-requested. GOTCHA: Always lock dependencies in requirements.txt before release"
            }
        ).json()
        self.assertTrue(move_res["ok"])

        # Check board memories
        mem_res = client.get(f"/api/plugins/zerofactory/boards/{b_slug}/memories").json()
        self.assertEqual(mem_res["total"], 1)
        mem = mem_res["memories"][0]
        self.assertEqual(mem["category"], "gotcha")
        self.assertIn("Always lock dependencies in requirements.txt before release", mem["content"])
        self.assertEqual(mem["author"], "zf-reviewer")
        self.assertEqual(mem["task_id"], t_id)

    def test_62_memory_auto_record_near_duplicate_dedup(self):
        """Test that near-identical rules (case/whitespace variants) dedup to a single row."""
        from dashboard.plugin_api import extract_and_record_memory, get_db_conn

        b_res = client.post(
            "/api/plugins/zerofactory/boards",
            json={"git_url": "https://github.com/example/arm-near-dup.git"}
        ).json()
        b_slug = b_res["slug"]

        base_rule = "GOTCHA: Always run db migrations before seeding test data"

        with get_db_conn() as conn:
            # 1. Record the base rule
            recorded = extract_and_record_memory(conn, board_slug=b_slug, text=base_rule, author="zf-reviewer")
            conn.commit()
            self.assertEqual(len(recorded), 1)

            # 2. Case + extra whitespace variant of the same rule → deduplicated
            variant = "gotcha:   always   run DB migrations before seeding test data"
            recorded_variant = extract_and_record_memory(conn, board_slug=b_slug, text=variant, author="zf-reviewer")
            conn.commit()
            self.assertEqual(len(recorded_variant), 0)

            # 3. Case variant with a markdown-bullet prefix → still deduplicated
            variant_md = "- **Gotcha:** ALWAYS RUN DB MIGRATIONS before seeding  test data"
            recorded_md = extract_and_record_memory(conn, board_slug=b_slug, text=variant_md, author="zf-reviewer")
            conn.commit()
            self.assertEqual(len(recorded_md), 0)

            # 4. Exact-match regression guard: identical re-run is also deduplicated
            recorded_exact = extract_and_record_memory(conn, board_slug=b_slug, text=base_rule, author="zf-reviewer")
            conn.commit()
            self.assertEqual(len(recorded_exact), 0)

            # 5. Mid-sentence rule (block/reviewer reason style, e.g.
            # "changes-requested. GOTCHA: ...") is still captured
            mid_sentence = "changes-requested. GOTCHA: Always lock dependencies in requirements.txt before release"
            recorded_mid = extract_and_record_memory(conn, board_slug=b_slug, text=mid_sentence, author="zf-reviewer")
            conn.commit()
            self.assertEqual(len(recorded_mid), 1)
            self.assertEqual(recorded_mid[0]["category"], "gotcha")

            # 6. A genuinely different rule is still recorded (no over-suppression)
            other = "CONVENTION: Use snake_case for all module-level constants"
            recorded_other = extract_and_record_memory(conn, board_slug=b_slug, text=other, author="zf-reviewer")
            conn.commit()
            self.assertEqual(len(recorded_other), 1)

            # 7. Board state: exactly 3 rows (base rule + mid-sentence rule +
            # genuinely different rule)
            cursor = conn.cursor()
            cursor.execute("SELECT COUNT(*) FROM board_memories WHERE board_slug = ?", (b_slug,))
            self.assertEqual(cursor.fetchone()[0], 3)

            # The gotcha rows are exactly the base rule + the mid-sentence
            # rule (stored in their original phrasing); variants were not
            # recorded as separate rows.
            cursor.execute(
                "SELECT content FROM board_memories WHERE board_slug = ? AND category = 'gotcha'",
                (b_slug,)
            )
            contents = sorted(r[0] for r in cursor.fetchall())
            self.assertEqual(
                contents,
                sorted([
                    "Always run db migrations before seeding test data",
                    "Always lock dependencies in requirements.txt before release",
                ])
            )

    def test_63_memory_manual_content_length_cap(self):
        """Test that manually created/updated memory content is bounded at 500 chars."""
        from dashboard.plugin_api import MEMORY_CONTENT_MAX_LENGTH

        self.assertGreater(MEMORY_CONTENT_MAX_LENGTH, 0)

        b_res = client.post(
            "/api/plugins/zerofactory/boards",
            json={"git_url": "https://github.com/example/arm-cap.git"}
        ).json()
        b_slug = b_res["slug"]

        # 1. Create: over-cap content is rejected with 422
        too_long = "GOTCHA: " + ("x" * (MEMORY_CONTENT_MAX_LENGTH - 5))
        res = client.post(
            f"/api/plugins/zerofactory/boards/{b_slug}/memories",
            json={"content": too_long}
        )
        self.assertEqual(res.status_code, 422)

        # 2. Create: exactly-at-cap content is accepted
        at_cap = "GOTCHA: " + ("x" * (MEMORY_CONTENT_MAX_LENGTH - 8))
        self.assertEqual(len(at_cap), MEMORY_CONTENT_MAX_LENGTH)
        ok = client.post(
            f"/api/plugins/zerofactory/boards/{b_slug}/memories",
            json={"content": at_cap, "category": "gotcha"}
        )
        self.assertEqual(ok.status_code, 200)
        mem = ok.json()["memory"]
        self.assertEqual(len(mem["content"]), MEMORY_CONTENT_MAX_LENGTH)

        # 3. Update: over-cap replacement is rejected with 422, content unchanged
        res = client.put(
            f"/api/plugins/zerofactory/memories/{mem['id']}",
            json={"content": too_long}
        )
        self.assertEqual(res.status_code, 422)
        after = client.get(f"/api/plugins/zerofactory/boards/{b_slug}/memories").json()
        self.assertEqual(after["memories"][0]["content"], at_cap)

        # 4. Update: whitespace-only replacement is rejected with 400
        # (min_length counts raw chars, so "   " passes pydantic — the
        # endpoint rejects blank content explicitly)
        res = client.put(
            f"/api/plugins/zerofactory/memories/{mem['id']}",
            json={"content": "   "}
        )
        self.assertEqual(res.status_code, 400)

        # 5. Update: valid shorter replacement is accepted
        short = "GOTCHA: keep memory content short"
        res = client.put(
            f"/api/plugins/zerofactory/memories/{mem['id']}",
            json={"content": short}
        )
        self.assertEqual(res.status_code, 200)
        self.assertEqual(res.json()["memory"]["content"], short)

        # 6. CLI `memory add` documents the cap and refuses over-cap content
        import argparse
        import io
        from contextlib import redirect_stdout
        from __init__ import register

        class DummyCtx:
            def __init__(self):
                self.commands = {}
            def register_cli_command(self, name, help, setup_fn, handler_fn):
                self.commands[name] = (setup_fn, handler_fn)

        ctx = DummyCtx()
        register(ctx)
        setup_fn, handler_fn = ctx.commands["zerofactory"]

        parser = argparse.ArgumentParser()
        setup_fn(parser)

        # Cap is documented in the CLI help text
        parser.parse_args(["memory", "add", "--board", b_slug, "rule"])
        subparsers_actions = [
            action for action in parser._actions
            if isinstance(action, argparse._SubParsersAction)
        ]
        memory_action = next(a for a in subparsers_actions if a.dest == "action")
        memory_parser = memory_action.choices["memory"]
        # Walk sub-subparsers: memory -> add
        mem_add_help = None
        for sub_action in memory_parser._actions:
            if isinstance(sub_action, argparse._SubParsersAction):
                add_parser = sub_action.choices["add"]
                mem_add_help = add_parser.format_help()
                break
        self.assertIsNotNone(mem_add_help)
        self.assertIn(str(MEMORY_CONTENT_MAX_LENGTH), mem_add_help)

        # Over-cap content is refused with a clear message and no row created
        f = io.StringIO()
        args_long = parser.parse_args([
            "memory", "add",
            "--board", b_slug,
            "GOTCHA: " + ("y" * 600),
        ])
        with redirect_stdout(f):
            handler_fn(args_long)
        out = f.getvalue()
        self.assertIn("maximum allowed", out)
        after_cli = client.get(f"/api/plugins/zerofactory/boards/{b_slug}/memories").json()
        self.assertEqual(after_cli["total"], 1)

        # Valid CLI add still works
        f = io.StringIO()
        args_ok = parser.parse_args([
            "memory", "add",
            "--board", b_slug,
            "CLI rule within the cap",
        ])
        with redirect_stdout(f):
            handler_fn(args_ok)
        self.assertIn("Added memory", f.getvalue())

    def test_64_digest_board_memories_unchanged_for_legit_rows(self):
        """Test that digest_board_memories_context output format is unchanged for legitimate rows."""
        from dispatcher import digest_board_memories_context

        b_res = client.post(
            "/api/plugins/zerofactory/boards",
            json={"git_url": "https://github.com/example/digest-regression.git"}
        ).json()
        b_slug = b_res["slug"]

        client.post(f"/api/plugins/zerofactory/boards/{b_slug}/memories", json={
            "category": "convention",
            "content": "Follow PEP 8 naming conventions",
            "tags": ["style", "pep8"],
            "author": "zf-builder"
        })

        digest = digest_board_memories_context(b_slug)
        self.assertEqual(
            digest,
            (
                "\U0001F9E0 REPOSITORY KNOWLEDGE & CONVENTIONS (Learned from prior tasks):\n"
                "- [convention] Follow PEP 8 naming conventions [tags: style, pep8]\n"
                "Please adhere to these conventions and avoid known gotchas during execution."
            )
        )

        # Long legitimate content is still truncated to 200 chars in the digest
        long_content = "CONVENTION-CONTENT: " + ("z" * 400)
        client.post(f"/api/plugins/zerofactory/boards/{b_slug}/memories", json={
            "category": "convention",
            "content": long_content
        })
        digest2 = digest_board_memories_context(b_slug)
        self.assertIn(long_content[:197] + "...", digest2)
        self.assertNotIn(long_content, digest2)

        # Signature is unchanged: (board_slug, db_path=None, limit=8)
        import inspect
        sig = inspect.signature(digest_board_memories_context)
        self.assertEqual(list(sig.parameters), ["board_slug", "db_path", "limit"])
        self.assertEqual(sig.parameters["limit"].default, 8)
    def test_65_comment_auto_record_memory(self):
        """Test auto-recording memory when adding comment to a task."""
        b_res = client.post(
            "/api/plugins/zerofactory/boards",
            json={"git_url": "https://github.com/example/arm-comment.git"}
        ).json()
        b_slug = b_res["slug"]

        t_res = client.post(
            "/api/plugins/zerofactory/tasks",
            json={"title": "Test comment memory", "board_slug": b_slug, "status": "running"}
        ).json()
        t_id = t_res["id"]

        # Add comment with CONVENTION
        cmt_res = client.post(
            f"/api/plugins/zerofactory/tasks/{t_id}/comments",
            json={
                "body": "PR review summary:\n- TIP: Prefer pytest fixtures over setUp methods for cleaner tests",
                "author": "zf-reviewer"
            }
        ).json()
        self.assertTrue(cmt_res["ok"])

        # Verify memory created
        mem_res = client.get(f"/api/plugins/zerofactory/boards/{b_slug}/memories").json()
        self.assertEqual(mem_res["total"], 1)
        mem = mem_res["memories"][0]
        self.assertEqual(mem["category"], "convention")
        self.assertIn("Prefer pytest fixtures over setUp methods for cleaner tests", mem["content"])
        self.assertEqual(mem["author"], "zf-reviewer")
        self.assertEqual(mem["task_id"], t_id)


class TestDispatcherExceptionHandlerHygiene(unittest.TestCase):
    """AST guards against unreachable duplicate exception handlers in dispatcher.py.

    Regression: PR #42 (commit 6866a84) moved the author commit/PR try-block in
    ``run_dispatch_cycle()`` section 3 into its own ``if`` block but left the
    original reviewer PR-check tail (``except Exception: ... "Reviewer PR check
    skipped"``) orphaned *inside* the new try-block. A second ``except Exception``
    is unreachable — the first one shadows it — and would misattribute
    commit/PR failures as reviewer-PR-check failures. This guard walks every
    ``try`` in dispatcher.py and fails on any repeated exception-handler type.
    """

    @classmethod
    def _dispatcher_tree(cls):
        import ast
        src_path = Path(__file__).resolve().parent / "dispatcher.py"
        if not src_path.exists():
            src_path = Path(__file__).resolve().parent / "dispatcher" / "scheduler.py"
        return ast.parse(src_path.read_text(), filename=str(src_path))

    @staticmethod
    def _handler_type_name(handler):
        import ast
        t = handler.type
        if isinstance(t, ast.Name):
            return t.id
        if isinstance(t, (ast.Tuple, ast.List)):
            return ",".join(
                e.id if isinstance(e, ast.Name) else repr(e) for e in t.elts
            )
        return repr(t)

    def test_no_duplicate_exception_handler_types_in_any_try_block(self):
        """No try-block in dispatcher.py may repeat an exception-handler type."""
        import ast
        tree = self._dispatcher_tree()
        duplicates = []
        for node in ast.walk(tree):
            if not isinstance(node, ast.Try):
                continue
            seen = set()
            for handler in node.handlers:
                tname = self._handler_type_name(handler)
                if tname in seen:
                    duplicates.append(
                        f"dispatcher.py:{node.lineno} try-block has duplicate "
                        f"'except {tname}' handler (line {handler.lineno})"
                    )
                seen.add(tname)
        self.assertEqual(duplicates, [], "\n".join(duplicates))

    def test_no_orphaned_reviewer_pr_check_skip_in_commit_pr_block(self):
        """The commit/PR try-block must not log 'Reviewer PR check skipped'.

        Asserts the exact regression pattern is gone: the author commit/PR
        block (the one whose generic handler logs 'commit/PR failed') must
        not contain a 'Reviewer PR check skipped' log line. The reviewer's
        own PR-check block (guarded by ``if row["pr_url"] and assignee ==
        "zf-reviewer"``) legitimately keeps that message; this asserts the
        commit/PR block no longer carries the orphaned copy.
        """
        src_path = Path(__file__).resolve().parent / "dispatcher.py"
        if not src_path.exists():
            src_path = Path(__file__).resolve().parent / "dispatcher" / "scheduler.py"
        src = src_path.read_text()
        lines = src.splitlines()

        # Locate the author commit/PR block: the try whose generic handler
        # logs 'commit/PR failed'. Its handler lines give us the block range.
        commit_pr_generic_line = None
        for i, ln in enumerate(lines):
            if "_log.warning(\"Task %s commit/PR failed:" in ln:
                # the 'except Exception as e:' is one line above
                commit_pr_generic_line = i
                break
        self.assertIsNotNone(
            commit_pr_generic_line,
            "could not locate the author commit/PR generic handler",
        )

        # Walk backwards from that handler to the enclosing 'try:' line.
        # The try-block body spans from the try line to the last handler's
        # end; the orphaned handler would sit *after* the commit/PR handler.
        try_line = None
        for i in range(commit_pr_generic_line, -1, -1):
            stripped = lines[i].strip()
            if stripped == "try:":
                try_line = i
                break
        self.assertIsNotNone(try_line, "could not locate commit/PR try: line")

        # Collect the handler tail: everything from the first 'except' at
        # this block's indent (the commit/PR generic handler) to the line
        # where the block ends (indent drops back to the try's parent).
        except_indent = len(lines[commit_pr_generic_line]) - len(
            lines[commit_pr_generic_line].lstrip()
        )
        block_end = commit_pr_generic_line
        for i in range(commit_pr_generic_line + 1, len(lines)):
            ln = lines[i]
            if ln.strip() == "":
                continue
            indent = len(ln) - len(ln.lstrip())
            if indent <= except_indent and ln.lstrip().startswith(("except ",)):
                block_end = i
            elif indent < except_indent:
                # dedented out of the handler tail -> block over
                break
            else:
                block_end = i

        tail = "\n".join(lines[commit_pr_generic_line:block_end + 1])
        self.assertNotIn(
            "Reviewer PR check skipped",
            tail,
            "orphaned 'Reviewer PR check skipped' handler left in the commit/PR "
            "try-block (regression from PR #42 code move)",
        )


if __name__ == "__main__":
    unittest.main()
