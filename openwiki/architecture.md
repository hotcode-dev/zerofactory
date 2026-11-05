---
type: architecture
title: Zero Factory Architecture
description: High-level map of the Zero Factory Hermes plugin — subsystem contracts, the dispatcher control loop, durable SQLite persistence, and the stateless-worker / stateful-substrate handoff model.
tags: [architecture, system-design, kanban, dispatcher, persistence, hermes-plugin]
verified:
  - by: openwiki/0.6.0
    at: 2026-11-04T14:49:39.483Z
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
  - id: openwiki-source-c705147b9966f3d6f300034a
    resource: repo://dashboard/routes/tasks.py
  - id: openwiki-source-e9d50a52581348b013457083
    resource: repo://dispatcher/context_builder.py
  - id: openwiki-source-9f9b3c9d5afeac588f3cdae1
    resource: repo://dispatcher/scheduler.py
  - id: openwiki-source-b73a2eae57b810a3ad15196e
    resource: repo://dispatcher/worker_spawner.py
  - id: openwiki-source-992af5f6e480f39b3a3a184e
    resource: repo://issues/importer.py
  - id: openwiki-source-73f3b62839035304ececba97
    resource: repo://migrations/0001_initial_schema.sql
  - id: openwiki-source-07cdf730b6e61ce01bddb2e2
    resource: repo://migrations/0002_add_automerge.sql
  - id: openwiki-source-2feae2067f9a49cc4d8f2150
    resource: repo://migrations/runner.py
  - id: openwiki-source-0d153fd68e7210eb5d3be49d
    resource: repo://paths.py
  - id: openwiki-source-81127d20a2ccc07b7626fc4e
    resource: repo://plugin.yaml
  - id: openwiki-source-20bc44fdf115b28983477777
    resource: repo://scripts/zf_openwiki_gate.py
  - id: openwiki-source-57b14ecc6ef51ae6212b15f0
    resource: repo://settings.py
generated: { by: "hermes", at: "2026-11-04T14:49:39.483Z" }
---

# Zero Factory Architecture

Zero Factory is a self-contained **Hermes Agent plugin** (see `repo://plugin.yaml#L1-L8`)
that runs a 24/7 multi-agent software factory. Three specialist agent profiles
— `zf-orchestrator`, `zf-builder`, `zf-reviewer` — operate on a durable Kanban
board; a dispatcher provisions isolated Git worktrees, spawns the right
specialist, enforces a deterministic precommit gate, opens GitHub PRs, and
routes work through review rounds until a human merges (or an optional
board-level auto-merge does it).

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
| Dispatcher | Task claiming, worktrees, worker spawn, precommit, PRs | `repo://dispatcher/scheduler.py` |
| Cron + scripts | 0-token background automation (watchdog, scanner gate, stats, openwiki gate) | `repo://cron/definitions.py` |
| Dashboard | FastAPI REST + services (db, models, setup services, Mem0 memory) | `repo://dashboard/plugin_api.py` |
| Issues import | GitHub/Jira issue → Kanban task ingestion (dedup, priority, board resolution), plus dashboard sync/import endpoints and deterministic setup flows | `repo://issues/importer.py` |
| Profile management | Auto-provisioning of `zf-*` profiles | `repo://profile_manager.py` |
| Mem0 memory | Semantic vector memory (Mem0 + embedded Qdrant, dual embedder) with dual-write to the `board_memories` SQLite table | `repo://dashboard/memory_service.py` |

External issue ingestion flows through the `issues/` package:
`hermes zerofactory import-gh-issue` and `hermes zerofactory
import-jira-issue` fetch a GitHub or Jira issue, normalize it into an
`ExternalIssue` (labels drive deterministic priority and category inference),
and `import_external_issue` resolves the target board, derives a deterministic
task id and an `issue:`-prefixed dedup key, and creates the Kanban task
(`repo://issues/importer.py#L31-L220`). `import-gh-issue --sync` bulk-imports
all open issues flagged with the AI request label, and
`hermes zerofactory setup-gh-issues` / `setup-jira` provision tracker
integration for a board. The dashboard also exposes REST endpoints that drive
the same synchronization and import flows. The stored `external_issue`
metadata is later read back by the dispatcher so the PR it opens for the task
links the source issue (`Fixes #42` / `Resolves: PROJ-123`). See
[External Issue Import](/openwiki/components/issues-importer.md).

