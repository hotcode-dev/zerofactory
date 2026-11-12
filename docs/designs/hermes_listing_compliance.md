# Zero Factory Hardening & Hermes Listing Compliance

* **Author:** ntsd
* **Status:** Proposed
* **Date:** 2026-11-13

--------------------------------------------------------------------------------

## Overview

Zero Factory is a multi-agent orchestration plugin for Hermes Agent (`NousResearch/hermes-agent#153625`). During listing review at commit `288ec9c`, the Hermes maintainer (`teknium1`) identified 8 security, isolation, and lifecycle issues that prevent the plugin from being listed.

This design updates Zero Factory so that loading the plugin is passive and safe, profile mutations and background workers are explicit and opt-in, and child agent subprocesses run with least-privilege defaults.

## The Problem

At commit `288ec9c`, installing or importing Zero Factory violates Hermes plugin boundaries in four ways:

1. **Unattended execution without approvals:** Every worker and scanner subprocess launches with `--yolo --accept-hooks`, and `templates/zf-builder/config.yaml` sets `security.protected_instruction_files: false`. Repository content or PR feedback can therefore drive shell and file commands without approval or instruction-file protection.
2. **Implicit host and profile mutation:** `register()` calls `ensure_zf_profiles()`, which edits `~/.hermes/.env`, `~/.hermes/config.yaml`, `~/.hermes/skills/`, `~/.hermes/scripts/`, and all other user profiles under `profiles/` (copying Langfuse keys and removing `langfuse` from plugin lists). `register()` and `dashboard/plugin_api.py` import also start the background dispatcher automatically.
3. **Over-broad environment and path assumptions:** Child workers receive `os.environ.copy()` (leaking unrelated parent environment variables), `templates/zf-builder/config.yaml` runs `npx -y openwiki` unpinned, and `profile_manager.py`, `paths.py`, `dashboard/db.py`, and `dispatcher/` hardcode `Path.home() / ".hermes"` or strip `profiles/` off `HERMES_HOME`.
4. **Untrusted auto-merge trigger:** `dispatcher/github_pr.py` enables merge-without-review when an imported GitHub issue carries an `automerge` or `yolo` label, allowing upstream issue collaborators to bypass review.

## Goals

