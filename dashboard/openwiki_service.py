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
    # Automatically sync the board's OpenWiki workspace registry so sibling repos are linked
    try:
        sync_board_openwiki_workspace(board_slug)
    except Exception:
        pass
    return res


WIKI_WORKSPACES_FILE = "wiki-workspaces.json"


def get_openwiki_home_dir() -> Path:
    """Resolve the base directory for OpenWiki user configuration and registries (~/.openwiki)."""
    env_dir = os.environ.get("OPENWIKI_CONFIG_DIR")
    if env_dir and env_dir.strip():
        p = env_dir.strip()
        if p.startswith("~"):
            return Path(os.path.expanduser(p))
        return Path(p).resolve()
    return Path.home() / ".openwiki"


def sync_board_openwiki_workspace(
    board_slug: str, db_path: str | Path | None = None
) -> dict[str, Any]:
    """Sync repositories linked to board_slug into a named OpenWiki workspace (~/.openwiki/wiki-workspaces.json).

    This enables OpenWiki's workspace linking feature so openwiki_search and openwiki_read
    can query architecture and contracts across all sibling repositories on the board.
    """
    if not board_slug:
        return {"status": "skipped", "reason": "No board slug provided"}

    import json
    import os
    import re
    import sqlite3
    import tempfile
    from .db import DEFAULT_DB_PATH, get_db_path

    eff_db = Path(db_path or os.environ.get("ZEROFACTORY_DB") or get_db_path())
    if not eff_db.exists():
        return {"status": "skipped", "reason": "Database not found"}

    resolver = get_repo_resolver()
    linked_repos: list[dict[str, Any]] = []

    try:
        with sqlite3.connect(str(eff_db), timeout=5.0) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(
                "SELECT repo_alias, git_url, target_branch FROM board_repositories WHERE board_slug = ? ORDER BY id ASC",
                (board_slug,),
            )
            rows = cursor.fetchall()
            for r in rows:
                alias = r["repo_alias"]
                url = r["git_url"]
                repo_path = None
                if resolver:
                    try:
                        resolved = resolver({"git_url": url, "slug": alias})
                        if resolved and resolved.is_dir() and (resolved / ".git").exists():
                            repo_path = resolved.resolve()
                    except Exception:
                        pass
                if not repo_path:
                    for cand in (
                        Path.home() / "git" / alias,
                        Path.home() / "git" / board_slug / alias,
                    ):
                        if cand.is_dir() and (cand / ".git").exists():
                            repo_path = cand.resolve()
                            break
                if repo_path:
                    linked_repos.append(
                        {
                            "alias": alias,
                            "path": repo_path,
                            "url": url,
                        }
                    )
    except Exception as e:
        return {"status": "error", "error": str(e)}

    if not linked_repos:
        return {"status": "skipped", "reason": "No local repositories resolved"}

    openwiki_dir = get_openwiki_home_dir()
    openwiki_dir.mkdir(parents=True, exist_ok=True)
    registry_file = openwiki_dir / WIKI_WORKSPACES_FILE

    registry: dict[str, Any] = {
        "version": 1,
        "wikis": [],
        "workspaces": [],
        "active": [],
    }

    if registry_file.exists():
        try:
            loaded = json.loads(registry_file.read_text(encoding="utf-8"))
            if isinstance(loaded, dict) and loaded.get("version") == 1:
                registry = loaded
        except Exception:
            pass

    existing_wikis: list[dict[str, Any]] = registry.setdefault("wikis", [])
    existing_workspaces: list[dict[str, Any]] = registry.setdefault("workspaces", [])
    existing_active: list[dict[str, Any]] = registry.setdefault("active", [])

    def _slugify(val: str, prefix: str = "item") -> str:
        s = re.sub(r"[^a-z0-9-]", "-", val.lower().strip()).strip("-")
        s = re.sub(r"-+", "-", s)
        return s[:63] if s else prefix

    # 1. Register or update wikis
    root_to_wiki_id: dict[str, str] = {}
    used_wiki_ids: set[str] = {w.get("id") for w in existing_wikis if w.get("id")}

    for w in existing_wikis:
        if w.get("root"):
            root_to_wiki_id[str(Path(w["root"]).resolve())] = w["id"]

    for lr in linked_repos:
        r_str = str(lr["path"])
        if r_str in root_to_wiki_id:
            continue
        base_id = _slugify(lr["alias"], "wiki")
        wiki_id = base_id
        counter = 1
        while wiki_id in used_wiki_ids:
            wiki_id = f"{base_id}-{counter}"
            counter += 1
        used_wiki_ids.add(wiki_id)
        existing_wikis.append(
            {
                "id": wiki_id,
                "name": lr["alias"],
                "root": r_str,
            }
        )
        root_to_wiki_id[r_str] = wiki_id

    member_wiki_ids = [
        root_to_wiki_id[str(lr["path"])]
        for lr in linked_repos
        if str(lr["path"]) in root_to_wiki_id
    ]

    # 2. Update or create workspace for board_slug
    ws_id = _slugify(board_slug, "workspace")
    target_ws = None
    for ws in existing_workspaces:
        if ws.get("id") == ws_id or ws.get("name") == board_slug:
            target_ws = ws
            break

    if target_ws:
        merged_ids = list(dict.fromkeys(target_ws.get("wikis", []) + member_wiki_ids))
        target_ws["wikis"] = merged_ids
        target_ws["name"] = board_slug
    else:
        existing_workspaces.append(
            {
                "id": ws_id,
                "name": board_slug,
                "wikis": member_wiki_ids,
            }
        )

    # 3. Update active selections
    for wid in member_wiki_ids:
        found = False
        for act in existing_active:
            if act.get("wiki") == wid:
                act["workspace"] = ws_id
                found = True
                break
        if not found:
            existing_active.append({"wiki": wid, "workspace": ws_id})

    # 4. Atomic write
    try:
        temp_fd, temp_path = tempfile.mkstemp(
            dir=str(openwiki_dir), prefix="workspaces_", suffix=".tmp"
        )
        with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
            json.dump(registry, f, indent=2)
            f.flush()
            os.fsync(f.fileno())
        os.replace(temp_path, str(registry_file))
        return {
            "status": "synced",
            "workspace_id": ws_id,
            "board_slug": board_slug,
            "member_wikis": member_wiki_ids,
        }
    except Exception as e:
        return {"status": "error", "error": f"Failed to persist registry: {e}"}
