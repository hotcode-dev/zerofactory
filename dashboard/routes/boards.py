"""Zero Factory Dashboard — Board routes (/boards)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any

_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)
_DASHBOARD_ROOT = str(Path(__file__).resolve().parent.parent)
if _DASHBOARD_ROOT not in sys.path:
    sys.path.insert(0, _DASHBOARD_ROOT)

from fastapi import APIRouter, HTTPException

try:
    from ..db import get_db_conn, init_db, parse_git_url
    from ..models import (
        BoardCreate,
        BoardRepoCreate,
        BoardRepoUpdate,
        BoardTestClone,
        BoardArchitectureUpdate,
        BoardUpdate,
        JiraSetupRequest,
    )
    from ..setup_common import get_repo_resolver
except (ImportError, ValueError):
    from db import get_db_conn, init_db, parse_git_url  # type: ignore
    from models import (  # type: ignore
        BoardCreate,
        BoardRepoCreate,
        BoardRepoUpdate,
        BoardTestClone,
        BoardArchitectureUpdate,
        BoardUpdate,
        JiraSetupRequest,
    )
    from setup_common import get_repo_resolver  # type: ignore

_log = logging.getLogger(__name__)

router = APIRouter()


def _get_cron_helpers():
    """Import builtin cron engine functions reliably regardless of how plugin_api is loaded."""
    try:
        from ...builtin_cron import (
            ensure_builtin_cron_jobs,
            list_builtin_jobs,
            prune_board_cron_job,
            reset_builtin_job,
            toggle_builtin_job,
            trigger_builtin_job,
            update_builtin_job,
        )

        return (
            ensure_builtin_cron_jobs,
            prune_board_cron_job,
            trigger_builtin_job,
            list_builtin_jobs,
            update_builtin_job,
            toggle_builtin_job,
            reset_builtin_job,
        )
    except Exception:
        pass
    try:
        from builtin_cron import (  # type: ignore
            ensure_builtin_cron_jobs,
            list_builtin_jobs,
            prune_board_cron_job,
            reset_builtin_job,
            toggle_builtin_job,
            trigger_builtin_job,
            update_builtin_job,
        )

        return (
            ensure_builtin_cron_jobs,
            prune_board_cron_job,
            trigger_builtin_job,
            list_builtin_jobs,
            update_builtin_job,
            toggle_builtin_job,
            reset_builtin_job,
        )
    except Exception:
        pass
    try:
        parent_dir = str(Path(__file__).resolve().parent.parent.parent)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        import builtin_cron

        return (
            builtin_cron.ensure_builtin_cron_jobs,
            builtin_cron.prune_board_cron_job,
            builtin_cron.trigger_builtin_job,
            builtin_cron.list_builtin_jobs,
            builtin_cron.update_builtin_job,
            builtin_cron.toggle_builtin_job,
            builtin_cron.reset_builtin_job,
        )
    except Exception as e:
        _log.warning("Failed to resolve builtin_cron helpers: %s", e)
        return None, None, None, None, None, None, None


@router.get("/boards")
@router.get("/boards")
def list_boards():
    """List all Kanban boards with their linked repositories."""
    init_db()
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM boards ORDER BY created_at ASC")
        boards = [dict(row) for row in cursor.fetchall()]

        for b in boards:
            b["jira_url"] = (b.get("jira_url") or "").strip()
            b["architecture"] = (b.get("architecture") or "").strip()
            b["auto_record_memory"] = bool(b.get("auto_record_memory", 1))
            cursor.execute(
                "SELECT id, board_slug, repo_alias, git_url, target_branch, additional_reviewer_usernames, created_at, updated_at "
                "FROM board_repositories WHERE board_slug = ? ORDER BY id ASC",
                (b["slug"],),
            )
            repos = [dict(r) for r in cursor.fetchall()]
            for r in repos:
                try:
                    r["additional_reviewer_usernames"] = json.loads(
                        r.get("additional_reviewer_usernames") or "[]"
                    )
                except Exception:
                    r["additional_reviewer_usernames"] = []
            b["repositories"] = repos
            if repos:
                b["git_url"] = repos[0]["git_url"]
                b["target_branch"] = repos[0]["target_branch"]
                b["additional_reviewer_usernames"] = repos[0]["additional_reviewer_usernames"]
            else:
                b["git_url"] = ""
                b["target_branch"] = "main"
                b["additional_reviewer_usernames"] = []

            cursor.execute(
                "SELECT COUNT(*) as count FROM tasks WHERE board_slug = ?", (b["slug"],)
            )
            b["task_count"] = cursor.fetchone()["count"]
            cursor.execute(
                "SELECT COUNT(*) as count FROM tasks WHERE board_slug = ? AND status = 'running'",
                (b["slug"],),
            )
            b["running_count"] = cursor.fetchone()["count"]
        return {"ok": True, "boards": boards}


@router.get("/boards/{slug}")
def get_board(slug: str):
    """Get a single board with its linked repositories and architecture notes."""
    init_db()
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM boards WHERE slug = ?", (slug,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Board '{slug}' not found")
        b = dict(row)
        b["jira_url"] = (b.get("jira_url") or "").strip()
        b["architecture"] = (b.get("architecture") or "").strip()
        b["auto_record_memory"] = bool(b.get("auto_record_memory", 1))
        cursor.execute(
            "SELECT id, board_slug, repo_alias, git_url, target_branch, additional_reviewer_usernames, created_at, updated_at "
            "FROM board_repositories WHERE board_slug = ? ORDER BY id ASC",
            (slug,),
        )
        repos = [dict(r) for r in cursor.fetchall()]
        for r in repos:
            try:
                r["additional_reviewer_usernames"] = json.loads(
                    r.get("additional_reviewer_usernames") or "[]"
                )
            except Exception:
                r["additional_reviewer_usernames"] = []
        b["repositories"] = repos
        if repos:
            b["git_url"] = repos[0]["git_url"]
            b["target_branch"] = repos[0]["target_branch"]
            b["additional_reviewer_usernames"] = repos[0]["additional_reviewer_usernames"]
        else:
            b["git_url"] = ""
            b["target_branch"] = "main"
            b["additional_reviewer_usernames"] = []

        cursor.execute(
            "SELECT COUNT(*) as count FROM tasks WHERE board_slug = ?", (slug,)
        )
        b["task_count"] = cursor.fetchone()["count"]
        cursor.execute(
            "SELECT COUNT(*) as count FROM tasks WHERE board_slug = ? AND status = 'running'",
            (slug,),
        )
        b["running_count"] = cursor.fetchone()["count"]
        return {"ok": True, "board": b}


@router.post("/boards")
def create_board(req: BoardCreate):
    """Create a new board / project with linked repositories."""
    init_db()
    now = int(time.time())

    # Build repo list
    repos_to_add: list[dict[str, Any]] = []

    top_git_url = (req.git_url or "").strip()
    if top_git_url:
        _, repo, auto_slug = parse_git_url(top_git_url)
        top_alias = repo or auto_slug or "main"
        top_branch = (req.target_branch or "main").strip()
        top_reviewers = sorted({
            u.strip().lstrip("@").lower()
            for u in (req.additional_reviewer_usernames or [])
            if u and u.strip()
        })
        repos_to_add.append({
            "repo_alias": top_alias,
            "git_url": top_git_url,
            "target_branch": top_branch,
            "additional_reviewer_usernames": top_reviewers,
        })

    if req.repositories:
        for r in req.repositories:
            alias = (r.repo_alias or "").strip()
            url = (r.git_url or "").strip()
            if not alias or not url:
                continue
            if any(existing["repo_alias"] == alias for existing in repos_to_add):
                continue
            branch = (r.target_branch or "main").strip()
            reviewers = sorted({
                u.strip().lstrip("@").lower()
                for u in (r.additional_reviewer_usernames or [])
                if u and u.strip()
            })
            repos_to_add.append({
                "repo_alias": alias,
                "git_url": url,
                "target_branch": branch,
                "additional_reviewer_usernames": reviewers,
            })

    if not repos_to_add:
        raise HTTPException(
            status_code=400,
            detail="At least one repository or remote Git URL is required",
        )

    slug = (req.slug or "").strip()
    if not slug:
        if top_git_url:
            _, _, auto_slug = parse_git_url(top_git_url)
            slug = auto_slug
        if not slug:
            first_url = repos_to_add[0]["git_url"]
            _, _, auto_slug = parse_git_url(first_url)
            slug = auto_slug or repos_to_add[0]["repo_alias"]

    if not slug:
        raise HTTPException(status_code=400, detail="Invalid board slug")

    desc = (req.description or "").strip()
    jira_url = (req.jira_url or "").strip()
    architecture = (req.architecture or "").strip()
    mcr = max(1, req.max_concurrent_running or 1)
    arm = 1 if (req.auto_record_memory is None or req.auto_record_memory) else 0

    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT slug FROM boards WHERE slug = ?", (slug,))
        if cursor.fetchone():
            raise HTTPException(
                status_code=409, detail=f"Board '{slug}' already exists"
            )

        cursor.execute(
            """INSERT INTO boards (
                slug, description, max_concurrent_running, 
                auto_record_memory, jira_url, architecture, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (slug, desc, mcr, arm, jira_url, architecture, now, now),
        )

        for r in repos_to_add:
            cursor.execute(
                """INSERT INTO board_repositories
                   (board_slug, repo_alias, git_url, target_branch, additional_reviewer_usernames, created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(board_slug, repo_alias) DO UPDATE SET
                       git_url = excluded.git_url,
                       target_branch = excluded.target_branch,
                       additional_reviewer_usernames = excluded.additional_reviewer_usernames,
                       updated_at = excluded.updated_at""",
                (
                    slug,
                    r["repo_alias"],
                    r["git_url"],
                    r["target_branch"],
                    json.dumps(r["additional_reviewer_usernames"]),
                    now,
                    now,
                ),
            )
        conn.commit()

    # Attempt repository clone / resolution for each repo
    resolver = get_repo_resolver()
    if resolver:
        for r in repos_to_add:
            try:
                resolver({"slug": r["repo_alias"], "git_url": r["git_url"], "description": desc})
            except Exception as e:
                _log.warning(
                    "Failed to auto-clone repo %s for board %s: %s", r["repo_alias"], slug, e
                )

    if not os.environ.get("ZEROFACTORY_SKIP_CRON_SYNC"):
        ensure_cron, *_ = _get_cron_helpers()
        if ensure_cron:
            try:
                ensure_cron()
            except Exception as e:
                _log.warning(
                    "Failed to sync cron jobs after creating board %s: %s", slug, e
                )

    setup_task_id = None
    if getattr(req, "auto_setup_precommit", False) and not os.environ.get(
        "ZEROFACTORY_SKIP_PRECOMMIT_SETUP"
    ):
        try:
            try:
                from ..precommit_service import (
                    check_board_precommit_status,
                    create_precommit_setup_task,
                )
            except (ImportError, ValueError):
                from precommit_service import (
                    check_board_precommit_status,
                    create_precommit_setup_task,
                )  # type: ignore
            status_info = check_board_precommit_status(slug, repo_alias=repos_to_add[0]["repo_alias"])
            if not status_info.get("has_precommit"):
                res = create_precommit_setup_task(slug, repo_alias=repos_to_add[0]["repo_alias"])
                if res.get("ok"):
                    setup_task_id = res.get("task_id")
        except Exception as e:
            _log.warning(
                "Failed to auto-trigger precommit setup for board %s: %s", slug, e
            )

    resp = {"ok": True, "slug": slug}
    if setup_task_id:
        resp["setup_task_id"] = setup_task_id
    return resp


