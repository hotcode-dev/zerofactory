"""Zero Factory Dashboard — Board Memories routes (/boards/{slug}/memories, /memories/{id})."""

from __future__ import annotations

import json
import logging
import secrets
import sys
import time
from pathlib import Path
from typing import Any, List, Optional

_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)
_DASHBOARD_ROOT = str(Path(__file__).resolve().parent.parent)
if _DASHBOARD_ROOT not in sys.path:
    sys.path.insert(0, _DASHBOARD_ROOT)

from fastapi import APIRouter, HTTPException

try:
    from ..db import get_db_conn, init_db
    from ..models import VALID_MEMORY_CATEGORIES, MemoryCreate, MemoryUpdate
except (ImportError, ValueError):
    from db import get_db_conn, init_db  # type: ignore
    from models import VALID_MEMORY_CATEGORIES, MemoryCreate, MemoryUpdate  # type: ignore

_log = logging.getLogger(__name__)

router = APIRouter()


@router.get("/memories")
@router.get("/boards/{slug}/memories")
def list_board_memories(
    slug: str = "all",
    category: Optional[str] = None,
    q: Optional[str] = None,
    limit: int = 50,
    offset: int = 0
):
    """List repository memories, conventions, and gotchas for a board."""
    init_db()
    with get_db_conn() as conn:
        cursor = conn.cursor()
        if slug != "all":
            cursor.execute("SELECT slug FROM boards WHERE slug = ?", (slug,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"Board '{slug}' not found")

        if slug == "all":
            query = "SELECT id, board_slug, task_id, category, content, tags, author, created_at, updated_at FROM board_memories WHERE 1=1"
            params: List[Any] = []
        else:
            query = "SELECT id, board_slug, task_id, category, content, tags, author, created_at, updated_at FROM board_memories WHERE board_slug = ?"
            params: List[Any] = [slug]

        if category and category != "all":
            query += " AND category = ?"
            params.append(category)

        if q and q.strip():
            query += " AND (content LIKE ? OR tags LIKE ?)"
            params.extend([f"%{q.strip()}%", f"%{q.strip()}%"])

        count_query = query.replace("SELECT id, board_slug, task_id, category, content, tags, author, created_at, updated_at", "SELECT COUNT(*)")
        cursor.execute(count_query, params)
        total = cursor.fetchone()[0]

        query += " ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params.extend([max(1, min(limit, 200)), max(0, offset)])
        cursor.execute(query, params)
        rows = cursor.fetchall()

        memories = []
        for r in rows:
            tags = []
            try:
                tags = json.loads(r[5] or "[]")
            except Exception:
                pass
            memories.append({
                "id": r[0],
                "board_slug": r[1],
                "task_id": r[2],
                "category": r[3],
                "content": r[4],
                "tags": tags,
                "author": r[6],
                "created_at": r[7],
                "updated_at": r[8],
            })

        return {"ok": True, "board_slug": slug, "total": total, "memories": memories}


@router.post("/boards/{slug}/memories")
def create_board_memory(slug: str, req: MemoryCreate):
    """Record a new memory, decision, convention, or gotcha for a board."""
    init_db()
    cat = (req.category or "general").strip().lower()
    if cat not in VALID_MEMORY_CATEGORIES:
        cat = "general"

    stripped_content = req.content.strip()
    if not stripped_content:
        raise HTTPException(status_code=400, detail="Memory content must not be blank")

    now = int(time.time())
    mem_id = f"mem-{secrets.token_hex(4)}"
    tags_json = json.dumps(req.tags or [])
    author = req.author or "user"

    with get_db_conn() as conn:
        cursor = conn.cursor()
        if slug == "all":
            cursor.execute("SELECT slug FROM boards ORDER BY created_at ASC LIMIT 1")
            row = cursor.fetchone()
            if not row:
                raise HTTPException(status_code=400, detail="No board available to associate memory")
            slug = row[0]
        else:
            cursor.execute("SELECT slug FROM boards WHERE slug = ?", (slug,))
            if not cursor.fetchone():
                raise HTTPException(status_code=404, detail=f"Board '{slug}' not found")

        cursor.execute(
            """
            INSERT INTO board_memories (id, board_slug, task_id, category, content, tags, author, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (mem_id, slug, req.task_id, cat, req.content.strip(), tags_json, author, now, now)
        )
        conn.commit()

    return {
        "ok": True,
        "memory": {
            "id": mem_id,
            "board_slug": slug,
            "task_id": req.task_id,
            "category": cat,
            "content": req.content.strip(),
            "tags": req.tags or [],
            "author": author,
            "created_at": now,
            "updated_at": now
        }
    }


@router.put("/memories/{memory_id}")
def update_board_memory(memory_id: str, req: MemoryUpdate):
    """Update an existing board memory."""
    init_db()
    now = int(time.time())
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT id, board_slug, task_id, category, content, tags, author, created_at, updated_at FROM board_memories WHERE id = ?", (memory_id,))
        row = cursor.fetchone()
        if not row:
            raise HTTPException(status_code=404, detail=f"Memory '{memory_id}' not found")

        updates = []
        params = []
        if req.category is not None:
            cat = req.category.strip().lower()
            if cat in VALID_MEMORY_CATEGORIES:
                updates.append("category = ?")
                params.append(cat)
        if req.content is not None:
            stripped_content = req.content.strip()
            if not stripped_content:
                raise HTTPException(status_code=400, detail="Memory content must not be blank")
            updates.append("content = ?")
            params.append(stripped_content)
        if req.tags is not None:
            updates.append("tags = ?")
            params.append(json.dumps(req.tags))
        if req.author is not None:
            updates.append("author = ?")
            params.append(req.author)
        if req.task_id is not None:
            updates.append("task_id = ?")
            params.append(req.task_id or None)

        if updates:
            updates.append("updated_at = ?")
            params.append(now)
            params.append(memory_id)
            cursor.execute(f"UPDATE board_memories SET {', '.join(updates)} WHERE id = ?", params)
            conn.commit()

        cursor.execute("SELECT id, board_slug, task_id, category, content, tags, author, created_at, updated_at FROM board_memories WHERE id = ?", (memory_id,))
        r = cursor.fetchone()
        tags = []
        try:
            tags = json.loads(r[5] or "[]")
        except Exception:
            pass

        return {
            "ok": True,
            "memory": {
                "id": r[0],
                "board_slug": r[1],
                "task_id": r[2],
                "category": r[3],
                "content": r[4],
                "tags": tags,
                "author": r[6],
                "created_at": r[7],
                "updated_at": r[8],
            }
        }


@router.delete("/memories/{memory_id}")
def delete_board_memory(memory_id: str):
    """Delete a memory entry."""
    init_db()
    with get_db_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("DELETE FROM board_memories WHERE id = ?", (memory_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail=f"Memory '{memory_id}' not found")
        conn.commit()
    return {"ok": True, "deleted": memory_id}


list_memories = list_board_memories
create_memory = create_board_memory
update_memory = update_board_memory
delete_memory = delete_board_memory
