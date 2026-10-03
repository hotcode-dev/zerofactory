"""End-to-End validation of the OpenWiki cron job lifecycle and execution."""

from __future__ import annotations

import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from cron.definitions import get_all_builtin_cron_jobs
from cron.executor import trigger_builtin_job
from cron.manager import ensure_builtin_cron_jobs
from cron.store import load_jobs_from_file
from dashboard.plugin_api import BoardCreate, create_board, init_db

REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class TestOpenWikiCronE2E(unittest.TestCase):
    """End-to-End test suite for OpenWiki cron synchronization, self-healing, and execution."""

    def setUp(self):
        self.td = tempfile.mkdtemp(prefix="zf-openwiki-e2e-")
        self.fake_home = Path(self.td) / "home"
        self.fake_home.mkdir(parents=True)
        self.db_path = self.fake_home / ".hermes" / "zerofactory.db"
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self.lock_path = Path(self.td) / "lock.lock"
        self.cron_jobs_file = (
            self.fake_home
            / ".hermes"
            / "profiles"
            / "zf-orchestrator"
            / "cron"
            / "jobs.json"
        )
        self.cron_jobs_file.parent.mkdir(parents=True, exist_ok=True)

        self.repo_dir = Path(self.td) / "repo"
        self.repo_dir.mkdir()
        subprocess.run(
            ["git", "init", "-b", "main"],
            cwd=str(self.repo_dir),
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Wiki E2E"],
            cwd=str(self.repo_dir),
            check=True,
        )
        subprocess.run(
            ["git", "config", "user.email", "wiki@e2e.test"],
            cwd=str(self.repo_dir),
            check=True,
        )
        (self.repo_dir / "README.md").write_text("# Test Repo\n")
        subprocess.run(["git", "add", "."], cwd=str(self.repo_dir), check=True)
        subprocess.run(
            ["git", "commit", "-m", "chore: init"], cwd=str(self.repo_dir), check=True
        )

        self.orig_env = {
            "HOME": os.environ.get("HOME"),
            "ZEROFACTORY_DB": os.environ.get("ZEROFACTORY_DB"),
            "ZEROFACTORY_CRON_JOBS_FILE": os.environ.get("ZEROFACTORY_CRON_JOBS_FILE"),
            "ZEROFACTORY_LOCK_PATH": os.environ.get("ZEROFACTORY_LOCK_PATH"),
            "ZEROFACTORY_SKIP_GIT": os.environ.get("ZEROFACTORY_SKIP_GIT"),
            "ZEROFACTORY_SKIP_WORKER_SPAWN": os.environ.get(
                "ZEROFACTORY_SKIP_WORKER_SPAWN"
            ),
            "ZEROFACTORY_DISABLE_DISPATCHER": os.environ.get(
                "ZEROFACTORY_DISABLE_DISPATCHER"
            ),
            "ZEROFACTORY_SKIP_CRON_SYNC": os.environ.get("ZEROFACTORY_SKIP_CRON_SYNC"),
        }

        os.environ["HOME"] = str(self.fake_home)
        os.environ["ZEROFACTORY_DB"] = str(self.db_path)
        os.environ["ZEROFACTORY_CRON_JOBS_FILE"] = str(self.cron_jobs_file)
        os.environ["ZEROFACTORY_LOCK_PATH"] = str(self.lock_path)
        os.environ["ZEROFACTORY_DISABLE_DISPATCHER"] = "1"
        os.environ["ZEROFACTORY_SKIP_GIT"] = "1"
        os.environ["ZEROFACTORY_SKIP_WORKER_SPAWN"] = "1"
        os.environ.pop("ZEROFACTORY_SKIP_CRON_SYNC", None)

        init_db(force=True)

    def tearDown(self):
        for k, v in self.orig_env.items():
            if v is not None:
                os.environ[k] = v
            else:
                os.environ.pop(k, None)
        shutil.rmtree(self.td, ignore_errors=True)

    def test_01_openwiki_cron_generation_and_sync(self):
        """OpenWiki cron job is automatically registered in zf-orchestrator with correct category and profile."""
        board = create_board(BoardCreate(git_url=str(self.repo_dir)))
        board_slug = board["slug"]
        wiki_job_id = f"zero-factory-openwiki-update-{board_slug}"

        # 1. Definitions check
        jobs = get_all_builtin_cron_jobs()
        self.assertIn(wiki_job_id, jobs)
        wiki_job = jobs[wiki_job_id]
        self.assertEqual(wiki_job["category"], "openwiki")
        self.assertEqual(wiki_job["profile"], "zf-orchestrator")
        self.assertEqual(wiki_job["script"], "zf_openwiki_gate.py")
        self.assertEqual(wiki_job["schedule"]["kind"], "interval")
        self.assertEqual(wiki_job["schedule"]["minutes"], 1440)
        self.assertEqual(wiki_job["schedule_display"], "daily")

        # 2. Sync to jobs.json
        ensure_builtin_cron_jobs()
        stored_jobs = load_jobs_from_file(self.cron_jobs_file)
        stored_dict = {
            j["id"]: j for j in stored_jobs if isinstance(j, dict) and "id" in j
        }

        self.assertIn(wiki_job_id, stored_dict)
        stored_wiki = stored_dict[wiki_job_id]
        self.assertEqual(stored_wiki["category"], "openwiki")
        self.assertEqual(stored_wiki["profile"], "zf-orchestrator")
        self.assertEqual(stored_wiki["script"], "zf_openwiki_gate.py")

    def test_02_openwiki_cron_profile_auto_healing(self):
        """If an existing OpenWiki job has 'zf-builder' (or custom_config=True), ensure_builtin_cron_jobs fixes it to 'zf-orchestrator'."""
        board = create_board(BoardCreate(git_url=str(self.repo_dir)))
        board_slug = board["slug"]
        wiki_job_id = f"zero-factory-openwiki-update-{board_slug}"

        # Write existing job with bad profile 'zf-builder' and custom_config=True
        bad_job = {
            "id": wiki_job_id,
            "name": f"Zero Factory OpenWiki update ({board_slug})",
            "profile": "zf-builder",
            "category": "openwiki",
            "custom_config": True,
            "schedule": {"kind": "interval", "minutes": 1440, "display": "daily"},
            "schedule_display": "daily",
            "enabled": True,
            "origin": "zerofactory",
        }
        self.cron_jobs_file.write_text(
            json.dumps({"jobs": [bad_job]}), encoding="utf-8"
        )

        # Run synchronization
        ensure_builtin_cron_jobs()

        # Verify profile is healed to zf-orchestrator
        stored_jobs = load_jobs_from_file(self.cron_jobs_file)
        stored_dict = {
            j["id"]: j for j in stored_jobs if isinstance(j, dict) and "id" in j
        }
        healed_job = stored_dict.get(wiki_job_id)
        self.assertIsNotNone(healed_job)
        self.assertEqual(healed_job["profile"], "zf-orchestrator")

    def test_03_trigger_builtin_job_executes_under_zf_orchestrator(self):
        """trigger_builtin_job routes OpenWiki cron to -p zf-orchestrator, avoiding code 1."""
        board = create_board(BoardCreate(git_url=str(self.repo_dir)))
        board_slug = board["slug"]
        wiki_job_id = f"zero-factory-openwiki-update-{board_slug}"

        executed_cmds = []

        class FakePopen:
            def __init__(self, cmd, **kwargs):
                executed_cmds.append(cmd)
                self.pid = 12345
                self.returncode = 0

            def wait(self, timeout=None):
                return 0

        # Even if job in definitions or DB erroneously had profile="zf-builder":
        bad_job_def = {
            wiki_job_id: {
                "id": wiki_job_id,
                "name": f"Zero Factory OpenWiki update ({board_slug})",
                "profile": "zf-builder",
            }
        }

        with (
            patch("cron.executor.get_all_builtin_cron_jobs", return_value=bad_job_def),
            patch("cron.executor.subprocess.Popen", side_effect=FakePopen),
        ):
            res = trigger_builtin_job(wiki_job_id)

        self.assertTrue(res.get("ok"), f"Job execution should succeed: {res}")
        self.assertEqual(res.get("returncode"), 0)

        hermes_cmds = [
            c for c in executed_cmds if isinstance(c, (list, tuple)) and "cron" in c
        ]
        self.assertEqual(len(hermes_cmds), 1)

        cmd = hermes_cmds[0]
        # Must execute with -p zf-orchestrator, NEVER -p zf-builder
        self.assertIn("-p", cmd)
        p_idx = cmd.index("-p")
        self.assertEqual(cmd[p_idx + 1], "zf-orchestrator")
        self.assertIn(wiki_job_id, cmd)


if __name__ == "__main__":
    unittest.main()
