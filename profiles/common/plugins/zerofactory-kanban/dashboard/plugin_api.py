"""Zero Factory Kanban — Backend API Routes & Durable SQLite Layer.

Mounted at /api/plugins/zerofactory-kanban/ in the Hermes Dashboard.
Provides a durable, rock-solid, multi-board task management engine specifically
crafted for Zero Factory multi-agent coordination.
"""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import sqlite3
import subprocess
import time
from contextlib import closing, contextmanager
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

_log = logging.getLogger(__name__)

router = APIRouter()

# --- Database Setup & Connection ---------------------------------------------

DEFAULT_DB_PATH = Path.home() / ".hermes" / "zerofactory_kanban.db"

def get_db_path() -> Path:
    override = os.environ.get("ZEROFACTORY_KANBAN_DB")
    if override:
        return Path(override)
    return DEFAULT_DB_PATH

@contextmanager
def get_db_conn():
    db_path = get_db_path()
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), timeout=10.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL;")
    conn.execute("PRAGMA foreign_keys=ON;")
    conn.execute("PRAGMA busy_timeout=5000;")
    try:
        yield conn
    finally:
        conn.close()

def init_db():
    """Idempotently initialize all database tables and seed default board."""
    with get_db_conn() as conn:
        with conn:
            conn.executescript("""
            CREATE TABLE IF NOT EXISTS boards (
                slug TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                description TEXT DEFAULT '',
                git_url TEXT DEFAULT '',
                created_at INTEGER NOT NULL,
                updated_at INTEGER NOT NULL
            );

            CREATE TABLE IF NOT EXISTS tasks (
                id TEXT PRIMARY KEY,
                board_slug TEXT NOT NULL DEFAULT 'default',
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

            CREATE INDEX IF NOT EXISTS idx_tasks_board_status ON tasks(board_slug, status);
            CREATE INDEX IF NOT EXISTS idx_tasks_assignee ON tasks(assignee);
            CREATE INDEX IF NOT EXISTS idx_tasks_status ON tasks(status);
            CREATE INDEX IF NOT EXISTS idx_links_parent ON task_links(parent_id);
            CREATE INDEX IF NOT EXISTS idx_links_child ON task_links(child_id);
            CREATE INDEX IF NOT EXISTS idx_comments_task ON task_comments(task_id, created_at);
            CREATE INDEX IF NOT EXISTS idx_activity_task ON task_activity(task_id, created_at);
            """)

            now = int(time.time())
            cursor = conn.cursor()
            cursor.execute("SELECT 1 FROM boards WHERE slug = 'default'")
            if not cursor.fetchone():
                cursor.execute(
                    "INSERT INTO boards (slug, name, description, git_url, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
                    ("default", "Default Board", "Primary Zero Factory development board", "", now, now)
                )

# Initialize on import
try:
    init_db()
except Exception as e:
    _log.error("Failed to initialize Zero Factory Kanban database: %s", e)


# --- Request & Response Models -----------------------------------------------

class BoardCreate(BaseModel):
    slug: str = Field(..., min_length=1, max_length=64, description="Unique URL-friendly slug")
    name: str = Field(..., min_length=1, max_length=128)
    description: Optional[str] = ""
    git_url: Optional[str] = ""

class TaskCreate(BaseModel):
    title: str = Field(..., min_length=1, max_length=256)
    description: Optional[str] = ""
    board_slug: Optional[str] = "default"
    status: Optional[str] = "triage"
    assignee: Optional[str] = "unassigned"
    priority: Optional[str] = "P2"
    workspace_path: Optional[str] = None
    workspace_kind: Optional[str] = "worktree"
    branch_name: Optional[str] = None
    pr_url: Optional[str] = None
    tenant: Optional[str] = ""
    tags: Optional[List[str]] = []
    parent_id: Optional[str] = None

