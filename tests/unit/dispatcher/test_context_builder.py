"""Unit tests for dispatcher/context_builder.py: conventional commit formatting, memory injection, reviewer git context."""

import sqlite3
import subprocess
from pathlib import Path

from dispatcher.context_builder import (
    digest_board_architecture_context,
    digest_board_memories_context,
    digest_parent_and_peer_tasks_context,
    digest_reviewer_git_context,
    format_conventional_message,
)


def test_conventional_commit_formatting():
    """Verify title parsing, badge stripping, and scope extraction."""
    cases = [
        (
            "REFACTOR: Extract shared reverseMap + regex encode/decode helpers (9x duplicated reverse-map construction, 3x duplicated global-regex substitution pairs) in src/dict.ts",
            "zf-fb4215f1",
            "refactor(dict): extract shared reverseMap + regex encode/decode helpers",
        ),
        (
            "BUG FIX [P0] dispatcher promote/spawn ignore parent dependencies: task dispatched before its prerequisites are done",
            "zf-86d5c7f5",
            "fix(dispatcher): promote/spawn ignore parent dependencies: task dispatched before its prerequisites are done",
        ),
        (
            "SECURITY: Remove committed API gateway secrets (.env) from git history",
            "zf-9493d068",
            "fix(security): remove committed API gateway secrets from git history",
        ),
        (
            "feat: implement base92 encoding",
            "zf-123",
            "feat: implement base92 encoding",
        ),
        (
            "Add unit tests for stuck task reaper in test_plugin.py",
            "zf-456",
            "test(test_plugin): add unit tests for stuck task reaper",
        ),
    ]

    for title, task_id, expected_subj in cases:
        subj, body = format_conventional_message(title, task_id)
        assert subj == expected_subj
        assert f"Task: {task_id}" in body


def test_digest_board_memories_context(tmp_path: Path):
    """Verify board memories retrieval, tag formatting, and limit enforcement."""
    db_file = tmp_path / "test.db"
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute(
            """
            CREATE TABLE board_memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board_slug TEXT,
                category TEXT,
                content TEXT,
                tags TEXT,
                author TEXT,
                created_at INTEGER
            )
            """
        )
        conn.execute(
            """
            INSERT INTO board_memories (board_slug, category, content, tags, author, created_at)
            VALUES ('repo-a', 'gotcha', 'Always run lint before commit', '["lint", "ci"]', 'zf-reviewer', 1000)
            """
        )
        conn.commit()

    # Board with memories
    context = digest_board_memories_context("repo-a", db_path=str(db_file))
    assert "REPOSITORY KNOWLEDGE & CONVENTIONS" in context
    assert "[gotcha] Always run lint before commit [tags: lint, ci]" in context

    # Board with no memories
    empty_context = digest_board_memories_context("repo-empty", db_path=str(db_file))
    assert empty_context == ""

    # None board slug
    assert digest_board_memories_context(None) == ""


def test_digest_reviewer_git_context_non_git(tmp_path: Path):
    """Non-git workspace returns empty string."""
    empty_dir = tmp_path / "empty"
    empty_dir.mkdir()
    assert digest_reviewer_git_context(empty_dir) == ""


def test_digest_reviewer_git_context_with_commits(tmp_path: Path):
    """Git workspace produces pre-digested commits, diffstat, and diff."""
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=str(repo), check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=str(repo), check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True
    )

    (repo / "base.txt").write_text("line 1\n")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial commit"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )

    # Branch to task/feature
    subprocess.run(
        ["git", "checkout", "-b", "task/feature"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    (repo / "feature.py").write_text("def hello():\n    return 'world'\n")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: add hello function"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )

    ctx = digest_reviewer_git_context(repo, target_branch="main")
    assert "Pre-Digested PR Changes" in ctx
    assert "feature.py" in ctx
    assert "feat: add hello function" in ctx


def test_digest_board_architecture_context(tmp_path: Path):
    """Verify system architecture notes and multi-repo topology extraction."""
    db_file = tmp_path / "test.db"
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute(
            """
            CREATE TABLE boards (
                slug TEXT PRIMARY KEY,
                name TEXT,
                architecture TEXT
            )
            """
        )
        conn.execute(
            """
            CREATE TABLE board_repositories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                board_slug TEXT,
                repo_alias TEXT,
                git_url TEXT,
                target_branch TEXT,
                additional_reviewer_usernames TEXT DEFAULT '[]'
            )
            """
        )
        conn.execute(
            "INSERT INTO boards (slug, name, architecture) VALUES ('b-multi', 'Multi-Repo', 'Services communicate via Kafka events.')"
        )
        conn.execute(
            "INSERT INTO board_repositories (board_slug, repo_alias, git_url, target_branch) VALUES ('b-multi', 'gateway', 'git@github.com:org/gateway.git', 'main')"
        )
        conn.execute(
            "INSERT INTO board_repositories (board_slug, repo_alias, git_url, target_branch) VALUES ('b-multi', 'auth-service', 'git@github.com:org/auth.git', 'main')"
        )
        conn.commit()

    ctx = digest_board_architecture_context("b-multi", current_repo_alias="gateway", db_path=str(db_file))
    assert "SYSTEM ARCHITECTURE & MULTI-REPO TOPOLOGY" in ctx
    assert "Active Target Repository: `gateway`" in ctx
    assert "auth-service" in ctx
    assert "../auth-service/" in ctx
    assert "Services communicate via Kafka events." in ctx


def test_digest_parent_and_peer_tasks_context(tmp_path: Path):
    """Verify parent blocker and peer relation extraction."""
    db_file = tmp_path / "test.db"
    with sqlite3.connect(str(db_file)) as conn:
        conn.execute(
            """
            CREATE TABLE tasks (
                id TEXT PRIMARY KEY,
                title TEXT,
                status TEXT,
                repo_alias TEXT,
                pr_url TEXT,
                metadata TEXT,
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
                link_type TEXT
            )
            """
        )
        conn.execute(
            "INSERT INTO tasks (id, title, status, repo_alias, pr_url, created_at) VALUES ('t-1', 'Update common lib', 'done', 'common-lib', 'https://github.com/org/common/pull/1', 100)"
        )
        conn.execute(
            "INSERT INTO tasks (id, title, status, repo_alias, pr_url, created_at) VALUES ('t-2', 'Update auth service', 'running', 'auth-service', '', 200)"
        )
        conn.execute(
            "INSERT INTO tasks (id, title, status, repo_alias, pr_url, created_at) VALUES ('t-3', 'Update gateway', 'todo', 'gateway', '', 300)"
        )

        # t-2 is blocked by t-1 (blocks) and relates to t-3 (relates_to)
        conn.execute("INSERT INTO task_links (parent_id, child_id, link_type) VALUES ('t-1', 't-2', 'blocks')")
        conn.execute("INSERT INTO task_links (parent_id, child_id, link_type) VALUES ('t-2', 't-3', 'relates_to')")
        conn.commit()

    ctx = digest_parent_and_peer_tasks_context("t-2", db_path=str(db_file))
    assert "TASK DEPENDENCIES & RELATED FEATURES" in ctx
    assert "Upstream Completed Dependencies:" in ctx
    assert "#t-1 [common-lib]: Update common lib" in ctx
    assert "(PR: https://github.com/org/common/pull/1)" in ctx
    assert "Related Peer Tasks in this Feature:" in ctx
    assert "#t-3 [gateway]: Update gateway" in ctx

