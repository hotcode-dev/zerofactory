"""Shared fixtures and configuration for Zero Factory tests."""

from __future__ import annotations

import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import Generator, Iterator

import pytest

# Ensure repository root is on sys.path
PLUGIN_ROOT = Path(__file__).resolve().parent.parent
if str(PLUGIN_ROOT) not in sys.path:
    sys.path.insert(0, str(PLUGIN_ROOT))

# Ensure hermetic defaults before any tests run
os.environ.setdefault("ZEROFACTORY_SKIP_GIT", "1")
os.environ.setdefault("ZEROFACTORY_SKIP_CRON_SYNC", "1")
os.environ.setdefault("ZEROFACTORY_DISABLE_DISPATCHER", "1")
os.environ.setdefault("ZEROFACTORY_SKIP_WORKER_SPAWN", "1")


@pytest.fixture
def isolated_env() -> Iterator[dict]:
    """Preserve and restore os.environ around a test."""
    orig = dict(os.environ)
    try:
        yield orig
    finally:
        os.environ.clear()
        os.environ.update(orig)


@pytest.fixture
def test_db_path(tmp_path: Path) -> Path:
    """Provide a path to a fresh SQLite database for tests."""
    return tmp_path / "zerofactory_test.db"


@pytest.fixture
def initialized_db(test_db_path: Path, isolated_env: dict) -> Path:
    """Initialize a fresh Zero Factory database schema and set environment variable."""
    from dashboard.plugin_api import init_db

    os.environ["ZEROFACTORY_DB"] = str(test_db_path)
    init_db(db_path=test_db_path, force=True)
    return test_db_path


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """Create and initialize a clean local git repository."""
    repo = tmp_path / "test_repo"
    repo.mkdir(parents=True)
    subprocess.run(["git", "init", "-b", "main"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.name", "Test User"], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "config", "user.email", "test@example.com"], cwd=str(repo), check=True, capture_output=True)
    (repo / "README.md").write_text("# Test Repo\n", encoding="utf-8")
    subprocess.run(["git", "add", "."], cwd=str(repo), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "chore: initial commit"], cwd=str(repo), check=True, capture_output=True)
    return repo


@pytest.fixture
def api_client(initialized_db: Path):
    """Provide a FastAPI TestClient wired to the Zero Factory plugin router."""
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from dashboard.plugin_api import router

    app = FastAPI()
    app.include_router(router, prefix="/api/plugins/zerofactory")
    return TestClient(app)
