"""Integration tests for Board API endpoints (/api/plugins/zerofactory/boards)."""

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


def test_board_precommit_endpoints(api_client: TestClient):
    """Verify precommit-status and setup-precommit API endpoints."""
    # Create board without auto setup
    create_res = api_client.post(
        "/api/plugins/zerofactory/boards",
        json={
            "git_url": "https://github.com/precommit-org/repo-pc.git",
            "auto_setup_precommit": False,
        },
    )
    assert create_res.status_code == 200
    slug = create_res.json()["slug"]

    # Check status
    status_res = api_client.get(
        f"/api/plugins/zerofactory/boards/{slug}/precommit-status"
    )
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["ok"] is True
    assert status_data["has_precommit"] is False
    assert status_data["pending_task_id"] is None

    # Trigger setup via API
    setup_res = api_client.post(
        f"/api/plugins/zerofactory/boards/{slug}/setup-precommit"
    )
    assert setup_res.status_code == 200
    setup_data = setup_res.json()
    assert setup_data["ok"] is True
    task_id = setup_data["task_id"]
    assert task_id is not None

    # Status check should now report pending setup task
    status_res2 = api_client.get(
        f"/api/plugins/zerofactory/boards/{slug}/precommit-status"
    )
    assert status_res2.status_code == 200
    status_data2 = status_res2.json()
    assert status_data2["pending_task_id"] == task_id


def test_create_board_with_auto_setup(api_client: TestClient):
    """Verify board creation with auto_setup_precommit=True generates setup task."""
    res = api_client.post(
        "/api/plugins/zerofactory/boards",
        json={
            "git_url": "https://github.com/auto-setup-org/repo-auto.git",
            "auto_setup_precommit": True,
        },
    )
    assert res.status_code == 200
    data = res.json()
    assert data["ok"] is True
    assert "setup_task_id" in data
    assert data["setup_task_id"] is not None


def test_board_openwiki_endpoints(api_client: TestClient):
    """Verify GET openwiki-status and POST setup-openwiki integration."""
    # Create board
    create_res = api_client.post(
        "/api/plugins/zerofactory/boards",
        json={"git_url": "https://github.com/example/openwiki-demo.git"},
    )
    assert create_res.status_code == 200
    slug = create_res.json()["slug"]

    # Initial openwiki status check
    status_res = api_client.get(
        f"/api/plugins/zerofactory/boards/{slug}/openwiki-status"
    )
    assert status_res.status_code == 200
    status_data = status_res.json()
    assert status_data["ok"] is True
    assert status_data["has_openwiki"] is False
    assert status_data["pending_task_id"] is None

    # Trigger setup via API
    setup_res = api_client.post(
        f"/api/plugins/zerofactory/boards/{slug}/setup-openwiki"
    )
    assert setup_res.status_code == 200
    setup_data = setup_res.json()
    assert setup_data["ok"] is True
    task_id = setup_data["task_id"]
    assert task_id is not None

    # Status check should now report pending setup task
    status_res2 = api_client.get(
        f"/api/plugins/zerofactory/boards/{slug}/openwiki-status"
    )
    assert status_res2.status_code == 200
    status_data2 = status_res2.json()
    assert status_data2["pending_task_id"] == task_id
