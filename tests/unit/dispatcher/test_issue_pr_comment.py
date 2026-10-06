"""Unit tests for the PR-opened reply on the source GitHub issue (Option B).

Covers the spec's test plan A–F hermetically: all `gh`/`git` subprocess calls
are mocked (no real GitHub or network access).
"""

import json
import os
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock, patch

from dispatcher.scheduler import post_issue_pr_comment
from dispatcher.scheduler import run_dispatch_cycle
from tests.unit.dispatcher.test_scheduler import _init_test_db

TASK_ID = "zf-hdz-test123"
ISSUE_ID = "42"
PR_URL = "https://github.com/foo/bar/pull/100"
MARKER = f"<!-- zf-task:{TASK_ID} -->"


class _NoneCursor:
    """Cursor stand-in whose queries fail (no such table)."""

    def execute(self, sql, params=None):
        raise sqlite3.OperationalError("no such table")


class _BoardGitUrlCursor:
    """Cursor stand-in answering the boards.git_url lookup only."""

    def __init__(self, git_url: str):
        self._row = (git_url,)

    def execute(self, sql, params=None):
        if "git_url" in sql:
            return self

    def fetchone(self):
        return self._row


def _gh_mock(
    repo_dir: Path, view_comments: list | None = None, comment_ok: bool = True
):
    """Build a fake_run for the full cycle + capture list for gh calls.

    view_comments: comment bodies returned by `gh issue view --json comments`.
    comment_ok: whether `gh issue comment` exits 0.
    """
    gh_calls: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        cmd = [str(c) for c in cmd]
        if "rev-parse" in cmd:
            return MagicMock(returncode=0, stdout=str(repo_dir))
        if "status" in cmd:
            return MagicMock(returncode=0, stdout="")
        if "issue" in cmd and "view" in cmd:
            # Dedup check: `gh issue view <id> --repo <r> --json comments`
            return MagicMock(returncode=0, stdout=json.dumps(view_comments or []))
        if "issue" in cmd and "comment" in cmd:
            gh_calls.append(cmd)
            return MagicMock(
                returncode=0 if comment_ok else 1,
                stdout="",
                stderr="" if comment_ok else "rate limit exceeded",
            )
        if "view" in cmd:
            return MagicMock(returncode=0, stdout=json.dumps({"url": PR_URL}))
        return MagicMock(returncode=0, stdout="")

    return fake_run, gh_calls


def _run_cycle(db_path: Path, fake_run):
    import dispatcher

    lock_file = db_path.parent / "dispatcher.lock"
    with (
        patch.object(dispatcher, "get_dispatcher_lock_path", return_value=lock_file),
        patch.dict(
            os.environ,
            {
                "ZEROFACTORY_SKIP_GIT": "",
                "ZEROFACTORY_SKIP_WORKER_SPAWN": "1",
                "ZEROFACTORY_SKIP_PRECOMMIT": "1",
            },
        ),
        patch.object(dispatcher, "resolve_task_repo_path", return_value=db_path.parent),
        patch("dispatcher.scheduler.subprocess.run", side_effect=fake_run),
        patch.object(dispatcher, "clean_stale_git_locks"),
        patch.object(dispatcher, "get_git_dir", return_value=None),
        patch.object(dispatcher, "get_unmerged_status_files", return_value=[]),
        patch.object(
            dispatcher, "check_unresolved_conflicts_safe", return_value=(True, [], "")
        ),
        patch.object(dispatcher, "pull_and_merge_main", return_value=(True, [], "")),
        patch.object(dispatcher, "stop_task_worker"),
        patch.object(dispatcher, "_remove_worktree"),
        patch.object(dispatcher, "setup_worktree"),
        patch.object(
            dispatcher, "get_scanner_cron_config", return_value={"scan_on_idle": False}
        ),
    ):
        return run_dispatch_cycle(db_path)


def _seed_task(db_path: Path, metadata: dict, workspace_dir: Path):
    # 'running' + awaiting_pr=True marks builder-finished work that still needs
    # dispatcher packaging (PR sync); 'done' is strictly terminal and would be
    # finalized instead of packaged.
    metadata.setdefault("awaiting_pr", True)
    now = 1000
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO boards (slug, name, git_url, target_branch) "
            "VALUES ('b1', 'Board', 'https://github.com/foo/bar.git', 'main')"
        )
        conn.execute(
            "INSERT INTO tasks VALUES (?, 'Work Item', '', 'running', 'zf-builder', "
            "'P1', ?, '[]', '', ?, '', 'b1', '', '', ?, ?)",
            (TASK_ID, json.dumps(metadata), str(workspace_dir), now, now),
        )
        conn.commit()