@router.post("/boards/test-clone")
def test_clone_board(req: BoardTestClone):
    """Test Git connectivity and clone the repository for a board."""
    git_url = (req.git_url or "").strip()
    if not git_url:
        raise HTTPException(status_code=400, detail="Remote Git URL is required")

    owner, repo, auto_slug = parse_git_url(git_url)
    slug = (req.slug or "").strip() or auto_slug or "repo"

    # If git operations disabled in test environment
    if os.environ.get("ZEROFACTORY_SKIP_GIT"):
        return {
            "ok": True,
            "message": "Git operations disabled via ZEROFACTORY_SKIP_GIT",
            "cloned": False,
            "path": None,
        }

    try:
        resolve_board_repo_path = get_repo_resolver()
        if resolve_board_repo_path is None:
            raise RuntimeError("resolve_board_repo_path could not be imported")

        # 1. First check if it's already resolved / cloned locally
        existing_path = resolve_board_repo_path({"slug": slug, "git_url": git_url})
        if (
            existing_path
            and existing_path.is_dir()
            and (existing_path / ".git").exists()
        ):
            return {
                "ok": True,
                "message": f"Git repository verified! Already cloned at {existing_path}",
                "cloned": True,
                "path": str(existing_path),
            }

        # 2. Check remote connectivity first via git ls-remote
        ls_res = subprocess.run(
            ["git", "ls-remote", "--heads", git_url],
            capture_output=True,
            text=True,
            timeout=15,
            stdin=subprocess.DEVNULL,
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"},
        )
        if ls_res.returncode != 0:
            err_msg = (
                ls_res.stderr.strip() or "Could not connect to remote Git repository"
            )
            raise HTTPException(
                status_code=400, detail=f"Git remote check failed: {err_msg}"
            )

        # 3. Attempt clone via resolve_board_repo_path
        cloned_path = resolve_board_repo_path({"slug": slug, "git_url": git_url})
        if cloned_path and cloned_path.is_dir() and (cloned_path / ".git").exists():
            return {
                "ok": True,
                "message": f"Successfully cloned repository to {cloned_path}!",
                "cloned": True,
                "path": str(cloned_path),
            }
        else:
            raise HTTPException(
                status_code=500,
                detail="Git clone failed to create a valid repository directory",
            )

    except HTTPException:
        raise
    except Exception as e:
        _log.warning("Test clone failed for %s: %s", git_url, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/boards/{slug}")
@router.put("/boards/{slug}")
def update_board(slug: str, req: BoardUpdate):
    """Update board metadata and repositories."""
    init_db()
    now = int(time.time())
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT slug FROM boards WHERE slug = ?", (slug,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Board '{slug}' not found")

        updates = []
        params = []
        if req.description is not None:
            updates.append("description = ?")
            params.append(req.description.strip())
        if req.max_concurrent_running is not None:
            mcr = max(1, int(req.max_concurrent_running))
            updates.append("max_concurrent_running = ?")
            params.append(mcr)
        if req.auto_record_memory is not None:
            arm = 1 if req.auto_record_memory else 0
            updates.append("auto_record_memory = ?")
            params.append(arm)
        if req.jira_url is not None:
            updates.append("jira_url = ?")
            params.append(req.jira_url.strip())
        if req.architecture is not None:
            updates.append("architecture = ?")
            params.append(req.architecture.strip())
        if updates:
            updates.append("updated_at = ?")
            params.append(now)
            params.append(slug)
            cursor.execute(
                f"UPDATE boards SET {', '.join(updates)} WHERE slug = ?", params
            )

        if req.repositories is not None:
            for r in req.repositories:
                r_alias = r.repo_alias.strip()
                if not r_alias:
                    continue
                r_url = r.git_url.strip()
                r_branch = (r.target_branch or "main").strip()
                reviewers = sorted({
                    u.strip().lstrip("@").lower()
                    for u in (r.additional_reviewer_usernames or [])
                    if u and u.strip()
                })
                cursor.execute(
                    """INSERT INTO board_repositories 
                       (board_slug, repo_alias, git_url, target_branch, additional_reviewer_usernames, created_at, updated_at)
                       VALUES (?, ?, ?, ?, ?, ?, ?)
                       ON CONFLICT(board_slug, repo_alias) DO UPDATE SET
                           git_url = excluded.git_url,
                           target_branch = excluded.target_branch,
                           additional_reviewer_usernames = excluded.additional_reviewer_usernames,
                           updated_at = excluded.updated_at""",
                    (slug, r_alias, r_url, r_branch, json.dumps(reviewers), now, now),
                )
        elif (
            req.target_branch is not None
            or req.additional_reviewer_usernames is not None
            or req.git_url is not None
        ):
            first_repo = cursor.execute(
                "SELECT id, repo_alias FROM board_repositories WHERE board_slug = ? ORDER BY id ASC LIMIT 1",
                (slug,),
            ).fetchone()
            if first_repo:
                r_id = first_repo[0]
                r_updates = []
                r_params = []
                if req.git_url is not None:
                    r_updates.append("git_url = ?")
                    r_params.append(req.git_url.strip())
                if req.target_branch is not None:
                    r_updates.append("target_branch = ?")
                    r_params.append(req.target_branch.strip())
                if req.additional_reviewer_usernames is not None:
                    reviewers = sorted({
                        u.strip().lstrip("@").lower()
                        for u in req.additional_reviewer_usernames
                        if u and u.strip()
                    })
                    r_updates.append("additional_reviewer_usernames = ?")
                    r_params.append(json.dumps(reviewers))
                if r_updates:
                    r_updates.append("updated_at = ?")
                    r_params.append(now)
                    r_params.append(r_id)
                    cursor.execute(
                        f"UPDATE board_repositories SET {', '.join(r_updates)} WHERE id = ?",
                        r_params,
                    )

        conn.commit()

        cursor.execute("SELECT * FROM boards WHERE slug = ?", (slug,))
        row = cursor.fetchone()
        board_data = dict(row) if row else {"slug": slug}
        board_data["jira_url"] = (board_data.get("jira_url") or "").strip()
        board_data["architecture"] = (board_data.get("architecture") or "").strip()
        board_data["auto_record_memory"] = bool(board_data.get("auto_record_memory", 1))

        cursor.execute(
            """SELECT id, board_slug, repo_alias, git_url, target_branch, additional_reviewer_usernames, created_at, updated_at
               FROM board_repositories WHERE board_slug = ? ORDER BY id ASC""",
            (slug,),
        )
        repos = [dict(r) for r in cursor.fetchall()]
        for r in repos:
            try:
                r["additional_reviewer_usernames"] = json.loads(
                    r.get("additional_reviewer_usernames") or "[]"
                )
            except Exception:
                r["additional_reviewer_usernames"] = []
        board_data["repositories"] = repos
        if repos:
            board_data["git_url"] = repos[0]["git_url"]
            board_data["target_branch"] = repos[0]["target_branch"]
            board_data["additional_reviewer_usernames"] = repos[0]["additional_reviewer_usernames"]
        else:
            board_data["git_url"] = ""
            board_data["target_branch"] = "main"
            board_data["additional_reviewer_usernames"] = []

    if not os.environ.get("ZEROFACTORY_SKIP_CRON_SYNC"):
        ensure_cron, *_ = _get_cron_helpers()
        if ensure_cron:
            try:
                ensure_cron()
            except Exception as e:
                _log.warning(
                    "Failed to sync cron jobs after updating board %s: %s", slug, e
                )

    return {"ok": True, "slug": slug, "board": board_data}


