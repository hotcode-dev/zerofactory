"""Unit tests for dashboard/db.py: board code derivation and task ID generation."""

from dashboard.db import derive_board_code, generate_task_id


def test_derive_board_code():
    """Verify board code derivation from slugs."""
    assert derive_board_code("ntsd-sdp-compact") == "nsc"
    assert derive_board_code("hotcode-dev-zerofactory") == "hdz"
    assert derive_board_code("example-zerohub") == "ez"
    assert derive_board_code("zerofactory") == "z"
    assert derive_board_code("my-team-project-service") == "tps"  # last 3 of mtps
    assert derive_board_code("a-b-c-d-e") == "cde"  # last 3 of abcde
    assert derive_board_code("") == ""
    assert derive_board_code(None) == ""


def test_generate_task_id():
    """Verify generated task ID contains board code prefix."""
    tid_nsc = generate_task_id("ntsd-sdp-compact")
    assert tid_nsc.startswith("zf-nsc-")
    assert len(tid_nsc.split("-")) == 3

    tid_hdz = generate_task_id("hotcode-dev-zerofactory")
    assert tid_hdz.startswith("zf-hdz-")

    tid_none = generate_task_id(None)
    assert tid_none.startswith("zf-")


def test_row_to_dict_populates_stage_and_ui_column():
    """Verify row_to_dict computes stage and ui_column for task rows."""
    import sqlite3
    from dashboard.db import row_to_dict

    conn = sqlite3.connect(":memory:")
    conn.row_factory = sqlite3.Row
    cur = conn.cursor()
    cur.execute(
        "SELECT 't1' AS id, 'triage' AS status, 'human' AS assignee, NULL AS pr_url, '{}' AS metadata"
    )
    d1 = row_to_dict(cur.fetchone())
    assert d1["stage"] == "triage"
    assert d1["ui_column"] == "human"

    cur.execute(
        "SELECT 't2' AS id, 'todo' AS status, 'zf-orchestrator' AS assignee, NULL AS pr_url, '{\"triage_phase\": \"recovery\"}' AS metadata"
    )
    d2 = row_to_dict(cur.fetchone())
    assert d2["stage"] == "recovery"
    assert d2["ui_column"] == "todo"
    conn.close()
