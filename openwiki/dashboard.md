# Dashboard (FastAPI Backend + UI)

The glassmorphic Kanban UI served at `/zerofactory` and its REST backend.
Back to [index](index.md).

## Backend architecture

- **`dashboard/plugin_api.py`** — the FastAPI plugin entry (declared in
  `dashboard/manifest.json` as `"api": "plugin_api.py"`). It imports the DB
  layer (`db.py`), Pydantic models (`models.py`), and each service, exposes
  helper functions used by the CLI (`__init__.py` imports from it), and
  mounts the master router.
- **`dashboard/routes/`** — one `APIRouter` per domain, aggregated by
  `routes/__init__.py::router` (include order: boards, tasks, stats, settings,
  dispatch, cron, memories, agents). Every route file uses the
  `try: from .x import … except: from x import …` dual-import pattern so the
  module works both as a package and flat-loaded by the plugin host.
- **Services** (business logic, DB-adjacent): `db.py` (connection + helpers),
  `openwiki_service.py`, `memory_service.py`, `precommit_service.py`,
  `session_service.py`.
- **UI**: `dist/index.js` (React) + `dist/style.css` (committed Tailwind v4
  build). Regenerate CSS with `npm install && node dashboard/build_css.mjs`
  (entry `input.css`); `tests/unit/dashboard/test_dashboard_css.py` guards it.

## Endpoints by module

### `routes/boards.py`
`GET /boards`, `POST /boards`, `POST /boards/test-clone`,
`PATCH|PUT /boards/{slug}`, `DELETE /boards/{slug}`,
`GET /boards/{slug}/precommit-status`, `POST /boards/{slug}/setup-precommit`,
`GET /boards/{slug}/openwiki-status`, `POST /boards/{slug}/setup-openwiki`.
(The last two back `openwiki_service.check_board_openwiki_status` /
`create_openwiki_setup_task` — the P0 setup task that generated this wiki.)

### `routes/tasks.py`
`GET /tasks` (filters: board, status, assignee, priority, search),
`POST /tasks`, `GET /tasks/{id}`, `GET /tasks/{id}/session`,
`GET /tasks/{id}/sessions`, `POST /tasks/{id}/stop`, `PATCH /tasks/{id}`,
`POST /tasks/{id}/move`, `DELETE /tasks/{id}`, `GET|POST /tasks/{id}/comments`,
`POST|DELETE /tasks/{id}/dependencies[/{parent_id}]`.

### `routes/dispatch.py`
`POST /dispatch/run`, `GET /dispatch/status`, `GET /health/stuck-tasks`,
`POST /health/reap-stuck`, `POST /tasks/{id}/reap`, `POST /import-legacy`.

### `routes/cron.py`
`GET /cron`, `POST|PUT /cron/scheduler/toggle`, `POST /cron/sync`,
`POST /cron/{job_id}/run`, `PUT|POST /cron/{job_id}`,
`POST|PUT /cron/{job_id}/toggle`, `POST|PUT /cron/{job_id}/reset`.

### `routes/memories.py`
`GET /memories`, `GET /boards/{slug}/memories` (category, q, limit, offset),
`POST /boards/{slug}/memories`, `PUT /memories/{memory_id}`,
`DELETE /memories/{memory_id}`.

### `routes/settings.py`
`GET /settings`, `PATCH|PUT /settings`, `POST /settings/langfuse/test`.

### `routes/stats.py`
`GET /stats?board=`, orchestrator scan activity helpers,
`GET /activities` (limit/offset/actor/assignee/action/board/search).

### `routes/agents.py`
`GET /sessions` (role/status/board filters), `GET /agents` (live agent card
status), `POST /sessions/{session_id}/stop`.

## DTOs (`models.py`)

Pydantic models: `BoardCreate/BoardUpdate/BoardTestClone`,
`TaskCreate/TaskUpdate/TaskMove`, `CommentCreate`, `DependencyLink`,
`CronJobUpdate`, `MemoryCreate/Update`, `SettingsUpdate`. Domain guards:
`VALID_STATUSES = {triage, todo, running, blocked, done}`,
`VALID_PRIORITIES = {P0..P3}`, `VALID_MEMORY_CATEGORIES`,
`MEMORY_CONTENT_MAX_LENGTH = 500`. Task statuses follow the lifecycle in
[index.md](index.md).

## OpenWiki service (`openwiki_service.py`)

- `OPENWIKI_RELATIVE_DIR = "openwiki"`; detects a board's wiki by checking
  `<repo_path>/openwiki/index.md` on disk (`check_board_openwiki_status`), and
  by finding the pending P0 setup task (dedup key `setup:openwiki`) —
  `create_openwiki_setup_task` files it via `routes/tasks.create_task`
  (category `config`, assignee `zf-builder`). `build_openwiki_setup_task_prompt`
  generates the builder instructions (this task was created that way).
