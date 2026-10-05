---
type: subsystem
title: Dashboard, Cron & Automation
description: The operator and automation layer — the FastAPI dashboard REST surface (boards, tasks, settings, GitHub issues sync/import, Jira link setup), the reusable React UI components (Modal, MarkdownView, GrillInterviewPanel), the cron subsystem, and the No-Agent Mode scripts that drive 0-token background queue checks and wake-gated codebase scans.
tags: [dashboard, rest-api, cron, automation, no-agent-mode, fastapi, setup-services, gh-issues, jira, ui-components]
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
generated: { by: "hermes", at: "2026-10-05T10:11:27.384Z" }
verified:
  - by: openwiki/0.6.0
    at: 2026-10-05T10:11:27.384Z
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

- **boards** — CRUD for repository boards (`git_url`, target branch,
  concurrency cap, `jira_url`), plus the external-tracker integration
  endpoints: `GET/POST /boards/{slug}/sync-gh-issues` and
  `POST /boards/{slug}/import-gh-issue` for GitHub issue synchronization and
  import, `GET /boards/{slug}/gh-issues-status` plus
  `POST /boards/{slug}/setup-gh-issues` for the GitHub issues setup flow
  (files or deduplicates a P0 `zf-builder` setup task instead of writing
  templates directly), and `POST /boards/{slug}/setup-jira` /
  `POST /boards/{slug}/test-jira` for the Jira Cloud link
  (`repo://dashboard/routes/boards.py#L500-L727`).
- **tasks** — Kanban card lifecycle (create, update, move, block, comment).
  Task creation accepts an optional explicit `task_id` and `metadata` so
  external importers can create deterministic, dedup-keyed cards
  (`repo://dashboard/routes/tasks.py#L243-L330`). `PATCH /tasks/{task_id}`
  edits fields in one call (`repo://dashboard/routes/tasks.py#L626-L630`), and
  the Grill-with-Docs protocol adds `POST /tasks/{task_id}/triage` (dispatches
 to `zf-orchestrator` for triage) and
 `POST /tasks/{task_id}/interview-reply` (records the human's answer to an
 open interview question) (`repo://dashboard/routes/tasks.py#L1003-L1122`).
  Query params and metadata fields are type-guarded with `isinstance` checks so
  non-string values never break grill/conflict status handling.
- **stats** — board velocity/column metrics (`get_stats`).
- **settings** — global + per-board settings, including
  `POST /settings/profiles/sync` which re-syncs the `zf-*` profile templates and
  skills (`repo://dashboard/routes/settings.py#L243-L268`).
- **dispatch** — manual dispatch / stuck-worker audit triggers.
- **cron** — list/sync/run of scheduled jobs.
- **memories** — the per-board repository-knowledge substrate CRUD.
- **agents** — live status of the three specialist profiles.

The routes import with a relative/absolute fallback pattern (try `from .routes`,
then `from routes`) so the backend works both as a plugin module and when loaded
directly — a repository-wide convention.

### Setup services (OpenWiki & precommit)

Two setup services detect when a board lacks the standard Zero Factory artifacts
and file a **P0 setup task** for `zf-builder`:

- `openwiki_service.py` — detects the absence of `openwiki/` and keys off the
  machine-readable ledger `openwiki/.page-manifest.json` (its `PAGE_MANIFEST_PATH`),
  not the generated `index.md`, so status reflects what the CLI actually produced
  (`repo://dashboard/openwiki_service.py#L29-L41`).
- `precommit_service.py` — detects a missing `.zerofactory/precommit.sh`.

Both route through the shared `setup_common.py` helper (`check_board_setup_status`,
`create_setup_task`) with a `setup:` dedup key so a superseded task is replaced
rather than duplicated (`repo://dashboard/setup_common.py`). The GitHub issues
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
(`repo://dashboard/setup_common.py#L56-L97`, `#L121-L127`).

> **Native-cron, not GitHub Actions.** These setup services file a `zf-builder`
> task that runs natively through the Zero Factory dispatcher + Hermes background
> cron. They do **not** emit `.github/workflows/openwiki-update.yml` or `CLAUDE.md`
> — external GitHub Actions is explicitly out of scope for this repo's wiki
> update path. If a tool ever produces them, delete them.

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
  (`repo://dashboard/src/utils/grillParser.js`).

