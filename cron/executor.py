"""Execution of builtin cron jobs via Hermes CLI or internal scheduler ticks."""

from __future__ import annotations

import logging
import os
import sqlite3
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import (
    CRON_RUN_OUTPUT_TAIL_CHARS,
    CRON_RUN_TIMEOUT,
    _active_cron_runs,
    _c,
    _log,
    get_db_path,
)
from .definitions import get_all_builtin_cron_jobs
from .manager import ensure_builtin_cron_jobs
from .scheduler_check import is_cron_scheduler_enabled


def trigger_builtin_job(job_id: str) -> Dict[str, Any]:
    """Immediately trigger an execution of a builtin job."""
    disp = _c()
    get_all_builtin_cron_jobs_fn = getattr(disp, "get_all_builtin_cron_jobs", get_all_builtin_cron_jobs)
    ensure_builtin_cron_jobs_fn = getattr(disp, "ensure_builtin_cron_jobs", ensure_builtin_cron_jobs)
    get_db_path_fn = getattr(disp, "get_db_path", get_db_path)
    sub_module = getattr(disp, "subprocess", subprocess)

    current_builtin_jobs = get_all_builtin_cron_jobs_fn()

    # Backwards compatibility: if someone triggers "zero-factory-improvement-scanner",
    # redirect to the first available board scanner job
    target_job_id = job_id
    if job_id not in current_builtin_jobs:
        if job_id == "zero-factory-improvement-scanner":
            scanner_jobs = [j for j in current_builtin_jobs if j.startswith("zero-factory-improvement-scanner-")]
            if scanner_jobs:
                target_job_id = scanner_jobs[0]
            else:
                return {"ok": False, "error": f"No active board scanner jobs found to execute: {job_id}"}
        else:
            return {"ok": False, "error": f"Unknown builtin job ID: {job_id}"}

    # Ensure job is registered in target files before running
    ensure_builtin_cron_jobs_fn()

    job_def = current_builtin_jobs.get(target_job_id) or {}
    if not job_def.get("no_agent", False):
        try:
            try:
                from .settings import load_settings
                from .dispatcher import _global_llm_occupancy, reap_active_scanners
            except ImportError:
                from settings import load_settings
                from dispatcher import _global_llm_occupancy, reap_active_scanners

            with sqlite3.connect(str(get_db_path_fn()), timeout=15) as conn:
                cap = load_settings(conn)["max_concurrent_llm_workers"]
                running = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'running'").fetchone()[0]
            reap_active_scanners()
            if _global_llm_occupancy(running) >= cap:
                return {"ok": False, "error": "Global concurrent LLM worker limit reached"}
        except (OSError, sqlite3.Error) as e:
            _log.warning("Cron capacity check failed: %s", e)
            return {"ok": False, "error": f"Cannot verify LLM worker capacity: {e}"}

    try:
        job_def = current_builtin_jobs.get(target_job_id) or {}
        profile = job_def.get("profile") or "zf-orchestrator"

        log_dir = Path.home() / ".hermes" / "logs"
        try:
            log_dir.mkdir(parents=True, exist_ok=True)
            log_file_path = log_dir / f"cron_run_{target_job_id}.log"
            log_handle = open(log_file_path, "ab")
            try:
                os.utime(log_file_path, None)
            except Exception:
                pass
        except Exception:
            log_file_path = None
            log_handle = None

        cmd = ["hermes", "-p", profile, "cron", "run", target_job_id, "--accept-hooks"]
        if log_handle is not None:
            stdout_dest: Any = log_handle
        else:
            stdout_dest = getattr(sub_module, "DEVNULL", subprocess.DEVNULL)

        proc = sub_module.Popen(
            cmd,
            stdin=subprocess.DEVNULL,
            stdout=stdout_dest,
            stderr=subprocess.STDOUT,
            start_new_session=True,
        )
        if log_handle is not None:
            log_handle.close()

        _active_cron_runs[target_job_id] = proc

        try:
            proc.wait(timeout=CRON_RUN_TIMEOUT)
        except subprocess.TimeoutExpired:
            _log.error("Cron job %s timed out after %ss; terminating", target_job_id, CRON_RUN_TIMEOUT)
            try:
                try:
                    from .dispatcher import terminate_process_group
                except ImportError:
                    from dispatcher import terminate_process_group  # type: ignore
                terminate_process_group(proc, proc.pid, grace=5.0)
            except Exception as term_exc:
                _log.warning("Group termination failed for cron job %s: %s", target_job_id, term_exc)
                proc.terminate()
                try:
                    proc.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    try:
                        proc.wait(timeout=5)
                    except Exception:
                        pass
            _active_cron_runs.pop(target_job_id, None)
            return {
                "ok": False,
                "job_id": target_job_id,
                "pid": proc.pid,
                "timed_out": True,
                "message": (
                    f"Cron job '{target_job_id}' (PID {proc.pid}) timed out after "
                    f"{CRON_RUN_TIMEOUT}s and was terminated"
                ),
            }

        _active_cron_runs.pop(target_job_id, None)

        returncode = proc.returncode
        if returncode == 0:
            _log.info("Cron job %s completed (PID: %d, rc=0)", target_job_id, proc.pid)
            return {
                "ok": True,
                "job_id": target_job_id,
                "pid": proc.pid,
                "returncode": returncode,
                "message": f"Cron job '{target_job_id}' completed successfully (exit 0)",
            }

        tail = ""
        if log_file_path is not None:
            try:
                with open(log_file_path, "rb") as lf:
                    raw = lf.read()[-CRON_RUN_OUTPUT_TAIL_CHARS:]
                tail = raw.decode("utf-8", errors="replace")
            except Exception:
                tail = ""
        _log.error("Cron job %s failed (PID: %d, rc=%s)", target_job_id, proc.pid, returncode)
        result: Dict[str, Any] = {
            "ok": False,
            "job_id": target_job_id,
            "pid": proc.pid,
            "returncode": returncode,
            "message": f"Cron job '{target_job_id}' exited with code {returncode}",
        }
        if tail:
            result["output_tail"] = tail
        return result
    except Exception as e:
        _active_cron_runs.pop(target_job_id, None)
        _log.error("Failed to run cron job %s: %s", target_job_id, e)
        return {"ok": False, "error": str(e)}


