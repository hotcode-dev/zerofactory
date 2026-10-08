"""Shared helpers for dashboard board setup services (precommit, openwiki)."""

from __future__ import annotations

import logging
import os
import sys
from pathlib import Path
from typing import Any, Callable

_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)
_DASHBOARD_ROOT = str(Path(__file__).resolve().parent)
if _DASHBOARD_ROOT not in sys.path:
    sys.path.insert(0, _DASHBOARD_ROOT)

try:
    from .db import get_db_conn, init_db
    from .models import TaskCreate
except (ImportError, ValueError):
    from db import get_db_conn, init_db  # type: ignore
    from models import TaskCreate  # type: ignore

_log = logging.getLogger(__name__)


def get_repo_resolver():
    """Import resolve_board_repo_path safely."""
    try:
        from ..builtin_cron import resolve_board_repo_path

        return resolve_board_repo_path
    except Exception:
        pass
    try:
        from builtin_cron import resolve_board_repo_path  # type: ignore

        return resolve_board_repo_path
    except Exception:
        pass
    try:
        from ..cron.definitions import resolve_board_repo_path

        return resolve_board_repo_path
    except Exception:
        pass
    try:
        from cron.definitions import resolve_board_repo_path  # type: ignore

        return resolve_board_repo_path
    except Exception:
        return None


def _find_setup_task(
    cursor,
    board_slug: str,
    title_prefix: str,
    dedup_substring: str,
    active_only: bool,
    repo_alias: str | None = None,
) -> tuple[str | None, str | None]:
    """Locate the newest setup task matching the title prefix or dedup key."""
    status_clause = (
        "status IN ('triage', 'todo', 'running')" if active_only else "status != 'done'"
    )
    if repo_alias:
        cursor.execute(
            f"""
            SELECT id, status, title FROM tasks
            WHERE board_slug = ? AND {status_clause}
            AND (repo_alias = ? OR repo_alias IS NULL OR repo_alias = '')
            AND (
                title LIKE ?
                OR metadata LIKE ?
            )
            ORDER BY created_at DESC LIMIT 1
        """,
            (board_slug, repo_alias, f"{title_prefix}%", f"%{dedup_substring}%"),
        )
    else:
        cursor.execute(
            f"""
            SELECT id, status, title FROM tasks
            WHERE board_slug = ? AND {status_clause}
            AND (
                title LIKE ?
                OR metadata LIKE ?
            )
            ORDER BY created_at DESC LIMIT 1
        """,
            (board_slug, f"{title_prefix}%", f"%{dedup_substring}%"),
        )
    t_row = cursor.fetchone()
    return (
        t_row["id"] if t_row else None,
        t_row["status"] if t_row else None,
    )


def check_board_setup_status(
    board_slug: str,
    repo_alias: str | None = None,
    *,
    has_key: str,
    path_key: str,
    preview_key: str,
    target_relpath: str,
    title_prefix: str,
    dedup_substring: str,
    preview_relpath: str | None = None,
    target_is_dir: bool = False,
) -> dict[str, Any]:
    """Check whether a repository setup target exists on disk and report active setup task."""
    init_db()
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM boards WHERE slug = ?", (board_slug,))
        row = cursor.fetchone()
        if not row:
            return {
                "ok": False,
                "error": f"Board '{board_slug}' not found",
                "repo_alias": repo_alias,
                has_key: False,
                "pending_task_id": None,
                "pending_task_status": None,
                "dedup_task_id": None,
                "dedup_task_status": None,
                preview_key: None,
            }

        # Resolve repository from board_repositories
        if repo_alias:
            cursor.execute(
                "SELECT * FROM board_repositories WHERE board_slug = ? AND repo_alias = ?",
                (board_slug, repo_alias),
            )
            r_row = cursor.fetchone()
        else:
            cursor.execute(
                "SELECT * FROM board_repositories WHERE board_slug = ? ORDER BY id ASC LIMIT 1",
                (board_slug,),
            )
            r_row = cursor.fetchone()

        target_repo = dict(r_row) if r_row else {}
        effective_alias = target_repo.get("repo_alias") or repo_alias or ""

        # Check for pending setup task
        pending_task_id, pending_task_status = _find_setup_task(
            cursor,
            board_slug,
            title_prefix,
            dedup_substring,
            active_only=False,
            repo_alias=effective_alias,
        )
        dedup_task_id, dedup_task_status = _find_setup_task(
            cursor,
            board_slug,
            title_prefix,
            dedup_substring,
            active_only=True,
            repo_alias=effective_alias,
        )

    # Check filesystem for the setup target
    has_target = False
    target_full_path = None
    preview = None

    resolver = get_repo_resolver()
    if resolver and target_repo:
        try:
            prev = os.environ.get("ZEROFACTORY_SKIP_CLONE")
            os.environ["ZEROFACTORY_SKIP_CLONE"] = "1"
            try:
                repo_path = resolver(
                    {"slug": effective_alias, "git_url": target_repo.get("git_url", "")}
                )
            finally:
                if prev is None:
                    os.environ.pop("ZEROFACTORY_SKIP_CLONE", None)
                else:
                    os.environ["ZEROFACTORY_SKIP_CLONE"] = prev
            if repo_path and repo_path.is_dir():
                target = repo_path / target_relpath
                is_target = target.is_dir() if target_is_dir else target.is_file()
                if is_target:
                    has_target = True
                    target_full_path = str(target)
                    if preview_relpath:
                        preview_file = repo_path / preview_relpath
                        if preview_file.is_file():
                            try:
                                preview = preview_file.read_text(encoding="utf-8")[:600]
                            except Exception:
                                pass
        except Exception as e:
            _log.debug("Failed checking repo path for board %s (%s): %s", board_slug, effective_alias, e)

    return {
        "ok": True,
        "board_slug": board_slug,
        "repo_alias": effective_alias,
        has_key: has_target,
        path_key: target_full_path,
        preview_key: preview,
        "pending_task_id": pending_task_id,
        "pending_task_status": pending_task_status,
        "dedup_task_id": dedup_task_id,
        "dedup_task_status": dedup_task_status,
    }


