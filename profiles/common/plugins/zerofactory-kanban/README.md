# Zero Factory Kanban Plugin

A dedicated, durable, high-performance Kanban board and task orchestration system for Zero Factory, integrated into the Hermes Agent Gateway.

## Motivation & Architecture

Upstream Hermes Kanban has undergone frequent breaking schema and API changes, making automated 24/7 multi-agent pipelines fragile. Furthermore, complex upstream features and brittle SQLite column schemas caused dispatch failures and data loss.

**Zero Factory Kanban** (`zerofactory-kanban`) replaces upstream Hermes Kanban with:
- **Durable Persistence**: Self-contained SQLite database (`~/.hermes/zerofactory_kanban.db`) configured with Write-Ahead Logging (`WAL` mode), explicit foreign keys, indexes, and a lean, strictly versioned schema.
- **Factory Lifecycle**: Purpose-built for Zero Factory's six lifecycle states:
  - `triage` — Ingested goals awaiting automated decomposition
  - `todo` — Sub-tasks queued for dispatcher assignment and worktree setup
  - `ready` — Unblocked tasks whose dependencies are satisfied, ready for specialist pickup
  - `running` — Actively being executed in isolated Git worktrees
  - `blocked` — Awaiting human PR review or parent tasks
  - `done` — Completed and merged
- **Modern Web Dashboard**: Fast, glassmorphic dark UI mounted directly into the Hermes Gateway web app at `/zerofactory-kanban`, supporting drag-and-drop, real-time metrics, board switching, task details drawer, and comment threads.
- **Built-in Dispatcher Engine**: Autonomous background engine handling dependency unblocking, WIP limit enforcement, specialist task assignment, git worktree provisioning, and GitHub PR review loops without requiring an external plugin.
- **Legacy Migration**: One-click import tool to migrate existing tasks from `~/.hermes/kanban.db` into the durable format without losing state.

---

## File Structure

```
profiles/common/plugins/zerofactory-kanban/
├── plugin.yaml               # Hermes plugin metadata
├── __init__.py               # Gateway startup hook, background loop & CLI commands
├── dispatcher.py             # Built-in dispatch engine (WIP limits, worktrees, PRs)
├── test_plugin.py            # Automated test suite (CRUD, API, transitions)
├── README.md                 # This documentation
└── dashboard/
    ├── manifest.json         # Dashboard route declaration (/zerofactory-kanban)
    ├── plugin_api.py         # FastAPI router (/api/plugins/zerofactory-kanban)
    └── dist/
        ├── index.js          # React Kanban UI (vanilla IIFE using Hermes SDK)
        └── style.css         # Glassmorphic dark theme stylesheet
```

---

## Database Schema

Database location: `~/.hermes/zerofactory_kanban.db` (can be overridden via `ZEROFACTORY_KANBAN_DB` environment variable).

### 1. `boards`
| Column | Type | Description |
|---|---|---|
| `slug` | `TEXT PRIMARY KEY` | Unique board identifier (slug) |
| `name` | `TEXT NOT NULL` | Human-readable board name |
| `description` | `TEXT` | Board description or target Git repository URL |
| `created_at` | `TEXT` | ISO 8601 timestamp |
| `updated_at` | `TEXT` | ISO 8601 timestamp |

### 2. `tasks`
| Column | Type | Description |
|---|---|---|
| `id` | `INTEGER PRIMARY KEY AUTOINCREMENT` | Task ID |
| `board_id` | `TEXT NOT NULL REFERENCES boards(id)` | Board task belongs to |
| `title` | `TEXT NOT NULL` | Concise task title |
| `description` | `TEXT` | Detailed prompt, context, or requirements |
| `status` | `TEXT NOT NULL` | `triage`, `todo`, `ready`, `running`, `blocked`, or `done` |
| `priority` | `TEXT NOT NULL` | `critical`, `high`, `medium`, or `low` |
| `assignee` | `TEXT` | Target agent profile (`builder`, `reviewer`, `orchestrator`) |
| `worktree_dir` | `TEXT` | Path to isolated Git worktree |
| `git_branch` | `TEXT` | Branch name associated with task |
| `pr_url` | `TEXT` | Associated GitHub Pull Request URL |
| `parent_id` | `INTEGER REFERENCES tasks(id)` | Direct parent task ID |
| `tags` | `TEXT DEFAULT '[]'` | JSON array of strings |
| `skills` | `TEXT DEFAULT '[]'` | JSON array of required skill names |
| `created_at` | `TEXT` | ISO 8601 creation timestamp |
| `updated_at` | `TEXT` | ISO 8601 update timestamp |
| `completed_at` | `TEXT` | ISO 8601 completion timestamp |

### 3. `task_links`
Tracks explicit parent-child or dependency links between tasks.
- `parent_id` (INTEGER REFERENCES tasks(id) ON DELETE CASCADE)
- `child_id` (INTEGER REFERENCES tasks(id) ON DELETE CASCADE)
- `link_type` (TEXT DEFAULT `'blocks'`)

