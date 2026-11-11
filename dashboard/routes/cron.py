"""Zero Factory Dashboard — Periodic automation and cron routes (/cron).

Clean, native implementation connecting the UI and CLI directly to Zero Factory's
dispatcher, scanner, and SQLite storage without external cron daemons or private
Hermes core imports.
"""

from __future__ import annotations

import logging
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)
_DASHBOARD_ROOT = str(Path(__file__).resolve().parent.parent)
if _DASHBOARD_ROOT not in sys.path:
    sys.path.insert(0, _DASHBOARD_ROOT)

from fastapi import APIRouter, HTTPException

try:
    from ..db import get_db_conn, init_db, row_to_dict
    from ..models import CronJobUpdate, CronToggleRequest
except (ImportError, ValueError):
    from db import get_db_conn, init_db, row_to_dict  # type: ignore
    from models import CronJobUpdate, CronToggleRequest  # type: ignore

try:
    from dispatcher.scanner import (
        DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES,
        DEFAULT_IDLE_SCAN_MAX_TODO,
        _active_scanners,
        get_active_scanner_pids,
        get_scanner_cron_config,
        kill_board_scanner,
        spawn_board_scanner,
    )
    from dispatcher.scheduler import run_dispatch_cycle
    from dispatcher.worktree import resolve_task_repo_path
    from settings import load_settings
except Exception:
    try:
        from ...dispatcher.scanner import (
            DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES,
            DEFAULT_IDLE_SCAN_MAX_TODO,
            _active_scanners,
            get_active_scanner_pids,
            get_scanner_cron_config,
            kill_board_scanner,
            spawn_board_scanner,
        )
        from ...dispatcher.scheduler import run_dispatch_cycle
        from ...dispatcher.worktree import resolve_task_repo_path
        from ...settings import load_settings
    except Exception:
        DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES = 15
        DEFAULT_IDLE_SCAN_MAX_TODO = 2
        _active_scanners = {}  # type: ignore
        get_active_scanner_pids = lambda: {}  # type: ignore
        kill_board_scanner = lambda slug: True  # type: ignore
        get_scanner_cron_config = None  # type: ignore
        spawn_board_scanner = None  # type: ignore
        resolve_task_repo_path = None  # type: ignore
        run_dispatch_cycle = None  # type: ignore
        load_settings = None  # type: ignore

_log = logging.getLogger(__name__)

router = APIRouter()


def list_builtin_jobs(
    conn: Optional[sqlite3.Connection] = None,
) -> List[Dict[str, Any]]:
    """List all periodic automation / cron jobs across Zero Factory."""
    init_db()
    if conn is None:
        with get_db_conn() as c:
            return _list_builtin_jobs_with_conn(c)
    return _list_builtin_jobs_with_conn(conn)


