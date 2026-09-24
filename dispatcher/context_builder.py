"""Prompt context ingestion, memory digestion, and commit formatting for Zero Factory agents."""

from __future__ import annotations

import json
import os
import re
import sqlite3
import subprocess
from pathlib import Path
from typing import Optional, Tuple

from .config import _d, _log, get_db_path


def digest_reviewer_git_context(
    workspace_path: Path,
    branch_name: Optional[str] = None,
    max_diff_lines: int = 100,
    max_diff_chars: int = 4000
) -> str:
    """Extract pre-digested commits, diffstat, and code diff for reviewer prompt.

    Pre-computes git diffs and commit summaries in Python before waking zf-reviewer,
    eliminating multi-turn git exploration tool calls and saving substantial LLM tokens.
    """
    if not workspace_path.exists():
        return ""

    try:
        git_check = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            timeout=5
        )
        if git_check.returncode != 0 or git_check.stdout.strip() != "true":
            return ""
    except Exception:
        return ""

    default_branch = _d().get_default_branch(workspace_path)
    base_ref = f"origin/{default_branch}"
    try:
        verify_remote = subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", f"refs/remotes/{base_ref}"],
            cwd=str(workspace_path), timeout=5
        )
        if verify_remote.returncode != 0:
            verify_local = subprocess.run(
                ["git", "show-ref", "--verify", "--quiet", f"refs/heads/{default_branch}"],
                cwd=str(workspace_path), timeout=5
            )
            base_ref = default_branch if verify_local.returncode == 0 else "HEAD~1"
    except Exception:
        base_ref = "HEAD~1"

    # Find merge base between HEAD and base_ref
    merge_base = base_ref
    try:
        mb_res = subprocess.run(
            ["git", "merge-base", "HEAD", base_ref],
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            timeout=5
        )
        if mb_res.returncode == 0 and mb_res.stdout.strip():
            merge_base = mb_res.stdout.strip()
    except Exception:
        pass

    diff_range = f"{merge_base}..HEAD" if merge_base else "HEAD~1..HEAD"

    # 1. Commit log on branch
    log_summary = ""
    try:
        log_res = subprocess.run(
            ["git", "log", "-n", "10", "--oneline", diff_range],
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            timeout=5
        )
        if log_res.returncode == 0:
            log_summary = log_res.stdout.strip()
    except Exception:
        pass

    # Pathspec exclusions to avoid token explosion on auto-generated / lock / minified files
    excluded_diff_pathspecs = [
        ":!*.lock",
        ":!*package-lock.json",
        ":!*pnpm-lock.yaml",
        ":!*yarn.lock",
        ":!*.min.*",
        ":!*.map",
        ":!*.svg",
    ]

    # 2. Diffstat
    diffstat = ""
    try:
        stat_res = subprocess.run(
            ["git", "diff", "--stat", diff_range, "--", *excluded_diff_pathspecs],
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            timeout=5
        )
        if stat_res.returncode == 0 and stat_res.stdout.strip():
            diffstat = stat_res.stdout.strip()
        else:
            stat_fallback = subprocess.run(
                ["git", "diff", "--stat", "HEAD", "--", *excluded_diff_pathspecs],
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
                timeout=5
            )
            if stat_fallback.returncode == 0:
                diffstat = stat_fallback.stdout.strip()
    except Exception:
        pass

    # 3. Code Diff
    diff_content = ""
    try:
        diff_res = subprocess.run(
            ["git", "diff", "-U2", diff_range, "--", *excluded_diff_pathspecs],
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            timeout=5
        )
        raw_diff = diff_res.stdout.strip() if diff_res.returncode == 0 else ""
        if not raw_diff:
            diff_fallback = subprocess.run(
                ["git", "diff", "-U2", "HEAD", "--", *excluded_diff_pathspecs],
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
                timeout=5
            )
            raw_diff = diff_fallback.stdout.strip() if diff_fallback.returncode == 0 else ""

        if raw_diff:
            lines = raw_diff.splitlines()
            is_truncated = False
            if len(lines) > max_diff_lines:
                raw_diff = "\n".join(lines[:max_diff_lines])
                is_truncated = True
            if len(raw_diff) > max_diff_chars:
                raw_diff = raw_diff[:max_diff_chars]
                is_truncated = True
            if is_truncated:
                raw_diff += "\n... [diff truncated for token efficiency; inspect remaining diff with git diff in workspace]"
            diff_content = raw_diff
    except Exception:
        pass

    # 4. Check uncommitted modifications if any
    status_summary = ""
    try:
        status_res = subprocess.run(
            ["git", "status", "--porcelain"],
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            timeout=5
        )
        if status_res.returncode == 0 and status_res.stdout.strip():
            status_summary = status_res.stdout.strip()
    except Exception:
        pass

    if not log_summary and not diffstat and not diff_content:
        return ""

    sections = [
        "### 🔍 Pre-Digested PR Changes (Zero-Token Ingested)",
        f"- **Target Base Branch:** `{default_branch}`"
    ]
    if log_summary:
        sections.append(f"#### Commits on Feature Branch:\n```\n{log_summary}\n```")
    if diffstat:
        sections.append(f"#### Changed Files (Diffstat):\n```\n{diffstat}\n```")
    if diff_content:
        sections.append(f"#### Code Changes (Diff):\n```diff\n{diff_content}\n```")
    if status_summary:
        sections.append(f"#### Uncommitted Modifications:\n```\n{status_summary}\n```")

    return "\n\n".join(sections)


