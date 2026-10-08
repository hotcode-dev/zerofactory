"""Unit tests for scripts/zf_scanner_gate.py."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from unittest.mock import MagicMock, patch

REPO_ROOT = Path(__file__).resolve().parent.parent.parent.parent
GATE_PATH = REPO_ROOT / "scripts" / "zf_scanner_gate.py"


def _load_gate():
    spec = importlib.util.spec_from_file_location("zf_scanner_gate_mod", GATE_PATH)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


class _ProcRecorder:
    def __init__(self, results=None, default_rc=0, default_stdout=""):
        self.results = dict(results or {})
        self.calls = []
        self.default_rc = default_rc
        self.default_stdout = default_stdout

    def __call__(self, cmd, *args, **kwargs):
        key = tuple(cmd)
        self.calls.append(key)
        if key in self.results:
            res = self.results[key]
            if isinstance(res, BaseException):
                raise res
            return res
        m = MagicMock()
        m.returncode = self.default_rc
        m.stdout = self.default_stdout
        m.stderr = ""
        return m


class _StrRecorder:
    def __init__(self, results=None, default=""):
        self.results = dict(results or {})
        self.calls = []
        self.default = default

    def __call__(self, cmd, cwd=None):
        key = tuple(cmd)
        self.calls.append(key)
        if key in self.results:
            res = self.results[key]
            if isinstance(res, BaseException):
                raise res
            return res
        return self.default


def _proc_result(rc=0, stdout=""):
    m = MagicMock()
    m.returncode = rc
    m.stdout = stdout
    m.stderr = ""
    return m


class TestAutoSyncRepoGuards(unittest.TestCase):
    """Pin the guard/exit branches of zf_scanner_gate._auto_sync_repo."""

    def _call_gate(self, str_results, proc_results):
        mod = _load_gate()
        str_rec = _StrRecorder(str_results)
        proc_rec = _ProcRecorder(proc_results)
        with (
            patch.object(mod, "_run_cmd", new=str_rec),
            patch.object(mod.subprocess, "run", new=proc_rec),
        ):
            out = mod._auto_sync_repo(Path("/tmp/fake_repo"))
        return out, str_rec, proc_rec

    def test_no_origin_early_return(self):
        out, str_rec, proc_rec = self._call_gate({("git", "remote"): "upstream"}, {})
        self.assertIsNone(out)
        self.assertEqual(str_rec.calls, [("git", "remote")])
        self.assertEqual(proc_rec.calls, [])

    def test_dirty_worktree_early_return(self):
        out, str_rec, proc_rec = self._call_gate(
            {
                ("git", "remote"): "origin",
                ("git", "status", "--porcelain"): " M dirty.txt\n",
            },
            {},
        )
        self.assertIsNone(out)
        self.assertNotIn(("git", "fetch", "origin", "main"), proc_rec.calls)

    def test_symbolic_ref_preferred(self):
        out, str_rec, proc_rec = self._call_gate(
            {
                ("git", "remote"): "origin",
                ("git", "status", "--porcelain"): "",
                (
                    "git",
                    "symbolic-ref",
                    "--short",
                    "refs/remotes/origin/HEAD",
                ): "origin/feature-x",
                ("git", "rev-parse", "--abbrev-ref", "HEAD"): "feature-x\n",
            },
            {
                ("git", "fetch", "origin", "feature-x"): _proc_result(0, ""),
                ("git", "merge", "--ff-only", "origin/feature-x"): _proc_result(0, ""),
            },
        )
        self.assertIsNone(out)
        self.assertIn(("git", "merge", "--ff-only", "origin/feature-x"), proc_rec.calls)

    def test_fallback_main_showref(self):
        out, str_rec, proc_rec = self._call_gate(
            {
                ("git", "remote"): "origin",
                ("git", "status", "--porcelain"): "",
                ("git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"): "",
                ("git", "rev-parse", "--abbrev-ref", "HEAD"): "main\n",
            },
            {
                (
                    "git",
                    "show-ref",
                    "--verify",
                    "--quiet",
                    "refs/remotes/origin/main",
                ): _proc_result(0, ""),
                ("git", "fetch", "origin", "main"): _proc_result(0, ""),
                ("git", "merge", "--ff-only", "origin/main"): _proc_result(0, ""),
            },
        )
        self.assertIsNone(out)
        self.assertIn(
            ("git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/main"),
            proc_rec.calls,
        )
        self.assertIn(("git", "merge", "--ff-only", "origin/main"), proc_rec.calls)

    def test_fallback_master_showref(self):
        out, str_rec, proc_rec = self._call_gate(
            {
                ("git", "remote"): "origin",
                ("git", "status", "--porcelain"): "",
                ("git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"): "",
                ("git", "rev-parse", "--abbrev-ref", "HEAD"): "master\n",
            },
            {
                (
                    "git",
                    "show-ref",
                    "--verify",
                    "--quiet",
                    "refs/remotes/origin/main",
                ): _proc_result(1, ""),
                (
                    "git",
                    "show-ref",
                    "--verify",
                    "--quiet",
                    "refs/remotes/origin/master",
                ): _proc_result(0, ""),
                ("git", "fetch", "origin", "master"): _proc_result(0, ""),
                ("git", "merge", "--ff-only", "origin/master"): _proc_result(0, ""),
            },
        )
        self.assertIsNone(out)
        self.assertIn(("git", "merge", "--ff-only", "origin/master"), proc_rec.calls)

    def test_not_on_default_branch_early_return(self):
        out, str_rec, proc_rec = self._call_gate(
            {
                ("git", "remote"): "origin",
                ("git", "status", "--porcelain"): "",
                (
                    "git",
                    "symbolic-ref",
                    "--short",
                    "refs/remotes/origin/HEAD",
                ): "origin/main",
                ("git", "rev-parse", "--abbrev-ref", "HEAD"): "feature\n",
            },
            {},
        )
        self.assertIsNone(out)
        self.assertNotIn(("git", "fetch", "origin", "main"), proc_rec.calls)

    def test_fetch_nonzero_aborts_before_merge(self):
        out, str_rec, proc_rec = self._call_gate(
            {
                ("git", "remote"): "origin",
                ("git", "status", "--porcelain"): "",
                (
                    "git",
                    "symbolic-ref",
                    "--short",
                    "refs/remotes/origin/HEAD",
                ): "origin/main",
                ("git", "rev-parse", "--abbrev-ref", "HEAD"): "main\n",
            },
            {("git", "fetch", "origin", "main"): _proc_result(1, "")},
        )
        self.assertIsNone(out)
        self.assertIn(("git", "fetch", "origin", "main"), proc_rec.calls)
        self.assertNotIn(("git", "merge", "--ff-only", "origin/main"), proc_rec.calls)

    def test_exceptions_swallowed(self):
        out, str_rec, proc_rec = self._call_gate(
            {("git", "remote"): RuntimeError("boom")},
            {},
        )
        self.assertIsNone(
            out, "_auto_sync_repo must swallow exceptions and return cleanly"
        )


class TestZfScannerGateUnit(unittest.TestCase):
    """Test scanner gate slug resolution, atomic persistence, and wake logic."""

    def test_resolve_board_slug_ignores_flags(self):
        """resolve_board_slug skips flags like --force and returns real slug or env fallback."""
        mod = _load_gate()
        old_argv = sys.argv
        old_board = os.environ.get("ZEROFACTORY_BOARD")
        try:
            repo_dir = Path("myrepo")
            os.environ["ZEROFACTORY_BOARD"] = "env-fallback-board"

            # Positional slug wins
            sys.argv = ["zf_scanner_gate.py", "my-real-board"]
            self.assertEqual(mod.resolve_board_slug(repo_dir), "my-real-board")

            # Flag token is skipped
            sys.argv = ["zf_scanner_gate.py", "--force"]
            self.assertEqual(mod.resolve_board_slug(repo_dir), "env-fallback-board")

            # Flag before positional slug
            sys.argv = ["zf_scanner_gate.py", "--force", "my-real-board"]
            self.assertEqual(mod.resolve_board_slug(repo_dir), "my-real-board")
        finally:
            sys.argv = old_argv
            if old_board is None:
                os.environ.pop("ZEROFACTORY_BOARD", None)
            else:
                os.environ["ZEROFACTORY_BOARD"] = old_board

    def test_scanner_state_atomic_write(self):
        """State is persisted atomically using a temp file + os.replace."""
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "scanner_state.json"
            mod = _load_gate()
            with patch.dict(os.environ, {"ZEROFACTORY_SCANNER_STATE": str(state_path)}):
                self.assertEqual(mod.get_state_file(), state_path)

                self.assertTrue(
                    mod.write_state_atomic({"board-a": {"last_scanned_sha": "abc"}})
                )
                self.assertTrue(state_path.exists())
                data = json.loads(state_path.read_text(encoding="utf-8"))
                self.assertEqual(data, {"board-a": {"last_scanned_sha": "abc"}})
                self.assertEqual(mod.load_state(), data)

    def test_scanner_state_concurrent_writes(self):
        """Concurrent atomic writes do not corrupt the JSON file."""
        with tempfile.TemporaryDirectory() as td:
            state_path = Path(td) / "scanner_state.json"
            mod = _load_gate()

            def write_worker(idx):
                with patch.dict(
                    os.environ, {"ZEROFACTORY_SCANNER_STATE": str(state_path)}
                ):
                    mod.mark_task_created(f"board-{idx}")

            with ThreadPoolExecutor(max_workers=8) as ex:
                futures = [ex.submit(write_worker, i) for i in range(20)]
                for f in futures:
                    f.result()

            with patch.dict(os.environ, {"ZEROFACTORY_SCANNER_STATE": str(state_path)}):
                final_data = mod.load_state()
            for i in range(20):
                self.assertIn(f"board-{i}", final_data)
                self.assertTrue(final_data[f"board-{i}"].get("task_created"))


class TestScanCodeMarkers(unittest.TestCase):
    """Regression: marker scan must match real TODO/FIXME/HACK markers only.

    Guards against the unanchored-substring bug where identifiers such as
    ``DEFAULT_IDLE_SCAN_MAX_TODO`` / ``idle_scan_max_todo`` (and prose) were
    picked up by ``git grep -E "TODO|FIXME|HACK"`` and polluted the scanner
    prompt.
    """

    #: env vars that must not leak into the fixture repo's git subprocesses
    ENV_PREFIXES = ("ZEROFACTORY_", "HERMES_", "GIT_")

    def _hermetic_env(self):
        saved = {}
        for k in list(os.environ):
            if k.startswith(self.ENV_PREFIXES):
                saved[k] = os.environ.pop(k)
        return saved

    def _restore_env(self, saved):
        os.environ.update(saved)

    def _init_fixture_repo(self, files: dict[str, str]) -> Path:
        repo = Path(tempfile.mkdtemp(prefix="zf-gate-fixture-"))
        for name, content in files.items():
            (repo / name).write_text(content, encoding="utf-8")
        for args in (
            ["init", "-q"],
            ["config", "user.email", "fixture@test.local"],
            ["config", "user.name", "fixture"],
            ["add", "-A"],
            ["commit", "-q", "-m", "fixture"],
        ):
            res = subprocess.run(
                ["git", *args],
                cwd=str(repo),
                capture_output=True,
                text=True,
                timeout=10,
            )
            if res.returncode != 0:
                raise AssertionError(f"git {args} failed: {res.stderr}")
        return repo

    def test_real_marker_detected_identifiers_ignored(self):
        saved = self._hermetic_env()
        repo = None
        try:
            repo = self._init_fixture_repo(
                {
                    "identifiers.py": (
                        "DEFAULT_IDLE_SCAN_MAX_TODO = 2\n"
                        "idle_scan_max_todo = DEFAULT_IDLE_SCAN_MAX_TODO\n"
                        "FOO_TODO = 1\n"
                    ),
                    "real_marker.py": (
                        "def work():\n"
                        "    # TODO: real marker that must be found\n"
                        "    return 0\n"
                    ),
                }
            )
            mod = _load_gate()
            out = mod.scan_code_markers(repo)
            self.assertIn("real_marker.py", out)
            self.assertIn("# TODO: real marker", out)
            # identifier false-positives must not leak into the output
            self.assertNotIn("MAX_TODO", out)
            self.assertNotIn("idle_scan_max_todo", out)
            self.assertNotIn("FOO_TODO", out)
            self.assertNotIn("identifiers.py", out)
            # only the single real marker line is reported
            self.assertEqual(len(out.splitlines()), 1)
        finally:
            self._restore_env(saved)
            if repo is not None:
                shutil.rmtree(repo, ignore_errors=True)

    def test_identifier_only_repo_reports_no_markers(self):
        saved = self._hermetic_env()
        repo = None
        try:
            repo = self._init_fixture_repo(
                {
                    "identifiers.py": (
                        "DEFAULT_IDLE_SCAN_MAX_TODO = 2\n"
                        "todo = MAX_TODO  # lowercase todo never matches\n"
                    ),
                }
            )
            mod = _load_gate()
            self.assertEqual(
                mod.scan_code_markers(repo),
                "",
                "identifiers/prose must produce zero marker warnings",
            )
        finally:
            self._restore_env(saved)
            if repo is not None:
                shutil.rmtree(repo, ignore_errors=True)


class TestZfScannerGateMultiRepo(unittest.TestCase):
    """Test scanner gate evaluation for boards with multiple repositories in 1 cron job."""

    def setUp(self):
        self.mod = _load_gate()
        self.td = tempfile.TemporaryDirectory()
        self.tmp = Path(self.td.name)
        self.db_path = self.tmp / "zerofactory.db"
        self.state_file = self.tmp / "scanner_state.json"

        # Initialize mock DB with multi-repo board
        with sqlite3.connect(str(self.db_path)) as conn:
            conn.execute(
                "CREATE TABLE boards (slug TEXT PRIMARY KEY, max_concurrent_running INTEGER)"
            )
            conn.execute(
                "CREATE TABLE board_repositories (id INTEGER PRIMARY KEY AUTOINCREMENT, board_slug TEXT, repo_alias TEXT, git_url TEXT, target_branch TEXT)"
            )
            conn.execute(
                "CREATE TABLE tasks (id TEXT PRIMARY KEY, board_slug TEXT, repo_alias TEXT, title TEXT, description TEXT, status TEXT, assignee TEXT, priority TEXT, created_at REAL, updated_at REAL)"
            )
            conn.execute(
                "INSERT INTO boards (slug, max_concurrent_running) VALUES ('ecommerce', 1)"
            )
            conn.execute(
                "INSERT INTO board_repositories (board_slug, repo_alias, git_url, target_branch) VALUES ('ecommerce', 'backend', '/path/to/backend', 'main')"
            )
            conn.execute(
                "INSERT INTO board_repositories (board_slug, repo_alias, git_url, target_branch) VALUES ('ecommerce', 'frontend', '/path/to/frontend', 'main')"
            )
            conn.commit()

    def tearDown(self):
        self.td.cleanup()

    def test_get_board_repositories(self):
        with patch.dict(os.environ, {"ZEROFACTORY_DB": str(self.db_path)}):
            repos = self.mod.get_board_repositories("ecommerce")
            self.assertEqual(len(repos), 2)
            self.assertEqual(repos[0]["repo_alias"], "backend")
            self.assertEqual(repos[1]["repo_alias"], "frontend")

    def test_multi_repo_unchanged_suppresses(self):
        import time

        now_ts = int(time.time())
        self.state_file.write_text(
            json.dumps(
                {
                    "ecommerce": {
                        "last_scanned_sha": "sha_backend_1",
                        "last_scan_at": now_ts,
                        "repos": {
                            "backend": {
                                "last_scanned_sha": "sha_backend_1",
                                "last_status": "",
                                "last_scan_at": now_ts,
                            },
                            "frontend": {
                                "last_scanned_sha": "sha_frontend_1",
                                "last_status": "",
                                "last_scan_at": now_ts,
                            },
                        },
                        "task_created": True,
                    }
                }
            ),
            encoding="utf-8",
        )

        repo_be = self.tmp / "backend"
        repo_fe = self.tmp / "frontend"
        (repo_be / ".git").mkdir(parents=True)
        (repo_fe / ".git").mkdir(parents=True)

        with patch.dict(
            os.environ,
            {
                "ZEROFACTORY_DB": str(self.db_path),
                "ZEROFACTORY_SCANNER_STATE": str(self.state_file),
                "ZEROFACTORY_SKIP_LLM_PROBE": "1",
            },
        ):
            with patch.object(self.mod, "_run_cmd") as mock_cmd, patch.object(
                self.mod, "resolve_repo_path"
            ) as mock_resolve:

                def _fake_resolve(board_slug, alias, git_url, curr_dir):
                    return repo_be if alias == "backend" else repo_fe

                mock_resolve.side_effect = _fake_resolve

                def _fake_cmd(cmd, cwd=None):
                    if "rev-parse" in cmd:
                        return "sha_backend_1" if cwd == repo_be else "sha_frontend_1"
                    if "status" in cmd:
                        return ""
                    if "log" in cmd:
                        return "100"
                    return ""

                mock_cmd.side_effect = _fake_cmd
                with patch("sys.argv", ["zf_scanner_gate.py", "ecommerce"]):
                    with patch("builtins.print") as mock_print:
                        rc = self.mod.run_scanner_gate()
                        self.assertEqual(rc, 0)
                        mock_print.assert_any_call(json.dumps({"wakeAgent": False}))

    def test_multi_repo_changed_repo_selected(self):
        self.state_file.write_text(
            json.dumps(
                {
                    "ecommerce": {
                        "repos": {
                            "backend": {
                                "last_scanned_sha": "sha_backend_1",
                                "last_status": "",
                            },
                            "frontend": {
                                "last_scanned_sha": "sha_frontend_1",
                                "last_status": "",
                            },
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        repo_be = self.tmp / "backend"
        repo_fe = self.tmp / "frontend"
        (repo_be / ".git").mkdir(parents=True)
        (repo_fe / ".git").mkdir(parents=True)

        with patch.dict(
            os.environ,
            {
                "ZEROFACTORY_DB": str(self.db_path),
                "ZEROFACTORY_SCANNER_STATE": str(self.state_file),
                "ZEROFACTORY_SKIP_LLM_PROBE": "1",
            },
        ):
            with patch.object(self.mod, "_run_cmd") as mock_cmd, patch.object(
                self.mod, "resolve_repo_path"
            ) as mock_resolve, patch.object(
                self.mod, "scan_code_markers", return_value=""
            ):

                def _fake_resolve(board_slug, alias, git_url, curr_dir):
                    return repo_be if alias == "backend" else repo_fe

                mock_resolve.side_effect = _fake_resolve

                def _fake_cmd(cmd, cwd=None):
                    if "rev-parse" in cmd:
                        return "sha_backend_1" if cwd == repo_be else "sha_frontend_2"
                    if "status" in cmd:
                        return ""
                    if "log" in cmd and "--format=%ct" in cmd:
                        return "200" if cwd == repo_fe else "100"
                    if "log" in cmd:
                        return "sha_frontend_2 feat: new ui component"
                    if "diff" in cmd:
                        return "src/App.tsx | 10 +"
                    return ""

                mock_cmd.side_effect = _fake_cmd
                with patch("sys.argv", ["zf_scanner_gate.py", "ecommerce"]):
                    printed = []
                    with patch(
                        "builtins.print",
                        side_effect=lambda *a: printed.append(
                            " ".join(str(x) for x in a)
                        ),
                    ):
                        rc = self.mod.run_scanner_gate()
                        self.assertEqual(rc, 0)
                        self.assertIn(json.dumps({"wakeAgent": True}), printed)
                        combined = "\n".join(printed)
                        self.assertIn("Target Repository:** `frontend`", combined)
                        self.assertIn(
                            '--board "ecommerce" --repo "frontend"', combined
                        )

    def test_multi_repo_idle_round_robin(self):
        # Both repos unchanged, but idle scan requested.
        # backend scanned at t=200, frontend scanned at t=100 -> frontend should be picked (least recently scanned)
        self.state_file.write_text(
            json.dumps(
                {
                    "ecommerce": {
                        "last_scanned_sha": "sha_backend_1",
                        "last_scan_at": 200,
                        "repos": {
                            "backend": {
                                "last_scanned_sha": "sha_backend_1",
                                "last_status": "",
                                "last_scan_at": 200,
                            },
                            "frontend": {
                                "last_scanned_sha": "sha_frontend_1",
                                "last_status": "",
                                "last_scan_at": 100,
                            },
                        },
                        "task_created": True,
                    }
                }
            ),
            encoding="utf-8",
        )

        repo_be = self.tmp / "backend"
        repo_fe = self.tmp / "frontend"
        (repo_be / ".git").mkdir(parents=True)
        (repo_fe / ".git").mkdir(parents=True)

        with patch.dict(
            os.environ,
            {
                "ZEROFACTORY_DB": str(self.db_path),
                "ZEROFACTORY_SCANNER_STATE": str(self.state_file),
                "ZEROFACTORY_SKIP_LLM_PROBE": "1",
            },
        ):
            with patch.object(self.mod, "_run_cmd") as mock_cmd, patch.object(
                self.mod, "resolve_repo_path"
            ) as mock_resolve, patch.object(
                self.mod, "scan_code_markers", return_value=""
            ):

                def _fake_resolve(board_slug, alias, git_url, curr_dir):
                    return repo_be if alias == "backend" else repo_fe

                mock_resolve.side_effect = _fake_resolve

                def _fake_cmd(cmd, cwd=None):
                    if "rev-parse" in cmd:
                        return "sha_backend_1" if cwd == repo_be else "sha_frontend_1"
                    if "status" in cmd:
                        return ""
                    if "log" in cmd and "--format=%ct" in cmd:
                        return "100"
                    if "log" in cmd:
                        return "recent commit"
                    return ""

                mock_cmd.side_effect = _fake_cmd
                with patch("sys.argv", ["zf_scanner_gate.py", "--idle", "ecommerce"]):
                    printed = []
                    with patch(
                        "builtins.print",
                        side_effect=lambda *a: printed.append(
                            " ".join(str(x) for x in a)
                        ),
                    ):
                        rc = self.mod.run_scanner_gate()
                        self.assertEqual(rc, 0)
                        self.assertIn(json.dumps({"wakeAgent": True}), printed)
                        combined = "\n".join(printed)
                        self.assertIn("Target Repository:** `frontend`", combined)
                        self.assertIn(
                            '--board "ecommerce" --repo "frontend"', combined
                        )


if __name__ == "__main__":
    unittest.main()
