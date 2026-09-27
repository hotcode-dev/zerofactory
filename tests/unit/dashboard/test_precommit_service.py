"""Unit tests for dashboard/precommit_service.py."""

from pathlib import Path
import pytest

from dashboard.precommit_service import (
    PRECOMMIT_RELATIVE_PATH,
    SETUP_TASK_DEDUP_KEY,
    SETUP_TASK_TITLE,
    build_precommit_setup_task_prompt,
    check_board_precommit_status,
    create_precommit_setup_task,
)
from dashboard.plugin_api import create_board, BoardCreate, get_db_conn


def test_build_precommit_setup_task_prompt():
    prompt = build_precommit_setup_task_prompt("test-board")
    assert PRECOMMIT_RELATIVE_PATH in prompt
    assert "run_format" in prompt
    assert "run_build" in prompt
    assert "run_test" in prompt
    assert "chmod +x" in prompt
    assert "test-board" in prompt
    assert "install-hook" in prompt
    assert ".git/hooks" in prompt
    assert "ruff" in prompt
    assert "prettier" in prompt
    assert "gofmt" in prompt
    assert "unittest" in prompt
    assert "compileall" in prompt
    assert "Vitest" in prompt


def test_precommit_status_missing_board(initialized_db: Path):
    res = check_board_precommit_status("nonexistent-board")
    assert res["ok"] is False
    assert res["has_precommit"] is False


def test_precommit_status_and_task_lifecycle(initialized_db: Path, tmp_path: Path):
    # Create a dummy repo with git
    repo_dir = tmp_path / "dummy_repo"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()

    # Create board pointing to this local directory
    b_res = create_board(BoardCreate(
        git_url=str(repo_dir),
        description="Local dummy repo",
        auto_setup_precommit=False
    ))
    slug = b_res["slug"]

    # Initial check: no precommit script
    status = check_board_precommit_status(slug)
    assert status["ok"] is True
    assert status["has_precommit"] is False
    assert status["pending_task_id"] is None

    # Trigger precommit setup task
    setup_res = create_precommit_setup_task(slug)
    assert setup_res["ok"] is True
    assert setup_res["already_exists"] is False
    task_id = setup_res["task_id"]
    assert task_id is not None

    # Check status again: pending task should now be detected
    status2 = check_board_precommit_status(slug)
    assert status2["has_precommit"] is False
    assert status2["pending_task_id"] == task_id
    assert status2["pending_task_status"] == "todo"

    # Calling create_precommit_setup_task again should deduplicate
    setup_res2 = create_precommit_setup_task(slug)
    assert setup_res2["ok"] is True
    assert setup_res2["already_exists"] is True
    assert setup_res2["task_id"] == task_id

    # Create .zerofactory/precommit.sh in the repo
    zf_dir = repo_dir / ".zerofactory"
    zf_dir.mkdir(parents=True, exist_ok=True)
    script_file = zf_dir / "precommit.sh"
    script_file.write_text("#!/usr/bin/env bash\necho 'clean'\n", encoding="utf-8")

    # Status check should now detect has_precommit = True
    status3 = check_board_precommit_status(slug)
    assert status3["has_precommit"] is True
    assert status3["precommit_path"] == str(script_file)
    assert "clean" in status3["script_preview"]
