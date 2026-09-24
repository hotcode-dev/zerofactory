"""Zero Factory Dashboard — Durable SQLite Database & Persistence Layer."""

from __future__ import annotations

import fcntl
import json
import logging
import os
import re
import secrets
import sqlite3
import sys
import tempfile
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

# Ensure zerofactory plugin root is in sys.path for direct module imports
_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)

try:
    from ..settings import (  # type: ignore
        DEFAULT_ACTIVITY_RETENTION_DAYS,
        DEFAULT_SETTING_VALUES,
        load_settings,
    )
except (ImportError, ValueError):
    from settings import (  # type: ignore
        DEFAULT_ACTIVITY_RETENTION_DAYS,
        DEFAULT_SETTING_VALUES,
        load_settings,
    )

_log = logging.getLogger(__name__)

# --- Scanner state file helpers -----------------------------------------------

def _load_scanner_gate_module():
    import importlib.util
    gate_path = Path(__file__).resolve().parent.parent / "scripts" / "zf_scanner_gate.py"
    if not gate_path.is_file():
        return None
    try:
        spec = importlib.util.spec_from_file_location("zf_scanner_gate", gate_path)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception:
        return None

_scanner_gate_mod = _load_scanner_gate_module()


def _mark_scanner_task_created(board_slug: str) -> bool:
    """Atomically flag that a task was created for ``board_slug`` in the shared
    scanner state file (flock-guarded read-modify-write + atomic os.replace).

    Prefer the shared implementation in scripts/zf_scanner_gate.py; fall back
    to an equivalent local implementation if that module is unavailable.
    """
    if not board_slug:
        return False
    if _scanner_gate_mod is not None and hasattr(_scanner_gate_mod, "mark_task_created"):
        return bool(_scanner_gate_mod.mark_task_created(board_slug))

    state_override = os.environ.get("ZEROFACTORY_SCANNER_STATE")
    state_file = Path(state_override) if state_override else (Path.home() / ".hermes" / "scanner_state.json")
    try:
        state_file.parent.mkdir(parents=True, exist_ok=True)
        lock_path = state_file.with_name(state_file.name + ".lock")
        with open(str(lock_path), "a+", encoding="utf-8") as lock_f:
            fcntl.flock(lock_f.fileno(), fcntl.LOCK_EX)
            try:
                data = {}
                if state_file.exists():
                    try:
                        parsed = json.loads(state_file.read_text(encoding="utf-8"))
                        if isinstance(parsed, dict):
                            data = parsed
                    except Exception:
                        data = {}
                board_state = data.setdefault(board_slug, {})
                if isinstance(board_state, dict):
                    board_state["task_created"] = True
                    board_state["scan_attempts"] = 0
                data[board_slug] = board_state
                payload = json.dumps(data, indent=2)
                temp_fd, temp_path = tempfile.mkstemp(
                    dir=str(state_file.parent), prefix="scanner_state_", suffix=".tmp"
                )
                try:
                    with os.fdopen(temp_fd, "w", encoding="utf-8") as f:
                        f.write(payload)
                        f.flush()
                        os.fsync(f.fileno())
                    os.replace(temp_path, str(state_file))
                except BaseException:
                    try:
                        os.unlink(temp_path)
                    except OSError:
                        pass
                    raise
            finally:
                fcntl.flock(lock_f.fileno(), fcntl.LOCK_UN)
        return True
    except Exception:
        return False


# --- Database Setup & Connection ---------------------------------------------

DEFAULT_DB_PATH = Path.home() / ".hermes" / "zerofactory.db"

def get_db_path() -> Path:
    override = os.environ.get("ZEROFACTORY_DB")
    if override:
        return Path(override)
    return DEFAULT_DB_PATH


@contextmanager
def get_db_conn():
    # If get_db_conn is mocked on dashboard.plugin_api, defer to that mock
    disp = sys.modules.get("dashboard.plugin_api") or sys.modules.get("plugin_api")
    if disp is not None:
        target = getattr(disp, "get_db_conn", None)
        if target is not None and target is not get_db_conn:
            with target() as c:
                yield c
            return

    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")
    try:
        yield conn
    finally:
        conn.close()


# Paths already initialized by init_db() in this process. Keyed by the resolved
# DB path (not a bare boolean) so that a later change of ZEROFACTORY_DB to a
# different file still triggers initialization/migration for that new path.
_DB_INITIALIZED_PATHS: set = set()

# Maximum interval between retention prunes when driven by per-request init_db().
ACTIVITY_PRUNE_INTERVAL_SECONDS = 3600


