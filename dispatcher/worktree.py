"""Git worktree provisioning, teardown, and merge conflict routing for Zero Factory."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
from pathlib import Path
from typing import List, Optional

from .config import (
    _REMOTE_BRANCH_DELETE_TIMEOUT,
    _WORKTREE_REMOVE_TIMEOUT,
    VALID_PROFILES,
    _d,
    _log,
    normalize_assignee,
)


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
                    try:
                        from ..builtin_cron import resolve_board_repo_path
                    except (ImportError, ValueError):
                        from .builtin_cron import resolve_board_repo_path  # type: ignore
                except Exception:
                    from builtin_cron import resolve_board_repo_path  # type: ignore
                resolved_b = resolve_board_repo_path(b_dict)
                if resolved_b and resolved_b.exists() and (resolved_b / ".git").exists():
                    return resolved_b
        except Exception:
            pass

    # 2. If tenant path is provided
    if tenant:
        t_path = Path(os.path.expanduser(tenant))
        if t_path.is_absolute() and t_path.exists() and (t_path / ".git").exists():
            return t_path
        g_tenant = Path.home() / "git" / tenant
        if g_tenant.exists() and (g_tenant / ".git").exists():
            return g_tenant

    # 3. Check ~/git/<board_slug> if board_slug provided
    if board_slug:
        g_board = Path.home() / "git" / board_slug
        if g_board.exists() and (g_board / ".git").exists():
            return g_board
        if "-" in board_slug:
            # Check ~/git/<owner>/<repo> (e.g. ~/git/hotcode-dev/zerofactory)
            owner_sub = Path.home() / "git" / board_slug.replace("-", "/", 1)
            if owner_sub.is_dir() and (owner_sub / ".git").exists():
                return owner_sub
            # Check ~/git/<repo> (e.g. ~/git/zerofactory)
            repo_only = Path.home() / "git" / board_slug.split("-", 1)[1]
            if repo_only.is_dir() and (repo_only / ".git").exists():
                return repo_only
        for sub in (Path.home() / "git").glob(f"*/{board_slug}"):
            if sub.is_dir() and (sub / ".git").exists():
                return sub


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
    valid_profiles = getattr(_d(), "VALID_PROFILES", VALID_PROFILES)
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
        repo_path = _d().resolve_task_repo_path(cursor, board_slug, tenant)
    if not repo_path or not repo_path.exists():
        return None
    reponame = repo_path.name

    worktree_dir = repo_path.parent / f"{reponame}-worktrees" / str(task_id)
    worktree_dir.parent.mkdir(parents=True, exist_ok=True)

    branch_name = f"task/{task_id}"
    try:
        default_branch = _d().sync_repo_main(repo_path)
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
                _d().pull_and_merge_main(worktree_dir, repo_path, default_branch)
        else:
            if not worktree_dir.exists():
                try:
                    subprocess.run(["git", "worktree", "add", str(worktree_dir), "-b", branch_name, base_ref], check=True, cwd=repo_path, timeout=5)
                except Exception:
                    subprocess.run(["git", "worktree", "add", str(worktree_dir), "-b", branch_name, "HEAD"], check=True, cwd=repo_path, timeout=5)
            # Sync newly created worktree with latest default branch if assignee is builder
            if assignee == "zf-builder" and worktree_dir.exists():
                _d().pull_and_merge_main(worktree_dir, repo_path, default_branch)
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


def _delete_remote_branch(task_id: str, repo_path: Path) -> None:
    """Best-effort deletion of the remote ``task/<task_id>`` branch on origin."""
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
    """Safely remove a git worktree without hanging the dispatch cycle."""
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

    _d().stop_task_worker(task_id, cursor)
    if workspace_path and Path(workspace_path).exists():
        _d()._remove_worktree(workspace_path, repo_path)

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

    wt_path = _d().setup_worktree(cursor, task_id, new_title, author, tenant, db_path, board_slug=board_slug, repo_path=repo_path)
    conflict_files = []
    if wt_path and Path(wt_path).exists():
        _verified, conflict_files, _err = _d().check_unresolved_conflicts_safe(Path(wt_path))

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
