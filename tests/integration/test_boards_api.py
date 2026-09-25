"""Integration tests for Board API endpoints (/api/plugins/zerofactory/boards)."""

import pytest
from fastapi.testclient import TestClient


def test_create_and_list_boards(api_client: TestClient):
    """Verify creating a board and listing boards via API."""
    res = api_client.post(
        "/api/plugins/zerofactory/boards",
        json={
            "git_url": "https://github.com/hotcode-dev/zerofactory.git",
            "description": "Zero Factory multi-agent coordination",
            "target_branch": "main",
            "max_concurrent_running": 2,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    slug = data["slug"]
    assert slug == "hotcode-dev-zerofactory"

    # List boards
    list_res = api_client.get("/api/plugins/zerofactory/boards")
    assert list_res.status_code == 200
    boards = list_res.json()["boards"]
    matching = [b for b in boards if b["slug"] == slug]
    assert len(matching) == 1
    assert matching[0]["target_branch"] == "main"
    assert matching[0]["max_concurrent_running"] == 2


def test_update_board(api_client: TestClient):
    """Verify updating board target_branch and max_concurrent_running."""
    # First create
    api_client.post(
        "/api/plugins/zerofactory/boards",
        json={"git_url": "https://github.com/test-org/repo-b.git"},
    )

    # Update
    update_res = api_client.patch(
        "/api/plugins/zerofactory/boards/test-org-repo-b",
        json={
            "description": "Updated description",
            "target_branch": "release/v1",
            "max_concurrent_running": 3,
        },
    )
    assert update_res.status_code == 200
    assert update_res.json()["ok"] is True

    # Check GET
    boards = api_client.get("/api/plugins/zerofactory/boards").json()["boards"]
    board = next(b for b in boards if b["slug"] == "test-org-repo-b")
    assert board["description"] == "Updated description"
    assert board["target_branch"] == "release/v1"
    assert board["max_concurrent_running"] == 3


def test_delete_board(api_client: TestClient):
    """Verify deleting a board."""
    api_client.post(
        "/api/plugins/zerofactory/boards",
        json={"git_url": "https://github.com/delete-org/repo-del.git"},
    )

    del_res = api_client.delete("/api/plugins/zerofactory/boards/delete-org-repo-del")
    assert del_res.status_code == 200
    assert del_res.json()["ok"] is True

    # Should no longer be present
    boards = api_client.get("/api/plugins/zerofactory/boards").json()["boards"]
    assert not any(b["slug"] == "delete-org-repo-del" for b in boards)