class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    board_slug: Optional[str] = None
    status: Optional[str] = None
    assignee: Optional[str] = None
    priority: Optional[str] = None
    workspace_path: Optional[str] = None
    workspace_kind: Optional[str] = None
    branch_name: Optional[str] = None
    pr_url: Optional[str] = None
    tenant: Optional[str] = None
    tags: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = None

class TaskMove(BaseModel):
    status: str = Field(..., pattern="^(triage|todo|ready|running|blocked|done)$")
    actor: Optional[str] = "user"

class CommentCreate(BaseModel):
    author: str = Field(default="user", max_length=64)
    body: str = Field(..., min_length=1)

class DependencyLink(BaseModel):
    parent_id: str
    child_id: str


# --- Helper Functions --------------------------------------------------------

VALID_STATUSES = {"triage", "todo", "ready", "running", "blocked", "done"}
VALID_PRIORITIES = {"P0", "P1", "P2", "P3"}
VALID_ASSIGNEES = {"unassigned", "orchestrator", "builder", "reviewer"}

def generate_task_id() -> str:
    token = secrets.token_hex(4)
    return f"zf-{token}"

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

def log_activity(conn: sqlite3.Connection, task_id: str, actor: str, action: str, details: str = ""):
    now = int(time.time())
    conn.execute(
        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, ?, ?, ?, ?)",
        (task_id, actor, action, details, now)
    )


# --- Board Endpoints ---------------------------------------------------------

@router.get("/boards")
def list_boards():
    """List all Kanban boards."""
    init_db()
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM boards ORDER BY created_at ASC")
        boards = [dict(row) for row in cursor.fetchall()]

        # Attach task counts per board
        for b in boards:
            cursor.execute("SELECT COUNT(*) as count FROM tasks WHERE board_slug = ?", (b["slug"],))
            b["task_count"] = cursor.fetchone()["count"]
            cursor.execute("SELECT COUNT(*) as count FROM tasks WHERE board_slug = ? AND status = 'running'", (b["slug"],))
            b["running_count"] = cursor.fetchone()["count"]
        return {"ok": True, "boards": boards}

@router.post("/boards")
def create_board(req: BoardCreate):
    """Create a new board / project."""
    init_db()
    now = int(time.time())
    slug = re.sub(r"[^a-zA-Z0-9_\-]", "", req.slug.lower().strip())
    if not slug:
        raise HTTPException(status_code=400, detail="Invalid board slug")

    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT slug FROM boards WHERE slug = ?", (slug,))
        if cursor.fetchone():
            raise HTTPException(status_code=409, detail=f"Board '{slug}' already exists")

        cursor.execute(
            "INSERT INTO boards (slug, name, description, git_url, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?)",
            (slug, req.name.strip(), req.description.strip(), req.git_url.strip(), now, now)
        )
        conn.commit()
    return {"ok": True, "slug": slug}

@router.delete("/boards/{slug}")
def delete_board(slug: str):
    """Delete a board and its associated tasks."""
    if slug == "default":
        raise HTTPException(status_code=400, detail="Cannot delete default board")

    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM boards WHERE slug = ?", (slug,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Board '{slug}' not found")
        conn.commit()
    return {"ok": True, "deleted": slug}


# --- Task Endpoints ----------------------------------------------------------

