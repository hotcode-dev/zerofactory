"""Zero Factory — shared global-settings definitions and parsing.

Single source of truth for the global settings keys persisted in the
``settings`` table:

* their default values,
* the seed rows written on first ``init_db()``, and
* the parse / clamp / fallback logic shared by the dashboard API
  (``dashboard/plugin_api.py``) and the dispatcher (``dispatcher.py``).

Both consumers call :func:`load_settings` instead of re-implementing the
key-lookup + clamp + fallback pattern, so the defaults and the clamping
semantics can no longer drift between the two modules.

Idle-scan settings (NOT in the ``settings`` table)
--------------------------------------------------
The idle-scan knobs (``scan_on_idle``, ``idle_scan_cooldown_minutes``,
``idle_scan_active_threshold``, ``idle_scan_max_todo``) are **not** part of
the global ``settings`` table and are **not** returned by
:func:`load_settings`. They live in the per-board scanner cron job config
(see ``cron/definitions.py``) and are read by the dispatcher via
``get_scanner_cron_config()``. The ``DEFAULT_*`` constants in this module
serve only as shared *defaults* for that fallback path.

Unit boundary
-------------
``idle_scan_cooldown_minutes`` is stored in **minutes** (the DB/API unit).
The dispatcher is the only consumer that needs seconds and converts at a
single, explicit site (``cooldown_seconds = cooldown_minutes * 60`` in
``dispatcher/scheduler.py``). :const:`DEFAULT_IDLE_SCAN_COOLDOWN_SECONDS`
exposes the seconds view of the default so that fallback path reads
naturally.
"""

from __future__ import annotations

from typing import Any

# --- Default values (source of truth) ---------------------------------------

# Kanban WIP limit: max total active tasks across all boards in 'running'.
# Controls direct todo->running dispatch and worktree pre-provisioning to avoid queue flooding.
DEFAULT_MAX_ACTIVE_TASKS = 10

# Global cap on concurrent LLM workers across boards (tasks and scans).
# Keep the task WIP limit independent from the process capacity limit.
DEFAULT_MAX_CONCURRENT_LLM_WORKERS = 10

# Fallback cap for concurrent active agent worker subprocesses ('running').
# Defaults to 1; customized per board via boards.max_concurrent_running.
DEFAULT_MAX_CONCURRENT_WORKERS = 1

# Automatically trigger idle improvement scans when running workers drop below threshold.
DEFAULT_SCAN_ON_IDLE = True

# Number of active running workers on a board below which an idle scan is considered.
DEFAULT_IDLE_SCAN_ACTIVE_THRESHOLD = 2

# Minimum cooldown between idle improvement scans for the same board, in MINUTES
# (the DB storage unit). See DEFAULT_IDLE_SCAN_COOLDOWN_SECONDS for the seconds view.
DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES = 15

# Max 'todo' backlog tasks allowed on a board before idle scans are suppressed.
DEFAULT_IDLE_SCAN_MAX_TODO = 2

# Retention window (days) for the append-only ``task_activity`` log. Rows older
# than this are pruned by ``dashboard.plugin_api.prune_old_activity``. A value of
# ``0`` disables pruning (the table then grows without bound). Kept >= 1 by the
# parser when set via the API so a stray "0" can't accidentally delete everything.
DEFAULT_ACTIVITY_RETENTION_DAYS = 30

# Enable periodic background cron scheduler execution (dispatcher ticker & scheduled runs).
DEFAULT_ENABLE_CRON_SCHEDULER = True

# Automatically create a public GitHub issue on hotcode-dev/zerofactory when internal defects are reported.
DEFAULT_AUTO_CREATE_GITHUB_ISSUES = False

# Langfuse observability settings
DEFAULT_LANGFUSE_ENABLED = False
DEFAULT_LANGFUSE_BASE_URL = "https://cloud.langfuse.com"
DEFAULT_LANGFUSE_PUBLIC_KEY = ""
DEFAULT_LANGFUSE_SECRET_KEY = ""
DEFAULT_LANGFUSE_CAPTURE_MODE = "sanitized"
DEFAULT_LANGFUSE_ENV = "zerofactory"

# Continuous Learning & Memory settings
# When enabled, reviewer feedback and rejections with gotchas/conventions are automatically
# persisted to board_memories for that repository.
DEFAULT_AUTO_RECORD_MEMORY = True
DEFAULT_MEM0_ENABLED = True
DEFAULT_MEM0_BASE_URL = ""
DEFAULT_MEM0_API_KEY = ""
DEFAULT_MEM0_MODEL = "RadixArk/Qwen3.8-27B-NVFP4"
DEFAULT_MEM0_EMBEDDER_PROVIDER = "fastembed"
DEFAULT_MEM0_EMBEDDER_MODEL = "BAAI/bge-small-en-v1.5"

