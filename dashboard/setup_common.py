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
    cursor, board_slug: str, title_prefix: str, dedup_substring: str, active_only: bool
) -> tuple[str | None, str | None]:
    """Locate the newest setup task matching the title prefix or dedup key.

    When active_only is set, restricts to statuses that represent active work
    (triage/todo/running). A 'blocked' task means 'awaiting human merge', NOT
    'active work', so active-only is used for deduplication while the
    non-done variant is used for UI display (the 'Setup in Progress' badge).
    """
    status_clause = (
        "status IN ('triage', 'todo', 'running')" if active_only else "status != 'done'"
    )
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
    """Check whether a board's setup target exists on disk and report the active setup task."""
    init_db()
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM boards WHERE slug = ?", (board_slug,))
        row = cursor.fetchone()
        if not row:
            return {
                "ok": False,
                "error": f"Board '{board_slug}' not found",
                has_key: False,
                "pending_task_id": None,
                "pending_task_status": None,
                "dedup_task_id": None,
                "dedup_task_status": None,
                preview_key: None,
            }

        board = dict(row)

        # Check for pending setup task
        pending_task_id, pending_task_status = _find_setup_task(
            cursor, board_slug, title_prefix, dedup_substring, active_only=False
        )
        dedup_task_id, dedup_task_status = _find_setup_task(
            cursor, board_slug, title_prefix, dedup_substring, active_only=True
        )

    # Check filesystem for the setup target
    has_target = False
    target_full_path = None
    preview = None

    resolver = get_repo_resolver()
    if resolver:
        try:
            prev = os.environ.get("ZEROFACTORY_SKIP_CLONE")
            # Read-only status check: never let the resolver auto-clone the remote.
            os.environ["ZEROFACTORY_SKIP_CLONE"] = "1"
            try:
                repo_path = resolver(board)
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
            _log.debug("Failed checking repo path for board %s: %s", board_slug, e)

    return {
        "ok": True,
        "board_slug": board_slug,
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
    *,
    status_checker: Callable[[str], dict[str, Any]],
    title: str,
    prompt_builder: Callable[..., str],
    files: list[str],
    dedup_key: str,
    progress_label: str,
    created_label: str,
    actor: str = "user",
) -> dict[str, Any]:
    """Create (or deduplicate to) a P0 setup task for a board."""
    init_db()

    # 1. Verify board exists
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM boards WHERE slug = ?", (board_slug,))
        row = cursor.fetchone()
        if not row:
            return {"ok": False, "error": f"Board '{board_slug}' not found"}
        board = dict(row)

    # 2. Check if an ACTIVE setup task already exists (dedup source).
    # Note: 'blocked' tasks (awaiting human merge) must NOT dedup — otherwise a
    # finished-but-unmerged task permanently wedges regenerate/retry flows.
    status_info = status_checker(board_slug)
    if status_info.get("dedup_task_id"):
        return {
            "ok": True,
            "task_id": status_info["dedup_task_id"],
            "status": status_info["dedup_task_status"],
            "already_exists": True,
            "message": f"{progress_label} setup task '{status_info['dedup_task_id']}' is already in progress ({status_info['dedup_task_status']}).",
        }

    # 3. Resolve repo path for prompt hint
    resolver = get_repo_resolver()
    repo_path = resolver(board) if resolver else None

    # 4. Create the P0 task
    req = TaskCreate(
        title=title,
        description=prompt_builder(board_slug, repo_path=repo_path),
        status="todo",
        priority="P0",
        assignee="zf-builder",
        board_slug=board_slug,
        category="config",
        files=files,
        dedup_key=dedup_key,
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
        "status": "todo",
        "already_exists": False,
        "message": f"Created {created_label} setup task '{task_id}' for board '{board_slug}'.",
    }