### 4. `task_comments`
Discussion and agent execution logs for each task.
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `task_id` (INTEGER REFERENCES tasks(id) ON DELETE CASCADE)
- `author` (TEXT NOT NULL)
- `comment` (TEXT NOT NULL)
- `created_at` (TEXT)

### 5. `task_activity`
Audit log tracking every status transition, priority change, and edit.
- `id` (INTEGER PRIMARY KEY AUTOINCREMENT)
- `task_id` (INTEGER REFERENCES tasks(id) ON DELETE CASCADE)
- `event_type` (TEXT NOT NULL: `'status_change'`, `'create'`, `'comment'`, `'update'`)
- `old_value` (TEXT)
- `new_value` (TEXT)
- `actor` (TEXT)
- `created_at` (TEXT)

---

## REST API Reference

All routes are mounted on the Hermes Gateway at: `/api/plugins/zerofactory-kanban/`

### Boards
- `GET /boards`: List all boards with task counts.
- `POST /boards`: Create a new board (`{"id": "...", "name": "...", "description": "..."}`).

### Tasks
- `GET /tasks`: Query tasks.
  - Query params: `board` (board slug), `status`, `assignee`, `search`.
- `POST /tasks`: Create a new task.
  - Body: `{"title": "...", "board_slug": "zerofactory", "description": "...", "status": "todo", "priority": "P2", "assignee": "builder", "parent_id": null, "tags": [], "skills": []}`
- `GET /tasks/{task_id}`: Retrieve a task with all comments, links, and activity logs.
- `PATCH /tasks/{task_id}`: Partial update (e.g. title, description, status, priority, assignee, pr_url).
- `DELETE /tasks/{task_id}`: Delete a task and associated activity/comments.
- `POST /tasks/{task_id}/move`: Move a task to a new status (supports optional `position` ordering).
  - Body: `{"status": "ready"}`
- `POST /tasks/{task_id}/comments`: Add a comment or progress update.
  - Body: `{"body": "...", "author": "reviewer"}`

### Operations & Metrics
- `GET /stats?board=zerofactory`: Return column counts, total tasks, and completion metrics.
- `POST /dispatch`: Trigger an evaluation run of the built-in dispatcher engine.
- `POST /import-legacy`: Import legacy tasks from `~/.hermes/kanban.db` into `~/.hermes/zerofactory_kanban.db`.
- `GET /cron`: List all built-in Zero Factory cron jobs and their current status.
- `POST /cron/sync`: Synchronize built-in cron jobs with Hermes cron storage.
- `POST /cron/{job_id}/run`: Immediately trigger a built-in cron job.

---

## CLI Reference

The plugin registers CLI commands under `hermes zerofactory-kanban`:

```bash
# List all tasks formatted by status
hermes zerofactory-kanban list
hermes zerofactory-kanban list --board zerohub --status running

# Create a task
hermes zerofactory-kanban create "Refactor database pool" \
  --desc "Use WAL mode with 30s timeout" \
  --status todo \
  --priority high \
  --assignee builder

# Move or block a task
hermes zerofactory-kanban move 42 ready
hermes zerofactory-kanban block 42 --reason "Waiting on PR review"

# Add a comment
hermes zerofactory-kanban comment 42 "CI passed, ready for merge" --author reviewer

# View summary metrics
hermes zerofactory-kanban stats

# Manually trigger the dispatcher
hermes zerofactory-kanban dispatch

# Built-in Cron Management
hermes zerofactory-kanban cron list
hermes zerofactory-kanban cron sync
hermes zerofactory-kanban cron run zero-factory-improvement-scanner
```

---

## Web UI Dashboard

The web dashboard is accessed via the Hermes Agent Gateway at:
`http://localhost:9119/zerofactory-kanban`

Key UI Features:
1. **Header & Navigation**: Board dropdown switcher, New Board creation modal, "Run Dispatcher" action, and "Import Legacy" button.
2. **Metrics Bar**: Real-time counter cards for Total Tasks, In Progress, Blocked, Done, and Completion Rate.
3. **Filter Bar**: Live instant search by keyword across titles/descriptions, plus quick priority filters.
4. **Kanban Columns**: 6 styled columns with custom color badges (`Triage`, `Todo`, `Ready`, `Running`, `Blocked`, `Done`).
5. **Drag-and-Drop**: HTML5 drag-and-drop between columns automatically updates status via the move API and logs activity.
6. **Task Detail Drawer**: Click any card to inspect full details, edit attributes, view parent/child dependency links, browse the immutable activity log, and submit comments.
7. **New Task Modal**: Clean modal dialog to quickly input title, priority, assignee, parent ID, tags, and description.

---

## Automated Testing

Run the plugin's dedicated test suite:

```bash
python3 profiles/common/plugins/zerofactory-kanban/test_plugin.py
```

Tests cover:
- Database schema initialization and WAL mode validation
- Board creation and retrieval
- Task lifecycle transitions and activity recording
- Dependency linking and cascading deletes
- Comment threads
- FastAPI router endpoints via TestClient
