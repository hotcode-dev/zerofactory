"""Unit tests for scripts/zf_scanner_gate.py."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
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
        with patch.object(mod, "_run_cmd", new=str_rec), \
             patch.object(mod.subprocess, "run", new=proc_rec):
            out = mod._auto_sync_repo(Path("/tmp/fake_repo"))
        return out, str_rec, proc_rec

    def test_no_origin_early_return(self):
        out, str_rec, proc_rec = self._call_gate({("git", "remote"): "upstream"}, {})
        self.assertIsNone(out)
        self.assertEqual(str_rec.calls, [("git", "remote")])
        self.assertEqual(proc_rec.calls, [])

    def test_dirty_worktree_early_return(self):
        out, str_rec, proc_rec = self._call_gate(
            {("git", "remote"): "origin",
             ("git", "status", "--porcelain"): " M dirty.txt\n"},
            {},
        )
        self.assertIsNone(out)
        self.assertNotIn(("git", "fetch", "origin", "main"), proc_rec.calls)

    def test_symbolic_ref_preferred(self):
        out, str_rec, proc_rec = self._call_gate(
            {("git", "remote"): "origin",
             ("git", "status", "--porcelain"): "",
             ("git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"): "origin/feature-x",
             ("git", "rev-parse", "--abbrev-ref", "HEAD"): "feature-x\n"},
            {("git", "fetch", "origin", "feature-x"): _proc_result(0, ""),
             ("git", "merge", "--ff-only", "origin/feature-x"): _proc_result(0, "")},
        )
        self.assertIsNone(out)
        self.assertIn(("git", "merge", "--ff-only", "origin/feature-x"), proc_rec.calls)

    def test_fallback_main_showref(self):
        out, str_rec, proc_rec = self._call_gate(
            {("git", "remote"): "origin",
             ("git", "status", "--porcelain"): "",
             ("git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"): "",
             ("git", "rev-parse", "--abbrev-ref", "HEAD"): "main\n"},
            {("git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/main"): _proc_result(0, ""),
             ("git", "fetch", "origin", "main"): _proc_result(0, ""),
             ("git", "merge", "--ff-only", "origin/main"): _proc_result(0, "")},
        )
        self.assertIsNone(out)
        self.assertIn(("git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/main"), proc_rec.calls)
        self.assertIn(("git", "merge", "--ff-only", "origin/main"), proc_rec.calls)

    def test_fallback_master_showref(self):
        out, str_rec, proc_rec = self._call_gate(
            {("git", "remote"): "origin",
             ("git", "status", "--porcelain"): "",
             ("git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"): "",
             ("git", "rev-parse", "--abbrev-ref", "HEAD"): "master\n"},
            {("git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/main"): _proc_result(1, ""),
             ("git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/master"): _proc_result(0, ""),
             ("git", "fetch", "origin", "master"): _proc_result(0, ""),
             ("git", "merge", "--ff-only", "origin/master"): _proc_result(0, "")},
        )
        self.assertIsNone(out)
        self.assertIn(("git", "merge", "--ff-only", "origin/master"), proc_rec.calls)

    def test_not_on_default_branch_early_return(self):
        out, str_rec, proc_rec = self._call_gate(
            {("git", "remote"): "origin",
             ("git", "status", "--porcelain"): "",
             ("git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"): "origin/main",
             ("git", "rev-parse", "--abbrev-ref", "HEAD"): "feature\n"},
            {},
        )
        self.assertIsNone(out)
        self.assertNotIn(("git", "fetch", "origin", "main"), proc_rec.calls)

    def test_fetch_nonzero_aborts_before_merge(self):
        out, str_rec, proc_rec = self._call_gate(
            {("git", "remote"): "origin",
             ("git", "status", "--porcelain"): "",
             ("git", "symbolic-ref", "--short", "refs/remotes/origin/HEAD"): "origin/main",
             ("git", "rev-parse", "--abbrev-ref", "HEAD"): "main\n"},
            {("git", "fetch", "origin", "main"): _proc_result(1, "")},
        )
        self.assertIsNone(out)
        self.assertIn(("git", "fetch", "origin", "main"), proc_rec.calls)
        self.assertNotIn(("git", "merge", "--ff-only", "origin/main"), proc_rec.calls)

    def test_exceptions_swallowed(self):
        out, str_rec, proc_rec = self._call_gate(
            {("git", "remote"): RuntimeError("boom")}, {},
        )
        self.assertIsNone(out, "_auto_sync_repo must swallow exceptions and return cleanly")


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

                self.assertTrue(mod.write_state_atomic({"board-a": {"last_scanned_sha": "abc"}}))
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
                with patch.dict(os.environ, {"ZEROFACTORY_SCANNER_STATE": str(state_path)}):
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


if __name__ == "__main__":
    unittest.main()
