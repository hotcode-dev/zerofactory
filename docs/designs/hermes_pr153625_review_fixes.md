# Fix NousResearch/hermes-agent#153625 Maintainer Review

*   **Author:** ntsd
*   **Status:** Proposed
*   **Date:** 2026-11-14

--------------------------------------------------------------------------------

## Overview

This design resolves the three blocking issues and two non-blocking recommendations from `teknium1`'s `CHANGES_REQUESTED` review (`PRR_kwDOPRF1G88AAAABXvJlBQ`) on `NousResearch/hermes-agent#153625`. The changes bring `zerofactory` into compliance with Hermes plugin catalog security, opt-in execution, and `HERMES_HOME` portability requirements without altering the core Kanban or dispatcher architecture.

## The Problem

1. **Private Mem0 fallback and `OPENAI_API_KEY` leakage**: When no user `base_url` is configured, `dashboard/memory_service.py` falls back to `https://spark.ntsd.dev:8001/v1` and `RadixArk/Qwen3.8-27B-NVFP4` (also mirrored in `settings.py` and `dashboard/src/modals/SettingsModal.jsx` placeholders). Because `mem0_enabled` defaults to `True` and `extract_and_record_memory()` omits `infer=False`, repo text and the user's `OPENAI_API_KEY` can be sent to that host or to any custom `base_url`.
2. **Un-gated gateway tick hook**: In `__init__.py`, `on_kanban_dispatch_tick` unconditionally calls `run_dispatch_cycle()`. Once `zerofactory.db` exists, any running Hermes gateway spawns workers, pushes branches, and opens PRs even when `auto_start_dispatcher` is `False`.
3. **Split-brain database and state paths**: `dispatcher/config.py`, `dashboard/memory_service.py`, `migrations/runner.py`, `scripts/zf_openwiki_gate.py`, `scripts/zf_daily_stats.py`, `dashboard/db.py`, and `dashboard/routes/stats.py` still hardcode `Path.home() / ".hermes"` instead of `paths.get_hermes_home()`, causing different components to read or write different files under a custom `HERMES_HOME`.
4. **Outdated documentation**: `README.md` still shows workers running with `--yolo` unconditionally (line 195) and does not document `mem0` as an optional dependency.

## Goals

*   Make Mem0 opt-in (`mem0_enabled: false` by default) so no vector-store initialization or external calls occur unless explicitly enabled by the user.
*   Remove all `https://spark.ntsd.dev:8001/v1` and `RadixArk/Qwen3.8-27B-NVFP4` defaults and UI placeholders for new installs.
*   Isolate `OPENAI_API_KEY` so it is only used for OpenAI's official endpoint (`api.openai.com` or unset `base_url`), never forwarded to custom endpoints.
*   Enforce `infer=False` on all `client.add()` calls and omit the `"llm"` block when no LLM endpoint/key is configured (returning `None` cleanly if `mem0` rejects it, falling back to SQLite `board_memories`).
*   Gate `on_kanban_dispatch_tick` in `__init__.py` so it returns early without calling `run_dispatch_cycle()` unless `_should_auto_start_dispatcher()` is `True` or `hermes zerofactory start` is actively running.
*   Unify all runtime DB, config, and state paths onto `paths.get_hermes_home()`.
*   Update `README.md` for opt-in `--yolo` execution and optional `mem0` dependency, and rebuild `dashboard/dist/index.js`.
*   Add unit tests verifying key isolation, tick gating, and `HERMES_HOME` path overrides.

## Non-Goals

*   Adding a database migration to scrub `RadixArk/Qwen3.8-27B-NVFP4` from pre-existing user `settings` rows.
*   Supporting LLM-inferred Mem0 extraction (`infer=True`) without a user-configured LLM endpoint.
*   Re-pinning `sha:` in `NousResearch/hermes-agent` (`plugin-catalog/zerofactory.yaml`), which occurs in the upstream PR after these changes land.

## Critical User Journeys (CUJs)

