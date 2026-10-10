"""Git worktree provisioning, teardown, and merge conflict routing for Zero Factory."""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from pathlib import Path

from .config import (
    _REMOTE_BRANCH_DELETE_TIMEOUT,
    _WORKTREE_REMOVE_TIMEOUT,
    VALID_PROFILES,
    StepTracker,
    _d,
    _log,
    normalize_assignee,
)


def resolve_task_repo_path(
    cursor: sqlite3.Cursor | None,
    board_slug: str | None,
    tenant: str | None,
    repo_alias: str | None = None,
) -> Path:
    """Resolve the git repository root for a task given its board_slug, tenant, and repo_alias."""
    # 0. Check board_repositories if board_slug and cursor are provided
    if board_slug and cursor:
        try:
            repo_row = None
            if repo_alias:
                try:
                    cursor.execute(
                        "SELECT repo_alias, git_url, target_branch FROM board_repositories WHERE board_slug = ? AND repo_alias = ?",
                        (board_slug, repo_alias),
                    )
                    repo_row = cursor.fetchone()
                except Exception:
                    pass
            if not repo_row:
                try:
                    cursor.execute(
                        "SELECT repo_alias, git_url, target_branch FROM board_repositories WHERE board_slug = ? ORDER BY id ASC LIMIT 1",
                        (board_slug,),
                    )
                    repo_row = cursor.fetchone()
                except Exception:
                    pass
            if not repo_row:
                try:
                    cursor.execute("SELECT slug, git_url FROM boards WHERE slug = ?", (board_slug,))
                    b_row = cursor.fetchone()
                    if b_row and dict(b_row).get("git_url"):
                        repo_row = {"repo_alias": dict(b_row)["slug"], "git_url": dict(b_row)["git_url"]}
                except Exception:
                    pass

            if repo_row:
                r_dict = dict(repo_row)
                alias = (r_dict.get("repo_alias") or "").strip()
                url = (r_dict.get("git_url") or "").strip()
                if url:
                    try:
                        p = Path(url)
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

                resolved_r = resolve_board_repo_path({"git_url": url, "slug": alias})
                if resolved_r and resolved_r.exists() and (resolved_r / ".git").exists():
                    return resolved_r

                if alias:
                    g_alias = Path.home() / "git" / alias
                    if g_alias.exists() and (g_alias / ".git").exists():
                        return g_alias
                    for sub in (Path.home() / "git").glob(f"*/{alias}"):
                        if sub.is_dir() and (sub / ".git").exists():
                            return sub
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
    tenant: str | None,
    db_path: Path,
    board_slug: str | None = None,
    repo_path: Path | None = None,
    repo_alias: str | None = None,
) -> str | None:
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
        cursor.execute(
            "UPDATE tasks SET assignee = ?, skills = '[]' WHERE id = ?",
            (assignee, task_id),
        )
    else:
        norm_assignee = normalize_assignee(assignee)
        if norm_assignee != assignee:
            assignee = norm_assignee
            cursor.execute(
                "UPDATE tasks SET assignee = ? WHERE id = ?", (assignee, task_id)
            )
        else:
            assignee = norm_assignee

    if os.environ.get("ZEROFACTORY_SKIP_GIT"):
        return None

    steps = StepTracker(task_id)
    steps.start("worktree.setup", f"assignee={assignee}")

    # Fetch repo_alias from tasks if not explicitly passed
    if not repo_alias and cursor:
        try:
            cursor.execute("SELECT repo_alias FROM tasks WHERE id = ?", (task_id,))
            t_row = cursor.fetchone()
            if t_row and t_row[0]:
                repo_alias = str(t_row[0]).strip()
        except Exception:
            pass

    # Resolve primary repo path
    if not repo_path:
        repo_path = _d().resolve_task_repo_path(
            cursor, board_slug, tenant, repo_alias=repo_alias
        )
    if not repo_path or not repo_path.exists():
        steps.end("fail", f"repo path unresolvable: {repo_path}")
        return None

    target_name = repo_alias or repo_path.name
    if board_slug:
        try:
            from paths import get_board_worktrees_dir  # type: ignore
        except Exception:
            try:
                from ..paths import get_board_worktrees_dir  # type: ignore
            except Exception:
                get_board_worktrees_dir = lambda b: Path.home() / ".zerofactory" / "workspaces" / b / "worktrees"  # type: ignore
        worktree_base = get_board_worktrees_dir(board_slug)
    else:
        worktree_base = repo_path.parent / f"{repo_path.name}-worktrees"
    task_root = worktree_base / str(task_id)
    worktree_dir = task_root / target_name
    worktree_dir.parent.mkdir(parents=True, exist_ok=True)

    branch_name = f"task/{task_id}"
    try:
        target_branch = ""
        if cursor and board_slug:
            try:
                if repo_alias:
                    cursor.execute(
                        "SELECT target_branch FROM board_repositories WHERE board_slug = ? AND repo_alias = ?",
                        (board_slug, repo_alias),
                    )
                    br_row = cursor.fetchone()
                    if br_row and br_row[0]:
                        target_branch = str(br_row[0]).strip()
                if not target_branch:
                    cursor.execute(
                        "SELECT target_branch FROM board_repositories WHERE board_slug = ? ORDER BY id ASC LIMIT 1",
                        (board_slug,),
                    )
                    br_row = cursor.fetchone()
                    if br_row and br_row[0]:
                        target_branch = str(br_row[0]).strip()
                if not target_branch:
                    cursor.execute(
                        "SELECT target_branch FROM boards WHERE slug = ?", (board_slug,)
                    )
                    b_row = cursor.fetchone()
                    if b_row and b_row[0]:
                        target_branch = str(b_row[0]).strip()
            except Exception:
                pass

        default_branch = _d().sync_repo_main(
            repo_path, default_branch=target_branch or None
        )
        base_ref = f"origin/{default_branch}"
        verify_ref = subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", f"refs/remotes/{base_ref}"],
            cwd=repo_path,
            timeout=5,
        )
        if verify_ref.returncode != 0:
            verify_local = subprocess.run(
                [
                    "git",
                    "show-ref",
                    "--verify",
                    "--quiet",
                    f"refs/heads/{default_branch}",
                ],
                cwd=repo_path,
                timeout=5,
            )
            base_ref = default_branch if verify_local.returncode == 0 else "HEAD"

        # Ensure worktree_dir is healthy if it exists on disk
        if worktree_dir.exists():
            rev_check = subprocess.run(
                ["git", "rev-parse", "--git-dir"],
                cwd=str(worktree_dir),
                capture_output=True,
                timeout=5,
            )
            if rev_check.returncode != 0:
                _log.warning(
                    "Worktree dir %s has invalid/dangling git pointer; removing to re-create",
                    worktree_dir,
                )
                import shutil

                try:
                    subprocess.run(
                        ["git", "worktree", "remove", "--force", str(worktree_dir)],
                        cwd=str(repo_path),
                        capture_output=True,
                        timeout=10,
                    )
                except Exception:
                    pass
                try:
                    subprocess.run(
                        ["git", "worktree", "prune"],
                        cwd=str(repo_path),
                        capture_output=True,
                        timeout=10,
                    )
                except Exception:
                    pass
                if worktree_dir.exists():
                    shutil.rmtree(str(worktree_dir), ignore_errors=True)

        res = subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{branch_name}"],
            cwd=repo_path,
            timeout=5,
        )
        if res.returncode == 0:
            if not worktree_dir.exists():
                try:
                    subprocess.run(
                        ["git", "worktree", "add", str(worktree_dir), branch_name],
                        check=True,
                        cwd=repo_path,
                        timeout=5,
                    )
                except subprocess.CalledProcessError:
                    subprocess.run(
                        ["git", "worktree", "prune"],
                        check=False,
                        cwd=repo_path,
                        capture_output=True,
                        timeout=10,
                    )
                    subprocess.run(
                        ["git", "worktree", "add", str(worktree_dir), branch_name],
                        check=True,
                        cwd=repo_path,
                        timeout=5,
                    )
            # Sync existing worktree with latest default branch if assignee is builder
            if assignee == "zf-builder" and worktree_dir.exists():
                _d().pull_and_merge_main(worktree_dir, repo_path, default_branch)
        else:
            if not worktree_dir.exists():
                try:
                    subprocess.run(
                        [
                            "git",
                            "worktree",
                            "add",
                            str(worktree_dir),
                            "-b",
                            branch_name,
                            base_ref,
                        ],
                        check=True,
                        cwd=repo_path,
                        timeout=5,
                    )
                except Exception:
                    subprocess.run(
                        [
                            "git",
                            "worktree",
                            "add",
                            str(worktree_dir),
                            "-b",
                            branch_name,
                            "HEAD",
                        ],
                        check=True,
                        cwd=repo_path,
                        timeout=5,
                    )
            # Sync newly created worktree with latest default branch if assignee is builder
            if assignee == "zf-builder" and worktree_dir.exists():
                _d().pull_and_merge_main(worktree_dir, repo_path, default_branch)

        # Provision side-by-side sibling repositories
        if cursor and board_slug:
            try:
                cursor.execute(
                    "SELECT repo_alias, git_url, target_branch FROM board_repositories WHERE board_slug = ? AND repo_alias != ?",
                    (board_slug, target_name),
                )
                sibling_rows = [dict(r) for r in cursor.fetchall()]
                for s in sibling_rows:
                    s_alias = (s.get("repo_alias") or "").strip()
                    if not s_alias:
                        continue
                    s_dir = task_root / s_alias
                    if not s_dir.exists():
                        s_repo = _d().resolve_task_repo_path(
                            cursor, board_slug, tenant, repo_alias=s_alias
                        )
                        if s_repo and s_repo.exists():
                            s_branch = (s.get("target_branch") or "main").strip()
                            try:
                                _d().sync_repo_main(s_repo, default_branch=s_branch)
                            except Exception:
                                pass
                            s_ref = f"origin/{s_branch}"
                            v = subprocess.run(
                                [
                                    "git",
                                    "show-ref",
                                    "--verify",
                                    "--quiet",
                                    f"refs/remotes/{s_ref}",
                                ],
                                cwd=s_repo,
                                timeout=5,
                            )
                            if v.returncode != 0:
                                v2 = subprocess.run(
                                    [
                                        "git",
                                        "show-ref",
                                        "--verify",
                                        "--quiet",
                                        f"refs/heads/{s_branch}",
                                    ],
                                    cwd=s_repo,
                                    timeout=5,
                                )
                                s_ref = s_branch if v2.returncode == 0 else "HEAD"
                            try:
                                subprocess.run(
                                    [
                                        "git",
                                        "worktree",
                                        "add",
                                        "--detach",
                                        str(s_dir),
                                        s_ref,
                                    ],
                                    check=True,
                                    cwd=s_repo,
                                    timeout=10,
                                    capture_output=True,
                                )
                            except Exception as sib_err:
                                _log.debug(
                                    "Could not add detached worktree for sibling %s: %s",
                                    s_alias,
                                    sib_err,
                                )
            except Exception as e:
                _log.debug(
                    "Error provisioning sibling worktrees for %s: %s", board_slug, e
                )

        cursor.execute(
            "UPDATE tasks SET workspace_kind = 'dir', workspace_path = ?, branch_name = ? WHERE id = ?",
            (str(worktree_dir), branch_name, task_id),
        )
        steps.end("ok", f"{worktree_dir} branch={branch_name}")
        return str(worktree_dir)
    except Exception as e:
        steps.end("error", f"{type(e).__name__}: {e}")
        _log.warning(
            "Worktree setup skipped or failed for task %s (%s): %s",
            task_id,
            repo_path,
            e,
        )
        return None


