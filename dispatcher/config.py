"""Configuration, paths, runtime state, and environment helpers for Zero Factory dispatcher."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

try:
    from ..settings import (  # type: ignore
        DEFAULT_MAX_ACTIVE_TASKS,
        DEFAULT_MAX_CONCURRENT_LLM_WORKERS,
        DEFAULT_MAX_CONCURRENT_WORKERS,
        DEFAULT_SCAN_ON_IDLE,
        DEFAULT_IDLE_SCAN_ACTIVE_THRESHOLD,
        DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES,
        DEFAULT_IDLE_SCAN_COOLDOWN_SECONDS,
        DEFAULT_IDLE_SCAN_MAX_TODO,
        load_settings,
    )
except (ImportError, ValueError):
    try:
        from .settings import (  # type: ignore
            DEFAULT_MAX_ACTIVE_TASKS,
            DEFAULT_MAX_CONCURRENT_LLM_WORKERS,
            DEFAULT_MAX_CONCURRENT_WORKERS,
            DEFAULT_SCAN_ON_IDLE,
            DEFAULT_IDLE_SCAN_ACTIVE_THRESHOLD,
            DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES,
            DEFAULT_IDLE_SCAN_COOLDOWN_SECONDS,
            DEFAULT_IDLE_SCAN_MAX_TODO,
            load_settings,
        )
    except (ImportError, ValueError):
        from settings import (  # type: ignore
            DEFAULT_MAX_ACTIVE_TASKS,
            DEFAULT_MAX_CONCURRENT_LLM_WORKERS,
            DEFAULT_MAX_CONCURRENT_WORKERS,
            DEFAULT_SCAN_ON_IDLE,
            DEFAULT_IDLE_SCAN_ACTIVE_THRESHOLD,
            DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES,
            DEFAULT_IDLE_SCAN_COOLDOWN_SECONDS,
            DEFAULT_IDLE_SCAN_MAX_TODO,
            load_settings,
        )

try:
    from ..paths import (  # type: ignore
        HUMAN,
        PROFILE_MAP,
        UNASSIGNED,
        normalize_assignee,
        resolve_profile_state_db,
    )
except (ImportError, ValueError):
    try:
        from .paths import (  # type: ignore
            HUMAN,
            PROFILE_MAP,
            UNASSIGNED,
            normalize_assignee,
            resolve_profile_state_db,
        )
    except (ImportError, ValueError):
        from paths import (  # type: ignore
            HUMAN,
            PROFILE_MAP,
            UNASSIGNED,
            normalize_assignee,
            resolve_profile_state_db,
        )

_log = logging.getLogger("zerofactory.kanban.dispatcher")

# Maximum wall-clock execution duration (in seconds) before an active task worker is terminated as stuck.
DEFAULT_TASK_TIMEOUT_SECONDS = 3600  # 1 hour max running time

# Maximum idle duration (in seconds) with no log output or session updates before an agent worker is reaped.
DEFAULT_INACTIVITY_TIMEOUT_SECONDS = 900  # 15 mins with no log/session update

# Maximum worker failure/timeout retries before task is permanently blocked.
DEFAULT_MAX_WORKER_RETRIES = 3

# Interval (in seconds) between background dispatcher polling cycles.
DISPATCH_INTERVAL_SECONDS = 30

# Background thread handle running the continuous dispatch loop.
_dispatcher_thread: Optional[threading.Thread] = None

# Global re-entrant lock ensuring only one dispatch cycle executes at any given time.
_dispatcher_lock = threading.Lock()

# Registry tracking active worker subprocesses keyed by task_id: {task_id: subprocess.Popen}
_active_workers: Dict[str, subprocess.Popen] = {}

# Timestamp tracking when an idle improvement scan was last triggered per board slug: {board_slug: timestamp}
_last_idle_scan_times: Dict[str, int] = {}

# Registry tracking active scanner worker subprocesses per board slug: {board_slug: subprocess.Popen}
_active_scanners: Dict[str, subprocess.Popen] = {}

# Bounded timeout (seconds) for `git worktree remove` cleanup on the PR-lifecycle hot path.
_WORKTREE_REMOVE_TIMEOUT = 30

# Bounded timeout (seconds) for best-effort remote branch deletion on the PR MERGED/CLOSED archive path.
_REMOTE_BRANCH_DELETE_TIMEOUT = 30

VALID_PROFILES = tuple(PROFILE_MAP)


def _d():
    """Return top-level dispatcher module/package for dynamic dispatch and mocking compatibility."""
    return sys.modules.get("dispatcher") or sys.modules.get(__package__) or sys.modules.get(__name__)


def get_dispatcher_lock_path() -> Path:
    """Path to the cross-process lock file for Kanban dispatch cycles."""
    env_lock = os.environ.get("ZEROFACTORY_LOCK_PATH")
    if env_lock:
        return Path(env_lock)
    return Path.home() / ".hermes" / "zerofactory_dispatcher.lock"


def is_worker_or_child_process() -> bool:
    """Return True if current process is a worker, cron runner, or child CLI process."""
    if os.environ.get("ZEROFACTORY_DISABLE_DISPATCHER") == "1" or os.environ.get("ZEROFACTORY_SKIP_DISPATCHER") == "1":
        return True
    profile = os.environ.get("HERMES_PROFILE") or ""
    if profile in ("zf-builder", "zf-reviewer"):
        return True
    if os.environ.get("HERMES_KANBAN_TASK"):
        return True
    if os.environ.get("_HERMES_CRON_EXTERNAL_WORKER"):
        return True
    return False


def get_max_worker_retries() -> int:
    """Return maximum allowed worker failure/timeout retries before task is permanently blocked."""
    return int(os.environ.get("ZEROFACTORY_MAX_WORKER_RETRIES", str(DEFAULT_MAX_WORKER_RETRIES)))


def get_task_timeout_seconds() -> int:
    """Return maximum allowed running duration before worker is considered stuck."""
    return int(os.environ.get("ZEROFACTORY_TASK_TIMEOUT_SECONDS", str(DEFAULT_TASK_TIMEOUT_SECONDS)))


def get_inactivity_timeout_seconds() -> int:
    """Return maximum allowed inactivity before worker is considered hung."""
    return int(os.environ.get("ZEROFACTORY_INACTIVITY_TIMEOUT_SECONDS", str(DEFAULT_INACTIVITY_TIMEOUT_SECONDS)))


def get_db_path() -> Path:
    """Return path to the Zero Factory SQLite database."""
    env_path = os.environ.get("ZEROFACTORY_DB")
    if env_path:
        return Path(env_path)
    return Path.home() / ".hermes" / "zerofactory.db"
