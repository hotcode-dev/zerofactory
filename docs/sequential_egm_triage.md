# Sequential Elephant-Goldfish Protocol in Zero Factory Triage

*   **Author:** ntsd
*   **Status:** Proposed
*   **Date:** 2026-11-05

--------------------------------------------------------------------------------

## Overview

Zero Factory is an autonomous multi-agent software factory operating 24/7 on local GPU hardware (a single DGX Spark node running open-weight 27B parameter models with a strict concurrency ceiling of 2).

This design introduces a sequential Elephant-Goldfish Model (EGM) into Zero Factory's `Triage` pipeline using a dedicated 4th profile (`zf-goldfish`). Under this protocol, when a complex or multi-repository goal enters `Triage`, `zf-orchestrator` acts as the Elephant to draft an architectural specification grounded in repository documentation. Upon completion, the dispatcher terminates the drafting session and spawns a fresh, zero-context review worker (`zf-goldfish`) acting as the Goldfish to audit the specification for YAGNI bloat, speculative abstractions, and implementation readiness. The task then parks in `Triage` assigned to `human` for one-click release before implementation tasks are decomposed and dispatched to `zf-builder`.

## The Problem

Operating an autonomous coding factory on local 27B-tier models introduces two competing constraints:

1. **High Downstream Failure Costs on 27B Models:**
   Unlike frontier cloud models (e.g., Claude 3.7 or GPT-4o), 27B open-weight models have higher susceptibility to unstated assumptions, vague acceptance criteria, and missing contract definitions. When a builder worker (`zf-builder`) receives an under-specified task, it frequently enters repetitive failure loops during `.zerofactory/precommit.sh` testing or multi-round PR reviews, tying up limited GPU capacity for hours.

2. **Severe Local GPU Concurrency Limits (DGX Spark):**
   A single DGX Spark node running 27B parameter models experiences steep throughput degradation and KV cache contention if concurrency exceeds 2. Canonical EGM implementations spawn 6 parallel subagents, which would instantly exhaust the 2-worker ceiling, starve running builders on other boards, and destabilize the local inference server.

3. **External Issue Flooding Vulnerability:**
   Default GitHub issue templates automatically attach the `zerofactory` label. If external feature requests automatically trigger full model drafting, unvetted or duplicate issues filed on public repositories will queue up model runs and drain local GPU availability.

A solution is needed that enforces adversarial specification stress-testing upstream while strictly honoring a concurrency footprint of 1 worker, zero conversational context pollution, and deterministic isolation from non-cognitive workflow tasks.

## Goals

*   **Strict Concurrency Cap ($\le 1$ Worker in Triage):** Execute the Elephant drafting and Goldfish audit sequentially as separate, stateless sessions so that the second GPU worker slot remains permanently available for active implementation tasks.
*   **Dedicated Goldfish Profile (`zf-goldfish`):** Establish a dedicated 4th profile with an isolated `state.db`, specialized contrarian system prompt, and strictly read-only tool privileges, integrated into the existing `hermes zerofactory setup` and `sync-profiles` mechanics.
*   **Zero-Context Adversarial Audit:** Guarantee that the Goldfish review runs in a fresh, isolated Hermes session with zero conversational memory of the drafting phase, evaluating only the draft specification, repository documentation, and the Ponytail Anti-Overengineering checklist.
*   **Deterministic Substrate Integration:** Manage all phase transitions (`elephant_drafting` $\rightarrow$ `goldfish_auditing` $\rightarrow$ `human_approval`) deterministically inside the Python dispatcher and SQLite substrate without requiring the LLM to manage Git, worktrees, or Kanban state.
*   **Parked Ingestion for Issue Flood Protection (Option A):** Ingest external GitHub issues into `status = 'triage'` with `assignee = 'human'`, ensuring zero automated GPU compute is spent on external submissions until explicitly activated by an operator.
*   **One-Click Operator Approval:** Provide clear UI badges and CLI commands (`hermes zerofactory approve`) so that human operators can inspect the side-by-side spec and audit and release the task with a single click.

## Non-Goals