* **Satisfy all 8 listing requirements** from [`NousResearch/hermes-agent#153625`](https://github.com/NousResearch/hermes-agent/pull/153625#pullrequestreview-5865989551).
* **Passive plugin load:** Keep `register()` and `dashboard/plugin_api.py` import free of profile writes, root config edits, and automatic background dispatcher startup.
* **Explicit lifecycle:** Limit `zf-*` profile creation and `gh auth status` checks to `hermes zerofactory setup`, and start the dispatcher only via `hermes zerofactory start` (foreground loop) or an opt-in `auto_start_dispatcher` setting (default `false`).
* **Read-only dashboard Setup Wizard:** When `zf-*` profiles, `gh` auth, or the dispatcher are not yet ready, display a read-only Setup Wizard in the dashboard showing the exact CLI commands (`hermes zerofactory setup`, `gh auth login`, `hermes zerofactory start`) to run—without mutating profiles or starting threads automatically.
* **Least-privilege worker defaults:** Drop `--yolo` and `--accept-hooks` by default (behind a single opt-in `allow_unattended_approvals` setting, default `false`), keep `protected_instruction_files` enabled, pass a minimal child environment, pin `openwiki@0.9.0`, use the active `HERMES_HOME` directly, and restrict auto-merge to local user-set task tags (`automerge`, `yolo`, `tag:automerge`, `tag:yolo`) or board settings.
* **Clean failure on unattended approval prompts:** When a worker cannot proceed without an approval while `allow_unattended_approvals` is `false`, transition the task to `blocked` (`blocked_reason_type = "human-gate"`) instead of retrying in a loop or hanging.

## Non-Goals

* Mutating profiles, writing `.env` secrets, or starting the dispatcher from dashboard `GET` requests or web UI buttons.
* Adding blocked-task decision modals or in-browser `.env` secret editors in this PR.
* Streaming interactive stdin approval prompts to an already-running `hermes chat -q` worker.
* Automatically copying API keys or secrets from root `~/.hermes/.env` or other user profiles into `zf-*` profiles.

## Resolved Questions

*All initial open questions have been resolved:*

* **Approval failure detection:** `dispatcher/reaper.py` (`reap_active_workers()`) inspects non-zero exits when `allow_unattended_approvals` is `False` by scanning the tail of `worker_<task_id>.log` for approval-prompt / non-interactive denial markers (`"approval required"`, `"command requires approval"`, `"interactive approval"`, `"EOF when reading a line"`). When matched, it skips retry/auto-recovery and transitions the task to `blocked` (`blocked_reason_type = "human-gate"`).
* **Opt-in dispatcher setting location:** Stored in Zero Factory's `settings.py` (`zerofactory.db`) as `auto_start_dispatcher` (default `False`).
* **`HERMES_HOME` resolution:** `paths.get_hermes_home()` treats `os.environ["HERMES_HOME"]` directly as the active Hermes home (never stripping `profiles/`). Spawned workers and scanners receive `env["HERMES_HOME"] = str(get_hermes_home())` (letting `-p <role>` select the profile), so child `hermes zerofactory` commands, logs (`$HERMES_HOME/logs/`), `zerofactory.db`, and `zf-*` profiles (`$HERMES_HOME/profiles/zf-*`) resolve consistently without nesting `profiles/<role>/profiles/<role>`.

## Critical User Journeys (CUJs)

### CUJ 1: Safe Plugin Install & Read-Only Dashboard Guidance

* **Given:** A user installs Zero Factory into Hermes (`hermes plugins install hotcode-dev/zerofactory`) without running `setup` or `start`.
* **When:** Hermes loads the plugin via `register()` or imports `dashboard/plugin_api.py`, and the user opens the dashboard.
* **Then:** No `zf-*` profiles are created, root `~/.hermes` and other profiles remain untouched, no background dispatcher or scanner threads start, and the dashboard Setup Wizard displays the CLI commands to run (`hermes zerofactory setup`, `gh auth login`, `hermes zerofactory start`).

### CUJ 2: Explicit Setup & Profile Isolation

* **Given:** A user has installed Zero Factory under an active `HERMES_HOME`.
* **When:** The user runs `hermes zerofactory setup`.
* **Then:** Only `ZF_PROFILES` (`zf-orchestrator`, `zf-goldfish`, `zf-builder`, `zf-reviewer`) are created/updated under `$HERMES_HOME/profiles/`, root `~/.hermes` and other user profiles are untouched, and `gh auth status` is checked with CLI/token instructions if unauthenticated.

### CUJ 3: Explicit Dispatcher Start & Least-Privilege Worker Execution

* **Given:** The user has run `hermes zerofactory setup` and starts the dispatcher via `hermes zerofactory start` (or enables `auto_start_dispatcher`).
* **When:** A task is dispatched to `zf-builder` or `zf-reviewer`.
* **Then:** The child process runs with `HERMES_HOME` set to `get_hermes_home()`, a minimal whitelisted environment, no `--yolo` or `--accept-hooks` (unless `allow_unattended_approvals` is `True`), `protected_instruction_files` kept on, and `openwiki@0.9.0` pinned. If an approval prompt causes a non-zero exit while unattended approvals are disabled, `reaper.py` moves the task to `blocked` (`human-gate`) without retrying.

### CUJ 4: Local-Only Auto-Merge

* **Given:** An external GitHub issue is imported with `automerge` or `yolo` labels.
* **When:** `issues/importer.py` imports the issue and `dispatcher/github_pr.py` later evaluates auto-merge on the PR.
* **Then:** Upstream `automerge`/`yolo` labels are filtered out of `task.tags` on import and ignored in `github_pr.py`; auto-merge only activates if the local operator sets a local auto-merge tag (`automerge`, `yolo`, `tag:automerge`, `tag:yolo`) on the task or enables the board `automerge` setting.

## Technical Plan (Architecture)

### 1. Plugin Lifecycle & Explicit Setup/Start Flow (`__init__.py`, `dashboard/plugin_api.py`, `settings.py`)

Zero Factory separates passive plugin loading from state-mutating setup and background execution:

```text
hermes plugins install / import
  └─► register() / dashboard/plugin_api.py
        ├─ Wire CLI commands & HTTP routes
        └─ Check settings.auto_start_dispatcher (default: False; only if zerofactory.db exists)
             ├─ False (default) ─► No background threads, no profile writes, no cron writes
             └─ True            ─► start_background_dispatcher()

hermes zerofactory setup (CLI only)
  ├─ Create/update ONLY zf-* profiles under $HERMES_HOME/profiles/zf-*
  ├─ Scope symlinks, scripts, & Langfuse sync strictly to ZF_PROFILES
  └─ Run `gh auth status` & print remediation if unauthenticated

hermes zerofactory start (CLI only)
  └─ Verify zf-* profiles exist ─► run foreground blocking dispatch loop (until SIGINT/SIGTERM)

Dashboard GET /api/plugins/zerofactory/setup/status (Read-only)
  └─ Report { profiles_ready, missing_profiles, gh_authenticated, dispatcher_running }
       └─ UI Setup Wizard displays missing CLI commands (no mutations)
```

* `ZEROFACTORY_SKIP_DISPATCHER` and `ZEROFACTORY_DISABLE_DISPATCHER` remain honored as emergency env overrides to suppress dispatcher startup even when `auto_start_dispatcher` is `True`.
* Built-in Zero Factory cron jobs target `zf-orchestrator` (never root `~/.hermes`), so removing root `~/.hermes/scripts/` writes does not break cron execution.

### 2. Active `HERMES_HOME` & Path Resolution (`paths.py`, `profile_manager.py`, `dispatcher/`, `dashboard/db.py`)

* **`paths.get_hermes_home()`**: Single source of truth. Returns `Path(os.environ["HERMES_HOME"]).expanduser().resolve()` when `HERMES_HOME` is set (never stripping `profiles/`), falling back to `(Path.home() / ".hermes").resolve()` when unset.
* Replace all hardcoded `Path.home() / ".hermes"` sites in `paths.py`, `profile_manager.py`, `dispatcher/worker_spawner.py`, `dispatcher/reaper.py`, `dispatcher/process_manager.py`, `dispatcher/scanner.py`, `dispatcher/config.py`, and `dashboard/db.py` with `get_hermes_home()`.

### 3. Profile Isolation (`__init__.py`, `profile_manager.py`)

* Remove `ensure_zf_profiles()` from `register()` in `__init__.py`.
* In `profile_manager.py`, remove the `root_skills` symlink loop (`ensure_zf_profiles()` lines 170–186), remove root `~/.hermes/plugins/`, `~/.hermes/config.yaml`, and `~/.hermes/scripts/` writes from `ensure_plugin_symlinks()` and `ensure_script_files()`, and scope `sync_langfuse_profiles()` strictly to `ZF_PROFILES` (reading Langfuse config only from `settings.py` / `zerofactory.db`, never from root or other profiles).
* In `hermes zerofactory setup`, run `gh auth status` and remind the user to run `gh auth login` (or set `GH_TOKEN` in `zf-*` `.env`) if unauthenticated, and remind fresh users to configure LLM API keys in `$HERMES_HOME/profiles/zf-*/.env`.

### 4. Opt-In Dispatcher (`__init__.py`, `dashboard/plugin_api.py`, `settings.py`, `dashboard/routes/settings.py`)

* Add `auto_start_dispatcher` (`DEFAULT_AUTO_START_DISPATCHER = False`) to `settings.py`, `dashboard/models.py` (`SettingsUpdate`), and `dashboard/routes/settings.py`.
* Remove `_maybe_start_background_dispatcher()` from `dashboard/plugin_api.py` module import.
* In `register()`, check `auto_start_dispatcher` only if `zerofactory.db` already exists (no DB creation on unrelated `hermes` CLI commands); only call `init_db()`, `ensure_builtin_cron_jobs()`, and `start_background_dispatcher()` when `auto_start_dispatcher` is `True` (and skip/disable env vars are unset).
* Add `hermes zerofactory start` CLI subcommand in `__init__.py`: verify `zf-*` profiles exist, initialize DB/crons, and run a foreground blocking dispatch loop until `SIGINT`/`SIGTERM`.

### 5. Unattended Approvals & Minimal Child Environment (`settings.py`, `dispatcher/worker_spawner.py`, `dispatcher/reaper.py`, `dispatcher/scanner.py`)

* **Single opt-in flag**: Add `allow_unattended_approvals` (`DEFAULT_ALLOW_UNATTENDED_APPROVALS = False`) to `settings.py`, `dashboard/models.py` (`SettingsUpdate`), and `dashboard/routes/settings.py`.
* **CLI flags**: In `worker_spawner.py` and `scanner.py`, omit `--yolo` and `--accept-hooks` from `cmd` unless `allow_unattended_approvals` is `True`.
* **Approval failure handling**: In `dispatcher/reaper.py` (`reap_active_workers()`), when `allow_unattended_approvals` is `False` and a worker exits non-zero with approval-prompt indicators in the log tail, skip automatic `Todo` / `zf-orchestrator` retry, set `blocked_reason_type = "human-gate"`, and transition the task to `blocked` with a comment explaining how to allowlist commands in `zf-*/config.yaml` or enable `allow_unattended_approvals`. In `scanner.py`, log approval-prompt non-zero exits without tight-looping.
* **Minimal child env**: Replace `env = os.environ.copy()` in `worker_spawner.py` and `scanner.py` with an explicit whitelist:
  * Shared keys: `PATH`, `HOME`, `HERMES_HOME` (`str(get_hermes_home())`), `LANG`, optional `LC_ALL` / `TMPDIR` / `SSH_AUTH_SOCK` / `XDG_CONFIG_HOME` (forwarded only if set in `os.environ`), all `ZEROFACTORY_*` from `os.environ`, plus `ZEROFACTORY_DB` (`str(get_db_path())` if the file exists).
  * `worker_spawner.py` adds: `HERMES_PROFILE`, `HERMES_KANBAN_STOP_NUDGE` (`"0"`, disables stop-hook nudging in child worker), `HERMES_KANBAN_WORKSPACE`, `TERMINAL_CWD`, `PYTHONUNBUFFERED`.
  * `scanner.py` adds: `HERMES_PROFILE` (`"zf-orchestrator"`), `PYTHONUNBUFFERED`, `ZEROFACTORY_IDLE_SCAN` (`"1"`), `ZEROFACTORY_DISABLE_DISPATCHER` (`"1"`).
  * Remove `_inject_langfuse_env(env)` calls from both spawners; child Hermes loads its own `zf-*` profile `.env`.

### 6. Template Hardening & Local-Only Auto-Merge (`templates/zf-builder/config.yaml`, `dispatcher/github_pr.py`, `issues/importer.py`)

* Remove `security.protected_instruction_files: false` from `templates/zf-builder/config.yaml` and pin `openwiki@0.9.0` in `mcp_servers.openwiki.args`. (Audited `zf-orchestrator`, `zf-reviewer`, and `zf-goldfish` templates: none define `protected_instruction_files` or `mcp_servers`.)
* In `issues/importer.py` (`import_external_issue()`), filter out `automerge` and `yolo` labels when building `task.tags` so `tag:automerge` and `tag:yolo` are never populated from external issues.
* In `dispatcher/github_pr.py` (`is_task_automerge_enabled()`), remove lines 579–580 (`ext_issue` `("automerge", "yolo")` check) while keeping `("hitl", "manual-review")` opt-out (lines 577–578), local `task.tags`, and the board `automerge` setting.

### 7. Read-Only Dashboard Setup Wizard (`dashboard/routes/dispatch.py`, `dashboard/frontend/`)

* Expose `@router.get("/setup/status")` (mounted at `/api/plugins/zerofactory/setup/status`) returning `{ "profiles_ready": bool, "missing_profiles": list[str], "gh_authenticated": bool, "dispatcher_running": bool }`.
* `check_setup_status()` verifies `config.yaml` and `plugins/zerofactory` exist for every role in `ZF_PROFILES`, checks `gh auth status` with a 3s timeout (catching `FileNotFoundError`/`TimeoutExpired` and caching for 30s, or checking `GH_TOKEN` in `zf-*` `.env`), and reports `dispatcher_running`.
* Display a read-only Setup Wizard banner in `dashboard/frontend/` whenever any prerequisite is false, listing the exact CLI commands (`hermes zerofactory setup`, `gh auth login`, `hermes zerofactory start`).

## Alternatives Considered

### Alternative A: Separate toggles for `--yolo` and `--accept-hooks`

* **Pros:** Allows accepting workspace hooks without disabling tool approvals, or vice versa.
* **Cons:** Doubles the configuration surface for unattended worker execution without a clear user need.
* **Reason for Rejection:** Rejected by author: a single `allow_unattended_approvals` boolean (default `false`) is simpler to configure and audit.

### Alternative B: Interactive Web UI Setup & `.env` Secret Editor

* **Pros:** Users could create profiles, write `GH_TOKEN`/LLM keys, and start the dispatcher directly from the browser.
* **Cons:** Requires mutating local profiles/secrets over localhost HTTP and maintaining a web-based `gh` auth flow, expanding security review scope for `NousResearch/hermes-agent#153625`.
* **Reason for Rejection:** Rejected by author: a read-only Setup Wizard in the dashboard that displays the CLI commands to run keeps all mutations in explicit CLI commands.

### Alternative C: Auto-creating profiles and starting the dispatcher in `register()`

* **Pros:** Zero-step activation immediately after plugin installation.
* **Cons:** Modifies root and non-`zf-*` profiles on plugin load and runs unattended background agents without opt-in.
* **Reason for Rejection:** Rejected by maintainer ([`NousResearch/hermes-agent#153625`](https://github.com/NousResearch/hermes-agent/pull/153625#pullrequestreview-5865989551)): plugins must not mutate other profiles at load time or start the dispatcher unless opted in.

### Alternative D: Board-only auto-merge setting

* **Pros:** Single boolean per board with no tag parsing.
* **Cons:** Cannot enable auto-merge on individual tasks without enabling it for the entire board.
* **Reason for Rejection:** Rejected by author: a local user-set task tag gives per-task control while filtering out upstream GitHub issue `automerge`/`yolo` labels.

## Non-Functional Requirements

* **Security & Isolation:** Child workers receive only whitelisted environment variables (`PATH`, `HOME`, `HERMES_HOME`, `LANG`, optional `LC_ALL`/`TMPDIR`/`SSH_AUTH_SOCK`/`XDG_CONFIG_HOME`, `ZEROFACTORY_*`, and role-specific variables); `security.protected_instruction_files` remains enabled; `openwiki` is pinned to `0.9.0`; upstream GitHub issue labels cannot trigger auto-merge.

--------------------------------------------------------------------------------

## Detailed Implementation Plan

### Target Files to Create/Modify

#### 1. `paths.py` (Modify)
* **Type / Scope:** Core path resolution module
* **Proposed Changes:** Add `get_hermes_home() -> Path` reading `os.environ.get("HERMES_HOME")` directly (expanding `~` and resolving) without stripping `profiles/`, falling back to `(Path.home() / ".hermes").resolve()` when unset. Update `_hermes_profiles_root()` and `resolve_profile_state_db()` (including its `state.db` fallback at line 165) to derive paths from `get_hermes_home()`.

#### 2. `profile_manager.py` (Modify)
* **Type / Scope:** Profile & plugin lifecycle manager
* **Proposed Changes:**
  * Replace `get_hermes_root()` / `get_hermes_home()` implementation with `paths.get_hermes_home()` (no `profiles/` stripping).
  * Remove the `root_skills` symlink loop (`ensure_zf_profiles()` lines 170–186) so `~/.hermes/skills/` is never modified.
  * Scope `ensure_plugin_symlinks()` and `ensure_script_files()` strictly to `ZF_PROFILES`; remove writes to root `~/.hermes/plugins/`, `~/.hermes/config.yaml`, and `~/.hermes/scripts/`.
  * Scope `sync_langfuse_profiles()` strictly to `ZF_PROFILES`, reading settings only from `settings.py` / `zerofactory.db` and never touching root or non-`zf-*` profiles.
  * Add read-only `check_setup_status()` returning `{ profiles_ready, missing_profiles, gh_authenticated }` (verifying `config.yaml` + `plugins/zerofactory` for each `ZF_PROFILES` entry and running `gh auth status` with a 3s timeout, `FileNotFoundError` catch, and 30s cache).

#### 3. `__init__.py` (Modify)
* **Type / Scope:** Plugin entrypoint & CLI registration
* **Proposed Changes:**
  * In `register()`: remove `ensure_zf_profiles()`. Check `auto_start_dispatcher` only if `zerofactory.db` exists; only call `init_db()`, `ensure_builtin_cron_jobs()`, and `start_background_dispatcher()` when `auto_start_dispatcher` is `True` and `ZEROFACTORY_SKIP_DISPATCHER` / `ZEROFACTORY_DISABLE_DISPATCHER` are unset.
  * In `hermes zerofactory setup`: update CLI help text to list all 4 `ZF_PROFILES` (including `zf-goldfish`), run `ensure_zf_profiles()`, check `gh auth status`, and print CLI/token instructions if unauthenticated or if `zf-*` `.env` lacks LLM keys.
  * Add `hermes zerofactory start` CLI subcommand: verify `zf-*` profiles exist (exit with setup instructions if missing), run `init_db()` + `ensure_builtin_cron_jobs()`, and execute a foreground blocking dispatch loop until `SIGINT`/`SIGTERM`.

#### 4. `settings.py`, `dashboard/models.py`, & `dashboard/routes/settings.py` (Modify)
* **Type / Scope:** Global settings schema, parser, and settings API (`zerofactory.db`)
* **Proposed Changes:**
  * In `settings.py`: add `DEFAULT_ALLOW_UNATTENDED_APPROVALS = False` (`allow_unattended_approvals`) and `DEFAULT_AUTO_START_DISPATCHER = False` (`auto_start_dispatcher`) to `SETTING_KEYS`, `DEFAULT_SETTING_VALUES`, and `load_settings()`.
  * In `dashboard/models.py` (`SettingsUpdate`) and `dashboard/routes/settings.py` (`update_settings`): add optional `allow_unattended_approvals: bool | None` and `auto_start_dispatcher: bool | None` fields so both settings can be read and updated via the Settings API.

#### 5. `dispatcher/worker_spawner.py` & `dispatcher/reaper.py` (Modify)
* **Type / Scope:** Worker subprocess spawner & exit reaper
* **Proposed Changes:**
  * In `dispatcher/worker_spawner.py`: replace `Path.home() / ".hermes"` with `get_hermes_home()`, set `env["HERMES_HOME"] = str(get_hermes_home())` (not `profile_home`), gate `--yolo` and `--accept-hooks` behind `allow_unattended_approvals`, replace `os.environ.copy()` with the minimal whitelist (`PATH`, `HOME`, `HERMES_HOME`, `LANG`, optional `LC_ALL`/`TMPDIR`/`SSH_AUTH_SOCK`/`XDG_CONFIG_HOME`, `ZEROFACTORY_*`, `ZEROFACTORY_DB`, `HERMES_PROFILE`, `HERMES_KANBAN_STOP_NUDGE`, `HERMES_KANBAN_WORKSPACE`, `TERMINAL_CWD`, `PYTHONUNBUFFERED`), and remove `_inject_langfuse_env(env)`.
  * In `dispatcher/reaper.py`: replace `Path.home() / ".hermes"` at `_worker_log_path()` (line 28) with `get_hermes_home()`. In `reap_active_workers()`, when `allow_unattended_approvals` is `False` and a non-zero exit log tail matches approval-prompt indicators, skip retry/auto-recovery, set `blocked_reason_type = "human-gate"`, and transition the task to `blocked` with remediation guidance.

#### 6. `dispatcher/scanner.py`, `dispatcher/process_manager.py`, `dispatcher/config.py`, & `dashboard/db.py` (Modify)
* **Type / Scope:** Scanner spawner, process artifacts, & remaining path sites
* **Proposed Changes:**
  * In `dispatcher/scanner.py`: replace all 5 `Path.home() / ".hermes"` references (lines 34, 60, 87, 238, 244, 306) with `get_hermes_home()`, set `env["HERMES_HOME"] = str(get_hermes_home())`, gate `--yolo` and `--accept-hooks` behind `allow_unattended_approvals`, replace `os.environ.copy()` with the minimal whitelist (`PATH`, `HOME`, `HERMES_HOME`, `LANG`, optional `LC_ALL`/`TMPDIR`/`SSH_AUTH_SOCK`/`XDG_CONFIG_HOME`, `ZEROFACTORY_*`, `ZEROFACTORY_DB`, `HERMES_PROFILE`, `PYTHONUNBUFFERED`, `ZEROFACTORY_IDLE_SCAN`, `ZEROFACTORY_DISABLE_DISPATCHER`), remove `_inject_langfuse_env(env)`, and log approval-prompt failures without tight-looping.
  * In `dispatcher/process_manager.py` (lines 35–51), `dispatcher/config.py` (line 121), and `dashboard/db.py` (lines 53, 104): replace hardcoded `Path.home() / ".hermes"` with `get_hermes_home()`.

#### 7. `templates/zf-builder/config.yaml` (Modify)
* **Type / Scope:** Builder profile template
* **Proposed Changes:** Remove `security.protected_instruction_files: false` and pin `openwiki` to `openwiki@0.9.0` in `mcp_servers.openwiki.args`.

#### 8. `dispatcher/github_pr.py` & `issues/importer.py` (Modify)
* **Type / Scope:** PR auto-merge & GitHub issue sync
* **Proposed Changes:**
  * In `issues/importer.py` (`import_external_issue()`, lines 156–159): skip `automerge` and `yolo` labels when building `task.tags` so `tag:automerge` and `tag:yolo` are never populated from external issues.
  * In `dispatcher/github_pr.py` (`is_task_automerge_enabled()`, lines 579–580): remove the `ext_issue` `("automerge", "yolo")` check while keeping `("hitl", "manual-review")` opt-out (lines 577–578), local `task.tags`, and the board `automerge` setting.

#### 9. `dashboard/plugin_api.py`, `dashboard/routes/dispatch.py`, & `dashboard/frontend/` (Modify)
* **Type / Scope:** Dashboard HTTP API & read-only Setup Wizard UI
* **Proposed Changes:**
  * In `dashboard/plugin_api.py`: remove `_maybe_start_background_dispatcher()` on module import.
  * In `dashboard/routes/dispatch.py`: add `@router.get("/setup/status")` returning `check_setup_status()` plus `dispatcher_running`.
  * In `dashboard/frontend/src/App.jsx` (and rebuild `dashboard/frontend/dist/` via `npm run build`): render a read-only Setup Wizard banner when `profiles_ready`, `gh_authenticated`, or `dispatcher_running` is false, displaying `hermes zerofactory setup`, `gh auth login`, and `hermes zerofactory start`.

#### 10. `README.md` (Modify; `AGENTS.md` is symlinked to `README.md`)
* **Type / Scope:** Plugin documentation
* **Proposed Changes:** Update Quick Start and CLI sections to document `hermes zerofactory setup` (including configuring LLM keys in `zf-*` `.env` and `gh auth status`), `hermes zerofactory start` (or `auto_start_dispatcher`), and `allow_unattended_approvals` defaulting to `false`.

#### 11. `tests/` (Modify / Create)
* **Type / Scope:** Unit & integration tests (`tests/test_listing_compliance.py` plus existing `tests/test_profile_manager.py`, `tests/test_worker_spawner.py`, `tests/test_github_pr.py`)
* **Proposed Changes:** Verify: (a) `paths.get_hermes_home()` respects `HERMES_HOME` without stripping `profiles/`; (b) `register()` and `dashboard/plugin_api.py` import perform zero profile writes and zero dispatcher starts; (c) `profile_manager.py` never touches root `~/.hermes` (including `skills/` and `scripts/`) or non-`zf-*` profiles; (d) `worker_spawner.py` and `scanner.py` omit `--yolo`/`--accept-hooks` by default, pass `HERMES_HOME = get_hermes_home()`, and use minimal env; (e) `reaper.py` transitions approval-blocked workers to `blocked` (`human-gate`) without retry; (f) `hermes zerofactory start` fails cleanly if `zf-*` profiles are missing; (g) `templates/zf-builder/config.yaml` pins `openwiki@0.9.0` and omits `protected_instruction_files: false`; (h) `issues/importer.py` and `dispatcher/github_pr.py` ignore upstream `automerge`/`yolo` labels; (i) `GET /api/plugins/zerofactory/setup/status` is read-only.

### Verification Plan

* **Unit Tests:** `pytest` covering `tests/` (including `tests/test_listing_compliance.py` and updated profile/spawner/PR suites).
* **Frontend Build:** `npm run build` in `zerofactory` (Vite build for `dashboard/frontend/`).
* **Static Analysis & Linting:** `ruff check .` (using `ruff.toml`) and `.zerofactory/precommit.sh`.
* **Manual Smoke Check:** Test `register()` with a temporary `HERMES_HOME` containing a dummy non-`zf` profile to confirm zero mutations on load, then run `hermes zerofactory setup` and `hermes zerofactory start`.

--------------------------------------------------------------------------------

<!-- Provenance: Indicates initial structural drafting via EGM. -->

*Drafted with EGM*
