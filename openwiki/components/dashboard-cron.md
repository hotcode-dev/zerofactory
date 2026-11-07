---
type: subsystem
title: Dashboard, Cron & Automation
description: The operator and automation layer — the FastAPI dashboard REST surface (multi-repository boards, task lifecycle incl. split/recover/report-bug, settings incl. Mem0 memory, GitHub issues sync/import, Jira link), the cron subsystem, and the No-Agent Mode scripts that drive 0-token background queue checks and wake-gated scans.
tags: [dashboard, rest-api, cron, automation, no-agent-mode, fastapi, setup-services, gh-issues, jira, ui-components, multi-repo, mem0]
sources:
  - id: openwiki-source-0fcd11b2ec72e81b8258e0a7
    resource: repo://cron/config.py
  - id: openwiki-source-334dcccc8c22be32509cfb1e
    resource: repo://cron/definitions.py
  - id: openwiki-source-c543e3bc44804657bf480372
    resource: repo://cron/executor.py
  - id: openwiki-source-e06775820f1d183b4e12d4a2
    resource: repo://cron/scheduler_check.py
  - id: openwiki-source-4751ad71b24eb2ac313122ba
    resource: repo://dashboard/gh_issues_service.py
  - id: openwiki-source-ed7166b96533513cf627ba0c
    resource: repo://dashboard/manifest.json
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
  - id: openwiki-source-8258252e9b79b31153b47276
    resource: repo://dashboard/src/utils/grillParser.js
  - id: openwiki-source-0d153fd68e7210eb5d3be49d
    resource: repo://paths.py
  - id: openwiki-source-9f27c77f1584beee490e0abd
    resource: repo://scripts/setup_gh_issues.py
  - id: openwiki-source-8bf8788755a522a066b8b827
    resource: repo://scripts/zf_daily_stats.py
  - id: openwiki-source-20bc44fdf115b28983477777
    resource: repo://scripts/zf_openwiki_gate.py
  - id: openwiki-source-08cee866d516142aa81f356d
    resource: repo://scripts/zf_queue_watchdog.py
  - id: openwiki-source-bc25bd3bfcf63b730444ea04
    resource: repo://scripts/zf_scanner_gate.py
generated: { by: "hermes", at: "2026-11-06T15:00:57.907Z" }
verified:
  - by: openwiki/0.6.0
    at: 2026-11-06T15:00:57.907Z
---

# Dashboard, Cron & Automation

The operator and automation surface has three distinct but linked parts:
the **FastAPI dashboard** (REST + web UI), the **cron subsystem** (scheduled
jobs), and the **No-Agent Mode scripts** (0-token background automation). The
dashboard is where a human sees and drives the factory; cron + scripts are the
autonomous layer that keeps it moving with minimal LLM spend.

## Dashboard REST surface

The dashboard is a Hermes gateway route declared by `repo://dashboard/manifest.json`
— mounted at the `/zerofactory` tab, rendered by `dist/index.js` +
`dist/style.css`, with its REST backend in `dashboard/plugin_api.py`.

`plugin_api.py` assembles a **master FastAPI `APIRouter`** that aggregates
eight sub-routers (`repo://dashboard/routes/__init__.py#L46-L54`):

- **boards** — CRUD for project boards plus their linked repositories. A board
  is now **multi-repository**: repositories are equal first-class peers linked
  one-to-many via `board_repositories` (`repo_alias`, `git_url`,
  `target_branch`, `additional_reviewer_usernames`), managed by
  `GET /boards/{slug}/repositories`,
  `POST /boards/{slug}/repositories` (add),
  `PUT/PATCH /boards/{slug}/repositories/{repo_alias}`, and
  `DELETE /boards/{slug}/repositories/{repo_alias}`
  (`repo://dashboard/routes/boards.py#L702-L861`), alongside
  `POST /boards/test-clone` to validate a git URL before linking
  (`repo://dashboard/routes/boards.py#L418-L538`). The external-tracker
  integration endpoints are per-repo aware:
  `GET/POST /boards/{slug}/sync-gh-issues` and
  `POST /boards/{slug}/import-gh-issue` for GitHub issue synchronization and
  import, `GET /boards/{slug}/gh-issues-status` plus
  `POST /boards/{slug}/setup-gh-issues` for the GitHub issues setup flow
  (files or deduplicates a P0 `zf-builder` setup task instead of writing
  templates directly), and `POST /boards/{slug}/setup-jira` /
  `POST /boards/{slug}/test-jira` for the Jira Cloud link
  (`repo://dashboard/routes/boards.py#L996-L1234`). Board-level
  per-repo precommit and OpenWiki status/setup endpoints mirror the same
  pattern (`repo://dashboard/routes/boards.py#L926-L995`).
