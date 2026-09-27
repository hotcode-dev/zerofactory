# Test Suite

3 tiers, 35 test files. Back to [index](index.md).

## Layout

```
tests/
├── conftest.py                     # Shared fixtures: hermetic env (ZEROFACTORY_DB→tmp),
│                                   #   initialized_db fixture, plugin-import helpers
├── unit/
│   ├── test_paths.py, test_profile_manager.py, test_settings.py
│   ├── cron/        test_cron_{definitions,executor,manager,scheduler_check,store}.py
│   ├── dashboard/   test_dashboard_css.py, test_db_helpers.py, test_memory_service.py,
│   │               test_models.py, test_openwiki_service.py, test_precommit_service.py
│   ├── dispatcher/  test_{context_builder,exception_hygiene,git_ops,precommit_dispatcher,
│   │               process_manager,reaper,scheduler,worker_spawner,worktree}.py
│   └── scripts/     test_zf_{daily_stats,queue_watchdog,scanner_gate}.py
├── integration/   # FastAPI route tests (TestClient):
│   test_boards_api.py, test_tasks_api.py, test_memories_api.py, test_settings_api.py
└── e2e/           # Hermetic full-workflow & resilience (hermes CLI mocked at the
    test_cli_lifecycle.py, test_multi_agent_workflow.py,
    test_plugin_api.py, test_automation_scripts.py, test_concurrency_resilience.py
    subprocess boundary)
```

## Running

```bash
python3 -m pytest tests/            # everything (what .zerofactory/precommit.sh runs)
python3 -m pytest tests/unit/ tests/integration/ tests/e2e/
python3 -m pytest tests/unit/dispatcher/test_reaper.py -q   # single file
```

Framework: **pytest** (declared by `tests/conftest.py`); `unittest` discovery
is only a fallback when pytest is missing.

## Hermeticity rules (important when writing tests)

- `conftest.py` points `ZEROFACTORY_DB` at a `tmp_path` database **before**
  importing plugin modules; the `initialized_db` fixture returns that path.
  Never point tests at `~/.hermes/zerofactory.db`.
- E2e tests model the dispatcher by driving `run_dispatch_cycle()` and mocking
  the `hermes` subprocess spawn boundary; task metadata (sessions, retries)
  must be modeled realistically — main's reaper semantics (orphan recovery,
  session isolation) can silently break harnesses that fake it.
- **Judge test health by the FULL suite run** (`pytest tests/`), not isolated
  `-m unittest` or single-file runs — later tests depend on boards/fixtures
  set up by earlier ones in the same process.
- Dashboard CSS guard: `tests/unit/dashboard/test_dashboard_css.py` asserts
  `dashboard/dist/style.css` is reproducible and covers every variant-prefixed
  class the UI references — regenerate via `node dashboard/build_css.mjs`
  after touching `input.css`/UI classes.

## Known pre-existing failures (as of base main, not PR regressions)

A test failing **identically at `git merge-base main <head>`** is a pre-existing
base failure, not a regression:

- `test_plugin.py::test_36c_author_handoff_with_existing_pr_url`
- `test_e2e.py::test_01_cli_setup_and_sync_profiles`
- `test_e2e.py::test_02_reviewer_changes_requested_loop`
  (asserts `'zf-builder' == 'zf-reviewer'` at clean main)

Verify at the merge-base before attributing a failure to your change.