@router.get("/boards/{slug}/repositories")
def get_board_repositories(slug: str):
    """List all repositories linked to a board."""
    init_db()
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT slug FROM boards WHERE slug = ?", (slug,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Board '{slug}' not found")
        cursor.execute(
            """SELECT id, board_slug, repo_alias, git_url, target_branch, additional_reviewer_usernames, created_at, updated_at
               FROM board_repositories WHERE board_slug = ? ORDER BY id ASC""",
            (slug,),
        )
        repos = [dict(r) for r in cursor.fetchall()]
        for r in repos:
            try:
                r["additional_reviewer_usernames"] = json.loads(
                    r.get("additional_reviewer_usernames") or "[]"
                )
            except Exception:
                r["additional_reviewer_usernames"] = []
        return {"ok": True, "repositories": repos}


@router.post("/boards/{slug}/repositories")
def add_board_repository(slug: str, req: BoardRepoCreate):
    """Add a new repository to a board."""
    init_db()
    now = int(time.time())
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT slug FROM boards WHERE slug = ?", (slug,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Board '{slug}' not found")

        r_alias = req.repo_alias.strip()
        r_url = req.git_url.strip()
        r_branch = (req.target_branch or "main").strip()
        reviewers = sorted({
            u.strip().lstrip("@").lower()
            for u in (req.additional_reviewer_usernames or [])
            if u and u.strip()
        })

        cursor.execute(
            "SELECT id FROM board_repositories WHERE board_slug = ? AND repo_alias = ?",
            (slug, r_alias),
        )
        if cursor.fetchone():
            raise HTTPException(
                status_code=409,
                detail=f"Repository '{r_alias}' already exists on board '{slug}'",
            )

        cursor.execute(
            """INSERT INTO board_repositories
               (board_slug, repo_alias, git_url, target_branch, additional_reviewer_usernames, created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (slug, r_alias, r_url, r_branch, json.dumps(reviewers), now, now),
        )
        conn.commit()

        cursor.execute(
            "SELECT id, board_slug, repo_alias, git_url, target_branch, additional_reviewer_usernames, created_at, updated_at FROM board_repositories WHERE board_slug = ? AND repo_alias = ?",
            (slug, r_alias),
        )
        row = dict(cursor.fetchone())
        try:
            row["additional_reviewer_usernames"] = json.loads(
                row.get("additional_reviewer_usernames") or "[]"
            )
        except Exception:
            row["additional_reviewer_usernames"] = []
        return {"ok": True, "repository": row}


@router.put("/boards/{slug}/repositories/{repo_alias}")
@router.patch("/boards/{slug}/repositories/{repo_alias}")
def update_board_repository(slug: str, repo_alias: str, req: BoardRepoUpdate):
    """Update properties of a linked repository."""
    init_db()
    now = int(time.time())
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "SELECT id FROM board_repositories WHERE board_slug = ? AND repo_alias = ?",
            (slug, repo_alias),
        )
        if not cursor.fetchone():
            raise HTTPException(
                status_code=404,
                detail=f"Repository '{repo_alias}' not found on board '{slug}'",
            )

        updates = []
        params = []
        if req.git_url is not None:
            updates.append("git_url = ?")
            params.append(req.git_url.strip())
        if req.target_branch is not None:
            updates.append("target_branch = ?")
            params.append(req.target_branch.strip())
        if req.additional_reviewer_usernames is not None:
            reviewers = sorted({
                u.strip().lstrip("@").lower()
                for u in req.additional_reviewer_usernames
                if u and u.strip()
            })
            updates.append("additional_reviewer_usernames = ?")
            params.append(json.dumps(reviewers))

        if updates:
            updates.append("updated_at = ?")
            params.append(now)
            params.append(slug)
            params.append(repo_alias)
            cursor.execute(
                f"UPDATE board_repositories SET {', '.join(updates)} WHERE board_slug = ? AND repo_alias = ?",
                params,
            )
            conn.commit()

        cursor.execute(
            "SELECT id, board_slug, repo_alias, git_url, target_branch, additional_reviewer_usernames, created_at, updated_at FROM board_repositories WHERE board_slug = ? AND repo_alias = ?",
            (slug, repo_alias),
        )
        row = dict(cursor.fetchone())
        try:
            row["additional_reviewer_usernames"] = json.loads(
                row.get("additional_reviewer_usernames") or "[]"
            )
        except Exception:
            row["additional_reviewer_usernames"] = []
        return {"ok": True, "repository": row}


@router.delete("/boards/{slug}/repositories/{repo_alias}")
def delete_board_repository(slug: str, repo_alias: str):
    """Remove a repository from a board."""
    init_db()
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "DELETE FROM board_repositories WHERE board_slug = ? AND repo_alias = ?",
            (slug, repo_alias),
        )
        if cursor.rowcount == 0:
            raise HTTPException(
                status_code=404,
                detail=f"Repository '{repo_alias}' not found on board '{slug}'",
            )
        conn.commit()
        return {"ok": True, "repo_alias": repo_alias}


@router.get("/boards/{slug}/architecture")
def get_board_architecture(slug: str):
    """Get system architecture notes for a board."""
    init_db()
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT architecture FROM boards WHERE slug = ?", (slug,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Board '{slug}' not found")
        return {"ok": True, "architecture": row[0] or ""}


@router.put("/boards/{slug}/architecture")
def update_board_architecture(slug: str, req: BoardArchitectureUpdate):
    """Update system architecture notes for a board."""
    init_db()
    now = int(time.time())
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT slug FROM boards WHERE slug = ?", (slug,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Board '{slug}' not found")
        cursor.execute(
            "UPDATE boards SET architecture = ?, updated_at = ? WHERE slug = ?",
            (req.architecture, now, slug),
        )
        conn.commit()
        return {"ok": True, "architecture": req.architecture}


@router.delete("/boards/{slug}")
def delete_board(slug: str):
    """Delete a board and its associated tasks."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM board_memories WHERE board_slug = ?", (slug,))
        cursor.execute("DELETE FROM tasks WHERE board_slug = ?", (slug,))
        cursor.execute("DELETE FROM boards WHERE slug = ?", (slug,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Board '{slug}' not found")
        conn.commit()

    if not os.environ.get("ZEROFACTORY_SKIP_CRON_SYNC"):
        ensure_cron, prune_cron, *_ = _get_cron_helpers()
        if prune_cron:
            try:
                prune_cron(slug)
            except Exception as e:
                _log.warning(
                    "Failed to prune cron job for deleted board %s: %s", slug, e
                )

        if ensure_cron:
            try:
                ensure_cron()
            except Exception as e:
                _log.warning(
                    "Failed to sync cron jobs after deleting board %s: %s", slug, e
                )

    return {"ok": True, "deleted": slug}


@router.get("/boards/{slug}/precommit-status")
@router.get("/boards/{slug}/repositories/{repo_alias}/precommit-status")
def get_board_precommit_status_endpoint(slug: str, repo_alias: str | None = None):
    """Get the precommit script and active setup task status for a board repository."""
    try:
        from ..precommit_service import check_board_precommit_status
    except (ImportError, ValueError):
        from precommit_service import check_board_precommit_status  # type: ignore

    res = check_board_precommit_status(slug, repo_alias=repo_alias)
    if not res.get("ok"):
        raise HTTPException(
            status_code=404, detail=res.get("error", f"Board '{slug}' not found")
        )
    return res


@router.post("/boards/{slug}/setup-precommit")
@router.post("/boards/{slug}/repositories/{repo_alias}/setup-precommit")
def setup_board_precommit_endpoint(slug: str, repo_alias: str | None = None):
    """Trigger creation of a P0 setup task to generate .zerofactory/precommit.sh."""
    try:
        from ..precommit_service import create_precommit_setup_task
    except (ImportError, ValueError):
        from precommit_service import create_precommit_setup_task  # type: ignore

    res = create_precommit_setup_task(slug, repo_alias=repo_alias)
    if not res.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=res.get("error", "Failed to initiate precommit setup task"),
        )
    return res


@router.get("/boards/{slug}/openwiki-status")
@router.get("/boards/{slug}/repositories/{repo_alias}/openwiki-status")
def get_board_openwiki_status_endpoint(slug: str, repo_alias: str | None = None):
    """Get the openwiki documentation and active setup task status for a board repository."""
    try:
        from ..openwiki_service import check_board_openwiki_status
    except (ImportError, ValueError):
        from openwiki_service import check_board_openwiki_status  # type: ignore

    res = check_board_openwiki_status(slug, repo_alias=repo_alias)
    if not res.get("ok"):
        raise HTTPException(
            status_code=404, detail=res.get("error", f"Board '{slug}' not found")
        )
    return res


@router.post("/boards/{slug}/setup-openwiki")
@router.post("/boards/{slug}/repositories/{repo_alias}/setup-openwiki")
def setup_board_openwiki_endpoint(slug: str, repo_alias: str | None = None):
    """Trigger creation of a P0 setup task to generate openwiki/ agent documentation."""
    try:
        from ..openwiki_service import create_openwiki_setup_task
    except (ImportError, ValueError):
        from openwiki_service import create_openwiki_setup_task  # type: ignore

    res = create_openwiki_setup_task(slug, repo_alias=repo_alias)
    if not res.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=res.get("error", "Failed to initiate OpenWiki setup task"),
        )
    return res


