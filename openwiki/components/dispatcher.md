---
type: subsystem
title: Dispatch Engine
description: The dispatcher subsystem — the centralized 13-stage task state machine, the run_dispatch_cycle lifecycle (in-dispatcher improvement scanner, autonomous recovery routing), multi-repo isolated Git worktrees, worker spawning with a spawn-grace period, the deterministic precommit self-healing gate plus the zero-token anti-slop diff gate, git/PR ops incl. the packaging-failure retry budget and the HTTPS-to-SSH push fallback, the per-commit review cap, automerge, and the WAL-tolerant stuck-worker reaper.
tags: [dispatcher, dispatch-loop, state-machine, git-worktree, worker-spawning, precommit, anti-slop, github-pr, reaper, self-healing, multi-repo, automerge, spawn-grace, recovery]
sources:
  - id: openwiki-source-c705147b9966f3d6f300034a
    resource: repo://dashboard/routes/tasks.py
  - id: openwiki-source-78d773f851580c376cac002d
    resource: repo://dispatcher/config.py
  - id: openwiki-source-5e3b047b4a47ae6a59b90052
    resource: repo://dispatcher/git_ops.py
  - id: openwiki-source-b9dde5e47d9b9a7f900ad216
    resource: repo://dispatcher/github_pr.py
  - id: openwiki-source-e7a6784a6e1f7f421dd572ed
    resource: repo://dispatcher/reaper.py
  - id: openwiki-source-ecd05021670a16c89458cec0
    resource: repo://dispatcher/scanner.py
  - id: openwiki-source-9f9b3c9d5afeac588f3cdae1
    resource: repo://dispatcher/scheduler.py
  - id: openwiki-source-0445f3be32f0f8efe9dfeca4
    resource: repo://dispatcher/slop_gate.py
  - id: openwiki-source-1cbc0eb99c8b57cd43185064
    resource: repo://dispatcher/state_machine.py
  - id: openwiki-source-b73a2eae57b810a3ad15196e
    resource: repo://dispatcher/worker_spawner.py
  - id: openwiki-source-bd2c9dd479aa89010adee0f5
    resource: repo://dispatcher/worktree.py
generated: { by: "hermes", at: "2026-11-23T15:15:28.452Z" }
verified:
  - by: openwiki/0.6.0
    at: 2026-11-23T15:15:28.452Z
---

# Dispatch Engine

The dispatcher (`dispatcher/`) is the heart of the factory. Its job is to turn
Kanban `todo` cards into live specialist workers, keep each one inside an
isolated Git worktree, gate its output through a deterministic precommit
pipeline, open a GitHub PR, route it through review (or auto-merge it), and
reap anything that hangs. Every task status/assignee move funnels through one
validated primitive — `transition_task` in `repo://dispatcher/state_machine.py`
— so the reaper, the scheduler, and the dashboard's `move_task` never disagree
about a legal move.

## The centralized 13-stage state machine

`VALID_TRANSITIONS` (`repo://dispatcher/state_machine.py#L13-L286`) defines the
legal edges between the five storage statuses; `transition_task`
(`repo://dispatcher/state_machine.py#L30`) validates each move against that
graph and raises `InvalidStateTransitionError` for illegal edges (non-human
actors are rejected from any edge outside the graph). Canonical assignee
resolution for a target status is delegated to `resolve_status_assignee` in
`repo://paths.py`, keeping the `(status, assignee)` invariant consistent
everywhere a transition happens.

## The core loop: `run_dispatch_cycle`

`run_dispatch_cycle` (`repo://dispatcher/scheduler.py#L40`) is the single
unit of work the dispatcher, the queue watchdog, and the CLI `dispatch` command
all trigger. It runs behind a process-level exclusive file lock so concurrent
cycles never corrupt board state (`repo://dispatcher/scheduler.py#L40-L90`).
Within one cycle it:

1. **Unblocks / promotes** — moves tasks whose parents are all `done` into
   `todo`, honoring task_links dependency gating.