*   **No Multi-Agent Swarms in Triage:** Spawning parallel subagents (e.g., the canonical 6-lens EGM swarm) inside a single task is strictly excluded to prevent GPU capacity collapse.
*   **No EGM for Routine Bug Fixes or Scanner Tasks:** Routine bugs and automated improvement scanner tasks will bypass EGM and use fast single-agent triage or direct `Todo` routing.
*   **No Changes to Builder or PR Review Mechanics:** `zf-builder` execution in isolated Git worktrees and the existing 2-round thematic PR review in `zf-reviewer` remain unchanged.
*   **No Autonomous Auto-Approval:** The system will not allow the Goldfish or Orchestrator to approve and split specifications into `Todo` without human sign-off.

## Open Questions

*   **Question 1 (Model Tiering):** Should `zf-goldfish` run on the same 27B model as `zf-orchestrator`, or should its profile `config.yaml` default to a lighter, faster quantized checkpoint (e.g., 14B) specifically for the audit pass?
*   **Question 2 (Revision Cap):** When a human requests spec revisions, should the rework loop between Elephant and Goldfish be capped at a maximum of 2 iterations before requiring manual specification?

## Critical User Journeys (CUJs)

### CUJ 1: Multi-Repository Epic Triage with EGM Verification

*   **Given**: A project board linking multiple repositories (e.g., `backend` and `frontend`) on a local DGX Spark node with active builder limit = 2.
*   **When**: An operator submits a high-level goal: `hermes zerofactory create "Add Webhook Delivery" --target-repos backend,frontend`.
*   **Then**:
    1. The dispatcher marks `triage_phase = 'elephant_drafting'` and spawns `zf-orchestrator`.
    2. `zf-orchestrator` drafts a technical specification into `tasks.description` and exits code 0.
    3. The reaper detects exit 0, updates `triage_phase = 'goldfish_auditing'`, and spawns `zf-goldfish` with a zero-context audit prompt.
    4. `zf-goldfish` audits the specification for YAGNI bloat and testability, posts findings to `task_comments`, and exits code 0.
    5. The reaper marks `triage_phase = 'human_approval'`, sets `assignee = 'human'`, and flags the card on the dashboard with `📋 Spec & Audit Ready`.
    6. The operator reviews the spec and audit, runs `hermes zerofactory approve <task_id> --split`, and the task decomposes into linked `Todo` tasks for each repository.

### CUJ 2: Parked GitHub Issue Ingestion (Abuse Protection)

*   **Given**: An external user files a feature request issue on GitHub using the repository template, which attaches the `zerofactory` label.
*   **When**: The 15-minute `zf_queue_watchdog.py` background cron runs and discovers the issue.
*   **Then**:
    1. The watchdog imports the issue deterministically into Kanban with `status = 'triage'` and `assignee = 'human'` (Option A).
    2. Zero LLM inference processes are spawned, and zero GPU tokens are consumed.
    3. The card appears in `Triage` on the dashboard with an "External Unverified" indicator.
    4. The operator inspects the issue. If duplicate or spam, the operator deletes or closes it without spending GPU compute. If approved, the operator clicks `[Run EGM Spec]` to initiate the Elephant drafting phase.

--------------------------------------------------------------------------------

## Technical Plan (Architecture)

### 1. Profile Topology & Isolation Boundaries

Zero Factory expands its agent profile roster from 3 to 4 specialized profiles in `~/.hermes/profiles/`:

| Profile | Substrate & Tool Permissions | Context Boundary | Primary Responsibility |
|---|---|---|---|
| `zf-orchestrator` | Workspace Read, SQLite Write (`tasks.description`, `memory`), Hermes CLI | Deep repository & goal context (Elephant) | Goal decomposition, docs inspection, specification drafting. |
| **`zf-goldfish`** | **Strictly Read-Only** Code & Docs, Discussion Comment Write | **Zero-Context** (No chat history, ephemeral session) | Adversarial audit: YAGNI violations, speculative bloat, acceptance criteria testability. |
| `zf-builder` | Worktree Read/Write, Shell Precommit, Git Stage | Isolated per-task Git worktree | Code and test implementation. |
| `zf-reviewer` | PR Diff Read, GitHub Review Comment Write | Isolated PR diff & commit log | 2-round thematic code review on GitHub PRs. |

`zf-goldfish` is provisioned identically to existing profiles via `setup.py` / `hermes zerofactory setup`, with prompt templates version-controlled in `profiles/zf-goldfish/system_prompt.txt`. It possesses no worktree tools and cannot mutate task statuses.

