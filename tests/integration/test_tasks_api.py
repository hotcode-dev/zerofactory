"""Integration tests for Task API endpoints (/api/plugins/zerofactory/tasks)."""

import json

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
    """Verify linking and unlinking task dependencies with repo_alias and link_type."""
    t1_id = api_client.post(
        "/api/plugins/zerofactory/tasks",
        json={"title": "Parent Task", "board_slug": default_board, "repo_alias": "common-lib"},
    ).json()["id"]
    t2_id = api_client.post(
        "/api/plugins/zerofactory/tasks",
        json={"title": "Child Task", "board_slug": default_board, "repo_alias": "order-service"},
    ).json()["id"]

    # Verify repo_alias was set
    t1_data = api_client.get(f"/api/plugins/zerofactory/tasks/{t1_id}").json()["task"]
    assert t1_data["repo_alias"] == "common-lib"

    # Link t1 as blocking parent of t2
    link_res = api_client.post(
        f"/api/plugins/zerofactory/tasks/{t2_id}/dependencies",
        json={"parent_id": t1_id, "link_type": "blocks"},
    )
    assert link_res.status_code == 200
    assert link_res.json()["ok"] is True
    assert link_res.json()["link_type"] == "blocks"

    # Check child task shows parent dependency with link_type and repo_alias
    child_details = api_client.get(f"/api/plugins/zerofactory/tasks/{t2_id}").json()[
        "task"
    ]
    matching_parent = next((p for p in child_details.get("parents", []) if p["id"] == t1_id), None)
    assert matching_parent is not None
    assert matching_parent["link_type"] == "blocks"
    assert matching_parent["repo_alias"] == "common-lib"

    # Test peer link relates_to
    t3_id = api_client.post(
        "/api/plugins/zerofactory/tasks",
        json={"title": "Peer Task", "board_slug": default_board, "repo_alias": "api-gateway"},
    ).json()["id"]
    peer_link_res = api_client.post(
        f"/api/plugins/zerofactory/tasks/{t3_id}/dependencies",
        json={"parent_id": t2_id, "link_type": "relates_to"},
    )
    assert peer_link_res.status_code == 200
    assert peer_link_res.json()["link_type"] == "relates_to"

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


def test_move_done_semantics_human_terminal_vs_agent_awaiting_pr(
    api_client: TestClient, default_board: str
):
    """A human move to 'done' is terminal (task is never re-dispatched), while an
    agent (zf-builder) move to 'done' flags the task for dispatcher PR packaging."""

    def _metadata(task_id: str) -> dict:
        task = api_client.get(f"/api/plugins/zerofactory/tasks/{task_id}").json()[
            "task"
        ]
        meta = task.get("metadata") or {}
        if isinstance(meta, str):
            meta = json.loads(meta or "{}")
        return meta

    task_id = api_client.post(
        "/api/plugins/zerofactory/tasks",
        json={
            "title": "Done Semantics Task",
            "board_slug": default_board,
            "status": "todo",
            "assignee": "zf-builder",
        },
    ).json()["id"]

    # Human closes the task -> terminal: no awaiting_pr flag set
    res = api_client.post(
        f"/api/plugins/zerofactory/tasks/{task_id}/move",
        json={"status": "done", "actor": "user"},
    )
    assert res.status_code == 200
    assert _metadata(task_id).get("awaiting_pr") is None

    # Revive, then let the builder report completion -> PR packaging may proceed
    api_client.post(
        f"/api/plugins/zerofactory/tasks/{task_id}/move",
        json={"status": "todo", "actor": "user"},
    )
    assert _metadata(task_id).get("awaiting_pr") is None

    api_client.post(
        f"/api/plugins/zerofactory/tasks/{task_id}/move",
        json={"status": "done", "actor": "zf-builder"},
    )
    assert _metadata(task_id).get("awaiting_pr") is True

    # Reviving clears the flag again so the task dispatches normally
    api_client.post(
        f"/api/plugins/zerofactory/tasks/{task_id}/move",
        json={"status": "todo", "actor": "zf-builder"},
    )
    assert _metadata(task_id).get("awaiting_pr") is None

    # A human close with an open PR additionally marks it for archival
    # (dispatcher closes the PR and deletes the remote branch)
    api_client.patch(
        f"/api/plugins/zerofactory/tasks/{task_id}",
        json={"pr_url": "https://github.com/example/repo/pull/42"},
    )
    api_client.post(
        f"/api/plugins/zerofactory/tasks/{task_id}/move",
        json={"status": "done", "actor": "user"},
    )
    meta = _metadata(task_id)
    assert meta.get("close_pr") is True
    assert meta.get("awaiting_pr") is None

    # Reviving the task drops the archival marker as well
    api_client.post(
        f"/api/plugins/zerofactory/tasks/{task_id}/move",
        json={"status": "todo", "actor": "user"},
    )
    assert _metadata(task_id).get("close_pr") is None


