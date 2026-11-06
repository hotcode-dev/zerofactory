---
type: subsystem
title: Dispatch Engine
description: The dispatcher subsystem — run_dispatch_cycle lifecycle, multi-repo isolated Git worktrees, worker spawning with a spawn-grace period, the deterministic precommit self-healing gate, git/PR ops incl. the packaging-failure retry budget and the HTTPS-to-SSH push fallback, the per-commit review cap, automerge, and the WAL-tolerant stuck-worker reaper.
tags: [dispatcher, dispatch-loop, git-worktree, worker-spawning, precommit, github-pr, reaper, self-healing, multi-repo, automerge, spawn-grace]
sources:
  - id: openwiki-source-78d773f851580c376cac002d
    resource: repo://dispatcher/config.py
  - id: openwiki-source-5e3b047b4a47ae6a59b90052
    resource: repo://dispatcher/git_ops.py
  - id: openwiki-source-b9dde5e47d9b9a7f900ad216
    resource: repo://dispatcher/github_pr.py
  - id: openwiki-source-e7a6784a6e1f7f421dd572ed
    resource: repo://dispatcher/reaper.py
  - id: openwiki-source-9f9b3c9d5afeac588f3cdae1
    resource: repo://dispatcher/scheduler.py
  - id: openwiki-source-b73a2eae57b810a3ad15196e
    resource: repo://dispatcher/worker_spawner.py
  - id: openwiki-source-bd2c9dd479aa89010adee0f5
    resource: repo://dispatcher/worktree.py
generated: { by: "hermes", at: "2026-11-06T15:00:57.907Z" }
verified:
  - by: openwiki/0.6.0
    at: 2026-11-06T15:00:57.907Z
---

# Dispatch Engine

The dispatcher (`dispatcher/`) is the heart of the factory. Its job is to turn
Kanban `todo` cards into live specialist workers, keep each one inside an
isolated Git worktree, gate its output through a deterministic precommit
pipeline, open a GitHub PR, route it through review (or auto-merge it), and
reap anything that hangs.

## The core loop: `run_dispatch_cycle`

`run_dispatch_cycle` (`repo://dispatcher/scheduler.py#L38`) is the single
unit of work the dispatcher, the queue watchdog, and the CLI `dispatch` command
all trigger. It runs behind a process-level exclusive file lock so concurrent
cycles never corrupt board state (`repo://dispatcher/scheduler.py#L38-L76`).
Within one cycle it:

1. **Unblocks / promotes** — moves tasks whose parents are all `done` into
   `todo`, honoring task_links dependency gating.
2. **Claims** — picks `todo` tasks under the board's `max_concurrent_running`
   and the global `DEFAULT_MAX_CONCURRENT_WORKERS` /
   `DEFAULT_MAX_CONCURRENT_LLM_WORKERS` caps; the task-timeout (default 1h) and
   inactivity-timeout (default 15 min) budgets are read from the settings table
   with a database fallback
   (`repo://dispatcher/config.py#L159-L229`). EGM triage work is capped at a
   single concurrent worker: the claim query also counts running
   `zf-orchestrator` / `zf-goldfish` tasks and refuses to claim another one
   while one is in flight
   (`repo://dispatcher/scheduler.py#L164-L201`), and the claim stamps
   `triage_phase` (`elephant_drafting` → `goldfish_auditing`) so the reaper
   can advance the phase when each triage worker exits
   (`repo://dispatcher/scheduler.py#L345-L366`,
   `repo://dispatcher/reaper.py#L190-L216`).
3. **Provisions a worktree** — `setup_worktree` resolves the task's repository
   via `resolve_task_repo_path` against `board_repositories` and creates a
   dedicated `~/.zerofactory/workspaces/<board>/worktrees/<task_id>/<repo_alias>`
   worktree on a `task/<task_id>` branch, so a worker never touches `main`
   directly (`repo://dispatcher/worktree.py#L174-L588`).
4. **Spawns the worker** — `spawn_agent_worker` launches the assigned specialist
   as an isolated `hermes -p <assignee>` subprocess
   (`repo://dispatcher/worker_spawner.py#L69-L788`).
5. **Packages** — on worker completion the task stays `running` with
   `awaiting_pr` set; `_package_and_open_pr` runs the deterministic precommit
   gate, commits, merges against latest main, pushes (with an HTTPS→SSH
   fallback when the OAuth token lacks workflow scope), opens a GitHub PR, and
   routes the ticket to `zf-reviewer` (or auto-merges it when enabled),
   retrying up to 3 times before parking the task in `blocked`
   (`repo://dispatcher/scheduler.py#L1717`).
