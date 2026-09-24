"""Zero Factory Dashboard — Pydantic Request/Response Models and Enums."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

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
VALID_MEMORY_CATEGORIES = {"decision", "gotcha", "convention", "rejected_path", "general"}

# Hard bound for manually written memory content (API + CLI). The auto-record
# path caps at 1000 chars; manual writes get a tighter 500-char cap so a single
# oversized blob can never bloat storage or the pre-injected worker prompt.
MEMORY_CONTENT_MAX_LENGTH = 500

ACTIVITY_ACTORS: List[str] = [
    "zf-orchestrator",
    "zf-builder",
    "zf-reviewer",
    "dispatcher",
    "user",
    "other",
]


class BoardCreate(BaseModel):
    git_url: str = Field(..., min_length=1, description="Remote Git URL (e.g. https://github.com/owner/repo.git)")
    description: Optional[str] = ""
    max_concurrent_running: Optional[int] = Field(default=1, ge=1, description="Max tasks running in parallel on this board (default 1)")
    auto_record_memory: Optional[bool] = Field(default=True, description="Enable automatic memory recording from reviewer feedback")
    additional_reviewer_usernames: Optional[List[str]] = Field(default_factory=list, description="Additional GitHub usernames whose PR feedback is trusted")


class BoardUpdate(BaseModel):
    description: Optional[str] = None
    git_url: Optional[str] = None
    max_concurrent_running: Optional[int] = Field(default=None, ge=1, description="Max tasks running in parallel on this board")
    auto_record_memory: Optional[bool] = Field(default=None, description="Enable automatic memory recording from reviewer feedback")
    additional_reviewer_usernames: Optional[List[str]] = Field(default=None, description="Additional GitHub usernames whose PR feedback is trusted")


class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = ""
    board_slug: Optional[str] = None
    status: Optional[str] = "triage"
    assignee: Optional[str] = "unassigned"
    priority: Optional[str] = "P2"
    workspace_path: Optional[str] = None
    workspace_kind: Optional[str] = "worktree"
    branch_name: Optional[str] = None
    pr_url: Optional[str] = None
    tenant: Optional[str] = ""
    tags: Optional[List[str]] = []
    parent_id: Optional[str] = None
    files: Optional[List[str]] = []
    category: Optional[str] = "bug-fix"
    dedup_key: Optional[str] = None
    actor: Optional[str] = None


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    board_slug: Optional[str] = None
    status: Optional[str] = None
    assignee: Optional[str] = None
    priority: Optional[str] = None
    workspace_path: Optional[str] = None
    workspace_kind: Optional[str] = None
    branch_name: Optional[str] = None
    pr_url: Optional[str] = None
    tenant: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None


class TaskMove(BaseModel):
    status: str = Field(..., pattern="^(triage|todo|running|blocked|done)$")
    actor: Optional[str] = "user"
    reason: Optional[str] = None


class CommentCreate(BaseModel):
    author: Optional[str] = Field(default=None, max_length=64)
    body: str = Field(..., min_length=1)


class DependencyLink(BaseModel):
    parent_id: Optional[str] = None
    child_id: Optional[str] = None
    link_type: Optional[str] = "blocks"


class CronJobUpdate(BaseModel):
    enabled: Optional[bool] = None
    minutes: Optional[int] = None
    cron_expr: Optional[str] = None
    schedule: Optional[Dict[str, Any]] = None
    schedule_display: Optional[str] = None
    model: Optional[str] = None
    workdir: Optional[str] = None
    prompt: Optional[str] = None
    name: Optional[str] = None
    script: Optional[str] = None
    no_agent: Optional[bool] = None
    context_from: Optional[Union[str, List[str]]] = None
    continuity: Optional[bool] = None


class CronToggleRequest(BaseModel):
    enabled: Optional[bool] = None


class SettingsUpdate(BaseModel):
    max_active_tasks: Optional[int] = Field(default=None, ge=1, description="Max total active tasks across all boards in running")
    max_concurrent_llm_workers: Optional[int] = Field(default=None, ge=1, description="Max concurrent task and scanner LLM workers across all boards")
    scan_on_idle: Optional[bool] = Field(default=None, description="Automatically trigger improvement scans when active workers are below threshold")
    idle_scan_active_threshold: Optional[int] = Field(default=None, ge=1, description="Max active running workers on a board to trigger idle scan")
    idle_scan_cooldown_minutes: Optional[int] = Field(default=None, ge=1, description="Minimum cooldown in minutes between idle improvement scans per board")
    idle_scan_max_todo: Optional[int] = Field(default=None, ge=0, description="Max todo backlog tasks on board before suppressing idle scan")
    activity_retention_days: Optional[int] = Field(default=None, ge=1, description="Days to retain task_activity log rows before pruning (default 30)")
    enable_cron_scheduler: Optional[bool] = Field(default=None, description="Enable periodic background cron scheduler execution")
    langfuse_enabled: Optional[bool] = Field(default=None, description="Enable Langfuse observability tracing across profiles")
    langfuse_base_url: Optional[str] = Field(default=None, description="Langfuse base API URL")
    langfuse_public_key: Optional[str] = Field(default=None, description="Langfuse public API key (pk-lf-...)")
    langfuse_secret_key: Optional[str] = Field(default=None, description="Langfuse secret API key (sk-lf-...)")
    langfuse_capture_mode: Optional[str] = Field(default=None, description="Capture mode: sanitized, metadata, or full")
    langfuse_env: Optional[str] = Field(default=None, description="Langfuse environment tag")
    auto_record_memory: Optional[bool] = Field(default=None, description="Automatically record gotchas/conventions to board memory on reviewer feedback")


class LangfuseTestRequest(BaseModel):
    base_url: Optional[str] = Field(default="https://cloud.langfuse.com", description="Langfuse host URL")
    public_key: Optional[str] = Field(default="", description="Langfuse public key (pk-lf-...)")
    secret_key: Optional[str] = Field(default="", description="Langfuse secret key (sk-lf-...)")


class MemoryCreate(BaseModel):
    category: Optional[str] = Field(default="general", description="Category: decision, gotcha, convention, rejected_path, general")
    content: str = Field(..., min_length=1, max_length=MEMORY_CONTENT_MAX_LENGTH, description=f"Memory content / rule / finding (max {MEMORY_CONTENT_MAX_LENGTH} chars)")
    tags: Optional[List[str]] = Field(default_factory=list, description="Tags for categorization")
    author: Optional[str] = Field(default="user", description="Author: agent name or user")
    task_id: Optional[str] = Field(default=None, description="Related task ID if applicable")


class MemoryUpdate(BaseModel):
    category: Optional[str] = None
    content: Optional[str] = Field(default=None, min_length=1, max_length=MEMORY_CONTENT_MAX_LENGTH, description=f"Replacement memory content (max {MEMORY_CONTENT_MAX_LENGTH} chars); omitted to keep current content")
    tags: Optional[List[str]] = None
    author: Optional[str] = None
    task_id: Optional[str] = None
