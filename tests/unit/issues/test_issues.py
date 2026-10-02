"""Unit tests for Zero Factory external issue tracker integration (GitHub & Jira)."""

import json
import sqlite3
import subprocess
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from dashboard.plugin_api import create_board, BoardCreate
from issues.base import ExternalIssue
from issues.github import GitHubIssueClient, parse_github_issue_ref
from issues.jira import JiraIssueClient, parse_jira_issue_ref
from issues.importer import import_external_issue, resolve_board_for_issue


class TestExternalIssueModel:
    def test_deterministic_dedup_key(self):
        issue_gh = ExternalIssue(
            source="github",
            id="42",
            key="#42",
            title="Fix login bug",
            repo_or_project="hotcode-dev/zerofactory",
        )
        assert issue_gh.to_dedup_key() == "issue:github:hotcode-dev/zerofactory:42"

        issue_jira = ExternalIssue(
            source="jira",
            id="PROJ-789",
            key="PROJ-789",
            title="Refactor auth service",
            repo_or_project="PROJ",
        )
        assert issue_jira.to_dedup_key() == "issue:jira:proj:proj-789"

    def test_deterministic_task_id(self):
        issue_gh = ExternalIssue(
            source="github",
            id="42",
            key="#42",
            title="Fix login bug",
            repo_or_project="hotcode-dev/zerofactory",
        )
        # Board code for "hotcode-dev-zerofactory" -> "hdz"
        assert issue_gh.to_task_id("hotcode-dev-zerofactory") == "zf-hdz-gh42"
        assert issue_gh.to_task_id(None) == "zf-gh42"

        issue_jira = ExternalIssue(
            source="jira",
            id="PROJ-123",
            key="PROJ-123",
            title="Update dependencies",
            repo_or_project="PROJ",
        )
        assert issue_jira.to_task_id("ntsd-sdp-compact") == "zf-nsc-jiproj123"

    def test_priority_inference(self):
        p0_issue = ExternalIssue(
            source="github", id="1", key="#1", title="Crash", labels=["bug", "critical"]
        )
        assert p0_issue.infer_priority() == "P0"

        p1_issue = ExternalIssue(
            source="github", id="2", key="#2", title="Error", labels=["bug"]
        )
        assert p1_issue.infer_priority() == "P1"

        p3_issue = ExternalIssue(
            source="github", id="3", key="#3", title="Typo", labels=["minor", "docs"]
        )
        assert p3_issue.infer_priority() == "P3"

        default_issue = ExternalIssue(
            source="github", id="4", key="#4", title="Feature", labels=["enhancement"]
        )
        assert default_issue.infer_priority() == "P2"

    def test_category_inference(self):
        sec_issue = ExternalIssue(
            source="github", id="1", key="#1", title="XSS", labels=["security"]
        )
        assert sec_issue.infer_category() == "security"

        perf_issue = ExternalIssue(
            source="github", id="2", key="#2", title="Slow queries", labels=["performance"]
        )
        assert perf_issue.infer_category() == "performance"

        refactor_issue = ExternalIssue(
            source="github", id="3", key="#3", title="Clean utils", labels=["refactor"]
        )
        assert refactor_issue.infer_category() == "refactoring"

        doc_issue = ExternalIssue(
            source="github", id="4", key="#4", title="Update README", labels=["docs"]
        )
        assert doc_issue.infer_category() == "documentation"

    def test_markdown_description_format(self):
        issue = ExternalIssue(
            source="github",
            id="42",
            key="#42",
            title="Fix broken link",
            body="Steps to reproduce:\n1. Click home\n2. 404",
            url="https://github.com/org/repo/issues/42",
            author="alice",
            labels=["bug", "p1"],
            assignees=["bob"],
        )
        desc = issue.to_markdown_description()
        assert "## Github Issue #42: Fix broken link" in desc
        assert "- **URL**: https://github.com/org/repo/issues/42" in desc
        assert "- **Author**: @alice" in desc
        assert "- **Labels**: `bug`, `p1`" in desc
        assert "Steps to reproduce:" in desc