2. **Claims** — picks `todo` tasks under the board's `max_concurrent_running`
   and the global `DEFAULT_MAX_CONCURRENT_WORKERS` /
   `DEFAULT_MAX_CONCURRENT_LLM_WORKERS` caps; the task-timeout (default 1h) and
   inactivity-timeout (default 15 min) budgets are read from the settings table
   with a database fallback
   (`repo://dispatcher/config.py#L22-L23`,
   `repo://dispatcher/config.py#L169-L239`). EGM triage work is capped at a
   single concurrent worker: the claim query also counts running
   `zf-orchestrator` / `zf-goldfish` tasks and refuses to claim another one
   while one is in flight
   (`repo://dispatcher/scheduler.py#L160-L218`), and the claim stamps
   `triage_phase` (`elephant_drafting` → `goldfish_auditing`) so the reaper
   can advance the phase when each triage worker exits
   (`repo://dispatcher/scheduler.py#L365-L382`,
   `repo://dispatcher/reaper.py#L260-L280`).
3. **Provisions a worktree** — `setup_worktree` resolves the task's repository
   via `resolve_task_repo_path` against `board_repositories` and creates a
   dedicated `~/.zerofactory/workspaces/<board>/worktrees/<task_id>/<repo_alias>`
   worktree on a `task/<task_id>` branch, so a worker never touches `main`
   directly (`repo://dispatcher/worktree.py#L230-L645`).
4. **Spawns the worker** — `spawn_agent_worker` launches the assigned specialist
   as an isolated `hermes -p <assignee>` subprocess
   (`repo://dispatcher/worker_spawner.py#L118-L856`).
5. **Packages** — on worker completion the task stays `running` with
   `awaiting_pr` set; `_package_and_open_pr` runs the deterministic precommit
   gate, then the zero-token anti-slop gate, commits, merges against latest main,
   pushes (with an HTTPS→SSH fallback when the OAuth token lacks workflow scope),
   opens a GitHub PR, and routes the ticket to `zf-reviewer` (or auto-merges it
   when enabled), retrying up to 3 times before parking the task in `blocked`
   (`repo://dispatcher/scheduler.py#L1721-L2368`).
6. **Reaps** — `reap_stuck_tasks` / `reap_active_workers` detect and clean up
   hung workers (`repo://dispatcher/reaper.py#L880-L1065`,
   `repo://dispatcher/reaper.py#L151-L691`).

A background thread (`_dispatcher_loop` → `start_background_dispatcher`)
drives this every `DISPATCH_INTERVAL_SECONDS` (30s,
`repo://dispatcher/config.py#L82`,
`repo://dispatcher/scheduler.py#L2437-L2446`), and the dashboard exposes
start/stop/status controls for that loop via
`repo://dashboard/routes/dispatch.py`.

## The in-dispatcher improvement scanner

The per-board improvement scanner runs **inside the dispatcher process**
rather than as an external cron daemon (`repo://dispatcher/scanner.py#L86-L310`).
Each dispatch cycle reaps dead scanner PIDs with `reap_active_scanners`
(`repo://dispatcher/scheduler.py#L123`), and when a board's active task count
is below its cap, its `todo` count is below `idle_scan_max_todo`, no scanner is
active for that board, and the `get_scanner_cron_config`
(`repo://dispatcher/scanner.py#L130-L187`) cooldown has elapsed, the cycle
launches a background `zf-orchestrator` scan of the board's repositories via
`spawn_board_scanner` (`repo://dispatcher/scanner.py#L188-L296`,
`repo://dispatcher/scheduler.py#L808-L834`). The scanner prompt instructs
`zf-orchestrator` to file findings directly in `todo` assigned to
`zf-builder` (`--status todo --assignee zf-builder`, respecting
`idle_scan_max_todo`) so the dispatcher picks them up without a human
triage step (`repo://dispatcher/scanner.py#L225-L227`). Lifecycle helpers —
`get_active_scanner_pids`, `kill_board_scanner`, `reset_idle_scanner_state` —
sit alongside in the same module (`repo://dispatcher/scanner.py#L33-L85`,
`repo://dispatcher/scanner.py#L299-L310`).

## Isolated-worktree invariant

