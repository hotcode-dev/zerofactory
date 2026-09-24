"""Zero Factory Kanban Dispatcher Engine.

The core orchestration engine driving 24/7 autonomous multi-agent software engineering
workflows within the Zero Factory system. It coordinates task scheduling, agent execution,
git worktree isolation, GitHub Pull Request reviews, and worker lifecycle management.

Core Responsibilities:
1. Dependency Graph & DAG Progression:
   - Evaluates parent-child ticket dependencies and automatically unblocks downstream tasks
     when prerequisite parent tasks reach 'done'.
2. Work-in-Progress (WIP) Management & Scheduling:
   - Enforces configurable WIP limits per board and assignee to avoid pipeline congestion.
   - Dispatches scheduled tickets from 'todo' to 'running' based on capacity and priority.
3. Specialist Role Assignment & Routing:
   - Directs tasks to specialized Hermes agent profiles:
     * zf-orchestrator: Goal decomposition, issue triage, repository improvement scanning.
     * zf-builder: Implementation, test writing, worktree-isolated development.
     * zf-reviewer: Thematic code review, security and performance audits, PR polish.
4. Isolated Git Worktree Provisioning:
   - Provisions isolated git worktrees (`~/git/<repo>-worktrees/<task_id>`) with dedicated
     feature branches (`task/<task_id>`).
   - Automatically synchronizes worktrees with the default branch (e.g. 'main') and detects
     merge conflicts, routing conflicting tasks back to builder agents for resolution.
   - Guarantees clean worktree teardown and prevents repository state pollution.
5. Agent Worker Process Lifecycle & Safety:
   - Spawns and tracks non-interactive Hermes worker subprocesses with custom context.
   - Monitors process health, maximum execution limits, and inactivity thresholds.
   - Safely terminates workers (SIGTERM -> SIGKILL) prior to worktree deletion
     to prevent zombie/orphan processes in deleted directories.
   - Reaps crashed, timed out, or orphaned workers, moving affected tickets to 'blocked'.
6. GitHub Pull Request & Review Feedback Loop:
   - Automates branch commits, remote pushes, and PR creation via GitHub CLI (`gh`).
   - Monitors GitHub PR status (`MERGED`, `CONFLICTING`, `CHANGES_REQUESTED`, `APPROVED`).
   - Orchestrates iterative multi-round code review loops between builder and reviewer agents.
   - Escalates approved PRs or unresolvable conflicts to human maintainers.
7. Concurrency & Dispatch Loop Safety:
   - Operates under a global re-entrant lock (`_dispatcher_lock`) to prevent race
     conditions across parallel background cron cycles, CLI commands, and dashboard triggers.
"""

from __future__ import annotations

import fcntl
import json
import logging
import os
import re
import signal
import sqlite3
import subprocess
import threading
import time
from pathlib import Path

# Submodule re-exports
from .config import (
    DEFAULT_INACTIVITY_TIMEOUT_SECONDS,
    DEFAULT_MAX_ACTIVE_TASKS,
    DEFAULT_MAX_CONCURRENT_LLM_WORKERS,
    DEFAULT_MAX_CONCURRENT_WORKERS,
    DEFAULT_MAX_WORKER_RETRIES,
    DEFAULT_SCAN_ON_IDLE,
    DEFAULT_IDLE_SCAN_ACTIVE_THRESHOLD,
    DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES,
    DEFAULT_IDLE_SCAN_COOLDOWN_SECONDS,
    DEFAULT_IDLE_SCAN_MAX_TODO,
    DEFAULT_TASK_TIMEOUT_SECONDS,
    DISPATCH_INTERVAL_SECONDS,
    HUMAN,
    PROFILE_MAP,
    UNASSIGNED,
    VALID_PROFILES,
    _active_scanners,
    _active_workers,
    _dispatcher_lock,
    _dispatcher_thread,
    _last_idle_scan_times,
    _log,
    _REMOTE_BRANCH_DELETE_TIMEOUT,
    _WORKTREE_REMOVE_TIMEOUT,
    get_db_path,
    get_dispatcher_lock_path,
    get_inactivity_timeout_seconds,
    get_max_worker_retries,
    get_task_timeout_seconds,
    is_worker_or_child_process,
    load_settings,
    normalize_assignee,
    resolve_profile_state_db,
)
from .context_builder import (
    digest_board_memories_context,
    digest_reviewer_git_context,
    format_conventional_message,
)
from .git_ops import (
    GitConflictCheckError,
    check_files_for_conflict_markers,
    check_unresolved_conflicts,
    check_unresolved_conflicts_safe,
    clean_stale_git_locks,
    get_default_branch,
    get_git_dir,
    get_modified_status_files,
    get_unmerged_status_files,
    pull_and_merge_main,
    sync_repo_main,
    _has_unresolved_conflict_markers,
    _unverifiable_result,
)
from .github_pr import (
    extract_gh_repo_info,
    fetch_pr_review_comments,
    format_task_comment_body,
    is_reviewer_approval_comment,
)
from .process_manager import (
    stop_task_worker,
    terminate_process_group,
    terminate_worker_process,
)
from .worker_spawner import (
    spawn_agent_worker,
    _inject_langfuse_env,
)
from .reaper import (
    check_stuck_tasks,
    reap_active_workers,
    reap_stuck_tasks,
    _compute_stuck_state,
    _mark_task_session_ended,
    _worker_log_path,
)
from .scanner import (
    reap_active_scanners,
    reset_idle_scanner_state,
    spawn_board_scanner,
    _global_llm_occupancy,
    _running_cron_llm_jobs,
)
from .scheduler import (
    run_dispatch_cycle,
    start_background_dispatcher,
    _dispatcher_loop,
)
from .worktree import (
    resolve_task_repo_path,
    setup_worktree,
    _delete_remote_branch,
    _handle_local_merge_conflict,
    _handle_pr_conflict_from_github,
    _remove_worktree,
)

