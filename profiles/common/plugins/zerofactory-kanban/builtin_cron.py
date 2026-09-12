"""Built-in Cron Engine for Zero Factory Kanban.

Natively embeds and orchestrates all Zero Factory periodic automation:
1. zero-factory-task-queue-check (every 120m)
2. zero-factory-daily-report (0 9 * * *)
3. zero-factory-improvement-scanner-{board_slug} (every 60m per board, with workdir set to repo)

Automatically synchronizes with the active Hermes profile's cron store and
allows background ticking and on-demand execution.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_log = logging.getLogger("zerofactory_kanban.cron")

DEFAULT_DB_PATH = Path.home() / ".hermes" / "zerofactory_kanban.db"


def get_db_path() -> Path:
    override = os.environ.get("ZEROFACTORY_KANBAN_DB")
    if override:
        return Path(override)
    return DEFAULT_DB_PATH


# Canonical Zero Factory Core Job Definitions
TASK_QUEUE_CHECK_PROMPT = """Check the Zero Factory Kanban board (using `hermes zerofactory-kanban list` or querying `~/.hermes/zerofactory_kanban.db`) - are any tasks stuck in 'running' too long? Any tasks stuck in 'blocked' with '[Human Review]'? Any PRs stuck waiting for Reviewer feedback? Create a new Kanban task using `hermes zerofactory-kanban create "[Report] Queue Health" --description "..." --status done` containing your bottleneck report and recommendations."""

DAILY_REPORT_PROMPT = """Generate a comprehensive daily report for Zero Factory using `hermes zerofactory-kanban stats` and querying `~/.hermes/zerofactory_kanban.db`. Include: total tasks completed, tasks currently running, tasks blocked, agent throughput, and open issues. Summarize with actionable items. Create a new task using `hermes zerofactory-kanban create "[Report] Daily Report" --description "..." --status done` with your full report."""


def build_board_scanner_prompt(board: Dict[str, Any], workdir: Optional[str]) -> str:
    """Generate a clean, focused improvement scanner prompt for a specific board."""
    slug = board.get("slug") or "default"
    name = board.get("name") or slug
    workdir_desc = f"Current repository root (`{workdir}`)" if workdir else "Current repository workspace"

    return f"""Scan the workspace repository for code quality issues, tech debt, and improvement opportunities for the '{name}' board (slug: '{slug}').

## Context:
- Working Directory: {workdir_desc}
- Target Board: `{slug}`

## STEP 1: Scanner Pre-Flight Board Check (CRITICAL)
Before inspecting files, review all existing tasks on the board:
Run: `hermes zerofactory-kanban list --board "{slug}"`
1. Review all open tasks (`triage`, `todo`, `ready`, `running`, `blocked`).
2. Note the files, modules, and issues they already track.
3. **NEVER** file a task for an issue, function, or file(s) that are already covered by an open task.
4. Only proceed to file a task if you discover a distinct, unaddressed problem.
5. If all issues you find in the codebase are already tracked on the board, STOP and report:
   "All discovered improvement opportunities are already tracked on the board." and finish without creating any tasks.

## STEP 2: Scan criteria (prioritized):
1. **BUG FIXES** — null pointers, missing edge cases, type mismatches, logic errors, broken imports
2. **DUPLICATE CODE** — repeated patterns that should be extracted or refactored
3. **MISSING TESTS** — functions/classes without coverage that should have them
4. **PERFORMANCE** — O(n²) patterns, redundant operations, memory leaks, unoptimized queries
5. **DOCUMENTATION** — undocumented functions, stale README sections, missing inline comments, broken links
6. **REFACTORING** — extract utility functions, improve naming, reduce cyclomatic complexity, remove dead code
7. **SECURITY** — hardcoded secrets, unsanitized input, missing error handling, unsafe eval/exec usage
8. **CONFIG** — missing .gitignore files, uncommitted config drift, stale dependencies

