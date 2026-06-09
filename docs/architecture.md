# Architecture

Zero Factory is an AI multi-agent orchestration system built on **Hermes Agent**. Six specialist agents form a complete software factory, from research to deployment.

## System Overview

```
┌─────────────────────────────────────────────────┐
│              Human User / Orchestrator           │
│              (Command → Goal)                    │
└──────────┬──────────────────────────────────────┘
           │ kanban board (task queue)
           ▼
┌─────────────────────────────────────────────────┐
│              Orchestrator Agent                  │
│              (CEO — task decomposition)          │
│  Tools: kanban, delegation, cronjob             │
│  max_turns: 120, timeout: 3600s                 │
└──┬──┬──┬──┬──┬─────────────────────────────────┘
   │  │  │  │  │
   ▼  ▼  ▼  ▼  ▼
┌─────┐┌─────┐┌─────┐┌─────┐┌─────┐
│Rsrch││Build││Reviw││ QA ││Scribe│
│(CTO)│(Lead ││(Lead│(QA)│(Docs)│
│     │ Eng.)│Reviw.│     │     │
└─────┘└─────┘└─────┘└─────┘└─────┘
```

## Core Components

### 1. Agent Profiles & Configuration

The agent roles, toolsets, and configuration patterns are explicitly defined in the [zerofactory-orchestration](../profiles/common/skills/zerofactory-orchestration/SKILL.md) skill document. Please refer to it as the single source of truth for agent capabilities.

### 3. Kanban Board

Task coordination uses a SQLite-based kanban board (`~/.hermes/kanban.db`). Key states:

- **todo** — Queued work
- **running** — Currently being processed
- **blocked** — Waiting on human input
- **done** — Completed

The Orchestrator creates tasks, assigns agents, and monitors progress through this board. Tasks can have parent → child dependencies: a child stays `blocked` until all parents are `done`.

## Data Flow

1. **Goal Formulation**: User submits a goal via CLI (`hermes -p orchestrator -m "..."`)
2. **Research**: Researcher explores the problem, produces a technical spec
3. 🛑 **Human Plan Review**: Orchestrator pauses, human approves the spec
4. **Implementation**: Builder writes code based on the approved spec
5. **Verification**: Reviewer checks quality/security while QA runs tests
6. 🛑 **Human Result Review**: Orchestrator pauses, human provides final acceptance
7. **Documentation**: Scribe documents the changes

Parallel execution: Review and QA run concurrently. Researcher can work on one feature while Builder handles another.

## Communication Channels

| Channel | Purpose |
|---------|---------|
| Kanban Board | Task handoffs, status tracking, dependency management |
| File System | Shared output files, configuration, documentation |
| Gateway API | Real-time messaging between agents |

## Cost Optimization

| Technique | Setting | Purpose |
|-----------|---------|---------|
| Toolsets | Per-profile | Each agent has only the tools it needs |
| Compression | enabled, threshold 0.5 | Reduces context window usage |
| Prompt caching | cache_ttl: 5m | Reuses system prompt tokens |
| max_turns limits | Per profile (60-120) | Caps token consumption per task |
| Short-lived tasks | Task-based lifecycle | No idle agents burning resources |

## File Structure

```
zerofactory/
├── README.md                  # Project overview
├── Makefile                   # Build/management shortcuts
├── LICENSE
├── docs/                      # Documentation suite
│   ├── architecture.md        # This file
│   ├── api.md                 # CLI interface reference
│   ├── setup-guide.md         # Setup instructions
│   ├── troubleshooting.md     # Common issues
│   ├── changelog.md           # Version history
│   └── runbook.md             # Operations runbook
│   ├── profiles/              # Agent configurations
│   │   ├── common/            # Base config for all agents
│   │   │   ├── config.yaml
│   │   │   └── SOUL.md
│   │   ├── orchestrator/      # CEO — task decomposition & dispatch
│   │   ├── researcher/        # CTO — research & architecture
│   │   ├── builder/           # Lead Engineer — implementation
│   │   ├── reviewer/          # Code Review — quality gates
│   │   ├── qa/                # QA — testing & verification
│   │   └── scribe/            # Documentation — API docs & guides
│   └── bin/                   # Helper scripts
```

## Agent Communication Protocol

Agents communicate through:
1. **Kanban board** — task status and handoffs
2. **Files** — shared output, configs, documentation
3. **Gateway** — real-time messaging

Each agent has a `description` field in its `config.custom.yaml` for quick identification by the Orchestrator.
