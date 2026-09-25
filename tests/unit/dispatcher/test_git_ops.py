"""Unit tests for dispatcher/git_ops.py: git synchronization, conflict markers, fail-closed guards."""

import os
import subprocess
import tempfile
from pathlib import Path
from unittest.mock import patch, MagicMock
import pytest

from dispatcher.git_ops import (
    get_default_branch,
    sync_repo_main,
    check_files_for_conflict_markers,
    check_unresolved_conflicts,
    check_unresolved_conflicts_safe,
    pull_and_merge_main,
    clean_stale_git_locks,
    GitConflictCheckError,
    _has_unresolved_conflict_markers,
)


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


def _proc_result(rc=0, stdout=""):
    m = MagicMock()
    m.returncode = rc
    m.stdout = stdout
    m.stderr = ""
    return m


def _merge_cmds(rec):
    return [c for c in rec.calls if c[:2] == ("git", "merge")]


# --- 1. Conflict Marker Unit Logic ---

def test_has_unresolved_conflict_markers():
    """Verify three-way conflict marker detection without false positives."""
    # Valid marker block
    valid_marker = b"<<<<<<< HEAD\nlocal changes\n=======\nremote changes\n>>>>>>> main\n"
    assert _has_unresolved_conflict_markers(valid_marker) is True

    # Missing separator
    no_sep = b"<<<<<<< HEAD\nlocal changes\n>>>>>>> main\n"
    assert _has_unresolved_conflict_markers(no_sep) is False

    # Incomplete start
    no_start = b"local changes\n=======\n>>>>>>> main\n"
    assert _has_unresolved_conflict_markers(no_start) is False

    # Normal text with single symbol
    normal = b"if x <<<<<<< 5:\n    print('test')\n"
    assert _has_unresolved_conflict_markers(normal) is False


# --- 2. Default Branch Resolution Fallback Chain ---

def test_get_default_branch_origin_head():
    rec = _ProcRecorder({
        ("git", "symbolic-ref", "refs/remotes/origin/HEAD"): _proc_result(0, "refs/remotes/origin/main"),
    })
    with patch("dispatcher.git_ops.subprocess.run", new=rec):
        assert get_default_branch(Path("/tmp/fake_repo")) == "main"


def test_get_default_branch_origin_main_showref():
    rec = _ProcRecorder({
        ("git", "symbolic-ref", "refs/remotes/origin/HEAD"): _proc_result(1, ""),
        ("git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/main"): _proc_result(0, ""),
    })
    with patch("dispatcher.git_ops.subprocess.run", new=rec):
        assert get_default_branch(Path("/tmp/fake_repo")) == "main"


def test_get_default_branch_origin_master_showref():
    rec = _ProcRecorder({
        ("git", "symbolic-ref", "refs/remotes/origin/HEAD"): _proc_result(1, ""),
        ("git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/main"): _proc_result(1, ""),
        ("git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/master"): _proc_result(0, ""),
    })
    with patch("dispatcher.git_ops.subprocess.run", new=rec):
        assert get_default_branch(Path("/tmp/fake_repo")) == "master"


def test_get_default_branch_fallback_main():
    rec = _ProcRecorder({
        ("git", "symbolic-ref", "refs/remotes/origin/HEAD"): _proc_result(1, ""),
        ("git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/main"): _proc_result(1, ""),
        ("git", "show-ref", "--verify", "--quiet", "refs/remotes/origin/master"): _proc_result(1, ""),
        ("git", "show-ref", "--verify", "--quiet", "refs/heads/main"): _proc_result(1, ""),
        ("git", "show-ref", "--verify", "--quiet", "refs/heads/master"): _proc_result(1, ""),
    })
    with patch("dispatcher.git_ops.subprocess.run", new=rec):
        assert get_default_branch(Path("/tmp/fake_repo")) == "main"


# --- 3. sync_repo_main Guards ---

def test_sync_repo_main_skipped_when_off_default_branch():
    rec = _ProcRecorder({
        ("git", "fetch", "origin", "main"): _proc_result(),
        ("git", "status", "--porcelain"): _proc_result(0, ""),
        ("git", "rev-parse", "--abbrev-ref", "HEAD"): _proc_result(0, "feature-x\n"),
    })
    with patch("dispatcher.git_ops._d") as mock_d, patch("dispatcher.git_ops.subprocess.run", new=rec):
        mock_d.return_value.get_default_branch.return_value = "main"
        out = sync_repo_main(Path("/tmp/fake_repo"))
    assert out == "main"
    assert _merge_cmds(rec) == []


