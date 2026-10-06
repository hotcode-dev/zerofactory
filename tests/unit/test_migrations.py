"""Unit tests for the migration runner and data migrations."""

import sqlite3
from pathlib import Path

from migrations.runner import run_migrations


def test_0004_migrates_legacy_ready_status_to_todo(tmp_path: Path):
    """Legacy 'ready' rows are folded into 'todo' so they remain claimable."""
    conn = sqlite3.connect(tmp_path / "m.db")
    try:
        run_migrations(conn)

        # Simulate a pre-0004 database: schema migrated, but the ready-column
        # removal migration is still pending and legacy rows exist.
        conn.execute("DELETE FROM schema_migrations WHERE version LIKE '0004_%'")
        conn.execute(
            "INSERT INTO tasks (id, title, status, created_at, updated_at) "
            "VALUES ('t-ready', 'Legacy task', 'ready', 1, 1)"
        )
        conn.commit()

        reapplied = run_migrations(conn)
        assert any(v.startswith("0004_") for v in reapplied)

        row = conn.execute("SELECT status FROM tasks WHERE id = 't-ready'").fetchone()
        assert row[0] == "todo"
        actions = [
            r[0]
            for r in conn.execute(
                "SELECT action FROM task_activity WHERE task_id = 't-ready'"
            )
        ]
        assert "migrate" in actions

        # Idempotent: re-running applies nothing and keeps the row stable.
        assert run_migrations(conn) == []
        row = conn.execute("SELECT status FROM tasks WHERE id = 't-ready'").fetchone()
        assert row[0] == "todo"
    finally:
        conn.close()
