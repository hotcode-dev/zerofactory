"""Subprocess E2E tests for Hermes listing compliance & setup/start lifecycle."""

from __future__ import annotations

import json
import os
import sqlite3
import stat
import subprocess
import sys
import textwrap
import time
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]


def _make_stub_gh(bin_dir: Path, exit_code: int = 0) -> None:
    bin_dir.mkdir(parents=True, exist_ok=True)
    gh_path = bin_dir / "gh"
    gh_path.write_text(f"#!/usr/bin/env sh\nexit {exit_code}\n", encoding="utf-8")
    gh_path.chmod(gh_path.stat().st_mode | stat.S_IXUSR)


def _subprocess_env(hermes_home: Path, db_path: Path, bin_dir: Path) -> dict[str, str]:
    env = os.environ.copy()
    env.pop("ZEROFACTORY_SKIP_WORKER_SPAWN", None)
    env["HERMES_HOME"] = str(hermes_home)
    env["ZEROFACTORY_DB"] = str(db_path)
    env["ZEROFACTORY_DISABLE_DISPATCHER"] = "0"
    env["PYTHONPATH"] = str(REPO_ROOT)
    env["PATH"] = f"{bin_dir}{os.pathsep}{env.get('PATH', '')}"
    env["PYTHONUNBUFFERED"] = "1"
    return env


def _run_py(code: str, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-c", textwrap.dedent(code)],
        cwd=str(REPO_ROOT),
        env=env,
        capture_output=True,
        text=True,
        timeout=30,
    )


def _cli_code(namespace_expr: str) -> str:
    return f"""
        import argparse
        import __init__ as zerofactory

        captured = {{}}
        class Ctx:
            def register_cli_command(self, **kwargs):
                captured["handler_fn"] = kwargs["handler_fn"]

        zerofactory.register(Ctx())
        captured["handler_fn"]({namespace_expr})
    """


