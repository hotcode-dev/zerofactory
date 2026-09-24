"""Zero Factory Dashboard — Memory extraction, deduplication, and recording service."""

from __future__ import annotations

import json
import logging
import re
import secrets
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

_PLUGIN_ROOT = str(Path(__file__).resolve().parent.parent)
if _PLUGIN_ROOT not in sys.path:
    sys.path.insert(0, _PLUGIN_ROOT)
_DASHBOARD_ROOT = str(Path(__file__).resolve().parent)
if _DASHBOARD_ROOT not in sys.path:
    sys.path.insert(0, _DASHBOARD_ROOT)

try:
    from ..settings import load_settings  # type: ignore
except (ImportError, ValueError):
    from settings import load_settings  # type: ignore

try:
    from .db import log_activity
except (ImportError, ValueError):
    from db import log_activity  # type: ignore

_log = logging.getLogger(__name__)

AUTO_MEMORY_PREFIX_REGEX = re.compile(
    r"(?:^|\n|[\s\.\;\,\:\-\(\)\[\]])(?:\*{1,2})?(GOTCHA|RULE|CONVENTION|GUIDELINE|DECISION|ARCH|REJECTED_PATH|REJECTED PATH|REJECTED|LESSON|LEARNING|TIP)(?:\*{1,2})?:\s*(?:\*{1,2})?([^\n\r]+)",
    re.IGNORECASE
)


def normalize_memory_content(content: str) -> str:
    """Normalize memory content for deduplication comparisons."""
    text = str(content).strip().strip("`*\"'")
    text = re.sub(r"\s+", " ", text).strip()
    return text.casefold()


def normalize_file_path(path_str: str) -> str:
    """Normalize file path for consistent deduplication comparisons."""
    p = str(path_str).strip().replace("\\", "/")
    p = re.sub(r"^\./+", "", p)
    return p.lstrip("/").lower()


def compute_dedup_key(files: Optional[List[str]], category: Optional[str] = None) -> Optional[str]:
    """Generate a deterministic fingerprint from a sorted list of affected files and category."""
    if not files:
        return None
    cleaned = []
    for f in files:
        if isinstance(f, str):
            for part in f.split(","):
                norm = normalize_file_path(part)
                if norm:
                    cleaned.append(norm)
    if not cleaned:
        return None
    sorted_files = sorted(set(cleaned))
    cat = (category or "bug-fix").strip().lower()
    return f"{','.join(sorted_files)}:{cat}"


def extract_and_record_memory(
    conn: sqlite3.Connection,
    board_slug: str,
    text: str,
    task_id: Optional[str] = None,
    author: str = "zf-reviewer",
) -> List[Dict[str, Any]]:
    """Extract structured rules/gotchas from reviewer feedback and auto-record to board_memories if enabled."""
    if not text or not board_slug:
        return []

    settings = load_settings(conn)
    if not settings.get("auto_record_memory", True):
        return []

    try:
        b_row = conn.execute("SELECT auto_record_memory FROM boards WHERE slug = ?", (board_slug,)).fetchone()
        if b_row:
            arm_val = b_row["auto_record_memory"] if "auto_record_memory" in b_row.keys() else b_row[0]
            if arm_val is not None and not bool(arm_val):
                return []
    except Exception:
        pass

    category_map = {
        "gotcha": "gotcha",
        "rule": "gotcha",
        "lesson": "gotcha",
        "learning": "gotcha",
        "tip": "convention",
        "convention": "convention",
        "guideline": "convention",
        "decision": "decision",
        "arch": "decision",
        "rejected_path": "rejected_path",
        "rejected path": "rejected_path",
        "rejected": "rejected_path",
    }

    recorded = []
    now = int(time.time())

    for match in AUTO_MEMORY_PREFIX_REGEX.finditer(text):
        raw_prefix = match.group(1).lower().strip()
        raw_content = match.group(2).strip()

        clean_content = raw_content.strip("`*\"' ")
        if len(clean_content) < 5 or len(clean_content) > 1000:
            continue

        cat = category_map.get(raw_prefix, "gotcha")

        dedup_key = normalize_memory_content(clean_content)
        exact_row = conn.execute(
            "SELECT id FROM board_memories WHERE board_slug = ? AND content = ?",
            (board_slug, clean_content)
        ).fetchone()
        if exact_row:
            continue
        rows = conn.execute(
            "SELECT content FROM board_memories WHERE board_slug = ?",
            (board_slug,)
        ).fetchall()
        if any(normalize_memory_content(r["content"]) == dedup_key for r in rows):
            continue

        mem_id = f"mem-{secrets.token_hex(4)}"
        tags = ["auto-recorded", f"from-{author}"]
        tags_json = json.dumps(tags)

        conn.execute(
            """
            INSERT INTO board_memories (id, board_slug, task_id, category, content, tags, author, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (mem_id, board_slug, task_id, cat, clean_content, tags_json, author, now, now)
        )

        if task_id:
            try:
                log_activity(conn, task_id, author, "auto_memory_recorded", f"Auto-recorded {cat}: {clean_content[:80]}")
            except Exception:
                pass

        recorded.append({
            "id": mem_id,
            "board_slug": board_slug,
            "task_id": task_id,
            "category": cat,
            "content": clean_content,
            "tags": tags,
            "author": author,
            "created_at": now,
            "updated_at": now
        })

    return recorded
