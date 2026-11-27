"""Regression tests for exit-130, self-termination, handoff preservation, and push observability."""

import json
import sqlite3
from unittest.mock import MagicMock, patch

import pytest

from dispatcher.config import _active_workers
from dispatcher.reaper import reap_active_workers
from dispatcher.state_machine import transition_task


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


def test_transition_task_does_not_kill_self_when_agent_exits_running(db_conn):
    """An agent actor transitioning its own running task must not call terminate_task_worker."""
    db_conn.execute(
        """
        INSERT INTO tasks (id, title, status, assignee, metadata, created_at, updated_at, worker_pid)
        VALUES ('t-rev', 'Review task', 'running', 'zf-reviewer', '{"worker_pid": 42424}', 100, 100, 42424)
        """
    )
    with patch("dispatcher.state_machine.terminate_task_worker") as mock_term:
        transition_task(
            db_conn,
            "t-rev",
            "blocked",
            target_assignee="human",
            blocked_reason="approved",
            actor="zf-reviewer",
        )
    mock_term.assert_not_called()
    row = db_conn.execute(
        "SELECT status, worker_pid FROM tasks WHERE id = 't-rev'"
    ).fetchone()
    assert row["status"] == "blocked"
    assert row["worker_pid"] is None


def test_transition_task_still_terminates_worker_for_human_actor(db_conn):
    """A human actor moving a running task out of running still terminates the worker."""
    db_conn.execute(
        """
        INSERT INTO tasks (id, title, status, assignee, metadata, created_at, updated_at, worker_pid)
        VALUES ('t-hum', 'Human stop', 'running', 'zf-builder', '{"worker_pid": 42425}', 100, 100, 42425)
        """
    )
    with patch("dispatcher.state_machine.terminate_task_worker") as mock_term:
        transition_task(
            db_conn,
            "t-hum",
            "blocked",
            target_assignee="human",
            blocked_reason="paused",
            actor="user",
        )
    mock_term.assert_called_once_with("t-hum", 42425)


def test_reaper_preserves_awaiting_pr_on_exit_130(db_conn):
    """Exit 130 after builder already moved to awaiting_pr=True must not retry or clear awaiting_pr."""
    meta = {
        "worker_pid": 99999,
        "awaiting_pr": True,
        "sessions": [{"session_id": "s1", "status": "ongoing", "started_at": 100}],
    }
    db_conn.execute(
        """
        INSERT INTO tasks (id, title, status, assignee, metadata, created_at, updated_at, worker_pid)
        VALUES ('t-ho', 'Handoff task', 'running', 'zf-builder', ?, 100, 100, 99999)
        """,
        (json.dumps(meta),),
    )
    mock_proc = MagicMock()
    mock_proc.poll.return_value = 130
    _active_workers["t-ho"] = mock_proc
    try:
        reaped = reap_active_workers(db_conn.cursor(), 200)
        assert reaped == 1
        row = db_conn.execute(
            "SELECT status, metadata FROM tasks WHERE id = 't-ho'"
        ).fetchone()
        assert row["status"] == "running"
        saved_meta = json.loads(row["metadata"])
        assert saved_meta.get("awaiting_pr") is True
        assert not saved_meta.get("worker_failure_retries")
    finally:
        _active_workers.pop("t-ho", None)


