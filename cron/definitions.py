"""Zero Factory Cron — Core and Dynamic Board Job Definitions."""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

from .config import (
    DEFAULT_CRON_BASE_URL,
    DEFAULT_CRON_MODEL,
    DEFAULT_CRON_PROVIDER,
    TASK_QUEUE_CHECK_PROMPT,
    _c,
    _load_env_defaults,
    get_db_path,
)

_log = logging.getLogger("zerofactory.cron")


def build_board_scanner_prompt(board: Dict[str, Any], workdir: Optional[str]) -> str:
    """Generate a clean, focused improvement scanner prompt for a specific board."""
    slug = board.get("slug") or "default"
    workdir_desc = f"Current repository root (`{workdir}`)" if workdir else "Current repository workspace"

    return f"""Scan the workspace repository for code quality issues, tech debt, and improvement opportunities for the '{slug}' board.

## Context:
- Working Directory: {workdir_desc}
- Target Board: `{slug}`

## STEP 1: Scanner Pre-Flight Board Check (CRITICAL)
Before inspecting files, review all existing tasks on the board:
Run: `hermes zerofactory list --board "{slug}"`
1. Review all open tasks (`triage`, `todo`, `running`, `blocked`).
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
Write your detailed context to a temporary file (e.g. `/tmp/task_desc.md`) and run:
`hermes zerofactory create "<issue title>" --description-file "/tmp/task_desc.md" --board "{slug}" --files "<relative_path1>,<relative_path2>" --category "<category>" --priority P0 --status todo --assignee zf-builder`
(Alternatively, pass inline `--description "<detailed context>"` if short).
- Always pass `--files` with all affected relative file paths (e.g., `--files "src/auth.ts,src/session.ts"`). Zero Factory computes a multi-file fingerprint safeguard to prevent duplicate tasks.
- Always pass `--category` (one of: `bug-fix`, `refactoring`, `performance`, `documentation`, `testing`, `security`, `config`).
- In description: Clear context with RELATIVE file paths and line numbers only. NEVER use absolute paths in the description!
- Priority: Assign `P0` (critical) or `P1` (high) so the dispatcher picks it up first.
- Status: `todo` (the built-in dispatcher will auto-assign, provision an isolated git worktree, and dispatch to `running`).

## Deliver to user:
- Summary of what was found and the task created in Kanban (or report that all issues were already tracked)
- Inform the user that the task has been created in the Todo column for execution.

## IMPORTANT:
- Scan ONLY this repository (current working directory). Do not inspect or touch any other folders or projects.
- DO NOT use any native kanban_* tools (e.g. kanban_create, kanban_list). The Zero Factory system exclusively uses the CLI commands 'hermes zerofactory create ...' and 'hermes zerofactory list ...' on zerofactory.db.
- DO NOT run destructive bash commands (e.g. rm) or -e/-c script execution in cron mode, as they trigger safety filters.
- DO NOT create or write any plan files (NEVER write `docs/IMPROVEMENT_PLAN.md` or any other plan files on disk). All issue details belong directly in the Zero Factory Kanban task.
- DO NOT create more than 1 task per run to avoid overwhelming the local LLM pipeline.
- DO NOT execute the improvements yet.
- Mark all new tasks as `todo` so the dispatcher will automatically provision the worktree.
- End the run after delivery."""


