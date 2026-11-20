---
type: subsystem
title: Dashboard & Automation
description: The operator and automation layer — the FastAPI dashboard REST surface (multi-repository boards, 13-stage task lifecycle, dispatcher start/stop controls, built-in cron jobs, settings incl. Mem0 memory, GitHub issues sync/import), the idle improvement scanner, and the No-Agent Mode wake-gate scripts.
tags: [dashboard, rest-api, cron, automation, no-agent-mode, fastapi, setup-services, gh-issues, ui-components, multi-repo, dispatch-controls]
sources:
  - id: openwiki-source-4942bcbe129130ccad2b7e2a
    resource: repo://__init__.py
  - id: openwiki-source-4751ad71b24eb2ac313122ba
    resource: repo://dashboard/gh_issues_service.py
  - id: openwiki-source-ed7166b96533513cf627ba0c
    resource: repo://dashboard/manifest.json
  - id: openwiki-source-4de239baa4d579276db7cf80
    resource: repo://dashboard/memory_service.py
  - id: openwiki-source-52ae51442f849fdbd57863a3
    resource: repo://dashboard/models.py
  - id: openwiki-source-ad6531284d0db039367da971
    resource: repo://dashboard/openwiki_service.py
  - id: openwiki-source-556692619b07f09e3b0370a5
    resource: repo://dashboard/precommit_service.py
  - id: openwiki-source-afe67e60bbdbffde9666707f
    resource: repo://dashboard/routes/__init__.py
  - id: openwiki-source-51d54395961048122dcc244f
    resource: repo://dashboard/routes/boards.py
  - id: openwiki-source-4d0299655ec14b97f5aaa9a7
    resource: repo://dashboard/routes/cron.py
  - id: openwiki-source-40abeef1715d8fbc4e418072
    resource: repo://dashboard/routes/dispatch.py
  - id: openwiki-source-bd5f75c9f65299ae52978752
    resource: repo://dashboard/routes/settings.py
  - id: openwiki-source-c705147b9966f3d6f300034a
    resource: repo://dashboard/routes/tasks.py
  - id: openwiki-source-9e3e91dd19f899c194f7c69e
    resource: repo://dashboard/setup_common.py
  - id: openwiki-source-bd9db10cf8ae31f7cc14e5a9
    resource: repo://dashboard/src/components/MarkdownView.jsx
  - id: openwiki-source-4ed61aeddc44827fa8135492
    resource: repo://dashboard/src/components/Modal.jsx
  - id: openwiki-source-4e30cd4a7d0804e1608dc8d2
    resource: repo://dashboard/src/components/SetupBanners.jsx
  - id: openwiki-source-2cfa5f18edc921e1b93b39fe
    resource: repo://dashboard/src/constants.js
  - id: openwiki-source-8258252e9b79b31153b47276
    resource: repo://dashboard/src/utils/grillParser.js
  - id: openwiki-source-ecd05021670a16c89458cec0
    resource: repo://dispatcher/scanner.py
  - id: openwiki-source-9f9b3c9d5afeac588f3cdae1
    resource: repo://dispatcher/scheduler.py
  - id: openwiki-source-0d153fd68e7210eb5d3be49d
    resource: repo://paths.py
  - id: openwiki-source-823a6ba05c3e376c5f6176a2
    resource: repo://profile_manager.py
  - id: openwiki-source-9f27c77f1584beee490e0abd
    resource: repo://scripts/setup_gh_issues.py
  - id: openwiki-source-8bf8788755a522a066b8b827
    resource: repo://scripts/zf_daily_stats.py
  - id: openwiki-source-20bc44fdf115b28983477777
    resource: repo://scripts/zf_openwiki_gate.py
generated: { by: "hermes", at: "2026-11-20T15:20:57.003Z" }
verified:
  - by: openwiki/0.6.0
    at: 2026-11-20T15:20:57.003Z
---

# Dashboard & Automation

The operator and automation surface has three distinct but linked parts:
the **FastAPI dashboard** (REST + web UI), the **built-in cron layer**
(job families materialized and toggled through `dashboard/routes/cron.py`),
and the **No-Agent Mode scripts** (0-token deterministic wake-gates). The
dashboard is where a human sees and drives the factory; the cron layer plus
the dispatcher's idle-scan logic keep it moving with minimal LLM spend.

## Dashboard REST surface