6. **Reaps** — `reap_stuck_tasks` / `reap_active_workers` detect and clean up
   hung workers (`repo://dispatcher/reaper.py`).

A background thread (`_dispatcher_loop` → `start_background_dispatcher`)
drives this every `DISPATCH_INTERVAL_SECONDS` (30s,
`repo://dispatcher/config.py#L78`).

## Isolated-worktree invariant

Every task executes in its own Git worktree on its own `task/<task_id>` branch
(`repo://dispatcher/worktree.py#L174-L588`). This is the load-bearing invariant:
workers never mutate `main`, parallel tasks don't clobber each other, and the
worktree + branch are the durable substrate that survives a worker crash. The
multi-repository layout keys the worktree by `<repo_alias>` so that sibling
repositories on the same board check out side-by-side under the shared
`~/.zerofactory/workspaces/<board>/worktrees/<task_id>/` root. Worktree
provisioning is bounded: every `git worktree add` runs under
`_WORKTREE_ADD_TIMEOUT` (30s, `repo://dispatcher/config.py#L98-L99`) and a
timeout/failed add triggers `git worktree prune` plus one retry, so a slow or
stuck checkout can never hang the dispatch cycle
(`repo://dispatcher/worktree.py#L354-L452`). When a task
completes or is abandoned, `_remove_worktree` / `_delete_remote_branch`
prune the worktree and remote branch
(`repo://dispatcher/worktree.py#L687-L852`). Merge conflicts are routed, not
swallowed: `_handle_local_merge_conflict` and `_handle_pr_conflict_from_github`
send the task back to `zf-builder` for conflict resolution
(`repo://dispatcher/worktree.py#L590-L686`, `repo://dispatcher/worktree.py#L854-L975`).

## Worker spawning

`spawn_agent_worker` resolves the `hermes` binary, builds a prompt (injecting
task context, board repository memories, and the review/handoff instructions),
and launches a **detached** subprocess with `stdin=DEVNULL`, `start_new_session=True`,
and `stderr=STDOUT` merged into the worker log, pinning `HERMES_HOME` to the
profile's home so the worker is fully isolated
(`repo://dispatcher/worker_spawner.py#L702-L726`). It then correlates the new
`session_id` against the profile's `state.db` via `resolve_profile_state_db`
(shared from `paths.py`) so the dashboard and dispatcher agree on which session
a task owns (`repo://dispatcher/worker_spawner.py#L741-L788`).

Prompt context is **pre-digested in Python** before the agent wakes:
`digest_reviewer_git_context` pre-computes the git log, diffstat, and a bounded
diff so the reviewer spends tokens on review, not on `git` exploration
(`repo://dispatcher/context_builder.py#L16-L209`). The reviewer prompt instructs
a **Ponytail anti-overengineering review** (diff hygiene, dependency veto,
YAGNI) and submission via `gh pr review --comment` — not `--approve` /
`--request-changes`, which GitHub blocks for the author's own token — with
`[AI:zf-reviewer]`-tagged comments; the builder prompt likewise tags its
GitHub output `[AI:zf-builder]`.

## Deterministic precommit + self-healing retry

Before any commit/PR, `run_deterministic_precommit` runs the worktree's
`.zerofactory/precommit.sh` (format → build → test) with a timeout, capturing
the full stdout/stderr (`repo://dispatcher/worktree.py#L977-L1025`). If it fails,
`_handle_precommit_failure` implements the **self-healing loop**
(`repo://dispatcher/worktree.py#L1027`):

- it increments `metadata["precommit_retries"]` and stores the last error;
- if retries are within `ZEROFACTORY_MAX_PRECOMMIT_RETRIES` (default **3**), it
  routes the task **back to `zf-builder` as a claimable `todo` retry** (clearing
  `awaiting_pr`) with the exact failing output injected into the respawned
  worker's prompt, so the agent can fix the regressions;
- once retries are exhausted it moves the task to **`blocked`** with
  `blocked_reason_type = "stuck"` and assignee `human` for inspection, and
  posts a failure comment (`repo://dispatcher/worktree.py#L942-L946`).

So a broken build or lint error never silently becomes a PR; the builder gets the
exact error logs to auto-fix (up to 3 retries), and only genuinely stuck work
escalates to a human.

## The packaging phase (`awaiting_pr` / `close_pr`)