@router.get("/boards/{slug}/gh-issues-status")
@router.get("/boards/{slug}/repositories/{repo_alias}/gh-issues-status")
def get_board_gh_issues_status_endpoint(slug: str, repo_alias: str | None = None):
    """Get the GitHub issue templates status and active setup task status for a board repository."""
    try:
        from ..gh_issues_service import check_board_gh_issues_status
    except (ImportError, ValueError):
        from gh_issues_service import check_board_gh_issues_status  # type: ignore

    res = check_board_gh_issues_status(slug, repo_alias=repo_alias)
    if not res.get("ok"):
        raise HTTPException(
            status_code=404, detail=res.get("error", f"Board '{slug}' not found")
        )
    return res


@router.post("/boards/{slug}/setup-gh-issues")
@router.post("/boards/{slug}/repositories/{repo_alias}/setup-gh-issues")
def setup_board_gh_issues_endpoint(slug: str, repo_alias: str | None = None):
    """Create (or deduplicate to) a P0 setup task that ships GitHub Issue templates and labels."""
    try:
        from ..gh_issues_service import create_gh_issues_setup_task
    except (ImportError, ValueError):
        from gh_issues_service import create_gh_issues_setup_task  # type: ignore

    res = create_gh_issues_setup_task(slug, repo_alias=repo_alias)

    if not res.get("ok"):
        raise HTTPException(
            status_code=400,
            detail=res.get("error", "Failed to setup GitHub issues"),
        )
    return res


