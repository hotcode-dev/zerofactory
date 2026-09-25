"""Unit tests for dashboard/db.py: board code derivation and task ID generation."""

from dashboard.db import derive_board_code, generate_task_id


def test_derive_board_code():
    """Verify board code derivation from slugs."""
    assert derive_board_code("ntsd-sdp-compact") == "nsc"
    assert derive_board_code("hotcode-dev-zerofactory") == "hdz"
    assert derive_board_code("example-zerohub") == "ez"
    assert derive_board_code("zerofactory") == "z"
    assert derive_board_code("my-team-project-service") == "tps"  # last 3 of mtps
    assert derive_board_code("a-b-c-d-e") == "cde"                # last 3 of abcde
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