def create_setup_task(
    board_slug: str,
    repo_alias: str | None = None,
    *,
    status_checker: Callable[..., dict[str, Any]],
    title: str,
    prompt_builder: Callable[..., str],
    files: list[str],
    dedup_key: str,
    progress_label: str,
    created_label: str,
    actor: str = "user",
) -> dict[str, Any]:
    """Create (or deduplicate to) a P0 setup task for a board repository."""
    init_db()

    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM boards WHERE slug = ?", (board_slug,))
        row = cursor.fetchone()
        if not row:
            return {"ok": False, "error": f"Board '{board_slug}' not found"}

        if repo_alias:
            cursor.execute(
                "SELECT * FROM board_repositories WHERE board_slug = ? AND repo_alias = ?",
                (board_slug, repo_alias),
            )
            r_row = cursor.fetchone()
        else:
            cursor.execute(
                "SELECT * FROM board_repositories WHERE board_slug = ? ORDER BY id ASC LIMIT 1",
                (board_slug,),
            )
            r_row = cursor.fetchone()
        if r_row:
            target_repo = dict(r_row)
            effective_alias = target_repo["repo_alias"]
        else:
            target_repo = {"repo_alias": repo_alias or board_slug, "git_url": ""}
            effective_alias = repo_alias or board_slug

        cursor.execute(
            "SELECT COUNT(*) FROM board_repositories WHERE board_slug = ?",
            (board_slug,),
        )
        repo_count = cursor.fetchone()[0]

    try:
        status_info = status_checker(board_slug, repo_alias=effective_alias)
    except TypeError:
        status_info = status_checker(board_slug)
    if status_info.get("dedup_task_id"):
        return {
            "ok": True,
            "task_id": status_info["dedup_task_id"],
            "repo_alias": effective_alias,
            "status": status_info["dedup_task_status"],
            "already_exists": True,
            "message": f"{progress_label} setup task '{status_info['dedup_task_id']}' is already in progress ({status_info['dedup_task_status']}).",
        }

    resolver = get_repo_resolver()
    repo_path = (
        resolver({"slug": effective_alias, "git_url": target_repo.get("git_url", "")})
        if resolver
        else None
    )

    if repo_count > 1 and effective_alias:
        effective_title = f"{title} ({effective_alias})"
        effective_dedup = f"{dedup_key}:{effective_alias}"
    else:
        effective_title = title
        effective_dedup = dedup_key

    # Create the P0 task
    try:
        task_desc = prompt_builder(board_slug, repo_path=repo_path, repo_alias=effective_alias)
    except TypeError:
        task_desc = prompt_builder(board_slug, repo_path=repo_path)

    req = TaskCreate(
        title=effective_title,
        description=task_desc,
        status="todo",
        priority="P0",
        assignee="zf-builder",
        board_slug=board_slug,
        repo_alias=effective_alias,
        category="config",
        files=files,
        dedup_key=effective_dedup,
        actor=actor or "user",
    )

    try:
        from .routes.tasks import create_task as _create_task
    except (ImportError, ValueError):
        from routes.tasks import create_task as _create_task  # type: ignore

    res = _create_task(req)
    task_id = res.get("id")

    return {
        "ok": True,
        "task_id": task_id,
        "repo_alias": effective_alias,
        "status": "todo",
        "already_exists": False,
        "message": f"Created {created_label} setup task '{task_id}' for repo '{effective_alias}' on board '{board_slug}'.",
    }
