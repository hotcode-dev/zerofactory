"""Unit tests for dashboard/gh_issues_service.py and its routes."""

import json
from pathlib import Path

from dashboard.gh_issues_service import (
    GH_ISSUES_RELATIVE_DIR,
    BUG_REPORT_RELPATH,
    FEATURE_REQUEST_RELPATH,
    build_gh_issues_setup_task_prompt,
    check_board_gh_issues_status,
    create_gh_issues_setup_task,
    setup_board_gh_issues_deterministic,
)
from dashboard.plugin_api import BoardCreate, create_board
from dashboard.routes.boards import (
    get_board_gh_issues_status_endpoint,
    setup_board_gh_issues_endpoint,
)


def test_build_gh_issues_setup_task_prompt():
    prompt = build_gh_issues_setup_task_prompt("test-board")
    assert GH_ISSUES_RELATIVE_DIR in prompt
    assert BUG_REPORT_RELPATH in prompt
    assert FEATURE_REQUEST_RELPATH in prompt
    assert "zerofactory" in prompt
    assert "test-board" in prompt
    assert "scripts/setup_gh_issues.py" in prompt


def test_gh_issues_status_missing_board(initialized_db: Path):
    res = check_board_gh_issues_status("nonexistent-board")
    assert res["ok"] is False
    assert res["has_gh_issues"] is False


def test_gh_issues_status_and_task_lifecycle(initialized_db: Path, tmp_path: Path):
    repo_dir = tmp_path / "dummy_gh_repo"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()

    board_res = create_board(BoardCreate(git_url=str(repo_dir)))
    slug = board_res["slug"]

    # 1. Initial status: templates missing
    status = check_board_gh_issues_status(slug)
    assert status["ok"] is True
    assert status["has_gh_issues"] is False
    assert status["pending_task_id"] is None

    # 2. Create setup task in async mode
    setup_res = create_gh_issues_setup_task(slug, deterministic=False)
    assert setup_res["ok"] is True
    assert setup_res["already_exists"] is False
    task_id = setup_res["task_id"]

    # 3. Status now shows pending task
    status2 = check_board_gh_issues_status(slug)
    assert status2["pending_task_id"] == task_id

    # 4. Creating again in async mode should deduplicate
    setup_res2 = create_gh_issues_setup_task(slug, deterministic=False)
    assert setup_res2["ok"] is True
    assert setup_res2["already_exists"] is True
    assert setup_res2["task_id"] == task_id

    # 5. Endpoint test: status endpoint
    ep_status = get_board_gh_issues_status_endpoint(slug)
    assert ep_status["ok"] is True
    assert ep_status["pending_task_id"] == task_id

    # 6. Endpoint test: deterministic setup endpoint
    ep_setup = setup_board_gh_issues_endpoint(slug)
    assert ep_setup["ok"] is True
    assert ep_setup["deterministic"] is True
    assert (repo_dir / ".github" / "ISSUE_TEMPLATE" / "bug_report.yml").exists()
    assert (repo_dir / ".github" / "ISSUE_TEMPLATE" / "feature_request.yml").exists()
    assert (repo_dir / ".github" / "ISSUE_TEMPLATE" / "config.yml").exists()

    # 7. Status now reflects templates are configured
    status_final = check_board_gh_issues_status(slug)
    assert status_final["ok"] is True
    assert status_final["has_gh_issues"] is True


def test_setup_board_gh_issues_deterministic(initialized_db: Path, tmp_path: Path):
    repo_dir = tmp_path / "dummy_gh_direct"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()

    board_res = create_board(BoardCreate(git_url=str(repo_dir)))
    slug = board_res["slug"]

    res = setup_board_gh_issues_deterministic(slug)
    assert res["ok"] is True
    assert res["deterministic"] is True
    assert len(res["templates"]) == 3

    config_path = repo_dir / ".github" / "ISSUE_TEMPLATE" / "config.yml"
    assert config_path.exists()
    content = config_path.read_text(encoding="utf-8")
    assert "blank_issues_enabled: false" in content
    assert "GitHub Discussions" in content
