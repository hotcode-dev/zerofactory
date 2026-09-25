"""Zero Factory Dashboard — Board routes (/boards)."""

from __future__ import annotations

import json
import logging
import os
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)
_DASHBOARD_ROOT = str(Path(__file__).resolve().parent.parent)
if _DASHBOARD_ROOT not in sys.path:
    sys.path.insert(0, _DASHBOARD_ROOT)

from fastapi import APIRouter, HTTPException

try:
    from ..db import get_db_conn, init_db, parse_git_url
    from ..models import BoardCreate, BoardTestClone, BoardUpdate
except (ImportError, ValueError):
    from db import get_db_conn, init_db, parse_git_url  # type: ignore
    from models import BoardCreate, BoardTestClone, BoardUpdate  # type: ignore

_log = logging.getLogger(__name__)

router = APIRouter()


def _get_cron_helpers():
    """Import builtin cron engine functions reliably regardless of how plugin_api is loaded."""
    try:
        from ...builtin_cron import (
            ensure_builtin_cron_jobs, prune_board_cron_job, trigger_builtin_job,
            list_builtin_jobs, update_builtin_job, toggle_builtin_job, reset_builtin_job
        )
        return (
            ensure_builtin_cron_jobs, prune_board_cron_job, trigger_builtin_job,
            list_builtin_jobs, update_builtin_job, toggle_builtin_job, reset_builtin_job
        )
    except Exception:
        pass
    try:
        from builtin_cron import (  # type: ignore
            ensure_builtin_cron_jobs, prune_board_cron_job, trigger_builtin_job,
            list_builtin_jobs, update_builtin_job, toggle_builtin_job, reset_builtin_job
        )
        return (
            ensure_builtin_cron_jobs, prune_board_cron_job, trigger_builtin_job,
            list_builtin_jobs, update_builtin_job, toggle_builtin_job, reset_builtin_job
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
            builtin_cron.reset_builtin_job
        )
    except Exception as e:
        _log.warning("Failed to resolve builtin_cron helpers: %s", e)
        return None, None, None, None, None, None, None


@router.get("/boards")
def list_boards():
    """List all Kanban boards."""
    init_db()
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM boards ORDER BY created_at ASC")
        boards = [dict(row) for row in cursor.fetchall()]

        for b in boards:
            b["auto_record_memory"] = bool(b.get("auto_record_memory", 1))
            try:
                b["additional_reviewer_usernames"] = json.loads(
                    b.get("additional_reviewer_usernames") or "[]"
                )
            except (TypeError, ValueError, json.JSONDecodeError):
                b["additional_reviewer_usernames"] = []
            cursor.execute("SELECT COUNT(*) as count FROM tasks WHERE board_slug = ?", (b["slug"],))
            b["task_count"] = cursor.fetchone()["count"]
            cursor.execute("SELECT COUNT(*) as count FROM tasks WHERE board_slug = ? AND status = 'running'", (b["slug"],))
            b["running_count"] = cursor.fetchone()["count"]
        return {"ok": True, "boards": boards}


