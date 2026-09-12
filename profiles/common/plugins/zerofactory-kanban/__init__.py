"""Zero Factory Kanban — Hermes Plugin Entrypoint & CLI."""

from __future__ import annotations

import argparse
import json
import os
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import the database logic from dashboard.plugin_api
try:
    from .dashboard.plugin_api import (
        init_db, get_db_conn, list_tasks as _list_tasks, create_task as _create_task,
        update_task as _update_task, move_task as _move_task, add_comment as _add_comment,
        get_stats as _get_stats, trigger_dispatch as _trigger_dispatch,
        TaskCreate, TaskUpdate, TaskMove, CommentCreate
    )
except ImportError:
    # If running directly or out-of-package
    current_dir = Path(__file__).parent
    if str(current_dir / "dashboard") not in sys.path:
        sys.path.insert(0, str(current_dir / "dashboard"))
    from plugin_api import (  # type: ignore
        init_db, get_db_conn, list_tasks as _list_tasks, create_task as _create_task,
        update_task as _update_task, move_task as _move_task, add_comment as _add_comment,
        get_stats as _get_stats, trigger_dispatch as _trigger_dispatch,
        TaskCreate, TaskUpdate, TaskMove, CommentCreate
    )


try:
    from .dispatcher import run_dispatch_cycle, start_background_dispatcher
except ImportError:
    from dispatcher import run_dispatch_cycle, start_background_dispatcher  # type: ignore

try:
    from .builtin_cron import ensure_builtin_cron_jobs, list_builtin_jobs, trigger_builtin_job
except ImportError:
    from builtin_cron import ensure_builtin_cron_jobs, list_builtin_jobs, trigger_builtin_job  # type: ignore

