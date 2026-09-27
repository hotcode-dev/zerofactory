# Dispatcher (Autonomous Dispatch Engine)

`dispatcher/` turns `Todo`/`Running` tasks into spawned agent workers and PRs.
Back to [index](index.md).

## Entry points

- `scheduler.py::run_dispatch_cycle(db_path=None)` — one full autonomous cycle.
  Idempotent & concurrency-safe: acquires an `fcntl.flock` on
  `get_dispatcher_lock_path()` (plus `_dispatcher_lock` RLock); returns
  `{skipped: True, reason: "concurrent_cycle_active"}` if another process holds
  it. Returns counters `{dispatched, prs_opened, reaped, unblocked, promoted,
  scans_triggered}`.
- `scheduler.py::_dispatcher_loop()` / `start_background_dispatcher()` —
  background thread ticking `run_dispatch_cycle` every
  `DISPATCH_INTERVAL_SECONDS` (30s).
- Triggered from: `dashboard/routes/dispatch.py::trigger_dispatch`
  (`POST /dispatch/run`), the no-agent watchdog (`scripts/zf_queue_watchdog.py`,
  see [cron.md](cron.md)), and CLI `hermes zerofactory dispatch`.

## What one cycle does (`run_dispatch_cycle`)

1. Load global `settings` (`settings.py::load_settings`).
2. **Unblock** tasks whose parent dependencies are all `done`
   (`task_links`).
3. **Reap** finished workers (`reaper.reap_active_workers`) and **dispatch**
   ready `Todo` tasks → `Running`: for each, provision a worktree
   (`worktree.setup_worktree`), build the prompt (`context_builder`), and spawn
   the specialist worker (`worker_spawner.spawn_agent_worker`).
4. **Handle `Running` tasks whose worker finished**: run deterministic
   precommit (`worktree.run_deterministic_precommit`); on success commit,
   merge latest main, push, and **open the GitHub PR**
   (`github_pr` / `worktree` merge helpers); route to `zf-reviewer` in a fresh
   session. On precommit test failure, the builder receives the error logs and
   retries (max `DEFAULT_MAX_WORKER_RETRIES` = 3).
5. **Reviewer → outcome**: approval moves the task to `Blocked`
   (reason `Human Review & Merge`) until the PR is merged on GitHub (then the
   dispatcher moves it to `Done` and prunes the worktree); changes requested
   routes it back to `Todo` for `zf-builder` with imported PR comments.
6. **Scanners**: trigger idle improvement-scanner spawns
   (`scanner.spawn_board_scanner`) under global/per-board LLM capacity gates.

Config/limits in `dispatcher/config.py`: `DEFAULT_TASK_TIMEOUT_SECONDS` (3600),
`DEFAULT_INACTIVITY_TIMEOUT_SECONDS` (900), `DEFAULT_MAX_WORKER_RETRIES` (3),
`DISPATCH_INTERVAL_SECONDS` (30), `_dispatcher_lock`, plus settings-backed
max-active/concurrent values.

## Worktrees (`worktree.py`)

- `setup_worktree()` — creates an isolated worktree at
  `~/git/<repo>-worktrees/<task_id>` (branch `task/<task_id>`); resolves the
  board repo path (`cron/definitions.py::resolve_board_repo_path`, auto-clone).
- `resolve_task_repo_path()` — board repo root for a task.
- `run_deterministic_precommit(workspace_path)` — runs
  `.zerofactory/precommit.sh` (format → build → test), auto-staging
  auto-formatted changes; returns `(passed, output, exit_code)`.
- `pull_and_merge_main()` / `_handle_local_merge_conflict()` /
  `_handle_pr_conflict_from_github()` — merge latest main & reconcile conflict
  markers (see [conventions.md](conventions.md) gotcha on merge semantics).
- `_remove_worktree()` / `_delete_remote_branch()` — cleanup on `Done`.

## Git helpers (`git_ops.py`)

`get_default_branch`, `sync_repo_main`, `get_git_dir`, `clean_stale_git_locks`,
`pull_and_merge_main`, and conflict-marker detection
(`check_unresolved_conflicts`, `check_files_for_conflict_markers`,
`GitConflictCheckError`). Use these for any in-worktree git logic rather than
ad-hoc shell.

## GitHub PR & review (`github_pr.py`)

- `extract_gh_repo_info(pr_url)` → `(owner, repo, pr_number)`.
- `fetch_pr_review_comments(...)` — pulls review comments, filtering authors
  (`is_trusted_reviewer`, `is_excluded_author`) so only real reviewer feedback
  is imported.
- `is_reviewer_approval_comment(body, state)` / `format_task_comment_body` —
  map PR comments onto Kanban `task_comments`.

## Stuck-worker reaper (`reaper.py`)

- `reap_active_workers(cursor, now)` — reaps workers past inactivity/task
  timeouts (`_compute_stuck_state`), marks sessions ended, requeues with
  `outcome='timed_out'`/crash.
- `check_stuck_tasks()` / `reap_stuck_tasks(...)` — CLI `check-stuck` /
  `POST /health/reap-stuck`, `POST /tasks/{id}/reap`, `GET /health/stuck-tasks`.
- `process_manager.py`: `is_pid_alive`, `terminate_process_group`,
  `terminate_worker_process`, `stop_task_worker` (PGID-safe termination).

## Improvement scanner (`scanner.py`)

`spawn_board_scanner(board_slug, repo_path)` — launches the
`zf-orchestrator` improvement scanner under capacity gates:
`_global_llm_occupancy(running_tasks)` + per-board limits (see
[cron.md](cron.md) and [conventions.md](conventions.md) for the global LLM
capacity rule). `reap_active_scanners()`, `reset_idle_scanner_state()`.

See [zf-profiles.md](zf-profiles.md) for what each spawned worker does.
