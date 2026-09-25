"""Unit tests for dispatcher/context_builder.py: conventional commit formatting, memory injection, reviewer git context."""

import json
import sqlite3
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch

from dispatcher.context_builder import (
    format_conventional_message,
    digest_board_memories_context,
    digest_reviewer_git_context,
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
            VALUES ('repo-a', 'gotcha', 'Always run lint before commit', '["lint", "ci"]', 'reviewer', 1000)
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
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True)

    (repo / "base.txt").write_text("line 1\n")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-m", "initial commit"], cwd=str(repo), check=True, capture_output=True)

    # Branch to task/feature
    subprocess.run(["git", "checkout", "-b", "task/feature"], cwd=str(repo), check=True, capture_output=True)
    (repo / "feature.py").write_text("def hello():\n    return 'world'\n")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(["git", "commit", "-m", "feat: add hello function"], cwd=str(repo), check=True, capture_output=True)

    ctx = digest_reviewer_git_context(repo, target_branch="main")
    assert "Pre-Digested PR Changes" in ctx
    assert "feature.py" in ctx
    assert "feat: add hello function" in ctx
