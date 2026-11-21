---
name: zf-reviewer-ponytail
description: "Pull Request review gatekeeping playbook for zf-reviewer applying the 7-Rung Ladder of Laziness."
version: 1.0.0
author: Zero Factory
license: MIT
platforms: [linux, macos, windows]
metadata:
  hermes:
    tags: [pr-review, code-review, clean-code, refactoring, gatekeeping, ladder-of-laziness, yagni]
    related_skills: [ponytail]
---

# ZF Reviewer Ponytail — PR Review Gatekeeping Playbook

> **"The best code is the code you never wrote."**

This skill equips `zf-reviewer` with the **Ponytail review rubric**: actively catching over-engineering, diff bloat, and redundant dependencies across **all Pull Request reviews** (starting immediately in **Round 1: Initial Review** and verifying fixes in **Round 2: Re-Verification**).

The core decision framework is defined in the shared **[7-Rung Ladder of Laziness](./LADDER.md)**.

---

## Reviewer's Ponytail Checklist

When reviewing a PR branch diff (`task/<task_id>`):

### 1. Diff Scope & Hygiene (Rung 7: Minimum Viable Solution)
- **Zero Drive-By Churn**: Did the author reformat unrelated code, reorder imports, or touch files outside the task scope? Reject diff bloat immediately in Round 1.
- **Leftover Artifacts**: Ensure no commented-out code, temporary debug logs, or unused variables were committed.

### 2. Dependency Veto (Rung 3 & 5: Standard Library & Installed Dependencies)
- Check `package.json`, `poetry.lock`, `requirements.txt`, etc.
- If a new external package was added, verify whether:
  - A standard library module could have handled it (Rung 3).
  - An already-installed library could have solved it (Rung 5).
- If unnecessary, request removal: *"Reject new dependency `<pkg>`. Standard library `<module>` handles this in 3 lines."*

### 3. Abstraction & Simplicity Check (Rungs 1 & 6: YAGNI & Simple Functions)
- Did the author create a class hierarchy, factory, or adapter where a single pure function suffices?
- Are there speculative parameters or "future-proofing" flags not requested in the task? Request their deletion.

---

## Actionable Review Feedback Format

When reviewing on GitHub (`gh pr review --comment`), structure feedback with reference to the Ponytail ladder:

```markdown
[AI:zf-reviewer] [Reviewer Feedback] Round 1: Ponytail Gatekeeping & Correctness

1. **Unnecessary Dependency (Rung 3/5)**:
   - File: `src/processor.py:12`
   - Problem: Added `requests` when the repo already standardizes on native `urllib.request` / `httpx`.
   - Action: Remove `requests` from `requirements.txt` and use native stdlib.

2. **Diff Bloat & Drive-by Churn (Rung 7)**:
   - File: `src/utils.py:1-40`
   - Problem: Re-ordered imports and reformatted comments unrelated to the task.
   - Action: Revert changes to `src/utils.py` to keep the PR focused on the task scope.

3. **Over-Engineered Factory (Rung 1/6)**:
   - File: `src/auth.py:45-80`
   - Problem: Introduced `AbstractTokenValidatorFactory` with only one concrete implementation.
   - Action: Collapse into a single `validate_token(token)` function.
```

## Posting the Review (GitHub)

- Use `gh pr review <n> --comment --body-file <file>` — never `--approve` / `--request-changes` (the authed identity is the PR author, so GitHub rejects self-approval) and never inline `--body` (shell-mangling risk).
- **Verify before retrying**: if the `gh pr review` terminal output looks garbled or truncated, re-check `gh api repos/<owner>/<repo>/pulls/<n>/reviews` before re-posting — the first call may have already succeeded (observed 2026-11-20 on PR #181: posted despite mangled output; the retry created a duplicate). Submitted reviews cannot be deleted; dedupe with a `gh pr comment` note naming the canonical review id.
