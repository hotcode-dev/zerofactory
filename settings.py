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

Unit boundary
-------------
``idle_scan_cooldown_minutes`` is stored in the database in **minutes** and
is returned by :func:`load_settings` in **minutes** (the API/DB unit). The
dispatcher is the only consumer that needs seconds and converts at a single,
explicit site (``cooldown_seconds = settings["idle_scan_cooldown_minutes"] * 60``).
:const:`DEFAULT_IDLE_SCAN_COOLDOWN_SECONDS` exposes the seconds view of the
default so the dispatcher's fallback path reads naturally.
"""

from __future__ import annotations

from typing import Any, Dict

# --- Default values (source of truth) ---------------------------------------

# Kanban WIP limit: max total active tasks across all boards in ('ready', 'running').
# Controls todo->ready promotion and worktree pre-provisioning to avoid queue flooding.
DEFAULT_MAX_ACTIVE_TASKS = 10

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

# Seconds view of the cooldown default — the single unit-conversion point for the
# default path. The DB stores minutes; the dispatcher converts to seconds where needed.
DEFAULT_IDLE_SCAN_COOLDOWN_SECONDS = DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES * 60

# Canonical list of the global settings keys (order is only for readability/seed order).
SETTING_KEYS = (
    "max_active_tasks",
    "default_max_concurrent_workers",
    "scan_on_idle",
    "idle_scan_active_threshold",
    "idle_scan_cooldown_minutes",
    "idle_scan_max_todo",
    "activity_retention_days",
)

# Seed values for the settings table, derived from the constants above (NOT
# string literals) so the seed rows and the in-code defaults can never drift.
DEFAULT_SETTING_VALUES: Dict[str, str] = {
    "max_active_tasks": str(DEFAULT_MAX_ACTIVE_TASKS),
    "default_max_concurrent_workers": str(DEFAULT_MAX_CONCURRENT_WORKERS),
    "scan_on_idle": "true" if DEFAULT_SCAN_ON_IDLE else "false",
    "idle_scan_active_threshold": str(DEFAULT_IDLE_SCAN_ACTIVE_THRESHOLD),
    "idle_scan_cooldown_minutes": str(DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES),
    "idle_scan_max_todo": str(DEFAULT_IDLE_SCAN_MAX_TODO),
    "activity_retention_days": str(DEFAULT_ACTIVITY_RETENTION_DAYS),
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


def load_settings(conn_or_cursor: Any) -> Dict[str, Any]:
    """Load all six global settings from the ``settings`` table.

    Accepts a ``sqlite3`` connection or cursor. Every key falls back to its
    module default when the row is missing or its value cannot be parsed,
    preserving the historical clamping semantics (``max(1, ...)`` /
    ``max(0, ...)``). Unknown keys in the table are ignored.

    Returns a dict with exactly the :data:`SETTING_KEYS` in their native
    types. ``idle_scan_cooldown_minutes`` is returned in MINUTES (the DB unit);
    see the module docstring for the unit boundary.
    """
    settings: Dict[str, Any] = {
        "max_active_tasks": DEFAULT_MAX_ACTIVE_TASKS,
        "default_max_concurrent_workers": DEFAULT_MAX_CONCURRENT_WORKERS,
        "scan_on_idle": DEFAULT_SCAN_ON_IDLE,
        "idle_scan_active_threshold": DEFAULT_IDLE_SCAN_ACTIVE_THRESHOLD,
        "idle_scan_cooldown_minutes": DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES,
        "idle_scan_max_todo": DEFAULT_IDLE_SCAN_MAX_TODO,
        "activity_retention_days": DEFAULT_ACTIVITY_RETENTION_DAYS,
    }
    try:
        rows = conn_or_cursor.execute("SELECT key, value FROM settings").fetchall()
    except Exception:
        # No settings table (legacy/minimal DB) — return defaults unchanged.
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
        elif k == "default_max_concurrent_workers":
            c = _clamp_int(v, 1)
            if c is not None:
                settings["default_max_concurrent_workers"] = c
        elif k == "scan_on_idle":
            # Bool is unconditional (matches prior behavior: a present row always wins).
            settings["scan_on_idle"] = _parse_bool(v)
        elif k == "idle_scan_active_threshold":
            c = _clamp_int(v, 1)
            if c is not None:
                settings["idle_scan_active_threshold"] = c
        elif k == "idle_scan_cooldown_minutes":
            c = _clamp_int(v, 1)
            if c is not None:
                settings["idle_scan_cooldown_minutes"] = c
        elif k == "idle_scan_max_todo":
            c = _clamp_int(v, 0)
            if c is not None:
                settings["idle_scan_max_todo"] = c
        elif k == "activity_retention_days":
            # Clamp to >= 1 so a stored "0"/garbage can never wipe the whole log;
            # 0 only disables pruning when passed programmatically to prune_old_activity.
            c = _clamp_int(v, 1)
            if c is not None:
                settings["activity_retention_days"] = c

    return settings
