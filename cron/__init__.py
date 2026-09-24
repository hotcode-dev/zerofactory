"""Zero Factory built-in cron management package.

Provides automated job definition, synchronization, scheduling checks, and execution.
"""

from __future__ import annotations

from .config import (
    CRON_RUN_OUTPUT_TAIL_CHARS,
    CRON_RUN_TIMEOUT,
    DAILY_REPORT_PROMPT,
    DEFAULT_DB_PATH,
    TASK_QUEUE_CHECK_PROMPT,
    _active_cron_runs,
    _c,
    _load_env_defaults,
    get_db_path,
    reap_active_cron_runs,
)
from .definitions import (
    BUILTIN_CRON_JOBS,
    CORE_CRON_JOBS,
    build_board_scanner_prompt,
    get_all_builtin_cron_jobs,
    resolve_board_repo_path,
)
from .executor import tick_builtin_cron, trigger_builtin_job
from .manager import (
    _apply_job_field_updates,
    ensure_builtin_cron_jobs,
    list_builtin_jobs,
    prune_board_cron_job,
    reset_builtin_job,
    toggle_builtin_job,
    update_builtin_job,
)
from .scheduler_check import is_cron_scheduler_enabled, set_cron_scheduler_enabled
from .store import (
    cleanup_duplicate_root_jobs,
    compute_job_next_run,
    get_target_jobs_files,
    load_jobs_from_file,
    save_jobs_to_file,
)

__all__ = [
    "CRON_RUN_OUTPUT_TAIL_CHARS",
    "CRON_RUN_TIMEOUT",
    "DAILY_REPORT_PROMPT",
    "DEFAULT_DB_PATH",
    "TASK_QUEUE_CHECK_PROMPT",
    "_active_cron_runs",
    "_apply_job_field_updates",
    "_c",
    "_load_env_defaults",
    "build_board_scanner_prompt",
    "BUILTIN_CRON_JOBS",
    "cleanup_duplicate_root_jobs",
    "compute_job_next_run",
    "CORE_CRON_JOBS",
    "ensure_builtin_cron_jobs",
    "get_all_builtin_cron_jobs",
    "get_db_path",
    "get_target_jobs_files",
    "is_cron_scheduler_enabled",
    "list_builtin_jobs",
    "load_jobs_from_file",
    "prune_board_cron_job",
    "reap_active_cron_runs",
    "reset_builtin_job",
    "resolve_board_repo_path",
    "save_jobs_to_file",
    "set_cron_scheduler_enabled",
    "tick_builtin_cron",
    "toggle_builtin_job",
    "trigger_builtin_job",
    "update_builtin_job",
]
