# Multi-Agent Orchestration

Set up specialized AI agent teams with role-specific toolsets, identities, and continuous workflows.

## Quick Start

The agents are fully pre-defined in the `zerofactory/profiles` directory. 
To customize an agent's behavior, toolset, or constraints, simply edit its `SOUL.custom.md` and `config.custom.yaml` files, then run `make merge-all`.

## Single Source of Truth

Never duplicate information. When a rule, convention, or definition applies across multiple agents:

- Store the **canonical version** in one place.
- **Edit one, update all** — linked profiles auto-see the change.
- If you must customize, **extend** rather than copy-paste-and-edit.

## Team Roles

| Role | Identity |
|------|----------|
| **Orchestrator** | CEO/coordinator — delegates, tracks progress, manages kanban |
| **Researcher** | Architect — researches APIs, designs specs |
| **Builder** | Engineer — writes code, implements features |
| **Reviewer** | Code reviewer — quality gate, security, architecture review |
| **QA** | Quality engineer — test design, regression, performance |
| **Scribe** | Technical writer — docs, API reference, changelogs |

## Pipeline

The workflow is managed via the **Hermes Kanban** system:

```
Goal → Triage → Todo → Ready → In progress (Agents) → Blocked → Done
```

- **Triage**: Raw goals enter here. The `kanban_decomposer` automatically breaks the goal down into a graph of assigned child tasks.
- **Todo**: Auto-generated child tasks sit here. A human must review and approve the generated plan before the pipeline proceeds.
- **Ready**: Plan approved and dependencies met. The dispatcher will automatically claim these.
- **In progress**: The dispatcher has spawned the specific agent (e.g., Researcher, Builder) who is actively working.
- **Blocked**: Worker calls `kanban_block("review-required")` when finished. Task halts and awaits human review.
- **Done**: Human approves final result.

Stages can parallelize: Researcher gathers context for future tasks; QA tests in parallel with Reviewer reviewing completed modules; Scribe documents continuously.

## File Structure

```
zerofactory-orchestration/
├── README.md            ← you are here
├── SKILL.md             ← full procedural guide
└── references/
    └── team-structure.md  ← example team rosters, pipeline layouts
```
