# Project Conventions

All agents reference this file. It is the single source of truth for project conventions.

## General Rules
- Code first, explanation second
- Prefer small, focused changes over big bangs
- Always run type checks and linters before submitting
- Use existing patterns unless justified
- No TODOs — leave no unfinished work
- Flag breaking changes and migration needs immediately
- Don't duplicate information — reference shared files

## Naming Conventions
- **Files**: kebab-case (`feature-name.ts`, `data-model.go`)
- **Classes/Types**: PascalCase (`UserManager`, `PaymentProcessor`)
- **Variables**: camelCase (`userId`, `requestCount`)
- **Constants**: UPPER_SNAKE_CASE (`MAX_RETRIES`, `DEFAULT_TIMEOUT`)
- **Functions**: camelCase with verb (`fetchUsers()`, `buildTemplate()`)
- **Tests**: match source naming (`user-manager.test.ts`, `handler_test.go`)
- **Directories**: kebab-case (`src/user-manager/`)

## TypeScript / Bun
```
project/
├── src/
│   ├── index.ts
│   └── modules/
│       └── <feature>/
│           ├── index.ts          # public API
│           ├── <feature>.ts      # implementation
│           └── <feature>.test.ts # tests
├── tests/
│   └── fixtures/
├── Makefile
├── package.json
└── README.md
```

## Go
```
project/
├── cmd/
│   └── <binary>/
│       └── main.go
├── internal/
│   └── <package>/
│       ├── <package>.go
│       └── <package>_test.go
├── Makefile
├── go.mod
└── README.md
```

## Test Conventions
- Arrange-Act-Assert structure
- Table-driven tests for multiple scenarios
- Test names: `Test<Function>_<scenario>_`
- Coverage threshold: minimum 80%

## Commit Format
```
<type>(<scope>): <subject>
```
Types: `feat`, `fix`, `docs`, `refactor`, `test`, `chore`, `perf`

## Review Criteria
**Blocking** — bugs, security, missing error handling, race conditions, breaking API
**Non-blocking** — performance, edge cases, readability, style

## Documentation
- README.md — project overview, setup, usage
- docs/api.md — API reference
- docs/architecture.md — system design
- No duplicate docs — link cross-references
