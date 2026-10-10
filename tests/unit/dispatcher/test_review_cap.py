"""Unit tests for Review Cap (2 rounds per commit) and Review Comment Filtering.

Tests:
1. is_reviewer_approval_comment:
   - Approval verdicts with non-blocking phrases like "no test changes needed"
   - Explicit approval phrases (APPROVED for human review, verdict: approve, etc.)
   - Rejection when changes are requested ("please fix", "changes requested", etc.)
2. is_actionable_review_comment:
   - Filters out builder verification notes ([AI:zf-builder] Builder verification...)
   - Filters out builder resolution summaries and dedup notes
   - Filters out approval comments
   - Preserves actionable reviewer feedback and change requests
3. Dispatch cycle 2-round review cap per commit:
   - Round 1 critique on commit -> routes to builder (commit_review_count = 1)
   - Round 2 critique on commit -> routes to builder (commit_review_count = 2)
   - Round 3 critique on same commit -> hits 2-round cap -> escalates to human review (assignee='human', status='blocked')
   - New commit SHA from builder -> resets commit_review_count to 0
   - Builder status comments do not bounce the task back to builder
"""

import json
import os
import sqlite3
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from dispatcher import (
    is_actionable_review_comment,
    is_reviewer_approval_comment,
    run_dispatch_cycle,
)


class TestReviewerApprovalComment:
    def test_approval_with_no_test_changes_needed(self):
        body = (
            "[AI:zf-reviewer] [Reviewer Feedback] Round 1: Correctness & Tests — APPROVED for human review\n\n"
            "- npm test: 224 passed / 0 failed. No test changes needed, exactly as the task predicted.\n"
            "Good fix."
        )
        assert is_reviewer_approval_comment(body) is True

    def test_approval_verdict_approve(self):
        body = "[AI:zf-reviewer] Verdict: Approve\n\nLooks clean and well structured."
        assert is_reviewer_approval_comment(body) is True

    def test_approval_state(self):
        assert is_reviewer_approval_comment("", state="APPROVED") is True

    def test_approval_for_human_review(self):
        body = "[AI:zf-reviewer] [Reviewer Feedback] Approved for human review."
        assert is_reviewer_approval_comment(body) is True

    def test_approval_lgtm(self):
        body = "Looks good to me! Ready for human review."
        assert is_reviewer_approval_comment(body) is True

    def test_rejection_changes_requested(self):
        body = (
            "[AI:zf-reviewer] [Reviewer Feedback] Round 1: Correctness & Tests\n\n"
            "Changes requested:\n"
            "1. Please fix null pointer exception on line 42.\n"
            "2. Add test coverage for missing parameter."
        )
        assert is_reviewer_approval_comment(body) is False

    def test_rejection_needs_work(self):
        body = "[AI:zf-reviewer] Needs work: please handle edge case where input is empty list."
        assert is_reviewer_approval_comment(body) is False

    def test_not_approval_just_round_header(self):
        body = "[AI:zf-reviewer] [Reviewer Feedback] Round 1: Checking edge cases in validation."
        assert is_reviewer_approval_comment(body) is False


