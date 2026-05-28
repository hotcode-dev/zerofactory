# Agent Task Dispatch Reference

Clear mapping of task types to the correct agent. The Orchestrator uses this guide to ensure every task is assigned to the specialist with the right toolset, skills, and constraints.

---

## Quick-Reference Table

| Task Type | Agent | Profile Flag | Key Toolsets |
|-----------|-------|--------------|--------------|
| Architecture research, feasibility, tech specs | Researcher | `-p researcher` | file, terminal, search_files, web, kanban, skills, mcp |
| Code implementation, bug fixes, refactoring | Builder | `-p builder` | file, terminal, search_files, web, kanban, skills, mcp |
| Code quality review, security audit, performance review | Reviewer | `-p reviewer` | file, terminal, search_files, web, skills, mcp |
| Test design, integration tests, QA | QA | `-p qa` | file, terminal, search_files, web, skills, mcp |
| Documentation, API reference, README, changelogs | Scribe | `-p scribe` | file, search_files, web |
| Task decomposition, coordination, kanban management | Orchestrator | `-p orchestrator` | kanban, delegation, cronjob, file, terminal, web, skills, mcp |

---

## Agent Dispatch Rules

### 1. Researcher (CTO) — Technical Investigation

**Assign when:**
- Research a new technology, library, or framework before coding
- Design architecture for a new feature or system
- Evaluate trade-offs between implementation approaches
- Produce technical specifications for the Builder
- Analyze feasibility of complex requirements
- Create PoC (proof of concept) designs

**Do NOT assign to Researcher when:**
- Writing production code (→ Builder)
- Writing tests (→ QA)
- Reviewing existing code (→ Reviewer)
- Writing user-facing documentation (→ Scribe)
- Running the overall project (→ Orchestrator)

**Output:** Technical specs, architecture docs, research reports, feasibility analyses.

---

### 2. Builder (Lead Engineer) — Implementation

**Assign when:**
- Implementing a feature from a spec or design
- Fixing a bug (diagnose and patch)
- Refactoring existing code
- Writing unit tests alongside code (co-located tests)
- Creating new files/modules from scratch
- Updating existing code to use new libraries

**Do NOT assign to Builder when:**
- Researching which library to use (→ Researcher)
- Reviewing someone else's code quality (→ Reviewer)
- Designing comprehensive test suites (→ QA)
- Writing API documentation for users (→ Scribe)
- Coordinating across multiple features (→ Orchestrator)

**Constraints:**
- Writes TypeScript (Bun) code only
- Must produce working, tested code — no TODOs
- Uses existing patterns unless justified

---

### 3. Reviewer (Code Reviewer) — Quality Gate

**Assign when:**
- Code has been implemented and needs quality review
- Security audit required (SQL injection, XSS, auth bypass)
- Performance review needed (bottlenecks, optimizations)
- Architecture decision review
- Test coverage audit
- Code style and maintainability check

**Do NOT assign to Reviewer when:**
- Writing new code (→ Builder)
- Writing the tests themselves (→ QA)
- Creating feature specs (→ Researcher)
- Writing documentation (→ Scribe)

**Output:** Structured review with severity levels (blocking vs. non-blocking), line references, and recommendations.

---

### 4. QA Engineer — Testing & Verification

**Assign when:**
- Designing comprehensive test suites
- Writing automated tests (unit, integration, E2E)
- Verifying edge cases and error handling
- Running tests and reporting results
- Verifying acceptance criteria are met
- Performance/benchmark testing
- Regression testing

**Do NOT assign to QA when:**
- Implementing the feature itself (→ Builder)
- Reviewing code quality (→ Reviewer)
- Designing system architecture (→ Researcher)
- Writing docs (→ Scribe)

**Output:** Test reports with pass/fail status, bug reports with reproduction steps, verification summaries.

---

### 5. Scribe — Documentation

