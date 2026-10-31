"""Zero Factory Dashboard — Mem0 memory extraction, semantic retrieval, and recording service."""

from __future__ import annotations

import json
import logging
import os
import re
import secrets
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any

# Disable PostHog telemetry in Mem0 to avoid network hangs and extra migration vector stores
os.environ["MEM0_TELEMETRY"] = "false"

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
    from .db import get_db_conn, log_activity
except (ImportError, ValueError):
    from db import get_db_conn, log_activity  # type: ignore

_log = logging.getLogger(__name__)

AUTO_MEMORY_PREFIX_REGEX = re.compile(
    r"(?:^|\n|[\s\.\;\,\:\-\(\)\[\]])(?:\*{1,2})?(GOTCHA|RULE|CONVENTION|GUIDELINE|DECISION|ARCH|REJECTED_PATH|REJECTED PATH|REJECTED|LESSON|LEARNING|TIP)(?:\*{1,2})?:\s*(?:\*{1,2})?([^\n\r]+)",
    re.IGNORECASE,
)

_mem0_client = None
_mem0_client_config = None


def get_mem0_dir() -> Path:
    """Return local directory for Mem0 vector storage and history."""
    base = os.environ.get("ZEROFACTORY_DIR")
    if base:
        p = Path(base) / "mem0"
    else:
        p = Path.home() / ".zerofactory" / "mem0"
    p.mkdir(parents=True, exist_ok=True)
    return p


def get_hermes_model_defaults() -> tuple[str, str, str]:
    """Retrieve default (model, base_url, api_key) inherited from the Hermes agent setup."""
    hermes_model = ""
    hermes_base_url = ""
    try:
        try:
            from profile_manager import get_root_model_config  # type: ignore

            cfg = get_root_model_config()
            m = cfg.get("model", {})
            if isinstance(m, dict):
                hermes_model = m.get("default") or ""
                hermes_base_url = m.get("base_url") or ""
        except Exception:
            pass

        if not hermes_model or not hermes_base_url:
            import yaml

            hermes_cfg_file = Path.home() / ".hermes" / "config.yaml"
            if hermes_cfg_file.exists():
                data = yaml.safe_load(hermes_cfg_file.read_text(encoding="utf-8")) or {}
                m = data.get("model", {})
                if isinstance(m, dict):
                    hermes_model = hermes_model or m.get("default") or ""
                    hermes_base_url = hermes_base_url or m.get("base_url") or ""
    except Exception as e:
        _log.debug("Could not inspect Hermes model config: %s", e)

    model = (
        hermes_model
        or os.environ.get("MEM0_LLM_MODEL")
        or os.environ.get("OPENAI_MODEL")
        or "RadixArk/Qwen3.8-27B-NVFP4"
    )
    base_url = (
        hermes_base_url
        or os.environ.get("MEM0_BASE_URL")
        or os.environ.get("OPENAI_BASE_URL")
        or "https://spark.ntsd.dev:8001/v1"
    )
    api_key = (
        os.environ.get("MEM0_API_KEY")
        or os.environ.get("OPENAI_API_KEY")
        or "dummy-key"
    )
    return model, base_url, api_key