### CUJ 1: Clean Plugin Install Under Hermes Gateway
*   **Given**: A user installs `zerofactory` with default settings (`auto_start_dispatcher: false`, `mem0_enabled: false`) and `OPENAI_API_KEY` set in their environment.
*   **When**: The Hermes gateway loads the plugin and fires `on_kanban_dispatch_tick` after `zerofactory.db` is created.
*   **Then**: `on_kanban_dispatch_tick` returns early without spawning workers or opening PRs, and no network requests or `OPENAI_API_KEY` transmissions occur for Mem0.

### CUJ 2: Custom `HERMES_HOME` Isolation
*   **Given**: `HERMES_HOME` is set to a custom directory (e.g., `/tmp/hermes-test`).
*   **When**: The dispatcher, migrations, dashboard routes, `zf_openwiki_gate.py`, or `zf_daily_stats.py` resolve the database, config, or state files.
*   **Then**: Every component reads and writes under `$HERMES_HOME` rather than `~/.hermes`.

### CUJ 3: Opt-In Mem0 with Local FastEmbed or Custom Endpoint
*   **Given**: A user enables `mem0_enabled: true` in settings.
*   **When**: `mem0_embedder_provider` is `fastembed` with no custom `base_url` (or with a custom `base_url` and `MEM0_API_KEY`).
*   **Then**: All `client.add()` calls pass `infer=False`, `OPENAI_API_KEY` is never sent to a custom `base_url`, and if `mem0` fails to initialize without an LLM block, `get_mem0_client()` returns `None` while SQLite `board_memories` continues working.

## Technical Plan (Architecture)

The fix spans four localized workstreams without changing the SQLite schema, Kanban state machine, or dispatcher worker protocol.

### 1. Mem0 Sanitization, Credential Isolation & Opt-In Default

```text
get_mem0_client(conn)
  ├── settings.get("mem0_enabled", False) == False ──► return None (SQLite board_memories only)
  └── mem0_enabled == True
        ├── base_url resolved from: settings -> MEM0_BASE_URL -> OPENAI_BASE_URL -> hermes config.yaml -> ""
        ├── _is_openai_official_url(base_url)?
        │     ├── True  (empty or api.openai.com) ──► allow MEM0_API_KEY -> OPENAI_API_KEY
        │     └── False (custom host)              ──► allow mem0_api_key -> MEM0_API_KEY -> "dummy-key" (NEVER OPENAI_API_KEY)
        ├── llm_config included ONLY if (base_url or api_key for OpenAI) and llm_model are present
        └── Memory.from_config(config) ──► on ValueError/Exception, return None (SQLite fallback)
```

*   **Opt-in Default**: Change `DEFAULT_MEM0_ENABLED` in `settings.py` and the fallback in `dashboard/memory_service.py:129` (`settings.get("mem0_enabled", False)`) to `False`.
*   **Remove Private Defaults**: Clear `DEFAULT_MEM0_MODEL = ""` in `settings.py:99`, remove `"RadixArk/Qwen3.8-27B-NVFP4"` and `"https://spark.ntsd.dev:8001/v1"` from `dashboard/memory_service.py:91,97`, and replace the matching placeholders in `dashboard/src/modals/SettingsModal.jsx:227,242` with generic examples (e.g., `gpt-4o-mini` / `https://api.openai.com/v1`). Rebuild `dashboard/dist/index.js`.
*   **Credential Isolation**: Add `_is_openai_official_url(base_url: str) -> bool` using `urllib.parse.urlparse(base_url).hostname`. Only fall back to `os.environ.get("OPENAI_API_KEY")` when `base_url` is empty or its hostname is `api.openai.com`. Custom endpoints never receive `OPENAI_API_KEY`.
*   **Enforce `infer=False`**: Add `infer=False` to `client.add(...)` in `extract_and_record_memory()` (`dashboard/memory_service.py:519`) so it matches `mem0_add_memory()`. Omit the `"llm"` dict from `Memory.from_config(config)` when no LLM endpoint/key is configured; if `mem0` rejects a missing `"llm"` block, `get_mem0_client()` catches the exception and returns `None`.

### 2. Gateway Tick Hook Gating (`on_kanban_dispatch_tick`)

