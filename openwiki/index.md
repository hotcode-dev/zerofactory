# Zero Factory — OpenWiki

Machine-readable architectural knowledge base for coding agents (`zf-builder`,
`zf-reviewer`, `zf-orchestrator`) and human developers. Read this index **first**,
then open only the page relevant to your task — do not re-read the entire source
tree.

> Maintained from the live code at `hotcode-dev/zerofactory`. If a page and the
> code disagree, the code wins — file a task to update the wiki.

## What this repository is

Zero Factory is a **Hermes Agent plugin** (see `plugin.yaml`) that runs a 24/7
autonomous software factory: a persistent Kanban substrate (SQLite), a background
**dispatcher** that provisions isolated Git worktrees and spawns specialist agent
workers, deterministic **precommit** gates (format → build → test), automatic
GitHub **PR** creation, multi-round **review**, and a FastAPI **dashboard** at
`/zerofactory`. Three specialist profiles form the team:

| Profile | Role |
|---|---|
| `zf-orchestrator` | Decomposes goals, scans repos for tech debt, files `Todo` tasks, escalates blockers |
| `zf-builder` | Implements features/fixes in an isolated worktree, writes tests |
| `zf-reviewer` | Reviews the open PR (Correctness → Performance → Clean Code, ≤ 3 rounds) |

Canonical profile identity lives in `PROFILE_MAP` (`paths.py:28`); sentinels
`unassigned` / `human` extend it into `VALID_ASSIGNEES` (`paths.py`). Both the
dispatcher (`dispatcher/config.py` → `VALID_PROFILES`) and the dashboard
(`dashboard/models.py` → `VALID_ASSIGNEES`) derive from it — **do not re-declare
the profile list elsewhere**.

## Task lifecycle

```
Triage → Todo → Running (zf-builder) → [precommit: format→build→test]
     → Dispatcher commits, merges main, pushes, opens GitHub PR
     → Running (zf-reviewer)
     → Approved?  yes → Blocked (human merges PR) → Done
                  no  → Todo (changes requested, new builder session)
```

Every handoff terminates the previous worker and spawns a **fresh session**
("stateless workers, stateful substrate") — durable state lives in Git, the
PR comments, and `kanban.db`, not in conversation history. See [zf-profiles.md](zf-profiles.md).

## Page index

| Page | Covers |
|---|---|
| [zf-profiles.md](zf-profiles.md) | The 3 specialist profiles, session-per-handoff model, prompt injection, board memory |
| [dispatcher.md](dispatcher.md) | Dispatch cycle, worktree lifecycle, deterministic precommit, GitHub PR/review flow, stuck-worker reaper |
| [dashboard.md](dashboard.md) | FastAPI backend, REST endpoints by module, dashboard UI, services |
| [database.md](database.md) | `kanban.db` schema, tables/columns, migrations, DB helpers, env overrides |
| [cron.md](cron.md) | Builtin cron jobs (no-agent watchdog, per-board improvement scanner), gate scripts |
| [cli.md](cli.md) | `hermes zerofactory` CLI command reference and handler locations |
| [tests.md](tests.md) | Test suite map: 3 tiers × 35 files, hermetic fixtures, known pre-existing failures |
| [conventions.md](conventions.md) | Architectural decisions, coding conventions, environment variables, gotchas |

## System layout (top level)

```
zerofactory/
├── __init__.py            # Plugin entrypoint: register() → CLI commands + lifecycle hooks
├── plugin.yaml / package.json
├── builtin_cron.py        # Public re-exports of cron helpers (test/mock seam)
├── paths.py               # PROFILE_MAP, assignee normalization, per-profile state.db resolution
├── settings.py            # Setting keys + defaults + load_settings()
├── profile_manager.py     # Auto-provisions zf-* profiles, scripts, symlinks, env
├── migrations/            # Versioned SQLite migrations (runner + 0001/0002)
├── dispatcher/            # Autonomous dispatch engine (scheduler, worktree, reaper, PR, …)
├── cron/                  # Builtin cron job definitions, manager, executor, store
├── scripts/               # No-Agent scripts: watchdog, scanner gate, daily stats
├── dashboard/             # FastAPI plugin_api.py + routes/ + services + dist/ UI
├── skills/                # Ponytail ladder + role playbooks (zf-*-ponytail, orchestration)
├── templates/             # Version-controlled zf-* profile templates
├── tests/                 # unit/ integration/ e2e/ + conftest.py
└── .zerofactory/          # precommit.sh (format → build → test)
```

## Cross-module dependency graph

```
Hermes plugin host
   └── __init__.py ──────────────► dashboard/plugin_api.py  (imports DB layer + route services)
        │                              ├── dashboard/db.py        (SQLite: kanban.db)
        │                              ├── dashboard/models.py     (Pydantic DTOs)
        │                              ├── dashboard/routes/*      (8 routers → master router)
        │                              ├── dashboard/openwiki_service.py, memory_service.py, …
        │                              └── migrations/runner.py    (auto-applied in init_db)
        │
        ├── dispatcher/*  ──► paths.py, settings.py, migrations/
        │     ├── scheduler.py        run_dispatch_cycle() — the autonomous loop
        │     ├── worker_spawner.py   hermes -p <profile> --yolo --cli spawns
        │     ├── worktree.py         ~/git/<repo>-worktrees/<task_id> + precommit + merge
        │     ├── github_pr.py        PR open/merge/review-comment sync
        │     ├── reaper.py           stuck-worker detection & requeue
        │     ├── scanner.py          improvement-scanner spawn/capacity gating
        │     ├── context_builder.py  prompt pre-digests (memories, git diff)
        │     └── process_manager.py  PID/PGID liveness & termination
        │
        ├── cron/* ───────► cron/definitions.py (job specs) ─► scripts/zf_*.py (no-agent)
        ├── builtin_cron.py  (re-export facade; dispatcher & dashboard import through it)
        └── profile_manager.py ──► ~/.hermes/profiles/zf-*/ + ~/.hermes/.env + config.yaml
```

Key rules:

- **`builtin_cron.py` is a re-export facade.** `dispatcher/*` and
  `dashboard/*` import cron helpers (e.g. `resolve_board_repo_path`,
  `get_all_builtin_cron_jobs`) through it so tests can monkeypatch one seam.
- **`dashboard/plugin_api.py`** imports `dashboard/db.py` (DB layer) and each
  service module; `__init__.py` imports the dashboard layer for the CLI.
  Services use `try: from .x import / except: from x import` so they work both
  as a package and when loaded flat by the plugin host.
- **`paths.py` is the single source of truth** for profile identity; anything
  needing "is X a valid assignee?" goes through `normalize_assignee` /
  `VALID_ASSIGNEES`.

## Build & verify

```bash
./.zerofactory/precommit.sh            # format (ruff) → build (compileall) → test (pytest)
./.zerofactory/precommit.sh test       # tests only
python3 -m pytest tests/ -q            # equivalent test run
```

See [tests.md](tests.md) for the suite map and [conventions.md](conventions.md)
for style rules and environment variables.
