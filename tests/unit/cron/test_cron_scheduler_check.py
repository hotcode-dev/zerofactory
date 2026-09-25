"""Tests for cron/scheduler_check.py: is_cron_scheduler_enabled and set_cron_scheduler_enabled."""

import os
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import yaml

from cron.scheduler_check import (
    is_cron_scheduler_enabled,
    set_cron_scheduler_enabled,
)
from cron.store import save_jobs_to_file, load_jobs_from_file
import settings


def test_is_cron_scheduler_enabled_defaults():
    """Verify default behavior when no overrides are set."""
    with tempfile.NamedTemporaryFile(suffix=".db") as tf:
        with patch.dict(os.environ, {"ZEROFACTORY_DB": tf.name}, clear=False):
            os.environ.pop("ZEROFACTORY_ENABLE_CRON_SCHEDULER", None)
            os.environ.pop("ZEROFACTORY_DISABLE_CRON_SCHEDULER", None)
            os.environ.pop("HERMES_CRON_ENABLED", None)
            os.environ.pop("ZEROFACTORY_CONFIG_FILE", None)
            os.environ.pop("HERMES_CONFIG_FILE", None)
            assert is_cron_scheduler_enabled() is True


def test_is_cron_scheduler_enabled_env_overrides():
    """Environment variables should have highest precedence."""
    with patch.dict(os.environ, {"ZEROFACTORY_ENABLE_CRON_SCHEDULER": "0"}):
        assert is_cron_scheduler_enabled() is False

    with patch.dict(os.environ, {"ZEROFACTORY_ENABLE_CRON_SCHEDULER": "false"}):
        assert is_cron_scheduler_enabled() is False

    with patch.dict(os.environ, {"ZEROFACTORY_ENABLE_CRON_SCHEDULER": "1"}):
        assert is_cron_scheduler_enabled() is True

    with patch.dict(os.environ, {"ZEROFACTORY_DISABLE_CRON_SCHEDULER": "1"}):
        assert is_cron_scheduler_enabled() is False

    with patch.dict(os.environ, {"HERMES_CRON_ENABLED": "0"}):
        assert is_cron_scheduler_enabled() is False


def test_is_cron_scheduler_enabled_db_settings():
    """Verify settings table inside DB toggles enablement."""
    with tempfile.NamedTemporaryFile(suffix=".db") as tf:
        with sqlite3.connect(tf.name) as conn:
            conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT, updated_at INTEGER)")
            conn.execute("INSERT INTO settings VALUES ('enable_cron_scheduler', 'false', 1000)")
            conn.commit()

            assert is_cron_scheduler_enabled(conn) is False

            # Verify settings module parses it
            loaded = settings.load_settings(conn)
            assert loaded["enable_cron_scheduler"] is False

            # Update to true
            conn.execute("UPDATE settings SET value = 'true' WHERE key = 'enable_cron_scheduler'")
            conn.commit()
            assert is_cron_scheduler_enabled(conn) is True


def test_is_cron_scheduler_enabled_yaml_configs():
    """Verify hermes and zerofactory config.yaml structures are inspected."""
    configs_to_test = [
        {"cron": {"enabled": False}},
        {"cron": {"scheduler": False}},
        {"cron": {"scheduler": {"enabled": False}}},
        {"cron": False},
        {"plugins": {"entries": {"zerofactory": {"cron_scheduler": False}}}},
        {"plugins": {"entries": {"zerofactory": {"enable_cron_scheduler": False}}}},
    ]
    for cfg_data in configs_to_test:
        with tempfile.NamedTemporaryFile(mode="w+", suffix=".yaml") as yf:
            yaml.dump(cfg_data, yf)
            yf.flush()
            with patch.dict(os.environ, {"ZEROFACTORY_CONFIG_FILE": yf.name}):
                assert is_cron_scheduler_enabled() is False, f"Failed for config: {cfg_data}"