def prune_old_activity(
    conn: Optional[sqlite3.Connection] = None,
    retention_days: Optional[int] = None,
    vacuum: bool = True,
) -> int:
    """Delete ``task_activity`` rows older than the retention window."""
    _close = False
    if conn is None:
        db_path = get_db_path()
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA busy_timeout=5000;")
        _close = True
    deleted = 0
    try:
        if retention_days is not None:
            days = retention_days
        else:
            try:
                days = load_settings(conn).get(
                    "activity_retention_days", DEFAULT_ACTIVITY_RETENTION_DAYS
                )
            except Exception:
                days = DEFAULT_ACTIVITY_RETENTION_DAYS
        try:
            days = int(days)
        except (TypeError, ValueError):
            days = DEFAULT_ACTIVITY_RETENTION_DAYS
        if days <= 0:
            return 0  # retention disabled
        cutoff = int(time.time()) - days * 86400
        cur = conn.execute("DELETE FROM task_activity WHERE created_at < ?", (cutoff,))
        deleted = cur.rowcount if cur.rowcount is not None else 0
    finally:
        if _close:
            try:
                conn.commit()
            except Exception:
                pass
            if vacuum and deleted > 0:
                try:
                    conn.execute("VACUUM")
                except Exception as _vac_err:
                    _log.debug("post-prune VACUUM skipped: %s", _vac_err)
            conn.close()
    return deleted