class TestActionableReviewComment:
    def test_filters_approval_comment(self):
        comment = {
            "author": "zf-reviewer",
            "body": "[AI:zf-reviewer] [Reviewer Feedback] Approved for human review.",
            "state": "COMMENTED",
        }
        assert (
            is_actionable_review_comment(comment, builder_assignee="zf-builder")
            is False
        )

    def test_filters_builder_verification_note(self):
        comment = {
            "author": "ntsd",
            "body": "[AI:zf-builder] Builder verification (Round 2): the alias-only refactor from commit 503fffb verified cleanly.",
            "state": "COMMENTED",
        }
        assert (
            is_actionable_review_comment(comment, builder_assignee="zf-builder")
            is False
        )

    def test_filters_builder_resolution_summary(self):
        comment = {
            "author": "zf-builder",
            "body": "[AI:zf-builder] Resolution summary: fixed the comments from Round 1.",
            "state": "COMMENTED",
        }
        assert (
            is_actionable_review_comment(comment, builder_assignee="zf-builder")
            is False
        )

    def test_filters_dedup_note(self):
        comment = {
            "author": "zf-orchestrator",
            "body": "[AI:zf-builder] Dedup note: skipped duplicate task.",
            "state": "COMMENTED",
        }
        assert (
            is_actionable_review_comment(comment, builder_assignee="zf-builder")
            is False
        )

    def test_filters_builder_assignee_author(self):
        comment = {
            "author": "my-builder-bot",
            "body": "I have updated the implementation.",
            "state": "COMMENTED",
        }
        assert (
            is_actionable_review_comment(comment, builder_assignee="my-builder-bot")
            is False
        )

    def test_allows_actionable_reviewer_critique(self):
        comment = {
            "author": "zf-reviewer",
            "body": "[AI:zf-reviewer] [Reviewer Feedback] Round 1: Please fix the error handling in sync().",
            "state": "COMMENTED",
        }
        assert (
            is_actionable_review_comment(comment, builder_assignee="zf-builder") is True
        )

    def test_allows_inline_review_comment(self):
        comment = {
            "author": "human-reviewer",
            "body": "Use Path.read_text() instead of open().",
            "state": "COMMENTED",
            "path": "src/utils.py",
        }
        assert (
            is_actionable_review_comment(comment, builder_assignee="zf-builder") is True
        )

    def test_allows_changes_requested_state(self):
        comment = {
            "author": "reviewer1",
            "body": "See inline comments.",
            "state": "CHANGES_REQUESTED",
        }
        assert (
            is_actionable_review_comment(comment, builder_assignee="zf-builder") is True
        )


def _init_test_db(db_path: Path):
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            """
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY,
                title TEXT,
                description TEXT,
                status TEXT DEFAULT 'todo',
                assignee TEXT,
                priority TEXT DEFAULT 'P1',
                metadata TEXT,
                skills TEXT,
                workspace_kind TEXT,
                workspace_path TEXT,
                branch_name TEXT,
                board_slug TEXT,
                tenant TEXT,
                pr_url TEXT,
                updated_at INTEGER,
                created_at INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE task_links (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                parent_id TEXT,
                child_id TEXT,
                link_type TEXT,
                created_at INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE task_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                actor TEXT,
                action TEXT,
                details TEXT,
                created_at INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE task_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT,
                author TEXT,
                body TEXT,
                created_at INTEGER
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE boards (
                slug TEXT PRIMARY KEY,
                name TEXT,
                description TEXT,
                git_url TEXT,
                target_branch TEXT,
                max_concurrent_running INTEGER DEFAULT 1
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE settings (
                key TEXT PRIMARY KEY,
                value TEXT,
                updated_at INTEGER
            )
            """
        )
        conn.commit()


