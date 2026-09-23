"""Zero Factory Kanban Dispatcher Engine.

The core orchestration engine driving 24/7 autonomous multi-agent software engineering
workflows within the Zero Factory system. It coordinates task scheduling, agent execution,
git worktree isolation, GitHub Pull Request reviews, and worker lifecycle management.

Core Responsibilities:
1. Dependency Graph & DAG Progression:
   - Evaluates parent-child ticket dependencies and automatically unblocks downstream tasks
     when prerequisite parent tasks reach 'done'.
2. Work-in-Progress (WIP) Management & Scheduling:
   - Enforces configurable WIP limits per board and assignee to avoid pipeline congestion.
   - Dispatches scheduled tickets from 'todo' to 'running' based on capacity and priority.
3. Specialist Role Assignment & Routing:
   - Directs tasks to specialized Hermes agent profiles:
     * zf-orchestrator: Goal decomposition, issue triage, repository improvement scanning.
     * zf-builder: Implementation, test writing, worktree-isolated development.
     * zf-reviewer: Thematic code review, security and performance audits, PR polish.
4. Isolated Git Worktree Provisioning:
   - Provisions isolated git worktrees (`~/git/<repo>-worktrees/<task_id>`) with dedicated
     feature branches (`task/<task_id>`).
   - Automatically synchronizes worktrees with the default branch (e.g. 'main') and detects
     merge conflicts, routing conflicting tasks back to builder agents for resolution.
   - Guarantees clean worktree teardown and prevents repository state pollution.
5. Agent Worker Process Lifecycle & Safety:
   - Spawns and tracks non-interactive Hermes worker subprocesses with custom context.
   - Monitors process health, maximum execution limits, and inactivity thresholds.
   - Safely terminates workers (SIGTERM -> SIGKILL) prior to worktree deletion
     to prevent zombie/orphan processes in deleted directories.
   - Reaps crashed, timed out, or orphaned workers, moving affected tickets to 'blocked'.
6. GitHub Pull Request & Review Feedback Loop:
   - Automates branch commits, remote pushes, and PR creation via GitHub CLI (`gh`).
   - Monitors GitHub PR status (`MERGED`, `CONFLICTING`, `CHANGES_REQUESTED`, `APPROVED`).
   - Orchestrates iterative multi-round code review loops between builder and reviewer agents.
   - Escalates approved PRs or unresolvable conflicts to human maintainers.
7. Concurrency & Dispatch Loop Safety:
   - Operates under a global re-entrant lock (`_dispatcher_lock`) to prevent race
     conditions across parallel background cron cycles, CLI commands, and dashboard triggers.
"""

from __future__ import annotations

from contextlib import closing
import fcntl
import json
import logging
import os
import re
import signal
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Shared global settings definitions: the six settings defaults and the
# load_settings() table reader live in the settings module (settings.py) and are
# imported by both dispatcher.py and dashboard/plugin_api.py so the defaults and
# the settings-parsing logic cannot drift between the two.
try:
    from .settings import (  # type: ignore
        DEFAULT_MAX_ACTIVE_TASKS,
        DEFAULT_MAX_CONCURRENT_LLM_WORKERS,
        DEFAULT_MAX_CONCURRENT_WORKERS,
        DEFAULT_SCAN_ON_IDLE,
        DEFAULT_IDLE_SCAN_ACTIVE_THRESHOLD,
        DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES,
        DEFAULT_IDLE_SCAN_COOLDOWN_SECONDS,
        DEFAULT_IDLE_SCAN_MAX_TODO,
        load_settings,
    )
except ImportError:
    from settings import (  # type: ignore
        DEFAULT_MAX_ACTIVE_TASKS,
        DEFAULT_MAX_CONCURRENT_LLM_WORKERS,
        DEFAULT_MAX_CONCURRENT_WORKERS,
        DEFAULT_SCAN_ON_IDLE,
        DEFAULT_IDLE_SCAN_ACTIVE_THRESHOLD,
        DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES,
        DEFAULT_IDLE_SCAN_COOLDOWN_SECONDS,
        DEFAULT_IDLE_SCAN_MAX_TODO,
        load_settings,
    )

# Shared profile-path resolution & assignee normalization (source of truth).
# Both the dispatcher and the dashboard (dashboard/plugin_api.py) consume these
# so the canonical-profile table, the normalizer, and the per-profile
# ``state.db`` resolution strategy cannot drift between the two surfaces.
try:
    from .paths import (  # type: ignore
        PROFILE_MAP,
        UNASSIGNED,
        normalize_assignee,
        resolve_profile_state_db,
    )
except ImportError:
    from paths import (  # type: ignore
        PROFILE_MAP,
        UNASSIGNED,
        normalize_assignee,
        resolve_profile_state_db,
    )

_log = logging.getLogger("zerofactory.kanban.dispatcher")


def get_dispatcher_lock_path() -> Path:
    """Path to the cross-process lock file for Kanban dispatch cycles."""
    env_lock = os.environ.get("ZEROFACTORY_LOCK_PATH")
    if env_lock:
        return Path(env_lock)
    return Path.home() / ".hermes" / "zerofactory_dispatcher.lock"


def is_worker_or_child_process() -> bool:
    """Return True if current process is a worker, cron runner, or child CLI process."""
    if os.environ.get("ZEROFACTORY_DISABLE_DISPATCHER") == "1" or os.environ.get("ZEROFACTORY_SKIP_DISPATCHER") == "1":
        return True
    profile = os.environ.get("HERMES_PROFILE") or ""
    if profile in ("zf-builder", "zf-reviewer"):
        return True
    if os.environ.get("HERMES_KANBAN_TASK"):
        return True
    if os.environ.get("_HERMES_CRON_EXTERNAL_WORKER"):
        return True
    return False

# Kanban WIP Limit and Worker Concurrency Limit defaults are imported from the
# shared ``settings`` module (see the import at the top of this file); the values
# are persisted in the settings table and can be customized in the UI settings.

# Maximum wall-clock execution duration (in seconds) before an active task worker is terminated as stuck.
DEFAULT_TASK_TIMEOUT_SECONDS = 3600  # 1 hour max running time

# Maximum idle duration (in seconds) with no log output or session updates before an agent worker is reaped.
DEFAULT_INACTIVITY_TIMEOUT_SECONDS = 900  # 15 mins with no log/session update

# Maximum worker failure/timeout retries before task is permanently blocked.
DEFAULT_MAX_WORKER_RETRIES = 3


def get_max_worker_retries() -> int:
    """Return maximum allowed worker failure/timeout retries before task is permanently blocked."""
    return int(os.environ.get("ZEROFACTORY_MAX_WORKER_RETRIES", str(DEFAULT_MAX_WORKER_RETRIES)))


# Interval (in seconds) between background dispatcher polling cycles.
DISPATCH_INTERVAL_SECONDS = 30

# Background thread handle running the continuous dispatch loop.
_dispatcher_thread: Optional[threading.Thread] = None

# Global re-entrant lock ensuring only one dispatch cycle executes at any given time.
_dispatcher_lock = threading.Lock()

# Registry tracking active worker subprocesses keyed by task_id: {task_id: subprocess.Popen}
_active_workers: Dict[str, subprocess.Popen] = {}

# Idle Improvement Scanner defaults (DEFAULT_SCAN_ON_IDLE,
# DEFAULT_IDLE_SCAN_ACTIVE_THRESHOLD, DEFAULT_IDLE_SCAN_COOLDOWN_SECONDS,
# DEFAULT_IDLE_SCAN_MAX_TODO) are imported from the shared ``settings`` module at
# the top of this file; they can be customized in the UI settings.

# Timestamp tracking when an idle improvement scan was last triggered per board slug: {board_slug: timestamp}
_last_idle_scan_times: Dict[str, int] = {}

# Registry tracking active scanner worker subprocesses per board slug: {board_slug: subprocess.Popen}
_active_scanners: Dict[str, subprocess.Popen] = {}

# Canonical alias mapping and profile normalization now live in the shared
# ``paths`` module (imported above) so the dispatcher and the dashboard share a
# single source of truth and can no longer drift. ``PROFILE_MAP`` and
# ``normalize_assignee`` are re-exported here for backward compatibility with
# importers that reference them via ``dispatcher``.
VALID_PROFILES = tuple(PROFILE_MAP)


def get_task_timeout_seconds() -> int:
    """Return maximum allowed running duration before worker is considered stuck."""
    return int(os.environ.get("ZEROFACTORY_TASK_TIMEOUT_SECONDS", str(DEFAULT_TASK_TIMEOUT_SECONDS)))


def get_inactivity_timeout_seconds() -> int:
    """Return maximum allowed inactivity before worker is considered hung."""
    return int(os.environ.get("ZEROFACTORY_INACTIVITY_TIMEOUT_SECONDS", str(DEFAULT_INACTIVITY_TIMEOUT_SECONDS)))


def get_db_path() -> Path:
    env_path = os.environ.get("ZEROFACTORY_DB")
    if env_path:
        return Path(env_path)
    return Path.home() / ".hermes" / "zerofactory.db"


def get_default_branch(repo_path: Path) -> str:
    """Determine default branch (e.g. main or master) for a git repository."""
    try:
        res = subprocess.run(
            ["git", "symbolic-ref", "refs/remotes/origin/HEAD"],
            cwd=str(repo_path), capture_output=True, text=True, timeout=5
        )
        if res.returncode == 0 and res.stdout.strip():
            return res.stdout.strip().split("/")[-1]
    except Exception:
        pass

    for cand in ("main", "master"):
        try:
            res = subprocess.run(
                ["git", "show-ref", "--verify", "--quiet", f"refs/remotes/origin/{cand}"],
                cwd=str(repo_path), timeout=5
            )
            if res.returncode == 0:
                return cand
        except Exception:
            pass

    for cand in ("main", "master"):
        try:
            res = subprocess.run(
                ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{cand}"],
                cwd=str(repo_path), timeout=5
            )
            if res.returncode == 0:
                return cand
        except Exception:
            pass

    return "main"


def sync_repo_main(repo_path: Path) -> str:
    """Fetch latest changes from origin for repository default branch."""
    default_branch = get_default_branch(repo_path)
    try:
        subprocess.run(
            ["git", "fetch", "origin", default_branch],
            cwd=str(repo_path), capture_output=True, text=True, timeout=10,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        )
        status = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(repo_path), capture_output=True, text=True, timeout=5
        )
        curr_branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            cwd=str(repo_path), capture_output=True, text=True, timeout=5
        )
        if (
            status.returncode == 0
            and not status.stdout.strip()
            and curr_branch.returncode == 0
            and curr_branch.stdout.strip() == default_branch
        ):
            subprocess.run(
                ["git", "merge", "--ff-only", f"origin/{default_branch}"],
                cwd=str(repo_path), capture_output=True, text=True, timeout=5
            )
    except Exception as e:
        _log.debug("git fetch/sync origin %s skipped or failed in %s: %s", default_branch, repo_path, e)
    return default_branch


def _has_unresolved_conflict_markers(content: bytes) -> bool:
    """Check if byte content contains a real git conflict marker block.

    A real conflict marker block requires a start line (<<<<<<< <label>),
    a middle separator line (=======), and an end line (>>>>>>> <label>).
    Simple substring occurrences inside single-line strings or comments
    will not trigger false-positive conflict detections.
    """
    try:
        text = content.decode("utf-8", errors="replace")
    except Exception:
        return False

    in_conflict = False
    has_sep = False
    for line in text.splitlines():
        line = line.rstrip("\r")
        if not in_conflict:
            if line.startswith("<<<<<<< "):
                in_conflict = True
                has_sep = False
        elif not has_sep:
            if line == "=======":
                has_sep = True
        else:
            if line.startswith(">>>>>>> "):
                return True
    return False


class GitConflictCheckError(Exception):
    """Raised when a git-backed conflict check could not be verified.

    Raised by :func:`check_unresolved_conflicts` when the authoritative
    unmerged-index query (``git diff --name-only --diff-filter=U``) or the
    ``git status --porcelain`` unmerged parse errors out. Callers on the
    dispatch hot path must treat this as "could not verify the worktree is
    clean" (fail-closed) rather than "no conflicts" (fail-open), because a
    silent empty result can mask a real merge conflict and let a broken
    worktree be auto-merged / advanced / shipped.
    """


def check_unresolved_conflicts(workspace_path: Path) -> List[str]:
    """Return a sorted list of relative file paths with unresolved merge conflicts or conflict markers.

    Fail-closed on git errors: if the authoritative unmerged-index query
    (``git diff --name-only --diff-filter=U``) or the ``git status
    --porcelain`` unmerged parse (steps 1-2) raises, a :class:`GitConflictCheckError`
    is raised so callers can distinguish "verified clean" from "could not
    verify". The leftover-marker scan (step 3) still swallows its own errors
    because it is a non-critical secondary signal.
    """
    if not workspace_path.exists():
        return []
    conflicted: set[str] = set()

    # 1. Check git unmerged index entries (diff-filter=U)
    try:
        res = subprocess.run(
            ["git", "diff", "--name-only", "--diff-filter=U"],
            cwd=str(workspace_path), capture_output=True, text=True, timeout=5
        )
        if res.returncode == 0 and res.stdout.strip():
            for line in res.stdout.strip().splitlines():
                if line.strip():
                    conflicted.add(line.strip())
    except Exception as e:
        _log.warning(
            "check_unresolved_conflicts: unmerged-index query failed for %s: %s",
            workspace_path, e,
        )
        raise GitConflictCheckError(
            f"could not verify unmerged index (git diff --diff-filter=U) in {workspace_path}: {e}"
        ) from e

    # 2. Check git status porcelain for unmerged status codes
    try:
        status_res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(workspace_path), capture_output=True, text=True, timeout=5
        )
        if status_res.returncode == 0:
            for line in status_res.stdout.splitlines():
                if len(line) >= 3 and line[:2] in ("UU", "AA", "UD", "DU", "DD", "AU", "UA"):
                    conflicted.add(line[3:].strip())
    except Exception as e:
        _log.warning(
            "check_unresolved_conflicts: status-porcelain query failed for %s: %s",
            workspace_path, e,
        )
        raise GitConflictCheckError(
            f"could not verify unmerged status (git status --porcelain) in {workspace_path}: {e}"
        ) from e

    # 3. Check modified, untracked, or conflicted text files for leftover conflict markers
    try:
        status_files = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(workspace_path), capture_output=True, text=True, timeout=5
        )
        files_to_check = set()
        if status_files.returncode == 0:
            for line in status_files.stdout.splitlines():
                if len(line) >= 3:
                    f = line[3:].strip()
                    if " -> " in f:
                        f = f.split(" -> ")[-1].strip()
                    files_to_check.add(f)

        # Also check files modified in the last commit
        diff_head = subprocess.run(
            ["git", "diff-tree", "--no-commit-id", "--name-only", "-r", "HEAD"],
            cwd=str(workspace_path), capture_output=True, text=True, timeout=5
        )
        if diff_head.returncode == 0 and diff_head.stdout.strip():
            for f in diff_head.stdout.strip().splitlines():
                if f.strip():
                    files_to_check.add(f.strip())

        for rel_file in files_to_check:
            fp = workspace_path / rel_file
            if fp.is_file() and not fp.is_symlink():
                try:
                    if fp.stat().st_size < 10 * 1024 * 1024:
                        content = fp.read_bytes()
                        if _has_unresolved_conflict_markers(content):
                            conflicted.add(rel_file)
                except Exception:
                    pass
    except Exception:
        pass

    return sorted(list(conflicted))


def check_unresolved_conflicts_safe(workspace_path: Path) -> tuple[bool, List[str], str]:
    """Fail-safe wrapper around :func:`check_unresolved_conflicts` for the dispatch hot path.

    Returns:
        tuple[bool, List[str], str]: (verified, conflicted_files, error_message).

        * ``verified=True``  - the check ran cleanly; ``conflicted_files`` is the
          (possibly empty) list of files with unresolved conflicts/markers.
        * ``verified=False`` - the authoritative git query raised; the worktree
          could NOT be verified clean. ``conflicted_files`` is ``[]`` and
          ``error_message`` explains why. Callers MUST treat ``verified=False``
          as "do not auto-merge / do not advance" (fail-closed), NOT as "clean".
    """
    try:
        return True, check_unresolved_conflicts(workspace_path), ""
    except GitConflictCheckError as e:
        _log.warning("check_unresolved_conflicts_safe: could not verify %s: %s", workspace_path, e)
        return False, [], str(e)


def _unverifiable_result(error: str, label: str = "worktree conflict check") -> tuple[bool, List[str], str]:
    """Build a fail-closed ``(False, [...], msg)`` tuple for an unverifiable worktree."""
    files = ["(unverifiable)"]
    return False, files, f"{label} could not be verified (fail-closed): {error}"