def _handle_local_merge_conflict(
    cursor: sqlite3.Cursor,
    task_id: str,
    title: str,
    workspace_path: str,
    conflict_files: list[str],
    now: int,
    err_msg: str = "",
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
        _log.debug(
            "Task %s has already reached conflict retries limit (%d > %d); skipping duplicate conflict failure handling",
            task_id,
            retries,
            max_conflict_retries,
        )
        return
    retries += 1
    meta["conflict_retries"] = retries
    meta.pop("awaiting_pr", None)

    file_msg = f" in: {', '.join(conflict_files)}" if conflict_files else ""

    if retries > max_conflict_retries:
        meta["blocked_reason"] = (
            f"Merge conflict resolution exceeded {max_conflict_retries} attempts{file_msg}"
        )
        meta["blocked_reason_type"] = "stuck"
        cursor.execute(
            "UPDATE tasks SET assignee = 'human', status = 'blocked', metadata = ?, updated_at = ? WHERE id = ?",
            (json.dumps(meta), now, task_id),
        )
        cursor.execute(
            "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'pr_conflict_failed', ?, ?)",
            (
                task_id,
                f"Merge conflict resolution exceeded {max_conflict_retries} attempts{file_msg}. Moved to blocked.",
                now,
            ),
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
                    now,
                ),
            )
        except Exception as e:
            _log.debug("Failed to record task comment for conflict limit: %s", e)
        return

    cursor.execute(
        "UPDATE tasks SET assignee = 'zf-builder', status = 'todo', metadata = ?, updated_at = ? WHERE id = ?",
        (json.dumps(meta), now, task_id),
    )
    cursor.execute(
        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'pr_conflict', ?, ?)",
        (
            task_id,
            f"Merge conflict with main branch detected{file_msg}. Routed back to zf-builder for resolution.",
            now,
        ),
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
                now,
            ),
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
            check=False,
            cwd=str(repo_path),
            capture_output=True,
            timeout=_REMOTE_BRANCH_DELETE_TIMEOUT,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
    except subprocess.TimeoutExpired:
        _log.warning(
            "Remote branch delete timed out after %ss for %s; leaving remote branch for manual cleanup",
            _REMOTE_BRANCH_DELETE_TIMEOUT,
            branch,
        )
        return
    except Exception as e:
        _log.warning("Remote branch delete failed for %s: %s", branch, e)
        return
    if res.returncode != 0:
        _log.warning(
            "Remote branch delete failed for %s (rc=%s): %s",
            branch,
            res.returncode,
            (res.stderr or res.stdout or "").strip(),
        )
    else:
        _log.info("Deleted remote branch %s (PR archived)", branch)


