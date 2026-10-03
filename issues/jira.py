"""Jira Issue client interface and implementation stub.

Designed to mirror GitHubIssueClient with the same ExternalIssue normalization contract.
Ready for direct expansion with Jira REST API or jira-cli.
"""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from .base import BaseIssueClient, ExternalIssue

_log = logging.getLogger("zerofactory.issues.jira")

_JIRA_URL_RE = re.compile(
    r"^https?://[^/]+/browse/([A-Z0-9]+-\d+)(?:[?#].*)?$", re.IGNORECASE
)
_JIRA_KEY_RE = re.compile(r"^([A-Z0-9]+)-(\d+)$", re.IGNORECASE)
_JIRA_NUM_ONLY_RE = re.compile(r"^#?(\d+)$")


def parse_jira_issue_ref(
    issue_ref: str, default_project: str | None = None
) -> tuple[str, str]:
    """Parse a Jira issue reference into (project_key, issue_key).

    Supported reference formats:
    - Full URL: `https://company.atlassian.net/browse/PROJ-123`
    - Issue Key: `PROJ-123`
    - Numeric ID with default project: `123` -> `("PROJ", "PROJ-123")`

    Raises ValueError if reference format is invalid or project cannot be determined.
    """
    ref = (issue_ref or "").strip()
    if not ref:
        raise ValueError("Jira issue reference cannot be empty")

    url_match = _JIRA_URL_RE.match(ref)
    if url_match:
        issue_key = url_match.group(1).upper()
        project = issue_key.split("-")[0]
        return project, issue_key

    key_match = _JIRA_KEY_RE.match(ref)
    if key_match:
        issue_key = ref.upper()
        project = key_match.group(1).upper()
        return project, issue_key

    num_match = _JIRA_NUM_ONLY_RE.match(ref)
    if num_match:
        num = num_match.group(1)
        if not default_project:
            raise ValueError(
                f"Numeric Jira reference '{ref}' requires a default project. Specify --project KEY or use KEY-123 format."
            )
        proj = default_project.strip().upper()
        return proj, f"{proj}-{num}"

    raise ValueError(
        f"Invalid Jira issue reference '{ref}'. Expected format: https://.../browse/PROJ-123 or PROJ-123."
    )


class JiraIssueClient(BaseIssueClient):
    """Client for fetching and parsing issues from Jira via REST API or CLI."""

    def __init__(
        self,
        base_url: str | None = None,
        email: str | None = None,
        api_token: str | None = None,
        default_project: str | None = None,
    ):
        self.base_url = base_url or os.environ.get("JIRA_BASE_URL", "")
        self.email = email or os.environ.get("JIRA_EMAIL", "")
        self.api_token = api_token or os.environ.get("JIRA_API_TOKEN", "")
        self.default_project = default_project or os.environ.get("JIRA_PROJECT", "")

    def test_connection(self) -> bool:
        """Verify Jira credentials and reachability."""
        return bool(self.base_url and self.api_token)

    def fetch_issue(
        self, issue_ref: str, project: str | None = None, **kwargs: Any
    ) -> ExternalIssue:
        """Fetch an issue from Jira and normalize it to ExternalIssue.

        If custom payload is supplied in kwargs (e.g. for testing/webhook), it will be parsed directly.
        """
        target_project = project or self.default_project
        effective_project, issue_key = parse_jira_issue_ref(
            issue_ref, default_project=target_project
        )

        mock_payload = kwargs.get("mock_data")
        if mock_payload:
            return self._parse_jira_payload(effective_project, issue_key, mock_payload)

        # When REST client is connected:
        if not self.base_url or not self.api_token:
            raise NotImplementedError(
                f"Jira client integration for {issue_key} requires JIRA_BASE_URL and JIRA_API_TOKEN environment variables."
            )

        # Placeholder for Jira REST HTTP GET /rest/api/3/issue/{issue_key}
        raise NotImplementedError(
            "Jira REST API fetcher will be enabled with Jira plugin."
        )

    def _parse_jira_payload(
        self, project: str, issue_key: str, data: dict[str, Any]
    ) -> ExternalIssue:
        """Helper to parse Jira API JSON response into ExternalIssue."""
        fields = data.get("fields", {})
        summary = str(fields.get("summary") or data.get("title") or issue_key).strip()

        # Jira description can be Atlassian Document Format (ADF) or plain string
        raw_desc = fields.get("description") or data.get("body") or ""
        body = raw_desc if isinstance(raw_desc, str) else str(raw_desc)

        author = ""
        reporter = fields.get("reporter")
        if isinstance(reporter, dict):
            author = reporter.get("displayName") or reporter.get("name") or ""

        status_obj = fields.get("status")
        state = status_obj.get("name") if isinstance(status_obj, dict) else "Open"

        labels = [str(l) for l in fields.get("labels", []) if l]

        assignees = []
        assignee_obj = fields.get("assignee")
        if isinstance(assignee_obj, dict):
            a_name = assignee_obj.get("displayName") or assignee_obj.get("name")
            if a_name:
                assignees.append(str(a_name))

        url = f"{self.base_url.rstrip('/')}/browse/{issue_key}" if self.base_url else ""

        return ExternalIssue(
            source="jira",
            id=issue_key,
            key=issue_key,
            title=summary,
            body=body,
            url=url,
            author=author,
            state=str(state).lower(),
            labels=labels,
            assignees=assignees,
            repo_or_project=project,
            raw=data,
        )
