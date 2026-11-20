"""Zero-token deterministic anti-slop gate and diff hygiene scorecard for Zero Factory."""

from __future__ import annotations

import os
import re
import subprocess
from dataclasses import dataclass, field
from pathlib import Path

from .config import _d

EXCLUDED_DIFF_PATHSPECS = (
    ":!*.lock",
    ":!*package-lock.json",
    ":!*pnpm-lock.yaml",
    ":!*yarn.lock",
    ":!*.min.*",
    ":!*.map",
    ":!*.svg",
    ":!dashboard/dist/*",
)

CODE_EXTENSIONS = frozenset(
    {
        ".py",
        ".js",
        ".jsx",
        ".ts",
        ".tsx",
        ".mjs",
        ".cjs",
        ".go",
        ".rs",
        ".java",
        ".rb",
        ".sh",
    }
)

DEPENDENCY_FILENAMES = frozenset(
    {
        "package.json",
        "pyproject.toml",
        "setup.py",
        "setup.cfg",
        "Cargo.toml",
        "go.mod",
        "Gemfile",
        "pom.xml",
        "build.gradle",
        "build.gradle.kts",
    }
)

_RE_HUNK = re.compile(r"^@@ -\d+(?:,\d+)? \+(\d+)(?:,\d+)? @@")
_RE_DEBUG = re.compile(
    r"\b(?:breakpoint\s*\(|pdb\.set_trace\s*\(|import\s+pdb\b|debugger\s*;)"
)
_RE_PLACEHOLDER = re.compile(r"(?:#|//|/\*)\s*(?:TODO|FIXME|XXX|HACK)\b")
_RE_TEST_SKIP = re.compile(
    r"^\s*(?:@pytest\.mark\.skip\b|@unittest\.skip\b|(?:it|test|describe)\.skip\s*\(|x(?:it|test|describe)\s*\()"
)
_RE_SUPPRESSOR = re.compile(
    r"#\s*noqa\b|#\s*type:\s*ignore\b|@ts-(?:ignore|expect-error)\b|eslint-disable\b"
)
_RE_INLINE_EMPTY_EXCEPT = re.compile(r"\bexcept\b[^:]*:\s*pass\b")
_RE_EXCEPT_HEADER = re.compile(r"^\s*except\b[^:]*:\s*(?:#.*)?$")
_RE_BARE_PASS = re.compile(r"^\s*pass\s*(?:#.*)?$")

DEFAULT_WARN_NET_LINES = 400
DEFAULT_WARN_FILES = 12


@dataclass
class SlopFinding:
    rule: str
    severity: str  # "error" | "warning"
    file: str
    line: int
    snippet: str
    message: str


@dataclass
class DiffHygieneReport:
    files_changed: list[str] = field(default_factory=list)
    added_lines: int = 0
    deleted_lines: int = 0
    test_files_changed: list[str] = field(default_factory=list)
    test_lines_added: int = 0
    test_lines_deleted: int = 0
    dependency_files_touched: list[str] = field(default_factory=list)
    errors: list[SlopFinding] = field(default_factory=list)
    warnings: list[SlopFinding] = field(default_factory=list)

    @property
    def net_lines(self) -> int:
        return self.added_lines - self.deleted_lines


def is_test_file(rel_path: str) -> bool:
    """Return True if rel_path looks like an automated test file."""
    p = Path(rel_path)
    parts_lower = {part.lower() for part in p.parts[:-1]}
    if parts_lower & {"tests", "test", "__tests__", "spec", "specs"}:
        return True
    name = p.name.lower()
    if name == "conftest.py" or name.startswith("test_"):
        return True
    if name.endswith(("_test.py", "_test.go", "_test.rs")):
        return True
    return ".test." in name or ".spec." in name


def is_dependency_file(rel_path: str) -> bool:
    """Return True if rel_path is a package/dependency manifest."""
    name = Path(rel_path).name
    if name in DEPENDENCY_FILENAMES:
        return True
    return name.startswith("requirements") and name.endswith(".txt")


def _is_code_file(rel_path: str) -> bool:
    return Path(rel_path).suffix.lower() in CODE_EXTENSIONS


def _is_excluded_untracked(rel_path: str) -> bool:
    norm = rel_path.replace("\\", "/")
    name = Path(norm).name
    if norm.startswith("dashboard/dist/"):
        return True
    if name in ("package-lock.json", "pnpm-lock.yaml", "yarn.lock"):
        return True
    if name.endswith((".lock", ".map", ".svg")) or ".min." in name:
        return True
    return False


