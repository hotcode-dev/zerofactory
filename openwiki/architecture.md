---
type: architecture
title: Zero Factory Architecture
description: High-level map of the Zero Factory Hermes plugin — subsystem contracts, the centralized 13-stage task state machine, the dispatcher control loop, durable SQLite persistence, and the stateless-worker / stateful-substrate handoff model.
tags: [architecture, system-design, kanban, dispatcher, state-machine, persistence, hermes-plugin]
verified:
  - by: openwiki/0.6.0
    at: 2026-11-20T15:20:57.003Z
sources:
  - id: openwiki-source-4942bcbe129130ccad2b7e2a
    resource: repo://__init__.py
  - id: openwiki-source-9ab161c6e9774cf771b19ced
    resource: repo://.zerofactory/precommit.sh
  - id: openwiki-source-594f18a4ed0f4f061e35fdc9
    resource: repo://dashboard/db.py
  - id: openwiki-source-4de239baa4d579276db7cf80
    resource: repo://dashboard/memory_service.py
  - id: openwiki-source-52ae51442f849fdbd57863a3
    resource: repo://dashboard/models.py
  - id: openwiki-source-4d0299655ec14b97f5aaa9a7
    resource: repo://dashboard/routes/cron.py
  - id: openwiki-source-c705147b9966f3d6f300034a
    resource: repo://dashboard/routes/tasks.py
  - id: openwiki-source-e9d50a52581348b013457083
    resource: repo://dispatcher/context_builder.py
  - id: openwiki-source-e7a6784a6e1f7f421dd572ed
    resource: repo://dispatcher/reaper.py
  - id: openwiki-source-9f9b3c9d5afeac588f3cdae1
    resource: repo://dispatcher/scheduler.py
  - id: openwiki-source-0445f3be32f0f8efe9dfeca4
    resource: repo://dispatcher/slop_gate.py
  - id: openwiki-source-1cbc0eb99c8b57cd43185064
    resource: repo://dispatcher/state_machine.py
  - id: openwiki-source-b73a2eae57b810a3ad15196e
    resource: repo://dispatcher/worker_spawner.py
  - id: openwiki-source-992af5f6e480f39b3a3a184e
    resource: repo://issues/importer.py
  - id: openwiki-source-73f3b62839035304ececba97
    resource: repo://migrations/0001_initial_schema.sql
  - id: openwiki-source-2feae2067f9a49cc4d8f2150
    resource: repo://migrations/runner.py
  - id: openwiki-source-0d153fd68e7210eb5d3be49d
    resource: repo://paths.py
  - id: openwiki-source-81127d20a2ccc07b7626fc4e
    resource: repo://plugin.yaml
  - id: openwiki-source-57b14ecc6ef51ae6212b15f0
    resource: repo://settings.py
generated: { by: "hermes", at: "2026-11-20T15:20:57.003Z" }
---

# Zero Factory Architecture

Zero Factory is a self-contained **Hermes Agent plugin** (see `repo://plugin.yaml#L1-L8`)
that runs a 24/7 multi-agent software factory. Four specialist agent profiles
— `zf-orchestrator`, `zf-goldfish`, `zf-builder`, `zf-reviewer` — operate on
a durable Kanban board; a dispatcher provisions isolated Git worktrees,
spawns the right specialist, enforces a deterministic precommit gate, opens
GitHub PRs, and routes work through review rounds until a human merges (or
an optional auto-merge — board-level or task-level `automerge` tag — does
it). Triage work for complex or multi-repo goals flows through a sequential
Elephant-Goldfish Model (EGM) pipeline: `zf-orchestrator` drafts the
specification, `zf-goldfish` audits it in a zero-context session, and a human
operator releases it (see
[Dashboard & Automation](/openwiki/components/dashboard-cron.md) and
[Dispatch Engine](/openwiki/components/dispatcher.md)).

The architecture deliberately follows **stateless workers, stateful substrate**:
durable state lives in Git worktrees, GitHub PR comments, the Kanban
SQLite database, and a Mem0 vector-memory substrate — not in any agent's
conversation memory. Each handoff spawns a brand-new agent session, keeping
context windows small and preventing "ghost-code" hallucination across
review rounds.

## Subsystem map

