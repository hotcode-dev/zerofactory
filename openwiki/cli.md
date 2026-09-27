# CLI Reference (`hermes zerofactory`)

Commands are registered in `__init__.py::register` → `cmd_setup(parser)`
(argparse subparsers) and dispatched by `cmd_run(args)`. Back to
[index](index.md).

## Profile management
```bash
hermes zerofactory setup            # Check/initialize zf-* profiles
hermes zerofactory sync-profiles    # Re-sync system prompts from templates/
```

## Task management
```bash
hermes zerofactory list [--status <s>] [--assignee <a>]   # List tasks (filters)
hermes zerofactory create "Title" [--description ...]     # Create a ticket
hermes zerofactory move <task_id> <status>                # Transition (triage|todo|running|blocked|done)
hermes zerofactory block <task_id> --reason "..."         # Block with reason (routes per reason)
hermes zerofactory comment <task_id> "Note..."            # Append to the task thread
hermes zerofactory stats                                   # Board statistics
```
Review handoff convention: `move <id> blocked --reason "review-required"`;
approved PRs: `block <id> --reason "Human Review & Merge"` (assigned to
human; the dispatcher auto-moves to `done` after the PR merges — workers must
**not** self-mark done on PR-backed work).

## Dispatcher & health
```bash
hermes zerofactory dispatch         # Run one dispatch cycle now
hermes zerofactory check-stuck [--timeout N] [--inactivity N] [--reap] [--task ID]
hermes zerofactory migrate [--status]   # Run/inspect SQLite migrations
```

## Boards
```bash
hermes zerofactory board list
hermes zerofactory board create <git_url> [--target-branch <b>] [--auto-setup-precommit]
hermes zerofactory board delete <slug>        # Deletes board + clears its scanner job
hermes zerofactory setup-repo --board <slug>      # P0 task: generate .zerofactory/precommit.sh
hermes zerofactory setup-openwiki --board <slug>  # P0 task: generate openwiki/ agent docs
```

## Memory
```bash
hermes zerofactory memory list --board <slug> [--category <c>] [-q <query>]
hermes zerofactory memory add --board <slug> "<content>" --category <convention|gotcha|decision|rejected_path|general> --tags "a,b"
hermes zerofactory memory delete <memory_id>
```

## Cron
```bash
hermes zerofactory cron list
hermes zerofactory cron sync
hermes zerofactory cron run <job_id>
```

## Notes for agents

- CLI actors default to `HERMES_PROFILE` / `user`; prefer the CLI over raw
  SQL for state changes so `task_activity` rows and memory auto-recording
  fire (see [zf-profiles.md](zf-profiles.md) board memory).
- The `blocked` reason string drives routing: `review-required` /
  `changes-requested` / `Human Review & Merge` have dispatcher semantics —
  use exactly these.
