"""Unit tests for the Sequential Elephant-Goldfish Model (EGM) triage pipeline."""

import json
import os
import sqlite3
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

import dispatcher
from dashboard.db import init_db
from dashboard.models import (
    TaskApproveRequest,
    TaskRejectRequest,
)
from dashboard.routes.tasks import approve_task, reject_task
from dispatcher.config import _active_workers
from dispatcher.reaper import reap_active_workers
from dispatcher.scheduler import run_dispatch_cycle
from dispatcher.worker_spawner import spawn_agent_worker


@pytest.fixture
def test_db(tmp_path: Path, monkeypatch):
    db_file = tmp_path / "zerofactory.db"
    lock_file = tmp_path / "dispatcher.lock"
    monkeypatch.setenv("ZEROFACTORY_DB", str(db_file))
    monkeypatch.setenv("ZEROFACTORY_LOCK_PATH", str(lock_file))
    monkeypatch.setenv("ZEROFACTORY_SKIP_GIT", "1")
    monkeypatch.setenv("ZEROFACTORY_SKIP_WORKER_SPAWN", "1")
    init_db(force=True)
    return db_file


def test_claim_elephant_drafting(test_db: Path):
    """Dispatcher claims triage task for zf-orchestrator into status='running' with elephant_drafting phase."""
    now = int(time.time())
    with sqlite3.connect(str(test_db)) as conn:
        conn.execute(
            """
            INSERT INTO tasks (id, title, status, assignee, priority, metadata, created_at, updated_at)
            VALUES ('task-egm-1', 'Epic Triage', 'triage', 'zf-orchestrator', 'P1', ?, ?, ?)
            """,
            (json.dumps({"egm": True, "category": "epic"}), now, now),
        )
        conn.commit()

    with patch.object(dispatcher, "spawn_agent_worker", return_value=(999, "sess-1")):
        res = run_dispatch_cycle(db_path=test_db)
        assert res.get("ok")

    with sqlite3.connect(str(test_db)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM tasks WHERE id = 'task-egm-1'").fetchone()
        assert row["status"] == "running"
        assert row["assignee"] == "zf-orchestrator"
        meta = json.loads(row["metadata"])
        assert meta["triage_phase"] == "elephant_drafting"
        assert meta["egm"] is True


def test_triage_worker_concurrency_cap(test_db: Path):
    """At most 1 triage worker (zf-orchestrator or zf-goldfish) can run concurrently."""
    now = int(time.time())
    with sqlite3.connect(str(test_db)) as conn:
        # 1 running orchestrator
        conn.execute(
            """
            INSERT INTO tasks (id, title, status, assignee, priority, metadata, created_at, updated_at)
            VALUES ('running-orch', 'Active Drafting', 'running', 'zf-orchestrator', 'P0', ?, ?, ?)
            """,
            (json.dumps({"triage_phase": "elephant_drafting", "worker_pid": 111}), now, now),
        )
        # 1 queued triage task
        conn.execute(
            """
            INSERT INTO tasks (id, title, status, assignee, priority, metadata, created_at, updated_at)
            VALUES ('queued-orch', 'Queued Triage', 'triage', 'zf-orchestrator', 'P1', ?, ?, ?)
            """,
            (json.dumps({"egm": True}), now, now),
        )
        conn.commit()

    with patch.object(dispatcher, "spawn_agent_worker") as mock_spawn:
        res = run_dispatch_cycle(db_path=test_db)
        mock_spawn.assert_not_called()

    with sqlite3.connect(str(test_db)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT status FROM tasks WHERE id = 'queued-orch'").fetchone()
        assert row["status"] == "triage"


def test_reaper_elephant_exit_transitions_to_goldfish(test_db: Path):
    """When elephant exits 0 with spec recorded, reaper transitions task to todo for zf-goldfish."""
    now = int(time.time())
    with sqlite3.connect(str(test_db)) as conn:
        conn.execute(
            """
            INSERT INTO tasks (id, title, status, assignee, priority, metadata, created_at, updated_at)
            VALUES ('task-egm-2', 'Elephant Finished', 'running', 'zf-orchestrator', 'P1', ?, ?, ?)
            """,
            (
                json.dumps({
                    "triage_phase": "elephant_drafting",
                    "egm": True,
                    "specification": "### System Architecture\nDefined components and contracts.",
                    "worker_pid": 8888,
                    "sessions": [{"status": "ongoing", "started_at": now}],
                }),
                now,
                now,
            ),
        )
        conn.commit()

    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0
    mock_proc.pid = 8888
    _active_workers["task-egm-2"] = mock_proc

    try:
        with sqlite3.connect(str(test_db)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            reaped = reap_active_workers(cursor, now)
            conn.commit()
    finally:
        _active_workers.pop("task-egm-2", None)

    with sqlite3.connect(str(test_db)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM tasks WHERE id = 'task-egm-2'").fetchone()
        assert row["status"] == "todo"
        assert row["assignee"] == "zf-goldfish"
        meta = json.loads(row["metadata"])
        assert meta["triage_phase"] == "goldfish_auditing"


def test_grill_interview_prevents_goldfish_advance(test_db: Path):
    """If orchestrator posted a Grill-with-Docs question, task remains parked in triage for human."""
    now = int(time.time())
    with sqlite3.connect(str(test_db)) as conn:
        conn.execute(
            """
            INSERT INTO tasks (id, title, status, assignee, priority, metadata, created_at, updated_at)
            VALUES ('task-grill-1', 'Grill Active', 'running', 'human', 'P1', ?, ?, ?)
            """,
            (
                json.dumps({
                    "triage_phase": "elephant_drafting",
                    "egm": True,
                    "awaiting_interview": True,
                    "worker_pid": 7777,
                    "sessions": [{"status": "ongoing", "started_at": now}],
                }),
                now,
                now,
            ),
        )
        conn.commit()

    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0
    mock_proc.pid = 7777
    _active_workers["task-grill-1"] = mock_proc

    try:
        with sqlite3.connect(str(test_db)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            reap_active_workers(cursor, now)
            conn.commit()
    finally:
        _active_workers.pop("task-grill-1", None)

    with sqlite3.connect(str(test_db)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM tasks WHERE id = 'task-grill-1'").fetchone()
        assert row["status"] == "triage"
        assert row["assignee"] == "human"
        meta = json.loads(row["metadata"])
        assert meta.get("awaiting_interview") is True
        assert meta.get("triage_phase") != "goldfish_auditing"


def test_claim_goldfish_auditing(test_db: Path):
    """Dispatcher claims goldfish task from todo into status='running'."""
    now = int(time.time())
    with sqlite3.connect(str(test_db)) as conn:
        conn.execute(
            """
            INSERT INTO tasks (id, title, status, assignee, priority, metadata, created_at, updated_at)
            VALUES ('task-gold-1', 'Goldfish Audit Task', 'todo', 'zf-goldfish', 'P1', ?, ?, ?)
            """,
            (
                json.dumps({
                    "triage_phase": "goldfish_auditing",
                    "specification": "### Spec\nTest spec",
                }),
                now,
                now,
            ),
        )
        conn.commit()

    with patch.object(dispatcher, "spawn_agent_worker", return_value=(5555, "goldfish-sess-1")):
        res = run_dispatch_cycle(db_path=test_db)
        assert res.get("ok")

    with sqlite3.connect(str(test_db)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM tasks WHERE id = 'task-gold-1'").fetchone()
        assert row["status"] == "running"
        assert row["assignee"] == "zf-goldfish"
        meta = json.loads(row["metadata"])
        assert meta["triage_phase"] == "goldfish_auditing"


def test_reaper_goldfish_exit_transitions_to_human_approval(test_db: Path):
    """When goldfish worker exits 0, reaper parks task in triage with human_approval phase."""
    now = int(time.time())
    with sqlite3.connect(str(test_db)) as conn:
        conn.execute(
            """
            INSERT INTO tasks (id, title, status, assignee, priority, metadata, created_at, updated_at)
            VALUES ('task-gold-2', 'Goldfish Audit Running', 'running', 'zf-goldfish', 'P1', ?, ?, ?)
            """,
            (
                json.dumps({
                    "triage_phase": "goldfish_auditing",
                    "specification": "Spec content",
                    "worker_pid": 4444,
                    "sessions": [{"status": "ongoing", "started_at": now}],
                }),
                now,
                now,
            ),
        )
        conn.commit()

    mock_proc = MagicMock()
    mock_proc.poll.return_value = 0
    mock_proc.pid = 4444
    _active_workers["task-gold-2"] = mock_proc

    try:
        with sqlite3.connect(str(test_db)) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            reap_active_workers(cursor, now)
            conn.commit()
    finally:
        _active_workers.pop("task-gold-2", None)

    with sqlite3.connect(str(test_db)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM tasks WHERE id = 'task-gold-2'").fetchone()
        assert row["status"] == "triage"
        assert row["assignee"] == "human"
        meta = json.loads(row["metadata"])
        assert meta["triage_phase"] == "human_approval"
        assert meta["awaiting_approval"] is True


def test_approve_single_repo(test_db: Path):
    """Approving single-repo triage task moves it to todo for zf-builder."""
    now = int(time.time())
    with sqlite3.connect(str(test_db)) as conn:
        conn.execute(
            """
            INSERT INTO tasks (id, title, status, assignee, priority, metadata, created_at, updated_at)
            VALUES ('task-appr-1', 'Single Repo Spec', 'triage', 'human', 'P1', ?, ?, ?)
            """,
            (
                json.dumps({
                    "triage_phase": "human_approval",
                    "awaiting_approval": True,
                    "specification": "Single repo implementation spec",
                }),
                now,
                now,
            ),
        )
        conn.commit()

    res = approve_task("task-appr-1", TaskApproveRequest(actor="reviewer"))
    assert res["status"] == "todo"
    assert res["assignee"] == "zf-builder"

    with sqlite3.connect(str(test_db)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM tasks WHERE id = 'task-appr-1'").fetchone()
        meta = json.loads(row["metadata"])
        assert meta["triage_phase"] == "approved"
        assert meta.get("awaiting_approval") is None
        assert meta["approved_by"] == "reviewer"


def test_approve_multi_repo_splits(test_db: Path):
    """Approving multi-repo triage task decomposes into per-repo child tasks with spec inherited."""
    now = int(time.time())
    with sqlite3.connect(str(test_db)) as conn:
        conn.execute(
            "INSERT INTO boards (slug, description, created_at, updated_at) VALUES ('test-board', 'Test Board', ?, ?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO board_repositories (board_slug, repo_alias, git_url, created_at, updated_at) VALUES ('test-board', 'backend', 'https://github.com/org/backend.git', ?, ?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO board_repositories (board_slug, repo_alias, git_url, created_at, updated_at) VALUES ('test-board', 'frontend', 'https://github.com/org/frontend.git', ?, ?)",
            (now, now),
        )
        conn.execute(
            """
            INSERT INTO tasks (id, title, description, status, assignee, priority, board_slug, metadata, created_at, updated_at)
            VALUES ('task-split-1', '[Triage] Multi-Repo Epic', 'Parent goal', 'triage', 'human', 'P1', 'test-board', ?, ?, ?)
            """,
            (
                json.dumps({
                    "triage_phase": "human_approval",
                    "awaiting_approval": True,
                    "target_repos": ["backend", "frontend"],
                    "specification": "Shared interface contracts and boundaries",
                }),
                now,
                now,
            ),
        )
        conn.commit()

    res = approve_task("task-split-1", TaskApproveRequest(actor="tech-lead"))
    assert "created_tasks" in res
    assert len(res["created_tasks"]) == 2

    # Original parent task should be done
    with sqlite3.connect(str(test_db)) as conn:
        conn.row_factory = sqlite3.Row
        parent = conn.execute("SELECT * FROM tasks WHERE id = 'task-split-1'").fetchone()
        assert parent["status"] == "done"

        # Check child task inherited specification
        children = conn.execute("SELECT * FROM tasks WHERE id != 'task-split-1'").fetchall()
        for child in children:
            assert child["status"] == "todo"
            assert child["assignee"] == "zf-builder"
            assert "Shared interface contracts and boundaries" in child["description"]


def test_reject_first_round_returns_to_elephant(test_db: Path):
    """Rejecting spec increments revision_count and routes back to zf-orchestrator in triage."""
    now = int(time.time())
    with sqlite3.connect(str(test_db)) as conn:
        conn.execute(
            """
            INSERT INTO tasks (id, title, status, assignee, priority, metadata, created_at, updated_at)
            VALUES ('task-rej-1', 'Spec to Revise', 'triage', 'human', 'P1', ?, ?, ?)
            """,
            (
                json.dumps({
                    "triage_phase": "human_approval",
                    "awaiting_approval": True,
                    "specification": "Initial spec draft",
                }),
                now,
                now,
            ),
        )
        conn.commit()

    res = reject_task("task-rej-1", TaskRejectRequest(feedback="Please remove unnecessary abstractions", actor="reviewer"))
    assert res["status"] == "triage"
    assert res["assignee"] == "zf-orchestrator"

    with sqlite3.connect(str(test_db)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM tasks WHERE id = 'task-rej-1'").fetchone()
        meta = json.loads(row["metadata"])
        assert meta["revision_count"] == 1
        assert meta["triage_phase"] == "elephant_drafting"
        assert meta.get("awaiting_approval") is None

        # Verify comment was posted
        comments = conn.execute("SELECT * FROM task_comments WHERE task_id = 'task-rej-1'").fetchall()
        assert len(comments) == 1
        assert "Please remove unnecessary abstractions" in comments[0]["body"]


def test_reject_second_round_blocks_task(test_db: Path):
    """When revision_count reaches 2, task is permanently blocked for human intervention."""
    now = int(time.time())
    with sqlite3.connect(str(test_db)) as conn:
        conn.execute(
            """
            INSERT INTO tasks (id, title, status, assignee, priority, metadata, created_at, updated_at)
            VALUES ('task-rej-2', 'Spec Second Rejection', 'triage', 'human', 'P1', ?, ?, ?)
            """,
            (
                json.dumps({
                    "triage_phase": "human_approval",
                    "awaiting_approval": True,
                    "revision_count": 1,
                    "specification": "Second spec draft",
                }),
                now,
                now,
            ),
        )
        conn.commit()

    res = reject_task("task-rej-2", TaskRejectRequest(feedback="Still too complex", actor="reviewer"))
    assert res["status"] == "blocked"
    assert res["assignee"] == "human"

    with sqlite3.connect(str(test_db)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute("SELECT * FROM tasks WHERE id = 'task-rej-2'").fetchone()
        meta = json.loads(row["metadata"])
        assert meta["revision_count"] == 2
        assert meta.get("permanently_blocked") is True
        assert "Maximum spec revision rounds reached" in meta.get("blocked_reason", "")


def test_goldfish_prompt_generation(tmp_path: Path):
    """spawn_agent_worker generates contrarian spec audit prompt for zf-goldfish."""
    meta = json.dumps({
        "specification": "### Microservice Interface\nExpose gRPC endpoint.",
        "revision_count": 1,
    })
    with (
        patch("subprocess.Popen") as mock_popen,
        patch.dict(os.environ, {}, clear=False),
    ):
        os.environ.pop("ZEROFACTORY_SKIP_WORKER_SPAWN", None)
        mock_proc = MagicMock()
        mock_proc.pid = 9999
        mock_proc.poll.return_value = None
        mock_popen.return_value = mock_proc

        pid, sess = spawn_agent_worker(
            task_id="task-gold-p",
            title="gRPC Gateway",
            description="Build gateway",
            priority="P1",
            assignee="zf-goldfish",
            workspace_path=str(tmp_path),
            branch_name="main",
            board_slug="test-board",
            metadata=meta,
        )
        assert mock_popen.called
        cmd = mock_popen.call_args[0][0]
        prompt = cmd[-1]
        assert "Spec Auditor (zf-goldfish)" in prompt
        assert "Expose gRPC endpoint" in prompt
        assert "Ponytail 7-Rung Ladder of Laziness" in prompt
        assert "SPEC AUDIT: APPROVED" in prompt
        assert "SPEC AUDIT: REVISION REQUESTED" in prompt
