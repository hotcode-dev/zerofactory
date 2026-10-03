"""Unit tests for dashboard/gh_issues_service.py and its routes."""

import sqlite3
from pathlib import Path

from dashboard.gh_issues_service import (
    GH_ISSUES_RELATIVE_DIR,
    BUG_REPORT_RELPATH,
    FEATURE_REQUEST_RELPATH,
    build_gh_issues_setup_task_prompt,
    check_board_gh_issues_status,
    create_gh_issues_setup_task,
)
from dashboard.plugin_api import BoardCreate, create_board
from dashboard.routes.boards import (
    get_board_gh_issues_status_endpoint,
    import_board_gh_issue_endpoint,
    setup_board_gh_issues_endpoint,
    sync_board_gh_issues_endpoint,
)


def test_build_gh_issues_setup_task_prompt():
    prompt = build_gh_issues_setup_task_prompt("test-board")
    assert GH_ISSUES_RELATIVE_DIR in prompt
    assert BUG_REPORT_RELPATH in prompt
    assert FEATURE_REQUEST_RELPATH in prompt
    assert "zerofactory" in prompt
    assert "test-board" in prompt
    assert "scripts/setup_gh_issues.py --path . --align" in prompt
    # Align semantics must be spelled out so the builder preserves
    # repo-customized templates that already carry the label.
    assert "ALWAYS regenerated" in prompt
    assert "preserved" in prompt


def test_gh_issues_status_missing_board(initialized_db: Path):
    res = check_board_gh_issues_status("nonexistent-board")
    assert res["ok"] is False
    assert res["has_gh_issues"] is False
    assert res["pending_task_id"] is None
    assert res["dedup_task_id"] is None


def test_gh_issues_status_and_task_lifecycle(initialized_db: Path, tmp_path: Path):
    repo_dir = tmp_path / "dummy_gh_repo"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()

    board_res = create_board(BoardCreate(git_url=str(repo_dir)))
    slug = board_res["slug"]

    # 1. Initial status: templates missing
    status = check_board_gh_issues_status(slug)
    assert status["ok"] is True
    assert status["has_gh_issues"] is False
    assert status["pending_task_id"] is None
    assert status["dedup_task_id"] is None

    # 2. Setup endpoint creates the P0 task; it must NOT write template files.
    ep_task = setup_board_gh_issues_endpoint(slug)
    assert ep_task["ok"] is True
    assert ep_task["already_exists"] is False
    assert ep_task["task_id"]
    assert ep_task.get("status") in ("triage", "todo", "running")
    assert ep_task["message"]
    assert not (repo_dir / ".github").exists(), "endpoint must not write files"

    task_id = ep_task["task_id"]

    # 3. Status now shows pending task (badge source) and dedup source
    status2 = check_board_gh_issues_status(slug)
    assert status2["pending_task_id"] == task_id
    assert status2["dedup_task_id"] == task_id

    # 4. Second call deduplicates to the same task
    setup_res2 = create_gh_issues_setup_task(slug)
    assert setup_res2["ok"] is True
    assert setup_res2["already_exists"] is True
    assert setup_res2["task_id"] == task_id

    # 5. Dedup wedge: a 'blocked' task (awaiting human merge) must NOT
    # permanently wedge regeneration — a new task gets created.
    with sqlite3.connect(str(initialized_db)) as conn:
        conn.execute("UPDATE tasks SET status = 'blocked' WHERE id = ?", (task_id,))
        conn.commit()

    status3 = check_board_gh_issues_status(slug)
    assert status3["pending_task_id"] == task_id  # badge stays truthful
    assert status3["dedup_task_id"] is None  # blocked != active work

    setup_res3 = create_gh_issues_setup_task(slug)
    assert setup_res3["ok"] is True
    assert setup_res3["already_exists"] is False
    assert setup_res3["task_id"] != task_id

    # 6. Endpoint status reflects both task generations
    ep_status = get_board_gh_issues_status_endpoint(slug)
    assert ep_status["ok"] is True
    assert ep_status["dedup_task_id"] == setup_res3["task_id"]


def test_sync_and_import_gh_issues_endpoints(
    initialized_db: Path, tmp_path: Path, monkeypatch
):
    from issues.base import ExternalIssue

    repo_dir = tmp_path / "dummy_gh_sync"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()

    board_res = create_board(
        BoardCreate(git_url="https://github.com/testowner/testrepo.git")
    )
    slug = board_res["slug"]

    mock_issue = ExternalIssue(
        source="github",
        id="42",
        key="#42",
        title="Test issue for AI investigation",
        issue_type="bug",
        body="Reproduction steps here",
        url="https://github.com/testowner/testrepo/issues/42",
        author="alice",
        state="open",
        labels=["bug", "zerofactory"],
        repo_or_project="testowner/testrepo",
    )

    class MockClient:
        def __init__(self, default_repo=None):
            self.default_repo = default_repo

        def fetch_investigation_issues(self, repo, label, state="open"):
            return [mock_issue]

        def fetch_issue(self, issue_ref, repo=None):
            return mock_issue

    import issues.github

    monkeypatch.setattr(issues.github, "GitHubIssueClient", MockClient)

    # 1. Sync endpoint
    sync_res = sync_board_gh_issues_endpoint(slug, label="zerofactory")
    assert sync_res["ok"] is True
    assert sync_res["imported_count"] == 1
    assert sync_res["duplicate_count"] == 0
    assert len(sync_res["imported"]) == 1

    # Syncing again should detect duplicate
    sync_res2 = sync_board_gh_issues_endpoint(slug, label="zerofactory")
    assert sync_res2["ok"] is True
    assert sync_res2["imported_count"] == 0
    assert sync_res2["duplicate_count"] == 1

    # 2. Import endpoint
    import_res = import_board_gh_issue_endpoint(slug, {"issue": "42"})
    assert import_res["ok"] is True
    assert import_res["duplicate"] is True


