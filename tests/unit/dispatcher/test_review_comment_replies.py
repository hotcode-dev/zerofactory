"""Unit tests for threaded reply support on GitHub PR review comments.

Covers:
- `in_reply_to` (GitHub `in_reply_to_id`) captured when fetching inline review
  comments from the REST API.
- `format_task_comment_body` rendering a "[Reply to review comment #N]" header
  for threaded comments and a numeric "GitHub review comment id" footer for
  inline reviews (the anchor a later worker uses to post a threaded reply via
  the GitHub replies endpoint).
- Builder worker prompts instructing the agent it may reply to each addressed
  review comment on GitHub.
"""

import os
import subprocess
from unittest.mock import patch

from dispatcher import fetch_pr_review_comments, format_task_comment_body


def _gh_api_response(payload):
    return subprocess.CompletedProcess(args=[], returncode=0, stdout=payload, stderr="")


def _fetch_inline(repo_path, items):
    """Drive the gh-api fetch path of fetch_pr_review_comments with fake output."""
    import json

    def fake_run(cmd, *args, **kwargs):
        if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "gh":
            if len(cmd) > 2 and "pulls/7/comments" in cmd[2]:
                return _gh_api_response(json.dumps(items))
            return _gh_api_response("[]")
        return subprocess.CompletedProcess(args=cmd, returncode=1, stdout="", stderr="")

    with (
        patch("subprocess.run", side_effect=fake_run),
        patch.dict(os.environ, {}, clear=False),
    ):
        os.environ.pop("ZEROFACTORY_SKIP_GIT", None)
        return fetch_pr_review_comments(
            repo_path=repo_path, pr_url="https://github.com/acme/widget/pull/7"
        )


class TestFetchPrReviewCommentsReplySupport:
    def test_inline_comment_captures_in_reply_to(self, tmp_path):
        items = [
            {
                "id": 111,
                "user": {"login": "human1"},
                "author_association": "OWNER",
                "body": "Original review note",
                "path": "src/app.py",
                "line": 10,
                "start_line": 10,
                "in_reply_to_id": 100,
                "created_at": "2026-09-29T00:00:00Z",
            }
        ]
        comments = _fetch_inline(tmp_path, items)
        assert len(comments) == 1
        assert comments[0]["comment_id"] == "inline_111"
        assert comments[0]["in_reply_to"] == 100

    def test_inline_comment_without_reply_has_null_in_reply_to(self, tmp_path):
        items = [
            {
                "id": 222,
                "user": {"login": "human1"},
                "author_association": "OWNER",
                "body": "Top-level note",
                "path": "src/app.py",
                "line": 5,
                "in_reply_to_id": None,
                "created_at": "2026-09-29T00:00:00Z",
            }
        ]
        comments = _fetch_inline(tmp_path, items)
        assert comments[0]["in_reply_to"] is None


class TestFormatTaskCommentBodyReplySupport:
    def test_reply_header_rendered_for_threaded_comment(self):
        body = format_task_comment_body(
            {
                "comment_id": "inline_111",
                "type": "inline_review",
                "path": "src/app.py",
                "line": 10,
                "start_line": 10,
                "body": "This fixes the race.",
                "in_reply_to": 100,
            }
        )
        assert body.startswith("**[Reply to review comment #100]**")
        assert "**[GitHub Review Comment on `src/app.py:L10`]**" in body
        # Footer exposes the numeric id the agent needs for the replies endpoint.
        assert "_(GitHub review comment id: 111)_" in body

    def test_no_reply_header_for_top_level_comment(self):
        body = format_task_comment_body(
            {
                "comment_id": "inline_222",
                "type": "inline_review",
                "path": "src/app.py",
                "line": 5,
                "body": "Original note",
                "in_reply_to": None,
            }
        )
        assert "Reply to review comment" not in body
        assert "_(GitHub review comment id: 222)_" in body

    def test_footer_only_for_inline_reviews(self):
        body = format_task_comment_body(
            {"comment_id": "issue_333", "type": "pr_comment", "body": "hi"}
        )
        assert "GitHub review comment id" not in body


class TestBuilderPromptInstructsCommentReplies:
    def test_fix_review_comments_prompt_mentions_gh_replies(self, tmp_path):
        """The builder prompt (review-comments branch) must tell the agent it
        can reply to each addressed review comment on GitHub."""
        import dispatcher
        from dispatcher.worker_spawner import spawn_agent_worker

        # Minimal DB with a review comment so the branch triggers.
        db = tmp_path / "zf.db"
        import sqlite3

        with sqlite3.connect(str(db)) as c:
            c.execute(
                "CREATE TABLE task_comments (task_id TEXT, author TEXT, body TEXT, created_at INTEGER)"
            )
            c.execute(
                "INSERT INTO task_comments VALUES ('t1', 'zf-reviewer', "
                "'**[GitHub Review Comment on `src/app.py:L10`]** Fix bug', 0)"
            )

        with (
            patch("subprocess.Popen") as mock_popen,
            patch.object(
                dispatcher, "resolve_profile_state_db", return_value=tmp_path / "s.db"
            ),
            patch.object(
                dispatcher,
                "check_unresolved_conflicts_safe",
                return_value=(True, [], ""),
            ),
            patch.dict(os.environ, {"ZEROFACTORY_DB": str(db)}, clear=False),
        ):
            os.environ.pop("ZEROFACTORY_SKIP_WORKER_SPAWN", None)
            mock_proc = mock_popen.return_value
            mock_proc.pid = 42
            mock_proc.poll.return_value = None

            pid, _ = spawn_agent_worker(
                task_id="t1",
                title="My Task",
                assignee="zf-builder",
                priority="P1",
                description="",
                workspace_path=str(tmp_path),
                branch_name="task/t1",
            )
            assert pid == 42
            prompt = mock_popen.call_args[0][0][-1]
            assert "REPLY" in prompt.upper() or "reply to" in prompt.lower()
            assert "comments/<comment_id>/replies" in prompt
            # AI attribution line must survive the prompt.
            assert "[AI:zf-builder]" in prompt
