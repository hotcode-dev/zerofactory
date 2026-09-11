"""Built-in Cron Engine for Zero Factory Kanban.

Natively embeds and orchestrates all Zero Factory periodic automation:
1. zero-factory-task-queue-check (every 120m)
2. zero-factory-daily-report (0 9 * * *)
3. zero-factory-improvement-scanner (every 60m, strict board-only scope)

Automatically synchronizes with the active Hermes profile's cron store and
allows background ticking and on-demand execution.
"""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_log = logging.getLogger("zerofactory_kanban.cron")

# Canonical Zero Factory Job Definitions
IMPROVEMENT_SCANNER_PROMPT = """Scan ZeroFactory workspaces for code quality issues, tech debt, and improvement opportunities.

## Discover target projects (STRICT BOARD-ONLY SCOPE):
1. **Check Zero Factory Kanban Boards** — Query all active boards from `~/.hermes/zerofactory_kanban.db` by running:
   `sqlite3 ~/.hermes/zerofactory_kanban.db "SELECT slug, name, description, git_url FROM boards;"`
   - **EDGE CASE**: If this query returns 0 rows, STOP IMMEDIATELY. Do NOT check ~/git. Output: "No active projects to scan. Waiting for new work." and finish.
2. **Find Git URLs** — Read the `git_url` (or fallback to URL in `description`) of each board to identify its remote Git repository.
3. **Locate ONLY the board's repository** — For each active board found, locate ONLY its specific local workspace in `~/git` (e.g., `~/git/<owner>/<repo>` or `~/git/<repo>`). If the repository does not exist locally, clone it from the board's `git_url` into `~/git/<repo>`.
4. **STRICT ISOLATION CONSTRAINT**:
   - ONLY scan repositories that have an active board in `~/.hermes/zerofactory_kanban.db`.
   - **NEVER** scan, inspect, read, or list other repositories or folders in `~/git` (such as other directories in `~/git/hotcode-dev/*`, `~/git/ntsd/*`, or `~/git/*`, e.g., `zerohub`, `dotai`, `sdp-compact`, `luma.examples`, etc.) that are NOT on an active board.
   - Do NOT run directory loops across `~/git` or broad `find ~/git` commands.
   - Do NOT report on unregistered repositories (not even as "informational" or "local clone"). They are completely out of scope.
   - The agent must NEVER automatically create new Kanban boards. It should only read existing boards created by the user and clone their repositories if missing.

## Scan criteria (prioritized):
1. **BUG FIXES** — null pointers, missing edge cases, type mismatches, logic errors, broken imports
2. **DUPLICATE CODE** — repeated patterns that should be extracted or refactored
3. **MISSING TESTS** — functions/classes without coverage that should have them
4. **PERFORMANCE** — O(n²) patterns, redundant operations, memory leaks, unoptimized queries
5. **DOCUMENTATION** — undocumented functions, stale README sections, missing inline comments, broken links
6. **REFACTORING** — extract utility functions, improve naming, reduce cyclomatic complexity, remove dead code
7. **SECURITY** — hardcoded secrets, unsanitized input, missing error handling, unsafe eval/exec usage
8. **CONFIG** — missing .gitignore files, uncommitted config drift, stale dependencies

## For each issue found (MAXIMUM 1 TASK TOTAL):
1. Create a task using the Zero Factory Kanban CLI:
   `hermes zerofactory-kanban create "<issue title>" --description "<detailed context>" --board "<board_slug>" --priority P0 --status todo --assignee builder`
   - Clear description of the issue with RELATIVE file paths ONLY (e.g., `src/main.ts`). NEVER use absolute paths in the task description!
   - Priority: Assign `P0` (critical) or `P1` (high) so the dispatcher picks it up first.
   - Category: bug-fix, refactoring, performance, documentation, testing, security, config.
   - Status: `todo` (the built-in dispatcher will auto-assign, provision an isolated git worktree, and promote to `ready`).
2. Write/update a summary to `docs/IMPROVEMENT_PLAN.md` (inside the scanned repository) with:
   - Number of improvements found across board-registered projects
   - Priority ranking
   - Estimated impact of each fix
   - List of board projects scanned (with paths)

## Deliver to user:
- Summary of what was found
- List of board projects scanned with paths
- Link to the plan file
- Inform the user that the task has been created in the Todo column for execution.

## IMPORTANT:
- DO NOT create more than 1 task per run to avoid overwhelming the local LLM pipeline.
- DO NOT execute the improvements yet.
- Only scan board-registered repositories, create kanban tasks, and deliver the plan.
- Mark all new tasks as `todo` so the dispatcher will automatically provision the worktree.
- End the run after delivery.

## Edge cases:
- If no active projects found on the board, report: "No active projects to scan. Waiting for new work."
- If scan fails on a project (e.g., missing deps), skip it and note the error"""