The dashboard is a Hermes gateway route declared by
`repo://dashboard/manifest.json` — mounted at the `/zerofactory` tab,
rendered by `dist/index.js` + `dist/style.css`, with its REST backend in
`dashboard/plugin_api.py`.

`plugin_api.py` assembles a **master FastAPI `APIRouter`** that aggregates
eight sub-routers — boards, tasks, stats, settings, dispatch, cron,
memories, and agents — wired up in
`repo://dashboard/routes/__init__.py#L17-L44`.

- **boards** — CRUD for project boards plus their linked repositories. A board
  is **multi-repository**: repositories are equal first-class peers linked
  one-to-many via `board_repositories` (`repo_alias`, `git_url`,
  `target_branch`, `additional_reviewer_usernames`), managed by
  `GET /boards/{slug}/repositories` and the add/update/delete variants,
  alongside `POST /boards/test-clone` to validate a git URL before linking.
  The external-tracker endpoints are per-repo aware:
  `GET/POST /boards/{slug}/sync-gh-issues` and
  `POST /boards/{slug}/import-gh-issue` for GitHub issue synchronization and
  import, `GET /boards/{slug}/gh-issues-status` plus
  `POST /boards/{slug}/setup-gh-issues` for the GitHub issues setup flow
  (files or deduplicates a P0 `zf-builder` setup task instead of writing
  templates directly; `repo://dashboard/routes/boards.py#L956-L1092`).
- **tasks** — Kanban card lifecycle (create, update, move, block, comment).
  Task creation accepts an optional explicit `task_id` and `metadata`
  (`repo://dashboard/models.py#L219-L240`): an existing task id returns a
  `duplicate` response with the current status instead of inserting, and
  provided metadata is merged into the stored task metadata — this supports
  deterministic external issue imports
  (`repo://dashboard/routes/tasks.py#L286-L330`). `PATCH /tasks/{task_id}`
  edits fields in one call but **refuses status changes** — status is a
  lifecycle transition with side effects owned by a single code path,
  `POST /tasks/{task_id}/move` (`move_task`), which classifies
  `blocked_reason_type` and manages the `awaiting_pr` / `close_pr` packaging
  flags (`repo://dashboard/routes/tasks.py#L844-L845`,
  `repo://paths.py#L93-L112`). The Grill-with-Docs protocol adds
  `POST /tasks/{task_id}/triage` (dispatches to `zf-orchestrator` for
  triage, `grill` or `egm` mode) and
  `POST /tasks/{task_id}/interview-reply` (records the human's answer to an
  open interview question)
  (`repo://dashboard/routes/tasks.py#L1322`,
  `repo://dashboard/routes/tasks.py#L1603`). The frontend
  `GrillInterviewPanel` and `grillParser.js` scan task comments backwards for
  a `Grill-with-Docs: Decision Required` marker (or a task-metadata
  `active_interview` state) to detect open questions and existing replies.
  New lifecycle endpoints round out the operator surface:
  `POST /tasks/{task_id}/split` decomposes a multi-repo triage task into
  per-repo `todo` tasks, `POST /tasks/{task_id}/recover` routes a
  failure-exhausted blocked task back to the orchestrator with optional
  operator guidance (resetting the failure counters including the packaging
  and orchestrator-recovery state), and `POST/PUT /tasks/{task_id}/report-bug`
  reports an internal Zero Factory defect to the upstream GitHub issue
  tracker (auto-creating the issue when the `auto_create_github_issues`
  setting is enabled)
  (`repo://dashboard/routes/tasks.py#L1398`,
  `repo://dashboard/routes/tasks.py#L1676`,
  `repo://dashboard/routes/tasks.py#L1791`). The EGM release gate adds
  `POST /tasks/{task_id}/approve` (promote an approved spec to `todo` or
  split it into per-repo `todo` children) and
  `POST /tasks/{task_id}/reject` (route the spec back to
  `zf-orchestrator` for a revision; at most 2 rounds, then blocked for a
  human with `blocked_reason_type = "human-gate"`). Rejection also auto-records
  the human's feedback as a `rejected_path` board memory via
  `memory_service.record_rejection_memory`, so future runs on that board avoid
  the rejected approach (`repo://dashboard/routes/tasks.py#L2225`,
  `repo://dashboard/memory_service.py#L619`); the UI shows a
  "Spec & Audit Ready • Awaiting Approval" badge on cards whose metadata
  carries `awaiting_approval` and one-click approve/reject buttons in the
  task detail modal
  (`repo://dashboard/routes/tasks.py#L2113`,
  `repo://dashboard/routes/tasks.py#L2187`). Query params and metadata fields
  are type-guarded with `isinstance` checks so non-string values never break
  grill/conflict status handling
  (`repo://dashboard/routes/tasks.py#L150-L160`).
