#!/usr/bin/env python3
"""ZeroFactory Codebase Scanner Pre-Screen & Wake-Gate.

Runs locally in the target repository workdir before the Hermes LLM scanner fires:
1. Compares current Git HEAD & working tree against `~/.hermes/scanner_state.json`.
2. If NO new commits or working tree modifications exist:
   Outputs `{"wakeAgent": false}`.
   Hermes detects this and SKIPS the LLM run entirely (0 tokens used!).
3. If new changes exist:
   Extracts recent git log, diffstat, modified file snippets, and existing task list.
   Outputs `{"wakeAgent": true}`.
   Hermes injects the pre-computed findings directly into prompt context, enabling
   single-turn task creation without multi-turn tool loops.
"""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

STATE_FILE = Path.home() / ".hermes" / "scanner_state.json"
DEFAULT_DB_PATH = Path.home() / ".hermes" / "zerofactory.db"


def _run_cmd(cmd: List[str], cwd: Optional[Path] = None) -> str:
    try:
        res = subprocess.run(
            cmd,
            cwd=str(cwd) if cwd else None,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            timeout=10
        )
        return res.stdout.strip() if res.returncode == 0 else ""
    except Exception:
        return ""


def load_state() -> Dict[str, Any]:
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding="utf-8"))
        except Exception:
            return {}
    return {}


def save_state(state: Dict[str, Any]) -> None:
    try:
        STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def get_existing_task_titles(board_slug: str) -> List[str]:
    db_path = Path(os.environ.get("ZEROFACTORY_DB") or DEFAULT_DB_PATH)
    if not db_path.exists():
        return []
    try:
        with sqlite3.connect(str(db_path), timeout=5.0) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT title FROM tasks WHERE board_slug = ? AND status != 'done' ORDER BY created_at DESC LIMIT 25",
                (board_slug,)
            )
            return [row[0] for row in cursor.fetchall()]
    except Exception:
        return []


def resolve_board_slug(repo_dir: Path) -> str:
    if len(sys.argv) > 1 and sys.argv[1].strip():
        return sys.argv[1].strip()
    if os.environ.get("ZEROFACTORY_BOARD"):
        return os.environ["ZEROFACTORY_BOARD"].strip()

    # Match repo directory against registered boards in zerofactory.db
    db_path = Path(os.environ.get("ZEROFACTORY_DB") or DEFAULT_DB_PATH)
    if db_path.exists():
        try:
            with sqlite3.connect(str(db_path), timeout=5.0) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT slug, name, git_url FROM boards")
                rows = cursor.fetchall()
                # 1. Match by slug == repo name or name == repo name
                for slug, name, _ in rows:
                    if repo_dir.name.lower() in (slug.lower(), (name or "").lower()):
                        return slug
                # 2. Match by git remote origin url
                remote_url = _run_cmd(["git", "config", "--get", "remote.origin.url"], cwd=repo_dir)
                if remote_url:
                    clean_remote = re.sub(r"\.git$", "", remote_url.strip().rstrip("/"))
                    for slug, _, git_url in rows:
                        if git_url and clean_remote in git_url:
                            return slug
                # Fallback to first board if available
                if rows:
                    return rows[0][0]
        except Exception:
            pass

    return repo_dir.name if repo_dir.name else "zerofactory"


def run_scanner_gate() -> int:
    repo_dir = Path.cwd()
    board_slug = resolve_board_slug(repo_dir)

    # Check if this is a git repo
    head_sha = _run_cmd(["git", "rev-parse", "HEAD"], cwd=repo_dir)
    status_porcelain = _run_cmd(["git", "status", "--porcelain", "-uno"], cwd=repo_dir)

    if not head_sha:
        # Not a git repo or git failed — allow normal run
        print(f"Warning: Not a valid git repository at {repo_dir}. Running standard inspection.")
        print(json.dumps({"wakeAgent": True}))
        return 0

    state = load_state()
    board_state = state.get(board_slug, {})
    last_sha = board_state.get("last_scanned_sha")
    last_status = board_state.get("last_status")

    is_same_commit = (head_sha == last_sha)
    is_same_status = (status_porcelain == last_status)

    # If HEAD is unchanged and working tree status is unchanged, suppress LLM execution
    if is_same_commit and is_same_status:
        # Output silent wake-gate signal
        print(f"NO_CHANGES_DETECTED: Repository at {head_sha[:8]} has had no new commits or working tree modifications since last check.")
        print(json.dumps({"wakeAgent": False}))
        return 0

    # Genuine changes detected! Update state
    board_state["last_scanned_sha"] = head_sha
    board_state["last_status"] = status_porcelain
    state[board_slug] = board_state
    save_state(state)

    # Collect pre-digested intelligence to pass to the LLM
    log_summary = _run_cmd(["git", "log", "-n", "5", "--oneline"], cwd=repo_dir)
    diffstat = _run_cmd(["git", "diff", "--stat", "HEAD~1..HEAD"], cwd=repo_dir)
    raw_diff = _run_cmd(["git", "diff", "-U2", "HEAD~1..HEAD"], cwd=repo_dir)

    # Cap diff to prevent prompt overflow
    diff_lines = raw_diff.splitlines()[:80]
    truncated_diff = "\n".join(diff_lines)
    if len(diff_lines) == 80:
        truncated_diff += "\n... [diff truncated for token efficiency]"

    # Check for uncommitted files
    is_worktree_clean = len(status_porcelain.strip()) == 0
    uncommitted_summary = ""
    if not is_worktree_clean:
        uncommitted_summary = f"### Uncommitted Changes:\n```\n{status_porcelain[:1000]}\n```\n"

    # Search for new TODO / FIXME in tracked files
    todo_matches = _run_cmd(["git", "grep", "-n", "-E", "TODO|FIXME|HACK", "--", "*.py", "*.ts", "*.js", "*.go", "*.rs"], cwd=repo_dir)
    todo_sample = "\n".join(todo_matches.splitlines()[:15]) if todo_matches else "None"

    # Fetch existing task titles to prevent duplicate suggestions
    existing_tasks = get_existing_task_titles(board_slug)
    tasks_block = "\n".join([f"- {t}" for t in existing_tasks]) if existing_tasks else "(No active tasks)"

    print("### 🔍 Pre-Screen Intelligence Package (Zero-Token Ingested)")
    print(f"**Repository:** `{repo_dir.name}` (Commit: `{head_sha[:8]}`)")
    print()
    print("#### Recent Commits:")
    print(f"```\n{log_summary}\n```")
    print()
    if uncommitted_summary:
        print(uncommitted_summary)
    if diffstat:
        print("#### Recent Diff Stat:")
        print(f"```\n{diffstat}\n```")
        print()
    if truncated_diff:
        print("#### Recent Code Changes:")
        print(f"```diff\n{truncated_diff}\n```")
        print()
    if todo_matches:
        print("#### Code Marker Warnings (TODO/FIXME):")
        print(f"```\n{todo_sample}\n```")
        print()
    print("#### Currently Open Kanban Tasks (DO NOT DUPLICATE THESE):")
    print(tasks_block)
    print()
    print("---")
    print("Instructions for Agent: Review the above pre-computed diff and tasks. If a genuine bug, refactoring, or improvement is warranted, create AT MOST 1 task in Kanban and finish. Do NOT run redundant git exploration commands.")
    print()

    # Emit wakeAgent: true to invoke LLM with this rich context
    print(json.dumps({"wakeAgent": True}))
    return 0


if __name__ == "__main__":
    sys.exit(run_scanner_gate())
