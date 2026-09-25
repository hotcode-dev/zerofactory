"""Agent worker spawning, environment preparation, and session tracking."""

from __future__ import annotations

from contextlib import closing
import json
import os
import shutil
import sqlite3
import subprocess
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

from .config import (
    _active_workers,
    _d,
    _log,
    get_db_path,
    load_settings,
    normalize_assignee,
    resolve_profile_state_db,
)


def _inject_langfuse_env(env: Dict[str, str], conn_or_cursor: Any = None) -> None:
    """Inject active Langfuse credentials and configuration into worker subprocess environment."""
    try:
        if conn_or_cursor is None:
            try:
                from ..dashboard.plugin_api import get_db_conn
            except (ImportError, ValueError):
                from dashboard.plugin_api import get_db_conn
            with get_db_conn() as conn:
                settings = load_settings(conn)
        else:
            settings = load_settings(conn_or_cursor)

        if settings.get("langfuse_enabled"):
            env["HERMES_LANGFUSE_PUBLIC_KEY"] = str(settings.get("langfuse_public_key") or "").strip()
            env["HERMES_LANGFUSE_SECRET_KEY"] = str(settings.get("langfuse_secret_key") or "").strip()
            env["HERMES_LANGFUSE_BASE_URL"] = str(settings.get("langfuse_base_url") or "https://cloud.langfuse.com").strip()
            env["HERMES_LANGFUSE_CAPTURE"] = str(settings.get("langfuse_capture_mode") or "sanitized").strip()
            env["HERMES_LANGFUSE_ENV"] = str(settings.get("langfuse_env") or "zerofactory").strip()
        else:
            for k in ("HERMES_LANGFUSE_PUBLIC_KEY", "HERMES_LANGFUSE_SECRET_KEY", "HERMES_LANGFUSE_BASE_URL", "HERMES_LANGFUSE_CAPTURE", "HERMES_LANGFUSE_ENV"):
                env.pop(k, None)
    except Exception as e:
        _log.debug("Could not inject Langfuse env: %s", e)


