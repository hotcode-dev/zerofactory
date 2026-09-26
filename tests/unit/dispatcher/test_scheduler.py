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


def test_run_dispatch_cycle_skips_pr_conflict_for_queued_or_builder_task(tmp_path: Path):
    """PR conflict check must not burn retries for tasks already in todo/ready or assigned to builder."""
    db_path = tmp_path / "test.db"
    _init_test_db(db_path)

    now = 1000
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO tasks VALUES ('t-conf-todo', 'Feature [PR Conflict]', '', 'todo', 'zf-builder', 'P0', '{\"conflict_retries\": 1}', '[]', '', ?, '', 'b1', '', 'https://github.com/foo/bar/pull/10', ?, ?)",
            (str(tmp_path), now, now)
        )
        conn.commit()

    lock_file = tmp_path / "dispatcher.lock"
    import dispatcher

    def fake_run(cmd, *args, **kwargs):
        if "rev-parse" in cmd:
            return MagicMock(returncode=0, stdout=str(tmp_path))
        return MagicMock(returncode=0, stdout=json.dumps({"state": "OPEN", "mergeable": "CONFLICTING", "url": "https://github.com/foo/bar/pull/10"}))

    with patch.object(dispatcher, "get_dispatcher_lock_path", return_value=lock_file), \
         patch.dict(os.environ, {"ZEROFACTORY_SKIP_WORKER_SPAWN": "1", "ZEROFACTORY_SKIP_GIT": ""}), \
         patch("dispatcher.resolve_task_repo_path", return_value=tmp_path), \
         patch("dispatcher.scheduler.subprocess.run", side_effect=fake_run), \
         patch.object(dispatcher, "_handle_pr_conflict_from_github") as mock_handle_conflict:
        res = run_dispatch_cycle(db_path)
        assert res["ok"] is True
        mock_handle_conflict.assert_not_called()

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT metadata FROM tasks WHERE id = 't-conf-todo'").fetchone()
        meta = json.loads(row["metadata"])
        # Conflict retries must not have been incremented
        assert meta.get("conflict_retries", 1) == 1


def test_run_dispatch_cycle_routes_blocked_human_pr_conflict_to_builder(tmp_path: Path):
    """A conflicting PR awaiting human review is routed to zf-builder for resolution."""
    db_path = tmp_path / "test.db"
    _init_test_db(db_path)

    now = 1000
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO tasks VALUES ('t-conf-blocked', 'Feature [Human Review]', '', 'blocked', 'human', 'P0', '{}', '[]', '', ?, '', 'b1', '', 'https://github.com/foo/bar/pull/20', ?, ?)",
            (str(tmp_path), now, now)
        )
        conn.commit()

    lock_file = tmp_path / "dispatcher.lock"
    import dispatcher

    def fake_run(cmd, *args, **kwargs):
        if "rev-parse" in cmd:
            return MagicMock(returncode=0, stdout=str(tmp_path))
        return MagicMock(returncode=0, stdout=json.dumps({"state": "OPEN", "mergeable": "CONFLICTING", "url": "https://github.com/foo/bar/pull/20"}))

    with patch.object(dispatcher, "get_dispatcher_lock_path", return_value=lock_file), \
         patch.dict(os.environ, {"ZEROFACTORY_SKIP_WORKER_SPAWN": "1", "ZEROFACTORY_SKIP_GIT": ""}), \
         patch("dispatcher.resolve_task_repo_path", return_value=tmp_path), \
         patch("dispatcher.scheduler.subprocess.run", side_effect=fake_run), \
         patch.object(dispatcher, "_handle_pr_conflict_from_github") as mock_handle_conflict:
        res = run_dispatch_cycle(db_path)
        assert res["ok"] is True
        mock_handle_conflict.assert_called_once()


def test_run_dispatch_cycle_routes_blocked_builder_pr_conflict_to_builder(tmp_path: Path):
    """A conflicting PR in blocked status assigned to zf-builder is routed to zf-builder for resolution."""
    db_path = tmp_path / "test.db"
    _init_test_db(db_path)

    now = 1000
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO tasks VALUES ('t-conf-builder-blocked', 'Feature [PR Conflict]', '', 'blocked', 'zf-builder', 'P0', '{}', '[]', '', ?, '', 'b1', '', 'https://github.com/foo/bar/pull/30', ?, ?)",
            (str(tmp_path), now, now)
        )
        conn.commit()

    lock_file = tmp_path / "dispatcher.lock"
    import dispatcher

    def fake_run(cmd, *args, **kwargs):
        if "rev-parse" in cmd:
            return MagicMock(returncode=0, stdout=str(tmp_path))
        return MagicMock(returncode=0, stdout=json.dumps({"state": "OPEN", "mergeable": "CONFLICTING", "url": "https://github.com/foo/bar/pull/30"}))

    with patch.object(dispatcher, "get_dispatcher_lock_path", return_value=lock_file), \
         patch.dict(os.environ, {"ZEROFACTORY_SKIP_WORKER_SPAWN": "1", "ZEROFACTORY_SKIP_GIT": ""}), \
         patch("dispatcher.resolve_task_repo_path", return_value=tmp_path), \
         patch("dispatcher.scheduler.subprocess.run", side_effect=fake_run), \
         patch.object(dispatcher, "_handle_pr_conflict_from_github") as mock_handle_conflict:
        res = run_dispatch_cycle(db_path)
        assert res["ok"] is True
        mock_handle_conflict.assert_called_once()