def test_reaper_does_not_overwrite_concurrent_blocked_state_on_exit_130(db_conn):
    """If a worker moves its task to blocked right before exiting 130, reaper preserves blocked."""
    meta = {
        "worker_pid": 88888,
        "blocked_reason": "approved",
        "blocked_reason_type": "approved",
        "sessions": [{"session_id": "s1", "status": "ongoing", "started_at": 100}],
    }
    db_conn.execute(
        """
        INSERT INTO tasks (id, title, status, assignee, metadata, created_at, updated_at, worker_pid)
        VALUES ('t-blk', 'Review', 'running', 'zf-reviewer', ?, 100, 100, 88888)
        """,
        (json.dumps(meta),),
    )
    mock_proc = MagicMock()
    mock_proc.poll.return_value = 130
    _active_workers["t-blk"] = mock_proc

    class ConcurrentCursor:
        def __init__(self, real):
            self._real = real
            self._flipped = False

        def __getattr__(self, name):
            return getattr(self._real, name)

        def execute(self, sql, params=()):
            if (
                "SELECT assignee, status, title, metadata FROM tasks" in sql
                and not self._flipped
            ):
                self._flipped = True
                self._real.execute(
                    "UPDATE tasks SET status = 'blocked', assignee = 'human' WHERE id = 't-blk'"
                )
            return self._real.execute(sql, params)

    try:
        reaped = reap_active_workers(ConcurrentCursor(db_conn.cursor()), 200)
        assert reaped == 1
        row = db_conn.execute(
            "SELECT status, assignee, metadata FROM tasks WHERE id = 't-blk'"
        ).fetchone()
        assert row["status"] == "blocked"
        assert row["assignee"] == "human"
        saved_meta = json.loads(row["metadata"])
        assert not saved_meta.get("worker_failure_retries")
    finally:
        _active_workers.pop("t-blk", None)


def test_spawn_agent_worker_sets_hermes_kanban_task(tmp_path):
    """spawn_agent_worker must set HERMES_KANBAN_TASK=task_id in child env."""
    from dispatcher.worker_spawner import spawn_agent_worker

    workdir = tmp_path / "wt"
    workdir.mkdir()
    captured_env = {}

    def fake_popen(cmd, **kwargs):
        captured_env.update(kwargs.get("env") or {})
        proc = MagicMock()
        proc.pid = 54321
        return proc

    with (
        patch.dict("os.environ", {"ZEROFACTORY_SKIP_WORKER_SPAWN": ""}, clear=False),
        patch("dispatcher.worker_spawner.shutil.which", return_value="/usr/bin/hermes"),
        patch("dispatcher.worker_spawner.subprocess.Popen", side_effect=fake_popen),
        patch("dispatcher.worker_spawner.cleanup_process_artifacts"),
        patch("dispatcher.worker_spawner._inject_langfuse_env"),
        patch("paths.get_hermes_home", return_value=tmp_path),
    ):
        spawn_agent_worker(
            task_id="t-env",
            title="Env test",
            description="Test desc",
            priority="medium",
            assignee="zf-builder",
            workspace_path=str(workdir),
            branch_name="task/t-env",
        )
    _active_workers.pop("t-env", None)
    assert captured_env.get("HERMES_KANBAN_TASK") == "t-env"


def test_worker_spawner_ignores_dispatcher_retry_comments(tmp_path):
    """Dispatcher 'Retrying: ...' comments must not be injected as PR review comments."""
    from dispatcher.worker_spawner import spawn_agent_worker

    db_file = tmp_path / "zf.db"
    conn = sqlite3.connect(str(db_file))
    conn.execute(
        "CREATE TABLE task_comments (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, author TEXT, body TEXT, created_at INTEGER)"
    )
    conn.execute(
        "INSERT INTO task_comments (task_id, author, body, created_at) VALUES ('t-cmt', 'dispatcher', 'Retrying: Worker process exited with code 130 (attempt 1/3)', 100)"
    )
    conn.execute(
        "INSERT INTO task_comments (task_id, author, body, created_at) VALUES ('t-cmt', 'zf-reviewer', 'Please add unit tests.', 101)"
    )
    conn.commit()
    conn.close()

    workdir = tmp_path / "wt"
    workdir.mkdir()
    captured_cmd = []

    def fake_popen(cmd, **kwargs):
        captured_cmd.extend(cmd)
        proc = MagicMock()
        proc.pid = 54322
        return proc

    with (
        patch.dict(
            "os.environ",
            {"ZEROFACTORY_DB": str(db_file), "ZEROFACTORY_SKIP_WORKER_SPAWN": ""},
            clear=False,
        ),
        patch("dispatcher.check_unresolved_conflicts_safe", return_value=(True, [], "")),
        patch("dispatcher.worker_spawner.shutil.which", return_value="/usr/bin/hermes"),
        patch("dispatcher.worker_spawner.subprocess.Popen", side_effect=fake_popen),
        patch("dispatcher.worker_spawner.cleanup_process_artifacts"),
        patch("dispatcher.worker_spawner._inject_langfuse_env"),
        patch("paths.get_hermes_home", return_value=tmp_path),
    ):
        spawn_agent_worker(
            task_id="t-cmt",
            title="Comment test",
            description="Test desc",
            priority="medium",
            assignee="zf-builder",
            workspace_path=str(workdir),
            branch_name="task/t-cmt",
        )
    _active_workers.pop("t-cmt", None)
    prompt = captured_cmd[-1]
    assert "Please add unit tests." in prompt
    assert "exited with code 130" not in prompt