TASK_QUEUE_CHECK_PROMPT = """Check the Zero Factory Kanban board (using `hermes zerofactory-kanban list` or querying `~/.hermes/zerofactory_kanban.db`) - are any tasks stuck in 'running' too long? Any tasks stuck in 'blocked' with '[Human Review]'? Any PRs stuck waiting for Reviewer feedback? Create a new Kanban task using `hermes zerofactory-kanban create "[Report] Queue Health" --description "..." --status done` containing your bottleneck report and recommendations."""

DAILY_REPORT_PROMPT = """Generate a comprehensive daily report for Zero Factory using `hermes zerofactory-kanban stats` and querying `~/.hermes/zerofactory_kanban.db`. Include: total tasks completed, tasks currently running, tasks blocked, agent throughput, and open issues. Summarize with actionable items. Create a new task using `hermes zerofactory-kanban create "[Report] Daily Report" --description "..." --status done` with your full report."""

def _load_env_defaults() -> tuple[str, str, str]:
    """Resolve default model, provider, and base_url from env or configs."""
    model = os.getenv("HERMES_MODEL")
    provider = os.getenv("HERMES_INFERENCE_PROVIDER")
    base_url = os.getenv("CUSTOM_BASE_URL")

    search_files = [
        Path(os.path.expanduser("~/.hermes/profiles/orchestrator/.env")),
        Path(__file__).resolve().parent.parent.parent / "common" / ".env",
        Path(os.path.expanduser("~/.hermes/.env")),
    ]
    env_override = os.getenv("HERMES_ENV_FILE")
    if env_override:
        search_files.insert(0, Path(os.path.expanduser(env_override)))
    for env_file in search_files:
        if model and provider and base_url:
            break
        if env_file.exists():
            try:
                for line in env_file.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line or line.startswith("#") or "=" not in line:
                        continue
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip().strip('"').strip("'")
                    if k == "HERMES_MODEL" and not model:
                        model = v
                    elif k == "HERMES_INFERENCE_PROVIDER" and not provider:
                        provider = v
                    elif k == "CUSTOM_BASE_URL" and not base_url:
                        base_url = v
            except Exception:
                pass

    return (
        model or "qwen38-27b-unsloth-nvfp4-dflash2",
        provider or "custom",
        base_url or "https://spark.ntsd.dev:8001/v1",
    )


DEFAULT_CRON_MODEL, DEFAULT_CRON_PROVIDER, DEFAULT_CRON_BASE_URL = _load_env_defaults()