def _gh_comment_args(gh_calls: list[list[str]]) -> list[list[str]]:
    return [c for c in gh_calls if "issue" in c and "comment" in c]


def _read_task(db_path: Path) -> dict:
    with sqlite3.connect(str(db_path)) as conn:
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT status, assignee, pr_url, metadata FROM tasks WHERE id = ?",
            (TASK_ID,),
        ).fetchone()
    return {
        "status": row["status"],
        "assignee": row["assignee"],
        "pr_url": row["pr_url"],
        "metadata": json.loads(row["metadata"] or "{}"),
    }


def _github_meta(**overrides):
    meta = {
        "external_issue": {
            "source": "github",
            "id": ISSUE_ID,
            "key": f"#{ISSUE_ID}",
            "has_ai_request": True,
            "repo_or_project": "foo/bar",
        }
    }
    for key, value in overrides.items():
        if isinstance(value, dict) and key == "external_issue":
            meta["external_issue"] = value
        else:
            meta[key] = value
    return meta


# --- Test A: github task, has_ai_request=true, no marker => exactly one comment
def test_issue_comment_posted_once_for_github_task(tmp_path: Path):
    db_path = tmp_path / "test.db"
    _init_test_db(db_path)
    _seed_task(db_path, _github_meta(), tmp_path)
    fake_run, gh_calls = _gh_mock(tmp_path)

    res = _run_cycle(db_path, fake_run)

    assert res["ok"] is True
    assert res["prs_opened"] == 1
    comments = _gh_comment_args(gh_calls)
    assert len(comments) == 1
    body = comments[0][comments[0].index("--body") + 1]
    assert "PR opened" in body
    assert PR_URL in body
    assert TASK_ID in body
    assert f"Fixes #{ISSUE_ID}" in body
    assert MARKER in body
    # --repo resolved from external_issue.repo_or_project
    assert "foo/bar" in comments[0]
    assert ISSUE_ID in comments[0]

    task = _read_task(db_path)
    assert task["status"] == "todo"
    assert task["assignee"] == "zf-reviewer"
    assert task["pr_url"] == PR_URL
    # Test F aspect: success marks the comment as posted in metadata
    assert task["metadata"].get("issue_pr_comment_posted") is True


# --- Test B: has_ai_request=false => no comment posted, flow still completes
def test_issue_comment_skipped_without_ai_request_label(tmp_path: Path):
    db_path = tmp_path / "test.db"
    _init_test_db(db_path)
    meta = _github_meta(
        external_issue={
            "source": "github",
            "id": ISSUE_ID,
            "key": f"#{ISSUE_ID}",
            "has_ai_request": False,
            "repo_or_project": "foo/bar",
        }
    )
    _seed_task(db_path, meta, tmp_path)
    fake_run, gh_calls = _gh_mock(tmp_path)

    res = _run_cycle(db_path, fake_run)

    assert res["ok"] is True
    assert res["prs_opened"] == 1
    assert _gh_comment_args(gh_calls) == []
    task = _read_task(db_path)
    assert task["assignee"] == "zf-reviewer"
    assert "issue_pr_comment_posted" not in task["metadata"]


# --- Test C: jira-sourced task => no gh issue comment; flow still completes
def test_issue_comment_skipped_for_jira_task(tmp_path: Path):
    db_path = tmp_path / "test.db"
    _init_test_db(db_path)
    meta = {
        "external_issue": {
            "source": "jira",
            "id": "PROJ-123",
            "key": "PROJ-123",
            "has_ai_request": True,
            "repo_or_project": "PROJ",
            "url": "https://jira.example.com/browse/PROJ-123",
        }
    }
    _seed_task(db_path, meta, tmp_path)
    fake_run, gh_calls = _gh_mock(tmp_path)

    res = _run_cycle(db_path, fake_run)

    assert res["ok"] is True
    assert res["prs_opened"] == 1
    assert _gh_comment_args(gh_calls) == []
    task = _read_task(db_path)
    assert task["assignee"] == "zf-reviewer"
    assert "issue_pr_comment_posted" not in task["metadata"]