def get_git_dir(workspace_path: Path) -> Optional[Path]:
    """Get the active git directory (.git or worktree git dir) for a workspace."""
    try:
        res = subprocess.run(
            ["git", "rev-parse", "--path-format=absolute", "--git-dir"],
            cwd=str(workspace_path), capture_output=True, text=True, timeout=5
        )
        if res.returncode == 0 and res.stdout.strip():
            p = Path(res.stdout.strip())
            if p.exists():
                return p
    except Exception:
        pass
    return None


def clean_stale_git_locks(workspace_path: Path, max_age_seconds: int = 15) -> List[Path]:
    """Find and clean stale git lock files (e.g. index.lock) in workspace git dir."""
    removed: List[Path] = []
    if not workspace_path or not workspace_path.exists():
        return removed
    git_dir = get_git_dir(workspace_path)
    if not git_dir or not git_dir.exists():
        return removed
    now = time.time()
    lock_names = ("index.lock", "MERGE_RR.lock", "HEAD.lock")
    for lock_name in lock_names:
        lock_file = git_dir / lock_name
        if lock_file.exists() and lock_file.is_file():
            try:
                age = now - lock_file.stat().st_mtime
                if age > max_age_seconds:
                    lock_file.unlink()
                    removed.append(lock_file)
                    _log.warning("Removed stale git lock file (%0.1fs old): %s", age, lock_file)
            except Exception as e:
                _log.debug("Failed to remove stale git lock %s: %s", lock_file, e)
    return removed


def pull_and_merge_main(
    workspace_path: Path,
    repo_path: Path,
    default_branch: Optional[str] = None
) -> tuple[bool, List[str], str]:
    """Pull and merge latest default branch (e.g. main) into the worktree branch.

    Returns:
        tuple[bool, List[str], str]: (success, list_of_conflicted_files, message)
    """
    if not workspace_path.exists():
        return False, [], f"Workspace path does not exist: {workspace_path}"

    clean_stale_git_locks(workspace_path)

    if not default_branch:
        default_branch = sync_repo_main(repo_path)

    # Check if worktree is already in an unmerged / conflict state.
    # Fail-closed: if the worktree cannot be verified clean, do NOT merge.
    existing_verified, existing_conflicts, existing_err = check_unresolved_conflicts_safe(workspace_path)
    if not existing_verified:
        return _unverifiable_result(existing_err, "pre-merge worktree conflict check")

    # Check if an in-progress merge exists (MERGE_HEAD)
    git_dir = get_git_dir(workspace_path)
    if git_dir and (git_dir / "MERGE_HEAD").exists():
        if existing_conflicts:
            return False, existing_conflicts, f"Worktree has in-progress merge with unresolved conflicts: {', '.join(existing_conflicts)}"
        # All conflicts resolved, conclude the merge before proceeding
        commit_res = subprocess.run(
            ["git", "commit", "--no-edit"],
            cwd=str(workspace_path), capture_output=True, text=True, timeout=30
        )
        if commit_res.returncode != 0:
            err = (commit_res.stderr or "").strip()
            return False, [], f"Failed to conclude existing merge: {err}"

    if existing_conflicts:
        return False, existing_conflicts, f"Worktree already has unresolved conflicts: {', '.join(existing_conflicts)}"

    # Determine target ref: prefer origin/<default_branch> if remote ref exists, else <default_branch>
    target_ref = f"origin/{default_branch}"
    ref_check = subprocess.run(
        ["git", "show-ref", "--verify", "--quiet", f"refs/remotes/{target_ref}"],
        cwd=str(workspace_path), timeout=5
    )
    if ref_check.returncode != 0:
        local_check = subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{default_branch}"],
            cwd=str(workspace_path), timeout=5
        )
        if local_check.returncode == 0:
            target_ref = default_branch
        else:
            return True, [], f"Default branch ref {target_ref} not found, skipping merge"

    # Check if target_ref is already an ancestor of HEAD
    ancestor_check = subprocess.run(
        ["git", "merge-base", "--is-ancestor", target_ref, "HEAD"],
        cwd=str(workspace_path), timeout=5
    )
    if ancestor_check.returncode == 0:
        return True, [], f"Branch is already up to date with {target_ref}"

    # Attempt merge with explicit -m message (omit --no-edit to avoid flag conflicts across git versions).
    merge_cmd = [
        "git",
        "merge",
        target_ref,
        "-m", f"Merge branch '{target_ref}' into task branch"
    ]
    merge_res = subprocess.run(
        merge_cmd,
        cwd=str(workspace_path),
        capture_output=True,
        text=True,
        timeout=15
    )

    if merge_res.returncode == 0:
        post_verified, post_conflicts, post_err = check_unresolved_conflicts_safe(workspace_path)
        if not post_verified:
            # Merge command reported success, but we cannot verify the worktree
            # is clean afterwards. Fail-closed: do not claim a clean merge.
            return _unverifiable_result(post_err, "post-merge worktree conflict check")
        if post_conflicts:
            return False, post_conflicts, f"Unresolved conflict markers in: {', '.join(post_conflicts)}"
        return True, [], f"Successfully merged {target_ref}"
    else:
        post_fail_verified, conflicted_files, post_fail_err = check_unresolved_conflicts_safe(workspace_path)
        err = (merge_res.stderr or "").strip() or (merge_res.stdout or "").strip()
        if not post_fail_verified:
            return _unverifiable_result(post_fail_err, f"post-failure worktree conflict check (merge with {target_ref} failed: {err})")
        if not conflicted_files and "conflict" not in err.lower():
            return False, [], f"Git merge execution failed (not a conflict): {err}"
        return False, conflicted_files, f"Merge conflict with {target_ref}: {err}"


def digest_reviewer_git_context(
    workspace_path: Path,
    branch_name: Optional[str] = None,
    max_diff_lines: int = 100,
    max_diff_chars: int = 4000
) -> str:
    """Extract pre-digested commits, diffstat, and code diff for reviewer prompt.

    Pre-computes git diffs and commit summaries in Python before waking zf-reviewer,
    eliminating multi-turn git exploration tool calls and saving substantial LLM tokens.
    """
    if not workspace_path.exists():
        return ""

    try:
        git_check = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            timeout=5
        )
        if git_check.returncode != 0 or git_check.stdout.strip() != "true":
            return ""
    except Exception:
        return ""

    default_branch = get_default_branch(workspace_path)
    base_ref = f"origin/{default_branch}"
    try:
        verify_remote = subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", f"refs/remotes/{base_ref}"],
            cwd=str(workspace_path), timeout=5
        )
        if verify_remote.returncode != 0:
            verify_local = subprocess.run(
                ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{default_branch}"],
                cwd=str(workspace_path), timeout=5
            )
            base_ref = default_branch if verify_local.returncode == 0 else "HEAD~1"
    except Exception:
        base_ref = "HEAD~1"

    # Find merge base between HEAD and base_ref
    merge_base = base_ref
    try:
        mb_res = subprocess.run(
            ["git", "merge-base", "HEAD", base_ref],
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            timeout=5
        )
        if mb_res.returncode == 0 and mb_res.stdout.strip():
            merge_base = mb_res.stdout.strip()
    except Exception:
        pass

    diff_range = f"{merge_base}..HEAD" if merge_base else "HEAD~1..HEAD"

    # 1. Commit log on branch
    log_summary = ""
    try:
        log_res = subprocess.run(
            ["git", "log", "-n", "10", "--oneline", diff_range],
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            timeout=5
        )
        if log_res.returncode == 0:
            log_summary = log_res.stdout.strip()
    except Exception:
        pass

    # Pathspec exclusions to avoid token explosion on auto-generated / lock / minified files
    excluded_diff_pathspecs = [
        ":!*.lock",
        ":!*package-lock.json",
        ":!*pnpm-lock.yaml",
        ":!*yarn.lock",
        ":!*.min.*",
        ":!*.map",
        ":!*.svg",
    ]

    # 2. Diffstat
    diffstat = ""
    try:
        stat_res = subprocess.run(
            ["git", "diff", "--stat", diff_range, "--", *excluded_diff_pathspecs],
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            timeout=5
        )
        if stat_res.returncode == 0 and stat_res.stdout.strip():
            diffstat = stat_res.stdout.strip()
        else:
            stat_fallback = subprocess.run(
                ["git", "diff", "--stat", "HEAD", "--", *excluded_diff_pathspecs],
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
                timeout=5
            )
            if stat_fallback.returncode == 0:
                diffstat = stat_fallback.stdout.strip()
    except Exception:
        pass

    # 3. Code Diff
    diff_content = ""
    try:
        diff_res = subprocess.run(
            ["git", "diff", "-U2", diff_range, "--", *excluded_diff_pathspecs],
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            timeout=5
        )
        raw_diff = diff_res.stdout.strip() if diff_res.returncode == 0 else ""
        if not raw_diff:
            diff_fallback = subprocess.run(
                ["git", "diff", "-U2", "HEAD", "--", *excluded_diff_pathspecs],
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
                timeout=5
            )
            raw_diff = diff_fallback.stdout.strip() if diff_fallback.returncode == 0 else ""

        if raw_diff:
            lines = raw_diff.splitlines()
            is_truncated = False
            if len(lines) > max_diff_lines:
                raw_diff = "\n".join(lines[:max_diff_lines])
                is_truncated = True
            if len(raw_diff) > max_diff_chars:
                raw_diff = raw_diff[:max_diff_chars]
                is_truncated = True
            if is_truncated:
                raw_diff += "\n... [diff truncated for token efficiency; inspect remaining diff with git diff in workspace]"
            diff_content = raw_diff
    except Exception:
        pass

    # 4. Check uncommitted modifications if any
    status_summary = ""
    try:
        status_res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            timeout=5
        )
        if status_res.returncode == 0 and status_res.stdout.strip():
            status_summary = status_res.stdout.strip()
    except Exception:
        pass

    if not log_summary and not diffstat and not diff_content:
        return ""

    sections = [
        "### 🔍 Pre-Digested PR Changes (Zero-Token Ingested)",
        f"- **Target Base Branch:** `{default_branch}`"
    ]
    if log_summary:
        sections.append(f"#### Commits on Feature Branch:\n```\n{log_summary}\n```")
    if diffstat:
        sections.append(f"#### Changed Files (Diffstat):\n```\n{diffstat}\n```")
    if diff_content:
        sections.append(f"#### Code Changes (Diff):\n```diff\n{diff_content}\n```")
    if status_summary:
        sections.append(f"#### Uncommitted Modifications:\n```\n{status_summary}\n```")

    return "\n\n".join(sections)
 
 