def test_set_cron_scheduler_enabled_durably_persists_to_conn():
    """Verify caller-provided connection commits to disk."""
    with tempfile.NamedTemporaryFile(suffix=".db") as tf:
        dbfile = Path(tf.name)
        conn = sqlite3.connect(str(dbfile))
        conn.execute(
            "CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT, updated_at INTEGER)"
        )
        conn.execute(
            "INSERT INTO settings VALUES ('enable_cron_scheduler', 'true', 1000)"
        )
        conn.commit()

        with tempfile.NamedTemporaryFile(suffix=".json") as jf:
            jobs_path = Path(jf.name)
            with patch.dict(
                os.environ,
                {
                    "ZEROFACTORY_DB": str(dbfile),
                    "ZEROFACTORY_CRON_JOBS_FILE": str(jobs_path),
                },
            ):
                res = set_cron_scheduler_enabled(False, conn=conn)
                assert res["ok"] is True
                assert res["scheduler_enabled"] is False

                # Separate connection must read committed state
                conn2 = sqlite3.connect(str(dbfile))
                try:
                    row = conn2.execute(
                        "SELECT value FROM settings WHERE key='enable_cron_scheduler'"
                    ).fetchone()
                finally:
                    conn2.close()
                assert row is not None
                assert row[0] == "false"

                # Re-enable
                res_on = set_cron_scheduler_enabled(True, conn=conn)
                assert res_on["ok"] is True
                assert res_on["scheduler_enabled"] is True
                conn3 = sqlite3.connect(str(dbfile))
                try:
                    row_on = conn3.execute(
                        "SELECT value FROM settings WHERE key='enable_cron_scheduler'"
                    ).fetchone()
                finally:
                    conn3.close()
                assert row_on is not None
                assert row_on[0] == "true"

        conn.close()


def test_set_cron_scheduler_enabled_syncs_job_files():
    """Verify disabling scheduler pauses Zero Factory jobs and marks paused_by_master."""
    with tempfile.NamedTemporaryFile(suffix=".db") as tf_db, tempfile.NamedTemporaryFile(suffix=".json") as jf:
        db_path = Path(tf_db.name)
        jobs_path = Path(jf.name)
        with sqlite3.connect(str(db_path)) as conn:
            conn.execute("CREATE TABLE settings (key TEXT PRIMARY KEY, value TEXT, updated_at INTEGER)")
            conn.commit()

        initial_jobs = [
            {
                "id": "zero-factory-task-queue-check",
                "name": "Queue Check",
                "schedule": {"kind": "interval", "minutes": 120},
                "enabled": True,
                "state": "scheduled",
            },
            {
                "id": "user-custom-backup-job",
                "name": "User Backup",
                "schedule": {"kind": "interval", "minutes": 60},
                "enabled": True,
                "state": "scheduled",
            },
        ]
        save_jobs_to_file(jobs_path, initial_jobs)

        with patch.dict(
            os.environ,
            {
                "ZEROFACTORY_DB": str(db_path),
                "ZEROFACTORY_CRON_JOBS_FILE": str(jobs_path),
            },
        ):
            # Disable scheduler
            res = set_cron_scheduler_enabled(False)
            assert res["ok"] is True
            assert res["updated_targets"] == 1

            saved = load_jobs_from_file(jobs_path)
            zf_job = next(j for j in saved if j["id"] == "zero-factory-task-queue-check")
            user_job = next(j for j in saved if j["id"] == "user-custom-backup-job")

            assert zf_job["enabled"] is False
            assert zf_job["state"] == "paused"
            assert zf_job.get("paused_by_master") is True

            # Non-ZF job left untouched
            assert user_job["enabled"] is True
            assert user_job["state"] == "scheduled"

            # Re-enable scheduler
            res_on = set_cron_scheduler_enabled(True)
            assert res_on["ok"] is True
            saved_resumed = load_jobs_from_file(jobs_path)
            zf_job_resumed = next(j for j in saved_resumed if j["id"] == "zero-factory-task-queue-check")
            assert zf_job_resumed["enabled"] is True
            assert zf_job_resumed["state"] == "scheduled"
            assert "paused_by_master" not in zf_job_resumed