# Maximum wall-clock execution duration (in seconds) before an active task worker is terminated as stuck.
DEFAULT_TASK_TIMEOUT_SECONDS = 3600  # 1 hour max running time

# Maximum idle duration (in seconds) with no log output or session updates before an agent worker is reaped.
DEFAULT_INACTIVITY_TIMEOUT_SECONDS = 900  # 15 mins with no log/session update

# Seconds view of the cooldown default — the single unit-conversion point for the
# default path. The DB stores minutes; the dispatcher converts to seconds where needed.
DEFAULT_IDLE_SCAN_COOLDOWN_SECONDS = DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES * 60

# Canonical list of the global settings keys (order is only for readability/seed order).
SETTING_KEYS = (
    "max_active_tasks",
    "max_concurrent_llm_workers",
    "activity_retention_days",
    "task_timeout_seconds",
    "inactivity_timeout_seconds",
    "enable_cron_scheduler",
    "langfuse_enabled",
    "langfuse_base_url",
    "langfuse_public_key",
    "langfuse_secret_key",
    "langfuse_capture_mode",
    "langfuse_env",
    "auto_record_memory",
    "mem0_enabled",
    "mem0_base_url",
    "mem0_api_key",
    "mem0_model",
    "mem0_embedder_provider",
    "mem0_embedder_model",
    "auto_create_github_issues",
)

# Seed values for the settings table, derived from the constants above (NOT
# string literals) so the seed rows and the in-code defaults can never drift.
DEFAULT_SETTING_VALUES: dict[str, str] = {
    "max_active_tasks": str(DEFAULT_MAX_ACTIVE_TASKS),
    "max_concurrent_llm_workers": str(DEFAULT_MAX_CONCURRENT_LLM_WORKERS),
    "activity_retention_days": str(DEFAULT_ACTIVITY_RETENTION_DAYS),
    "task_timeout_seconds": str(DEFAULT_TASK_TIMEOUT_SECONDS),
    "inactivity_timeout_seconds": str(DEFAULT_INACTIVITY_TIMEOUT_SECONDS),
    "enable_cron_scheduler": "true" if DEFAULT_ENABLE_CRON_SCHEDULER else "false",
    "auto_create_github_issues": "true" if DEFAULT_AUTO_CREATE_GITHUB_ISSUES else "false",
    "langfuse_enabled": "true" if DEFAULT_LANGFUSE_ENABLED else "false",
    "langfuse_base_url": DEFAULT_LANGFUSE_BASE_URL,
    "langfuse_public_key": DEFAULT_LANGFUSE_PUBLIC_KEY,
    "langfuse_secret_key": DEFAULT_LANGFUSE_SECRET_KEY,
    "langfuse_capture_mode": DEFAULT_LANGFUSE_CAPTURE_MODE,
    "langfuse_env": DEFAULT_LANGFUSE_ENV,
    "auto_record_memory": "true" if DEFAULT_AUTO_RECORD_MEMORY else "false",
    "mem0_enabled": "true" if DEFAULT_MEM0_ENABLED else "false",
    "mem0_base_url": DEFAULT_MEM0_BASE_URL,
    "mem0_api_key": DEFAULT_MEM0_API_KEY,
    "mem0_model": DEFAULT_MEM0_MODEL,
    "mem0_embedder_provider": DEFAULT_MEM0_EMBEDDER_PROVIDER,
    "mem0_embedder_model": DEFAULT_MEM0_EMBEDDER_MODEL,
}


def _clamp_int(value: Any, lower: int) -> Any:
    """Coerce ``value`` to ``int`` clamped to ``lower``; return ``None`` on failure."""
    try:
        return max(lower, int(value))
    except (TypeError, ValueError):
        return None


def _parse_bool(value: Any) -> bool:
    """Parse a stored boolean ('true'/'1'/'yes' are truthy). Never raises."""
    return str(value).lower() in ("true", "1", "yes")