- **stats** — board velocity/column metrics (`get_stats`).
- **settings** — global + per-board settings, now including Mem0 memory keys
  (`mem0_enabled`, `mem0_embedder_provider` fastembed/openai,
  `mem0_embedder_model`, `mem0_base_url`/`api_key`/`model`),
  `auto_create_github_issues`, `auto_record_memory`,
  `allow_unattended_approvals`, `auto_start_dispatcher`, Langfuse
  observability, task/inactivity timeouts, and
  `POST /settings/profiles/sync` which re-syncs the `zf-*` profile templates
  and skills (`repo://settings.py#L114-L137`).
- **dispatch** — dispatcher start/stop/status controls and stuck-task health
  (below).
- **cron** — list/toggle/update/reset/run of built-in jobs (below).
- **memories** — the per-board repository-knowledge substrate CRUD (dual-write
  to SQLite `board_memories` and Mem0 Qdrant; see
  [Architecture](/openwiki/architecture.md#mem0-vector-memory)).
- **agents** — live status of the four specialist profiles (including
  `zf-goldfish`, labeled "Spec Auditor").

The routes import with a relative/absolute fallback pattern (try `from .routes`,
then `from routes`) so the backend works both as a plugin module and when loaded
directly — a repository-wide convention.

### Dispatcher controls & background start

`dashboard/routes/dispatch.py` exposes explicit operator control over the
background loop: `POST /dispatch/run` triggers one `run_dispatch_cycle`;
`POST /dispatch/start` verifies profile readiness
(`check_setup_status`, answering with a 400 pointing at
`hermes zerofactory setup` when profiles are missing), ensures the built-in
cron jobs are registered, then starts the in-process loop
(`start_background_dispatcher`, `repo://dispatcher/scheduler.py#L2406`);
`POST /dispatch/stop` stops it; `GET /dispatch/status` lists in-flight
(running/blocked) tasks; and `GET /health/stuck-tasks`,
`POST /health/reap-stuck`, and `POST /tasks/{task_id}/reap` expose the
reaper's inspection and single-task reap
(`repo://dashboard/routes/dispatch.py#L28-L228`,
`repo://dashboard/routes/dispatch.py#L44-L101`).

The loop itself auto-starts **only when opted in**: the plugin `register()`
in `__init__.py` runs `_should_auto_start_dispatcher()`, which passes only
when `ZEROFACTORY_SKIP_DISPATCHER` / `ZEROFACTORY_DISABLE_DISPATCHER` are
unset, `zerofactory.db` exists, and the `auto_start_dispatcher` setting
(default **false**) is enabled; it then runs `init_db()`,
`ensure_builtin_cron_jobs()`, and `start_background_dispatcher()`
(`repo://__init__.py#L252-L288`). The `on_kanban_dispatch_tick` hook skips
with `dispatcher_disabled` when the gate fails.

### Web UI: 4 columns, 13-stage badges

The React dashboard groups cards into four actor columns — **Human, Todo,
Running, Done** (`repo://dashboard/src/constants.js#L7-L44`) — while each
card renders a stage badge from `STAGE_META`, which maps all 13 canonical
stages (`triage`, `grill`, `interview`, `spec_draft`, `spec_audit`,
`spec_approval`, `building`, `packaging`, `review`, `recovery`,
`awaiting_merge`, `blocked`, `done`) to an owner, icon, and urgency
(`repo://dashboard/src/constants.js#L55-L69`);
`KanbanBoard.jsx` renders the columns and cards
(`repo://dashboard/src/components/KanbanBoard.jsx#L33`).

The setup-status data from `GET /dispatch/setup/status`
(`repo://dashboard/routes/dispatch.py#L105-L150`, which wraps
`profile_manager.check_setup_status`, `repo://profile_manager.py#L756-L788`)
also drives the dashboard's readiness banners
(`repo://dashboard/src/components/SetupBanners.jsx`): a "Zero Factory Setup
Checklist" banner lists the missing one-shot steps (profiles not initialized,
GitHub CLI not authenticated, dispatcher not running) with copy-ready CLI
commands and an inline start-dispatcher action; an amber "Agent Profiles Out
of Sync" banner appears when `outdated_profiles` is non-empty (the installed
SOUL.md prompts differ from the plugin templates) with a one-click "🔄 Sync
Profiles" button; and an indigo "Zero Factory Plugin Update Available" banner
(driven by `plugin_update_available` / `latest_plugin_version` from
`check_plugin_update`, `repo://profile_manager.py#L634-L709`) shows the current
→ latest version, the `hermes plugins update zerofactory` command, a link to
the Hermes Marketplace, and a per-session dismiss (✕) button.

