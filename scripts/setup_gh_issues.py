#!/usr/bin/env python3
"""Setup script for Zero Factory GitHub Issue integration.

Provisions:
1. GitHub Issue Templates (.github/ISSUE_TEMPLATE/bug_report.yml, feature_request.yml, config.yml)
   with dedicated 'zerofactory' label to flag human AI investigation requests.
2. Standard GitHub repository labels (zerofactory, ai-investigate, bug, feature, p0-p3) via `gh` CLI.
"""

from __future__ import annotations

import argparse
import re
import shutil
import subprocess
from pathlib import Path
from typing import Any

BUG_REPORT_TEMPLATE = """name: "🐛 Bug Report (Zero Factory)"
description: Report a bug for Zero Factory AI to investigate, triage, and fix.
title: "[Bug]: "
labels: ["bug", "zerofactory"]
body:
  - type: markdown
    attributes:
      value: |
        ### Zero Factory AI Bug Report
        Issues labeled `zerofactory` are automatically picked up by Zero Factory's AI orchestrator into a human-gated **Triage** task.

  - type: textarea
    id: problem
    attributes:
      label: Problem Description
      description: What happened? Please provide a clear and concise description of the bug.
      placeholder: Describe the defect or error encountered...
    validations:
      required: true

  - type: textarea
    id: reproduction
    attributes:
      label: Steps to Reproduce
      description: Exact steps to reproduce the behavior so the AI and developer can inspect and test.
      placeholder: |
        1. Run '...'
        2. Execute '...'
        3. See error '...'
    validations:
      required: true

  - type: textarea
    id: expected
    attributes:
      label: Expected vs Actual Behavior
      description: What did you expect to happen versus what actually happened?
      placeholder: Expected ... but got ...
    validations:
      required: true

  - type: checkboxes
    id: ai_investigate
    attributes:
      label: Zero Factory AI Investigation
      description: Explicit human request for AI assistance.
      options:
        - label: "Request Zero Factory AI to investigate, reproduce, and prepare triage task"
          required: false
"""

FEATURE_REQUEST_TEMPLATE = """name: "🚀 Feature Request (Zero Factory)"
description: Propose a new feature for Zero Factory AI to investigate and implement.
title: "[Feature]: "
labels: ["feature", "zerofactory"]
body:
  - type: markdown
    attributes:
      value: |
        ### Zero Factory AI Feature Proposal
        Issues labeled `zerofactory` are triaged by Zero Factory's AI orchestrator to design architecture and decompose implementation tasks.

  - type: textarea
    id: summary
    attributes:
      label: Feature Summary & Motivation
      description: What problem does this solve, or what value does it bring?
      placeholder: As a developer / user, I want ... so that ...
    validations:
      required: true

  - type: textarea
    id: solution
    attributes:
      label: Proposed Solution / User Experience
      description: How should this work from a developer or end-user perspective?
      placeholder: Describe the desired interface, API, or workflow...
    validations:
      required: true

  - type: textarea
    id: constraints
    attributes:
      label: Technical Constraints & Acceptance Criteria
      description: Any architectural boundaries, performance requirements, or acceptance criteria?
      placeholder: Must conform to ...
    validations:
      required: false

  - type: checkboxes
    id: ai_investigate
    attributes:
      label: Zero Factory AI Investigation
      description: Explicit human request for AI assistance.
      options:
        - label: "Request Zero Factory AI to investigate, plan architecture, and prepare triage task"
          required: false
"""


def build_config_template(repo: str | None = None) -> str:
    repo_slug = (repo or "").strip()
    discussions_url = (
        f"https://github.com/{repo_slug}/discussions"
        if repo_slug and "/" in repo_slug
        else "https://github.com/hotcode-dev/zerofactory/discussions"
    )
    return f"""blank_issues_enabled: false
contact_links:
  - name: GitHub Discussions
    url: {discussions_url}
    about: Please ask questions, share ideas, and engage with the community in Discussions instead of opening an issue.
  - name: Zero Factory Documentation
    url: https://github.com/hotcode-dev/zerofactory
    about: Learn how Zero Factory AI agents triage and resolve issues.
"""


def _template_has_expected_labels(
    content: str, expected_labels: tuple[str, ...]
) -> bool:
    """Check whether template content carries the expected Zero Factory labels."""
    normalized = " ".join(content.split())
    return all(f'"{label}"' in normalized for label in expected_labels)


BUG_REPORT_EXPECTED_LABELS = ("bug", "zerofactory")
FEATURE_REQUEST_EXPECTED_LABELS = ("feature", "zerofactory")


def setup_github_issue_templates(
    target_dir: Path,
    repo: str | None = None,
    align: bool = False,
) -> list[Path]:
    """Write issue template YAML files into target_dir/.github/ISSUE_TEMPLATE/.

    When align=True, config.yml is always regenerated (repo-aware) while
    bug_report.yml / feature_request.yml are rewritten only when missing or
    when they lack the expected Zero Factory labels — preserving
    repo-customized templates that already carry the label.
    """
    template_dir = target_dir / ".github" / "ISSUE_TEMPLATE"
    template_dir.mkdir(parents=True, exist_ok=True)

    files_written = []

    def write_if_aligned(
        file_path: Path, template: str, expected_labels: tuple[str, ...]
    ) -> bool:
        if not file_path.is_file() or not _template_has_expected_labels(
            file_path.read_text(encoding="utf-8"), expected_labels
        ):
            file_path.write_text(template, encoding="utf-8")
            files_written.append(file_path)
            return True
        return False

    bug_file = template_dir / "bug_report.yml"
    feature_file = template_dir / "feature_request.yml"

    if align:
        write_if_aligned(bug_file, BUG_REPORT_TEMPLATE, BUG_REPORT_EXPECTED_LABELS)
        write_if_aligned(
            feature_file,
            FEATURE_REQUEST_TEMPLATE,
            FEATURE_REQUEST_EXPECTED_LABELS,
        )
    else:
        bug_file.write_text(BUG_REPORT_TEMPLATE, encoding="utf-8")
        files_written.append(bug_file)
        feature_file.write_text(FEATURE_REQUEST_TEMPLATE, encoding="utf-8")
        files_written.append(feature_file)

    # config.yml is always (re)generated so it stays repo-aware.
    effective_repo = repo or detect_repo_from_git(target_dir)
    config_file = template_dir / "config.yml"
    config_file.write_text(build_config_template(effective_repo), encoding="utf-8")
    files_written.append(config_file)

    return files_written


