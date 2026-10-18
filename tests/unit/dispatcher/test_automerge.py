"""Unit tests for Auto-Merge / YOLO mode functionality.

Tests tag/label resolution, prompt injection, and dispatcher auto-merge execution.
"""

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dispatcher.github_pr import attempt_pr_automerge, is_task_automerge_enabled
from dispatcher.worker_spawner import spawn_agent_worker


def test_is_task_automerge_enabled_board_default():
    """Board default automerge=True enables auto-merge when no task tags or labels override it."""
    task = {"tags": [], "metadata": {}}
    board_off = {"automerge": False}
    board_on = {"automerge": True}

    assert is_task_automerge_enabled(task, board_off) is False
    assert is_task_automerge_enabled(task, board_on) is True
    assert is_task_automerge_enabled(task, None) is False


def test_is_task_automerge_enabled_task_tags_override():
    """Task tags 'automerge' or 'yolo' enable auto-merge even if board default is False."""
    board_off = {"automerge": False}

    assert is_task_automerge_enabled({"tags": ["automerge"]}, board_off) is True
    assert is_task_automerge_enabled({"tags": ["yolo"]}, board_off) is True
    assert is_task_automerge_enabled({"tags": "tag:automerge"}, board_off) is True
    assert is_task_automerge_enabled({"tags": json.dumps(["yolo"])}, board_off) is True


def test_is_task_automerge_enabled_hitl_override_wins():
    """Opt-out tags 'hitl' or 'manual-review' force HITL even if board default is True."""
    board_on = {"automerge": True}

    assert is_task_automerge_enabled({"tags": ["hitl"]}, board_on) is False
    assert is_task_automerge_enabled({"tags": ["manual-review"]}, board_on) is False
    assert is_task_automerge_enabled({"tags": ["yolo", "hitl"]}, board_on) is False


def test_is_task_automerge_enabled_jira_labels():
    """Jira external_issue labels control auto-merge resolution."""
    board_off = {"automerge": False}
    board_on = {"automerge": True}

    task_yolo = {
        "tags": [],
        "metadata": {"external_issue": {"labels": ["automerge", "backend"]}},
    }
    assert is_task_automerge_enabled(task_yolo, board_off) is True

    task_hitl = {
        "tags": [],
        "metadata": {"external_issue": {"labels": ["hitl", "security"]}},
    }
    assert is_task_automerge_enabled(task_hitl, board_on) is False


def test_attempt_pr_automerge_skip_git(monkeypatch):
    """When ZEROFACTORY_SKIP_GIT is set, attempt_pr_automerge succeeds immediately."""
    monkeypatch.setenv("ZEROFACTORY_SKIP_GIT", "1")
    ok, msg = attempt_pr_automerge("https://github.com/org/repo/pull/1", Path("/tmp"))
    assert ok is True
    assert "skip-git" in msg


def test_attempt_pr_automerge_empty_url(monkeypatch):
    """Empty PR URL returns False."""
    monkeypatch.delenv("ZEROFACTORY_SKIP_GIT", raising=False)
    ok, msg = attempt_pr_automerge("", Path("/tmp"))
    assert ok is False
    assert "No PR URL" in msg


@patch("subprocess.run")
def test_attempt_pr_automerge_success(mock_run, monkeypatch):
    """Successful gh pr merge returns True."""
    monkeypatch.delenv("ZEROFACTORY_SKIP_GIT", raising=False)
    mock_run.return_value = MagicMock(returncode=0, stdout="Merged\n", stderr="")

    ok, msg = attempt_pr_automerge("https://github.com/org/repo/pull/10", Path("/tmp"))
    assert ok is True
    assert "Squash merged successfully" in msg
    mock_run.assert_called_once()