`done` is strictly terminal, so the deterministic pipeline (precommit → commit
→ merge → push → PR → route to reviewer) runs while the task is still `running`,
marked by `metadata["awaiting_pr"] = true` (set by the dashboard `move_task`
when an agent actor reports completion, and by the reaper when it observes a
worker exit mid-package). `_package_and_open_pr`
(`repo://dispatcher/scheduler.py#L1717`) is the single owner of that
phase; it is idempotent and re-runs on the next cycle until it succeeds.
The phase also carries its own failure budget: any git/PR command failure
(including timeouts) routes to `_handle_packaging_failure`, which increments
`metadata["packaging_retries"]`, stores the first 2500 chars of the error in
`metadata["last_packaging_error"]`, and — once 3 attempts are exhausted —
parks the task in `blocked` with `blocked_reason_type = "stuck"`, assignee
`human`, a dispatcher comment, and a `packaging_failed` activity entry,
instead of looping the packaging step forever
(`repo://dispatcher/scheduler.py#L1666-L1715`). The `recover` endpoint and
`build_stuck_task_context` both surface/reset these counters
(`repo://dashboard/routes/tasks.py#L1564-L1677`,
(`repo://dispatcher/reaper.py#L816-L899`). When a task is closed terminally by a human or by a merged PR,
`_finalize_terminal_done` (`repo://dispatcher/scheduler.py#L2289`) only
cleans up — stopping any stale worker, pruning the worktree, and, when
`close_pr` is set, closing the open PR and deleting the remote branch so
GitHub matches the board. It never commits, pushes, opens a PR, or routes the
task back to review. When automerge is active, the PR-poll path instead marks
the task `done` directly after `attempt_pr_automerge` succeeds (see Git & PR
ops).

## Git & PR ops

- **`git_ops.py`** — low-level git plumbing: resolving the default branch,
  syncing `main`, detecting and resolving **unresolved conflict markers**, and
  cleaning stale git locks (`repo://dispatcher/git_ops.py`).
- **`github_pr.py`** — PR interaction: fetching PR review comments, formatting
  them into task comments, and deciding which comments actually demand builder
  action. **`ai_prefix(text, role="zf-builder")`** prepends a **role-tagged**
  marker `[AI:<role>]` (e.g. `[AI:zf-builder]`, `[AI:zf-reviewer]`) to
  agent-authored GitHub text; it is idempotent — any existing role-tagged
  `[AI:<role>]` marker (matched by `AI_PREFIX_RE`) is left untouched so
  re-writes never double-prefix, and a bare `[AI]` is no longer produced
  (`repo://dispatcher/github_pr.py#L324-L336`).
  **`is_actionable_review_comment`** filters PR comments down to genuine
  reviewer/human critiques: approval verdicts, builder-authored notes,
  automated notifications, and dedup notes are excluded, so only actionable
  feedback re-opens a task (`repo://dispatcher/github_pr.py#L475-L528`).
- **Auto-merge** — when a board (or task) opts into auto-merge, the PR-poll
  path resolves it with `is_task_automerge_enabled` (precedence: opt-out
  `hitl`/`manual-review` tags/labels → false; opt-in `automerge`/`yolo` → true;
  else the board `automerge` default) and executes `attempt_pr_automerge` via
  the `gh` CLI (squash + delete-branch, falling back to `--auto --squash` when
  status checks or required reviews gate the merge). The PR-poll query
  selects the task's `tags` (and `description`) columns when present, and
  `_poll_pr_and_route_review` falls back to a `SELECT tags FROM tasks` lookup
  by task id when the row lacks a `tags` field, so task-level `automerge`
  tags apply even on older query shapes. On success the dispatcher
  stops the worker, prunes the worktree and remote branch, and moves the task
  to `done` directly; on failure it parks the task for a human
  (`repo://dispatcher/github_pr.py#L529-L587`,
  `repo://dispatcher/scheduler.py#L104-L106`, `repo://dispatcher/scheduler.py#L465-L470`, `repo://dispatcher/scheduler.py#L1527-L1535`).
- **Per-commit review cap** — when a reviewer's actionable comments route a task
  back to the builder, the dispatcher tracks `commit_review_count` in task
  metadata keyed to the PR's `headRefOid` (reset to 0 whenever the head commit
  changes, so a new commit restarts the round budget). The cap is
  `ZEROFACTORY_MAX_REVIEW_ROUNDS` (default **2**): exceeding it sets
  `review_cap_reached` and `blocked_reason_type = "human-gate"`, assigns the
  task to `human`, and moves it to `blocked` instead of looping builder ↔
  reviewer forever (`repo://dispatcher/scheduler.py#L1374-L1448`).
