"""Unit tests for scripts/zf_openwiki_gate.py."""

from __future__ import annotations

import importlib.util
import json
import os
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
GATE_PATH = REPO_ROOT / "scripts" / "zf_openwiki_gate.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("zf_openwiki_gate_mod", GATE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class TestOpenWikiGate(unittest.TestCase):
    def setUp(self):
        self.gate = _load_gate()
        self.td = tempfile.TemporaryDirectory()
        self.tmp = Path(self.td.name)
        self.state_file = self.tmp / "openwiki_state.json"
        os.environ["ZEROFACTORY_OPENWIKI_STATE"] = str(self.state_file)

    def tearDown(self):
        os.environ.pop("ZEROFACTORY_OPENWIKI_STATE", None)
        os.environ.pop("ZEROFACTORY_FORCE_OPENWIKI_UPDATE", None)
        self.td.cleanup()

    def test_missing_git_directory(self):
        wake, reason = self.gate.check_openwiki_gate(self.tmp, board_slug="test-board")
        self.assertFalse(wake)
        self.assertIn("Not a git repository", reason)

    def test_missing_openwiki_directory(self):
        (self.tmp / ".git").mkdir()
        wake, reason = self.gate.check_openwiki_gate(self.tmp, board_slug="test-board")
        self.assertFalse(wake)
        self.assertIn("no openwiki/ directory found", reason)

    def test_dirty_working_tree(self):
        (self.tmp / ".git").mkdir()
        (self.tmp / "openwiki").mkdir()
        with patch.object(self.gate, "_run_cmd") as mock_cmd:
            mock_cmd.return_value = " M file.py"
            wake, reason = self.gate.check_openwiki_gate(
                self.tmp, board_slug="test-board"
            )
            self.assertFalse(wake)
            self.assertIn("uncommitted changes", reason)

    def test_force_flag(self):
        (self.tmp / ".git").mkdir()
        (self.tmp / "openwiki").mkdir()
        with patch.dict(os.environ, {"ZEROFACTORY_FORCE_OPENWIKI_UPDATE": "1"}):
            wake, reason = self.gate.check_openwiki_gate(
                self.tmp, board_slug="test-board", auto_create_task=False
            )
            self.assertTrue(wake)
            self.assertIn("Force update requested", reason)

    def test_no_changes_same_head_sha(self):
        (self.tmp / ".git").mkdir()
        (self.tmp / "openwiki").mkdir()
        self.state_file.write_text(
            json.dumps({"test-board": {"last_scanned_sha": "abc12345"}}),
            encoding="utf-8",
        )
        with patch.object(self.gate, "_run_cmd") as mock_cmd:

            def _fake_run(cmd, cwd=None):
                if "status" in cmd:
                    return ""
                if "rev-parse" in cmd:
                    return "abc12345"
                return ""

            mock_cmd.side_effect = _fake_run
            wake, reason = self.gate.check_openwiki_gate(
                self.tmp, board_slug="test-board"
            )
            self.assertFalse(wake)
            self.assertIn("OpenWiki is up to date", reason)

    def test_only_openwiki_commits_skipped(self):
        (self.tmp / ".git").mkdir()
        (self.tmp / "openwiki").mkdir()
        self.state_file.write_text(
            json.dumps({"test-board": {"last_scanned_sha": "old12345"}}),
            encoding="utf-8",
        )
        with patch.object(self.gate, "_run_cmd") as mock_cmd:

            def _fake_run(cmd, cwd=None):
                if "status" in cmd:
                    return ""
                if "rev-parse" in cmd:
                    return "new67890"
                if "log" in cmd and ":(exclude)openwiki" in cmd:
                    return ""  # No non-openwiki commits
                return ""

            mock_cmd.side_effect = _fake_run
            wake, reason = self.gate.check_openwiki_gate(
                self.tmp, board_slug="test-board"
            )
            self.assertFalse(wake)
            self.assertIn("No code changes", reason)

    def test_branch_updates_detected_creates_task(self):
        (self.tmp / ".git").mkdir()
        (self.tmp / "openwiki").mkdir()
        db_file = self.tmp / "zerofactory.db"
        with sqlite3.connect(str(db_file)) as conn:
            conn.execute(
                "CREATE TABLE tasks (id TEXT PRIMARY KEY, board_slug TEXT, title TEXT, description TEXT, status TEXT, assignee TEXT, priority TEXT, created_at REAL, updated_at REAL)"
            )
            conn.commit()

        self.state_file.write_text(
            json.dumps({"test-board": {"last_scanned_sha": "old12345"}}),
            encoding="utf-8",
        )
        with patch.dict(os.environ, {"ZEROFACTORY_DB": str(db_file)}):
            with patch.object(self.gate, "_run_cmd") as mock_cmd:

                def _fake_run(cmd, cwd=None):
                    if "status" in cmd:
                        return ""
                    if "rev-parse" in cmd:
                        return "new67890"
                    if "log" in cmd and ":(exclude)openwiki" in cmd:
                        return "new67890 feat: add billing service\naaa1111 fix: auth token"
                    return ""

                mock_cmd.side_effect = _fake_run
                wake, reason = self.gate.check_openwiki_gate(
                    self.tmp, board_slug="test-board"
                )
                self.assertFalse(wake)
                self.assertIn("Detected 2 branch update(s)", reason)
                self.assertIn("created task", reason)
                self.assertIn("for zf-builder", reason)


    def test_active_task_in_todo_suppresses_wake(self):
        (self.tmp / ".git").mkdir()
        (self.tmp / "openwiki").mkdir()
        db_file = self.tmp / "zerofactory.db"
        with sqlite3.connect(str(db_file)) as conn:
            conn.execute(
                "CREATE TABLE tasks (id TEXT PRIMARY KEY, board_slug TEXT, title TEXT, status TEXT, created_at REAL)"
            )
            conn.execute(
                "INSERT INTO tasks (id, board_slug, title, status, created_at) VALUES ('task-1', 'test-board', 'docs(openwiki): sync architecture documentation', 'todo', 100)"
            )
            conn.commit()

        with patch.dict(os.environ, {"ZEROFACTORY_DB": str(db_file)}):
            wake, reason = self.gate.check_openwiki_gate(
                self.tmp, board_slug="test-board"
            )
            self.assertFalse(wake)
            self.assertIn("already has an active OpenWiki task 'task-1'", reason)
            self.assertIn("status 'todo'", reason)

    def test_active_task_in_running_and_blocked_suppresses_wake(self):
        (self.tmp / ".git").mkdir()
        (self.tmp / "openwiki").mkdir()
        db_file = self.tmp / "zerofactory.db"
        with sqlite3.connect(str(db_file)) as conn:
            conn.execute(
                "CREATE TABLE tasks (id TEXT PRIMARY KEY, board_slug TEXT, title TEXT, status TEXT, created_at REAL)"
            )
            conn.execute(
                "INSERT INTO tasks (id, board_slug, title, status, created_at) VALUES ('task-run', 'test-board', 'docs(openwiki): sync architecture documentation', 'running', 100)"
            )
            conn.commit()

        with patch.dict(os.environ, {"ZEROFACTORY_DB": str(db_file)}):
            wake, reason = self.gate.check_openwiki_gate(
                self.tmp, board_slug="test-board"
            )
            self.assertFalse(wake)
            self.assertIn("status 'running'", reason)

            # Change to blocked
            with sqlite3.connect(str(db_file)) as conn:
                conn.execute("UPDATE tasks SET status = 'blocked' WHERE id = 'task-run'")
                conn.commit()

            wake, reason = self.gate.check_openwiki_gate(
                self.tmp, board_slug="test-board"
            )
            self.assertFalse(wake)
            self.assertIn("status 'blocked'", reason)

    def test_completed_task_in_done_allows_wake_on_new_commits(self):
        (self.tmp / ".git").mkdir()
        (self.tmp / "openwiki").mkdir()
        db_file = self.tmp / "zerofactory.db"
        with sqlite3.connect(str(db_file)) as conn:
            conn.execute(
                "CREATE TABLE tasks (id TEXT PRIMARY KEY, board_slug TEXT, title TEXT, description TEXT, status TEXT, assignee TEXT, priority TEXT, created_at REAL, updated_at REAL)"
            )
            conn.execute(
                "INSERT INTO tasks (id, board_slug, title, status, created_at) VALUES ('task-done', 'test-board', 'docs(openwiki): sync architecture documentation', 'done', 100)"
            )
            conn.commit()

        self.state_file.write_text(
            json.dumps({"test-board": {"last_scanned_sha": "old12345"}}),
            encoding="utf-8",
        )
        with patch.dict(os.environ, {"ZEROFACTORY_DB": str(db_file)}):
            with patch.object(self.gate, "_run_cmd") as mock_cmd:

                def _fake_run(cmd, cwd=None):
                    if "status" in cmd:
                        return ""
                    if "rev-parse" in cmd:
                        return "new67890"
                    if "log" in cmd and ":(exclude)openwiki" in cmd:
                        return "new67890 feat: new feature"
                    return ""

                mock_cmd.side_effect = _fake_run
                wake, reason = self.gate.check_openwiki_gate(
                    self.tmp, board_slug="test-board"
                )
                self.assertFalse(wake)
                self.assertIn("Detected 1 branch update(s)", reason)
                self.assertIn("created task", reason)
                self.assertIn("for zf-builder", reason)