def digest_board_memories_context(
    board_slug: Optional[str],
    db_path: Optional[str] = None,
    limit: int = 8
) -> str:
    """Extract pre-digested repository memories, conventions, and gotchas for agent worker prompt.

    Pre-injects relevant repository knowledge learned from prior tasks directly into the agent
    prompt to prevent repeat mistakes and align code style with repository conventions.
    """
    if not board_slug:
        return ""

    target_db = Path(db_path or os.environ.get("ZEROFACTORY_DB") or get_db_path())
    if not target_db.exists():
        return ""

    try:
        with sqlite3.connect(str(target_db), timeout=2.0) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            rows = cur.execute(
                """
                SELECT category, content, tags, author
                FROM board_memories
                WHERE board_slug = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (board_slug, limit)
            ).fetchall()

            if not rows:
                return ""

            lines = ["🧠 REPOSITORY KNOWLEDGE & CONVENTIONS (Learned from prior tasks):"]
            for r in rows:
                cat = r["category"] or "general"
                content = (r["content"] or "").strip().replace("\n", " ")
                if len(content) > 200:
                    content = content[:197] + "..."
                tag_str = ""
                try:
                    tags = json.loads(r["tags"] or "[]")
                    if tags and isinstance(tags, list):
                        tag_str = f" [tags: {', '.join(tags)}]"
                except Exception:
                    pass
                lines.append(f"- [{cat}] {content}{tag_str}")

            lines.append("Please adhere to these conventions and avoid known gotchas during execution.")
            return "\n".join(lines)
    except Exception as e:
        _log.debug("Could not digest board memories for %s: %s", board_slug, e)
        return ""


def extract_gh_repo_info(pr_url: str) -> Optional[tuple[str, str, int]]:
    """Parse owner, repo, and pull number from a GitHub PR URL."""
    if not pr_url:
        return None
    match = re.match(r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)", pr_url)
    if not match:
        return None
    return match.group(1), match.group(2), int(match.group(3))


def fetch_pr_review_comments(
    repo_path: Path,
    pr_url: Optional[str] = None,
    task_id: Optional[str] = None,
    pr_data: Optional[Dict[str, Any]] = None,
    exclude_authors: Optional[set[str]] = None,
    additional_reviewer_usernames: Optional[set[str]] = None,
) -> List[Dict[str, Any]]:
    """Fetch all types of review comments for a GitHub PR:
    1. Inline diff review comments (/pulls/{pr}/comments)
    2. Review summaries and states (/pulls/{pr}/reviews)
    3. PR issue/conversation comments (/issues/{pr}/comments)
    4. Code suggestions inside comments

    Only feedback from repository owners, members, collaborators, or the
    board's explicit additional-reviewer allowlist is returned. This prevents
    unrelated PR participants from changing an automation task's disposition.

    Returns a standardized list of comment dicts.
    """
    if os.environ.get("ZEROFACTORY_SKIP_GIT"):
        return []

    if exclude_authors is None:
        exclude_authors = {"github-actions[bot]", "web-flow"}
    trusted_associations = {"OWNER", "MEMBER", "COLLABORATOR"}
    additional_reviewers = {
        username.strip().lstrip("@").lower()
        for username in (additional_reviewer_usernames or set())
        if username and username.strip()
    }

    def is_excluded_author(author: str) -> bool:
        """Exclude automation from actionable review feedback.

        Deployment/status bots post ordinary PR conversation comments.  Those
        comments must not undo an explicit reviewer approval and send the task
        back to the builder.
        """
        normalized = (author or "").lower()
        return not normalized or normalized in exclude_authors or normalized.endswith("[bot]")

    def is_trusted_reviewer(author: str, association: str = "") -> bool:
        """Return whether a non-bot PR participant may control task routing."""
        normalized = (author or "").lower()
        return (
            not is_excluded_author(normalized)
            and (
                normalized in additional_reviewers
                or (association or "").upper() in trusted_associations
            )
        )

    comments: List[Dict[str, Any]] = []
    seen_ids: set[str] = set()

    # If pr_url is not provided, try to get from pr_data or gh pr view
    if not pr_url and pr_data:
        pr_url = pr_data.get("url")

    info = extract_gh_repo_info(pr_url or "")
    if not info and repo_path and task_id:
        try:
            res = subprocess.run(
                ["gh", "pr", "view", f"task/{task_id}", "--json", "url"],
                cwd=str(repo_path), capture_output=True, text=True, timeout=10
            )
            if res.returncode == 0:
                url_val = json.loads(res.stdout).get("url") or ""
                info = extract_gh_repo_info(url_val)
        except Exception:
            pass

    # 1. Check pr_data if provided (e.g. from gh pr view --json reviews,comments)
    if pr_data:
        for rev in pr_data.get("reviews", []):
            author = (rev.get("author") or {}).get("login") or rev.get("user", {}).get("login") or ""
            association = rev.get("authorAssociation") or rev.get("author_association") or ""
            body = (rev.get("body") or "").strip()
            state = rev.get("state") or ""
            rev_id = str(rev.get("id") or "")
            cid = f"review_{rev_id}"
            if cid not in seen_ids and is_trusted_reviewer(author, association):
                if body or state == "CHANGES_REQUESTED":
                    seen_ids.add(cid)
                    comments.append({
                        "comment_id": cid,
                        "type": "review_summary",
                        "author": author,
                        "state": state,
                        "body": body or f"Review submitted with state: {state}",
                        "path": None,
                        "line": None,
                        "diff_hunk": None,
                        "suggestion": None,
                        "created_at": rev.get("submittedAt") or rev.get("submitted_at") or ""
                    })

        for com in pr_data.get("comments", []):
            author = (com.get("author") or {}).get("login") or com.get("user", {}).get("login") or ""
            association = com.get("authorAssociation") or com.get("author_association") or ""
            body = (com.get("body") or "").strip()
            com_id = str(com.get("id") or "")
            cid = f"issue_{com_id}"
            if cid not in seen_ids and is_trusted_reviewer(author, association):
                if body and "Automated PR for task" not in body:
                    seen_ids.add(cid)
                    comments.append({
                        "comment_id": cid,
                        "type": "pr_comment",
                        "author": author,
                        "state": "COMMENTED",
                        "body": body,
                        "path": None,
                        "line": None,
                        "diff_hunk": None,
                        "suggestion": None,
                        "created_at": com.get("createdAt") or com.get("created_at") or ""
                    })

    if not info or os.environ.get("ZEROFACTORY_SKIP_GH_API"):
        return comments

    owner, repo, pr_num = info

    # 2. Fetch inline diff review comments via GitHub REST API
    try:
        res = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}/pulls/{pr_num}/comments"],
            cwd=str(repo_path), capture_output=True, text=True, timeout=5
        )
        if res.returncode == 0:
            raw_inline = json.loads(res.stdout)
            if isinstance(raw_inline, list):
                for item in raw_inline:
                    cid = f"inline_{item.get('id')}"
                    if cid in seen_ids:
                        continue
                    author = item.get("user", {}).get("login") or ""
                    if not is_trusted_reviewer(author, item.get("author_association") or ""):
                        continue
                    body = (item.get("body") or "").strip()
                    if not body:
                        continue

                    suggestion = None
                    sugg_match = re.search(r"```suggestion\r?\n(.*?)\r?\n```", body, re.DOTALL)
                    if sugg_match:
                        suggestion = sugg_match.group(1)

                    seen_ids.add(cid)
                    comments.append({
                        "comment_id": cid,
                        "type": "inline_review",
                        "author": author,
                        "state": "COMMENTED",
                        "body": body,
                        "path": item.get("path"),
                        "line": item.get("line") or item.get("original_line"),
                        "start_line": item.get("start_line") or item.get("original_start_line"),
                        "diff_hunk": item.get("diff_hunk"),
                        "suggestion": suggestion,
                        "created_at": item.get("created_at") or ""
                    })
    except Exception as e:
        _log.debug("Failed to fetch inline review comments for %s/%s#%s: %s", owner, repo, pr_num, e)

    # 3. Fetch PR reviews via GitHub REST API if not already retrieved
    try:
        res = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}/pulls/{pr_num}/reviews"],
            cwd=str(repo_path), capture_output=True, text=True, timeout=5
        )
        if res.returncode == 0:
            raw_reviews = json.loads(res.stdout)
            if isinstance(raw_reviews, list):
                for item in raw_reviews:
                    cid = f"review_{item.get('id')}"
                    if cid in seen_ids:
                        continue
                    author = item.get("user", {}).get("login") or ""
                    if not is_trusted_reviewer(author, item.get("author_association") or ""):
                        continue
                    body = (item.get("body") or "").strip()
                    state = item.get("state") or ""
                    if body or state == "CHANGES_REQUESTED":
                        seen_ids.add(cid)
                        comments.append({
                            "comment_id": cid,
                            "type": "review_summary",
                            "author": author,
                            "state": state,
                            "body": body or f"Review submitted with state: {state}",
                            "path": None,
                            "line": None,
                            "diff_hunk": None,
                            "suggestion": None,
                            "created_at": item.get("submitted_at") or ""
                        })
    except Exception as e:
        _log.debug("Failed to fetch reviews for %s/%s#%s: %s", owner, repo, pr_num, e)

    # 4. Fetch PR conversation/issue comments if not already retrieved
    try:
        res = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}/issues/{pr_num}/comments"],
            cwd=str(repo_path), capture_output=True, text=True, timeout=5
        )
        if res.returncode == 0:
            raw_issues = json.loads(res.stdout)
            if isinstance(raw_issues, list):
                for item in raw_issues:
                    cid = f"issue_{item.get('id')}"
                    if cid in seen_ids:
                        continue
                    author = item.get("user", {}).get("login") or ""
                    if not is_trusted_reviewer(author, item.get("author_association") or ""):
                        continue
                    body = (item.get("body") or "").strip()
                    if body and "Automated PR for task" not in body:
                        seen_ids.add(cid)
                        comments.append({
                            "comment_id": cid,
                            "type": "pr_comment",
                            "author": author,
                            "state": "COMMENTED",
                            "body": body,
                            "path": None,
                            "line": None,
                            "diff_hunk": None,
                            "suggestion": None,
                            "created_at": item.get("created_at") or ""
                        })
    except Exception as e:
        _log.debug("Failed to fetch issue comments for %s/%s#%s: %s", owner, repo, pr_num, e)

    return comments


def format_task_comment_body(comment: Dict[str, Any]) -> str:
    """Format a GitHub PR comment into a descriptive task comment."""
    ctype = comment.get("type", "")
    body = comment.get("body", "")
    path = comment.get("path")
    line = comment.get("line")
    start_line = comment.get("start_line")
    suggestion = comment.get("suggestion")

    parts = []
    if ctype == "inline_review" and path:
        # GitHub leaves `line` null (keeping only `start_line`/`start_side`) for
        # comments anchored to lines no longer present in the diff. Guard both
        # sides so a None value is never interpolated into the anchor.
        line_str = (
            f":L{start_line}-{line}"
            if (start_line and line and start_line != line)
            else (
                f":L{line}"
                if line
                else (f":L{start_line}" if start_line else "")
            )
        )
        parts.append(f"**[GitHub Review Comment on `{path}{line_str}`]**")
    elif ctype == "review_summary":
        state = comment.get("state", "COMMENTED")
        parts.append(f"**[GitHub PR Review ({state})]**")
    else:
        parts.append("**[GitHub PR Comment]**")

    parts.append(body)
    if suggestion:
        parts.append(f"\n```suggestion\n{suggestion}\n```")

    return "\n".join(parts)


def is_reviewer_approval_comment(comment_body: str, state: Optional[str] = None) -> bool:
    """Return True if a PR review comment or review summary represents an approval verdict.

    Handles cases where GitHub prevents self-approval (PR author matches reviewer CLI identity)
    and the reviewer submits their approval verdict as a review comment.
    """
    if state == "APPROVED":
        return True
    body = (comment_body or "").strip()
    if not body:
        return False
    lower = body.lower()

    has_approval_signal = any(phrase in lower for phrase in [
        "[reviewer feedback]",
        "reviewer feedback",
        "verdict: approve",
        "verdict: approved",
        "verdict: **approve**",
        "approved — no changes requested",
        "approved - no changes requested",
        "approved for human review",
        "no changes requested",
        "approving for human review",
        "status: approved",
    ]) or lower.startswith("approved")

    clean_for_changes = (
        lower
        .replace("no changes requested", "")
        .replace("without changes requested", "")
        .replace("zero changes requested", "")
    )
    has_changes_requested = any(phrase in clean_for_changes for phrase in [
        "changes requested",
        "changes needed",
        "requires changes",
        "please fix",
        "must be fixed",
        "needs work",
        "action required",
        "unresolved conflict",
    ])

    return has_approval_signal and not has_changes_requested


def _inject_langfuse_env(env: Dict[str, str], conn_or_cursor: Any = None) -> None:
    """Inject active Langfuse credentials and configuration into worker subprocess environment."""
    try:
        if conn_or_cursor is None:
            from dashboard.plugin_api import get_db_conn
            with get_db_conn() as conn:
                settings = load_settings(conn)
        else:
            settings = load_settings(conn_or_cursor)

        if settings.get("langfuse_enabled"):
            env["HERMES_LANGFUSE_PUBLIC_KEY"] = str(settings.get("langfuse_public_key") or "").strip()
            env["HERMES_LANGFUSE_SECRET_KEY"] = str(settings.get("langfuse_secret_key") or "").strip()
            env["HERMES_LANGFUSE_BASE_URL"] = str(settings.get("langfuse_base_url") or "https://cloud.langfuse.com").strip()
            env["HERMES_LANGFUSE_CAPTURE"] = str(settings.get("langfuse_capture_mode") or "sanitized").strip()
            env["HERMES_LANGFUSE_ENV"] = str(settings.get("langfuse_env") or "zerofactory").strip()
        else:
            for k in ("HERMES_LANGFUSE_PUBLIC_KEY", "HERMES_LANGFUSE_SECRET_KEY", "HERMES_LANGFUSE_BASE_URL", "HERMES_LANGFUSE_CAPTURE", "HERMES_LANGFUSE_ENV"):
                env.pop(k, None)
    except Exception as e:
        _log.debug("Could not inject Langfuse env: %s", e)


def spawn_agent_worker(
    task_id: str,
    title: str,
    description: str,
    priority: str,
    assignee: str,
    workspace_path: Optional[str],
    branch_name: Optional[str],
    board_slug: Optional[str] = None
) -> tuple[Optional[int], Optional[str]]:
    """Spawn an isolated hermes worker subprocess for the assigned specialist agent."""
    if os.environ.get("ZEROFACTORY_SKIP_WORKER_SPAWN"):
        return None, None

    assignee = normalize_assignee(assignee)
    import shutil
    local_hermes = Path.home() / ".local" / "bin" / "hermes"
    hermes_bin = (
        os.environ.get("HERMES_BIN")
        or shutil.which("hermes")
        or (str(local_hermes) if local_hermes.exists() else "hermes")
    )

    workdir = workspace_path if (workspace_path and Path(workspace_path).exists()) else os.getcwd()
    memories_digest = digest_board_memories_context(board_slug)
    memories_block = f"{memories_digest}\n\n" if memories_digest else ""

    if assignee == "zf-reviewer":
        pre_digested_git = digest_reviewer_git_context(Path(workdir), branch_name)
        pre_digested_block = f"\n{pre_digested_git}\n\n" if pre_digested_git else "\n"
        prompt = (
            f"Task ID: {task_id}\n"
            f"Title: {title}\n"
            f"Priority: {priority}\n"
            f"Assigned Role: {assignee}\n\n"
            f"Description:\n{description or 'No description provided.'}\n\n"
            f"Workspace: {workdir}\n"
            f"Git Branch: {branch_name or 'main'}\n\n"
            f"{memories_block}"
            f"{pre_digested_block}"
            f"Your goal as Reviewer:\n"
            f"1. Examine the Pull Request branch changes ({branch_name or 'main'}) for correctness, edge cases, test coverage, and security (review the pre-digested diff above).\n"
            f"2. Run automated test suites and linters in your workspace ({workdir}).\n"
            f"3. Submit your review decision on GitHub (`gh pr review --approve` or `gh pr review --request-changes`).\n"
            f"4. Continuous Learning & Repository Knowledge:\n"
            f"   - If you catch a recurring mistake, testing gotcha, or project convention that future tasks should follow, record it!\n"
            f"   - In your review comment or summary, include a line: `GOTCHA: <rule>` or `CONVENTION: <rule>` (the system will auto-record it).\n"
            f"   - Or run: `hermes zerofactory memory add --board {board_slug or 'default'} \"<rule>\" --category <gotcha|convention>`.\n"
            f"5. When finished:\n"
            f"   - If approved: run `hermes zerofactory block {task_id} --reason 'Human Review & Merge'` (the dispatcher will automatically move the task to 'done' once the PR is merged on GitHub; DO NOT mark done yourself).\n"
            f"   - If changes are requested: run `hermes zerofactory block {task_id} --reason 'changes-requested'` (the dispatcher will route it back to the builder).\n"
            f"6. Provide a clear review summary.\n"
        )
    else:
        # Fail-closed: if the worktree cannot be verified clean, treat it as a
        # potential conflict and route to the conflict-resolution prompt rather
        # than the generic implement prompt (an unverifiable worktree must not
        # be advanced as if it were clean).
        conflict_check_verified = True
        _files: List[str] = []
        _cc_err = ""
        try:
            conflict_check_verified, _files, _cc_err = check_unresolved_conflicts_safe(Path(workdir))
        except Exception as e:  # defensive: safe wrapper should not raise
            conflict_check_verified, _cc_err = False, str(e)
        has_conflict = (
            "[pr conflict]" in title.lower()
            or "[merge conflict]" in title.lower()
            or (not conflict_check_verified and Path(workdir).exists())
            or (conflict_check_verified and Path(workdir).exists() and bool(_files))
        )
        if has_conflict:
            if conflict_check_verified and Path(workdir).exists():
                conflicted_files = _files
            elif not conflict_check_verified:
                conflicted_files = []  # unverifiable -> fall back to marker scan / git status
            else:
                conflicted_files = []
            file_list_str = (
                "\n".join(f"- {f}" for f in conflicted_files)
                if conflicted_files
                else "- (Unverifiable or no unmerged files; check `git status` for unmerged files)"
            )
            prompt = (
                f"Task ID: {task_id}\n"
                f"Title: {title}\n"
                f"Priority: {priority}\n"
                f"Assigned Role: {assignee}\n\n"
                f"Description:\n{description or 'No description provided.'}\n\n"
                f"Workspace: {workdir}\n"
                f"Git Branch: {branch_name or 'main'}\n\n"
                f"{memories_block}"
                f"🚨 CRITICAL: MERGE CONFLICT DETECTED WITH MAIN BRANCH\n"
                f"The latest changes from the main branch conflict with this task branch.\n"
                f"Conflicted files:\n{file_list_str}\n\n"
                f"Your goal as Builder (Conflict Resolution):\n"
                f"1. Inspect each conflicted file in {workdir}.\n"
                f"2. Resolve all conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`), reconciling incoming changes with your task implementation.\n"
                f"3. Ensure NO conflict markers remain in any files.\n"
                f"4. Apply targeted edits (search/replace or localized chunk edits) rather than rewriting entire files to conserve tokens.\n"
                f"5. Run the repository test suites and linters to verify everything compiles and passes cleanly.\n"
                f"6. Hand off for re-review:\n"
                f"   hermes zerofactory move {task_id} blocked --reason \"review-required\"\n\n"
                f"NOTE: Do NOT run git commands (git add/commit/push). The factory dispatcher automatically verifies clean conflict resolution and commits with 'fix(merge): resolve merge conflicts with main' upon handoff.\n"
            )
        else:
            # Check if there are review comments for this task in task_comments
            review_comments_prompt = ""
            try:
                _db = Path(os.environ.get("ZEROFACTORY_DB") or get_db_path())
                if _db.exists():
                    with sqlite3.connect(str(_db)) as _c:
                        _c.row_factory = sqlite3.Row
                        _cur = _c.cursor()
                        _cur.execute(
                            "SELECT author, body, created_at FROM task_comments WHERE task_id = ? ORDER BY created_at ASC",
                            (task_id,)
                        )
                        _rows = _cur.fetchall()
                        _rev_rows = [
                            r for r in _rows
                            if "[github review" in r["body"].lower()
                            or "[github pr" in r["body"].lower()
                            or r["author"] in ("zf-reviewer", "reviewer")
                            or r["author"] != assignee
                        ]
                        if _rev_rows:
                            _cmt_blocks = []
                            for idx, r in enumerate(_rev_rows, 1):
                                _cmt_blocks.append(f"### Review Comment #{idx} (by @{r['author']}):\n{r['body']}")
                            review_comments_prompt = (
                                "🚨 CRITICAL: PULL REQUEST REVIEW COMMENTS TO ADDRESS\n"
                                "The reviewer / human has submitted the following review comments on your Pull Request.\n"
                                "You must address EVERY review comment in your implementation:\n\n"
                                + "\n\n".join(_cmt_blocks)
                                + "\n\n"
                            )
            except Exception as e:
                _log.debug("Could not inspect task_comments for worker prompt: %s", e)

            goal_instructions = (
                f"Your goal as Builder (Fix Review Comments):\n"
                f"1. Carefully address every review comment listed above in your workspace ({workdir}).\n"
                f"2. Apply targeted, concise code edits rather than rewriting or bloating files.\n"
                f"3. Run automated tests and linters in your workspace to verify correctness.\n"
                f"4. When finished, hand off for re-review:\n"
                f"   hermes zerofactory move {task_id} blocked --reason \"review-required\"\n"
                f"5. Provide a summary of how each review comment was resolved.\n\n"
                f"NOTE: Do NOT run git commands (git add/commit/push/checkout). The factory dispatcher automatically stages, commits, and pushes your fixes to the PR upon handoff.\n"
            ) if review_comments_prompt else (
                f"Your goal:\n"
                f"1. Read the task requirements and explore the codebase in your workspace ({workdir}).\n"
                f"2. Implement the required changes cleanly, adhering to repository patterns.\n"
                f"   - TOKEN EFFICIENCY: Apply targeted search/replace or hunk edits instead of rewriting entire files.\n"
                f"3. Verify your changes with tests, linters, or typechecks.\n"
                f"4. When finished, mark the task as complete using:\n"
                f"   hermes zerofactory move {task_id} done\n"
                f"   (or if human review or external dependencies are required, run:\n"
                f"   hermes zerofactory move {task_id} blocked --reason \"review-required\")\n"
                f"5. Provide a summary of your changes.\n\n"
                f"NOTE: Do NOT run git commands (git add/commit/push/checkout). Your worktree is already synced with latest main. The factory dispatcher automatically stages, commits, and opens PRs upon task completion.\n"
            )

            prompt = (
                f"Task ID: {task_id}\n"
                f"Title: {title}\n"
                f"Priority: {priority}\n"
                f"Assigned Role: {assignee}\n\n"
                f"Description:\n{description or 'No description provided.'}\n\n"
                f"Workspace: {workdir}\n"
                f"Git Branch: {branch_name or 'main'}\n\n"
                f"{memories_block}"
                f"{review_comments_prompt}"
                f"{goal_instructions}"
            )

    cmd = [
        hermes_bin,
        "-p", assignee,
        "--yolo",
        "--cli",
        "--accept-hooks",
        "chat",
        "-q", prompt
    ]

    log_dir = Path.home() / ".hermes" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file_path = log_dir / f"worker_{task_id}.log"

    env = os.environ.copy()
    env.pop("HERMES_KANBAN_TASK", None)
    env["HERMES_KANBAN_STOP_NUDGE"] = "0"
    env["HERMES_KANBAN_WORKSPACE"] = str(workdir)
    env["TERMINAL_CWD"] = str(workdir)
    env["HERMES_PROFILE"] = assignee
    profile_home = Path.home() / ".hermes" / "profiles" / assignee
    if profile_home.exists():
        env["HERMES_HOME"] = str(profile_home)
    env["PYTHONUNBUFFERED"] = "1"
    _inject_langfuse_env(env)

    try:
        log_f = open(log_file_path, "ab")
        try:
            os.utime(log_file_path, None)
        except Exception:
            pass
        spawn_time = time.time()
        proc = subprocess.Popen(
            cmd,
            cwd=str(workdir),
            stdin=subprocess.DEVNULL,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
        log_f.close()
        _active_workers[task_id] = proc
        _log.info("Spawned %s worker for task %s (PID: %d, cwd: %s)", assignee, task_id, proc.pid, workdir)

        # Detect session_id from profile's state.db (only if started around this spawn).
        # Resolution goes through the shared helper so the dispatcher and the
        # dashboard agree on which state.db a profile owns (per-profile ->
        # legacy-un-prefixed -> plugin-relative -> global ~/.hermes/state.db).
        session_id = None
        state_db_path = resolve_profile_state_db(assignee)
        if state_db_path is not None and state_db_path.exists():
            resolved_state = state_db_path.resolve()
            uri = resolved_state.as_uri() + "?mode=ro"
            # Poll up to 3 seconds for Hermes to initialize and record its session
            poll_attempts = 1 if os.environ.get("ZEROFACTORY_SKIP_WORKER_SPAWN") else 6
            for _ in range(poll_attempts):
                try:
                    try:
                        s_conn = sqlite3.connect(uri, uri=True, timeout=2.0)
                    except Exception:
                        s_conn = sqlite3.connect(str(resolved_state), timeout=2.0)
                    with closing(s_conn) as s_conn:
                        s_cur = s_conn.cursor()
                        s_cur.execute(
                            "SELECT id FROM sessions WHERE started_at >= ? ORDER BY started_at DESC LIMIT 1",
                            (spawn_time - 2.0,)
                        )
                        s_row = s_cur.fetchone()
                        if s_row:
                            session_id = s_row[0]
                            break
                except Exception:
                    pass
                if proc.poll() is not None:
                    break
                time.sleep(0.5)

        return proc.pid, session_id
    except Exception as e:
        _log.error("Failed to spawn %s worker for task %s: %s", assignee, task_id, e)
        return None, None


def terminate_process_group(proc: Optional[subprocess.Popen], pid: Optional[int], grace: float = 2.0) -> None:
    """Terminate a worker's ENTIRE process group (session), not just the child.

    All Zero Factory spawn sites run children with ``start_new_session=True``
    so the tree survives the spawner; the direct child (the ``hermes`` CLI
    wrapper) spawns its own descendants (the agent loop, git, npm, network
    subprocesses). Signalling only the direct child (``proc.terminate()`` /
    ``os.kill(pid, ...)``) left the whole descendant tree orphaned: it kept
    consuming LLM API credits, could write to the worktree/GitHub after the
    task had already transitioned, and (when a descendant held the combined
    stdout log pipe open) blocked the dispatcher on ``proc.wait(timeout=...)``.

    Because ``start_new_session=True`` puts the child in a NEW session whose
    PGID equals its PID, ``os.killpg`` on that group reaches every descendant.
    Linux-only (``os.killpg``); Windows is not a target platform.

    Fail-open contract (matches the previous child-only termination path):
    every failure mode — dead/unknown group (``ProcessLookupError``),
    permission problems, recycled PIDs — is logged and swallowed; this never
    raises. A cheap pre-flight ``killpg(pgid, 0)`` probes the group without
    delivering a signal and guards against signalling a recycled PGID.
    """
    pgid: Optional[int] = None
    if proc is not None and isinstance(proc.pid, int):
        try:
            pgid = os.getpgid(proc.pid)
        except (AttributeError, OSError):
            pgid = None
    if pgid is None and isinstance(pid, int) and pid > 0:
        # PID-only fallback (metadata path, no live handle): start_new_session
        # guarantees PGID == PID, so signal the group via the child's PID.
        pgid = pid

    if pgid is None:
        _log.debug("terminate_process_group: no resolvable process group (proc=%s, pid=%s)", proc, pid)
        return

    # Cheap guard: make sure the group still exists before signalling (avoids
    # racing a recycled PGID). killpg(..., 0) probes without delivering a
    # signal; a recycled/unknown group raises ProcessLookupError here.
    try:
        os.killpg(pgid, 0)
    except ProcessLookupError:
        _log.debug("terminate_process_group: group %s no longer exists; nothing to do", pgid)
        return
    except OSError as e:
        # EPERM (we lack permission for the group) still proves it exists —
        # proceed and let the TERM/KILL attempts handle it.
        _log.debug("terminate_process_group: probe on group %s failed: %s", pgid, e)

    try:
        os.killpg(pgid, signal.SIGTERM)
    except (ProcessLookupError, OSError) as e:
        _log.debug("terminate_process_group: SIGTERM to group %s failed: %s", pgid, e)
        return

    if proc is not None and isinstance(proc.pid, int):
        try:
            proc.wait(timeout=grace)
            return  # group exited gracefully within the grace window
        except Exception:
            pass
    elif grace > 0:
        time.sleep(grace)

    try:
        os.killpg(pgid, signal.SIGKILL)
    except (ProcessLookupError, OSError) as e:
        # Group likely exited between the grace window and the SIGKILL — fine.
        _log.debug("terminate_process_group: SIGKILL to group %s failed: %s", pgid, e)

    if proc is not None and isinstance(proc.pid, int):
        try:
            proc.wait(timeout=5)
        except Exception:
            pass


def terminate_worker_process(proc: Optional[subprocess.Popen], pid: Optional[int]) -> None:
    """Safely terminate a worker process with SIGTERM then SIGKILL.

    Signals the worker's whole process group (session) rather than just the
    direct child, because all spawn sites use ``start_new_session=True`` and
    the ``hermes`` CLI wrapper spawns its own descendants. Fail-open: never
    raises. See ``terminate_process_group`` for details.
    """
    try:
        terminate_process_group(proc, pid)
    except Exception as e:  # defensive: the helper is fail-open, but never leak
        _log.debug("terminate_worker_process: group termination raised: %s", e)


def stop_task_worker(task_id: str, cursor: Optional[sqlite3.Cursor] = None) -> None:
    """Safely terminate any active worker process for a task.

    Invoked before git worktree removal or task transitions to prevent orphaned
    zombie processes from running in deleted directories, leaking resources,
    and corrupting plugin symlinks. Checks in-memory workers first, then falls
    back to metadata `worker_pid`. Idempotent and exception-safe.
    """
    proc = _active_workers.pop(task_id, None)
    pid = None
    if proc is not None:
        pid = proc.pid
    elif cursor:
        try:
            cursor.execute("SELECT metadata FROM tasks WHERE id = ?", (task_id,))
            row = cursor.fetchone()
            if row:
                raw_meta = row["metadata"] if hasattr(row, "keys") or isinstance(row, dict) else row[0]
                meta = json.loads(raw_meta or "{}")
                pid = meta.get("worker_pid")
        except Exception:
            pass
    terminate_worker_process(proc, pid)


def _mark_task_session_ended(meta: Dict[str, Any], now: int, final_status: str = "finished") -> Dict[str, Any]:
    """Helper to finalize the ongoing session entry in task metadata."""
    sessions = meta.get("sessions")
    if isinstance(sessions, list):
        for s in sessions:
            if isinstance(s, dict) and s.get("status") == "ongoing":
                s["status"] = final_status
                if not s.get("ended_at"):
                    s["ended_at"] = now
    return meta


def reap_active_workers(cursor: sqlite3.Cursor, now: int) -> int:
    """Check running tasks and reap finished, crashed, or stuck worker processes."""
    cursor.execute("SELECT id, title, metadata, updated_at, created_at FROM tasks WHERE status = 'running'")
    running_rows = cursor.fetchall()
    reaped = 0

    task_timeout = get_task_timeout_seconds()
    inactivity_timeout = get_inactivity_timeout_seconds()

    for row in running_rows:
        task_id = str(row["id"])
        meta = {}
        try:
            meta = json.loads(row["metadata"] or "{}")
        except Exception:
            pass

        proc = _active_workers.get(task_id)
        pid = meta.get("worker_pid") or (proc.pid if proc else None)

        # A task can be reassigned after its previous worker was stopped (for
        # example builder -> reviewer).  A persisted PID does not belong to the
        # newly assigned agent and must not turn that new run into a false
        # worker-loss failure before it has been dispatched.
        sessions = meta.get("sessions")
        has_ongoing_session = isinstance(sessions, list) and any(
            isinstance(session, dict) and session.get("status") == "ongoing"
            for session in sessions
        )
        if proc is None and pid and not has_ongoing_session:
            meta.pop("worker_pid", None)
            meta.pop("session_id", None)
            meta.pop("started_at", None)
            pid = None
            cursor.execute(
                "UPDATE tasks SET metadata = ? WHERE id = ?",
                (json.dumps(meta), task_id),
            )

        if proc is not None:
            retcode = proc.poll()
            if retcode is not None:
                _active_workers.pop(task_id, None)
                if retcode == 0:
                    meta = _mark_task_session_ended(meta, now, "finished")
                    meta.pop("worker_failure_retries", None)
                    meta.pop("last_worker_failure", None)
                    cursor.execute("UPDATE tasks SET status = 'done', metadata = ?, updated_at = ? WHERE id = ?", (json.dumps(meta), now, task_id))
                    cursor.execute(
                        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_done', 'Worker process completed successfully (exit 0)', ?)",
                        (task_id, now)
                    )
                    _log.info("Worker for task %s finished successfully (exit 0); moved to done", task_id)
                else:
                    meta = _mark_task_session_ended(meta, now, "failed")
                    fail_retries = int(meta.get("worker_failure_retries", 0)) + 1
                    meta["worker_failure_retries"] = fail_retries
                    meta["last_worker_failure"] = {"retcode": retcode, "failed_at": now}
                    max_worker_retries = get_max_worker_retries()
                    if fail_retries >= max_worker_retries:
                        meta["permanently_blocked"] = True
                        meta["blocked_reason"] = f"Worker process failed {fail_retries} times (limit {max_worker_retries})"
                        cursor.execute("UPDATE tasks SET status = 'blocked', metadata = ?, updated_at = ? WHERE id = ?", (json.dumps(meta), now, task_id))
                        cursor.execute(
                            "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, 'dispatcher', ?, ?)",
                            (task_id, f"Blocked: {meta['blocked_reason']}", now)
                        )
                        cursor.execute(
                            "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_failed_permanently', ?, ?)",
                            (task_id, f"Worker process failed with exit code {retcode} ({fail_retries}/{max_worker_retries} retries exceeded); task permanently blocked", now)
                        )
                        _log.warning("Worker for task %s permanently blocked after %d failures (code %d)", task_id, fail_retries, retcode)
                    else:
                        meta["blocked_reason"] = f"Worker process exited with code {retcode} (attempt {fail_retries}/{max_worker_retries})"
                        cursor.execute("UPDATE tasks SET status = 'blocked', metadata = ?, updated_at = ? WHERE id = ?", (json.dumps(meta), now, task_id))
                        cursor.execute(
                            "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, 'dispatcher', ?, ?)",
                            (task_id, f"Blocked: {meta['blocked_reason']}", now)
                        )
                        cursor.execute(
                            "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_failed', ?, ?)",
                            (task_id, f"Worker process exited with code {retcode} (attempt {fail_retries}/{max_worker_retries})", now)
                        )
                        _log.warning("Worker for task %s failed with exit code %d; moved to blocked", task_id, retcode)
                reaped += 1
                continue
        elif pid:
            try:
                os.kill(pid, 0)
            except OSError:
                meta = _mark_task_session_ended(meta, now, "lost")
                fail_retries = int(meta.get("worker_failure_retries", 0)) + 1
                meta["worker_failure_retries"] = fail_retries
                meta["last_worker_failure"] = {"retcode": -1, "reason": "PID not found", "failed_at": now}
                max_worker_retries = get_max_worker_retries()
                if fail_retries >= max_worker_retries:
                    meta["permanently_blocked"] = True
                    meta["blocked_reason"] = f"Worker lost {fail_retries} times (limit {max_worker_retries})"
                    cursor.execute("UPDATE tasks SET status = 'blocked', metadata = ?, updated_at = ? WHERE id = ?", (json.dumps(meta), now, task_id))
                    cursor.execute(
                        "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, 'dispatcher', ?, ?)",
                        (task_id, f"Blocked: {meta['blocked_reason']}", now)
                    )
                    cursor.execute(
                        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_failed_permanently', ?, ?)",
                        (task_id, f"Worker process PID {pid} not found ({fail_retries}/{max_worker_retries} retries exceeded); task permanently blocked", now)
                    )
                else:
                    meta["blocked_reason"] = f"Worker process PID {pid} not found (attempt {fail_retries}/{max_worker_retries})"
                    cursor.execute("UPDATE tasks SET status = 'blocked', metadata = ?, updated_at = ? WHERE id = ?", (json.dumps(meta), now, task_id))
                    cursor.execute(
                        "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, 'dispatcher', ?, ?)",
                        (task_id, f"Blocked: {meta['blocked_reason']}", now)
                    )
                    cursor.execute(
                        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_lost', ?, ?)",
                        (task_id, f"Worker process PID {pid} not found (attempt {fail_retries}/{max_worker_retries}); moved to blocked", now)
                    )
                _log.warning("Worker PID %d for task %s not found; moved to blocked", pid, task_id)
                reaped += 1
                continue

        # Check if running task exceeded overall timeout or inactivity threshold
        started_at = meta.get("started_at") or row["updated_at"] or row["created_at"] or now
        running_time = max(0, now - int(started_at))

        is_stuck = False
        stuck_reason = ""

        if running_time > task_timeout:
            is_stuck = True
            stuck_reason = f"Worker exceeded running timeout ({running_time}s > {task_timeout}s)"
        elif running_time > inactivity_timeout:
            idle_time = running_time
            log_path = Path.home() / ".hermes" / "logs" / f"worker_{task_id}.log"
            if log_path.exists():
                try:
                    mtime = int(log_path.stat().st_mtime)
                    if mtime > int(started_at):
                        idle_time = max(0, now - mtime)
                except Exception:
                    pass
            if idle_time > inactivity_timeout:
                is_stuck = True
                stuck_reason = f"Worker inactive with no updates for {idle_time}s (limit {inactivity_timeout}s)"

        if is_stuck:
            terminate_worker_process(proc, pid)
            _active_workers.pop(task_id, None)
            meta = _mark_task_session_ended(meta, now, "timed_out")
            fail_retries = int(meta.get("worker_failure_retries", 0)) + 1
            meta["worker_failure_retries"] = fail_retries
            meta["last_worker_failure"] = {"retcode": -9, "reason": stuck_reason, "failed_at": now}
            max_worker_retries = get_max_worker_retries()
            if fail_retries >= max_worker_retries:
                meta["permanently_blocked"] = True
                meta["blocked_reason"] = f"Worker timeout/inactivity {fail_retries} times (limit {max_worker_retries}): {stuck_reason}"
                cursor.execute("UPDATE tasks SET status = 'blocked', metadata = ?, updated_at = ? WHERE id = ?", (json.dumps(meta), now, task_id))
                cursor.execute(
                    "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, 'dispatcher', ?, ?)",
                    (task_id, f"Blocked: {meta['blocked_reason']}", now)
                )
                cursor.execute(
                    "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_timeout_permanently', ?, ?)",
                    (task_id, f"Task exceeded timeout/inactivity limit ({fail_retries}/{max_worker_retries}): {stuck_reason}; task permanently blocked", now)
                )
            else:
                meta["blocked_reason"] = f"{stuck_reason} (attempt {fail_retries}/{max_worker_retries})"
                cursor.execute("UPDATE tasks SET status = 'blocked', metadata = ?, updated_at = ? WHERE id = ?", (json.dumps(meta), now, task_id))
                cursor.execute(
                    "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, 'dispatcher', ?, ?)",
                    (task_id, f"Blocked: {meta['blocked_reason']}", now)
                )
                cursor.execute(
                    "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_timeout', ?, ?)",
                    (task_id, f"{stuck_reason} (attempt {fail_retries}/{max_worker_retries})", now)
                )
            _log.warning("Task %s reaped due to timeout/inactivity: %s; moved to blocked", task_id, stuck_reason)
            reaped += 1

    return reaped


def reap_active_scanners() -> int:
    """Clean up finished or exited scanner worker processes."""
    reaped = 0
    for slug, proc in list(_active_scanners.items()):
        if proc is not None:
            retcode = proc.poll()
            if retcode is not None:
                _active_scanners.pop(slug, None)
                reaped += 1
                _log.debug("Scanner process for board '%s' exited with code %d", slug, retcode)
    return reaped


def _running_cron_llm_jobs() -> int:
    """Count in-process Zero Factory cron LLM jobs (exclude No-Agent queue checks)."""
    try:
        from cron.scheduler import get_running_job_ids
        return sum(
            job_id == "zero-factory-daily-report" or job_id.startswith("zero-factory-improvement-scanner-")
            for job_id in get_running_job_ids()
        )
    except (ImportError, RuntimeError):
        return 0


def _global_llm_occupancy(running_tasks: int) -> int:
    """LLM workers currently tracked by this Zero Factory process."""
    try:
        from .builtin_cron import _active_cron_runs, reap_active_cron_runs
    except ImportError:
        from builtin_cron import _active_cron_runs, reap_active_cron_runs
    reap_active_cron_runs()
    return running_tasks + len(_active_scanners) + _running_cron_llm_jobs() + sum(
        job_id != "zero-factory-task-queue-check" for job_id in _active_cron_runs
    )


def spawn_board_scanner(board_slug: str, repo_path: Optional[Path] = None) -> Optional[int]:
    """Spawn an improvement scanner agent worker process for a specific board."""
    if os.environ.get("ZEROFACTORY_SKIP_WORKER_SPAWN") or os.environ.get("ZEROFACTORY_SKIP_SCANNER_SPAWN"):
        return None

    try:
        try:
            from .builtin_cron import is_cron_scheduler_enabled
        except ImportError:
            from builtin_cron import is_cron_scheduler_enabled  # type: ignore
        if not is_cron_scheduler_enabled():
            _log.debug("Cron scheduler is disabled in config; skipping scanner spawn for '%s'", board_slug)
            return None
    except Exception as e:
        _log.debug("Scanner cron scheduler check failed: %s", e)

    import shutil
    local_hermes = Path.home() / ".local" / "bin" / "hermes"
    hermes_bin = (
        os.environ.get("HERMES_BIN")
        or shutil.which("hermes")
        or (str(local_hermes) if local_hermes.exists() else "hermes")
    )
    job_id = f"zero-factory-improvement-scanner-{board_slug}"
    # Check if this scanner job is paused/disabled before running
    try:
        try:
            from .builtin_cron import list_builtin_jobs, get_target_jobs_files, load_jobs_from_file
        except ImportError:
            from builtin_cron import list_builtin_jobs, get_target_jobs_files, load_jobs_from_file  # type: ignore
        for tf in get_target_jobs_files():
            if tf.exists():
                for j in load_jobs_from_file(tf):
                    if isinstance(j, dict) and j.get("id") == job_id:
                        if not j.get("enabled", True) or j.get("state") == "paused":
                            _log.debug("Scanner job '%s' is paused/disabled in %s; skipping spawn", job_id, tf)
                            return None
        all_jobs = list_builtin_jobs()
        job = next((j for j in all_jobs if j.get("id") == job_id), None)
        if job and not job.get("enabled", True):
            _log.debug("Scanner job '%s' is paused/disabled; skipping spawn for board '%s'", job_id, board_slug)
            return None
    except Exception as e:
        _log.debug("Scanner enabled check failed: %s", e)

    cmd = [hermes_bin, "-p", "zf-orchestrator", "cron", "run", job_id, "--accept-hooks"]

    log_dir = Path.home() / ".hermes" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file_path = log_dir / f"scanner_{board_slug}.log"

    env = os.environ.copy()
    env["HERMES_PROFILE"] = "zf-orchestrator"
    profile_home = Path.home() / ".hermes" / "profiles" / "zf-orchestrator"
    if profile_home.exists():
        env["HERMES_HOME"] = str(profile_home)
    env["PYTHONUNBUFFERED"] = "1"
    _inject_langfuse_env(env)

    workdir = str(repo_path) if repo_path and repo_path.exists() else os.getcwd()

    if repo_path and repo_path.is_dir():
        try:
            sync_repo_main(repo_path)
        except Exception as e:
            _log.debug("Auto-pull before idle scanner spawn failed for '%s': %s", board_slug, e)

    try:
        log_f = open(log_file_path, "ab")
        proc = subprocess.Popen(
            cmd,
            cwd=workdir,
            stdin=subprocess.DEVNULL,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
        log_f.close()
        _active_scanners[board_slug] = proc
        _log.info("Spawned idle improvement scanner for board '%s' (PID: %d, cwd: %s)", board_slug, proc.pid, workdir)
        return proc.pid
    except Exception as e:
        _log.error("Failed to spawn idle improvement scanner for board '%s': %s", board_slug, e)
        return None


def reset_idle_scanner_state() -> None:
    """Reset scanner state tracking (useful for test isolation)."""
    _last_idle_scan_times.clear()
    for slug, proc in list(_active_scanners.items()):
        if proc is not None and proc.poll() is None:
            # Scanners are spawned with start_new_session=True; terminate the
            # whole process group so no descendants outlive the scanner.
            terminate_process_group(proc, proc.pid)
    _active_scanners.clear()


def check_stuck_tasks(cursor: Optional[sqlite3.Cursor] = None, db_path: Optional[Path] = None) -> List[Dict[str, Any]]:
    """Inspect all running tasks and identify any that are stuck or inactive."""
    if db_path is None:
        db_path = get_db_path()

    if not db_path.exists():
        return []

    close_conn = False
    if cursor is None:
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()
        close_conn = True

    now = int(time.time())
    task_timeout = get_task_timeout_seconds()
    inactivity_timeout = get_inactivity_timeout_seconds()

    results = []
    try:
        cursor.execute("SELECT id, title, status, assignee, workspace_path, metadata, created_at, updated_at, board_slug FROM tasks WHERE status = 'running'")
        for row in cursor.fetchall():
            task_id = str(row["id"])
            meta = {}
            try:
                meta = json.loads(row["metadata"] or "{}")
            except Exception:
                pass

            proc = _active_workers.get(task_id)
            pid = meta.get("worker_pid") or (proc.pid if proc else None)

            is_alive = False
            if proc is not None:
                is_alive = proc.poll() is None
            elif pid:
                try:
                    os.kill(int(pid), 0)
                    is_alive = True
                except (OSError, ValueError):
                    is_alive = False

            started_at = meta.get("started_at") or row["updated_at"] or row["created_at"] or now
            running_seconds = max(0, now - int(started_at))

            idle_seconds = running_seconds
            log_path = Path.home() / ".hermes" / "logs" / f"worker_{task_id}.log"
            if log_path.exists():
                try:
                    mtime = int(log_path.stat().st_mtime)
                    if mtime > int(started_at):
                        idle_seconds = max(0, now - mtime)
                except Exception:
                    pass

            is_stuck = False
            stuck_reason = None

            if not is_alive and pid:
                is_stuck = True
                stuck_reason = f"Worker process PID {pid} is dead/not found"
            elif running_seconds > task_timeout:
                is_stuck = True
                stuck_reason = f"Exceeded running timeout ({running_seconds}s > {task_timeout}s)"
            elif running_seconds > inactivity_timeout and idle_seconds > inactivity_timeout:
                is_stuck = True
                stuck_reason = f"Worker inactive with no updates for {idle_seconds}s (limit {inactivity_timeout}s)"

            results.append({
                "id": task_id,
                "title": row["title"],
                "board_slug": row["board_slug"] if "board_slug" in row.keys() else None,
                "assignee": row["assignee"] or "zf-builder",
                "worker_pid": pid,
                "is_alive": is_alive,
                "started_at": started_at,
                "running_seconds": running_seconds,
                "idle_seconds": idle_seconds,
                "is_stuck": is_stuck,
                "stuck_reason": stuck_reason,
                "timeout_limit": task_timeout,
                "inactivity_limit": inactivity_timeout
            })

        return results
    finally:
        if close_conn:
            try:
                conn.close()
            except Exception:
                pass


def reap_stuck_tasks(task_id: Optional[str] = None, db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Manually or programmatically reap stuck tasks or a specific running task."""
    if db_path is None:
        db_path = get_db_path()

    now = int(time.time())
    reaped_tasks = []

    with _dispatcher_lock:
        with sqlite3.connect(str(db_path), timeout=10.0) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            stuck_list = check_stuck_tasks(cursor=cursor)
            for item in stuck_list:
                t_id = item["id"]
                if task_id and t_id != task_id:
                    continue
                if task_id or item["is_stuck"]:
                    proc = _active_workers.pop(t_id, None)
                    pid = item["worker_pid"]
                    terminate_worker_process(proc, pid)

                    reason = item["stuck_reason"] or f"Manually reaped after running {item['running_seconds']}s"
                    # Persist the reason into task metadata so downstream consumers
                    # (e.g. the daily report's "Active Blockers") can recover it.
                    # The reap previously only set a task_activity row, so the report
                    # fell back to the task description for these blocked tasks.
                    _meta = {}
                    _row = cursor.execute(
                        "SELECT metadata FROM tasks WHERE id = ?", (t_id,)
                    ).fetchone()
                    if _row is not None:
                        try:
                            _meta = json.loads(_row["metadata"] or "{}")
                        except Exception:
                            _meta = {}
                    _meta["blocked_reason"] = reason
                    cursor.execute(
                        "UPDATE tasks SET status = 'blocked', metadata = ?, updated_at = ? WHERE id = ?",
                        (json.dumps(_meta), now, t_id)
                    )
                    cursor.execute(
                        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'worker_timeout', ?, ?)",
                        (t_id, reason, now)
                    )
                    reaped_tasks.append({"id": t_id, "title": item["title"], "reason": reason})

            conn.commit()

    return {
        "ok": True,
        "reaped_count": len(reaped_tasks),
        "reaped_tasks": reaped_tasks,
        "reaped": reaped_tasks
    }


