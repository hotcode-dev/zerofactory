"""Zero Factory SQLite Migration Runner.

Discovers and executes numbered SQL/Python migrations sequentially.
Tracks applied migrations in the `schema_migrations` table.
"""

from __future__ import annotations

import importlib.util
import logging
import os
import re
import sqlite3
import sys
import time
from pathlib import Path
_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

_log = logging.getLogger("zerofactory.migrations")

MIGRATION_FILENAME_PATTERN = re.compile(r"^(\d{4}_[\w\-]+)\.(sql|py)$")


def get_migrations_dir() -> Path:
    """Return the absolute path to the migrations directory."""
    return Path(__file__).resolve().parent


def ensure_migration_table(conn: sqlite3.Connection) -> None:
    """Ensure the schema_migrations tracking table exists."""
    conn.execute("""
        CREATE TABLE IF NOT EXISTS schema_migrations (
            version TEXT PRIMARY KEY,
            applied_at INTEGER NOT NULL
        )
    """)


def get_applied_migrations(conn: sqlite3.Connection) -> Dict[str, int]:
    """Return a mapping of applied migration versions to their application timestamp."""
    ensure_migration_table(conn)
    cursor = conn.cursor()
    cursor.execute("SELECT version, applied_at FROM schema_migrations ORDER BY version ASC")
    return {row[0]: row[1] for row in cursor.fetchall()}


def get_available_migrations(migrations_dir: Optional[Path] = None) -> List[Path]:
    """Return a sorted list of all available migration files (.sql and .py)."""
    mdir = migrations_dir or get_migrations_dir()
    if not mdir.exists() or not mdir.is_dir():
        return []

    migration_files: List[Path] = []
    for p in mdir.iterdir():
        if p.is_file() and MIGRATION_FILENAME_PATTERN.match(p.name):
            migration_files.append(p)

    migration_files.sort(key=lambda p: p.name)
    return migration_files


def _resolve_default_db_path() -> Path:
    """Resolve the active database path from environment or dashboard.db."""
    override = os.environ.get("ZEROFACTORY_DB")
    if override:
        return Path(override)
    try:
        from dashboard.db import get_db_path
        return get_db_path()
    except Exception:
        return Path.home() / ".hermes" / "zerofactory.db"


def get_migration_status(
    conn: Optional[sqlite3.Connection] = None,
    db_path: Optional[Union[str, Path]] = None,
    migrations_dir: Optional[Path] = None,
) -> List[Dict[str, Any]]:
    """Return the status of all available migrations."""
    should_close = False
    if conn is None:
        if db_path is None:
            db_path = _resolve_default_db_path()
        conn = sqlite3.connect(str(db_path))
        should_close = True

    try:
        applied = get_applied_migrations(conn)
        available = get_available_migrations(migrations_dir)
        status: List[Dict[str, Any]] = []

        for p in available:
            version = p.stem
            is_applied = version in applied
            status.append({
                "version": version,
                "filename": p.name,
                "path": str(p),
                "applied": is_applied,
                "applied_at": applied.get(version),
            })

        return status
    finally:
        if should_close and conn:
            conn.close()


def _execute_sql_file(conn: sqlite3.Connection, file_path: Path) -> None:
    """Execute a .sql migration file statement-by-statement.

    Safely handles statements like `ALTER TABLE ADD COLUMN` if the column already exists.
    """
    content = file_path.read_text(encoding="utf-8")
    # Split by semicolon while respecting comments
    raw_statements = content.split(";")
    for raw in raw_statements:
        stmt = raw.strip()
        if not stmt:
            continue
        # Remove comment lines to see if there is actual executable SQL
        lines = [line for line in stmt.splitlines() if not line.strip().startswith("--")]
        executable_sql = "\n".join(lines).strip()
        if not executable_sql:
            continue

        try:
            conn.execute(stmt)
        except sqlite3.OperationalError as e:
            err_msg = str(e).lower()
            # If the column or index already exists, allow idempotent pass-through
            if "duplicate column name" in err_msg or "already exists" in err_msg:
                _log.debug("Migration %s statement skipped (%s): %s", file_path.name, e, stmt[:60])
            else:
                raise


def _execute_py_file(conn: sqlite3.Connection, file_path: Path) -> None:
    """Execute a .py migration file by invoking its `up(conn)` function."""
    spec = importlib.util.spec_from_file_location(f"migration_{file_path.stem}", str(file_path))
    if not spec or not spec.loader:
        raise ImportError(f"Cannot load migration module from {file_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    if not hasattr(module, "up"):
        raise AttributeError(f"Python migration {file_path.name} must define an `up(conn)` function")
    module.up(conn)


def run_migrations(
    db: Optional[Union[str, Path, sqlite3.Connection]] = None,
    migrations_dir: Optional[Path] = None,
) -> List[str]:
    """Run all pending database migrations in sequential order.

    Args:
        db: Optional database path (str/Path) or an active sqlite3.Connection.
            Defaults to Zero Factory's configured DB path.
        migrations_dir: Optional path to the migrations directory.

    Returns:
        A list of migration versions applied during this invocation.
    """
    should_close = False
    conn: sqlite3.Connection

    if isinstance(db, sqlite3.Connection):
        conn = db
    else:
        if db is None:
            db_path = _resolve_default_db_path()
        else:
            db_path = Path(db)

        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        should_close = True

    applied_now: List[str] = []

    try:
        ensure_migration_table(conn)
        applied = get_applied_migrations(conn)
        available = get_available_migrations(migrations_dir)

        for p in available:
            version = p.stem
            if version in applied:
                continue

            _log.info("Applying migration: %s", p.name)
            now = int(time.time())

            with conn:
                if p.suffix == ".sql":
                    _execute_sql_file(conn, p)
                elif p.suffix == ".py":
                    _execute_py_file(conn, p)
                else:
                    continue

                conn.execute(
                    "INSERT INTO schema_migrations (version, applied_at) VALUES (?, ?)",
                    (version, now),
                )
                applied_now.append(version)

        return applied_now
    finally:
        if should_close:
            conn.close()


def main() -> None:
    """CLI helper to run migrations or check status."""
    import argparse

    parser = argparse.ArgumentParser(description="Zero Factory SQLite Migrations")
    parser.add_argument("--status", action="store_true", help="Show migration status")
    parser.add_argument("--db", default=None, help="Database file path")
    args = parser.parse_args()

    if args.status:
        statuses = get_migration_status(db_path=args.db)
        print(f"{'Version':<35} {'Status':<12} {'Applied At'}")
        print("-" * 65)
        for s in statuses:
            st = "Applied" if s["applied"] else "Pending"
            applied_str = time.strftime("%Y-%m-%d %H:%M:%S", time.localtime(s["applied_at"])) if s["applied_at"] else "-"
            print(f"{s['version']:<35} {st:<12} {applied_str}")
    else:
        applied = run_migrations(db=args.db)
        if applied:
            print(f"Successfully applied {len(applied)} migration(s):")
            for m in applied:
                print(f"  ✓ {m}")
        else:
            print("Database is up to date (no pending migrations).")


if __name__ == "__main__":
    main()