### 2. Dispatcher State Machine & Sequence

The dispatcher orchestrates the handoff through structured SQLite metadata without altering the core Kanban column (`status = 'triage'` throughout):

```text
       [Epic / Multi-Repo Task Created]
                       │
                       ▼
       ┌────────────────────────────────────────────────────────┐
       │ Step 1: Claim for Elephant                             │
       │ status = 'triage', assignee = 'zf-orchestrator'        │
       │ metadata["triage_phase"] = "elephant_drafting"         │
       └────────────────────────────────────────────────────────┘
                       │
                       ▼ (spawns hermes -p zf-orchestrator)
       ┌────────────────────────────────────────────────────────┐
       │ Elephant Phase:                                        │
       │ - Evaluates docs & architecture                        │
       │ - Updates tasks.description with specification         │
       │ - Exits code 0                                         │
       └────────────────────────────────────────────────────────┘
                       │
                       ▼ (reaper detects exit 0 & phase=="elephant_drafting")
       ┌────────────────────────────────────────────────────────┐
       │ Step 2: Transition to Goldfish                         │
       │ status = 'triage', assignee = 'zf-goldfish'            │
       │ metadata["triage_phase"] = "goldfish_auditing"         │
       └────────────────────────────────────────────────────────┘
                       │
                       ▼ (spawns hermes -p zf-goldfish --session-id goldfish-<task_id>)
       ┌────────────────────────────────────────────────────────┐
       │ Goldfish Phase (Zero Context):                         │
       │ - Ingests draft spec + architecture notes              │
       │ - Evaluates Ponytail Anti-Overengineering rules        │
       │ - Posts audit comment via zerofactory comment          │
       │ - Exits code 0                                         │
       └────────────────────────────────────────────────────────┘
                       │
                       ▼ (reaper detects exit 0 & phase=="goldfish_auditing")
       ┌────────────────────────────────────────────────────────┐
       │ Step 3: Human Release Gate                             │
       │ status = 'triage', assignee = 'human'                  │
       │ metadata["triage_phase"] = "human_approval"            │
       │ metadata["awaiting_approval"] = true                   │
       └────────────────────────────────────────────────────────┘
                       │
         ┌─────────────┴─────────────┐
         ▼                           ▼
[Human Clicks Approve]       [Human Requests Revision]
         │                           │
         ▼                           ▼
Promote to Todo              Reset: assignee = 'zf-orchestrator'
or Split across repos        triage_phase = 'elephant_drafting'
```

### 3. Database Schema & Query Modifications

1. **Scheduler Claim Query (`dispatcher/scheduler.py`):**
   Expand the task claim query so the dispatcher picks up both Elephant and Goldfish phases:
   ```sql
   UPDATE tasks 
   SET status = ?, updated_at = ?, metadata = ? 
   WHERE id = ? 
     AND (status = 'todo' OR (status = 'triage' AND assignee IN ('zf-orchestrator', 'zf-goldfish')))
   ```

2. **Metadata Contract (`tasks.metadata`):**
   ```json
   {
     "triage_phase": "elephant_drafting | goldfish_auditing | human_approval",
     "awaiting_approval": true,
     "audit_verdict": "pass | changes_recommended",
     "elephant_session_id": "orch-task-123",
     "goldfish_session_id": "goldfish-task-123",
     "revision_count": 0
   }
   ```

3. **Reaper State Transitions (`dispatcher/reaper.py`):**
   * When `assignee == 'zf-orchestrator'` exits 0 and `metadata["triage_phase"] == "elephant_drafting"`:
     - Set `metadata["triage_phase"] = "goldfish_auditing"`.
     - Set `assignee = "zf-goldfish"`.
     - Retain `status = "triage"`.
   * When `assignee == 'zf-goldfish'` exits 0 and `metadata["triage_phase"] == "goldfish_auditing"`:
     - Set `metadata["triage_phase"] = "human_approval"`.
     - Set `metadata["awaiting_approval"] = True`.
     - Set `assignee = "human"`.
     - Retain `status = "triage"`.

### 4. Spawner Prompt Assembly (`dispatcher/worker_spawner.py`)

