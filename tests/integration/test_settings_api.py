"""Integration tests for Settings API endpoints (/api/plugins/zerofactory/settings)."""

import pytest
from fastapi.testclient import TestClient


def test_get_and_patch_settings(api_client: TestClient):
    """Verify getting default settings and patching settings values."""
    # 1. GET defaults
    res = api_client.get("/api/plugins/zerofactory/settings")
    assert res.status_code == 200
    data = res.json()
    assert "settings" in data
    settings = data["settings"]
    assert "max_active_tasks" in settings
    assert "enable_cron_scheduler" in settings

    # 2. PATCH settings
    patch_res = api_client.patch(
        "/api/plugins/zerofactory/settings",
        json={
            "max_active_tasks": 7,
            "max_concurrent_llm_workers": 3,
            "enable_cron_scheduler": False,
        },
    )
    assert patch_res.status_code == 200
    updated = patch_res.json()["settings"]
    assert updated["max_active_tasks"] == 7
    assert updated["max_concurrent_llm_workers"] == 3
    assert updated["enable_cron_scheduler"] is False

    # 3. GET verifies persistence
    get_after = api_client.get("/api/plugins/zerofactory/settings").json()["settings"]
    assert get_after["max_active_tasks"] == 7
    assert get_after["enable_cron_scheduler"] is False
