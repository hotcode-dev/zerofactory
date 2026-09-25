"""Unit tests for profile_manager.py."""

from __future__ import annotations

import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import yaml

import profile_manager as PM


class TestProfileManagerUnit(unittest.TestCase):
    """Test profile setup, script deployment, symlinks, and env/config updates."""

    def test_ensure_zf_profiles(self):
        """Bootstraps the 3 Zero Factory profiles under fake home."""
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            with patch("profile_manager.get_hermes_home", return_value=fake_home):
                res = PM.ensure_zf_profiles()
                self.assertIsInstance(res, dict)
                profiles_found = set(res["created"] + res["existing"] + res["updated"])
                for p in PM.ZF_PROFILES:
                    self.assertIn(p, profiles_found)
                    p_dir = fake_home / "profiles" / p
                    self.assertTrue(p_dir.exists())
                    self.assertTrue((p_dir / "SOUL.md").exists())
                    self.assertTrue((p_dir / "config.yaml").exists())

    def test_ensure_plugin_symlinks(self):
        """Creates symlink to zerofactory in ~/.hermes/plugins."""
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            with patch("profile_manager.get_hermes_home", return_value=fake_home):
                res = PM.ensure_plugin_symlinks()
                self.assertIsInstance(res, dict)
                root_plugins = fake_home / "plugins"
                self.assertTrue((root_plugins / "zerofactory").is_symlink())

    def test_ensure_script_files(self):
        """Copies background scripts as real files (not symlinks) for Hermes security check."""
        with tempfile.TemporaryDirectory() as td:
            fake_home = Path(td)
            with patch("profile_manager.get_hermes_home", return_value=fake_home):
                # Ensure profile directories exist first
                PM.ensure_zf_profiles()
                res = PM.ensure_script_files()
                self.assertIsInstance(res, dict)
                copied = res.get("copied", [])
                self.assertGreater(len(copied), 0)

                expected_scripts = ["zf_queue_watchdog.py", "zf_scanner_gate.py", "zf_daily_stats.py"]
                for s in expected_scripts:
                    root_s = fake_home / "scripts" / s
                    self.assertTrue(root_s.exists(), f"Missing {root_s}")
                    self.assertTrue(root_s.is_file())
                    self.assertFalse(root_s.is_symlink(), f"{root_s} should not be a symlink")

                    for role in PM.ZF_PROFILES:
                        prof_s = fake_home / "profiles" / role / "scripts" / s
                        self.assertTrue(prof_s.exists(), f"Missing {prof_s}")
                        self.assertFalse(prof_s.is_symlink())

    def test_update_env_file(self):
        """update_env_file preserves unrelated keys and comments."""
        with tempfile.TemporaryDirectory() as td:
            env_p = Path(td) / ".env"
            env_p.write_text("# Custom comment\nOPENROUTER_API_KEY=existing-key\nOTHER_VAR=123\n", encoding="utf-8")
            updates = {
                "HERMES_LANGFUSE_PUBLIC_KEY": "pk-lf-sample",
                "HERMES_LANGFUSE_SECRET_KEY": "sk-lf-sample",
            }
            PM.update_env_file(env_p, updates)
            lines = env_p.read_text(encoding="utf-8").splitlines()
            self.assertIn("# Custom comment", lines)
            self.assertIn("OPENROUTER_API_KEY=existing-key", lines)
            self.assertIn("OTHER_VAR=123", lines)
            self.assertIn("HERMES_LANGFUSE_PUBLIC_KEY=pk-lf-sample", lines)
            self.assertIn("HERMES_LANGFUSE_SECRET_KEY=sk-lf-sample", lines)

            # Update in-place
            PM.update_env_file(env_p, {"HERMES_LANGFUSE_PUBLIC_KEY": "pk-lf-modified"})
            lines2 = env_p.read_text(encoding="utf-8").splitlines()
            self.assertIn("HERMES_LANGFUSE_PUBLIC_KEY=pk-lf-modified", lines2)
            self.assertNotIn("HERMES_LANGFUSE_PUBLIC_KEY=pk-lf-sample", lines2)
            self.assertIn("OPENROUTER_API_KEY=existing-key", lines2)

    def test_update_config_yaml_plugins(self):
        """update_config_yaml_plugins adds and removes plugins cleanly."""
        with tempfile.TemporaryDirectory() as td:
            cfg_p = Path(td) / "config.yaml"
            cfg_p.write_text(yaml.dump({"plugins": {"enabled": ["zerofactory"]}, "model": {"default": "test"}}, sort_keys=False), encoding="utf-8")

            # Enable langfuse
            PM.update_config_yaml_plugins(cfg_p, enable_plugin="langfuse")
            loaded = yaml.safe_load(cfg_p.read_text(encoding="utf-8"))
            self.assertIn("langfuse", loaded["plugins"]["enabled"])
            self.assertIn("zerofactory", loaded["plugins"]["enabled"])

            # Disable langfuse
            PM.update_config_yaml_plugins(cfg_p, disable_plugin="langfuse")
            loaded_after = yaml.safe_load(cfg_p.read_text(encoding="utf-8"))
            self.assertNotIn("langfuse", loaded_after["plugins"]["enabled"])
            self.assertIn("zerofactory", loaded_after["plugins"]["enabled"])


if __name__ == "__main__":
    unittest.main()