## Built-in cron jobs

Periodic automation no longer lives in a standalone `cron/` package: the
built-in job families are materialized, listed, toggled, updated, reset, and
triggered through `dashboard/routes/cron.py`, persisted in the `settings`
table under `cron_enabled_<job_id>` (plus `scan_on_idle_<slug>` for the
scanner). The families (`repo://dashboard/routes/cron.py#L77-L231`):

- **`zero-factory-task-queue-check`** (category `core`, every 15m display) —
  the queue watchdog + dispatch cycle. Triggering it runs
  `run_dispatch_cycle` (`repo://dashboard/routes/cron.py#L246-L259`); the
  actual cadence is the 30s background dispatcher loop.
- **`zero-factory-daily-stats`** (category `core`, daily 09:00 display) —
  daily performance/agent-activity aggregation.
- **`zero-factory-improvement-scanner-<slug>`** (category `scanner`,
  per-board) — an **idle** scan, **disabled by default**: it is enabled only
  when the board's `cron_enabled_zero-factory-improvement-scanner-<slug>` /
  `scan_on_idle_<slug>` (or global `scan_on_idle`, or the
  `ZEROFACTORY_SCAN_ON_IDLE` env var) setting is true
  (`repo://dispatcher/scanner.py#L130-L187`). When the dashboard
  triggers it, `spawn_board_scanner` launches a `zf-orchestrator` worker with
  pre-digested git context, or skips when busy/cooldown-active
  (`repo://dashboard/routes/cron.py#L261-L284`,
  `repo://dispatcher/scanner.py#L188-L297`).
- **`zero-factory-openwiki-update-<slug>`** (category `openwiki`, per-board) —
  the OpenWiki doc-sync schedule driven by the `zf_openwiki_gate.py` wake-gate
  (below).

`ensure_builtin_cron_jobs` registers the jobs
(`repo://dashboard/routes/cron.py#L234-L243`); toggling persists
`cron_enabled_<job_id>` and — for scanners — `scan_on_idle_<slug>`, killing
any live scanner process on disable
(`repo://dashboard/routes/cron.py#L296-L317`). `GET /cron` also reports the
`enable_cron_scheduler` master switch
(`repo://dashboard/routes/cron.py#L386-L405`); the CLI mirrors this via
`hermes zerofactory cron list | sync | run <job_id>`
(`repo://__init__.py#L731-L748`).

### Idle improvement scans (in the dispatch cycle)

Beyond the on-demand trigger, the dispatch cycle itself spawns idle scans:
for each board whose running count dropped below the idle threshold with a
`todo` backlog at or below `idle_scan_max_todo` (default 2), the scheduler
checks the active-scanner PID map and the per-board cooldown
(`idle_scan_cooldown_minutes`, default 15) and, when due, calls
`spawn_board_scanner` for the board — so scans ride the 30s loop with zero
extra infrastructure (`repo://dispatcher/scheduler.py#L810-L835`).
`reap_active_scanners` and `reset_idle_scanner_state` keep the scanner table
and in-memory cooldown map honest across restarts
(`repo://dispatcher/scanner.py#L86-L118`,
`repo://dispatcher/scanner.py#L298-L309`).

## No-Agent Mode scripts (0-token automation)

Two deterministic scripts remain, emitting the `wakeAgent` signal Hermes uses
to skip the LLM run entirely:

