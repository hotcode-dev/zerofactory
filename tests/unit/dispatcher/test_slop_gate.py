"""Unit tests for dispatcher/slop_gate.py: deterministic anti-slop gate and Diff Hygiene Scorecard."""

import subprocess
from pathlib import Path

from dispatcher.context_builder import digest_reviewer_git_context
from dispatcher.slop_gate import (
    DEFAULT_MAX_DIFF_LINES,
    analyze_workspace_diff,
    build_diff_hygiene_scorecard,
    extract_do_not_touch_patterns,
    is_dependency_file,
    is_test_file,
    run_deterministic_slop_gate,
)


def _init_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    subprocess.run(
        ["git", "init", "-b", "main"], cwd=str(repo), check=True, capture_output=True
    )
    subprocess.run(
        ["git", "config", "user.name", "Test User"], cwd=str(repo), check=True
    )
    subprocess.run(
        ["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True
    )
    (repo / "app.py").write_text("def greet():\n    return 'hi'\n")
    (repo / "tests").mkdir()
    (repo / "tests" / "test_app.py").write_text(
        "def test_greet():\n" + "".join(f"    assert {i} == {i}\n" for i in range(12))
    )
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(
        ["git", "commit", "-m", "initial"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    subprocess.run(
        ["git", "checkout", "-b", "task/slop-test"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )
    return repo


def test_file_classifiers():
    assert is_test_file("tests/unit/test_foo.py")
    assert is_test_file("src/utils.test.ts")
    assert is_test_file("pkg/foo_test.go")
    assert not is_test_file("dispatcher/slop_gate.py")

    assert is_dependency_file("package.json")
    assert is_dependency_file("pyproject.toml")
    assert is_dependency_file("requirements-dev.txt")
    assert not is_dependency_file("dispatcher/slop_gate.py")


def test_slop_gate_passes_clean_diff(tmp_path: Path):
    repo = _init_repo(tmp_path)
    (repo / "app.py").write_text(
        "def greet(name: str = 'world') -> str:\n    return f'hi {name}'\n"
    )
    passed, msg, code = run_deterministic_slop_gate(repo, target_branch="main")
    assert passed is True
    assert code == 0
    assert "Slop gate passed" in msg


def test_slop_gate_blocks_debugger_todo_and_skipped_test(tmp_path: Path):
    repo = _init_repo(tmp_path)
    # Untracked new production file with debugger + placeholder comment
    (repo / "feature.py").write_text(
        "def run():\n"
        "    breakpoint()\n"
        "    # " + "TODO" + ": implement real logic\n"
        "    return 1\n"
    )
    # Modified test file with skipped test
    (repo / "tests" / "test_app.py").write_text(
        "import pytest\n\n"
        "@pytest.mark.skip(reason='flaky')\n"
        "def test_greet():\n"
        "    assert True\n"
    )

    passed, msg, code = run_deterministic_slop_gate(repo, target_branch="main")
    assert passed is False
    assert code == 1
    assert "[debug_leftover] feature.py:2" in msg
    assert "[placeholder_todo] feature.py:3" in msg
    assert "[test_disabled] tests/test_app.py:3" in msg


def test_slop_gate_skip_env_and_non_git(tmp_path: Path, monkeypatch):
    # Non-git directory passes safely
    empty = tmp_path / "not_a_repo"
    empty.mkdir()
    passed, _, code = run_deterministic_slop_gate(empty)
    assert passed is True
    assert code == 0

    # ZEROFACTORY_SKIP_SLOP_GATE bypasses errors
    repo = _init_repo(tmp_path)
    (repo / "bad.py").write_text("breakpoint()\n")
    monkeypatch.setenv("ZEROFACTORY_SKIP_SLOP_GATE", "1")
    passed, msg, code = run_deterministic_slop_gate(repo, target_branch="main")
    assert passed is True
    assert code == 0
    assert "ZEROFACTORY_SKIP_SLOP_GATE" in msg


def test_slop_gate_optional_diff_budget(tmp_path: Path, monkeypatch):
    repo = _init_repo(tmp_path)
    (repo / "big.py").write_text("\n".join(f"x_{i} = {i}" for i in range(30)) + "\n")
    monkeypatch.setenv("ZEROFACTORY_MAX_DIFF_LINES", "20")

    passed, msg, code = run_deterministic_slop_gate(
        repo, target_branch="main", skip_untested_check=True
    )
    assert passed is False
    assert code == 1
    assert "[diff_budget_exceeded]" in msg

    # Setting ZEROFACTORY_MAX_DIFF_LINES=0 disables the hard diff cap
    monkeypatch.setenv("ZEROFACTORY_MAX_DIFF_LINES", "0")
    passed_unbounded, _, _ = run_deterministic_slop_gate(
        repo, target_branch="main", skip_untested_check=True
    )
    assert passed_unbounded is True

    # Default cap (800 net lines) applies when ZEROFACTORY_MAX_DIFF_LINES is unset
    monkeypatch.delenv("ZEROFACTORY_MAX_DIFF_LINES", raising=False)
    assert DEFAULT_MAX_DIFF_LINES == 800
    (repo / "big.py").write_text("\n".join(f"x_{i} = {i}" for i in range(805)) + "\n")
    passed_default, msg_default, _ = run_deterministic_slop_gate(
        repo, target_branch="main", skip_untested_check=True
    )
    assert passed_default is False
    assert "[diff_budget_exceeded]" in msg_default


def test_slop_gate_do_not_touch_violation(tmp_path: Path):
    spec = (
        "## Implementation Plan\n"
        "- Update `app.py`\n\n"
        "## Do Not Touch / Non-Goals\n"
        "- Do not modify `dispatcher/state_machine.py` or `dashboard/dist/*`.\n"
        "- Keep `package-lock.json` untouched.\n\n"
        "## Verification\n"
        "- Run `pytest -v`\n"
    )
    patterns = extract_do_not_touch_patterns(spec)
    assert "dispatcher/state_machine.py" in patterns
    assert "dashboard/dist/*" in patterns
    assert "package-lock.json" in patterns
    assert "pytest -v" not in patterns

    repo = _init_repo(tmp_path)
    # Modify an excluded path (dashboard/dist/index.js) and a regular forbidden path
    (repo / "dashboard" / "dist").mkdir(parents=True)
    (repo / "dashboard" / "dist" / "index.js").write_text("console.log('touched');\n")
    (repo / "dispatcher").mkdir()
    (repo / "dispatcher" / "state_machine.py").write_text("X = 1\n")

    passed, msg, code = run_deterministic_slop_gate(
        repo, target_branch="main", spec_text=spec
    )
    assert passed is False
    assert code == 1
    assert "[do_not_touch_violation] dashboard/dist/index.js" in msg
    assert "[do_not_touch_violation] dispatcher/state_machine.py" in msg


def test_slop_gate_assertion_free_and_mock_heavy_tests(tmp_path: Path):
    repo = _init_repo(tmp_path)
    # Add an assertion-free Python test function and a mock-heavy test function
    (repo / "tests" / "test_new.py").write_text(
        "from unittest.mock import MagicMock, patch\n\n"
        "def test_no_assert():\n"
        "    x = 1 + 1\n"
        "    # comment only, no assert\n\n"
        "def test_heavy_mocks():\n"
        "    m1 = MagicMock()\n"
        "    m2 = MagicMock()\n"
        "    m3 = MagicMock()\n"
        "    m4 = MagicMock()\n"
        "    assert m1 is not None\n"
    )
    # Also add an assertion-free JS test
    (repo / "tests" / "ui.test.js").write_text(
        "test('renders without crashing', () => {\n"
        "  const el = document.createElement('div');\n"
        "});\n"
    )

    passed, msg, code = run_deterministic_slop_gate(repo, target_branch="main")
    assert passed is False
    assert code == 1
    assert "[assertion_free_test] tests/test_new.py:3" in msg
    assert "[assertion_free_test] tests/ui.test.js:1" in msg

    # Fix assertions and commit to verify mock_heavy_test warning in scorecard
    (repo / "tests" / "test_new.py").write_text(
        "from unittest.mock import MagicMock\n\n"
        "def test_heavy_mocks():\n"
        "    m1 = MagicMock()\n"
        "    m2 = MagicMock()\n"
        "    m3 = MagicMock()\n"
        "    m4 = MagicMock()\n"
        "    assert m1 is not None\n"
    )
    (repo / "tests" / "ui.test.js").unlink()
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(
        ["git", "commit", "-m", "test: add mock heavy test"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )

    scorecard = build_diff_hygiene_scorecard(repo, target_branch="main")
    assert "[mock_heavy_test]" in scorecard
    assert "4 mocks vs 1 assertions" in scorecard


def test_slop_gate_untested_production_diff(tmp_path: Path, monkeypatch):
    repo = _init_repo(tmp_path)
    # Docs-only change (>20 lines) does NOT trigger untested_production_diff
    (repo / "README.md").write_text("\n".join(f"Doc line {i}" for i in range(30)) + "\n")
    passed_docs, _, _ = run_deterministic_slop_gate(repo, target_branch="main")
    assert passed_docs is True

    # >20 net lines of production Python code with 0 test lines triggers untested_production_diff
    (repo / "service.py").write_text(
        "\n".join(f"def fn_{i}(): return {i}" for i in range(25)) + "\n"
    )
    passed_prod, msg_prod, _ = run_deterministic_slop_gate(repo, target_branch="main")
    assert passed_prod is False
    assert "[untested_production_diff]" in msg_prod

    # Explicit task metadata skip_untested_check=True bypasses the check
    passed_skip, _, _ = run_deterministic_slop_gate(
        repo, target_branch="main", skip_untested_check=True
    )
    assert passed_skip is True

    # Adding a test with an assertion satisfies the check
    (repo / "tests" / "test_service.py").write_text(
        "from service import fn_0\n\ndef test_fn_0():\n    assert fn_0() == 0\n"
    )
    passed_tested, _, _ = run_deterministic_slop_gate(repo, target_branch="main")
    assert passed_tested is True


def test_scorecard_surfaces_warnings_and_truncation(tmp_path: Path):
    repo = _init_repo(tmp_path)
    (repo / "app.py").write_text(
        "def greet():\n"
        "    try:\n"
        "        return 'hi'  # noqa\n"
        "    except ValueError:\n"
        "        pass\n"
    )
    (repo / "package.json").write_text('{"name": "demo"}\n')
    # Delete >10 lines of existing tests
    (repo / "tests" / "test_app.py").write_text("def test_greet():\n    assert True\n")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True)
    subprocess.run(
        ["git", "commit", "-m", "feat: noisy change"],
        cwd=str(repo),
        check=True,
        capture_output=True,
    )

    report = analyze_workspace_diff(
        repo, target_branch="main", include_working_tree=False
    )
    assert "package.json" in report.dependency_files_touched
    warning_rules = {w.rule for w in report.warnings}
    assert "suppressor_added" in warning_rules
    assert "empty_except" in warning_rules
    assert "net_test_deletion" in warning_rules

    scorecard = build_diff_hygiene_scorecard(
        repo, target_branch="main", is_diff_truncated=True
    )
    assert "Diff Hygiene Scorecard" in scorecard
    assert "Dependency Manifests Modified" in scorecard
    assert "`package.json`" in scorecard
    assert "Truncated Preview" in scorecard
    assert "suppressor_added" in scorecard
    assert "empty_except" in scorecard
    assert "net_test_deletion" in scorecard

    # Verify digest_reviewer_git_context integrates the scorecard
    ctx = digest_reviewer_git_context(repo, target_branch="main")
    assert "Diff Hygiene Scorecard" in ctx
    assert "Dependency Manifests Modified" in ctx


def test_record_rejection_memory_and_reject_task_loop(initialized_db: Path):
    """Human spec rejection automatically records a deduplicated rejected_path memory."""
    import time

    from dashboard.models import TaskRejectRequest
    from dashboard.plugin_api import get_db_conn, record_rejection_memory, reject_task

    now = int(time.time())
    task_id = "zf-reject-mem-1"
    with get_db_conn() as conn:
        conn.execute(
            "INSERT INTO boards (slug, description, created_at, updated_at) VALUES ('slop-board', 'Slop Board', ?, ?)",
            (now, now),
        )
        conn.execute(
            "INSERT INTO tasks (id, board_slug, title, status, assignee, priority, created_at, updated_at) "
            "VALUES (?, 'slop-board', 'Add caching layer', 'triage', 'human', 'P1', ?, ?)",
            (task_id, now, now),
        )
        conn.commit()

    # Plain natural-language rejection feedback should auto-record as rejected_path
    reject_task(
        task_id,
        TaskRejectRequest(
            feedback="Do not add a custom Redis wrapper; reuse the existing SQLite cache.",
            actor="alice",
        ),
    )

    with get_db_conn() as conn:
        rows = conn.execute(
            "SELECT category, content, tags, author FROM board_memories WHERE board_slug = 'slop-board'"
        ).fetchall()
        assert len(rows) == 1
        assert rows[0]["category"] == "rejected_path"
        assert "Add caching layer" in rows[0]["content"]
        assert "reuse the existing SQLite cache" in rows[0]["content"]
        assert "human-rejection" in rows[0]["tags"]
        assert rows[0]["author"] == "alice"

        # Duplicate feedback is deduplicated
        dup = record_rejection_memory(
            conn,
            board_slug="slop-board",
            feedback="Do not add a custom Redis wrapper; reuse the existing SQLite cache.",
            task_id=task_id,
            task_title="Add caching layer",
            author="alice",
        )
        assert dup == []

        # Trivial short feedback (<10 chars) is ignored
        trivial = record_rejection_memory(
            conn,
            board_slug="slop-board",
            feedback="no",
            task_id=task_id,
            task_title="Add caching layer",
            author="alice",
        )
        assert trivial == []