def test_setup_gh_issues_align(tmp_path: Path):
    """--align rewrites only missing/label-less templates; config.yml is
    always regenerated repo-aware; customized templates keep their content."""
    import scripts.setup_gh_issues as setup_mod

    repo_dir = tmp_path / "align_repo"
    template_dir = repo_dir / ".github" / "ISSUE_TEMPLATE"
    template_dir.mkdir(parents=True)

    custom_bug = (
        'name: "Custom Bug Form"\n'
        'labels: ["bug", "zerofactory"]\n'
        "body:\n  - type: textarea\n    id: problem\n"
    )
    labelless_feature = (
        'name: "Feature"\n'
        'labels: ["feature"]\n'
        "body:\n  - type: textarea\n    id: summary\n"
    )
    old_config = "blank_issues_enabled: true\n"
    (template_dir / "bug_report.yml").write_text(custom_bug, encoding="utf-8")
    (template_dir / "feature_request.yml").write_text(
        labelless_feature, encoding="utf-8"
    )
    (template_dir / "config.yml").write_text(old_config, encoding="utf-8")

    # 1. Default mode (no --align): always writes all three.
    res_default = setup_mod.setup_github_issues(
        repo_root=repo_dir, repo="acme/widgets", create_labels=False
    )
    assert res_default["ok"] is True
    assert len(res_default["templates"]) == 3
    bug_after_default = (template_dir / "bug_report.yml").read_text(encoding="utf-8")
    assert "bug_report" in bug_after_default or "Bug Report" in bug_after_default
    assert '"zerofactory"' in bug_after_default

    # 2. Align mode: customized bug_report.yml (has the label) is preserved,
    #    label-less feature_request.yml is rewritten, config is regenerated.
    (template_dir / "bug_report.yml").write_text(custom_bug, encoding="utf-8")
    (template_dir / "feature_request.yml").write_text(
        labelless_feature, encoding="utf-8"
    )
    res_align = setup_mod.setup_github_issues(
        repo_root=repo_dir, repo="acme/widgets", create_labels=False, align=True
    )
    assert res_align["ok"] is True

    assert (template_dir / "bug_report.yml").read_text(
        encoding="utf-8"
    ) == custom_bug, "custom template with the zerofactory label must be preserved"

    feature_aligned = (template_dir / "feature_request.yml").read_text(encoding="utf-8")
    assert '"feature"' in feature_aligned
    assert '"zerofactory"' in feature_aligned

    config_aligned = (template_dir / "config.yml").read_text(encoding="utf-8")
    assert "blank_issues_enabled: false" in config_aligned
    assert "https://github.com/acme/widgets/discussions" in config_aligned

    # 3. Align again with everything in place: bug/feature preserved, config
    #    still regenerated repo-aware (only config lands in the write list).
    res_align2 = setup_mod.setup_github_issues(
        repo_root=repo_dir, repo="acme/widgets", create_labels=False, align=True
    )
    written = [Path(p).name for p in res_align2["templates"]]
    assert written == ["config.yml"]
    assert (template_dir / "feature_request.yml").read_text(
        encoding="utf-8"
    ) == feature_aligned


def test_setup_gh_issues_cli_board_creates_task(initialized_db: Path, tmp_path: Path):
    """CLI 'setup-gh-issues --board' routes through task creation and writes
    no template files directly."""
    repo_dir = tmp_path / "cli_gh_repo"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()

    board_res = create_board(BoardCreate(git_url=str(repo_dir)))
    slug = board_res["slug"]

    import argparse
    import io
    from contextlib import redirect_stdout

    import __init__ as zf_cli

    parser = argparse.ArgumentParser(prog="hermes zerofactory")
    state = {}

    class MockCtx:
        def register_cli_command(ctx_self, name, help, setup_fn, handler_fn):
            setup_fn(parser)
            state["handler"] = handler_fn

    zf_cli.register(MockCtx())
    args = parser.parse_args(["setup-gh-issues", "--board", slug, "--actor", "tester"])
    buf = io.StringIO()
    with redirect_stdout(buf):
        state["handler"](args)
    out = buf.getvalue()

    assert "Created P0 GitHub Issues setup task" in out
    assert not (repo_dir / ".github").exists(), "CLI board path must not write files"

    # Second run deduplicates to the same task.
    buf2 = io.StringIO()
    with redirect_stdout(buf2):
        state["handler"](args)
    out2 = buf2.getvalue()
    assert "already active" in out2