@router.post("/boards")
def create_board(req: BoardCreate):
    """Create a new board / project from Git URL."""
    init_db()
    now = int(time.time())

    git_url = (req.git_url or "").strip()
    if not git_url:
        raise HTTPException(status_code=400, detail="Remote Git URL is required")

    owner, repo, slug = parse_git_url(git_url)
    if not slug:
        raise HTTPException(status_code=400, detail="Invalid board slug (could not derive slug from Git URL)")

    desc = (req.description or "").strip()
    mcr = max(1, req.max_concurrent_running or 1)
    arm = 1 if (req.auto_record_memory is None or req.auto_record_memory) else 0
    reviewer_usernames = sorted({
        username.strip().lstrip("@").lower()
        for username in (req.additional_reviewer_usernames or [])
        if username and username.strip()
    })

    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT slug FROM boards WHERE slug = ?", (slug,))
        if cursor.fetchone():
            raise HTTPException(status_code=409, detail=f"Board '{slug}' already exists")

        cursor.execute(
            "INSERT INTO boards (slug, description, git_url, max_concurrent_running, auto_record_memory, additional_reviewer_usernames, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (slug, desc, git_url, mcr, arm, json.dumps(reviewer_usernames), now, now)
        )
        conn.commit()

    # Attempt repository clone / resolution immediately upon board creation
    try:
        try:
            from ...builtin_cron import resolve_board_repo_path
        except Exception:
            from builtin_cron import resolve_board_repo_path  # type: ignore
        resolve_board_repo_path({"slug": slug, "git_url": git_url, "description": desc})
    except Exception as e:
        _log.warning("Failed to auto-clone/resolve repo after creating board %s: %s", slug, e)

    if not os.environ.get("ZEROFACTORY_SKIP_CRON_SYNC"):
        ensure_cron, *_ = _get_cron_helpers()
        if ensure_cron:
            try:
                ensure_cron()
            except Exception as e:
                _log.warning("Failed to sync cron jobs after creating board %s: %s", slug, e)

    return {"ok": True, "slug": slug}


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
        try:
            from ...builtin_cron import resolve_board_repo_path
        except Exception:
            from builtin_cron import resolve_board_repo_path  # type: ignore

        # 1. First check if it's already resolved / cloned locally
        existing_path = resolve_board_repo_path({"slug": slug, "git_url": git_url})
        if existing_path and existing_path.is_dir() and (existing_path / ".git").exists():
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
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}
        )
        if ls_res.returncode != 0:
            err_msg = ls_res.stderr.strip() or "Could not connect to remote Git repository"
            raise HTTPException(status_code=400, detail=f"Git remote check failed: {err_msg}")

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
            raise HTTPException(status_code=500, detail="Git clone failed to create a valid repository directory")

    except HTTPException:
        raise
    except Exception as e:
        _log.warning("Test clone failed for %s: %s", git_url, e)
        raise HTTPException(status_code=500, detail=str(e))


@router.patch("/boards/{slug}")
@router.put("/boards/{slug}")
def update_board(slug: str, req: BoardUpdate):
    """Update board metadata."""
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
        if req.git_url is not None:
            updates.append("git_url = ?")
            params.append(req.git_url.strip())
        if req.max_concurrent_running is not None:
            mcr = max(1, int(req.max_concurrent_running))
            updates.append("max_concurrent_running = ?")
            params.append(mcr)
        if req.auto_record_memory is not None:
            arm = 1 if req.auto_record_memory else 0
            updates.append("auto_record_memory = ?")
            params.append(arm)
        if req.additional_reviewer_usernames is not None:
            reviewer_usernames = sorted({
                username.strip().lstrip("@").lower()
                for username in req.additional_reviewer_usernames
                if username and username.strip()
            })
            updates.append("additional_reviewer_usernames = ?")
            params.append(json.dumps(reviewer_usernames))

        if updates:
            updates.append("updated_at = ?")
            params.append(now)
            params.append(slug)
            cursor.execute(f"UPDATE boards SET {', '.join(updates)} WHERE slug = ?", params)
            conn.commit()

        cursor.execute("SELECT * FROM boards WHERE slug = ?", (slug,))
        row = cursor.fetchone()
        board_data = dict(row) if row else {"slug": slug}
        if "auto_record_memory" in board_data:
            board_data["auto_record_memory"] = bool(board_data["auto_record_memory"])
        if "additional_reviewer_usernames" in board_data:
            try:
                board_data["additional_reviewer_usernames"] = json.loads(board_data["additional_reviewer_usernames"] or "[]")
            except (TypeError, ValueError, json.JSONDecodeError):
                board_data["additional_reviewer_usernames"] = []

    if not os.environ.get("ZEROFACTORY_SKIP_CRON_SYNC"):
        ensure_cron, *_ = _get_cron_helpers()
        if ensure_cron:
            try:
                ensure_cron()
            except Exception as e:
                _log.warning("Failed to sync cron jobs after updating board %s: %s", slug, e)

    return {"ok": True, "slug": slug, "board": board_data}


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
                _log.warning("Failed to prune cron job for deleted board %s: %s", slug, e)

        if ensure_cron:
            try:
                ensure_cron()
            except Exception as e:
                _log.warning("Failed to sync cron jobs after deleting board %s: %s", slug, e)

    return {"ok": True, "deleted": slug}

