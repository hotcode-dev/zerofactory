"""Unit tests for scripts/zf_daily_stats.py."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import re
import sqlite3
import tempfile
import time as _time
import unittest
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent


class TestZfDailyStatsUnit(unittest.TestCase):
    """Test duration resolution and daily stats formatting."""

    @classmethod
    def setUpClass(cls):
        script_path = REPO_ROOT / "scripts" / "zf_daily_stats.py"
        spec = importlib.util.spec_from_file_location("zf_daily_stats_under_test", script_path)
        cls.mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(cls.mod)

    def test_running_since_resolution_priority(self):
        """started_at wins, then updated_at, then created_at."""
        now = 2_000_000_000
        # started_at (recent) must beat a stale updated_at
        rt_a = {
            "id": "t", "updated_at": now - 10, "created_at": now - 999,
            "metadata": json.dumps({"started_at": now - 47 * 60}),
        }
        self.assertEqual(self.mod._resolve_running_since(rt_a, now), now - 47 * 60)

        # No started_at -> fall back to updated_at
        rt_b = {
            "id": "t", "updated_at": now - 120, "created_at": now - 999, "metadata": "{}",
        }
        self.assertEqual(self.mod._resolve_running_since(rt_b, now), now - 120)

        # No started_at and no updated_at (0/unset) -> fall back to created_at
        rt_c = {
            "id": "t", "updated_at": 0, "created_at": now - 999, "metadata": "not-json",
        }
        self.assertEqual(self.mod._resolve_running_since(rt_c, now), now - 999)

    def test_daily_stats_inflight_duration_uses_started_at(self):
        """In-flight duration derives from metadata.started_at and clamps clock skew."""
        with tempfile.TemporaryDirectory() as td:
            db_path = Path(td) / "stats.db"
            conn = sqlite3.connect(str(db_path))
            conn.executescript(
                "CREATE TABLE boards ("
                " slug TEXT PRIMARY KEY, description TEXT DEFAULT '', git_url TEXT DEFAULT '',"
                " created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);"
                "CREATE TABLE tasks ("
                " id TEXT PRIMARY KEY, board_slug TEXT NOT NULL DEFAULT '', title TEXT NOT NULL,"
                " description TEXT DEFAULT '', status TEXT NOT NULL DEFAULT 'triage', assignee TEXT NOT NULL DEFAULT 'unassigned',"
                " priority TEXT NOT NULL DEFAULT 'P2', workspace_path TEXT, workspace_kind TEXT DEFAULT 'worktree', branch_name TEXT,"
                " pr_url TEXT, tenant TEXT DEFAULT '', skills TEXT DEFAULT '[]', tags TEXT DEFAULT '[]', metadata TEXT DEFAULT '{}',"
                " created_at INTEGER NOT NULL, updated_at INTEGER NOT NULL);"
            )
            real_now = int(_time.time())
            conn.execute("INSERT INTO boards (slug, created_at, updated_at) VALUES (?,1,1)", ("stats-board",))
            # Task A: running ~47 min per metadata.started_at, but updated_at is seconds old
            conn.execute(
                "INSERT INTO tasks (id, board_slug, title, status, assignee, metadata, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                ("zf-run-a", "stats-board", "Long build", "running", "zf-builder",
                 json.dumps({"started_at": real_now - 47 * 60, "worker_pid": 1234}),
                 real_now - 47 * 60, real_now - 5),
            )
            # Task B: clock skew — started_at in the future; must clamp to 0m (never negative)
            conn.execute(
                "INSERT INTO tasks (id, board_slug, title, status, assignee, metadata, created_at, updated_at)"
                " VALUES (?,?,?,?,?,?,?,?)",
                ("zf-run-b", "stats-board", "Skewed task", "running", "zf-builder",
                 json.dumps({"started_at": real_now + 600}), real_now - 5, real_now - 5),
            )
            conn.commit()
            conn.close()

            old_db = os.environ.get("ZEROFACTORY_DB")
            os.environ["ZEROFACTORY_DB"] = str(db_path)
            buf = io.StringIO()
            try:
                with contextlib.redirect_stdout(buf):
                    rc = self.mod.run_daily_stats()
            finally:
                if old_db is None:
                    os.environ.pop("ZEROFACTORY_DB", None)
                else:
                    os.environ["ZEROFACTORY_DB"] = old_db
            out = buf.getvalue()
            self.assertEqual(rc, 0)

            # Task A: active for ~47m (derived from started_at, NOT the stale updated_at)
            m = re.search(r"`zf-run-a`.*active for (-?\d+)m", out)
            self.assertIsNotNone(m, f"missing in-flight line for zf-run-a in:\n{out}")
            mins_a = int(m.group(1))
            self.assertGreaterEqual(mins_a, 45)
            self.assertLess(mins_a, 60)

            # Task B: clamped to 0m, never negative (clock skew)
            m2 = re.search(r"`zf-run-b`.*active for (-?\d+)m", out)
            self.assertIsNotNone(m2, f"missing in-flight line for zf-run-b in:\n{out}")
            self.assertGreaterEqual(int(m2.group(1)), 0)
            self.assertNotIn("active for -", out)


if __name__ == "__main__":
    unittest.main()