@router.get("/tasks")
def list_tasks(
    board: Optional[str] = Query(None, description="Board slug filter"),
    status: Optional[str] = Query(None, description="Status column filter"),
    assignee: Optional[str] = Query(None, description="Assignee filter"),
    priority: Optional[str] = Query(None, description="Priority filter"),
    search: Optional[str] = Query(None, description="Search term in title or description")
):
    """List tasks with flexible filtering."""
    init_db()

    # Normalize if invoked directly in python with default Query descriptors
    if not isinstance(board, str):
        board = None
    if not isinstance(status, str):
        status = None
    if not isinstance(assignee, str):
        assignee = None
    if not isinstance(priority, str):
        priority = None
    if not isinstance(search, str):
        search = None

    query = "SELECT * FROM tasks WHERE 1=1"
    params: List[Any] = []

    if board:
        query += " AND board_slug = ?"
        params.append(board)
    if status:
        query += " AND status = ?"
        params.append(status)
    if assignee:
        query += " AND assignee = ?"
        params.append(assignee)
    if priority:
        query += " AND priority = ?"
        params.append(priority)
    if search:
        query += " AND (title LIKE ? OR description LIKE ? OR id LIKE ?)"
        s = f"%{search}%"
        params.extend([s, s, s])

    # Prioritize P0 -> P1 -> P2 -> P3 and newest tasks
    query += " ORDER BY CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 WHEN 'P3' THEN 3 ELSE 4 END, created_at DESC"

    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(query, params)
        rows = cursor.fetchall()
        tasks = [row_to_dict(r) for r in rows]

        # Fetch dependency indicators and comment counts in batch
        task_ids = [t["id"] for t in tasks]
        if task_ids:
            placeholders = ",".join("?" for _ in task_ids)
            # Count parents (tasks this task depends on)
            cursor.execute(f"SELECT child_id, COUNT(*) as count FROM task_links WHERE child_id IN ({placeholders}) GROUP BY child_id", task_ids)
            parent_counts = {r["child_id"]: r["count"] for r in cursor.fetchall()}

            # Count uncompleted parents
            cursor.execute(f"""
                SELECT tl.child_id, COUNT(*) as count
                FROM task_links tl
                JOIN tasks pt ON pt.id = tl.parent_id
                WHERE tl.child_id IN ({placeholders}) AND pt.status != 'done'
                GROUP BY tl.child_id
            """, task_ids)
            blocking_counts = {r["child_id"]: r["count"] for r in cursor.fetchall()}

            # Count children (tasks depending on this task)
            cursor.execute(f"SELECT parent_id, COUNT(*) as count FROM task_links WHERE parent_id IN ({placeholders}) GROUP BY parent_id", task_ids)
            child_counts = {r["parent_id"]: r["count"] for r in cursor.fetchall()}

            # Count comments
            cursor.execute(f"SELECT task_id, COUNT(*) as count FROM task_comments WHERE task_id IN ({placeholders}) GROUP BY task_id", task_ids)
            comment_counts = {r["task_id"]: r["count"] for r in cursor.fetchall()}

            for t in tasks:
                t_id = t["id"]
                t["parent_count"] = parent_counts.get(t_id, 0)
                t["blocking_parent_count"] = blocking_counts.get(t_id, 0)
                t["child_count"] = child_counts.get(t_id, 0)
                t["comment_count"] = comment_counts.get(t_id, 0)

        return {"ok": True, "tasks": tasks, "count": len(tasks)}

