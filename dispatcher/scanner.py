"""Board scanner spawning, tracking, and capacity-based occupancy calculations."""

from __future__ import annotations

import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Any

from .config import (
    DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES,
    DEFAULT_IDLE_SCAN_MAX_TODO,
    _active_scanners,
    _last_idle_scan_times,
    _log,
)
from .git_ops import sync_repo_main
from .process_manager import (
    build_shell_wrapper,
    cleanup_process_artifacts,
    get_exit_file_path,
    get_process_exit_code,
    is_pid_alive,
    terminate_process_group,
)
from .worker_spawner import _inject_langfuse_env


def get_active_scanner_pids() -> dict[str, int]:
    """Return mapping of board_slug -> active scanner PID across all processes."""
    active: dict[str, int] = {}
    logs_dir = Path.home() / ".hermes" / "logs"
    if logs_dir.exists():
        for pf in logs_dir.glob("scanner_*.pid"):
            slug = pf.stem.replace("scanner_", "")
            try:
                pid = int(pf.read_text().strip())
                if is_pid_alive(pid):
                    active[slug] = pid
                else:
                    pf.unlink(missing_ok=True)
            except Exception:
                pf.unlink(missing_ok=True)
    for slug, proc in list(_active_scanners.items()):
        if proc is not None and proc.poll() is None and is_pid_alive(proc.pid):
            active[slug] = proc.pid
    return active


def kill_board_scanner(board_slug: str) -> bool:
    """Terminate any active scanner process for board_slug."""
    proc = _active_scanners.pop(board_slug, None)
    if proc is not None and proc.poll() is None:
        try:
            terminate_process_group(proc, proc.pid)
        except Exception:
            pass
    logs_dir = Path.home() / ".hermes" / "logs"
    pid_file = logs_dir / f"scanner_{board_slug}.pid"
    if pid_file.exists():
        try:
            pid = int(pid_file.read_text().strip())
            if is_pid_alive(pid):
                try:
                    import signal

                    os.killpg(os.getpgid(pid), signal.SIGTERM)
                except Exception:
                    try:
                        import signal

                        os.kill(pid, signal.SIGTERM)
                    except Exception:
                        pass
        except Exception:
            pass
        pid_file.unlink(missing_ok=True)
    cleanup_process_artifacts(f"scanner_{board_slug}")
    return True


def reap_active_scanners() -> int:
    """Clean up finished or exited scanner worker processes."""
    reaped = 0
    logs_dir = Path.home() / ".hermes" / "logs"
    for slug, proc in list(_active_scanners.items()):
        task_ref = f"scanner_{slug}"
        exit_code = get_process_exit_code(task_ref)
        proc_done = proc is not None and proc.poll() is not None
        if proc_done or exit_code is not None:
            _active_scanners.pop(slug, None)
            cleanup_process_artifacts(task_ref)
            pid_file = logs_dir / f"scanner_{slug}.pid"
            pid_file.unlink(missing_ok=True)
            reaped += 1
            code = exit_code if exit_code is not None else (proc.poll() if proc else 0)
            _log.debug("Scanner process for board '%s' exited with code %s", slug, code)

    # Also reap dead PID files from other processes
    if logs_dir.exists():
        for pf in logs_dir.glob("scanner_*.pid"):
            slug = pf.stem.replace("scanner_", "")
            if slug not in _active_scanners:
                try:
                    pid = int(pf.read_text().strip())
                    if not is_pid_alive(pid):
                        pf.unlink(missing_ok=True)
                        cleanup_process_artifacts(f"scanner_{slug}")
                        reaped += 1
                except Exception:
                    pf.unlink(missing_ok=True)
    return reaped


def _running_cron_llm_jobs() -> int:
    """Obsolete stub: custom cron subsystem removed; returns 0."""
    return 0


def _global_llm_occupancy(running_tasks: int) -> int:
    """LLM workers currently tracked across all Zero Factory processes."""
    return running_tasks + len(get_active_scanner_pids())


