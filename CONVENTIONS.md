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
- **Always use the latest stable versions of packages, libraries, and frameworks.** Pin to exact versions (e.g. `^1.2.3` or `==1.2.3`) and run `npm outdated` / `pip list --outdated` / `go list -u -m all` regularly to track updates.

## Naming Conventions

- **Files**: kebab-case — `feature-name.ts`, `data-model.go`
- **Classes/Types**: PascalCase — `UserManager`, `PaymentProcessor`
- **Variables**: camelCase — `userId`, `requestCount`
- **Constants**: UPPER_SNAKE_CASE — `MAX_RETRIES`, `DEFAULT_TIMEOUT`
- **Functions**: camelCase with clear verb — `fetchUsers()`, `buildTemplate()`
- **Interfaces/Protocols**: PascalCase or `I` prefix — `IUserService` or `UserService`
- **Tests**: match source naming with extension — `user-manager.test.ts`, `handler_test.go`
- **Directories**: kebab-case — `src/user-manager/`, `internal/payment/`

## TypeScript / Bun Conventions

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
├── docs/
│   └── README.md
├── Makefile
├── package.json
└── README.md
```

- All public APIs re-exported from `index.ts`
- Strict TypeScript mode enabled
- ES modules with `.ts` extension
- Test files co-located with source when possible, otherwise in `tests/`
- All dependencies explicitly versioned

## Go Conventions

```
project/
├── cmd/
│   └── <binary>/
│       └── main.go
├── internal/
│   └── <package>/
│       ├── <package>.go
│       └── <package>_test.go
├── pkg/
│   └── <external-package>/
│       └── <file>.go
├── Makefile
├── go.mod
└── README.md
```

- `internal/` for private package code (Go visibility rule)
- `pkg/` for public package code
- One public type per file when possible
- Receiver names: short, 1-2 chars, consistent across package
- Errors wrapped with context: `fmt.Errorf("failed to X: %w", err)`
- Test files: `<source>_test.go`

## Test Conventions

- Arrange-Act-Assert structure
- Table-driven tests for multiple scenarios
- Mock external dependencies
- One assertion per test line when possible
- Test names: `Test<Function>_<scenario>_expected`
- Coverage threshold: minimum 80%

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

## Git Directory Structure

- **Always use `~/git/<gituser>/<reponame>` as the local clone path** when cloning or working with a repository. The `<gituser>` component matches the GitHub (or Git hosting) username/organization from the remote URL, and `<reponame>` matches the repository name.
  - Example: `https://github.com/hotcode-dev/zerofactory` → `~/git/hotcode-dev/zerofactory`
  - Example: `https://github.com/ntsd/git-fight` → `~/git/ntsd/git-fight`
  - Example: `https://github.com/ntsd/zerofactory` → `~/git/ntsd/zerofactory`
- This ensures a consistent, predictable location for every project's local copy across runs and workspaces.

## Code Review Criteria

### Must Fix (blocking)
- Bugs or incorrect logic
- Security vulnerabilities
- Missing error handling
- Race conditions / concurrency issues
- Breaking API changes without migration

### Should Fix (non-blocking)
- Performance improvements
- Missing edge case coverage
- Code smell / readability issues
- Inconsistent style

### Optional
- Minor refactoring
- Better naming
- Additional comments

## Documentation Standards

- **README.md**: project overview, setup, usage
- **docs/api.md**: endpoint reference, parameters, examples
- **docs/architecture.md**: system design, data flows
- **docs/changelog.md**: version history, breaking changes
- Inline comments for non-obvious logic
- No duplicate docs — link cross-references

## File References

- This file: `CONVENTIONS.md`
- Agent configs: `hermes/profiles/<agent>/config.yaml`
- Agent identity: `hermes/profiles/<agent>/SOUL.md`
- System prompt: `hermes/profiles/<agent>/system_prompt.txt`
- Project root README: `README.md`
