"""Zero Factory Dashboard — Pydantic Request/Response Models and Enums."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

# Ensure zerofactory plugin root is in sys.path for direct module imports
_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

from pydantic import BaseModel, Field

try:
    from ..paths import (  # type: ignore
        HUMAN,
        PROFILE_MAP,
        UNASSIGNED,
        VALID_ASSIGNEES,
        normalize_assignee,
    )
except (ImportError, ValueError):
    from paths import (  # type: ignore
        HUMAN,
        PROFILE_MAP,
        UNASSIGNED,
        VALID_ASSIGNEES,
        normalize_assignee,
    )

VALID_STATUSES = {"triage", "todo", "running", "blocked", "done"}
VALID_PRIORITIES = {"P0", "P1", "P2", "P3"}
VALID_MEMORY_CATEGORIES = {
    "decision",
    "gotcha",
    "convention",
    "rejected_path",
    "general",
}

# Hard bound for manually written memory content (API + CLI). The auto-record
# path caps at 1000 chars; manual writes get a tighter 500-char cap so a single
# oversized blob can never bloat storage or the pre-injected worker prompt.
MEMORY_CONTENT_MAX_LENGTH = 500

ACTIVITY_ACTORS: list[str] = [
    "zf-orchestrator",
    "zf-builder",
    "zf-reviewer",
    "dispatcher",
    "user",
    "other",
]


class BoardCreate(BaseModel):
    git_url: str = Field(
        ...,
        min_length=1,
        description="Remote Git URL (e.g. https://github.com/owner/repo.git)",
    )
    description: str | None = ""
    target_branch: str | None = Field(
        default="",
        description="Target/base branch to branch off and merge PRs into (e.g. main)",
    )
    max_concurrent_running: int | None = Field(
        default=1,
        ge=1,
        description="Max tasks running in parallel on this board (default 1)",
    )
    auto_record_memory: bool | None = Field(
        default=True,
        description="Enable automatic memory recording from reviewer feedback",
    )
    additional_reviewer_usernames: list[str] | None = Field(
        default_factory=list,
        description="Additional GitHub usernames whose PR feedback is trusted",
    )
    auto_setup_precommit: bool | None = Field(
        default=False,
        description="Automatically trigger setup task for .zerofactory/precommit.sh if missing",
    )


class BoardUpdate(BaseModel):
    description: str | None = None
    git_url: str | None = None
    target_branch: str | None = Field(
        default=None,
        description="Target/base branch to branch off and merge PRs into (e.g. main)",
    )
    max_concurrent_running: int | None = Field(
        default=None, ge=1, description="Max tasks running in parallel on this board"
    )
    auto_record_memory: bool | None = Field(
        default=None,
        description="Enable automatic memory recording from reviewer feedback",
    )
    additional_reviewer_usernames: list[str] | None = Field(
        default=None,
        description="Additional GitHub usernames whose PR feedback is trusted",
    )


class BoardTestClone(BaseModel):
    git_url: str = Field(
        ..., min_length=1, description="Remote Git URL to test cloning"
    )
    slug: str | None = Field(default=None, description="Optional board slug")


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    description: str | None = ""
    board_slug: str | None = None
    status: str | None = "triage"
    assignee: str | None = "unassigned"
    priority: str | None = "P2"
    workspace_path: str | None = None
    workspace_kind: str | None = "worktree"
    branch_name: str | None = None
    pr_url: str | None = None
    tenant: str | None = ""
    tags: list[str] | None = []
    parent_id: str | None = None
    files: list[str] | None = []
    category: str | None = "bug-fix"
    dedup_key: str | None = None
    actor: str | None = None
    task_id: str | None = None
    metadata: dict[str, Any] | None = None


class TaskUpdate(BaseModel):
    title: str | None = None
    description: str | None = None
    board_slug: str | None = None
    status: str | None = None
    assignee: str | None = None
    priority: str | None = None
    workspace_path: str | None = None
    workspace_kind: str | None = None
    branch_name: str | None = None
    pr_url: str | None = None
    tenant: str | None = None
    tags: list[str] | None = None
    metadata: dict[str, Any] | None = None


class TaskMove(BaseModel):
    status: str = Field(..., pattern="^(triage|todo|running|blocked|done)$")
    actor: str | None = "user"
    reason: str | None = None


class CommentCreate(BaseModel):
    author: str | None = Field(default=None, max_length=64)
    body: str = Field(..., min_length=1)


class DependencyLink(BaseModel):
    parent_id: str | None = None
    child_id: str | None = None
    link_type: str | None = "blocks"


class CronJobUpdate(BaseModel):
    enabled: bool | None = None
    minutes: int | None = None
    cron_expr: str | None = None
    schedule: dict[str, Any] | None = None
    schedule_display: str | None = None
    model: str | None = None
    workdir: str | None = None
    prompt: str | None = None
    name: str | None = None
    script: str | None = None
    no_agent: bool | None = None
    context_from: str | list[str] | None = None
    continuity: bool | None = None
    scan_on_idle: bool | None = None
    idle_scan_cooldown_minutes: int | None = None
    idle_scan_max_todo: int | None = None


class CronToggleRequest(BaseModel):
    enabled: bool | None = None


class SettingsUpdate(BaseModel):
    max_active_tasks: int | None = Field(
        default=None,
        ge=1,
        description="Max total active tasks across all boards in running",
    )
    max_concurrent_llm_workers: int | None = Field(
        default=None,
        ge=1,
        description="Max concurrent task and scanner LLM workers across all boards",
    )
    activity_retention_days: int | None = Field(
        default=None,
        ge=1,
        description="Days to retain task_activity log rows before pruning (default 30)",
    )
    enable_cron_scheduler: bool | None = Field(
        default=None, description="Enable periodic background cron scheduler execution"
    )
    langfuse_enabled: bool | None = Field(
        default=None,
        description="Enable Langfuse observability tracing across profiles",
    )
    langfuse_base_url: str | None = Field(
        default=None, description="Langfuse base API URL"
    )
    langfuse_public_key: str | None = Field(
        default=None, description="Langfuse public API key (pk-lf-...)"
    )
    langfuse_secret_key: str | None = Field(
        default=None, description="Langfuse secret API key (sk-lf-...)"
    )
    langfuse_capture_mode: str | None = Field(
        default=None, description="Capture mode: sanitized, metadata, or full"
    )
    langfuse_env: str | None = Field(
        default=None, description="Langfuse environment tag"
    )
    auto_record_memory: bool | None = Field(
        default=None,
        description="Automatically record gotchas/conventions to board memory on reviewer feedback",
    )


class LangfuseTestRequest(BaseModel):
    base_url: str | None = Field(
        default="https://cloud.langfuse.com", description="Langfuse host URL"
    )
    public_key: str | None = Field(
        default="", description="Langfuse public key (pk-lf-...)"
    )
    secret_key: str | None = Field(
        default="", description="Langfuse secret key (sk-lf-...)"
    )


class MemoryCreate(BaseModel):
    category: str | None = Field(
        default="general",
        description="Category: decision, gotcha, convention, rejected_path, general",
    )
    content: str = Field(
        ...,
        min_length=1,
        max_length=MEMORY_CONTENT_MAX_LENGTH,
        description=f"Memory content / rule / finding (max {MEMORY_CONTENT_MAX_LENGTH} chars)",
    )
    tags: list[str] | None = Field(
        default_factory=list, description="Tags for categorization"
    )
    author: str | None = Field(default="user", description="Author: agent name or user")
    task_id: str | None = Field(
        default=None, description="Related task ID if applicable"
    )


class MemoryUpdate(BaseModel):
    category: str | None = None
    content: str | None = Field(
        default=None,
        min_length=1,
        max_length=MEMORY_CONTENT_MAX_LENGTH,
        description=f"Replacement memory content (max {MEMORY_CONTENT_MAX_LENGTH} chars); omitted to keep current content",
    )
    tags: list[str] | None = None
    author: str | None = None
    task_id: str | None = None
