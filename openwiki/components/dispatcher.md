---
type: subsystem
title: Dispatch Engine
description: The dispatcher subsystem — run_dispatch_cycle lifecycle, isolated Git worktrees, worker spawning, the deterministic precommit self-healing gate, git/PR ops, and the stuck-worker reaper.
tags: [dispatcher, dispatch-loop, git-worktree, worker-spawning, precommit, github-pr, reaper, self-healing]
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
generated: { by: "hermes", at: "2026-10-03T01:15:19.967Z" }
verified:
  - by: openwiki/0.6.0
    at: 2026-10-03T01:15:19.967Z
---

# Dispatch Engine

The dispatcher (`dispatcher/`) is the heart of the factory. Its job is to turn
Kanban `ready` cards into live specialist workers, keep each one inside an
isolated Git worktree, gate its output through a deterministic precommit
pipeline, open a GitHub PR, route it through review, and reap anything that
hangs.

## The core loop: `run_dispatch_cycle`

`run_dispatch_cycle` (`repo://dispatcher/scheduler.py#L36`) is the single
unit of work the dispatcher, the queue watchdog, and the CLI `dispatch` command
all trigger. It runs behind a process-level exclusive file lock so concurrent
cycles never corrupt board state (`repo://dispatcher/scheduler.py#L36-L70`).
Within one cycle it:

1. **Unblocks / promotes** — moves tasks whose parents are all `done` into
   `ready`, honoring task_links dependency gating.
2. **Claims** — picks `ready` tasks under the board's `max_concurrent_running`
   and the global `DEFAULT_MAX_CONCURRENT_WORKERS` /
   `DEFAULT_MAX_CONCURRENT_LLM_WORKERS` caps (`repo://dispatcher/config.py#L79-L111`).
3. **Provisions a worktree** — `setup_worktree` creates a dedicated
   `<reponame>-worktrees/<task_id>` worktree on a `task/<task_id>` branch, so a
   worker never touches `main` directly
   (`repo://dispatcher/worktree.py#L90-L140`).
4. **Spawns the worker** — `spawn_agent_worker` launches the assigned specialist
   as an isolated `hermes -p <assignee>` subprocess
   (`repo://dispatcher/worker_spawner.py#L67`).
5. **Gates, commits, opens PR** — on worker completion it runs the deterministic
   precommit gate, commits, merges against latest main, pushes, opens a GitHub
   PR, and routes the ticket to `zf-reviewer`.
6. **Reaps** — `reap_stuck_tasks` / `reap_active_workers` detect and clean up
   hung workers (`repo://dispatcher/reaper.py#L94-L453`).

A background thread (`_dispatcher_loop` → `start_background_dispatcher`,
`repo://dispatcher/scheduler.py#L1412-L1444`) drives this every
`DISPATCH_INTERVAL_SECONDS` (30s).

## Isolated-worktree invariant

Every task executes in its own Git worktree on its own `task/<task_id>` branch
(`repo://dispatcher/worktree.py#L90-L140`). This is the load-bearing invariant:
workers never mutate `main`, parallel tasks don't clobber each other, and the
worktree + branch are the durable substrate that survives a worker crash. When a
task completes or is abandoned, `_remove_worktree` / `_delete_remote_branch`
prune the worktree and remote branch
(`repo://dispatcher/worktree.py#L388-L425`). Merge conflicts are routed, not
swallowed: `_handle_local_merge_conflict` and `_handle_pr_conflict_from_github`
send the task back to `zf-builder` for conflict resolution
(`repo://dispatcher/worktree.py#L292-L607`).

## Worker spawning

`spawn_agent_worker` resolves the `hermes` binary, builds a prompt (injecting
task context, board repository memories, and the review/handoff instructions),
and launches a **detached** subprocess with `stdin=DEVNULL` and `stderr=STDOUT`
merged into the worker log, pinning `HERMES_HOME` to the profile's home so the
worker is fully isolated
(`repo://dispatcher/worker_spawner.py#L303-L342`). It then correlates the new
`session_id` against the profile's `state.db` via `resolve_profile_state_db` so
the dashboard and dispatcher agree on which session a task owns
(`repo://dispatcher/worker_spawner.py#L356-L378`).

Prompt context is **pre-digested in Python** before the agent wakes:
`digest_reviewer_git_context` pre-computes the git log, diffstat, and a bounded
diff so the reviewer spends tokens on review, not on `git` exploration
(`repo://dispatcher/context_builder.py#L15-L88`). The reviewer prompt instructs
a **Ponytail anti-overengineering review** (diff hygiene, dependency veto,
YAGNI) and submission via `gh pr review --comment` — not `--approve` /
`--request-changes`, which GitHub blocks for the author's own token — with
`[AI:zf-reviewer]`-tagged comments; the builder prompt likewise tags its
GitHub output `[AI:zf-builder]`
(`repo://dispatcher/worker_spawner.py#L120-L160`).

