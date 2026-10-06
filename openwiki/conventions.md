---
type: conventions
title: Conventions
description: Repository patterns and rules agents must follow — the relative-import fallback, sys.path bootstrap, namespaced logging, the ruff lint/format gate, the pytest test organization, and the dashboard CSS rebuild rule.
tags: [conventions, import-pattern, ruff, pytest, css-build, logging, error-handling]
sources:
  - id: openwiki-source-9ab161c6e9774cf771b19ced
    resource: repo://.zerofactory/precommit.sh
  - id: openwiki-source-334dcccc8c22be32509cfb1e
    resource: repo://cron/definitions.py
  - id: openwiki-source-b0b96941097286c5af925c64
    resource: repo://dashboard/build_css.mjs
  - id: openwiki-source-594f18a4ed0f4f061e35fdc9
    resource: repo://dashboard/db.py
  - id: openwiki-source-afe67e60bbdbffde9666707f
    resource: repo://dashboard/routes/__init__.py
  - id: openwiki-source-b9dde5e47d9b9a7f900ad216
    resource: repo://dispatcher/github_pr.py
  - id: openwiki-source-b73a2eae57b810a3ad15196e
    resource: repo://dispatcher/worker_spawner.py
  - id: openwiki-source-2feae2067f9a49cc4d8f2150
    resource: repo://migrations/runner.py
  - id: openwiki-source-d763dfe33a2468865a9b9ce5
    resource: repo://ruff.toml
  - id: openwiki-source-f0a6e7dc03522b2682f88655
    resource: repo://tests/conftest.py
  - id: openwiki-source-b4194cdb1aee8e18787b21d6
    resource: repo://tests/unit/dashboard/test_dashboard_css.py
generated: { by: "hermes", at: "2026-10-03T01:15:19.967Z" }
verified:
  - by: openwiki/0.6.0
    at: 2026-10-05T10:11:27.384Z
---

# Conventions

Rules for writing code in this repository. These are the patterns every
`zf-builder` edit and `zf-reviewer` check relies on; following them keeps diffs
surgical and the deterministic precommit gate green.

## The relative-import fallback (mandatory pattern)

Every internal module that imports a sibling module uses a
**try/except relative→absolute fallback**, because the code is loaded both as a
plugin subpackage and as top-level modules when a script bootstraps `sys.path`:

```python
try:
    from ..settings import load_settings  # as a plugin package
except (ImportError, ValueError):
    from settings import load_settings  # type: ignore   # direct module load
```

See `repo://dashboard/db.py#L24-L30` and the route aggregator
`repo://dashboard/routes/__init__.py#L23-L46`. Preserve this exact shape when
adding cross-module imports.

## `sys.path` bootstrap before imports

Modules that may be loaded directly (scripts, `cron/definitions.py`,
`dashboard/*`) insert the plugin root onto `sys.path` **before** importing
internal modules, e.g. `repo://cron/definitions.py#L14-L16`. Ruff ignores
`E402` specifically so this required ordering is legal
(`repo://ruff.toml#L14`). The test suite does the same in
`repo://tests/conftest.py#L13-L16`.

## Namespaced logging

Loggers are namespaced under `zerofactory.*` per subsystem
(`zerofactory.cron`, `zerofactory.migrations`, ...), created with
`logging.getLogger("zerofactory.<subsystem>")`
(`repo://cron/definitions.py#L28`, `repo://migrations/runner.py#L23`). Use the
matching namespace for new modules rather than the root logger.

## Error handling

Prefer narrow `except (ImportError, ValueError)` for the import-fallback idiom,
and catch specific exceptions (e.g. `subprocess.TimeoutExpired`,
`BlockingIOError`) in worker/process code rather than bare `except:`.
`repo://dispatcher/worker_spawner.py` and `repo://dispatcher/scheduler.py` are
the reference style. Fail loudly at process boundaries (the precommit gate exits
non-zero on a missing tool) rather than silently skipping.

## Lint & format: ruff (the deterministic gate)

- **`ruff.toml`** targets **py311** and enables the `E`, `F`, `W` rule sets
  (`repo://ruff.toml#L1-L19`).
- `E501`, `W291`, `W293` are ignored because `ruff format` owns line length and
  trailing whitespace (`repo://ruff.toml#L12-L19`).
