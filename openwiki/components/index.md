# Files

- [Dashboard, Cron & Automation](dashboard-cron.md) - The operator and automation layer — the FastAPI dashboard REST surface, the cron subsystem, and the No-Agent Mode scripts that drive 0-token background queue checks and wake-gated codebase scans.
- [Dispatch Engine](dispatcher.md) - The dispatcher subsystem — run_dispatch_cycle lifecycle, isolated Git worktrees, worker spawning, the deterministic precommit self-healing gate, git/PR ops, and the stuck-worker reaper.
