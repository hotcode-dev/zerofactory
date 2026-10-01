---
type: quickstart
title: Quickstart
description: Install the Zero Factory Hermes plugin, provision the zf-* specialist profiles, open the dashboard, verify the deterministic precommit gate, and use the core CLI surface to operate the factory.
tags: [quickstart, installation, cli, dashboard, precommit, tests, hermes-plugin]
verified:
  - by: openwiki/0.6.0
    at: 2026-10-01T13:01:50.039Z
sources:
  - id: openwiki-source-4942bcbe129130ccad2b7e2a
    resource: repo://__init__.py
  - id: openwiki-source-9ab161c6e9774cf771b19ced
    resource: repo://.zerofactory/precommit.sh
  - id: openwiki-source-81127d20a2ccc07b7626fc4e
    resource: repo://plugin.yaml
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
  - id: openwiki-source-f0a6e7dc03522b2682f88655
    resource: repo://tests/conftest.py
generated: { by: "hermes", at: "2026-10-01T13:01:50.039Z" }
---

# Quickstart

This is the canonical entry point to the Zero Factory knowledge base. Use it to
get the factory running and to navigate to the deeper pages. The architecture
lives in [Architecture](/openwiki/architecture.md); the moving parts in
[Dispatch Engine](/openwiki/components/dispatcher.md) and
[Dashboard, Cron & Automation](/openwiki/components/dashboard-cron.md); and the
coding rules in [Conventions](/openwiki/conventions.md).

## What it is

Zero Factory is a self-contained **Hermes Agent plugin** that runs a 24/7
multi-agent software factory. Three specialist profiles — `zf-orchestrator`
(decomposes goals and scans for tech debt), `zf-builder` (writes code + tests),
and `zf-reviewer` (thematic PR review, up to 3 rounds) — operate on a durable
Kanban board, each in an isolated Git worktree. No external Node.js daemon or
profile-manager is required.

## Install

```bash
# 1. Install the plugin into Hermes
hermes plugins install hotcode-dev/zerofactory

# 2. Verify or pre-create the zf-* profiles (bootstraps on first run, inheriting
#    the default LLM settings from ~/.hermes/config.yaml)
hermes zerofactory setup

# 3. Open the Kanban dashboard
hermes dashboard
# → open http://localhost:9119/zerofactory
```

## Add a codebase board

A *board* is one repository the factory works on. Create one and provision its
standard artifacts (the deterministic precommit gate and the `openwiki/`
agent docs):

```bash
# Add a board (optional --target-branch to point at a non-main base)
hermes zerofactory board create <git_url> [--target-branch <branch>]

# File a P0 task that generates .zerofactory/precommit.sh for the board
hermes zerofactory setup-repo --board <slug>

# File a P0 task that generates openwiki/ agent documentation (the OpenWiki MCP
# lifecycle) for the board
hermes zerofactory setup-openwiki --board <slug>
```

## Run the deterministic precommit gate

Every task's output is gated by `.zerofactory/precommit.sh` **before** a commit
or PR is opened. It runs three phases in order and exits non-zero on the first
failure:

1. **format** — `ruff check --fix .` then `ruff format .` (pinned ruff; auto-
   installed if missing).
2. **build** — `python3 -m compileall -q .` (static compile, stdlib only).
3. **test** — `python3 -m pytest tests/ -q`.

```bash
.zerofactory/precommit.sh        # run all three phases
# or a single phase:
.zerofactory/precommit.sh format    # / build / test / install-hook
```

If the gate fails, the dispatcher re-spawns `zf-builder` with the exact error
output (up to 3 precommit retries) before the work may become a PR.

## Run the tests

pytest is the framework (defined by `tests/conftest.py`), and the suite is
hermetic — `conftest.py` sets `ZEROFACTORY_SKIP_GIT`, `ZEROFACTORY_SKIP_CRON_SYNC`,
`ZEROFACTORY_DISABLE_DISPATCHER`, and `ZEROFACTORY_SKIP_WORKER_SPAWN` so tests
run without a live factory. Three tiers: `tests/unit/`, `tests/integration/`
(FastAPI REST), `tests/e2e/` (multi-agent workflow + resilience).

```bash
pytest tests/                 # full suite
pytest tests/unit/            # or a single tier: integration/ / e2e/
```

**As of this commit the full suite is green: `179 passed, 1 skipped`.** Re-run
it before publishing any claim about the count.

## Core CLI surface

```bash
# Tasks
hermes zerofactory list [--status <status>] [--assignee <profile>]
hermes zerofactory create "Implement Feature X"
hermes zerofactory move <task_id> <status> [--reason "..."]
hermes zerofactory block <task_id> --reason "..."
hermes zerofactory comment <task_id> "Note..."

# Boards
hermes zerofactory board list
hermes zerofactory board delete <slug>

# Repository memory (the per-board knowledge substrate)
hermes zerofactory memory list --board <slug> [--category <cat>] [-q <query>]
hermes zerofactory memory add --board <slug> "<content>" --category convention --tags "test,lint"
hermes zerofactory memory delete <memory_id>

# Automation / dispatch
hermes zerofactory dispatch          # trigger an immediate dispatch cycle
hermes zerofactory check-stuck       # audit hung worker processes
hermes zerofactory cron list         # view periodic health & scanner jobs
hermes zerofactory cron sync         # sync cron jobs with the Hermes scheduler
hermes zerofactory cron run <job_id> # run a cron scanner immediately

# Profiles
hermes zerofactory setup             # check/initialize zf-* profiles
hermes zerofactory sync-profiles     # update system prompts from templates
```

## Task lifecycle

`triage → todo → running (zf-builder) → running (zf-reviewer) → blocked (human
merge) → done`. Approved PRs park in `blocked` awaiting a human merge on
GitHub; the dispatcher moves them to `done` and prunes the worktree once merged.
Details in [Architecture](/openwiki/architecture.md#session-per-handoff-model)
and [Dispatch Engine](/openwiki/components/dispatcher.md).