STANDARD_LABELS = [
    {
        "name": "zerofactory",
        "color": "7c3aed",
        "description": "Triggers Zero Factory AI triage and investigation",
    },
    {
        "name": "ai-investigate",
        "color": "8b5cf6",
        "description": "Request Zero Factory AI investigation",
    },
    {
        "name": "bug",
        "color": "d73a4a",
        "description": "Something isn't working",
    },
    {
        "name": "feature",
        "color": "a2eeef",
        "description": "New feature or enhancement",
    },
    {
        "name": "p0",
        "color": "b60205",
        "description": "Critical priority / blocker",
    },
    {
        "name": "p1",
        "color": "d93f0b",
        "description": "High priority",
    },
    {
        "name": "p2",
        "color": "fbca04",
        "description": "Medium priority",
    },
    {
        "name": "p3",
        "color": "0e8a16",
        "description": "Low priority",
    },
]


def detect_repo_from_git(cwd: Path) -> str | None:
    """Detect 'owner/repo' from git remote get-url origin."""
    try:
        res = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=5,
        )
        if res.returncode == 0:
            url = res.stdout.strip()
            # Match git@github.com:owner/repo.git or https://github.com/owner/repo.git
            m = re.search(r"github\.com[:/]([^/]+)/([^/.]+)(?:\.git)?$", url)
            if m:
                return f"{m.group(1)}/{m.group(2)}"
    except Exception:
        pass
    return None


def provision_github_labels(repo: str) -> dict[str, Any]:
    """Create or update required labels in the target GitHub repository via `gh` CLI."""
    if not shutil.which("gh"):
        return {
            "ok": False,
            "error": "GitHub CLI ('gh') is not installed or not in PATH.",
            "created": [],
            "failed": [],
        }

    created = []
    failed = []

    for lbl in STANDARD_LABELS:
        cmd = [
            "gh",
            "label",
            "create",
            lbl["name"],
            "--repo",
            repo,
            "--color",
            lbl["color"],
            "--description",
            lbl["description"],
            "--force",
        ]
        try:
            res = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                created.append(lbl["name"])
            else:
                failed.append(
                    f"{lbl['name']}: {res.stderr.strip() or res.stdout.strip()}"
                )
        except Exception as e:
            failed.append(f"{lbl['name']}: {e}")

    return {
        "ok": len(failed) == 0,
        "repo": repo,
        "created": created,
        "failed": failed,
    }


def setup_github_issues(
    repo_root: Path,
    repo: str | None = None,
    create_labels: bool = True,
    align: bool = False,
) -> dict[str, Any]:
    """Unified setup function for issue templates and repository labels.

    When align=True, existing templates are aligned rather than blindly
    clobbered: config.yml is always regenerated repo-aware, while
    bug_report.yml / feature_request.yml are rewritten only when missing or
    when they lack the expected Zero Factory labels.
    """
    repo_root = repo_root.resolve()
    effective_repo = repo or detect_repo_from_git(repo_root)

    # 1. Write issue templates
    templates = setup_github_issue_templates(
        repo_root, repo=effective_repo, align=align
    )

    # 2. Provision labels if requested and repo is available
    label_res: dict[str, Any] | None = None
    if create_labels:
        if effective_repo:
            label_res = provision_github_labels(effective_repo)
        else:
            label_res = {
                "ok": False,
                "error": "Could not determine target GitHub repository for label provisioning.",
                "created": [],
                "failed": [],
            }

    return {
        "ok": True,
        "repo_root": str(repo_root),
        "target_repo": effective_repo,
        "templates": [str(t) for t in templates],
        "label_results": label_res,
    }


def main():
    parser = argparse.ArgumentParser(
        description="Setup Zero Factory GitHub Issue templates and investigation labels."
    )
    parser.add_argument(
        "--path",
        default=".",
        help="Path to repository root (defaults to current working directory).",
    )
    parser.add_argument(
        "--repo",
        default=None,
        help="Target GitHub repository (owner/repo). Detected from git origin if omitted.",
    )
    parser.add_argument(
        "--no-labels",
        action="store_true",
        help="Skip creating labels in GitHub via gh CLI.",
    )
    parser.add_argument(
        "--align",
        action="store_true",
        help=(
            "Align with existing templates instead of clobbering: config.yml is "
            "always regenerated repo-aware; bug_report.yml / feature_request.yml "
            "are rewritten only when missing or when they lack the expected "
            "'zerofactory' label."
        ),
    )

    args = parser.parse_args()
    root = Path(args.path)

    print("\nZero Factory GitHub Issue Setup:")
    print(f"  Target Directory: {root.resolve()}")
    if args.align:
        print(
            "  Mode: align (preserve repo-customized templates that carry the zerofactory label)"
        )

    res = setup_github_issues(
        repo_root=root,
        repo=args.repo,
        create_labels=not args.no_labels,
        align=args.align,
    )

    print("\n✓ Generated/Aligned GitHub Issue Templates:")
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


if __name__ == "__main__":
    main()