def test_blocked_assigns_human_except_changes_requested(
    api_client: TestClient, default_board: str
):
    """'blocked' parks the task on the human queue (assignee=human); the sole
    exception is 'changes-requested', which is builder-bound feedback."""

    def _assignee(task_id: str) -> str:
        return api_client.get(f"/api/plugins/zerofactory/tasks/{task_id}").json()[
            "task"
        ]["assignee"]

    def _new_task(title: str) -> str:
        return api_client.post(
            "/api/plugins/zerofactory/tasks",
            json={
                "title": title,
                "board_slug": default_board,
                "status": "todo",
                "assignee": "zf-builder",
            },
        ).json()["id"]

    # 1. Reviewer verdict prose (classifies as human-gate) -> human queue
    t1 = _new_task("Approved Merge Gate")
    res = api_client.post(
        f"/api/plugins/zerofactory/tasks/{t1}/move",
        json={
            "status": "blocked",
            "actor": "zf-reviewer",
            "reason": "Human Review & Merge",
        },
    )
    assert res.status_code == 200
    assert _assignee(t1) == "human"

    # 2. Canonical 'approved' code -> human queue
    t2 = _new_task("Approved Canonical Code")
    api_client.post(
        f"/api/plugins/zerofactory/tasks/{t2}/move",
        json={"status": "blocked", "actor": "zf-reviewer", "reason": "approved"},
    )
    assert _assignee(t2) == "human"

    # 3. 'changes-requested' is builder-bound feedback -> assignee unchanged
    t3 = _new_task("Changes Requested Feedback")
    api_client.post(
        f"/api/plugins/zerofactory/tasks/{t3}/move",
        json={
            "status": "blocked",
            "actor": "zf-reviewer",
            "reason": "changes-requested",
        },
    )
    assert _assignee(t3) == "zf-builder"


def test_unknown_status_rejected(api_client: TestClient, default_board: str):
    """Unknown status values are rejected by the move endpoint."""
    task_id = api_client.post(
        "/api/plugins/zerofactory/tasks",
        json={
            "title": "Status validation",
            "board_slug": default_board,
            "status": "todo",
        },
    ).json()["id"]

    res = api_client.post(
        f"/api/plugins/zerofactory/tasks/{task_id}/move",
        json={"status": "bogus-status", "actor": "user"},
    )
    # Rejected by model validation (422) or status validation (400)
    assert res.status_code in (400, 422)


def test_patch_cannot_change_status(api_client: TestClient, default_board: str):
    """Status is a lifecycle transition owned by /move — PATCH must reject it."""
    task_id = api_client.post(
        "/api/plugins/zerofactory/tasks",
        json={
            "title": "Patch status guard",
            "board_slug": default_board,
            "status": "todo",
        },
    ).json()["id"]

    res = api_client.patch(
        f"/api/plugins/zerofactory/tasks/{task_id}",
        json={"status": "running"},
    )
    assert res.status_code == 400
    assert (
        api_client.get(f"/api/plugins/zerofactory/tasks/{task_id}").json()["task"][
            "status"
        ]
        == "todo"
    )


def test_stale_agent_completion_cannot_clobber_parked_state(
    api_client: TestClient, default_board: str
):
    """Regression (zf-hdz-4dc03cee): a zombie builder's `move done` flipped an
    approved-for-merge task back to running and wiped its blocked_reason.

    'done' is strictly terminal and 'blocked' is a human/reviewer gate — stale
    worker completions must be ignored for both, except the builder-bound
    'changes-requested' park where finishing the fix is the desired outcome.
    """
    task_id = api_client.post(
        "/api/plugins/zerofactory/tasks",
        json={
            "title": "Stale completion guard",
            "board_slug": default_board,
            "status": "todo",
            "assignee": "zf-builder",
        },
    ).json()["id"]

    # Parked states: approved / human-gate / stuck must all reject the zombie.
    for parked_reason in ("approved", "human-gate", "stuck"):
        park_res = api_client.post(
            f"/api/plugins/zerofactory/tasks/{task_id}/move",
            json={"status": "blocked", "actor": "zf-reviewer", "reason": parked_reason},
        )
        assert park_res.status_code == 200

        stale_res = api_client.post(
            f"/api/plugins/zerofactory/tasks/{task_id}/move",
            json={"status": "done", "actor": "zf-builder"},
        )
        assert stale_res.status_code == 200
        assert stale_res.json()["ignored"] is True
        assert stale_res.json()["status"] == "blocked"

        # State unchanged: still blocked, and the block reason survives.
        check = api_client.get(f"/api/plugins/zerofactory/tasks/{task_id}").json()[
            "task"
        ]
        assert check["status"] == "blocked"
        assert check["metadata"]["blocked_reason_type"] == parked_reason

    # Builder-bound exception: 'changes-requested' accepts the fix's completion.
    api_client.post(
        f"/api/plugins/zerofactory/tasks/{task_id}/move",
        json={
            "status": "blocked",
            "actor": "zf-reviewer",
            "reason": "changes-requested",
        },
    )
    fix_res = api_client.post(
        f"/api/plugins/zerofactory/tasks/{task_id}/move",
        json={"status": "done", "actor": "zf-builder"},
    )
    assert fix_res.status_code == 200
    assert "ignored" not in fix_res.json()
    assert fix_res.json()["status"] == "running"

    # Terminal 'done' is also protected: a late completion cannot resurrect it.
    api_client.post(
        f"/api/plugins/zerofactory/tasks/{task_id}/move",
        json={"status": "done", "actor": "user"},
    )
    late_res = api_client.post(
        f"/api/plugins/zerofactory/tasks/{task_id}/move",
        json={"status": "done", "actor": "zf-builder"},
    )
    assert late_res.status_code == 200
    assert late_res.json()["ignored"] is True
    assert (
        api_client.get(f"/api/plugins/zerofactory/tasks/{task_id}").json()["task"][
            "status"
        ]
        == "done"
    )
