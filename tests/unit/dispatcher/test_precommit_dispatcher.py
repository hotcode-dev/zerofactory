"""Unit tests for deterministic precommit runner and failure handling in dispatcher."""

import json
import time
from pathlib import Path

from dashboard.plugin_api import get_db_conn
from dispatcher.worktree import (
    _handle_precommit_failure,
    run_deterministic_precommit,
)


def test_run_precommit_missing_script(tmp_path: Path):
    """When .zerofactory/precommit.sh does not exist, precommit passes silently."""
    passed, msg, code = run_deterministic_precommit(tmp_path)
    assert passed is True
    assert code == 0
    assert "No .zerofactory/precommit.sh found" in msg


def test_run_precommit_skip_env(tmp_path: Path, monkeypatch):
    """When ZEROFACTORY_SKIP_PRECOMMIT=1, precommit skips execution."""
    monkeypatch.setenv("ZEROFACTORY_SKIP_PRECOMMIT", "1")
    zf_dir = tmp_path / ".zerofactory"
    zf_dir.mkdir()
    (zf_dir / "precommit.sh").write_text("#!/usr/bin/env bash\nexit 1\n")
    passed, msg, code = run_deterministic_precommit(tmp_path)
    assert passed is True
    assert code == 0


def test_run_precommit_success_and_format(tmp_path: Path):
    """Verify clean execution and that formatting modifications in workspace are kept."""
    zf_dir = tmp_path / ".zerofactory"
    zf_dir.mkdir()
    script = zf_dir / "precommit.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "set -e\n"
        "echo 'formatted code' > formatted.txt\n"
        "echo 'All checks passed'\n"
    )

    passed, out, code = run_deterministic_precommit(tmp_path)
    assert passed is True
    assert code == 0
    assert "All checks passed" in out
    assert (tmp_path / "formatted.txt").read_text().strip() == "formatted code"


def test_run_precommit_failure(tmp_path: Path):
    """Verify failing precommit captures error output and non-zero exit code."""
    zf_dir = tmp_path / ".zerofactory"
    zf_dir.mkdir()
    script = zf_dir / "precommit.sh"
    script.write_text(
        "#!/usr/bin/env bash\n"
        "echo 'Running tests...'\n"
        "echo 'Test failed: assert 1 == 2' >&2\n"
        "exit 1\n"
    )

    passed, out, code = run_deterministic_precommit(tmp_path)
    assert passed is False
    assert code == 1
    assert "Test failed: assert 1 == 2" in out


def test_handle_precommit_failure_retries(initialized_db: Path, tmp_path: Path):
    """Verify retrying up to max_retries routes back to zf-builder, then marks blocked."""
    now = int(time.time())
    task_id = "zf-test-precommit"
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO boards (slug, description, created_at, updated_at) VALUES ('test-board', 'Test Board', ?, ?)",
            (now, now),
        )
        cursor.execute(
            "INSERT INTO tasks (id, board_slug, title, status, assignee, priority, created_at, updated_at) VALUES (?, 'test-board', ?, 'running', 'zf-builder', 'P1', ?, ?)",
            (task_id, "feat: my task", now, now),
        )
        conn.commit()

        # Attempt 1: Should keep task in running and record attempt 1/3
        _handle_precommit_failure(
            cursor,
            task_id,
            "feat: my task",
            str(tmp_path),
            "Syntax error on line 5",
            now,
        )
        conn.commit()

        cursor.execute("SELECT status, metadata FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        # Retry routes back to a claimable 'todo' (builder respawned on claim)
        assert row["status"] == "todo"
        meta = json.loads(row["metadata"])
        assert meta["precommit_retries"] == 1
        assert "Syntax error on line 5" in meta["last_precommit_error"]

        # Attempt 2
        _handle_precommit_failure(
            cursor, task_id, "feat: my task", str(tmp_path), "Syntax error 2", now
        )
        conn.commit()
        cursor.execute("SELECT metadata FROM tasks WHERE id = ?", (task_id,))
        meta = json.loads(cursor.fetchone()["metadata"])
        assert meta["precommit_retries"] == 2

        # Attempt 3
        _handle_precommit_failure(
            cursor, task_id, "feat: my task", str(tmp_path), "Syntax error 3", now
        )
        conn.commit()
        cursor.execute("SELECT metadata FROM tasks WHERE id = ?", (task_id,))
        meta = json.loads(cursor.fetchone()["metadata"])
        assert meta["precommit_retries"] == 3

        # Attempt 4 (exceeding default 3 retries): Should move task to blocked
        _handle_precommit_failure(
            cursor, task_id, "feat: my task", str(tmp_path), "Syntax error 4", now
        )
        conn.commit()
        cursor.execute("SELECT status, metadata FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        assert row["status"] == "blocked"
        meta = json.loads(row["metadata"])
        assert meta["precommit_retries"] == 4

        # Verify comment was logged
        cursor.execute(
            "SELECT body FROM task_comments WHERE task_id = ? ORDER BY id DESC LIMIT 1",
            (task_id,),
        )
        cmt = cursor.fetchone()["body"]
        assert "Deterministic Precommit Failed" in cmt
        assert "Syntax error 4" in cmt
