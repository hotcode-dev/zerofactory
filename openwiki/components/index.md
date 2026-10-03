# Files

- [Dashboard, Cron & Automation](dashboard-cron.md) - The operator and automation layer — the FastAPI dashboard REST surface, the cron subsystem, and the No-Agent Mode scripts that drive 0-token background queue checks and wake-gated codebase scans.
- [Dispatch Engine](dispatcher.md) - The dispatcher subsystem — run_dispatch_cycle lifecycle, isolated Git worktrees, worker spawning, the deterministic precommit self-healing gate, git/PR ops, and the stuck-worker reaper.
- [External Issue Import (GitHub & Jira)](issues-importer.md) - The issues/ subsystem that deterministically ingests external tracker issues (GitHub via gh CLI, Jira) into Kanban tasks — label-driven priority/category inference, deterministic task IDs and dedup keys, board resolution, and PR linkage back to the source issue.
