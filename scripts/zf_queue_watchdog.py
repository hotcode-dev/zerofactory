#!/usr/bin/env python3
"""ZeroFactory Queue Watchdog & Autonomous Dispatcher.

Designed for Hermes No-Agent Mode (`no_agent: true`).
Runs on a scheduled interval without calling an LLM:
1. Detects and reaps stuck worker subprocesses.
2. Moves timed-out tasks to 'blocked'.
3. Triggers the dispatcher loop to promote todo tasks and handle PR workflows.
4. If healthy: outputs `{"wakeAgent": false}` (silent execution).
5. If issues found: outputs markdown alert for operator delivery.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

# Add plugin root to sys.path so we can import internal modules
SCRIPT_DIR = Path(__file__).resolve().parent
candidate_roots = [
    SCRIPT_DIR.parent,
    Path.home() / ".hermes" / "plugins" / "zerofactory",
    Path.home() / "git" / "hotcode-dev" / "zerofactory",
]
if os.environ.get("ZEROFACTORY_ROOT"):
    candidate_roots.insert(0, Path(os.environ["ZEROFACTORY_ROOT"]))

for candidate in candidate_roots:
    try:
        resolved = candidate.resolve()
        if resolved.is_dir() and str(resolved) not in sys.path:
            sys.path.insert(0, str(resolved))
    except Exception:
        pass

from dispatcher import check_stuck_tasks, reap_stuck_tasks, run_dispatch_cycle
from dashboard.plugin_api import get_stats, get_db_path


def _count_legacy_ready() -> int:
    """Count tasks still stuck in the removed legacy 'ready' status.

    Non-zero here means the ready->todo migration did not run on this DB
    (e.g. it was created before the migration landed and is driven only by
    the dispatcher). The dispatcher's own defensive re-mapping will fix the
    rows on its next cycle, but the watchdog surfaces the count so a status
    regression is visible to the operator instead of silent.
    """
    import sqlite3
    db_path = get_db_path()
    if not db_path.exists():
        return 0
    try:
        conn = sqlite3.connect(str(db_path), timeout=10.0)
        try:
            row = conn.execute(
                "SELECT COUNT(*) FROM tasks WHERE status = 'ready'"
            ).fetchone()
            return int(row[0]) if row else 0
        finally:
            conn.close()
    except Exception:
        return 0


def run_watchdog() -> int:
    timeout_sec = int(os.environ.get("ZEROFACTORY_TASK_TIMEOUT_SECONDS", "3600"))
    inactivity_sec = int(os.environ.get("ZEROFACTORY_INACTIVITY_TIMEOUT_SECONDS", "900"))

    # 1. Check and reap stuck tasks
    reap_res = reap_stuck_tasks()
    reaped_tasks = reap_res.get("reaped_tasks") or reap_res.get("reaped", [])
    reaped_count = len(reaped_tasks)
    reaped_details = [
        f"- **Task `{r['id']}`** ({r.get('title', 'unnamed')}): {r.get('reason')}"
        for r in reaped_tasks
    ]

    # 2. Trigger dispatch cycle
    dispatch_res = run_dispatch_cycle()
    dispatched = dispatch_res.get("dispatched", 0)
    # The dispatch cycle's defensive re-mapping may have already fixed
    # legacy 'ready' rows this tick; a non-zero count here means rows were
    # missed (status regression) and deserve an operator-visible warning.
    migrated_ready = dispatch_res.get("migrated_ready", 0)
    legacy_ready = _count_legacy_ready()

    # 3. Retrieve stats
    stats = get_stats()
    cols = stats.get("columns", {})

    has_bottleneck = reaped_count > 0 or cols.get("blocked", 0) > 10
    has_legacy_ready = legacy_ready > 0 or migrated_ready > 0

    if not has_bottleneck and not has_legacy_ready:
        # Healthy: Output silent wake-gate signal
        gate = {
            "wakeAgent": False,
            "status": "healthy",
            "total_tasks": stats.get("total", 0),
            "todo": cols.get("todo", 0),
            "running": cols.get("running", 0),
            "dispatched": dispatched
        }
        print(json.dumps(gate))
        return 0

    # Bottleneck or legacy-status regression detected: Print report for operator
    print("# ⚠ ZeroFactory Queue Watchdog Alert\n")
    if reaped_details:
        print("### Reaped Stuck Tasks:")
        for line in reaped_details:
            print(line)
        print()

    print("### Current Board State:")
    print(f"- **Total Tasks:** {stats.get('total', 0)}")
    print(f"- **Todo:** {cols.get('todo', 0)}")
    print(f"- **Running:** {cols.get('running', 0)}")
    print(f"- **Blocked:** {cols.get('blocked', 0)}")
    print(f"- **Dispatched this tick:** {dispatched}")
    if has_legacy_ready:
        print(f"- **Legacy 'ready' tasks migrated this tick:** {migrated_ready}")
        if legacy_ready > 0:
            print(f"- **Legacy 'ready' tasks still remaining:** {legacy_ready}")
        print()
        print(
            "Legacy 'ready' status was removed from the workflow; affected tasks "
            "are re-mapped to 'todo' automatically on the next dispatch cycle."
        )
        print()
    print("Action taken: Timed-out workers were terminated and moved to `blocked` for triage.")
    return 0


if __name__ == "__main__":
    sys.exit(run_watchdog())