Every task executes in its own Git worktree on its own `task/<task_id>` branch
(`repo://dispatcher/worktree.py#L230-L645`). This is the load-bearing invariant:
workers never mutate `main`, parallel tasks don't clobber each other, and the
worktree + branch are the durable substrate that survives a worker crash. The
multi-repository layout keys the worktree by `<repo_alias>` so that sibling
repositories on the same board check out side-by-side under the shared
`~/.zerofactory/workspaces/<board>/worktrees/<task_id>/` root. Worktree
provisioning is bounded: every `git worktree add` runs under
`_WORKTREE_ADD_TIMEOUT` (30s, `repo://dispatcher/config.py#L103`) and a
timeout/failed add triggers `git worktree prune` plus one retry, so a slow or
stuck checkout can never hang the dispatch cycle
(`repo://dispatcher/worktree.py#L412-L452`). When a task
completes or is abandoned, `_delete_remote_branch` / `_remove_worktree`
prune the worktree and remote branch
(`repo://dispatcher/worktree.py#L765-L931`). Merge conflicts are routed, not
swallowed: `_handle_local_merge_conflict` and `_handle_pr_conflict_from_github`
send the task back to `zf-builder` for conflict resolution
(`repo://dispatcher/worktree.py#L646-L764`,
`repo://dispatcher/worktree.py#L932-L1076`), and once the conflict-retry budget
is exhausted the first exhaustion stamps `triage_phase = "recovery"` and routes
the task to `zf-orchestrator` for one autonomous diagnostic attempt (gated on
`orchestrator_recovery_count < 1`), otherwise parking it in `blocked` for a
human (`repo://dispatcher/worktree.py#L684-L700`).

## Worker spawning

`spawn_agent_worker` resolves the `hermes` binary, builds a prompt (injecting
task context, board repository memories, and the review/handoff instructions),
and launches a **detached** subprocess with `stdin=DEVNULL`,
`start_new_session=True`,
and `stderr=STDOUT` merged into the worker log, pinning `HERMES_HOME` to the
profile's home so the worker is fully isolated
(`repo://dispatcher/worker_spawner.py#L787-L795`). It then correlates the new
`session_id` against the profile's `state.db` via `resolve_profile_state_db`
(shared from `paths.py`) so the dashboard and dispatcher agree on which session
a task owns (`repo://dispatcher/worker_spawner.py#L809-L812`). The spawn
command is `--cli chat -q <prompt>`; `--yolo --accept-hooks` are appended only
when the `allow_unattended_approvals` setting is enabled
(`repo://dispatcher/worker_spawner.py#L759-L761`).

