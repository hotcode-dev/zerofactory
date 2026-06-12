# Zero Factory — Shared Conventions

All agents reference this file. It is the single source of truth for project conventions. If anything here changes, every agent follows automatically.

---

## General Rules

- Code first, explanation second.
- Prefer small, focused changes over big bangs.
- Always run type checks and linters before submitting.
- Use existing patterns unless justified.
- No TODOs — leave no unfinished work.
- Flag breaking changes and migration needs immediately.
- Don't duplicate information — reference shared files with relative paths.
- Always use the latest stable versions of packages, libraries, and frameworks. Pin to exact versions (e.g. `^1.2.3`) and run `npm outdated` regularly to track updates.

## Naming Conventions

- **Files**: kebab-case — `feature-name.ts`, `data-model.ts`
- **Classes/Types**: PascalCase — `UserManager`, `PaymentProcessor`
- **Variables**: camelCase — `userId`, `requestCount`
- **Constants**: UPPER_SNAKE_CASE — `MAX_RETRIES`, `DEFAULT_TIMEOUT`
- **Functions**: camelCase with clear verb — `fetchUsers()`, `buildTemplate()`
- **Interfaces/Protocols**: PascalCase or `I` prefix — `IUserService` or `UserService`
- **Tests**: match source naming with extension — `user-manager.test.ts`, `handler.test.ts`
- **Directories**: kebab-case — `src/user-manager/`, `internal/payment/`
- **Kanbam**: Tasks use `t_<hex_id>` format, Branch names follow pattern `task/<task_id>` when applicable

## TypeScript / Bun Conventions

All code is written in **TypeScript** using **Bun** as the runtime.

```
project/
├── src/
│   ├── index.ts
│   ├── config.ts
│   └── modules/
│       └── <feature>/
│           ├── index.ts          # public API
│           ├── <feature>.ts      # implementation
│           └── <feature>.test.ts # tests
├── tests/
│   ├── fixtures/
│   └── helpers/

├── Makefile
├── package.json
└── README.md
```

- All public APIs re-exported from `index.ts`
- Strict TypeScript mode enabled
- ES modules with `.ts` extension
- Test files co-located with source when possible, otherwise in `tests/`
- All dependencies explicitly versioned

## Test Conventions

- Arrange-Act-Assert structure
- Table-driven tests for multiple scenarios
- Mock external dependencies
- One assertion per test line when possible
- Test names: `Test<Function>_<scenario>_expected`
- Coverage threshold: minimum 90%

## Commit Message Convention

```
<type>(<scope>): <subject>

body (optional)

footer (optional)
```

Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`, `ci`

Examples:
- `feat(auth): add OAuth2 login flow`
- `fix(user): handle null email in validation`
- `docs(api): add webhook reference`

## Git Workflow

- **Always push to git remote after finishing a task.** Work stored only in a local worktree or scratch directory is lost if the run is reclaimed or the workspace is garbage-collected. Push commits to the remote before marking a task complete so work survives.
- Commit frequently with small, focused changes.
- Push a descriptive branch per task for traceability.

### Always create pull request to git remote after a task is done
Every agent **must** push their work and create a pull request to the git remote after finishing a task. This ensures:
- Work is not lost during workspace garbage collection
- Changes are reviewed before merging
- All progress is tracked in the repository

**Required steps:**
1. Commit changes with clear, descriptive messages
2. Push to the remote repository
3. Open a pull request against the target branch using the `gh pr create` terminal command
4. Reference the PR URL in task completion notes or when calling `kanban_block("review-required")` if human review is needed

> **Important:** Never finish a task or block for human review without pushing to remote and creating a PR via `gh`.

## Git Directory Structure

- **Always use `~/git/<gituser>/<reponame>` as the local clone path** when cloning or working with a repository. The `<gituser>` component matches the GitHub (or Git hosting) username/organization from the remote URL, and `<reponame>` matches the repository name.
  - Example: `https://github.com/hotcode-dev/zerofactory` → `~/git/hotcode-dev/zerofactory`
  - Example: `https://github.com/ntsd/zerofactory` → `~/git/ntsd/zerofactory`
- This ensures a consistent, predictable location for every project's local copy across runs and workspaces.

## Code Review Criteria

### Must Fix (blocking)
- Bugs or incorrect logic
- Security vulnerabilities
- Missing error handling
- Race conditions / concurrency issues
- Breaking API changes without migration
- Naming conventions
- Code smell / readability issues

### Should Fix (non-blocking)
- Performance improvements
- Missing edge case coverage
- Inconsistent style
- Minor refactoring
- Additional comments

## Documentation Standards

- **README.md**: the single source of truth for all project documentation (architecture, runbook, API, changelog, setup)
- Inline comments for non-obvious logic
- No duplicate docs — everything must be consolidated into `README.md`

## File References

- Agent configs (this will overwrite the runtime config.yaml): `hermes/profiles/<agent>/config.custom.yaml`
- Agent identity: `hermes/profiles/<agent>/SOUL.md`
- Project root README: `README.md`


## Task Lifecycle
1. **triage** → Initial state, being prepared
2. **todo** → Ready to work on
3. **running** → Currently being worked on
4. **blocked** → Waiting on something/someone
5. **done** → Task completed

## Communication
- Reference task IDs in all comments and notes
- Use structured metadata in task completion
- Keep summaries concise and actionable

## Tool Management
- If a task requires an MCP server that's not available, add it in `profiles/<agent>/config.custom.yaml`, then run `make config-merge`
- If a skill is needed for a task, add it: create `profiles/<agent>/skills/<skill-name>/SKILL.md`
- **IMPORTANT**: The repository uses a strict whitelist in `.gitignore`. You MUST unignore any newly created custom skills or non-builtin files in the root `.gitignore` file so they can be pushed to GitHub.
- Always inform the human before adding new tools — explain why they're needed and what task they enable
- Do not add tools without a clear task-driven reason