## Cron subsystem

`cron/definitions.py` defines the scheduled jobs the dispatcher syncs into Hermes.
Three families (`repo://cron/definitions.py`), each carrying a `category` field
(`core`, `scanner`, `openwiki`) used by the dashboard filters and CLI:

- **`zero-factory-task-queue-check`** — a **`no_agent: True`** job on a 120-minute
  interval. It runs pure Python with no LLM and reaps stuck workers / triggers the
  dispatch cycle (`repo://cron/definitions.py#L248-L260`).
- **`zero-factory-improvement-scanner-<slug>`** — one **per board**, running on
  idle (when the board has spare capacity). It wakes `zf-orchestrator` to scan the
  repo for tech debt and file at most one `zf-builder` `Todo` task
  (`repo://cron/definitions.py#L312-L380`).
- **`zero-factory-openwiki-update-<slug>`** — one **per board**, daily by default
  (`ZEROFACTORY_OPENWIKI_INTERVAL_MINUTES`, default 1440), also
  **`no_agent: True`** with the `zf_openwiki_gate.py` script as its deterministic
  wake-gate (`repo://cron/definitions.py#L381-L418`). It does **not** wake the LLM
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

- **`scripts/zf_queue_watchdog.py`** — the queue watchdog. It (1) reaps stuck
  worker subprocesses via `reap_stuck_tasks`, (2) triggers `run_dispatch_cycle`,
  and (3) pulls `get_stats`. When the queue is healthy it emits
  `{"wakeAgent": false}` (0 tokens); when it finds a bottleneck it emits a markdown
  alert for the operator (`repo://scripts/zf_queue_watchdog.py#L1-L20`).
- **`scripts/zf_scanner_gate.py`** — the scanner wake-gate. It compares the current
  Git HEAD / working tree against a durable `~/.hermes/scanner_state.json`; when
  nothing material changed (or the board is busy / in cooldown) it emits
  `{"wakeAgent": false}` and suppresses the LLM scan, otherwise it emits
  `{"wakeAgent": true}` and provides pre-digested git context
  (`repo://scripts/zf_scanner_gate.py`). It also counts active pipeline tasks
  (`running`, `todo`) and the board's concurrency cap to decide whether the board
  is idle enough to scan (`repo://scripts/zf_scanner_gate.py#L299-L351`).
- **`scripts/zf_openwiki_gate.py`** — the OpenWiki doc-sync gate. It is a
  **deterministic task-creation** wake-gate rather than an LLM wake: it skips
  (`wakeAgent: false`) when `openwiki/` is missing, when the working tree is
  dirty, or — unless forced (`--force` / `ZEROFACTORY_FORCE_OPENWIKI_UPDATE`) —
  when an OpenWiki-titled task is already active on the board in `triage`/`todo`/
  `ready`/`running`/`blocked` (`repo://scripts/zf_openwiki_gate.py#L185-L215`).
  When HEAD has advanced past the last `openwiki`-touching commit, it creates at
  most **one** P2 `todo` task for `zf-builder` via `create_openwiki_task` —
  deterministically, idempotent via the create-task endpoint, with a SQLite
  fallback if the plugin API is unavailable (`repo://scripts/zf_openwiki_gate.py#L50-L112`)
  — and reports 0-token completion
  (`repo://scripts/zf_openwiki_gate.py#L185-L215` checks for an
  already-active OpenWiki-titled task in `triage`/`todo`/`ready`/`running`/
  `blocked`).
- **`scripts/zf_daily_stats.py`** — a deterministic 24-hour metrics / velocity
  calculator with no LLM involvement.

This design is what lets Zero Factory run 24/7 while spending near-zero tokens on
the background checks that fire every two minutes.

## Relationships

Upstream: the dashboard exposes the same durable SQLite substrate the
[Dispatch Engine](/openwiki/components/dispatcher.md) mutates, and cron/scripts
call `run_dispatch_cycle` directly. Downstream: setup services file tasks that the
dispatcher provisions a worktree and worker for. Rules for building on this layer
live in [Conventions](/openwiki/conventions.md); the big picture in
[Architecture](/openwiki/architecture.md).