- **Per-file ignores** (`repo://ruff.toml#L21-L31`) allow intentional re-exports
  and unused test variables: `__init__.py`/`plugin_api.py`/`models.py`/
  `dispatcher/config.py` allow `F401`/`F403`, and `tests/**` allows `F401`/`F841`.
- The precommit gate runs **`ruff check --fix .`** then **`ruff format .`**
  (`repo://.zerofactory/precommit.sh`). Do not introduce a `# noqa` or a style
  that the auto-fix would rewrite — the dispatcher re-runs the gate and re-spawns
  the builder on any diff, so keep output ruff-clean on the first pass.

## Tests: pytest, three tiers

`repo://tests/conftest.py` is the single source of truth for test fixtures and
the **hermetic environment defaults** that make every test safe to run without a
real factory: it sets `ZEROFACTORY_SKIP_GIT`, `ZEROFACTORY_SKIP_CRON_SYNC`,
`ZEROFACTORY_DISABLE_DISPATCHER`, and `ZEROFACTORY_SKIP_WORKER_SPAWN`
(`repo://tests/conftest.py#L18-L22`) and provides `test_db_path` /
`initialized_db`, `git_repo`, `api_client`, and `default_board` fixtures
(`repo://tests/conftest.py#L36-L106`).

Test tiers (mirrored on disk):

- **`tests/unit/`** — fast, isolated units per subsystem
  (`unit/dispatcher/`, `unit/cron/`, `unit/dashboard/`, `unit/scripts/`,
  `unit/issues/`).
- **`tests/integration/`** — the FastAPI REST surface via the `api_client`
  fixture (`test_tasks_api.py`, `test_boards_api.py`, `test_memories_api.py`,
  `test_settings_api.py`).
- **`tests/e2e/`** — hermetic multi-agent workflow and resilience simulations
  (`test_multi_agent_workflow.py`, `test_concurrency_resilience.py`,
  `test_cli_lifecycle.py`, `test_automation_scripts.py`, `test_plugin_api.py`).

The precommit gate runs **`python3 -m pytest tests/ -q`**
(`repo://.zerofactory/precommit.sh`). Add a regression test alongside any bug fix
— a fix without a test is not considered done.

## Dashboard CSS rebuild (mandatory when touching the UI)

Any change to `dashboard/dist/index.js` or `dashboard/input.css` **must** end with
`npm install && node dashboard/build_css.mjs` so `dist/style.css` is regenerated
byte-consistently, then committed. `build_css.mjs` is portable — it resolves the
`tailwindcss` package from the project's `node_modules` (walking up from the repo
root) or the `ZEROFACTORY_TAILWIND_DIR` override, with no machine-specific paths
(`repo://dashboard/build_css.mjs`). It is a *scoped* stylesheet: every Tailwind
utility used by `dist/index.js` is emitted, `zfk-*` keyframes are hoisted, and the
theme/utilities are wrapped in `@scope (.zerofactory-root)` so they cannot leak
into the host Hermes UI. `repo://tests/unit/dashboard/test_dashboard_css.py`
guards reproducibility and asserts the stylesheet carries selectors for every
referenced (including variant-prefixed) utility class.

## AI attribution on GitHub

Any agent-authored GitHub text (PR titles/bodies, review comments) **must**
begin with a **role-tagged** marker `[AI:<role>]` — e.g. `[AI:zf-builder]`,
`[AI:zf-reviewer]` — enforced by the role-aware `ai_prefix(text, role)` in
`repo://dispatcher/github_pr.py#L321-L335`). Text already carrying a role-tagged
marker is returned unchanged, so re-writes are idempotent and never double-prefix.
The reviewer submits verdicts
as `gh pr review --comment` (not `--approve` / `--request-changes`, which GitHub
blocks for the PR author's own token) with `[AI:zf-reviewer]`-tagged bodies
(`repo://dispatcher/worker_spawner.py#L127-L140`).

## What NOT to add

- No new class tokens / heavy dependencies to `dist/index.js` beyond what the
  committed `dist/style.css` already emits.
- No external `.github/workflows` or `CLAUDE.md` — wiki / precommit setup is
  driven natively via the Zero Factory dispatcher + Hermes cron.
- Never hand-write `openwiki/` Markdown or the `AGENTS.md` OpenWiki block; the
  OpenWiki MCP lifecycle owns both.

See [Quickstart](/openwiki/quickstart.md) for running the gates and
[Architecture](/openwiki/architecture.md) for the subsystem context.