def tick_builtin_cron() -> int:
    """Safe periodic scheduler tick called by the background dispatcher daemon.

    Ticks the zf-orchestrator profile's cron store where Zero Factory jobs reside,
    ensuring scheduled jobs fire on time even when the external gateway is inactive.
    """
    disp = _c()
    is_cron_scheduler_enabled_fn = getattr(disp, "is_cron_scheduler_enabled", is_cron_scheduler_enabled)
    if not is_cron_scheduler_enabled_fn():
        _log.debug("[builtin_cron] Cron scheduler is disabled in config; skipping tick")
        return 0

    try:
        from .settings import load_settings
        from .dispatcher import _global_llm_occupancy, reap_active_scanners
    except ImportError:
        from settings import load_settings
        from dispatcher import _global_llm_occupancy, reap_active_scanners
    try:
        get_db_path_fn = getattr(disp, "get_db_path", get_db_path)
        with sqlite3.connect(str(get_db_path_fn()), timeout=5) as conn:
            cap = load_settings(conn)["max_concurrent_llm_workers"]
            running = conn.execute("SELECT COUNT(*) FROM tasks WHERE status = 'running'").fetchone()[0]
        reap_active_scanners()
        if _global_llm_occupancy(running) >= cap:
            _log.debug("[builtin_cron] Global LLM worker limit reached; deferring scheduled jobs")
            return 0
    except sqlite3.Error as e:
        _log.warning("[builtin_cron] Cannot verify LLM worker capacity: %s", e)
        return 0

    try:
        tick = None
        if "cron.scheduler" in sys.modules:
            sched_mod = sys.modules["cron.scheduler"]
            tick = getattr(sched_mod, "tick", None)

        if tick is None:
            hermes_agent_dir = Path(os.getenv("HERMES_AGENT_DIR", str(Path.home() / ".hermes" / "hermes-agent")))
            sched_py = hermes_agent_dir / "cron" / "scheduler.py"
            if sched_py.exists():
                import importlib.util
                spec = importlib.util.spec_from_file_location("hermes_cron_scheduler", sched_py)
                if spec and spec.loader:
                    mod = importlib.util.module_from_spec(spec)
                    spec.loader.exec_module(mod)
                    tick = getattr(mod, "tick", None)

        if tick is None:
            if str(hermes_agent_dir) not in sys.path:
                sys.path.insert(0, str(hermes_agent_dir))
            from cron.scheduler import tick  # type: ignore

        orch_profile_dir = Path.home() / ".hermes" / "profiles" / "zf-orchestrator"
        if orch_profile_dir.is_dir():
            try:
                from hermes_constants import set_hermes_home_override, reset_hermes_home_override
                token = set_hermes_home_override(str(orch_profile_dir))
                try:
                    executed = tick(verbose=False)
                    if executed:
                        _log.info("[builtin_cron] Scheduler tick fired %s due job(s)", executed)
                    return executed or 0
                finally:
                    reset_hermes_home_override(token)
            except ImportError:
                pass

        executed = tick(verbose=False)
        if executed:
            _log.info("[builtin_cron] Scheduler tick fired %s due job(s)", executed)
        return executed or 0
    except Exception as e:
        _log.debug("[builtin_cron] Tick skipped or yielded: %s", e)
        return 0