| Subsystem | Responsibility | Entry |
|---|---|---|
| Plugin shell / CLI | Registers CLI, profiles, hooks with Hermes | `repo://__init__.py` |
| State machine | Canonical task stages, status transitions, assignee resolution | `repo://dispatcher/state_machine.py` |
| Dispatcher | Task claiming, worktrees, worker spawn, precommit, PRs | `repo://dispatcher/scheduler.py` |
| Built-in cron + scripts | Periodic automation (task queue check, daily stats, per-board improvement scanner, OpenWiki sync) plus No-Agent Mode wake-gate scripts | `repo://dashboard/routes/cron.py` |
| Dashboard | FastAPI REST + services (db, models, setup services, Mem0 memory) | `repo://dashboard/plugin_api.py` |
| Issues import | GitHub issue → Kanban task ingestion (dedup, priority, board resolution), plus dashboard sync/import endpoints and deterministic setup flows | `repo://issues/importer.py` |
| Profile management | Auto-provisioning of `zf-*` profiles | `repo://profile_manager.py` |
| Mem0 memory | Semantic vector memory (Mem0 + embedded Qdrant, dual embedder) with dual-write to the `board_memories` SQLite table | `repo://dashboard/memory_service.py` |
| Anti-slop gate | Zero-token deterministic diff hygiene checks (debugger residue, placeholder comments, skipped tests, diff-budget cap) that gate packaging before commit/PR | `repo://dispatcher/slop_gate.py` |

External issue ingestion flows through the `issues/` package (GitHub-only):
`hermes zerofactory import-gh-issue` fetches a GitHub issue, normalizes it
into an `ExternalIssue` (labels drive deterministic priority and category
inference), and `import_external_issue` resolves the target board, derives a
deterministic task id and an `issue:`-prefixed dedup key, and creates the
Kanban task (`repo://issues/importer.py#L112-L229`). `import-gh-issue --sync`
bulk-imports all open issues flagged with the AI request label, and
`hermes zerofactory setup-gh-issues` provisions tracker integration for a
board. The dashboard also exposes REST endpoints that drive the same
synchronization and import flows. The stored `external_issue` metadata is
later read back by the dispatcher so the PR it opens for the task
links the source issue (`Fixes #42`). See
[External Issue Import](/openwiki/components/issues-importer.md).

## The 13-stage state machine

The Kanban UI shows four actor columns — Human, Todo, Running, Done
(`repo://dashboard/src/constants.js#L7-L12`) — but each card carries a
finer-grained **13-stage** classification (`triage`, `interview`,
`spec_approval`, `awaiting_merge`, `blocked`, `grill`, `spec_draft`,
`spec_audit`, `building`, `review`, `recovery`, `packaging`, `done`; the
five Human-column stages are `HUMAN_STAGES`) that maps to the five storage
statuses (`triage`, `todo`, `running`, `blocked`, `done`)
(`repo://paths.py#L117-L134`).

`resolve_status_assignee` deterministically derives the canonical assignee
for a target status (e.g. `blocked` goes to `zf-builder` only when
`blocked_reason_type = "changes-requested"`, otherwise `human`; `todo` is
restricted to `zf-builder` / `zf-reviewer` / `zf-goldfish`), and
`derive_task_stage` computes the stage from status + assignee +
`pr_url` + metadata (`repo://paths.py#L137-L278`).

Every status change funnels through **one** primitive: `transition_task`
(`repo://dispatcher/state_machine.py#L30-L286`). It (1) validates the
transition against the `VALID_TRANSITIONS` graph — notably `done` only
transitions back to `triage` (rework), and non-human agents are rejected
from any edge outside the graph (`InvalidStateTransitionError`) — and
(2) runs a two-phase commit: **Phase 1** tears down OS resources *outside*
the DB transaction (terminate the old worker when exiting `running` or
switching workers; clear process artifacts otherwise), and **Phase 2**
atomically updates status, assignee, `worker_pid`, `started_at`,
`blocked_reason`, and metadata (clearing failure counters, `awaiting_pr`,
`triage_phase`, etc. as the target state requires), then logs a
`task_activity` row. Human actors additionally clear stale failure/blocked
metadata. This makes the reaper, scheduler, and dashboard `move_task`
agree on every transition's side effects.

