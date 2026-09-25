---
name: zf-builder-ponytail
description: "Anti-overengineering code authoring playbook for zf-builder applying the 7-Rung Ladder of Laziness."
version: 1.0.0
author: Zero Factory
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [code-authoring, clean-code, refactoring, simplification, ladder-of-laziness, yagni]
    related_skills: [ponytail]
---

# ZF Builder Ponytail — Code Authoring Playbook

> **"The best code is the code you never wrote."**

This skill equips `zf-builder` with the **Ponytail discipline**: writing minimal, surgical, robust code that solves problems without bloat, unnecessary dependencies, or speculative abstractions.

The core decision framework is defined in the shared **[7-Rung Ladder of Laziness](./LADDER.md)**.

---

## The Builder's Authoring Workflow

Follow these steps on every task:

### Step 1: Pre-Code Inspection (Rungs 1 & 2)
1. **Understand Chesterton's Fence**: Before modifying or deleting code, inspect why it exists (`git log -S`, comments).
2. **Search Before Building**: Search the repository (`search_files`, `grep`) for existing utilities, constants, or helpers. Never reinvent something that already exists in the project.

### Step 2: Implementation Discipline (Rungs 3, 4, 5 & 6)
1. **Standard Library First (Rung 3)**: Always favor native language/stdlib modules (`pathlib`, `json`, `subprocess`, `dataclasses`, `node:fs`, `crypto`) over new libraries.
2. **Dependency Veto (Rung 5)**: Never run `npm install <pkg>` or `pip install <pkg>` unless the task explicitly requires an external integration that is impossible with existing libraries.
3. **Simplicity over Abstraction (Rung 6)**:
   - Keep functions flat. Prefer early returns over deeply nested `if/else` blocks.
   - Avoid creating new classes, wrappers, or interfaces when a simple pure function does the job.
   - Do not write speculative configuration options or unused parameter flags.

### Step 3: Minimal Diff Hygiene (Rung 7)
1. **Surgical Edits**: Touch only the exact lines required for the fix/feature. Never reformat, reorder, or touch unrelated lines.
2. **Token Efficiency**: Use targeted search/replace or concise patch hunks rather than rewriting whole files.
3. **Verify with Tests**: Run the targeted unit test suite to prove correctness before handing off.

---

## Pre-Handoff Self-Check Checklist

Before calling `hermes zerofactory move <task_id> blocked --reason "review-required"`:
- [ ] Did I add any code or parameters that aren't strictly required by the task? *(If yes, delete them)*
- [ ] Did I add a new dependency? *(If yes, can stdlib or an existing package do it?)*
- [ ] Is there an existing helper in the codebase I should have reused instead?
- [ ] Are my diffs minimal, clean, and free of commented-out code or debug prints?