For `zf-reviewer` specifically, the spawn resolves the target branch
repo-alias-aware (`board_repositories` by `(board_slug, repo_alias)`, falling
back to the board's first repository row) and injects a
`Review Round: Round X of Y` header into the prompt so the reviewer knows its
position in the review budget before escalating
(`repo://dispatcher/worker_spawner.py#L238-L326`).

Prompt context is **pre-digested in Python** before the agent wakes:
`digest_reviewer_git_context` pre-computes the git log, diffstat, and a bounded
diff (default 400 lines / 24000 chars) so the reviewer spends tokens on review,
not on `git` exploration
(`repo://dispatcher/context_builder.py#L16-L183`), and
`digest_board_memories_context` injects the most relevant Mem0/board-memory
entries into the same prompt (`repo://dispatcher/context_builder.py#L186`).
The reviewer digest also receives `spec_text` (the task's specification or
description) and `skip_untested_check` so the embedded diff-hygiene scorecard
applies the same Do Not Touch / untested-production boundaries as the
packaging gate. The reviewer prompt instructs a **Ponytail
anti-overengineering review** (diff hygiene, dependency veto, YAGNI) and
submission via `gh pr review --comment` — not `--approve` /
`--request-changes`, which GitHub blocks for the author's own token — with
`[AI:zf-reviewer]`-tagged comments (the attribution example interpolates the
live round number); the builder prompt likewise tags its GitHub output
`[AI:zf-builder]` (`repo://dispatcher/worker_spawner.py#L316-L317`,
`repo://dispatcher/worker_spawner.py#L707`).

## Deterministic precommit + self-healing retry

Before any commit/PR, `run_deterministic_precommit` runs the worktree's
`.zerofactory/precommit.sh` (format → build → test) with a timeout, capturing
the full stdout/stderr (`repo://dispatcher/worktree.py#L1077-L1126`). If it
fails, `_handle_precommit_failure` implements the **self-healing loop**
(`repo://dispatcher/worktree.py#L1127-L1269`):

- it increments `metadata["precommit_retries"]` and stores the last error;
- if retries are within `ZEROFACTORY_MAX_PRECOMMIT_RETRIES` (default **3**), it
  routes the task **back to `zf-builder` as a claimable `todo` retry** (clearing
  `awaiting_pr`) with the exact failing output injected into the respawned
  worker's prompt, so the agent can fix the regressions;
- once retries are exhausted the first exhaustion stamps
  `triage_phase = "recovery"` and routes the task to `zf-orchestrator` for one
  autonomous diagnostic attempt (gated on `orchestrator_recovery_count < 1`);
  a second exhaustion moves the task to **`blocked`** with
  `blocked_reason_type = "stuck"` and assignee `human` for inspection, and
  posts a failure comment
  (`repo://dispatcher/worktree.py#L1165-L1185`,
  `repo://dispatcher/worktree.py#L1249-L1268`).

So a broken build or lint error never silently becomes a PR; the builder gets the
exact error logs to auto-fix (up to 3 retries), and only work that is still stuck
after one orchestrator diagnostic attempt escalates to a human.

## The deterministic anti-slop gate

After precommit passes, the packaging phase runs the **zero-token deterministic
anti-slop gate** (`run_deterministic_slop_gate` in
`repo://dispatcher/slop_gate.py#L736`, wired in at
`repo://dispatcher/scheduler.py#L1962-L1993`) before any commit/PR is authored.
It is invoked with the resolved board target branch plus the task's spec/description
text (`spec_text`) and a `skip_untested_check` flag so spec-level boundaries apply
even to paths excluded from the diff. It scans the full diff for leftover debugger
statements, unresolved `TODO`/`FIXME`/`XXX`/`HACK` placeholder comments, and skipped
tests — any violation is an error that blocks packaging and re-spawns the builder with
the exact findings (routing back through `_handle_precommit_failure`, sharing the same
retry budget). It additionally errors on assertion-free newly added test functions
(`assertion_free_test`), on production code that adds more than 20 net lines
(`DEFAULT_UNTESTED_PROD_LINE_THRESHOLD`) without any test lines
(`untested_production_diff`, skippable per task via `skip_untested_check` or the
`ZEROFACTORY_SKIP_UNTESTED_CHECK` env var), and on modifications of files named in the
task spec's "Do Not Touch" / "Non-Goals" section
(`extract_do_not_touch_patterns` / `_matches_do_not_touch`,
`repo://dispatcher/slop_gate.py#L150-L209`). The net-line budget
(`diff_budget_exceeded`) now defaults to **800** lines
(`DEFAULT_MAX_DIFF_LINES`, `repo://dispatcher/slop_gate.py#L111-L114`) and is
overridden by `ZEROFACTORY_MAX_DIFF_LINES` (≤ 0 disables it). Large diffs, net
test-line deletions, dependency-manifest changes, and newly added lint/type suppressors
remain warnings, and mock-heavy test additions (≥ 4 mocks with more mocks than
assertions) are flagged as a `mock_heavy_test` warning. The gate's compact markdown
(`build_diff_hygiene_scorecard`, `repo://dispatcher/slop_gate.py#L778`) is
pre-digested into the `zf-reviewer` prompt so review starts from a quantitative
diff summary rather than a raw diff.

## The packaging phase (`awaiting_pr` / `close_pr`)

`done` is strictly terminal, so the deterministic pipeline (precommit →
anti-slop gate → commit → merge → push → PR → route to reviewer) runs while the
task is still `running`,
marked by `metadata["awaiting_pr"] = true` (set by the dashboard `move_task`
when an agent actor reports completion, and by the reaper when it observes a
worker exit mid-package). `_package_and_open_pr`
(`repo://dispatcher/scheduler.py#L1784-L2387`) is the single owner of that
phase; it is idempotent and re-runs on the next cycle until it succeeds.
The phase also carries its own failure budget: any git/PR command failure
(including timeouts) routes to `_handle_packaging_failure`, which increments
`metadata["packaging_retries"]`, stores the first 2500 chars of the error in
`metadata["last_packaging_error"]`, and — once 3 attempts are exhausted —
parks the task in `blocked` with `blocked_reason_type = "stuck"`, assignee
`human`, a dispatcher comment, and a `packaging_failed` activity entry,
instead of looping the packaging step forever
(`repo://dispatcher/scheduler.py#L1733-L1781`). The `recover` endpoint and
`build_stuck_task_context` both surface/reset these counters
(`repo://dashboard/routes/tasks.py#L1678-L1775`,
`repo://dispatcher/reaper.py#L982-L1065`). When a task is closed terminally by a human or by a merged PR,
`_finalize_terminal_done` (`repo://dispatcher/scheduler.py#L2390-L2454`) only
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
  status checks or required reviews gate the merge)
  (`repo://dispatcher/github_pr.py#L529-L633`). The PR-poll query
  selects the task's `tags` (and `description`) columns when present, and
  `_poll_pr_and_route_review` falls back to a `SELECT tags FROM tasks` lookup
  by task id when the row lacks a `tags` field, so task-level `automerge`
  tags apply even on older query shapes. On success the dispatcher
  stops the worker, prunes the worktree and remote branch, and moves the task
  to `done` directly; on failure it parks the task for a human
  (`repo://dispatcher/scheduler.py#L1596-L1650`).