def spawn_agent_worker(
    task_id: str,
    title: str,
    description: str,
    priority: str,
    assignee: str,
    workspace_path: Optional[str],
    branch_name: Optional[str],
    board_slug: Optional[str] = None
) -> Tuple[Optional[int], Optional[str]]:
    """Spawn an isolated hermes worker subprocess for the assigned specialist agent."""
    if os.environ.get("ZEROFACTORY_SKIP_WORKER_SPAWN"):
        return None, None

    assignee = normalize_assignee(assignee)
    local_hermes = Path.home() / ".local" / "bin" / "hermes"
    hermes_bin = (
        os.environ.get("HERMES_BIN")
        or shutil.which("hermes")
        or (str(local_hermes) if local_hermes.exists() else "hermes")
    )

    workdir = workspace_path if (workspace_path and Path(workspace_path).exists()) else os.getcwd()
    memories_digest = _d().digest_board_memories_context(board_slug)
    memories_block = f"{memories_digest}\n\n" if memories_digest else ""

    if assignee == "zf-reviewer":
        target_branch = ""
        if board_slug:
            try:
                try:
                    from ..dashboard.plugin_api import get_db_conn
                except (ImportError, ValueError):
                    from dashboard.plugin_api import get_db_conn
                with get_db_conn() as conn:
                    row = conn.execute("SELECT target_branch FROM boards WHERE slug = ?", (board_slug,)).fetchone()
                    if row and row[0]:
                        target_branch = str(row[0]).strip()
            except Exception:
                pass
        pre_digested_git = _d().digest_reviewer_git_context(Path(workdir), branch_name, target_branch=target_branch or None)
        pre_digested_block = f"\n{pre_digested_git}\n\n" if pre_digested_git else "\n"
        prompt = (
            f"Task ID: {task_id}\n"
            f"Title: {title}\n"
            f"Priority: {priority}\n"
            f"Assigned Role: {assignee}\n\n"
            f"Description:\n{description or 'No description provided.'}\n\n"
            f"Workspace: {workdir}\n"
            f"Git Branch: {branch_name or 'main'}\n\n"
            f"{memories_block}"
            f"{pre_digested_block}"
            f"Your goal as Reviewer:\n"
            f"1. Examine the Pull Request branch changes ({branch_name or 'main'}) for correctness, edge cases, test coverage, and security (review the pre-digested diff above).\n"
            f"2. Run automated test suites and linters in your workspace ({workdir}).\n"
            f"3. Submit your review decision on GitHub (`gh pr review --approve` or `gh pr review --request-changes`).\n"
            f"4. Continuous Learning & Repository Knowledge:\n"
            f"   - If you catch a recurring mistake, testing gotcha, or project convention that future tasks should follow, record it!\n"
            f"   - In your review comment or summary, include a line: `GOTCHA: <rule>` or `CONVENTION: <rule>` (the system will auto-record it).\n"
            f"   - Or run: `hermes zerofactory memory add --board {board_slug or 'default'} \"<rule>\" --category <gotcha|convention>`.\n"
            f"5. When finished:\n"
            f"   - If approved: run `hermes zerofactory block {task_id} --reason 'Human Review & Merge'` (the task will be assigned to human for review/merge, and the dispatcher will automatically move the task to 'done' once merged on GitHub; DO NOT mark done yourself).\n"
            f"   - If changes are requested: run `hermes zerofactory block {task_id} --reason 'changes-requested'` (the dispatcher will route it back to the builder).\n"
            f"6. Provide a clear review summary.\n"
        )
    else:
        # Fail-closed: if the worktree cannot be verified clean, treat it as a
        # potential conflict and route to the conflict-resolution prompt rather
        # than the generic implement prompt (an unverifiable worktree must not
        # be advanced as if it were clean).
        conflict_check_verified = True
        _files: List[str] = []
        _cc_err = ""
        try:
            conflict_check_verified, _files, _cc_err = _d().check_unresolved_conflicts_safe(Path(workdir))
        except Exception as e:  # defensive: safe wrapper should not raise
            conflict_check_verified, _cc_err = False, str(e)
        has_conflict = (
            "[pr conflict]" in title.lower()
            or "[merge conflict]" in title.lower()
            or (not conflict_check_verified and Path(workdir).exists())
            or (conflict_check_verified and Path(workdir).exists() and bool(_files))
        )
        if has_conflict:
            if conflict_check_verified and Path(workdir).exists():
                conflicted_files = _files
            elif not conflict_check_verified:
                conflicted_files = []  # unverifiable -> fall back to marker scan / git status
            else:
                conflicted_files = []
            file_list_str = (
                "\n".join(f"- {f}" for f in conflicted_files)
                if conflicted_files
                else "- (Unverifiable or no unmerged files; check `git status` for unmerged files)"
            )
            prompt = (
                f"Task ID: {task_id}\n"
                f"Title: {title}\n"
                f"Priority: {priority}\n"
                f"Assigned Role: {assignee}\n\n"
                f"Description:\n{description or 'No description provided.'}\n\n"
                f"Workspace: {workdir}\n"
                f"Git Branch: {branch_name or 'main'}\n\n"
                f"{memories_block}"
                f"🚨 CRITICAL: MERGE CONFLICT DETECTED WITH MAIN BRANCH\n"
                f"The latest changes from the main branch conflict with this task branch.\n"
                f"Conflicted files:\n{file_list_str}\n\n"
                f"Your goal as Builder (Conflict Resolution):\n"
                f"1. Inspect each conflicted file in {workdir}.\n"
                f"2. Resolve all conflict markers (`<<<<<<<`, `=======`, `>>>>>>>`), reconciling incoming changes with your task implementation.\n"
                f"3. Ensure NO conflict markers remain in any files.\n"
                f"4. Apply targeted edits (search/replace or localized chunk edits) rather than rewriting entire files to conserve tokens.\n"
                f"5. Run the repository test suites and linters to verify everything compiles and passes cleanly.\n"
                f"6. Hand off for re-review:\n"
                f"   hermes zerofactory move {task_id} blocked --reason \"review-required\"\n\n"
                f"NOTE: Do NOT run git commands (git add/commit/push). The factory dispatcher automatically verifies clean conflict resolution and commits with 'fix(merge): resolve merge conflicts with main' upon handoff.\n"
            )
        else:
            # Check if there are review comments for this task in task_comments
            review_comments_prompt = ""
            try:
                _db = Path(os.environ.get("ZEROFACTORY_DB") or get_db_path())
                if _db.exists():
                    with sqlite3.connect(str(_db)) as _c:
                        _c.row_factory = sqlite3.Row
                        _cur = _c.cursor()
                        _cur.execute(
                            "SELECT author, body, created_at FROM task_comments WHERE task_id = ? ORDER BY created_at ASC",
                            (task_id,)
                        )
                        _rows = _cur.fetchall()
                        _rev_rows = [
                            r for r in _rows
                            if "[github review" in r["body"].lower()
                            or "[github pr" in r["body"].lower()
                            or r["author"] in ("zf-reviewer", "reviewer")
                            or r["author"] != assignee
                        ]
                        if _rev_rows:
                            _cmt_blocks = []
                            for idx, r in enumerate(_rev_rows, 1):
                                _cmt_blocks.append(f"### Review Comment #{idx} (by @{r['author']}):\n{r['body']}")
                            review_comments_prompt = (
                                "🚨 CRITICAL: PULL REQUEST REVIEW COMMENTS TO ADDRESS\n"
                                "The reviewer / human has submitted the following review comments on your Pull Request.\n"
                                "You must address EVERY review comment in your implementation:\n\n"
                                + "\n\n".join(_cmt_blocks)
                                + "\n\n"
                            )
            except Exception as e:
                _log.debug("Could not inspect task_comments for worker prompt: %s", e)

            goal_instructions = (
                f"Your goal as Builder (Fix Review Comments):\n"
                f"1. Carefully address every review comment listed above in your workspace ({workdir}).\n"
                f"2. Apply targeted, concise code edits rather than rewriting or bloating files.\n"
                f"3. Run automated tests and linters in your workspace to verify correctness.\n"
                f"4. When finished, hand off for re-review:\n"
                f"   hermes zerofactory move {task_id} blocked --reason \"review-required\"\n"
                f"5. Provide a summary of how each review comment was resolved.\n\n"
                f"NOTE: Do NOT run git commands (git add/commit/push/checkout). The factory dispatcher automatically stages, commits, and pushes your fixes to the PR upon handoff.\n"
            ) if review_comments_prompt else (
                f"Your goal:\n"
                f"1. Read the task requirements and explore the codebase in your workspace ({workdir}).\n"
                f"2. Implement the required changes cleanly, adhering to repository patterns.\n"
                f"   - TOKEN EFFICIENCY: Apply targeted search/replace or hunk edits instead of rewriting entire files.\n"
                f"3. Verify your changes with tests, linters, or typechecks.\n"
                f"4. When finished, mark the task as complete using:\n"
                f"   hermes zerofactory move {task_id} done\n"
                f"   (or if human review or external dependencies are required, run:\n"
                f"   hermes zerofactory move {task_id} blocked --reason \"review-required\")\n"
                f"5. Provide a summary of your changes.\n\n"
                f"NOTE: Do NOT run git commands (git add/commit/push/checkout). Your worktree is already synced with latest main. The factory dispatcher automatically stages, commits, and opens PRs upon task completion.\n"
            )

            prompt = (
                f"Task ID: {task_id}\n"
                f"Title: {title}\n"
                f"Priority: {priority}\n"
                f"Assigned Role: {assignee}\n\n"
                f"Description:\n{description or 'No description provided.'}\n\n"
                f"Workspace: {workdir}\n"
                f"Git Branch: {branch_name or 'main'}\n\n"
                f"{memories_block}"
                f"{review_comments_prompt}"
                f"{goal_instructions}"
            )

    cmd = [
        hermes_bin,
        "-p", assignee,
        "--yolo",
        "--cli",
        "--accept-hooks",
        "chat",
        "-q", prompt
    ]

    log_dir = Path.home() / ".hermes" / "logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    log_file_path = log_dir / f"worker_{task_id}.log"

    env = os.environ.copy()
    env.pop("HERMES_KANBAN_TASK", None)
    env["HERMES_KANBAN_STOP_NUDGE"] = "0"
    env["HERMES_KANBAN_WORKSPACE"] = str(workdir)
    env["TERMINAL_CWD"] = str(workdir)
    env["HERMES_PROFILE"] = assignee
    profile_home = Path.home() / ".hermes" / "profiles" / assignee
    if profile_home.exists():
        env["HERMES_HOME"] = str(profile_home)
    env["PYTHONUNBUFFERED"] = "1"
    _d()._inject_langfuse_env(env)

    try:
        log_f = open(log_file_path, "ab")
        try:
            os.utime(log_file_path, None)
        except Exception:
            pass
        spawn_time = time.time()
        proc = subprocess.Popen(
            cmd,
            cwd=str(workdir),
            stdin=subprocess.DEVNULL,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            env=env,
            start_new_session=True,
        )
        log_f.close()
        _active_workers[task_id] = proc
        _log.info("Spawned %s worker for task %s (PID: %d, cwd: %s)", assignee, task_id, proc.pid, workdir)

        # Detect session_id from profile's state.db (only if started around this spawn).
        # Resolution goes through the shared helper so the dispatcher and the
        # dashboard agree on which state.db a profile owns.
        session_id = None
        state_db_path = getattr(_d(), "resolve_profile_state_db", resolve_profile_state_db)(assignee)
        if state_db_path is not None and state_db_path.exists():
            resolved_state = state_db_path.resolve()
            uri = resolved_state.as_uri() + "?mode=ro"
            # Poll up to 3 seconds for Hermes to initialize and record its session
            poll_attempts = 1 if os.environ.get("ZEROFACTORY_SKIP_WORKER_SPAWN") else 6
            for _ in range(poll_attempts):
                try:
                    try:
                        s_conn = sqlite3.connect(uri, uri=True, timeout=2.0)
                    except Exception:
                        s_conn = sqlite3.connect(str(resolved_state), timeout=2.0)
                    with closing(s_conn) as s_conn:
                        s_cur = s_conn.cursor()
                        # Match sessions started around this spawn that explicitly reference this task_id
                        # in the session title (e.g. "Task ID: zf-...") or working directory to avoid
                        # cross-task contamination when multiple workers run under the same profile.
                        s_cur.execute(
                            """
                            SELECT id FROM sessions
                            WHERE started_at >= ?
                              AND (
                                  (title IS NOT NULL AND title LIKE ?)
                                  OR (cwd IS NOT NULL AND cwd LIKE ?)
                              )
                            ORDER BY started_at DESC LIMIT 1
                            """,
                            (spawn_time - 2.0, f"%{task_id}%", f"%{task_id}%")
                        )
                        s_row = s_cur.fetchone()
                        if s_row:
                            session_id = s_row[0]
                            break
                except Exception:
                    pass
                if proc.poll() is not None:
                    break
                time.sleep(0.5)

        return proc.pid, session_id
    except Exception as e:
        _log.error("Failed to spawn %s worker for task %s: %s", assignee, task_id, e)
        return None, None