def resolve_task_repo_path(cursor: Optional[sqlite3.Cursor], board_slug: Optional[str], tenant: Optional[str]) -> Path:
    """Resolve the git repository root for a task given its board_slug and tenant."""
    # 1. If board_slug is provided, query boards table and resolve repo path
    if board_slug and cursor:
        try:
            cursor.execute("SELECT slug, description, git_url FROM boards WHERE slug = ?", (board_slug,))
            b_row = cursor.fetchone()
            if b_row:
                b_dict = dict(b_row)
                if b_dict.get("git_url"):
                    try:
                        p = Path(b_dict["git_url"])
                        if p.is_dir() and (p / ".git").exists():
                            return p.resolve()
                    except Exception:
                        pass
                try:
                    from .builtin_cron import resolve_board_repo_path
                except Exception:
                    from builtin_cron import resolve_board_repo_path
                resolved_b = resolve_board_repo_path(b_dict)
                if resolved_b and resolved_b.exists():
                    return resolved_b
        except Exception:
            pass

    # 2. If tenant path is provided
    if tenant:
        t_path = Path(os.path.expanduser(tenant))
        if t_path.is_absolute() and t_path.exists():
            return t_path
        g_tenant = Path.home() / "git" / tenant
        if g_tenant.exists():
            return g_tenant

    # 3. Check ~/git/<board_slug> if board_slug provided
    if board_slug:
        g_board = Path.home() / "git" / board_slug
        if g_board.exists():
            return g_board
        if "-" in board_slug:
            # Check ~/git/<owner>/<repo> (e.g. ~/git/hotcode-dev/zerofactory)
            owner_sub = Path.home() / "git" / board_slug.replace("-", "/", 1)
            if owner_sub.is_dir():
                return owner_sub
            # Check ~/git/<repo> (e.g. ~/git/zerofactory)
            repo_only = Path.home() / "git" / board_slug.split("-", 1)[1]
            if repo_only.is_dir():
                return repo_only
        for sub in (Path.home() / "git").glob(f"*/{board_slug}"):
            if sub.is_dir():
                return sub