def get_mem0_client(conn: sqlite3.Connection | None = None):
    """Lazily initialize and return the Mem0 Memory instance configured for Zero Factory.

    Returns None if Mem0 is disabled in settings (mem0_enabled is False).
    """
    global _mem0_client, _mem0_client_config

    os.environ["MEM0_TELEMETRY"] = "false"

    settings = {}
    if conn is not None:
        try:
            settings = load_settings(conn)
        except Exception:
            pass
    else:
        try:
            with get_db_conn() as db_conn:
                settings = load_settings(db_conn)
        except Exception:
            pass

    if not settings.get("mem0_enabled", True):
        return None

    def_model, def_base_url, def_api_key = get_hermes_model_defaults()

    api_key = (
        settings.get("mem0_api_key") or os.environ.get("MEM0_API_KEY") or def_api_key
    )
    base_url = (
        settings.get("mem0_base_url") or os.environ.get("MEM0_BASE_URL") or def_base_url
    )
    llm_model = (
        settings.get("mem0_model") or os.environ.get("MEM0_LLM_MODEL") or def_model
    )
    embedder_provider = (
        (
            settings.get("mem0_embedder_provider")
            or os.environ.get("MEM0_EMBEDDER_PROVIDER")
            or "fastembed"
        )
        .strip()
        .lower()
    )

    if embedder_provider == "openai":
        embedder_model = (
            settings.get("mem0_embedder_model")
            or os.environ.get("MEM0_EMBEDDER_MODEL")
            or "text-embedding-3-small"
        )
        embedder_config = {
            "provider": "openai",
            "config": {
                "api_key": api_key,
                "openai_base_url": base_url,
                "model": embedder_model,
            },
        }
        collection_name = "zerofactory_memories_openai"
        dims = 1536
    else:
        embedder_provider = "fastembed"
        embedder_model = (
            settings.get("mem0_embedder_model")
            or os.environ.get("MEM0_EMBEDDER_MODEL")
            or "BAAI/bge-small-en-v1.5"
        )
        embedder_config = {
            "provider": "fastembed",
            "config": {
                "model": embedder_model,
                "embedding_dims": 384,
            },
        }
        collection_name = "zerofactory_memories_fastembed"
        dims = 384

    current_config = (base_url, llm_model, embedder_provider, embedder_model, api_key)
    if _mem0_client is not None and _mem0_client_config == current_config:
        return _mem0_client

    mem0_dir = get_mem0_dir()
    qdrant_path = str(mem0_dir / "qdrant")
    history_db_path = str(mem0_dir / "history.db")

    try:
        from mem0 import Memory

        config = {
            "vector_store": {
                "provider": "qdrant",
                "config": {
                    "path": qdrant_path,
                    "collection_name": collection_name,
                    "embedding_model_dims": dims,
                },
            },
            "llm": {
                "provider": "openai",
                "config": {
                    "api_key": api_key,
                    "openai_base_url": base_url,
                    "model": llm_model,
                },
            },
            "embedder": embedder_config,
            "history_db_path": history_db_path,
        }

        _mem0_client = Memory.from_config(config)
        _mem0_client_config = current_config
        return _mem0_client
    except Exception as e:
        _log.debug("Could not initialize Mem0 client: %s", e)
        return None


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


def compute_dedup_key(
    files: list[str] | None, category: str | None = None
) -> str | None:
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


def mem0_add_memory(
    board_slug: str,
    content: str,
    category: str = "general",
    task_id: str | None = None,
    author: str = "user",
    tags: list[str] | None = None,
    db_conn: sqlite3.Connection | None = None,
) -> str:
    """Store memory in both Mem0 vector store and SQLite board_memories table."""
    mem_id = f"mem-{secrets.token_hex(4)}"
    clean_content = content.strip()
    now = int(time.time())
    tags_list = tags or []
    tags_json = json.dumps(tags_list)

    # 1. Index in Mem0 vector store
    try:
        client = get_mem0_client(db_conn)
        if client:
            client.add(
                clean_content,
                user_id=board_slug,
                metadata={
                    "memory_id": mem_id,
                    "category": category,
                    "task_id": task_id or "",
                    "author": author,
                    "tags": tags_list,
                },
                infer=False,
            )
    except Exception as e:
        _log.debug("Mem0 add failed for board '%s': %s", board_slug, e)

    # 2. Persist to SQLite table for UI rendering and CLI commands
    def _insert_db(conn: sqlite3.Connection):
        conn.execute(
            """
            INSERT INTO board_memories (id, board_slug, task_id, category, content, tags, author, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mem_id,
                board_slug,
                task_id,
                category,
                clean_content,
                tags_json,
                author,
                now,
                now,
            ),
        )

    if db_conn is not None:
        _insert_db(db_conn)
    else:
        try:
            with get_db_conn() as conn:
                _insert_db(conn)
                conn.commit()
        except Exception as e:
            _log.debug("SQLite memory insert failed: %s", e)

    return mem_id


def search_board_memories(
    board_slug: str,
    query: str | None = None,
    limit: int = 8,
    db_path: str | None = None,
    conn: sqlite3.Connection | None = None,
) -> list[dict[str, Any]]:
    """Search board memories semantically using Mem0 vector index, falling back to SQLite."""
    results = []

    # 1. Try Mem0 semantic search if query is provided
    if query and query.strip():
        try:
            client = get_mem0_client(conn)
            if client:
                try:
                    m_res = client.search(
                        query=query.strip(),
                        filters={"user_id": board_slug},
                        limit=limit,
                    )
                except Exception:
                    m_res = client.search(
                        query=query.strip(), user_id=board_slug, limit=limit
                    )

                items = (
                    m_res.get("results", [])
                    if isinstance(m_res, dict)
                    else (m_res if isinstance(m_res, list) else [])
                )
                for item in items:
                    content = (
                        item.get("memory")
                        or item.get("text")
                        or item.get("content")
                        or ""
                    )
                    meta = item.get("metadata") or {}
                    cat = meta.get("category") or "general"
                    tags = meta.get("tags") or []
                    results.append(
                        {
                            "id": item.get("id") or meta.get("memory_id"),
                            "category": cat,
                            "content": content,
                            "tags": tags,
                            "author": meta.get("author") or "mem0",
                            "score": item.get("score", 1.0),
                        }
                    )
                if results:
                    return results
        except Exception as e:
            _log.debug("Mem0 search for board '%s' failed: %s", board_slug, e)

    # 2. SQLite retrieval fallback (or when query is not semantic)
    try:
        from .db import get_db_conn as _gdb

        with _gdb(db_path) as conn:
            cur = conn.cursor()
            rows = cur.execute(
                """
                SELECT id, category, content, tags, author
                FROM board_memories
                WHERE board_slug = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (board_slug, limit),
            ).fetchall()
            for r in rows:
                tag_list = []
                try:
                    tag_list = json.loads(r["tags"] or "[]")
                except Exception:
                    pass
                results.append(
                    {
                        "id": r["id"],
                        "category": r["category"] or "general",
                        "content": r["content"] or "",
                        "tags": tag_list,
                        "author": r["author"] or "user",
                        "score": 1.0,
                    }
                )
    except Exception as e:
        _log.debug("SQLite memory fallback failed: %s", e)

    return results