BUILTIN_CRON_JOBS: Dict[str, Dict[str, Any]] = {
    "zero-factory-task-queue-check": {
        "id": "zero-factory-task-queue-check",
        "name": "Zero Factory task queue check",
        "prompt": TASK_QUEUE_CHECK_PROMPT,
        "skills": [],
        "skill": None,
        "model": DEFAULT_CRON_MODEL,
        "provider": DEFAULT_CRON_PROVIDER,
        "base_url": DEFAULT_CRON_BASE_URL,
        "script": None,
        "no_agent": False,
        "context_from": None,
        "schedule": {
            "kind": "interval",
            "minutes": 120,
            "display": "every 120m"
        },
        "schedule_display": "every 120m",
        "enabled": True,
        "state": "scheduled",
        "paused_at": None,
        "paused_reason": None,
        "deliver": None,
        "origin": "zerofactory-kanban",
        "enabled_toolsets": ["terminal", "file", "kanban"],
        "workdir": None,
        "profile": "orchestrator"
    },
    "zero-factory-daily-report": {
        "id": "zero-factory-daily-report",
        "name": "Zero Factory daily report",
        "prompt": DAILY_REPORT_PROMPT,
        "skills": [],
        "skill": None,
        "model": DEFAULT_CRON_MODEL,
        "provider": DEFAULT_CRON_PROVIDER,
        "base_url": DEFAULT_CRON_BASE_URL,
        "script": None,
        "no_agent": False,
        "context_from": None,
        "schedule": {
            "kind": "cron",
            "expr": "0 9 * * *",
            "display": "0 9 * * *"
        },
        "schedule_display": "0 9 * * *",
        "enabled": True,
        "state": "scheduled",
        "paused_at": None,
        "paused_reason": None,
        "deliver": None,
        "origin": "zerofactory-kanban",
        "enabled_toolsets": ["terminal", "file", "kanban"],
        "workdir": None,
        "profile": "orchestrator"
    },
    "zero-factory-improvement-scanner": {
        "id": "zero-factory-improvement-scanner",
        "name": "Zero Factory-improvement scanner",
        "prompt": IMPROVEMENT_SCANNER_PROMPT,
        "skills": [],
        "skill": None,
        "model": DEFAULT_CRON_MODEL,
        "provider": DEFAULT_CRON_PROVIDER,
        "base_url": DEFAULT_CRON_BASE_URL,
        "script": None,
        "no_agent": False,
        "context_from": None,
        "schedule": {
            "kind": "interval",
            "minutes": 60,
            "display": "every 60m"
        },
        "schedule_display": "every 60m",
        "enabled": True,
        "state": "scheduled",
        "paused_at": None,
        "paused_reason": None,
        "deliver": None,
        "origin": "zerofactory-kanban",
        "enabled_toolsets": ["terminal", "file", "web", "kanban"],
        "workdir": None,
        "profile": "orchestrator"
    }
}


def cleanup_duplicate_root_jobs() -> None:
    """Ensure root ~/.hermes/cron/jobs.json does not contain duplicate Zero Factory jobs.

    The Hermes dashboard aggregates jobs across all profiles (profile=all).
    If jobs are written to both the profile store and the root (default) store,
    they appear duplicated in the UI (e.g. 6 jobs instead of 3).
    """
    try:
        hermes_root = Path(os.path.expanduser("~/.hermes"))
        root_jobs_file = hermes_root / "cron" / "jobs.json"
        if root_jobs_file.exists():
            existing = load_jobs_from_file(root_jobs_file)
            filtered = [j for j in existing if isinstance(j, dict) and j.get("id") not in BUILTIN_CRON_JOBS]
            if len(filtered) != len(existing):
                save_jobs_to_file(root_jobs_file, filtered)
                _log.info("Cleaned %d duplicate Zero Factory job(s) from root cron store", len(existing) - len(filtered))
    except Exception as e:
        _log.warning("Failed to cleanup duplicate jobs from root store: %s", e)


def get_target_jobs_files() -> List[Path]:
    """Resolve all locations where jobs.json should be synced.

    Only targets active profile and orchestrator profile stores.
    Root ~/.hermes/cron/jobs.json is intentionally excluded to prevent
    duplicate listings in the dashboard's all-profiles view.
    """
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

    # 2. Orchestrator profile jobs.json (canonical Zero Factory profile)
    orch_jobs = hermes_root / "profiles" / "orchestrator" / "cron" / "jobs.json"
    if orch_jobs not in files:
        files.append(orch_jobs)

    return files


def load_jobs_from_file(jobs_file: Path) -> List[Dict[str, Any]]:
    """Load jobs from a given JSON file safely."""
    if not jobs_file.exists():
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