## STEP 3: Create Task with Fingerprint Safeguard (MAXIMUM 1 TASK TOTAL):
If you find a genuine, unaddressed issue:
Create a task using the Zero Factory Kanban CLI:
`hermes zerofactory-kanban create "<issue title>" --description "<detailed context>" --board "{slug}" --files "<relative_path1>,<relative_path2>" --category "<category>" --priority P0 --status todo --assignee builder`
- Always pass `--files` with all affected relative file paths (e.g., `--files "src/auth.ts,src/session.ts"`). Zero Factory computes a multi-file fingerprint safeguard to prevent duplicate tasks.
- Always pass `--category` (one of: `bug-fix`, `refactoring`, `performance`, `documentation`, `testing`, `security`, `config`).
- In `--description`: Clear context with RELATIVE file paths and line numbers only. NEVER use absolute paths in the description!
- Priority: Assign `P0` (critical) or `P1` (high) so the dispatcher picks it up first.
- Status: `todo` (the built-in dispatcher will auto-assign, provision an isolated git worktree, and promote to `ready`).

## Deliver to user:
- Summary of what was found and the task created in Kanban (or report that all issues were already tracked)
- Inform the user that the task has been created in the Todo column for execution.

## IMPORTANT:
- Scan ONLY this repository (current working directory). Do not inspect or touch any other folders or projects.
- DO NOT create or write any plan files (NEVER write `docs/IMPROVEMENT_PLAN.md` or any other plan files on disk). All issue details belong directly in the Zero Factory Kanban task.
- DO NOT create more than 1 task per run to avoid overwhelming the local LLM pipeline.
- DO NOT execute the improvements yet.
- Mark all new tasks as `todo` so the dispatcher will automatically provision the worktree.
- End the run after delivery."""


def resolve_board_repo_path(board: Dict[str, Any]) -> Optional[Path]:
    """Resolve the local repository path for a given Kanban board.

    Checks ~/git/<slug>, ~/git/<owner>/<repo>, ~/git/<repo>, subdirectories in ~/git,
    and current working directory.
    """
    slug = (board.get("slug") or "").strip()
    name = (board.get("name") or "").strip()
    git_url = (board.get("git_url") or "").strip()
    if not git_url and board.get("description"):
        match = re.search(r"https?://[^\s)]+", board["description"])
        if match:
            git_url = match.group(0)

    # Extract repo and owner from git_url if available
    owner = ""
    repo = ""
    if git_url:
        cleaned_url = re.sub(r"\.git$", "", git_url.strip().rstrip("/"))
        parts = cleaned_url.replace(":", "/").split("/")
        if len(parts) >= 1:
            repo = parts[-1]
        if len(parts) >= 2:
            owner = parts[-2]

    candidate_names = set()
    for n in (slug, repo, name):
        if n:
            candidate_names.add(n)
            candidate_names.add(n.lower())

    home = Path.home()
    candidates: List[Path] = []

    # 1. Direct owner/repo matches under ~/git/
    if owner and repo:
        candidates.append(home / "git" / owner / repo)
        candidates.append(home / "git" / f"{owner}-{repo}")

    # 2. Candidate names directly under ~/git/
    for cname in candidate_names:
        candidates.append(home / "git" / cname)

    # 3. Check immediate subdirectories of ~/git (e.g. ~/git/<org>/<repo>)
    git_root = home / "git"
    if git_root.is_dir():
        try:
            for child in git_root.iterdir():
                if child.is_dir():
                    for cname in candidate_names:
                        sub = child / cname
                        if sub not in candidates:
                            candidates.append(sub)
        except Exception:
            pass

    # 4. Check current working directory if matching
    try:
        cwd = Path.cwd()
        if any(cname in (cwd.name, cwd.name.lower()) for cname in candidate_names):
            candidates.insert(0, cwd)
    except Exception:
        pass

    # Check candidates for directory existence
    for cand in candidates:
        if cand.is_dir():
            return cand.resolve()

    # 5. Optional auto-clone if git_url is present and git operations not disabled
    if (
        git_url
        and not os.environ.get("ZEROFACTORY_KANBAN_SKIP_GIT")
        and not os.environ.get("ZEROFACTORY_KANBAN_SKIP_CLONE")
    ):
        target_clone = home / "git" / (repo or slug)
        if owner and (home / "git" / owner).is_dir():
            target_clone = home / "git" / owner / (repo or slug)
        try:
            target_clone.parent.mkdir(parents=True, exist_ok=True)
            res = subprocess.run(["git", "clone", git_url, str(target_clone)], capture_output=True, timeout=10)
            if res.returncode == 0 and target_clone.is_dir():
                return target_clone.resolve()
        except Exception as e:
            _log.debug("Auto-clone skipped or failed for %s: %s", git_url, e)

    return None


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

CORE_CRON_JOBS: Dict[str, Dict[str, Any]] = {
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
    }
}

BUILTIN_CRON_JOBS: Dict[str, Dict[str, Any]] = {}


def get_all_builtin_cron_jobs() -> Dict[str, Dict[str, Any]]:
    """Resolve all builtin jobs including core jobs and dynamic per-board scanner jobs."""
    eff_model, eff_provider, eff_base_url = _load_env_defaults()

    jobs: Dict[str, Dict[str, Any]] = {}
    for jid, cjob in CORE_CRON_JOBS.items():
        job_copy = dict(cjob)
        job_copy["model"] = eff_model
        job_copy["provider"] = eff_provider
        job_copy["base_url"] = eff_base_url
        jobs[jid] = job_copy

    # Query all active boards from DB
    db_path = get_db_path()
    boards: List[Dict[str, Any]] = []
    if db_path.exists():
        try:
            with sqlite3.connect(str(db_path), timeout=5.0) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT slug, name, description, git_url FROM boards ORDER BY created_at ASC")
                boards = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            _log.warning("Failed to query boards for cron generation: %s", e)

    # Fallback: if no boards in table yet, default to zerofactory board
    if not boards:
        boards = [{
            "slug": "zerofactory",
            "name": "ZeroFactory",
            "description": "Zero Factory Multi-Agent Orchestration",
            "git_url": "https://github.com/hotcode-dev/zerofactory.git"
        }]

    for board in boards:
        slug = board.get("slug") or "default"
        job_id = f"zero-factory-improvement-scanner-{slug}"
        repo_path = resolve_board_repo_path(board)
        workdir = str(repo_path) if repo_path and repo_path.is_dir() else None
        prompt = build_board_scanner_prompt(board, workdir)

        jobs[job_id] = {
            "id": job_id,
            "name": f"Zero Factory improvement scanner ({board.get('name', slug)})",
            "prompt": prompt,
            "skills": [],
            "skill": None,
            "model": eff_model,
            "provider": eff_provider,
            "base_url": eff_base_url,
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
            "workdir": workdir,
            "profile": "orchestrator"
        }

    BUILTIN_CRON_JOBS.clear()
    BUILTIN_CRON_JOBS.update(jobs)
    return jobs


# Initial populate on import
get_all_builtin_cron_jobs()


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
            current_ids = set(get_all_builtin_cron_jobs().keys())
            filtered = [
                j for j in existing
                if isinstance(j, dict) and not (
                    j.get("id") in current_ids or
                    str(j.get("id", "")).startswith("zero-factory-") or
                    j.get("origin") == "zerofactory-kanban"
                )
            ]
            if len(filtered) != len(existing):
                save_jobs_to_file(root_jobs_file, filtered)
                _log.info("Cleaned %d duplicate Zero Factory job(s) from root cron store", len(existing) - len(filtered))
    except Exception as e:
        _log.warning("Failed to cleanup duplicate jobs from root store: %s", e)


def get_target_jobs_files() -> List[Path]:
    """Resolve all locations where jobs.json should be synced.

    Targets:
    1. Active profile jobs.json (if active and not default)
    2. Orchestrator profile jobs.json in ~/.hermes/profiles/orchestrator
    3. Workspace repository profiles/orchestrator/cron/jobs.json (if present)
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

    # 3. Local workspace repository orchestrator jobs.json
    try:
        repo_orch_jobs = Path(__file__).resolve().parents[3] / "orchestrator" / "cron" / "jobs.json"
        if repo_orch_jobs.exists() and repo_orch_jobs not in files:
            files.append(repo_orch_jobs)
    except Exception:
        pass

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
    # Refresh all builtin jobs from DB and env
    current_builtin_jobs = get_all_builtin_cron_jobs()

    # Ensure no duplicates in root ~/.hermes/cron/jobs.json
    cleanup_duplicate_root_jobs()

    synced_targets = []
    total_added = 0
    total_updated = 0
    total_pruned = 0

    for target in get_target_jobs_files():
        existing_jobs = load_jobs_from_file(target)

        # 1. Prune obsolete Zero Factory jobs (e.g. monolithic scanner or deleted board scanners)
        pruned_jobs = []
        for j in existing_jobs:
            if not isinstance(j, dict):
                continue
            jid = str(j.get("id", ""))
            is_zf_job = (
                j.get("origin") == "zerofactory-kanban"
                or jid.startswith("zero-factory-")
            )
            if is_zf_job and jid not in current_builtin_jobs:
                total_pruned += 1
                continue
            pruned_jobs.append(j)
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
                existing_jobs.append(new_job)
                added_here += 1
            else:
                # Update prompts, schedule, provider, model, base_url, workdir if drifted
                curr = existing_by_id[job_id]
                changed = False
                for field in (
                    "name", "prompt", "schedule", "schedule_display",
                    "enabled_toolsets", "origin", "model", "provider", "base_url", "workdir"
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

        if added_here > 0 or updated_here > 0 or total_pruned > 0 or not target.exists():
            save_jobs_to_file(target, existing_jobs)
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


def list_builtin_jobs() -> List[Dict[str, Any]]:
    """Return the current configuration and runtime status of builtin jobs."""
    current_builtin_jobs = get_all_builtin_cron_jobs()
    target_files = get_target_jobs_files()
    existing_by_id = {}
    for t in target_files:
        if t.exists():
            for j in load_jobs_from_file(t):
                if isinstance(j, dict) and j.get("id") in current_builtin_jobs and j.get("id") not in existing_by_id:
                    existing_by_id[j["id"]] = j

    results = []
    for job_id, builtin_def in current_builtin_jobs.items():
        curr = existing_by_id.get(job_id, builtin_def)
        results.append({
            "id": job_id,
            "name": curr.get("name", builtin_def["name"]),
            "schedule": curr.get("schedule_display") or curr.get("schedule", {}).get("display", "configured"),
            "enabled": curr.get("enabled", True),
            "state": curr.get("state", "scheduled"),
            "workdir": curr.get("workdir"),
            "last_status": curr.get("last_status"),
            "last_run_at": curr.get("last_run_at"),
            "next_run_at": curr.get("next_run_at"),
            "last_error": curr.get("last_error")
        })
    return results


def trigger_builtin_job(job_id: str) -> Dict[str, Any]:
    """Immediately trigger an execution of a builtin job."""
    current_builtin_jobs = get_all_builtin_cron_jobs()

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
    ensure_builtin_cron_jobs()

    # Trigger via hermes CLI
    try:
        proc = subprocess.Popen(
            ["hermes", "cron", "run", target_job_id, "--accept-hooks"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True
        )
        return {
            "ok": True,
            "job_id": target_job_id,
            "pid": proc.pid,
            "message": f"Triggered execution for job '{target_job_id}' (PID: {proc.pid})"
        }
    except Exception as e:
        _log.error("Failed to run cron job %s: %s", target_job_id, e)
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