- **`scripts/zf_openwiki_gate.py`** — the OpenWiki doc-sync wake-gate. It
  skips (`wakeAgent: false`, 0 tokens) when `openwiki/` is missing, the
  working tree is dirty, or HEAD has not advanced past the last
  `docs(openwiki)` sync point; when non-doc commits landed it
  deterministically creates **one** P2 `todo` task for `zf-builder` via
  `create_openwiki_task` — through the dashboard create-task endpoint with a
  SQLite fallback, stamped with the `["automerge", "cat:documentation"]` tags
  — and the filed task carries the `automerge` tag so it can auto-merge after
  review. The script always exits 0, so the LLM run is suppressed either way
  (`repo://scripts/zf_openwiki_gate.py#L1-L30`).
- **`scripts/zf_daily_stats.py`** — a deterministic 24-hour metrics / velocity
  calculator with no LLM involvement: it resolves the kanban DB path through
  the shared `paths.get_zerofactory_db_path` helper, queries `zerofactory.db`
  for completed tasks in the last 24h, and pre-formats cycle-time, column
  distribution, throughput, and bottleneck tables for injection into the LLM
  prompt (`repo://scripts/zf_daily_stats.py#L20-L24`,
  `repo://paths.py#L304`).

This design is what lets Zero Factory run 24/7 while spending near-zero tokens
on the background checks that fire every fifteen minutes.

## Setup services (OpenWiki & precommit)

Three setup services detect when a board repository lacks the standard Zero
Factory artifacts and file a **P0 setup task** for `zf-builder`:

- `openwiki_service.py` — detects the absence of `openwiki/` for a repository
  and keys off the machine-readable ledger `openwiki/.page-manifest.json`
  (its `OPENWIKI_PAGE_MANIFEST_RELPATH` constant), not the generated
  `index.md`, so status reflects what the CLI actually produced. It is
  multi-repo aware: `get_board_linked_repos` resolves every repository on the
  board and the status check accepts an optional `repo_alias`
  (`repo://dashboard/openwiki_service.py#L30-L41`, `#L42-L60`, `#L202-L220`).
- `precommit_service.py` — detects a missing `.zerofactory/precommit.sh` for a
  repository (`repo://dashboard/precommit_service.py#L130-L152`).
- `gh_issues_service.py` — files the P0 GitHub-issue-templates setup task whose
  prompt runs `python3 scripts/setup_gh_issues.py --path . --align` — align
  mode always regenerates `config.yml` repo-aware and rewrites
  `bug_report.yml` / `feature_request.yml` only when missing or when they
  lack the expected `zerofactory` label, so repository-customized templates
  are preserved (`repo://dashboard/gh_issues_service.py#L100-L118`).

All three route through the shared `setup_common.py` helpers
(`check_board_setup_status` at `repo://dashboard/setup_common.py#L96`,
`create_setup_task` at `repo://dashboard/setup_common.py#L217`) with per-flow
dedup keys — `setup:openwiki`, `setup:precommit`, `setup:gh-issues`
(`repo://dashboard/openwiki_service.py#L38`,
`repo://dashboard/precommit_service.py#L32`,
`repo://dashboard/gh_issues_service.py#L30`) — so a superseded task is
replaced rather than duplicated. Deduplication is deliberately **active-only**
(`_find_setup_task(active_only=True)` restricts to `triage`/`todo`/`running`):
`blocked` means "awaiting human merge", not active work, so a
finished-but-unmerged setup task must not dedup or it permanently wedges
regenerate/retry flows; `check_board_setup_status` therefore reports a
`pending_task_id` (any non-done, for the UI "Setup in Progress" badge)
alongside a `dedup_task_id` (active only, for `create_setup_task`)
(`repo://dashboard/setup_common.py#L52-L95`).

> **Native-cron, not GitHub Actions.** These setup services file a `zf-builder`
> task that runs natively through the Zero Factory dispatcher + built-in cron.
> They do **not** emit `.github/workflows/openwiki-update.yml` or `CLAUDE.md`
> — external GitHub Actions is explicitly out of scope for this repo's wiki
> update path. The OpenWiki setup prompt instructs the worker to delete them
> if a tool ever produces them
> (`repo://dashboard/openwiki_service.py#L190`).

## Relationships

Upstream: the dashboard exposes the same durable SQLite substrate the
[Dispatch Engine](/openwiki/components/dispatcher.md) mutates, and the
dispatch/cron routes call `run_dispatch_cycle` and `spawn_board_scanner`
directly. Downstream: setup services file tasks that the dispatcher
provisions a worktree and worker for. Rules for building on this layer
live in [Conventions](/openwiki/conventions.md); the big picture in
[Architecture](/openwiki/architecture.md).