def test_run_dispatch_cycle_logs_conflict_fixing_activity(tmp_path: Path):
    """When a worker is dispatched on a task with conflict, conflict_fixing activity is logged."""
    db_path = tmp_path / "test.db"
    _init_test_db(db_path)

    now = 1000
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO tasks VALUES ('t-fix-conf', 'Fix feature [PR Conflict]', 'desc', 'todo', 'zf-builder', 'P1', '{\"conflict_retries\": 1}', '[]', '', ?, '', 'b1', '', '', ?, ?)",
            (str(tmp_path), now, now)
        )
        conn.commit()

    lock_file = tmp_path / "dispatcher.lock"
    import dispatcher

    with patch.object(dispatcher, "get_dispatcher_lock_path", return_value=lock_file), \
         patch.dict(os.environ, {"ZEROFACTORY_SKIP_GIT": "1"}), \
         patch.object(dispatcher, "setup_worktree", return_value=str(tmp_path)), \
         patch.object(dispatcher, "spawn_agent_worker", return_value=(9999, "sess-conf")):
        res = run_dispatch_cycle(db_path)
        assert res["ok"] is True
        assert res["dispatched"] == 1

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        acts = conn.execute("SELECT action, details FROM task_activity WHERE task_id = 't-fix-conf' ORDER BY id ASC").fetchall()
        actions = [a["action"] for a in acts]
        assert "start" in actions
        assert "conflict_fixing" in actions
        fixing_act = next(a for a in acts if a["action"] == "conflict_fixing")
        assert "attempt 1" in fixing_act["details"]


def test_run_dispatch_cycle_logs_conflict_resolved_activity(tmp_path: Path):
    """When a conflict task has resolved cleanly and updates PR, conflict_resolved activity is logged."""
    db_path = tmp_path / "test.db"
    _init_test_db(db_path)

    now = 1000
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO tasks VALUES ('t-conf-res', 'Fix feature [PR Conflict]', 'desc', 'done', 'zf-builder', 'P1', '{\"conflict_retries\": 1}', '[]', '', ?, '', 'b1', '', 'https://github.com/foo/bar/pull/50', ?, ?)",
            (str(tmp_path), now, now)
        )
        conn.commit()

    lock_file = tmp_path / "dispatcher.lock"
    import dispatcher

    def fake_subprocess_run(cmd, *args, **kwargs):
        if "rev-parse" in cmd:
            return MagicMock(returncode=0, stdout=str(tmp_path))
        if "status" in cmd:
            return MagicMock(returncode=0, stdout="")
        if "view" in cmd:
            return MagicMock(returncode=0, stdout=json.dumps({"url": "https://github.com/foo/bar/pull/50"}))
        return MagicMock(returncode=0, stdout="")

    with patch.object(dispatcher, "get_dispatcher_lock_path", return_value=lock_file), \
         patch.dict(os.environ, {"ZEROFACTORY_SKIP_GIT": ""}), \
         patch.object(dispatcher, "resolve_task_repo_path", return_value=tmp_path), \
         patch("dispatcher.scheduler.subprocess.run", side_effect=fake_subprocess_run), \
         patch.object(dispatcher, "clean_stale_git_locks"), \
         patch.object(dispatcher, "get_git_dir", return_value=None), \
         patch.object(dispatcher, "get_unmerged_status_files", return_value=[]), \
         patch.object(dispatcher, "check_unresolved_conflicts_safe", return_value=(True, [], "")), \
         patch.object(dispatcher, "pull_and_merge_main", return_value=(True, [], "")), \
         patch.object(dispatcher, "stop_task_worker"), \
         patch.object(dispatcher, "_remove_worktree"), \
         patch.object(dispatcher, "setup_worktree"):
        res = run_dispatch_cycle(db_path)
        assert res["ok"] is True
        assert res["prs_opened"] == 1

    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        acts = conn.execute("SELECT action, details FROM task_activity WHERE task_id = 't-conf-res' ORDER BY id ASC").fetchall()
        actions = [a["action"] for a in acts]
        assert "conflict_resolved" in actions
        assert "pr_opened" in actions