def register(ctx: Any):
    """Register plugin CLI commands and lifecycle hooks with Hermes."""

    # Initialize DB, sync builtin cron jobs, & start continuous background dispatcher loop
    try:
        init_db()
        ensure_builtin_cron_jobs()
        start_background_dispatcher()
    except Exception as e:
        print(f"[zerofactory-kanban] Initialization error: {e}")

    # Register tick hook if supported by Hermes
    if hasattr(ctx, "register_hook"):
        try:
            ctx.register_hook("on_kanban_dispatch_tick", lambda *a, **kw: run_dispatch_cycle())
        except Exception:
            pass

    # Register CLI command
    def cmd_setup(parser: argparse.ArgumentParser):
        subparsers = parser.add_subparsers(dest="action", help="Zero Factory Kanban actions")

        # list
        p_list = subparsers.add_parser("list", help="List kanban tasks")
        p_list.add_argument("--board", default=None, help="Filter by board slug")
        p_list.add_argument("--status", default=None, help="Filter by status (triage, todo, ready, running, blocked, done)")
        p_list.add_argument("--assignee", default=None, help="Filter by assignee")

        # create
        p_create = subparsers.add_parser("create", help="Create a new task")
        p_create.add_argument("title", help="Task title")
        p_create.add_argument("--description", default="", help="Task description")
        p_create.add_argument("--status", default="triage", help="Initial status")
        p_create.add_argument("--priority", default="P2", help="Priority (P0, P1, P2, P3)")
        p_create.add_argument("--assignee", default="unassigned", help="Assignee (orchestrator, builder, reviewer)")
        p_create.add_argument("--board", default=None, help="Board slug (defaults to first available board)")
        p_create.add_argument("--parent", default=None, help="Parent task ID")
        p_create.add_argument("--files", default=None, help="Affected relative file path(s), comma-separated")
        p_create.add_argument("--category", default="bug-fix", help="Issue category (e.g. bug-fix, refactoring, performance, test, config)")
        p_create.add_argument("--dedup-key", default=None, help="Explicit deduplication key override")

        # move
        p_move = subparsers.add_parser("move", help="Move a task to a different column")
        p_move.add_argument("task_id", help="Task ID")
        p_move.add_argument("status", choices=["triage", "todo", "ready", "running", "blocked", "done"], help="Target status")

        # block
        p_block = subparsers.add_parser("block", help="Mark a task as blocked")
        p_block.add_argument("task_id", help="Task ID")
        p_block.add_argument("--reason", default="review-required", help="Block reason")

        # comment
        p_comment = subparsers.add_parser("comment", help="Add a comment to a task")
        p_comment.add_argument("task_id", help="Task ID")
        p_comment.add_argument("body", help="Comment body")
        p_comment.add_argument("--author", default="user", help="Author name")

        # stats
        subparsers.add_parser("stats", help="Show Kanban board statistics")

        # dispatch
        subparsers.add_parser("dispatch", help="Trigger dispatch cycle")

        # cron
        p_cron = subparsers.add_parser("cron", help="Manage built-in Zero Factory cron jobs")
        cron_subs = p_cron.add_subparsers(dest="cron_action", help="Cron actions")
        cron_subs.add_parser("list", help="List built-in Zero Factory cron jobs and status")
        cron_subs.add_parser("sync", help="Synchronize built-in cron jobs with Hermes cron storage")
        p_cron_run = cron_subs.add_parser("run", help="Trigger immediate execution of a built-in cron job")
        p_cron_run.add_argument("job_id", help="Job ID (e.g. zero-factory-task-queue-check, zero-factory-daily-report, zero-factory-improvement-scanner)")

    def cmd_run(args: argparse.Namespace):
        init_db()
        action = getattr(args, "action", "list")

        if action == "list" or not action:
            res = _list_tasks(board=getattr(args, "board", None), status=getattr(args, "status", None), assignee=getattr(args, "assignee", None))
            tasks = res.get("tasks", [])
            print(f"\nZero Factory Kanban ({len(tasks)} tasks):")
            print(f"{'ID':<12} {'PRIO':<6} {'STATUS':<10} {'ASSIGNEE':<14} {'TITLE'}")
            print("-" * 75)
            for t in tasks:
                prio = t.get("priority", "P2")
                stat = t.get("status", "triage")
                asgn = t.get("assignee", "unassigned")
                title = t.get("title", "")
                if len(title) > 40:
                    title = title[:37] + "..."
                print(f"{t['id']:<12} {prio:<6} {stat:<10} {asgn:<14} {title}")
            print()

        elif action == "create":
            files_arg = getattr(args, "files", None)
            files_list = [f.strip() for f in files_arg.split(",") if f.strip()] if files_arg else []
            req = TaskCreate(
                title=args.title,
                description=args.description,
                status=args.status,
                priority=args.priority,
                assignee=args.assignee,
                board_slug=args.board,
                parent_id=args.parent,
                files=files_list,
                category=getattr(args, "category", "bug-fix"),
                dedup_key=getattr(args, "dedup_key", None),
            )
            res = _create_task(req)
            if res.get("duplicate"):
                print(f"[Duplicate Skipped] {res.get('message', 'Task already exists')}")
            else:
                print(f"Created task {res['id']}: {args.title}")

        elif action == "move":
            req = TaskMove(status=args.status)
            res = _move_task(args.task_id, req)
            print(f"Moved task {args.task_id} to {args.status}")

        elif action == "block":
            req = TaskMove(status="blocked")
            _move_task(args.task_id, req)
            _add_comment(args.task_id, CommentCreate(author="cli", body=f"Blocked: {args.reason}"))
            print(f"Task {args.task_id} marked as BLOCKED ({args.reason})")

        elif action == "comment":
            _add_comment(args.task_id, CommentCreate(author=args.author, body=args.body))
            print(f"Added comment to task {args.task_id}")

        elif action == "stats":
            res = _get_stats()
            print("\nZero Factory Kanban Statistics:")
            print(f"  Total Tasks:     {res['total']}")
            print(f"  Active Worktrees: {res['active_worktrees']}")
            print("  Columns:")
            for col, count in res["columns"].items():
                print(f"    - {col.capitalize():<10}: {count}")
            print()

        elif action == "dispatch":
            res = _trigger_dispatch()
            print(f"Dispatch result: {res.get('message', res)}")

        elif action == "cron":
            cron_act = getattr(args, "cron_action", "list") or "list"
            if cron_act == "list":
                jobs = list_builtin_jobs()
                print("\nZero Factory Built-in Cron Jobs:")
                print(f"{'ID':<36} {'SCHEDULE':<14} {'STATE':<10} {'LAST STATUS':<12} {'LAST RUN'}")
                print("-" * 90)
                for j in jobs:
                    jid = j["id"]
                    sch = j.get("schedule") or "-"
                    st = j.get("state") or "scheduled"
                    ls = j.get("last_status") or "-"
                    lr = j.get("last_run_at") or "-"
                    print(f"{jid:<36} {sch:<14} {st:<10} {ls:<12} {lr}")
                print()
            elif cron_act == "sync":
                res = ensure_builtin_cron_jobs()
                print(f"Synced builtin cron jobs: added {res.get('added', 0)}, updated {res.get('updated', 0)} across {len(res.get('synced_targets', []))} targets.")
                for t in res.get("synced_targets", []):
                    print(f"  ✓ {t}")
            elif cron_act == "run":
                res = trigger_builtin_job(args.job_id)
                if res.get("ok"):
                    print(f"✓ {res.get('message')}")
                else:
                    print(f"✗ Failed to trigger job: {res.get('error')}")

    if hasattr(ctx, "register_cli_command"):
        ctx.register_cli_command(
            name="zerofactory-kanban",
            help="Zero Factory durable Kanban board management",
            setup_fn=cmd_setup,
            handler_fn=cmd_run
        )
