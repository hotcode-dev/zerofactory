"""Zero Factory — Hermes Plugin Entrypoint & CLI."""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

# Import the database logic from dashboard.plugin_api
try:
    from .dashboard.plugin_api import (
        ACTIVITY_ACTORS,
        BoardCreate,
        BoardUpdate as _BoardUpdate,
        CommentCreate,
        MemoryCreate,
        TaskCreate,
        TaskMove,
        TaskUpdate,
        get_db_conn,
        init_db,
    )
    from .dashboard.plugin_api import (
        MEMORY_CONTENT_MAX_LENGTH as _MEMORY_CONTENT_MAX_LENGTH,
    )
    from .dashboard.plugin_api import (
        add_comment as _add_comment,
    )
    from .dashboard.plugin_api import (
        check_board_openwiki_status as _check_board_openwiki_status,
    )
    from .dashboard.plugin_api import (
        check_board_precommit_status as _check_board_precommit_status,
    )
    from .dashboard.plugin_api import (
        create_board as _create_board,
    )
    from .dashboard.plugin_api import (
        create_memory as _create_memory,
    )
    from .dashboard.plugin_api import (
        create_openwiki_setup_task as _create_openwiki_setup_task,
    )
    from .dashboard.plugin_api import (
        create_precommit_setup_task as _create_precommit_setup_task,
    )
    from .dashboard.plugin_api import (
        create_task as _create_task,
    )
    from .dashboard.plugin_api import (
        delete_board as _delete_board,
    )
    from .dashboard.plugin_api import (
        delete_memory as _delete_memory,
    )
    from .dashboard.plugin_api import (
        get_stats as _get_stats,
    )
    from .dashboard.plugin_api import (
        list_boards as _list_boards,
    )
    from .dashboard.plugin_api import (
        list_memories as _list_memories,
    )
    from .dashboard.plugin_api import (
        list_tasks as _list_tasks,
    )
    from .dashboard.plugin_api import (
        move_task as _move_task,
    )
    from .dashboard.plugin_api import (
        trigger_dispatch as _trigger_dispatch,
    )
    from .dashboard.plugin_api import (
        update_task as _update_task,
    )
    from .dashboard.plugin_api import (
        update_board as _update_board,
    )
except ImportError:
    current_dir = Path(__file__).parent
    if str(current_dir / "dashboard") not in sys.path:
        sys.path.insert(0, str(current_dir / "dashboard"))
    from plugin_api import (  # type: ignore
        ACTIVITY_ACTORS,
        BoardCreate,
        BoardUpdate as _BoardUpdate,
        CommentCreate,
        MemoryCreate,
        TaskCreate,
        TaskMove,
        TaskUpdate,
        get_db_conn,
        init_db,
    )
    from plugin_api import (
        MEMORY_CONTENT_MAX_LENGTH as _MEMORY_CONTENT_MAX_LENGTH,
    )
    from plugin_api import (
        add_comment as _add_comment,
    )
    from plugin_api import (
        check_board_openwiki_status as _check_board_openwiki_status,
    )
    from plugin_api import (
        check_board_precommit_status as _check_board_precommit_status,
    )
    from plugin_api import (
        create_board as _create_board,
    )
    from plugin_api import (
        create_memory as _create_memory,
    )
    from plugin_api import (
        create_openwiki_setup_task as _create_openwiki_setup_task,
    )
    from plugin_api import (
        create_precommit_setup_task as _create_precommit_setup_task,
    )
    from plugin_api import (
        create_task as _create_task,
    )
    from plugin_api import (
        delete_board as _delete_board,
    )
    from plugin_api import (
        delete_memory as _delete_memory,
    )
    from plugin_api import (
        get_stats as _get_stats,
    )
    from plugin_api import (
        list_boards as _list_boards,
    )
    from plugin_api import (
        list_memories as _list_memories,
    )
    from plugin_api import (
        list_tasks as _list_tasks,
    )
    from plugin_api import (
        move_task as _move_task,
    )
    from plugin_api import (
        trigger_dispatch as _trigger_dispatch,
    )
    from plugin_api import (
        update_task as _update_task,
    )
    from plugin_api import (
        update_board as _update_board,
    )

try:
    from .dispatcher import run_dispatch_cycle, start_background_dispatcher
except ImportError:
    from dispatcher import (  # type: ignore
        run_dispatch_cycle,
        start_background_dispatcher,
    )

try:
    from .builtin_cron import (
        ensure_builtin_cron_jobs,
        list_builtin_jobs,
        trigger_builtin_job,
    )
except ImportError:
    from builtin_cron import (
        ensure_builtin_cron_jobs,
        list_builtin_jobs,
        trigger_builtin_job,
    )  # type: ignore

try:
    from .profile_manager import ZF_PROFILES, ensure_zf_profiles
except ImportError:
    from profile_manager import ZF_PROFILES, ensure_zf_profiles  # type: ignore

try:
    from .issues import GitHubIssueClient, JiraIssueClient, import_external_issue
except ImportError:
    from issues import GitHubIssueClient, JiraIssueClient, import_external_issue  # type: ignore