def digest_board_memories_context(
    board_slug: Optional[str],
    db_path: Optional[str] = None,
    limit: int = 8
) -> str:
    """Extract pre-digested repository memories, conventions, and gotchas for agent worker prompt.

    Pre-injects relevant repository knowledge learned from prior tasks directly into the agent
    prompt to prevent repeat mistakes and align code style with repository conventions.
    """
    if not board_slug:
        return ""

    target_db = Path(db_path or os.environ.get("ZEROFACTORY_DB") or get_db_path())
    if not target_db.exists():
        return ""

    try:
        with sqlite3.connect(str(target_db), timeout=2.0) as conn:
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            rows = cur.execute(
                """
                SELECT category, content, tags, author
                FROM board_memories
                WHERE board_slug = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (board_slug, limit)
            ).fetchall()

            if not rows:
                return ""

            lines = ["🧠 REPOSITORY KNOWLEDGE & CONVENTIONS (Learned from prior tasks):"]
            for r in rows:
                cat = r["category"] or "general"
                content = (r["content"] or "").strip().replace("\n", " ")
                if len(content) > 200:
                    content = content[:197] + "..."
                tag_str = ""
                try:
                    tags = json.loads(r["tags"] or "[]")
                    if tags and isinstance(tags, list):
                        tag_str = f" [tags: {', '.join(tags)}]"
                except Exception:
                    pass
                lines.append(f"- [{cat}] {content}{tag_str}")

            lines.append("Please adhere to these conventions and avoid known gotchas during execution.")
            return "\n".join(lines)
    except Exception as e:
        _log.debug("Could not digest board memories for %s: %s", board_slug, e)
        return ""


def format_conventional_message(title: str, task_id: str = "") -> Tuple[str, str]:
    """Format task title into Conventional Commits subject and body.

    Output format:
      subject: <type>(<scope>)?: <description>
      body: Task: <task_id>\n\n<title>
    """
    raw_title = title
    # 1. Strip role and priority badges
    cleaned = re.sub(r"\[(?:zf-builder|zf-reviewer|zf-orchestrator|PR Opened by .*?|P[0-3]|p[0-3])\]", "", title)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()

    # 2. Check if already conventional
    m = re.match(r"^(feat|fix|refactor|perf|test|docs|style|chore|ci|build)(\([^)]+\))?(!)?:\s*(.*)$", cleaned, re.IGNORECASE)
    if m:
        c_type = m.group(1).lower()
        c_scope = m.group(2) or ""
        c_desc = m.group(4).strip()
    else:
        # Check common prefixes
        prefix_rules = [
            (r"^(?:BUG\s*FIX|BUGFIX|HOTFIX)[:\s-]+(.*)$", "fix", ""),
            (r"^(?:FIX|BUG):\s*(.*)$", "fix", ""),
            (r"^(?:SECURITY|SEC)[:\s-]+(.*)$", "fix", "(security)"),
            (r"^(?:REFACTOR(?:ING)?|CLEANUP|DEDUP(?:LICATE)?)[:\s-]+(.*)$", "refactor", ""),
            (r"^(?:FEAT(?:URE)?|NEW)[:\s-]+(.*)$", "feat", ""),
            (r"^(?:ADD):\s*(.*)$", "feat", ""),
            (r"^(?:PERF(?:ORMANCE)?|OPTIMIZE|OPTIMIZATION)[:\s-]+(.*)$", "perf", ""),
            (r"^(?:TEST(?:S|ING)?)[:\s-]+(.*)$", "test", ""),
            (r"^(?:DOCS?|DOCUMENTATION)[:\s-]+(.*)$", "docs", ""),
            (r"^(?:CHORE|MAINTENANCE|DEPS|DEPENDENCIES)[:\s-]+(.*)$", "chore", ""),
            (r"^(?:CI|WORKFLOW|PIPELINE)[:\s-]+(.*)$", "ci", ""),
            (r"^(?:BUILD|RELEASE)[:\s-]+(.*)$", "build", ""),
        ]
        c_type, c_scope, c_desc = "chore", "", cleaned
        for pattern, t, s in prefix_rules:
            match = re.match(pattern, cleaned, re.IGNORECASE)
            if match:
                c_type = t
                c_scope = s
                c_desc = match.group(1).strip()
                break
        else:
            lower_cleaned = cleaned.lower()
            if re.search(r"\b(?:unit[\s_-]?tests?|e2e|integration[\s_-]?tests?|tests?)\b", lower_cleaned) and not any(lower_cleaned.startswith(p) for p in ("fix ", "patch ")):
                c_type = "test"
            elif any(lower_cleaned.startswith(p) for p in ("add ", "create ", "implement ", "support ", "introduce ", "integrate ")):
                c_type = "feat"
            elif any(lower_cleaned.startswith(p) for p in ("fix ", "resolve ", "patch ", "correct ", "prevent ", "handle ")):
                c_type = "fix"
            elif any(lower_cleaned.startswith(p) for p in ("refactor ", "extract ", "reorganize ", "simplify ", "deduplicate ", "clean ")):
                c_type = "refactor"
            elif any(lower_cleaned.startswith(p) for p in ("optimize ", "speed ", "accelerate ", "reduce ")):
                c_type = "perf"
            elif any(lower_cleaned.startswith(p) for p in ("doc ", "document ", "readme")):
                c_type = "docs"

    # 3. Infer scope if not provided
    if not c_scope:
        file_m = re.search(r"(?:in\s+)?(?:[\w\-]+/)*([a-zA-Z0-9_\-]+)\.(?:ts|js|py|go|rs|json|jsx|tsx|svelte|vue|md)\b", c_desc)
        if file_m:
            c_scope = f"({file_m.group(1)})"
        else:
            mod_m = re.match(r"^([a-zA-Z0-9_\-]+)\s+", c_desc)
            if mod_m and mod_m.group(1).lower() in ("dispatcher", "cron", "dashboard", "api", "auth", "worker", "agent"):
                c_scope = f"({mod_m.group(1).lower()})"

    # 4. Clean description
    if c_scope:
        scope_name = c_scope.strip("()")
        c_desc = re.sub(rf"\s*in\s+(?:[\w\-]+/)*{re.escape(scope_name)}\.[a-zA-Z0-9]+\b", "", c_desc, flags=re.IGNORECASE)
        c_desc = re.sub(rf"^{re.escape(scope_name)}[:\s]+", "", c_desc, flags=re.IGNORECASE)

    if len(c_desc) > 1 and c_desc[0].isupper() and not c_desc[1].isupper():
        c_desc = c_desc[0].lower() + c_desc[1:]

    c_desc = c_desc.rstrip(".").strip()

    subject_desc = c_desc
    if len(f"{c_type}{c_scope}: {c_desc}") > 72:
        no_parens = re.sub(r"\s*\([^)]*\)", "", c_desc).strip()
        if no_parens and len(f"{c_type}{c_scope}: {no_parens}") <= 80:
            subject_desc = no_parens

    subject = f"{c_type}{c_scope}: {subject_desc}".strip()

    body_lines = []
    if task_id:
        body_lines.append(f"Task: {task_id}")
    if raw_title.strip() != subject:
        body_lines.append(raw_title.strip())
    body = "\n\n".join(body_lines)

    return subject, body