@router.post("/tasks")
def create_task(req: TaskCreate):
    """Create a new task."""
    init_db()
    now = int(time.time())
    task_id = generate_task_id()

    # Normalize fields
    status_val = req.status if req.status in VALID_STATUSES else "triage"
    priority_val = req.priority if req.priority in VALID_PRIORITIES else "P2"
    assignee_val = req.assignee if req.assignee in VALID_ASSIGNEES else "unassigned"
    board_slug = req.board_slug or "default"
    tags_json = json.dumps(req.tags or [])
    metadata_json = "{}"

    # Auto-infer branch name if not provided
    branch_name = req.branch_name or f"task/{task_id}"

    with get_db_conn() as conn:
        cursor = conn.cursor()
        # Verify board exists
        cursor.execute("SELECT slug FROM boards WHERE slug = ?", (board_slug,))
        if not cursor.fetchone():
            board_slug = "default"

        cursor.execute("""
            INSERT INTO tasks (
                id, board_slug, title, description, status, assignee, priority,
                workspace_path, workspace_kind, branch_name, pr_url, tenant,
                tags, metadata, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            task_id, board_slug, req.title.strip(), req.description or "", status_val,
            assignee_val, priority_val, req.workspace_path, req.workspace_kind or "worktree",
            branch_name, req.pr_url, req.tenant or "", tags_json, metadata_json, now, now
        ))

        if req.parent_id:
            cursor.execute("SELECT id FROM tasks WHERE id = ?", (req.parent_id,))
            if cursor.fetchone():
                cursor.execute(
                    "INSERT OR IGNORE INTO task_links (parent_id, child_id, created_at) VALUES (?, ?, ?)",
                    (req.parent_id, task_id, now)
                )

        log_activity(conn, task_id, "user", "create", f"Task created in {status_val}")
        conn.commit()

    return {"ok": True, "id": task_id}

@router.get("/tasks/{task_id}")
def get_task(task_id: str):
    """Get full task details including dependencies, comments, and activity."""
    init_db()
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM tasks WHERE id = ?", (task_id,))
        task_row = cursor.fetchone()
        if not task_row:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

        task = row_to_dict(task_row)

        # Fetch parent tasks (dependencies)
        cursor.execute("""
            SELECT t.id, t.title, t.status, t.assignee, t.priority
            FROM task_links tl
            JOIN tasks t ON t.id = tl.parent_id
            WHERE tl.child_id = ?
        """, (task_id,))
        task["parents"] = [dict(r) for r in cursor.fetchall()]

        # Fetch child tasks
        cursor.execute("""
            SELECT t.id, t.title, t.status, t.assignee, t.priority
            FROM task_links tl
            JOIN tasks t ON t.id = tl.child_id
            WHERE tl.parent_id = ?
        """, (task_id,))
        task["children"] = [dict(r) for r in cursor.fetchall()]

        # Fetch comments
        cursor.execute("SELECT * FROM task_comments WHERE task_id = ? ORDER BY created_at ASC", (task_id,))
        task["comments"] = [dict(r) for r in cursor.fetchall()]

        # Fetch activity
        cursor.execute("SELECT * FROM task_activity WHERE task_id = ? ORDER BY created_at DESC LIMIT 50", (task_id,))
        task["activity"] = [dict(r) for r in cursor.fetchall()]

        return {"ok": True, "task": task}

@router.patch("/tasks/{task_id}")
def update_task(task_id: str, req: TaskUpdate):
    """Update task fields."""
    init_db()
    now = int(time.time())
    updates: List[str] = []
    params: List[Any] = []
    changes: List[str] = []

    if req.title is not None:
        updates.append("title = ?")
        params.append(req.title.strip())
        changes.append("title updated")
    if req.description is not None:
        updates.append("description = ?")
        params.append(req.description)
        changes.append("description updated")
    if req.board_slug is not None:
        updates.append("board_slug = ?")
        params.append(req.board_slug)
        changes.append(f"moved to board {req.board_slug}")
    if req.status is not None:
        if req.status not in VALID_STATUSES:
            raise HTTPException(status_code=400, detail=f"Invalid status: {req.status}")
        updates.append("status = ?")
        params.append(req.status)
        changes.append(f"status changed to {req.status}")
    if req.assignee is not None:
        updates.append("assignee = ?")
        params.append(req.assignee)
        changes.append(f"assignee changed to {req.assignee}")
    if req.priority is not None:
        if req.priority not in VALID_PRIORITIES:
            raise HTTPException(status_code=400, detail=f"Invalid priority: {req.priority}")
        updates.append("priority = ?")
        params.append(req.priority)
        changes.append(f"priority changed to {req.priority}")
    if req.workspace_path is not None:
        updates.append("workspace_path = ?")
        params.append(req.workspace_path)
    if req.workspace_kind is not None:
        updates.append("workspace_kind = ?")
        params.append(req.workspace_kind)
    if req.branch_name is not None:
        updates.append("branch_name = ?")
        params.append(req.branch_name)
    if req.pr_url is not None:
        updates.append("pr_url = ?")
        params.append(req.pr_url)
    if req.tenant is not None:
        updates.append("tenant = ?")
        params.append(req.tenant)
    if req.tags is not None:
        updates.append("tags = ?")
        params.append(json.dumps(req.tags))
    if req.metadata is not None:
        updates.append("metadata = ?")
        params.append(json.dumps(req.metadata))

    if not updates:
        return {"ok": True, "message": "No changes requested"}

    updates.append("updated_at = ?")
    params.append(now)
    params.append(task_id)

    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(f"UPDATE tasks SET {', '.join(updates)} WHERE id = ?", params)
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

        log_activity(conn, task_id, "user", "update", "; ".join(changes))
        conn.commit()

    return {"ok": True, "id": task_id}

@router.post("/tasks/{task_id}/move")
def move_task(task_id: str, req: TaskMove):
    """Move a task to another status / column (e.g. via Drag and Drop)."""
    init_db()
    if req.status not in VALID_STATUSES:
        raise HTTPException(status_code=400, detail=f"Invalid status: {req.status}")

    now = int(time.time())
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT status FROM tasks WHERE id = ?", (task_id,))
        curr = cursor.fetchone()
        if not curr:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

        prev_status = curr["status"]
        if prev_status != req.status:
            cursor.execute("UPDATE tasks SET status = ?, updated_at = ? WHERE id = ?", (req.status, now, task_id))
            log_activity(conn, task_id, req.actor or "user", "move", f"Moved from {prev_status} to {req.status}")
            conn.commit()

    return {"ok": True, "id": task_id, "status": req.status, "prev_status": prev_status}

@router.delete("/tasks/{task_id}")
def delete_task(task_id: str):
    """Delete a task and all associated comments, links, and activity."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")
        conn.commit()
    return {"ok": True, "deleted": task_id}


