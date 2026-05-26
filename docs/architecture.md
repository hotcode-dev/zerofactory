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

### 1. Agent Profiles

Each agent is configured in `hermes/profiles/<name>/` with:

- **SOUL.md** — Agent identity, responsibilities, tools, constraints
- **system_prompt.txt** — Concise prompt for context injection
- **config.custom.yaml** — Profile-specific configuration overrides
- **mcp_servers.json** — MCP server configuration (optional)

Configuration is built by merging `profiles/common/config.yaml` (base config) with `profiles/<profile>/config.custom.yaml` (overrides) using `hermes/bin/merge-config.sh`.

### 2. Configuration Hierarchy

```
profiles/common/config.yaml    ← Base config (shared by all agents)
         ↓ + profile override
profiles/<profile>/config.custom.yaml  ← Profile-specific overrides
         ↓ merge-config.sh
hermes/profiles/<profile>/config.yaml  ← Merged final config (symlinked to ~/.hermes/)
```

| Profile | max_turns | gateway_timeout | Key Settings |
|---------|-----------|-----------------|--------------|
| orchestrator | 120 | 3600s | compression threshold 0.3, higher protection |
| researcher | 60 | 1800s | Web/browser toolset |
| builder | 90 | 1800s | Terminal-heavy, file output |
| reviewer | 60 | 1800s | File review checks |
| qa | 60 | 1800s | Terminal testing |
| scribe | 60 | 1800s | File I/O only (no terminal in toolsets) |

### 3. Kanban Board

Task coordination uses a SQLite-based kanban board (`~/.hermes/kanban.db`). Key states:

- **todo** — Queued work
- **running** — Currently being processed
- **blocked** — Waiting on human input
- **done** — Completed

The Orchestrator creates tasks, assigns agents, and monitors progress through this board. Tasks can have parent → child dependencies: a child stays `blocked` until all parents are `done`.

### 4. Systemd Services

Three services run continuously on Linux:

| Service | Port | Purpose |
|---------|------|---------|
| hermes-gateway | 8642 | API server for agent communication |
| hermes-dashboard | 9119 | Web UI for monitoring |
| hermes-workspace | 3000 | Workspace management (chat, terminal, files) |

See [systemd/README.md](../systemd/README.md) for setup details.

## Data Flow

1. **Goal**: User or Orchestrator submits a goal via CLI (`hermes -p orchestrator -m "..."`)
2. **Research**: Researcher explores the problem, produces a spec
3. **Implementation**: Builder writes code based on the spec
4. **Review**: Reviewer checks quality, security, architecture
5. **Testing**: QA verifies functionality with tests
6. **Documentation**: Scribe documents the changes

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
├── CONVENTIONS.md             # Shared conventions (single source of truth)
├── ORCHESTRATION.md           # Team structure details
├── Makefile                   # Build/management shortcuts
├── LICENSE
├── docs/                      # Documentation suite
│   ├── architecture.md        # This file
│   ├── api.md                 # CLI interface reference
│   ├── setup-guide.md         # Setup instructions
│   ├── troubleshooting.md     # Common issues
│   ├── changelog.md           # Version history
│   └── runbook.md             # Operations runbook
├── hermes/
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
├── systemd/                   # Systemd service files
│   ├── *.service.template     # Service templates
│   └── *.service              # Generated services
└── vllm/                      # LLM inference Docker configs
    ├── qwen3.6-35b-a3b/       # 35B model with DFlash
    └── qwen3.6-27b/           # 27B model with DFlash
```

## Agent Communication Protocol

Agents communicate through:
1. **Kanban board** — task status and handoffs
2. **Files** — shared output, configs, documentation
3. **Gateway** — real-time messaging

Each agent has a `description` field in its `config.custom.yaml` for quick identification by the Orchestrator.
