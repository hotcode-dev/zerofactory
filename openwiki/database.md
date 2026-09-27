# Database (`kanban.db`)

Durable SQLite substrate. Back to [index](index.md).

## Location & access

- Default path: `~/.hermes/zerofactory.db`; override with the
  **`ZEROFACTORY_DB`** env var (`dashboard/db.py::get_db_path`,
  `dispatcher/config.py::get_db_path`, `cron/config.py::DEFAULT_DB_PATH`).
- `dashboard/db.py::get_db_conn()` — contextmanager connection (WAL mode,
  `row_factory = sqlite3.Row`, `PRAGMA busy_timeout`).
- `init_db(force=False)` — creates the schema and **auto-applies pending
  migrations** (`migrations/runner.py::run_migrations`) in a transaction.
- Activity log: `log_activity(conn, task_id, actor, action, details)`;
  `prune_old_activity(conn, retention_days, vacuum)` (interval-gated,
  `ACTIVITY_PRUNE_INTERVAL_SECONDS = 3600`; retention from the
  `activity_retention_days` setting).
- ID/slug helpers: `generate_task_id(board_slug)`, `derive_board_code(board_slug)`,
  `parse_git_url(git_url)`, `row_to_dict(row)`.

## Schema (migrations 0001 + 0002)

Defined in `migrations/0001_initial_schema.sql` and
`0002_add_board_settings.sql`; applied & tracked in the `schema_migrations`
table (`version`, `applied_at`). Migrations run in alphabetical order; the
runner tolerates `duplicate column name` / `already exists` (idempotent
re-runs). See `migrations/README.md` for how to add one (new `NNNN_name.sql`).

### `boards`
`slug PK`, `description`, `git_url`, `target_branch` (default `''`),
`max_concurrent_running INT DEFAULT 1`, `auto_record_memory INT DEFAULT 1`
(0/1), `additional_reviewer_usernames TEXT '[]'` (JSON list), `created_at`,
`updated_at`.

### `tasks`
`id PK` (e.g. `zf-<boardcode>-<hash>`), `board_slug`, `title`, `description`,
`status` (one of `triage|todo|running|blocked|done` per `VALID_STATUSES` in
`dashboard/models.py`; the dispatcher also handles the internal `ready`
status — `dispatcher/scheduler.py` claims rows with `status IN ('todo',
'ready')`, so `ready` rows are valid dispatchable tasks, not corrupt data), `assignee` (a
`zf-*` profile, `human`, or `unassigned`), `priority` (`P0`–`P3`),
`workspace_path`, `workspace_kind` (default `worktree`), `branch_name`,
`pr_url`, `tenant`, `skills TEXT '[]'`, `tags TEXT '[]'`,
`metadata TEXT '{}'` (sessions, retries, outcomes — **not** a JSON column;
parse with `json.loads`), `created_at`, `updated_at`.

### `task_links` (dependencies)
`parent_id`, `child_id`, `created_at`. A `todo` task promotes to `ready`/
dispatch only when **all** parents are `done`. Indexes on both columns.

### `task_comments`
`id PK AUTOINCREMENT`, `task_id`, `author`, `body`, `created_at`.
Imported from GitHub PR review comments on changes-requested handoffs.

### `task_activity`
`id PK AUTOINCREMENT`, `task_id`, `actor`, `action`, `details`, `created_at`.
Pruned by retention; powers the dashboard activity feed.

### `settings`
`key PK`, `value TEXT`, `updated_at`. Keys & defaults in `settings.py`
(`SETTING_KEYS`, `load_settings`) — e.g. `max_active_tasks` (10),
`max_concurrent_llm_workers` (10), `scan_on_idle` (true),
`idle_scan_active_threshold` (2), `idle_scan_cooldown_minutes` (15),
`idle_scan_max_todo` (2), `enable_cron_scheduler` (true), `auto_record_memory`
(true), plus `langfuse_*` keys.

### `board_memories`
`id PK`, `board_slug`, `task_id`, `category` (`general` default; also
`convention`, `gotcha`, `decision`, `rejected_path`), `content`
(≤ `MEMORY_CONTENT_MAX_LENGTH` = 500), `tags TEXT '[]'`, `author`,
`created_at`, `updated_at`. Pre-digested into worker prompts by
`context_builder.digest_board_memories_context` — see [zf-profiles.md](zf-profiles.md).
Indexes: `idx_memories_board`, `idx_memories_category`,
`idx_memories_board_content`.

### Indexes
`idx_tasks_board_status`, `idx_tasks_assignee`, `idx_tasks_status`,
`idx_links_parent`, `idx_links_child`, `idx_comments_task`,
`idx_activity_task`, `idx_activity_created`, `idx_activity_actor`,
`idx_memories_*`.

## Environment variables

| Var | Effect |
|---|---|
| `ZEROFACTORY_DB` | Kanban DB path override |
| `ZEROFACTORY_SCANNER_STATE` | Scanner gate state-file override (`paths.py`) |

`scripts/zf_scanner_gate.py` uses `~/.hermes/scanner_state.json` by default
(atomic JSON read-modify-write under a lock file).

## Test isolation

Tests never touch the real DB: `tests/conftest.py` provides the hermetic
`initialized_db` fixture and sets `ZEROFACTORY_DB`/related env to
`tmp_path` before importing the plugin layer. **Trust the full
`python3 -m pytest tests/` (or `./.zerofactory/precommit.sh test`) run, not
isolated module runs** — several e2e cases depend on boards set up by earlier
tests in the same process.