def test_sync_repo_main_skipped_when_dirty():
    rec = _ProcRecorder({
        ("git", "fetch", "origin", "main"): _proc_result(),
        ("git", "status", "--porcelain"): _proc_result(0, " M dirty.txt\n"),
        ("git", "rev-parse", "--abbrev-ref", "HEAD"): _proc_result(0, "main\n"),
    })
    with patch("dispatcher.git_ops._d") as mock_d, patch("dispatcher.git_ops.subprocess.run", new=rec):
        mock_d.return_value.get_default_branch.return_value = "main"
        out = sync_repo_main(Path("/tmp/fake_repo"))
    assert out == "main"
    assert _merge_cmds(rec) == []


def test_sync_repo_main_ff_merge_on_clean_main():
    rec = _ProcRecorder({
        ("git", "fetch", "origin", "main"): _proc_result(),
        ("git", "status", "--porcelain"): _proc_result(0, ""),
        ("git", "rev-parse", "--abbrev-ref", "HEAD"): _proc_result(0, "main\n"),
        ("git", "merge", "--ff-only", "origin/main"): _proc_result(),
    })
    with patch("dispatcher.git_ops._d") as mock_d, patch("dispatcher.git_ops.subprocess.run", new=rec):
        mock_d.return_value.get_default_branch.return_value = "main"
        out = sync_repo_main(Path("/tmp/fake_repo"))
    assert out == "main"
    assert ("git", "merge", "--ff-only", "origin/main") in rec.calls


# --- 4. Fail-Closed Conflict Detection & Safe Wrapper ---

def test_check_unresolved_conflicts_fail_closed(tmp_path: Path):
    """Authoritative git query failure must raise GitConflictCheckError, not silently return []."""
    wt = tmp_path / "wt"
    wt.mkdir()

    orig_run = subprocess.run

    def fail_unmerged(cmd, *a, **k):
        if isinstance(cmd, list) and any("--diff-filter=U" in str(c) for c in cmd):
            raise OSError("index.lock held")
        return orig_run(cmd, *a, **k)

    with patch("dispatcher.git_ops.subprocess.run", side_effect=fail_unmerged):
        with pytest.raises(GitConflictCheckError):
            check_unresolved_conflicts(wt)

        ok, files, err = check_unresolved_conflicts_safe(wt)
        assert ok is False
        assert files == []
        assert "could not verify" in err


# --- 5. Stale Lock File Cleanup ---

def test_clean_stale_git_locks(tmp_path: Path):
    """Locks older than max_age_seconds must be removed, fresh ones preserved."""
    repo = tmp_path / "repo"
    git_dir = repo / ".git"
    git_dir.mkdir(parents=True)

    old_lock = git_dir / "index.lock"
    old_lock.write_text("lock")
    # Set mtime to 30 seconds ago
    import time
    old_time = time.time() - 30
    os.utime(str(old_lock), (old_time, old_time))

    fresh_lock = git_dir / "HEAD.lock"
    fresh_lock.write_text("lock")

    with patch("dispatcher.git_ops._d") as mock_d:
        mock_d.return_value.get_git_dir.return_value = git_dir
        removed = clean_stale_git_locks(repo, max_age_seconds=15)

    assert old_lock in removed
    assert not old_lock.exists()
    assert fresh_lock.exists()


# --- 6. Non-Fast-Forward Merge Integration ---

def test_pull_and_merge_main_non_ff(tmp_path: Path):
    """Test 3-way merge without conflict on diverged branches."""
    repo_path = tmp_path / "repo"
    repo_path.mkdir()
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo_path), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo_path), check=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo_path), check=True)

    (repo_path / "base.txt").write_text("base\n")
    subprocess.run(["git", "add", "."], cwd=str(repo_path), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "base"], cwd=str(repo_path), check=True, capture_output=True)

    worktree_dir = tmp_path / "wt"
    subprocess.run(
        ["git", "worktree", "add", str(worktree_dir), "-b", "task/nff"],
        cwd=str(repo_path), check=True, capture_output=True,
    )
    (worktree_dir / "task.txt").write_text("task change\n")
    subprocess.run(["git", "add", "."], cwd=str(worktree_dir), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "task commit"], cwd=str(worktree_dir), check=True, capture_output=True)

    (repo_path / "main.txt").write_text("main change\n")
    subprocess.run(["git", "add", "."], cwd=str(repo_path), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "main commit"], cwd=str(repo_path), check=True, capture_output=True)

    success, conflicts, msg = pull_and_merge_main(worktree_dir, repo_path, default_branch="main")
    assert success is True
    assert conflicts == []
    assert "Successfully merged" in msg
    assert (worktree_dir / "main.txt").exists()
    assert (worktree_dir / "task.txt").exists()
