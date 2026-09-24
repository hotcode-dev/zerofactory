"""Storage, loading, saving, and target file resolution for cron jobs."""

from __future__ import annotations

import json
import logging
import os
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import _c, _log
from .definitions import get_all_builtin_cron_jobs


def compute_job_next_run(schedule: Dict[str, Any], last_run_at: Optional[str] = None) -> Optional[str]:
    """Compute ISO next_run_at timestamp for a cron job schedule."""
    disp = _c()
    custom_fn = getattr(disp, "compute_job_next_run", None)
    if custom_fn and custom_fn is not compute_job_next_run:
        return custom_fn(schedule, last_run_at=last_run_at)

    try:
        hermes_agent_dir = Path(os.getenv("HERMES_AGENT_DIR", str(Path.home() / ".hermes" / "hermes-agent")))
        jobs_py = hermes_agent_dir / "cron" / "jobs.py"
        if jobs_py.exists():
            import importlib.util
            spec = importlib.util.spec_from_file_location("hermes_cron_jobs", jobs_py)
            if spec and spec.loader:
                mod = importlib.util.module_from_spec(spec)
                spec.loader.exec_module(mod)
                if hasattr(mod, "compute_next_run"):
                    return mod.compute_next_run(schedule, last_run_at=last_run_at)
    except Exception:
        pass

    kind = schedule.get("kind") if isinstance(schedule, dict) else None
    if kind == "interval":
        minutes = schedule.get("minutes", 60)
        from datetime import datetime, timezone, timedelta
        return (datetime.now(timezone.utc) + timedelta(minutes=minutes)).isoformat()
    elif kind == "cron":
        from datetime import datetime, timezone, timedelta
        return (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
    return None


def cleanup_duplicate_root_jobs() -> None:
    """Ensure root ~/.hermes/cron/jobs.json does not contain duplicate Zero Factory jobs.

    The Hermes dashboard aggregates jobs across all profiles (profile=all).
    If jobs are written to both the profile store and the root (default) store,
    they appear duplicated in the UI (e.g. 6 jobs instead of 3).
    """
    disp = _c()
    custom_fn = getattr(disp, "cleanup_duplicate_root_jobs", None)
    if custom_fn and custom_fn is not cleanup_duplicate_root_jobs:
        return custom_fn()

    load_jobs_fn = getattr(disp, "load_jobs_from_file", load_jobs_from_file)
    save_jobs_fn = getattr(disp, "save_jobs_to_file", save_jobs_to_file)
    get_jobs_fn = getattr(disp, "get_all_builtin_cron_jobs", get_all_builtin_cron_jobs)

    try:
        hermes_root = Path(os.path.expanduser("~/.hermes"))
        root_jobs_file = hermes_root / "cron" / "jobs.json"
        if root_jobs_file.exists():
            existing = load_jobs_fn(root_jobs_file)
            current_ids = set(get_jobs_fn().keys())
            filtered = [
                j for j in existing
                if isinstance(j, dict) and not (
                    j.get("id") in current_ids or
                    str(j.get("id", "")).startswith("zero-factory-") or
                    j.get("origin") == "zerofactory"
                )
            ]
            if len(filtered) != len(existing):
                save_jobs_fn(root_jobs_file, filtered)
                _log.info("Cleaned %d duplicate Zero Factory job(s) from root cron store", len(existing) - len(filtered))
    except Exception as e:
        _log.warning("Failed to cleanup duplicate jobs from root store: %s", e)


def get_target_jobs_files() -> List[Path]:
    """Resolve all locations where jobs.json should be synced.

    Targets:
    1. Explicit ZEROFACTORY_CRON_JOBS_FILE environment override (if set)
    2. Active profile jobs.json (if active and not default)
    3. ZF Orchestrator profile jobs.json in ~/.hermes/profiles/zf-orchestrator
    """
    disp = _c()
    custom_fn = getattr(disp, "get_target_jobs_files", None)
    if custom_fn and custom_fn is not get_target_jobs_files:
        return custom_fn()

    env_target = os.environ.get("ZEROFACTORY_CRON_JOBS_FILE")
    if env_target:
        return [Path(env_target)]

    # Safeguard: If ZEROFACTORY_DB points to a custom or test database (not ~/.hermes/zerofactory.db),
    # never pollute the live ~/.hermes profile unless explicitly requested via ZEROFACTORY_CRON_JOBS_FILE.
    custom_db = os.environ.get("ZEROFACTORY_DB")
    default_db = Path.home() / ".hermes" / "zerofactory.db"
    if custom_db:
        try:
            if Path(custom_db).resolve() != default_db.resolve():
                return []
        except Exception:
            return []

    files: List[Path] = []
    hermes_root = Path(os.path.expanduser("~/.hermes"))

    # 1. Active profile jobs.json
    active_profile_file = hermes_root / "active_profile"
    if active_profile_file.exists():
        try:
            profile_name = active_profile_file.read_text(encoding="utf-8").strip()
            if profile_name and profile_name != "default":
                profile_jobs = hermes_root / "profiles" / profile_name / "cron" / "jobs.json"
                files.append(profile_jobs)
        except Exception:
            pass

    # 2. ZF Orchestrator profile jobs.json (canonical Zero Factory profile)
    zf_orch_jobs = hermes_root / "profiles" / "zf-orchestrator" / "cron" / "jobs.json"
    if zf_orch_jobs not in files:
        files.append(zf_orch_jobs)

    return files


def load_jobs_from_file(jobs_file: Path) -> List[Dict[str, Any]]:
    """Load jobs from a given JSON file safely."""
    disp = _c()
    custom_fn = getattr(disp, "load_jobs_from_file", None)
    if custom_fn and custom_fn is not load_jobs_from_file:
        return custom_fn(jobs_file)

    if not jobs_file.exists() or jobs_file.stat().st_size == 0:
        return []
    try:
        with open(jobs_file, "r", encoding="utf-8") as f:
            data = json.load(f)
            if isinstance(data, dict):
                return data.get("jobs", [])
            elif isinstance(data, list):
                return data
    except Exception as e:
        _log.warning("Failed to load jobs from %s: %s", jobs_file, e)
    return []


def save_jobs_to_file(jobs_file: Path, jobs: List[Dict[str, Any]]) -> bool:
    """Save jobs atomically to a JSON file."""
    disp = _c()
    custom_fn = getattr(disp, "save_jobs_to_file", None)
    if custom_fn and custom_fn is not save_jobs_to_file:
        return custom_fn(jobs_file, jobs)

    try:
        jobs_file.parent.mkdir(parents=True, exist_ok=True)
        payload = {"jobs": jobs}
        temp_fd, temp_path = tempfile.mkstemp(dir=str(jobs_file.parent), prefix="jobs_", suffix=".tmp")
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            json.dump(payload, f, indent=2, ensure_ascii=False)
        os.replace(temp_path, str(jobs_file))
        return True
    except Exception as e:
        _log.error("Failed to write jobs to %s: %s", jobs_file, e)
        return False
