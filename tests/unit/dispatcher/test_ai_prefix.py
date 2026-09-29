"""Unit tests for the `[AI]` attribution prefix applied to agent-authored GitHub PRs/comments."""

import subprocess
from unittest.mock import patch

from dispatcher import ai_prefix


class TestAiPrefix:
    def test_plain_text_is_prefixed(self):
        assert ai_prefix("feat(auth): add JWT token generator") == (
            "[AI] feat(auth): add JWT token generator"
        )

    def test_idempotent_on_existing_prefix(self):
        assert ai_prefix("[AI] Fix bug") == "[AI] Fix bug"

    def test_empty_and_blank_input_unchanged(self):
        assert ai_prefix("") == ""
        assert ai_prefix("   ") == "   "

    def test_multiline_pr_body_prefixed_once(self):
        body = "chore: fix tests\n\nAutomated PR for task zf-abc\n\nCompleted by: @zf-builder"
        prefixed = ai_prefix(body)
        assert prefixed == "[AI] " + body
        assert prefixed.count("[AI]") == 1

    def test_leading_whitespace_stripped_before_prefix(self):
        assert ai_prefix("\n  indented body") == "[AI] indented body"


class TestDispatcherPrCreationUsesAiPrefix:
    """The dispatcher's `gh pr create` call must prefix title and body with `[AI]`."""

    def test_pr_create_command_captures_ai_prefixed_title_and_body(self):
        """Exercise the scheduler PR-open code path via the fake-gh e2e pattern."""
        from tests.e2e.test_multi_agent_workflow import TestMultiAgentLifecycleE2E

        case = TestMultiAgentLifecycleE2E(
            "test_01_full_delivery_cycle_builder_review_rounds_approval_and_merge"
        )
        # Reuse setUp to create db + board + repo, then drive the same
        # builder-finished -> dispatch -> PR-opened sequence as test_01.
        case.setUp()
        try:
            from dashboard.plugin_api import (
                create_task,
                get_task,
                init_db,
                move_task,
                TaskCreate,
                TaskMove,
            )

            t_res = create_task(
                TaskCreate(
                    board_slug=case.board_slug,
                    title="Implement Feature X",
                    description="desc",
                    status="todo",
                    assignee="zf-builder",
                    priority="P1",
                )
            )
            task_id = t_res["id"]

            import dispatcher as dispatcher_mod

            dispatcher_mod.run_dispatch_cycle(case.db_path)
            t_info = get_task(task_id)["task"]
            worktree_path = t_info["workspace_path"]

            from pathlib import Path

            (Path(worktree_path) / "feature.py").write_text("def f(): pass\n")
            case._git(Path(worktree_path), "add", ".")
            case._git(Path(worktree_path), "commit", "-m", "feat: implement feature")

            move_task(task_id, TaskMove(status="done", actor="zf-builder"))

            pr_url = "https://github.com/example/repo/pull/900"
            captured = []
            orig_run = subprocess.run

            def mock_gh_run(cmd, *args, **kwargs):
                if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "gh":
                    captured.append(list(cmd))
                    if "create" in cmd:
                        return subprocess.CompletedProcess(
                            args=cmd, returncode=0, stdout=pr_url, stderr=""
                        )
                    if "view" in cmd:
                        # Fail the branch lookup so the scheduler falls through
                        # to the `gh pr create` code path (fresh PR, no URL yet).
                        return subprocess.CompletedProcess(
                            args=cmd, returncode=1, stdout="", stderr="not found"
                        )
                    return subprocess.CompletedProcess(
                        args=cmd, returncode=0, stdout="", stderr=""
                    )
                if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "git":
                    if cmd[1] == "push":
                        return subprocess.CompletedProcess(
                            args=cmd, returncode=0, stdout="", stderr=""
                        )
                    return orig_run(cmd, *args, **kwargs)
                return orig_run(cmd, *args, **kwargs)

            with patch("subprocess.run", side_effect=mock_gh_run):
                res = dispatcher_mod.run_dispatch_cycle(case.db_path)
            assert res["ok"]

            create_cmds = [c for c in captured if "create" in c]
            assert create_cmds, "gh pr create was never invoked"
            cmd = create_cmds[0]
            title = cmd[cmd.index("--title") + 1]
            body = cmd[cmd.index("--body") + 1]
            assert title.startswith("[AI]"), f"PR title missing [AI] prefix: {title!r}"
            assert body.startswith("[AI] "), f"PR body missing [AI] prefix: {body!r}"
            assert title.count("[AI]") == 1
            assert body.count("[AI]") == 1

            t_info2 = get_task(task_id)["task"]
            assert t_info2["assignee"] == "zf-reviewer"
        finally:
            case.tearDown()