* **Elephant Prompt (`zf-orchestrator`)**:
  Receives: Task Title, Description, Board Architecture (`board.architecture`), `openwiki/` links, board memories, and discussion history.
  Instruction: Draft comprehensive specification into `tasks.description` using the standard specification template (Context, Proposed Changes, Acceptance Criteria, Test Plan) and exit cleanly.
* **Goldfish Prompt (`zf-goldfish`)**:
  Zero conversational history. Receives strictly:
  1. The Draft Specification (extracted directly from `tasks.description`).
  2. The Board Architecture & inter-service contract definitions.
  3. The Ponytail Anti-Overengineering Audit Checklist:
     - *YAGNI / Minimalism:* Can this be solved with existing standard library code or repo utilities without new abstractions?
     - *Implementation Readiness:* Are file paths, interfaces, and migration steps concrete and testable?
     - *Failure Mode Coverage:* Are error states, edge cases, and rollback procedures defined?
  4. Terminal Command: Post structured audit comment via `hermes zerofactory comment {task_id} "<report>"` and exit cleanly.

### 5. Parked Ingestion Flow (`issues/importer.py` & `scripts/zf_queue_watchdog.py`)

In `scripts/zf_queue_watchdog.py` (L116–122):
```python
res = import_external_issue(
    issue=iss,
    board_slug=slug,
    status="triage",
    assignee="human",  # Option A: Parked Ingestion to prevent unverified GPU compute
    actor="zf-watchdog",
)
```
When imported:
* `status = "triage"`
* `assignee = "human"`
* `metadata["external_unverified"] = True`
* The task is ignored by the scheduler until an operator updates `assignee = "zf-orchestrator"`.

### 6. Operator Interface & CLI Commands

* **Dashboard Task Modal**:
  When `triage_phase == "human_approval"`, renders an amber header badge: `📋 Spec & Audit Ready`.
  Displays side-by-side tabs:
  1. `Draft Specification` (from `tasks.description`).
  2. `Goldfish Audit Report` (parsed from latest comment by `zf-goldfish`).
  Buttons:
  - `[✅ Approve & Split]` (for multi-repo tasks)
  - `[✅ Approve & Move to Todo]` (for single-repo tasks)
  - `[🔄 Request Revision]` (prompts for feedback, resets phase to `elephant_drafting`)
* **CLI Surface (`hermes zerofactory approve`)**:
  ```bash
  hermes zerofactory approve <task_id> [--split]
  hermes zerofactory reject <task_id> --feedback "Simplify interface"
  ```

--------------------------------------------------------------------------------

## Alternatives Considered

### Alternative A: Canonical Multi-Agent Swarm (6 Parallel Subagents)

*   **Pros**: Evaluates 6 specialized lenses (design, codebase, comprehension, structure, readiness, contrarian) simultaneously with fast wall-clock review.
*   **Cons**: Monopolizes up to 6 worker slots, instantly breaching the DGX Spark node's 2-worker concurrency ceiling, thrashes KV cache, and starves active builders.
*   **Reason for Rejection**: `Rejected by author: Multiplies token spend by 5x–7x and causes severe GPU latency and throughput collapse on a single DGX node with max concurrency = 2.`

### Alternative B: Reusing `zf-reviewer` or `zf-orchestrator` Profiles

*   **Pros**: Avoids adding a 4th profile directory in `~/.hermes/profiles/`.
*   **Cons**: Mixes PR code-review history or orchestrator planning history with triage audits in the same `state.db`; `zf-reviewer` system prompt is biased toward git diffs rather than system architecture; `zf-orchestrator` has write permissions that risk self-mutation.
*   **Reason for Rejection**: `Rejected by author: Zero Factory already maintains a built-in profile synchronization and bootstrap mechanism (`hermes zerofactory setup` / `sync-profiles`), making a dedicated `zf-goldfish` profile straightforward to support while delivering complete context isolation and read-only safety.`

### Alternative C: In-Band Sequential Self-Critique (Same Session)

*   **Pros**: Zero new profiles, zero handoffs, lowest implementation complexity.
*   **Cons**: Suffers from conversational confirmation bias and sycophancy; the LLM defends its own decisions rather than evaluating the draft objectively.
*   **Reason for Rejection**: `Rejected by author: Violates the core invariant of the Elephant-Goldfish Model. An LLM reviewing its own draft in the same session context fails to detect its own implicit assumptions.`