def load_settings(conn_or_cursor: Any) -> dict[str, Any]:
    """Load all global settings from the ``settings`` table.

    Accepts a ``sqlite3`` connection or cursor. Every key falls back to its
    module default when the row is missing or its value cannot be parsed,
    preserving the clamping semantics (``max(1, ...)`` /
    ``max(0, ...)``). Unknown keys in the table are ignored.

    Returns a dict with exactly the :data:`SETTING_KEYS` in their native
    types. The idle-scan settings (``scan_on_idle``,
    ``idle_scan_cooldown_minutes``, ``idle_scan_active_threshold``,
    ``idle_scan_max_todo``) are **not** included — they live in the
    per-board scanner cron job config, see the module docstring.
    """
    settings: dict[str, Any] = {
        "max_active_tasks": DEFAULT_MAX_ACTIVE_TASKS,
        "max_concurrent_llm_workers": DEFAULT_MAX_CONCURRENT_LLM_WORKERS,
        "activity_retention_days": DEFAULT_ACTIVITY_RETENTION_DAYS,
        "task_timeout_seconds": DEFAULT_TASK_TIMEOUT_SECONDS,
        "inactivity_timeout_seconds": DEFAULT_INACTIVITY_TIMEOUT_SECONDS,
        "enable_cron_scheduler": DEFAULT_ENABLE_CRON_SCHEDULER,
        "langfuse_enabled": DEFAULT_LANGFUSE_ENABLED,
        "langfuse_base_url": DEFAULT_LANGFUSE_BASE_URL,
        "langfuse_public_key": DEFAULT_LANGFUSE_PUBLIC_KEY,
        "langfuse_secret_key": DEFAULT_LANGFUSE_SECRET_KEY,
        "langfuse_capture_mode": DEFAULT_LANGFUSE_CAPTURE_MODE,
        "langfuse_env": DEFAULT_LANGFUSE_ENV,
        "auto_record_memory": DEFAULT_AUTO_RECORD_MEMORY,
        "mem0_enabled": DEFAULT_MEM0_ENABLED,
        "mem0_base_url": DEFAULT_MEM0_BASE_URL,
        "mem0_api_key": DEFAULT_MEM0_API_KEY,
        "mem0_model": DEFAULT_MEM0_MODEL,
        "mem0_embedder_provider": DEFAULT_MEM0_EMBEDDER_PROVIDER,
        "mem0_embedder_model": DEFAULT_MEM0_EMBEDDER_MODEL,
        "auto_create_github_issues": DEFAULT_AUTO_CREATE_GITHUB_ISSUES,
    }
    try:
        rows = conn_or_cursor.execute("SELECT key, value FROM settings").fetchall()
    except Exception:
        # No settings table (minimal DB) — return defaults unchanged.
        return settings

    for row in rows:
        try:
            k, v = row["key"], row["value"]
        except Exception:
            # Tolerate non-Row cursors (index access fallback).
            try:
                k, v = row[0], row[1]
            except Exception:
                continue

        if k == "max_active_tasks":
            c = _clamp_int(v, 1)
            if c is not None:
                settings["max_active_tasks"] = c
        elif k == "max_concurrent_llm_workers":
            c = _clamp_int(v, 1)
            if c is not None:
                settings["max_concurrent_llm_workers"] = c
        elif k == "activity_retention_days":
            # Clamp to >= 1 so a stored "0"/garbage can never wipe the whole log;
            # 0 only disables pruning when passed programmatically to prune_old_activity.
            c = _clamp_int(v, 1)
            if c is not None:
                settings["activity_retention_days"] = c
        elif k == "task_timeout_seconds":
            c = _clamp_int(v, 1)
            if c is not None:
                settings["task_timeout_seconds"] = c
        elif k == "inactivity_timeout_seconds":
            c = _clamp_int(v, 1)
            if c is not None:
                settings["inactivity_timeout_seconds"] = c
        elif k == "enable_cron_scheduler":
            settings["enable_cron_scheduler"] = _parse_bool(v)
        elif k == "langfuse_enabled":
            settings["langfuse_enabled"] = _parse_bool(v)
        elif k == "langfuse_base_url":
            if v is not None:
                settings["langfuse_base_url"] = str(v).strip()
        elif k == "langfuse_public_key":
            if v is not None:
                settings["langfuse_public_key"] = str(v).strip()
        elif k == "langfuse_secret_key":
            if v is not None:
                settings["langfuse_secret_key"] = str(v).strip()
        elif k == "langfuse_capture_mode":
            mode = str(v).strip().lower() if v is not None else ""
            if mode in ("sanitized", "metadata", "full"):
                settings["langfuse_capture_mode"] = mode
        elif k == "langfuse_env":
            if v is not None and str(v).strip():
                settings["langfuse_env"] = str(v).strip()
        elif k == "auto_record_memory":
            settings["auto_record_memory"] = _parse_bool(v)
        elif k == "mem0_enabled":
            settings["mem0_enabled"] = _parse_bool(v)
        elif k == "mem0_base_url":
            if v is not None:
                settings["mem0_base_url"] = str(v).strip()
        elif k == "mem0_api_key":
            if v is not None:
                settings["mem0_api_key"] = str(v).strip()
        elif k == "mem0_model":
            if v is not None and str(v).strip():
                settings["mem0_model"] = str(v).strip()
        elif k == "mem0_embedder_provider":
            prov = str(v).strip().lower() if v is not None else ""
            if prov in ("fastembed", "openai"):
                settings["mem0_embedder_provider"] = prov
        elif k == "mem0_embedder_model":
            if v is not None and str(v).strip():
                settings["mem0_embedder_model"] = str(v).strip()
        elif k == "auto_create_github_issues":
            settings["auto_create_github_issues"] = _parse_bool(v)

    return settings
