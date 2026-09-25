"""Unit tests for dispatcher/worker_spawner.py: agent worker spawning, session isolation, and environment injection."""

import os
import sqlite3
import tempfile
import time
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from dispatcher.worker_spawner import (
    _inject_langfuse_env,
    spawn_agent_worker,
)


def test_inject_langfuse_env():
    """Verify Langfuse env injection when enabled vs disabled."""
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT, updated_at INTEGER)")
    conn.execute("INSERT INTO settings VALUES ('langfuse_enabled', 'true', 1000)")
    conn.execute("INSERT INTO settings VALUES ('langfuse_public_key', 'pk-123', 1000)")
    conn.execute("INSERT INTO settings VALUES ('langfuse_secret_key', 'sk-456', 1000)")
    conn.commit()

    env = {}
    _inject_langfuse_env(env, conn_or_cursor=conn)
    assert env["HERMES_LANGFUSE_PUBLIC_KEY"] == "pk-123"
    assert env["HERMES_LANGFUSE_SECRET_KEY"] == "sk-456"

    # Now disable
    conn.execute("UPDATE settings SET value = 'false' WHERE key = 'langfuse_enabled'")
    conn.commit()
    _inject_langfuse_env(env, conn_or_cursor=conn)
    assert "HERMES_LANGFUSE_PUBLIC_KEY" not in env
    assert "HERMES_LANGFUSE_SECRET_KEY" not in env


def test_spawn_agent_worker_skip_env():
    """When ZEROFACTORY_SKIP_WORKER_SPAWN is set, spawn returns None immediately."""
    with patch.dict(os.environ, {"ZEROFACTORY_SKIP_WORKER_SPAWN": "1"}):
        pid, sess = spawn_agent_worker("t1", "Title", "Desc", "P1", "zf-builder", "/tmp", "task/t1")
        assert pid is None
        assert sess is None


def test_spawn_agent_worker_cmd_and_session_isolation():
    """Verify hermes command structure, start_new_session=True, and session matching."""
    with tempfile.NamedTemporaryFile(suffix=".db") as tmp_db:
        conn = sqlite3.connect(tmp_db.name)
        conn.execute(
            """
            CREATE TABLE sessions (
                id TEXT PRIMARY KEY,
                title TEXT,
                cwd TEXT,
                started_at REAL
            )
            """
        )
        now = time.time()
        # Concurrent session from other task
        conn.execute("INSERT INTO sessions VALUES ('sess-other', 'Task ID: zf-other', '/ws/other', ?)", (now + 0.1,))
        # Session for target task
        conn.execute("INSERT INTO sessions VALUES ('sess-mine', 'Task ID: zf-mine', '/ws/mine', ?)", (now,))
        conn.commit()
        conn.close()

        import dispatcher
        with patch.object(dispatcher, "resolve_profile_state_db", return_value=Path(tmp_db.name)), \
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
                workspace_path="/ws/mine",
                branch_name="task/zf-mine"
            )

            assert pid == 99999
            assert sess == "sess-mine"
            assert mock_popen.called
            args, kwargs = mock_popen.call_args
            cmd = args[0]
            env = kwargs.get("env", {})

            assert "--yolo" in cmd
            assert kwargs.get("start_new_session") is True
            assert env.get("HERMES_PROFILE") == "zf-reviewer"