- **Per-PR review cap** — when a reviewer's actionable comments route a task
  back to the builder, the dispatcher increments `review_round` in task
  metadata (written alongside the legacy `commit_review_count` for
  compatibility). The counter is a **per-PR** round count and is *not* reset
  when the PR head commit changes, so each new commit does not restart the
  budget. The cap is `ZEROFACTORY_MAX_REVIEW_ROUNDS` (default **2**): once
  `review_round >= max` the dispatcher sets `review_cap_reached` and
  `blocked_reason_type = "human-gate"`, assigns the task to `human`, and moves
  it to `blocked` instead of looping builder ↔ reviewer forever. Once
  `review_cap_reached` is set, subsequent polls of that blocked/human task
  early-return when no new PR comments have arrived, so the cap is applied exactly
  once (`repo://dispatcher/scheduler.py#L1437-L1483`,
  `repo://dispatcher/scheduler.py#L1344-L1351`). The `recover` endpoint clears
  `review_cap_reached`, `review_round`, and `commit_review_count`, giving a
  human-recovered task a fresh round budget
  (`repo://dashboard/routes/tasks.py#L1724-L1726`).
- **External-issue PR linkage** — when a task carries `external_issue` metadata
  (see [External Issue Import](/openwiki/components/issues-importer.md)), the
  PR body the dispatcher opens appends `Fixes #<n>` for GitHub issues (a legacy
  `Resolves: <KEY>` branch still exists for pre-Jira-removal `jira`-source
  metadata rows) so merging the PR closes the source issue
  (`repo://dispatcher/scheduler.py#L2199-L2216`); for GitHub issues the
  dispatcher additionally posts a single idempotent "PR opened" status reply on
  the source issue via `post_issue_pr_comment` (gated on `has_ai_request`,
  marker-deduped with `<!-- zf-task:<task_id> -->`)
  (`repo://dispatcher/scheduler.py#L961-L1048`).
- **HTTPS→SSH push fallback** — when `git push` of the task branch is rejected
  because the GitHub OAuth token lacks the `workflow` scope, the dispatcher
  derives the SSH URL from the `https://github.com/…` origin remote, retries the
  push against `git@github.com:…`, and — on success — rewrites the worktree's
  `origin` remote, the base repo's remote, and the `board_repositories.git_url`
  row to the SSH URL so subsequent pushes stay on SSH
  (`repo://dispatcher/scheduler.py#L2098-L2162`).

## Reaper & autonomous recovery

