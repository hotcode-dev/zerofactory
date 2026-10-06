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
