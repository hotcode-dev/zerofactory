"""Core dispatch loop, task claiming, scheduling, and background thread management."""

from __future__ import annotations

import fcntl
import json
import os
import re
import sqlite3
import subprocess
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from .config import (
    DEFAULT_MAX_ACTIVE_TASKS,
    DEFAULT_MAX_CONCURRENT_LLM_WORKERS,
    DEFAULT_MAX_CONCURRENT_WORKERS,
    DEFAULT_SCAN_ON_IDLE,
    DEFAULT_IDLE_SCAN_ACTIVE_THRESHOLD,
    DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES,
    DEFAULT_IDLE_SCAN_MAX_TODO,
    DISPATCH_INTERVAL_SECONDS,
    _active_scanners,
    _d,
    _dispatcher_lock,
    _dispatcher_thread,
    _last_idle_scan_times,
    _log,
    get_db_path,
    get_dispatcher_lock_path,
    is_worker_or_child_process,
    load_settings,
    normalize_assignee,
)


def run_dispatch_cycle(db_path: Optional[Path] = None) -> Dict[str, Any]:
    """Execute one full dispatch cycle."""
    _disp = _d()
    _subprocess = getattr(_disp, "subprocess", subprocess)

    if db_path is None:
        db_path = _disp.get_db_path()

    if not db_path.exists():
        return {"ok": False, "message": f"Database not found: {db_path}"}

    unblocked = 0
    promoted = 0
    dispatched = 0
    prs_opened = 0
    reaped = 0
    scans_triggered = 0
    now = int(time.time())

    with _dispatcher_lock:
        lock_path = _disp.get_dispatcher_lock_path()
        lock_fd: Optional[int] = None
        try:
            lock_flags = os.O_CREAT | os.O_RDWR
            if hasattr(os, "O_CLOEXEC"):
                lock_flags |= os.O_CLOEXEC
            lock_fd = os.open(str(lock_path), lock_flags, 0o666)
            fcntl.flock(lock_fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except (BlockingIOError, OSError):
            if lock_fd is not None:
                try:
                    os.close(lock_fd)
                except Exception:
                    pass
            _log.debug("Another process is currently running a Zero Factory dispatch cycle; skipping.")
            return {"ok": True, "skipped": True, "reason": "concurrent_cycle_active"}
        except Exception as e:
            _log.debug("Failed to acquire cross-process lock %s: %s", lock_path, e)
            if lock_fd is not None:
                try:
                    os.close(lock_fd)
                except Exception:
                    pass
            lock_fd = None

        try:
            with sqlite3.connect(str(db_path), timeout=15.0) as conn:
                conn.execute("PRAGMA busy_timeout=15000;")
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()

                # 0. Load global settings
                try:
                    settings = load_settings(cursor)
                except Exception:
                    settings = {}

                # 1. Unblock tasks whose parent dependencies are all done
                cursor.execute("""
                    SELECT id, title FROM tasks
                    WHERE status = 'blocked'
                    AND id IN (SELECT child_id FROM task_links)
                    AND NOT EXISTS (
                        SELECT 1 FROM task_links tl
                        JOIN tasks pt ON pt.id = tl.parent_id
                        WHERE tl.child_id = tasks.id AND pt.status != 'done'
                    )
                """)
                for row in cursor.fetchall():
                    cursor.execute("UPDATE tasks SET status = 'todo', updated_at = ? WHERE id = ?", (now, row["id"]))
                    cursor.execute(
                        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'unblock', 'All parent dependencies satisfied; moved to todo', ?)",
                        (row["id"], now)
                    )
                    unblocked += 1

                # 2. Reap finished workers and dispatch Todo tasks to Running
                reaped = _disp.reap_active_workers(cursor, now)
                _disp.reap_active_scanners()

                max_active_tasks = int(settings.get("max_active_tasks", DEFAULT_MAX_ACTIVE_TASKS))
                max_llm_workers = int(settings.get("max_concurrent_llm_workers", DEFAULT_MAX_CONCURRENT_LLM_WORKERS))

                cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'running'")
                active_count = cursor.fetchone()[0]
                llm_workers = _disp._global_llm_occupancy(active_count)

                # Per-board concurrent running caps (boards.max_concurrent_running, default 1).
                board_max_running: Dict[str, int] = {}
                try:
                    for b_row in cursor.execute(
                        "SELECT slug, max_concurrent_running FROM boards"
                    ).fetchall():
                        b_mcr = b_row["max_concurrent_running"]
                        board_max_running[str(b_row["slug"])] = max(1, int(b_mcr)) if b_mcr else DEFAULT_MAX_CONCURRENT_WORKERS
                except Exception:
                    board_max_running = {}

                running_per_board: Dict[str, int] = {}
                for rc_row in cursor.execute(
                    "SELECT board_slug, COUNT(*) AS cnt FROM tasks WHERE status = 'running' GROUP BY board_slug"
                ).fetchall():
                    running_per_board[str(rc_row["board_slug"] or "")] = rc_row["cnt"]

                if active_count < max_active_tasks and llm_workers < max_llm_workers:
                    cursor.execute("""
                        SELECT id, title, description, priority, workspace_path, assignee, tenant, branch_name, metadata, board_slug FROM tasks
                        WHERE status IN ('todo', 'ready')
                        ORDER BY CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 WHEN 'P3' THEN 3 ELSE 4 END, created_at ASC
                    """)
                    for row in cursor.fetchall():
                        if active_count >= max_active_tasks or llm_workers >= max_llm_workers:
                            break
                        task_id = str(row["id"])
                        assignee = normalize_assignee(row["assignee"] or "zf-builder")
                        if assignee == "human":
                            continue
                        title = row["title"] or ""
                        description = row["description"] or ""
                        priority = row["priority"] or "P2"
                        tenant = row["tenant"] if "tenant" in row.keys() else None
                        workspace_path = row["workspace_path"]
                        branch_name = row["branch_name"] if "branch_name" in row.keys() else None
                        board_slug = row["board_slug"] if "board_slug" in row.keys() else None
                        board_key = str(board_slug or "")
                        board_cap = board_max_running.get(board_key, DEFAULT_MAX_CONCURRENT_WORKERS)
                        board_active = running_per_board.get(board_key, 0)
                        if board_active >= board_cap:
                            _log.info("Task %s skipped (board %s at running limit %d/%d); will dispatch next cycle", task_id, board_key or "global", board_active, board_cap)
                            continue

                        if not workspace_path or not Path(workspace_path).exists():
                            wt = _disp.setup_worktree(cursor, task_id, title, assignee, tenant, db_path, board_slug=board_slug)
                            if wt:
                                workspace_path = wt

                        # Guardrail: Always pull git to latest before implement
                        if not os.environ.get("ZEROFACTORY_SKIP_GIT") and assignee == "zf-builder" and workspace_path and Path(workspace_path).exists():
                            _pre_verify_ok, _pre_verify_files, _pre_verify_err = _disp.check_unresolved_conflicts_safe(Path(workspace_path))
                            is_conflict_resolution = (
                                "[pr conflict]" in title.lower()
                                or "[merge conflict]" in title.lower()
                                or (_pre_verify_ok and bool(_pre_verify_files))
                            )
                            if not is_conflict_resolution:
                                if not _pre_verify_ok:
                                    _log.warning(
                                        "Task %s pre-implement conflict check unverifiable; skipping auto-merge: %s",
                                        task_id, _pre_verify_err,
                                    )
                                else:
                                    repo_for_task = _disp.resolve_task_repo_path(cursor, board_slug, tenant)
                                    if repo_for_task and repo_for_task.exists():
                                        merged_ok, conflict_files, merge_err = _disp.pull_and_merge_main(Path(workspace_path), repo_for_task)
                                        if not merged_ok:
                                            _log.warning("Task %s pre-implement merge conflict with main: %s (%s)", task_id, conflict_files, merge_err)
                                            _disp._handle_local_merge_conflict(cursor, task_id, title, workspace_path, conflict_files, now, merge_err)
                                            continue

                        # Atomic claim to prevent double-dispatch across processes
                        cursor.execute(
                            "UPDATE tasks SET status = 'running', updated_at = ? WHERE id = ? AND status IN ('todo', 'ready')",
                            (now, task_id)
                        )
                        if cursor.rowcount == 0:
                            continue
                        conn.commit()

                        try:
                            pid, session_id = _disp.spawn_agent_worker(
                                task_id, title, description, priority, assignee, workspace_path, branch_name, board_slug=row["board_slug"]
                            )
                        except Exception as e:
                            _log.error("Failed to spawn agent worker for %s: %s", task_id, e)
                            cursor.execute("UPDATE tasks SET status = 'todo', updated_at = ? WHERE id = ?", (now, task_id))
                            conn.commit()
                            continue

                        meta = {}
                        try:
                            meta = json.loads(row["metadata"] or "{}")
                        except Exception:
                            pass

                        sessions_list = meta.get("sessions")
                        if not isinstance(sessions_list, list):
                            sessions_list = []
                        for s in sessions_list:
                            if isinstance(s, dict) and s.get("status") == "ongoing":
                                s["status"] = "finished"
                                if not s.get("ended_at"):
                                    s["ended_at"] = now
                        sessions_list.append({
                            "session_id": session_id,
                            "agent": assignee,
                            "status": "ongoing",
                            "started_at": now,
                            "ended_at": None,
                            "pid": pid,
                        })
                        meta["sessions"] = sessions_list
                        if pid:
                            meta["worker_pid"] = pid
                        if session_id:
                            meta["session_id"] = session_id
                        meta["started_at"] = now

                        cursor.execute(
                            "UPDATE tasks SET metadata = ?, updated_at = ? WHERE id = ?",
                            (json.dumps(meta), now, task_id)
                        )
                        cursor.execute(
                            "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'start', ?, ?)",
                            (task_id, f"Agent {assignee} dispatched to work on task (PID: {pid or 'skipped'}, Session: {session_id or 'auto'})", now)
                        )
                        conn.commit()
                        running_per_board[board_key] = board_active + 1
                        active_count += 1
                        llm_workers += 1
                        dispatched += 1
                        promoted += 1

                # 3. Handle Blocked / Completed Tasks (PR generation & Reviewer handoff)
                if not os.environ.get("ZEROFACTORY_SKIP_GIT"):
                    cursor.execute("""
                        SELECT id, title, workspace_path, assignee, tenant, branch_name, pr_url, board_slug, status, metadata FROM tasks
                        WHERE (status != 'done' AND pr_url IS NOT NULL AND pr_url != '')
                           OR (status = 'blocked' AND assignee != 'zf-reviewer')
                           OR (status = 'done' AND assignee != 'zf-reviewer' AND workspace_path IS NOT NULL)
                    """)
                    for row in cursor.fetchall():
                        task_id = str(row["id"])
                        title = row["title"]
                        workspace_path = row["workspace_path"]
                        assignee = row["assignee"]
                        tenant = row["tenant"] if "tenant" in row.keys() else None
                        board_slug = row["board_slug"] if "board_slug" in row.keys() else None
                        raw_meta = row["metadata"] if "metadata" in row.keys() else "{}"
                        meta = {}
                        try:
                            meta = json.loads(raw_meta or "{}")
                        except Exception:
                            pass

                        if not workspace_path or not Path(workspace_path).exists():
                            repo_for_task = _disp.resolve_task_repo_path(cursor, board_slug, tenant)
                            if repo_for_task:
                                cand_wt = repo_for_task.parent / f"{repo_for_task.name}-worktrees" / task_id
                                if cand_wt.exists():
                                    workspace_path = str(cand_wt)
                                    cursor.execute("UPDATE tasks SET workspace_path = ? WHERE id = ?", (workspace_path, task_id))

                        repo_path = None
                        if workspace_path and Path(workspace_path).exists():
                            try:
                                rev_res = _subprocess.run(
                                    ["git", "rev-parse", "--path-format=absolute", "--git-common-dir"],
                                    cwd=workspace_path, capture_output=True, text=True, timeout=5
                                )
                                if rev_res.returncode == 0:
                                    common_git = Path(rev_res.stdout.strip())
                                    repo_path = common_git.parent if common_git.name == ".git" else common_git
                            except Exception:
                                pass

                        if not repo_path or not repo_path.exists():
                            repo_path = _disp.resolve_task_repo_path(cursor, board_slug, tenant)

                        if not repo_path or not repo_path.exists():
                            continue

                        if row["pr_url"]:
                            if row["status"] == "done" and (assignee == "zf-reviewer" or not workspace_path or not Path(workspace_path).exists()):
                                continue

                            try:
                                res = _subprocess.run(
                                    ["gh", "pr", "view", f"task/{task_id}", "--json", "reviewDecision,state,url,mergeable"],
                                    capture_output=True, text=True, cwd=str(repo_path), timeout=10
                                )
                                if res.returncode != 0 and row["pr_url"]:
                                    res = _subprocess.run(
                                        ["gh", "pr", "view", row["pr_url"], "--json", "reviewDecision,state,url,mergeable"],
                                        capture_output=True, text=True, cwd=str(repo_path), timeout=10
                                    )
                                if res.returncode == 0:
                                    pr_data = json.loads(res.stdout)
                                    pr_state = pr_data.get("state")
                                    decision = pr_data.get("reviewDecision")
                                    mergeable = pr_data.get("mergeable")
                                    current_pr_url = pr_data.get("url") or row["pr_url"] or ""

                                    if pr_state == "MERGED":
                                        _disp.stop_task_worker(task_id, cursor)
                                        _disp._remove_worktree(workspace_path, repo_path)
                                        _disp._delete_remote_branch(task_id, repo_path)
                                        cursor.execute(
                                            "UPDATE tasks SET status = 'done', workspace_path = NULL, updated_at = ? WHERE id = ?",
                                            (now, task_id)
                                        )
                                        cursor.execute(
                                            "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'merged', 'PR merged by human, task completed', ?)",
                                            (task_id, now)
                                        )
                                        continue
                                    elif pr_state == "CLOSED":
                                        _disp.stop_task_worker(task_id, cursor)
                                        _disp._remove_worktree(workspace_path, repo_path)
                                        _disp._delete_remote_branch(task_id, repo_path)
                                        cursor.execute(
                                            "UPDATE tasks SET status = 'done', workspace_path = NULL, updated_at = ? WHERE id = ?",
                                            (now, task_id)
                                        )
                                        cursor.execute(
                                            "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'closed', 'PR closed on GitHub, task archived', ?)",
                                            (task_id, now)
                                        )
                                        continue

                                    if meta.get("permanently_blocked") or row["status"] == "running":
                                        continue

                                    if assignee not in ("zf-reviewer", "human") and row["status"] in ("done", "blocked"):
                                        pass
                                    elif mergeable == "CONFLICTING":
                                        task_meta = {}
                                        try:
                                            cursor.execute("SELECT metadata FROM tasks WHERE id = ?", (task_id,))
                                            m_res = cursor.fetchone()
                                            if m_res and m_res[0]:
                                                task_meta = json.loads(m_res[0])
                                        except Exception:
                                            pass
                                        max_conflict_retries = int(os.environ.get("ZEROFACTORY_MAX_CONFLICT_RETRIES", "3"))
                                        if row["status"] == "blocked" and int(task_meta.get("conflict_retries", 0)) > max_conflict_retries:
                                            _log.debug("Task %s is blocked and already exceeded conflict retries (%d > %d); skipping PR conflict handling", task_id, int(task_meta.get("conflict_retries", 0)), max_conflict_retries)
                                        else:
                                            _disp._handle_pr_conflict_from_github(cursor, task_id, title, workspace_path, repo_path, tenant, db_path, board_slug, now)
                                        continue
                                    else:
                                        task_meta = {}
                                        try:
                                            cursor.execute("SELECT metadata FROM tasks WHERE id = ?", (task_id,))
                                            m_res = cursor.fetchone()
                                            if m_res and m_res[0]:
                                                task_meta = json.loads(m_res[0])
                                        except Exception:
                                            pass

                                        processed_cmt_ids = set(task_meta.get("processed_review_comment_ids", []))
                                        additional_reviewer_usernames: set[str] = set()
                                        if board_slug:
                                            try:
                                                board_row = cursor.execute(
                                                    "SELECT additional_reviewer_usernames FROM boards WHERE slug = ?",
                                                    (board_slug,),
                                                ).fetchone()
                                                if board_row and board_row[0]:
                                                    additional_reviewer_usernames = set(
                                                        json.loads(board_row[0])
                                                    )
                                            except (TypeError, ValueError, json.JSONDecodeError):
                                                _log.warning(
                                                    "Ignoring malformed additional reviewer allowlist for board %s",
                                                    board_slug,
                                                )
                                        all_pr_comments = _disp.fetch_pr_review_comments(
                                            repo_path=repo_path,
                                            pr_url=current_pr_url,
                                            task_id=task_id,
                                            pr_data=pr_data,
                                            additional_reviewer_usernames=additional_reviewer_usernames,
                                        )
                                        new_pr_comments = [c for c in all_pr_comments if c["comment_id"] not in processed_cmt_ids]

                                        actionable_comments = [
                                            c for c in new_pr_comments
                                            if not _disp.is_reviewer_approval_comment(c.get("body", ""), c.get("state"))
                                        ]
                                        approval_comments = [
                                            c for c in new_pr_comments
                                            if _disp.is_reviewer_approval_comment(c.get("body", ""), c.get("state"))
                                        ]

                                        has_actionable_feedback = bool(actionable_comments) or (decision == "CHANGES_REQUESTED")
                                        is_approved = (decision == "APPROVED") or (bool(approval_comments) and not has_actionable_feedback)

                                        if has_actionable_feedback and row["status"] in ("blocked", "todo"):
                                            for c in new_pr_comments:
                                                cmt_body = _disp.format_task_comment_body(c)
                                                cursor.execute(
                                                    "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, ?, ?, ?)",
                                                    (task_id, c["author"], cmt_body, now)
                                                )
                                                cursor.execute(
                                                    "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, ?, 'review_comment', ?, ?)",
                                                    (task_id, c["author"], f"PR review comment on {c.get('path') or 'PR'}: {c['body'][:80]}", now)
                                                )
                                                processed_cmt_ids.add(c["comment_id"])

                                                if board_slug and c.get("body"):
                                                    try:
                                                        try:
                                                            from ..dashboard.plugin_api import extract_and_record_memory
                                                        except (ImportError, ValueError):
                                                            from dashboard.plugin_api import extract_and_record_memory
                                                        extract_and_record_memory(conn, board_slug=board_slug, text=c["body"], task_id=task_id, author=c.get("author") or "zf-reviewer")
                                                    except Exception as _mem_e:
                                                        _log.debug("Auto-record memory from review comment failed: %s", _mem_e)

                                            task_meta["processed_review_comment_ids"] = list(processed_cmt_ids)

                                            _disp.stop_task_worker(task_id, cursor)
                                            _disp._remove_worktree(workspace_path, repo_path)
                                            match = re.search(r"\[PR Opened by (.*?)\]", title)
                                            author = match.group(1) if match else "zf-builder"
                                            author = normalize_assignee(author)
                                            clean_title = title.replace(" [Human Review]", "").replace("[Human Review]", "").strip()

                                            cursor.execute(
                                                "UPDATE tasks SET title = ?, assignee = ?, status = 'todo', metadata = ?, updated_at = ? WHERE id = ?",
                                                (clean_title, author, json.dumps(task_meta), now, task_id)
                                            )
                                            _disp.setup_worktree(cursor, task_id, clean_title, author, tenant, db_path, board_slug=board_slug)
                                            reason_text = (
                                                f"Review feedback received ({len(actionable_comments)} actionable comment(s)), routed back to {author}"
                                                if actionable_comments else "Changes requested by reviewer, routed back to author"
                                            )
                                            cursor.execute(
                                                "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'changes_requested', ?, ?)",
                                                (task_id, reason_text, now)
                                            )
                                            continue
                                        elif is_approved and row["status"] in ("blocked", "todo", "running"):
                                            for c in new_pr_comments:
                                                cmt_body = _disp.format_task_comment_body(c)
                                                cursor.execute(
                                                    "INSERT INTO task_comments (task_id, author, body, created_at) VALUES (?, ?, ?, ?)",
                                                    (task_id, c["author"], cmt_body, now)
                                                )
                                                cursor.execute(
                                                    "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, ?, 'review_comment', ?, ?)",
                                                    (task_id, c["author"], f"PR review comment on {c.get('path') or 'PR'}: {c['body'][:80]}", now)
                                                )
                                                processed_cmt_ids.add(c["comment_id"])

                                            task_meta["processed_review_comment_ids"] = list(processed_cmt_ids)
                                            task_meta["blocked_reason"] = "Reviewer approved; awaiting human merge"

                                            _disp.stop_task_worker(task_id, cursor)
                                            _disp._remove_worktree(workspace_path, repo_path)
                                            new_title = title if "[Human Review]" in title else f"{title} [Human Review]"
                                            cursor.execute(
                                                "UPDATE tasks SET title = ?, assignee = 'human', status = 'blocked', metadata = ?, workspace_path = NULL, updated_at = ? WHERE id = ?",
                                                (new_title, json.dumps(task_meta), now, task_id)
                                            )
                                            cursor.execute(
                                                "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'approved', 'Reviewer approved PR; task assigned to human awaiting merge', ?)",
                                                (task_id, now)
                                            )
                                            continue
                            except Exception as e:
                                _log.info("Reviewer PR check skipped for task %s: %s", task_id, e)

                        if assignee not in ("zf-reviewer", "human") and (not row["pr_url"] or row["status"] in ("done", "blocked")):
                            if meta.get("permanently_blocked") or meta.get("last_worker_failure"):
                                continue

                            if not workspace_path or not Path(workspace_path).exists():
                                continue
                            try:
                                _disp.clean_stale_git_locks(Path(workspace_path))
                                git_dir = _disp.get_git_dir(Path(workspace_path))
                                is_merging = bool(git_dir and (git_dir / "MERGE_HEAD").exists())

                                unmerged_files = _disp.get_unmerged_status_files(Path(workspace_path))
                                if is_merging or unmerged_files:
                                    files_to_scan = unmerged_files if unmerged_files else _disp.get_modified_status_files(Path(workspace_path))
                                    markers = _disp.check_files_for_conflict_markers(Path(workspace_path), files_to_scan)
                                    if markers:
                                        _log.warning("Task %s has unresolved conflict markers in worktree: %s", task_id, markers)
                                        _disp._handle_local_merge_conflict(cursor, task_id, title, workspace_path, markers, now, "Unresolved conflict markers in worktree")
                                        continue
                                    try:
                                        _subprocess.run(["git", "add", "."], check=True, cwd=workspace_path, capture_output=True, timeout=60)
                                    except Exception as e:
                                        _log.warning("Task %s failed to stage resolved conflict files: %s", task_id, e)

                                _initial_verified, initial_conflicts, _initial_err = _disp.check_unresolved_conflicts_safe(Path(workspace_path))
                                if not _initial_verified:
                                    _log.warning("Task %s worktree conflict state unverifiable; leaving blocked: %s", task_id, _initial_err)
                                    cursor.execute(
                                        "UPDATE tasks SET status = 'blocked', updated_at = ? WHERE id = ?",
                                        (now, task_id)
                                    )
                                    cursor.execute(
                                        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'conflict_unverifiable', ?, ?)",
                                        (task_id, f"Worktree conflict state could not be verified; left in blocked state (fail-closed): {_initial_err}", now)
                                    )
                                    conn.commit()
                                    continue
                                if initial_conflicts:
                                    _log.warning("Task %s has unresolved conflicts in worktree: %s", task_id, initial_conflicts)
                                    _disp._handle_local_merge_conflict(cursor, task_id, title, workspace_path, initial_conflicts, now, "Unresolved conflicts in worktree")
                                    continue

                                subject, commit_body = _disp.format_conventional_message(title, task_id)
                                status_res = _subprocess.run(["git", "status", "--porcelain"], cwd=workspace_path, capture_output=True, text=True, timeout=5)
                                if status_res.stdout.strip() or is_merging:
                                    _subprocess.run(["git", "add", "."], check=True, cwd=workspace_path, capture_output=True, timeout=60)
                                    commit_cmd = ["git", "commit"]
                                    if is_merging:
                                        commit_cmd.extend(["-m", "fix(merge): resolve merge conflicts with main", "-m", f"Task: {task_id}\n\n{title}"])
                                    else:
                                        commit_cmd.extend(["-m", subject, "-m", commit_body])
                                    _subprocess.run(
                                        commit_cmd,
                                        check=True, cwd=workspace_path, capture_output=True, timeout=60
                                    )

                                target_branch = ""
                                if board_slug:
                                    try:
                                        cursor.execute("SELECT target_branch FROM boards WHERE slug = ?", (board_slug,))
                                        b_row = cursor.fetchone()
                                        if b_row and b_row[0]:
                                            target_branch = str(b_row[0]).strip()
                                    except Exception:
                                        pass

                                merged_ok, conflict_files, merge_err = _disp.pull_and_merge_main(Path(workspace_path), repo_path, default_branch=target_branch or None)
                                if not merged_ok:
                                    _log.warning("Task %s merge conflict with main detected: %s (%s)", task_id, conflict_files, merge_err)
                                    _disp._handle_local_merge_conflict(cursor, task_id, title, workspace_path, conflict_files, now, merge_err)
                                    continue

                                _leftover_verified, leftover_conflicts, _leftover_err = _disp.check_unresolved_conflicts_safe(Path(workspace_path))
                                if not _leftover_verified:
                                    _log.warning("Task %s post-merge conflict state unverifiable; not pushing: %s", task_id, _leftover_err)
                                    cursor.execute(
                                        "UPDATE tasks SET status = 'blocked', updated_at = ? WHERE id = ?",
                                        (now, task_id)
                                    )
                                    cursor.execute(
                                        "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'conflict_unverifiable', ?, ?)",
                                        (task_id, f"Post-merge conflict state could not be verified; not pushing (fail-closed): {_leftover_err}", now)
                                    )
                                    conn.commit()
                                    continue
                                if leftover_conflicts:
                                    _disp._handle_local_merge_conflict(cursor, task_id, title, workspace_path, leftover_conflicts, now, "Leftover conflict markers detected after merge")
                                    continue

                                _subprocess.run(
                                    ["git", "push", "-u", "origin", f"task/{task_id}"],
                                    check=True, cwd=workspace_path, capture_output=True, timeout=180,
                                    env={**os.environ, "GIT_TERMINAL_PROMPT": "0"}
                                )

                                pr_url = row["pr_url"] or ""
                                if not pr_url:
                                    gh_view = _subprocess.run(["gh", "pr", "view", f"task/{task_id}", "--json", "url"], cwd=workspace_path, capture_output=True, text=True, timeout=30)
                                    if gh_view.returncode == 0:
                                        try:
                                            pr_url = json.loads(gh_view.stdout).get("url") or ""
                                        except Exception:
                                            pr_url = ""
                                    else:
                                        pr_title = subject
                                        pr_body = f"{commit_body}\n\nAutomated PR for task {task_id}\n\nCompleted by: @{assignee}"
                                        pr_cmd = ["gh", "pr", "create", "--title", pr_title, "--body", pr_body]
                                        if target_branch:
                                            pr_cmd.extend(["--base", target_branch])
                                        pr_res = _subprocess.run(pr_cmd, check=True, cwd=workspace_path, capture_output=True, text=True, timeout=180)
                                        pr_url = pr_res.stdout.strip()

                                _disp.stop_task_worker(task_id, cursor)
                                _disp._remove_worktree(workspace_path, repo_path)

                                new_title = title
                                for tag in ("[PR Conflict]", "[Merge Conflict]"):
                                    new_title = new_title.replace(f" {tag}", "").replace(tag, "").strip()
                                if not re.search(r"\[PR Opened by .*?\]", new_title):
                                    new_title = f"{new_title} [PR Opened by {assignee}]"

                                meta = {}
                                try:
                                    cursor.execute("SELECT metadata FROM tasks WHERE id = ?", (task_id,))
                                    m_row = cursor.fetchone()
                                    if m_row and m_row[0]:
                                        meta = json.loads(m_row[0])
                                        meta.pop("conflict_retries", None)
                                except Exception:
                                    pass

                                for key in ("worker_pid", "session_id", "started_at",
                                            "last_worker_failure", "worker_failure_retries",
                                            "blocked_reason", "permanently_blocked"):
                                    meta.pop(key, None)

                                cursor.execute(
                                    "UPDATE tasks SET title = ?, assignee = 'zf-reviewer', pr_url = ?, metadata = ?, status = 'todo', updated_at = ? WHERE id = ?",
                                    (new_title, pr_url, json.dumps(meta), now, task_id)
                                )
                                _disp.setup_worktree(cursor, task_id, new_title, "zf-reviewer", tenant, db_path, board_slug=board_slug)
                                cursor.execute(
                                    "INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'pr_opened', ?, ?)",
                                    (task_id, f"PR synced with main, routed to reviewer: {pr_url}", now)
                                )
                                prs_opened += 1
                            except subprocess.CalledProcessError as e:
                                err_msg = (e.stderr or "").strip() or str(e)
                                if "No commits between" in err_msg:
                                    _log.info("Task %s has no commits between main and branch; completing task without PR.", task_id)
                                    _disp.stop_task_worker(task_id, cursor)
                                    _disp._remove_worktree(workspace_path, repo_path)
                                    cursor.execute("UPDATE tasks SET workspace_path = NULL, status = 'done', updated_at = ? WHERE id = ?", (now, task_id))
                                    cursor.execute("INSERT INTO task_activity (task_id, actor, action, details, created_at) VALUES (?, 'dispatcher', 'completed_no_diff', 'No commits between branch and main; task marked done', ?)", (task_id, now))
                                else:
                                    _log.warning("Task %s commit/PR command failed: %s", task_id, err_msg)
                            except subprocess.TimeoutExpired as e:
                                _log.warning("Task %s commit/PR step timed out after %ss: %s (task left in pre-PR status; next cycle will retry idempotently)", task_id, e.timeout, e.cmd)
                            except Exception as e:
                                _log.warning("Task %s commit/PR failed: %s", task_id, e)

                # 4. Capacity-driven / Idle Improvement Scanner Check
                _disp.reap_active_scanners()
                active_count = cursor.execute("SELECT COUNT(*) FROM tasks WHERE status = 'running'").fetchone()[0]
                llm_workers = _disp._global_llm_occupancy(active_count)

                scan_on_idle = bool(settings.get("scan_on_idle", DEFAULT_SCAN_ON_IDLE))
                idle_active_threshold = int(settings.get("idle_scan_active_threshold", DEFAULT_IDLE_SCAN_ACTIVE_THRESHOLD))
                cooldown_seconds = int(settings.get("idle_scan_cooldown_minutes", DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES)) * 60
                max_todo = int(settings.get("idle_scan_max_todo", DEFAULT_IDLE_SCAN_MAX_TODO))

                if scan_on_idle:
                    try:
                        b_rows = cursor.execute("SELECT slug, git_url FROM boards").fetchall()
                    except Exception:
                        b_rows = []

                    todo_per_board: Dict[str, int] = {}
                    try:
                        for td_row in cursor.execute(
                            "SELECT board_slug, COUNT(*) AS cnt FROM tasks WHERE status = 'todo' GROUP BY board_slug"
                        ).fetchall():
                            todo_per_board[str(td_row["board_slug"] or "")] = td_row["cnt"]
                    except Exception:
                        pass

                    for b_row in b_rows:
                        if llm_workers >= max_llm_workers:
                            break
                        board_slug = str(b_row["slug"] or "")
                        if not board_slug:
                            continue
                        board_active_running = running_per_board.get(board_slug, 0)
                        board_todo_count = todo_per_board.get(board_slug, 0)

                        if board_active_running < idle_active_threshold and board_todo_count < max_todo:
                            if board_slug not in _active_scanners:
                                last_scan = _last_idle_scan_times.get(board_slug, 0)
                                if (now - last_scan) >= cooldown_seconds:
                                    repo_for_task = _disp.resolve_task_repo_path(cursor, board_slug, None)
                                    pid = _disp.spawn_board_scanner(board_slug, repo_for_task)
                                    if pid is not None:
                                        _last_idle_scan_times[board_slug] = now
                                        scans_triggered += 1
                                        llm_workers += 1
                                        _log.info(
                                            "Triggered idle improvement scan for board '%s' (running: %d < %d, todo: %d, PID: %d)",
                                            board_slug, board_active_running, idle_active_threshold, board_todo_count, pid
                                        )
                                    else:
                                        _log.warning(
                                            "Idle improvement scan spawn failed for board '%s'; cooldown NOT consumed, will retry next cycle",
                                            board_slug
                                        )

                conn.commit()

            return {
                "ok": True,
                "unblocked": unblocked,
                "promoted": promoted,
                "dispatched": dispatched,
                "reaped": reaped,
                "prs_opened": prs_opened,
                "scans_triggered": scans_triggered,
                "message": f"Dispatch cycle complete: {unblocked} unblocked, {promoted} promoted, {dispatched} dispatched to running, {reaped} reaped, {prs_opened} PRs opened, {scans_triggered} scans triggered."
            }
        except Exception as e:
            _log.error("Error during dispatch cycle: %s", e)
            return {"ok": False, "error": str(e)}
        finally:
            if lock_fd is not None:
                try:
                    fcntl.flock(lock_fd, fcntl.LOCK_UN)
                except Exception:
                    pass
                try:
                    os.close(lock_fd)
                except Exception:
                    pass