`reaper.py` detects hung workers using a shared `_compute_stuck_state` (a
per-task max running time plus an inactivity timeout) so `reap_active_workers`
(the only path that kills processes) and `check_stuck_tasks` (reporting /
manual reap) cannot drift apart (`repo://dispatcher/reaper.py#L70-L134`).
Because the dashboard holds many open
connections plus an active writer, the reaper opens **WAL-tolerant**
connections: `_open_reaper_conn` sets `PRAGMA busy_timeout`, and
`reap_stuck_tasks` retries on `sqlite3.OperationalError` "database is locked"
with capped exponential backoff (~30s) and returns a clean failure dict instead
of raising, so a busy DB can never abort the watchdog tick
(`repo://dispatcher/reaper.py#L70-L76`,
`repo://dispatcher/reaper.py#L880-L1065`). `reap_active_workers`
terminates a worker that exceeded its budget and records the session end;
`reap_stuck_tasks` is the entry the watchdog and `check-stuck` CLI use
(`repo://dispatcher/reaper.py#L151-L691`).

Worker-failure handling is **retry-oriented, not terminal**: a crashed or
vanished worker is routed back to `todo` (or `triage` for in-flight EGM drafts)
when it was already `running` (so the
dispatcher re-spawns it on the next cycle, up to `DEFAULT_MAX_WORKER_RETRIES`)
and only escalates when retries are exhausted
(`repo://dispatcher/reaper.py#L151-L691`). Exhaustion routes to autonomous
recovery, not straight to a human: when the assignee is not `zf-orchestrator`
and `orchestrator_recovery_count < 1`, the task goes back to `todo` with
`triage_phase = "recovery"` for **one** diagnostic attempt by
`zf-orchestrator` (which can `recover` with guidance, `report-bug` an internal
defect, or `block` for a human gate); a second exhaustion — or any exhaustion
of the orchestrator itself — sets `permanently_blocked` and parks the task in
`blocked` with `blocked_reason_type = "stuck"` for a human
(`repo://dispatcher/reaper.py#L382-L510`). The conflict and precommit failure
handlers share the same two-tier routing, stamping `triage_phase = "recovery"`
after their own retry budgets (`repo://dispatcher/worktree.py#L684-L700`,
`repo://dispatcher/worktree.py#L1165-L1185`). The reaper recognizes two more
states: the **packaging phase** (a `running` task with `awaiting_pr` set is
owned by `_package_and_open_pr` and is deliberately skipped rather than treated
as an orphan, `repo://dispatcher/reaper.py#L554-L555`) and the **spawn grace
period** — a freshly claimed task with a `spawning_at` timestamp younger than
`DEFAULT_SPAWN_GRACE_SECONDS` (180s) is treated as "spawn in flight", not an
orphan, so the reaper does not double-dispatch the builder mid-startup
(`repo://dispatcher/reaper.py#L556-L567`,
`repo://dispatcher/config.py#L79`). A clean `zf-reviewer` exit that recorded no
verdict via `block --reason ...` is not retried: the reaper parks the task in
`blocked` with `blocked_reason_type = "human-gate"` and the reason "Reviewer
exited without recording a verdict; awaiting human review", clearing
`awaiting_pr` so the task never re-enters the packaging phase
(`repo://dispatcher/reaper.py#L284-L294`). `check_stuck_tasks` /
`build_stuck_task_context` power the `check-stuck` CLI and the dashboard's
⚡ Recover Task button (`repo://dispatcher/reaper.py#L692-L1065`).

## Step logging

Every pipeline step emits paired, grep-able markers in
`~/.hermes/logs/agent.log` — `STEP <name> start | task=<id> | …` and
`STEP <name> end | task=<id> | <outcome> | <duration>s | …` — via
`StepTracker` / `log_step_start` / `log_step_end`
(`repo://dispatcher/config.py`). Steps covered: `worktree.setup`,
`worker.spawn`, `package.precheck` → `package.precommit` → `package.slop_gate`
→ `package.commit` →
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
precommit and PR ops hand off to the reviewer, and the dashboard layer
([Dashboard & Automation](/openwiki/components/dashboard-cron.md)) triggers
`run_dispatch_cycle` and inspects worker liveness. Coding rules for touching
this code live in
[Conventions](/openwiki/conventions.md).
