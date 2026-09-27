"""Zero Factory OpenWiki Service — Status detection, prompt generation, and setup task management."""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any

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

OPENWIKI_RELATIVE_DIR = "openwiki"
SETUP_OPENWIKI_TASK_TITLE = (
    "chore(repo): setup OpenWiki machine-readable agent documentation"
)
SETUP_OPENWIKI_TASK_DEDUP_KEY = "setup:openwiki"


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


def build_openwiki_setup_task_prompt(
    board_slug: str, repo_path: Path | None = None
) -> str:
    """Generate structured instructions for zf-builder to initialize and generate OpenWiki agent docs."""
    path_hint = f" (`{repo_path}`)" if repo_path else ""
    return f"""Set up OpenWiki machine-readable agent documentation for this repository{path_hint} on board `{board_slug}`.

## Target
Directory: `{OPENWIKI_RELATIVE_DIR}/`
Pointers: `AGENTS.md` (and `CLAUDE.md` if present)

## Goal
Generate a high-signal, machine-readable architectural knowledge base in `{OPENWIKI_RELATIVE_DIR}/` (based on the LLM Wiki / Docs for Agents pattern) and link it into `AGENTS.md`. This optimizes context windows, slashes exploratory token consumption by 30–40%, and prevents multi-agent hallucination across Zero Factory workers (`zf-builder`, `zf-reviewer`, `zf-orchestrator`).

## Instructions
1. **Ensure Node.js and OpenWiki Tooling**:
   - Check if `openwiki` is installed (`openwiki --version`).
   - If not installed, install it globally using npm:
     ```bash
     npm install -g openwiki
     ```
     (or run on-demand via `npx -y openwiki`).

2. **Initialize & Generate OpenWiki Documentation**:
   - Create `{OPENWIKI_RELATIVE_DIR}/` at repository root if it does not already exist.
   - Run `openwiki` (or `npx -y openwiki --init` / `openwiki generate` or manually structure the wiki if non-interactive):
     Generate clear, hyperlinked Markdown documents covering:
     - `{OPENWIKI_RELATIVE_DIR}/index.md`: Navigational table of contents and system architecture summary.
     - Component overviews: Key subsystems, entrypoints, database models/migrations, API routes, background workers/dispatchers, and test suites.
     - Cross-module dependency graph and key architectural decisions/conventions.

3. **Link OpenWiki in `AGENTS.md`**:
   - Update `AGENTS.md` in the repository root (or create it if missing) with an explicit reference section directing coding agents to read `{OPENWIKI_RELATIVE_DIR}/index.md` before performing exploratory tool calls:
     ```markdown
     ## Repository Architecture & Agent Wiki
     For architectural overviews, subsystem maps, and module contracts, consult the machine-readable wiki in `{OPENWIKI_RELATIVE_DIR}/index.md` before reading individual source files.
     ```

4. **Verify Precommit Checks**:
   - Run `./.zerofactory/precommit.sh` (or `git status`) in the repository to verify that format, build, and test checks execute cleanly.
   - Ensure markdown files are clean, readable, and well-linked.

5. **Complete Task**:
   - Mark task done via `hermes zerofactory move <task_id> done`.
   - (NOTE: Do NOT run git add/commit/push manually. The dispatcher automatically verifies precommit and stages/commits/opens PR upon task completion).
"""