def get_scanner_cron_config(board_slug: str, cursor: Any = None) -> dict[str, Any]:
    """Retrieve scanner configuration for a board slug from settings or environment defaults."""
    raw_settings: dict[str, Any] = {}
    if cursor is not None:
        try:
            for row in cursor.execute("SELECT key, value FROM settings").fetchall():
                raw_settings[str(row[0])] = str(row[1])
        except Exception:
            pass
    else:
        try:
            from .config import get_db_path

            db_p = get_db_path()
            if db_p.exists():
                import sqlite3

                with sqlite3.connect(str(db_p)) as conn:
                    for row in conn.execute(
                        "SELECT key, value FROM settings"
                    ).fetchall():
                        raw_settings[str(row[0])] = str(row[1])
        except Exception:
            pass

    is_board_disabled = (
        raw_settings.get(
            f"cron_enabled_zero-factory-improvement-scanner-{board_slug}", "true"
        )
        .strip()
        .lower()
        in ("0", "false", "no")
        or raw_settings.get(f"scan_on_idle_{board_slug}", "true").strip().lower()
        in ("0", "false", "no")
        or raw_settings.get("scan_on_idle", "true").strip().lower()
        in ("0", "false", "no")
    )
    scan_on_idle = not is_board_disabled
    env_soi = os.environ.get("ZEROFACTORY_SCAN_ON_IDLE")
    if env_soi is not None:
        scan_on_idle = env_soi.strip().lower() in ("1", "true", "yes")

    return {
        "enabled": scan_on_idle,
        "scan_on_idle": scan_on_idle,
        "idle_scan_cooldown_minutes": int(
            raw_settings.get(
                "idle_scan_cooldown_minutes", DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES
            )
        ),
        "idle_scan_max_todo": int(
            raw_settings.get("idle_scan_max_todo", DEFAULT_IDLE_SCAN_MAX_TODO)
        ),
        "last_run_timestamp": _last_idle_scan_times.get(board_slug, 0),
    }


def spawn_board_scanner(board_slug: str, repo_path: Path | None = None) -> int | None:
    """Spawn an improvement scanner agent worker process for a specific board."""
    if os.environ.get("ZEROFACTORY_SKIP_WORKER_SPAWN") or os.environ.get(
        "ZEROFACTORY_SKIP_SCANNER_SPAWN"
    ):
        return None

    # Cross-process duplicate prevention check
    active_pids = get_active_scanner_pids()
    if board_slug in active_pids:
        _log.debug(
            "Scanner already active for board '%s' (PID: %d); skipping spawn",
            board_slug,
            active_pids[board_slug],
        )
        return None

    cron_cfg = get_scanner_cron_config(board_slug)
    if not cron_cfg.get("scan_on_idle"):
        _log.debug(
            "Idle scanning disabled; skipping scanner spawn for '%s'", board_slug
        )
        return None

    local_hermes = Path.home() / ".local" / "bin" / "hermes"
    hermes_bin = (
        os.environ.get("HERMES_BIN")
        or shutil.which("hermes")
        or (str(local_hermes) if local_hermes.exists() else "hermes")
    )

    prompt = (
        f"Scan repository for board '{board_slug}' for improvements and "
        "technical debt following Ponytail ladder of laziness."
    )
    cmd = [
        hermes_bin,
        "-p",
        "zf-orchestrator",
        "--yolo",
        "--cli",
        "--accept-hooks",
        "chat",
        "-q",
        prompt,
    ]

    task_ref = f"scanner_{board_slug}"
    exit_file = get_exit_file_path(task_ref)
    if exit_file.exists():
        exit_file.unlink(missing_ok=True)
    wrapped_cmd = build_shell_wrapper(cmd, exit_file)

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
    env["ZEROFACTORY_DISABLE_DISPATCHER"] = "1"
    _inject_langfuse_env(env)

    workdir = str(repo_path) if repo_path and repo_path.exists() else os.getcwd()

    if repo_path and repo_path.is_dir():
        try:
            sync_repo_main(repo_path)
        except Exception as e:
            _log.debug(
                "Auto-pull before idle scanner spawn failed for '%s': %s",
                board_slug,
                e,
            )

    try:
        log_f = open(log_file_path, "ab")
        proc = subprocess.Popen(
            wrapped_cmd,
            cwd=workdir,
            stdin=subprocess.DEVNULL,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
        log_f.close()
        pid_file = log_dir / f"scanner_{board_slug}.pid"
        try:
            pid_file.write_text(str(proc.pid))
        except Exception as pe:
            _log.debug("Failed to write scanner pid file for %s: %s", board_slug, pe)
        _active_scanners[board_slug] = proc
        _last_idle_scan_times[board_slug] = int(time.time())
        _log.info(
            "Spawned idle improvement scanner for board '%s' (PID: %d, cwd: %s)",
            board_slug,
            proc.pid,
            workdir,
        )
        return proc.pid
    except Exception as e:
        _log.error(
            "Failed to spawn idle improvement scanner for board '%s': %s",
            board_slug,
            e,
        )
        return None


def reset_idle_scanner_state() -> None:
    """Reset scanner state tracking (useful for test isolation)."""
    _last_idle_scan_times.clear()
    for slug, proc in list(_active_scanners.items()):
        if proc is not None and proc.poll() is None:
            terminate_process_group(proc, proc.pid)
        cleanup_process_artifacts(f"scanner_{slug}")
    logs_dir = Path.home() / ".hermes" / "logs"
    if logs_dir.exists():
        for pf in logs_dir.glob("scanner_*.pid"):
            pf.unlink(missing_ok=True)
    _active_scanners.clear()