@patch("subprocess.run")
def test_attempt_pr_automerge_fallback_to_auto(mock_run, monkeypatch):
    """When status checks are required, falls back to gh pr merge --auto."""
    monkeypatch.delenv("ZEROFACTORY_SKIP_GIT", raising=False)
    # First call fails because checks are required; second call with --auto succeeds
    mock_run.side_effect = [
        MagicMock(returncode=1, stdout="", stderr="required status checks are in progress"),
        MagicMock(returncode=0, stdout="Auto-merge enabled\n", stderr=""),
    ]

    ok, msg = attempt_pr_automerge("https://github.com/org/repo/pull/10", Path("/tmp"))
    assert ok is True
    assert "Auto-merge enabled" in msg
    assert mock_run.call_count == 2


def test_worker_prompt_automerge_injection(tmp_path, monkeypatch):
    """When automerge is active, prompts for builder and reviewer contain the auto-merge directive."""
    db_file = tmp_path / "test.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute("CREATE TABLE boards (slug TEXT PRIMARY KEY, automerge INTEGER)")
    conn.execute("CREATE TABLE tasks (id TEXT PRIMARY KEY, tags TEXT, metadata TEXT, repo_alias TEXT)")
    conn.execute("INSERT INTO boards VALUES ('test-board', 1)")
    conn.execute("INSERT INTO tasks VALUES ('t1', '[]', '{}', 'main-repo')")
    conn.commit()
    conn.close()

    monkeypatch.setenv("ZEROFACTORY_DB", str(db_file))
    monkeypatch.delenv("ZEROFACTORY_SKIP_WORKER_SPAWN", raising=False)
    monkeypatch.setenv("ZEROFACTORY_SKIP_GIT", "1")

    with (
        patch("subprocess.Popen") as mock_popen,
        patch("dispatcher.worker_spawner.resolve_profile_state_db", return_value=None),
    ):
        mock_proc = MagicMock()
        mock_proc.pid = 1234
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        # 1. zf-builder prompt with automerge=True
        spawn_agent_worker(
            task_id="t1",
            title="Fix bug",
            description="Fixing something",
            priority="P1",
            assignee="zf-builder",
            workspace_path=str(tmp_path),
            branch_name="task/t1",
            board_slug="test-board",
        )
        cmd_builder = mock_popen.call_args[0][0]
        prompt_builder = cmd_builder[cmd_builder.index("-q") + 1]
        assert "🚨 CRITICAL: AUTO-MERGE ACTIVE" in prompt_builder
        assert "This task is operating in Auto-Merge mode" in prompt_builder

        # 2. zf-reviewer prompt with automerge=True
        spawn_agent_worker(
            task_id="t1",
            title="Fix bug",
            description="Fixing something",
            priority="P1",
            assignee="zf-reviewer",
            workspace_path=str(tmp_path),
            branch_name="task/t1",
            board_slug="test-board",
        )
        cmd_reviewer = mock_popen.call_args[0][0]
        prompt_reviewer = cmd_reviewer[cmd_reviewer.index("-q") + 1]
        assert "🚨 CRITICAL: AUTO-MERGE ACTIVE" in prompt_reviewer
        assert "This PR will be automatically merged into the target branch" in prompt_reviewer

        # 3. Disable automerge on board
        conn = sqlite3.connect(str(db_file))
        conn.execute("UPDATE boards SET automerge = 0 WHERE slug = 'test-board'")
        conn.commit()
        conn.close()

        spawn_agent_worker(
            task_id="t1",
            title="Fix bug",
            description="Fixing something",
            priority="P1",
            assignee="zf-builder",
            workspace_path=str(tmp_path),
            branch_name="task/t1",
            board_slug="test-board",
        )
        cmd_no_automerge = mock_popen.call_args[0][0]
        prompt_no_automerge = cmd_no_automerge[cmd_no_automerge.index("-q") + 1]
        assert "🚨 CRITICAL: AUTO-MERGE ACTIVE" not in prompt_no_automerge


