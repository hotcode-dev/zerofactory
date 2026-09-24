"""GitHub Pull Request and review comments integration for Zero Factory."""

from __future__ import annotations

import json
import os
import re
import subprocess
from pathlib import Path
from typing import Any, Dict, List, Optional, Set, Tuple

from .config import _d, _log


def extract_gh_repo_info(pr_url: str) -> Optional[Tuple[str, str, int]]:
    """Parse owner, repo, and pull number from a GitHub PR URL."""
    if not pr_url:
        return None
    match = re.match(r"https?://github\.com/([^/]+)/([^/]+)/pull/(\d+)", pr_url)
    if not match:
        return None
    return match.group(1), match.group(2), int(match.group(3))


def fetch_pr_review_comments(
    repo_path: Path,
    pr_url: Optional[str] = None,
    task_id: Optional[str] = None,
    pr_data: Optional[Dict[str, Any]] = None,
    exclude_authors: Optional[Set[str]] = None,
    additional_reviewer_usernames: Optional[Set[str]] = None,
) -> List[Dict[str, Any]]:
    """Fetch all types of review comments for a GitHub PR:
    1. Inline diff review comments (/pulls/{pr}/comments)
    2. Review summaries and states (/pulls/{pr}/reviews)
    3. PR issue/conversation comments (/issues/{pr}/comments)
    4. Code suggestions inside comments

    Only feedback from repository owners, members, collaborators, or the
    board's explicit additional-reviewer allowlist is returned. This prevents
    unrelated PR participants from changing an automation task's disposition.

    Returns a standardized list of comment dicts.
    """
    if os.environ.get("ZEROFACTORY_SKIP_GIT"):
        return []

    if exclude_authors is None:
        exclude_authors = {"github-actions[bot]", "web-flow"}
    trusted_associations = {"OWNER", "MEMBER", "COLLABORATOR"}
    additional_reviewers = {
        username.strip().lstrip("@").lower()
        for username in (additional_reviewer_usernames or set())
        if username and username.strip()
    }

    def is_excluded_author(author: str) -> bool:
        """Exclude automation from actionable review feedback.

        Deployment/status bots post ordinary PR conversation comments.  Those
        comments must not undo an explicit reviewer approval and send the task
        back to the builder.
        """
        normalized = (author or "").lower()
        return not normalized or normalized in exclude_authors or normalized.endswith("[bot]")

    def is_trusted_reviewer(author: str, association: str = "") -> bool:
        """Return whether a non-bot PR participant may control task routing."""
        normalized = (author or "").lower()
        return (
            not is_excluded_author(normalized)
            and (
                normalized in additional_reviewers
                or (association or "").upper() in trusted_associations
            )
        )

    comments: List[Dict[str, Any]] = []
    seen_ids: Set[str] = set()

    # If pr_url is not provided, try to get from pr_data or gh pr view
    if not pr_url and pr_data:
        pr_url = pr_data.get("url")

    info = _d().extract_gh_repo_info(pr_url or "")
    if not info and repo_path and task_id:
        try:
            res = subprocess.run(
                ["gh", "pr", "view", f"task/{task_id}", "--json", "url"],
                cwd=str(repo_path), capture_output=True, text=True, timeout=10
            )
            if res.returncode == 0:
                url_val = json.loads(res.stdout).get("url") or ""
                info = _d().extract_gh_repo_info(url_val)
        except Exception:
            pass

    # 1. Check pr_data if provided (e.g. from gh pr view --json reviews,comments)
    if pr_data:
        for rev in pr_data.get("reviews", []):
            author = (rev.get("author") or {}).get("login") or rev.get("user", {}).get("login") or ""
            association = rev.get("authorAssociation") or rev.get("author_association") or ""
            body = (rev.get("body") or "").strip()
            state = rev.get("state") or ""
            rev_id = str(rev.get("id") or "")
            cid = f"review_{rev_id}"
            if cid not in seen_ids and is_trusted_reviewer(author, association):
                if body or state == "CHANGES_REQUESTED":
                    seen_ids.add(cid)
                    comments.append({
                        "comment_id": cid,
                        "type": "review_summary",
                        "author": author,
                        "state": state,
                        "body": body or f"Review submitted with state: {state}",
                        "path": None,
                        "line": None,
                        "diff_hunk": None,
                        "suggestion": None,
                        "created_at": rev.get("submittedAt") or rev.get("submitted_at") or ""
                    })

        for com in pr_data.get("comments", []):
            author = (com.get("author") or {}).get("login") or com.get("user", {}).get("login") or ""
            association = com.get("authorAssociation") or com.get("author_association") or ""
            body = (com.get("body") or "").strip()
            com_id = str(com.get("id") or "")
            cid = f"issue_{com_id}"
            if cid not in seen_ids and is_trusted_reviewer(author, association):
                if body and "Automated PR for task" not in body:
                    seen_ids.add(cid)
                    comments.append({
                        "comment_id": cid,
                        "type": "pr_comment",
                        "author": author,
                        "state": "COMMENTED",
                        "body": body,
                        "path": None,
                        "line": None,
                        "diff_hunk": None,
                        "suggestion": None,
                        "created_at": com.get("createdAt") or com.get("created_at") or ""
                    })

    if not info or os.environ.get("ZEROFACTORY_SKIP_GH_API"):
        return comments

    owner, repo, pr_num = info

    # 2. Fetch inline diff review comments via GitHub REST API
    try:
        res = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}/pulls/{pr_num}/comments"],
            cwd=str(repo_path), capture_output=True, text=True, timeout=5
        )
        if res.returncode == 0:
            raw_inline = json.loads(res.stdout)
            if isinstance(raw_inline, list):
                for item in raw_inline:
                    cid = f"inline_{item.get('id')}"
                    if cid in seen_ids:
                        continue
                    author = item.get("user", {}).get("login") or ""
                    if not is_trusted_reviewer(author, item.get("author_association") or ""):
                        continue
                    body = (item.get("body") or "").strip()
                    if not body:
                        continue

                    suggestion = None
                    sugg_match = re.search(r"```suggestion\r?\n(.*?)\r?\n```", body, re.DOTALL)
                    if sugg_match:
                        suggestion = sugg_match.group(1)

                    seen_ids.add(cid)
                    comments.append({
                        "comment_id": cid,
                        "type": "inline_review",
                        "author": author,
                        "state": "COMMENTED",
                        "body": body,
                        "path": item.get("path"),
                        "line": item.get("line") or item.get("original_line"),
                        "start_line": item.get("start_line") or item.get("original_start_line"),
                        "diff_hunk": item.get("diff_hunk"),
                        "suggestion": suggestion,
                        "created_at": item.get("created_at") or ""
                    })
    except Exception as e:
        _log.debug("Failed to fetch inline review comments for %s/%s#%s: %s", owner, repo, pr_num, e)

    # 3. Fetch PR reviews via GitHub REST API if not already retrieved
    try:
        res = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}/pulls/{pr_num}/reviews"],
            cwd=str(repo_path), capture_output=True, text=True, timeout=5
        )
        if res.returncode == 0:
            raw_reviews = json.loads(res.stdout)
            if isinstance(raw_reviews, list):
                for item in raw_reviews:
                    cid = f"review_{item.get('id')}"
                    if cid in seen_ids:
                        continue
                    author = item.get("user", {}).get("login") or ""
                    if not is_trusted_reviewer(author, item.get("author_association") or ""):
                        continue
                    body = (item.get("body") or "").strip()
                    state = item.get("state") or ""
                    if body or state == "CHANGES_REQUESTED":
                        seen_ids.add(cid)
                        comments.append({
                            "comment_id": cid,
                            "type": "review_summary",
                            "author": author,
                            "state": state,
                            "body": body or f"Review submitted with state: {state}",
                            "path": None,
                            "line": None,
                            "diff_hunk": None,
                            "suggestion": None,
                            "created_at": item.get("submitted_at") or ""
                        })
    except Exception as e:
        _log.debug("Failed to fetch reviews for %s/%s#%s: %s", owner, repo, pr_num, e)

    # 4. Fetch PR conversation/issue comments if not already retrieved
    try:
        res = subprocess.run(
            ["gh", "api", f"repos/{owner}/{repo}/issues/{pr_num}/comments"],
            cwd=str(repo_path), capture_output=True, text=True, timeout=5
        )
        if res.returncode == 0:
            raw_issues = json.loads(res.stdout)
            if isinstance(raw_issues, list):
                for item in raw_issues:
                    cid = f"issue_{item.get('id')}"
                    if cid in seen_ids:
                        continue
                    author = item.get("user", {}).get("login") or ""
                    if not is_trusted_reviewer(author, item.get("author_association") or ""):
                        continue
                    body = (item.get("body") or "").strip()
                    if body and "Automated PR for task" not in body:
                        seen_ids.add(cid)
                        comments.append({
                            "comment_id": cid,
                            "type": "pr_comment",
                            "author": author,
                            "state": "COMMENTED",
                            "body": body,
                            "path": None,
                            "line": None,
                            "diff_hunk": None,
                            "suggestion": None,
                            "created_at": item.get("created_at") or ""
                        })
    except Exception as e:
        _log.debug("Failed to fetch issue comments for %s/%s#%s: %s", owner, repo, pr_num, e)

    return comments


