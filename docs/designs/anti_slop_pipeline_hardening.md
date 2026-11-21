# Zero Factory Anti-Slop Pipeline Hardening

*   **Author:** ntsd
*   **Status:** Approved
*   **Date:** 2026-11-22

--------------------------------------------------------------------------------

## Overview

Zero Factory runs an automated multi-agent software pipeline where `zf-builder` writes code inside an isolated Git worktree, the dispatcher runs precommit and anti-slop checks before opening a GitHub Pull Request, and `zf-reviewer` performs up to two rounds of code review before handing the PR to a human operator (or merging it when Auto-Merge is enabled).

This design closes concrete gaps in packaging and PR review where low-quality or out-of-scope AI output ("AI slop") currently escapes detection:
1. It expands the zero-token deterministic gate (`dispatcher/slop_gate.py`) to block modifications to files listed under a task specification's `Do Not Touch` section, enforce a default 800-line net diff ceiling, reject newly added test functions that contain no assertions, block large production code additions (`> 20` net lines) that add zero test lines, and warn on mock-heavy test diffs in the Diff Hygiene Scorecard.
2. It fixes two state-machine defects in the 2-round review loop (`dispatcher/scheduler.py` and `templates/zf-reviewer/SOUL.md`) that previously caused review counters to reset on every builder rework commit and instructed `zf-reviewer` to mark unresolved Round 2 PRs as `"approved"`.
3. It formalizes the 400-line / 24,000-character inline diff preview defaults in `dispatcher/context_builder.py` so normal pull requests are presented in full to `zf-reviewer` without truncation.

## The Problem

Today, three failure modes allow low-quality code to pass packaging or review:

1. **Incomplete Deterministic Packaging Gate (`dispatcher/slop_gate.py`)**:
   * `run_deterministic_slop_gate()` currently blocks only leftover debuggers (`breakpoint()`, `pdb.set_trace()`, `debugger;`), `TODO`/`FIXME`/`XXX`/`HACK` comments, and skipped tests (`@pytest.mark.skip`, `it.skip`).
   * The net diff line cap (`ZEROFACTORY_MAX_DIFF_LINES`) is disabled unless an operator manually exports the environment variable.
   * `_package_and_open_pr()` in `dispatcher/scheduler.py` calls `run_deterministic_slop_gate(Path(workspace_path))` without passing the task specification (`meta.get("specification") or row["description"]`) or `target_branch`. Consequently, `slop_gate.py` cannot check whether `zf-builder` modified files explicitly forbidden by the specification's `Do Not Touch / Non-Goals` section.
   * A builder can add hundreds of lines of production code with zero test lines (`test_lines_added == 0`), or add superficial `def test_*` functions containing zero assertions, and pass both `.zerofactory/precommit.sh` and `run_deterministic_slop_gate()`.

2. **Broken 2-Round Review Cap and Fake Approval Escalation (`dispatcher/scheduler.py` & `templates/zf-reviewer/SOUL.md`)**:
   * In `dispatcher/scheduler.py` (lines 1430–1446), `commit_review_count` resets to `0` whenever `last_reviewed_commit != head_commit_sha`. Because `zf-builder` creates a new commit each time it addresses review feedback, `commit_review_count` resets to `1` on every rework cycle. Even on the same commit, the check `if commit_review_count > max_review_rounds:` (`2`) allows a third review cycle before triggering.
   * Line 28 of `templates/zf-reviewer/SOUL.md` instructs `zf-reviewer`: *"If still unresolved: Submit your final findings. The dispatcher enforces the hard 2-round cap per commit and escalates directly to human review (`hermes zerofactory block <task_id> --reason "approved"`)."* Passing `--reason "approved"` marks an unresolved, defective PR as approved (`awaiting_merge`) and, on boards with Auto-Merge enabled, merges unapproved code directly into the target branch.
   * In addition, `dispatcher/worker_spawner.py` does not inform `zf-reviewer` whether it is running Round 1 or Round 2 of review.

3. **Over-Aggressive Inline Diff Truncation (`dispatcher/context_builder.py`)**:
   * `digest_reviewer_git_context()` previously truncated inline diffs at `100` lines / `4,000` characters, forcing `zf-reviewer` to make extra shell tool calls to see the tail of routine pull requests.

## Goals