def format_conventional_message(title: str, task_id: str = "") -> tuple[str, str]:
    """Format task title into Conventional Commits subject and body.

    Output format:
      subject: <type>(<scope>)?: <description>
      body: Task: <task_id>\\n\\n<title>
    """
    raw_title = title
    # 1. Strip role and priority badges
    cleaned = re.sub(r"\[(?:zf-builder|zf-reviewer|zf-orchestrator|PR Opened by .*?|P[0-3]|p[0-3])\]", "", title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # 2. Check if already conventional
    m = re.match(r"^(feat|fix|refactor|perf|test|docs|style|chore|ci|build)(\([^)]+\))?(!)?:\s*(.*)$", cleaned, re.IGNORECASE)
    if m:
        c_type = m.group(1).lower()
        c_scope = m.group(2) or ""
        c_desc = m.group(4).strip()
    else:
        # Check common prefixes
        prefix_rules = [
            (r"^(?:BUG\s*FIX|BUGFIX|HOTFIX)[:\s-]+(.*)$", "fix", ""),
            (r"^(?:FIX|BUG):\s*(.*)$", "fix", ""),
            (r"^(?:SECURITY|SEC)[:\s-]+(.*)$", "fix", "(security)"),
            (r"^(?:REFACTOR(?:ING)?|CLEANUP|DEDUP(?:LICATE)?)[:\s-]+(.*)$", "refactor", ""),
            (r"^(?:FEAT(?:URE)?|NEW)[:\s-]+(.*)$", "feat", ""),
            (r"^(?:ADD):\s*(.*)$", "feat", ""),
            (r"^(?:PERF(?:ORMANCE)?|OPTIMIZE|OPTIMIZATION)[:\s-]+(.*)$", "perf", ""),
            (r"^(?:TEST(?:S|ING)?)[:\s-]+(.*)$", "test", ""),
            (r"^(?:DOCS?|DOCUMENTATION)[:\s-]+(.*)$", "docs", ""),
            (r"^(?:CHORE|MAINTENANCE|DEPS|DEPENDENCIES)[:\s-]+(.*)$", "chore", ""),
            (r"^(?:CI|WORKFLOW|PIPELINE)[:\s-]+(.*)$", "ci", ""),
            (r"^(?:BUILD|RELEASE)[:\s-]+(.*)$", "build", ""),
        ]
        c_type, c_scope, c_desc = "chore", "", cleaned
        for pattern, t, s in prefix_rules:
            match = re.match(pattern, cleaned, re.IGNORECASE)
            if match:
                c_type = t
                c_scope = s
                c_desc = match.group(1).strip()
                break
        else:
            lower_cleaned = cleaned.lower()
            if re.search(r"\b(?:unit[\s_-]?tests?|e2e|integration[\s_-]?tests?|tests?)\b", lower_cleaned) and not any(lower_cleaned.startswith(p) for p in ("fix ", "patch ")):
                c_type = "test"
            elif any(lower_cleaned.startswith(p) for p in ("add ", "create ", "implement ", "support ", "introduce ", "integrate ")):
                c_type = "feat"
            elif any(lower_cleaned.startswith(p) for p in ("fix ", "resolve ", "patch ", "correct ", "prevent ", "handle ")):
                c_type = "fix"
            elif any(lower_cleaned.startswith(p) for p in ("refactor ", "extract ", "reorganize ", "simplify ", "deduplicate ", "clean ")):
                c_type = "refactor"
            elif any(lower_cleaned.startswith(p) for p in ("optimize ", "speed ", "accelerate ", "reduce ")):
                c_type = "perf"
            elif any(lower_cleaned.startswith(p) for p in ("doc ", "document ", "readme")):
                c_type = "docs"

    # 3. Infer scope if not provided
    if not c_scope:
        file_m = re.search(r"(?:in\s+)?(?:[\w\-]+/)*([a-zA-Z0-9_\-]+)\.(?:ts|js|py|go|rs|json|jsx|tsx|svelte|vue|md)\b", c_desc)
        if file_m:
            c_scope = f"({file_m.group(1)})"
        else:
            mod_m = re.match(r"^([a-zA-Z0-9_\-]+)\s+", c_desc)
            if mod_m and mod_m.group(1).lower() in ("dispatcher", "cron", "dashboard", "api", "auth", "worker", "agent"):
                c_scope = f"({mod_m.group(1).lower()})"

    # 4. Clean description
    if c_scope:
        scope_name = c_scope.strip("()")
        c_desc = re.sub(rf"\s*in\s+(?:[\w\-]+/)*{re.escape(scope_name)}\.[a-zA-Z0-9]+\b", "", c_desc, flags=re.IGNORECASE)
        c_desc = re.sub(rf"^{re.escape(scope_name)}[:\s]+", "", c_desc, flags=re.IGNORECASE)

    if len(c_desc) > 1 and c_desc[0].isupper() and not c_desc[1].isupper():
        c_desc = c_desc[0].lower() + c_desc[1:]

    c_desc = c_desc.rstrip(".").strip()

    subject_desc = c_desc
    if len(f"{c_type}{c_scope}: {c_desc}") > 72:
        no_parens = re.sub(r"\s*\([^)]*\)", "", c_desc).strip()
        if no_parens and len(f"{c_type}{c_scope}: {no_parens}") <= 80:
            subject_desc = no_parens

    subject = f"{c_type}{c_scope}: {subject_desc}".strip()

    body_lines = []
    if task_id:
        body_lines.append(f"Task: {task_id}")
    if raw_title.strip() != subject:
        body_lines.append(raw_title.strip())
    body = "\n\n".join(body_lines)

    return subject, body


def setup_worktree(
    cursor: sqlite3.Cursor,
    task_id: str,
    title: str,
    assignee: str,
    tenant: Optional[str],
    db_path: Path,
    board_slug: Optional[str] = None,
    repo_path: Optional[Path] = None
) -> Optional[str]:
    """Ensure git worktree and branch exist for task execution."""
    valid_profiles = VALID_PROFILES
    if not assignee or assignee == "unassigned" or assignee not in valid_profiles:
        if "[zf-reviewer]" in title:
            assignee = "zf-reviewer"
        elif "[zf-builder]" in title:
            assignee = "zf-builder"
        elif "[zf-orchestrator]" in title:
            assignee = "zf-orchestrator"
        else:
            assignee = "zf-builder"
        cursor.execute("UPDATE tasks SET assignee = ?, skills = '[]' WHERE id = ?", (assignee, task_id))
    else:
        norm_assignee = normalize_assignee(assignee)
        if norm_assignee != assignee:
            assignee = norm_assignee
            cursor.execute("UPDATE tasks SET assignee = ? WHERE id = ?", (assignee, task_id))
        else:
            assignee = norm_assignee

    if os.environ.get("ZEROFACTORY_SKIP_GIT"):
        return None

    # Resolve repo path
    if not repo_path:
        repo_path = resolve_task_repo_path(cursor, board_slug, tenant)
    if not repo_path or not repo_path.exists():
        return None
    reponame = repo_path.name

    worktree_dir = repo_path.parent / f"{reponame}-worktrees" / str(task_id)
    worktree_dir.parent.mkdir(parents=True, exist_ok=True)

    branch_name = f"task/{task_id}"
    try:
        default_branch = sync_repo_main(repo_path)
        base_ref = f"origin/{default_branch}"
        verify_ref = subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", f"refs/remotes/{base_ref}"],
            cwd=repo_path, timeout=5
        )
        if verify_ref.returncode != 0:
            verify_local = subprocess.run(
                ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{default_branch}"],
                cwd=repo_path, timeout=5
            )
            base_ref = default_branch if verify_local.returncode == 0 else "HEAD"

        # Ensure worktree_dir is healthy if it exists on disk
        if worktree_dir.exists():
            rev_check = subprocess.run(["git", "rev-parse", "--git-dir"], cwd=str(worktree_dir), capture_output=True, timeout=5)
            if rev_check.returncode != 0:
                _log.warning("Worktree dir %s has invalid/dangling git pointer; removing to re-create", worktree_dir)
                import shutil
                try:
                    subprocess.run(["git", "worktree", "remove", "--force", str(worktree_dir)], cwd=str(repo_path), capture_output=True, timeout=10)
                except Exception:
                    pass
                try:
                    subprocess.run(["git", "worktree", "prune"], cwd=str(repo_path), capture_output=True, timeout=10)
                except Exception:
                    pass
                if worktree_dir.exists():
                    shutil.rmtree(str(worktree_dir), ignore_errors=True)

        res = subprocess.run(["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"], cwd=repo_path, timeout=5)
        if res.returncode == 0:
            if not worktree_dir.exists():
                try:
                    subprocess.run(["git", "worktree", "add", str(worktree_dir), branch_name], check=True, cwd=repo_path, timeout=5)
                except subprocess.CalledProcessError:
                    subprocess.run(["git", "worktree", "prune"], check=False, cwd=repo_path, capture_output=True, timeout=10)
                    subprocess.run(["git", "worktree", "add", str(worktree_dir), branch_name], check=True, cwd=repo_path, timeout=5)
            # Sync existing worktree with latest default branch if assignee is builder
            if assignee == "zf-builder" and worktree_dir.exists():
                pull_and_merge_main(worktree_dir, repo_path, default_branch)
        else:
            if not worktree_dir.exists():
                try:
                    subprocess.run(["git", "worktree", "add", str(worktree_dir), "-b", branch_name, base_ref], check=True, cwd=repo_path, timeout=5)
                except Exception:
                    subprocess.run(["git", "worktree", "add", str(worktree_dir), "-b", branch_name, "HEAD"], check=True, cwd=repo_path, timeout=5)
            # Sync newly created worktree with latest default branch if assignee is builder
            if assignee == "zf-builder" and worktree_dir.exists():
                pull_and_merge_main(worktree_dir, repo_path, default_branch)
        cursor.execute(
            "UPDATE tasks SET workspace_kind = 'dir', workspace_path = ?, branch_name = ? WHERE id = ?",
            (str(worktree_dir), branch_name, task_id)
        )
        return str(worktree_dir)
    except Exception as e:
        _log.warning("Worktree setup skipped or failed for task %s (%s): %s", task_id, repo_path, e)
        return None


