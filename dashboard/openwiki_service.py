"""Zero Factory OpenWiki Service — Status detection, prompt generation, and setup task management."""

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

OPENWIKI_RELATIVE_DIR = "openwiki"
SETUP_OPENWIKI_TASK_TITLE = (
    "chore(repo): setup OpenWiki machine-readable agent documentation"
)
SETUP_OPENWIKI_TASK_DEDUP_KEY = "setup:openwiki"
SETUP_OPENWIKI_TASK_TITLE_PREFIX = "chore(repo): setup OpenWiki"


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
    return check_board_setup_status(
        board_slug,
        has_key="has_openwiki",
        path_key="openwiki_path",
        preview_key="wiki_index_preview",
        target_relpath=OPENWIKI_RELATIVE_DIR,
        title_prefix=SETUP_OPENWIKI_TASK_TITLE_PREFIX,
        dedup_substring=SETUP_OPENWIKI_TASK_DEDUP_KEY,
        preview_relpath=f"{OPENWIKI_RELATIVE_DIR}/index.md",
        target_is_dir=True,
    )


def create_openwiki_setup_task(board_slug: str, actor: str = "user") -> dict[str, Any]:
    """Create or return an existing setup task to generate openwiki/ documentation."""
    return create_setup_task(
        board_slug,
        status_checker=check_board_openwiki_status,
        title=SETUP_OPENWIKI_TASK_TITLE,
        prompt_builder=build_openwiki_setup_task_prompt,
        files=[
            OPENWIKI_RELATIVE_DIR,
            f"{OPENWIKI_RELATIVE_DIR}/index.md",
            "AGENTS.md",
        ],
        dedup_key=SETUP_OPENWIKI_TASK_DEDUP_KEY,
        progress_label="OpenWiki",
        created_label="OpenWiki",
        actor=actor,
    )
