"""Unit tests for dashboard dispatcher start/stop and setup status routes."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient


def _make_client() -> TestClient:
    from dashboard.plugin_api import router

    app = FastAPI()
    app.include_router(router, prefix="/api/plugins/zerofactory")
    return TestClient(app)


def test_dispatch_start_rejects_when_profiles_missing(tmp_path, monkeypatch):
    import profile_manager
    from dispatcher import scheduler as sched

    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("ZEROFACTORY_DB", str(tmp_path / "zf.db"))
    monkeypatch.setattr(
        profile_manager, "check_gh_auth_status", lambda use_cache=True: True
    )

    started_calls = []
    monkeypatch.setattr(
        sched, "start_background_dispatcher", lambda: started_calls.append(True) or True
    )

    client = _make_client()
    resp = client.post("/api/plugins/zerofactory/dispatch/start")
    assert resp.status_code == 400
    assert "hermes zerofactory setup" in resp.json()["detail"]
    assert started_calls == []


def test_dispatch_start_and_stop_lifecycle(tmp_path, monkeypatch):
    import cron
    import profile_manager
    from dispatcher import scheduler as sched

    hermes_home = tmp_path / "hermes"
    hermes_home.mkdir()
    monkeypatch.setenv("HERMES_HOME", str(hermes_home))
    monkeypatch.setenv("ZEROFACTORY_DB", str(tmp_path / "zf.db"))
    monkeypatch.setattr(
        profile_manager, "check_gh_auth_status", lambda use_cache=True: True
    )
    monkeypatch.setattr(cron, "ensure_builtin_cron_jobs", lambda: None)
    monkeypatch.setattr(sched, "run_dispatch_cycle", lambda *a, **kw: {"ok": True})
    monkeypatch.setattr(sched, "is_worker_or_child_process", lambda: False)

    profile_manager.ensure_zf_profiles()

    client = _make_client()
    try:
        # Initially stopped
        status_before = client.get("/api/plugins/zerofactory/setup/status").json()
        assert status_before["dispatcher_running"] is False
        assert status_before["dispatcher_in_process"] is False

        # Start from UI endpoint
        start_resp = client.post("/api/plugins/zerofactory/dispatch/start")
        assert start_resp.status_code == 200
        start_data = start_resp.json()
        assert start_data["ok"] is True
        assert start_data["started"] is True
        assert start_data["dispatcher_running"] is True
        assert start_data["dispatcher_in_process"] is True

        # Setup status reflects in-process running dispatcher
        status_running = client.get("/api/plugins/zerofactory/setup/status").json()
        assert status_running["dispatcher_running"] is True
        assert status_running["dispatcher_in_process"] is True

        # Second start is idempotent
        start_again = client.post("/api/plugins/zerofactory/dispatch/start").json()
        assert start_again["ok"] is True
        assert start_again["started"] is False

        # Stop from UI endpoint
        stop_resp = client.post("/api/plugins/zerofactory/dispatch/stop")
        assert stop_resp.status_code == 200
        stop_data = stop_resp.json()
        assert stop_data["ok"] is True
        assert stop_data["stopped"] is True
        assert stop_data["dispatcher_running"] is False

        # Setup status reflects stopped dispatcher
        status_after = client.get("/api/plugins/zerofactory/setup/status").json()
        assert status_after["dispatcher_running"] is False
        assert status_after["dispatcher_in_process"] is False
    finally:
        sched.stop_background_dispatcher()