def _remove_worktree(workspace_path: str | None, repo_path: Path) -> None:
    """Safely remove a git worktree and any sibling worktrees without hanging the dispatch cycle."""
    if not workspace_path or not Path(workspace_path).exists():
        return

    ws_path = Path(workspace_path)
    task_root = ws_path.parent

    # 1. Clean up any sibling worktrees in task_root if under a -worktrees or workspaces/.../worktrees directory
    try:
        is_managed_worktree = "-worktrees" in str(task_root) or "worktrees" in task_root.parts
        if task_root.exists() and is_managed_worktree:
            for item in task_root.iterdir():
                if item.is_dir() and item != ws_path and (item / ".git").is_file():
                    try:
                        rev_res = subprocess.run(
                            ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                            cwd=str(item),
                            capture_output=True,
                            text=True,
                            timeout=5,
                        )
                        sib_main = None
                        if rev_res.returncode == 0:
                            c_dir = Path(rev_res.stdout.strip())
                            sib_main = c_dir.parent if c_dir.name == ".git" else c_dir
                        if sib_main and sib_main.exists():
                            subprocess.run(
                                ["git", "worktree", "remove", str(item), "--force"],
                                cwd=str(sib_main),
                                capture_output=True,
                                timeout=_WORKTREE_REMOVE_TIMEOUT,
                            )
                            subprocess.run(
                                ["git", "worktree", "prune"],
                                cwd=str(sib_main),
                                capture_output=True,
                                timeout=_WORKTREE_REMOVE_TIMEOUT,
                            )
                    except Exception as e:
                        _log.debug("Could not cleanly remove sibling worktree %s: %s", item, e)
    except Exception as e:
        _log.debug("Could not inspect siblings in task_root %s: %s", task_root, e)

    # 2. Remove primary worktree
    try:
        subprocess.run(
            ["git", "worktree", "remove", workspace_path, "--force"],
            check=False,
            cwd=str(repo_path),
            capture_output=True,
            timeout=_WORKTREE_REMOVE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        _log.warning(
            "Worktree remove timed out after %ss for %s; falling back to 'git worktree prune'",
            _WORKTREE_REMOVE_TIMEOUT,
            workspace_path,
        )
        try:
            subprocess.run(
                ["git", "worktree", "prune"],
                check=False,
                cwd=str(repo_path),
                capture_output=True,
                timeout=_WORKTREE_REMOVE_TIMEOUT,
            )
        except subprocess.TimeoutExpired as e:
            _log.warning(
                "Worktree prune also timed out after %ss for %s: %s",
                _WORKTREE_REMOVE_TIMEOUT,
                workspace_path,
                e.cmd,
            )
        return
    except Exception as e:
        _log.warning("Worktree remove failed for %s: %s", workspace_path, e)

    if Path(workspace_path).exists():
        try:
            subprocess.run(
                ["git", "worktree", "prune"],
                check=False,
                cwd=str(repo_path),
                capture_output=True,
                timeout=_WORKTREE_REMOVE_TIMEOUT,
            )
        except subprocess.TimeoutExpired as e:
            _log.warning(
                "Worktree prune timed out after %ss for %s: %s",
                _WORKTREE_REMOVE_TIMEOUT,
                workspace_path,
                e.cmd,
            )
        if Path(workspace_path).exists():
            _log.warning(
                "Worktree directory still present after cleanup attempts: %s",
                workspace_path,
            )

    # 3. Clean up task_root directory if empty or under -worktrees / workspaces/.../worktrees
    try:
        import shutil

        is_managed_task_root = (
            "-worktrees" in str(task_root)
            or ("worktrees" in task_root.parts and task_root.name == str(ws_path.parent.name))
        )
        if (
            task_root.exists()
            and is_managed_task_root
            and task_root != repo_path.parent
            and task_root != Path.home()
            and task_root != Path.home() / "git"
            and task_root != Path.home() / ".zerofactory"
        ):
            shutil.rmtree(str(task_root), ignore_errors=True)
    except Exception:
        pass


def _handle_pr_conflict_from_github(
    cursor: sqlite3.Cursor,
    task_id: str,
    title: str,
    workspace_path: str | None,
    repo_path: Path,
    tenant: str | None,
    db_path: Path,
    board_slug: str | None,
    now: int,
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
        _log.debug(
            "Task %s has already reached conflict retries limit (%d > %d); skipping duplicate PR conflict failure handling",
            task_id,
            retries,
            max_conflict_retries,
        )
        return
    retries += 1
    meta["conflict_retries"] = retries
    meta.pop("awaiting_pr", None)

    _d().stop_task_worker(task_id, cursor)
    if workspace_path and Path(workspace_path).exists():
        _d()._remove_worktree(workspace_path, repo_path)

    # PR author lives in metadata (set at packaging); titles carry no state.
    author = normalize_assignee(meta.get("packaged_by") or "zf-builder")
    if author == "zf-reviewer":
        author = "zf-builder"

    if retries > max_conflict_retries:
        meta["blocked_reason"] = (
            f"GitHub PR conflict resolution exceeded {max_conflict_retries} attempts"
        )
        meta["blocked_reason_type"] = "stuck"
        cursor.execute(
            "UPDATE tasks SET assignee = 'human', status = 'blocked', metadata = ?, updated_at = ? WHERE id = ?",
            (json.dumps(meta), now, task_id),
        )
        cursor.execute(
            "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'pr_conflict_failed', ?, ?)",
            (
                task_id,
                f"GitHub PR conflict resolution exceeded {max_conflict_retries} attempts. Moved to blocked.",
                now,
            ),
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
                    now,
                ),
            )
        except Exception as e:
            _log.debug("Failed to record task comment for conflict limit: %s", e)
        return

    wt_path = _d().setup_worktree(
        cursor,
        task_id,
        title,
        author,
        tenant,
        db_path,
        board_slug=board_slug,
        repo_path=repo_path,
    )
    conflict_files = []
    if wt_path and Path(wt_path).exists():
        _verified, conflict_files, _err = _d().check_unresolved_conflicts_safe(
            Path(wt_path)
        )

    file_msg = f" in {', '.join(conflict_files)}" if conflict_files else ""
    cursor.execute(
        "UPDATE tasks SET assignee = ?, status = 'todo', metadata = ?, updated_at = ? WHERE id = ?",
        (author, json.dumps(meta), now, task_id),
    )
    cursor.execute(
        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'pr_conflict', ?, ?)",
        (
            task_id,
            f"GitHub PR is conflicting with main branch{file_msg}. Routed to {author} to resolve conflicts.",
            now,
        ),
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
                now,
            ),
        )
    except Exception as e:
        _log.debug("Failed to record task comment for conflict: %s", e)


