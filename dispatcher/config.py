"""Configuration, paths, runtime state, and environment helpers for Zero Factory dispatcher."""

from __future__ import annotations

import logging
import os
import subprocess
import sys
import threading
import time
from pathlib import Path

try:
    from ..settings import (  # type: ignore
        DEFAULT_IDLE_SCAN_ACTIVE_THRESHOLD,
        DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES,
        DEFAULT_IDLE_SCAN_COOLDOWN_SECONDS,
        DEFAULT_IDLE_SCAN_MAX_TODO,
        DEFAULT_MAX_ACTIVE_TASKS,
        DEFAULT_MAX_CONCURRENT_LLM_WORKERS,
        DEFAULT_MAX_CONCURRENT_WORKERS,
        DEFAULT_SCAN_ON_IDLE,
        load_settings,
    )
except (ImportError, ValueError):
    from settings import (  # type: ignore
        DEFAULT_IDLE_SCAN_ACTIVE_THRESHOLD,
        DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES,
        DEFAULT_IDLE_SCAN_COOLDOWN_SECONDS,
        DEFAULT_IDLE_SCAN_MAX_TODO,
        DEFAULT_MAX_ACTIVE_TASKS,
        DEFAULT_MAX_CONCURRENT_LLM_WORKERS,
        DEFAULT_MAX_CONCURRENT_WORKERS,
        DEFAULT_SCAN_ON_IDLE,
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

# Grace window (seconds) during which a freshly-claimed task is treated as
# "spawn in flight" rather than an orphan. Covers hermes worker startup plus
# session registration; recovering inside this window double-dispatched the
# builder on task zf-hdz-4dc03cee (two concurrent sessions on one worktree).
DEFAULT_SPAWN_GRACE_SECONDS = 180

# Interval (in seconds) between background dispatcher polling cycles.
DISPATCH_INTERVAL_SECONDS = 30

# Background thread handle running the continuous dispatch loop.
_dispatcher_thread: threading.Thread | None = None

# Global re-entrant lock ensuring only one dispatch cycle executes at any given time.
_dispatcher_lock = threading.RLock()

# Registry tracking active worker subprocesses keyed by task_id: {task_id: subprocess.Popen}
_active_workers: dict[str, subprocess.Popen] = {}

# Timestamp tracking when an idle improvement scan was last triggered per board slug: {board_slug: timestamp}
_last_idle_scan_times: dict[str, int] = {}

# Registry tracking active scanner worker subprocesses per board slug: {board_slug: subprocess.Popen}
_active_scanners: dict[str, subprocess.Popen] = {}

# Bounded timeout (seconds) for `git worktree remove` cleanup on the PR-lifecycle hot path.
_WORKTREE_REMOVE_TIMEOUT = 30

# Bounded timeout (seconds) for best-effort remote branch deletion on the PR MERGED/CLOSED archive path.
_REMOTE_BRANCH_DELETE_TIMEOUT = 30

VALID_PROFILES = tuple(PROFILE_MAP)


def _d():
    """Return top-level dispatcher module/package for dynamic dispatch and mocking compatibility."""
    return (
        sys.modules.get("dispatcher")
        or sys.modules.get(__package__)
        or sys.modules.get(__name__)
    )


def get_dispatcher_lock_path() -> Path:
    """Path to the cross-process lock file for Kanban dispatch cycles."""
    env_lock = os.environ.get("ZEROFACTORY_LOCK_PATH")
    if env_lock:
        return Path(env_lock)
    return Path.home() / ".hermes" / "zerofactory_dispatcher.lock"


def is_worker_or_child_process() -> bool:
    """Return True if current process is a worker, cron runner, or child CLI process."""
    if (
        os.environ.get("ZEROFACTORY_DISABLE_DISPATCHER") == "1"
        or os.environ.get("ZEROFACTORY_SKIP_DISPATCHER") == "1"
    ):
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
    return int(
        os.environ.get(
            "ZEROFACTORY_MAX_WORKER_RETRIES", str(DEFAULT_MAX_WORKER_RETRIES)
        )
    )


def get_spawn_grace_seconds() -> int:
    """Return how long a claimed task may spend spawning before it counts as orphaned."""
    return int(
        os.environ.get(
            "ZEROFACTORY_SPAWN_GRACE_SECONDS", str(DEFAULT_SPAWN_GRACE_SECONDS)
        )
    )


def get_task_timeout_seconds() -> int:
    """Return maximum allowed running duration before worker is considered stuck."""
    return int(
        os.environ.get(
            "ZEROFACTORY_TASK_TIMEOUT_SECONDS", str(DEFAULT_TASK_TIMEOUT_SECONDS)
        )
    )


def get_inactivity_timeout_seconds() -> int:
    """Return maximum allowed inactivity before worker is considered hung."""
    return int(
        os.environ.get(
            "ZEROFACTORY_INACTIVITY_TIMEOUT_SECONDS",
            str(DEFAULT_INACTIVITY_TIMEOUT_SECONDS),
        )
    )


def get_db_path() -> Path:
    """Return path to the Zero Factory SQLite database."""
    env_path = os.environ.get("ZEROFACTORY_DB")
    if env_path:
        return Path(env_path)
    return Path.home() / ".hermes" / "zerofactory.db"


# --- Step logging: grep-able start/end markers for every pipeline step -------
# Every dispatcher step (spawn, precheck, precommit, commit, merge, push, PR,
# verdict routing, ...) logs a `STEP <name> start` / `STEP <name> end` pair so
# agent.log reconstructs exactly which step a task entered, finished, or stalled
# in — the gap that made task zf-hdz-4dc03cee's 3.5h silent stall undiagnosable.
# `log_step_state` records recurring gate decisions (e.g. "why the poller left
# the task alone this cycle") without flooding the log every 30s cycle.

_STEP_STATE_LOG_INTERVAL = 900  # seconds between repeat logs of the same state
_STEP_STATE_CACHE_MAX = 4096
_step_state_last: dict[str, tuple[str, float]] = {}


def log_step_start(
    step: str,
    task_id: str | None = None,
    detail: str = "",
    logger: logging.Logger | None = None,
) -> float:
    """Log a pipeline step start; returns the start timestamp for log_step_end."""
    t0 = time.monotonic()
    (logger or _log).info(
        "STEP %s start | task=%s | %s", step, task_id or "-", detail or "-"
    )
    return t0


def log_step_end(
    step: str,
    started_at: float,
    task_id: str | None = None,
    outcome: str = "ok",
    detail: str = "",
    logger: logging.Logger | None = None,
) -> None:
    """Log a pipeline step end with its outcome and duration (always paired)."""
    (logger or _log).info(
        "STEP %s end | task=%s | %s | %.1fs | %s",
        step,
        task_id or "-",
        outcome,
        time.monotonic() - started_at,
        detail or "-",
    )


class StepTracker:
    """Sequential pipeline steps with guaranteed paired start/end log lines.

    ``start()`` implicitly ends the previous step, so a multi-exit pipeline only
    needs one ``start()`` per phase plus ``end()`` where the pipeline actually
    stops (including the error exits). A step that never ends in the log means
    the process died mid-step — exactly the forensic trail needed to find where
    a task stalled::

        steps = StepTracker(task_id).start("package.precommit")
        ...
        steps.start("package.commit")      # ends package.precommit (ok)
        ...
        steps.end("fail", "merge conflict")  # pipeline stops here
    """

    __slots__ = ("task_id", "logger", "name", "t0")

    def __init__(
        self, task_id: str | None = None, logger: logging.Logger | None = None
    ) -> None:
        self.task_id = task_id
        self.logger = logger
        self.name = ""
        self.t0 = 0.0

    def start(self, step: str, detail: str = "") -> "StepTracker":
        """End the in-flight step (if any) and start ``step``."""
        self.end()
        self.name = step
        self.t0 = log_step_start(step, self.task_id, detail, logger=self.logger)
        return self

    def end(self, outcome: str = "ok", detail: str = "") -> None:
        """End the in-flight step; no-op when no step is active."""
        if not self.name:
            return
        log_step_end(
            self.name, self.t0, self.task_id, outcome, detail, logger=self.logger
        )
        self.name = ""


def log_step_state(
    step: str,
    task_id: str | None,
    state: str,
    detail: str = "",
    logger: logging.Logger | None = None,
) -> None:
    """Log a recurring gate decision, rate-limited per (step, task, state).

    The dispatch loop re-evaluates the same gates every cycle; this logs the
    first time a state is seen and then at most once per
    ``_STEP_STATE_LOG_INTERVAL`` while it persists, so a stuck task leaves a
    breadcrumb trail without flooding agent.log. Any state/detail *change*
    logs immediately.
    """
    key = f"{step}:{task_id or '-'}"
    signature = f"{state}|{detail}"
    now = time.monotonic()
    last_signature, last_at = _step_state_last.get(key, ("", 0.0))
    if signature == last_signature and (now - last_at) < _STEP_STATE_LOG_INTERVAL:
        return
    if len(_step_state_last) >= _STEP_STATE_CACHE_MAX:
        _step_state_last.clear()
    _step_state_last[key] = (signature, now)
    (logger or _log).info(
        "STEP %s | task=%s | %s | %s", step, task_id or "-", state, detail or "-"
    )