def ensure_builtin_cron_jobs() -> Dict[str, Any]:
    """Ensure all builtin Zero Factory cron jobs are registered and up-to-date."""
    # Ensure no duplicates in root ~/.hermes/cron/jobs.json
    cleanup_duplicate_root_jobs()

    synced_targets = []
    total_added = 0
    total_updated = 0

    # Dynamically refresh env defaults in case environment variables or .env changed
    eff_model, eff_provider, eff_base_url = _load_env_defaults()
    for bdef in BUILTIN_CRON_JOBS.values():
        bdef["model"] = eff_model
        bdef["provider"] = eff_provider
        bdef["base_url"] = eff_base_url

    for target in get_target_jobs_files():
        existing_jobs = load_jobs_from_file(target)
        existing_by_id = {j.get("id"): j for j in existing_jobs if isinstance(j, dict) and j.get("id")}

        added_here = 0
        updated_here = 0

        for job_id, builtin_def in BUILTIN_CRON_JOBS.items():
            if job_id not in existing_by_id:
                # Add new job
                new_job = dict(builtin_def)
                new_job["created_at"] = time.strftime("%Y-%m-%dT%H:%M:%S%z")
                existing_jobs.append(new_job)
                added_here += 1
            else:
                # Update prompts, schedule, provider, model, base_url if drifted
                curr = existing_by_id[job_id]
                changed = False
                for field in (
                    "name", "prompt", "schedule", "schedule_display",
                    "enabled_toolsets", "origin", "model", "provider", "base_url"
                ):
                    if curr.get(field) != builtin_def.get(field):
                        curr[field] = builtin_def[field]
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

        if added_here > 0 or updated_here > 0 or not target.exists():
            save_jobs_to_file(target, existing_jobs)
        synced_targets.append(str(target))
        total_added += added_here
        total_updated += updated_here

    return {
        "ok": True,
        "synced_targets": synced_targets,
        "added": total_added,
        "updated": total_updated,
        "job_ids": list(BUILTIN_CRON_JOBS.keys())
    }


def list_builtin_jobs() -> List[Dict[str, Any]]:
    """Return the current configuration and runtime status of builtin jobs."""
    target_files = get_target_jobs_files()
    existing_by_id = {}
    for t in target_files:
        if t.exists():
            for j in load_jobs_from_file(t):
                if j.get("id") in BUILTIN_CRON_JOBS and j.get("id") not in existing_by_id:
                    existing_by_id[j["id"]] = j

    results = []
    for job_id, builtin_def in BUILTIN_CRON_JOBS.items():
        curr = existing_by_id.get(job_id, builtin_def)
        results.append({
            "id": job_id,
            "name": curr.get("name", builtin_def["name"]),
            "schedule": curr.get("schedule_display") or curr.get("schedule", {}).get("display", "configured"),
            "enabled": curr.get("enabled", True),
            "state": curr.get("state", "scheduled"),
            "last_status": curr.get("last_status"),
            "last_run_at": curr.get("last_run_at"),
            "next_run_at": curr.get("next_run_at"),
            "last_error": curr.get("last_error")
        })
    return results


def trigger_builtin_job(job_id: str) -> Dict[str, Any]:
    """Immediately trigger an execution of a builtin job."""
    if job_id not in BUILTIN_CRON_JOBS:
        return {"ok": False, "error": f"Unknown builtin job ID: {job_id}"}

    # Ensure job is registered in target files before running
    ensure_builtin_cron_jobs()

    # Trigger via hermes CLI
    try:
        proc = subprocess.Popen(
            ["hermes", "cron", "run", job_id, "--accept-hooks"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return {
            "ok": True,
            "job_id": job_id,
            "pid": proc.pid,
            "message": f"Triggered execution for job '{job_id}' (PID: {proc.pid})"
        }
    except Exception as e:
        _log.error("Failed to run cron job %s: %s", job_id, e)
        return {"ok": False, "error": str(e)}


def tick_builtin_cron() -> int:
    """Safe periodic scheduler tick called by the background dispatcher daemon."""
    try:
        # Import lazily to avoid circular or early import issues
        hermes_agent_dir = Path(os.getenv("HERMES_AGENT_DIR", str(Path.home() / ".hermes" / "hermes-agent")))
        if str(hermes_agent_dir) not in sys.path:
            sys.path.insert(0, str(hermes_agent_dir))

        from cron.scheduler import tick
        executed = tick(verbose=False)
        if executed:
            _log.info("[builtin_cron] Scheduler tick fired %s due job(s)", executed)
        return executed or 0
    except Exception as e:
        # CronTickYielded, lock contention, or transient idle states are expected and safe
        _log.debug("[builtin_cron] Tick skipped or yielded: %s", e)
        return 0
