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
import logging
import os
import sys
from pathlib import Path

_log = logging.getLogger(__name__)

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

from dashboard.plugin_api import get_db_conn, get_stats
from dispatcher import reap_stuck_tasks, run_dispatch_cycle


def sync_open_github_issues(cooldown_seconds: int = 900) -> list[dict]:
    """Scan and import open GitHub issues labeled 'zerofactory' for active boards.

    Guards against GitHub rate limits by:
    1. Checking ZEROFACTORY_AUTO_SYNC_GH_ISSUES (disable with '0' or 'false').
    2. Enforcing a per-repo cooldown window (default 15 minutes) so frequent
       watchdog ticks never spam the GitHub API.
    """
    if os.environ.get("ZEROFACTORY_AUTO_SYNC_GH_ISSUES", "1").lower() in (
        "0",
        "false",
        "no",
    ):
        return []

    try:
        import re
        import time
        from issues.github import GitHubIssueClient
        from issues.importer import import_external_issue

        client = GitHubIssueClient()
        if not client.test_connection():
            return []

        # Load cooldown timestamps
        cache_file = Path.home() / ".hermes" / "gh_issues_sync_cache.json"
        sync_cache: dict[str, float] = {}
        if cache_file.exists():
            try:
                sync_cache = json.loads(cache_file.read_text(encoding="utf-8"))
            except Exception:
                sync_cache = {}

        now = time.time()
        imported_tasks = []
        with get_db_conn() as conn:
            cursor = conn.cursor()
            cursor.execute(
                """
                SELECT b.slug, br.repo_alias, br.git_url
                FROM boards b
                JOIN board_repositories br ON b.slug = br.board_slug
                ORDER BY b.created_at ASC
                """
            )
            repos = cursor.fetchall()

        cache_updated = False
        for r in repos:
            slug = r["slug"]
            git_url = r["git_url"] or ""
            m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)(?:\.git)?$", git_url)
            if not m:
                continue
            repo = f"{m.group(1)}/{m.group(2)}"

            # Skip if synced within cooldown window
            last_synced = sync_cache.get(repo, 0.0)
            if now - last_synced < cooldown_seconds:
                continue
            try:
                open_issues = client.fetch_investigation_issues(
                    repo=repo, label="zerofactory", state="open"
                )
                for iss in open_issues:
                    res = import_external_issue(
                        issue=iss,
                        board_slug=slug,
                        status="triage",
                        assignee="zf-orchestrator",
                        actor="zf-watchdog",
                    )
                    if not res.get("duplicate"):
                        imported_tasks.append(res)
            except Exception as e:
                # Do NOT stamp the cooldown on failure so the next tick
                # retries immediately instead of silently skipping the
                # board for the whole cooldown window.
                _log.warning("GitHub issue sync failed for %s: %s", repo, e)
                continue
            # Stamp only after fetch + import complete without exception.
            sync_cache[repo] = now
            cache_updated = True

        if cache_updated:
            tmp_file = cache_file.with_name(cache_file.name + ".tmp")
            try:
                cache_file.parent.mkdir(parents=True, exist_ok=True)
                # Atomic write: write to a sibling temp file then rename
                # (os.replace semantics), matching the durability
                # convention in scripts/zf_scanner_gate.py /
                # scripts/zf_openwiki_gate.py so a crash mid-write can
                # never leave a corrupt cache file behind.
                tmp_file.write_text(json.dumps(sync_cache), encoding="utf-8")
                os.replace(tmp_file, cache_file)
            except Exception as e:
                try:
                    tmp_file.unlink(missing_ok=True)
                except Exception:
                    pass
                _log.warning("Failed to persist GitHub issue sync cache: %s", e)

        return imported_tasks
    except Exception:
        return []


def run_watchdog() -> int:
    # 0. Auto-sync open GitHub issues labeled 'zerofactory'
    synced_issues = sync_open_github_issues()

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
            "todo": cols.get("todo", 0),
            "running": cols.get("running", 0),
            "dispatched": dispatched,
            "imported_issues": len(synced_issues),
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
    print(f"- **Todo:** {cols.get('todo', 0)}")
    print(f"- **Running:** {cols.get('running', 0)}")
    print(f"- **Blocked:** {cols.get('blocked', 0)}")
    print(f"- **Dispatched this tick:** {dispatched}")
    print()
    print(
        "Action taken: Timed-out workers were terminated and moved to `blocked` for triage."
    )
    return 0


if __name__ == "__main__":
    sys.exit(run_watchdog())