# --- Comments & Dependencies Endpoints ---------------------------------------

@router.get("/tasks/{task_id}/comments")
def get_comments(task_id: str):
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM task_comments WHERE task_id = ? ORDER BY created_at ASC", (task_id,))
        return {"ok": True, "comments": [dict(r) for r in cursor.fetchall()]}

@router.post("/tasks/{task_id}/comments")
def add_comment(task_id: str, req: CommentCreate):
    now = int(time.time())
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM tasks WHERE id = ?", (task_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Task '{task_id}' not found")

        cursor.execute(
            "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, ?, ?, ?)",
            (task_id, req.author, req.body.strip(), now)
        )
        comment_id = cursor.lastrowid
        log_activity(conn, task_id, req.author, "comment", f"Added comment #{comment_id}")
        conn.commit()

    return {"ok": True, "id": comment_id}

@router.post("/tasks/{task_id}/dependencies")
def add_dependency(task_id: str, link: DependencyLink):
    """Add a dependency link between parent and child."""
    now = int(time.time())
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id FROM tasks WHERE id = ?", (link.parent_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Parent task '{link.parent_id}' not found")
        cursor.execute("SELECT id FROM tasks WHERE id = ?", (link.child_id,))
        if not cursor.fetchone():
            raise HTTPException(status_code=404, detail=f"Child task '{link.child_id}' not found")

        if link.parent_id == link.child_id:
            raise HTTPException(status_code=400, detail="Task cannot depend on itself")

        cursor.execute(
            "INSERT OR IGNORE INTO task_links (parent_id, child_id, created_at) VALUES (?, ?, ?)",
            (link.parent_id, link.child_id, now)
        )
        log_activity(conn, link.child_id, "user", "link", f"Added parent dependency #{link.parent_id}")
        conn.commit()

    return {"ok": True, "parent_id": link.parent_id, "child_id": link.child_id}

