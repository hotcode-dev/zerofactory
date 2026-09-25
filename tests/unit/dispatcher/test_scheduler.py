"""Unit tests for dispatcher/scheduler.py: dispatch cycle, concurrency flock, dependency unblocking, and WIP limits."""

import fcntl
import json
import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from dispatcher.scheduler import run_dispatch_cycle


def _init_test_db(db_path: Path):
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY,
                title TEXT,
                description TEXT,
                status TEXT DEFAULT 'todo',
                assignee TEXT,
                priority TEXT DEFAULT 'P1',
                metadata TEXT,
                skills TEXT,
                workspace_kind TEXT,
                workspace_path TEXT,
                branch_name TEXT,
                board_slug TEXT,
                tenant TEXT,
                pr_url TEXT,
                updated_at INTEGER,
                created_at INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE task_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_id TEXT,
                child_id TEXT,
                link_type TEXT,
                created_at INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE task_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                actor TEXT,
                action TEXT,
                details TEXT,
                created_at INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE task_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                author TEXT,
                body TEXT,
                created_at INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE boards (
                slug TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                git_url TEXT,
                target_branch TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at INTEGER
            )
            """
        )
        conn.commit()


def test_run_dispatch_cycle_concurrent_flock_skipped(tmp_path: Path):
    """When cross-process lock is already held, cycle skips with concurrent_cycle_active."""
    db_path = tmp_path / "test.db"
    _init_test_db(db_path)

    lock_file = tmp_path / "dispatcher.lock"

    # Hold exclusive flock in this process
    fd = os.open(str(lock_file), os.O_CREAT | os.O_RDWR, 0o666)
    fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)

    try:
        import dispatcher
        with patch.object(dispatcher, "get_dispatcher_lock_path", return_value=lock_file):
            res = run_dispatch_cycle(db_path)
            assert res["ok"] is True
            assert res.get("skipped") is True
            assert res.get("reason") == "concurrent_cycle_active"
    finally:
        fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def test_run_dispatch_cycle_unblocks_prerequisite_dependencies(tmp_path: Path):
    """Task blocked on parent task is automatically unblocked when parent is done."""
    db_path = tmp_path / "test.db"
    _init_test_db(db_path)

    now = 1000
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO tasks VALUES ('parent-1', 'Parent', '', 'done', 'zf-builder', 'P0', '{}', '[]', '', '', '', 'b1', '', '', ?, ?)",
            (now, now)
        )
        conn.execute(
            "INSERT INTO tasks VALUES ('child-1', 'Child', '', 'blocked', 'zf-builder', 'P0', '{}', '[]', '', '', '', 'b1', '', '', ?, ?)",
            (now, now)
        )
        conn.execute(
            "INSERT INTO task_links (parent_id, child_id, link_type, created_at) VALUES ('parent-1', 'child-1', 'blocks', ?)",
            (now,)
        )
        conn.commit()

    lock_file = tmp_path / "dispatcher.lock"
    import dispatcher
    with patch.object(dispatcher, "get_dispatcher_lock_path", return_value=lock_file), \
         patch.dict(os.environ, {"ZEROFACTORY_SKIP_WORKER_SPAWN": "1", "ZEROFACTORY_SKIP_GIT": "1"}):
        res = run_dispatch_cycle(db_path)
        assert res["ok"] is True
        assert res.get("unblocked", 0) >= 1

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        child = conn.execute("SELECT status FROM tasks WHERE id = 'child-1'").fetchone()
        # Either unblocked to 'todo' or promoted to 'running'
        assert child["status"] in ("todo", "running")


def test_run_dispatch_cycle_promotes_todo_to_running(tmp_path: Path):
    """Eligible todo task is promoted to running."""
    db_path = tmp_path / "test.db"
    _init_test_db(db_path)

    now = 1000
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO tasks VALUES ('t-todo', 'Work Item', '', 'todo', 'zf-builder', 'P0', '{}', '[]', '', '', '', 'b1', '', '', ?, ?)",
            (now, now)
        )
        conn.commit()

    lock_file = tmp_path / "dispatcher.lock"
    import dispatcher
    with patch.object(dispatcher, "get_dispatcher_lock_path", return_value=lock_file), \
         patch.dict(os.environ, {"ZEROFACTORY_SKIP_WORKER_SPAWN": "1", "ZEROFACTORY_SKIP_GIT": "1"}):
        res = run_dispatch_cycle(db_path)
        assert res["ok"] is True
        assert res.get("dispatched", 0) >= 1

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT status FROM tasks WHERE id = 't-todo'").fetchone()
        assert row["status"] == "running"