```text
Hermes Gateway Tick ──► on_kanban_dispatch_tick()
                          ├── _should_auto_start_dispatcher() == True  ──► run_dispatch_cycle()
                          ├── _is_dispatcher_daemon_running() == True  ──► run_dispatch_cycle()
                          └── both False ──► return {"ok": True, "skipped": True, "reason": "dispatcher_disabled"}
```

*   `hermes zerofactory start` (`__init__.py` `cmd_run` `action == "start"`) acquires an exclusive non-blocking `fcntl.flock` on `get_hermes_home() / "zerofactory_daemon.lock"` for the lifetime of the foreground dispatcher process.
*   `_is_dispatcher_daemon_running()` attempts `fcntl.flock(fd, LOCK_EX | LOCK_NB)` on that lock file: if `BlockingIOError` is raised, a `hermes zerofactory start` process is active.
*   `on_kanban_dispatch_tick` checks `_should_auto_start_dispatcher() or _is_dispatcher_daemon_running()` before invoking `run_dispatch_cycle()`.

### 3. `HERMES_HOME` Path Unification

*   Replace all remaining module-level or hardcoded `Path.home() / ".hermes"` / `~/.hermes` runtime paths with lazy helper calls backed by `paths.get_hermes_home()`:
    *   `dispatcher/config.py`: `get_db_path()` returns `get_hermes_home() / "zerofactory.db"`.
    *   `dashboard/memory_service.py`: `get_hermes_model_defaults()` reads `get_hermes_home() / "config.yaml"`.
    *   `migrations/runner.py`: `_resolve_default_db_path()` falls back to `get_hermes_home() / "zerofactory.db"`.
    *   `scripts/zf_openwiki_gate.py`: use `get_hermes_home() / "plugins" / "zerofactory"`, `get_hermes_home() / "openwiki_state.json"`, and `get_hermes_home() / "zerofactory.db"` lazily via helper functions.
    *   `scripts/zf_daily_stats.py`: prepend repo root to `sys.path`, import `get_hermes_home`, and resolve `zerofactory.db` lazily.
    *   `dashboard/db.py`: remove or derive `DEFAULT_DB_PATH` from `get_hermes_home()`.
    *   `dashboard/routes/stats.py`: resolve `get_hermes_home() / "profiles" / "zf-orchestrator" / "cron" / "executions.db"`.

### 4. Documentation (`README.md`)

*   Update `README.md:195` to show opt-in `--yolo` behavior (`allow_unattended_approvals`) instead of an unconditional `--yolo` command.
*   Document `mem0` (`mem0ai`, `fastembed`, `qdrant-client`) as an optional dependency with automatic SQLite `board_memories` fallback.

## Alternatives Considered

### Alternative A: Disable Mem0 Whenever No LLM Endpoint Is Configured
*   **Pros**: Guarantees `mem0.Memory.from_config()` never fails on a missing `"llm"` block and eliminates conditional config assembly.
*   **Cons**: Breaks local-only `fastembed` vector indexing (`infer=False`) for users who enable `mem0_enabled` without an external LLM endpoint.
*   **Reason for Rejection**: Rejected by author: omitting `"llm"` when unconfigured and catching validation errors preserves local `fastembed` when supported while failing safely to `None`.

### Alternative B: Gate `on_kanban_dispatch_tick` Solely on `_should_auto_start_dispatcher()`
*   **Pros**: Requires no daemon lock file or `fcntl.flock` check; `hermes zerofactory start` already runs its own `run_dispatch_cycle()` loop.
*   **Cons**: Gateway ticks would skip even when a user intentionally started `hermes zerofactory start` with `auto_start_dispatcher: false`, diverging from `teknium1`'s review guidance (`PRR_kwDOPRF1G88AAAABXvJlBQ`).
*   **Reason for Rejection**: Rejected by author: adding a lightweight `zerofactory_daemon.lock` check satisfies both opt-in paths with minimal code.

### Alternative C: Patch Only the Six File Paths Named in the Review
*   **Pros**: Slightly smaller diff.
*   **Cons**: Leaves `dashboard/db.py:107` (`DEFAULT_DB_PATH`) and `dashboard/routes/stats.py:109,153` (`executions.db`) hardcoded to `~/.hermes`, causing split-brain stats queries under a custom `HERMES_HOME`.
*   **Reason for Rejection**: Rejected by author: routing all runtime `.hermes` references through `paths.get_hermes_home()` keeps path resolution consistent.