@router.delete("/tasks/{task_id}/dependencies/{parent_id}")
def remove_dependency(task_id: str, parent_id: str):
    """Remove a dependency link."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM task_links WHERE parent_id = ? AND child_id = ?", (parent_id, task_id))
        log_activity(conn, task_id, "user", "unlink", f"Removed parent dependency #{parent_id}")
        conn.commit()
    return {"ok": True, "removed": f"{parent_id} -> {task_id}"}


# --- Metrics & Stats ---------------------------------------------------------

@router.get("/stats")
def get_stats(board: Optional[str] = None):
    """Get board metrics and task distribution."""
    init_db()
    with get_db_conn() as conn:
        cursor = conn.cursor()
        base_filter = " WHERE 1=1"
        params: List[Any] = []
        if board:
            base_filter += " AND board_slug = ?"
            params.append(board)

        # Status breakdown
        cursor.execute(f"SELECT status, COUNT(*) as count FROM tasks{base_filter} GROUP BY status", params)
        status_counts = {r["status"]: r["count"] for r in cursor.fetchall()}

        # Priority breakdown
        cursor.execute(f"SELECT priority, COUNT(*) as count FROM tasks{base_filter} GROUP BY priority", params)
        priority_counts = {r["priority"]: r["count"] for r in cursor.fetchall()}

        # Assignee breakdown
        cursor.execute(f"SELECT assignee, COUNT(*) as count FROM tasks{base_filter} GROUP BY assignee", params)
        assignee_counts = {r["assignee"]: r["count"] for r in cursor.fetchall()}

        # Total tasks
        cursor.execute(f"SELECT COUNT(*) as count FROM tasks{base_filter}", params)
        total_tasks = cursor.fetchone()["count"]

        # Active worktrees count
        cursor.execute(f"SELECT COUNT(*) as count FROM tasks{base_filter} AND workspace_path IS NOT NULL AND status IN ('ready', 'running')", params)
        active_worktrees = cursor.fetchone()["count"]

        return {
            "ok": True,
            "total": total_tasks,
            "columns": {
                "triage": status_counts.get("triage", 0),
                "todo": status_counts.get("todo", 0),
                "ready": status_counts.get("ready", 0),
                "running": status_counts.get("running", 0),
                "blocked": status_counts.get("blocked", 0),
                "done": status_counts.get("done", 0),
            },
            "priorities": priority_counts,
            "assignees": assignee_counts,
            "active_worktrees": active_worktrees
        }


# --- Dispatcher Controls -----------------------------------------------------

@router.post("/dispatch/run")
def trigger_dispatch():
    """Trigger atomic dependency unblocking, WIP promotion, worktree setup, and PR review routing."""
    try:
        from ..dispatcher import run_dispatch_cycle
    except Exception:
        import sys
        parent_dir = str(Path(__file__).parent.parent)
        if parent_dir not in sys.path:
            sys.path.insert(0, parent_dir)
        from dispatcher import run_dispatch_cycle  # type: ignore

    return run_dispatch_cycle(get_db_path())


@router.get("/dispatch/status")
def get_dispatch_status():
    """Get active worktree directories and dispatcher status."""
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("""
            SELECT id, title, assignee, status, workspace_path, branch_name, pr_url, updated_at
            FROM tasks
            WHERE status IN ('ready', 'running', 'blocked')
            ORDER BY updated_at DESC
        """)
        in_flight = [dict(r) for r in cursor.fetchall()]
        return {"ok": True, "in_flight": in_flight, "count": len(in_flight)}


# --- Legacy Migration Tool ---------------------------------------------------

@router.post("/import-legacy")
def import_legacy():
    """Import tasks from legacy ~/.hermes/kanban.db into Zero Factory Kanban."""
    legacy_db = Path.home() / ".hermes" / "kanban.db"
    if not legacy_db.exists():
        return {"ok": False, "message": "Legacy database ~/.hermes/kanban.db does not exist."}

    imported_tasks = 0
    imported_links = 0
    imported_comments = 0

    try:
        with sqlite3.connect(f"file:{legacy_db.resolve()}?mode=ro", uri=True, timeout=5.0) as leg_conn:
            leg_conn.row_factory = sqlite3.Row
            leg_cur = leg_conn.cursor()

            # Read tasks
            leg_cur.execute("SELECT * FROM tasks")
            legacy_tasks = leg_cur.fetchall()

            # Read links
            leg_cur.execute("SELECT * FROM task_links")
            legacy_links = leg_cur.fetchall()

            # Read comments
            leg_cur.execute("SELECT * FROM task_comments")
            legacy_comments = leg_cur.fetchall()

        now = int(time.time())
        with get_db_conn() as conn:
            cursor = conn.cursor()
            for t in legacy_tasks:
                keys = t.keys()
                t_id = t["id"]
                cursor.execute("SELECT 1 FROM tasks WHERE id = ?", (t_id,))
                if cursor.fetchone():
                    continue  # Already exists

                # Map priority
                raw_prio = t["priority"] if "priority" in keys else 1
                prio_str = "P2"
                if isinstance(raw_prio, int):
                    if raw_prio >= 3:
                        prio_str = "P0"
                    elif raw_prio == 2:
                        prio_str = "P1"
                    elif raw_prio == 1:
                        prio_str = "P2"
                    else:
                        prio_str = "P3"

                raw_status = t["status"] if "status" in keys else "triage"
                status_val = raw_status if raw_status in VALID_STATUSES else "triage"

                raw_asgn = t["assignee"] if "assignee" in keys else "unassigned"
                assignee_val = raw_asgn if raw_asgn in VALID_ASSIGNEES else "unassigned"

                desc_val = (t["description"] if "description" in keys else None) or (t["body"] if "body" in keys else None) or ""

                cursor.execute("""
                    INSERT OR IGNORE INTO tasks (
                        id, board_slug, title, description, status, assignee, priority,
                        workspace_path, workspace_kind, branch_name, pr_url, tenant,
                        skills, tags, metadata, created_at, updated_at
                    ) VALUES (?, 'default', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '[]', '[]', '{}', ?, ?)
                """, (
                    t_id,
                    (t["title"] if "title" in keys else None) or "Untitled Task",
                    desc_val,
                    status_val,
                    assignee_val,
                    prio_str,
                    t["workspace_path"] if "workspace_path" in keys else None,
                    t["workspace_kind"] if "workspace_kind" in keys else "worktree",
                    f"task/{t_id}",
                    None,
                    t["tenant"] if "tenant" in keys and t["tenant"] else "",
                    t["created_at"] if "created_at" in keys and t["created_at"] else now,
                    t["updated_at"] if "updated_at" in keys and t["updated_at"] else now
                ))
                imported_tasks += 1

            for l in legacy_links:
                cursor.execute(
                    "INSERT OR IGNORE INTO task_links (parent_id, child_id, created_at) VALUES (?, ?, ?)",
                    (l["parent_id"], l["child_id"], now)
                )
                imported_links += 1

            for c in legacy_comments:
                cursor.execute(
                    "INSERT OR IGNORE INTO task_comments (task_id, author, body, created_at) VALUES (?, ?, ?, ?)",
                    (c["task_id"], c["author"] or "agent", c["body"] or "", c["created_at"] if "created_at" in c.keys() and c["created_at"] else now)
                )
                imported_comments += 1

            conn.commit()

        return {
            "ok": True,
            "imported_tasks": imported_tasks,
            "imported_links": imported_links,
            "imported_comments": imported_comments,
            "message": f"Successfully imported {imported_tasks} tasks from legacy Kanban."
        }
    except Exception as e:
        _log.error("Failed to import legacy kanban tasks: %s", e)
        return {"ok": False, "error": str(e)}
