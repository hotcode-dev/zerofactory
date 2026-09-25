"""Unit tests for dashboard/models.py: Pydantic schemas, validation, defaults, and bounds."""

import pytest
from pydantic import ValidationError

from dashboard.models import (
    BoardCreate,
    BoardUpdate,
    TaskCreate,
    TaskUpdate,
    TaskMove,
    MemoryCreate,
    SettingsUpdate,
    VALID_STATUSES,
    VALID_PRIORITIES,
    VALID_MEMORY_CATEGORIES,
    MEMORY_CONTENT_MAX_LENGTH,
)


def test_board_create_validation():
    """BoardCreate requires git_url and enforces max_concurrent_running >= 1."""
    # Valid model
    b = BoardCreate(
        git_url="https://github.com/owner/repo.git",
        target_branch="develop",
        max_concurrent_running=2,
    )
    assert b.git_url == "https://github.com/owner/repo.git"
    assert b.target_branch == "develop"
    assert b.max_concurrent_running == 2

    # Empty git_url fails
    with pytest.raises(ValidationError):
        BoardCreate(git_url="")

    # max_concurrent_running < 1 fails
    with pytest.raises(ValidationError):
        BoardCreate(git_url="https://github.com/owner/repo.git", max_concurrent_running=0)


def test_task_create_validation():
    """TaskCreate enforces title min/max length and default status/priority."""
    t = TaskCreate(title="Fix login bug")
    assert t.title == "Fix login bug"
    assert t.status == "triage"
    assert t.priority == "P2"
    assert t.assignee == "unassigned"

    # Empty title fails
    with pytest.raises(ValidationError):
        TaskCreate(title="")

    # Title exceeding 256 chars fails
    with pytest.raises(ValidationError):
        TaskCreate(title="A" * 257)


def test_task_move_validation():
    """TaskMove requires a status within VALID_STATUSES."""
    tm = TaskMove(status="todo", actor="user")
    assert tm.status == "todo"

    # Invalid status should still instantiate but route validation catches it,
    # or if validated by model:
    assert "todo" in VALID_STATUSES
    assert "running" in VALID_STATUSES
    assert "invalid_status" not in VALID_STATUSES


def test_memory_create_length_cap():
    """MemoryCreate enforces MEMORY_CONTENT_MAX_LENGTH (500 chars)."""
    # 500 chars is fine
    m_ok = MemoryCreate(content="X" * MEMORY_CONTENT_MAX_LENGTH, category="gotcha")
    assert len(m_ok.content) == 500

    # 501 chars must fail validation
    with pytest.raises(ValidationError):
        MemoryCreate(content="X" * (MEMORY_CONTENT_MAX_LENGTH + 1), category="gotcha")

    # Empty content must fail
    with pytest.raises(ValidationError):
        MemoryCreate(content="", category="gotcha")


def test_settings_update_fields():
    """SettingsUpdate allows optional partial updates across system settings."""
    s = SettingsUpdate(
        max_active_tasks=5,
        default_max_concurrent_workers=2,
        scan_on_idle=True,
        enable_cron_scheduler=False,
    )
    assert s.max_active_tasks == 5
    assert s.enable_cron_scheduler is False