def check_board_openwiki_status(board_slug: str) -> dict[str, Any]:
    """Check if openwiki/ exists for a board and check active setup task status."""
    init_db()
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM boards WHERE slug = ?", (board_slug,))
        row = cursor.fetchone()
        if not row:
            return {
                "ok": False,
                "error": f"Board '{board_slug}' not found",
                "has_openwiki": False,
                "pending_task_id": None,
                "pending_task_status": None,
                "wiki_index_preview": None,
            }

        board = dict(row)

        # Check for a setup task. Only actively-dispatchable statuses count as
        # pending work: a `blocked` task is awaiting a human action (merge
        # review) and must not masquerade as in-progress work — otherwise a
        # blocked setup task would permanently wedge the Setup/Regenerate button.
        cursor.execute(
            """
            SELECT id, status, title FROM tasks
            WHERE board_slug = ? AND status IN ('triage', 'todo', 'ready', 'running')
            AND (
                title LIKE 'chore(repo): setup OpenWiki%'
                OR metadata LIKE '%setup:openwiki%'
            )
            ORDER BY created_at DESC LIMIT 1
        """,
            (board_slug,),
        )
        t_row = cursor.fetchone()
        pending_task_id = t_row["id"] if t_row else None
        pending_task_status = t_row["status"] if t_row else None

        # Surface a most-recent blocked setup task as awaiting human merge,
        # so the UI can show a distinct "awaiting merge" state.
        cursor.execute(
            """
            SELECT id, status, title FROM tasks
            WHERE board_slug = ? AND status = 'blocked'
            AND (
                title LIKE 'chore(repo): setup OpenWiki%'
                OR metadata LIKE '%setup:openwiki%'
            )
            ORDER BY created_at DESC LIMIT 1
        """,
            (board_slug,),
        )
        b_row = cursor.fetchone()
        blocked_task_id = b_row["id"] if b_row else None
        blocked_task_status = b_row["status"] if b_row else None

    # Check filesystem for openwiki directory & index.md
    has_openwiki = False
    wiki_index_preview = None
    openwiki_full_path = None

    resolver = get_repo_resolver()
    if resolver:
        try:
            repo_path = resolver(board)
            if repo_path and repo_path.is_dir():
                target_dir = repo_path / OPENWIKI_RELATIVE_DIR
                target_index = target_dir / "index.md"
                if target_dir.is_dir():
                    has_openwiki = True
                    openwiki_full_path = str(target_dir)
                    if target_index.is_file():
                        try:
                            content = target_index.read_text(encoding="utf-8")
                            wiki_index_preview = content[:600]
                        except Exception:
                            pass
        except Exception as e:
            _log.debug("Failed checking repo path for board %s: %s", board_slug, e)

    return {
        "ok": True,
        "board_slug": board_slug,
        "has_openwiki": has_openwiki,
        "openwiki_path": openwiki_full_path,
        "wiki_index_preview": wiki_index_preview,
        "pending_task_id": pending_task_id,
        "pending_task_status": pending_task_status,
        "blocked_task_id": blocked_task_id,
        "blocked_task_status": blocked_task_status,
    }


def create_openwiki_setup_task(board_slug: str, actor: str = "user") -> dict[str, Any]:
    """Create or return an existing setup task to generate openwiki/ documentation."""
    init_db()

    # 1. Verify board exists
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM boards WHERE slug = ?", (board_slug,))
        row = cursor.fetchone()
        if not row:
            return {"ok": False, "error": f"Board '{board_slug}' not found"}
        board = dict(row)

    # 2. Check if a setup task already exists and is not done
    status_info = check_board_openwiki_status(board_slug)
    if status_info.get("pending_task_id"):
        return {
            "ok": True,
            "task_id": status_info["pending_task_id"],
            "status": status_info["pending_task_status"],
            "already_exists": True,
            "message": f"OpenWiki setup task '{status_info['pending_task_id']}' is already in progress ({status_info['pending_task_status']}).",
        }

    # 3. Resolve repo path for prompt hint
    resolver = get_repo_resolver()
    repo_path = resolver(board) if resolver else None

    # 4. Create the P0 task
    prompt = build_openwiki_setup_task_prompt(board_slug, repo_path=repo_path)
    req = TaskCreate(
        title=SETUP_OPENWIKI_TASK_TITLE,
        description=prompt,
        status="todo",
        priority="P0",
        assignee="zf-builder",
        board_slug=board_slug,
        category="config",
        files=[OPENWIKI_RELATIVE_DIR, f"{OPENWIKI_RELATIVE_DIR}/index.md", "AGENTS.md"],
        dedup_key=SETUP_OPENWIKI_TASK_DEDUP_KEY,
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
        "already_exists": False,
        "message": f"Created OpenWiki setup task '{task_id}' for board '{board_slug}'.",
    }