def _handle_local_merge_conflict(
    cursor: sqlite3.Cursor,
    task_id: str,
    title: str,
    workspace_path: str,
    conflict_files: List[str],
    now: int,
    err_msg: str = ""
) -> None:
    """Handle a local merge conflict when syncing task branch with main before push."""
    max_conflict_retries = int(os.environ.get("ZEROFACTORY_MAX_CONFLICT_RETRIES", "3"))

    cursor.execute("SELECT metadata FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    meta = {}
    if row and row[0]:
        try:
            meta = json.loads(row[0])
        except Exception:
            meta = {}

    retries = int(meta.get("conflict_retries", 0))
    if retries > max_conflict_retries:
        _log.debug("Task %s has already reached conflict retries limit (%d > %d); skipping duplicate conflict failure handling", task_id, retries, max_conflict_retries)
        return
    retries += 1
    meta["conflict_retries"] = retries

    new_title = title
    if "[PR Conflict]" not in new_title and "[Merge Conflict]" not in new_title:
        new_title = f"{new_title} [PR Conflict]"

    file_msg = f" in: {', '.join(conflict_files)}" if conflict_files else ""

    if retries > max_conflict_retries:
        cursor.execute(
            "UPDATE tasks SET title = ?, assignee = 'zf-builder', status = 'blocked', metadata = ?, updated_at = ? WHERE id = ?",
            (new_title, json.dumps(meta), now, task_id)
        )
        cursor.execute(
            "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'pr_conflict_failed', ?, ?)",
            (task_id, f"Merge conflict resolution exceeded {max_conflict_retries} attempts{file_msg}. Moved to blocked.", now)
        )
        try:
            cursor.execute(
                "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, ?, ?, ?)",
                (
                    task_id,
                    "dispatcher",
                    f"🚨 **Merge Conflict Resolution Failed**: Pulling latest main branch encountered conflicts{file_msg}. "
                    f"Automatic resolution was attempted {retries - 1} times without success. "
                    f"Task has been moved to **blocked** for manual review and resolution.",
                    now
                )
            )
        except Exception as e:
            _log.debug("Failed to record task comment for conflict limit: %s", e)
        return

    cursor.execute(
        "UPDATE tasks SET title = ?, assignee = 'zf-builder', status = 'todo', metadata = ?, updated_at = ? WHERE id = ?",
        (new_title, json.dumps(meta), now, task_id)
    )
    cursor.execute(
        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'pr_conflict', ?, ?)",
        (task_id, f"Merge conflict with main branch detected{file_msg}. Routed back to zf-builder for resolution.", now)
    )
    try:
        cursor.execute(
            "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, ?, ?, ?)",
            (
                task_id,
                "dispatcher",
                f"🚨 **Merge Conflict Detected**: Pulling latest main branch encountered conflicts{file_msg}. "
                f"Worktree has been left with conflict markers for resolution. "
                f"Please reconcile conflict markers, verify tests pass, and commit.",
                now
            )
        )
    except Exception as e:
        _log.debug("Failed to record task comment for conflict: %s", e)


# Bounded timeout (seconds) for `git worktree remove` cleanup on the PR-lifecycle
# hot path. Worktree removal is local and fast; 30s is a generous margin against
# the 60s commit timeouts. A hung remove (locked .git/index, locks held by a
# still-terminating worker, slow filesystem) must not stall the whole dispatch
# cycle or hold the cross-process dispatcher lock indefinitely.
_WORKTREE_REMOVE_TIMEOUT = 30

# Bounded timeout (seconds) for best-effort remote branch deletion
# (`git push origin --delete`) on the PR MERGED/CLOSED archive path.
_REMOTE_BRANCH_DELETE_TIMEOUT = 30