__all__ = [
    # Config & Constants
    "DEFAULT_TASK_TIMEOUT_SECONDS",
    "DEFAULT_INACTIVITY_TIMEOUT_SECONDS",
    "DEFAULT_MAX_WORKER_RETRIES",
    "DISPATCH_INTERVAL_SECONDS",
    "DEFAULT_MAX_ACTIVE_TASKS",
    "DEFAULT_MAX_CONCURRENT_LLM_WORKERS",
    "DEFAULT_MAX_CONCURRENT_WORKERS",
    "DEFAULT_SCAN_ON_IDLE",
    "DEFAULT_IDLE_SCAN_ACTIVE_THRESHOLD",
    "DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES",
    "DEFAULT_IDLE_SCAN_COOLDOWN_SECONDS",
    "DEFAULT_IDLE_SCAN_MAX_TODO",
    "VALID_PROFILES",
    "PROFILE_MAP",
    "UNASSIGNED",
    "HUMAN",
    "_dispatcher_thread",
    "_dispatcher_lock",
    "_active_workers",
    "_last_idle_scan_times",
    "_active_scanners",
    "_WORKTREE_REMOVE_TIMEOUT",
    "_REMOTE_BRANCH_DELETE_TIMEOUT",
    "_log",
    "get_dispatcher_lock_path",
    "is_worker_or_child_process",
    "get_max_worker_retries",
    "get_task_timeout_seconds",
    "get_inactivity_timeout_seconds",
    "get_db_path",
    "normalize_assignee",
    "resolve_profile_state_db",
    "load_settings",
    # Git Ops
    "GitConflictCheckError",
    "get_default_branch",
    "sync_repo_main",
    "_has_unresolved_conflict_markers",
    "check_files_for_conflict_markers",
    "get_unmerged_status_files",
    "get_modified_status_files",
    "check_unresolved_conflicts",
    "check_unresolved_conflicts_safe",
    "_unverifiable_result",
    "get_git_dir",
    "clean_stale_git_locks",
    "pull_and_merge_main",
    # Context & GitHub
    "digest_reviewer_git_context",
    "digest_board_memories_context",
    "format_conventional_message",
    "extract_gh_repo_info",
    "fetch_pr_review_comments",
    "format_task_comment_body",
    "is_reviewer_approval_comment",
    # Worker & Process
    "spawn_agent_worker",
    "terminate_process_group",
    "terminate_worker_process",
    "stop_task_worker",
    "_inject_langfuse_env",
    # Reaper
    "_worker_log_path",
    "_compute_stuck_state",
    "_mark_task_session_ended",
    "reap_active_workers",
    "check_stuck_tasks",
    "reap_stuck_tasks",
    # Scanner
    "reap_active_scanners",
    "_running_cron_llm_jobs",
    "_global_llm_occupancy",
    "spawn_board_scanner",
    "reset_idle_scanner_state",
    # Worktree
    "resolve_task_repo_path",
    "setup_worktree",
    "_handle_local_merge_conflict",
    "_delete_remote_branch",
    "_remove_worktree",
    "_handle_pr_conflict_from_github",
    # Scheduler
    "run_dispatch_cycle",
    "_dispatcher_loop",
    "start_background_dispatcher",
]