def test_passive_load_then_setup_status_and_start_lifecycle(tmp_path):
    hermes_home = tmp_path / "hermes"
    (hermes_home / "skills").mkdir(parents=True)
    (hermes_home / "config.yaml").write_text("model: gpt-4o\n", encoding="utf-8")
    (hermes_home / ".env").write_text("OPENAI_API_KEY=secret\n", encoding="utf-8")

    personal = hermes_home / "profiles" / "personal"
    personal.mkdir(parents=True)
    (personal / "config.yaml").write_text("model: personal\n", encoding="utf-8")

    db_path = tmp_path / "zerofactory.db"
    bin_dir = tmp_path / "bin"
    _make_stub_gh(bin_dir, exit_code=0)
    env = _subprocess_env(hermes_home, db_path, bin_dir)

    # 1. Fresh import + register() must be passive and leave HERMES_HOME profiles/threads untouched
    res_load = _run_py(
        """
        import json, threading
        from unittest.mock import MagicMock
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        import __init__ as zerofactory

        ctx = MagicMock()
        zerofactory.register(ctx)

        from dashboard.plugin_api import router
        threads = [t.name for t in threading.enumerate()]
        app = FastAPI()
        app.include_router(router, prefix="/api/plugins/zerofactory")
        status = TestClient(app).get("/api/plugins/zerofactory/setup/status").json()
        print(json.dumps({"threads": threads, "status": status}))
        """,
        env,
    )
    assert res_load.returncode == 0, res_load.stderr
    payload = json.loads(res_load.stdout.strip().splitlines()[-1])
    assert not any("dispatcher" in t.lower() for t in payload["threads"])
    assert payload["status"]["profiles_ready"] is False
    assert payload["status"]["dispatcher_running"] is False
    assert not (hermes_home / "profiles" / "zf-builder").exists()

    # 2. `start` before `setup` exits non-zero with clear guidance
    res_start_early = _run_py(_cli_code('argparse.Namespace(action="start")'), env)
    assert res_start_early.returncode == 1
    assert "hermes zerofactory setup" in res_start_early.stdout

    # 3. `setup` provisions only zf-* profiles and verifies gh auth
    res_setup = _run_py(
        _cli_code('argparse.Namespace(action="setup", force=False)'), env
    )
    assert res_setup.returncode == 0, res_setup.stderr
    assert "GitHub CLI authentication verified." in res_setup.stdout
    for role in ("zf-orchestrator", "zf-goldfish", "zf-builder", "zf-reviewer"):
        assert (hermes_home / "profiles" / role / "config.yaml").is_file()

    # Provisioned zf-builder/config.yaml pins openwiki@0.9.0 and keeps instruction guard
    builder_cfg = yaml.safe_load(
        (hermes_home / "profiles" / "zf-builder" / "config.yaml").read_text(
            encoding="utf-8"
        )
    )
    assert (
        "security" not in builder_cfg
        or builder_cfg["security"].get("protected_instruction_files") is not False
    )
    openwiki_args = builder_cfg["mcp_servers"]["openwiki"]["args"]
    assert "openwiki@0.9.0" in openwiki_args
    assert "openwiki" not in openwiki_args

    # Root & non-zf profile remain untouched
    assert list((hermes_home / "skills").iterdir()) == []
    assert (hermes_home / "config.yaml").read_text(
        encoding="utf-8"
    ) == "model: gpt-4o\n"
    assert (hermes_home / ".env").read_text(
        encoding="utf-8"
    ) == "OPENAI_API_KEY=secret\n"
    assert (personal / "config.yaml").read_text(encoding="utf-8") == "model: personal\n"

    # 4. `/setup/status` now reports profiles_ready and gh_authenticated
    res_status = _run_py(
        """
        import json
        from fastapi import FastAPI
        from fastapi.testclient import TestClient
        from dashboard.plugin_api import router

        app = FastAPI()
        app.include_router(router, prefix="/api/plugins/zerofactory")
        print(json.dumps(TestClient(app).get("/api/plugins/zerofactory/setup/status").json()))
        """,
        env,
    )
    assert res_status.returncode == 0, res_status.stderr
    status_after = json.loads(res_status.stdout.strip().splitlines()[-1])
    assert status_after["profiles_ready"] is True
    assert status_after["missing_profiles"] == []
    assert status_after["gh_authenticated"] is True

    # 5. `start` runs foreground dispatcher and exits cleanly on SIGTERM
    proc = subprocess.Popen(
        [
            sys.executable,
            "-c",
            textwrap.dedent(_cli_code('argparse.Namespace(action="start")')),
        ],
        cwd=str(REPO_ROOT),
        env=env,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    try:
        started_line = ""
        assert proc.stdout is not None
        for _ in range(50):
            line = proc.stdout.readline()
            if "Zero Factory dispatcher started (foreground)." in line:
                started_line = line
                break
        assert started_line, "Dispatcher foreground loop did not start"
        proc.terminate()
        stdout_rest, stderr_rest = proc.communicate(timeout=10)
        assert proc.returncode == 0, stderr_rest
        assert "Zero Factory dispatcher stopped." in stdout_rest
    finally:
        if proc.poll() is None:
            proc.kill()
            proc.wait(timeout=5)


def test_hermes_home_profiles_subdir_not_stripped_and_worker_env_no_yolo_reaper_and_labels(
    tmp_path,
):
    # Requirement 3: HERMES_HOME ending in /profiles/work must NOT be stripped
    hermes_home = tmp_path / "hermes" / "profiles" / "work"
    hermes_home.mkdir(parents=True)
    db_path = tmp_path / "zerofactory.db"
    bin_dir = tmp_path / "bin"
    _make_stub_gh(bin_dir, exit_code=0)

    capture_file = tmp_path / "hermes_capture.json"
    stub_hermes = bin_dir / "hermes"
    stub_hermes.write_text(
        textwrap.dedent(
            f"""\
            #!{sys.executable}
            import json, os, sys
            from pathlib import Path

            Path({str(capture_file)!r}).write_text(
                json.dumps({{"argv": sys.argv[1:], "env": dict(os.environ)}}),
                encoding="utf-8",
            )
            print("Error: Command requires approval in non-interactive mode")
            sys.exit(1)
            """
        ),
        encoding="utf-8",
    )
    stub_hermes.chmod(stub_hermes.stat().st_mode | stat.S_IXUSR)

    env = _subprocess_env(hermes_home, db_path, bin_dir)
    env["HERMES_BIN"] = str(stub_hermes)
    env["SECRET_PARENT_TOKEN"] = "should-not-leak"

    # Setup creates zf-* inside the exact HERMES_HOME (not parent)
    res_setup = _run_py(
        _cli_code('argparse.Namespace(action="setup", force=False)'), env
    )
    assert res_setup.returncode == 0, res_setup.stderr
    assert (hermes_home / "profiles" / "zf-builder" / "config.yaml").is_file()
    assert not (tmp_path / "hermes" / "profiles" / "zf-builder").exists()

    # Requirement 1, 5, 8: spawn_agent_worker -> stub hermes -> reaper -> issue import
    res_flow = _run_py(
        f"""
        import json, os, sqlite3, time
        from pathlib import Path
        from dashboard.db import init_db
        from dispatcher.worker_spawner import spawn_agent_worker
        from dispatcher.reaper import reap_active_workers
        from dispatcher.github_pr import is_task_automerge_enabled
        from issues.base import ExternalIssue
        from issues.importer import import_external_issue

        init_db()
        db = Path(os.environ["ZEROFACTORY_DB"])
        now = int(time.time())
        with sqlite3.connect(str(db)) as conn:
            conn.execute(
                "INSERT INTO boards (slug, created_at, updated_at) VALUES ('b1', ?, ?)",
                (now, now),
            )
            conn.execute(
                "INSERT INTO board_repositories (board_slug, repo_alias, git_url, created_at, updated_at) "
                "VALUES ('b1', 'main', 'https://example.com/repo.git', ?, ?)",
                (now, now),
            )
            conn.execute(
                "INSERT INTO tasks (id, board_slug, title, description, status, assignee, priority, created_at, updated_at) "
                "VALUES ('t-yolo-check', 'b1', 'Test worker', 'Desc', 'running', 'zf-builder', 'P1', ?, ?)",
                (now, now),
            )
            conn.commit()

        workdir = Path({str(tmp_path)!r}) / "workdir"
        workdir.mkdir(exist_ok=True)
        pid, _ = spawn_agent_worker(
            task_id="t-yolo-check",
            title="Test worker",
            description="Desc",
            priority="P1",
            assignee="zf-builder",
            workspace_path=str(workdir),
            branch_name="feat/test",
            board_slug="b1",
        )
        assert pid is not None

        # Wait for stub hermes to finish and write capture + log
        capture_path = Path({str(capture_file)!r})
        log_path = Path(os.environ["HERMES_HOME"]) / "logs" / "worker_t-yolo-check.log"
        for _ in range(50):
            if capture_path.exists() and log_path.exists() and "approval" in log_path.read_text(encoding="utf-8"):
                break
            time.sleep(0.1)

        with sqlite3.connect(str(db)) as conn:
            conn.row_factory = sqlite3.Row
            conn.execute(
                "UPDATE tasks SET metadata = ? WHERE id = 't-yolo-check'",
                (json.dumps({{"worker_pid": pid, "worker_started_at": now - 60}}),),
            )
            conn.commit()
            cur = conn.cursor()
            reap_active_workers(cur, int(time.time()))
            conn.commit()
            row = dict(
                conn.execute(
                    "SELECT status, metadata FROM tasks WHERE id = 't-yolo-check'"
                ).fetchone()
            )

        ext = ExternalIssue(
            id="99",
            source="github",
            key="#99",
            title="External issue",
            body="Body",
            url="https://github.com/org/repo/issues/99",
            labels=["bug", "automerge", "yolo"],
            author="outsider",
            issue_type="bug",
        )
        imp = import_external_issue(ext, board_slug="b1", db_path=db)
        imp_id = imp.get("id") or imp["task"]["id"]
        with sqlite3.connect(str(db)) as conn:
            conn.row_factory = sqlite3.Row
            imp_task = dict(conn.execute("SELECT * FROM tasks WHERE id = ?", (imp_id,)).fetchone())

        print(json.dumps({{
            "reaped": row,
            "imported_tags": json.loads(imp_task["tags"]),
            "automerge_enabled": is_task_automerge_enabled(imp_task, {{"automerge": False}}),
        }}))
        """,
        env,
    )
    assert res_flow.returncode == 0, res_flow.stderr
    flow = json.loads(res_flow.stdout.strip().splitlines()[-1])

    # Verify spawned child CLI args & minimal env
    captured = json.loads(capture_file.read_text(encoding="utf-8"))
    assert "--yolo" not in captured["argv"]
    assert "--accept-hooks" not in captured["argv"]
    assert "SECRET_PARENT_TOKEN" not in captured["env"]
    assert captured["env"]["HERMES_HOME"] == str(hermes_home.resolve())

    # Verify reaper routed approval failure to blocked (human-gate)
    assert flow["reaped"]["status"] == "blocked"
    reaped_meta = json.loads(flow["reaped"]["metadata"])
    assert reaped_meta["blocked_reason_type"] == "human-gate"

    # Verify external issue automerge/yolo labels ignored
    assert "tag:bug" in flow["imported_tags"]
    assert "tag:automerge" not in flow["imported_tags"]
    assert "tag:yolo" not in flow["imported_tags"]
    assert flow["automerge_enabled"] is False
