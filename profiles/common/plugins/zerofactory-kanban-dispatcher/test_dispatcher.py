import sqlite3
import os
import time
from pathlib import Path
import sys
from unittest.mock import patch
import pytest

sys.path.append(os.path.join(os.path.dirname(__file__)))
import __init__ as dispatcher

# Use an in-memory database for testing instead of the real one
@pytest.fixture
def mock_db_path(tmp_path):
    db_file = tmp_path / "kanban.db"
    
    # Initialize schema
    with sqlite3.connect(db_file) as conn:
        cursor = conn.cursor()
        cursor.execute("""
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY,
                title TEXT,
                body TEXT,
                assignee TEXT,
                status TEXT,
                priority INTEGER DEFAULT 0,
                created_by TEXT,
                created_at INTEGER,
                started_at INTEGER,
                completed_at INTEGER,
                workspace_kind TEXT DEFAULT 'scratch',
                workspace_path TEXT,
                branch_name TEXT,
                claim_lock TEXT,
                claim_expires INTEGER,
                tenant TEXT,
                result TEXT,
                idempotency_key TEXT,
                consecutive_failures INTEGER DEFAULT 0,
                worker_pid INTEGER,
                last_failure_error TEXT,
                max_runtime_seconds INTEGER,
                last_heartbeat_at INTEGER,
                current_run_id INTEGER,
                workflow_template_id TEXT,
                current_step_key TEXT,
                skills TEXT,
                model_override TEXT,
                max_retries INTEGER,
                goal_mode INTEGER DEFAULT 0,
                goal_max_turns INTEGER,
                session_id TEXT
            )
        """)
        cursor.execute("""
            CREATE TABLE task_links (
                parent_id TEXT,
                child_id TEXT,
                FOREIGN KEY(parent_id) REFERENCES tasks(id),
                FOREIGN KEY(child_id) REFERENCES tasks(id)
            )
        """)
        conn.commit()
    
    # Patch the global DB_PATH in the dispatcher module
    with patch.object(dispatcher, 'DB_PATH', db_file):
        yield db_file

class MockProcess:
    def __init__(self, returncode=0, stdout="", stderr=""):
        self.returncode = returncode
        self.stdout = stdout
        self.stderr = stderr

def test_kanban_dispatcher_full_lifecycle(mock_db_path):
    task_id = "test_task_1"
    title = "[builder] Test Task"
    
    # Setup initial state
    with sqlite3.connect(mock_db_path) as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO tasks (id, title, status, priority, created_at) VALUES (?, ?, 'todo', 0, ?)", 
            (task_id, title, int(time.time()))
        )
        conn.commit()
        
    def get_task():
        with sqlite3.connect(mock_db_path) as conn:
            conn.row_factory = sqlite3.Row
            return dict(conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone())

    # Step 1: Promote and assign
    dispatcher.run_dispatch_cycle()
    task = get_task()
    assert task['status'] == 'ready'
    assert task['assignee'] == 'builder'
    assert task['priority'] == 0

    # Step 2: Builder finishes (creates PR)
    with patch("subprocess.run", return_value=MockProcess()):
        with sqlite3.connect(mock_db_path) as conn:
            conn.execute("UPDATE tasks SET status = 'blocked' WHERE id = ?", (task_id,))
            conn.commit()
        dispatcher.run_dispatch_cycle()
        
    task = get_task()
    assert task['status'] == 'ready'
    assert task['assignee'] == 'reviewer'
    assert "[PR Opened by builder]" in task['title']

    # Helper for simulating GH CLI reviews
    def simulate_agent_work(mock_decision, mock_state=None):
        def mock_subprocess_run(cmd, *args, **kwargs):
            if cmd[0:3] == ["gh", "pr", "view"]:
                res = f'{{"reviewDecision": "{mock_decision}"'
                if mock_state:
                    res += f', "state": "{mock_state}"'
                res += '}'
                return MockProcess(stdout=res)
            return MockProcess()
            
        with sqlite3.connect(mock_db_path) as conn:
            conn.execute("UPDATE tasks SET status = 'blocked', workspace_path = ? WHERE id = ?", (f"/tmp/{task_id}_wt", task_id))
            conn.commit()
            
        with patch("subprocess.run", side_effect=mock_subprocess_run):
            dispatcher.run_dispatch_cycle()

    # Step 3: Reviewer Rejects
    simulate_agent_work("CHANGES_REQUESTED")
    task = get_task()
    assert task['status'] == 'ready'
    assert task['assignee'] == 'builder'
    assert task['priority'] == -1

    # Step 4: Builder fixes
    with patch("subprocess.run", return_value=MockProcess()):
        with sqlite3.connect(mock_db_path) as conn:
            conn.execute("UPDATE tasks SET status = 'blocked', workspace_path = ? WHERE id = ?", (f"/tmp/wt", task_id))
            conn.commit()
        dispatcher.run_dispatch_cycle()
    task = get_task()
    assert task['assignee'] == 'reviewer'

    # Step 5: Reviewer Approves
    simulate_agent_work("APPROVED")
    task = get_task()
    assert task['status'] == 'blocked'
    assert "[Human Review]" in task['title']

    # Step 6: Human Merges
    simulate_agent_work("APPROVED", mock_state="MERGED")
    task = get_task()
    assert task['status'] == 'done'