def mem0_delete_memory(memory_id: str, board_slug: str | None = None) -> bool:
    """Delete memory from Mem0 vector index and SQLite board_memories table."""
    try:
        client = get_mem0_client()
        if client:
            client.delete(memory_id)
    except Exception as e:
        _log.debug("Mem0 delete failed for %s: %s", memory_id, e)

    try:
        with get_db_conn() as conn:
            conn.execute("DELETE FROM board_memories WHERE id = ?", (memory_id,))
            conn.commit()
            return True
    except Exception:
        return False


def extract_and_record_memory(
    conn: sqlite3.Connection,
    board_slug: str,
    text: str,
    task_id: str | None = None,
    author: str = "zf-reviewer",
) -> list[dict[str, Any]]:
    """Extract structured rules/gotchas and record to Mem0 and board_memories."""
    if not text or not board_slug:
        return []

    settings = load_settings(conn)
    if not settings.get("auto_record_memory", True):
        return []

    try:
        b_row = conn.execute(
            "SELECT auto_record_memory FROM boards WHERE slug = ?", (board_slug,)
        ).fetchone()
        if b_row:
            arm_val = (
                b_row["auto_record_memory"]
                if "auto_record_memory" in b_row.keys()
                else b_row[0]
            )
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
            (board_slug, clean_content),
        ).fetchone()
        if exact_row:
            continue
        rows = conn.execute(
            "SELECT content FROM board_memories WHERE board_slug = ?", (board_slug,)
        ).fetchall()
        if any(normalize_memory_content(r["content"]) == dedup_key for r in rows):
            continue

        mem_id = f"mem-{secrets.token_hex(4)}"
        tags = ["auto-recorded", f"from-{author}"]
        tags_json = json.dumps(tags)

        # 1. Store in Mem0
        try:
            client = get_mem0_client()
            if client:
                client.add(
                    clean_content,
                    user_id=board_slug,
                    metadata={
                        "memory_id": mem_id,
                        "category": cat,
                        "task_id": task_id or "",
                        "author": author,
                        "tags": tags,
                    },
                )
        except Exception as _me:
            _log.debug("Mem0 auto-record index failed: %s", _me)

        # 2. Store in SQLite table
        conn.execute(
            """
            INSERT INTO board_memories (id, board_slug, task_id, category, content, tags, author, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                mem_id,
                board_slug,
                task_id,
                cat,
                clean_content,
                tags_json,
                author,
                now,
                now,
            ),
        )

        if task_id:
            try:
                log_activity(
                    conn,
                    task_id,
                    author,
                    "auto_memory_recorded",
                    f"Auto-recorded {cat}: {clean_content[:80]}",
                )
            except Exception:
                pass

        recorded.append(
            {
                "id": mem_id,
                "board_slug": board_slug,
                "task_id": task_id,
                "category": cat,
                "content": clean_content,
                "tags": tags,
                "author": author,
                "created_at": now,
                "updated_at": now,
            }
        )

    return recorded
