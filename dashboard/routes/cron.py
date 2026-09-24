"""Zero Factory Dashboard — Built-in Cron routes (/cron)."""

from __future__ import annotations

import logging
import sqlite3
import sys
from pathlib import Path
from typing import Optional

_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)
_DASHBOARD_ROOT = str(Path(__file__).resolve().parent.parent)
if _DASHBOARD_ROOT not in sys.path:
    sys.path.insert(0, _DASHBOARD_ROOT)

from fastapi import APIRouter, HTTPException

try:
    from ..db import get_db_path, init_db
    from ..models import CronJobUpdate, CronToggleRequest
    from .boards import _get_cron_helpers
except (ImportError, ValueError):
    from db import get_db_path, init_db  # type: ignore
    from models import CronJobUpdate, CronToggleRequest  # type: ignore
    try:
        from routes.boards import _get_cron_helpers  # type: ignore
    except (ImportError, ValueError):
        from boards import _get_cron_helpers  # type: ignore

_log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/cron")
def get_builtin_cron_jobs():
    """List all built-in Zero Factory cron jobs and their current runtime status."""
    helpers = _get_cron_helpers()
    ensure_cron = helpers[0] if len(helpers) > 0 else None
    list_cron = helpers[3] if len(helpers) > 3 else None
    scheduler_enabled = True
    try:
        from ...builtin_cron import is_cron_scheduler_enabled
        scheduler_enabled = is_cron_scheduler_enabled()
    except Exception:
        try:
            from builtin_cron import is_cron_scheduler_enabled  # type: ignore
            scheduler_enabled = is_cron_scheduler_enabled()
        except Exception:
            pass

    if not list_cron:
        return {"ok": False, "error": "Builtin cron engine not available", "jobs": [], "count": 0, "scheduler_enabled": scheduler_enabled}
    if ensure_cron:
        try:
            ensure_cron()
        except Exception:
            pass
    jobs = list_cron()
    return {"ok": True, "jobs": jobs, "count": len(jobs), "scheduler_enabled": scheduler_enabled}


@router.post("/cron/scheduler/toggle")
@router.put("/cron/scheduler/toggle")
def toggle_cron_scheduler(req: Optional[CronToggleRequest] = None):
    """Toggle the periodic background cron scheduler on or off."""
    init_db()
    db_p = get_db_path()
    try:
        from ...builtin_cron import is_cron_scheduler_enabled, set_cron_scheduler_enabled
    except (ImportError, ValueError):
        from builtin_cron import is_cron_scheduler_enabled, set_cron_scheduler_enabled  # type: ignore
    with sqlite3.connect(str(db_p), timeout=10.0) as conn:
        current = is_cron_scheduler_enabled(conn)
        target = req.enabled if (req and req.enabled is not None) else not current
        res = set_cron_scheduler_enabled(target, conn=conn)
        conn.commit()
    return {"ok": True, "scheduler_enabled": target, "updated_targets": res.get("updated_targets", 0)}


@router.post("/cron/sync")
def sync_builtin_cron_jobs():
    """Ensure all built-in Zero Factory cron jobs are registered and synchronized."""
    helpers = _get_cron_helpers()
    ensure_cron = helpers[0] if len(helpers) > 0 else None
    if not ensure_cron:
        raise HTTPException(status_code=500, detail="Builtin cron engine not available")
    return ensure_cron()


@router.post("/cron/{job_id}/run")
def run_builtin_cron_job(job_id: str):
    """Trigger an immediate run of a built-in Zero Factory cron job."""
    helpers = _get_cron_helpers()
    trigger_cron = helpers[2] if len(helpers) > 2 else None
    if not trigger_cron:
        raise HTTPException(status_code=500, detail="Builtin cron engine not available")
    return trigger_cron(job_id)


@router.put("/cron/{job_id}")
@router.post("/cron/{job_id}")
def update_builtin_cron_job(job_id: str, req: CronJobUpdate):
    """Update schedule, enabled state, prompt, model, or workdir of a builtin cron job."""
    helpers = _get_cron_helpers()
    update_cron = helpers[4] if len(helpers) > 4 else None
    if not update_cron:
        raise HTTPException(status_code=500, detail="Builtin cron engine not available")
    update_data = req.model_dump(exclude_unset=True) if hasattr(req, "model_dump") else req.dict(exclude_unset=True)
    res = update_cron(job_id, update_data)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Update failed"))
    return res


@router.post("/cron/{job_id}/toggle")
@router.put("/cron/{job_id}/toggle")
def toggle_builtin_cron_job(
    job_id: str,
    req: Optional[CronToggleRequest] = None,
    enabled: Optional[bool] = None
):
    """Toggle a builtin cron job between enabled and paused."""
    helpers = _get_cron_helpers()
    toggle_cron = helpers[5] if len(helpers) > 5 else None
    if not toggle_cron:
        raise HTTPException(status_code=500, detail="Builtin cron engine not available")
    target_enabled = req.enabled if (req and req.enabled is not None) else enabled
    res = toggle_cron(job_id, target_enabled)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Toggle failed"))
    return res


@router.post("/cron/{job_id}/reset")
@router.put("/cron/{job_id}/reset")
def reset_builtin_cron_job(job_id: str):
    """Reset a builtin cron job to its canonical default configuration."""
    helpers = _get_cron_helpers()
    reset_cron = helpers[6] if len(helpers) > 6 else None
    if not reset_cron:
        raise HTTPException(status_code=500, detail="Builtin cron engine not available")
    res = reset_cron(job_id)
    if not res.get("ok"):
        raise HTTPException(status_code=400, detail=res.get("error", "Reset failed"))
    return res
