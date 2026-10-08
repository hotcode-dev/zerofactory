"""Unit tests for dashboard/setup_common.py (board setup dedup & status logic).

Covers the four public helpers without touching the live board DB, real git, or
the network:
  * get_repo_resolver()
  * _find_setup_task()           -- the active_only dedup contract
  * check_board_setup_status()   -- not-found + filesystem + env-restore
  * create_setup_task()          -- dedup / not-found / create paths

SQLite fixtures come from the shared ``initialized_db`` fixture; the repo
resolver and ``routes.tasks.create_task`` are patched with unittest.mock so the
suite is hermetic.
"""

from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from unittest import mock

from dashboard import setup_common as sc


# Canonical key names used by the generic helpers.
HAS_KEY = "has_target"
PATH_KEY = "target_path"
PREVIEW_KEY = "target_preview"


# --- Fixture helpers --------------------------------------------------------


def _insert_board(db_path: Path, slug: str, git_url: str = "") -> None:
    now = 1_000_000_000
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO boards (slug, description, "
            "max_concurrent_running, auto_record_memory, "
            "jira_url, created_at, updated_at) "
            "VALUES (?, '', 1, 1, '', ?, ?)",
            (slug, now, now),
        )
        conn.execute(
            "INSERT INTO board_repositories (board_slug, repo_alias, git_url, target_branch, "
            "additional_reviewer_usernames, created_at, updated_at) "
            "VALUES (?, ?, ?, 'main', '[]', ?, ?)",
            (slug, slug, git_url or "", now, now),
        )
        conn.commit()


def _insert_task(
    db_path: Path,
    slug: str,
    task_id: str,
    status: str,
    title: str,
    metadata: str,
    created_at: int,
) -> None:
    with sqlite3.connect(str(db_path)) as conn:
        conn.execute(
            "INSERT INTO tasks (id, board_slug, title, description, status, "
            "assignee, priority, metadata, created_at, updated_at) "
            "VALUES (?, ?, ?, '', ?, 'zf-builder', 'P0', ?, ?, ?)",
            (task_id, slug, title, status, metadata, created_at, created_at),
        )
        conn.commit()


def _cursor(db_path: Path):
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    return conn, conn.cursor()


def _make_repo(tmp_path: Path, name: str) -> Path:
    """A fake on-disk repo: a dir with a .git/ marker (the resolver's probe)."""
    repo = tmp_path / name
    repo.mkdir(parents=True)
    (repo / ".git").mkdir()
    return repo


# --- get_repo_resolver ------------------------------------------------------


def test_get_repo_resolver_returns_callable():
    """At least one import path resolves, so the returned resolver is a working
    callable: it accepts a board dict and returns a Path or None without raising."""
    resolver = sc.get_repo_resolver()
    assert callable(resolver)
    out = resolver({"slug": "no-such-board", "git_url": "https://example.com/x.git"})
    assert out is None or isinstance(out, Path)


def test_get_repo_resolver_none_when_all_imports_fail():
    """When every import path raises, the resolver degrades to None.

    Force all four import paths to fail by intercepting ``__import__`` for the
    two module families that carry ``resolve_board_repo_path``
    (``builtin_cron`` and ``cron.definitions``).
    """
    real_import = __import__("builtins").__import__

    def blocked_import(name, *args, **kwargs):
        top = name.split(".")[0]
        if top in ("builtin_cron", "cron"):
            raise ImportError(f"blocked import: {name}")
        return real_import(name, *args, **kwargs)

    with mock.patch("builtins.__import__", blocked_import):
        resolver = sc.get_repo_resolver()
    assert resolver is None


# --- _find_setup_task: the dedup contract ----------------------------------


def test_find_setup_task_blocked_matches_only_when_not_active(
    initialized_db: Path,
):
    """'blocked' = awaiting human merge. active_only=False must match it,
    active_only=True must NOT (otherwise a done-but-unmerged task permanently
    wedges regenerate/retry)."""
    _insert_board(initialized_db, "dedup")
    _insert_task(
        initialized_db,
        "dedup",
        "zf-dedup-blocked",
        "blocked",
        "chore(repo): setup target",
        "{}",
        100,
    )
    conn, cur = _cursor(initialized_db)
    try:
        tid, status = sc._find_setup_task(
            cur, "dedup", "chore(repo): setup", "setup:target", active_only=False
        )
        assert tid == "zf-dedup-blocked"
        assert status == "blocked"

        tid_active, status_active = sc._find_setup_task(
            cur, "dedup", "chore(repo): setup", "setup:target", active_only=True
        )
        assert tid_active is None
        assert status_active is None
    finally:
        conn.close()


