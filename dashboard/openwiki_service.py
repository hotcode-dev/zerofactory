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
# The openwiki CLI's canonical machine-readable artifact (its PAGE_MANIFEST_PATH
# constant). Detection and preview key off this JSON ledger, not the Markdown
# index.md the CLI also writes, so status reflects what the CLI actually produced.
OPENWIKI_PAGE_MANIFEST_RELPATH = f"{OPENWIKI_RELATIVE_DIR}/.page-manifest.json"
SETUP_OPENWIKI_TASK_TITLE = (
    "chore(repo): setup OpenWiki machine-readable agent documentation"
)
SETUP_OPENWIKI_TASK_DEDUP_KEY = "setup:openwiki"
SETUP_OPENWIKI_TASK_TITLE_PREFIX = "chore(repo): setup OpenWiki"


def build_openwiki_setup_task_prompt(
    board_slug: str, repo_path: Path | None = None, repo_alias: str | None = None
) -> str:
    """Generate structured instructions for zf-builder to generate OpenWiki agent docs via OpenWiki MCP in repository code mode."""
    path_hint = f" (`{repo_path}`)" if repo_path else ""
    target_desc = f"repository `{repo_alias}`" if repo_alias else "this repository"
    return f"""Set up OpenWiki machine-readable agent documentation for {target_desc}{path_hint} on board `{board_slug}` in repository code mode.

## Target
Directory: `{OPENWIKI_RELATIVE_DIR}/` (managed via OpenWiki MCP in repository code mode)
Pointer: `AGENTS.md` (managed via OpenWiki)

## Goal
Generate a high-signal, machine-readable architectural knowledge base in `{OPENWIKI_RELATIVE_DIR}/` (Docs for Agents pattern) using the **OpenWiki MCP server** (in repository code mode) and its standard artifacts, so agents consume the wiki instead of re-reading source. This optimizes context windows, slashes exploratory token consumption by 30–40%, and prevents multi-agent hallucination across Zero Factory workers (`zf-builder`, `zf-reviewer`, `zf-orchestrator`).

## Instructions
1. **OpenWiki MCP Server & Skill (Repository Code Mode)**:
   - The `openwiki` MCP server is pre-configured in your `zf-builder` profile.
   - The MCP server operates exclusively in repository **code mode** (targeting `{OPENWIKI_RELATIVE_DIR}/` in the repository root, never personal mode).
   - It exposes native lifecycle tools: `openwiki_begin`, `openwiki_submit_plan`, `openwiki_next_page`, `openwiki_submit_page`, and `openwiki_finish`.
   - **Zero API keys or environment variables (`export OPENWIKI_*`) are needed!** OpenWiki runs purely as a local MCP tool provider over stdio, and Hermes provides the model intelligence.
   - Review your `openwiki` skill (`skills/openwiki/SKILL.md`) for detailed guidance on claims, taxonomy, and frontmatter.

2. **Generate the wiki via OpenWiki MCP Lifecycle — never manually**:
   - **CRITICAL: the wiki MUST be generated and finalized through the OpenWiki MCP lifecycle in repository code mode. Do NOT hand-write, hand-structure, or manually create `{OPENWIKI_RELATIVE_DIR}/` or `AGENTS.md`.** If MCP tools cannot complete a run in this environment, BLOCK the task (`hermes zerofactory block <task_id> --reason "<MCP error>"`) with the captured error output instead of falling back to manual wiki authoring.
   - **Step 1: Begin Run (Code Mode)**:
     Call `openwiki_begin({{"root": ".", "mode": "init"}})` (or `"mode": "update"` for updates).
     This runs the repository code documentation lifecycle for the target repository.
     If it returns `status: "noop"`, report that the wiki is up-to-date and complete the task.
   - **Step 2: Submit Plan**:
     Inspect repository manifests, entrypoints, and public interfaces to plan a logical documentation taxonomy. Keep the initial taxonomy focused and consolidated (4–6 pages, e.g. quickstart, architecture, subsystems, operations, conventions). Call `openwiki_submit_plan` with canonical page paths (always include `/openwiki/quickstart.md` for `init`).
   - **Step 3: Page Loop**:
     Repeatedly call `openwiki_next_page`. For each assigned page job:
     - Research that specific page topic using native repository tools.
     - Author the Markdown page with valid OKF frontmatter (`type`, `title`, `description`, `tags`).
     - Call `openwiki_submit_page` with your page decisions.
   - **Step 4: Finish Run**:
     When `openwiki_next_page` returns `status: "complete"`, call `openwiki_finish`. This finalizes the run, writes the machine-readable ledger at `{OPENWIKI_PAGE_MANIFEST_RELPATH}`, stamps `.last-update.json`, and links `AGENTS.md`.

3. **Verify Standard Artifacts on Disk & Clean Up**:
   - `{OPENWIKI_PAGE_MANIFEST_RELPATH}` — the machine-readable JSON page ledger (its `PAGE_MANIFEST_PATH` constant). Confirm it exists and parses as valid JSON with shape `{{"schemaVersion": 1, "pages": {{...}}}}`.
   - `{OPENWIKI_RELATIVE_DIR}/quickstart.md` — the canonical entry point, which must exist and must never be deleted.
   - Do NOT key off `{OPENWIKI_RELATIVE_DIR}/index.md` or hand-write any Markdown page in `{OPENWIKI_RELATIVE_DIR}/` — the machine-readable JSON ledger is the source of truth.
   - `AGENTS.md` — confirm the managed block (`<!-- OPENWIKI:START --> ... <!-- OPENWIKI:END -->`) points at `{OPENWIKI_RELATIVE_DIR}/quickstart.md`.
   - **Do NOT commit `.github/workflows/openwiki-update.yml` or `CLAUDE.md`**: Zero Factory manages wiki updates natively via Hermes background cron, NOT external GitHub Actions. If OpenWiki's `init` created them, delete them (`rm -rf .github CLAUDE.md`).

4. **Verify Precommit Checks**:
   - Run `./.zerofactory/precommit.sh` (or `git status`) in the repository to verify that format, build, and test checks execute cleanly.
   - Re-confirm the standard artifacts are present and well-formed: the machine-readable JSON ledger at `{OPENWIKI_PAGE_MANIFEST_RELPATH}` and canonical `{OPENWIKI_RELATIVE_DIR}/quickstart.md`.

5. **Complete Task**:
   - Mark task done via `hermes zerofactory move <task_id> done`.
   - (NOTE: Do NOT run git add/commit/push manually. The dispatcher automatically verifies precommit and stages/commits/opens PR upon task completion).
"""


