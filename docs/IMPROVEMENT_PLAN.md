# ZeroFactory Improvement Plan

_Last scan: Monday, 2026-09-07 23:17 +07, cron `zero-factory-improvement-scanner`_

## Scan Summary

- **Projects scanned:** 1 active Kanban-board target (`zerofactory`); other `~/git` clones have no board and are out of scope.
- **Improvements found (tracked):** 5 — 1 already tracked, 4 re-verified against the live working tree this run.
- **New Kanban task created this run:** **1** — `t_9523eb18` `[bug-fix] Dispatcher: stop promoting tasks to Ready when worktree setup fails; dedupe repo-resolution` (priority 3, `todo`→`ready`, tenant `~/git/hotcode-dev/zerofactory`).
- **Board:** `zerofactory` (only active board, excluding Default) → repo `https://github.com/hotcode-dev/zerofactory` (already cloned at `~/git/hotcode-dev/zerofactory`, on `main`, up to date with `origin/main`).

## Why this task (and not the #1 security issue)

The single most critical finding is still the **committed API gateway secrets** — but it is **already tracked** as `t_70a26fcf` (priority 3, security) and is **blocked on a dispatcher spawn/infra failure** (`systemd-run --user --scope` unavailable), not on its content. Re-creating a duplicate card cannot resolve it and would re-hit the same spawn failure (it already has `consecutive_failures=2`). Per scanner policy (max 1 task, no duplicates), this run targets the **next most critical, untracked** issue: a real logic bug in the dispatcher control plane.

> **Human action still required on `t_70a26fcf`:** the top security fix cannot be dispatched until the gateway child-spawn path works without `systemd-run --user --scope`. Once that infra issue is fixed, re-queue `t_70a26fcf` to `ready`.

## Projects Scanned

| Project | Path | Source | In scope? |
|---------|------|--------|-----------|
| zerofactory | `~/git/hotcode-dev/zerofactory` | Kanban board `zerofactory` (board.json description) | **Yes** |
| zerohub | `~/git/hotcode-dev/zerohub` | Local clone (not a board) | No (informational) |
| luma.examples | `~/git/luma.examples` | Local clone, no board | No |
| dotai / sdp-compact | `~/git/ntsd/…` | Local clones, no board | No |

## Findings (priority ranked)

### 1. [CRITICAL / security] Real API gateway key committed in Git — tracked as `t_70a26fcf` (BLOCKED on spawn) — NOT re-created this run
- **Where:** `profiles/common/.env`, `profiles/builder/.env`, `profiles/orchestrator/.env`, `profiles/reviewer/.env` (all four **still tracked** — re-verified via `git ls-files` this run)
- **What:** Live `API_SERVER_KEY` (64-hex, introduced in commit `67f93ca`) is committed and pushed with `API_SERVER_HOST=0.0.0.0` + `GATEWAY_ALLOW_ALL_USERS=true`. Root `.gitignore` **still** un-ignores the real `.env` files (lines 14 and 21).
- **Impact:** Anyone with repo access can authenticate to the Hermes gateway API bound to all interfaces. High-severity credential exposure. **Still unresolved.**
- **Status:** Already an actionable card (`t_70a26fcf`). The only thing stopping it is the spawn/infra failure. **Not duplicated this run.**
- **Estimated impact:** High (security); effort: low (once spawning works).

### 2. [HIGH / bug-fix + refactoring + testing] Dispatcher control plane — NEW TASK `t_9523eb18` (created this run)
- **Where:** `profiles/common/plugins/zerofactory-kanban-dispatcher/__init__.py` (282 lines) — the system's control plane; a silent regression here breaks the whole pipeline.
- **Headline bug:** `setup_worktree()` is called (line ~125) and its return value is **discarded**, yet the task is unconditionally promoted to `ready` (line ~128). On a `git worktree add` failure the function returns `None` without setting `workspace_path` (lines ~104-106), leaving a `ready` task with no valid worktree that the assigned agent cannot pick up. Fix: gate the promotion on a successful worktree path.
- **Duplicate code (must extract):** the identical `tenant → repo_path` resolution block (~22 lines) is repeated **verbatim** in `setup_worktree` (lines ~66-88) and the blocked/done handler (lines ~143-165). Extract `resolve_repo_path(tenant, db_path)`.
- **Dead code + style:** `cmd_setup(parser)` is an empty `pass` stub (line ~267); `import re`/`import json` are done mid-function (lines ~187, ~208-209) instead of at module top.
- **Missing tests:** `test_dispatcher.py` (157 lines) does not cover the failure path (worktree setup failure must NOT promote to ready), the tenant-resolution fallbacks, the WIP-limit selection SQL, or the PR-flow transitions (`CHANGES_REQUESTED` priority decrement, `MERGED` done). A silent regression here breaks the entire pipeline.
- **Impact:** Medium (reliability of the whole pipeline); effort: medium.
- **Estimated impact:** Medium (reliability); effort: medium. **Task created → `t_9523eb18`.**

### 3. [MEDIUM / config] Tracked runtime artifact `.workspaces/sdp-compact-1782928112534` — STILL TRACKED
- **Where:** `.workspaces/sdp-compact-1782928112534` (verified present in `git ls-files`; currently deleted in working tree, uncommitted)
- **What:** Runtime/scratch artifact committed in `da7e2a4`. `.workspaces/` is not in `.gitignore`.
- **Impact:** Repo hygiene; risk of re-committing future artifacts.
- **Fix:** Folded into `t_70a26fcf` (step 4).
- **Estimated impact:** Low (hygiene); effort: trivial.

### 4. [LOW / config] `.env.example` model drift
- **Where:** `profiles/common/.env.example`
- **What:** Example pins an older model + an internal endpoint URL while the live config uses `qwen38-27b-unsloth-nvfp4-dflash2`. (Re-confirmed this run: `.env.example` holds no real key — good — but model/provider naming and the internal endpoint remain stale.)
- **Impact:** New clones get stale defaults; low-risk internal info disclosure.
- **Fix:** Align example with current provider/model naming; use placeholder URLs.
- **Estimated impact:** Low; effort: trivial.

### 5. [INFO / config] Working-tree drift in the scanned repo
- **Where:** `~/git/hotcode-dev/zerofactory`
- **What:** Uncommitted changes: `M profiles/common/config.yaml` (YAML re-indentation — cosmetic), deleted-but-uncommitted `.workspaces/sdp-compact-1782928112534`, and untracked `docs/` (this plan file).
- **Impact:** Minor hygiene; `config.yaml` drift should be normalized or committed through the normal task flow.
- **Fix:** Human or future task: commit or discard the `config.yaml` change via the normal flow; `docs/` should be added to `.gitignore` or committed.
- **Estimated impact:** Low; effort: trivial.

## Notes
- **No new Kanban boards were created** (per policy — scanner only reads existing boards).
- **1 new Kanban task created this run:** `t_9523eb18` (bug-fix, priority 3, tenant `~/git/hotcode-dev/zerofactory`). It bypassed the decomposer and was promoted to `ready`; the next dispatcher cycle auto-assigns it to `builder`.
- Max 1 task per run respected: 1 new created. The #1 security issue is intentionally **not** duplicated (already `t_70a26fcf`, blocked on infra).
- Scan of all projects succeeded (no missing deps / no skips).
