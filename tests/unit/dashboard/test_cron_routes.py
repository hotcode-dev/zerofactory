"""Unit tests for dashboard/routes/cron.py endpoints."""

from fastapi.testclient import TestClient


def test_get_cron_jobs(api_client: TestClient, default_board: str):
    """Verify listing cron jobs returns core watchdog and board scanners."""
    res = api_client.get("/api/plugins/zerofactory/cron")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["scheduler_enabled"] is True
    jobs = data["jobs"]
    assert len(jobs) >= 2

    # Check for core watchdog
    watchdog = next(
        (j for j in jobs if j["id"] == "zero-factory-task-queue-check"), None
    )
    assert watchdog is not None
    assert watchdog["category"] == "core"

    # Check for board scanner
    scanner = next(
        (
            j
            for j in jobs
            if j["id"] == f"zero-factory-improvement-scanner-{default_board}"
        ),
        None,
    )
    assert scanner is not None
    assert scanner["category"] == "scanner"
    assert scanner["scan_on_idle"] is True


def test_toggle_scheduler(api_client: TestClient):
    """Verify toggling scheduler."""
    res = api_client.post(
        "/api/plugins/zerofactory/cron/scheduler/toggle",
        json={"enabled": False},
    )
    assert res.status_code == 200
    assert res.json()["scheduler_enabled"] is False

    res2 = api_client.post(
        "/api/plugins/zerofactory/cron/scheduler/toggle",
        json={"enabled": True},
    )
    assert res2.status_code == 200
    assert res2.json()["scheduler_enabled"] is True


def test_cron_sync(api_client: TestClient):
    """Verify syncing cron jobs."""
    res = api_client.post("/api/plugins/zerofactory/cron/sync")
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert data["synced"] >= 1


def test_cron_job_update_and_reset(api_client: TestClient, default_board: str):
    """Verify updating and resetting a board scanner job."""
    job_id = f"zero-factory-improvement-scanner-{default_board}"

    # Update cooldown and max todo
    res = api_client.put(
        f"/api/plugins/zerofactory/cron/{job_id}",
        json={
            "idle_scan_cooldown_minutes": 30,
            "idle_scan_max_todo": 5,
            "scan_on_idle": False,
        },
    )
    assert res.status_code == 200
    assert res.json()["ok"] is True

    # Toggle job
    res_toggle = api_client.post(
        f"/api/plugins/zerofactory/cron/{job_id}/toggle",
        json={"enabled": True},
    )
    assert res_toggle.status_code == 200
    assert res_toggle.json()["enabled"] is True

    # Reset job
    res_reset = api_client.post(f"/api/plugins/zerofactory/cron/{job_id}/reset")
    assert res_reset.status_code == 200
    assert res_reset.json()["ok"] is True


def test_cron_run_job(api_client: TestClient, default_board: str):
    """Verify triggering an immediate run of a cron job."""
    res = api_client.post(
        "/api/plugins/zerofactory/cron/zero-factory-task-queue-check/run"
    )
    assert res.status_code == 200
    assert res.json()["ok"] is True

    # Unknown job
    res_unknown = api_client.post("/api/plugins/zerofactory/cron/unknown-job-id/run")
    assert res_unknown.status_code == 400


def test_cron_job_pause_persists_status(api_client: TestClient, default_board: str):
    """Verify pausing a job updates its enabled flag and paused state in GET /cron."""
    job_id = f"zero-factory-improvement-scanner-{default_board}"

    # Pause job
    res_pause = api_client.post(
        f"/api/plugins/zerofactory/cron/{job_id}/toggle",
        json={"enabled": False},
    )
    assert res_pause.status_code == 200
    assert res_pause.json()["enabled"] is False

    # Check GET /cron reflects paused state
    res = api_client.get("/api/plugins/zerofactory/cron")
    assert res.status_code == 200
    jobs = res.json()["jobs"]
    scanner = next((j for j in jobs if j["id"] == job_id), None)
    assert scanner is not None
    assert scanner["enabled"] is False
    assert scanner["state"] == "paused"

    # Resume job
    res_resume = api_client.post(
        f"/api/plugins/zerofactory/cron/{job_id}/toggle",
        json={"enabled": True},
    )
    assert res_resume.status_code == 200
    assert res_resume.json()["enabled"] is True

    # Check GET /cron reflects active state
    res2 = api_client.get("/api/plugins/zerofactory/cron")
    scanner2 = next((j for j in res2.json()["jobs"] if j["id"] == job_id), None)
    assert scanner2 is not None
    assert scanner2["enabled"] is True
    assert scanner2["state"] == "active"