def check_board_openwiki_status(
    board_slug: str, repo_alias: str | None = None
) -> dict[str, Any]:
    """Check if openwiki/ exists for a repository and check active setup task status."""
    return check_board_setup_status(
        board_slug,
        repo_alias=repo_alias,
        has_key="has_openwiki",
        path_key="openwiki_path",
        preview_key="wiki_index_preview",
        target_relpath=OPENWIKI_RELATIVE_DIR,
        title_prefix=SETUP_OPENWIKI_TASK_TITLE_PREFIX,
        dedup_substring=SETUP_OPENWIKI_TASK_DEDUP_KEY,
        preview_relpath=OPENWIKI_PAGE_MANIFEST_RELPATH,
        target_is_dir=True,
    )


def create_openwiki_setup_task(
    board_slug: str, repo_alias: str | None = None, actor: str = "user"
) -> dict[str, Any]:
    """Create or return an existing setup task to generate openwiki/ documentation for a repository."""
    return create_setup_task(
        board_slug,
        repo_alias=repo_alias,
        status_checker=check_board_openwiki_status,
        title=SETUP_OPENWIKI_TASK_TITLE,
        prompt_builder=build_openwiki_setup_task_prompt,
        files=[
            OPENWIKI_RELATIVE_DIR,
            OPENWIKI_PAGE_MANIFEST_RELPATH,
            "AGENTS.md",
        ],
        dedup_key=SETUP_OPENWIKI_TASK_DEDUP_KEY,
        progress_label="OpenWiki",
        created_label="OpenWiki",
        actor=actor,
    )
