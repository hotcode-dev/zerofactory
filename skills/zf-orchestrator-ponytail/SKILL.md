---
name: zf-orchestrator-ponytail
description: "Codebase auditing and improvement scanning playbook for zf-orchestrator applying the 7-Rung Ladder of Laziness."
version: 1.0.0
author: Zero Factory
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [code-audit, scanner, refactoring, simplification, dead-code, ladder-of-laziness, yagni]
    related_skills: [ponytail]
---

# ZF Orchestrator Ponytail — Codebase Auditing Playbook

> **"The best code is the code you never wrote."**

This skill equips `zf-orchestrator` with the **Ponytail auditing lens**: scanning repositories for over-engineering, dead code, redundant dependencies, and speculative complexity to file high-value `refactoring` tasks for `zf-builder`.

The core decision framework is defined in the shared **[7-Rung Ladder of Laziness](./LADDER.md)**.

---

## The Orchestrator's Auditing Heuristics

When running idle improvement scans (`zero-factory-improvement-scanner-{slug}`), systematically inspect the codebase against the rungs:

### 1. Spotting Dead Code & Vestigial Shims (Rung 1: YAGNI)
- **Uncalled functions/methods**: Search for exported utilities or helpers that have 0 internal call sites.
- **Obsolete compatibility shims**: Flags, wrappers, or fallback branches left over from previous migrations.
- **Commented-out code & dead branches**: Blockers that should be deleted instead of preserved.

### 2. Spotting Redundant Helpers (Rung 2 & 3: Codebase Reuse & Stdlib)
- **Bespoke reimplementations**: Custom path parsing, URL manipulation, or manual dict merging where standard library (`pathlib`, `urllib`, `dataclasses`, `node:fs`) provides native, robust equivalents.
- **Near-duplicate utility functions**: Two modules having slightly different versions of the same formatting or validation logic.

### 3. Spotting Dependency Bloat (Rung 5: Installed Dependencies)
- Check `package.json` / `pyproject.toml` for third-party libraries installed for trivial operations (e.g. 5-line string utils, single regex helpers) that can be removed in favor of native APIs.

### 4. Spotting Over-Engineering (Rung 6: Simplicity over Indirection)
- **Single-caller abstractions**: Interfaces, abstract base classes, or factories implemented for only a single concrete class.
- **Deeply nested logic**: Pyramid if/else structures or nested ternaries that can be flattened into guard clauses.

---

## How to File a Ponytail Refactoring Task

When an unaddressed simplification opportunity is discovered:
1. **Pre-Flight Check**: Verify no open task on the board already covers the issue (`hermes zerofactory list --board "<slug>"`).
2. **Reference the Rung**: In the task description, cite the exact Ponytail rung and describe what code should be removed or simplified.
3. **Specify Exact Files & Lines**: Provide relative file paths and line ranges.
4. **File the Task**:
   ```bash
   hermes zerofactory create "refactor: simplify <component> and remove dead code (Ponytail Rung 1/3)" \
     --description-file "/tmp/task_desc.md" \
     --board "<slug>" \
     --files "src/utils.py" \
     --category "refactoring" \
     --priority P1 \
     --status todo \
     --assignee zf-builder
   ```
5. **DO NOT execute the code changes yourself**: The Orchestrator’s job is discovery and triage; `zf-builder` handles the implementation in an isolated Git worktree.
