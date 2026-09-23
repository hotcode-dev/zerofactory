#!/usr/bin/env python3
"""ZeroFactory Daily Metrics & Aggregation Pre-Run Script.

Pre-computes ZeroFactory analytics and Kanban metrics deterministically:
1. Queries `zerofactory.db` for completed tasks in the last 24h.
2. Formats cycle time, column distributions, throughput, and blocked bottlenecks.
3. Produces clean markdown tables to inject directly into the LLM prompt.
4. Eliminates the need for the LLM agent to execute multiple sqlite/cli tool loops.
"""

from __future__ import annotations

import json
import os
import sqlite3
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

DEFAULT_DB_PATH = Path.home() / ".hermes" / "zerofactory.db"


def _resolve_running_since(rt: Dict[str, Any], now: int) -> int:
    """Return the epoch second a running task started, for in-flight duration.

    ``tasks.updated_at`` is written exactly once — at claim/spawn time — and is
    never refreshed while a worker runs, so deriving duration from
    ``now - updated_at`` permanently reports ~0-1m for the whole lifetime of a
    build (the exact metric needed to spot hung/stuck workers is wrong).

    The dispatcher records the authoritative dispatch time in task metadata at
    spawn (``meta["started_at"]``) — the same field the stuck-detection path
    relies on (``meta.get("started_at") or updated_at or created_at``) — so we
    prefer that and fall back to ``updated_at`` then ``created_at``.
    """
    started_at = None
    meta = rt.get("metadata")
    if isinstance(meta, dict):
        started_at = meta.get("started_at")
    elif meta:
        try:
            parsed = json.loads(meta)
            if isinstance(parsed, dict):
                started_at = parsed.get("started_at")
        except Exception:
            started_at = None
    since = started_at or rt.get("updated_at") or rt.get("created_at") or now
    try:
        return int(since)
    except (TypeError, ValueError):
        return now


def run_daily_stats() -> int:
    db_path = Path(os.environ.get("ZEROFACTORY_DB") or DEFAULT_DB_PATH)
    if not db_path.exists():
        print("ZeroFactory database not found at", db_path)
        return 0

    now = int(time.time())
    one_day_ago = now - 86400

    try:
        with sqlite3.connect(str(db_path), timeout=5.0) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()

            # Column breakdown
            cursor.execute("SELECT status, count(*) FROM tasks GROUP BY status")
            columns = dict(cursor.fetchall())

            # Total tasks
            cursor.execute("SELECT count(*) FROM tasks")
            total = cursor.fetchone()[0]

            # Completed in last 24h
            cursor.execute(
                "SELECT id, title, assignee, board_slug, updated_at FROM tasks WHERE status = 'done' AND updated_at >= ? ORDER BY updated_at DESC",
                (one_day_ago,)
            )
            completed_24h = [dict(r) for r in cursor.fetchall()]

            # Blocked tasks
            cursor.execute(
                "SELECT id, title, assignee, description, metadata, board_slug FROM tasks WHERE status = 'blocked' ORDER BY priority ASC, updated_at DESC"
            )
            blocked_tasks = [dict(r) for r in cursor.fetchall()]

            # Active running tasks
            cursor.execute(
                "SELECT id, title, assignee, board_slug, updated_at, created_at, metadata FROM tasks WHERE status = 'running'"
            )
            running_tasks = [dict(r) for r in cursor.fetchall()]

            # Boards overview
            cursor.execute("SELECT slug, git_url FROM boards")
            boards = [dict(r) for r in cursor.fetchall()]

    except Exception as e:
        print(f"Failed to query database metrics: {e}")
        return 0

    print("### 📊 Pre-Calculated ZeroFactory Daily Metrics (Deterministic 0-Token Ingestion)")
    print(f"**Report Generated:** {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime(now))}")
    print()
    print("#### Column Distribution:")
    print("| Column | Task Count | Status |")
    print("|---|---|---|")
    for col in ("triage", "todo", "running", "blocked", "done"):
        cnt = columns.get(col, 0)
        indicator = "🟢" if col == "done" else ("🔴" if col == "blocked" and cnt > 0 else "⚪")
        print(f"| `{col}` | {cnt} | {indicator} |")
    print(f"| **Total** | **{total}** | |")
    print()

    print(f"#### 24-Hour Velocity:")
    print(f"- **Tasks Completed in Last 24h:** {len(completed_24h)}")
    if completed_24h:
        for ct in completed_24h[:8]:
            print(f"  - `{ct['id']}`: {ct['title']} ({ct.get('board_slug', 'default')})")
    print()

    if blocked_tasks:
        print(f"#### ⚠ Active Blockers ({len(blocked_tasks)} tasks):")
        for bt in blocked_tasks[:5]:
            meta = {}
            if bt.get("metadata"):
                try:
                    meta = json.loads(bt["metadata"])
                except Exception:
                    pass
            reason = meta.get("blocked_reason") or meta.get("reason") or bt.get("description") or "unspecified"
            print(f"- `{bt['id']}` ({bt['assignee']}): {bt['title']} — *Reason: {reason}*")
        print()

    if running_tasks:
        print(f"#### ⚡ Currently In-Flight ({len(running_tasks)} tasks):")
        for rt in running_tasks:
            elapsed = max(0, (now - _resolve_running_since(rt, now)) // 60)
            print(f"- `{rt['id']}` ({rt['assignee']}): {rt['title']} (active for {elapsed}m)")
        print()

    print(f"#### Active Boards: {len(boards)}")
    for b in boards:
        print(f"- `{b['slug']}` ({b.get('git_url', '') or 'local'})")
    print()
    print("---")
    print("Instructions for Agent: Synthesize the above metrics into a concise, professional executive briefing. Highlight velocity, blocker resolution, and recommended focus areas. Create the task using `hermes zerofactory create \"[Report] Daily Report\" --status done`.")
    return 0


if __name__ == "__main__":
    sys.exit(run_daily_stats())
