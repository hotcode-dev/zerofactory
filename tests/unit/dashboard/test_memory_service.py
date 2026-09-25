"""Unit tests for dashboard/memory_service.py: rule extraction, normalization, deduplication."""

import sqlite3
import pytest

from dashboard.memory_service import (
    normalize_memory_content,
    normalize_file_path,
    compute_dedup_key,
    extract_and_record_memory,
)


def _init_memory_db() -> sqlite3.Connection:
    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    conn.execute(
        """
        CREATE TABLE settings (
            key TEXT PRIMARY KEY,
            value TEXT,
            updated_at INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE boards (
            slug TEXT PRIMARY KEY,
            auto_record_memory INTEGER DEFAULT 1
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE board_memories (
            id TEXT PRIMARY KEY,
            board_slug TEXT,
            task_id TEXT,
            category TEXT,
            content TEXT,
            tags TEXT,
            author TEXT,
            created_at INTEGER,
            updated_at INTEGER
        )
        """
    )
    conn.execute(
        """
        CREATE TABLE activity_log (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            action TEXT,
            actor TEXT,
            board_slug TEXT,
            details TEXT,
            created_at INTEGER
        )
        """
    )
    conn.commit()
    return conn


def test_normalize_memory_content_and_file_path():
    """Verify stripping of quotes, backticks, casefolding, and path normalizing."""
    assert normalize_memory_content("  `*Important Rule*`  ") == "important rule"
    assert normalize_file_path("./src/utils/file.ts") == "src/utils/file.ts"
    assert normalize_file_path("src\\utils\\file.ts") == "src/utils/file.ts"


def test_compute_dedup_key():
    """Deterministic fingerprint from file list and category."""
    files = ["src/b.py", "src/a.py", "./src/b.py"]
    key = compute_dedup_key(files, category="bug-fix")
    assert key == "src/a.py,src/b.py:bug-fix"

    assert compute_dedup_key([]) is None
    assert compute_dedup_key(None) is None


def test_extract_and_record_memory_basic():
    """Reviewer feedback containing GOTCHA: is extracted and stored."""
    conn = _init_memory_db()
    conn.execute("INSERT INTO boards (slug, auto_record_memory) VALUES ('test-board', 1)")
    conn.commit()

    feedback = "LGTM! One note for future: **GOTCHA**: Always run db migrations before starting worker."
    recorded = extract_and_record_memory(conn, "test-board", feedback, task_id="t-1", author="zf-reviewer")

    assert len(recorded) == 1
    assert recorded[0]["category"] == "gotcha"
    assert "Always run db migrations before starting worker" in recorded[0]["content"]

    # Verify stored in DB
    rows = conn.execute("SELECT * FROM board_memories WHERE board_slug = 'test-board'").fetchall()
    assert len(rows) == 1

    # Second run with same feedback should deduplicate and return empty
    duplicate_run = extract_and_record_memory(conn, "test-board", feedback, task_id="t-2")
    assert duplicate_run == []
    rows_after = conn.execute("SELECT * FROM board_memories WHERE board_slug = 'test-board'").fetchall()
    assert len(rows_after) == 1


def test_extract_and_record_memory_board_disabled():
    """When board has auto_record_memory disabled, nothing is extracted."""
    conn = _init_memory_db()
    conn.execute("INSERT INTO boards (slug, auto_record_memory) VALUES ('disabled-board', 0)")
    conn.commit()

    feedback = "GOTCHA: Should not be saved."
    recorded = extract_and_record_memory(conn, "disabled-board", feedback)
    assert recorded == []

    rows = conn.execute("SELECT * FROM board_memories WHERE board_slug = 'disabled-board'").fetchall()
    assert len(rows) == 0