- **tasks** — Kanban card lifecycle (create, update, move, block, comment).
  Task creation accepts an optional explicit `task_id` and `metadata` so
  external importers can create deterministic, dedup-keyed cards
  (`repo://dashboard/routes/tasks.py#L269-L340`,
  `repo://dashboard/models.py#L221-L244`). `PATCH /tasks/{task_id}`
  edits fields in one call but **refuses status changes** — status is a
  lifecycle transition with side effects owned by a single code path,
  `POST /tasks/{task_id}/move` (`move_task`), which also classifies
  `blocked_reason_type` and manages the `awaiting_pr` / `close_pr` packaging
  flags (`repo://dashboard/routes/tasks.py#L807-L1092`); the Grill-with-Docs
  protocol adds `POST /tasks/{task_id}/triage` (dispatches to
  `zf-orchestrator` for triage) and
  `POST /tasks/{task_id}/interview-reply` (records the human's answer to an
  open interview question) (`repo://dashboard/routes/tasks.py#L1237-L1557`).
  New lifecycle endpoints round out the operator surface:
  `POST /tasks/{task_id}/split` decomposes a multi-repo triage task into
  per-repo `todo` tasks, `POST /tasks/{task_id}/recover` routes a
  failure-exhausted blocked task back to the orchestrator with optional
  operator guidance (resetting the failure counters including the packaging
  retry state), and `POST /tasks/{task_id}/report-bug` reports an
  internal Zero Factory defect to the upstream GitHub issue tracker
  (auto-creating the issue when the `auto_create_github_issues` setting is
  enabled) (`repo://dashboard/routes/tasks.py#L1286-L1993`). The EGM
  release gate adds `POST /tasks/{task_id}/approve` (promote an approved
  spec to `todo` or split it into per-repo `todo` children) and
  `POST /tasks/{task_id}/reject` (route the spec back to
  `zf-orchestrator` for a revision; at most 2 rounds, then blocked for a
  human with `blocked_reason_type = "human-gate"`); the UI shows a
  "Spec & Audit Ready • Awaiting Approval" badge on cards whose metadata
  carries `awaiting_approval` and one-click approve/reject buttons in the
  task detail modal (`repo://dashboard/routes/tasks.py#L1992-L2141`,
  `repo://dashboard/src/components/KanbanBoard.jsx#L272-L293`,
  `repo://dashboard/src/modals/TaskDetailModal.jsx#L147-L171`). Query params
  and metadata fields are type-guarded with `isinstance` checks so
  non-string values never break grill/conflict status handling
  (`repo://dashboard/routes/tasks.py#L122-L145`).
- **stats** — board velocity/column metrics (`get_stats`).
- **settings** — global + per-board settings, now including Mem0 memory keys
  (`mem0_enabled`, `mem0_embedder_provider` fastembed/openai,
  `mem0_embedder_model`, `mem0_base_url`/`api_key`/`model`),
  `auto_create_github_issues`, Langfuse observability, task/inactivity
  timeouts, and `POST /settings/profiles/sync` which re-syncs the `zf-*`
  profile templates and skills (`repo://dashboard/routes/settings.py#L243-L268`,
  `repo://settings.py#L86-L156`).
