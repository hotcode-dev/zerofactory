"""Integration tests for Board API endpoints (/api/plugins/zerofactory/boards)."""

import subprocess

import cron.definitions as defs
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


def test_board_status_endpoints_do_not_clone(api_client: TestClient, monkeypatch):
    """Read-only status endpoints must not spawn a git clone subprocess.

    The board is created first (board creation is the sanctioned clone point),
    then ZEROFACTORY_SKIP_GIT / ZEROFACTORY_AUTO_CLONE are cleared and a fake
    subprocess.run records every spawn: the status endpoints must not clone.
    """
    calls: list[list[str]] = []

    def fake_run(cmd, *args, **kwargs):
        calls.append(list(cmd))
        return subprocess.CompletedProcess(
            args=cmd, returncode=1, stdout=b"", stderr=b""
        )

    create_res = api_client.post(
        "/api/plugins/zerofactory/boards",
        json={
            "git_url": "https://github.com/no-clone-org/no-clone-endpoints.git",
            "auto_setup_precommit": False,
        },
    )
    assert create_res.status_code == 200
    slug = create_res.json()["slug"]

    # With auto-clone enabled, the read-only status endpoints must stay read-only.
    monkeypatch.delenv("ZEROFACTORY_SKIP_GIT", raising=False)
    monkeypatch.delenv("ZEROFACTORY_AUTO_CLONE", raising=False)
    monkeypatch.setattr(defs.subprocess, "run", fake_run)

    precommit_res = api_client.get(
        f"/api/plugins/zerofactory/boards/{slug}/precommit-status"
    )
    assert precommit_res.status_code == 200
    precommit_data = precommit_res.json()
    assert precommit_data["ok"] is True
    assert precommit_data["has_precommit"] is False

    openwiki_res = api_client.get(
        f"/api/plugins/zerofactory/boards/{slug}/openwiki-status"
    )
    assert openwiki_res.status_code == 200
    openwiki_data = openwiki_res.json()
    assert openwiki_data["ok"] is True
    assert openwiki_data["has_openwiki"] is False

    clones = [c for c in calls if len(c) >= 2 and c[1] == "clone"]
    assert not clones, f"status endpoints triggered git clone: {clones}"


def test_board_multi_repositories_and_architecture(api_client: TestClient):
    """Verify multi-repo management and architecture notes endpoints on boards."""
    # 1. Create a board with initial repositories and architecture
    arch_initial = """---
dependencies:
  api-gateway: [common-lib, order-service]
---
### Notes
Shared protobufs in common-lib.
"""
    res = api_client.post(
        "/api/plugins/zerofactory/boards",
        json={
            "git_url": "https://github.com/my-org/api-gateway.git",
            "description": "API Gateway service",
            "architecture": arch_initial,
            "repositories": [
                {
                    "repo_alias": "common-lib",
                    "git_url": "https://github.com/my-org/common-lib.git",
                    "target_branch": "main",
                },
                {
                    "repo_alias": "order-service",
                    "git_url": "https://github.com/my-org/order-service.git",
                    "target_branch": "main",
                },
            ],
        },
    )
    assert res.status_code == 200
    slug = res.json()["slug"]
    assert slug == "my-org-api-gateway"

    # 2. GET board and verify repositories and architecture
    board_res = api_client.get(f"/api/plugins/zerofactory/boards/{slug}")
    assert board_res.status_code == 200
    b = board_res.json()["board"]
    assert b["architecture"] == arch_initial.strip()
    aliases = {r["repo_alias"] for r in b["repositories"]}
    assert "api-gateway" in aliases
    assert "common-lib" in aliases
    assert "order-service" in aliases

    # 3. Add 4th repository via POST /repositories
    add_repo_res = api_client.post(
        f"/api/plugins/zerofactory/boards/{slug}/repositories",
        json={
            "repo_alias": "event-worker",
            "git_url": "https://github.com/my-org/event-worker.git",
            "target_branch": "main",
            "additional_reviewer_usernames": ["worker-lead"],
        },
    )
    assert add_repo_res.status_code == 200
    assert add_repo_res.json()["repository"]["repo_alias"] == "event-worker"

    # 4. List repositories
    list_repos_res = api_client.get(f"/api/plugins/zerofactory/boards/{slug}/repositories")
    assert list_repos_res.status_code == 200
    repo_aliases = [r["repo_alias"] for r in list_repos_res.json()["repositories"]]
    assert "event-worker" in repo_aliases
    assert len(repo_aliases) == 4

    # 5. Update repository
    put_repo_res = api_client.put(
        f"/api/plugins/zerofactory/boards/{slug}/repositories/event-worker",
        json={"target_branch": "develop", "additional_reviewer_usernames": ["worker-lead", "qa-eng"]},
    )
    assert put_repo_res.status_code == 200
    assert put_repo_res.json()["repository"]["target_branch"] == "develop"
    assert "qa-eng" in put_repo_res.json()["repository"]["additional_reviewer_usernames"]

    # 6. Update architecture via PUT /architecture
    new_arch = "### Updated Architecture\nAll services ready."
    arch_res = api_client.put(
        f"/api/plugins/zerofactory/boards/{slug}/architecture",
        json={"architecture": new_arch},
    )
    assert arch_res.status_code == 200
    assert arch_res.json()["architecture"] == new_arch

    get_arch_res = api_client.get(f"/api/plugins/zerofactory/boards/{slug}/architecture")
    assert get_arch_res.status_code == 200
    assert get_arch_res.json()["architecture"] == new_arch

    # 7. Delete repository
    del_repo_res = api_client.delete(f"/api/plugins/zerofactory/boards/{slug}/repositories/event-worker")
    assert del_repo_res.status_code == 200

    list_after_del = api_client.get(f"/api/plugins/zerofactory/boards/{slug}/repositories")
    aliases_after = [r["repo_alias"] for r in list_after_del.json()["repositories"]]
    assert "event-worker" not in aliases_after
    assert len(aliases_after) == 3