def _delete_remote_branch(task_id: str, repo_path: Path) -> None:
    """Best-effort deletion of the remote ``task/<task_id>`` branch on origin.

    When the dispatcher archives a task because its PR was MERGED or CLOSED,
    the worktree is removed locally but the remote branch that was pushed with
    ``git push -u origin task/<task_id>`` would otherwise linger on GitHub
    permanently. This helper issues ``git push origin --delete task/<task_id>``
    with a bounded timeout and ``GIT_TERMINAL_PROMPT=0``.

    Fail-open by design (same style as :func:`_remove_worktree`): a failing
    delete (branch already gone after merge, network hiccup, missing remote,
    timeout) is logged as a warning and never raised, so the dispatch cycle
    and the task archive outcome are never affected.
    """
    if not task_id:
        return
    if not repo_path or not Path(repo_path).exists():
        return
    branch = f"task/{task_id}"
    try:
        res = subprocess.run(
            ["git", "push", "origin", "--delete", branch],
            check=False, cwd=str(repo_path), capture_output=True,
            timeout=_REMOTE_BRANCH_DELETE_TIMEOUT,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except subprocess.TimeoutExpired:
        _log.warning(
            "Remote branch delete timed out after %ss for %s; leaving remote branch for manual cleanup",
            _REMOTE_BRANCH_DELETE_TIMEOUT, branch,
        )
        return
    except Exception as e:
        _log.warning("Remote branch delete failed for %s: %s", branch, e)
        return
    if res.returncode != 0:
        _log.warning(
            "Remote branch delete failed for %s (rc=%s): %s",
            branch, res.returncode, (res.stderr or res.stdout or "").strip(),
        )
    else:
        _log.info("Deleted remote branch %s (PR archived)", branch)


def _remove_worktree(workspace_path: Optional[str], repo_path: Path) -> None:
    """Safely remove a git worktree without hanging the dispatch cycle.

    No-ops when the path is missing; otherwise runs `git worktree remove
    --force` bounded by ``_WORKTREE_REMOVE_TIMEOUT`` and falls back to a bounded
    ``git worktree prune`` if the remove times out or fails. Any failure or
    timeout is logged as a warning (never raised) so the dispatch cycle survives
    and the cleanup failure is auditable in the dispatcher log.
    """
    if not workspace_path or not Path(workspace_path).exists():
        return
    try:
        subprocess.run(
            ["git", "worktree", "remove", workspace_path, "--force"],
            check=False, cwd=str(repo_path), capture_output=True,
            timeout=_WORKTREE_REMOVE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        _log.warning(
            "Worktree remove timed out after %ss for %s; falling back to 'git worktree prune'",
            _WORKTREE_REMOVE_TIMEOUT, workspace_path,
        )
        try:
            subprocess.run(
                ["git", "worktree", "prune"],
                check=False, cwd=str(repo_path), capture_output=True,
                timeout=_WORKTREE_REMOVE_TIMEOUT,
            )
        except subprocess.TimeoutExpired as e:
            _log.warning(
                "Worktree prune also timed out after %ss for %s: %s",
                _WORKTREE_REMOVE_TIMEOUT, workspace_path, e.cmd,
            )
        return
    except Exception as e:
        _log.warning("Worktree remove failed for %s: %s", workspace_path, e)

    if Path(workspace_path).exists():
        # `worktree remove` returned an error or did not fully delete the
        # directory; prune to release any remaining metadata.
        try:
            subprocess.run(
                ["git", "worktree", "prune"],
                check=False, cwd=str(repo_path), capture_output=True,
                timeout=_WORKTREE_REMOVE_TIMEOUT,
            )
        except subprocess.TimeoutExpired as e:
            _log.warning(
                "Worktree prune timed out after %ss for %s: %s",
                _WORKTREE_REMOVE_TIMEOUT, workspace_path, e.cmd,
            )
        if Path(workspace_path).exists():
            _log.warning("Worktree directory still present after cleanup attempts: %s", workspace_path)


def _handle_pr_conflict_from_github(
    cursor: sqlite3.Cursor,
    task_id: str,
    title: str,
    workspace_path: Optional[str],
    repo_path: Path,
    tenant: Optional[str],
    db_path: Path,
    board_slug: Optional[str],
    now: int
) -> None:
    """Handle a PR that has merge conflicts on GitHub by routing back to builder."""
    max_conflict_retries = int(os.environ.get("ZEROFACTORY_MAX_CONFLICT_RETRIES", "3"))

    cursor.execute("SELECT metadata FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    meta = {}
    if row and row[0]:
        try:
            meta = json.loads(row[0])
        except Exception:
            meta = {}

    retries = int(meta.get("conflict_retries", 0))
    if retries > max_conflict_retries:
        _log.debug("Task %s has already reached conflict retries limit (%d > %d); skipping duplicate PR conflict failure handling", task_id, retries, max_conflict_retries)
        return
    retries += 1
    meta["conflict_retries"] = retries

    stop_task_worker(task_id, cursor)
    if workspace_path and Path(workspace_path).exists():
        _remove_worktree(workspace_path, repo_path)

    match = re.search(r"\[PR Opened by (.*?)\]", title)
    author = match.group(1) if match else "zf-builder"
    author = normalize_assignee(author)
    if author == "zf-reviewer":
        author = "zf-builder"

    new_title = title
    if "[PR Conflict]" not in new_title and "[Merge Conflict]" not in new_title:
        new_title = f"{new_title} [PR Conflict]"

    if retries > max_conflict_retries:
        cursor.execute(
            "UPDATE tasks SET title = ?, assignee = ?, status = 'blocked', metadata = ?, updated_at = ? WHERE id = ?",
            (new_title, author, json.dumps(meta), now, task_id)
        )
        cursor.execute(
            "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'pr_conflict_failed', ?, ?)",
            (task_id, f"GitHub PR conflict resolution exceeded {max_conflict_retries} attempts. Moved to blocked.", now)
        )
        try:
            cursor.execute(
                "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, ?, ?, ?)",
                (
                    task_id,
                    "dispatcher",
                    f"🚨 **PR Conflict Resolution Failed**: GitHub reports mergeable state is CONFLICTING. "
                    f"Automatic resolution was attempted {retries - 1} times without success. "
                    f"Task has been moved to **blocked** for manual review and resolution.",
                    now
                )
            )
        except Exception as e:
            _log.debug("Failed to record task comment for conflict limit: %s", e)
        return

    wt_path = setup_worktree(cursor, task_id, new_title, author, tenant, db_path, board_slug=board_slug, repo_path=repo_path)
    conflict_files = []
    if wt_path and Path(wt_path).exists():
        # This path is already the "conflict detected" branch (GitHub reported
        # CONFLICTING), so an unverifiable worktree still routes to zf-builder
        # (fail-closed); the file list is simply empty when it can't be read.
        _verified, conflict_files, _err = check_unresolved_conflicts_safe(Path(wt_path))

    file_msg = f" in {', '.join(conflict_files)}" if conflict_files else ""
    cursor.execute(
        "UPDATE tasks SET title = ?, assignee = ?, status = 'todo', metadata = ?, updated_at = ? WHERE id = ?",
        (new_title, author, json.dumps(meta), now, task_id)
    )
    cursor.execute(
        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'pr_conflict', ?, ?)",
        (task_id, f"GitHub PR is conflicting with main branch{file_msg}. Routed to {author} to resolve conflicts.", now)
    )
    try:
        cursor.execute(
            "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, ?, ?, ?)",
            (
                task_id,
                "dispatcher",
                f"🚨 **PR Conflict Detected**: GitHub reports mergeable state is CONFLICTING. "
                f"The worktree has been synced with latest main branch{file_msg}. "
                f"Please resolve all conflict markers, verify tests pass, and commit.",
                now
            )
        )
    except Exception as e:
        _log.debug("Failed to record task comment for conflict: %s", e)


def run_dispatch_cycle(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Execute one full dispatch cycle."""
    if db_path is None:
        db_path = get_db_path()

    if not db_path.exists():
        return {"ok": False, "message": f"Database not found: {db_path}"}

    unblocked = 0
    promoted = 0
    dispatched = 0
    prs_opened = 0
    reaped = 0
    scans_triggered = 0
    now = int(time.time())

    with _dispatcher_lock:
        lock_path = get_dispatcher_lock_path()
        lock_fd: Optional[int] = None
        try:
            lock_path.parent.mkdir(parents=True, exist_ok=True)
            lock_fd = os.open(str(lock_path), os.O_CREAT | os.O_RDWR, 0o666)
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            if lock_fd is not None:
                try:
                    os.close(lock_fd)
                except Exception:
                    pass
            _log.debug("Another process is currently running a Zero Factory dispatch cycle; skipping.")
            return {"ok": True, "skipped": True, "reason": "concurrent_cycle_active"}
        except Exception as e:
            _log.debug("Failed to acquire cross-process lock %s: %s", lock_path, e)
            if lock_fd is not None:
                try:
                    os.close(lock_fd)
                except Exception:
                    pass
            lock_fd = None

        try:
            with sqlite3.connect(str(db_path), timeout=15.0) as conn:
                conn.execute("PRAGMA busy_timeout=15000;")
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # 0. Load global settings (single shared read of the settings
                #    table). The WIP limit, the per-board concurrent-worker
                #    fallback, and the idle-scan knobs all derive from this one
                #    call so the parsing/clamping logic lives in one place.
                #    load_settings() returns defaults for any missing key and
                #    falls back to defaults if the settings table is absent.
                try:
                    settings = load_settings(cursor)
                except Exception:
                    settings = {}

                # 1. Unblock tasks whose parent dependencies are all done
                cursor.execute("""
                    SELECT id, title FROM tasks
                    WHERE status = 'blocked'
                    AND id IN (SELECT child_id FROM task_links)
                    AND NOT EXISTS (
                        SELECT 1 FROM task_links tl
                        JOIN tasks pt ON pt.id = tl.parent_id
                        WHERE tl.child_id = tasks.id AND pt.status != 'done'
                    )
                """)
                for row in cursor.fetchall():
                    cursor.execute("UPDATE tasks SET status = 'todo', updated_at = ? WHERE id = ?", (now, row["id"]))
                    cursor.execute(
                        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'unblock', 'All parent dependencies satisfied; moved to todo', ?)",
                        (row["id"], now)
                    )
                    unblocked += 1

                # 2. Reap finished workers and dispatch Todo tasks to Running
                reaped = reap_active_workers(cursor, now)
                reap_active_scanners()

                # Derive the WIP limit from the shared settings read above.
                max_active_tasks = int(settings.get("max_active_tasks", DEFAULT_MAX_ACTIVE_TASKS))
                max_llm_workers = int(settings.get("max_concurrent_llm_workers", DEFAULT_MAX_CONCURRENT_LLM_WORKERS))

                cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'running'")
                active_count = cursor.fetchone()[0]
                # Running tasks (including those on other boards) and live
                # scanner subprocesses share the same global capacity.
                llm_workers = _global_llm_occupancy(active_count)

                # Fallback concurrent running workers per board from settings table
                default_concurrent_workers = int(
                    settings.get("default_max_concurrent_workers", DEFAULT_MAX_CONCURRENT_WORKERS)
                )

                # Per-board concurrent running caps (boards.max_concurrent_running, default 1).
                board_max_running: Dict[str, int] = {}
                try:
                    for b_row in cursor.execute(
                        "SELECT slug, max_concurrent_running FROM boards"
                    ).fetchall():
                        b_mcr = b_row["max_concurrent_running"]
                        board_max_running[str(b_row["slug"])] = max(1, int(b_mcr)) if b_mcr else default_concurrent_workers
                except Exception:
                    board_max_running = {}

                running_per_board: Dict[str, int] = {}
                for rc_row in cursor.execute(
                    "SELECT board_slug, COUNT(*) AS cnt FROM tasks WHERE status = 'running' GROUP BY board_slug"
                ).fetchall():
                    running_per_board[str(rc_row["board_slug"] or "")] = rc_row["cnt"]

                if active_count < max_active_tasks and llm_workers < max_llm_workers:
                    # Fetch the full candidate set across all boards; a LIMIT
                    # here would starve other boards, so the global WIP budget
                    # is enforced in the loop below.
                    cursor.execute("""
                        SELECT id, title, description, priority, workspace_path, assignee, tenant, branch_name, metadata, board_slug FROM tasks
                        WHERE status IN ('todo', 'ready')
                        ORDER BY CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 WHEN 'P3' THEN 3 ELSE 4 END, created_at ASC
                    """)
                    for row in cursor.fetchall():
                        # Global WIP budget exhausted: stop claiming more
                        # tasks this cycle.
                        if active_count >= max_active_tasks or llm_workers >= max_llm_workers:
                            break
                        task_id = str(row["id"])
                        assignee = normalize_assignee(row["assignee"] or "zf-builder")
                        title = row["title"] or ""
                        description = row["description"] or ""
                        priority = row["priority"] or "P2"
                        tenant = row["tenant"] if "tenant" in row.keys() else None
                        workspace_path = row["workspace_path"]
                        branch_name = row["branch_name"] if "branch_name" in row.keys() else None
                        board_slug = row["board_slug"] if "board_slug" in row.keys() else None
                        board_key = str(board_slug or "")
                        board_cap = board_max_running.get(board_key, default_concurrent_workers)
                        board_active = running_per_board.get(board_key, 0)
                        if board_active >= board_cap:
                            _log.info("Task %s skipped (board %s at running limit %d/%d); will dispatch next cycle", task_id, board_key or "global", board_active, board_cap)
                            continue

                        if not workspace_path or not Path(workspace_path).exists():
                            wt = setup_worktree(cursor, task_id, title, assignee, tenant, db_path, board_slug=board_slug)
                            if wt:
                                workspace_path = wt

                        # Guardrail: Always pull git to latest before implement
                        if not os.environ.get("ZEROFACTORY_SKIP_GIT") and assignee == "zf-builder" and workspace_path and Path(workspace_path).exists():
                            _pre_verify_ok, _pre_verify_files, _pre_verify_err = check_unresolved_conflicts_safe(Path(workspace_path))
                            is_conflict_resolution = (
                                "[pr conflict]" in title.lower()
                                or "[merge conflict]" in title.lower()
                                or (_pre_verify_ok and bool(_pre_verify_files))
                            )
                            if not is_conflict_resolution:
                                if not _pre_verify_ok:
                                    _log.warning(
                                        "Task %s pre-implement conflict check unverifiable; skipping auto-merge: %s",
                                        task_id, _pre_verify_err,
                                    )
                                else:
                                    repo_for_task = resolve_task_repo_path(cursor, board_slug, tenant)
                                    if repo_for_task and repo_for_task.exists():
                                        merged_ok, conflict_files, merge_err = pull_and_merge_main(Path(workspace_path), repo_for_task)
                                        if not merged_ok:
                                            _log.warning("Task %s pre-implement merge conflict with main: %s (%s)", task_id, conflict_files, merge_err)
                                            _handle_local_merge_conflict(cursor, task_id, title, workspace_path, conflict_files, now, merge_err)
                                            continue

                        # Atomic claim to prevent double-dispatch across processes
                        cursor.execute(
                            "UPDATE tasks SET status = 'running', updated_at = ? WHERE id = ? AND status IN ('todo', 'ready')",
                            (now, task_id)
                        )
                        if cursor.rowcount == 0:
                            continue
                        conn.commit()

                        try:
                            pid, session_id = spawn_agent_worker(
                                task_id, title, description, priority, assignee, workspace_path, branch_name, board_slug=row["board_slug"]
                            )
                        except Exception as e:
                            _log.error("Failed to spawn agent worker for %s: %s", task_id, e)
                            cursor.execute("UPDATE tasks SET status = 'todo', updated_at = ? WHERE id = ?", (now, task_id))
                            conn.commit()
                            continue

                        meta = {}
                        try:
                            meta = json.loads(row["metadata"] or "{}")
                        except Exception:
                            pass

                        # Multi-session tracking: record every agent run (orchestrator, builder, reviewer)
                        sessions_list = meta.get("sessions")
                        if not isinstance(sessions_list, list):
                            sessions_list = []
                        for s in sessions_list:
                            if isinstance(s, dict) and s.get("status") == "ongoing":
                                s["status"] = "finished"
                                if not s.get("ended_at"):
                                    s["ended_at"] = now
                        sessions_list.append({
                            "session_id": session_id,
                            "agent": assignee,
                            "status": "ongoing",
                            "started_at": now,
                            "ended_at": None,
                            "pid": pid,
                        })
                        meta["sessions"] = sessions_list
                        if pid:
                            meta["worker_pid"] = pid
                        if session_id:
                            meta["session_id"] = session_id
                        meta["started_at"] = now

                        cursor.execute(
                            "UPDATE tasks SET metadata = ?, updated_at = ? WHERE id = ?",
                            (json.dumps(meta), now, task_id)
                        )
                        cursor.execute(
                            "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'start', ?, ?)",
                            (task_id, f"Agent {assignee} dispatched to work on task (PID: {pid or 'skipped'}, Session: {session_id or 'auto'})", now)
                        )
                        conn.commit()
                        running_per_board[board_key] = board_active + 1
                        active_count += 1
                        llm_workers += 1
                        dispatched += 1
                        promoted += 1

                # 3. Handle Blocked / Completed Tasks (PR generation & Reviewer handoff)
                if not os.environ.get("ZEROFACTORY_SKIP_GIT"):
                    cursor.execute("""
                        SELECT id, title, workspace_path, assignee, tenant, branch_name, pr_url, board_slug, status, metadata FROM tasks
                        WHERE (status != 'done' AND pr_url IS NOT NULL AND pr_url != '')
                           OR (status = 'blocked' AND assignee != 'zf-reviewer')
                           OR (status = 'done' AND assignee != 'zf-reviewer' AND workspace_path IS NOT NULL)
                    """)
                    for row in cursor.fetchall():
                        task_id = str(row["id"])
                        title = row["title"]
                        workspace_path = row["workspace_path"]
                        assignee = row["assignee"]
                        tenant = row["tenant"] if "tenant" in row.keys() else None
                        board_slug = row["board_slug"] if "board_slug" in row.keys() else None
                        raw_meta = row["metadata"] if "metadata" in row.keys() else "{}"
                        meta = {}
                        try:
                            meta = json.loads(raw_meta or "{}")
                        except Exception:
                            pass

                        if not workspace_path or not Path(workspace_path).exists():
                            repo_for_task = resolve_task_repo_path(cursor, board_slug, tenant)
                            if repo_for_task:
                                cand_wt = repo_for_task.parent / f"{repo_for_task.name}-worktrees" / task_id
                                if cand_wt.exists():
                                    workspace_path = str(cand_wt)
                                    cursor.execute("UPDATE tasks SET workspace_path = ? WHERE id = ?", (workspace_path, task_id))

                        # Determine repository root reliably from git worktree or board
                        repo_path = None
                        if workspace_path and Path(workspace_path).exists():
                            try:
                                rev_res = subprocess.run(
                                    ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                    cwd=workspace_path, capture_output=True, text=True, timeout=5
                                )
                                if rev_res.returncode == 0:
                                    common_git = Path(rev_res.stdout.strip())
                                    repo_path = common_git.parent if common_git.name == ".git" else common_git
                            except Exception:
                                pass

                        if not repo_path or not repo_path.exists():
                            repo_path = resolve_task_repo_path(cursor, board_slug, tenant)

                        if not repo_path or not repo_path.exists():
                            continue

                        # If task has an associated PR, check GitHub PR state first
                        if row["pr_url"]:
                            if row["status"] == "done":
                                continue

                            try:
                                res = subprocess.run(
                                    ["gh", "pr", "view", f"task/{task_id}", "--json", "reviewDecision,state,url,mergeable"],
                                    capture_output=True, text=True, cwd=str(repo_path), timeout=10
                                )
                                if res.returncode != 0 and row["pr_url"]:
                                    res = subprocess.run(
                                        ["gh", "pr", "view", row["pr_url"], "--json", "reviewDecision,state,url,mergeable"],
                                        capture_output=True, text=True, cwd=str(repo_path), timeout=10
                                    )
                                if res.returncode == 0:
                                    pr_data = json.loads(res.stdout)
                                    pr_state = pr_data.get("state")
                                    decision = pr_data.get("reviewDecision")
                                    mergeable = pr_data.get("mergeable")
                                    current_pr_url = pr_data.get("url") or row["pr_url"] or ""

                                    if pr_state == "MERGED":
                                        stop_task_worker(task_id, cursor)
                                        _remove_worktree(workspace_path, repo_path)
                                        _delete_remote_branch(task_id, repo_path)
                                        cursor.execute(
                                            "UPDATE tasks SET status = 'done', workspace_path = NULL, updated_at = ? WHERE id = ?",
                                            (now, task_id)
                                        )
                                        cursor.execute(
                                            "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'merged', 'PR merged by human, task completed', ?)",
                                            (task_id, now)
                                        )
                                        continue
                                    elif pr_state == "CLOSED":
                                        stop_task_worker(task_id, cursor)
                                        _remove_worktree(workspace_path, repo_path)
                                        _delete_remote_branch(task_id, repo_path)
                                        cursor.execute(
                                            "UPDATE tasks SET status = 'done', workspace_path = NULL, updated_at = ? WHERE id = ?",
                                            (now, task_id)
                                        )
                                        cursor.execute(
                                            "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'closed', 'PR closed on GitHub, task archived', ?)",
                                            (task_id, now)
                                        )
                                        continue

                                    # If permanently blocked or worker is actively running, skip routing
                                    if meta.get("permanently_blocked") or row["status"] == "running":
                                        continue

                                    if assignee != "zf-reviewer" and row["status"] == "done":
                                        # Author finished re-implementing/fixing review feedback -> commit and update PR below
                                        pass
                                    elif mergeable == "CONFLICTING":
                                        task_meta = {}
                                        try:
                                            cursor.execute("SELECT metadata FROM tasks WHERE id = ?", (task_id,))
                                            m_res = cursor.fetchone()
                                            if m_res and m_res[0]:
                                                task_meta = json.loads(m_res[0])
                                        except Exception:
                                            pass
                                        max_conflict_retries = int(os.environ.get("ZEROFACTORY_MAX_CONFLICT_RETRIES", "3"))
                                        if row["status"] == "blocked" and int(task_meta.get("conflict_retries", 0)) > max_conflict_retries:
                                            _log.debug("Task %s is blocked and already exceeded conflict retries (%d > %d); skipping PR conflict handling", task_id, int(task_meta.get("conflict_retries", 0)), max_conflict_retries)
                                        else:
                                            _handle_pr_conflict_from_github(cursor, task_id, title, workspace_path, repo_path, tenant, db_path, board_slug, now)
                                        continue
                                    else:
                                        # Check for review feedback (inline diff comments, reviews, PR conversation comments)
                                        task_meta = {}
                                        try:
                                            cursor.execute("SELECT metadata FROM tasks WHERE id = ?", (task_id,))
                                            m_res = cursor.fetchone()
                                            if m_res and m_res[0]:
                                                task_meta = json.loads(m_res[0])
                                        except Exception:
                                            pass

                                        processed_cmt_ids = set(task_meta.get("processed_review_comment_ids", []))
                                        additional_reviewer_usernames: set[str] = set()
                                        if board_slug:
                                            try:
                                                board_row = cursor.execute(
                                                    "SELECT additional_reviewer_usernames FROM boards WHERE slug = ?",
                                                    (board_slug,),
                                                ).fetchone()
                                                if board_row and board_row[0]:
                                                    additional_reviewer_usernames = set(
                                                        json.loads(board_row[0])
                                                    )
                                            except (TypeError, ValueError, json.JSONDecodeError):
                                                _log.warning(
                                                    "Ignoring malformed additional reviewer allowlist for board %s",
                                                    board_slug,
                                                )
                                        all_pr_comments = fetch_pr_review_comments(
                                            repo_path=repo_path,
                                            pr_url=current_pr_url,
                                            task_id=task_id,
                                            pr_data=pr_data,
                                            additional_reviewer_usernames=additional_reviewer_usernames,
                                        )
                                        new_pr_comments = [c for c in all_pr_comments if c["comment_id"] not in processed_cmt_ids]

                                        actionable_comments = [
                                            c for c in new_pr_comments
                                            if not is_reviewer_approval_comment(c.get("body", ""), c.get("state"))
                                        ]
                                        approval_comments = [
                                            c for c in new_pr_comments
                                            if is_reviewer_approval_comment(c.get("body", ""), c.get("state"))
                                        ]

                                        has_actionable_feedback = bool(actionable_comments) or (decision == "CHANGES_REQUESTED")
                                        is_approved = (decision == "APPROVED") or (bool(approval_comments) and not has_actionable_feedback)

                                        if has_actionable_feedback and row["status"] in ("blocked", "todo"):
                                            for c in new_pr_comments:
                                                cmt_body = format_task_comment_body(c)
                                                cursor.execute(
                                                    "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, ?, ?, ?)",
                                                    (task_id, c["author"], cmt_body, now)
                                                )
                                                cursor.execute(
                                                    "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, ?, 'review_comment', ?, ?)",
                                                    (task_id, c["author"], f"PR review comment on {c.get('path') or 'PR'}: {c['body'][:80]}", now)
                                                )
                                                processed_cmt_ids.add(c["comment_id"])

                                                # Auto-record gotchas/conventions from reviewer feedback
                                                if board_slug and c.get("body"):
                                                    try:
                                                        from dashboard.plugin_api import extract_and_record_memory
                                                        extract_and_record_memory(conn, board_slug=board_slug, text=c["body"], task_id=task_id, author=c.get("author") or "zf-reviewer")
                                                    except Exception as _mem_e:
                                                        _log.debug("Auto-record memory from review comment failed: %s", _mem_e)

                                            task_meta["processed_review_comment_ids"] = list(processed_cmt_ids)

                                            stop_task_worker(task_id, cursor)
                                            _remove_worktree(workspace_path, repo_path)
                                            match = re.search(r"\[PR Opened by (.*?)\]", title)
                                            author = match.group(1) if match else "zf-builder"
                                            author = normalize_assignee(author)
                                            clean_title = title.replace(" [Human Review]", "").replace("[Human Review]", "").strip()

                                            cursor.execute(
                                                "UPDATE tasks SET title = ?, assignee = ?, status = 'todo', metadata = ?, updated_at = ? WHERE id = ?",
                                                (clean_title, author, json.dumps(task_meta), now, task_id)
                                            )
                                            setup_worktree(cursor, task_id, clean_title, author, tenant, db_path, board_slug=board_slug)
                                            reason_text = (
                                                f"Review feedback received ({len(actionable_comments)} actionable comment(s)), routed back to {author}"
                                                if actionable_comments else "Changes requested by reviewer, routed back to author"
                                            )
                                            cursor.execute(
                                                "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'changes_requested', ?, ?)",
                                                (task_id, reason_text, now)
                                            )
                                            continue
                                        elif is_approved and row["status"] in ("blocked", "todo", "running"):
                                            for c in new_pr_comments:
                                                cmt_body = format_task_comment_body(c)
                                                cursor.execute(
                                                    "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, ?, ?, ?)",
                                                    (task_id, c["author"], cmt_body, now)
                                                )
                                                cursor.execute(
                                                    "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, ?, 'review_comment', ?, ?)",
                                                    (task_id, c["author"], f"PR review comment on {c.get('path') or 'PR'}: {c['body'][:80]}", now)
                                                )
                                                processed_cmt_ids.add(c["comment_id"])

                                            task_meta["processed_review_comment_ids"] = list(processed_cmt_ids)
                                            task_meta["blocked_reason"] = "Reviewer approved; awaiting human merge"

                                            stop_task_worker(task_id, cursor)
                                            _remove_worktree(workspace_path, repo_path)
                                            new_title = title if "[Human Review]" in title else f"{title} [Human Review]"
                                            cursor.execute(
                                                "UPDATE tasks SET title = ?, status = 'blocked', metadata = ?, workspace_path = NULL, updated_at = ? WHERE id = ?",
                                                (new_title, json.dumps(task_meta), now, task_id)
                                            )
                                            cursor.execute(
                                                "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'approved', 'Reviewer approved PR; task blocked awaiting human merge', ?)",
                                                (task_id, now)
                                            )
                                            continue
                            except Exception as e:
                                _log.info("Reviewer PR check skipped for task %s: %s", task_id, e)

                        if assignee != "zf-reviewer" and (not row["pr_url"] or row["status"] == "done"):
                            # Guard: Do not treat task as finished work if worker failed/timed out
                            # or is permanently blocked!
                            if meta.get("permanently_blocked") or meta.get("last_worker_failure"):
                                continue

                            if not workspace_path or not Path(workspace_path).exists():
                                continue
                            # Author finished work -> check conflicts, commit, pull/merge main, push, create PR, hand off to reviewer
                            try:
                                clean_stale_git_locks(Path(workspace_path))
                                git_dir = get_git_dir(Path(workspace_path))
                                is_merging = bool(git_dir and (git_dir / "MERGE_HEAD").exists())

                                # 1. Guardrail: Check if worktree is already in an unmerged conflict state
                                # Fail-closed: if the worktree cannot be verified clean,
                                # do NOT commit / merge / push. Leave the task in its
                                # current (pre-PR) status and retry next cycle.
                                _initial_verified, initial_conflicts, _initial_err = check_unresolved_conflicts_safe(Path(workspace_path))
                                if not _initial_verified:
                                    _log.warning("Task %s worktree conflict state unverifiable; leaving blocked: %s", task_id, _initial_err)
                                    cursor.execute(
                                        "UPDATE tasks SET status = 'blocked', updated_at = ? WHERE id = ?",
                                        (now, task_id)
                                    )
                                    cursor.execute(
                                        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'conflict_unverifiable', ?, ?)",
                                        (task_id, f"Worktree conflict state could not be verified; left in blocked state (fail-closed): {_initial_err}", now)
                                    )
                                    conn.commit()
                                    continue
                                if initial_conflicts:
                                    _log.warning("Task %s has unresolved conflicts in worktree: %s", task_id, initial_conflicts)
                                    _handle_local_merge_conflict(cursor, task_id, title, workspace_path, initial_conflicts, now, "Unresolved conflicts in worktree")
                                    continue

                                subject, commit_body = format_conventional_message(title, task_id)
                                status_res = subprocess.run(["git", "status", "--porcelain"], cwd=workspace_path, capture_output=True, text=True, timeout=5)
                                if status_res.stdout.strip() or is_merging:
                                    subprocess.run(["git", "add", "."], check=True, cwd=workspace_path, capture_output=True, timeout=60)
                                    commit_cmd = ["git", "commit"]
                                    if is_merging and not status_res.stdout.strip():
                                        commit_cmd.append("--no-edit")
                                    else:
                                        commit_cmd.extend(["-m", subject, "-m", commit_body])
                                    subprocess.run(
                                        commit_cmd,
                                        check=True, cwd=workspace_path, capture_output=True, timeout=60
                                    )

                                # 2. Guardrail: Always pull and merge latest main branch before pushing
                                merged_ok, conflict_files, merge_err = pull_and_merge_main(Path(workspace_path), repo_path)
                                if not merged_ok:
                                    _log.warning("Task %s merge conflict with main detected: %s (%s)", task_id, conflict_files, merge_err)
                                    _handle_local_merge_conflict(cursor, task_id, title, workspace_path, conflict_files, now, merge_err)
                                    continue

                                # 3. Guardrail: Check for any leftover conflict markers post-merge.
                                # Fail-closed: if we cannot verify the post-merge
                                # worktree is clean, do NOT push / open a PR.
                                _leftover_verified, leftover_conflicts, _leftover_err = check_unresolved_conflicts_safe(Path(workspace_path))
                                if not _leftover_verified:
                                    _log.warning("Task %s post-merge conflict state unverifiable; not pushing: %s", task_id, _leftover_err)
                                    cursor.execute(
                                        "UPDATE tasks SET status = 'blocked', updated_at = ? WHERE id = ?",
                                        (now, task_id)
                                    )
                                    cursor.execute(
                                        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'conflict_unverifiable', ?, ?)",
                                        (task_id, f"Post-merge conflict state could not be verified; not pushing (fail-closed): {_leftover_err}", now)
                                    )
                                    conn.commit()
                                    continue
                                if leftover_conflicts:
                                    _handle_local_merge_conflict(cursor, task_id, title, workspace_path, leftover_conflicts, now, "Leftover conflict markers detected after merge")
                                    continue

                                subprocess.run(
                                    ["git", "push", "-u", "origin", f"task/{task_id}"],
                                    check=True, cwd=workspace_path, capture_output=True, timeout=180,
                                    env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}
                                )

                                pr_url = row["pr_url"] or ""
                                if not pr_url:
                                    gh_view = subprocess.run(["gh", "pr", "view", f"task/{task_id}", "--json", "url"], cwd=workspace_path, capture_output=True, text=True, timeout=30)
                                    if gh_view.returncode == 0:
                                        try:
                                            pr_url = json.loads(gh_view.stdout).get("url") or ""
                                        except Exception:
                                            pr_url = ""
                                    else:
                                        pr_title = subject
                                        pr_body = f"{commit_body}\n\nAutomated PR for task {task_id}\n\nCompleted by: @{assignee}"
                                        pr_res = subprocess.run(["gh", "pr", "create", "--title", pr_title, "--body", pr_body], check=True, cwd=workspace_path, capture_output=True, text=True, timeout=180)
                                        pr_url = pr_res.stdout.strip()

                                # Cleanup author worktree
                                stop_task_worker(task_id, cursor)
                                _remove_worktree(workspace_path, repo_path)

                                new_title = title
                                for tag in ("[PR Conflict]", "[Merge Conflict]"):
                                    new_title = new_title.replace(f" {tag}", "").replace(tag, "").strip()
                                if not re.search(r"\[PR Opened by .*?\]", new_title):
                                    new_title = f"{new_title} [PR Opened by {assignee}]"

                                meta = {}
                                try:
                                    cursor.execute("SELECT metadata FROM tasks WHERE id = ?", (task_id,))
                                    m_row = cursor.fetchone()
                                    if m_row and m_row[0]:
                                        meta = json.loads(m_row[0])
                                        meta.pop("conflict_retries", None)
                                except Exception:
                                    pass

                                # The builder process has just been stopped.  Do not
                                # carry its PID into the reviewer phase: on the next
                                # dispatch cycle ``reap_active_workers`` would see the
                                # dead PID, mark the new reviewer task as failed, and
                                # block it before it can be dispatched.
                                for key in ("worker_pid", "session_id", "started_at",
                                            "last_worker_failure", "worker_failure_retries",
                                            "blocked_reason", "permanently_blocked"):
                                    meta.pop(key, None)

                                cursor.execute(
                                    "UPDATE tasks SET title = ?, assignee = 'zf-reviewer', pr_url = ?, metadata = ?, status = 'todo', updated_at = ? WHERE id = ?",
                                    (new_title, pr_url, json.dumps(meta), now, task_id)
                                )
                                setup_worktree(cursor, task_id, new_title, "zf-reviewer", tenant, db_path, board_slug=board_slug)
                                cursor.execute(
                                    "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'pr_opened', ?, ?)",
                                    (task_id, f"PR synced with main, routed to reviewer: {pr_url}", now)
                                )
                                prs_opened += 1
                            except subprocess.CalledProcessError as e:
                                err_msg = (e.stderr or "").strip() or str(e)
                                if "No commits between" in err_msg:
                                    _log.info("Task %s has no commits between main and branch; completing task without PR.", task_id)
                                    stop_task_worker(task_id, cursor)
                                    _remove_worktree(workspace_path, repo_path)
                                    cursor.execute("UPDATE tasks SET workspace_path = NULL, status = 'done', updated_at = ? WHERE id = ?", (now, task_id))
                                    cursor.execute("INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'completed_no_diff', 'No commits between branch and main; task marked done', ?)", (task_id, now))
                                else:
                                    _log.warning("Task %s commit/PR command failed: %s", task_id, err_msg)
                            except subprocess.TimeoutExpired as e:
                                _log.warning("Task %s commit/PR step timed out after %ss: %s (task left in pre-PR status; next cycle will retry idempotently)", task_id, e.timeout, e.cmd)
                            except Exception as e:
                                _log.warning("Task %s commit/PR failed: %s", task_id, e)

                # 4. Capacity-driven / Idle Improvement Scanner Check
                reap_active_scanners()
                # Phase 3 may have completed/rerouted tasks; refresh the count
                # before allocating scan slots. Track successful mock spawns as
                # well as real registered processes within this cycle.
                active_count = cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'running'").fetchone()[0]
                llm_workers = _global_llm_occupancy(active_count)

                # Derive the idle-scan knobs from the shared settings read above.
                # load_settings() stores idle_scan_cooldown_minutes in MINUTES; the
                # dispatcher works in seconds, so the single minutes->seconds
                # conversion (value * 60) is performed exactly here and nowhere
                # else (see the settings module docstring for the unit boundary).
                # .get() defaults only guard the rare empty-settings case; the
                # stored values themselves are already clamped by load_settings().
                scan_on_idle = bool(settings.get("scan_on_idle", DEFAULT_SCAN_ON_IDLE))
                idle_active_threshold = int(settings.get("idle_scan_active_threshold", DEFAULT_IDLE_SCAN_ACTIVE_THRESHOLD))
                cooldown_seconds = int(settings.get("idle_scan_cooldown_minutes", DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES)) * 60
                max_todo = int(settings.get("idle_scan_max_todo", DEFAULT_IDLE_SCAN_MAX_TODO))

                if scan_on_idle:
                    try:
                        b_rows = cursor.execute("SELECT slug, git_url FROM boards").fetchall()
                    except Exception:
                        b_rows = []

                    # Count todo tasks per board to prevent backlog flooding
                    todo_per_board: Dict[str, int] = {}
                    try:
                        for td_row in cursor.execute(
                            "SELECT board_slug, COUNT(*) AS cnt FROM tasks WHERE status = 'todo' GROUP BY board_slug"
                        ).fetchall():
                            todo_per_board[str(td_row["board_slug"] or "")] = td_row["cnt"]
                    except Exception:
                        pass

                    for b_row in b_rows:
                        if llm_workers >= max_llm_workers:
                            break
                        board_slug = str(b_row["slug"] or "")
                        if not board_slug:
                            continue
                        board_active_running = running_per_board.get(board_slug, 0)
                        board_todo_count = todo_per_board.get(board_slug, 0)

                        if board_active_running < idle_active_threshold and board_todo_count < max_todo:
                            if board_slug not in _active_scanners:
                                last_scan = _last_idle_scan_times.get(board_slug, 0)
                                if (now - last_scan) >= cooldown_seconds:
                                    repo_for_task = resolve_task_repo_path(cursor, board_slug, None)
                                    pid = spawn_board_scanner(board_slug, repo_for_task)
                                    if pid is not None:
                                        # Consume the cooldown and count the scan only when a
                                        # scanner process actually started, so a transient spawn
                                        # failure does not lock the board out for the cooldown.
                                        _last_idle_scan_times[board_slug] = now
                                        scans_triggered += 1
                                        llm_workers += 1
                                        _log.info(
                                            "Triggered idle improvement scan for board '%s' (running: %d < %d, todo: %d, PID: %d)",
                                            board_slug, board_active_running, idle_active_threshold, board_todo_count, pid
                                        )
                                    else:
                                        _log.warning(
                                            "Idle improvement scan spawn failed for board '%s'; cooldown NOT consumed, will retry next cycle",
                                            board_slug
                                        )

                conn.commit()

            return {
                "ok": True,
                "unblocked": unblocked,
                "promoted": promoted,
                "dispatched": dispatched,
                "reaped": reaped,
                "prs_opened": prs_opened,
                "scans_triggered": scans_triggered,
                "message": f"Dispatch cycle complete: {unblocked} unblocked, {promoted} promoted, {dispatched} dispatched to running, {reaped} reaped, {prs_opened} PRs opened, {scans_triggered} scans triggered."
            }
        except Exception as e:
            _log.error("Error during dispatch cycle: %s", e)
            return {"ok": False, "error": str(e)}
        finally:
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                except Exception:
                    pass
                try:
                    os.close(lock_fd)
                except Exception:
                    pass


def _dispatcher_loop():
    """Background polling daemon thread for Kanban dispatch and periodic cron ticks."""
    while True:
        try:
            run_dispatch_cycle()
        except Exception as e:
            _log.error("Unexpected error in background dispatcher loop: %s", e)

        try:
            try:
                from .builtin_cron import is_cron_scheduler_enabled, tick_builtin_cron
            except ImportError:
                from builtin_cron import is_cron_scheduler_enabled, tick_builtin_cron  # type: ignore
            if is_cron_scheduler_enabled():
                tick_builtin_cron()
            else:
                _log.debug("Builtin cron scheduler disabled; skipping periodic tick")
        except Exception as e:
            _log.debug("Builtin cron tick check: %s", e)

        time.sleep(DISPATCH_INTERVAL_SECONDS)


def start_background_dispatcher():
    """Start background dispatcher daemon thread if not already running."""
    if is_worker_or_child_process():
        _log.debug("Skipping background dispatcher in worker/child process (profile=%s)", os.environ.get("HERMES_PROFILE"))
        return
    global _dispatcher_thread
    with _dispatcher_lock:
        if _dispatcher_thread is None or not _dispatcher_thread.is_alive():
            _dispatcher_thread = threading.Thread(target=_dispatcher_loop, name="ZeroFactoryKanbanDispatcher", daemon=True)
            _dispatcher_thread.start()
            _log.info("Zero Factory Kanban background dispatcher started (interval: %ss)", DISPATCH_INTERVAL_SECONDS)
