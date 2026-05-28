# Multi-Agent Orchestration

Set up specialized AI agent teams with role-specific toolsets, identities, and continuous workflows.

## Quick Start

1. Pick the roles you need (Researcher, Builder, Reviewer, QA, Scribe, Orchestrator).
2. Create a profile directory under `hermes/profiles/<agent-name>/`.
3. Copy the starter template from `templates/profile-template/` as your starting point.
4. Fill in SOUL.md and config.custom.yaml, then generate config.yaml.
5. Each profile gets three files:

| File | Purpose |
|------|---------|
| **SOUL.md** | Agent identity, core responsibilities, tools & skills, constraints, communication style |
| **config.custom.yaml** | Profile overrides including MCP server settings |
| **config.yaml** | Generated runtime config (do not edit directly) |

## Single Source of Truth

Never duplicate information. When a rule, convention, or definition applies across multiple agents:

- Store the **canonical version** in one place.
- **Cross-reference** it via file links (e.g. `../shared/toolset-conventions.md`).
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

```
Goal → Researcher → Builder → Reviewer → QA → Scribe → Done
```

Stages can parallelize: Reviewer reviews as soon as Builder finishes a module; QA tests in parallel with Reviewer; Scribe documents continuously.

## File Structure

```
multi-agent-orchestration/
├── README.md            ← you are here
├── SKILL.md             ← full procedural guide
├── references/
│   └── team-structure.md  ← example team rosters, pipeline layouts
└── templates/
    └── profile-template/  ← starter for new agent profiles
```