def register(ctx: Any):
    """Register plugin CLI commands, profiles bootstrap, and lifecycle hooks with Hermes."""

    # Initialize DB, pre-create agent profiles, sync builtin crons, and start dispatcher
    try:
        init_db()
        ensure_zf_profiles()
        ensure_builtin_cron_jobs()
        if not os.environ.get("ZEROFACTORY_SKIP_DISPATCHER") and not os.environ.get(
            "ZEROFACTORY_DISABLE_DISPATCHER"
        ):
            start_background_dispatcher()
    except Exception as e:
        print(f"[zerofactory] Initialization error: {e}")

    # Register tick hook if supported by Hermes
    if hasattr(ctx, "register_hook"):
        try:
            ctx.register_hook(
                "on_kanban_dispatch_tick", lambda *a, **kw: run_dispatch_cycle()
            )
        except Exception:
            pass

    # Register CLI command
    def cmd_setup(parser: argparse.ArgumentParser):
        subparsers = parser.add_subparsers(dest="action", help="Zero Factory actions")

        # setup profiles
        p_setup = subparsers.add_parser(
            "setup",
            help="Verify and bootstrap Zero Factory agent profiles (zf-orchestrator, zf-builder, zf-reviewer)",
        )
        p_setup.add_argument(
            "--force",
            action="store_true",
            help="Force overwrite existing profiles with templates",
        )

        # sync-profiles
        p_sync_prof = subparsers.add_parser(
            "sync-profiles",
            help="Update SOUL.md system prompts for zf-* profiles from templates",
        )
        p_sync_prof.add_argument(
            "--force", action="store_true", help="Also overwrite config.yaml"
        )

        # list
        p_list = subparsers.add_parser("list", help="List kanban tasks")
        p_list.add_argument("--board", default=None, help="Filter by board slug")
        p_list.add_argument(
            "--repo", default=None, help="Filter by repository alias on the board"
        )
        p_list.add_argument(
            "--status",
            default=None,
            help="Filter by status (triage, todo, running, blocked, done)",
        )
        p_list.add_argument("--assignee", default=None, help="Filter by assignee")

        # create
        p_create = subparsers.add_parser("create", help="Create a new task")
        p_create.add_argument("title", help="Task title")
        p_create.add_argument("--description", default="", help="Task description")
        p_create.add_argument(
            "--description-file",
            default=None,
            help="Path to file containing task description (prevents shell quoting issues)",
        )
        p_create.add_argument("--status", default="triage", help="Initial status")
        p_create.add_argument(
            "--priority", default="P2", help="Priority (P0, P1, P2, P3)"
        )
        p_create.add_argument(
            "--assignee",
            default="unassigned",
            help="Assignee (zf-orchestrator, zf-builder, zf-reviewer)",
        )
        p_create.add_argument(
            "--board",
            default=None,
            help="Board slug (defaults to first available board)",
        )
        p_create.add_argument(
            "--repo",
            default=None,
            help="Target repository alias on the board (e.g. backend, frontend)",
        )
        p_create.add_argument("--parent", default=None, help="Parent task ID")
        p_create.add_argument(
            "--files",
            default=None,
            help="Affected relative file path(s), comma-separated",
        )
        p_create.add_argument(
            "--category",
            default="bug-fix",
            help="Issue category (e.g. bug-fix, refactoring, performance, test, config)",
        )
        p_create.add_argument(
            "--dedup-key", default=None, help="Explicit deduplication key override"
        )
        p_create.add_argument(
            "--actor",
            default=None,
            help="Actor creating the task (defaults to HERMES_PROFILE or 'user')",
        )

        # import-gh-issue
        p_import_gh = subparsers.add_parser(
            "import-gh-issue",
            help="Import GitHub issue(s) into Zero Factory Kanban deterministically",
        )
        p_import_gh.add_argument(
            "issue",
            nargs="?",
            default=None,
            help="GitHub issue number (e.g. 42, #42), URL, or owner/repo#42. Omit when using --sync.",
        )
        p_import_gh.add_argument(
            "--repo",
            default=None,
            help="GitHub repository (owner/repo). Inferred from board git_url or git remote if omitted.",
        )
        p_import_gh.add_argument(
            "--board",
            default=None,
            help="Target board slug. Inferred from repository if omitted.",
        )
        p_import_gh.add_argument(
            "--status",
            default="triage",
            choices=["triage", "todo", "running", "blocked", "done"],
            help="Initial Kanban column (default: triage)",
        )
        p_import_gh.add_argument(
            "--priority",
            default=None,
            choices=["P0", "P1", "P2", "P3"],
            help="Priority override (inferred deterministically from issue labels if omitted)",
        )
        p_import_gh.add_argument(
            "--assignee",
            default="zf-orchestrator",
            help="Assignee (default: zf-orchestrator)",
        )
        p_import_gh.add_argument(
            "--label",
            default="zerofactory",
            help="Required human request label for AI investigation (default: 'zerofactory')",
        )
        p_import_gh.add_argument(
            "--force",
            action="store_true",
            help="Import issue even if it lacks the AI request label",
        )
        p_import_gh.add_argument(
            "--sync",
            action="store_true",
            help="Fetch and import all open issues flagged with the AI request label",
        )
        p_import_gh.add_argument(
            "--type",
            choices=["bug", "feature"],
            default=None,
            help="Explicit issue type override ('bug' or 'feature')",
        )
        p_import_gh.add_argument(
            "--actor",
            default=None,
            help="Actor executing import (defaults to HERMES_PROFILE or 'user')",
        )

        # import-jira-issue
        p_import_jira = subparsers.add_parser(
            "import-jira-issue",
            help="Import Jira issue into Zero Factory Kanban deterministically",
        )
        p_import_jira.add_argument(
            "issue",
            help="Jira issue key (e.g. PROJ-123) or full URL (https://domain.atlassian.net/browse/PROJ-123)",
        )
        p_import_jira.add_argument(
            "--project",
            default=None,
            help="Default Jira project key (e.g. PROJ)",
        )
        p_import_jira.add_argument(
            "--board",
            default=None,
            help="Target board slug. Inferred from project or board's jira_url if omitted.",
        )
        p_import_jira.add_argument(
            "--status",
            default="triage",
            choices=["triage", "todo", "running", "blocked", "done"],
            help="Initial Kanban column (default: triage)",
        )
        p_import_jira.add_argument(
            "--priority",
            default=None,
            choices=["P0", "P1", "P2", "P3"],
            help="Priority override (inferred deterministically from issue labels if omitted)",
        )
        p_import_jira.add_argument(
            "--assignee",
            default="zf-orchestrator",
            help="Assignee (default: zf-orchestrator)",
        )
        p_import_jira.add_argument(
            "--type",
            choices=["bug", "feature"],
            default=None,
            help="Explicit issue type override ('bug' or 'feature')",
        )
        p_import_jira.add_argument(
            "--actor",
            default=None,
            help="Actor executing import (defaults to HERMES_PROFILE or 'user')",
        )

        # setup-gh-issues
        p_setup_gh = subparsers.add_parser(
            "setup-gh-issues",
            help="Provision GitHub issue templates (.github/ISSUE_TEMPLATE) and standard labels",
        )
        p_setup_gh.add_argument(
            "--board",
            default=None,
            help="Target board slug to create a P0 setup task or inspect board workspace.",
        )
        p_setup_gh.add_argument(
            "--repo",
            default=None,
            help="Target GitHub repository (owner/repo). Inferred from git origin if omitted.",
        )
        p_setup_gh.add_argument(
            "--path",
            default=None,
            help="Path to repository root (defaults to current working directory).",
        )
        p_setup_gh.add_argument(
            "--no-labels",
            action="store_true",
            help="Skip creating GitHub labels via gh CLI",
        )
        p_setup_gh.add_argument(
            "--actor",
            default=None,
            help="Actor executing setup (defaults to HERMES_PROFILE or 'user')",
        )

        # setup-jira
        p_setup_jira = subparsers.add_parser(
            "setup-jira",
            help="Configure Jira Cloud link and test connectivity for a board",
        )
        p_setup_jira.add_argument(
            "--board",
            required=True,
            help="Target board slug to configure Jira for",
        )
        p_setup_jira.add_argument(
            "--url",
            default=None,
            help="Jira Cloud instance URL (e.g. https://your-domain.atlassian.net)",
        )
        p_setup_jira.add_argument(
            "--test",
            action="store_true",
            help="Test Jira connectivity and API authentication",
        )

        # move
        p_move = subparsers.add_parser("move", help="Move a task to a different column")
        p_move.add_argument("task_id", help="Task ID")
        p_move.add_argument(
            "status",
            choices=["triage", "todo", "running", "blocked", "done"],
            help="Target status",
        )
        p_move.add_argument(
            "--reason",
            default=None,
            help="Optional reason; recorded as a comment when moving to 'blocked' (mirrors the 'block' command)",
        )
        p_move.add_argument(
            "--assignee",
            default=None,
            help="Optional new assignee (e.g. zf-builder or human)",
        )
        p_move.add_argument(
            "--actor",
            default=None,
            help="Actor executing move (defaults to HERMES_PROFILE or 'user')",
        )

        # update
        p_update = subparsers.add_parser("update", help="Update task fields")
        p_update.add_argument("task_id", help="Task ID")
        p_update.add_argument("--title", default=None, help="New title")
        p_update.add_argument("--description", default=None, help="New description")
        p_update.add_argument("--assignee", default=None, help="New assignee")
        p_update.add_argument(
            "--priority",
            choices=["P0", "P1", "P2", "P3"],
            default=None,
            help="New priority",
        )
        p_update.add_argument(
            "--status",
            choices=["triage", "todo", "running", "blocked", "done"],
            default=None,
            help="New status",
        )

        # block
        p_block = subparsers.add_parser("block", help="Mark a task as blocked")
        p_block.add_argument("task_id", help="Task ID")
        p_block.add_argument("--reason", default="review-required", help="Block reason")
        p_block.add_argument(
            "--actor",
            default=None,
            help="Actor executing block (defaults to HERMES_PROFILE or 'user')",
        )

        # comment
        p_comment = subparsers.add_parser("comment", help="Add a comment to a task")
        p_comment.add_argument("task_id", help="Task ID")
        p_comment.add_argument("body", help="Comment body")
        p_comment.add_argument(
            "--author",
            default=None,
            help="Author name (defaults to HERMES_PROFILE or 'user')",
        )

        # stats
        subparsers.add_parser("stats", help="Show Kanban board statistics")

        # dispatch
        subparsers.add_parser("dispatch", help="Trigger dispatch cycle")

        # check-stuck
        p_stuck = subparsers.add_parser(
            "check-stuck",
            help="Check running tasks for excessive duration or inactivity",
        )
        p_stuck.add_argument(
            "--timeout",
            type=int,
            default=None,
            help="Override running timeout threshold in seconds",
        )
        p_stuck.add_argument(
            "--inactivity",
            type=int,
            default=None,
            help="Override inactivity threshold in seconds",
        )
        p_stuck.add_argument(
            "--reap",
            action="store_true",
            help="Automatically terminate and move stuck tasks to blocked",
        )
        p_stuck.add_argument(
            "--task", default=None, help="Specific task ID to inspect or reap"
        )

        # cron
        p_cron = subparsers.add_parser(
            "cron", help="Manage built-in Zero Factory cron jobs"
        )
        cron_subs = p_cron.add_subparsers(dest="cron_action", help="Cron actions")
        cron_subs.add_parser(
            "list", help="List built-in Zero Factory cron jobs and status"
        )
        cron_subs.add_parser(
            "sync", help="Synchronize built-in cron jobs with Hermes cron storage"
        )
        p_cron_run = cron_subs.add_parser(
            "run", help="Trigger immediate execution of a built-in cron job"
        )
        p_cron_run.add_argument(
            "job_id",
            help="Job ID (e.g. zero-factory-task-queue-check, zero-factory-improvement-scanner)",
        )

        # board
        p_board = subparsers.add_parser(
            "board", help="Manage Zero Factory Kanban boards"
        )
        board_subs = p_board.add_subparsers(dest="board_action", help="Board actions")
        board_subs.add_parser("list", help="List all boards")
        p_bcreate = board_subs.add_parser(
            "create", help="Create a new board from Remote Git URL"
        )
        p_bcreate.add_argument(
            "git_url", help="Remote Git URL (e.g. https://github.com/owner/repo.git)"
        )
        p_bcreate.add_argument(
            "--slug",
            default=None,
            help="Custom board slug (defaults to slug inferred from git URL)",
        )
        p_bcreate.add_argument("--description", default="", help="Board description")
        p_bcreate.add_argument(
            "--target-branch",
            default="",
            help="Target/base branch to branch off and merge PRs into (e.g. main)",
        )
        p_bcreate.add_argument(
            "--architecture",
            default="",
            help="Cross-service architecture notes and contracts",
        )
        p_bcreate.add_argument(
            "--setup-precommit",
            action="store_true",
            help="Automatically trigger setup task for .zerofactory/precommit.sh",
        )
        p_bcreate.add_argument(
            "--jira-url",
            default="",
            help="Optional Jira Cloud instance or project URL (e.g. https://your-domain.atlassian.net)",
        )
        p_bupdate = board_subs.add_parser(
            "update",
            help="Update board configuration (description, target-branch, jira-url, architecture)",
        )
        p_bupdate.add_argument("slug", help="Board slug to update")
        p_bupdate.add_argument(
            "--description", default=None, help="New board description"
        )
        p_bupdate.add_argument(
            "--target-branch", default=None, help="New target branch"
        )
        p_bupdate.add_argument(
            "--jira-url", default=None, help="Jira Cloud instance URL"
        )
        p_bupdate.add_argument(
            "--architecture", default=None, help="Inter-service architecture and contracts"
        )

        p_bdelete = board_subs.add_parser(
            "delete", help="Delete a board and clear its cron scanner job"
        )
        p_bdelete.add_argument("slug", help="Board slug to delete")

        # memory
        p_mem = subparsers.add_parser(
            "memory", help="Manage native board memories & repository knowledge"
        )
        mem_subs = p_mem.add_subparsers(dest="memory_action", help="Memory actions")
        p_mlist = mem_subs.add_parser("list", help="List memories for a board")
        p_mlist.add_argument("--board", required=True, help="Board slug")
        p_mlist.add_argument(
            "--category",
            default=None,
            help="Category filter (decision, gotcha, convention, rejected_path, general)",
        )
        p_mlist.add_argument("--query", "-q", default=None, help="Keyword search query")

        p_madd = mem_subs.add_parser(
            "add",
            help=f"Add a new repository memory (max {_MEMORY_CONTENT_MAX_LENGTH} chars)",
        )
        p_madd.add_argument("--board", required=True, help="Board slug")
        p_madd.add_argument(
            "content",
            help=f"Memory content / finding / convention (max {_MEMORY_CONTENT_MAX_LENGTH} chars)",
        )
        p_madd.add_argument(
            "--category",
            default="general",
            choices=["decision", "gotcha", "convention", "rejected_path", "general"],
            help="Category",
        )
        p_madd.add_argument("--tags", default=None, help="Comma-separated tags")
        p_madd.add_argument(
            "--author",
            default=None,
            help="Author name (defaults to HERMES_PROFILE or 'user')",
        )
        p_madd.add_argument("--task", default=None, help="Associated task ID")

        p_mdel = mem_subs.add_parser("delete", help="Delete a memory by ID")
        p_mdel.add_argument("memory_id", help="Memory ID")

        # migrate
        p_mig = subparsers.add_parser(
            "migrate", help="Run or inspect SQLite database migrations"
        )
        p_mig.add_argument(
            "--status",
            action="store_true",
            help="Show migration status without applying",
        )

        # setup-repo
        p_setupr = subparsers.add_parser(
            "setup-repo",
            help="Create P0 setup task to generate .zerofactory/precommit.sh for a board",
        )
        p_setupr.add_argument("--board", required=True, help="Board slug")
        p_setupr.add_argument(
            "--actor",
            default=None,
            help="Actor executing setup (defaults to HERMES_PROFILE or 'user')",
        )

        # setup-openwiki
        p_setupow = subparsers.add_parser(
            "setup-openwiki",
            help="Create P0 setup task to generate OpenWiki architecture documentation for a board",
        )
        p_setupow.add_argument("--board", required=True, help="Board slug")
        p_setupow.add_argument(
            "--actor",
            default=None,
            help="Actor executing setup (defaults to HERMES_PROFILE or 'user')",
        )

    def cmd_run(args: argparse.Namespace):
        init_db()
        action = getattr(args, "action", "list")

        if action == "setup":
            force = getattr(args, "force", False)
            res = ensure_zf_profiles(force=force)
            print("\nZero Factory Profiles Setup:")
            if res["created"]:
                print(f"  ✓ Created:  {', '.join(res['created'])}")
            if res["updated"]:
                print(f"  ✓ Updated:  {', '.join(res['updated'])}")
            if res["existing"]:
                print(f"  ✓ Verified: {', '.join(res['existing'])}")
            print("All Zero Factory profiles are ready in ~/.hermes/profiles/.\n")

        elif action == "sync-profiles":
            force = getattr(args, "force", False)
            res = ensure_zf_profiles(force=force, update_prompts=True)
            print("\nZero Factory Profiles Synced:")
            if res["updated"]:
                print(f"  ✓ Updated SOUL/Prompts: {', '.join(res['updated'])}")
            if res["created"]:
                print(f"  ✓ Created: {', '.join(res['created'])}")
            if res["existing"]:
                print(f"  ✓ Current: {', '.join(res['existing'])}")
            print()

        elif action == "list" or not action:
            res = _list_tasks(
                board=getattr(args, "board", None),
                repo=getattr(args, "repo", None),
                status=getattr(args, "status", None),
                assignee=getattr(args, "assignee", None),
            )
            tasks = res.get("tasks", [])
            print(f"\nZero Factory Kanban ({len(tasks)} tasks):")
            print(f"{'ID':<12} {'PRIO':<6} {'STATUS':<10} {'ASSIGNEE':<16} {'TITLE'}")
            print("-" * 75)
            for t in tasks:
                prio = t.get("priority", "P2")
                stat = t.get("status", "triage")
                asgn = t.get("assignee", "unassigned")
                title = t.get("title", "")
                if len(title) > 40:
                    title = title[:37] + "..."
                print(f"{t['id']:<12} {prio:<6} {stat:<10} {asgn:<16} {title}")
            print()

        elif action == "create":
            desc = args.description or ""
            desc_file = getattr(args, "description_file", None)
            if desc_file and os.path.isfile(desc_file):
                try:
                    desc = Path(desc_file).read_text(encoding="utf-8").strip()
                except Exception as e:
                    print(f"Warning: Failed to read --description-file: {e}")

            files_arg = getattr(args, "files", None)
            files_list = (
                [f.strip() for f in files_arg.split(",") if f.strip()]
                if files_arg
                else []
            )
            actor_val = (
                getattr(args, "actor", None) or os.environ.get("HERMES_PROFILE") or None
            )
            req = TaskCreate(
                title=args.title,
                description=desc,
                status=args.status,
                priority=args.priority,
                assignee=args.assignee,
                board_slug=args.board,
                repo_alias=getattr(args, "repo", None),
                parent_id=args.parent,
                files=files_list,
                category=getattr(args, "category", "bug-fix"),
                dedup_key=getattr(args, "dedup_key", None),
                actor=actor_val,
            )
            res = _create_task(req)
            if res.get("duplicate"):
                print(
                    f"[Duplicate Skipped] {res.get('message', 'Task already exists')}"
                )
            else:
                print(f"Created task {res['id']}: {args.title}")

        elif action == "import-gh-issue":
            client = GitHubIssueClient(default_repo=getattr(args, "repo", None))
            actor = (
                getattr(args, "actor", None)
                or os.environ.get("HERMES_PROFILE")
                or "user"
            )
            req_label = getattr(args, "label", "zerofactory")
            force = getattr(args, "force", False)
            sync_mode = getattr(args, "sync", False)

            try:
                if sync_mode or not getattr(args, "issue", None):
                    # Batch sync open issues with the AI investigation request label
                    repo_to_sync = getattr(args, "repo", None)
                    if not repo_to_sync:
                        try:
                            from scripts.setup_gh_issues import detect_repo_from_git

                            repo_to_sync = detect_repo_from_git(Path("."))
                        except Exception:
                            pass
                    if not repo_to_sync:
                        print(
                            "Error: Specify --repo owner/repo or run from a git repository with remote origin."
                        )
                        sys.exit(1)

                    print(
                        f"\nScanning {repo_to_sync} for open issues labeled '{req_label}'..."
                    )
                    issues_to_import = client.fetch_investigation_issues(
                        repo=repo_to_sync, label=req_label, state="open"
                    )
                    if not issues_to_import:
                        print(f"No open issues found with label '{req_label}'.\n")
                        return

                    print(
                        f"Found {len(issues_to_import)} issue(s) requested for AI investigation.\n"
                    )
                    imported_count = 0
                    duplicate_count = 0
                    for iss in issues_to_import:
                        if getattr(args, "type", None):
                            iss.issue_type = getattr(args, "type")
                        res = import_external_issue(
                            issue=iss,
                            board_slug=getattr(args, "board", None),
                            status=getattr(args, "status", "triage"),
                            priority=getattr(args, "priority", None),
                            assignee=getattr(args, "assignee", "zf-orchestrator"),
                            actor=actor,
                        )
                        if res.get("duplicate"):
                            duplicate_count += 1
                            print(
                                f"  [Duplicate] {res['issue_key']}: {res['title']} ({res['id']})"
                            )
                        else:
                            imported_count += 1
                            print(
                                f"  ✓ Imported  {res['issue_key']} [{res['issue_type'].capitalize()}] -> {res['id']}: {res['title']}"
                            )

                    print(
                        f"\nSync complete: {imported_count} imported, {duplicate_count} skipped duplicates.\n"
                    )
                else:
                    issue = client.fetch_issue(
                        args.issue, repo=getattr(args, "repo", None)
                    )
                    # Check human request label
                    if not force and not issue.has_ai_request_label(
                        {req_label, "zerofactory", "ai-investigate", "ai-triage"}
                    ):
                        print(
                            f"\nError: GitHub issue #{issue.id} ('{issue.title}') lacks an explicit human AI investigation label "
                            f"(expected '{req_label}' or 'ai-investigate').",
                            file=sys.stderr,
                        )
                        print(
                            "Zero Factory only imports issues where a human explicitly requested AI investigation.\n"
                            f"Add the '{req_label}' label on GitHub, or pass --force to bypass this check.\n",
                            file=sys.stderr,
                        )
                        sys.exit(1)

                    if getattr(args, "type", None):
                        issue.issue_type = getattr(args, "type")

                    res = import_external_issue(
                        issue=issue,
                        board_slug=getattr(args, "board", None),
                        status=getattr(args, "status", "triage"),
                        priority=getattr(args, "priority", None),
                        assignee=getattr(args, "assignee", "zf-orchestrator"),
                        actor=actor,
                    )
                    if res.get("duplicate"):
                        print(
                            f"\n[Duplicate Skipped] {res.get('message', 'Task already exists')}"
                        )
                        print(f"  Task ID:    {res['id']}")
                        print(
                            f"  Issue:      {res['issue_key']} ({res['issue_url']})\n"
                        )
                    else:
                        print(
                            f"\n✓ Successfully imported GitHub issue {res['issue_key']}"
                        )
                        print(f"  Task ID:    {res['id']}")
                        print(f"  Type:       {res['issue_type'].capitalize()}")
                        print(f"  Board:      {res['board_slug']}")
                        print(f"  Status:     {res['status']}")
                        print(f"  Assignee:   {res['assignee']}")
                        print(f"  Priority:   {res['priority']}")
                        print(f"  Title:      {res['title']}")
                        if res.get("issue_url"):
                            print(f"  URL:        {res['issue_url']}")
                        print()
            except Exception as e:
                print(
                    f"\nError importing GitHub issue: {e}\n",
                    file=sys.stderr,
                )
                sys.exit(1)

        elif action == "import-jira-issue":
            client = JiraIssueClient(
                board_slug=getattr(args, "board", None),
                default_project=getattr(args, "project", None),
            )
            actor = (
                getattr(args, "actor", None)
                or os.environ.get("HERMES_PROFILE")
                or "user"
            )
            try:
                issue = client.fetch_issue(
                    args.issue, project=getattr(args, "project", None)
                )
                if getattr(args, "type", None):
                    issue.issue_type = getattr(args, "type")

                res = import_external_issue(
                    issue=issue,
                    board_slug=getattr(args, "board", None),
                    status=getattr(args, "status", "triage"),
                    priority=getattr(args, "priority", None),
                    assignee=getattr(args, "assignee", "zf-orchestrator"),
                    actor=actor,
                )
                if res.get("duplicate"):
                    print(
                        f"\n[Duplicate Skipped] {res.get('message', 'Task already exists')}"
                    )
                    print(f"  Task ID:    {res['id']}")
                    print(f"  Issue:      {res['issue_key']} ({res['issue_url']})\n")
                else:
                    print(f"\n✓ Successfully imported Jira issue {res['issue_key']}")
                    print(f"  Task ID:    {res['id']}")
                    print(f"  Type:       {res['issue_type'].capitalize()}")
                    print(f"  Board:      {res['board_slug']}")
                    print(f"  Status:     {res['status']}")
                    print(f"  Assignee:   {res['assignee']}")
                    print(f"  Priority:   {res['priority']}")
                    print(f"  Title:      {res['title']}")
                    if res.get("issue_url"):
                        print(f"  URL:        {res['issue_url']}")
                    print()
            except Exception as e:
                print(
                    f"\nError importing Jira issue: {e}\n",
                    file=sys.stderr,
                )
                sys.exit(1)

        elif action == "setup-gh-issues":
            board_slug = getattr(args, "board", None)
            actor_val = (
                getattr(args, "actor", None)
                or os.environ.get("HERMES_PROFILE")
                or "user"
            )
            if board_slug:
                try:
                    from .dashboard.gh_issues_service import (
                        create_gh_issues_setup_task,
                    )
                except Exception:
                    from dashboard.gh_issues_service import (
                        create_gh_issues_setup_task,
                    )

                res = create_gh_issues_setup_task(board_slug, actor=actor_val)
                if res.get("ok"):
                    if res.get("already_exists"):
                        print(
                            f"✓ GitHub Issues setup task already active: {res.get('task_id')} ({res.get('status')})"
                        )
                    else:
                        print(
                            f"✓ Created P0 GitHub Issues setup task: {res.get('task_id')}"
                        )
                    print(
                        f"  Task '{res.get('task_id')}' will ship a PR with the aligned templates after precommit verification."
                    )
                else:
                    print(f"✗ Failed to initiate setup task: {res.get('error')}")
                return

            from scripts.setup_gh_issues import setup_github_issues

            target_path = Path(getattr(args, "path", None) or ".").resolve()
            repo_arg = getattr(args, "repo", None)
            create_labels = not getattr(args, "no_labels", False)

            print("\nZero Factory GitHub Issue Setup:")
            print(f"  Target Directory: {target_path}")

            res = setup_github_issues(
                repo_root=target_path,
                repo=repo_arg,
                create_labels=create_labels,
            )

            print("\n✓ Generated GitHub Issue Templates:")
            for t in res["templates"]:
                print(f"  - {t}")

            if res.get("label_results"):
                l_res = res["label_results"]
                if l_res.get("created"):
                    print(f"\n✓ Provisioned GitHub Labels in {res.get('target_repo')}:")
                    for lbl in l_res["created"]:
                        print(f"  ✓ {lbl}")
                if l_res.get("failed"):
                    print("\n⚠️ Label Provisioning Warnings:")
                    for err in l_res["failed"]:
                        print(f"  - {err}")
                if l_res.get("error"):
                    print(f"\n⚠️ {l_res['error']}")
            print(
                "\nSetup complete! Issues filed with the 'zerofactory' label can now be triaged by Zero Factory AI.\n"
            )

        elif action == "setup-jira":
            board_slug = getattr(args, "board", None)
            new_url = getattr(args, "url", None)

            if not board_slug:
                print("Error: --board <slug> is required", file=sys.stderr)
                sys.exit(1)

            init_db()
            with get_db_conn() as conn:
                board = conn.execute(
                    "SELECT * FROM boards WHERE slug = ?", (board_slug,)
                ).fetchone()
                if not board:
                    print(f"Error: Board '{board_slug}' not found", file=sys.stderr)
                    sys.exit(1)

                current_url = (board["jira_url"] or "").strip()
                if new_url is not None:
                    current_url = new_url.strip()
                    conn.execute(
                        "UPDATE boards SET jira_url = ?, updated_at = ? WHERE slug = ?",
                        (current_url, int(time.time()), board_slug),
                    )
                    print(
                        f"\n✓ Updated Jira URL for board '{board_slug}': {current_url}"
                    )

            client = JiraIssueClient(base_url=current_url, board_slug=board_slug)
            status = client.check_connection()
            print(f"\nJira Connection Status for board '{board_slug}':")
            print(f"  Configured URL : {status.get('base_url') or '(none)'}")
            print(
                f"  Reachable      : {'✓ Yes' if status.get('connected') else '✗ No'}"
            )
            print(
                f"  Authenticated  : {'✓ Yes' if status.get('authenticated') else '⚪ No (Token/Email required for private issues)'}"
            )
            print(f"  Message        : {status.get('message')}\n")
            return

        elif action == "move":
            actor = (
                getattr(args, "actor", None)
                or os.environ.get("HERMES_PROFILE")
                or "user"
            )
            reason = getattr(args, "reason", None)
            assignee = getattr(args, "assignee", None)
            req = TaskMove(
                status=args.status, actor=actor, reason=reason, assignee=assignee
            )
            res = _move_task(args.task_id, req)
            if res.get("ignored"):
                print(
                    f"Warning: Move for task {args.task_id} was ignored: {res.get('reason')}",
                    file=sys.stderr,
                )
                sys.exit(1)
            elif res.get("status") == "blocked" and reason:
                print(f"Moved task {args.task_id} to {args.status} (reason: {reason})")
            else:
                print(f"Moved task {args.task_id} to {args.status}")

        elif action == "update":
            status_val = getattr(args, "status", None)
            req = TaskUpdate(
                title=getattr(args, "title", None),
                description=getattr(args, "description", None),
                assignee=getattr(args, "assignee", None),
                priority=getattr(args, "priority", None),
            )
            res = _update_task(args.task_id, req)
            if status_val:
                # Status is a lifecycle transition — always via move_task so the
                # move semantics (flags, worker stop, dispatch trigger) apply.
                actor = (
                    getattr(args, "actor", None)
                    or os.environ.get("HERMES_PROFILE")
                    or "user"
                )
                _move_task(args.task_id, TaskMove(status=status_val, actor=actor))
            print(f"Updated task {args.task_id}")

        elif action == "block":
            # Delegate to `move_task` with the reason so the single shared
            # code path in dashboard/plugin_api.py records the "Blocked: ..."
            # comment — identical to `move <id> blocked --reason ...`.
            actor = (
                getattr(args, "actor", None)
                or os.environ.get("HERMES_PROFILE")
                or "user"
            )
            req = TaskMove(status="blocked", actor=actor, reason=args.reason)
            _move_task(args.task_id, req)
            print(f"Task {args.task_id} marked as BLOCKED ({args.reason})")

        elif action == "comment":
            author = (
                getattr(args, "author", None)
                or os.environ.get("HERMES_PROFILE")
                or "user"
            )
            _add_comment(args.task_id, CommentCreate(author=author, body=args.body))
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

        elif action == "check-stuck":
            try:
                from .dispatcher import check_stuck_tasks, reap_stuck_tasks
            except Exception:
                from dispatcher import check_stuck_tasks, reap_stuck_tasks

            if getattr(args, "timeout", None):
                os.environ["ZEROFACTORY_TASK_TIMEOUT_SECONDS"] = str(args.timeout)
            if getattr(args, "inactivity", None):
                os.environ["ZEROFACTORY_INACTIVITY_TIMEOUT_SECONDS"] = str(
                    args.inactivity
                )

            tasks = check_stuck_tasks()
            target_task = getattr(args, "task", None)
            if target_task:
                tasks = [t for t in tasks if t["id"] == target_task]

            print(f"\nZero Factory Running Tasks ({len(tasks)} running):")
            if not tasks:
                print("  No tasks currently in 'running' state.\n")
            else:
                print(
                    f"{'ID':<14} {'PID':<8} {'ALIVE':<6} {'RUNNING':<10} {'IDLE':<10} {'STATUS':<10} {'TITLE'}"
                )
                print("-" * 85)
                for t in tasks:
                    t_id = t["id"]
                    pid = str(t.get("worker_pid") or "-")
                    alive = "yes" if t.get("is_alive") else "NO"
                    run_str = f"{t.get('running_seconds', 0)}s"
                    idle_str = f"{t.get('idle_seconds', 0)}s"
                    stuck_str = "STUCK ⚠️" if t.get("is_stuck") else "OK ✓"
                    title = t.get("title", "")
                    if len(title) > 32:
                        title = title[:29] + "..."
                    print(
                        f"{t_id:<14} {pid:<8} {alive:<6} {run_str:<10} {idle_str:<10} {stuck_str:<10} {title}"
                    )
                    if t.get("is_stuck") and t.get("stuck_reason"):
                        print(f"   ↳ Reason: {t['stuck_reason']}")
                print()

            if getattr(args, "reap", False):
                reap_res = reap_stuck_tasks(task_id=target_task)
                reaped = reap_res.get("reaped_tasks", [])
                if reaped:
                    print(f"✓ Reaped {len(reaped)} stuck task(s):")
                    for rt in reaped:
                        print(f"  - {rt['id']} ({rt['title']}): {rt['reason']}")
                else:
                    print("✓ No stuck tasks needed reaping.")
                print()

        elif action == "cron":
            cron_act = getattr(args, "cron_action", "list") or "list"
            if cron_act == "list":
                jobs = list_builtin_jobs()
                print("\nZero Factory Built-in Cron Jobs:")
                print(
                    f"{'ID':<36} {'SCHEDULE':<14} {'STATE':<10} {'LAST STATUS':<12} {'LAST RUN'}"
                )
                print("-" * 90)
                for j in jobs:
                    jid = str(j.get("id") or "-")
                    sch = j.get("schedule_display")
                    if not sch:
                        raw_sch = j.get("schedule")
                        if isinstance(raw_sch, dict):
                            sch = raw_sch.get("cron") or (
                                f"every {raw_sch['minutes']}m"
                                if "minutes" in raw_sch
                                else str(raw_sch)
                            )
                        else:
                            sch = str(raw_sch or "-")
                    st = str(j.get("state") or "scheduled")
                    ls = str(j.get("last_status") or "-")
                    lr = str(j.get("last_run_at") or "-")
                    print(f"{jid:<36} {sch:<14} {st:<10} {ls:<12} {lr}")
                print()
            elif cron_act == "sync":
                res = ensure_builtin_cron_jobs()
                print(
                    f"Synced builtin cron jobs: added {res.get('added', 0)}, updated {res.get('updated', 0)} across {len(res.get('synced_targets', []))} targets."
                )
                for t in res.get("synced_targets", []):
                    print(f"  ✓ {t}")
            elif cron_act == "run":
                res = trigger_builtin_job(args.job_id)
                if res.get("ok"):
                    print(f"✓ {res.get('message')}")
                else:
                    print(f"✗ Failed to trigger job: {res.get('error')}")

        elif action == "board":
            b_act = getattr(args, "board_action", "list") or "list"
            if b_act == "list":
                res = _list_boards()
                boards = res.get("boards", [])
                print(f"\nZero Factory Boards ({len(boards)}):")
                print(
                    f"{'SLUG':<32} {'TASKS':<8} {'RUNNING':<8} {'MAX RUN':<8} {'GIT URL'}"
                )
                print("-" * 96)
                for b in boards:
                    print(
                        f"{b['slug']:<32} {b.get('task_count', 0):<8} {b.get('running_count', 0):<8} {b.get('max_concurrent_running', 1):<8} {b.get('git_url', '')}"
                    )
                print()
            elif b_act == "create":
                req = BoardCreate(
                    slug=getattr(args, "slug", None),
                    git_url=args.git_url,
                    description=args.description,
                    architecture=getattr(args, "architecture", "") or "",
                    target_branch=getattr(args, "target_branch", "") or "",
                    auto_setup_precommit=getattr(args, "setup_precommit", False),
                    jira_url=getattr(args, "jira_url", "") or "",
                )
                res = _create_board(req)
                slug = res.get("slug")
                if res.get("setup_task_id"):
                    print(
                        f"✓ Created board '{slug}' and initiated precommit setup task '{res.get('setup_task_id')}'."
                    )
                else:
                    print(f"✓ Created board: {slug}")
            elif b_act == "update":
                up_kwargs = {}
                if getattr(args, "description", None) is not None:
                    up_kwargs["description"] = args.description
                if getattr(args, "target_branch", None) is not None:
                    up_kwargs["target_branch"] = args.target_branch
                if getattr(args, "jira_url", None) is not None:
                    up_kwargs["jira_url"] = args.jira_url
                if getattr(args, "architecture", None) is not None:
                    up_kwargs["architecture"] = args.architecture
                res = _update_board(args.slug, _BoardUpdate(**up_kwargs))
                print(f"✓ Updated board '{args.slug}'.")
            elif b_act == "delete":
                res = _delete_board(args.slug)
                print(
                    f"✓ Deleted board '{args.slug}' and cleared associated cron scanner job."
                )

        elif action == "memory":
            m_act = getattr(args, "memory_action", "list") or "list"
            if m_act == "list":
                res = _list_memories(
                    slug=args.board,
                    category=getattr(args, "category", None),
                    q=getattr(args, "query", None),
                )
                memories = res.get("memories", [])
                print(
                    f"\nRepository Memories for '{args.board}' ({len(memories)} entries):"
                )
                print(f"{'ID':<14} {'CATEGORY':<14} {'AUTHOR':<14} {'CONTENT'}")
                print("-" * 80)
                for m in memories:
                    cat = m.get("category", "general")
                    author = m.get("author", "user")
                    content = m.get("content", "").replace("\n", " ")
                    if len(content) > 45:
                        content = content[:42] + "..."
                    print(f"{m['id']:<14} {cat:<14} {author:<14} {content}")
                print()
            elif m_act == "add":
                tag_list = (
                    [t.strip() for t in args.tags.split(",") if t.strip()]
                    if getattr(args, "tags", None)
                    else []
                )
                author = (
                    getattr(args, "author", None)
                    or os.environ.get("HERMES_PROFILE")
                    or "user"
                )
                content = (args.content or "").strip()
                if len(content) > _MEMORY_CONTENT_MAX_LENGTH:
                    print(
                        f"✗ Memory content is {len(content)} chars; "
                        f"the maximum allowed is {_MEMORY_CONTENT_MAX_LENGTH} (API rejects it with 422)."
                    )
                    return
                if not content:
                    print("✗ Memory content must not be empty.")
                    return
                try:
                    req = MemoryCreate(
                        category=args.category,
                        content=args.content,
                        tags=tag_list,
                        author=author,
                        task_id=getattr(args, "task", None),
                    )
                except Exception as e:
                    print(f"✗ Invalid memory payload: {e}")
                    return
                res = _create_memory(args.board, req)
                mem = res.get("memory", {})
                print(
                    f"✓ Added memory {mem.get('id')} to board '{args.board}' [{mem.get('category')}]."
                )
            elif m_act == "delete":
                res = _delete_memory(args.memory_id)
                print(f"✓ Deleted memory '{args.memory_id}'.")

        elif action == "migrate":
            try:
                from .migrations.runner import get_migration_status, run_migrations
            except Exception:
                from migrations.runner import get_migration_status, run_migrations

            if getattr(args, "status", False):
                statuses = get_migration_status()
                print("\nZero Factory Migration Status:")
                print(f"  {'Version':<35} {'Status':<12} {'Applied At'}")
                print("  " + "-" * 65)
                for s in statuses:
                    st = "Applied" if s["applied"] else "Pending"
                    applied_str = (
                        time.strftime(
                            "%Y-%m-%d %H:%M:%S", time.localtime(s["applied_at"])
                        )
                        if s["applied_at"]
                        else "-"
                    )
                    print(f"  {s['version']:<35} {st:<12} {applied_str}")
                print()
            else:
                applied = run_migrations()
                if applied:
                    print(f"\nSuccessfully applied {len(applied)} migration(s):")
                    for m in applied:
                        print(f"  ✓ {m}")
                    print()
                else:
                    print("Database is up to date (no pending migrations).")

        elif action == "setup-repo":
            board_slug = getattr(args, "board", None)
            if not board_slug:
                print("Error: --board <slug> is required.")
                return
            actor_val = (
                getattr(args, "actor", None)
                or os.environ.get("HERMES_PROFILE")
                or "user"
            )
            status_info = _check_board_precommit_status(board_slug)
            if status_info.get("has_precommit"):
                print(
                    f"Notice: Board '{board_slug}' already has .zerofactory/precommit.sh at {status_info.get('precommit_path')}."
                )

            res = _create_precommit_setup_task(board_slug, actor=actor_val)
            if res.get("ok"):
                if res.get("already_exists"):
                    print(
                        f"✓ Precommit setup task already active: {res.get('task_id')} ({res.get('status')})"
                    )
                else:
                    print(f"✓ Created P0 precommit setup task: {res.get('task_id')}")
            else:
                print(f"✗ Failed to initiate setup task: {res.get('error')}")

        elif action == "setup-openwiki":
            board_slug = getattr(args, "board", None)
            if not board_slug:
                print("Error: --board <slug> is required.")
                return
            actor_val = (
                getattr(args, "actor", None)
                or os.environ.get("HERMES_PROFILE")
                or "user"
            )
            status_info = _check_board_openwiki_status(board_slug)
            if status_info.get("has_openwiki"):
                print(
                    f"Notice: Board '{board_slug}' already has OpenWiki at {status_info.get('openwiki_path')}."
                )

            res = _create_openwiki_setup_task(board_slug, actor=actor_val)
            if res.get("ok"):
                if res.get("already_exists"):
                    print(
                        f"✓ OpenWiki setup task already active: {res.get('task_id')} ({res.get('status')})"
                    )
                else:
                    print(f"✓ Created P0 OpenWiki setup task: {res.get('task_id')}")
            else:
                print(f"✗ Failed to initiate setup task: {res.get('error')}")

    if hasattr(ctx, "register_cli_command"):
        ctx.register_cli_command(
            name="zerofactory",
            help="Zero Factory multi-agent software factory & Kanban",
            setup_fn=cmd_setup,
            handler_fn=cmd_run,
        )