def init_db(force: bool = False):
    """Idempotently initialize all database tables for the current DB path."""
    global _DB_INITIALIZED_PATHS
    db_path = get_db_path()
    if not force and db_path in _DB_INITIALIZED_PATHS:
        return
    with get_db_conn() as conn:
        try:
            conn.execute("PRAGMA journal_mode=WAL;")
        except Exception:
            pass
        with conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS boards (
                slug TEXT PRIMARY KEY,
                description TEXT DEFAULT '',
                git_url TEXT DEFAULT '',
                max_concurrent_running INTEGER NOT NULL DEFAULT 1,
                auto_record_memory INTEGER NOT NULL DEFAULT 1,
                additional_reviewer_usernames TEXT NOT NULL DEFAULT '[]',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                board_slug TEXT NOT NULL DEFAULT '',
                title TEXT NOT NULL,
                description TEXT DEFAULT '',
                status TEXT NOT NULL DEFAULT 'triage',
                assignee TEXT NOT NULL DEFAULT 'unassigned',
                priority TEXT NOT NULL DEFAULT 'P2',
                workspace_path TEXT,
                workspace_kind TEXT DEFAULT 'worktree',
                branch_name TEXT,
                pr_url TEXT,
                tenant TEXT DEFAULT '',
                skills TEXT DEFAULT '[]',
                tags TEXT DEFAULT '[]',
                metadata TEXT DEFAULT '{}',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (board_slug) REFERENCES boards(slug) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS task_links (
                parent_id TEXT NOT NULL,
                child_id TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                PRIMARY KEY (parent_id, child_id),
                FOREIGN KEY (parent_id) REFERENCES tasks(id) ON DELETE CASCADE,
                FOREIGN KEY (child_id) REFERENCES tasks(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS task_comments (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                author TEXT NOT NULL,
                body TEXT NOT NULL,
                created_at INTEGER NOT NULL,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS task_activity (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                task_id TEXT NOT NULL,
                actor TEXT NOT NULL,
                action TEXT NOT NULL,
                details TEXT DEFAULT '',
                created_at INTEGER NOT NULL,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE CASCADE
            );

            CREATE TABLE IF NOT EXISTS settings (
                key TEXT PRIMARY KEY,
                value TEXT NOT NULL,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS board_memories (
                id TEXT PRIMARY KEY,
                board_slug TEXT NOT NULL,
                task_id TEXT,
                category TEXT NOT NULL DEFAULT 'general',
                content TEXT NOT NULL,
                tags TEXT DEFAULT '[]',
                author TEXT DEFAULT 'agent',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL,
                FOREIGN KEY (board_slug) REFERENCES boards(slug) ON DELETE CASCADE,
                FOREIGN KEY (task_id) REFERENCES tasks(id) ON DELETE SET NULL
            );

            CREATE INDEX IF NOT EXISTS idx_tasks_board_status ON tasks(board_slug, status);
            CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_links_parent ON task_links(parent_id);
            CREATE INDEX IF NOT EXISTS idx_links_child ON task_links(child_id);
            CREATE INDEX IF NOT EXISTS idx_comments_task ON task_comments(task_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_activity_task ON task_activity(task_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_memories_board ON board_memories(board_slug, created_at);
            CREATE INDEX IF NOT EXISTS idx_memories_category ON board_memories(category);
            CREATE INDEX IF NOT EXISTS idx_memories_board_content ON board_memories(board_slug, content);
            CREATE INDEX IF NOT EXISTS idx_activity_created ON task_activity(created_at, id);
            CREATE INDEX IF NOT EXISTS idx_activity_actor ON task_activity(actor, created_at);
            """)

            # Idempotent migration: add board settings to pre-existing boards tables.
            cols = [r[1] for r in conn.execute("PRAGMA table_info(boards)").fetchall()]
            if "max_concurrent_running" not in cols:
                conn.execute(
                    "ALTER TABLE boards ADD COLUMN max_concurrent_running INTEGER NOT NULL DEFAULT 1"
                )
            if "auto_record_memory" not in cols:
                conn.execute(
                    "ALTER TABLE boards ADD COLUMN auto_record_memory INTEGER NOT NULL DEFAULT 1"
                )
            if "additional_reviewer_usernames" not in cols:
                conn.execute(
                    "ALTER TABLE boards ADD COLUMN additional_reviewer_usernames TEXT NOT NULL DEFAULT '[]'"
                )

            # Seed default global settings if missing
            now_ts = int(time.time())
            for _key, _value in DEFAULT_SETTING_VALUES.items():
                conn.execute(
                    "INSERT OR IGNORE INTO settings (key, value, updated_at) VALUES (?, ?, ?)",
                    (_key, _value, now_ts)
                )

            # Retention prune throttled to at most once per hour
            try:
                _last_prune_row = conn.execute(
                    "SELECT value FROM settings WHERE key = 'activity_last_prune'"
                ).fetchone()
                if _last_prune_row is None or (
                    now_ts - int(_last_prune_row[0])
                ) >= ACTIVITY_PRUNE_INTERVAL_SECONDS:
                    _deleted = prune_old_activity(conn=conn)
                    conn.execute(
                        "INSERT OR REPLACE INTO settings (key, value, updated_at) "
                        "VALUES ('activity_last_prune', ?, ?)",
                        (str(now_ts), now_ts),
                    )
                    if _deleted:
                        _log.debug("Pruned %d task_activity rows past retention", _deleted)
            except Exception as _prune_err:
                _log.warning("task_activity retention prune skipped: %s", _prune_err)
    _DB_INITIALIZED_PATHS.add(db_path)


def log_activity(conn: sqlite3.Connection, task_id: str, actor: str, action: str, details: str = ""):
    actor = actor or "user"
    now = int(time.time())
    conn.execute(
        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, ?, ?, ?, ?)",
        (task_id, actor, action, details, now)
    )


def row_to_dict(row: sqlite3.Row) -> Dict[str, Any]:
    d = dict(row)
    if "tags" in d and isinstance(d["tags"], str):
        try:
            d["tags"] = json.loads(d["tags"])
        except Exception:
            d["tags"] = []
    if "metadata" in d and isinstance(d["metadata"], str):
        try:
            d["metadata"] = json.loads(d["metadata"])
        except Exception:
            d["metadata"] = {}
    return d


def derive_board_code(board_slug: Optional[str]) -> str:
    """Extract all first characters of the board slug (e.g. ntsd-sdp-compact -> nsc)."""
    if not board_slug:
        return ""
    cleaned = board_slug.strip().lower()
    parts = [p for p in re.split(r"[-_.\s]+", cleaned) if p]
    code = "".join(p[0] for p in parts if p[0].isalnum())
    return code


def generate_task_id(board_slug: Optional[str] = None) -> str:
    token = secrets.token_hex(4)
    code = derive_board_code(board_slug)
    if code:
        return f"zf-{code}-{token}"
    return f"zf-{token}"


def parse_git_url(git_url: str) -> tuple[str, str, str]:
    """Parse remote Git URL into (owner, repo, slug)."""
    if not git_url:
        return "", "", ""
    cleaned = re.sub(r"\.git$", "", git_url.strip().rstrip("/"))
    cleaned = re.sub(r"^[a-zA-Z]+://", "", cleaned)
    if "@" in cleaned:
        cleaned = cleaned.split("@", 1)[1]
        if ":" in cleaned:
            cleaned = cleaned.split(":", 1)[1]
        elif "/" in cleaned:
            cleaned = cleaned.split("/", 1)[1]
    elif "/" in cleaned:
        first_part = cleaned.split("/", 1)[0]
        if "." in first_part or ":" in first_part:
            cleaned = cleaned.split("/", 1)[1]

    parts = [p for p in cleaned.split("/") if p]
    repo = parts[-1] if len(parts) >= 1 else ""
    owner = parts[-2] if len(parts) >= 2 else ""

    repo = re.sub(r"[^a-zA-Z0-9_\-.]", "", repo).strip(".-")
    owner = re.sub(r"[^a-zA-Z0-9_\-.]", "", owner).strip(".-")

    if owner and repo:
        slug = f"{owner}-{repo}".lower()
    elif repo:
        slug = repo.lower()
    else:
        slug = "project"

    slug = re.sub(r"[^a-zA-Z0-9_\-]", "-", slug).strip("-")
    return owner, repo, slug
