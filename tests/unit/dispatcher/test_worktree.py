"""Unit tests for dispatcher/worktree.py: worktree provisioning, cleanup, timeouts, and conflict routing."""

import json
import os
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from dispatcher.worktree import (
    resolve_task_repo_path,
    setup_worktree,
    _remove_worktree,
    _handle_local_merge_conflict,
    _handle_pr_conflict_from_github,
    _delete_remote_branch,
)


def _init_tasks_db(conn: sqlite3.Connection):
    conn.execute(
        """
        CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            title TEXT,
            status TEXT DEFAULT 'todo',
            assignee TEXT,
            skills TEXT,
            metadata TEXT,
            workspace_kind TEXT,
            workspace_path TEXT,
            branch_name TEXT,
            updated_at INTEGER
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
    conn.commit()


# --- 1. resolve_task_repo_path ---

def test_resolve_task_repo_path_from_board_git_url(tmp_path: Path):
    """Local repo path in board git_url is preferred when valid."""
    repo = tmp_path / "my_repo"
    repo.mkdir()
    (repo / ".git").mkdir()

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _init_tasks_db(conn)
    conn.execute("INSERT INTO boards (slug, git_url) VALUES ('b1', ?)", (str(repo),))
    conn.commit()

    resolved = resolve_task_repo_path(conn.cursor(), "b1", None)
    assert resolved == repo.resolve()


def test_resolve_task_repo_path_from_tenant(tmp_path: Path):
    """Absolute tenant path with .git resolves correctly."""
    repo = tmp_path / "tenant_repo"
    repo.mkdir()
    (repo / ".git").mkdir()

    resolved = resolve_task_repo_path(None, None, str(repo))
    assert resolved == repo


# --- 2. _remove_worktree ---

def test_remove_worktree_missing_path_noops(tmp_path: Path):
    """Missing or empty path does nothing and does not invoke git."""
    repo = tmp_path / "repo"
    repo.mkdir()

    with patch("subprocess.run") as mock_run:
        _remove_worktree(str(tmp_path / "does_not_exist"), repo)
        mock_run.assert_not_called()
        _remove_worktree(None, repo)
        _remove_worktree("", repo)
        mock_run.assert_not_called()


def test_remove_worktree_survives_hanging_remove(tmp_path: Path):
    """Hanging `git worktree remove` is caught by timeout, and fallback `git worktree prune` is called."""
    repo = tmp_path / "repo"
    repo.mkdir()
    wt = tmp_path / "wt"
    wt.mkdir()

    prune_called = []
    orig_run = subprocess.run

    def fake_run(cmd, *args, **kwargs):
        if isinstance(cmd, list) and cmd[:3] == ["git", "worktree", "remove"]:
            assert kwargs.get("timeout") is not None
            raise subprocess.TimeoutExpired(cmd=cmd, timeout=30)
        if isinstance(cmd, list) and cmd[:3] == ["git", "worktree", "prune"]:
            prune_called.append(cmd)
            return orig_run(["git", "--version"], *args, **kwargs)
        return orig_run(cmd, *args, **kwargs)

    with patch("dispatcher.worktree.subprocess.run", side_effect=fake_run):
        # Must not raise
        _remove_worktree(str(wt), repo)

    assert len(prune_called) == 1


# --- 3. _delete_remote_branch ---

def test_delete_remote_branch_timeout_handled(tmp_path: Path):
    """Timeout during remote branch deletion logs a warning and returns cleanly."""
    repo = tmp_path / "repo"
    repo.mkdir()

    def fake_run(cmd, *args, **kwargs):
        raise subprocess.TimeoutExpired(cmd=cmd, timeout=10)

    with patch("dispatcher.worktree.subprocess.run", side_effect=fake_run):
        # Must not raise
        _delete_remote_branch("t-123", repo)


# --- 4. Conflict Handlers ---

def test_handle_local_merge_conflict_increments_retries_and_routes_to_builder():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _init_tasks_db(conn)
    conn.execute(
        "INSERT INTO tasks (id, title, status, assignee, metadata, updated_at) VALUES ('t1', 'Feature 1', 'running', 'zf-builder', '{}', 1000)"
    )
    conn.commit()

    cur = conn.cursor()
    _handle_local_merge_conflict(cur, "t1", "Feature 1", "/fake/ws", ["file.py"], now=1001)
    conn.commit()

    row = conn.execute("SELECT title, status, assignee, metadata FROM tasks WHERE id = 't1'").fetchone()
    assert "[PR Conflict]" in row["title"]
    assert row["status"] == "todo"
    assert row["assignee"] == "zf-builder"
    meta = json.loads(row["metadata"])
    assert meta["conflict_retries"] == 1


def test_handle_local_merge_conflict_blocks_when_max_retries_exceeded():
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _init_tasks_db(conn)
    initial_meta = json.dumps({"conflict_retries": 3})
    conn.execute(
        "INSERT INTO tasks (id, title, status, assignee, metadata, updated_at) VALUES ('t2', 'Feature 2', 'running', 'zf-builder', ?, 1000)",
        (initial_meta,)
    )
    conn.commit()

    cur = conn.cursor()
    with patch.dict(os.environ, {"ZEROFACTORY_MAX_CONFLICT_RETRIES": "3"}):
        _handle_local_merge_conflict(cur, "t2", "Feature 2", "/fake/ws", ["file.py"], now=1001)
        conn.commit()

    row = conn.execute("SELECT status, metadata FROM tasks WHERE id = 't2'").fetchone()
    assert row["status"] == "blocked"
    meta = json.loads(row["metadata"])
    assert meta["conflict_retries"] == 4
