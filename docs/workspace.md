# ZeroFactory Workspace Layout

This document defines the workspace layout for ZeroFactory. All agents must follow these conventions.

## Workspace Root: `~/git/`

All projects managed by ZeroFactory are stored under `~/git/<user>/<project>/`. This is the single source of truth for project locations.

### Layout Convention

```
~/git/
├── <github_user>/<repo_name>/          # Main project workspace
│   ├── .git/                           # Git repository
│   ├── src/                            # Source code
│   ├── tests/                          # Test files
│   ├── docs/                           # Documentation
│   └── README.md                       # Project overview
├── another_user/another_repo/
└── ...
```

### Naming Rules

| Component | Format | Example |
|-----------|--------|---------|
| User/org | GitHub-style namespace | `hotcode-dev`, `ntsd` |
| Project | kebab-case | `zerofactory`, `api-gateway` |
| Path | `~/git/<user>/<project>/` | `~/git/hotcode-dev/zerofactory/` |

### Discovery Rules

When looking for active projects:
1. **Scan `~/git/`** — list all top-level directories, each is a potential project.
2. **Check git activity** — filter for repos with commits in the last 30 days.
3. **Check kanban board** — cross-reference tasks with active repos.
4. **Exclude** archived repos (marked as such in kanban metadata).

### Project Metadata

Each project should include:
- `README.md` — project overview, setup, usage
- `docs/` — documentation suite
- `.git/` — version control

If `README.md` exists, the project is considered active.

### Scanner Integration

The **self-improvement scanner** (cron job `fb9f56bb73f5`) automatically:
1. Scans `~/git/` for active repos
2. Creates improvement tasks on the kanban board
3. Delivers plans for human review
4. Executes improvements when approved

No manual configuration needed — the scanner detects projects automatically based on this layout.

### Workspace Best Practices

1. **One project per directory** — each project is self-contained under its own directory.
2. **Consistent naming** — use `kebab-case` for project names.
3. **Git version control** — every project must be a git repo with active commits.
4. **README always present** — `README.md` is the entry point; if missing, the project is considered inactive.
5. **No hidden state** — don't store project-specific state outside of the project directory.

### Examples

```bash
# Active project (has recent commits)
~/git/hotcode-dev/zerofactory/
  README.md
  docs/
  src/
  .git/

# Another active project
~/git/another_user/api-gateway/
  README.md
  src/
  tests/
  .git/

# Inactive project (no recent commits)
~/git/old_user/legacy-project/
  # ... but no commits in 30+ days
```

## Why This Matters

This convention ensures:
- **Zero configuration** — agents discover projects automatically by scanning `~/git/`.
- **Consistent layout** — every project follows the same structure.
- **Easy maintenance** — new agents can find any project by reading this single file.
- **Scanner compatibility** — the self-improvement scanner relies on this layout to detect projects.

## Scanner Behavior

When the **self-improvement scanner** runs:
1. Scans `~/git/` for directories
2. Checks each for recent git activity
3. Creates improvement tasks for active projects
4. Reports findings on the kanban board

No manual setup required — the scanner handles project discovery automatically.