def _resolve_merge_base(workspace_path: Path, target_branch: str | None = None) -> str:
    default_branch = (target_branch or "").strip() or _d().get_default_branch(
        workspace_path
    )
    base_ref = f"origin/{default_branch}"
    try:
        r = subprocess.run(
            ["git", "show-ref", "--verify", "--quiet", f"refs/remotes/{base_ref}"],
            cwd=str(workspace_path),
            timeout=5,
        )
        if r.returncode != 0:
            r2 = subprocess.run(
                [
                    "git",
                    "show-ref",
                    "--verify",
                    "--quiet",
                    f"refs/heads/{default_branch}",
                ],
                cwd=str(workspace_path),
                timeout=5,
            )
            base_ref = default_branch if r2.returncode == 0 else "HEAD~1"
    except Exception:
        base_ref = "HEAD~1"

    try:
        mb = subprocess.run(
            ["git", "merge-base", "HEAD", base_ref],
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if mb.returncode == 0 and mb.stdout.strip():
            return mb.stdout.strip()
    except Exception:
        pass
    return base_ref


def _scan_added_lines(
    rel_path: str,
    lines_with_nums: list[tuple[int, str]],
    report: DiffHygieneReport,
) -> None:
    if not _is_code_file(rel_path):
        return

    test_file = is_test_file(rel_path)
    is_python = Path(rel_path).suffix.lower() == ".py"
    prev_was_except = False
    prev_line_num = -1

    for line_num, content in lines_with_nums:
        stripped = content.strip()
        if test_file:
            if _RE_TEST_SKIP.search(content):
                report.errors.append(
                    SlopFinding(
                        rule="test_disabled",
                        severity="error",
                        file=rel_path,
                        line=line_num,
                        snippet=stripped[:120],
                        message="Skipped/disabled test added; fix the test instead of skipping it.",
                    )
                )
            continue

        # Non-test code checks
        if _RE_DEBUG.search(content):
            report.errors.append(
                SlopFinding(
                    rule="debug_leftover",
                    severity="error",
                    file=rel_path,
                    line=line_num,
                    snippet=stripped[:120],
                    message="Debugger statement left in production code.",
                )
            )
        if _RE_PLACEHOLDER.search(content):
            report.errors.append(
                SlopFinding(
                    rule="placeholder_todo",
                    severity="error",
                    file=rel_path,
                    line=line_num,
                    snippet=stripped[:120],
                    message="Unfinished placeholder comment added in production code.",
                )
            )
        if _RE_SUPPRESSOR.search(content):
            report.warnings.append(
                SlopFinding(
                    rule="suppressor_added",
                    severity="warning",
                    file=rel_path,
                    line=line_num,
                    snippet=stripped[:120],
                    message="Lint or type-check suppressor added; verify it is justified.",
                )
            )
        if is_python:
            if _RE_INLINE_EMPTY_EXCEPT.search(content):
                report.warnings.append(
                    SlopFinding(
                        rule="empty_except",
                        severity="warning",
                        file=rel_path,
                        line=line_num,
                        snippet=stripped[:120],
                        message="Silent `except: pass` added; verify failure is not swallowed.",
                    )
                )
            elif (
                prev_was_except
                and line_num == prev_line_num + 1
                and _RE_BARE_PASS.match(content)
            ):
                report.warnings.append(
                    SlopFinding(
                        rule="empty_except",
                        severity="warning",
                        file=rel_path,
                        line=line_num,
                        snippet="except ...: pass",
                        message="Silent `except: pass` added; verify failure is not swallowed.",
                    )
                )
            prev_was_except = bool(_RE_EXCEPT_HEADER.match(content))
            prev_line_num = line_num


def analyze_workspace_diff(
    workspace_path: Path,
    target_branch: str | None = None,
    include_working_tree: bool = False,
) -> DiffHygieneReport:
    """Analyze git diff (and optionally untracked/working-tree files) for slop & hygiene metrics."""
    report = DiffHygieneReport()
    if not workspace_path.exists():
        return report

    try:
        git_check = subprocess.run(
            ["git", "rev-parse", "--is-inside-work-tree"],
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if git_check.returncode != 0 or git_check.stdout.strip() != "true":
            return report
    except Exception:
        return report

    merge_base = _resolve_merge_base(workspace_path, target_branch=target_branch)
    diff_cmd = ["git", "diff", "-U0"]
    diff_cmd.append(merge_base if include_working_tree else f"{merge_base}..HEAD")
    diff_cmd.extend(["--", *EXCLUDED_DIFF_PATHSPECS])

    raw_diff = ""
    try:
        res = subprocess.run(
            diff_cmd,
            cwd=str(workspace_path),
            capture_output=True,
            text=True,
            timeout=15,
        )
        if res.returncode == 0:
            raw_diff = res.stdout
    except Exception:
        raw_diff = ""

    files_seen: set[str] = set()
    test_files_seen: set[str] = set()
    dep_files_seen: set[str] = set()
    added_by_file: dict[str, list[tuple[int, str]]] = {}

    current_file: str | None = None
    current_line = 0

    for raw_line in raw_diff.splitlines():
        if raw_line.startswith("+++ "):
            target = raw_line[4:].strip()
            if target == "/dev/null":
                current_file = None
                continue
            if target.startswith("b/"):
                target = target[2:]
            current_file = target
            files_seen.add(current_file)
            if is_test_file(current_file):
                test_files_seen.add(current_file)
            if is_dependency_file(current_file):
                dep_files_seen.add(current_file)
            continue

        if raw_line.startswith("--- ") or raw_line.startswith("diff --git "):
            continue

        m = _RE_HUNK.match(raw_line)
        if m:
            current_line = int(m.group(1))
            continue

        if current_file is None:
            continue

        if raw_line.startswith("+"):
            line_text = raw_line[1:]
            report.added_lines += 1
            if current_file in test_files_seen:
                report.test_lines_added += 1
            added_by_file.setdefault(current_file, []).append((current_line, line_text))
            current_line += 1
        elif raw_line.startswith("-"):
            report.deleted_lines += 1
            if current_file in test_files_seen:
                report.test_lines_deleted += 1

    # Also inspect untracked files during packaging (before `git add .`)
    if include_working_tree:
        try:
            untracked_res = subprocess.run(
                ["git", "ls-files", "--others", "--exclude-standard"],
                cwd=str(workspace_path),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if untracked_res.returncode == 0:
                for rel in untracked_res.stdout.splitlines():
                    rel = rel.strip()
                    if not rel or rel in files_seen or _is_excluded_untracked(rel):
                        continue
                    fp = workspace_path / rel
                    if not fp.is_file() or fp.is_symlink():
                        continue
                    try:
                        if fp.stat().st_size > 512 * 1024:
                            continue
                        raw_bytes = fp.read_bytes()
                        if b"\x00" in raw_bytes[:1024]:
                            continue
                        text = raw_bytes.decode("utf-8", errors="replace")
                    except Exception:
                        continue
                    files_seen.add(rel)
                    is_tf = is_test_file(rel)
                    if is_tf:
                        test_files_seen.add(rel)
                    if is_dependency_file(rel):
                        dep_files_seen.add(rel)
                    file_lines = text.splitlines()
                    report.added_lines += len(file_lines)
                    if is_tf:
                        report.test_lines_added += len(file_lines)
                    added_by_file[rel] = [
                        (idx, ln) for idx, ln in enumerate(file_lines, start=1)
                    ]
        except Exception:
            pass

    report.files_changed = sorted(files_seen)
    report.test_files_changed = sorted(test_files_seen)
    report.dependency_files_touched = sorted(dep_files_seen)

    for rel_path, lines_with_nums in added_by_file.items():
        _scan_added_lines(rel_path, lines_with_nums, report)

    # Aggregate budget & test-integrity checks
    max_diff_env = os.environ.get("ZEROFACTORY_MAX_DIFF_LINES", "").strip()
    if max_diff_env:
        try:
            max_diff_cap = int(max_diff_env)
            if max_diff_cap > 0 and report.net_lines > max_diff_cap:
                report.errors.append(
                    SlopFinding(
                        rule="diff_budget_exceeded",
                        severity="error",
                        file="(diff)",
                        line=0,
                        snippet=f"+{report.added_lines}/-{report.deleted_lines} (net +{report.net_lines})",
                        message=f"Net added lines (+{report.net_lines}) exceeds ZEROFACTORY_MAX_DIFF_LINES={max_diff_cap}. Split or simplify the diff.",
                    )
                )
        except ValueError:
            pass

    if (
        report.net_lines > DEFAULT_WARN_NET_LINES
        or len(report.files_changed) > DEFAULT_WARN_FILES
    ):
        report.warnings.append(
            SlopFinding(
                rule="large_diff",
                severity="warning",
                file="(diff)",
                line=0,
                snippet=f"{len(report.files_changed)} files, net +{report.net_lines} lines",
                message="Large diff — scrutinize for scope creep or over-engineering.",
            )
        )

    if (
        report.test_lines_deleted > report.test_lines_added
        and report.test_lines_deleted >= 10
    ):
        report.warnings.append(
            SlopFinding(
                rule="net_test_deletion",
                severity="warning",
                file="(tests)",
                line=0,
                snippet=f"+{report.test_lines_added}/-{report.test_lines_deleted} test lines",
                message="More test lines were deleted than added; verify existing tests were not weakened.",
            )
        )

    return report


def run_deterministic_slop_gate(
    workspace_path: Path,
    target_branch: str | None = None,
) -> tuple[bool, str, int]:
    """Run zero-token deterministic anti-slop checks before commit/PR creation.

    Returns:
        (passed, summary_or_error, exit_code)
    """
    if os.environ.get("ZEROFACTORY_SKIP_SLOP_GATE"):
        return True, "ZEROFACTORY_SKIP_SLOP_GATE enabled", 0

    report = analyze_workspace_diff(
        workspace_path,
        target_branch=target_branch,
        include_working_tree=True,
    )
    if not report.errors:
        return (
            True,
            f"Slop gate passed ({len(report.files_changed)} files, +{report.added_lines}/-{report.deleted_lines})",
            0,
        )

    lines = [
        f"Deterministic anti-slop gate failed with {len(report.errors)} violation(s):"
    ]
    for err in report.errors[:15]:
        loc = f"{err.file}:{err.line}" if err.line > 0 else err.file
        lines.append(f"- [{err.rule}] {loc}: {err.message} (`{err.snippet}`)")
    if len(report.errors) > 15:
        lines.append(f"... and {len(report.errors) - 15} more violation(s).")
    lines.append(
        "Fix all violations above (remove debuggers, unresolved placeholder comments, or skipped tests) before handoff."
    )
    return False, "\n".join(lines), 1


def build_diff_hygiene_scorecard(
    workspace_path: Path,
    target_branch: str | None = None,
    is_diff_truncated: bool = False,
) -> str:
    """Build a compact Diff Hygiene Scorecard markdown block for zf-reviewer."""
    report = analyze_workspace_diff(
        workspace_path,
        target_branch=target_branch,
        include_working_tree=False,
    )
    if not report.files_changed:
        return ""

    net_sign = "+" if report.net_lines >= 0 else ""
    lines = [
        "#### 🛡️ Diff Hygiene Scorecard (Zero-Token Deterministic Check):",
        f"- **Scope:** {len(report.files_changed)} file(s) changed (`+{report.added_lines} / -{report.deleted_lines}`, net `{net_sign}{report.net_lines}`)",
        f"- **Tests:** {len(report.test_files_changed)} test file(s) (`+{report.test_lines_added} / -{report.test_lines_deleted}` lines)",
    ]

    if report.dependency_files_touched:
        deps = ", ".join(f"`{f}`" for f in report.dependency_files_touched)
        lines.append(
            f"- **⚠️ Dependency Manifests Modified:** {deps} (verify Rung 3/5 — no unnecessary packages)"
        )

    if is_diff_truncated:
        lines.append(
            "- **⚠️ Truncated Preview:** The inline diff below was truncated; run `git diff` in the workspace to inspect all changed files before approving."
        )

    # Summarize warnings compactly
    warning_bullets: list[str] = []
    suppressors = [w for w in report.warnings if w.rule == "suppressor_added"]
    empty_excepts = [w for w in report.warnings if w.rule == "empty_except"]
    other_warnings = [
        w for w in report.warnings if w.rule not in ("suppressor_added", "empty_except")
    ]

    for w in other_warnings:
        warning_bullets.append(f"[{w.rule}] {w.message} ({w.snippet})")
    if suppressors:
        locs = ", ".join(f"`{w.file}:{w.line}`" for w in suppressors[:5])
        extra = f" (+{len(suppressors) - 5} more)" if len(suppressors) > 5 else ""
        warning_bullets.append(
            f"[suppressor_added] {len(suppressors)} lint/type suppressor(s) added at {locs}{extra}"
        )
    if empty_excepts:
        locs = ", ".join(f"`{w.file}:{w.line}`" for w in empty_excepts[:5])
        extra = f" (+{len(empty_excepts) - 5} more)" if len(empty_excepts) > 5 else ""
        warning_bullets.append(
            f"[empty_except] {len(empty_excepts)} silent `except: pass` block(s) added at {locs}{extra}"
        )
    for err in report.errors[:5]:
        loc = f"`{err.file}:{err.line}`" if err.line > 0 else f"`{err.file}`"
        warning_bullets.append(f"[{err.rule}] {err.message} at {loc}")

    if warning_bullets:
        lines.append("- **Flags to Verify:**")
        for wb in warning_bullets:
            lines.append(f"  - {wb}")

    return "\n".join(lines)
