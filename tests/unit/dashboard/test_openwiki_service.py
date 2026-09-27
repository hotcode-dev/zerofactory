"""Unit tests for dashboard/openwiki_service.py."""

from pathlib import Path

from dashboard.openwiki_service import (
    OPENWIKI_RELATIVE_DIR,
    build_openwiki_setup_task_prompt,
    check_board_openwiki_status,
    create_openwiki_setup_task,
)
from dashboard.plugin_api import BoardCreate, create_board


def test_build_openwiki_setup_task_prompt():
    prompt = build_openwiki_setup_task_prompt("test-board")
    assert OPENWIKI_RELATIVE_DIR in prompt
    assert "openwiki" in prompt
    assert "AGENTS.md" in prompt
    assert "index.md" in prompt
    assert "test-board" in prompt
    assert "npm install -g openwiki" in prompt


def test_openwiki_status_missing_board(initialized_db: Path):
    res = check_board_openwiki_status("nonexistent-board")
    assert res["ok"] is False
    assert res["has_openwiki"] is False


def test_openwiki_status_and_task_lifecycle(initialized_db: Path, tmp_path: Path):
    # Create a dummy repo with git
    repo_dir = tmp_path / "dummy_repo"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()

    # Create board pointing to this local directory
    b_res = create_board(
        BoardCreate(
            git_url=str(repo_dir),
            description="Local dummy repo",
            auto_setup_precommit=False,
        )
    )
    slug = b_res["slug"]

    # Initial check: no openwiki directory
    status = check_board_openwiki_status(slug)
    assert status["ok"] is True
    assert status["has_openwiki"] is False
    assert status["pending_task_id"] is None

    # Trigger openwiki setup task
    setup_res = create_openwiki_setup_task(slug)
    assert setup_res["ok"] is True
    assert setup_res["already_exists"] is False
    task_id = setup_res["task_id"]
    assert task_id is not None

    # Check status again: pending task should now be detected
    status2 = check_board_openwiki_status(slug)
    assert status2["has_openwiki"] is False
    assert status2["pending_task_id"] == task_id
    assert status2["pending_task_status"] == "todo"

    # Calling create_openwiki_setup_task again should deduplicate
    setup_res2 = create_openwiki_setup_task(slug)
    assert setup_res2["ok"] is True
    assert setup_res2["already_exists"] is True
    assert setup_res2["task_id"] == task_id

    # Create openwiki/ directory and index.md in the repo
    ow_dir = repo_dir / "openwiki"
    ow_dir.mkdir(parents=True, exist_ok=True)
    index_file = ow_dir / "index.md"
    index_file.write_text(
        "# Repository Architecture Overview\nSystem map.\n", encoding="utf-8"
    )

    # Status check should now detect has_openwiki = True
    status3 = check_board_openwiki_status(slug)
    assert status3["has_openwiki"] is True
    assert status3["openwiki_path"] == str(ow_dir)
    assert "Repository Architecture Overview" in status3["wiki_index_preview"]


def test_openwiki_blocked_task_allows_regenerate(initialized_db: Path, tmp_path: Path):
    """A setup task blocked awaiting human merge must NOT block regeneration."""
    from dashboard.db import get_db_conn

    repo_dir = tmp_path / "ow_blocked_repo"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()

    b_res = create_board(
        BoardCreate(
            git_url=str(repo_dir),
            description="Local blocked repo",
            auto_setup_precommit=False,
        )
    )
    slug = b_res["slug"]

    # First setup run
    setup_res = create_openwiki_setup_task(slug)
    assert setup_res["ok"] is True
    assert setup_res["already_exists"] is False
    task_id = setup_res["task_id"]

    # Simulate the human merge gate: the setup task sits in `blocked`
    # awaiting review/merge (dispatcher PR workflow)
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT updated_at FROM tasks WHERE id = ?", (task_id,))
        row = cursor.fetchone()
        cursor.execute(
            "UPDATE tasks SET status = 'blocked', updated_at = ? WHERE id = ?",
            (row["updated_at"], task_id),
        )
        conn.commit()

    # A blocked task is not active work: no pending task, surfaced as blocked
    status = check_board_openwiki_status(slug)
    assert status["ok"] is True
    assert status["pending_task_id"] is None
    assert status["pending_task_status"] is None
    assert status["blocked_task_id"] == task_id
    assert status["blocked_task_status"] == "blocked"

    # Regenerate must create a FRESH task instead of returning the stale one
    regen_res = create_openwiki_setup_task(slug)
    assert regen_res["ok"] is True
    assert regen_res["already_exists"] is False
    assert regen_res["task_id"] is not None
    assert regen_res["task_id"] != task_id

    # The fresh task is reported as active pending work again
    status2 = check_board_openwiki_status(slug)
    assert status2["pending_task_id"] == regen_res["task_id"]
    assert status2["pending_task_status"] == "todo"
