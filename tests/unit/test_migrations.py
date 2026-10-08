"""Unit tests for the migration runner."""

import sqlite3
from pathlib import Path

from migrations.runner import get_applied_migrations, run_migrations


def test_run_migrations_applies_pending_in_order_and_once(tmp_path: Path):
    """Pending migrations apply oldest-first and are recorded for idempotency."""
    mdir = tmp_path / "migrations"
    mdir.mkdir()
    (mdir / "0001_first.sql").write_text("CREATE TABLE t (id INTEGER PRIMARY KEY);")
    (mdir / "0002_second.sql").write_text("INSERT INTO t (id) VALUES (1);")

    conn = sqlite3.connect(tmp_path / "m.db")
    try:
        applied = run_migrations(conn, migrations_dir=mdir)
        assert applied == ["0001_first", "0002_second"]

        # Recorded in schema_migrations and idempotent on re-run.
        assert set(get_applied_migrations(conn)) == {"0001_first", "0002_second"}
        assert run_migrations(conn, migrations_dir=mdir) == []
        assert conn.execute("SELECT COUNT(*) FROM t").fetchone()[0] == 1
    finally:
        conn.close()


def test_migration_0001_initial_schema(tmp_path: Path):
    """Verify 0001 initial schema creates boards, board_repositories, tasks, and task_links with unified multi-repo structure."""
    from migrations import run_migrations

    conn = sqlite3.connect(tmp_path / "actual.db")
    try:
        applied = run_migrations(conn)
        assert "0001_initial_schema" in applied

        cur = conn.cursor()
        cur.execute("PRAGMA table_info(boards)")
        board_cols = {row[1] for row in cur.fetchall()}
        assert {"slug", "description", "architecture", "max_concurrent_running", "auto_record_memory", "jira_url"}.issubset(board_cols)

        cur.execute("PRAGMA table_info(board_repositories)")
        repo_cols = {row[1] for row in cur.fetchall()}
        assert {"id", "board_slug", "repo_alias", "git_url", "target_branch", "additional_reviewer_usernames"}.issubset(repo_cols)

        cur.execute("PRAGMA table_info(tasks)")
        task_cols = {row[1] for row in cur.fetchall()}
        assert "repo_alias" in task_cols

        cur.execute("PRAGMA table_info(task_links)")
        link_cols = {row[1] for row in cur.fetchall()}
        assert "link_type" in link_cols
    finally:
        conn.close()
