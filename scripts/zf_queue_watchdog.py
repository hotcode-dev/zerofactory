#!/usr/bin/env python3
"""ZeroFactory Queue Watchdog & Autonomous Dispatcher.

Designed for Hermes No-Agent Mode (`no_agent: true`).
Runs on a scheduled interval without calling an LLM:
1. Detects and reaps stuck worker subprocesses.
2. Moves timed-out tasks to 'blocked'.
3. Triggers the dispatcher loop to promote ready tasks and handle PR workflows.
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
from dashboard.plugin_api import get_stats


def run_watchdog() -> int:
    timeout_sec = int(os.environ.get("ZEROFACTORY_TASK_TIMEOUT_SECONDS", "3600"))
    inactivity_sec = int(os.environ.get("ZEROFACTORY_INACTIVITY_TIMEOUT_SECONDS", "900"))

    # 1. Check and reap stuck tasks
    reap_res = reap_stuck_tasks()
    reaped_tasks = reap_res.get("reaped", [])
    reaped_count = len(reaped_tasks)
    reaped_details = [
        f"- **Task `{r['id']}`** ({r.get('title', 'unnamed')}): {r.get('reason')}"
        for r in reaped_tasks
    ]

    # 2. Trigger dispatch cycle
    dispatch_res = run_dispatch_cycle()
    dispatched = dispatch_res.get("dispatched", 0)

    # 3. Retrieve stats
    stats = get_stats()
    cols = stats.get("columns", {})

    has_bottleneck = reaped_count > 0 or cols.get("blocked", 0) > 10

    if not has_bottleneck:
        # Healthy: Output silent wake-gate signal
        gate = {
            "wakeAgent": False,
            "status": "healthy",
            "total_tasks": stats.get("total", 0),
            "running": cols.get("running", 0),
            "ready": cols.get("ready", 0),
            "dispatched": dispatched
        }
        print(json.dumps(gate))
        return 0

    # Bottleneck detected: Print report for operator
    print("# ⚠ ZeroFactory Queue Watchdog Alert\n")
    if reaped_details:
        print("### Reaped Stuck Tasks:")
        for line in reaped_details:
            print(line)
        print()

    print("### Current Board State:")
    print(f"- **Total Tasks:** {stats.get('total', 0)}")
    print(f"- **Running:** {cols.get('running', 0)}")
    print(f"- **Ready:** {cols.get('ready', 0)}")
    print(f"- **Blocked:** {cols.get('blocked', 0)}")
    print(f"- **Dispatched this tick:** {dispatched}")
    print()
    print("Action taken: Timed-out workers were terminated and moved to `blocked` for triage.")
    return 0


if __name__ == "__main__":
    sys.exit(run_watchdog())