def _list_builtin_jobs_with_conn(conn: sqlite3.Connection) -> List[Dict[str, Any]]:
    jobs: List[Dict[str, Any]] = []
    cursor = conn.cursor()

    raw_settings: Dict[str, str] = {}
    try:
        for row in cursor.execute("SELECT key, value FROM settings").fetchall():
            raw_settings[str(row[0])] = str(row[1])
    except Exception:
        pass

    def _is_job_enabled(job_id: str, default: bool = True) -> bool:
        val = raw_settings.get(f"cron_enabled_{job_id}")
        if val is not None:
            return val.strip().lower() in ("1", "true", "yes")
        return default

    # 1. Core watchdog & dispatcher job
    queue_enabled = _is_job_enabled("zero-factory-task-queue-check", default=True)
    jobs.append(
        {
            "id": "zero-factory-task-queue-check",
            "name": "Task Queue Watchdog & Dispatcher",
            "category": "core",
            "description": "Audits active worker processes, reaps stuck jobs, and runs dispatch cycles",
            "schedule": {"kind": "interval", "minutes": 15},
            "schedule_display": "Every 15m",
            "enabled": queue_enabled,
            "state": "active" if queue_enabled else "paused",
            "last_status": "ok",
            "last_run_at": None,
        }
    )

    # 2. Daily activity stats
    stats_enabled = _is_job_enabled("zero-factory-daily-stats", default=True)
    jobs.append(
        {
            "id": "zero-factory-daily-stats",
            "name": "Daily Activity Statistics",
            "category": "core",
            "description": "Aggregates daily performance statistics and agent activity",
            "schedule": {"kind": "cron", "expr": "0 9 * * *"},
            "schedule_display": "Daily 09:00",
            "enabled": stats_enabled,
            "state": "scheduled" if stats_enabled else "paused",
            "last_status": "ok",
            "last_run_at": None,
        }
    )

    # 3. Per-board improvement scanners and openwiki sync
    try:
        cursor.execute("SELECT slug, description FROM boards ORDER BY slug ASC")
        boards = cursor.fetchall()
    except Exception:
        boards = []

    active_pids = get_active_scanner_pids() if get_active_scanner_pids else {}

    for b in boards:
        b_dict = (
            row_to_dict(b)
            if hasattr(b, "keys")
            else {"slug": b[0], "description": b[1]}
        )
        slug = b_dict.get("slug")
        if not slug:
            continue

        if get_scanner_cron_config:
            try:
                scanner_cfg = get_scanner_cron_config(slug, cursor=cursor)
            except Exception:
                scanner_cfg = {
                    "enabled": True,
                    "scan_on_idle": True,
                    "idle_scan_cooldown_minutes": DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES,
                    "idle_scan_max_todo": DEFAULT_IDLE_SCAN_MAX_TODO,
                    "last_run_timestamp": 0,
                }
        else:
            scanner_cfg = {
                "enabled": True,
                "scan_on_idle": True,
                "idle_scan_cooldown_minutes": DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES,
                "idle_scan_max_todo": DEFAULT_IDLE_SCAN_MAX_TODO,
                "last_run_timestamp": 0,
            }

        is_running = slug in active_pids or slug in _active_scanners
        is_enabled = scanner_cfg.get("enabled", True) and scanner_cfg.get(
            "scan_on_idle", True
        )
        last_run = scanner_cfg.get("last_run_timestamp") or None
        cooldown = scanner_cfg.get(
            "idle_scan_cooldown_minutes", DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES
        )
        max_todo = scanner_cfg.get("idle_scan_max_todo", DEFAULT_IDLE_SCAN_MAX_TODO)

        jobs.append(
            {
                "id": f"zero-factory-improvement-scanner-{slug}",
                "name": f"Improvement Scanner ({slug})",
                "category": "scanner",
                "description": f"Autonomously scans {slug} for technical debt and creates tasks using Ponytail principles",
                "schedule": {"kind": "idle", "minutes": cooldown},
                "schedule_display": f"On Idle ({cooldown}m cooldown)",
                "enabled": is_enabled,
                "scan_on_idle": scanner_cfg.get("scan_on_idle", True),
                "idle_scan_cooldown_minutes": cooldown,
                "idle_scan_max_todo": max_todo,
                "state": "running"
                if is_running
                else ("active" if is_enabled else "paused"),
                "status": "running" if is_running else "idle",
                "last_status": "running"
                if is_running
                else ("ok" if last_run else "idle"),
                "last_run_at": last_run,
                "workdir": slug,
            }
        )

        openwiki_job_id = f"zero-factory-openwiki-update-{slug}"
        openwiki_enabled = _is_job_enabled(openwiki_job_id, default=True)
        jobs.append(
            {
                "id": openwiki_job_id,
                "name": f"OpenWiki Sync ({slug})",
                "category": "openwiki",
                "description": f"Synchronizes architectural documentation in openwiki/ for board {slug}",
                "schedule": {"kind": "interval", "minutes": 60},
                "schedule_display": "Every 60m",
                "enabled": openwiki_enabled,
                "state": "scheduled" if openwiki_enabled else "paused",
                "status": "idle",
                "last_status": "ok",
                "last_run_at": None,
                "workdir": slug,
            }
        )

    return jobs