--------------------------------------------------------------------------------

## Non-Functional Requirements

*   **Security & Privacy**: `OPENAI_API_KEY` is never sent to non-OpenAI `base_url` hosts, private URLs (`spark.ntsd.dev`) are removed from code and UI, and `mem0_enabled` defaults to `False` so no data leaves the machine on fresh installs.
*   **Backward Compatibility**: Existing `settings` rows containing `RadixArk/Qwen3.8-27B-NVFP4` are left untouched; users who already enabled Mem0 retain their stored `mem0_enabled` setting in SQLite.

--------------------------------------------------------------------------------

## Detailed Implementation Plan

### Target Files to Create/Modify

#### 1. `settings.py` (Modify)
*   **Type / Scope**: Python Settings & Defaults
*   **Proposed Changes**: Change `DEFAULT_MEM0_MODEL` from `"RadixArk/Qwen3.8-27B-NVFP4"` to `""` and change the default `mem0_enabled` setting from `True` to `False` so Mem0 is opt-in on fresh installs and no private model name is seeded.

#### 2. `dashboard/memory_service.py` (Modify)
*   **Type / Scope**: Python Service (Mem0 Client & Memory Extraction)
*   **Proposed Changes**:
    *   In `get_hermes_model_defaults()`: read `paths.get_hermes_home() / "config.yaml"` instead of `Path.home() / ".hermes" / "config.yaml"`; remove `"RadixArk/Qwen3.8-27B-NVFP4"` and `"https://spark.ntsd.dev:8001/v1"` fallbacks (default both to `""`).
    *   Add `_is_openai_official_url(base_url: str) -> bool` returning `True` only when `base_url` is empty or its parsed hostname is `api.openai.com`. Only fall back to `OPENAI_API_KEY` when `_is_openai_official_url(base_url)` is `True`; custom `base_url` endpoints only receive `mem0_api_key` / `MEM0_API_KEY` (or `"dummy-key"` when unauthenticated).
    *   In `get_mem0_client()`: change `settings.get("mem0_enabled", True)` to `settings.get("mem0_enabled", False)`. Omit the `"llm"` block from `Memory.from_config(config)` when no LLM endpoint/key is configured; catch any validation error and return `None` to fall back to SQLite `board_memories`.
    *   In `extract_and_record_memory()`: pass `infer=False` to `client.add(...)` to match `mem0_add_memory()`.

#### 3. `dashboard/src/modals/SettingsModal.jsx` and `dashboard/dist/index.js` (Modify)
*   **Type / Scope**: Frontend UI & Compiled Bundle
*   **Proposed Changes**: Replace the `RadixArk/Qwen3.8-27B-NVFP4` and `https://spark.ntsd.dev:8001/v1` input placeholders in `SettingsModal.jsx` with generic placeholders (e.g., `gpt-4o-mini (inherited from ~/.hermes/config.yaml)` and `https://api.openai.com/v1 (inherited from ~/.hermes/config.yaml)`), then rebuild `dashboard/dist/index.js`.

#### 4. `__init__.py` (Modify)
*   **Type / Scope**: Plugin Entrypoint & Hook Registration
*   **Proposed Changes**:
    *   Add `_get_daemon_lock_path()` (`get_hermes_home() / "zerofactory_daemon.lock"`) and `_is_dispatcher_daemon_running()` (non-blocking `fcntl.flock(LOCK_EX | LOCK_NB)` probe).
    *   In `cmd_run()` for `action == "start"`, acquire and hold the exclusive `zerofactory_daemon.lock` for the lifetime of the foreground dispatcher loop.
    *   Replace the unconditional `on_kanban_dispatch_tick` lambda with a handler that checks `_should_auto_start_dispatcher() or _is_dispatcher_daemon_running()` and returns `{"ok": True, "skipped": True, "reason": "dispatcher_disabled"}` immediately when both are `False`.