class TestGitHubParserAndClient:
    def test_parse_github_issue_ref_url(self):
        repo, num = parse_github_issue_ref("https://github.com/octocat/Hello-World/issues/1347")
        assert repo == "octocat/Hello-World"
        assert num == "1347"

    def test_parse_github_issue_ref_short(self):
        repo, num = parse_github_issue_ref("octocat/Hello-World#1347")
        assert repo == "octocat/Hello-World"
        assert num == "1347"

    def test_parse_github_issue_ref_hash_and_num(self):
        repo, num = parse_github_issue_ref("#1347", default_repo="octocat/Hello-World")
        assert repo == "octocat/Hello-World"
        assert num == "1347"

        repo, num = parse_github_issue_ref("1347", default_repo="octocat/Hello-World")
        assert repo == "octocat/Hello-World"
        assert num == "1347"

    def test_parse_github_issue_ref_missing_repo_error(self):
        with pytest.raises(ValueError, match="requires a target repository"):
            parse_github_issue_ref("1347")

    def test_parse_github_issue_ref_invalid(self):
        with pytest.raises(ValueError, match="Invalid GitHub issue reference"):
            parse_github_issue_ref("not-an-issue")

    @patch("subprocess.run")
    def test_fetch_issue_success(self, mock_run):
        fake_data = {
            "number": 42,
            "title": "Fix token expiration",
            "body": "Tokens expire immediately on login.",
            "url": "https://github.com/my-org/my-repo/issues/42",
            "author": {"login": "devuser"},
            "state": "OPEN",
            "labels": [{"name": "bug"}, {"name": "p0"}],
            "assignees": [{"login": "alice"}],
        }
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(fake_data), stderr=""
        )

        client = GitHubIssueClient(default_repo="my-org/my-repo")
        issue = client.fetch_issue("42")

        assert issue.source == "github"
        assert issue.id == "42"
        assert issue.key == "#42"
        assert issue.title == "Fix token expiration"
        assert issue.body == "Tokens expire immediately on login."
        assert issue.author == "devuser"
        assert issue.labels == ["bug", "p0"]
        assert issue.assignees == ["alice"]
        assert issue.infer_priority() == "P0"

    @patch("subprocess.run")
    def test_fetch_issue_gh_error(self, mock_run):
        mock_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=1, stdout="", stderr="GraphQL: Could not resolve to an issue"
        )
        client = GitHubIssueClient(default_repo="my-org/my-repo")
        with pytest.raises(RuntimeError, match="Failed to fetch GitHub issue"):
            client.fetch_issue("9999")


class TestJiraParserAndClient:
    def test_parse_jira_issue_ref(self):
        proj, key = parse_jira_issue_ref("https://mycompany.atlassian.net/browse/PROJ-456")
        assert proj == "PROJ"
        assert key == "PROJ-456"

        proj, key = parse_jira_issue_ref("PROJ-456")
        assert proj == "PROJ"
        assert key == "PROJ-456"

        proj, key = parse_jira_issue_ref("456", default_project="PROJ")
        assert proj == "PROJ"
        assert key == "PROJ-456"

    def test_jira_mock_payload_parsing(self):
        client = JiraIssueClient(base_url="https://company.atlassian.net", default_project="AUTH")
        fake_jira_data = {
            "fields": {
                "summary": "Implement OAuth2 PKCE",
                "description": "Add PKCE validation for SPA clients",
                "reporter": {"displayName": "Security Lead"},
                "status": {"name": "In Progress"},
                "labels": ["security", "p1"],
                "assignee": {"displayName": "Dev Two"},
            }
        }
        issue = client.fetch_issue("AUTH-101", mock_data=fake_jira_data)
        assert issue.source == "jira"
        assert issue.id == "AUTH-101"
        assert issue.key == "AUTH-101"
        assert issue.title == "Implement OAuth2 PKCE"
        assert issue.url == "https://company.atlassian.net/browse/AUTH-101"
        assert issue.author == "Security Lead"
        assert issue.labels == ["security", "p1"]
        assert issue.infer_category() == "security"
        assert issue.infer_priority() == "P0"