def test_scheduler_automerge_on_approval(tmp_path, monkeypatch):
    """When zf-reviewer approves and automerge is enabled, scheduler auto-merges and moves task to done."""
    from dispatcher.scheduler import _poll_pr_and_route_review

    db_file = tmp_path / "kanban.db"
    conn = sqlite3.connect(str(db_file))
    conn.row_factory = sqlite3.Row
    conn.execute("CREATE TABLE boards (slug TEXT PRIMARY KEY, automerge INTEGER)")
    conn.execute(
        """CREATE TABLE tasks (
            id TEXT PRIMARY KEY,
            title TEXT,
            assignee TEXT,
            status TEXT,
            board_slug TEXT,
            repo_alias TEXT,
            pr_url TEXT,
            tags TEXT,
            workspace_path TEXT,
            metadata TEXT,
            updated_at INTEGER
        )"""
    )
    conn.execute("CREATE TABLE board_repositories (board_slug TEXT, repo_alias TEXT, additional_reviewer_usernames TEXT)")
    conn.execute("CREATE TABLE task_comments (id INTEGER PRIMARY KEY, task_id TEXT, author TEXT, body TEXT, created_at INTEGER)")
    conn.execute("CREATE TABLE task_activity (id INTEGER PRIMARY KEY, task_id TEXT, actor TEXT, action TEXT, details TEXT, created_at INTEGER)")

    conn.execute("INSERT INTO boards VALUES ('test-board', 1)")
    conn.execute("INSERT INTO board_repositories VALUES ('test-board', 'repo-1', '[]')")
    conn.execute(
        """INSERT INTO tasks VALUES (
            'task-100', 'Auto-merge feature', 'zf-reviewer', 'blocked', 'test-board',
            'repo-1', 'https://github.com/org/repo/pull/100', '[]', '/tmp/ws/100',
            '{"blocked_reason_type": "approved"}', 1000
        )"""
    )
    conn.commit()

    cursor = conn.cursor()
    cursor.execute("SELECT * FROM tasks WHERE id = 'task-100'")
    row = cursor.fetchone()

    # Mock gh pr view returning APPROVED reviewDecision and open state
    fake_pr_view = {
        "state": "OPEN",
        "reviewDecision": "APPROVED",
        "url": "https://github.com/org/repo/pull/100",
        "mergeable": "MERGEABLE",
        "headRefOid": "abc1234",
    }

    def fake_subprocess_run(cmd, *args, **kwargs):
        if "view" in cmd:
            return MagicMock(returncode=0, stdout=json.dumps(fake_pr_view), stderr="")
        if "merge" in cmd:
            return MagicMock(returncode=0, stdout="Merged\n", stderr="")
        if "api" in cmd:
            return MagicMock(returncode=0, stdout="[]", stderr="")
        return MagicMock(returncode=0, stdout="", stderr="")

    with (
        patch("subprocess.run", side_effect=fake_subprocess_run),
        patch("dispatcher._remove_worktree"),
        patch("dispatcher.stop_task_worker"),
        patch("dispatcher._delete_remote_branch"),
    ):
        result = _poll_pr_and_route_review(
            conn=conn,
            cursor=cursor,
            row=row,
            meta={"blocked_reason_type": "approved"},
            workspace_path="/tmp/ws/100",
            repo_path=tmp_path,
            board_slug="test-board",
            tenant=None,
            db_path=db_file,
            now=2000,
        )

        assert result is True

        # Task should now be in 'done' status
        cursor.execute("SELECT status, metadata FROM tasks WHERE id = 'task-100'")
        updated_task = cursor.fetchone()
        assert updated_task["status"] == "done"

        # Activity row should record 'automerged'
        cursor.execute("SELECT action, details FROM task_activity WHERE task_id = 'task-100'")
        act = cursor.fetchone()
        assert act is not None
        assert act["action"] == "automerged"
        assert "Auto-Merge mode" in act["details"]

    conn.close()