def _dispatcher_loop():
    """Background polling daemon thread for Kanban dispatch and periodic cron ticks."""
    while True:
        try:
            _d().run_dispatch_cycle()
        except Exception as e:
            _log.error("Unexpected error in background dispatcher loop: %s", e)

        try:
            try:
                from ..builtin_cron import is_cron_scheduler_enabled, tick_builtin_cron
            except (ImportError, ValueError):
                try:
                    from .builtin_cron import is_cron_scheduler_enabled, tick_builtin_cron  # type: ignore
                except (ImportError, ValueError):
                    from builtin_cron import is_cron_scheduler_enabled, tick_builtin_cron  # type: ignore
            if is_cron_scheduler_enabled():
                tick_builtin_cron()
            else:
                _log.debug("Builtin cron scheduler disabled; skipping periodic tick")
        except Exception as e:
            _log.debug("Builtin cron tick check: %s", e)

        time.sleep(DISPATCH_INTERVAL_SECONDS)


def start_background_dispatcher():
    """Start background dispatcher daemon thread if not already running."""
    if _d().is_worker_or_child_process():
        _log.debug("Skipping background dispatcher in worker/child process (profile=%s)", os.environ.get("HERMES_PROFILE"))
        return
    global _dispatcher_thread
    with _dispatcher_lock:
        if _dispatcher_thread is None or not _dispatcher_thread.is_alive():
            _dispatcher_thread = threading.Thread(target=_dispatcher_loop, name="ZeroFactoryKanbanDispatcher", daemon=True)
            _dispatcher_thread.start()
            _log.info("Zero Factory Kanban background dispatcher started (interval: %ss)", DISPATCH_INTERVAL_SECONDS)
