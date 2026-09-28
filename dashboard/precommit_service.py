"""Zero Factory Precommit Service — Status detection, prompt generation, and setup task management."""

from __future__ import annotations

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
    from .setup_common import (
        check_board_setup_status,
        create_setup_task,
        get_repo_resolver,  # noqa: F401  (re-exported for API compatibility)
    )
except (ImportError, ValueError):
    from setup_common import (  # type: ignore
        check_board_setup_status,
        create_setup_task,
        get_repo_resolver,  # noqa: F401  (re-exported for API compatibility)
    )

PRECOMMIT_RELATIVE_PATH = ".zerofactory/precommit.sh"
SETUP_TASK_TITLE = "chore(repo): setup Zero Factory precommit script"
SETUP_TASK_TITLE_PREFIX = "chore(repo): setup Zero Factory precommit"
SETUP_TASK_DEDUP_KEY = "setup:precommit"


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
    return check_board_setup_status(
        board_slug,
        has_key="has_precommit",
        path_key="precommit_path",
        preview_key="script_preview",
        target_relpath=PRECOMMIT_RELATIVE_PATH,
        title_prefix=SETUP_TASK_TITLE_PREFIX,
        dedup_substring=SETUP_TASK_DEDUP_KEY,
        preview_relpath=PRECOMMIT_RELATIVE_PATH,
    )


def create_precommit_setup_task(board_slug: str, actor: str = "user") -> dict[str, Any]:
    """Create or return an existing setup task to generate .zerofactory/precommit.sh."""
    return create_setup_task(
        board_slug,
        status_checker=check_board_precommit_status,
        title=SETUP_TASK_TITLE,
        prompt_builder=build_precommit_setup_task_prompt,
        files=[PRECOMMIT_RELATIVE_PATH],
        dedup_key=SETUP_TASK_DEDUP_KEY,
        progress_label="Precommit",
        created_label="precommit",
        actor=actor,
    )