def test_find_setup_task_matches_via_metadata_dedup_key(
    initialized_db: Path,
):
    """Matching works through the metadata dedup key even when the title
    prefix does not match."""
    _insert_board(initialized_db, "metadup")
    # Title deliberately does NOT start with the prefix; only metadata matches.
    _insert_task(
        initialized_db,
        "metadup",
        "zf-metadup-active",
        "running",
        "some other title",
        '{"dedup_key": "setup:target"}',
        200,
    )
    conn, cur = _cursor(initialized_db)
    try:
        tid, status = sc._find_setup_task(
            cur, "metadup", "chore(repo): setup", "setup:target", active_only=True
        )
        assert tid == "zf-metadup-active"
        assert status == "running"
    finally:
        conn.close()


def test_find_setup_task_orders_by_newest_created_at(initialized_db: Path):
    """With multiple matches, the newest created_at row wins (DESC LIMIT 1)."""
    _insert_board(initialized_db, "newest")
    _insert_task(
        initialized_db,
        "newest",
        "zf-newest-old",
        "todo",
        "chore(repo): setup target",
        "{}",
        100,
    )
    _insert_task(
        initialized_db,
        "newest",
        "zf-newest-new",
        "running",
        "chore(repo): setup target",
        "{}",
        900,  # strictly later
    )
    conn, cur = _cursor(initialized_db)
    try:
        tid, status = sc._find_setup_task(
            cur, "newest", "chore(repo): setup", "setup:target", active_only=True
        )
        assert tid == "zf-newest-new"
        assert status == "running"
    finally:
        conn.close()


# --- check_board_setup_status ----------------------------------------------


def test_check_status_not_found(initialized_db: Path):
    """Unknown board -> ok:False + error + the full key set (no partial dict)."""
    res = sc.check_board_setup_status(
        "no-such-board",
        has_key=HAS_KEY,
        path_key=PATH_KEY,
        preview_key=PREVIEW_KEY,
        target_relpath="openwiki",
        title_prefix="chore(repo): setup",
        dedup_substring="setup:ow",
    )
    assert res["ok"] is False
    assert "no-such-board" in res["error"]
    expected_keys = {
        "ok",
        "error",
        HAS_KEY,
        "pending_task_id",
        "pending_task_status",
        "dedup_task_id",
        "dedup_task_status",
        PREVIEW_KEY,
    }
    assert expected_keys.issubset(res.keys())
    assert res[HAS_KEY] is False
    assert res["pending_task_id"] is None
    assert res["dedup_task_id"] is None
    assert res[PREVIEW_KEY] is None


def test_check_status_happy_path_file_target(
    initialized_db: Path, tmp_path: Path, monkeypatch
):
    """Resolver returns a real temp repo containing the target file -> has_key
    True, path_key/preview_key populated from the on-disk file."""
    _insert_board(initialized_db, "happy", git_url="https://example.com/x.git")
    repo = _make_repo(tmp_path, "happy_repo")
    (repo / "openwiki").mkdir()
    (repo / "openwiki" / "quickstart.md").write_text(
        "# quickstart\npreview content here\n", encoding="utf-8"
    )

    monkeypatch.setattr(sc, "get_repo_resolver", lambda: lambda board: repo)
    res = sc.check_board_setup_status(
        "happy",
        has_key=HAS_KEY,
        path_key=PATH_KEY,
        preview_key=PREVIEW_KEY,
        target_relpath="openwiki",
        title_prefix="chore(repo): setup",
        dedup_substring="setup:ow",
        preview_relpath="openwiki/quickstart.md",
        target_is_dir=True,
    )
    assert res["ok"] is True
    assert res[HAS_KEY] is True
    assert res[PATH_KEY] == str(repo / "openwiki")
    assert "preview content here" in res[PREVIEW_KEY]
    assert res["pending_task_id"] is None
    assert res["dedup_task_id"] is None


def test_check_status_file_target_missing(
    initialized_db: Path, tmp_path: Path, monkeypatch
):
    """Resolver returns a repo that lacks the target file -> has_key False."""
    _insert_board(initialized_db, "missing", git_url="https://example.com/x.git")
    repo = _make_repo(tmp_path, "missing_repo")
    # No target_relpath file/directory created.

    monkeypatch.setattr(sc, "get_repo_resolver", lambda: lambda board: repo)
    res = sc.check_board_setup_status(
        "missing",
        has_key=HAS_KEY,
        path_key=PATH_KEY,
        preview_key=PREVIEW_KEY,
        target_relpath="openwiki",
        title_prefix="chore(repo): setup",
        dedup_substring="setup:ow",
    )
    assert res["ok"] is True
    assert res[HAS_KEY] is False
    assert res[PATH_KEY] is None
    assert res[PREVIEW_KEY] is None