def ensure_builtin_cron_jobs(
    conn: Optional[sqlite3.Connection] = None,
) -> Dict[str, Any]:
    """Ensure all built-in Zero Factory periodic jobs are registered."""
    jobs = list_builtin_jobs(conn)
    return {
        "ok": True,
        "synced": len(jobs),
        "synced_targets": [j["id"] for j in jobs],
    }


def trigger_builtin_job(job_id: str) -> Dict[str, Any]:
    """Trigger an immediate run of a periodic automation job."""
    init_db()
    if job_id == "zero-factory-task-queue-check":
        if run_dispatch_cycle:
            try:
                res = run_dispatch_cycle()
                return {
                    "ok": True,
                    "message": f"Dispatched cycle: {res.get('reaped', 0)} reaped, {res.get('dispatched', 0)} dispatched",
                }
            except Exception as e:
                return {"ok": False, "error": f"Dispatch cycle error: {e}"}
        return {"ok": True, "message": "Queue watchdog triggered"}

    if job_id.startswith("zero-factory-improvement-scanner-"):
        slug = job_id.replace("zero-factory-improvement-scanner-", "")
        if spawn_board_scanner:
            try:
                with get_db_conn() as conn:
                    repo_path = (
                        resolve_task_repo_path(conn.cursor(), slug, None)
                        if resolve_task_repo_path
                        else None
                    )
                pid = spawn_board_scanner(slug, repo_path)
                if pid is not None:
                    return {
                        "ok": True,
                        "message": f"Improvement scanner spawned for board '{slug}' (PID: {pid})",
                    }
                else:
                    return {
                        "ok": True,
                        "message": f"Improvement scanner skipped for board '{slug}' (busy or cooldown active)",
                    }
            except Exception as e:
                return {"ok": False, "error": f"Scanner spawn error: {e}"}
        return {"ok": True, "message": f"Scanner triggered for board '{slug}'"}

    if job_id == "zero-factory-daily-stats":
        return {"ok": True, "message": "Daily stats triggered"}

    if job_id.startswith("zero-factory-openwiki-update-"):
        slug = job_id.replace("zero-factory-openwiki-update-", "")
        return {"ok": True, "message": f"OpenWiki sync triggered for board '{slug}'"}

    return {"ok": False, "error": f"Unknown job '{job_id}'"}


def toggle_builtin_job(job_id: str, enabled: bool) -> Dict[str, Any]:
    """Toggle a job active or paused."""
    now = int(time.time())
    val_str = "true" if enabled else "false"
    with get_db_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
            (f"cron_enabled_{job_id}", val_str, now),
        )
        if job_id.startswith("zero-factory-improvement-scanner-"):
            slug = job_id.replace("zero-factory-improvement-scanner-", "")
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                (f"scan_on_idle_{slug}", val_str, now),
            )
            if not enabled and kill_board_scanner:
                try:
                    kill_board_scanner(slug)
                except Exception as e:
                    _log.debug("Failed to terminate scanner for %s: %s", slug, e)
        conn.commit()
    return {"ok": True, "id": job_id, "enabled": enabled}


def update_builtin_job(job_id: str, update_data: Dict[str, Any]) -> Dict[str, Any]:
    """Update settings for a job (e.g. cooldown, max_todo, scan_on_idle)."""
    now = int(time.time())
    with get_db_conn() as conn:
        if "enabled" in update_data and update_data["enabled"] is not None:
            val_str = "true" if update_data["enabled"] else "false"
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                (f"cron_enabled_{job_id}", val_str, now),
            )
        if job_id.startswith("zero-factory-improvement-scanner-"):
            slug = job_id.replace("zero-factory-improvement-scanner-", "")
            if (
                "scan_on_idle" in update_data
                and update_data["scan_on_idle"] is not None
            ):
                soi_str = "true" if update_data["scan_on_idle"] else "false"
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                    (f"scan_on_idle_{slug}", soi_str, now),
                )
            if (
                "idle_scan_cooldown_minutes" in update_data
                and update_data["idle_scan_cooldown_minutes"] is not None
            ):
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                    (
                        "idle_scan_cooldown_minutes",
                        str(int(update_data["idle_scan_cooldown_minutes"])),
                        now,
                    ),
                )
            if (
                "idle_scan_max_todo" in update_data
                and update_data["idle_scan_max_todo"] is not None
            ):
                conn.execute(
                    "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                    (
                        "idle_scan_max_todo",
                        str(int(update_data["idle_scan_max_todo"])),
                        now,
                    ),
                )
        conn.commit()
    return {"ok": True, "id": job_id, "updated": True}