The CLI surface also carries a `hermes zerofactory update` command (edit a
task's title, description, assignee, or priority in one call; a `--status` on
`update` routes through the `move_task` code path so lifecycle side effects —
worker stop, flag cleanup, dispatch trigger — always apply, the same rule
enforced server-side by `PATCH /tasks/{id}` refusing status changes) plus an
`--assignee` option on `move`, letting handoffs reassign ownership while
transitioning columns (`repo://__init__.py#L1084-L1105`,
`repo://dashboard/routes/tasks.py#L655-L665`). Triage work gained
`hermes zerofactory split <task_id> --repos r1,r2` (decompose a multi-repo
triage task into per-repo `todo` tasks), `hermes zerofactory recover
<task_id> [--guidance ...]` (route a failure-exhausted blocked task back to
the orchestrator with operator guidance), and `hermes zerofactory
report-bug --task <task_id> --title ...` (report an internal Zero Factory
defect to the upstream GitHub issue tracker, optionally auto-creating the
issue when the `auto_create_github_issues` setting is enabled)
(`repo://__init__.py#L573-L694`). `create` accepts an optional
`--tags` flag (comma-separated, e.g. `automerge,hitl`) that writes task tags
into the `tags` column; these tags drive the auto-merge precedence check in
the PR-poll path (the `automerge` opt-in vs `hitl`/`manual-review` opt-out
tags described in [Dispatch Engine](/openwiki/components/dispatcher.md)), and
the automated OpenWiki doc-sync + setup flows stamp `automerge` on the tasks
they file so they can auto-merge after review
(`repo://__init__.py#L332-L336`, `#L907-L927`).

## Control / data flow

The core loop is `run_dispatch_cycle`, which acquires a process-level exclusive
file lock before mutating state so concurrent cycles are serialized
(`repo://dispatcher/scheduler.py#L38-L76`). Each cycle unblocks due tasks
(promoting them to `todo`), claims `todo` tasks under the board and global
concurrency caps, provisions an isolated Git worktree per task, spawns the
assigned specialist's Hermes worker, and — when the worker finishes — keeps the
task in `running` with `awaiting_pr` set so the deterministic packaging phase
(precommit → commit → push → PR → reviewer) can package it; only after a
terminal close (merge, auto-merge, human close, or PR archive) does the task
leave the packaging phase. A background reaper audits and cleans up hung
workers.

Worker spawning is deliberately isolated: `spawn_agent_worker` launches
`hermes -p <assignee> ... --yolo --accept-hooks chat -q <prompt>` as a detached
subprocess with the worker's `HERMES_HOME` pinned to the profile's home
directory, then correlates the new `session_id` against the profile's
`state.db` (`repo://dispatcher/worker_spawner.py#L69-L72`,
`#L550-L618`). The prompt is pre-digested in Python before the agent wakes —
`digest_reviewer_git_context` pre-computes the git log, diffstat, and a bounded
diff so the reviewer does not burn turns on exploratory `git` calls
(`repo://dispatcher/context_builder.py#L16-L88`), and
`digest_board_memories_context` retrieves the most relevant Mem0/board-memory
entries into the same prompt so agents do not repeat past mistakes
(`repo://dispatcher/context_builder.py#L210`).

## Durable persistence (the substrate)

All durable state is an embedded SQLite database in **WAL mode** with
foreign keys and a busy timeout enabled on every connection
(`repo://dashboard/db.py#L158-L159`, `#L232`). The schema is created by
numbered migrations tracked in `schema_migrations`
(`repo://migrations/runner.py#L26-L40`).

The core schema (`repo://migrations/0001_initial_schema.sql`) defines:

- **`boards`** — one row per project board (the explicit user-defined slug)
  with an optional `jira_url` link to a Jira Cloud instance, an `automerge`
  flag added by migration 0002 (`repo://migrations/0002_add_automerge.sql`),
  and per-board settings. Boards no longer carry a single repository `git_url`:
  repositories are first-class peers linked one-to-many via
  `board_repositories` (`repo://migrations/0001_initial_schema.sql#L15-L27`).
- **`board_repositories`** — the multi-repository linkage: `board_slug`,
  `repo_alias`, `git_url`, `target_branch`, and
  `additional_reviewer_usernames` per repo (`#L15-L27`). Each task targets one
  `repo_alias`; sibling repositories on the same board check out side-by-side
  in the workspace.
