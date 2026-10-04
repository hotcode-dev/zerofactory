"""Integration tests for Task API endpoints (/api/plugins/zerofactory/tasks)."""

from fastapi.testclient import TestClient


def test_task_lifecycle_crud(api_client: TestClient, default_board: str):
    """Verify task creation, details fetch, updating, moving, and listing."""
    # 1. Create task
    create_res = api_client.post(
        "/api/plugins/zerofactory/tasks",
        json={
            "title": "Build Integration Test Suite",
            "description": "Create modular pytest suites",
            "board_slug": default_board,
            "status": "triage",
            "priority": "P1",
            "assignee": "zf-builder",
        },
    )
    assert create_res.status_code == 200
    task_id = create_res.json()["id"]
    assert task_id.startswith("zf-")

    # 2. Get task
    get_res = api_client.get(f"/api/plugins/zerofactory/tasks/{task_id}")
    assert get_res.status_code == 200
    task = get_res.json()["task"]
    assert task["title"] == "Build Integration Test Suite"
    assert task["status"] == "triage"
    assert task["priority"] == "P1"

    # 3. Move task
    move_res = api_client.post(
        f"/api/plugins/zerofactory/tasks/{task_id}/move",
        json={"status": "todo", "actor": "user"},
    )
    assert move_res.status_code == 200
    assert move_res.json()["status"] == "todo"

    # 4. Update task
    update_res = api_client.patch(
        f"/api/plugins/zerofactory/tasks/{task_id}",
        json={"title": "Build Integration Test Suite (Updated)", "priority": "P0"},
    )
    assert update_res.status_code == 200
    assert update_res.json()["ok"] is True

    # 5. Add comment
    comment_res = api_client.post(
        f"/api/plugins/zerofactory/tasks/{task_id}/comments",
        json={"author": "zf-reviewer", "body": "Looking good so far!"},
    )
    assert comment_res.status_code == 200

    # 6. Verify comments & activities in details
    task_updated = api_client.get(f"/api/plugins/zerofactory/tasks/{task_id}").json()[
        "task"
    ]
    assert task_updated["title"] == "Build Integration Test Suite (Updated)"
    assert task_updated["priority"] == "P0"
    assert len(task_updated["comments"]) == 1
    assert task_updated["comments"][0]["body"] == "Looking good so far!"
    assert len(task_updated["activity"]) >= 2

    # 7. List tasks with filter
    list_res = api_client.get("/api/plugins/zerofactory/tasks?status=todo&priority=P0")
    assert list_res.status_code == 200
    filtered_tasks = list_res.json()["tasks"]
    assert any(t["id"] == task_id for t in filtered_tasks)


def test_task_dependencies(api_client: TestClient, default_board: str):
    """Verify linking and unlinking task dependencies."""
    t1_id = api_client.post(
        "/api/plugins/zerofactory/tasks",
        json={"title": "Parent Task", "board_slug": default_board},
    ).json()["id"]
    t2_id = api_client.post(
        "/api/plugins/zerofactory/tasks",
        json={"title": "Child Task", "board_slug": default_board},
    ).json()["id"]

    # Link t1 as parent of t2
    link_res = api_client.post(
        f"/api/plugins/zerofactory/tasks/{t2_id}/dependencies",
        json={"parent_id": t1_id, "link_type": "blocks"},
    )
    assert link_res.status_code == 200
    assert link_res.json()["ok"] is True

    # Check child task shows parent dependency
    child_details = api_client.get(f"/api/plugins/zerofactory/tasks/{t2_id}").json()[
        "task"
    ]
    assert any(parent["id"] == t1_id for parent in child_details.get("parents", []))

    # Delete link
    del_res = api_client.delete(
        f"/api/plugins/zerofactory/tasks/{t2_id}/dependencies/{t1_id}"
    )
    assert del_res.status_code == 200
    assert del_res.json()["ok"] is True

    # Check child task no longer has parent
    child_after = api_client.get(f"/api/plugins/zerofactory/tasks/{t2_id}").json()[
        "task"
    ]
    assert not any(parent["id"] == t1_id for parent in child_after.get("parents", []))


def test_task_grill_with_docs_triage_and_interview_reply(
    api_client: TestClient, default_board: str
):
    """Verify Grill-with-Docs triage dispatch and human interview reply workflow."""
    # 1. Create a task in blocked awaiting input
    create_res = api_client.post(
        "/api/plugins/zerofactory/tasks",
        json={
            "title": "Add Database Sharding",
            "description": "Partition tenant database across nodes",
            "board_slug": default_board,
            "status": "blocked",
            "assignee": "zf-builder",
        },
    )
    assert create_res.status_code == 200
    task_id = create_res.json()["id"]

    # 2. Trigger Grill-with-Docs triage dispatch
    triage_res = api_client.post(f"/api/plugins/zerofactory/tasks/{task_id}/triage")
    assert triage_res.status_code == 200
    assert triage_res.json()["status"] == "triage"
    assert triage_res.json()["assignee"] == "zf-orchestrator"

    # Verify task state in database
    task_details = api_client.get(f"/api/plugins/zerofactory/tasks/{task_id}").json()[
        "task"
    ]
    assert task_details["status"] == "triage"
    assert task_details["assignee"] == "zf-orchestrator"

    # 3. Simulate zf-orchestrator posting a Grill-with-Docs question
    question_body = (
        "### 🎯 Grill-with-Docs: Decision Required\n"
        "**Question:** Which partitioning key should be used for sharding?\n"
        "- [ ] **Option A:** Tenant ID hash (even distribution)\n"
        "- [ ] **Option B:** Geographic Region (latency optimized)\n"
        "**Documentation Context:** openwiki/architecture.md recommends tenant isolation."
    )
    api_client.post(
        f"/api/plugins/zerofactory/tasks/{task_id}/comments",
        json={"author": "zf-orchestrator", "body": question_body},
    )

    # 4. Human replies via interactive interview endpoint
    reply_res = api_client.post(
        f"/api/plugins/zerofactory/tasks/{task_id}/interview-reply",
        json={
            "selection": "Option A: Tenant ID hash (even distribution)",
            "notes": "Ensure consistent hashing is used with 128 virtual nodes.",
            "advance": False,
        },
    )
    assert reply_res.status_code == 200
    assert reply_res.json()["ok"] is True
    assert reply_res.json()["status"] == "triage"

    # 5. Verify the comment and metadata were recorded
    task_after = api_client.get(f"/api/plugins/zerofactory/tasks/{task_id}").json()[
        "task"
    ]
    comments = task_after.get("comments", [])
    assert any("[Grill-with-Docs Human Response]" in c["body"] for c in comments)
    assert any("Option A" in c["body"] for c in comments)
    assert any("consistent hashing" in c["body"] for c in comments)
