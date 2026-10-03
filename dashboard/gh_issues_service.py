"""Zero Factory GitHub Issues Service — Status detection, prompt generation, and setup task management."""

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
    from .setup_common import (
        check_board_setup_status,
        create_setup_task,
        get_repo_resolver,
    )
except (ImportError, ValueError):
    from db import get_db_conn, init_db  # type: ignore
    from setup_common import (  # type: ignore
        check_board_setup_status,
        create_setup_task,
        get_repo_resolver,
    )

_log = logging.getLogger("zerofactory.dashboard.gh_issues_service")

GH_ISSUES_RELATIVE_DIR = ".github/ISSUE_TEMPLATE"
BUG_REPORT_RELPATH = f"{GH_ISSUES_RELATIVE_DIR}/bug_report.yml"
FEATURE_REQUEST_RELPATH = f"{GH_ISSUES_RELATIVE_DIR}/feature_request.yml"
CONFIG_RELPATH = f"{GH_ISSUES_RELATIVE_DIR}/config.yml"

SETUP_GH_ISSUES_TASK_TITLE = (
    "chore(repo): setup GitHub Issue templates and Zero Factory triage labels"
)
SETUP_GH_ISSUES_TASK_TITLE_PREFIX = "chore(repo): setup GitHub Issue"
SETUP_GH_ISSUES_TASK_DEDUP_KEY = "setup:gh-issues"


def build_gh_issues_setup_task_prompt(
    board_slug: str, repo_path: Path | None = None
) -> str:
    """Generate structured instructions for zf-builder to set up GitHub Issue templates and labels."""
    path_hint = f" at `{repo_path}`" if repo_path else ""
    return f"""Set up standardized GitHub Issue templates and Zero Factory AI triage labels for this repository{path_hint} on board `{board_slug}`.

Target Directory: `{GH_ISSUES_RELATIVE_DIR}/`

### Context & Goals
Zero Factory selectively imports external issues into human-gated **Triage** tasks when a human explicitly requests AI investigation.
This requires:
1. **GitHub Issue Forms (YAML)**:
   - `{BUG_REPORT_RELPATH}`: Bug report form automatically pre-labeled with `["bug", "zerofactory"]`, with problem description, reproduction steps, expected behavior, and AI investigation confirmation checkbox.
   - `{FEATURE_REQUEST_RELPATH}`: Feature proposal form automatically pre-labeled with `["feature", "zerofactory"]`, with summary, proposed solution, constraints, and AI investigation confirmation checkbox.
   - `{CONFIG_RELPATH}`: Configuration disabling blank issues (`blank_issues_enabled: false`) and directing users to GitHub Discussions for questions, ideas, and general community discussions.
2. **Repository Labels**:
   - `zerofactory` (#7c3aed): Triggers Zero Factory AI triage and investigation.
   - `ai-investigate` (#8b5cf6): Request Zero Factory AI investigation.
   - `bug` (#d73a4a): Something isn't working.
   - `feature` (#a2eeef): New feature or enhancement.
   - `p0` (#b60205), `p1` (#d93f0b), `p2` (#fbca04), `p3` (#0e8a16): Standard priority tiers.

### Builder Execution Steps
1. **Generate Issue Templates**:
   You can run the built-in generator script:
   ```bash
   python3 scripts/setup_gh_issues.py --path .
   ```
   Or ensure `{BUG_REPORT_RELPATH}`, `{FEATURE_REQUEST_RELPATH}`, and `{CONFIG_RELPATH}` are written according to the Zero Factory standard.

2. **Provision Labels (if gh CLI is available and authenticated)**:
   ```bash
   python3 scripts/setup_gh_issues.py --path .
   ```
   (If `gh` CLI is not authenticated in this environment, writing the template files is sufficient; label creation will be skipped gracefully).

3. **Verify Files**:
   - Confirm `{BUG_REPORT_RELPATH}` exists and contains `labels: ["bug", "zerofactory"]`.
   - Confirm `{FEATURE_REQUEST_RELPATH}` exists and contains `labels: ["feature", "zerofactory"]`.
   - Confirm `{CONFIG_RELPATH}` exists.

4. **Complete Task**:
   - Mark task done via `hermes zerofactory move <task_id> done`.
   - (NOTE: Do NOT run git add/commit/push manually. The dispatcher automatically verifies precommit and stages/commits/opens PR upon task completion).
"""


def check_board_gh_issues_status(board_slug: str) -> dict[str, Any]:
    """Check if .github/ISSUE_TEMPLATE exists for a board and check active setup task status."""
    return check_board_setup_status(
        board_slug,
        has_key="has_gh_issues",
        path_key="gh_issues_path",
        preview_key="template_preview",
        target_relpath=GH_ISSUES_RELATIVE_DIR,
        title_prefix=SETUP_GH_ISSUES_TASK_TITLE_PREFIX,
        dedup_substring=SETUP_GH_ISSUES_TASK_DEDUP_KEY,
        preview_relpath=BUG_REPORT_RELPATH,
        target_is_dir=True,
    )


def setup_board_gh_issues_deterministic(
    board_slug: str, actor: str = "user"
) -> dict[str, Any]:
    """Deterministically provision GitHub Issue templates and standard labels for a board."""
    init_db()
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM boards WHERE slug = ?", (board_slug,))
        row = cursor.fetchone()
        if not row:
            return {"ok": False, "error": f"Board '{board_slug}' not found"}
        board = dict(row)

    # Resolve board repository root
    repo_path: Path | None = None
    resolver = get_repo_resolver()
    if resolver:
        try:
            repo_path = resolver(board)
        except Exception as e:
            _log.warning("Could not resolve repo path for board %s: %s", board_slug, e)

    if not repo_path or not repo_path.is_dir():
        repo_path = Path(".").resolve()

    try:
        from ..scripts.setup_gh_issues import setup_github_issues
    except Exception:
        try:
            from scripts.setup_gh_issues import setup_github_issues
        except Exception:
            _scripts_path = Path(__file__).resolve().parent.parent / "scripts"
            if str(_scripts_path) not in sys.path:
                sys.path.insert(0, str(_scripts_path))
            from setup_gh_issues import setup_github_issues  # type: ignore

    res = setup_github_issues(
        repo_root=repo_path,
        repo=board.get("git_url") or None,
        create_labels=True,
    )
    res["board_slug"] = board_slug
    res["deterministic"] = True
    res["has_gh_issues"] = True
    res["message"] = (
        "Configured GitHub Issue templates and AI labels deterministically."
    )
    return res


def create_gh_issues_setup_task(
    board_slug: str, actor: str = "user", deterministic: bool = False
) -> dict[str, Any]:
    """Provision GitHub Issue templates. Defaults to creating a P0 setup task."""
    if deterministic:
        return setup_board_gh_issues_deterministic(board_slug, actor=actor)
    return create_setup_task(
        board_slug,
        status_checker=check_board_gh_issues_status,
        title=SETUP_GH_ISSUES_TASK_TITLE,
        prompt_builder=build_gh_issues_setup_task_prompt,
        files=[
            GH_ISSUES_RELATIVE_DIR,
            BUG_REPORT_RELPATH,
            FEATURE_REQUEST_RELPATH,
            CONFIG_RELPATH,
        ],
        dedup_key=SETUP_GH_ISSUES_TASK_DEDUP_KEY,
        progress_label="GitHub Issues",
        created_label="GitHub Issues",
        actor=actor,
    )
