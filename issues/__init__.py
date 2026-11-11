"""Zero Factory External Issue Tracker Integration.

Standardized, deterministic issue ingestion for GitHub.
"""

from __future__ import annotations

from .base import BaseIssueClient, ExternalIssue
from .github import GitHubIssueClient, parse_github_issue_ref
from .importer import import_external_issue, resolve_board_for_issue

__all__ = [
    "BaseIssueClient",
    "ExternalIssue",
    "GitHubIssueClient",
    "import_external_issue",
    "parse_github_issue_ref",
    "resolve_board_for_issue",
]