*   **Enforce Default Diff Budget**: Set a default net diff limit of `800` added lines (`DEFAULT_MAX_DIFF_LINES = 800`) in `dispatcher/slop_gate.py` when `ZEROFACTORY_MAX_DIFF_LINES` is unset, while allowing `ZEROFACTORY_MAX_DIFF_LINES=0` (or negative values) to disable the hard cap.
*   **Block Spec `Do Not Touch` Violations**: Parse file and directory patterns from the task specification's `Do Not Touch / Non-Goals` section and fail packaging (`do_not_touch_violation`) if any changed or untracked file in the worktree (including paths otherwise excluded from line-count metrics) matches a forbidden path or glob.
*   **Block Assertion-Free New Tests**: Detect newly added test functions in Python (`def test_*`, `async def test_*`) and JS/TS (`it(`, `test(`) whose added non-comment body lines contain zero assertion statements, and fail packaging (`assertion_free_test`).
*   **Block Untested Production Code Additions**: Track net added lines specifically on production code files (`_is_code_file(f) and not is_test_file(f)`). Fail packaging (`untested_production_diff`) when net production code lines exceed `+20` and `test_lines_added == 0`, unless exempted via task metadata (`skip_untested_check`), `ZEROFACTORY_SKIP_UNTESTED_CHECK`, or `ZEROFACTORY_SKIP_SLOP_GATE`.
*   **Flag Mock-Heavy Tests in Scorecard**: Emit a `mock_heavy_test` warning in `build_diff_hygiene_scorecard()` when added test lines in a test file contain `>= 4` mock/patch declarations and more mocks than assertions.
*   **Enforce True 2-Round Review Cap Across Commits**: Increment canonical `review_round` cumulatively across rework commits on a task without resetting on new `head_commit_sha`. Route Round 1 `changes-requested` back to `zf-builder`, and escalate Round 2 `changes-requested` (`review_round >= max_review_rounds`) to `Human (blocked)` (`assignee = 'human'`, `status = 'blocked'`, `blocked_reason_type = 'human-gate'`, `review_cap_reached = True`).
*   **Prevent Poll Loop Re-Triggers and Reset on Recovery**: Short-circuit `_poll_pr_and_route_review()` when `review_cap_reached` is already `True` and no new PR comments exist, and reset `review_round` and `review_cap_reached` when an operator runs `hermes zerofactory recover <task_id>`.
*   **Eliminate Fake Round 2 Approvals & Surface Review Round**: Update `templates/zf-reviewer/SOUL.md` and `dispatcher/worker_spawner.py` so `zf-reviewer` sees the active review round (`Round X of Y`) and always runs `--reason "changes-requested"` when defects remain.
*   **Synchronize Documentation Surfaces**: Update `docs/FLOWS.md`, `docs/DEBUGGING.md`, `README.md` (`AGENTS.md`), and `dashboard/src/views/InstructionsView.jsx` (plus rebuilt `dashboard/dist/` assets) to reflect the updated anti-slop gate rules and per-PR 2-round review cap.

## Non-Goals

