"""Zero Factory Dashboard — Global Settings & Langfuse Routes (/settings)."""

from __future__ import annotations

import base64
import logging
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any, Dict, Optional

_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)
_DASHBOARD_ROOT = str(Path(__file__).resolve().parent.parent)
if _DASHBOARD_ROOT not in sys.path:
    sys.path.insert(0, _DASHBOARD_ROOT)

from fastapi import APIRouter

try:
    from ...settings import load_settings  # type: ignore
except (ImportError, ValueError):
    from settings import load_settings  # type: ignore

try:
    from ...profile_manager import sync_langfuse_profiles  # type: ignore
except (ImportError, ValueError):
    try:
        from profile_manager import sync_langfuse_profiles  # type: ignore
    except (ImportError, ValueError):
        sync_langfuse_profiles = None  # type: ignore

try:
    from ..db import get_db_conn
    from ..models import LangfuseTestRequest, SettingsUpdate
except (ImportError, ValueError):
    from db import get_db_conn  # type: ignore
    from models import LangfuseTestRequest, SettingsUpdate  # type: ignore

_log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/settings")
def get_settings():
    """Retrieve global Zero Factory settings."""
    with get_db_conn() as conn:
        settings = load_settings(conn)
    return {"ok": True, "settings": settings}


@router.patch("/settings")
@router.put("/settings")
def update_settings(req: SettingsUpdate):
    """Update global Zero Factory settings."""
    now = int(time.time())
    with get_db_conn() as conn:
        cursor = conn.cursor()
        if req.max_active_tasks is not None:
            val = str(max(1, int(req.max_active_tasks)))
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('max_active_tasks', ?, ?)",
                (val, now)
            )
        if req.max_concurrent_llm_workers is not None:
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('max_concurrent_llm_workers', ?, ?)",
                (str(req.max_concurrent_llm_workers), now)
            )
        if req.scan_on_idle is not None:
            val = "true" if req.scan_on_idle else "false"
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('scan_on_idle', ?, ?)",
                (val, now)
            )
        if req.idle_scan_active_threshold is not None:
            val = str(max(1, int(req.idle_scan_active_threshold)))
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('idle_scan_active_threshold', ?, ?)",
                (val, now)
            )
        if req.idle_scan_cooldown_minutes is not None:
            val = str(max(1, int(req.idle_scan_cooldown_minutes)))
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('idle_scan_cooldown_minutes', ?, ?)",
                (val, now)
            )
        if req.idle_scan_max_todo is not None:
            val = str(max(0, int(req.idle_scan_max_todo)))
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('idle_scan_max_todo', ?, ?)",
                (val, now)
            )
        if req.activity_retention_days is not None:
            val = str(max(1, int(req.activity_retention_days)))
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('activity_retention_days', ?, ?)",
                (val, now)
            )
        if req.enable_cron_scheduler is not None:
            try:
                from ..builtin_cron import set_cron_scheduler_enabled
            except (ImportError, ValueError):
                try:
                    from ...builtin_cron import set_cron_scheduler_enabled  # type: ignore
                except (ImportError, ValueError):
                    from builtin_cron import set_cron_scheduler_enabled  # type: ignore
            set_cron_scheduler_enabled(bool(req.enable_cron_scheduler), conn=conn)
        if req.langfuse_enabled is not None:
            val = "true" if req.langfuse_enabled else "false"
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('langfuse_enabled', ?, ?)",
                (val, now)
            )
        if req.langfuse_base_url is not None:
            val = str(req.langfuse_base_url).strip()
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('langfuse_base_url', ?, ?)",
                (val, now)
            )
        if req.langfuse_public_key is not None:
            val = str(req.langfuse_public_key).strip()
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('langfuse_public_key', ?, ?)",
                (val, now)
            )
        if req.langfuse_secret_key is not None:
            val = str(req.langfuse_secret_key).strip()
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('langfuse_secret_key', ?, ?)",
                (val, now)
            )
        if req.langfuse_capture_mode is not None:
            val = str(req.langfuse_capture_mode).strip().lower()
            if val in ("sanitized", "metadata", "full"):
                cursor.execute(
                    "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('langfuse_capture_mode', ?, ?)",
                    (val, now)
                )
        if req.langfuse_env is not None:
            val = str(req.langfuse_env).strip()
            if val:
                cursor.execute(
                    "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('langfuse_env', ?, ?)",
                    (val, now)
                )
        if req.auto_record_memory is not None:
            val = "true" if req.auto_record_memory else "false"
            cursor.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('auto_record_memory', ?, ?)",
                (val, now)
            )
        conn.commit()

    res = get_settings()
    current_settings = res.get("settings", {})
    if any(getattr(req, k) is not None for k in (
        "langfuse_enabled", "langfuse_base_url", "langfuse_public_key",
        "langfuse_secret_key", "langfuse_capture_mode", "langfuse_env"
    )):
        if callable(sync_langfuse_profiles):
            try:
                sync_langfuse_profiles(current_settings)
            except Exception as e:
                _log.warning("Could not sync Langfuse across profiles: %s", e)

    return res


