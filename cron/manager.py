"""Management, registration, synchronization, and updates for builtin cron jobs."""

from __future__ import annotations

import logging
import os
import sqlite3
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import _c, _log, get_db_path
from .definitions import get_all_builtin_cron_jobs
from .scheduler_check import is_cron_scheduler_enabled
from .store import (
    cleanup_duplicate_root_jobs,
    compute_job_next_run,
    get_target_jobs_files,
    load_jobs_from_file,
    save_jobs_to_file,
)


def ensure_builtin_cron_jobs() -> Dict[str, Any]:
    """Ensure all builtin Zero Factory cron jobs are registered and up-to-date."""
    disp = _c()
    custom_ensure = getattr(disp, "ensure_builtin_cron_jobs", None)
    if custom_ensure and custom_ensure is not ensure_builtin_cron_jobs:
        return custom_ensure()

    if os.environ.get("ZEROFACTORY_SKIP_CRON_SYNC"):
        return {"ok": True, "synced_targets": [], "added": 0, "updated": 0, "pruned": 0}

    # Automatically deploy scripts to ~/.hermes/scripts/ before registering jobs
    try:
        from profile_manager import ensure_script_files
        ensure_script_files()
    except Exception as e:
        _log.debug("Script sync in ensure_builtin_cron_jobs skipped: %s", e)

    get_db_path_fn = getattr(disp, "get_db_path", get_db_path)
    get_all_builtin_cron_jobs_fn = getattr(disp, "get_all_builtin_cron_jobs", get_all_builtin_cron_jobs)
    cleanup_duplicate_root_jobs_fn = getattr(disp, "cleanup_duplicate_root_jobs", cleanup_duplicate_root_jobs)
    get_target_jobs_files_fn = getattr(disp, "get_target_jobs_files", get_target_jobs_files)
    load_jobs_from_file_fn = getattr(disp, "load_jobs_from_file", load_jobs_from_file)
    save_jobs_to_file_fn = getattr(disp, "save_jobs_to_file", save_jobs_to_file)
    compute_job_next_run_fn = getattr(disp, "compute_job_next_run", compute_job_next_run)
    is_cron_scheduler_enabled_fn = getattr(disp, "is_cron_scheduler_enabled", is_cron_scheduler_enabled)

    # Active board slugs currently registered in the database
    active_board_slugs = set()
    db_path = get_db_path_fn()
    if db_path.exists():
        try:
            with sqlite3.connect(str(db_path), timeout=5.0) as conn:
                conn.row_factory = sqlite3.Row
                cur = conn.cursor()
                cur.execute("SELECT slug FROM boards")
                active_board_slugs = {row["slug"] for row in cur.fetchall() if row["slug"]}
        except Exception as e:
            _log.warning("Failed to query board slugs for cron pruning: %s", e)

    # Refresh all builtin jobs from DB and env
    current_builtin_jobs = get_all_builtin_cron_jobs_fn()

    # Ensure no duplicates in root ~/.hermes/cron/jobs.json
    cleanup_duplicate_root_jobs_fn()

    synced_targets = []
    total_added = 0
    total_updated = 0
    total_pruned = 0

    for target in get_target_jobs_files_fn():
        existing_jobs = load_jobs_from_file_fn(target)
        initial_count = len(existing_jobs)

        # 1. Prune obsolete Zero Factory jobs (e.g. monolithic scanner, deleted board scanners, or test boards)
        pruned_jobs = []
        for j in existing_jobs:
            if not isinstance(j, dict):
                continue
            jid = str(j.get("id", ""))

            # Explicit check: If it is an improvement scanner job, prune if slug is not an active board
            if jid.startswith("zero-factory-improvement-scanner-"):
                board_slug = jid[len("zero-factory-improvement-scanner-"):]
                if board_slug not in active_board_slugs:
                    continue

            # Prune any Zero Factory job not in active definitions
            is_zf_job = (
                j.get("origin") == "zerofactory"
                or jid.startswith("zero-factory-")
            )
            if is_zf_job and jid not in current_builtin_jobs:
                continue

            pruned_jobs.append(j)

        pruned_here = initial_count - len(pruned_jobs)
        total_pruned += pruned_here
        existing_jobs = pruned_jobs
        existing_by_id = {j.get("id"): j for j in existing_jobs if isinstance(j, dict) and j.get("id")}

        added_here = 0
        updated_here = 0

        # 2. Add or update active builtin jobs
        for job_id, builtin_def in current_builtin_jobs.items():
            if job_id not in existing_by_id:
                # Add new job
                new_job = dict(builtin_def)
                new_job["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                if not new_job.get("next_run_at") and new_job.get("enabled", True):
                    new_job["next_run_at"] = compute_job_next_run_fn(new_job.get("schedule", {}))
                existing_jobs.append(new_job)
                added_here += 1
            else:
                # Update prompts, schedule, provider, model, base_url, workdir, script, no_agent if drifted
                curr = existing_by_id[job_id]
                changed = False
                is_custom = bool(curr.get("custom_config"))
                for field in (
                    "name", "prompt", "schedule", "schedule_display",
                    "enabled_toolsets", "origin", "model", "provider", "base_url", "workdir",
                    "script", "no_agent", "context_from", "continuity"
                ):
                    if is_custom and field in ("name", "schedule", "schedule_display", "prompt", "model", "provider", "base_url", "workdir", "script", "no_agent", "context_from", "continuity"):
                        continue
                    if curr.get(field) != builtin_def.get(field):
                        curr[field] = builtin_def.get(field)
                        changed = True

                # Re-activate any scanner job that was retired as a one-shot completed job (only if scheduler enabled)
                # Note: NEVER re-activate "paused" jobs here — if a job is paused, it was disabled by configuration or user.
                if curr.get("state") == "completed" and not is_custom and is_cron_scheduler_enabled_fn():
                    curr["state"] = "scheduled"
                    curr["enabled"] = True
                    curr["paused_at"] = None
                    curr["paused_reason"] = None
                    changed = True

                # Ensure next_run_at is populated for active scheduled jobs
                sched = curr.get("schedule", builtin_def.get("schedule", {}))
                if curr.get("enabled", True) and not curr.get("next_run_at"):
                    curr["next_run_at"] = compute_job_next_run_fn(sched, curr.get("last_run_at"))
                    changed = True

                # Unblock job if it was previously blocked by preflight credential missing
                if (
                    curr.get("last_status") == "blocked_config"
                    or (curr.get("last_error") and "[blocked_config]" in str(curr.get("last_error")))
                ):
                    curr["last_status"] = None
                    curr["last_error"] = None
                    curr["state"] = "scheduled"
                    curr["preflight_alerted"] = False
                    curr["failure_streak"] = 0
                    changed = True

                if changed:
                    updated_here += 1

        if added_here > 0 or updated_here > 0 or pruned_here > 0 or not target.exists():
            save_jobs_to_file_fn(target, existing_jobs)
        synced_targets.append(str(target))
        total_added += added_here
        total_updated += updated_here

    return {
        "ok": True,
        "synced_targets": synced_targets,
        "added": total_added,
        "updated": total_updated,
        "pruned": total_pruned,
        "job_ids": list(current_builtin_jobs.keys())
    }


def prune_board_cron_job(slug: str) -> None:
    """Explicitly remove any improvement scanner cron job for a given board slug from all cron stores."""
    disp = _c()
    get_target_jobs_files_fn = getattr(disp, "get_target_jobs_files", get_target_jobs_files)
    load_jobs_from_file_fn = getattr(disp, "load_jobs_from_file", load_jobs_from_file)
    save_jobs_to_file_fn = getattr(disp, "save_jobs_to_file", save_jobs_to_file)

    job_id = f"zero-factory-improvement-scanner-{slug}"
    for target in get_target_jobs_files_fn():
        if not target.exists():
            continue
        jobs = load_jobs_from_file_fn(target)
        initial_len = len(jobs)
        filtered = [j for j in jobs if isinstance(j, dict) and j.get("id") != job_id]
        if len(filtered) != initial_len:
            save_jobs_to_file_fn(target, filtered)
            _log.info("Pruned scanner cron job %s from %s", job_id, target)


def list_builtin_jobs() -> List[Dict[str, Any]]:
    """Return the current configuration and runtime status of builtin jobs."""
    disp = _c()
    get_all_builtin_cron_jobs_fn = getattr(disp, "get_all_builtin_cron_jobs", get_all_builtin_cron_jobs)
    get_target_jobs_files_fn = getattr(disp, "get_target_jobs_files", get_target_jobs_files)
    load_jobs_from_file_fn = getattr(disp, "load_jobs_from_file", load_jobs_from_file)

    current_builtin_jobs = get_all_builtin_cron_jobs_fn()
    target_files = get_target_jobs_files_fn()
    existing_by_id = {}
    for t in target_files:
        if t.exists():
            for j in load_jobs_from_file_fn(t):
                if isinstance(j, dict) and j.get("id") in current_builtin_jobs and j.get("id") not in existing_by_id:
                    existing_by_id[j["id"]] = j

    results = []
    for job_id, builtin_def in current_builtin_jobs.items():
        curr = existing_by_id.get(job_id, builtin_def)
        results.append({
            "id": job_id,
            "name": curr.get("name", builtin_def.get("name")),
            "schedule": curr.get("schedule", builtin_def.get("schedule")),
            "schedule_display": curr.get("schedule_display") or curr.get("schedule", {}).get("display", "configured"),
            "enabled": curr.get("enabled", True),
            "state": curr.get("state", "scheduled"),
            "prompt": curr.get("prompt", builtin_def.get("prompt")),
            "model": curr.get("model", builtin_def.get("model")),
            "provider": curr.get("provider", builtin_def.get("provider")),
            "base_url": curr.get("base_url", builtin_def.get("base_url")),
            "workdir": curr.get("workdir", builtin_def.get("workdir")),
            "profile": curr.get("profile", builtin_def.get("profile", "zf-orchestrator")),
            "script": curr.get("script", builtin_def.get("script")),
            "no_agent": bool(curr.get("no_agent", builtin_def.get("no_agent", False))),
            "context_from": curr.get("context_from", builtin_def.get("context_from")),
            "continuity": bool(curr.get("continuity", builtin_def.get("continuity", False))),
            "custom_config": bool(curr.get("custom_config")),
            "last_status": curr.get("last_status"),
            "last_run_at": curr.get("last_run_at"),
            "next_run_at": curr.get("next_run_at"),
            "last_error": curr.get("last_error")
        })
    return results


def _apply_job_field_updates(job: Dict[str, Any], updates: Dict[str, Any]) -> None:
    """Apply user-supplied field updates to a single jobs.json entry, in place."""
    # Enabled / State toggle
    if "enabled" in updates:
        is_enabled = bool(updates["enabled"])
        job["enabled"] = is_enabled
        job["state"] = "scheduled" if is_enabled else "paused"
        if not is_enabled:
            job["paused_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
        else:
            job["paused_at"] = None
        job["custom_config"] = True

    # Schedule updates
    if "minutes" in updates and updates["minutes"]:
        try:
            m = int(updates["minutes"])
            if m > 0:
                job["schedule"] = {"kind": "interval", "minutes": m, "display": f"every {m}m"}
                job["schedule_display"] = f"every {m}m"
                job["custom_config"] = True
        except (ValueError, TypeError):
            pass
    elif "cron_expr" in updates and updates["cron_expr"]:
        expr = str(updates["cron_expr"]).strip()
        if expr:
            job["schedule"] = {"kind": "cron", "expr": expr, "display": expr}
            job["schedule_display"] = expr
            job["custom_config"] = True
    elif "schedule" in updates and isinstance(updates["schedule"], dict):
        job["schedule"] = updates["schedule"]
        job["schedule_display"] = updates.get("schedule_display") or updates["schedule"].get("display", "configured")
        job["custom_config"] = True

    # Model / workdir / prompt updates
    if "model" in updates and updates["model"] is not None:
        job["model"] = str(updates["model"]).strip() or None
        job["custom_config"] = True
    if "workdir" in updates and updates["workdir"] is not None:
        job["workdir"] = str(updates["workdir"]).strip() or None
        job["custom_config"] = True
    if "prompt" in updates and updates["prompt"] is not None:
        job["prompt"] = str(updates["prompt"])
        job["custom_config"] = True
    if "name" in updates and updates["name"]:
        job["name"] = str(updates["name"])
        job["custom_config"] = True
    if "script" in updates:
        job["script"] = str(updates["script"]).strip() if updates["script"] else None
        job["custom_config"] = True
    if "no_agent" in updates:
        job["no_agent"] = bool(updates["no_agent"])
        job["custom_config"] = True
    if "context_from" in updates:
        cf = updates["context_from"]
        if isinstance(cf, str):
            cf = [cf]
        job["context_from"] = [str(x).strip() for x in cf if str(x).strip()] if cf else None
        job["custom_config"] = True
    if "continuity" in updates:
        job["continuity"] = bool(updates["continuity"])
        job["custom_config"] = True


def update_builtin_job(job_id: str, updates: Dict[str, Any]) -> Dict[str, Any]:
    """Update a builtin job configuration across all target cron store files."""
    disp = _c()
    get_all_builtin_cron_jobs_fn = getattr(disp, "get_all_builtin_cron_jobs", get_all_builtin_cron_jobs)
    get_target_jobs_files_fn = getattr(disp, "get_target_jobs_files", get_target_jobs_files)
    load_jobs_from_file_fn = getattr(disp, "load_jobs_from_file", load_jobs_from_file)
    save_jobs_to_file_fn = getattr(disp, "save_jobs_to_file", save_jobs_to_file)

    current_builtin_jobs = get_all_builtin_cron_jobs_fn()
    if job_id not in current_builtin_jobs:
        if job_id.startswith("zero-factory-improvement-scanner-"):
            slug = job_id.replace("zero-factory-improvement-scanner-", "")
            builtin_def = {
                "id": job_id,
                "name": f"Zero Factory improvement scanner ({slug})",
                "schedule": {"kind": "interval", "minutes": 10080, "display": "on idle (active < 2)"},
                "schedule_display": "on idle (active < 2)",
                "enabled": True,
                "state": "scheduled",
                "custom_config": True
            }
        else:
            return {"ok": False, "error": f"Unknown builtin job ID: {job_id}"}
    else:
        builtin_def = current_builtin_jobs[job_id]

    target_files = get_target_jobs_files_fn()
    updated_count = 0
    updated_job_data = None

    for target in target_files:
        jobs = load_jobs_from_file_fn(target) if target.exists() else []
        found = False
        for j in jobs:
            if isinstance(j, dict) and j.get("id") == job_id:
                found = True
                _apply_job_field_updates(j, updates)
                updated_job_data = dict(j)
                break

        if not found:
            # If job not in this target yet, instantiate from builtin_def and apply updates
            new_job = dict(builtin_def)
            new_job["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
            _apply_job_field_updates(new_job, updates)
            jobs.append(new_job)
            updated_job_data = dict(new_job)

        if save_jobs_to_file_fn(target, jobs):
            updated_count += 1

    return {"ok": True, "job_id": job_id, "updated_targets": updated_count, "job": updated_job_data}


def toggle_builtin_job(job_id: str, enabled: Optional[bool] = None) -> Dict[str, Any]:
    """Toggle a builtin job between enabled (scheduled) and disabled (paused)."""
    disp = _c()
    custom_toggle = getattr(disp, "toggle_builtin_job", None)
    if custom_toggle and custom_toggle is not toggle_builtin_job:
        return custom_toggle(job_id, enabled)

    list_builtin_jobs_fn = getattr(disp, "list_builtin_jobs", list_builtin_jobs)
    update_builtin_job_fn = getattr(disp, "update_builtin_job", update_builtin_job)

    current_jobs = list_builtin_jobs_fn()
    target = next((j for j in current_jobs if j["id"] == job_id), None)
    if not target:
        return {"ok": False, "error": f"Unknown builtin job ID: {job_id}"}

    new_enabled = not target["enabled"] if enabled is None else bool(enabled)
    return update_builtin_job_fn(job_id, {"enabled": new_enabled})


def reset_builtin_job(job_id: str) -> Dict[str, Any]:
    """Reset a builtin job back to canonical default definition, clearing custom_config."""
    disp = _c()
    get_all_builtin_cron_jobs_fn = getattr(disp, "get_all_builtin_cron_jobs", get_all_builtin_cron_jobs)
    get_target_jobs_files_fn = getattr(disp, "get_target_jobs_files", get_target_jobs_files)
    load_jobs_from_file_fn = getattr(disp, "load_jobs_from_file", load_jobs_from_file)
    save_jobs_to_file_fn = getattr(disp, "save_jobs_to_file", save_jobs_to_file)

    current_builtin_jobs = get_all_builtin_cron_jobs_fn()
    if job_id not in current_builtin_jobs:
        return {"ok": False, "error": f"Unknown builtin job ID: {job_id}"}

    builtin_def = current_builtin_jobs[job_id]
    target_files = get_target_jobs_files_fn()
    reset_count = 0

    for target in target_files:
        if not target.exists():
            continue
        jobs = load_jobs_from_file_fn(target)
        for j in jobs:
            if isinstance(j, dict) and j.get("id") == job_id:
                for k in ("schedule", "schedule_display", "model", "provider", "base_url", "prompt", "workdir", "name", "script", "no_agent", "context_from", "continuity"):
                    j[k] = builtin_def.get(k)
                j["enabled"] = builtin_def.get("enabled", True)
                j["state"] = "scheduled" if j["enabled"] else "paused"
                j["paused_at"] = None
                j["custom_config"] = False
                reset_count += 1
                break
        save_jobs_to_file_fn(target, jobs)

    return {"ok": True, "job_id": job_id, "reset_targets": reset_count}