- **dispatch** — manual dispatch / stuck-worker audit triggers.
- **cron** — list/sync/run of scheduled jobs.
- **memories** — the per-board repository-knowledge substrate CRUD (dual-write
  to SQLite `board_memories` and Mem0 Qdrant; see
  [Architecture](/openwiki/architecture.md#mem0-vector-memory)).
- **agents** — live status of the four specialist profiles (including
  `zf-goldfish`, labeled "Spec Auditor").

The routes import with a relative/absolute fallback pattern (try `from .routes`,
then `from routes`) so the backend works both as a plugin module and when loaded
directly — a repository-wide convention.

### Setup services (OpenWiki & precommit)

Two setup services detect when a board repository lacks the standard Zero
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

Both route through the shared `setup_common.py` helper (`check_board_setup_status`,
`create_setup_task`) with a `setup:` dedup key so a superseded task is replaced
rather than duplicated (`repo://dashboard/setup_common.py`); the helper accepts
an optional `tags` parameter, and the OpenWiki setup flow stamps `["automerge"]`
on its P0 task (`repo://dashboard/openwiki_service.py#L236-L240`). The GitHub issues
setup reuses the same helper: `create_gh_issues_setup_task`
(`repo://dashboard/gh_issues_service.py#L100-L118`) files the P0 task whose
prompt runs `python3 scripts/setup_gh_issues.py --path . --align` — align mode
always regenerates `config.yml` repo-aware and rewrites `bug_report.yml` /
`feature_request.yml` only when missing or when they lack the expected
`zerofactory` label, so repository-customized templates are preserved
(`repo://scripts/setup_gh_issues.py`). Deduplication is deliberately
**active-only** (`_find_setup_task(active_only=True)` restricts to
`triage`/`todo`/`running`): `blocked` means "awaiting human merge", not active
work, so a finished-but-unmerged setup task must not dedup or it permanently
wedges regenerate/retry flows; `check_board_setup_status` therefore reports a
`pending_task_id` (any non-done, for the UI "Setup in Progress" badge) alongside
a `dedup_task_id` (active only, for `create_setup_task`)
(`repo://dashboard/setup_common.py#L56-L127`).

> **Native-cron, not GitHub Actions.** These setup services file a `zf-builder`
> task that runs natively through the Zero Factory dispatcher + Hermes background
> cron. They do **not** emit `.github/workflows/openwiki-update.yml` or `CLAUDE.md`
> — external GitHub Actions is explicitly out of scope for this repo's wiki
> update path. The OpenWiki setup prompt instructs the worker to delete them if a
> tool ever produces them
> (`repo://dashboard/openwiki_service.py#L190`).

## Web UI components

The React dashboard (built into `dist/index.js`) is built from a small set of
reusable primitives in `dashboard/src/components/`:

- **`Modal.jsx`** — a single standard modal dialog enforcing uniform responsive
  sizing, backdrop, mobile padding, and an Escape-key close listener. All
  modals (add memory, cron, edit board, new board, new task, settings, task
  detail) compose it instead of reimplementing dialog chrome
  (`repo://dashboard/src/components/Modal.jsx`).
- **`MarkdownView.jsx`** — a lightweight, zero-dependency Markdown renderer
  (headers, bold/italic, inline code, links, lists, Pros/Cons callouts) used
  to display task descriptions and issue bodies in the UI
  (`repo://dashboard/src/components/MarkdownView.jsx`).
- **`GrillInterviewPanel.jsx`** — the interactive Grill-with-Docs requirement
  panel. It surfaces the active interview question/options for a task and
  posts the human's reply through the `interview-reply` endpoint. The parser
  `dashboard/src/utils/grillParser.js` scans task comments backwards for a
  `Grill-with-Docs: Decision Required` marker (or a task-metadata
  `active_interview` state) and detects whether a human reply already exists
  (`repo://dashboard/src/utils/grillParser.js`). A **`BoardSelector.jsx`**
  component lets the operator switch the active board; the header no longer
  carries a dedicated "refresh board" button.

## Cron subsystem

`cron/definitions.py` defines the scheduled jobs the dispatcher syncs into
Hermes. Three families (`repo://cron/definitions.py`), each carrying a
`category` field (`core`, `scanner`, `openwiki`) used by the dashboard filters
and CLI:

- **`zero-factory-task-queue-check`** — a `no_agent: False` job on a **15-minute**
  interval (was previously `no_agent: True` on 120 minutes) whose script is
  `zf_queue_watchdog.py` and whose category is `core`
  (`repo://cron/definitions.py#L268-L293`). It still runs pure Python with no
  LLM on the deterministic path; the Hermes host only wakes when the watchdog
  emits a bottleneck alert.
- **`zero-factory-improvement-scanner-<slug>`** — one **per board**, running on
  idle (when the board has spare capacity; the per-board
  `ZEROFACTORY_SCANNER_INTERVAL_MINUTES` interval is the fallback when not
  idle) and wakes `zf-orchestrator` to scan the repo for tech debt and file at
  most one `zf-builder` `Todo` task
  (`repo://cron/definitions.py#L342-L405`).
- **`zero-factory-openwiki-update-<slug>`** — one **per board**, daily by default
  (`ZEROFACTORY_OPENWIKI_INTERVAL_MINUTES`, default 1440), also
  **`no_agent: True`** with the `zf_openwiki_gate.py` script as its deterministic
  wake-gate (`repo://cron/definitions.py#L411-L450`). It does **not** wake the LLM
  to rewrite docs itself: the gate decides whether to create at most one P2
  `zf-builder` doc-sync task on the board (see below).

`cron/manager.py` persists/updates the job definitions in the settings store
(including pruning openwiki jobs whose board was deleted, and keeping the
canonical `zf-orchestrator` profile in sync) and `cron/executor.py` runs them —
every `zero-factory-*` job is pinned to the `zf-orchestrator` profile regardless
of stored fields (`repo://cron/executor.py#L87-L92`). `cron/scheduler_check.py`
audits long-running or hung worker processes; when it pauses built-in jobs via
the master scheduler it tags them `paused_by_master` **without** marking
`custom_config`, so user-tuned job fields survive a scheduler enable/disable
toggle (`repo://cron/scheduler_check.py#L218-L220`). On-demand
`hermes cron run` waits up to `CRON_RUN_TIMEOUT` (default **900s**,
`ZEROFACTORY_CRON_RUN_TIMEOUT`) so multi-step agent runs are not cut off
(`repo://cron/config.py#L20-L22`).

## No-Agent Mode scripts (0-token automation)

Four deterministic scripts drive the token-efficient automation and emit a
`wakeAgent` signal that Hermes uses to skip the LLM run entirely:

- **`scripts/zf_queue_watchdog.py`** — the queue watchdog. It (1) auto-syncs
  open GitHub issues labeled `zerofactory` into the active boards on a
  per-repo cooldown (guarded by `ZEROFACTORY_AUTO_SYNC_GH_ISSUES` and a
  `gh_issues_sync_cache.json` timestamp so frequent ticks never spam the GitHub
  API; a sync failure does **not** stamp the cooldown; synced issues park in
  `triage` assigned to `human` so no GPU tokens are spent on unvetted
  submissions), (2) reaps stuck worker
  subprocesses via `reap_stuck_tasks`, (3) triggers `run_dispatch_cycle`,
  (4) pulls `check_stuck_tasks(include_blocked=True)` for failure-exhausted
  reporting, and (5) pulls `get_stats`. When the queue is healthy it emits
  `{"wakeAgent": false}` (0 tokens); when it finds a bottleneck it emits a
  markdown alert for the operator (`repo://scripts/zf_queue_watchdog.py#L50-L193`).
- **`scripts/zf_scanner_gate.py`** — the scanner wake-gate. It compares the
  current Git HEAD / working tree against a durable `~/.hermes/scanner_state.json`;
  when nothing material changed (or the board is busy / in cooldown) it emits
  `{"wakeAgent": false}` and suppresses the LLM scan, otherwise it emits
  `{"wakeAgent": true}` and provides pre-digested git context
  (`repo://scripts/zf_scanner_gate.py`). It also counts active pipeline tasks
  (`running`, `todo`) and the board's concurrency cap to decide whether the
  board is idle enough to scan.
- **`scripts/zf_openwiki_gate.py`** — the OpenWiki doc-sync gate. It is a
  **deterministic task-creation** wake-gate rather than an LLM wake: it skips
  (`wakeAgent: false`) when `openwiki/` is missing, when the working tree is
  dirty, or — unless forced (`--force` / `ZEROFACTORY_FORCE_OPENWIKI_UPDATE`) —
  when an OpenWiki-titled task is already active on the board in `triage`/`todo`/
  `running`/`blocked`. When HEAD has advanced past the last `openwiki`-touching
  commit, it creates at most **one** P2 `todo` task for `zf-builder` via
  `create_openwiki_task` — deterministically, idempotent via the create-task
  endpoint, with a SQLite fallback if the plugin API is unavailable — and the
  filed task carries the `automerge` tag (and `cat:documentation`) so it can
  auto-merge after review; it then reports 0-token completion (the script
  always exits 0, so the LLM run is suppressed either way;
  `repo://scripts/zf_openwiki_gate.py`).
- **`scripts/zf_daily_stats.py`** — a deterministic 24-hour metrics / velocity
  calculator with no LLM involvement.

This design is what lets Zero Factory run 24/7 while spending near-zero tokens on
the background checks that fire every fifteen minutes.

## Relationships

Upstream: the dashboard exposes the same durable SQLite substrate the
[Dispatch Engine](/openwiki/components/dispatcher.md) mutates, and cron/scripts
call `run_dispatch_cycle` directly. Downstream: setup services file tasks that the
dispatcher provisions a worktree and worker for. Rules for building on this layer
live in [Conventions](/openwiki/conventions.md); the big picture in
[Architecture](/openwiki/architecture.md).