def test_check_status_pending_and_dedup_reflect_task_states(
    initialized_db: Path, tmp_path: Path, monkeypatch
):
    """A blocked task shows as pending (badge) but NOT as the dedup source;
    an active task shows as both."""
    _insert_board(initialized_db, "state")
    _insert_task(
        initialized_db,
        "state",
        "zf-state-blocked",
        "blocked",
        "chore(repo): setup target",
        '{"dedup_key": "setup:ow"}',
        100,
    )
    repo = _make_repo(tmp_path, "state_repo")
    monkeypatch.setattr(sc, "get_repo_resolver", lambda: lambda board: repo)

    res_blocked = sc.check_board_setup_status(
        "state",
        has_key=HAS_KEY,
        path_key=PATH_KEY,
        preview_key=PREVIEW_KEY,
        target_relpath="openwiki",
        title_prefix="chore(repo): setup",
        dedup_substring="setup:ow",
    )
    assert res_blocked["pending_task_id"] == "zf-state-blocked"
    assert res_blocked["pending_task_status"] == "blocked"
    assert res_blocked["dedup_task_id"] is None  # blocked != active work

    # Flip to an active status: now it is also the dedup source.
    with sqlite3.connect(str(initialized_db)) as conn:
        conn.execute(
            "UPDATE tasks SET status = 'running' WHERE id = 'zf-state-blocked'"
        )
        conn.commit()

    res_active = sc.check_board_setup_status(
        "state",
        has_key=HAS_KEY,
        path_key=PATH_KEY,
        preview_key=PREVIEW_KEY,
        target_relpath="openwiki",
        title_prefix="chore(repo): setup",
        dedup_substring="setup:ow",
    )
    assert res_active["dedup_task_id"] == "zf-state-blocked"
    assert res_active["dedup_task_status"] == "running"


def test_check_status_env_skip_clone_restored_was_none(
    initialized_db: Path, tmp_path: Path, monkeypatch
):
    """ZEROFACTORY_SKIP_CLONE is forced to '1' during the resolver call and
    removed afterwards when it was not set before."""
    _insert_board(initialized_db, "enva", git_url="https://example.com/x.git")
    repo = _make_repo(tmp_path, "enva_repo")

    captured: dict = {}

    def fake_resolver(board):
        captured["during"] = os.environ.get("ZEROFACTORY_SKIP_CLONE")
        return repo

    monkeypatch.setattr(sc, "get_repo_resolver", lambda: fake_resolver)
    monkeypatch.delenv("ZEROFACTORY_SKIP_CLONE", raising=False)

    sc.check_board_setup_status(
        "enva",
        has_key=HAS_KEY,
        path_key=PATH_KEY,
        preview_key=PREVIEW_KEY,
        target_relpath="openwiki",
        title_prefix="chore(repo): setup",
        dedup_substring="setup:ow",
    )
    assert captured["during"] == "1"
    assert "ZEROFACTORY_SKIP_CLONE" not in os.environ


def test_check_status_env_skip_clone_restored_was_set(
    initialized_db: Path, tmp_path: Path, monkeypatch
):
    """A pre-existing ZEROFACTORY_SKIP_CLONE value is restored, not wiped."""
    _insert_board(initialized_db, "envb", git_url="https://example.com/x.git")
    repo = _make_repo(tmp_path, "envb_repo")

    captured: dict = {}

    def fake_resolver(board):
        captured["during"] = os.environ.get("ZEROFACTORY_SKIP_CLONE")
        return repo

    monkeypatch.setattr(sc, "get_repo_resolver", lambda: fake_resolver)
    monkeypatch.setenv("ZEROFACTORY_SKIP_CLONE", "7")

    sc.check_board_setup_status(
        "envb",
        has_key=HAS_KEY,
        path_key=PATH_KEY,
        preview_key=PREVIEW_KEY,
        target_relpath="openwiki",
        title_prefix="chore(repo): setup",
        dedup_substring="setup:ow",
    )
    assert captured["during"] == "1"
    assert os.environ.get("ZEROFACTORY_SKIP_CLONE") == "7"


# --- create_setup_task ------------------------------------------------------