*   **External Static Analysis Dependencies**: Adding third-party linters, AST complexity libraries, or external services to the dispatcher runtime (all deterministic checks use Python's standard library).
*   **Multi-Turn Reviewer Session Persistence**: Changing Zero Factory's Session-per-Handoff execution model (`zf-reviewer` remains stateless across review rounds).
*   **Removing the Inline Diff Ceiling Completely**: Passing unbounded diffs into the reviewer CLI prompt (inline previews remain capped at `max_diff_lines = 400` and `max_diff_chars = 24000` to respect Linux `MAX_ARG_STRLEN` and token budgets).

## Open Questions

None. All scope boundaries and exception-handling rules were resolved during Elephant-Goldfish Model (EGM) brainstorming (`/egm-brainstorm`).

## Critical User Journeys (CUJs)

### CUJ 1: Packaging Gate Blocks Out-of-Scope File Edit and Missing Tests

*   **Given**: A task in `Running (building)` whose approved specification includes a `## Do Not Touch / Non-Goals` section listing `` `dispatcher/state_machine.py` `` and `` `dashboard/dist/*` ``.
*   **When**: `zf-builder` modifies `dispatcher/state_machine.py` (or `dashboard/dist/index.js`) and adds `35` net lines of Python code in `dispatcher/scheduler.py` without modifying any test file, then marks the task done to enter `packaging`.
*   **Then**: `_package_and_open_pr()` resolves `target_branch` and runs `run_deterministic_slop_gate()` with the task specification, fails packaging with `[do_not_touch_violation]` and `[untested_production_diff]`, records the exact violation summary in `last_precommit_error`, increments `precommit_retries`, and routes the task back to `zf-builder` without opening a GitHub PR.

### CUJ 2: Unresolved Round 2 Review Escalates to Human Blocked Instead of Approving

*   **Given**: A task with an open PR that failed Round 1 review (`review_round = 1`), was reworked by `zf-builder` in a new commit SHA, and is now dispatched to `zf-reviewer` for Round 2 (`Round 2 of 2`).
*   **When**: `zf-reviewer` inspects the updated diff, finds that an edge case from Round 1 is still broken, posts `[AI:zf-reviewer] [Reviewer Feedback] Round 2: ...` on GitHub, and runs `hermes zerofactory block <task_id> --reason "changes-requested"`.
*   **Then**: `_poll_pr_and_route_review()` increments `review_round` to `2` (without resetting on the new commit SHA), detects `review_round >= max_review_rounds` (`2`), stops the worker, removes the worktree, and updates the task to `status = 'blocked'`, `assignee = 'human'`, `blocked_reason_type = 'human-gate'`, `review_cap_reached = True` (preventing Auto-Merge and avoiding `awaiting_merge`). Subsequent 30-second poll cycles short-circuit without duplicating `review_cap_reached` activity logs.

### CUJ 3: Human Operator Recovers a Review-Cap-Blocked Task

*   **Given**: A task parked in `Human (blocked)` with `metadata["review_cap_reached"] = True` and `metadata["review_round"] = 2`.
*   **When**: A human operator runs `hermes zerofactory recover <task_id> --guidance "Fix the null check in parse_token"`.
*   **Then**: The recovery handler clears `review_cap_reached`, `review_round`, and legacy `commit_review_count`, stores the guidance, and moves the task back to `Todo (building)` for `zf-builder` with a fresh 2-round review budget.

## Technical Plan (Architecture)

The hardening spans three subsystems in the dispatcher and dashboard API:

1. **Deterministic Packaging & Diff Hygiene Engine (`dispatcher/slop_gate.py` & `dispatcher/context_builder.py`)**
2. **PR Review Round State Machine & Escalation (`dispatcher/scheduler.py`, `dashboard/routes/tasks.py`, `templates/zf-reviewer/SOUL.md`)**
3. **Reviewer Prompt Context Injection (`dispatcher/worker_spawner.py` & `dispatcher/context_builder.py`)**

```mermaid
flowchart TD
    BuilderDone["zf-builder completes work (packaging stage)"] --> Precommit[".zerofactory/precommit.sh (format -> build -> test)"]
    Precommit -->|Pass| SlopGate["run_deterministic_slop_gate(workspace, target_branch, spec_text, skip_untested_check)"]
    Precommit -->|Fail <= 3x| BuilderRetry["Route back to zf-builder with error log"]
    
    SlopGate -->|Hard Error: debug_leftover / placeholder_todo / test_disabled / diff_budget_exceeded (>800) / do_not_touch_violation / assertion_free_test / untested_production_diff (>20 net prod lines, 0 test lines)| BuilderRetry
    SlopGate -->|Pass (0 errors)| OpenPR["Commit, push, open/update GitHub PR"]
    
    OpenPR --> DigestCtx["digest_reviewer_git_context (400 lines / 24k chars + Diff Hygiene Scorecard with mock_heavy_test / suppressor_added / empty_except warnings)"]
    DigestCtx --> SpawnReviewer["Spawn zf-reviewer (Prompt displays 'Round X of 2')"]
    
    SpawnReviewer -->|Approved| HumanMerge["Human: awaiting_merge (or Auto-Merge)"]
    SpawnReviewer -->|Changes Requested (--reason changes-requested)| CheckRound{"review_round >= max_review_rounds (2)?"}
    
    CheckRound -->|No (Round 1)| Rework["Route back to zf-builder (review_round = 1)"]
    Rework --> BuilderDone
    CheckRound -->|Yes (Round 2 exhausted)| EscalateBlocked["Human: blocked (review_cap_reached = True, blocked_reason_type = 'human-gate')"]
    EscalateBlocked -->|hermes zerofactory recover| ResetCap["Clear review_cap_reached & review_round -> Todo (zf-builder)"]
```

### 1. Deterministic Slop Gate & Scorecard (`dispatcher/slop_gate.py`)

#### Data Model Extensions (`DiffHygieneReport`)
Extend `DiffHygieneReport` with production-code line counters so markdown, documentation, and configuration edits are separated from executable code changes:
*   `prod_code_lines_added: int = 0` — lines added in files where `_is_code_file(rel_path) and not is_test_file(rel_path)`.
*   `prod_code_lines_deleted: int = 0` — lines deleted in files where `_is_code_file(rel_path) and not is_test_file(rel_path)`.
*   `@property def prod_code_net_lines(self) -> int` — returns `self.prod_code_lines_added - self.prod_code_lines_deleted`.

#### Rule 1: Default 800-Line Net Diff Ceiling (`diff_budget_exceeded`)
*   Set `DEFAULT_MAX_DIFF_LINES = 800` as the default net diff budget when `ZEROFACTORY_MAX_DIFF_LINES` is unset or empty.
*   Allow setting `ZEROFACTORY_MAX_DIFF_LINES` to `0` or a negative integer to disable the hard diff cap.
*   When `max_diff_cap > 0 and report.net_lines > max_diff_cap`, append a `SlopFinding` with `rule="diff_budget_exceeded"` and `severity="error"`.

#### Rule 2: Spec `Do Not Touch` Boundary Enforcement (`do_not_touch_violation`)
*   Extract backtick-quoted file paths, directory prefixes, and globs from any `Do Not Touch` / `Non-Goals` / `Out of Scope` / `Negative Scope` section in the task specification, ignoring CLI commands or prose tokens containing whitespace or parentheses.
*   When extracted `Do Not Touch` patterns are non-empty, evaluate them against the **full un-excluded set of changed and untracked files** (`git diff --name-only <merge_base>` plus untracked paths prior to `EXCLUDED_DIFF_PATHSPECS` / `_is_excluded_untracked` filtering) while keeping `EXCLUDED_DIFF_PATHSPECS` active for line-count metrics. This guarantees forbidden modifications to generated bundles (e.g., `dashboard/dist/*`) or lockfiles are caught without inflating line-count budgets.
*   Emit `SlopFinding(rule="do_not_touch_violation", severity="error", ...)` for each matching file.

#### Rule 3: Assertion-Free New Test Detection (`assertion_free_test`) & Rule 5: Mock-Overload Scorecard Warning (`mock_heavy_test`)
*   When scanning added lines in a test file (`is_test_file(rel_path)`):
    *   Group added lines by newly added test definitions (`def test_*` / `async def test_*` in Python, `it(` / `test(` in JS/TS) up to the next function/class/test block at the same or outer indentation.
    *   If a newly added test block contains at least one non-empty, non-comment body line (`stripped and not stripped.startswith(("#", "//"))`) and zero assertion indicators (`assert`, `self.assert*`, `pytest.raises`, `pytest.warns`, `expect(`, `.toBe`, `.toEqual`, `.toThrow`, `.assert_called*`), emit `SlopFinding(rule="assertion_free_test", severity="error", ...)`.
    *   Count added mock/patch lines (`MagicMock`, `AsyncMock`, `patch`, `monkeypatch.setattr`, `mocker.patch`, `jest.fn`, `vi.fn`, `sinon.stub`, etc.) vs. assertion lines across the test file. When `mock_count >= 4 and mock_count > assert_count`, emit `SlopFinding(rule="mock_heavy_test", severity="warning", ...)`.

#### Rule 4: Untested Production Code Diff (`untested_production_diff`)
*   Define `DEFAULT_UNTESTED_PROD_LINE_THRESHOLD = 20`.
*   When `not skip_untested_check` and `not os.environ.get("ZEROFACTORY_SKIP_UNTESTED_CHECK")`, emit `SlopFinding(rule="untested_production_diff", severity="error", ...)` if `report.prod_code_net_lines > 20` and `report.test_lines_added == 0`.

#### Packaging Integration (`dispatcher/scheduler.py`)
*   In `_package_and_open_pr()`, hoist the existing `target_branch` and `repo_alias` resolution block (currently located just before `package.merge`) to execute before `steps.start("package.slop_gate")` so `target_branch` is resolved once and passed into both `run_deterministic_slop_gate()` and `pull_and_merge_main()`.

### 2. True 2-Round Review Cap & Safe Escalation (`dispatcher/scheduler.py`, `dashboard/routes/tasks.py`, `templates/zf-reviewer/SOUL.md`)

*   **Idempotent Guard in `_poll_pr_and_route_review()`**:
    *   Before entering the `if has_actionable_feedback:` rework/escalation branch, check if `bool(task_meta.get("review_cap_reached")) and row["status"] == "blocked" and (row["assignee"] or "") == "human" and not new_pr_comments`. If true, return `False` immediately so the 30-second poll loop does not re-trigger or append duplicate `review_cap_reached` rows to `task_activity`.
*   **Cumulative Review Round Counting Across Commits**:
    *   Use `review_round` as the canonical metadata key across the PR review lifecycle, reading `int(task_meta.get("review_round", task_meta.get("commit_review_count", 0))) + 1` for backward compatibility on in-flight tasks and popping legacy `commit_review_count` (or syncing it only if required by existing callers).
    *   Record `task_meta["last_reviewed_commit"] = head_commit_sha` for observability without resetting `review_round`.
    *   Trigger cap escalation when `review_round >= max_review_rounds` (where `max_review_rounds` defaults to `2` via `ZEROFACTORY_MAX_REVIEW_ROUNDS`):
        *   **After Round 1 (`review_round == 1 < 2`)**: Route back to `zf-builder` (`status = 'todo'`, `assignee = builder_author`) and provision the worktree for rework.
        *   **After Round 2 (`review_round >= 2`)**: Stop the worker, remove the worktree, set `task_meta["blocked_reason"]`, `task_meta["blocked_reason_type"] = "human-gate"`, `task_meta["review_cap_reached"] = True`, update the task to `assignee = 'human', status = 'blocked'`, and log `review_cap_reached` once to `task_activity`.
*   **Reset on Task Recovery (`dashboard/routes/tasks.py`)**:
    *   In `recover_task()`, clear `review_cap_reached`, `review_round`, and legacy `commit_review_count` alongside the existing retry counters so a human-recovered task receives a fresh 2-round review budget.
*   **Reviewer Protocol Fix (`templates/zf-reviewer/SOUL.md`)**:
    *   Update `templates/zf-reviewer/SOUL.md` to refer to "2 Reviews per PR" and instruct `zf-reviewer` on Round 2: if issues remain unresolved, submit findings and run `hermes zerofactory block <task_id> --reason "changes-requested"` (never `--reason "approved"`), letting the dispatcher enforce the 2-round cap and escalate to `Human (blocked)`.

### 3. Reviewer Prompt Round Context & Inline Diff Preview (`dispatcher/worker_spawner.py` & `dispatcher/context_builder.py`)

*   In `dispatcher/worker_spawner.py`:
    *   Hoist `task_meta` parsing (`json.loads(metadata or "{}")`) once above the role-specific `if assignee == ...` branches so `task_meta` is available in `zf-reviewer`, `zf-orchestrator`, `zf-goldfish`, and `zf-builder` branches without duplicate JSON parsing.
    *   In the `zf-reviewer` branch, query `target_branch` from `board_repositories` filtering by `(board_slug, repo_alias)` first (falling back to `board_slug` when `repo_alias` is unset).
    *   Compute `current_review_round = int(task_meta.get("review_round", task_meta.get("commit_review_count", 0))) + 1` and `max_review_rounds = int(os.environ.get("ZEROFACTORY_MAX_REVIEW_ROUNDS", "2"))`.
    *   Pass `spec_text = str(task_meta.get("specification") or description or "")` and `skip_untested_check = bool(task_meta.get("skip_untested_check"))` into `digest_reviewer_git_context()`.
    *   Include `Review Round: Round {current_review_round} of {max_review_rounds}` in the reviewer prompt header and state in step 6 that whenever changes are needed (in Round 1 or Round 2), `zf-reviewer` must run `hermes zerofactory block {task_id} --reason 'changes-requested'`.
*   In `dispatcher/context_builder.py`:
    *   Import and reuse `_resolve_merge_base` and `EXCLUDED_DIFF_PATHSPECS` from `dispatcher/slop_gate.py` instead of duplicating merge-base resolution and pathspec tuples.
    *   Retain `max_diff_lines: int = 400` and `max_diff_chars: int = 24000` in `digest_reviewer_git_context()`, and forward `spec_text: str | None = None` and `skip_untested_check: bool = False` to `build_diff_hygiene_scorecard()`.

## Alternatives Considered

### Alternative A: Uncapped Inline Diff Preview in `digest_reviewer_git_context()`

*   **Pros**: Guarantees `zf-reviewer` always sees 100% of changed lines directly inside the initial prompt without ever running `git diff` in the workspace.
*   **Cons**: Large pull requests (such as multi-file refactors or test fixtures) can exceed Linux's 128 KB single-argument limit (`MAX_ARG_STRLEN`) when spawning the `hermes` CLI worker process, inflate input token cost, and degrade LLM review accuracy due to middle-context attention loss.
*   **Reason for Rejection**: Rejected by author: dumping unbounded diffs into the reviewer CLI prompt risks `E2BIG` process-spawn failures, spikes token costs on large files, and degrades review accuracy on long diffs. Raising the inline preview cap to `400` lines / `24,000` characters covers normal pull requests in full while keeping a safe upper bound.

### Alternative B: Fake-Approving Unresolved Round 2 PRs (`--reason "approved"`)

*   **Pros**: Avoids adding a dedicated `review_cap_reached` escalation path in `dispatcher/scheduler.py` by reusing the existing `approved` -> `awaiting_merge` state transition.
*   **Cons**: Makes an unapproved, defective pull request indistinguishable from a clean approval in the `Human` column (`awaiting_merge`), and causes boards with Auto-Merge enabled to automatically merge broken code into the target branch.
*   **Reason for Rejection**: Rejected by author: routing unresolved Round 2 PRs through `--reason "approved"` places defective code in `awaiting_merge` and causes boards with Auto-Merge enabled to merge broken code into the target branch.

### Alternative C: Per-Commit Review Counter (`commit_review_count` Reset on New Commit SHA)

*   **Pros**: Allows `zf-reviewer` up to two review attempts on each individual commit SHA if a review process is interrupted or re-run on the same commit.
*   **Cons**: Because `zf-builder` creates a new commit every time it addresses review feedback, resetting the counter when `head_commit_sha != last_reviewed_commit` resets the round count to `1` on every rework commit, preventing the 2-round review cap from ever terminating builder-reviewer ping-pong loops.
*   **Reason for Rejection**: Rejected by author: resetting the counter on new commit SHAs prevents the 2-round review cap from ever triggering across builder-reviewer rework loops.

--------------------------------------------------------------------------------

## Non-Functional Requirements

*   **Performance & Latency**: All checks in `dispatcher/slop_gate.py` execute deterministically in Python using `git diff` and standard-library regex/path matching in `< 100 ms` with `0` LLM tokens consumed.
*   **Security & Safety**: Preventing fake Round 2 approvals (`--reason "approved"`) guarantees that Auto-Merge boards never merge pull requests that still have unresolved `zf-reviewer` objections.
*   **Rollout & Rollback**: All new hard gates support environment-variable overrides (`ZEROFACTORY_SKIP_SLOP_GATE=1` to bypass the entire gate, `ZEROFACTORY_MAX_DIFF_LINES=0` to disable the net diff line cap, and `ZEROFACTORY_SKIP_UNTESTED_CHECK=1` or task metadata `skip_untested_check=True` to bypass `untested_production_diff`).

--------------------------------------------------------------------------------

### Additional Resources

*   [`docs/FLOWS.md`](../FLOWS.md) — End-to-end packaging, anti-slop gate, and review handoff sequences.
*   [`docs/DEBUGGING.md`](../DEBUGGING.md) — Incident playbook and SQLite `task_activity` / metadata inspection queries.
*   [`templates/zf-reviewer/SOUL.md`](../../templates/zf-reviewer/SOUL.md) — System prompt and 2-round review protocol for `zf-reviewer`.

### Future Improvements

*   **Per-File Chunked Reviewer Fallback**: For pull requests that exceed the 400-line / 24,000-character inline preview cap, pre-digest per-file hunk summaries so `zf-reviewer` sees an outline of every truncated file before running `git diff <file>`.

--------------------------------------------------------------------------------

## Detailed Implementation Plan

### Target Files to Create/Modify

#### 1. `dispatcher/slop_gate.py` (Modify)

*   **Type / Scope**: Python Module (Deterministic Pre-PR Gate & Diff Hygiene Scorecard)
*   **Proposed Changes**:
    *   **Why**: Expand the deterministic pre-PR gate and reviewer scorecard to catch `Do Not Touch` file violations (including excluded globs like `dashboard/dist/*`), oversized diffs by default, assertion-free new tests, untested production code diffs, and mock-heavy test additions.
    *   **What**:
        *   Add constants `DEFAULT_MAX_DIFF_LINES = 800` and `DEFAULT_UNTESTED_PROD_LINE_THRESHOLD = 20`.
        *   Extend `DiffHygieneReport` with `prod_code_lines_added: int = 0`, `prod_code_lines_deleted: int = 0`, and property `prod_code_net_lines -> int`.
        *   Add `extract_do_not_touch_patterns(spec_text: str | None) -> list[str]`:
            *   Match section headers via `(?im)^(?:#{1,4}\s*|\*\*|[-*]\s*\*\*)[^*\n]*(?:do\s+not\s+touch|non-goals|out\s+of\s+scope|negative\s+scope)[^*\n]*(?:\*\*)?:?\s*(.*)$` up to the next heading `^(?:#{1,4}\s+|\*\*[A-Z][^*\n]+:\*\*)`.
            *   Extract backticked tokens `` `([^`\n]+)` `` that contain no whitespace, parentheses, or `--` flags and contain `/`, glob wildcards (`*`, `?`), or known file extensions.
        *   Add `_matches_do_not_touch(rel_path: str, pattern: str) -> bool` using normalized POSIX paths, directory prefix matching (`norm_pat.rstrip("/") + "/"`), and `fnmatch.fnmatch`.
        *   When `do_not_touch_patterns` is non-empty in `analyze_workspace_diff()`, query all changed paths without `EXCLUDED_DIFF_PATHSPECS` (`git diff --name-only <merge_base>` or `<merge_base>..HEAD` plus all untracked files prior to `_is_excluded_untracked()`) and emit `SlopFinding(rule="do_not_touch_violation", severity="error", ...)` for any matching file.
        *   In `_scan_added_lines()` when `test_file` is `True`:
            *   Match newly added Python test definitions (`_RE_PY_TEST_DEF = re.compile(r"^(\s*)(?:async\s+)?def\s+(test_[A-Za-z0-9_]*)\s*\(")`) and JS/TS test definitions (`_RE_JS_TEST_DEF = re.compile(r"^(\s*)(?:it|test)\s*\(\s*['\"`]")`).
            *   Match assertion indicators (`_RE_ASSERTION`: `\bassert\b`, `self\.assert`, `pytest\.(?:raises|warns|deprecated_call|fail)\b`, `\bexpect\s*\(`, `\.to(?:Be|Equal|Throw|Have|Match|Contain)\b`, `\.assert_called`, `\bassert_[A-Za-z0-9_]+\s*\(`, `\bmock\.assert`).
            *   Match mock usages (`_RE_MOCK_USAGE`: `\b(?:MagicMock|AsyncMock|NonCallableMock|patch(?:\.object|\.dict|\.multiple)?|monkeypatch\.setattr|mocker\.patch|jest\.fn|jest\.spyOn|vi\.fn|vi\.spyOn|sinon\.(?:stub|mock|spy))\b` or `@patch\b`).
            *   Emit `SlopFinding(rule="assertion_free_test", severity="error", ...)` when a newly added test block has at least one non-empty, non-comment body line (`stripped and not stripped.startswith(("#", "//"))`) and zero lines matching `_RE_ASSERTION`.
            *   Emit `SlopFinding(rule="mock_heavy_test", severity="warning", ...)` when `mock_count >= 4 and mock_count > assert_count` in a test file.
        *   In `analyze_workspace_diff(..., spec_text: str | None = None, skip_untested_check: bool = False)`:
            *   Enforce `diff_budget_exceeded` at `DEFAULT_MAX_DIFF_LINES` (`800`) when `ZEROFACTORY_MAX_DIFF_LINES` is unset (disabled when `<= 0`).
            *   Emit `untested_production_diff` (`error`) when `prod_code_net_lines > 20` and `test_lines_added == 0` unless `skip_untested_check` or `ZEROFACTORY_SKIP_UNTESTED_CHECK` is active.
        *   Update `run_deterministic_slop_gate()` and `build_diff_hygiene_scorecard()` signatures to accept and forward `spec_text: str | None = None` and `skip_untested_check: bool = False`, and format `mock_heavy_test` in the scorecard warning bullets.

#### 2. `dispatcher/context_builder.py` (Modify)

*   **Type / Scope**: Python Module (Agent Prompt Context Ingestion)
*   **Proposed Changes**:
    *   **Why**: Ensure normal pull requests are shown in full inline (`400` lines / `24,000` chars), reuse merge-base and pathspec logic from `dispatcher/slop_gate.py`, and forward `spec_text` and `skip_untested_check` to `build_diff_hygiene_scorecard()`.
    *   **What**:
        *   Import and reuse `_resolve_merge_base` and `EXCLUDED_DIFF_PATHSPECS` from `dispatcher.slop_gate` instead of duplicating merge-base subprocess calls and pathspec lists in `digest_reviewer_git_context()`.
        *   Keep `max_diff_lines: int = 400` and `max_diff_chars: int = 24000` as the defaults on `digest_reviewer_git_context()`.
        *   Add optional parameters `spec_text: str | None = None` and `skip_untested_check: bool = False` to `digest_reviewer_git_context()` and forward both into `build_diff_hygiene_scorecard()`.

#### 3. `dispatcher/worker_spawner.py` (Modify)

*   **Type / Scope**: Python Module (Agent Worker Prompt Construction)
*   **Proposed Changes**:
    *   **Why**: Hoist `task_meta` parsing once across all role branches, resolve `target_branch` accurately for multi-repo boards (`repo_alias`), make `zf-reviewer` aware of the active review round (`Round X of Y`), and forward `spec_text` and `skip_untested_check` into `digest_reviewer_git_context()`.
    *   **What**:
        *   Hoist `task_meta` parsing (`json.loads(metadata or "{}") if isinstance(metadata, str) else dict(metadata or {})`) above `if assignee == "zf-reviewer":` (around line 228) and reuse `task_meta` across the `zf-reviewer`, `zf-orchestrator`, `zf-goldfish`, and `zf-builder` branches.
        *   In `if assignee == "zf-reviewer":`, query `target_branch` from `board_repositories` filtering by `(board_slug, repo_alias)` when `repo_alias` is set, falling back to `board_slug` (`ORDER BY id ASC LIMIT 1`).
        *   Compute `current_review_round = int(task_meta.get("review_round", task_meta.get("commit_review_count", 0))) + 1` and `max_review_rounds = int(os.environ.get("ZEROFACTORY_MAX_REVIEW_ROUNDS", "2"))`.
        *   Pass `spec_text=str(task_meta.get("specification") or description or "")` and `skip_untested_check=bool(task_meta.get("skip_untested_check"))` into `_d().digest_reviewer_git_context(...)`.
        *   Add `Review Round: Round {current_review_round} of {max_review_rounds}` to the reviewer prompt header and clarify in step 6 that whenever changes are requested (in any round), `zf-reviewer` must run `hermes zerofactory block {task_id} --reason 'changes-requested'`.

#### 4. `dispatcher/scheduler.py` (Modify)

*   **Type / Scope**: Python Module (Packaging & PR Review Routing State Machine)
*   **Proposed Changes**:
    *   **Why**: Hoist `target_branch` resolution in `_package_and_open_pr()` so `run_deterministic_slop_gate()` receives `target_branch`, `spec_text`, and `skip_untested_check`; count review rounds cumulatively across builder rework commits; escalate unresolved Round 2 PRs (`review_round >= max_review_rounds`) to `Human (blocked)`; and prevent 30-second poll re-triggers once `review_cap_reached` is set.
    *   **What**:
        *   In `_poll_pr_and_route_review()` (around line 1345): Add an idempotent guard before processing `has_actionable_feedback`—if `bool(task_meta.get("review_cap_reached")) and row["status"] == "blocked" and (row["assignee"] or "") == "human" and not new_pr_comments`, return `False`.
        *   In `_poll_pr_and_route_review()` (lines 1429–1471): Stop resetting the review counter when `last_reviewed_commit != head_commit_sha`. Increment `review_round = int(task_meta.get("review_round", task_meta.get("commit_review_count", 0))) + 1`, update `task_meta["last_reviewed_commit"] = head_commit_sha`, `task_meta["review_round"] = review_round`, and `task_meta["commit_review_count"] = review_round` (for backward compatibility with existing readers). Escalate to `assignee = 'human'`, `status = 'blocked'`, `blocked_reason_type = 'human-gate'`, `review_cap_reached = True` when `review_round >= max_review_rounds` (default `2`).
        *   In `_package_and_open_pr()`: Hoist the `repo_alias` and `target_branch` resolution block from lines `1992–2020` to run before `steps.start("package.slop_gate")` at line 1921, then pass `target_branch=target_branch or None`, `spec_text=str((meta or {}).get("specification") or row["description"] or "")`, and `skip_untested_check=bool((meta or {}).get("skip_untested_check"))` to `_disp.run_deterministic_slop_gate()`.

#### 5. `dashboard/routes/tasks.py` (Modify)

*   **Type / Scope**: Python FastAPI Route & CLI Recovery Backend (`recover_task`)
*   **Proposed Changes**:
    *   **Why**: When an operator recovers a blocked task via `hermes zerofactory recover <task_id>` or the dashboard UI, reset the 2-round review cap so the recovered builder run gets a fresh review budget.
    *   **What**:
        *   In `recover_task()` (lines 1713–1728): Add `meta.pop("review_cap_reached", None)`, `meta.pop("review_round", None)`, and `meta.pop("commit_review_count", None)` to the metadata cleanup block.

#### 6. `templates/zf-reviewer/SOUL.md` (Modify)

*   **Type / Scope**: Agent System Prompt Template (`zf-reviewer`)
*   **Proposed Changes**:
    *   **Why**: Remove the instruction on line 28 that tells `zf-reviewer` to run `--reason "approved"` when Round 2 still has unresolved defects, preventing fake approvals and accidental auto-merges.
    *   **What**:
        *   Update lines 12, 14, and 28 to state that the 2-round review cap applies per PR (across rework commits) and that if Round 2 issues remain unresolved, `zf-reviewer` must submit its findings and run `hermes zerofactory block <task_id> --reason "changes-requested"` so the dispatcher escalates the task to `Human (blocked)`.

#### 7. `tests/unit/dispatcher/test_slop_gate.py` (Modify)

*   **Type / Scope**: Unit Test Suite
*   **Proposed Changes**:
    *   **Why**: Validate all five new deterministic checks and scorecard flags in `dispatcher/slop_gate.py`.
    *   **What**:
        *   Add unit tests covering `DEFAULT_MAX_DIFF_LINES = 800` (and `ZEROFACTORY_MAX_DIFF_LINES=0` opt-out), `extract_do_not_touch_patterns()` and `do_not_touch_violation` (including excluded paths such as `dashboard/dist/index.js`), `assertion_free_test` on Python and JS test files, `untested_production_diff` (verifying docs-only and `<= 20` line diffs pass while `> 20` net production code lines with `0` test lines fail unless `skip_untested_check=True`), and `mock_heavy_test` warning generation in `build_diff_hygiene_scorecard()`.

#### 8. `tests/unit/dispatcher/test_context_builder.py` (Modify)

*   **Type / Scope**: Unit Test Suite
*   **Proposed Changes**:
    *   **Why**: Verify the 400-line / 24,000-character inline diff preview defaults and `spec_text` / `skip_untested_check` forwarding to the Diff Hygiene Scorecard.
    *   **What**:
        *   Retain `test_digest_reviewer_git_context_diff_limits` and add assertions verifying `spec_text` and `skip_untested_check` forwarding into `digest_reviewer_git_context()`.

#### 9. `tests/unit/dispatcher/test_review_cap.py` (Modify)

*   **Type / Scope**: Unit Test Suite
*   **Proposed Changes**:
    *   **Why**: Update the review cap test expectations from the old per-commit-SHA counter reset (`commit_review_count > 2` on identical SHA) to cumulative per-PR review rounds (`review_round >= 2` across distinct rework commit SHAs) plus idempotent poll handling and recovery reset.
    *   **What**:
        *   Update existing test cases to assert that Round 1 `changes-requested` (`review_round == 1`) routes back to `zf-builder`, Round 2 `changes-requested` on a new commit SHA (`review_round == 2 >= max_review_rounds`) escalates to `status = 'blocked'`, `assignee = 'human'`, `review_cap_reached = True`, subsequent poll cycles with no new comments short-circuit without adding duplicate `review_cap_reached` activity rows, and calling `recover_task()` clears `review_cap_reached`, `review_round`, and `commit_review_count`.

#### 10. `docs/FLOWS.md` and `docs/DEBUGGING.md` (Modify)

*   **Type / Scope**: Architecture, Flow, and Debugging Reference Documentation
*   **Proposed Changes**:
    *   **Why**: Satisfy the mandatory 3-surface Documentation Sync Rule (`AGENTS.md`) for changes to packaging gates and review round state transitions.
    *   **What**:
        *   Update `docs/FLOWS.md` lines `107`, `228–231`, `306`, `342–352`, `403`, `539`, and `558` to document the new deterministic slop gate rules (`DEFAULT_MAX_DIFF_LINES = 800`, `do_not_touch_violation`, `assertion_free_test`, `untested_production_diff`, `mock_heavy_test`) and replace all "per commit SHA" review round descriptions with cumulative per-PR review rounds (`review_round >= 2` escalates to `Human (blocked)`).
        *   Update `docs/DEBUGGING.md` line `166` from `2 review rounds per commit` to `2 review rounds per PR`.

#### 11. `README.md` (Modify — symlinked as `AGENTS.md`)

*   **Type / Scope**: Root Documentation & Agent Rules
*   **Proposed Changes**:
    *   **Why**: Satisfy the mandatory Documentation Sync Rule (`AGENTS.md`).
    *   **What**:
        *   Update step 4 of `Task Lifecycle & Workflow` (around line 200) to list the expanded deterministic anti-slop gate checks (`do_not_touch_violation`, default 800-line diff cap, assertion-free tests, untested production code diffs, and scorecard `mock_heavy_test` warnings) and clarify that unresolved Round 2 reviews escalate to `Human (blocked)`.

#### 12. `dashboard/src/views/InstructionsView.jsx`, `dashboard/dist/index.js`, and `dashboard/dist/style.css` (Modify)

*   **Type / Scope**: Dashboard UI Documentation Component & Built Bundle
*   **Proposed Changes**:
    *   **Why**: Satisfy the mandatory 3-surface Documentation Sync Rule (`AGENTS.md`).
    *   **What**:
        *   Update the Phase 2 `packaging` and `review` stage descriptions in `dashboard/src/views/InstructionsView.jsx` (around lines `244–245`, `294–307`, and `501–509`) to reflect the expanded Anti-Slop Gate checks and the 2-round per-PR review cap escalating to `Human (blocked)`.
        *   Run `npm run build` in `dashboard/` to regenerate `dashboard/dist/index.js` and `dashboard/dist/style.css`.

### Verification Plan

*   **Compilation/Build**: `cd dashboard && npm run build` (verifies clean frontend bundle build for `dashboard/dist/index.js` and `dashboard/dist/style.css`).
*   **Unit Tests**: `pytest tests/unit/dispatcher/test_slop_gate.py tests/unit/dispatcher/test_context_builder.py tests/unit/dispatcher/test_review_cap.py tests/unit/dispatcher/test_automerge.py -v`
*   **Full Dispatcher Test Suite**: `pytest tests/unit/dispatcher/ -v`
*   **Static Analysis & Precommit Gate**: `.zerofactory/precommit.sh` (or repository linter/test runner).

--------------------------------------------------------------------------------

<!-- Provenance: Indicates initial structural drafting via Elephant-Goldfish Model (EGM). -->

*Drafted with EGM*
