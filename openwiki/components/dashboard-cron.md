---
type: subsystem
title: Dashboard, Cron & Automation
description: The operator and automation layer — the FastAPI dashboard REST surface, the cron subsystem, and the No-Agent Mode scripts that drive 0-token background queue checks and wake-gated codebase scans.
tags: [dashboard, rest-api, cron, automation, no-agent-mode, fastapi, setup-services]
verified:
  - by: openwiki/0.6.0
    at: 2026-10-01T13:01:50.039Z
sources:
  - id: openwiki-source-334dcccc8c22be32509cfb1e
    resource: repo://cron/definitions.py
  - id: openwiki-source-ed7166b96533513cf627ba0c
    resource: repo://dashboard/manifest.json
  - id: openwiki-source-ad6531284d0db039367da971
    resource: repo://dashboard/openwiki_service.py
  - id: openwiki-source-556692619b07f09e3b0370a5
    resource: repo://dashboard/precommit_service.py
  - id: openwiki-source-afe67e60bbdbffde9666707f
    resource: repo://dashboard/routes/__init__.py
  - id: openwiki-source-9e3e91dd19f899c194f7c69e
    resource: repo://dashboard/setup_common.py
  - id: openwiki-source-8bf8788755a522a066b8b827
    resource: repo://scripts/zf_daily_stats.py
  - id: openwiki-source-08cee866d516142aa81f356d
    resource: repo://scripts/zf_queue_watchdog.py
  - id: openwiki-source-bc25bd3bfcf63b730444ea04
    resource: repo://scripts/zf_scanner_gate.py
generated: { by: "hermes", at: "2026-10-01T13:01:50.039Z" }
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
eight sub-routers (`repo://dashboard/routes/__init__.py#L39-L46`):

- **boards** — CRUD for repository boards (`git_url`, target branch, concurrency cap).
- **tasks** — Kanban card lifecycle (create, move, block, comment).
- **stats** — board velocity/column metrics (`get_stats`).
- **settings** — global + per-board settings.
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
rather than duplicated (`repo://dashboard/setup_common.py`).

> **Native-cron, not GitHub Actions.** These setup services file a `zf-builder`
> task that runs natively through the Zero Factory dispatcher + Hermes background
> cron. They do **not** emit `.github/workflows/openwiki-update.yml` or `CLAUDE.md`
> — external GitHub Actions is explicitly out of scope for this repo's wiki
> update path. If a tool ever produces them, delete them.

## Cron subsystem

`cron/definitions.py` defines the scheduled jobs the dispatcher syncs into Hermes.
Two families (`repo://cron/definitions.py`):

- **`zero-factory-task-queue-check`** — a **`no_agent: True`** job on a 120-minute
  interval. It runs pure Python with no LLM and reaps stuck workers / triggers the
  dispatch cycle (`repo://cron/definitions.py#L207-L222`).
- **`zero-factory-improvement-scanner-<slug>`** — one **per board**, running on
  idle (when the board has spare capacity). It wakes `zf-orchestrator` to scan the
  repo for tech debt and file at most one `zf-builder` `Todo` task.

`cron/manager.py` persists/updates the job definitions in the settings store and
`cron/executor.py` runs them; `cron/scheduler_check.py` audits long-running or
hung worker processes.

## No-Agent Mode scripts (0-token automation)

Two deterministic scripts drive the token-efficient automation and emit a
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