#### 5. `dispatcher/config.py` (Modify)
*   **Type / Scope**: Dispatcher Configuration
*   **Proposed Changes**: Update `get_db_path()` to return `get_hermes_home() / "zerofactory.db"` (respecting `ZEROFACTORY_DB` override) instead of `Path.home() / ".hermes" / "zerofactory.db"`.

#### 6. `migrations/runner.py` (Modify)
*   **Type / Scope**: Database Migration Runner
*   **Proposed Changes**: Update `_resolve_default_db_path()` fallback to call `paths.get_hermes_home() / "zerofactory.db"` instead of `Path.home() / ".hermes" / "zerofactory.db"`.

#### 7. `scripts/zf_openwiki_gate.py` (Modify)
*   **Type / Scope**: Standalone Cron/Gate Script
*   **Proposed Changes**: Replace `Path.home() / ".hermes" / "plugins" / "zerofactory"`, `STATE_FILE`, and `DEFAULT_DB_PATH` module-level constants with lazy helpers backed by `paths.get_hermes_home()`.

#### 8. `scripts/zf_daily_stats.py` (Modify)
*   **Type / Scope**: Standalone Daily Stats Script
*   **Proposed Changes**: Ensure `Path(__file__).resolve().parent.parent` is inserted into `sys.path` before importing `paths`, and replace `DEFAULT_DB_PATH` with a lazy helper returning `get_hermes_home() / "zerofactory.db"`.

#### 9. `dashboard/db.py` (Modify)
*   **Type / Scope**: Dashboard Database Module
*   **Proposed Changes**: Remove or derive `DEFAULT_DB_PATH` from `paths.get_hermes_home()` rather than `Path.home() / ".hermes" / "zerofactory.db"`.

#### 10. `dashboard/routes/stats.py` (Modify)
*   **Type / Scope**: Dashboard Stats API Route
*   **Proposed Changes**: Update `get_orchestrator_scan_activities()` and `count_orchestrator_scans_today()` to resolve `get_hermes_home() / "profiles" / "zf-orchestrator" / "cron" / "executions.db"` instead of `os.path.expanduser("~/.hermes/...")`.

#### 11. `README.md` (Modify)
*   **Type / Scope**: Documentation
*   **Proposed Changes**: Update line 195 to reflect opt-in `--yolo` execution (`allow_unattended_approvals`), and document `mem0` (`mem0ai`, `fastembed`, `qdrant-client`) as an optional dependency with SQLite `board_memories` fallback and `mem0_enabled: false` default.

#### 12. Unit Tests (`tests/unit/test_memory_service.py`, `tests/unit/test_init_hooks.py`, `tests/unit/test_hermes_home_paths.py`) (Create / Modify)
*   **Type / Scope**: Unit Test Suite
*   **Proposed Changes**:
    *   Verify `memory_service`: `mem0_enabled` defaults to `False`, no `spark.ntsd.dev` or `RadixArk/Qwen3.8-27B-NVFP4` defaults, `OPENAI_API_KEY` is never sent to custom `base_url`, `infer=False` is passed in `extract_and_record_memory()`, and missing `"llm"` config returns `None` cleanly on validation error.
    *   Verify `__init__.py`: `on_kanban_dispatch_tick` skips `run_dispatch_cycle()` when `auto_start_dispatcher` is `False` and no daemon lock is held, and executes when either is active.
    *   Verify `HERMES_HOME` override across `dispatcher/config.py`, `dashboard/memory_service.py`, `migrations/runner.py`, `scripts/zf_openwiki_gate.py`, `scripts/zf_daily_stats.py`, `dashboard/db.py`, and `dashboard/routes/stats.py`.

### Verification Plan

*   **Frontend Build**: Rebuild `dashboard/dist/index.js` using the dashboard build script and verify no unbuilt `spark.ntsd.dev` or `RadixArk` strings remain in `dashboard/dist/index.js`.
*   **Unit & Integration Tests**: Run `pytest` on the full test suite (`tests/unit/` and `tests/integration/`) with all tests passing.
*   **Static Analysis & Linting**: Run `ruff check .` and `ruff format --check .` with zero errors.
*   **Plugin Validation**: Run `hermes plugins validate .` and `hermes plugins doctor .` (if available in environment) with clean pass.

--------------------------------------------------------------------------------

*Drafted with EGM*