@router.get("/boards/{slug}/sync-gh-issues")
@router.post("/boards/{slug}/sync-gh-issues")
@router.post("/boards/{slug}/repositories/{repo_alias}/sync-gh-issues")
def sync_board_gh_issues_endpoint(
    slug: str, repo_alias: str | None = None, label: str = "zerofactory", force: bool = False
):
    """Scan and import open GitHub issues requested for AI investigation into human-gated Triage tasks."""
    init_db()
    with get_db_conn() as conn:
        board = conn.execute("SELECT * FROM boards WHERE slug = ?", (slug,)).fetchone()
        if not board:
            raise HTTPException(status_code=404, detail=f"Board '{slug}' not found")
        board_dict = dict(board)

        if repo_alias:
            repo_row = conn.execute(
                "SELECT git_url, repo_alias FROM board_repositories WHERE board_slug = ? AND repo_alias = ?",
                (slug, repo_alias),
            ).fetchone()
        else:
            repo_row = conn.execute(
                "SELECT git_url, repo_alias FROM board_repositories WHERE board_slug = ? ORDER BY id ASC LIMIT 1",
                (slug,),
            ).fetchone()

        git_url = repo_row[0] if repo_row else ""

    owner, repo_name, _slug = parse_git_url(git_url)
    repo = f"{owner}/{repo_name}" if owner and repo_name else None

    if not repo:
        resolver = get_repo_resolver()
        repo_path = (
            resolver({"slug": repo_row[1], "git_url": git_url})
            if resolver and repo_row
            else None
        )
        if repo_path:
            try:
                from scripts.setup_gh_issues import detect_repo_from_git

                repo = detect_repo_from_git(repo_path)
            except Exception:
                pass

    if not repo:
        raise HTTPException(
            status_code=400,
            detail=f"Board '{slug}' does not have a recognizable GitHub repository.",
        )

    try:
        from issues.github import GitHubIssueClient
        from issues.importer import import_external_issue
    except ImportError:
        try:
            from ...issues.github import GitHubIssueClient
            from ...issues.importer import import_external_issue
        except ImportError:
            from zerofactory.issues.github import GitHubIssueClient  # type: ignore
            from zerofactory.issues.importer import import_external_issue  # type: ignore

    client = GitHubIssueClient(default_repo=repo)
    try:
        issues_to_import = client.fetch_investigation_issues(
            repo=repo, label=label, state="open"
        )
    except Exception as e:
        raise HTTPException(
            status_code=500, detail=f"Failed to fetch GitHub issues from {repo}: {e}"
        )

    imported = []
    duplicates = []
    for iss in issues_to_import:
        res = import_external_issue(
            issue=iss,
            board_slug=slug,
            status="triage",
            assignee="zf-orchestrator",
            actor="user",
        )
        if res.get("duplicate"):
            duplicates.append(res)
        else:
            imported.append(res)

    return {
        "ok": True,
        "repo": repo,
        "imported_count": len(imported),
        "duplicate_count": len(duplicates),
        "imported": imported,
        "duplicates": duplicates,
        "message": f"Synced {len(imported)} new issue(s) from {repo} ({len(duplicates)} duplicates skipped).",
    }


