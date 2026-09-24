"""Scheduler enablement inspection and persistence across environments and settings."""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import _c, _log, get_db_path
from .definitions import get_all_builtin_cron_jobs
from .store import get_target_jobs_files, load_jobs_from_file, save_jobs_to_file


def is_cron_scheduler_enabled(conn_or_cursor: Any = None) -> bool:
    """Return True if the cron scheduler is enabled across env, settings table, and config.yaml.

    Resolution precedence:
    1. Environment variables:
       - ZEROFACTORY_ENABLE_CRON_SCHEDULER ('0'/'false'/'no' -> False, '1'/'true'/'yes' -> True)
       - ZEROFACTORY_DISABLE_CRON_SCHEDULER ('1'/'true'/'yes' -> False)
       - HERMES_CRON_ENABLED ('0'/'false'/'no' -> False)
    2. Zero Factory global settings table (if DB accessible):
       - 'enable_cron_scheduler': bool
    3. Hermes config.yaml (root ~/.hermes/config.yaml or active profile config.yaml):
       - cron.enabled == False -> False
       - cron.scheduler == False -> False
       - cron.scheduler.enabled == False -> False
       - cron == False -> False
       - plugins.entries.zerofactory.cron_scheduler == False -> False
       - plugins.entries.zerofactory.enable_cron_scheduler == False -> False
    4. Default: True
    """
    disp = _c()
    # Check if this function itself was monkeypatched on the facade
    custom_fn = getattr(disp, "is_cron_scheduler_enabled", None)
    if custom_fn and custom_fn is not is_cron_scheduler_enabled:
        return custom_fn(conn_or_cursor)

    # 1. Environment variable check
    env_enable = os.environ.get("ZEROFACTORY_ENABLE_CRON_SCHEDULER")
    if env_enable is not None:
        return env_enable.strip().lower() in ("true", "1", "yes")

    env_disable = os.environ.get("ZEROFACTORY_DISABLE_CRON_SCHEDULER")
    if env_disable is not None and env_disable.strip().lower() in ("true", "1", "yes"):
        return False

    hermes_cron_enable = os.environ.get("HERMES_CRON_ENABLED")
    if hermes_cron_enable is not None and hermes_cron_enable.strip().lower() in ("false", "0", "no"):
        return False

    # 2. Zero Factory global settings table check
    try:
        try:
            from .settings import load_settings
        except ImportError:
            from settings import load_settings  # type: ignore

        if conn_or_cursor is not None:
            db_settings = load_settings(conn_or_cursor)
            if not db_settings.get("enable_cron_scheduler", True):
                return False
        else:
            get_db_path_fn = getattr(disp, "get_db_path", get_db_path)
            db_path = get_db_path_fn()
            if db_path.exists():
                with sqlite3.connect(str(db_path), timeout=2.0) as conn:
                    conn.row_factory = sqlite3.Row
                    db_settings = load_settings(conn)
                    if not db_settings.get("enable_cron_scheduler", True):
                        return False
    except Exception as e:
        _log.debug("Failed reading settings table for cron scheduler check: %s", e)

    # 3. Hermes config.yaml check
    try:
        import yaml
        search_configs: List[Path] = []

        config_override = os.environ.get("HERMES_CONFIG_FILE") or os.environ.get("ZEROFACTORY_CONFIG_FILE")
        if config_override:
            search_configs.append(Path(config_override))

        hermes_home = os.environ.get("HERMES_HOME")
        if hermes_home:
            search_configs.append(Path(hermes_home) / "config.yaml")

        active_prof = os.environ.get("HERMES_PROFILE")
        if active_prof:
            search_configs.append(Path.home() / ".hermes" / "profiles" / active_prof / "config.yaml")

        search_configs.append(Path.home() / ".hermes" / "profiles" / "zf-orchestrator" / "config.yaml")
        search_configs.append(Path.home() / ".hermes" / "config.yaml")

        for cfg_path in search_configs:
            if not cfg_path.exists():
                continue
            try:
                with open(cfg_path, "r", encoding="utf-8") as f:
                    cfg = yaml.safe_load(f)
                if not isinstance(cfg, dict):
                    continue

                # Check plugins.entries.zerofactory.[enable_]cron_scheduler
                zf_entry = (
                    cfg.get("plugins", {})
                    .get("entries", {})
                    .get("zerofactory", {})
                    if isinstance(cfg.get("plugins"), dict) and isinstance(cfg.get("plugins", {}).get("entries"), dict)
                    else {}
                )
                if isinstance(zf_entry, dict):
                    if zf_entry.get("cron_scheduler") is False or zf_entry.get("enable_cron_scheduler") is False:
                        return False

                # Check top-level cron configuration
                if "cron" in cfg:
                    cron_val = cfg["cron"]
                    if cron_val is False:
                        return False
                    if isinstance(cron_val, dict):
                        if cron_val.get("enabled") is False:
                            return False
                        sched_val = cron_val.get("scheduler")
                        if sched_val is False:
                            return False
                        if isinstance(sched_val, dict) and sched_val.get("enabled") is False:
                            return False
            except Exception as e:
                _log.debug("Failed checking config file %s for cron settings: %s", cfg_path, e)
    except Exception as e:
        _log.debug("YAML parser unavailable or error inspecting config.yaml: %s", e)

    return True


