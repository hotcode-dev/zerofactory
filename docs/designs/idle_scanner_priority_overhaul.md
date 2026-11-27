# Idle Improvement Scanner Priority & Anti-Slop Overhaul

*   **Author:** ntsd
*   **Status:** Proposed
*   **Date:** 2026-11-26

--------------------------------------------------------------------------------

## Overview

This design overhauls Zero Factory's idle improvement scanner (`zf-orchestrator` spawned by `dispatcher/scanner.py`) so autonomous scans prioritize **high-risk missing tests first**, followed by **verified bugs**, **dead code or duplicate logic**, and **net-LOC-reducing simplifications**. It makes `skills/zf-orchestrator-ponytail/SKILL.md` the single source of truth for the 4-tier rubric, enforces concrete file-and-line evidence and a low-mock test strategy, clamps all scanner-filed tasks to `P3` with `metadata["source"] = "idle_scanner"` at the CLI boundary (`./__init__.py`) when `ZEROFACTORY_IDLE_SCAN=1` is set, and updates `dispatcher/scheduler.py` so non-scanner tasks win priority ties.

## The Problem

1.  **Wrong scanning priorities:** Today, `dispatcher/scanner.py`, `templates/zf-orchestrator/SOUL.md`, and `skills/zf-orchestrator-ponytail/SKILL.md` focus the idle scanner almost exclusively on Ponytail refactoring (Zero Factory's 7-Rung Ladder of Laziness for dead code, redundant helpers, dependency bloat, and single-caller abstractions) and do not instruct it to look for missing tests at all—even though `dashboard/src/views/InstructionsView.jsx` already claims the scanner looks for "missing tests."
2.  **Priority inversion on constrained hardware:** `skills/zf-orchestrator-ponytail/SKILL.md` tells the scanner to file tasks at `--priority P1`, and `dispatcher/scheduler.py` sorts `todo` tasks strictly by `priority` and `created_at` without distinguishing scanner-filed tasks from human-filed tasks. On constrained local hardware (for example, a 2-slot DGX Spark running Qwen 3.8), background scanner work can preempt or tie with human `P1`/`P2` work.
3.  **Test-slop risk without extra LLM gates:** Adding a `zf-goldfish` (`spec_audit` zero-context adversarial spec audit) and `spec_draft` rewrite loop to scanner tasks would consume 2x–3x local LLM turns on the same underlying model. Instead, the scanner playbook itself needs strict evidence and low-mock rules against coverage theater, backed by existing zero-token checks in `dispatcher/slop_gate.py` and `zf-reviewer` downstream during `packaging` (deterministic precommit and PR creation) and `review`.

## Goals

*   **4-tier scanner priority order:** Configure the idle scanner to evaluate and file at most 1 task per scan in strict order:
    1.  High-risk missing tests (uncovered entrypoints, error/exception branches, state transitions).
    2.  Verified bugs (reproducible logic, concurrency, or error-handling defects).
    3.  Dead code and duplicate logic (Ponytail Rungs 1–2: YAGNI and codebase reuse).
    4.  Net-LOC-reducing simplifications (Ponytail Rungs 3, 5, 6: stdlib reuse, dependency bloat removal, and flattening indirection; Rung 4 covers existing-code search and Rung 7 covers diff scope during PRs).
*   **Single source of truth & anti-slop guardrails:** Consolidate the 4-tier rubric in `skills/zf-orchestrator-ponytail/SKILL.md`, require exact `file:line-range` citations, scope pre-flight duplicate checks to open statuses (excluding `done`), require explicit `--files` / `--dedup-key` usage, and require a concrete low-mock test strategy for Tier 1 tasks.
*   **Deterministic `P3` priority & source tagging:** Automatically clamp scanner-created tasks to `priority = "P3"` and `metadata["source"] = "idle_scanner"` in `./__init__.py` when `ZEROFACTORY_IDLE_SCAN=1` is set, and break priority ties in `dispatcher/scheduler.py` in favor of non-scanner tasks (`priority ASC`, `is_scanner ASC` where `is_scanner` is shorthand for `metadata.source == 'idle_scanner'`, `created_at ASC`).
*   **Documentation sync:** Align `docs/FLOWS.md`, `README.md` (symlinked as `AGENTS.md`), and `dashboard/src/views/InstructionsView.jsx` (plus rebuilt `dashboard/dist/`).

## Non-Goals

*   Adding a `zf-goldfish` (`spec_audit`) gate or `spec_draft` rewrite loop to scanner-filed tasks.
*   Building a custom multi-factor scoring engine or adding new SQLite columns when `metadata["source"]` + tie-breaking is sufficient.
*   Chasing arbitrary line-coverage percentages or turning `mock_heavy_test` in `dispatcher/slop_gate.py` into a hard blocking error.
*   Changing multi-repo `repo_alias` resolution in `spawn_board_scanner` (which continues to target the resolved board repository working directory).

## Open Questions

None. (Confirmed in `./__init__.py` that `--category test` is the canonical category for test tasks.)

## Critical User Journeys (CUJs)

### CUJ 1: Idle Scanner Files a High-Risk Missing Test Task

*   **Given:** A board has `scan_on_idle` enabled in board cron settings, active LLM workers are below `max_concurrent_llm_workers` (e.g., 2 on DGX Spark), and a module has an untested error-handling branch or state transition.
*   **When:** `spawn_board_scanner` launches `zf-orchestrator` with `ZEROFACTORY_IDLE_SCAN=1`.
*   **Then:** `zf-orchestrator` checks open tasks (`todo`, `running`, `triage`, `blocked`) to avoid duplicates, prioritizes high-risk missing tests over refactors, and files at most 1 task (respecting `idle_scan_max_todo`) citing exact `file:line-range` evidence, `--files` / `--dedup-key`, and a concrete low-mock test strategy. `./__init__.py` clamps `priority = "P3"` and sets `metadata["source"] = "idle_scanner"`.

### CUJ 2: Human Task Preempts or Wins Ties Against Scanner Work

*   **Given:** A scanner-filed `P3` task is sitting in `todo`, and a human creates a `P1`/`P2` task (or a `P3` task at a later timestamp).
*   **When:** `dispatcher/scheduler.py` runs `run_dispatch_cycle`.
*   **Then:** Any human `P0`–`P2` task is dispatched before the `P3` scanner task, and a human `P3` task wins the tie ahead of the `idle_scanner` `P3` task.

### CUJ 3: Downstream Anti-Slop Rejection Without Goldfish

*   **Given:** `zf-builder` picks up a scanner-filed test task and opens a PR with assertion-free tests or excessive mocking (`mock_count >= 4` and `mock_count > assert_count`).
*   **When:** The task enters `packaging` and `review`.
*   **Then:** `dispatcher/slop_gate.py` blocks assertion-free or skipped tests at 0 tokens, and surfaces any `mock_heavy_test` warning in the Diff Hygiene Scorecard (the deterministic pre-review summary passed to the reviewer) so `zf-reviewer` can request changes or reject coverage theater.

## Technical Plan (Architecture)

The overhaul spans three layers—**Scanner Discovery & Single-Source Playbook**, **CLI Boundary Tagging & Safe Tie-Breaking**, and **Downstream Anti-Slop Enforcement**—without introducing new agents, database tables, or pre-build `zf-goldfish` loops.

```text
[Idle Board + LLM Workers < max]
        │
        ▼
dispatcher/scanner.py: spawn_board_scanner()
  sets env ZEROFACTORY_IDLE_SCAN=1
  invokes zf-orchestrator (concise prompt -> zf-orchestrator-ponytail SKILL.md)
    1. High-risk missing tests (category: test, low-mock strategy)
    2. Verified bugs (category: bug-fix)
    3. Dead code & duplicate logic (category: refactoring)
    4. Net-LOC simplifications (category: refactoring)
        │
        ▼
./__init__.py: hermes zerofactory create  ──►  dashboard/routes/tasks.py: create_task()
  if ZEROFACTORY_IDLE_SCAN == "1":
    - clamps priority = "P3"
    - sets metadata["source"] = "idle_scanner"
        │
        ▼
dispatcher/scheduler.py: run_dispatch_cycle()
  orders by priority ASC, is_scanner ASC (safe metadata.source check), created_at ASC
        │
        ▼
zf-builder ──► dispatcher/slop_gate.py (0 tokens) ──► zf-reviewer
                 blocks: assertion_free_test,           vetoes mock_heavy_test
                         test_disabled                  coverage theater
                 warns:  mock_heavy_test
```

### 1. Single-Source Playbook & Concise Scanner Prompt

*   **`skills/zf-orchestrator-ponytail/SKILL.md` (Single Source of Truth):** Define the 4-tier priority order, required `file:line-range` evidence, open-task-only duplicate check (`--status todo`, `--status running`, `--status triage`, `--status blocked`), `--files` / `--dedup-key` guidance, category mapping (`test`, `bug-fix`, `refactoring`), `--priority P3`, and Tier 1 low-mock test strategy (preferring real `tmp_path` filesystems, temp SQLite DBs, and real function/FastAPI calls over mock chains).
*   **`templates/zf-orchestrator/SOUL.md` & `dispatcher/scanner.py` (`spawn_board_scanner`):** Keep `SOUL.md` as a high-level role contract pointing to `zf-orchestrator-ponytail`, and keep `spawn_board_scanner()`'s inline `-q` prompt concise (passing `board_slug` and `idle_scan_max_todo` / max 1 task per scan and directing the agent to follow the 4-tier rubric in `zf-orchestrator-ponytail`).

### 2. CLI Boundary Tagging & Safe Tie-Breaking

*   **CLI boundary clamping (`./__init__.py`):** `dispatcher/scanner.py` already exports `ZEROFACTORY_IDLE_SCAN=1` to the scanner subprocess, and `./__init__.py` (`action == "create"`) constructs `TaskCreate` and calls `create_task()` in-process. Enforcing `priority="P3"` and `metadata={"source": "idle_scanner"}` at the CLI boundary in `./__init__.py` keeps `dashboard/routes/tasks.py` free of hidden subprocess environment coupling.
*   **Safe tie-breaking (`dispatcher/scheduler.py`):** Update `run_dispatch_cycle()` to sort `todo` tasks by `priority ASC`, `is_scanner ASC` (where `is_scanner` is true when `metadata["source"] == "idle_scanner"`), and `created_at ASC`. Because `tasks.metadata` is an unvalidated `TEXT` column that may hold malformed JSON, guard any SQL `json_extract` call with `json_valid(metadata)` or apply the `is_scanner` tie-break in Python after the existing safe `json.loads` parse.

### 3. Downstream Anti-Slop Enforcement

*   **`dispatcher/slop_gate.py`:** No behavioral change needed. It already blocks `assertion_free_test` and `test_disabled` as errors and emits `mock_heavy_test` warnings (`mock_count >= 4 and mock_count > assert_count`) in the Diff Hygiene Scorecard.
*   **`templates/zf-reviewer/SOUL.md`:** Add one concise bullet under the existing Round 1 Ponytail Rubric instructing `zf-reviewer` to veto `mock_heavy_test` coverage theater (tests that mock out the behavior they claim to verify) when reviewing test PRs.

## Alternatives Considered

### Alternative A: Add a `zf-goldfish` (`spec_audit`) Gate + `spec_draft` Rewrite Loop on Scanner Tasks

*   **Pros:** Adds an independent zero-context review pass before `zf-builder` creates a worktree or edits files.
*   **Cons:** Consumes 2x–3x LLM turns on a constrained local concurrency budget (e.g., 2 slots on DGX Spark), mismatches `zf-goldfish`'s full architectural-spec rubric against small test/cleanup tasks, and runs on the same underlying model (Qwen 3.8) with shared blind spots.
*   **Reason for Rejection:** Extra pre-build LLM loops are not justified when `dispatcher/slop_gate.py` and `zf-reviewer` already gate output downstream.

### Alternative B: Add a One-Shot `zf-goldfish` Pass/Drop Filter (No Rewrite Loop)

*   **Pros:** Caps pre-build overhead at 1 extra LLM session while still dropping weak scanner tasks before `zf-builder` runs.
*   **Cons:** Still consumes 1 local concurrency slot (e.g., 1 of 2 on DGX Spark) and repeats file-reading work that `zf-orchestrator` just performed.
*   **Reason for Rejection:** Prioritized fixing the scanner's own priority order and evidence rules first without adding extra pre-build LLM sessions.

### Alternative C: Turn `mock_heavy_test` in `dispatcher/slop_gate.py` into a Hard Blocking Error

*   **Pros:** Enforces a zero-token deterministic block on any PR where `mock_count >= 4 and mock_count > assert_count`.
*   **Cons:** Risks false-positive blocks on legitimate integration or subprocess tests that genuinely require multiple mocks.
*   **Reason for Rejection:** Keeping `mock_heavy_test` as a warning in `slop_gate.py` lets `zf-reviewer` reject coverage theater in context without breaking valid tests.

### Alternative D: Strict `is_scanner ASC` Preemption Over `priority`

*   **Pros:** Guarantees every human task—even `P3`—preempts every scanner task regardless of priority labels.
*   **Cons:** Overrides explicit `P0`–`P3` priority ordering and is unnecessary when all scanner tasks are already clamped to `P3`.
*   **Reason for Rejection:** Setting all scanner tasks to `P3` and sorting by `priority ASC, is_scanner ASC, created_at ASC` (where `is_scanner` means `metadata.source == 'idle_scanner'`) keeps priority semantics intact while ensuring human `P0`–`P2` tasks always run first and human `P3` tasks win ties.

## Non-Functional Requirements

*   **Concurrency & Token Overhead:** No additional LLM sessions or background workers are introduced. Existing `max_concurrent_llm_workers`, `idle_scan_max_todo`, and scanner cooldown settings (configured in dashboard Settings / board cron config) continue to bound scanner and builder token usage for both local hardware (e.g., 2-slot DGX Spark) and API-paying users.
*   **Backward Compatibility:** Existing `tasks` rows without `metadata["source"]` or with malformed `metadata` evaluate safely as non-scanner (`0`), requiring no SQLite schema migration or data backfill.

--------------------------------------------------------------------------------

## Detailed Implementation Plan

### Target Files to Create/Modify

1.  **`skills/zf-orchestrator-ponytail/SKILL.md`** (Modify — Single Source of Truth for Scanner Rubric)
    *   **What changes & why:** Add "Tier 1: High-Risk Missing Tests" ahead of the Ponytail rungs, followed by Tier 2 (Verified Bugs), Tier 3 (Dead Code & Duplicate Logic), and Tier 4 (Net-LOC Simplifications). Require concrete `file:line-range` citations, open-task-only duplicate checks (`--status todo`, `--status running`, `--status triage`, `--status blocked`), `--files` / `--dedup-key` usage so distinct gaps in the same file do not collide, and a concrete low-mock test strategy (real `tmp_path`, temp SQLite DBs, real function/FastAPI calls; mock only external network or LLM subprocess boundaries). Update the task-filing example from `--category "refactoring" --priority P1` to `--priority P3` with `test`, `bug-fix`, and `refactoring` category guidance.

2.  **`dispatcher/scanner.py`** (Modify — Python Worker Spawner)
    *   **What changes & why:** Update the inline `-q` prompt in `spawn_board_scanner()` to be a concise invocation that passes `board_slug`, preserves the `idle_scan_max_todo` / "at most 1 task per scan" cap, and directs `zf-orchestrator` to apply the 4-tier priority order (missing tests first), low-mock test rules, and `--priority P3 --status todo --assignee zf-builder` from `zf-orchestrator-ponytail`.

3.  **`templates/zf-orchestrator/SOUL.md`** (Modify — Agent System Prompt Template)
    *   **What changes & why:** Update the Autonomous Repository Scanning responsibility and "Autonomous Codebase Auditing (Ponytail Scanner Lens)" section to reflect the 4-tier priority order (high-risk missing tests first) and `--priority P3`, referencing `zf-orchestrator-ponytail` for detailed heuristics rather than duplicating them.

4.  **`templates/zf-reviewer/SOUL.md`** (Modify — Reviewer System Prompt Template)
    *   **What changes & why:** Add one concise bullet under the existing Round 1 Ponytail Rubric instructing `zf-reviewer` to inspect `mock_heavy_test` warnings in the Diff Hygiene Scorecard and veto mock-heavy coverage theater on test PRs.

5.  **`./__init__.py`** (Modify — CLI Entrypoint)
    *   **What changes & why:** In the `action == "create"` handler (lines 979–1023), when `os.environ.get("ZEROFACTORY_IDLE_SCAN") == "1"`, clamp `priority="P3"` and pass `metadata={"source": "idle_scanner"}` into `TaskCreate(...)` before calling `_create_task(req)`. This keeps `dashboard/routes/tasks.py` free of subprocess environment coupling while leveraging `TaskCreate.metadata` (already merged by `create_task()`).

6.  **`dispatcher/scheduler.py`** (Modify — Task Dispatch Loop)
    *   **What changes & why:** Update both `SELECT ... FROM tasks ... ORDER BY` queries in `run_dispatch_cycle()` (the primary query and its `except sqlite3.OperationalError:` schema-fallback query) to sort by `CASE priority WHEN 'P0' THEN 0 WHEN 'P1' THEN 1 WHEN 'P2' THEN 2 WHEN 'P3' THEN 3 ELSE 4 END, CASE WHEN json_valid(metadata) AND json_extract(metadata, '$.source') = 'idle_scanner' THEN 1 ELSE 0 END ASC, created_at ASC`. Using `json_valid(metadata)` prevents `sqlite3.OperationalError: malformed JSON` on corrupt `metadata` rows.

7.  **`tests/unit/dispatcher/test_scanner.py`**, **`tests/unit/dispatcher/test_scheduler.py`**, **`tests/integration/test_tasks_api.py`** (Modify — Automated Tests)
    *   **What changes & why:**
        *   `test_scanner.py`: Verify `spawn_board_scanner()`'s prompt references the 4-tier priority order (missing tests first), `--priority P3`, and `idle_scan_max_todo` cap.
        *   `test_tasks_api.py` (or CLI create unit test): Verify `ZEROFACTORY_IDLE_SCAN=1` in `./__init__.py`'s `create` path clamps `priority = "P3"` and sets `metadata["source"] = "idle_scanner"`, leaving non-scanner tasks unaffected.
        *   `test_scheduler.py`: Verify `run_dispatch_cycle()` dispatches human `P0`–`P2` tasks before `idle_scanner` `P3` tasks, dispatches a human `P3` task ahead of an older `idle_scanner` `P3` task, and does not crash when a row has malformed `metadata` JSON.

8.  **`docs/FLOWS.md`**, **`README.md`** (symlinked as `AGENTS.md`), **`dashboard/src/views/InstructionsView.jsx`**, and rebuilt **`dashboard/dist/index.js`**, **`dashboard/dist/style.css`** (Modify — Documentation Sync Rule)
    *   **What changes & why:** Document the 4-tier scanner priority order (high-risk missing tests first), `P3` clamping / `idle_scanner` source tagging, and priority-first tie-breaking across all three documentation surfaces (keeping `InstructionsView.jsx` concise without duplicating `SKILL.md`), then rebuild the dashboard bundle.

### Verification Plan

*   **Unit & Integration Tests:** Run `pytest tests/unit/dispatcher/test_scanner.py tests/unit/dispatcher/test_scheduler.py tests/integration/test_tasks_api.py` to verify prompt contents, `ZEROFACTORY_IDLE_SCAN=1` clamping/tagging, malformed-JSON safety, and scheduler tie-breaking.
*   **Dashboard Build:** Run `npm run build` in `dashboard/` to verify `dashboard/dist/index.js` and `dashboard/dist/style.css` compile cleanly after updating `dashboard/src/views/InstructionsView.jsx`.
*   **Profile Sync Check:** Run `hermes zerofactory sync-profiles` after editing templates to propagate `templates/zf-orchestrator/SOUL.md` and `templates/zf-reviewer/SOUL.md` to live profiles.

--------------------------------------------------------------------------------

<!-- Provenance: Indicates initial structural drafting via EGM. -->

*Drafted with EGM*
