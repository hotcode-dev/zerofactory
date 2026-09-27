# Specialist Agents & Session Model

The three `zf-*` profiles and the "stateless workers, stateful substrate"
session model. Back to [index](index.md).

## Profiles

Identity: `PROFILE_MAP` in `paths.py` — `{"zf-builder", "zf-reviewer",
"zf-orchestrator"}`. Sentinels `unassigned` and `human` extend it;
`VALID_ASSIGNEES` (`paths.py`) is the full set, `dispatcher/config.py::VALID_PROFILES`
is the profiles-only view. **Do not re-declare the profile list elsewhere.**

| Profile | Role | Main touchpoints |
|---|---|---|
| `zf-orchestrator` | Pipeline overseer: decomposes `Triage` goals into `Todo` sub-tasks; runs the periodic improvement scanner; files at most 1 actionable `Todo` per scan for `zf-builder`; escalates blockers | `dispatcher/scanner.py`, `cron/definitions.py::build_board_scanner_prompt`, `scripts/zf_scanner_gate.py` |
| `zf-builder` | Senior engineer: implements in an isolated worktree, writes tests, runs precommit | `dispatcher/worktree.py`, `dispatcher/context_builder.py` (prompt injection incl. review comments), `templates/zf-builder/` |
| `zf-reviewer` | Quality gatekeeper: reviews the open PR in up to 3 thematic rounds (Correctness → Performance → Clean Code/Ponytail); requests changes or approves | `dispatcher/github_pr.py` (comment fetch + approval detection), `templates/zf-reviewer/` |

Profile artifacts live under `~/.hermes/profiles/zf-*/` (one `state.db` per
profile) and are (re)provisioned by `profile_manager.py`: `ensure_zf_profiles()`
(create missing profiles, inherit root LLM settings), `ensure_plugin_symlinks()`,
`ensure_script_files()`, `update_env_file()`, `update_config_yaml_plugins()`,
`sync_langfuse_profiles()`. Profile templates (version-controlled) are in
`templates/zf-*/`. Per-profile `state.db` resolution is
`paths.py::resolve_profile_state_db` (4-strategy search, never cached).

Skills each worker gets: its `skills/zf-*-ponytail/` playbook (LADDER.md),
`skills/ponytail/` (canonical 7-Rung Ladder of Laziness), and
`skills/zerofactory-orchestration/`.

## Session-per-handoff model

Workers are **stateless per handoff**: the dispatcher terminates a finished or
superseded worker (`SIGTERM`/`SIGKILL`, `process_manager.py`) and spawns a
**fresh Hermes session** for the next phase:

1. **Builder phase** — `worker_spawner.spawn_agent_worker()` runs
   `hermes -p <profile> --yolo --cli --accept-hooks chat -q <prompt>`
   (hermes binary resolved from `~/.local/bin/hermes` or `PATH`). The spawned
   session is tracked in `tasks.metadata["sessions"]` and correlated with the
   profile's `state.db` via `resolve_profile_state_db`.
2. **Reviewer phase** — after precommit passes, the dispatcher commits, merges
   latest main, pushes, and opens the GitHub PR (see [dispatcher.md](dispatcher.md)),
   then spawns `zf-reviewer` with a **pre-digested** git diff/commit log
   (`context_builder.digest_reviewer_git_context`).
3. **Changes requested** — PR review comments are fetched
   (`github_pr.fetch_pr_review_comments`, filtered to trusted reviewer authors)
   and imported into `task_comments`; the reviewer is stopped and the ticket
   routes back to `zf-builder` in a **new session** whose prompt contains a
   `🚨 CRITICAL: PULL REQUEST REVIEW COMMENTS TO ADDRESS` block.

Design rationale (compact context, flat token cost per round, no poisoned
loops) is documented in `README.md` § "Session Lifecycle & Architecture".
Durable state lives in three places, never in chat history: **Git worktrees**,
**GitHub PR comments**, and **kanban.db** (tasks, comments, board memory —
see [database.md](database.md)).

## Prompt injection (context_builder.py)

`dispatcher/context_builder.py` pre-digests context **in Python** so workers do
not re-derive it:

- `digest_reviewer_git_context()` — clean diffstat + commit log for the PR head.
- `digest_board_memories_context()` — board memory cards
  ([database.md](database.md) `board_memories`) injected so workers never
  repeat known gotchas.
- `format_conventional_message(title, task_id)` — commit message
  `type(scope): title [task-id]`.

## Board memory (per-repo knowledge)

Auto-recorded from PR review comments, block reasons, and task comments when a
line is prefixed with `GOTCHA:`, `CONVENTION:`, `RULE:`, `DECISION:`, `ARCH:`,
`REJECTED_PATH:`, `LESSON:`, `LEARNING:`, or `TIP:` (deduped, tagged
`auto-recorded` / `from-<actor>`). Categories: `convention`, `gotcha`,
`decision`, `rejected_path`, `general`. Managed by `dashboard/memory_service.py`
+ `routes/memories.py`; toggles: global `auto_record_memory` setting and
per-board `auto_record_memory` column (see [conventions.md](conventions.md)).
