# Conventions & Architectural Decisions

High-signal rules for coding agents. Back to [index](index.md).

## Style & tooling

- **Python 3.10+** (`from __future__ import annotations`; modern `X | None`
  unions). Lint/format with **ruff** (`ruff.toml` at repo root;
  `./.zerofactory/precommit.sh` runs `ruff check --fix` + `ruff format`).
- **Surgical diffs only** — targeted hunks, no drive-by reformatting, no
  speculative abstractions (Ponytail 7-Rung Ladder of Laziness; see
  `skills/zf-builder-ponytail/` and `skills/ponytail/LADDER.md`):
  stdlib-first, reuse before create, flat > nested.
- **No new runtime dependencies** unless the task requires it; `package.json`
  exists only for the dashboard CSS build (`tailwindcss` devDependency).
- **Dual-import pattern**: every dashboard/dispatcher module does
  `try: from .x import … except (ImportError, ValueError): from x import …`
  (relative when loaded as a package, flat when loaded by the plugin host).
  Keep this pattern when adding imports to those modules.
- Markdown/README: keep `AGENTS.md` in sync (it **symlinks to README.md**).

## Module contracts

- `paths.py` is the **single source of truth** for profile identity —
  `PROFILE_MAP`, `normalize_assignee`, `VALID_ASSIGNEES`,
  `resolve_profile_state_db`. Do not re-declare the profile list elsewhere.
- `builtin_cron.py` is a **re-export facade** for cron helpers (the
  dispatcher/dashboard import through it; tests monkeypatch it there).
- `dashboard/plugin_api.py` owns the FastAPI app + CLI-facing helper imports;
  routes stay in `dashboard/routes/`, business logic in `dashboard/*_service.py`.
- Task `metadata` is a **JSON string column** — parse/serialize with
  `json.loads`/`json.dumps`; never treat it as a dict column.
- DB access goes through `dashboard/db.py::get_db_conn()` (or
  `dispatcher/config.py::get_db_path` + `sqlite3` with `PRAGMA busy_timeout`).
  Never open the default `~/.hermes/zerofactory.db` path directly in code that
  must respect `ZEROFACTORY_DB`.

## Workflow conventions

- **Never edit `main` directly** — all agent work happens in
  `~/git/<repo>-worktrees/<task_id>` (branch `task/<task_id>`).
- **Never `git add/commit/push` manually in a task worktree** — the dispatcher
  runs `.zerofactory/precommit.sh` (format → build → test, up to 3 fix
  retries), then commits, merges main, pushes, and opens the PR.
- Review handoff: `hermes zerofactory move <id> blocked --reason
  "review-required"`; approved PR: `block <id> --reason "Human Review &
  Merge"` (human merges; dispatcher auto-completes to `done` — do **not**
  self-mark done).
- Commit messages: `type(scope): summary` (see
  `context_builder.format_conventional_message`).
- Knowledge capture: prefix review/block/comment lines with `GOTCHA:` /
  `CONVENTION:` / `DECISION:` etc. to auto-record into `board_memories`
  (categories + toggles in [zf-profiles.md](zf-profiles.md)).

## Environment variables

| Var | Purpose |
|---|---|
| `ZEROFACTORY_DB` | Kanban DB path override (all layers) |
| `ZEROFACTORY_SCANNER_STATE` | Scanner state-file override |
| `HERMES_LANGFUSE_*` | Injected into worker env when `langfuse_enabled` |
| `ZEROFACTORY_TAILWIND_DIR` | Tailwind resolution dir for CSS builds |
| `GIT_TERMINAL_PROMPT=0` | Set by all git subprocesses (no interactive auth) |

## Known gotchas (from repo memory)

- **Destroyed cwd**: if the session worktree is deleted mid-run, terminal cwd
  becomes a dead path; pin `workdir=` per call and verify `patch` results with
  `git diff` (a post-write chdir can return spurious ENOENT even when the edit
  applied).
- **Merge-then-retest**: after merging main into a task branch, re-run the PR's
  OWN new regression tests — main's reaper/session semantics can silently break
  the test harness.
- **Pre-existing failures**: reproduce failures at
  `git merge-base main <head>` before blaming your change (see [tests.md](tests.md)).
- **Test health**: trust the full `pytest tests/` run over isolated runs.

## Precommit pipeline (`.zerofactory/precommit.sh`)

`all|format|build|test|install-hook`:
- `format` — ruff required (auto-installed via uv/pip if missing); fails hard
  if unavailable.
- `build` — `python3 -m compileall -q .` (no other build system exists).
- `test` — `python3 -m pytest tests/ -q` (unittest-discovery fallback).