# --- Test D (cycle level): dispatcher retry after a posted comment — the marker
#     check finds the existing comment, so `gh issue comment` is not invoked.
def test_issue_comment_no_duplicate_on_retry_when_marker_present(tmp_path: Path):
    db_path = tmp_path / "test.db"
    _init_test_db(db_path)
    meta = _github_meta(issue_pr_comment_posted=True)
    _seed_task(db_path, meta, tmp_path)
    # Existing issue comment already carries the marker from the first run
    fake_run, gh_calls = _gh_mock(tmp_path, view_comments=[f"🔀 PR opened\n{MARKER}"])

    res = _run_cycle(db_path, fake_run)

    assert res["ok"] is True
    assert res["prs_opened"] == 1
    assert _gh_comment_args(gh_calls) == []
    task = _read_task(db_path)
    assert task["assignee"] == "zf-reviewer"
    assert task["metadata"].get("issue_pr_comment_posted") is True


# --- Test E: gh issue comment failure is non-fatal; transition still completes
def test_issue_comment_failure_is_non_fatal(tmp_path: Path, caplog):
    db_path = tmp_path / "test.db"
    _init_test_db(db_path)
    _seed_task(db_path, _github_meta(), tmp_path)
    fake_run, gh_calls = _gh_mock(tmp_path, comment_ok=False)

    res = _run_cycle(db_path, fake_run)

    assert res["ok"] is True
    assert res["prs_opened"] == 1
    assert len(_gh_comment_args(gh_calls)) == 1
    task = _read_task(db_path)
    assert task["status"] == "todo"
    assert task["assignee"] == "zf-reviewer"
    assert task["pr_url"] == PR_URL
    assert "issue_pr_comment_posted" not in task["metadata"]
    assert any("Failed to post issue PR comment" in r.message for r in caplog.records)


# --- Test F: helper-level dedup and posting semantics
def test_helper_dedup_marker_present_skips_comment():
    gh_calls: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        cmd = [str(c) for c in cmd]
        if "issue" in cmd and "comment" in cmd:
            gh_calls.append(cmd)
            return MagicMock(returncode=0, stdout="")
        if "issue" in cmd and "view" in cmd:
            # Existing comment already carries the marker (earlier dispatcher run)
            return MagicMock(
                returncode=0,
                stdout=json.dumps([{"body": f"🔀 PR opened\n\n{MARKER}"}]),
            )
        return MagicMock(returncode=0, stdout="")

    with patch("dispatcher.scheduler.subprocess.run", side_effect=fake_run):
        ok = post_issue_pr_comment(
            TASK_ID,
            {
                "source": "github",
                "id": ISSUE_ID,
                "has_ai_request": True,
                "repo_or_project": "foo/bar",
            },
            PR_URL,
        )

    assert ok is True
    assert gh_calls == []


def test_helper_posts_once_and_repo_fallback_from_board():
    fake_run_calls: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        cmd = [str(c) for c in cmd]
        fake_run_calls.append(cmd)
        if "issue" in cmd and "comment" in cmd:
            return MagicMock(returncode=0, stdout="")
        if "issue" in cmd and "view" in cmd:
            return MagicMock(returncode=0, stdout=json.dumps([]))
        return MagicMock(returncode=0, stdout="")

    with patch("dispatcher.scheduler.subprocess.run", side_effect=fake_run):
        ok = post_issue_pr_comment(
            TASK_ID,
            {"source": "github", "id": ISSUE_ID, "has_ai_request": True},
            PR_URL,
            cursor=_BoardGitUrlCursor("https://github.com/foo/bar.git"),  # type: ignore[arg-type]
            board_slug="b1",
        )

    assert ok is True
    comments = [c for c in fake_run_calls if "issue" in c and "comment" in c]
    assert len(comments) == 1
    # owner/repo fell back to the board git_url (repo_or_project missing)
    assert "foo/bar" in comments[0]


def test_helper_gates_no_gh_calls():
    """Jira source / missing id / no ai_request / no pr_url / no resolvable repo => no gh calls."""
    fake_run_calls: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        fake_run_calls.append([str(c) for c in cmd])
        return MagicMock(returncode=0, stdout="[]")

    cases = [
        {"source": "jira", "id": "PROJ-1", "has_ai_request": True},
        {"source": "github", "id": "", "has_ai_request": True},
        {"source": "github", "id": ISSUE_ID, "has_ai_request": False},
        {"source": "github", "id": ISSUE_ID, "has_ai_request": True},
    ]
    with patch("dispatcher.scheduler.subprocess.run", side_effect=fake_run):
        results = [post_issue_pr_comment(TASK_ID, ext, PR_URL) for ext in cases]
    assert results == [False, False, False, False]
    # Last case (no repo_or_project, no cursor/board) warns and skips
    assert fake_run_calls == []
