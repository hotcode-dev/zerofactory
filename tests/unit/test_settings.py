"""Unit tests for settings.py shared global settings definitions and parsing."""

from __future__ import annotations

import sqlite3
import tempfile
import unittest

import settings as S


class TestSettingsUnit(unittest.TestCase):
    """Test defaults, parsing, clamping, and fallbacks in settings.py."""

    def test_default_constants_and_keys_consistency(self):
        """Every key in SETTING_KEYS has a matching default value in DEFAULT_SETTING_VALUES."""
        for key in S.SETTING_KEYS:
            self.assertIn(key, S.DEFAULT_SETTING_VALUES)

        # Ensure types and values match defaults
        self.assertEqual(S.DEFAULT_SETTING_VALUES["max_active_tasks"], str(S.DEFAULT_MAX_ACTIVE_TASKS))
        self.assertEqual(S.DEFAULT_SETTING_VALUES["max_concurrent_llm_workers"], str(S.DEFAULT_MAX_CONCURRENT_LLM_WORKERS))
        self.assertEqual(S.DEFAULT_SETTING_VALUES["scan_on_idle"], "true" if S.DEFAULT_SCAN_ON_IDLE else "false")
        self.assertEqual(S.DEFAULT_SETTING_VALUES["idle_scan_active_threshold"], str(S.DEFAULT_IDLE_SCAN_ACTIVE_THRESHOLD))
        self.assertEqual(S.DEFAULT_SETTING_VALUES["idle_scan_cooldown_minutes"], str(S.DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES))
        self.assertEqual(S.DEFAULT_SETTING_VALUES["idle_scan_max_todo"], str(S.DEFAULT_IDLE_SCAN_MAX_TODO))
        self.assertEqual(S.DEFAULT_SETTING_VALUES["activity_retention_days"], str(S.DEFAULT_ACTIVITY_RETENTION_DAYS))
        self.assertEqual(S.DEFAULT_SETTING_VALUES["enable_cron_scheduler"], "true" if S.DEFAULT_ENABLE_CRON_SCHEDULER else "false")
        self.assertEqual(S.DEFAULT_SETTING_VALUES["auto_record_memory"], "true" if S.DEFAULT_AUTO_RECORD_MEMORY else "false")

    def test_load_settings_missing_table_returns_defaults(self):
        """When settings table is absent, load_settings returns module defaults."""
        conn = sqlite3.connect(":memory:")
        res = S.load_settings(conn)
        self.assertEqual(res["max_active_tasks"], S.DEFAULT_MAX_ACTIVE_TASKS)
        self.assertEqual(res["max_concurrent_llm_workers"], S.DEFAULT_MAX_CONCURRENT_LLM_WORKERS)
        self.assertEqual(res["scan_on_idle"], S.DEFAULT_SCAN_ON_IDLE)
        self.assertEqual(res["idle_scan_active_threshold"], S.DEFAULT_IDLE_SCAN_ACTIVE_THRESHOLD)
        self.assertEqual(res["idle_scan_cooldown_minutes"], S.DEFAULT_IDLE_SCAN_COOLDOWN_MINUTES)
        self.assertEqual(res["idle_scan_max_todo"], S.DEFAULT_IDLE_SCAN_MAX_TODO)
        self.assertEqual(res["activity_retention_days"], S.DEFAULT_ACTIVITY_RETENTION_DAYS)
        self.assertEqual(res["enable_cron_scheduler"], S.DEFAULT_ENABLE_CRON_SCHEDULER)
        self.assertEqual(res["auto_record_memory"], S.DEFAULT_AUTO_RECORD_MEMORY)
        conn.close()

    def test_load_settings_clamping_and_coercion(self):
        """Negative or zero values are clamped to their lower bounds."""
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.executemany("INSERT INTO settings VALUES (?, ?)", [
            ("max_active_tasks", "-5"),
            ("max_concurrent_llm_workers", "0"),
            ("idle_scan_active_threshold", "-1"),
            ("idle_scan_cooldown_minutes", "0"),
            ("idle_scan_max_todo", "-3"),
            ("activity_retention_days", "0"),
            ("scan_on_idle", "true"),
            ("enable_cron_scheduler", "1"),
            ("auto_record_memory", "yes"),
        ])
        conn.commit()

        res = S.load_settings(conn)
        # Clamped to >= 1
        self.assertEqual(res["max_active_tasks"], 1)
        self.assertEqual(res["max_concurrent_llm_workers"], 1)
        self.assertEqual(res["idle_scan_active_threshold"], 1)
        self.assertEqual(res["idle_scan_cooldown_minutes"], 1)
        self.assertEqual(res["activity_retention_days"], 1)
        # Clamped to >= 0
        self.assertEqual(res["idle_scan_max_todo"], 0)
        # Boolean parsing
        self.assertTrue(res["scan_on_idle"])
        self.assertTrue(res["enable_cron_scheduler"])
        self.assertTrue(res["auto_record_memory"])
        conn.close()

    def test_load_settings_boolean_falsy(self):
        """Falsy string representations parse to False."""
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.executemany("INSERT INTO settings VALUES (?, ?)", [
            ("scan_on_idle", "false"),
            ("enable_cron_scheduler", "0"),
            ("auto_record_memory", "no"),
        ])
        conn.commit()

        res = S.load_settings(conn)
        self.assertFalse(res["scan_on_idle"])
        self.assertFalse(res["enable_cron_scheduler"])
        self.assertFalse(res["auto_record_memory"])
        conn.close()

    def test_load_settings_langfuse_fields(self):
        """Langfuse configuration keys are loaded and validated."""
        conn = sqlite3.connect(":memory:")
        conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT)")
        conn.executemany("INSERT INTO settings VALUES (?, ?)", [
            ("langfuse_enabled", "true"),
            ("langfuse_base_url", "https://custom.langfuse.com"),
            ("langfuse_public_key", "pk-lf-test"),
            ("langfuse_secret_key", "sk-lf-test"),
            ("langfuse_capture_mode", "metadata"),
            ("langfuse_env", "staging"),
        ])
        conn.commit()

        res = S.load_settings(conn)
        self.assertTrue(res["langfuse_enabled"])
        self.assertEqual(res["langfuse_base_url"], "https://custom.langfuse.com")
        self.assertEqual(res["langfuse_public_key"], "pk-lf-test")
        self.assertEqual(res["langfuse_secret_key"], "sk-lf-test")
        self.assertEqual(res["langfuse_capture_mode"], "metadata")
        self.assertEqual(res["langfuse_env"], "staging")
        conn.close()


if __name__ == "__main__":
    unittest.main()