def format_task_comment_body(comment: Dict[str, Any]) -> str:
    """Format a GitHub PR comment into a descriptive task comment."""
    ctype = comment.get("type", "")
    body = comment.get("body", "")
    path = comment.get("path")
    line = comment.get("line")
    start_line = comment.get("start_line")
    suggestion = comment.get("suggestion")

    parts = []
    if ctype == "inline_review" and path:
        # GitHub leaves `line` null (keeping only `start_line`/`start_side`) for
        # comments anchored to lines no longer present in the diff. Guard both
        # sides so a None value is never interpolated into the anchor.
        line_str = (
            f":L{start_line}-{line}"
            if (start_line and line and start_line != line)
            else (
                f":L{line}"
                if line
                else (f":L{start_line}" if start_line else "")
            )
        )
        parts.append(f"**[GitHub Review Comment on `{path}{line_str}`]**")
    elif ctype == "review_summary":
        state = comment.get("state", "COMMENTED")
        parts.append(f"**[GitHub PR Review ({state})]**")
    else:
        parts.append("**[GitHub PR Comment]**")

    parts.append(body)
    if suggestion:
        parts.append(f"\n```suggestion\n{suggestion}\n```")

    return "\n".join(parts)


def is_reviewer_approval_comment(comment_body: str, state: Optional[str] = None) -> bool:
    """Return True if a PR review comment or review summary represents an approval verdict.

    Handles cases where GitHub prevents self-approval (PR author matches reviewer CLI identity)
    and the reviewer submits their approval verdict as a review comment.
    """
    if state == "APPROVED":
        return True
    body = (comment_body or "").strip()
    if not body:
        return False
    lower = body.lower()

    has_approval_signal = any(phrase in lower for phrase in [
        "[reviewer feedback]",
        "reviewer feedback",
        "verdict: approve",
        "verdict: approved",
        "verdict: **approve**",
        "approved — no changes requested",
        "approved - no changes requested",
        "approved for human review",
        "no changes requested",
        "approving for human review",
        "status: approved",
    ]) or lower.startswith("approved")

    clean_for_changes = (
        lower
        .replace("no changes requested", "")
        .replace("without changes requested", "")
        .replace("zero changes requested", "")
    )
    has_changes_requested = any(phrase in clean_for_changes for phrase in [
        "changes requested",
        "changes needed",
        "requires changes",
        "please fix",
        "must be fixed",
        "needs work",
        "action required",
        "unresolved conflict",
    ])

    return has_approval_signal and not has_changes_requested
