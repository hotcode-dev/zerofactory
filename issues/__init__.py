"""Zero Factory External Issue Tracker Integration.

Standardized, deterministic issue ingestion for GitHub and Jira.
"""

from __future__ import annotations

from .base import BaseIssueClient, ExternalIssue
from .github import GitHubIssueClient, parse_github_issue_ref
from .importer import import_external_issue, resolve_board_for_issue
from .jira import JiraIssueClient, parse_jira_issue_ref

__all__ = [
    "BaseIssueClient",
    "ExternalIssue",
    "GitHubIssueClient",
    "JiraIssueClient",
    "import_external_issue",
    "parse_github_issue_ref",
    "parse_jira_issue_ref",
    "resolve_board_for_issue",
]
