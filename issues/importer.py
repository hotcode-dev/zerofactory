"""Unified, deterministic importer for external issues (GitHub & Jira)."""

from __future__ import annotations

import logging
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any

_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

try:
    from ..dashboard.db import get_db_path
    from ..dashboard.plugin_api import TaskCreate, create_task
except (ImportError, ValueError):
    from dashboard.db import get_db_path
    from dashboard.plugin_api import TaskCreate, create_task

from .base import ExternalIssue

_log = logging.getLogger("zerofactory.issues.importer")


def resolve_board_for_issue(
    repo_or_project: str | None = None,
    board_slug: str | None = None,
    db_path: Path | None = None,
) -> str | None:
    """Find the most appropriate board slug for a given issue repository/project."""
    if db_path is None:
        db_path = get_db_path()

    if not db_path.exists():
        return board_slug

    with sqlite3.connect(str(db_path), timeout=5.0) as conn:
        conn.row_factory = sqlite3.Row
        cursor = conn.cursor()

        # 1. If explicit board_slug provided and valid, return it
        if board_slug:
            cursor.execute("SELECT slug FROM boards WHERE slug = ?", (board_slug,))
            row = cursor.fetchone()
            if row:
                return str(row["slug"])

        # 2. Try matching repo_or_project to git_url, jira_url, or slug in boards
        if repo_or_project:
            cursor.execute(
                "SELECT b.slug, b.jira_url, br.git_url, br.repo_alias FROM boards b LEFT JOIN board_repositories br ON b.slug = br.board_slug ORDER BY b.created_at ASC"
            )
            for row in cursor.fetchall():
                row_dict = dict(row)
                slug = str(row_dict.get("slug") or "")
                git_url = str(row_dict.get("git_url") or "")
                repo_alias = str(row_dict.get("repo_alias") or "")
                jira_url = str(row_dict.get("jira_url") or "")
                if jira_url and repo_or_project.lower() in jira_url.lower():
                    return slug
                if repo_alias and repo_or_project.lower() in repo_alias.lower():
                    return slug
                # Normalize git_url (strip .git, protocol)
                cleaned_git = re.sub(r"\.git$", "", git_url).strip().rstrip("/")
                if cleaned_git and repo_or_project.lower() in cleaned_git.lower():
                    return slug
                # Check slug match
                norm_repo_slug = (
                    re.sub(r"[^a-zA-Z0-9]+", "-", repo_or_project).strip("-").lower()
                )
                if norm_repo_slug in slug.lower():
                    return slug

        # 3. Try matching current working directory git remote
        try:
            cwd_remote = subprocess.run(
                ["git", "remote", "get-url", "origin"],
                capture_output=True,
                text=True,
                timeout=2,
            )
            if cwd_remote.returncode == 0:
                cwd_url = cwd_remote.stdout.strip()
                cleaned_cwd = re.sub(r"\.git$", "", cwd_url).strip().rstrip("/")
                cursor.execute(
                    "SELECT b.slug, br.git_url FROM boards b LEFT JOIN board_repositories br ON b.slug = br.board_slug ORDER BY b.created_at ASC"
                )
                for row in cursor.fetchall():
                    slug = str(row["slug"])
                    git_url = str(row["git_url"] or "")
                    cleaned_board_url = (
                        re.sub(r"\.git$", "", git_url).strip().rstrip("/")
                    )
                    if (
                        cleaned_board_url
                        and cleaned_board_url.lower() == cleaned_cwd.lower()
                    ):
                        return slug
        except Exception:
            pass

        # 4. Fallback to first available board
        cursor.execute("SELECT slug FROM boards ORDER BY created_at ASC LIMIT 1")
        first_row = cursor.fetchone()
        if first_row:
            return str(first_row["slug"])

    return board_slug


def import_external_issue(
    issue: ExternalIssue,
    board_slug: str | None = None,
    status: str = "triage",
    priority: str | None = None,
    assignee: str = "zf-orchestrator",
    actor: str | None = None,
    require_ai_request: bool = False,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Import an ExternalIssue into Zero Factory as a Kanban task deterministically.

    Ensures:
    - Deterministic task ID derived from board + issue key
    - Deterministic dedup key to avoid duplicate tasks
    - Deterministic priority & category mapping
    - Option 1 triage routing: status='triage', assignee='zf-orchestrator'
    - Rich metadata preservation for downstream PR linking and reviewer context
    """
    if require_ai_request and not issue.has_ai_request_label():
        raise ValueError(
            f"Issue {issue.key} lacks an explicit human AI investigation request label "
            "(e.g. 'zerofactory', 'ai-investigate'). Add the label on GitHub or use --force to bypass."
        )

    effective_board = resolve_board_for_issue(
        repo_or_project=issue.repo_or_project,
        board_slug=board_slug,
        db_path=db_path,
    )

    task_id = issue.to_task_id(effective_board)
    dedup_key = issue.to_dedup_key()
    effective_priority = priority or issue.infer_priority()
    category = issue.infer_category()

    # Build clean tags list
    tags = [
        f"issue:{issue.source}",
        f"issue:type:{issue.issue_type}",
        f"{issue.source}-{issue.key.lstrip('#').lower()}",
        f"cat:{category}",
    ]
    for lbl in issue.labels:
        clean_lbl = re.sub(r"[^a-zA-Z0-9_-]", "-", lbl.strip().lower())
        if clean_lbl and f"tag:{clean_lbl}" not in tags:
            tags.append(f"tag:{clean_lbl}")

    # Strip redundant leading type badges from issue title if present
    clean_title = re.sub(
        r"^\[?(?:bug|feature|enhancement|triage)\]?[:\s-]*",
        "",
        issue.title.strip(),
        flags=re.IGNORECASE,
    ).strip()
    if not clean_title:
        clean_title = issue.title.strip()

    type_badge = issue.issue_type.capitalize()
    title = f"[Triage] [{type_badge}] [{issue.key}] {clean_title}"
    description = issue.to_markdown_description()

    effective_assignee = assignee
    if (
        not effective_assignee or effective_assignee == "unassigned"
    ) and status == "triage":
        effective_assignee = "zf-orchestrator"

    metadata: dict[str, Any] = {
        "external_issue": issue.to_metadata_dict(),
        "dedup_key": dedup_key,
        "category": category,
        "issue_type": issue.issue_type,
    }

    actor_val = actor or os.environ.get("HERMES_PROFILE") or "user"

    req = TaskCreate(
        task_id=task_id,
        title=title,
        description=description,
        board_slug=effective_board,
        status=status,
        assignee=effective_assignee,
        priority=effective_priority,
        category=category,
        dedup_key=dedup_key,
        tags=tags,
        actor=actor_val,
        metadata=metadata,
    )

    res = create_task(req)

    return {
        "ok": res.get("ok", True),
        "id": res.get("id") or task_id,
        "duplicate": res.get("duplicate", False),
        "title": title,
        "board_slug": effective_board,
        "status": status,
        "priority": effective_priority,
        "category": category,
        "assignee": effective_assignee,
        "source": issue.source,
        "issue_key": issue.key,
        "issue_type": issue.issue_type,
        "issue_url": issue.url,
        "message": res.get("message"),
    }