@router.post("/boards/{slug}/import-gh-issue")
def import_board_gh_issue_endpoint(slug: str, req: dict[str, Any]):
    """Import a specific GitHub issue into the board's triage column."""
    issue_ref = req.get("issue")
    if not issue_ref:
        raise HTTPException(
            status_code=400, detail="Missing 'issue' field in request body"
        )
    force = bool(req.get("force", False))
    label = str(req.get("label", "zerofactory"))

    init_db()
    with get_db_conn() as conn:
        board = conn.execute("SELECT * FROM boards WHERE slug = ?", (slug,)).fetchone()
        if not board:
            raise HTTPException(status_code=404, detail=f"Board '{slug}' not found")
        board_dict = dict(board)

    git_url = board_dict.get("git_url") or ""

    owner, repo_name, _slug = parse_git_url(git_url)
    repo = f"{owner}/{repo_name}" if owner and repo_name else None

    try:
        from issues.github import GitHubIssueClient
        from issues.importer import import_external_issue
    except ImportError:
        try:
            from ...issues.github import GitHubIssueClient
            from ...issues.importer import import_external_issue
        except ImportError:
            from zerofactory.issues.github import GitHubIssueClient  # type: ignore
            from zerofactory.issues.importer import import_external_issue  # type: ignore

    client = GitHubIssueClient(default_repo=repo)
    try:
        issue = client.fetch_issue(str(issue_ref), repo=repo)
    except Exception as e:
        raise HTTPException(
            status_code=400, detail=f"Failed to fetch issue '{issue_ref}': {e}"
        )

    if not force and not issue.has_ai_request_label(
        {label, "zerofactory", "ai-investigate", "ai-triage"}
    ):
        raise HTTPException(
            status_code=400,
            detail=f"GitHub issue #{issue.id} lacks an AI investigation request label ('{label}'). Add the label or pass force=True.",
        )

    res = import_external_issue(
        issue=issue,
        board_slug=slug,
        status="triage",
        assignee="zf-orchestrator",
        actor="user",
    )
    return res


