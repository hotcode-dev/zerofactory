"""Jira Issue client interface and implementation stub.

Designed to mirror GitHubIssueClient with the same ExternalIssue normalization contract.
Ready for direct expansion with Jira REST API or jira-cli.
"""

from __future__ import annotations

import base64
import json
import logging
import os
import re
import urllib.error
import urllib.request
from typing import Any

from .base import BaseIssueClient, ExternalIssue

_log = logging.getLogger("zerofactory.issues.jira")

_JIRA_URL_RE = re.compile(
    r"^https?://[^/]+/browse/([A-Z0-9]+-\d+)(?:[?#].*)?$", re.IGNORECASE
)
_JIRA_KEY_RE = re.compile(r"^([A-Z0-9]+)-(\d+)$", re.IGNORECASE)
_JIRA_NUM_ONLY_RE = re.compile(r"^#?(\d+)$")


def extract_adf_text(node: Any) -> str:
    """Extract plain text from Atlassian Document Format (ADF) json structure."""
    if isinstance(node, str):
        return node
    if isinstance(node, dict):
        node_type = node.get("type")
        if node_type == "text":
            return str(node.get("text", ""))
        chunks = []
        for child in node.get("content", []):
            chunks.append(extract_adf_text(child))
        joined = "".join(chunks)
        if node_type in ("paragraph", "heading"):
            return joined + "\n"
        if node_type == "listItem":
            return f"- {joined}\n"
        return joined
    if isinstance(node, list):
        return "".join(extract_adf_text(item) for item in node)
    return str(node) if node is not None else ""


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
        board_slug: str | None = None,
    ):
        self.base_url = (base_url or os.environ.get("JIRA_BASE_URL", "")).strip()
        self.email = (email or os.environ.get("JIRA_EMAIL", "")).strip()
        self.api_token = (api_token or os.environ.get("JIRA_API_TOKEN", "")).strip()
        self.default_project = (default_project or os.environ.get("JIRA_PROJECT", "")).strip()
        self.board_slug = board_slug
        if not self.base_url and board_slug:
            self.base_url = self._resolve_board_jira_url(board_slug)

    @staticmethod
    def _resolve_board_jira_url(board_slug: str) -> str:
        try:
            try:
                from ..dashboard.db import get_db_conn
            except (ImportError, ValueError):
                from dashboard.db import get_db_conn  # type: ignore

            with get_db_conn() as conn:
                row = conn.execute(
                    "SELECT jira_url FROM boards WHERE slug = ?", (board_slug,)
                ).fetchone()
                if row and row["jira_url"]:
                    return str(row["jira_url"]).strip()
        except Exception:
            pass
        return ""

    def _build_auth_headers(self) -> dict[str, str]:
        headers = {
            "Accept": "application/json",
            "User-Agent": "ZeroFactory-JiraClient/1.0",
        }
        if self.api_token:
            if self.email:
                cred = f"{self.email}:{self.api_token}".encode("utf-8")
                b64 = base64.b64encode(cred).decode("ascii")
                headers["Authorization"] = f"Basic {b64}"
            else:
                headers["Authorization"] = f"Bearer {self.api_token}"
        return headers

    def check_connection(self) -> dict[str, Any]:
        """Verify Jira credentials and host reachability."""
        if not self.base_url:
            return {
                "ok": False,
                "connected": False,
                "authenticated": False,
                "base_url": "",
                "message": "No Jira Cloud URL configured for this board or environment.",
            }

        url = self.base_url.rstrip("/")
        if not (url.startswith("http://") or url.startswith("https://")):
            url = f"https://{url}"

        # If credentials provided, check /rest/api/3/myself; otherwise check host root
        test_url = f"{url}/rest/api/3/myself" if self.api_token else url
        headers = self._build_auth_headers()
        req = urllib.request.Request(test_url, headers=headers, method="GET")

        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                status = resp.status
                return {
                    "ok": True,
                    "connected": True,
                    "authenticated": bool(self.api_token and status == 200),
                    "status_code": status,
                    "base_url": url,
                    "message": "Jira Cloud reachable and authenticated"
                    if self.api_token
                    else "Jira Cloud reachable (no API token configured)",
                }
        except urllib.error.HTTPError as e:
            # 401 or 403 means host is reachable, but credentials are required or bad
            if e.code in (401, 403):
                return {
                    "ok": True,
                    "connected": True,
                    "authenticated": False,
                    "status_code": e.code,
                    "base_url": url,
                    "message": f"Jira Cloud reachable; credentials rejected or missing (HTTP {e.code}). Set JIRA_EMAIL and JIRA_API_TOKEN.",
                }
            return {
                "ok": False,
                "connected": False,
                "authenticated": False,
                "status_code": e.code,
                "base_url": url,
                "message": f"HTTP error {e.code}: {e.reason}",
            }
        except Exception as e:
            return {
                "ok": False,
                "connected": False,
                "authenticated": False,
                "status_code": None,
                "base_url": url,
                "message": f"Connection error: {e}",
            }

    def test_connection(self) -> bool:
        """Verify Jira credentials and reachability."""
        res = self.check_connection()
        return bool(res.get("connected"))

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

        if not self.base_url:
            raise ValueError(
                f"Jira client integration for {issue_key} requires a Jira URL. Set jira_url on the board or JIRA_BASE_URL environment variable."
            )

        url = self.base_url.rstrip("/")
        if not (url.startswith("http://") or url.startswith("https://")):
            url = f"https://{url}"

        api_url = f"{url}/rest/api/3/issue/{issue_key}"
        headers = self._build_auth_headers()
        req = urllib.request.Request(api_url, headers=headers, method="GET")

        try:
            with urllib.request.urlopen(req, timeout=15) as resp:
                raw_bytes = resp.read()
                data = json.loads(raw_bytes.decode("utf-8"))
                return self._parse_jira_payload(effective_project, issue_key, data)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                raise ValueError(f"Jira issue '{issue_key}' not found at {api_url}") from e
            if e.code in (401, 403):
                raise PermissionError(
                    f"Authentication failed fetching Jira issue '{issue_key}' (HTTP {e.code}). Set JIRA_EMAIL and JIRA_API_TOKEN."
                ) from e
            raise RuntimeError(f"Failed to fetch Jira issue '{issue_key}': HTTP {e.code} {e.reason}") from e
        except Exception as e:
            raise RuntimeError(f"Failed to connect to Jira at {api_url}: {e}") from e

    def _parse_jira_payload(
        self, project: str, issue_key: str, data: dict[str, Any]
    ) -> ExternalIssue:
        """Helper to parse Jira API JSON response into ExternalIssue."""
        fields = data.get("fields", {})
        summary = str(fields.get("summary") or data.get("title") or issue_key).strip()

        # Jira description can be Atlassian Document Format (ADF) or plain string
        raw_desc = fields.get("description") or data.get("body") or ""
        if isinstance(raw_desc, dict):
            body = extract_adf_text(raw_desc).strip()
        else:
            body = str(raw_desc)

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

        iss = ExternalIssue(
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
        iss.issue_type = iss.infer_issue_type()
        return iss