@router.post("/settings/langfuse/test")
def test_langfuse_connection(req: LangfuseTestRequest):
    """Test connection to Langfuse server and optionally validate API keys."""
    base_url = (req.base_url or "").strip().rstrip("/")
    if not base_url:
        base_url = "https://cloud.langfuse.com"
    if not (base_url.startswith("http://") or base_url.startswith("https://")):
        base_url = "https://" + base_url

    public_key = (req.public_key or "").strip()
    secret_key = (req.secret_key or "").strip()

    health_url = f"{base_url}/api/public/health"
    status_code = None
    try:
        req_obj = urllib.request.Request(
            health_url,
            headers={"User-Agent": "ZeroFactory/1.0", "Accept": "application/json"}
        )
        with urllib.request.urlopen(req_obj, timeout=6.0) as resp:
            status_code = resp.status
    except urllib.error.HTTPError as e:
        status_code = e.code
    except Exception as e:
        return {
            "ok": False,
            "error": f"Failed to connect to Langfuse host at {base_url}: {e}"
        }

    if public_key or secret_key:
        if not public_key.startswith("pk-lf-") or not secret_key.startswith("sk-lf-"):
            return {
                "ok": False,
                "error": "Invalid key format: public key must start with 'pk-lf-' and secret key with 'sk-lf-'"
            }

        auth_url = f"{base_url}/api/public/projects"
        auth_header = base64.b64encode(f"{public_key}:{secret_key}".encode("utf-8")).decode("ascii")
        try:
            auth_req = urllib.request.Request(
                auth_url,
                headers={
                    "Authorization": f"Basic {auth_header}",
                    "User-Agent": "ZeroFactory/1.0",
                    "Accept": "application/json"
                }
            )
            with urllib.request.urlopen(auth_req, timeout=6.0) as resp:
                if resp.status in (200, 201):
                    return {
                        "ok": True,
                        "message": f"Successfully connected and authenticated with Langfuse ({base_url})!"
                    }
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                return {
                    "ok": False,
                    "error": f"Authentication failed (HTTP {e.code}): Check that your public and secret keys are correct."
                }
            if status_code in (200, 204):
                return {
                    "ok": True,
                    "message": f"Server reached at {base_url} (HTTP {e.code} on auth check)."
                }
            return {
                "ok": False,
                "error": f"Langfuse server returned HTTP {e.code}: {e.reason}"
            }
        except Exception as e:
            return {
                "ok": False,
                "error": f"Error during auth check to {base_url}: {e}"
            }

    if status_code in (200, 204):
        return {
            "ok": True,
            "message": f"Langfuse server is healthy and reachable at {base_url}."
        }
    return {
        "ok": False,
        "error": f"Unexpected health status {status_code} from {base_url}."
    }