**Assign when:**
- Writing API reference documentation
- Creating or updating README files
- Writing architecture documentation
- Creating user guides and tutorials
- Updating changelogs
- Writing runbooks and operations docs
- Creating step-by-step guides

**Do NOT assign to Scribe when:**
- Writing code (→ Builder)
- Testing code (→ QA)
- Reviewing code (→ Reviewer)
- Architecting systems (→ Researcher)
- Coordinating the workflow (→ Orchestrator)

**Output:** Well-structured markdown with clear sections, code examples, and consistent formatting. No spec — documents what exists.

---

### 6. Orchestrator (CEO) — Coordination

**Assign when:**
- Decomposing a complex goal into subtasks
- Dispatching tasks to other agents
- Monitoring kanban progress
- Coordinating cross-feature dependencies
- Reporting status to human
- Making go/no-go decisions between stages

**Do NOT assign to Orchestrator when:**
- Implementing code (→ Builder)
- Writing documentation (→ Scribe)
- Reviewing code (→ Reviewer)
- Writing tests (→ QA)

---

## Decision Flowchart

```
New task comes in
│
├─ Is it about WHAT to build / HOW to build it?
│   └─→ Researcher (technical research, specs, architecture)
│
├─ Is it about BUILDING something?
│   └─→ Builder (implementation, bug fixes, refactoring)
│
├─ Is it about VERIFYING quality?
│   ├─→ Code review, security, performance?
│   │   └─→ Reviewer
│   └─→ Testing, verification, acceptance?
│       └─→ QA
│
├─ Is it about DOCUMENTING something?
│   └─→ Scribe (docs, API reference, changelogs)
│
├─ Is it about COORDINATING multiple things?
│   └─→ Orchestrator
│
└─ Unknown?
    └─→ Orchestrator decides
```

---

## Parallel Assignment Matrix

The following tasks can run in parallel:

| Phase | Can Run in Parallel | Must Wait For |
|-------|---------------------|---------------|
| Research | Researcher works independently | None |
| Implementation | Builder works on separate features | Researcher specs for their feature |
| Review + QA | Reviewer and QA run simultaneously | Builder code complete |
| Documentation | Scribe documents completed features | All features complete |

---

## Constraint Matrix

| Agent | max_turns | terminal? | kanban? | web? | skills? | mcp? |
|-------|-----------|-----------|---------|------|---------|------|
| Orchestrator | 120 | Yes | Yes | Yes | Yes | Yes |
| Researcher | 60 | Yes | Yes | Yes | Yes | Yes |
| Builder | 90 | Yes | Yes | Yes | Yes | Yes |
| Reviewer | 60 | Yes | No | Yes | Yes | Yes |
| QA | 60 | Yes | No | Yes | Yes | Yes |
| Scribe | 60 | No (limited) | No | Yes | No | No |

---

## Anti-Patterns: Wrong Agent Mistakes

| Mistake | Should Be | Why |
|---------|-----------|-----|
| Researcher writing code | Builder | Researcher focuses on specs, not production code |
| Builder reviewing code quality | Reviewer | Reviewer has dedicated checklist and output format |
| Reviewer writing tests | QA | QA specializes in test design and execution |
| QA writing docs | Scribe | Scribe has documentation-specific standards |
| Orchestrator implementing features | Builder | Orchestrator should delegate, not code |
| Scribe designing architecture | Researcher | Architecture is Researcher's domain |
| Any agent doing the Orchestrator's job | Orchestrator | Only CEO dispatches and coordinates |

---

## Task Description Template

When creating a task, include:

```
Task: <short description>
Assignee: <profile name>
Description: <what needs to be done>
Acceptance Criteria:
  - <verifiable criterion 1>
  - <verifiable criterion 2>
Dependencies: <task IDs that must be done first>
Notes: <relevant context>
```

---

## Version History

| Date | Version | Changes |
|------|---------|---------|
| 2026-05-28 | v1.0.0 | Initial release |
