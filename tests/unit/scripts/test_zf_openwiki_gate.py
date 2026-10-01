"""Unit tests for scripts/zf_openwiki_gate.py."""

from __future__ import annotations

import importlib.util
import json
import os
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
                self.tmp, board_slug="test-board"
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
            self.assertIn("No code changes since last scan", reason)

    def test_branch_updates_detected_wakes_agent(self):
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
                    return "new67890 feat: add billing service\naaa1111 fix: auth token"
                return ""

            mock_cmd.side_effect = _fake_run
            wake, reason = self.gate.check_openwiki_gate(
                self.tmp, board_slug="test-board"
            )
            self.assertTrue(wake)
            self.assertIn("Detected 2 branch update(s)", reason)

            # Verify updated state file
            saved = json.loads(self.state_file.read_text(encoding="utf-8"))
            self.assertEqual(saved["test-board"]["last_scanned_sha"], "new67890")