- **External-issue PR linkage** — when a task carries `external_issue` metadata
  (see [External Issue Import](/openwiki/components/issues-importer.md)), the
  PR body the dispatcher opens appends `Fixes #<n>` (GitHub) or
  `Resolves: <KEY>` (Jira) so merging the PR closes the source issue
  (`repo://dispatcher/scheduler.py#L2116-L2133`); for GitHub issues the
  dispatcher additionally posts a single idempotent "PR opened" status reply on
  the source issue via `post_issue_pr_comment` (gated on `has_ai_request`,
  marker-deduped with `<!-- zf-task:<task_id> -->`)
  (`repo://dispatcher/scheduler.py#L925-L1012`).
- **HTTPS→SSH push fallback** — when `git push` of the task branch is rejected
  because the GitHub OAuth token lacks the `workflow` scope, the dispatcher
  derives the SSH URL from the `https://github.com/…` origin remote, retries the
  push against `git@github.com:…`, and — on success — rewrites the worktree's
  `origin` remote, the base repo's remote, and the `board_repositories.git_url`
  row to the SSH URL so subsequent pushes stay on SSH
  (`repo://dispatcher/scheduler.py#L2008-L2086`).

## Reaper

`reaper.py` detects hung workers using a shared `_compute_stuck_state` (a
per-task max running time plus an inactivity timeout) so `reap_active_workers`
(the only path that kills processes) and `check_stuck_tasks` (reporting /
manual reap) cannot drift apart. Because the dashboard holds many open
connections plus an active writer, the reaper opens **WAL-tolerant**
connections: `_open_reaper_conn` sets `PRAGMA busy_timeout=15000`, and
`reap_stuck_tasks` retries on `sqlite3.OperationalError` "database is locked"
with capped exponential backoff (~30s) and returns a clean failure dict instead
of raising, so a busy DB can never abort the watchdog tick
(`repo://dispatcher/reaper.py#L33-L38`, `repo://dispatcher/reaper.py#L787-L800`). `reap_active_workers`
terminates a worker that exceeded its budget and records the session end;
`reap_stuck_tasks` is the entry the watchdog and `check-stuck` CLI use.

Worker-failure handling is **retry-oriented, not terminal**: a crashed or
vanished worker is routed back to `todo` when it was already `running` (so the
dispatcher re-spawns it on the next cycle, up to `DEFAULT_MAX_WORKER_RETRIES`)
and only escalates to `blocked` when the task was parked elsewhere
(`repo://dispatcher/reaper.py#L272-L330`, `repo://dispatcher/reaper.py#L345-L411`). The reaper recognizes two more
states: the **packaging phase** (a `running` task with `awaiting_pr` set is
owned by `_package_and_open_pr` and is deliberately skipped rather than treated
as an orphan, `repo://dispatcher/reaper.py#L337-L344`, `repo://dispatcher/reaper.py#L407-L414`) and the **spawn grace
period** — a freshly claimed task with a `spawning_at` timestamp younger than
`DEFAULT_SPAWN_GRACE_SECONDS` (180s) is treated as "spawn in flight", not an
orphan, so the reaper does not double-dispatch the builder mid-startup
(`repo://dispatcher/reaper.py#L407-L444`). The exhausted-retry path instead
stamps `blocked_reason_type = "stuck"` on the parked task
(`repo://dispatcher/reaper.py#L455-L495`).

## Step logging

Every pipeline step emits paired, grep-able markers in
`~/.hermes/logs/agent.log` — `STEP <name> start | task=<id> | …` and
`STEP <name> end | task=<id> | <outcome> | <duration>s | …` — via
`StepTracker` / `log_step_start` / `log_step_end`
(`repo://dispatcher/config.py`). Steps covered: `worktree.setup`,
`worker.spawn`, `package.precheck` → `package.precommit` → `package.commit` →
`package.merge` → `package.push` → `package.pr` → `package.route_reviewer`,
`done.cleanup`, `move`, and the `pr_poll` verdict check. Recurring gate
decisions use `log_step_state`, which rate-limits repeats (first occurrence
plus every state change, then at most once per 15 minutes) so the 30s poll
loop leaves breadcrumbs — e.g. `skip | no candidate (assignee=human, …)` —
instead of flooding the log. A `start` without a matching `end` pinpoints the
step that died; the full grep playbook lives in
`repo://docs/DEBUGGING.md` §2b.

## Relationships

Upstream: claims work off the durable Kanban SQLite substrate described in
[Architecture](/openwiki/architecture.md). Downstream: the deterministic
precommit and PR ops hand off to the reviewer, and the dashboard / cron layer
(`Dashboard, Cron & Automation`) triggers `run_dispatch_cycle` and inspects
worker liveness. Coding rules for touching this code live in
[Conventions](/openwiki/conventions.md).