def set_cron_scheduler_enabled(enabled: bool, conn: Optional[Any] = None) -> Dict[str, Any]:
    """Persist the scheduler enabled state to database settings and synchronize all jobs files."""
    disp = _c()
    get_db_path_fn = getattr(disp, "get_db_path", get_db_path)
    get_target_jobs_files_fn = getattr(disp, "get_target_jobs_files", get_target_jobs_files)
    load_jobs_from_file_fn = getattr(disp, "load_jobs_from_file", load_jobs_from_file)
    save_jobs_to_file_fn = getattr(disp, "save_jobs_to_file", save_jobs_to_file)
    get_all_builtin_cron_jobs_fn = getattr(disp, "get_all_builtin_cron_jobs", get_all_builtin_cron_jobs)

    db_path = get_db_path_fn()
    val = "true" if enabled else "false"
    now = int(time.time())

    if conn is not None:
        conn.execute(
            "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('enable_cron_scheduler', ?, ?)",
            (val, now)
        )
        conn.commit()
    elif db_path.exists():
        with sqlite3.connect(str(db_path), timeout=10.0) as c:
            c.execute(
                "INSERT OR REPLACE INTO settings (key, value, updated_at) VALUES ('enable_cron_scheduler', ?, ?)",
                (val, now)
            )
            c.commit()

    target_files = get_target_jobs_files_fn()
    updated_targets = 0
    current_builtin_jobs = get_all_builtin_cron_jobs_fn()

    for target in target_files:
        if not target.exists():
            continue
        jobs = load_jobs_from_file_fn(target)
        changed = False
        has_any_paused_by_master = any(j.get("paused_by_master") for j in jobs if isinstance(j, dict))
        for j in jobs:
            if not isinstance(j, dict):
                continue
            jid = j.get("id", "")
            is_zf_job = j.get("origin") == "zerofactory" or jid.startswith("zero-factory-") or jid in current_builtin_jobs
            if not is_zf_job:
                continue

            if not enabled:
                # Disabling scheduler -> pause active Zero Factory jobs
                if j.get("enabled", True) or j.get("state") != "paused":
                    j["enabled"] = False
                    j["state"] = "paused"
                    j["paused_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                    j["paused_by_master"] = True
                    j["custom_config"] = True
                    changed = True
            else:
                # Enabling scheduler -> resume jobs paused by master (or all if none tagged)
                if j.get("paused_by_master") or not has_any_paused_by_master:
                    j["enabled"] = True
                    j["state"] = "scheduled"
                    j["paused_at"] = None
                    j.pop("paused_by_master", None)
                    changed = True

        if changed:
            if save_jobs_to_file_fn(target, jobs):
                updated_targets += 1

    if not enabled:
        try:
            try:
                from .dispatcher import reset_idle_scanner_state
            except ImportError:
                from dispatcher import reset_idle_scanner_state  # type: ignore
            reset_idle_scanner_state()
        except Exception as e:
            _log.debug("Failed resetting scanner state on scheduler pause: %s", e)

    return {"ok": True, "scheduler_enabled": enabled, "updated_targets": updated_targets}