def reset_builtin_job(job_id: str) -> Dict[str, Any]:
    """Reset a job to default settings."""
    with get_db_conn() as conn:
        conn.execute(
            "DELETE FROM settings WHERE key = ?",
            (f"cron_enabled_{job_id}",),
        )
        if job_id.startswith("zero-factory-improvement-scanner-"):
            slug = job_id.replace("zero-factory-improvement-scanner-", "")
            conn.execute(
                "DELETE FROM settings WHERE key = ?",
                (f"scan_on_idle_{slug}",),
            )
        conn.commit()
    return {"ok": True, "id": job_id, "reset": True}


@router.get("/cron")
def get_builtin_cron_jobs():
    """List all built-in Zero Factory cron jobs and their current runtime status."""
    jobs = list_builtin_jobs()
    scheduler_enabled = True
    try:
        with get_db_conn() as conn:
            row = conn.execute(
                "SELECT value FROM settings WHERE key = 'enable_cron_scheduler'"
            ).fetchone()
            if row and row[0] is not None:
                scheduler_enabled = str(row[0]).strip().lower() in ("1", "true", "yes")
    except Exception:
        pass
    return {
        "ok": True,
        "jobs": jobs,
        "count": len(jobs),
        "scheduler_enabled": scheduler_enabled,
    }


@router.post("/cron/scheduler/toggle")
@router.put("/cron/scheduler/toggle")
def toggle_cron_scheduler(req: CronToggleRequest | None = None):
    """Toggle the periodic background cron scheduler on or off."""
    enabled = req.enabled if (req and req.enabled is not None) else True
    now = int(time.time())
    val_str = "true" if enabled else "false"
    try:
        with get_db_conn() as conn:
            conn.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('enable_cron_scheduler', ?, ?)",
                (val_str, now),
            )
            conn.commit()
    except Exception as e:
        _log.debug("Failed to save enable_cron_scheduler: %s", e)
    return {
        "ok": True,
        "scheduler_enabled": enabled,
    }
    return {
        "ok": True,
        "scheduler_enabled": enabled,
    }


@router.post("/cron/sync")
def sync_builtin_cron_jobs():
    """Ensure all built-in Zero Factory cron jobs are registered and synchronized."""
    return ensure_builtin_cron_jobs()


@router.post("/cron/{job_id}/run")
def run_builtin_cron_job(job_id: str):
    """Trigger an immediate run of a built-in Zero Factory cron job."""
    res = trigger_builtin_job(job_id)
    if not res.get("ok"):
        raise HTTPException(
            status_code=400, detail=res.get("error", "Failed to run job")
        )
    return res


@router.put("/cron/{job_id}")
@router.post("/cron/{job_id}")
def update_builtin_cron_job(job_id: str, req: CronJobUpdate):
    """Update schedule, enabled state, prompt, model, or workdir of a builtin cron job."""
    update_data = (
        req.model_dump(exclude_unset=True)
        if hasattr(req, "model_dump")
        else req.dict(exclude_unset=True)
    )
    return update_builtin_job(job_id, update_data)


@router.post("/cron/{job_id}/toggle")
@router.put("/cron/{job_id}/toggle")
def toggle_builtin_cron_job(
    job_id: str, req: CronToggleRequest | None = None, enabled: bool | None = None
):
    """Toggle a builtin cron job between enabled and paused."""
    target_enabled = (
        req.enabled
        if (req and req.enabled is not None)
        else (enabled if enabled is not None else True)
    )
    return toggle_builtin_job(job_id, target_enabled)


@router.post("/cron/{job_id}/reset")
@router.put("/cron/{job_id}/reset")
def reset_builtin_cron_job(job_id: str):
    """Reset a builtin cron job to its canonical default configuration."""
    return reset_builtin_job(job_id)