## Deterministic precommit + self-healing retry

Before any commit/PR, `run_deterministic_precommit` runs the worktree's
`.zerofactory/precommit.sh` (format → build → test) with `CI=1` and a timeout,
capturing the full stdout/stderr (`repo://dispatcher/worktree.py#L608-L656`).
If it fails, `_handle_precommit_failure` implements the **self-healing loop**:

- it increments `metadata["precommit_retries"]` and stores the last error
  (`repo://dispatcher/worktree.py#L666-L670`);
- if retries are within `ZEROFACTORY_MAX_PRECOMMIT_RETRIES` (default **3**), it
  routes the task **back to `zf-builder` in `running`** with the exact failing
  output so the agent can fix the regressions
  (`repo://dispatcher/worktree.py#L658-L700`);
- once retries are exhausted it moves the task to **`blocked`** for human
  inspection and posts a failure comment
  (`repo://dispatcher/worktree.py#L658-L700`).

So a broken build or lint error never silently becomes a PR; the builder gets the
exact error logs to auto-fix (up to 3 retries), and only genuinely stuck work
escalates to a human.

## Git & PR ops

- **`git_ops.py`** — low-level git plumbing: resolving the default branch,
  syncing `main`, detecting and resolving **unresolved conflict markers**, and
  cleaning stale git locks (`repo://dispatcher/git_ops.py#L14-L416`).
- **`github_pr.py`** — PR interaction: fetching PR review comments, formatting
  them into task comments, and deciding which comments actually demand builder
  action. **`ai_prefix(text, role="zf-builder")`** prepends a **role-tagged**
  marker `[AI:<role>]` (e.g. `[AI:zf-builder]`, `[AI:zf-reviewer]`) to
  agent-authored GitHub text; it is idempotent — any existing `[AI]` /
  `[AI:<tag>]` marker (matched by `AI_PREFIX_RE`) is left untouched so
  re-writes never double-prefix
  (`repo://dispatcher/github_pr.py#L321-L335`).
  **`is_actionable_review_comment`** filters PR comments down to genuine
  reviewer/human critiques: approval verdicts, builder-authored notes,
  automated notifications, and dedup notes are excluded, so only actionable
  feedback re-opens a task
  (`repo://dispatcher/github_pr.py#L477-L532`).
- **Per-commit review cap** — when a reviewer's actionable comments route a task
  back to the builder, the dispatcher tracks `commit_review_count` in task
  metadata keyed to the PR's `headRefOid` (reset to 0 whenever the head commit
  changes, so a new commit restarts the round budget). The cap is
  `ZEROFACTORY_MAX_REVIEW_ROUNDS` (default **2**): exceeding it sets
  `review_cap_reached`, renames the task with `[Human Review]`, assigns it to
  `human`, and moves it to `blocked` instead of looping builder ↔ reviewer
  forever (`repo://dispatcher/scheduler.py#L749-L847`).
- **External-issue PR linkage** — when a task carries `external_issue` metadata
  (see [External Issue Import](/openwiki/components/issues-importer.md)), the
  PR body the dispatcher opens appends `Fixes #<n>` (GitHub) or
  `Resolves: <KEY>` (Jira) so merging the PR closes the source issue
  (`repo://dispatcher/scheduler.py#L1277-L1295`).

## Reaper

`reaper.py` detects hung workers using two clocks: a per-task max running time
(`DEFAULT_TASK_TIMEOUT_SECONDS`, 1h) and an inactivity timeout
(`DEFAULT_INACTIVITY_TIMEOUT_SECONDS`, 15 min with no log/session update)
(`repo://dispatcher/config.py#L79-L85`). `reap_active_workers` terminates a
worker that exceeded its budget and records the session end; `reap_stuck_tasks`
is the entry the watchdog and `check-stuck` CLI use
(`repo://dispatcher/reaper.py#L94-L453`).

## Relationships

Upstream: claims work off the durable Kanban SQLite substrate described in
[Architecture](/openwiki/architecture.md). Downstream: the deterministic
precommit and PR ops hand off to the reviewer, and the dashboard / cron layer
(`Dashboard, Cron & Automation`) triggers `run_dispatch_cycle` and inspects
worker liveness. Coding rules for touching this code live in
[Conventions](/openwiki/conventions.md).
