"""Unit tests for dashboard/precommit_service.py."""

import subprocess
from pathlib import Path

import cron.definitions as defs

from dashboard.plugin_api import BoardCreate, create_board
from dashboard.precommit_service import (
    PRECOMMIT_RELATIVE_PATH,
    build_precommit_setup_task_prompt,
    check_board_precommit_status,
    create_precommit_setup_task,
)


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
    assert "pytest" in prompt
    # The unittest fallback caused false precommit failures on pytest suites —
    # it must only ever appear as an explicit prohibition, never as a suggestion.
    assert "unittest discover -s" not in prompt
    assert "NEVER fall back" in prompt
    assert "Self-bootstrapping is mandatory" in prompt
    assert "uv pip install" in prompt
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
    b_res = create_board(
        BoardCreate(
            git_url=str(repo_dir),
            description="Local dummy repo",
            auto_setup_precommit=False,
        )
    )
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


def test_precommit_status_check_does_not_auto_clone(initialized_db: Path, monkeypatch):
    """Read-only precommit status check must never spawn a git clone subprocess."""
    import shutil

    calls: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(
            args=cmd, returncode=1, stdout=b"", stderr=b""
        )

    # Clean up any stale directory a previous (unfixed) run may have created,
    # so the end-of-test home-dir assertion stays hermetic.
    stale = Path.home() / "git" / "no-clone-org"
    if stale.exists():
        shutil.rmtree(stale, ignore_errors=True)

    # Create the board while conftest's ZEROFACTORY_SKIP_GIT is still set so
    # board creation itself does not enter the auto-clone branch.
    b_res = create_board(
        BoardCreate(
            git_url="https://github.com/no-clone-org/no-clone-repo-pc.git",
            description="Remote board without a local clone",
            auto_setup_precommit=False,
        )
    )
    slug = b_res["slug"]

    # Exercise the read-only status check with auto-clone fully enabled.
    monkeypatch.delenv("ZEROFACTORY_SKIP_GIT", raising=False)
    monkeypatch.delenv("ZEROFACTORY_AUTO_CLONE", raising=False)
    monkeypatch.setattr(defs.subprocess, "run", fake_run)

    res = check_board_precommit_status(slug)

    assert res["ok"] is True
    assert res["has_precommit"] is False
    clones = [c for c in calls if len(c) >= 2 and c[1] == "clone"]
    assert not clones, f"status check triggered git clone: {clones}"
    assert not (Path.home() / "git" / "no-clone-org").exists()