def run_deterministic_precommit(workspace_path: Path) -> tuple[bool, str, int]:
    """Execute .zerofactory/precommit.sh in the workspace if present.

    Returns:
        (passed, output_or_error, exit_code)
    """
    if os.environ.get("ZEROFACTORY_SKIP_PRECOMMIT"):
        return True, "ZEROFACTORY_SKIP_PRECOMMIT enabled", 0

    script_path = workspace_path / ".zerofactory" / "precommit.sh"
    if not script_path.is_file():
        return True, "No .zerofactory/precommit.sh found", 0

    try:
        current_mode = script_path.stat().st_mode
        script_path.chmod(current_mode | 0o755)
    except Exception:
        pass

    timeout = int(os.environ.get("ZEROFACTORY_PRECOMMIT_TIMEOUT_SECONDS", "300"))
    env = {**os.environ, "CI": "1", "ZEROFACTORY_PRECOMMIT": "1"}

    try:
        res = subprocess.run(
            ["bash", str(script_path)],
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            timeout=timeout,
            env=env,
        )
        out = res.stdout or ""
        if res.stderr:
            out += "\n" + res.stderr if out else res.stderr
        if res.returncode == 0:
            return True, out.strip(), 0
        return (
            False,
            out.strip() or f"Precommit script exited with code {res.returncode}",
            res.returncode,
        )
    except subprocess.TimeoutExpired as te:
        out = te.stdout or ""
        if te.stderr:
            out += "\n" + te.stderr if out else te.stderr
        return False, f"Precommit script timed out after {timeout}s.\n{out}".strip(), -1
    except Exception as e:
        return False, f"Precommit script execution failed: {e}", -1


