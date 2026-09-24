"""Git operations, merge conflict checking, and lock cleanup for Zero Factory."""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Iterable, List, Optional

from .config import _d, _log


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
    default_branch = _d().get_default_branch(repo_path)
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


def check_files_for_conflict_markers(workspace_path: Path, files: Iterable[str]) -> List[str]:
    """Scan given relative file paths within workspace_path for conflict markers."""
    conflicted = []
    for rel_file in files:
        fp = workspace_path / rel_file
        if fp.is_file() and not fp.is_symlink():
            try:
                if fp.stat().st_size < 10 * 1024 * 1024:
                    if _has_unresolved_conflict_markers(fp.read_bytes()):
                        conflicted.append(rel_file)
            except Exception:
                pass
    return sorted(conflicted)


def get_unmerged_status_files(workspace_path: Path) -> List[str]:
    """Return files that have unmerged git status codes (UU, AA, UD, DU, DD, AU, UA)."""
    unmerged = []
    try:
        status_res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(workspace_path), capture_output=True, text=True, timeout=5
        )
        if status_res.returncode == 0:
            for line in status_res.stdout.splitlines():
                if len(line) >= 3 and line[:2] in ("UU", "AA", "UD", "DU", "DD", "AU", "UA"):
                    f = line[3:].strip()
                    if " -> " in f:
                        f = f.split(" -> ")[-1].strip()
                    unmerged.append(f)
    except Exception:
        pass
    return sorted(unmerged)


def get_modified_status_files(workspace_path: Path) -> List[str]:
    """Return all modified/unmerged/untracked file paths from git status --porcelain."""
    files = set()
    try:
        status_res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(workspace_path), capture_output=True, text=True, timeout=5
        )
        if status_res.returncode == 0:
            for line in status_res.stdout.splitlines():
                if len(line) >= 3:
                    f = line[3:].strip()
                    if " -> " in f:
                        f = f.split(" -> ")[-1].strip()
                    files.add(f)
    except Exception:
        pass
    return sorted(list(files))


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

        for rel_file in _d().check_files_for_conflict_markers(workspace_path, files_to_check):
            conflicted.add(rel_file)
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
        return True, _d().check_unresolved_conflicts(workspace_path), ""
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
    git_dir = _d().get_git_dir(workspace_path)
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

    _d().clean_stale_git_locks(workspace_path)

    if not default_branch:
        default_branch = _d().sync_repo_main(repo_path)

    # Check if worktree is already in an unmerged / conflict state.
    # Fail-closed: if the worktree cannot be verified clean, do NOT merge.
    existing_verified, existing_conflicts, existing_err = _d().check_unresolved_conflicts_safe(workspace_path)
    if not existing_verified:
        return _unverifiable_result(existing_err, "pre-merge worktree conflict check")

    # Check if an in-progress merge exists (MERGE_HEAD)
    git_dir = _d().get_git_dir(workspace_path)
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
        post_verified, post_conflicts, post_err = _d().check_unresolved_conflicts_safe(workspace_path)
        if not post_verified:
            # Merge command reported success, but we cannot verify the worktree
            # is clean afterwards. Fail-closed: do not claim a clean merge.
            return _unverifiable_result(post_err, "post-merge worktree conflict check")
        if post_conflicts:
            return False, post_conflicts, f"Unresolved conflict markers in: {', '.join(post_conflicts)}"
        return True, [], f"Successfully merged {target_ref}"
    else:
        post_fail_verified, conflicted_files, post_fail_err = _d().check_unresolved_conflicts_safe(workspace_path)
        err = (merge_res.stderr or "").strip() or (merge_res.stdout or "").strip()
        if not post_fail_verified:
            return _unverifiable_result(post_fail_err, f"post-failure worktree conflict check (merge with {target_ref} failed: {err})")
        if not conflicted_files and "conflict" not in err.lower():
            return False, [], f"Git merge execution failed (not a conflict): {err}"
        return False, conflicted_files, f"Merge conflict with {target_ref}: {err}"
