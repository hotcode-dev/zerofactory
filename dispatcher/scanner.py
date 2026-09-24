"""Board scanner spawning, tracking, and capacity-based occupancy calculations."""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path
from typing import Optional

from .config import (
    _active_scanners,
    _d,
    _last_idle_scan_times,
    _log,
)


def reap_active_scanners() -> int:
    """Clean up finished or exited scanner worker processes."""
    reaped = 0
    for slug, proc in list(_active_scanners.items()):
        if proc is not None:
            retcode = proc.poll()
            if retcode is not None:
                _active_scanners.pop(slug, None)
                reaped += 1
                _log.debug("Scanner process for board '%s' exited with code %d", slug, retcode)
    return reaped


def _running_cron_llm_jobs() -> int:
    """Count in-process Zero Factory cron LLM jobs (exclude No-Agent queue checks)."""
    try:
        from cron.scheduler import get_running_job_ids  # type: ignore
        return sum(
            job_id == "zero-factory-daily-report" or job_id.startswith("zero-factory-improvement-scanner-")
            for job_id in get_running_job_ids()
        )
    except (ImportError, RuntimeError):
        return 0


def _global_llm_occupancy(running_tasks: int) -> int:
    """LLM workers currently tracked by this Zero Factory process."""
    try:
        from ..builtin_cron import _active_cron_runs, reap_active_cron_runs
    except (ImportError, ValueError):
        try:
            from .builtin_cron import _active_cron_runs, reap_active_cron_runs  # type: ignore
        except (ImportError, ValueError):
            from builtin_cron import _active_cron_runs, reap_active_cron_runs  # type: ignore
    reap_active_cron_runs()
    running_cron = getattr(_d(), "_running_cron_llm_jobs", _running_cron_llm_jobs)()
    return running_tasks + len(_active_scanners) + running_cron + sum(
        job_id != "zero-factory-task-queue-check" for job_id in _active_cron_runs
    )


def spawn_board_scanner(board_slug: str, repo_path: Optional[Path] = None) -> Optional[int]:
    """Spawn an improvement scanner agent worker process for a specific board."""
    if os.environ.get("ZEROFACTORY_SKIP_WORKER_SPAWN") or os.environ.get("ZEROFACTORY_SKIP_SCANNER_SPAWN"):
        return None

    try:
        try:
            from ..builtin_cron import is_cron_scheduler_enabled
        except (ImportError, ValueError):
            try:
                from .builtin_cron import is_cron_scheduler_enabled  # type: ignore
            except (ImportError, ValueError):
                from builtin_cron import is_cron_scheduler_enabled  # type: ignore
        if not is_cron_scheduler_enabled():
            _log.debug("Cron scheduler is disabled in config; skipping scanner spawn for '%s'", board_slug)
            return None
    except Exception as e:
        _log.debug("Scanner cron scheduler check failed: %s", e)

    local_hermes = Path.home() / ".local" / "bin" / "hermes"
    hermes_bin = (
        os.environ.get("HERMES_BIN")
        or shutil.which("hermes")
        or (str(local_hermes) if local_hermes.exists() else "hermes")
    )
    job_id = f"zero-factory-improvement-scanner-{board_slug}"
    # Check if this scanner job is paused/disabled before running
    try:
        try:
            from ..builtin_cron import list_builtin_jobs, get_target_jobs_files, load_jobs_from_file
        except (ImportError, ValueError):
            try:
                from .builtin_cron import list_builtin_jobs, get_target_jobs_files, load_jobs_from_file  # type: ignore
            except (ImportError, ValueError):
                from builtin_cron import list_builtin_jobs, get_target_jobs_files, load_jobs_from_file  # type: ignore
        for tf in get_target_jobs_files():
            if tf.exists():
                for j in load_jobs_from_file(tf):
                    if isinstance(j, dict) and j.get("id") == job_id:
                        if not j.get("enabled", True) or j.get("state") == "paused":
                            _log.debug("Scanner job '%s' is paused/disabled in %s; skipping spawn", job_id, tf)
                            return None
        all_jobs = list_builtin_jobs()
        job = next((j for j in all_jobs if j.get("id") == job_id), None)
        if job and not job.get("enabled", True):
            _log.debug("Scanner job '%s' is paused/disabled; skipping spawn for board '%s'", job_id, board_slug)
            return None
    except Exception as e:
        _log.debug("Scanner enabled check failed: %s", e)

    cmd = [hermes_bin, "-p", "zf-orchestrator", "cron", "run", job_id, "--accept-hooks"]

    log_dir = Path.home() / ".hermes" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file_path = log_dir / f"scanner_{board_slug}.log"

    env = os.environ.copy()
    env["HERMES_PROFILE"] = "zf-orchestrator"
    profile_home = Path.home() / ".hermes" / "profiles" / "zf-orchestrator"
    if profile_home.exists():
        env["HERMES_HOME"] = str(profile_home)
    env["PYTHONUNBUFFERED"] = "1"
    env["ZEROFACTORY_IDLE_SCAN"] = "1"
    _d()._inject_langfuse_env(env)

    workdir = str(repo_path) if repo_path and repo_path.exists() else os.getcwd()

    if repo_path and repo_path.is_dir():
        try:
            _d().sync_repo_main(repo_path)
        except Exception as e:
            _log.debug("Auto-pull before idle scanner spawn failed for '%s': %s", board_slug, e)

    try:
        log_f = open(log_file_path, "ab")
        proc = subprocess.Popen(
            cmd,
            cwd=workdir,
            stdin=subprocess.DEVNULL,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
        log_f.close()
        _active_scanners[board_slug] = proc
        _log.info("Spawned idle improvement scanner for board '%s' (PID: %d, cwd: %s)", board_slug, proc.pid, workdir)
        return proc.pid
    except Exception as e:
        _log.error("Failed to spawn idle improvement scanner for board '%s': %s", board_slug, e)
        return None


def reset_idle_scanner_state() -> None:
    """Reset scanner state tracking (useful for test isolation)."""
    _last_idle_scan_times.clear()
    for slug, proc in list(_active_scanners.items()):
        if proc is not None and proc.poll() is None:
            # Scanners are spawned with start_new_session=True; terminate the whole process group
            _d().terminate_process_group(proc, proc.pid)
    _active_scanners.clear()