def _handle_precommit_failure(
    cursor: sqlite3.Cursor,
    task_id: str,
    title: str,
    workspace_path: str,
    err_output: str,
    now: int,
) -> None:
    """Handle deterministic precommit check failure before git commit/push."""
    max_retries = int(os.environ.get("ZEROFACTORY_MAX_PRECOMMIT_RETRIES", "3"))

    cursor.execute("SELECT metadata FROM tasks WHERE id = ?", (task_id,))
    row = cursor.fetchone()
    meta = {}
    if row and row[0]:
        try:
            meta = json.loads(row[0])
        except Exception:
            meta = {}

    retries = int(meta.get("precommit_retries", 0)) + 1
    meta["precommit_retries"] = retries
    meta["last_precommit_error"] = err_output[:2500]

    snippet = err_output.strip()
    if len(snippet) > 1500:
        snippet = snippet[-1500:]

    if retries > max_retries:
        meta["blocked_reason"] = (
            f"Deterministic precommit failed after {max_retries} attempts"
        )
        meta["blocked_reason_type"] = "stuck"
        cursor.execute(
            "UPDATE tasks SET assignee = 'human', status = 'blocked', metadata = ?, updated_at = ? WHERE id = ?",
            (json.dumps(meta), now, task_id),
        )
        cursor.execute(
            "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'precommit_failed', ?, ?)",
            (
                task_id,
                f"Deterministic precommit failed after {max_retries} attempts. Moved to blocked.",
                now,
            ),
        )
        try:
            cursor.execute(
                "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, ?, ?, ?)",
                (
                    task_id,
                    "dispatcher",
                    f"🚨 **Deterministic Precommit Failed**: Execution of `.zerofactory/precommit.sh` failed after {max_retries} attempts.\n\n```\n{snippet}\n```\nMoved task to **blocked** for inspection.",
                    now,
                ),
            )
        except Exception as e:
            _log.warning(
                "Failed to insert precommit failure comment for task %s: %s", task_id, e
            )
    else:
        # Route back to the builder as a claimable 'todo' retry (the precommit
        # failure output is injected into the respawned worker's prompt); clear
        # awaiting_pr — this is builder work again, not the packaging phase.
        meta.pop("awaiting_pr", None)
        cursor.execute(
            "UPDATE tasks SET assignee = 'zf-builder', status = 'todo', metadata = ?, updated_at = ? WHERE id = ?",
            (json.dumps(meta), now, task_id),
        )
        cursor.execute(
            "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'precommit_failed_retry', ?, ?)",
            (
                task_id,
                f"Deterministic precommit failed (attempt {retries}/{max_retries}); routing back to zf-builder",
                now,
            ),
        )
        try:
            cursor.execute(
                "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, ?, ?, ?)",
                (
                    task_id,
                    "dispatcher",
                    f"🚨 **Deterministic Precommit Failed** (Attempt {retries}/{max_retries})\n\nExecution of `.zerofactory/precommit.sh` failed with output:\n```\n{snippet}\n```\nPlease fix the formatting, build, or test failures and mark done.",
                    now,
                ),
            )
        except Exception as e:
            _log.warning(
                "Failed to insert precommit retry comment for task %s: %s", task_id, e
            )
