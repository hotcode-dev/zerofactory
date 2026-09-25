# The 7-Rung Ladder of Laziness

> **"The best code is the code you never wrote."**

Whenever evaluating an implementation, design decision, or existing codebase, climb the ladder from **Rung 1 to Rung 7**. Stop at the first rung that solves the problem.

```
┌────────────────────────────────────────────────────────┐
│ Rung 1: Does this need to exist? (YAGNI)               │  ← Best outcome: 0 lines
├────────────────────────────────────────────────────────┤
│ Rung 2: Already in this codebase?                      │  ← Call existing helper
├────────────────────────────────────────────────────────┤
│ Rung 3: Standard library does it?                      │  ← Zero new dependencies
├────────────────────────────────────────────────────────┤
│ Rung 4: Native platform feature?                       │  ← OS / runtime built-in
├────────────────────────────────────────────────────────┤
│ Rung 5: Installed dependency handles it?               │  ← Don't add a new package
├────────────────────────────────────────────────────────┤
│ Rung 6: One line / simple function?                    │  ← Flat > Nested; Simple > Clever
├────────────────────────────────────────────────────────┤
│ Rung 7: Minimum viable solution                        │  ← Only write minimal necessary code
└────────────────────────────────────────────────────────┘
```

---

## Detailed Rung Rules

### Rung 1 — Does this need to exist? (YAGNI)
- **You Aren't Gonna Need It**: Do not write speculative code for "future requirements" that are not currently requested.
- **Dead Code Elimination**: If an existing function, class, or parameter is unused, delete it rather than maintaining it.
- **No Premature Abstraction**: Do not add wrappers, adapters, or factories around things that only have a single caller.

### Rung 2 — Already in this codebase?
- Search the project (`search_files`, `grep`) before creating utilities, formats, or helpers.
- Reuse existing logging, validation, error handling, and configuration patterns already proven in the repo.

### Rung 3 — Standard library does it?
- **Python**: Use `pathlib`, `json`, `dataclasses`, `functools`, `typing`, `subprocess`, `sqlite3`, `re`, `argparse`.
- **Node/TypeScript**: Use native `fetch`, `URL`, `node:fs`, `node:path`, `crypto`.
- Do not pull in a 3rd-party library for things the standard library already does in a few lines.

### Rung 4 — Native platform feature?
- Leverage OS features (e.g. `O_CLOEXEC`, POSIX signals, process groups, standard shell utilities) instead of building custom daemon managers.
- In browsers, use native DOM APIs and Web Standards instead of adding framework-heavy utility libraries.

### Rung 5 — Installed dependency handles it?
- Check `pyproject.toml`, `requirements.txt`, or `package.json` for libraries already installed before proposing a new package.
- Never add a new dependency if an existing one can solve the problem.

### Rung 6 — One line / simple function?
- A 5-line pure function is almost always better than a 60-line class with inheritance and a factory.
- Avoid deep nesting, complex ternary trees, and multi-layer abstraction indirection. Flat is better than nested.

### Rung 7 — Minimum viable solution
- If new code must be written, write only what is required to pass the test suite and fulfill the task requirements.
- Keep diffs small, token-efficient, and easy to review.
