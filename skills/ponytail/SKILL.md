---
name: ponytail
description: "Anti-overengineering discipline applying the 7-Rung Ladder of Laziness across Zero Factory roles."
version: 1.0.0
author: Zero Factory
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [clean-code, refactoring, simplification, audit, code-review, ladder-of-laziness, yagni]
    related_skills: [zf-builder-ponytail, zf-orchestrator-ponytail, zf-reviewer-ponytail]
---

# Ponytail — Anti-Overengineering & The Ladder of Laziness

> **"The best code is the code you never wrote."**

Ponytail is an engineering philosophy designed to eliminate speculative complexity, dependency bloat, and code clutter. It guides AI agents to think like pragmatic senior developers who prioritize simplicity, standard libraries, and deleting code over building complex monuments.

The canonical core decision framework is defined in **[The 7-Rung Ladder of Laziness](./LADDER.md)**.

---

## Role-Specific Ponytail Skills

Zero Factory divides Ponytail into three specialized playbooks tailored to each agent role:

1. **[`zf-builder-ponytail`](../zf-builder-ponytail/SKILL.md)**:
   - Code authoring discipline.
   - Minimal surgical diffs, stdlib-first implementations, dependency vetoes, and pre-handoff hygiene checklists.

2. **[`zf-orchestrator-ponytail`](../zf-orchestrator-ponytail/SKILL.md)**:
   - Codebase auditing and improvement scanning rubric.
   - Heuristics for detecting dead code, unused exports, and over-engineered abstractions, and filing actionable `refactoring` tasks for `zf-builder`.

3. **[`zf-reviewer-ponytail`](../zf-reviewer-ponytail/SKILL.md)**:
   - Pull Request review gatekeeping.
   - Checklists for identifying diff bloat, redundant dependencies, and speculative abstractions, especially during **Round 3: Clean Code & Refactoring**.