### Alternative D: Grill-Me Protocol Alone without EGM

*   **Pros**: Directly resolves ambiguous user intent and human preferences via interactive multiple-choice buttons.
*   **Cons**: Lacks adversarial technical stress-testing; an agreed-upon human plan can still contain severe YAGNI bloat, missing failure modes, or untestable acceptance criteria that cause `zf-builder` rework loops.
*   **Reason for Rejection**: `Rejected by author: Grill-Me handles requirements discovery, but does not verify technical feasibility or eliminate speculative bloat. Both are needed in a hybrid sequence.`

### Alternative E: Autonomous Ingestion & Unfiltered EGM Trigger on GitHub Features

*   **Pros**: Fully autonomous; no human intervention needed to start drafting features filed on GitHub.
*   **Cons**: Vulnerable to issue flooding and denial-of-service; duplicate or spam feature requests filed on public repos will queue up hours of 27B model inference on the DGX node.
*   **Reason for Rejection**: `Rejected by author: Option A (Parked Ingestion) is required to ensure that external issues land with assignee = 'human' consuming zero automated GPU compute until explicitly vetted by an operator.`

--------------------------------------------------------------------------------

## Detailed Implementation Plan

All changes are organized into a single sequential implementation plan across 6 core components:

### 1. Profile Bootstrap & Prompt Definition

*   **`profiles/zf-goldfish/system_prompt.txt`** (Create):
    *   *Rationale*: Define the specialized contrarian system prompt for `zf-goldfish`. Enforces the Ponytail 7-Rung Ladder of Laziness, mandates checking for stdlib/existing repo utilities before new abstractions, audits acceptance criteria testability, and instructs the agent to write its audit to task comments via `hermes zerofactory comment <task_id>` before cleanly exiting.
*   **`__init__.py`** (Modify):
    *   *Rationale*: Register `zf-goldfish` in `setup_profiles()` so that `hermes zerofactory setup` provisions `~/.hermes/profiles/zf-goldfish/` with default config, state database, and prompt template.
*   **`setup.py` / `scripts/sync_profiles.py`** (Modify):
    *   *Rationale*: Ensure `hermes zerofactory sync-profiles` updates `zf-goldfish` prompt templates from the repository source.

### 2. Dispatcher Scheduling & Claim Logic

*   **`dispatcher/scheduler.py`** (Modify):
    *   *Rationale*: Update the atomic task claim SQL query (lines 171, 332) from:
        `WHERE status = 'todo' OR (status = 'triage' AND assignee = 'zf-orchestrator')`
        to:
        `WHERE status = 'todo' OR (status = 'triage' AND assignee IN ('zf-orchestrator', 'zf-goldfish'))`.
    *   *Rationale*: Ensure that when a task enters `status = 'triage'` with `assignee = 'zf-goldfish'`, the scheduler claims it, increments `running_tasks`, and dispatches it under the global concurrency cap.

### 3. Reaper Lifecycle & Phase Transitions

*   **`dispatcher/reaper.py`** (Modify):
    *   *Rationale*: In `audit_and_reap_processes()` (lines 180–215), intercept successful worker exits (exit code 0):
        *   If `curr_asgn == 'zf-orchestrator'` and `metadata.get("triage_phase") == "elephant_drafting"`:
            *   Transition `metadata["triage_phase"] = "goldfish_auditing"`.
            *   Update task: `UPDATE tasks SET status = 'triage', assignee = 'zf-goldfish', metadata = ? WHERE id = ?`.
            *   Append activity log: `"Elephant specification complete; queued for Goldfish YAGNI audit"`.
        *   If `curr_asgn == 'zf-goldfish'` and `metadata.get("triage_phase") == "goldfish_auditing"`:
            *   Transition `metadata["triage_phase"] = "human_approval"`.
            *   Set `metadata["awaiting_approval"] = True`.
            *   Update task: `UPDATE tasks SET status = 'triage', assignee = 'human', metadata = ? WHERE id = ?`.
            *   Append activity log: `"Goldfish audit complete; parked in Triage for human approval"`.
    *   *Rationale*: Ensure worker failure retries (`worker_failure_retries <= 3`) apply to `zf-goldfish`, moving to `blocked` if the audit worker times out or crashes repeatedly.

### 4. Spawner Prompt Assembly

