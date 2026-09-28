"""Zero Factory Precommit Service — Status detection, prompt generation, and setup task management."""

from __future__ import annotations

import logging
import os
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

PRECOMMIT_RELATIVE_PATH = ".zerofactory/precommit.sh"
SETUP_TASK_TITLE = "chore(repo): setup Zero Factory precommit script"
SETUP_TASK_DEDUP_KEY = "setup:precommit"


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


def build_precommit_setup_task_prompt(
    board_slug: str, repo_path: Path | None = None
) -> str:
    """Generate structured instructions for zf-builder to inspect repo and generate .zerofactory/precommit.sh."""
    path_hint = f" (`{repo_path}`)" if repo_path else ""
    return f"""Set up the standard Zero Factory precommit script for this repository{path_hint} on board `{board_slug}`.

## Target
File: `{PRECOMMIT_RELATIVE_PATH}`

## Goal
Automate and standardize code formatting, building/typechecking, and test execution for this repository so that the Zero Factory dispatcher can deterministically verify every commit before creating Pull Requests.

## Instructions
1. **Analyze Repository Tooling & Manifests**:
   Inspect the project workspace to detect active languages, tools, package managers, and script targets.
   **Rule of Precedence**:
   - **First**: Respect existing project commands and scripts (e.g. `package.json` scripts, `pyproject.toml`, `Makefile`, `Taskfile`).
   - **Fallback (Zero Factory Standards)**: If no specific tool or configuration is defined, use the standard modern Zero Factory choices:
     - **Python**:
       - `run_format`: `ruff check --fix . && ruff format .` (with `ruff.toml` configuration)
       - `run_build`: `python3 -m compileall -q .` (built-in bytecode compilation)
       - `run_test`: `python3 -m pytest tests/ -q` (or `python3 -m unittest discover -s .`)
     - **Go** (All built-in to Go toolchain):
       - `run_format`: `gofmt -s -w .`
       - `run_build`: `go build -v ./...` (and `go vet ./...`)
       - `run_test`: `go test -race ./...`
     - **TypeScript / JavaScript**:
       - `run_format`: Prettier (`npx -y prettier --write --ignore-unknown .`)
       - `run_build`: TSC (`npx -y tsc --noEmit`) or `npm run build`
       - `run_test`: Vitest (`npx -y vitest run`) or `npm test`
     - **Rust**:
       - Standard targets: `cargo fmt`, `cargo check` / `cargo build`, `cargo test`.
     - **C / C++ / Other**:
       - Check `Makefile`, `CMakeLists.txt`, `Justfile`.
   - If a step is not applicable (e.g. no build step for a pure Python library), echo an informational notice and exit cleanly (`exit 0`).

2. **Force Install Required Tools to System**:
   You MUST install all missing commands and tools to the system environment before creating the precommit script. Do NOT skip or bypass tools due to them being missing:
   - **Python**: Install `ruff` if missing (`uv tool install ruff@latest` or `pip install ruff` / `pip3 install --user ruff`). If tests require pytest, ensure `pytest` is installed. When configuring ruff, write a clean `ruff.toml` with appropriate lint rules and per-file ignores for `__init__.py` and tests so `ruff check --fix .` and `ruff format .` both exit 0 cleanly.
   - **Node.js / TypeScript**: If `package.json` exists, run `npm install`. Use `npx -y` for on-demand tool execution (Prettier, Vitest, TSC).
   - **Go / Rust**: Ensure respective compilers and formatters are present in PATH.
   - If any required tool is missing, install it on the system before completing the task.

3. **Create Directory & Script**:
   Create `.zerofactory/` directory if missing, and write `.zerofactory/precommit.sh`:
   - Must start with `#!/usr/bin/env bash` and `set -e`.
   - Must change directory to the repository root:
     ```bash
     ROOT_DIR="$(cd "$(dirname "${{BASH_SOURCE[0]}}")/.." && pwd)"
     cd "$ROOT_DIR"
     ```
   - Structure with three phase functions:
     - `run_format`: In-place code formatting & lint auto-fixing (e.g. `ruff check --fix . && ruff format .`, Prettier, or `gofmt -s -w .`).
     - `run_build`: Compilation or static typechecking (e.g. `python3 -m compileall -q .`, `tsc --noEmit` / `npm run build`, `go build ./...`).
     - `run_test`: Test suite execution (e.g. `python3 -m pytest tests/ -q`, Vitest / `npm test`, `go test -race ./...`).
   - Add a subcommand dispatcher supporting individual phases and git hook linking:
     ```bash
     install_hook() {{
       HOOK_DIR="$(git rev-parse --git-path hooks 2>/dev/null || echo ".git/hooks")"
       mkdir -p "$HOOK_DIR"
       ln -sf "../../.zerofactory/precommit.sh" "$HOOK_DIR/pre-commit"
       chmod +x "$HOOK_DIR/pre-commit"
       echo "✓ Linked .zerofactory/precommit.sh -> $HOOK_DIR/pre-commit"
     }}

     case "${{1:-all}}" in
       format)       run_format ;;
       build)        run_build ;;
       test)         run_test ;;
       install-hook) install_hook ;;
       all|*)
         run_format
         run_build
         run_test
         ;;
     esac

     echo "✓ Zero Factory precommit checks passed!"
     ```

4. **Verify Execution & Git Hook Support**:
   - Make script executable: `chmod +x {PRECOMMIT_RELATIVE_PATH}`.
   - Run `./{PRECOMMIT_RELATIVE_PATH}` inside your workspace to verify that all phases execute and exit with code 0!
   - Verify `./{PRECOMMIT_RELATIVE_PATH} install-hook` allows developers to link `.git/hooks/pre-commit` to this script with one command.
   - If any command fails, adjust the flags or configuration so that it passes cleanly on the repository.

5. **Complete Task**:
   - Once `{PRECOMMIT_RELATIVE_PATH}` is created, executable, and verified working:
     Mark task done via `hermes zerofactory move <task_id> done`.
   - (NOTE: Do NOT run git add/commit/push manually. The dispatcher automatically verifies precommit and stages/commits/opens PR upon task completion).
"""


