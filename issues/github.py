"""GitHub Issues client implementation using the GitHub CLI (`gh`)."""

from __future__ import annotations

import json
import logging
import re
import shutil
import subprocess
from typing import Any

from .base import BaseIssueClient, ExternalIssue

_log = logging.getLogger("zerofactory.issues.github")

_GH_ISSUE_URL_RE = re.compile(
    r"^https?://github\.com/([^/]+)/([^/]+)/issues/(\d+)(?:[?#].*)?$"
)
_GH_REPO_ISSUE_RE = re.compile(r"^([^/]+)/([^/#]+)#(\d+)$")
_GH_HASH_OR_NUM_RE = re.compile(r"^#?(\d+)$")


def parse_github_issue_ref(
    issue_ref: str, default_repo: str | None = None
) -> tuple[str, str]:
    """Parse a GitHub issue reference into (owner/repo, issue_number).

    Supported reference formats:
    - Full URL: `https://github.com/owner/repo/issues/42`
    - Short form: `owner/repo#42`
    - Hash form: `#42` (requires default_repo)
    - Plain numeric: `42` (requires default_repo)

    Raises ValueError if reference format is invalid or repository cannot be determined.
    """
    ref = (issue_ref or "").strip()
    if not ref:
        raise ValueError("GitHub issue reference cannot be empty")

    url_match = _GH_ISSUE_URL_RE.match(ref)
    if url_match:
        owner, repo, number = url_match.groups()
        return f"{owner}/{repo}", number

    repo_issue_match = _GH_REPO_ISSUE_RE.match(ref)
    if repo_issue_match:
        owner, repo, number = repo_issue_match.groups()
        return f"{owner}/{repo}", number

    num_match = _GH_HASH_OR_NUM_RE.match(ref)
    if num_match:
        number = num_match.group(1)
        if not default_repo:
            raise ValueError(
                f"Issue '{ref}' requires a target repository. Specify --repo owner/repo or set up a board."
            )
        return default_repo.strip(), number

    raise ValueError(
        f"Invalid GitHub issue reference '{ref}'. Expected format: URL, owner/repo#42, #42, or 42."
    )


class GitHubIssueClient(BaseIssueClient):
    """Client for fetching and parsing issues from GitHub via `gh` CLI."""

    def __init__(self, default_repo: str | None = None):
        self.default_repo = default_repo

    def test_connection(self) -> bool:
        """Verify that `gh` CLI is installed and authenticated."""
        if not shutil.which("gh"):
            return False
        try:
            res = subprocess.run(
                ["gh", "auth", "status"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            return res.returncode == 0
        except Exception:
            return False

    def fetch_issue(
        self, issue_ref: str, repo: str | None = None, **kwargs: Any
    ) -> ExternalIssue:
        """Fetch an issue from GitHub and normalize it to ExternalIssue."""
        target_repo = repo or self.default_repo
        effective_repo, issue_num = parse_github_issue_ref(
            issue_ref, default_repo=target_repo
        )

        cmd = [
            "gh",
            "issue",
            "view",
            str(issue_num),
            "--repo",
            effective_repo,
            "--json",
            "number,title,body,url,author,state,labels,assignees",
        ]

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "GitHub CLI ('gh') is not installed or not in PATH. Please install gh to import GitHub issues."
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"Timed out fetching issue #{issue_num} from '{effective_repo}' via GitHub CLI."
            )

        if res.returncode != 0:
            err_msg = (
                res.stderr.strip()
                or res.stdout.strip()
                or f"exit code {res.returncode}"
            )
            raise RuntimeError(
                f"Failed to fetch GitHub issue #{issue_num} from '{effective_repo}': {err_msg}"
            )

        try:
            data = json.loads(res.stdout)
        except Exception as e:
            raise RuntimeError(
                f"Failed to parse GitHub CLI response for #{issue_num}: {e}"
            )

        author_login = ""
        if isinstance(data.get("author"), dict):
            author_login = data["author"].get("login") or ""

        raw_labels = data.get("labels") or []
        labels = [
            lbl["name"] if isinstance(lbl, dict) else str(lbl)
            for lbl in raw_labels
            if lbl
        ]

        raw_assignees = data.get("assignees") or []
        assignees = [
            a["login"] if isinstance(a, dict) else str(a) for a in raw_assignees if a
        ]

        num_str = str(data.get("number", issue_num))
        issue = ExternalIssue(
            source="github",
            id=num_str,
            key=f"#{num_str}",
            title=str(data.get("title") or "").strip(),
            body=str(data.get("body") or ""),
            url=str(
                data.get("url")
                or f"https://github.com/{effective_repo}/issues/{num_str}"
            ),
            author=author_login,
            state=str(data.get("state") or "OPEN").lower(),
            labels=labels,
            assignees=assignees,
            repo_or_project=effective_repo,
            raw=data,
        )
        issue.issue_type = issue.infer_issue_type()
        return issue

    def fetch_investigation_issues(
        self,
        repo: str | None = None,
        label: str = "zerofactory",
        state: str = "open",
        limit: int = 50,
    ) -> list[ExternalIssue]:
        """Fetch all issues from GitHub flagged for AI investigation via label."""
        target_repo = repo or self.default_repo
        if not target_repo:
            raise ValueError(
                "Repository is required to list issues. Specify --repo owner/repo or set up a board."
            )

        cmd = [
            "gh",
            "issue",
            "list",
            "--repo",
            target_repo,
            "--state",
            state,
            "--limit",
            str(limit),
            "--json",
            "number,title,body,url,author,state,labels,assignees",
        ]
        if label:
            cmd.extend(["--label", label])

        try:
            res = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=30,
            )
        except FileNotFoundError:
            raise RuntimeError(
                "GitHub CLI ('gh') is not installed or not in PATH. Please install gh to import GitHub issues."
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(
                f"Timed out fetching issues from '{target_repo}' via GitHub CLI."
            )

        if res.returncode != 0:
            err_msg = (
                res.stderr.strip()
                or res.stdout.strip()
                or f"exit code {res.returncode}"
            )
            raise RuntimeError(
                f"Failed to list GitHub issues from '{target_repo}': {err_msg}"
            )

        try:
            data_list = json.loads(res.stdout) if res.stdout.strip() else []
        except Exception as e:
            raise RuntimeError(f"Failed to parse GitHub CLI response: {e}")

        issues = []
        for item in data_list:
            author_login = ""
            if isinstance(item.get("author"), dict):
                author_login = item["author"].get("login") or ""

            raw_labels = item.get("labels") or []
            labels = [
                lbl["name"] if isinstance(lbl, dict) else str(lbl)
                for lbl in raw_labels
                if lbl
            ]

            raw_assignees = item.get("assignees") or []
            assignees = [
                a["login"] if isinstance(a, dict) else str(a)
                for a in raw_assignees
                if a
            ]

            num_str = str(item.get("number", ""))
            iss = ExternalIssue(
                source="github",
                id=num_str,
                key=f"#{num_str}",
                title=str(item.get("title") or "").strip(),
                body=str(item.get("body") or ""),
                url=str(
                    item.get("url")
                    or f"https://github.com/{target_repo}/issues/{num_str}"
                ),
                author=author_login,
                state=str(item.get("state") or "OPEN").lower(),
                labels=labels,
                assignees=assignees,
                repo_or_project=target_repo,
                raw=item,
            )
            iss.issue_type = iss.infer_issue_type()
            issues.append(iss)

        return issues