class TestImporterIdempotencyAndDeterminism:
    @pytest.fixture(autouse=True)
    def setup_db(self, tmp_path, monkeypatch):
        db_file = tmp_path / "zerofactory.db"
        monkeypatch.setenv("ZEROFACTORY_DB", str(db_file))
        # Create a test board
        b_res = create_board(BoardCreate(git_url="https://github.com/hotcode-dev/zerofactory.git"))
        self.board_slug = b_res["slug"]
        self.db_path = db_file

    def test_import_issue_deterministic_and_idempotent(self):
        issue = ExternalIssue(
            source="github",
            id="42",
            key="#42",
            title="Crash when parsing bad yaml",
            body="YAML parse exception on empty file",
            url="https://github.com/hotcode-dev/zerofactory/issues/42",
            author="tester",
            labels=["bug", "critical"],
            repo_or_project="hotcode-dev/zerofactory",
        )

        # 1. First import
        res1 = import_external_issue(issue, board_slug=self.board_slug)
        assert res1["ok"]
        assert not res1["duplicate"]
        task_id = res1["id"]
        assert "gh42" in task_id
        assert res1["priority"] == "P0"
        assert res1["category"] == "bug-fix"

        # 2. Second import of same issue: must deterministically return duplicate
        res2 = import_external_issue(issue, board_slug=self.board_slug)
        assert res2["ok"]
        assert res2["duplicate"]
        assert res2["id"] == task_id

        # 3. Verify task metadata in DB has external_issue properly populated
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
            assert row is not None
            meta = json.loads(row["metadata"])
            assert "external_issue" in meta
            assert meta["external_issue"]["source"] == "github"
            assert meta["external_issue"]["id"] == "42"
            assert meta["external_issue"]["key"] == "#42"
            assert meta["dedup_key"] == issue.to_dedup_key()


class TestCliImportGhIssue:
    @patch("issues.github.subprocess.run")
    def test_cli_import_gh_issue_flow(self, mock_gh_run, tmp_path, monkeypatch, capsys):
        import argparse
        import __init__ as plugin_main

        db_file = tmp_path / "zerofactory.db"
        monkeypatch.setenv("ZEROFACTORY_DB", str(db_file))
        create_board(BoardCreate(git_url="https://github.com/my-org/my-repo.git"))

        fake_issue = {
            "number": 99,
            "title": "Bug in auth session",
            "body": "Auth session drops",
            "url": "https://github.com/my-org/my-repo/issues/99",
            "author": {"login": "tester"},
            "state": "OPEN",
            "labels": [{"name": "bug"}, {"name": "p0"}],
            "assignees": [],
        }
        mock_gh_run.return_value = subprocess.CompletedProcess(
            args=[], returncode=0, stdout=json.dumps(fake_issue), stderr=""
        )

        fake_ctx = MagicMock()
        fake_ctx.register_cli_command = MagicMock()
        plugin_main.register(fake_ctx)

        # Get the registered runner callback
        cmd_runner = fake_ctx.register_cli_command.call_args[1]["handler_fn"]

        args = argparse.Namespace(
            action="import-gh-issue",
            issue="99",
            repo="my-org/my-repo",
            board=None,
            status="triage",
            priority=None,
            assignee="unassigned",
            actor="test-user",
        )

        # First run: should successfully import
        cmd_runner(args)
        out = capsys.readouterr().out
        assert "Successfully imported GitHub issue #99" in out
        assert "P0" in out

        # Second run: should report duplicate
        cmd_runner(args)
        out2 = capsys.readouterr().out
        assert "[Duplicate Skipped]" in out2