## Control / data flow

The core loop is `run_dispatch_cycle`, which acquires a process-level exclusive
file lock before mutating state so concurrent cycles are serialized
(`repo://dispatcher/scheduler.py#L40-L80`). Each cycle unblocks due tasks
(promoting them to `todo`), claims `todo` tasks under the board and global
concurrency caps, provisions an isolated Git worktree per task, spawns the
assigned specialist's Hermes worker, and — when the worker finishes — keeps the
task in `running` with `awaiting_pr` set so the deterministic packaging phase
(precommit → commit → push → PR → reviewer) can package it; only after a
terminal close (merge, auto-merge, human close, or PR archive) does the task
leave the packaging phase. A background reaper audits and cleans up hung
workers.

Worker spawning is deliberately isolated: `spawn_agent_worker` launches
`hermes -p <assignee> ... --cli chat -q <prompt>` as a detached
subprocess with the worker's `HERMES_HOME` pinned to the profile's home
directory (`--yolo --accept-hooks` are appended only when the
`allow_unattended_approvals` setting is enabled), then correlates the new
`session_id` against the profile's `state.db`
(`repo://dispatcher/worker_spawner.py#L751-L790`). The prompt is pre-digested in Python before the agent wakes —
`digest_reviewer_git_context` pre-computes the git log, diffstat, and a bounded
diff so the reviewer does not burn turns on exploratory `git` calls
(`repo://dispatcher/context_builder.py#L16`), and
`digest_board_memories_context` retrieves the most relevant Mem0/board-memory
entries into the same prompt so agents do not repeat past mistakes
(`repo://dispatcher/context_builder.py#L224`).

## Self-healing & autonomous recovery

Worker-failure handling is retry-oriented: a crashed or vanished worker
increments `worker_failure_retries` and routes back to `todo` for re-spawn up
to the retry budget. When the budget is exhausted and the task's assignee is
not `zf-orchestrator`, the reaper routes it to `todo` with
`triage_phase = "recovery"` for **one** autonomous diagnostic attempt by
`zf-orchestrator` (gated on `orchestrator_recovery_count < 1`); a second
exhaustion — or any exhaustion of the orchestrator itself — parks the task in
`blocked` with `blocked_reason_type = "stuck"` and `permanently_blocked` for
a human (`repo://dispatcher/reaper.py#L359-L560`). A clean `zf-reviewer`
exit that recorded no verdict (no `block --reason approved|changes-requested|
human-gate`) is not retried: the reaper parks the task in `blocked` with
`blocked_reason_type = "human-gate"` and the reason *"Reviewer exited without
recording a verdict; awaiting human review"*, deliberately clearing `awaiting_pr`
so the task never re-enters the packaging phase
(`repo://dispatcher/reaper.py#L284-L294`). The orchestrator then acts
via `hermes zerofactory recover <task_id> [--guidance ...]` (back to
`zf-builder`), `report-bug` (internal defect → GitHub issue + `blocked`), or
`block` (human gate) — all surfaced through the dashboard's `recover` /
`report-bug` endpoints
(`repo://dashboard/routes/tasks.py#L1678`, `repo://dashboard/routes/tasks.py#L1791`).

## Durable persistence (the substrate)

All durable state is an embedded SQLite database in **WAL mode** (set during
`init_db`) with `foreign_keys=ON` enabled on every connection
(`repo://dashboard/db.py#L122-L141`, WAL at `repo://dashboard/db.py#L221`):
the main `get_db_conn` connection uses a 15s `busy_timeout` and a 30s
connect timeout. The schema is created by numbered migrations tracked in
`schema_migrations` (`repo://migrations/runner.py`); a single migration,
`0001_initial_schema.sql`, currently defines the whole schema.

The core schema defines:

- **`boards`** — one row per project board (the explicit user-defined slug)
  with an `automerge` flag (`repo://migrations/0001_initial_schema.sql#L4-L13`)
  and per-board settings. Boards no longer carry a single repository `git_url`:
  repositories are first-class peers linked one-to-many via
  `board_repositories` (`repo://migrations/0001_initial_schema.sql#L15-L26`).