def resolve_board_repo_path(board: Dict[str, Any]) -> Optional[Path]:
    """Resolve the local repository path for a given Kanban board."""
    slug = (board.get("slug") or "").strip()
    git_url = (board.get("git_url") or "").strip()
    if not git_url and board.get("description"):
        match = re.search(r"(?:https?://|git@)[^\s)]+", board["description"])
        if match:
            git_url = match.group(0)

    owner = ""
    repo = ""
    if git_url:
        cleaned_url = re.sub(r"\.git$", "", git_url.strip().rstrip("/"))
        parts = cleaned_url.replace(":", "/").split("/")
        if len(parts) >= 1:
            repo = parts[-1]
        if len(parts) >= 2:
            owner = parts[-2]
    elif "-" in slug:
        parts = slug.split("-", 1)
        owner, repo = parts[0], parts[1]

    candidate_names = set()
    for n in (slug, repo):
        if n:
            candidate_names.add(n)
            candidate_names.add(n.lower())

    home = Path.home()
    candidates: List[Path] = []

    # 0. Check if git_url is an existing local directory
    if git_url:
        try:
            local_p = Path(git_url)
            if local_p.is_dir() and (local_p / ".git").exists():
                return local_p.resolve()
        except Exception:
            pass

    # 1. Direct owner/repo matches under ~/git/
    if owner and repo:
        candidates.append(home / "git" / owner / repo)
        candidates.append(home / "git" / f"{owner}-{repo}")

    # 2. Candidate names directly under ~/git/
    for cname in candidate_names:
        candidates.append(home / "git" / cname)

    # 3. Check immediate subdirectories of ~/git
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

    for cand in candidates:
        if cand.is_dir():
            return cand.resolve()

    # 5. Optional auto-clone
    if (
        git_url
        and os.environ.get("ZEROFACTORY_AUTO_CLONE")
        and not os.environ.get("ZEROFACTORY_SKIP_GIT")
        and not os.environ.get("ZEROFACTORY_SKIP_CLONE")
    ):
        target_clone = home / "git" / (repo or slug)
        if owner and (home / "git" / owner).is_dir():
            target_clone = home / "git" / owner / (repo or slug)
        try:
            target_clone.parent.mkdir(parents=True, exist_ok=True)
            res = subprocess.run(
                ["git", "clone", git_url, str(target_clone)],
                capture_output=True,
                timeout=10,
                stdin=subprocess.DEVNULL,
                env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}
            )
            if res.returncode == 0 and target_clone.is_dir():
                return target_clone.resolve()
        except Exception as e:
            _log.debug("Auto-clone skipped or failed for %s: %s", git_url, e)

    return None


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
        "script": "zf_queue_watchdog.py",
        "no_agent": True,
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
        "origin": "zerofactory",
        "enabled_toolsets": ["terminal", "file"],
        "workdir": None,
        "profile": "zf-orchestrator"
    }
}

BUILTIN_CRON_JOBS: Dict[str, Dict[str, Any]] = {}


def get_all_builtin_cron_jobs() -> Dict[str, Dict[str, Any]]:
    """Resolve all builtin jobs including core jobs and dynamic per-board scanner jobs."""
    disp = _c()
    if disp and hasattr(disp, "get_all_builtin_cron_jobs"):
        # If patched by test on builtin_cron, return mock
        target = getattr(disp, "get_all_builtin_cron_jobs")
        if target is not get_all_builtin_cron_jobs:
            return target()

    eff_model, eff_provider, eff_base_url = _load_env_defaults()

    jobs: Dict[str, Dict[str, Any]] = {}
    for jid, cjob in CORE_CRON_JOBS.items():
        job_copy = dict(cjob)
        job_copy["model"] = eff_model
        job_copy["provider"] = eff_provider
        job_copy["base_url"] = eff_base_url
        jobs[jid] = job_copy

    get_db_path_fn = getattr(disp, "get_db_path", get_db_path)
    db_path = get_db_path_fn()
    boards: List[Dict[str, Any]] = []
    if db_path.exists():
        try:
            with sqlite3.connect(str(db_path), timeout=5.0) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute("SELECT slug, description, git_url FROM boards ORDER BY created_at ASC")
                boards = [dict(row) for row in cursor.fetchall()]
        except Exception as e:
            _log.warning("Failed to query boards for cron generation: %s", e)

    for board in boards:
        slug = board.get("slug") or "default"
        job_id = f"zero-factory-improvement-scanner-{slug}"
        repo_path = resolve_board_repo_path(board)
        workdir = str(repo_path) if repo_path and repo_path.is_dir() else None
        prompt = build_board_scanner_prompt(board, workdir)

        jobs[job_id] = {
            "id": job_id,
            "name": f"Zero Factory improvement scanner ({slug})",
            "prompt": prompt,
            "skills": [],
            "skill": None,
            "model": eff_model,
            "provider": eff_provider,
            "base_url": eff_base_url,
            "script": "zf_scanner_gate.py",
            "no_agent": False,
            "context_from": None,
            "continuity": False,
            "schedule": {
                "kind": "interval",
                "minutes": 10080,
                "display": "on idle (active < 2)"
            },
            "schedule_display": "on idle (active < 2)",
            "enabled": True,
            "state": "scheduled",
            "paused_at": None,
            "paused_reason": None,
            "deliver": None,
            "origin": "zerofactory",
            "enabled_toolsets": ["terminal", "file", "web"],
            "workdir": workdir,
            "profile": "zf-orchestrator"
        }

    BUILTIN_CRON_JOBS.clear()
    BUILTIN_CRON_JOBS.update(jobs)
    return jobs


# Initial populate on import
get_all_builtin_cron_jobs()
