"""Base abstractions and models for external issue tracker integration.

Provides a unified, deterministic interface for importing issues from external
trackers (GitHub, Jira, etc.) into Zero Factory Kanban tasks.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any, Literal

# Common label-to-priority heuristic rules (evaluated in order)
_P0_LABELS = {"p0", "critical", "blocker", "urgent", "security", "hotfix"}
_P1_LABELS = {"p1", "high", "high-priority", "major", "bug"}
_P3_LABELS = {"p3", "low", "low-priority", "trivial", "minor", "nice-to-have"}

# Common label-to-category heuristic rules
_CATEGORY_RULES: list[tuple[str, set[str]]] = [
    ("security", {"security", "sec", "cve", "vulnerability"}),
    ("performance", {"performance", "perf", "speed", "optimization", "latency"}),
    ("feature", {"feature", "feat", "enhancement", "new-feature", "story"}),
    ("bug-fix", {"bug", "fix", "defect", "error", "failure"}),
    ("refactoring", {"refactor", "refactoring", "cleanup", "techdebt", "tech-debt"}),
    ("documentation", {"documentation", "doc", "docs"}),
    ("testing", {"testing", "test", "tests", "coverage"}),
    (
        "config",
        {"config", "configuration", "ci", "build", "chore", "deps", "dependencies"},
    ),
]

# Default labels indicating a human explicitly requested AI investigation
_AI_INVESTIGATION_LABELS = {
    "zerofactory",
    "ai-investigate",
    "ai-triage",
    "ai-review",
    "ai",
}

# Type inference keyword sets
_BUG_TYPE_KEYWORDS = {
    "bug",
    "fix",
    "defect",
    "error",
    "failure",
    "broken",
    "fault",
    "crash",
}
_FEATURE_TYPE_KEYWORDS = {
    "feature",
    "enhancement",
    "feat",
    "request",
    "story",
    "improvement",
}


@dataclass
class ExternalIssue:
    """Standardized representation of an issue from any tracker (GitHub, Jira)."""

    source: Literal["github", "jira"]
    id: str  # Numeric ID or issue key (e.g. "42", "PROJ-123")
    key: str  # Display key (e.g. "#42", "PROJ-123")
    title: str
    issue_type: Literal["bug", "feature", "task"] = "bug"
    body: str = ""
    url: str = ""
    author: str = ""
    state: str = "open"
    labels: list[str] = field(default_factory=list)
    assignees: list[str] = field(default_factory=list)
    repo_or_project: str = ""  # e.g. "owner/repo" or "PROJ"
    raw: dict[str, Any] = field(default_factory=dict)

    def to_dedup_key(self) -> str:
        """Deterministic fingerprint preventing duplicate tasks across runs.

        Format: issue:<source>:<repo_or_project_lowercased>:<sanitized_id>
        """
        source_clean = self.source.strip().lower()
        repo_clean = self.repo_or_project.strip().lower()
        id_clean = self.id.strip().lower()
        return f"issue:{source_clean}:{repo_clean}:{id_clean}"

    def to_task_id(self, board_slug: str | None = None) -> str:
        """Deterministic task ID derived from board code, source, and issue id.

        Example:
        - Board "hotcode-dev-zerofactory" + GitHub #42 -> "zf-hdz-gh42"
        - Board "my-proj" + Jira "PROJ-123" -> "zf-mp-proj123"
        - No board + GitHub #42 -> "zf-gh42"
        """
        # Derive up to 3 chars board code
        board_code = ""
        if board_slug:
            cleaned = board_slug.strip().lower()
            parts = [p for p in re.split(r"[-_.\s]+", cleaned) if p]
            board_code = "".join(p[0] for p in parts if p[0].isalnum())[-3:]

        prefix = "gh" if self.source == "github" else (self.source[:2].lower() or "ex")
        sanitized_id = re.sub(r"[^a-zA-Z0-9]", "", self.id).lower()

        if board_code:
            return f"zf-{board_code}-{prefix}{sanitized_id}"
        return f"zf-{prefix}{sanitized_id}"

    def infer_issue_type(self) -> Literal["bug", "feature", "task"]:
        """Deterministically infer issue type ('bug' or 'feature') from labels, title, or raw metadata."""
        normalized_labels = {lbl.strip().lower() for lbl in self.labels if lbl}

        # 1. Check raw fields (e.g. Jira issue type)
        if self.raw:
            raw_type = ""
            if "fields" in self.raw and isinstance(self.raw["fields"], dict):
                raw_type = str(
                    self.raw["fields"].get("issuetype", {}).get("name") or ""
                ).lower()
            if raw_type:
                if any(kw in raw_type for kw in ("bug", "defect", "incident")):
                    return "bug"
                if any(
                    kw in raw_type
                    for kw in ("story", "feature", "enhancement", "improvement")
                ):
                    return "feature"

        # 2. Check labels (bug takes priority over general feature if both present, or check order)
        if any(lbl in normalized_labels for lbl in _BUG_TYPE_KEYWORDS):
            return "bug"
        if any(lbl in normalized_labels for lbl in _FEATURE_TYPE_KEYWORDS):
            return "feature"

        # 3. Check title prefixes
        title_clean = self.title.strip().lower()
        if re.search(r"^\[?(?:bug|fix)\]?", title_clean):
            return "bug"
        if re.search(r"^\[?(?:feat|feature|enhancement)\]?", title_clean):
            return "feature"

        return "bug"

    def has_ai_request_label(
        self, allowed_labels: set[str] | list[str] | None = None
    ) -> bool:
        """Check whether the issue has an explicit human request for AI investigation."""
        check_set = (
            {lbl.strip().lower() for lbl in allowed_labels}
            if allowed_labels
            else _AI_INVESTIGATION_LABELS
        )
        normalized_labels = {lbl.strip().lower() for lbl in self.labels if lbl}
        return bool(check_set.intersection(normalized_labels))

    def infer_priority(self) -> str:
        """Deterministically infer task priority (P0, P1, P2, P3) from issue labels/metadata."""
        normalized_labels = {lbl.strip().lower() for lbl in self.labels if lbl}

        if any(lbl in normalized_labels for lbl in _P0_LABELS):
            return "P0"
        if any(lbl in normalized_labels for lbl in _P1_LABELS):
            return "P1"
        if any(lbl in normalized_labels for lbl in _P3_LABELS):
            return "P3"
        return "P2"

    def infer_category(self) -> str:
        """Deterministically infer category (bug-fix, feature, refactoring, etc.) from issue labels."""
        normalized_labels = {lbl.strip().lower() for lbl in self.labels if lbl}

        for cat_name, cat_keywords in _CATEGORY_RULES:
            if any(lbl in normalized_labels for lbl in cat_keywords):
                return cat_name
        if self.issue_type == "feature":
            return "feature"
        return "bug-fix"

    def to_markdown_description(self) -> str:
        """Generate a deterministic markdown task description preserving issue context."""
        lines = [
            f"## {self.source.capitalize()} {self.issue_type.capitalize()} {self.key}: {self.title.strip()}",
            "",
            f"- **Source**: {self.source.capitalize()}",
            f"- **Type**: `{self.issue_type.capitalize()}`",
            f"- **Identifier**: `{self.key}`",
        ]
        if self.url:
            lines.append(f"- **URL**: {self.url}")
        if self.author:
            lines.append(f"- **Author**: @{self.author}")
        if self.state:
            lines.append(f"- **State**: `{self.state}`")
        if self.labels:
            lines.append(f"- **Labels**: {', '.join(f'`{l}`' for l in self.labels)}")
        if self.assignees:
            lines.append(
                f"- **Assignees**: {', '.join(f'@{a}' for a in self.assignees)}"
            )

        lines.extend(
            [
                "",
                "### Description",
                "",
                self.body.strip()
                if self.body
                else "_No description provided in original issue._",
                "",
            ]
        )
        return "\n".join(lines)

    def to_metadata_dict(self) -> dict[str, Any]:
        """Serializable dictionary for task.metadata['external_issue']."""
        return {
            "source": self.source,
            "id": self.id,
            "key": self.key,
            "title": self.title,
            "issue_type": self.issue_type,
            "has_ai_request": self.has_ai_request_label(),
            "url": self.url,
            "author": self.author,
            "state": self.state,
            "labels": list(self.labels),
            "assignees": list(self.assignees),
            "repo_or_project": self.repo_or_project,
        }


class BaseIssueClient(ABC):
    """Abstract interface for fetching issues from an external tracker."""

    @abstractmethod
    def fetch_issue(self, issue_ref: str, **kwargs: Any) -> ExternalIssue:
        """Fetch and normalize an issue by its reference (number, key, or URL)."""
        pass

    @abstractmethod
    def test_connection(self) -> bool:
        """Test whether the issue tracker CLI/API is available and authenticated."""
        pass
