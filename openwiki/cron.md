# Cron & Background Automation

Token-efficient periodic jobs: mostly **No-Agent** (0 LLM tokens) with
wake-gate change detection. Back to [index](index.md).

## Builtin job catalog (`cron/definitions.py`)

`CORE_CRON_JOBS` + dynamic per-board scanner jobs are assembled by
`get_all_builtin_cron_jobs()`; `build_board_scanner_prompt(board, workdir)`
renders the orchestrator scan prompt. Job specs include `id`, `name`,
`prompt`, `script`, `no_agent`, `schedule` (`{kind: interval, minutes,
display}`), `enabled`, `state`, `profile`, `workdir`, `enabled_toolsets`.

| Job ID | Schedule | Mode | What it does |
|---|---|---|---|
| `zero-factory-task-queue-check` | every 120m | **No-Agent** (`no_agent: true`, `script: zf_queue_watchdog.py`) | Python-only watchdog: audits running workers, reaps stuck subprocesses, triggers `run_dispatch_cycle()`. Healthy queue ⇒ exits with `{"wakeAgent": false}` (0 tokens); bottleneck ⇒ human-readable alert to the operator. |
| `zero-factory-improvement-scanner-{board_slug}` | on idle (active < 2), per board | Agent (wake-gated, `continuity: false`, `script: zf_scanner_gate.py` as pre-screen) | `zf-orchestrator` scans the repo for tech debt/refactor/missing tests and files **at most 1** actionable `Todo` for `zf-builder`. Busy board (`running ≥ 2` or `todo ≥ 2`) or 15-min cooldown ⇒ `{"wakeAgent": false}` (0 tokens). |

## No-Agent scripts (`scripts/`)

- **`zf_queue_watchdog.py::run_watchdog()`** — the queue-check script.
  Resolves the plugin root from several candidate locations, then reaps and
  dispatches. Consumes no LLM.
- **`zf_scanner_gate.py::run_scanner_gate()`** — pre-screens the board before
  waking the orchestrator: `get_active_pipeline_task_count`,
  `get_board_pipeline_capacity`, `get_existing_task_titles`,
  `has_task_on_or_after_commit`, `is_llm_reachable(timeout)`,
  `mark_task_created(board_slug)` (state in `~/.hermes/scanner_state.json`,
  atomic writes + lock file), `_auto_sync_repo`, `resolve_board_slug`.
- **`zf_daily_stats.py::run_daily_stats()`** — deterministic 24h metrics /
  velocity calculator from `kanban.db` (no LLM).

## Job management (`cron/manager.py`, `executor.py`, `store.py`)

- `manager.py`: `ensure_builtin_cron_jobs()`, `prune_board_cron_job(slug)`,
  `list_builtin_jobs()`, `update_builtin_job(job_id, updates)`,
  `toggle_builtin_job(job_id, enabled)`, `reset_builtin_job(job_id)`.
- `executor.py`: `trigger_builtin_job(job_id)`, `tick_builtin_cron()`;
  timeouts in `cron/config.py` (`CRON_RUN_TIMEOUT` = 300s,
  `CRON_RUN_OUTPUT_TAIL_CHARS` = 2048).
- `store.py`: `compute_job_next_run`, job-file load/save
  (`get_target_jobs_files`), `cleanup_duplicate_root_jobs`.
- `scheduler_check.py`: `is_cron_scheduler_enabled()` /
  `set_cron_scheduler_enabled()` — global `enable_cron_scheduler` setting.
- `builtin_cron.py` — public re-export facade (`__all__`): **import cron
  helpers through it** so tests can monkeypatch a single seam.

## Capacity gating (global LLM capacity)

`dispatcher/scanner.py::_global_llm_occupancy(running_tasks)` +
`_running_cron_llm_jobs()` enforce the **Settings → Global Max Concurrent LLM
Workers** cap across all boards: running task agents and in-flight scanners
share the budget (e.g. cap 3 with 2 running tasks + 1 scanner leaves no
slot). Per-board `max_concurrent_running` and `max_active_tasks` (WIP) apply
independently. No-Agent queue checks never consume LLM capacity.

Dashboard surface: `routes/cron.py` (list/sync/run/toggle/reset jobs,
scheduler toggle) and CLI `hermes zerofactory cron list|sync|run <job_id>`.