- **`tasks`** — the Kanban cards: status, assignee, priority, `repo_alias`,
  workspace path/kind, branch, `pr_url`, and a `metadata` JSON column, keyed by
  `id` and scoped by `board_slug` (`#L28-L50`).
- **`task_links`** — parent/child dependency edges that gate promotion
  (`#L52-L61`).
- **`task_comments` / `task_activity`** — the durable handoff trail and audit
  log (`#L63-L83`).
- **`settings`** — key/value global configuration (`#L85-L88`), including
  Mem0 keys (`mem0_enabled`, `mem0_embedder_provider`,
  `mem0_embedder_model`, `mem0_base_url`/`api_key`/`model`) and
  `auto_create_github_issues` (`repo://settings.py#L108-L156`).
- **`board_memories`** — the per-board repository-knowledge substrate (category,
  content, tags, author) that the dispatcher pre-digests into every spawned
  worker's prompt so agents never repeat past mistakes (`#L85-L96`); it is the
  SQLite half of a dual-write pair with Mem0 vector storage.

Because the database and worktrees are the source of truth, any worker can be
killed and re-spawned without losing progress — the substrate survives the
session.

### Mem0 vector memory

On top of SQLite, `dashboard/memory_service.py` embeds a Mem0 client backed by
an embedded Qdrant collection, with a dual embedder option: `fastembed`
(100% local ONNX CPU, default) or `openai`/compatible (cloud, separate
collection to avoid dimension mismatches)
(`repo://dashboard/memory_service.py#L107-L188`). Memory writes are dual:
into Qdrant for semantic cosine-similarity retrieval (`user_id` = board slug)
and into `board_memories` for CLI/UI/deterministic access. Relevant memories
are pre-digested by the dispatcher into `zf-builder` and `zf-reviewer`
prompts, and automated background extraction records lessons on task
completion / PR merge.

## Task status taxonomy & the packaging phase

The task status is strictly **`triage`, `todo`, `running`, `blocked`,
`done`** — the legacy `ready` column was retired (its migration, which folded
stranded `ready` rows into `todo`, was itself removed as dead code
(`repo://migrations/0001_initial_schema.sql#L28-L33`,
`repo://dashboard/models.py#L35`)). Status changes have exactly one code path:
`move_task` on the dashboard (`repo://dashboard/routes/tasks.py#L798-L990`),
reached by `POST /tasks/{id}/move` and `hermes zerofactory move`; `PATCH
/tasks/{id}` refuses a status change with a 400 pointing the caller back to the
move endpoint (`repo://dashboard/routes/tasks.py#L677-L700`).

`done` is **strictly terminal**: the moment an agent actor (builder/reviewer)
reports completion the task deliberately stays `running` and is marked
`metadata["awaiting_pr"] = true` — the *packaging phase* — during which the
dispatcher runs the deterministic pipeline (precommit → commit → push → PR →
route to reviewer) via `_package_and_open_pr`. Only a terminal event (a human
closing the task, a merged PR, an auto-merge, or a PR archive via `close_pr`)
clears the flag and finalizes the task through `_finalize_terminal_done`, which
never commits, pushes, or re-opens review
(`repo://dispatcher/scheduler.py#L1638`, `#L2210`). Blocked tasks carry a
canonical `metadata["blocked_reason_type"]` classified by
`normalize_blocked_reason_type` into `changes-requested`, `approved`,
`human-gate`, or `stuck` (stamped by the dispatcher when a retry budget is
exhausted; any other free-text reason falls through to
`human-gate`), so downstream routing is deterministic instead of
prose-matching (`repo://paths.py#L91-L105`). The packaging phase itself now
carries its own retry budget: repeated git/PR failures during
`_package_and_open_pr` increment `metadata["packaging_retries"]` and store
`metadata["last_packaging_error"]`; after 3 attempts the task is parked in
`blocked` with `blocked_reason_type = "stuck"` and assignee `human`
(`repo://dispatcher/scheduler.py#L1587-L1636`), and the `recover` endpoint
resets both fields alongside the other failure counters
(`repo://dashboard/routes/tasks.py#L1551-L1590`).

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
in depth, [Dashboard, Cron & Automation](/openwiki/components/dashboard-cron.md)
for the operator/automation layer, [Conventions](/openwiki/conventions.md) for
the coding rules agents must follow, and [Quickstart](/openwiki/quickstart.md)
to run the factory.