def check_board_precommit_status(board_slug: str) -> dict[str, Any]:
    """Check if .zerofactory/precommit.sh exists for a board and check active setup task status."""
    init_db()
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM boards WHERE slug = ?", (board_slug,))
        row = cursor.fetchone()
        if not row:
            return {
                "ok": False,
                "error": f"Board '{board_slug}' not found",
                "has_precommit": False,
                "pending_task_id": None,
                "pending_task_status": None,
                "script_preview": None,
            }

        board = dict(row)

        # Check for pending setup task
        cursor.execute(
            """
            SELECT id, status, title FROM tasks
            WHERE board_slug = ? AND status != 'done'
            AND (
                title LIKE 'chore(repo): setup Zero Factory precommit%'
                OR metadata LIKE '%setup:precommit%'
            )
            ORDER BY created_at DESC LIMIT 1
        """,
            (board_slug,),
        )
        t_row = cursor.fetchone()
        pending_task_id = t_row["id"] if t_row else None
        pending_task_status = t_row["status"] if t_row else None

    # Check filesystem for script
    has_precommit = False
    script_preview = None
    precommit_full_path = None

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
                target = repo_path / PRECOMMIT_RELATIVE_PATH
                if target.is_file():
                    has_precommit = True
                    precommit_full_path = str(target)
                    try:
                        content = target.read_text(encoding="utf-8")
                        script_preview = content[:600]
                    except Exception:
                        pass
        except Exception as e:
            _log.debug("Failed checking repo path for board %s: %s", board_slug, e)

    return {
        "ok": True,
        "board_slug": board_slug,
        "has_precommit": has_precommit,
        "precommit_path": precommit_full_path,
        "script_preview": script_preview,
        "pending_task_id": pending_task_id,
        "pending_task_status": pending_task_status,
    }


def create_precommit_setup_task(board_slug: str, actor: str = "user") -> dict[str, Any]:
    """Create or return an existing setup task to generate .zerofactory/precommit.sh."""
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
    status_info = check_board_precommit_status(board_slug)
    if status_info.get("pending_task_id"):
        return {
            "ok": True,
            "task_id": status_info["pending_task_id"],
            "status": status_info["pending_task_status"],
            "already_exists": True,
            "message": f"Precommit setup task '{status_info['pending_task_id']}' is already in progress ({status_info['pending_task_status']}).",
        }

    # 3. Resolve repo path for prompt hint
    resolver = get_repo_resolver()
    repo_path = resolver(board) if resolver else None

    # 4. Create the P0 task
    prompt = build_precommit_setup_task_prompt(board_slug, repo_path=repo_path)
    req = TaskCreate(
        title=SETUP_TASK_TITLE,
        description=prompt,
        status="todo",
        priority="P0",
        assignee="zf-builder",
        board_slug=board_slug,
        category="config",
        files=[PRECOMMIT_RELATIVE_PATH],
        dedup_key=SETUP_TASK_DEDUP_KEY,
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
        "message": f"Created precommit setup task '{task_id}' for board '{board_slug}'.",
    }