class TestReviewCapPerCommit:
    def test_structured_changes_requested_routes_without_comments(self, tmp_path: Path):
        """Signal-first routing: the reviewer's `block --reason changes-requested`
        verdict routes to the builder even when no comments are parseable."""
        db_path = tmp_path / "test.db"
        _init_test_db(db_path)
        lock_file = tmp_path / "dispatcher.lock"

        task_id = "t-structured-verdict"
        initial_meta = {
            "processed_review_comment_ids": [],
            "blocked_reason_type": "changes-requested",
            "packaged_by": "zf-builder",
        }

        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                """
                INSERT INTO tasks (id, title, status, assignee, pr_url, metadata, workspace_path)
                VALUES (?, ?, 'blocked', 'zf-reviewer', 'https://github.com/acme/repo/pull/2', ?, ?)
                """,
                (
                    task_id,
                    "feat: structured verdict",
                    json.dumps(initial_meta),
                    str(tmp_path / "wt"),
                ),
            )
            conn.commit()

        (tmp_path / "wt").mkdir(parents=True, exist_ok=True)

        fake_pr_data = {
            "state": "OPEN",
            "reviewDecision": "",
            "url": "https://github.com/acme/repo/pull/2",
            "mergeable": "MERGEABLE",
            "headRefOid": "commit_sha_abc",
        }

        def fake_subprocess_run(cmd, *args, **kwargs):
            if "view" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps(fake_pr_data))
            return MagicMock(returncode=0, stdout="")

        import dispatcher

        with (
            patch.object(
                dispatcher, "get_dispatcher_lock_path", return_value=lock_file
            ),
            patch.dict(os.environ, {"ZEROFACTORY_SKIP_GIT": ""}),
            patch.object(dispatcher, "resolve_task_repo_path", return_value=tmp_path),
            patch(
                "dispatcher.scheduler.subprocess.run", side_effect=fake_subprocess_run
            ),
            # No comments at all — only the structured verdict can route this.
            patch.object(dispatcher, "fetch_pr_review_comments", return_value=[]),
            patch.object(dispatcher, "stop_task_worker"),
            patch.object(dispatcher, "_remove_worktree"),
            patch.object(dispatcher, "setup_worktree"),
        ):
            res = run_dispatch_cycle(db_path)
            assert res["ok"] is True

        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT status, assignee, metadata FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            assert row["status"] == "todo"
            assert row["assignee"] == "zf-builder"
            meta = json.loads(row["metadata"])
            assert meta["commit_review_count"] == 1

    def test_review_cap_escalation_after_two_rounds(self, tmp_path: Path):
        """When 2 review rounds on the same commit are exceeded, task escalates to human review."""
        db_path = tmp_path / "test.db"
        _init_test_db(db_path)
        lock_file = tmp_path / "dispatcher.lock"

        # Task already had 2 review rounds on commit 'commit_sha_123'
        task_id = "t-cap-test"
        initial_meta = {
            "last_reviewed_commit": "commit_sha_123",
            "commit_review_count": 2,
            "processed_review_comment_ids": [],
            "blocked_reason_type": "changes-requested",
        }

        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                """
                INSERT INTO tasks (id, title, status, assignee, pr_url, metadata, workspace_path)
                VALUES (?, ?, 'blocked', 'zf-reviewer', 'https://github.com/acme/repo/pull/1', ?, ?)
                """,
                (
                    task_id,
                    "feat: test review cap",
                    json.dumps(initial_meta),
                    str(tmp_path / "wt"),
                ),
            )
            conn.commit()

        (tmp_path / "wt").mkdir(parents=True, exist_ok=True)

        fake_pr_data = {
            "state": "OPEN",
            "reviewDecision": "",
            "url": "https://github.com/acme/repo/pull/1",
            "mergeable": "MERGEABLE",
            "headRefOid": "commit_sha_123",  # Same commit!
        }

        fake_review_comment = [
            {
                "comment_id": "cmt_999",
                "type": "pr_comment",
                "author": "zf-reviewer",
                "state": "COMMENTED",
                "body": "[AI:zf-reviewer] [Reviewer Feedback] Round 3: Still seeing issues on commit.",
            }
        ]

        def fake_subprocess_run(cmd, *args, **kwargs):
            if "view" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps(fake_pr_data))
            return MagicMock(returncode=0, stdout="")

        import dispatcher

        with (
            patch.object(
                dispatcher, "get_dispatcher_lock_path", return_value=lock_file
            ),
            patch.dict(
                os.environ,
                {"ZEROFACTORY_SKIP_GIT": "", "ZEROFACTORY_MAX_REVIEW_ROUNDS": "2"},
            ),
            patch.object(dispatcher, "resolve_task_repo_path", return_value=tmp_path),
            patch(
                "dispatcher.scheduler.subprocess.run", side_effect=fake_subprocess_run
            ),
            patch.object(
                dispatcher, "fetch_pr_review_comments", return_value=fake_review_comment
            ),
            patch.object(dispatcher, "stop_task_worker"),
            patch.object(dispatcher, "_remove_worktree"),
        ):
            res = run_dispatch_cycle(db_path)
            assert res["ok"] is True

        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT status, assignee, title, metadata FROM tasks WHERE id = ?",
                (task_id,),
            ).fetchone()
            # Must be escalated to human with status='blocked'
            assert row["assignee"] == "human"
            assert row["status"] == "blocked"
            # Titles carry no lifecycle state markers
            assert "[Human Review]" not in row["title"]

            meta = json.loads(row["metadata"])
            assert meta["review_cap_reached"] is True
            assert (
                "Review cap reached (2 rounds on commit commit_"
                in meta["blocked_reason"]
            )

            # Verify activity log
            activity = conn.execute(
                "SELECT action, details FROM task_activity WHERE task_id = ? AND action = 'review_cap_reached'",
                (task_id,),
            ).fetchone()
            assert activity is not None
            assert (
                "Review cap reached (2 review rounds on commit)" in activity["details"]
            )

    def test_new_commit_resets_review_count(self, tmp_path: Path):
        """When builder pushes a new commit SHA, review count resets to 1 instead of escalating."""
        db_path = tmp_path / "test.db"
        _init_test_db(db_path)
        lock_file = tmp_path / "dispatcher.lock"

        task_id = "t-new-commit"
        initial_meta = {
            "last_reviewed_commit": "old_commit_111",
            "commit_review_count": 2,  # Was at 2 on old commit
            "processed_review_comment_ids": [],
            "blocked_reason_type": "changes-requested",
        }

        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                """
                INSERT INTO tasks (id, title, status, assignee, pr_url, metadata, workspace_path)
                VALUES (?, ?, 'blocked', 'zf-reviewer', 'https://github.com/acme/repo/pull/2', ?, ?)
                """,
                (
                    task_id,
                    "feat: test new commit",
                    json.dumps(initial_meta),
                    str(tmp_path / "wt2"),
                ),
            )
            conn.commit()

        (tmp_path / "wt2").mkdir(parents=True, exist_ok=True)

        fake_pr_data = {
            "state": "OPEN",
            "reviewDecision": "",
            "url": "https://github.com/acme/repo/pull/2",
            "mergeable": "MERGEABLE",
            "headRefOid": "new_commit_222",  # New commit!
        }

        fake_review_comment = [
            {
                "comment_id": "cmt_888",
                "type": "pr_comment",
                "author": "zf-reviewer",
                "state": "COMMENTED",
                "body": "[AI:zf-reviewer] [Reviewer Feedback] Round 1 on new commit: Please fix typo.",
            }
        ]

        def fake_subprocess_run(cmd, *args, **kwargs):
            if "view" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps(fake_pr_data))
            return MagicMock(returncode=0, stdout="")

        import dispatcher

        with (
            patch.object(
                dispatcher, "get_dispatcher_lock_path", return_value=lock_file
            ),
            patch.dict(
                os.environ,
                {"ZEROFACTORY_SKIP_GIT": "", "ZEROFACTORY_MAX_REVIEW_ROUNDS": "2"},
            ),
            patch.object(dispatcher, "resolve_task_repo_path", return_value=tmp_path),
            patch(
                "dispatcher.scheduler.subprocess.run", side_effect=fake_subprocess_run
            ),
            patch.object(
                dispatcher, "fetch_pr_review_comments", return_value=fake_review_comment
            ),
            patch.object(dispatcher, "stop_task_worker"),
            patch.object(dispatcher, "_remove_worktree"),
            patch.object(dispatcher, "setup_worktree"),
        ):
            res = run_dispatch_cycle(db_path)
            assert res["ok"] is True

        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT status, assignee, metadata FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            # Routes to builder for round 1 of new commit
            assert row["assignee"] == "zf-builder"
            assert row["status"] == "todo"

            meta = json.loads(row["metadata"])
            assert meta["last_reviewed_commit"] == "new_commit_222"
            assert meta["commit_review_count"] == 1

    def test_builder_verification_note_does_not_bounce_task(self, tmp_path: Path):
        """Builder verification notes are recorded in comments but do not route task back to builder."""
        db_path = tmp_path / "test.db"
        _init_test_db(db_path)
        lock_file = tmp_path / "dispatcher.lock"

        task_id = "t-builder-note"
        initial_meta = {
            "processed_review_comment_ids": [],
        }

        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                """
                INSERT INTO tasks (id, title, status, assignee, pr_url, metadata, workspace_path)
                VALUES (?, ?, 'blocked', 'zf-reviewer', 'https://github.com/acme/repo/pull/3', ?, ?)
                """,
                (
                    task_id,
                    "feat: test builder note",
                    json.dumps(initial_meta),
                    str(tmp_path / "wt3"),
                ),
            )
            conn.commit()

        (tmp_path / "wt3").mkdir(parents=True, exist_ok=True)

        fake_pr_data = {
            "state": "OPEN",
            "reviewDecision": "",
            "url": "https://github.com/acme/repo/pull/3",
            "mergeable": "MERGEABLE",
            "headRefOid": "commit_111",
        }

        fake_builder_comment = [
            {
                "comment_id": "cmt_builder_note",
                "type": "pr_comment",
                "author": "zf-builder",
                "state": "COMMENTED",
                "body": "[AI:zf-builder] Builder verification (Round 2): tests verified cleanly.",
            }
        ]

        def fake_subprocess_run(cmd, *args, **kwargs):
            if "view" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps(fake_pr_data))
            return MagicMock(returncode=0, stdout="")

        import dispatcher

        with (
            patch.object(
                dispatcher, "get_dispatcher_lock_path", return_value=lock_file
            ),
            patch.dict(os.environ, {"ZEROFACTORY_SKIP_GIT": ""}),
            patch.object(dispatcher, "resolve_task_repo_path", return_value=tmp_path),
            patch(
                "dispatcher.scheduler.subprocess.run", side_effect=fake_subprocess_run
            ),
            patch.object(
                dispatcher,
                "fetch_pr_review_comments",
                return_value=fake_builder_comment,
            ),
            patch.object(dispatcher, "stop_task_worker") as mock_stop,
            patch.object(dispatcher, "setup_worktree") as mock_setup,
        ):
            res = run_dispatch_cycle(db_path)
            assert res["ok"] is True
            mock_stop.assert_not_called()
            mock_setup.assert_not_called()

        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT status, assignee, metadata FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            # Task stays blocked under reviewer, NOT bounced back to builder
            assert row["assignee"] == "zf-reviewer"
            assert row["status"] == "blocked"

            # Comment was recorded in task_comments
            comment_row = conn.execute(
                "SELECT author, body FROM task_comments WHERE task_id = ?", (task_id,)
            ).fetchone()
            assert comment_row is not None
            assert "[AI:zf-builder] Builder verification" in comment_row["body"]

            # ID added to processed_review_comment_ids
            meta = json.loads(row["metadata"])
            assert "cmt_builder_note" in meta["processed_review_comment_ids"]


