# Pre-Existing Work Disclosure (Hermes Agent Plugin Hackathon)

This document discloses what existed in **Zero Factory** prior to the **Hermes Agent Plugin Hackathon** (November 5 – November 11, 2026) and what was newly built during the hackathon window.

## 1. Pre-Existing Base (Before November 5, 2026)

Zero Factory started in April 2026 (`28a02c2`) and was ported to the Hermes Agent plugin architecture in May 2026 (`75bf900`). Prior to November 5, 2026 (`9e5f1d5`), the repository contained:

- **Core Hermes Plugin & CLI (`__init__.py`, `profile_manager.py`, `paths.py`, `settings.py`)**:
  - `hermes zerofactory` CLI commands (`setup`, `list`, `create`, `move`, `block`, `comment`, `board`, `dispatch`, `cron`, `memory`).
  - Automatic provisioning of isolated Hermes profiles (`zf-orchestrator`, `zf-builder`, `zf-reviewer`) in `~/.hermes/profiles/`.
- **Dispatcher, Git Worktrees & Thematic Code Review (`dispatcher/`)**:
  - Isolated per-task Git worktree management across multi-repository boards.
  - Precommit verification gate (`.zerofactory/precommit.sh`), GitHub PR creation, and 2-round thematic PR review loop.
- **Kanban SQLite Backend & Web Dashboard (`dashboard/`, `migrations/`)**:
  - Embedded SQLite (`WAL` mode) task/board storage, Mem0 + Qdrant hybrid vector memory substrate, and React/Vite dashboard UI (`/zerofactory`).
- **Token-Efficient Cron Watchdog & Scanners (`cron/`, `scripts/`, `builtin_cron.py`)**:
  - No-Agent queue watchdog (`zf_queue_watchdog.py`) and wake-gate improvement scanner (`zf_scanner_gate.py`).

## 2. Built During the Hackathon (November 5 – November 11, 2026)

The following features, workflows, and reliability improvements were designed and implemented during the hackathon period:

- **Sequential EGM Triage Pipeline & `zf-goldfish` Spec Auditor (`5212778`, `f68a408`)**:
  - Added the 4th specialist agent profile **`zf-goldfish`** (`templates/zf-goldfish/SOUL.md`, `templates/zf-goldfish/config.yaml`) to perform adversarial, zero-context specification audits enforcing the Ponytail 7-Rung Ladder of Laziness and concrete acceptance criteria.
  - Implemented sequential Triage state machine (`Triage` → Elephant Spec Drafting by `zf-orchestrator` → Goldfish Spec Audit by `zf-goldfish` → Human Release Gate) in `dispatcher/scheduler.py`, `dispatcher/worker_spawner.py`, and `dispatcher/reaper.py`.
  - Added CLI and Dashboard triage approval/rejection/splitting workflows (`hermes zerofactory approve`, `reject`, `split`, `dashboard/routes/tasks.py`, `TaskDetailModal.jsx`, and `docs/sequential_egm_triage.md`) with 460+ lines of unit tests (`tests/unit/dispatcher/test_egm_triage.py`).
- **Task-Level Automerge Support (`e772b40`)**:
  - Added `automerge` tag support in `dispatcher/scheduler.py` so eligible low-risk tasks (such as automated `openwiki/` documentation syncs) can auto-merge upon passing checks, backed by `tests/unit/dispatcher/test_automerge.py`.
- **Multi-Repo Worktree Discovery & Server-Mode Dispatcher Fixes (`9dbf4ce`, `de0354c`, `fb122b1`)**:
  - Hardened worktree discovery and resolution across `dispatcher/worktree.py`, `dispatcher/scheduler.py`, and `dashboard/routes/tasks.py`.
  - Fixed background dispatcher startup in dashboard server mode (`dashboard/plugin_api.py`) without blocking CLI imports.
  - Added fast-path SQLite initialization check and 30s busy timeout (`dashboard/db.py`).
- **OpenWiki Architecture Documentation Sync & Catalog Manifest Compliance (`55ff0ee`, `b69ab01`, `ba4d81c`)**:
  - Synchronized machine-readable `openwiki/` architecture claims and updated `plugin.yaml` capability declarations (`provides_hooks`, `requires_hermes`) for Hermes Plugin Catalog validation.

