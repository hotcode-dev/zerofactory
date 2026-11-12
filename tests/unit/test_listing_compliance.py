"""Tests for Hermes listing compliance (NousResearch/hermes-agent#153625)."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from unittest.mock import MagicMock

import pytest
import yaml


def test_get_hermes_home_does_not_strip_profiles(tmp_path, monkeypatch):
    import paths
    import profile_manager

    custom_profile_home = tmp_path / "hermes" / "profiles" / "work"
    custom_profile_home.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(custom_profile_home))

    assert paths.get_hermes_home() == custom_profile_home.resolve()
    assert profile_manager.get_hermes_root() == custom_profile_home.resolve()
    assert profile_manager.get_hermes_home() == custom_profile_home.resolve()


def test_register_is_passive_and_never_creates_profiles_or_starts_dispatcher(
    tmp_path, monkeypatch
):
    import zerofactory

    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("ZEROFACTORY_DB", str(tmp_path / "missing_zerofactory.db"))

    start_mock = MagicMock()
    monkeypatch.setattr(zerofactory, "start_background_dispatcher", start_mock)

    ctx = MagicMock()
    zerofactory.register(ctx)

    assert not (hermes_home / "profiles").exists()
    assert not (tmp_path / "missing_zerofactory.db").exists()
    start_mock.assert_not_called()


def test_profile_manager_never_touches_root_or_non_zf_profiles(tmp_path, monkeypatch):
    import profile_manager

    hermes_home = tmp_path / "hermes"
    (hermes_home / "skills").mkdir(parents=True)
    (hermes_home / "plugins").mkdir(parents=True)
    (hermes_home / "config.yaml").write_text("model: gpt-4o\n", encoding="utf-8")
    (hermes_home / ".env").write_text("OPENAI_API_KEY=secret\n", encoding="utf-8")

    other_profile = hermes_home / "profiles" / "personal"
    other_profile.mkdir(parents=True)
    (other_profile / "config.yaml").write_text(
        "plugins:\n  enabled:\n    - langfuse\n", encoding="utf-8"
    )
    (other_profile / ".env").write_text("PERSONAL_KEY=keep\n", encoding="utf-8")

    monkeypatch.setenv("HERMES_HOME", str(hermes_home))

    profile_manager.ensure_zf_profiles()
    profile_manager.sync_langfuse_profiles({"langfuse_enabled": False})

    # Root and non-zf profile must remain untouched
    assert list((hermes_home / "skills").iterdir()) == []
    assert list((hermes_home / "plugins").iterdir()) == []
    assert not (hermes_home / "scripts").exists()
    assert (hermes_home / "config.yaml").read_text(
        encoding="utf-8"
    ) == "model: gpt-4o\n"
    assert (hermes_home / ".env").read_text(
        encoding="utf-8"
    ) == "OPENAI_API_KEY=secret\n"
    assert "langfuse" in (other_profile / "config.yaml").read_text(encoding="utf-8")
    assert (other_profile / ".env").read_text(encoding="utf-8") == "PERSONAL_KEY=keep\n"

    # Canonical zf-* profiles were created
    for role in profile_manager.ZF_PROFILES:
        assert (hermes_home / "profiles" / role / "config.yaml").is_file()


def test_builder_template_pins_openwiki_and_keeps_instruction_guard():
    tpl_path = (
        Path(__file__).resolve().parents[2] / "templates" / "zf-builder" / "config.yaml"
    )
    cfg = yaml.safe_load(tpl_path.read_text(encoding="utf-8"))

    assert (
        "security" not in cfg
        or cfg["security"].get("protected_instruction_files") is not False
    )
    args = cfg["mcp_servers"]["openwiki"]["args"]
    assert "openwiki@0.9.0" in args
    assert "openwiki" not in args


def test_minimal_child_env_and_default_no_yolo(tmp_path, monkeypatch):
    from dispatcher.worker_spawner import (
        build_minimal_child_env,
        is_unattended_approvals_enabled,
    )

    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("SECRET_PARENT_TOKEN", "should-not-leak")
    monkeypatch.setenv("ZEROFACTORY_CUSTOM_FLAG", "yes")
    monkeypatch.setenv("ZEROFACTORY_DB", str(tmp_path / "nonexistent.db"))

    assert is_unattended_approvals_enabled() is False

    env = build_minimal_child_env({"HERMES_PROFILE": "zf-builder"})
    assert "SECRET_PARENT_TOKEN" not in env
    assert env["HERMES_HOME"] == str(hermes_home.resolve())
    assert env["ZEROFACTORY_CUSTOM_FLAG"] == "yes"
    assert env["HERMES_PROFILE"] == "zf-builder"


def test_reaper_blocks_on_unattended_approval_failure(tmp_path, monkeypatch):
    from dispatcher.reaper import _is_unattended_approval_failure

    hermes_home = tmp_path / "hermes"
    logs_dir = hermes_home / "logs"
    logs_dir.mkdir(parents=True)
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("ZEROFACTORY_DB", str(tmp_path / "nonexistent.db"))

    (logs_dir / "worker_t1.log").write_text(
        "Error: Command requires approval in non-interactive mode\n",
        encoding="utf-8",
    )
    assert _is_unattended_approval_failure("t1") is True

    (logs_dir / "worker_t2.log").write_text(
        "AssertionError: expected 1 == 2\n",
        encoding="utf-8",
    )
    assert _is_unattended_approval_failure("t2") is False


def test_github_issue_automerge_labels_ignored(tmp_path, monkeypatch):
    from dispatcher.github_pr import is_task_automerge_enabled
    from issues.importer import import_external_issue
    from issues.base import ExternalIssue

    # External issue labels automerge/yolo must not enable automerge in github_pr
    task = {
        "tags": json.dumps(["issue:github"]),
        "metadata": json.dumps({"external_issue": {"labels": ["automerge", "yolo"]}}),
    }
    assert is_task_automerge_enabled(task, {"automerge": False}) is False

    # Local user-set tag still enables automerge
    local_task = {
        "tags": json.dumps(["automerge"]),
        "metadata": json.dumps({}),
    }
    assert is_task_automerge_enabled(local_task, {"automerge": False}) is True

    # import_external_issue must strip automerge/yolo labels from imported task.tags
    db_path = tmp_path / "zf.db"
    monkeypatch.setenv("ZEROFACTORY_DB", str(db_path))
    from dashboard.db import init_db

    init_db()
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO boards (slug, created_at, updated_at) VALUES ('b1', 1, 1)"
        )
        conn.execute(
            "INSERT INTO board_repositories (board_slug, repo_alias, git_url, created_at, updated_at) "
            "VALUES ('b1', 'main', 'https://example.com/repo.git', 1, 1)"
        )
        conn.commit()

    ext = ExternalIssue(
        id="42",
        source="github",
        key="#42",
        title="Test issue",
        body="Body",
        url="https://github.com/org/repo/issues/42",
        labels=["bug", "automerge", "yolo"],
        author="outsider",
        issue_type="bug",
    )
    res = import_external_issue(ext, board_slug="b1", db_path=db_path)
    assert res["ok"] is True
    task_id = res.get("id") or res["task"]["id"]
    with sqlite3.connect(str(db_path)) as conn:
        row = conn.execute("SELECT tags FROM tasks WHERE id = ?", (task_id,)).fetchone()
    imported_tags = json.loads(row[0])
    assert "tag:bug" in imported_tags
    assert "tag:automerge" not in imported_tags
    assert "tag:yolo" not in imported_tags


def test_setup_status_endpoint_is_read_only(tmp_path, monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from dashboard.plugin_api import router

    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("ZEROFACTORY_DB", str(tmp_path / "zf.db"))

    import profile_manager

    monkeypatch.setattr(
        profile_manager, "check_gh_auth_status", lambda use_cache=True: False
    )

    app = FastAPI()
    app.include_router(router, prefix="/api/plugins/zerofactory")
    client = TestClient(app)
    resp = client.get("/api/plugins/zerofactory/setup/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is True
    assert data["profiles_ready"] is False
    assert set(data["missing_profiles"]) == set(profile_manager.ZF_PROFILES)
    assert data["gh_authenticated"] is False
    assert data["dispatcher_running"] is False
    # Read-only: must not have created profiles
    assert not (hermes_home / "profiles").exists()