@router.post("/boards/{slug}/setup-jira")
def setup_board_jira_endpoint(slug: str, req: JiraSetupRequest | None = None):
    """Configure and/or test Jira Cloud integration for a board."""
    init_db()
    with get_db_conn() as conn:
        board = conn.execute("SELECT * FROM boards WHERE slug = ?", (slug,)).fetchone()
        if not board:
            raise HTTPException(status_code=404, detail=f"Board '{slug}' not found")

        current_jira_url = (board["jira_url"] or "").strip()
        if req and req.jira_url is not None:
            new_jira_url = req.jira_url.strip()
            conn.execute(
                "UPDATE boards SET jira_url = ?, updated_at = ? WHERE slug = ?",
                (new_jira_url, int(time.time()), slug),
            )
            conn.commit()
            current_jira_url = new_jira_url

    try:
        from ...issues.jira import JiraIssueClient
    except (ImportError, ValueError):
        try:
            from issues.jira import JiraIssueClient  # type: ignore
        except (ImportError, ValueError):
            from zerofactory.issues.jira import JiraIssueClient  # type: ignore

    client = JiraIssueClient(base_url=current_jira_url, board_slug=slug)
    conn_status = client.check_connection()

    return {
        "ok": True,
        "slug": slug,
        "jira_url": current_jira_url,
        "connection": conn_status,
        "message": conn_status.get("message", "Jira status checked"),
    }


@router.post("/boards/{slug}/test-jira")
def verify_board_jira_endpoint(slug: str):
    """Test reachability and authentication of configured Jira Cloud link."""
    return setup_board_jira_endpoint(slug, None)