class TestApprovedParkIdempotent:
    """Regression: a task already parked for human merge must not re-run the
    park side effects every dispatch cycle (zf-hdz-4dc03cee: 450 duplicate
    `approved` activity rows from the non-idempotent branch)."""

    def _seed_task(self, db_path: Path, task_id: str, meta: dict, assignee: str):
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute(
                """
                INSERT INTO tasks (id, title, status, assignee, pr_url, metadata, workspace_path)
                VALUES (?, ?, 'blocked', ?, 'https://github.com/acme/repo/pull/7', ?, ?)
                """,
                (
                    task_id,
                    "feat: approved once",
                    assignee,
                    json.dumps(meta),
                    str(db_path / "wt"),
                ),
            )
            conn.commit()

    def _run_cycles(self, db_path: Path, n: int, comments, decision: str = ""):
        # Lock path must be a plain sibling file — under the sqlite file it
        # would raise ENOTDIR and the cycle would silently skip.
        lock_file = db_path.parent / "dispatcher.lock"
        fake_pr_data = {
            "state": "OPEN",
            "reviewDecision": decision,
            "url": "https://github.com/acme/repo/pull/7",
            "mergeable": "MERGEABLE",
            "headRefOid": "sha_park",
        }

        def fake_subprocess_run(cmd, *args, **kwargs):
            if "view" in cmd:
                return MagicMock(returncode=0, stdout=json.dumps(fake_pr_data))
            return MagicMock(returncode=0, stdout="")

        import dispatcher

        with (
            patch.object(
                dispatcher, "get_dispatcher_lock_path", return_value=lock_file
            ),
            patch.dict(os.environ, {"ZEROFACTORY_SKIP_GIT": ""}),
            patch.object(dispatcher, "resolve_task_repo_path", return_value=db_path),
            patch(
                "dispatcher.scheduler.subprocess.run", side_effect=fake_subprocess_run
            ),
            patch.object(dispatcher, "fetch_pr_review_comments", return_value=comments),
            patch.object(dispatcher, "stop_task_worker") as mock_stop,
            patch.object(dispatcher, "_remove_worktree") as mock_remove,
            patch.object(dispatcher, "setup_worktree"),
        ):
            for _ in range(n):
                res = run_dispatch_cycle(db_path)
                assert res["ok"] is True
        return mock_stop, mock_remove

    def _approved_rows(self, db_path: Path, task_id: str) -> int:
        with sqlite3.connect(str(db_path)) as conn:
            return conn.execute(
                "SELECT COUNT(*) FROM task_activity WHERE task_id = ? AND action = 'approved'",
                (task_id,),
            ).fetchone()[0]

    def test_parked_approved_task_is_not_reparked(self, tmp_path: Path):
        """Task already at the human-merge gate (blocked/human/approved): cycles
        must not add `approved` rows nor redo teardown."""
        db_path = tmp_path / "test.db"
        _init_test_db(db_path)
        task_id = "t-already-parked"
        self._seed_task(
            db_path,
            task_id,
            {
                "blocked_reason": "Reviewer approved; awaiting human merge",
                "blocked_reason_type": "approved",
                "packaged_by": "zf-builder",
                "processed_review_comment_ids": [],
            },
            assignee="human",
        )

        mock_stop, mock_remove = self._run_cycles(db_path, n=3, comments=[])

        assert self._approved_rows(db_path, task_id) == 0
        mock_stop.assert_not_called()
        mock_remove.assert_not_called()
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT status, assignee, metadata FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            assert row["status"] == "blocked"
            assert row["assignee"] == "human"
            assert json.loads(row["metadata"])["blocked_reason_type"] == "approved"

    def test_fresh_approval_parks_exactly_once(self, tmp_path: Path):
        """First approval parks the task; subsequent cycles are no-ops."""
        db_path = tmp_path / "test.db"
        _init_test_db(db_path)
        task_id = "t-fresh-approved"
        self._seed_task(
            db_path,
            task_id,
            {"packaged_by": "zf-builder", "processed_review_comment_ids": []},
            assignee="zf-reviewer",
        )

        mock_stop, mock_remove = self._run_cycles(
            db_path, n=2, comments=[], decision="APPROVED"
        )

        assert self._approved_rows(db_path, task_id) == 1
        assert mock_stop.call_count == 1
        assert mock_remove.call_count == 1
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT status, assignee, metadata FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            assert row["status"] == "blocked"
            assert row["assignee"] == "human"
            assert json.loads(row["metadata"])["blocked_reason_type"] == "approved"

    def test_new_comments_on_parked_task_are_forwarded_not_reparked(
        self, tmp_path: Path
    ):
        """A parked task forwards late review comments but stays parked."""
        db_path = tmp_path / "test.db"
        _init_test_db(db_path)
        task_id = "t-parked-late-comment"
        self._seed_task(
            db_path,
            task_id,
            {
                "blocked_reason": "Reviewer approved; awaiting human merge",
                "blocked_reason_type": "approved",
                "packaged_by": "zf-builder",
                "processed_review_comment_ids": ["cmt_old"],
            },
            assignee="human",
        )
        late_comment = [
            {
                "comment_id": "cmt_late",
                "author": "reviewer1",
                "body": "One more nit on naming.",
                "state": "COMMENTED",
            }
        ]

        self._run_cycles(db_path, n=2, comments=late_comment)

        assert self._approved_rows(db_path, task_id) == 0
        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            bodies = [
                r["body"]
                for r in conn.execute(
                    "SELECT body FROM task_comments WHERE task_id = ?", (task_id,)
                )
            ]
            assert any("One more nit" in b for b in bodies)
            meta_row = conn.execute(
                "SELECT metadata FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            meta = json.loads(meta_row["metadata"])
            assert "cmt_late" in meta["processed_review_comment_ids"]

    def test_actionable_comment_on_parked_approved_task_unparks_to_builder(
        self, tmp_path: Path
    ):
        """When an actionable comment arrives on a parked approved task, it unparks and routes to builder."""
        db_path = tmp_path / "test.db"
        _init_test_db(db_path)
        task_id = "t-parked-actionable-comment"
        self._seed_task(
            db_path,
            task_id,
            {
                "blocked_reason": "Reviewer approved; awaiting human merge",
                "blocked_reason_type": "approved",
                "packaged_by": "zf-builder",
                "processed_review_comment_ids": ["cmt_old"],
            },
            assignee="human",
        )
        actionable_comment = [
            {
                "comment_id": "cmt_human_feedback",
                "author": "human-reviewer",
                "body": "All origins should be able to call to check the status. Please fix CORS.",
                "state": "COMMENTED",
            }
        ]

        self._run_cycles(db_path, n=1, comments=actionable_comment)

        with sqlite3.connect(str(db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT status, assignee, metadata FROM tasks WHERE id = ?", (task_id,)
            ).fetchone()
            assert row["status"] == "todo"
            assert row["assignee"] == "zf-builder"
            meta = json.loads(row["metadata"])
            assert "blocked_reason" not in meta
            assert "blocked_reason_type" not in meta
            assert "cmt_human_feedback" in meta["processed_review_comment_ids"]