- **`board_repositories`** — the multi-repository linkage: `board_slug`,
  `repo_alias`, `git_url`, `target_branch`, and
  `additional_reviewer_usernames` per repo (`#L15-L26`). Each task targets one
  `repo_alias`; sibling repositories on the same board check out side-by-side
  in the workspace.
- **`tasks`** — the Kanban cards: status, assignee, priority, `repo_alias`,
  workspace path/kind, branch, `pr_url`, and a `metadata` JSON column, keyed by
  `id` and scoped by `board_slug` (`#L28-L51`).
- **`task_links`** — parent/child dependency edges that gate promotion
  (`#L53-L61`).
- **`task_comments` / `task_activity`** — the durable handoff trail and audit
  log (`#L63-L80`).
- **`settings`** — key/value global configuration (`#L82-L86`), including
  Mem0 keys (`mem0_enabled`, `mem0_embedder_provider`,
  `mem0_embedder_model`, `mem0_base_url`/`api_key`/`model`),
  `auto_create_github_issues`, `allow_unattended_approvals`, and
  `auto_start_dispatcher` (`repo://settings.py#L92-L137`).
- **`board_memories`** — the per-board repository-knowledge substrate (category,
  content, tags, author) that the dispatcher pre-digests into every spawned
  worker's prompt so agents never repeat past mistakes (`#L88-L100`); it is the
  SQLite half of a dual-write pair with Mem0 vector storage.

Because the database and worktrees are the source of truth, any worker can be
killed and re-spawned without losing progress — the substrate survives the
session.

### Mem0 vector memory

On top of SQLite, `dashboard/memory_service.py` embeds a Mem0 client backed by
an embedded Qdrant collection, with a dual embedder option: `fastembed`
(100% local ONNX CPU, default) or `openai`/compatible (cloud, separate
collection to avoid dimension mismatches)
(`repo://dashboard/memory_service.py#L133`). Memory writes are dual:
into Qdrant for semantic cosine-similarity retrieval (`user_id` = board slug)
and into `board_memories` for CLI/UI/deterministic access. Relevant memories
are pre-digested by the dispatcher into `zf-builder` and `zf-reviewer`
prompts, and automated background extraction records lessons on task
completion / PR merge.

## Task status taxonomy & the packaging phase

The task status is strictly **`triage`, `todo`, `running`, `blocked`,
`done`** — the legacy `ready` column was retired (its migration, which folded
stranded `ready` rows into `todo`, was itself removed as dead code
(`repo://migrations/0001_initial_schema.sql#L28-L51`,
`repo://dashboard/models.py#L23`)). Status changes have exactly one code path:
`move_task` on the dashboard (`repo://dashboard/routes/tasks.py#L845`),
reached by `POST /tasks/{id}/move` and `hermes zerofactory move`; `PATCH
/tasks/{id}` refuses a status change with a 400 pointing the caller back to the
move endpoint. `move_task` (and every other transition) applies through the
`transition_task` state-machine primitive described above.

`done` is **strictly terminal**: the moment an agent actor (builder/reviewer)
reports completion the task deliberately stays `running` and is marked
`metadata["awaiting_pr"] = true` — the *packaging phase* — during which the
dispatcher runs the deterministic pipeline (precommit → anti-slop gate →
commit → push → PR → route to reviewer) via `_package_and_open_pr`
(`repo://dispatcher/scheduler.py#L1772`). After the precommit check, a
zero-token deterministic **anti-slop gate** (`run_deterministic_slop_gate` in
`repo://dispatcher/slop_gate.py#L467`, wired in at
`repo://dispatcher/scheduler.py#L1920`) blocks leftover debuggers,
placeholder `TODO`/`FIXME` comments, and skipped tests, plus an optional
`ZEROFACTORY_MAX_DIFF_LINES` budget; a failure routes back through
`_handle_precommit_failure`, and its `build_diff_hygiene_scorecard`
(`repo://dispatcher/slop_gate.py#L505`) is pre-digested into the `zf-reviewer`
prompt. Only a terminal event (a human closing the task, a merged PR, an
auto-merge, or a PR archive via `close_pr`) clears the flag and finalizes the
task through `_finalize_terminal_done`, which never commits, pushes, or
re-opens review (`repo://dispatcher/scheduler.py#L2370`). Blocked tasks carry a
canonical `metadata["blocked_reason_type"]` classified by
`normalize_blocked_reason_type` into `changes-requested`, `approved`,
`human-gate`, or `stuck` (stamped by the dispatcher when a retry budget is
exhausted; any other free-text reason falls through to
`human-gate`), so downstream routing is deterministic instead of
prose-matching (`repo://paths.py#L93-L112`). The packaging phase itself now
carries its own retry budget: repeated git/PR failures during
`_package_and_open_pr` increment `metadata["packaging_retries"]` and store
`metadata["last_packaging_error"]`; after 3 attempts the task is parked in
`blocked` with `blocked_reason_type = "stuck"` and assignee `human`
(`repo://dispatcher/scheduler.py#L1721`), and the `recover` endpoint
resets both fields alongside the other failure counters
(`repo://dashboard/routes/tasks.py#L1678`).