def test_scheduler_called_process_error_includes_stdout_and_stderr(tmp_path):
    """PR packaging CalledProcessError must preserve stdout (e.g. pre-push hook output) alongside stderr."""
    from dispatcher.scheduler import _package_and_open_pr

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        "CREATE TABLE tasks (id TEXT PRIMARY KEY, board_slug TEXT, title TEXT, description TEXT, priority TEXT, status TEXT, assignee TEXT, target_branch TEXT, repo_alias TEXT, workspace_path TEXT, branch_name TEXT, pr_url TEXT, tags TEXT, metadata TEXT, created_at INTEGER, updated_at INTEGER, worker_pid INTEGER, started_at INTEGER, blocked_reason TEXT)"
    )
    conn.execute(
        "CREATE TABLE task_activity (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, actor TEXT, action TEXT, details TEXT, created_at INTEGER)"
    )
    conn.execute(
        "CREATE TABLE task_comments (id INTEGER PRIMARY KEY AUTOINCREMENT, task_id TEXT, author TEXT, body TEXT, created_at INTEGER)"
    )
    ws = tmp_path / "ws"
    ws.mkdir()
    repo = tmp_path / "repo"
    repo.mkdir()
    conn.execute(
        """
        INSERT INTO tasks (id, board_slug, title, status, assignee, workspace_path, branch_name, metadata, created_at, updated_at)
        VALUES ('t-push', 'b1', 'Push test', 'running', 'zf-builder', ?, 'task/t-push', '{"awaiting_pr": true}', 100, 100)
        """,
        (str(ws),),
    )
    row = conn.execute("SELECT * FROM tasks WHERE id = 't-push'").fetchone()

    captured_err = {}

    def fake_pkg_fail(cursor, c, tid, err_msg, now, meta):
        captured_err["msg"] = err_msg

    def fake_run(cmd, **kwargs):
        if cmd[:2] == ["git", "push"]:
            res = MagicMock()
            res.returncode = 1
            res.stdout = "Pipeline triggered. Re-run the push after the task is completed."
            res.stderr = "error: failed to push some refs"
            return res
        res = MagicMock()
        res.returncode = 0
        res.stdout = ""
        res.stderr = ""
        return res

    with (
        patch(
            "dispatcher.scheduler._handle_packaging_failure", side_effect=fake_pkg_fail
        ),
        patch("dispatcher.run_deterministic_precommit", return_value=(True, "", 0)),
        patch("dispatcher.run_deterministic_slop_gate", return_value=(True, "", 0)),
        patch("dispatcher.check_unresolved_conflicts_safe", return_value=(True, [], "")),
        patch("dispatcher.scheduler.subprocess.run", side_effect=fake_run),
    ):
        ok = _package_and_open_pr(
            conn, conn.cursor(), row, {}, str(ws), repo, "b1", None, tmp_path / "zf.db", 200
        )

    assert ok is False
    assert (
        "Pipeline triggered. Re-run the push after the task is completed."
        in captured_err["msg"]
    )
    assert "error: failed to push some refs" in captured_err["msg"]
