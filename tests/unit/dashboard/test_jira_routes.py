"""Unit tests for Jira setup and test endpoints in dashboard/routes/boards.py."""

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from dashboard.models import BoardCreate, JiraSetupRequest
from dashboard.plugin_api import create_board
from dashboard.routes.boards import (
    setup_board_jira_endpoint,
    verify_board_jira_endpoint,
)


def test_setup_and_test_jira_endpoint(initialized_db: Path, tmp_path: Path):
    repo_dir = tmp_path / "dummy_jira_repo"
    repo_dir.mkdir(parents=True)
    (repo_dir / ".git").mkdir()

    board_res = create_board(BoardCreate(git_url=str(repo_dir)))
    slug = board_res["slug"]

    # 1. Non-existent board raises 404
    with pytest.raises(HTTPException) as exc_info:
        setup_board_jira_endpoint(
            "nonexistent-slug", JiraSetupRequest(jira_url="https://test.atlassian.net")
        )
    assert exc_info.value.status_code == 404

    # 2. Setup Jira URL for board (with mocked reachable connection)
    with patch("urllib.request.urlopen") as mock_urlopen:
        mock_resp = MagicMock()
        mock_resp.status = 200
        mock_resp.__enter__.return_value = mock_resp
        mock_urlopen.return_value = mock_resp

        res = setup_board_jira_endpoint(
            slug,
            JiraSetupRequest(jira_url="https://myteam.atlassian.net"),
        )
        assert res["ok"] is True
        assert res["slug"] == slug
        assert res["jira_url"] == "https://myteam.atlassian.net"
        assert res["connection"]["ok"] is True
        assert res["connection"]["connected"] is True

        # 3. Test Jira endpoint directly
        test_res = verify_board_jira_endpoint(slug)
        assert test_res["ok"] is True
        assert test_res["jira_url"] == "https://myteam.atlassian.net"
        assert test_res["connection"]["connected"] is True