## Sequential EGM triage pipeline

Complex triage work runs through a sequential Elephant-Goldfish Model (EGM)
pipeline with a strict 1-worker cap so it never starves implementation
tasks: the claim query counts running `zf-orchestrator` / `zf-goldfish`
tasks and refuses to claim another EGM task while one is in flight
(`repo://dispatcher/scheduler.py#L161-L168`), and stamps `triage_phase` as
the claim lands — `elephant_drafting` for `zf-orchestrator` (setting
`egm = true` when the task is multi-repo, `category == "epic"`, or already
flagged) and `goldfish_auditing` for `zf-goldfish`
(`repo://dispatcher/scheduler.py#L361-L385`). Phase transitions are
deterministic reaper side effects, not agent decisions: when the
`zf-orchestrator` drafting worker exits cleanly the reaper promotes the task
to `todo` assigned to `zf-goldfish` with `triage_phase = "goldfish_auditing"`,
and when the `zf-goldfish` audit worker exits it parks the task back in
`triage` assigned to `human` with `triage_phase = "human_approval"` and
`awaiting_approval = true`
(`repo://dispatcher/reaper.py#L215-L260`). Each phase runs in a brand-new
zero-context session (the goldfish audit prompt carries no drafting
conversation).

The release gate is human-only. `POST /tasks/{id}/approve` (or `hermes
zerofactory approve <task_id> [--split]`) promotes a single-repo task to
`todo` or splits a multi-repo one into linked `todo` children
(`repo://dashboard/routes/tasks.py#L2114`); `POST /tasks/{id}/reject`
(or `hermes zerofactory reject <task_id> --feedback "..."`) bumps
`revision_count` and routes the spec back to `zf-orchestrator` in
`elephant_drafting` — at most 2 revision rounds, after which the task is
blocked for a human with `blocked_reason_type = "human-gate"`
(`repo://dashboard/routes/tasks.py#L2189`); rejecting also auto-records the
human's feedback as a `rejected_path` board memory so future runs avoid the
same mistake (`repo://dashboard/routes/tasks.py#L2225`). The full protocol is
documented in `repo://docs/sequential_egm_triage.md`.

## Session-per-handoff model

On each handoff (implementation → review → changes-requested) the dispatcher
terminates the previous worker, then launches a **new** session for the next
profile. The reviewer receives a clean, pre-digested current delta rather than
the full implementation history; the builder, when asked for changes, gets a
fresh session with the PR comments injected. This keeps token cost flat across
review rounds and makes bad debugging loops self-terminating.

## Design philosophy

The whole system is built around the **Ponytail "Ladder of Laziness"**
anti-overengineering doctrine: prefer the standard library, keep diffs surgical,
eliminate dead code, and cap speculative bloat. The same discipline is
enforced structurally — a deterministic precommit pipeline
(`.zerofactory/precommit.sh`: format → build → test) stands between a worker's
output and a real PR, so a broken build or lint error never reaches a human.

See [Dispatch Engine](/openwiki/components/dispatcher.md) for the dispatch loop
in depth, [Dashboard & Automation](/openwiki/components/dashboard-cron.md)
for the operator/automation layer, [Conventions](/openwiki/conventions.md) for
the coding rules agents must follow, and [Quickstart](/openwiki/quickstart.md)
to run the factory.