def test_create_setup_task_dedup_does_not_call_create(
    initialized_db: Path, monkeypatch
):
    """When status_checker reports a dedup_task_id, we short-circuit and never
    call routes.tasks.create_task."""
    _insert_board(initialized_db, "cdupe")

    def status_checker(slug):
        return {
            "dedup_task_id": "zf-exist-task",
            "dedup_task_status": "running",
            "pending_task_id": "zf-exist-task",
        }

    with mock.patch("dashboard.routes.tasks.create_task") as mock_create:
        res = sc.create_setup_task(
            "cdupe",
            status_checker=status_checker,
            title="chore(repo): setup target",
            prompt_builder=lambda slug, repo_path=None: "prompt",
            files=["openwiki"],
            dedup_key="setup:ow",
            progress_label="OpenWiki",
            created_label="openwiki",
            actor="tester",
        )
        assert res["ok"] is True
        assert res["already_exists"] is True
        assert res["task_id"] == "zf-exist-task"
        assert res["status"] == "running"
        mock_create.assert_not_called()


def test_create_setup_task_board_not_found(initialized_db: Path):
    """Unknown board -> ok:False + error, no task created."""

    with mock.patch("dashboard.routes.tasks.create_task") as mock_create:
        res = sc.create_setup_task(
            "ghost-board",
            status_checker=lambda slug: {"dedup_task_id": None},
            title="chore(repo): setup target",
            prompt_builder=lambda slug, repo_path=None: "prompt",
            files=["openwiki"],
            dedup_key="setup:ow",
            progress_label="OpenWiki",
            created_label="openwiki",
        )
    assert res["ok"] is False
    assert "ghost-board" in res["error"]
    mock_create.assert_not_called()


def test_create_setup_task_create_path(
    initialized_db: Path, tmp_path: Path, monkeypatch
):
    """dedup_task_id is None -> create_task called once with expected TaskCreate
    fields; the returned task_id is propagated."""
    _insert_board(initialized_db, "create", git_url="https://example.com/x.git")
    repo = _make_repo(tmp_path, "create_repo")
    monkeypatch.setattr(sc, "get_repo_resolver", lambda: lambda board: repo)

    captured: dict = {}

    def prompt_builder(slug, repo_path=None):
        captured["slug"] = slug
        captured["repo_path"] = repo_path
        return f"prompt for {slug} at {repo_path}"

    with mock.patch(
        "dashboard.routes.tasks.create_task",
        return_value={"ok": True, "id": "zf-created-task"},
    ) as mock_create:
        res = sc.create_setup_task(
            "create",
            status_checker=lambda slug: {"dedup_task_id": None},
            title="chore(repo): setup target",
            prompt_builder=prompt_builder,
            files=["openwiki"],
            dedup_key="setup:ow",
            progress_label="OpenWiki",
            created_label="openwiki",
            actor="tester",
        )

    assert res["ok"] is True
    assert res["already_exists"] is False
    assert res["task_id"] == "zf-created-task"
    assert res["status"] == "todo"
    assert "zf-created-task" in res["message"]

    mock_create.assert_called_once()
    (req,) = mock_create.call_args[0]
    assert req.title == "chore(repo): setup target"
    assert req.status == "todo"
    assert req.priority == "P0"
    assert req.assignee == "zf-builder"
    assert req.board_slug == "create"
    assert req.category == "config"
    assert req.files == ["openwiki"]
    assert req.dedup_key == "setup:ow"
    assert req.actor == "tester"
    assert captured["repo_path"] == repo  # resolver result fed to the prompt
    assert captured["slug"] == "create"


def test_create_setup_task_allows_clone_at_setup_time(
    initialized_db: Path, tmp_path: Path, monkeypatch
):
    """Intentional asymmetry: create_setup_task resolves the repo path WITHOUT
    the ZEROFACTORY_SKIP_CLONE guard that check_board_setup_status applies, so
    setup-time creation is allowed to trigger a clone. Lock that contract in."""
    _insert_board(initialized_db, "cloneok", git_url="https://example.com/x.git")
    repo = _make_repo(tmp_path, "cloneok_repo")

    observed: dict = {}

    def fake_resolver(board):
        observed["skip_clone"] = os.environ.get("ZEROFACTORY_SKIP_CLONE")
        return repo

    monkeypatch.setattr(sc, "get_repo_resolver", lambda: fake_resolver)
    monkeypatch.delenv("ZEROFACTORY_SKIP_CLONE", raising=False)

    with mock.patch(
        "dashboard.routes.tasks.create_task",
        return_value={"ok": True, "id": "zf-clone-task"},
    ):
        res = sc.create_setup_task(
            "cloneok",
            status_checker=lambda slug: {"dedup_task_id": None},
            title="chore(repo): setup target",
            prompt_builder=lambda slug, repo_path=None: "prompt",
            files=["openwiki"],
            dedup_key="setup:ow",
            progress_label="OpenWiki",
            created_label="openwiki",
        )

    assert res["ok"] is True
    # No SKIP_CLONE guard at setup-creation time: the resolver saw the env as
    # unset (the status-check helper would have forced it to "1").
    assert observed["skip_clone"] is None
