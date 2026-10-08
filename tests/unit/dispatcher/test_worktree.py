"""Unit tests for dispatcher/worktree.py: worktree provisioning, cleanup, timeouts, and conflict routing."""

import json
import os
import sqlite3
import subprocess
from pathlib import Path
from unittest.mock import patch

from dispatcher.worktree import (
    _delete_remote_branch,
    _handle_local_merge_conflict,
    _remove_worktree,
    resolve_task_repo_path,
    setup_worktree,
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
    _handle_local_merge_conflict(
        cur, "t1", "Feature 1", "/fake/ws", ["file.py"], now=1001
    )
    conn.commit()

    row = conn.execute(
        "SELECT title, status, assignee, metadata FROM tasks WHERE id = 't1'"
    ).fetchone()
    # Conflict state lives in metadata; the handler must not mark the title
    assert "[PR Conflict]" not in row["title"]
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
        (initial_meta,),
    )
    conn.commit()

    cur = conn.cursor()
    with patch.dict(os.environ, {"ZEROFACTORY_MAX_CONFLICT_RETRIES": "3"}):
        _handle_local_merge_conflict(
            cur, "t2", "Feature 2", "/fake/ws", ["file.py"], now=1001
        )
        conn.commit()

    row = conn.execute(
        "SELECT status, assignee, metadata FROM tasks WHERE id = 't2'"
    ).fetchone()
    assert row["status"] == "blocked"
    assert row["assignee"] == "human"
    meta = json.loads(row["metadata"])
    assert meta["conflict_retries"] == 4
    assert meta["blocked_reason_type"] == "stuck"


def test_resolve_task_repo_path_multi_repo(tmp_path: Path):
    """Board repositories table resolves specific repo aliases correctly."""
    repo_primary = tmp_path / "primary"
    repo_primary.mkdir()
    (repo_primary / ".git").mkdir()

    repo_secondary = tmp_path / "secondary"
    repo_secondary.mkdir()
    (repo_secondary / ".git").mkdir()

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    _init_tasks_db(conn)
    conn.execute(
        """
        CREATE TABLE board_repositories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            board_slug TEXT,
            repo_alias TEXT,
            git_url TEXT,
            target_branch TEXT,
            additional_reviewer_usernames TEXT DEFAULT '[]'
        )
        """
    )
    conn.execute("INSERT INTO boards (slug, git_url) VALUES ('b-multi', ?)", (str(repo_primary),))
    conn.execute(
        "INSERT INTO board_repositories (board_slug, repo_alias, git_url, target_branch) VALUES ('b-multi', 'primary', ?, 'main')",
        (str(repo_primary),),
    )
    conn.execute(
        "INSERT INTO board_repositories (board_slug, repo_alias, git_url, target_branch) VALUES ('b-multi', 'secondary', ?, 'main')",
        (str(repo_secondary),),
    )
    conn.commit()

    cur = conn.cursor()
    # Resolve explicit secondary
    res_sec = resolve_task_repo_path(cur, "b-multi", None, repo_alias="secondary")
    assert res_sec == repo_secondary.resolve()

    # Resolve default primary
    res_prim = resolve_task_repo_path(cur, "b-multi", None)
    assert res_prim == repo_primary.resolve()


def test_setup_worktree_multi_repo_side_by_side(tmp_path: Path):
    """setup_worktree provisions primary writable worktree and sibling read-only detached worktree side-by-side."""
    primary_repo = tmp_path / "prim_repo"
    primary_repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=str(primary_repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "ZeroFactory"], cwd=str(primary_repo), check=True)
    subprocess.run(["git", "config", "user.email", "zf@example.com"], cwd=str(primary_repo), check=True)
    (primary_repo / "main.txt").write_text("prim init\n")
    subprocess.run(["git", "add", "."], cwd=str(primary_repo), check=True)
    subprocess.run(["git", "commit", "-m", "init prim"], cwd=str(primary_repo), check=True, capture_output=True)

    sibling_repo = tmp_path / "sib_repo"
    sibling_repo.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=str(sibling_repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "ZeroFactory"], cwd=str(sibling_repo), check=True)
    subprocess.run(["git", "config", "user.email", "zf@example.com"], cwd=str(sibling_repo), check=True)
    (sibling_repo / "lib.txt").write_text("sib init\n")
    subprocess.run(["git", "add", "."], cwd=str(sibling_repo), check=True)
    subprocess.run(["git", "commit", "-m", "init sib"], cwd=str(sibling_repo), check=True, capture_output=True)

    db_path = tmp_path / "tasks.db"
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    _init_tasks_db(conn)
    conn.execute(
        """
        CREATE TABLE board_repositories (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            board_slug TEXT,
            repo_alias TEXT,
            git_url TEXT,
            target_branch TEXT,
            additional_reviewer_usernames TEXT DEFAULT '[]'
        )
        """
    )
    conn.execute("INSERT INTO boards (slug, git_url, target_branch) VALUES ('test-board', ?, 'main')", (str(primary_repo),))
    conn.execute(
        "INSERT INTO board_repositories (board_slug, repo_alias, git_url, target_branch) VALUES ('test-board', 'prim', ?, 'main')",
        (str(primary_repo),),
    )
    conn.execute(
        "INSERT INTO board_repositories (board_slug, repo_alias, git_url, target_branch) VALUES ('test-board', 'sib', ?, 'main')",
        (str(sibling_repo),),
    )
    conn.execute(
        "INSERT INTO tasks (id, title, status, assignee, updated_at) VALUES ('t-101', 'Multi Repo Task', 'todo', 'zf-builder', 1000)"
    )
    conn.commit()

    cur = conn.cursor()
    # Intercept home directory to isolate worktrees under tmp_path / "home"
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    with (
        patch("dispatcher.worktree.Path.home", return_value=fake_home),
        patch.dict(os.environ, {"ZEROFACTORY_SKIP_GIT": ""}),
    ):
        ws_path = setup_worktree(
            cur,
            task_id="t-101",
            title="Multi Repo Task",
            assignee="zf-builder",
            tenant=None,
            db_path=db_path,
            board_slug="test-board",
            repo_alias="prim",
        )
        conn.commit()

        assert ws_path is not None
        prim_dir = Path(ws_path)
        assert prim_dir.exists()
        assert prim_dir.name == "prim"
        task_root = prim_dir.parent
        assert task_root.name == "t-101"

        # Check sibling side-by-side worktree
        sib_dir = task_root / "sib"
        assert sib_dir.exists()
        assert (sib_dir / "lib.txt").exists()

        # Teardown removes primary and sibling worktrees
        _remove_worktree(ws_path, primary_repo)
        assert not prim_dir.exists()
        assert not sib_dir.exists()