*   **`dispatcher/worker_spawner.py`** (Modify):
    *   *Rationale*: Add `build_goldfish_audit_prompt(task_id, title, description, workdir, board_slug)`:
        *   Extracts the draft specification directly from `tasks.description`.
        *   Injects `board.architecture` notes and `openwiki/` links for contract boundary verification.
        *   Injects the Ponytail Anti-Overengineering audit rubric.
        *   Instructs `zf-goldfish` to format its critique with severity badges (`🔴 Blocker`, `🟡 Major`, `🟢 Nit`) and post via `hermes zerofactory comment <task_id>`.
    *   *Rationale*: In `spawn_worker_subprocess()`, launch `zf-goldfish` without an isolated Git worktree (running directly in board root or inspect-only directory with read-only environment variables).

### 5. Issue Ingestion Flooding Guardrail (Option A)

*   **`scripts/zf_queue_watchdog.py`** (Modify):
    *   *Rationale*: Update the periodic GitHub issue import loop (lines 116–122) so that issues imported by the watchdog are assigned to `human`:
        ```python
        res = import_external_issue(
            issue=iss,
            board_slug=slug,
            status="triage",
            assignee="human",  # Option A: Parked Ingestion
            actor="zf-watchdog",
        )
        ```
    *   *Rationale*: Prevent untrusted or spam GitHub feature requests from autonomously spawning Elephant/Goldfish model runs on the DGX Spark node.
*   **`issues/importer.py`** (Modify):
    *   *Rationale*: Ensure `import_external_issue` preserves `assignee = 'human'` when explicitly supplied during triage import, setting `metadata["external_unverified"] = True`.

### 6. CLI Commands & Operator Ergonomics

*   **`__init__.py`** (Modify):
    *   *Rationale*: Register the `approve` and `reject` subcommands under `hermes zerofactory`:
        *   `hermes zerofactory approve <task_id> [--split]`: Validates that `triage_phase == 'human_approval'`, clears `awaiting_approval`, and promotes single-repo tasks to `status = 'todo', assignee = 'zf-builder'` (or decomposes multi-repo tasks via `split_task()`).
        *   `hermes zerofactory reject <task_id> --feedback "<feedback>"`: Posts the human feedback to task comments, increments `revision_count`, and resets `assignee = 'zf-orchestrator', metadata['triage_phase'] = 'elephant_drafting'`.

### 7. Dashboard & Web UI Integration

*   **`dashboard/models.py` & `dashboard/routes/tasks.py`** (Modify):
    *   *Rationale*: Expose `triage_phase`, `awaiting_approval`, and `audit_verdict` in task serializations.
*   **`dashboard/src/views/KanbanBoard.jsx`** (Modify):
    *   *Rationale*: Render an amber badge `📋 Spec & Audit Ready` on Kanban cards when `triage_phase == 'human_approval'`.
*   **`dashboard/src/components/TaskDetailModal.jsx`** (Modify):
    *   *Rationale*: Render side-by-side tabs in the task modal for `Proposed Specification` (from `description`) and `Goldfish Audit Report` (from comments), with `[Approve]` and `[Request Revision]` buttons.

### 8. Verification & Unit Testing Suite

*   **`tests/unit/dispatcher/test_egm_triage.py`** (Create):
    *   *Rationale*: Add automated unit tests covering the end-to-end state transitions:
        1. `test_claim_elephant_drafting`: Scheduler claims new triage task for `zf-orchestrator`.
        2. `test_reaper_transitions_to_goldfish`: Reaper detects orchestrator exit 0, updates phase to `goldfish_auditing`, sets assignee to `zf-goldfish`.
        3. `test_claim_goldfish_auditing`: Scheduler claims `zf-goldfish` task and verifies prompt contains draft spec and zero chat history.
        4. `test_reaper_transitions_to_human_approval`: Reaper detects goldfish exit 0, updates phase to `human_approval`, assigns to `human`.
        5. `test_approve_promotes_to_todo`: CLI `approve` command promotes single-repo task to `todo`.
        6. `test_approve_splits_multi_repo`: CLI `approve --split` decomposes multi-repo task into linked `todo` tasks.
        7. `test_parked_github_ingestion`: Verifies watchdog imports issues with `assignee = 'human'` and scheduler skips them.

