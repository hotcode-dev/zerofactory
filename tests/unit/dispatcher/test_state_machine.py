"""Unit tests for dispatcher/state_machine.py: task lifecycle transitions and process teardown."""

import json
import sqlite3
import pytest
from unittest.mock import patch

from dispatcher.state_machine import (
    VALID_TRANSITIONS,
    InvalidStateTransitionError,
    transition_task,
)


@pytest.fixture
def db_conn():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            board_slug TEXT,
            title TEXT NOT NULL,
            description TEXT,
            priority TEXT,
            status TEXT NOT NULL,
            assignee TEXT,
            target_branch TEXT,
            repo_alias TEXT,
            workspace_path TEXT,
            branch_name TEXT,
            pr_url TEXT,
            tags TEXT,
            metadata TEXT,
            created_at INTEGER NOT NULL,
            updated_at INTEGER NOT NULL,
            worker_pid INTEGER DEFAULT NULL,
            started_at INTEGER DEFAULT NULL,
            blocked_reason TEXT DEFAULT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE task_activity (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            actor TEXT NOT NULL,
            action TEXT NOT NULL,
            details TEXT,
            created_at INTEGER NOT NULL
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE task_comments (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            task_id TEXT NOT NULL,
            author TEXT NOT NULL,
            body TEXT NOT NULL,
            created_at INTEGER NOT NULL
        )
        """
    )
    yield conn
    conn.close()


def test_transition_valid_triage_to_todo(db_conn):
    """Verify triage -> todo transition."""
    db_conn.execute(
        """
        INSERT INTO tasks (id, title, status, assignee, created_at, updated_at)
        VALUES ('t1', 'Title 1', 'triage', 'zf-orchestrator', 1000, 1000)
        """
    )
    db_conn.commit()

    res = transition_task(
        db_conn,
        "t1",
        "todo",
        target_assignee="zf-builder",
        actor="human",
        comment="Spec approved",
    )
    assert res["status"] == "todo"
    assert res["prev_status"] == "triage"
    assert res["assignee"] == "zf-builder"

    cur = db_conn.cursor()
    cur.execute("SELECT status, assignee FROM tasks WHERE id = 't1'")
    row = cur.fetchone()
    assert row["status"] == "todo"
    assert row["assignee"] == "zf-builder"

    cur.execute("SELECT actor, action, details FROM task_activity WHERE task_id = 't1'")
    act = cur.fetchone()
    assert act["actor"] == "human"
    assert act["action"] == "status_change"
    assert act["details"] == "triage -> todo"

    cur.execute("SELECT author, body FROM task_comments WHERE task_id = 't1'")
    cmt = cur.fetchone()
    assert cmt["author"] == "human"
    assert cmt["body"] == "Spec approved"


def test_transition_invalid_raises(db_conn):
    """Verify invalid transition raises InvalidStateTransitionError."""
    db_conn.execute(
        """
        INSERT INTO tasks (id, title, status, assignee, created_at, updated_at)
        VALUES ('t2', 'Title 2', 'todo', 'zf-builder', 1000, 1000)
        """
    )
    db_conn.commit()

    with pytest.raises(InvalidStateTransitionError):
        transition_task(db_conn, "t2", "done")


def test_transition_exiting_running_terminates_worker(db_conn):
    """Verify exiting running triggers terminate_task_worker and clears worker_pid/started_at."""
    meta = json.dumps({"worker_pid": 1234, "started_at": 1000})
    db_conn.execute(
        """
        INSERT INTO tasks (id, title, status, assignee, worker_pid, started_at, metadata, created_at, updated_at)
        VALUES ('t3', 'Title 3', 'running', 'zf-builder', 1234, 1000, ?, 1000, 1000)
        """,
        (meta,),
    )
    db_conn.commit()

    with patch("dispatcher.state_machine.terminate_task_worker") as mock_term:
        res = transition_task(
            db_conn, "t3", "blocked", blocked_reason="precommit_failed"
        )
        assert res["status"] == "blocked"
        assert res["worker_pid"] is None
        assert res["started_at"] is None
        assert res["blocked_reason"] == "precommit_failed"
        mock_term.assert_called_once_with("t3", 1234)

    cur = db_conn.cursor()
    cur.execute(
        "SELECT worker_pid, started_at, blocked_reason, metadata FROM tasks WHERE id = 't3'"
    )
    row = cur.fetchone()
    assert row["worker_pid"] is None
    assert row["started_at"] is None
    assert row["blocked_reason"] == "precommit_failed"
    saved_meta = json.loads(row["metadata"])
    assert "worker_pid" not in saved_meta
    assert "started_at" not in saved_meta


def test_transition_exiting_blocked_clears_blocked_state(db_conn):
    """Verify exiting blocked clears blocked_reason and failure retries from metadata."""
    meta = json.dumps(
        {
            "worker_failure_retries": 3,
            "last_worker_failure": "Crashed",
            "blocked_reason_type": "crash",
            "custom_key": "preserve_me",
        }
    )
    db_conn.execute(
        """
        INSERT INTO tasks (id, title, status, assignee, blocked_reason, metadata, created_at, updated_at)
        VALUES ('t4', 'Title 4', 'blocked', 'human', 'crash', ?, 1000, 1000)
        """,
        (meta,),
    )
    db_conn.commit()

    res = transition_task(db_conn, "t4", "todo", target_assignee="zf-builder")
    assert res["status"] == "todo"
    assert res["blocked_reason"] is None
    assert "worker_failure_retries" not in res["metadata"]
    assert "last_worker_failure" not in res["metadata"]
    assert res["metadata"]["custom_key"] == "preserve_me"

    cur = db_conn.cursor()
    cur.execute("SELECT blocked_reason, metadata FROM tasks WHERE id = 't4'")
    row = cur.fetchone()
    assert row["blocked_reason"] is None
    saved_meta = json.loads(row["metadata"])
    assert "worker_failure_retries" not in saved_meta
    assert "last_worker_failure" not in saved_meta
    assert saved_meta["custom_key"] == "preserve_me"


def test_transition_to_todo_clears_interview_flags(db_conn):
    """Verify transitioning to todo clears interview flags."""
    meta = json.dumps({"awaiting_interview": True, "reply_interview": "Some reply"})
    db_conn.execute(
        """
        INSERT INTO tasks (id, title, status, assignee, metadata, created_at, updated_at)
        VALUES ('t5', 'Title 5', 'triage', 'zf-orchestrator', ?, 1000, 1000)
        """,
        (meta,),
    )
    db_conn.commit()

    res = transition_task(db_conn, "t5", "todo")
    assert "awaiting_interview" not in res["metadata"]
    assert "reply_interview" not in res["metadata"]


def test_transition_running_to_running_handoff(db_conn):
    """Verify intra-state running -> running handoff terminates old worker if pid differs."""
    db_conn.execute(
        """
        INSERT INTO tasks (id, title, status, assignee, worker_pid, started_at, created_at, updated_at)
        VALUES ('t6', 'Title 6', 'running', 'zf-builder', 1111, 1000, 1000, 1000)
        """
    )
    db_conn.commit()

    with patch("dispatcher.state_machine.terminate_task_worker") as mock_term:
        res = transition_task(
            db_conn,
            "t6",
            "running",
            target_assignee="zf-reviewer",
            worker_pid=2222,
            started_at=2000,
        )
        assert res["status"] == "running"
        assert res["assignee"] == "zf-reviewer"
        assert res["worker_pid"] == 2222
        assert res["started_at"] == 2000
        mock_term.assert_called_once_with("t6", 1111)


def test_transition_nonexistent_task(db_conn):
    """Verify transition on nonexistent task raises ValueError."""
    with pytest.raises(ValueError, match="not found"):
        transition_task(db_conn, "nonexistent", "todo")
