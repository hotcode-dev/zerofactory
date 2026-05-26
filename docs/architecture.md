# Architecture

Zero Factory is an AI multi-agent orchestration system built on top of **Hermes Agent**. Six specialist agents form a complete software factory, from research to deployment.

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

Each agent is configured in `hermes/profiles/<name>/` with three files:

- **SOUL.md** — Agent identity, responsibilities, tools, constraints
- **system_prompt.txt** — Concise prompt for context injection
- **config.yaml** — Runtime configuration (toolsets, timeouts)

| Profile | Role | Purpose | Key Tools |
|---------|------|---------|-----------|
| orchestrator | CEO | Task decomposition, kanban, delegation | kanban, delegation, cronjob |
| researcher | CTO | Research, specs, architecture | web, browser, file, search_files |
| builder | Lead Engineer | Feature implementation, tests | file, terminal, search_files, web |
| reviewer | Code Reviewer | Quality gates, security | file, terminal, search_files, web |
| qa | QA Engineer | Test design, integration | file, terminal, search_files, web |
| scribe | Documentation | API docs, user guides, changelogs | file, terminal, search_files, web |

### 2. Configuration

Main config at `hermes/config.yaml`:

- **model** — Default model (`qwen36-fast`) via custom provider at `http://spark.ntsd.dev:8000/v1`
- **toolsets** — Controls which tools each agent has access to
- **agent** — Max turns, gateway timeout, retry settings
- **terminal** — Backend (local), Docker images, timeouts
- **compression** — Context compression enabled (threshold 0.5)
- **prompt_caching** — LLM prompt caching for cost reduction

See [setup-guide.md](setup-guide.md) for configuration steps.

### 3. Kanban Board

Task coordination uses a SQLite-based kanban board (`~/.hermes/kanban.db`). Key states:

- **todo** — Queued work
- **running** — Currently being processed
- **blocked** — Waiting on human input
- **done** — Completed

The Orchestrator creates tasks, assigns agents, and monitors progress through this board.

### 4. Systemd Services

Three services run continuously on Linux:

| Service | Purpose |
|---------|---------|
| hermes-gateway | API server for agent communication |
| hermes-dashboard | Web UI for monitoring |
| hermes-workspace | Workspace management (chat, terminal, files) |

See [systemd/README.md](../systemd/README.md) for setup details.

## Data Flow

1. **Goal**: User or Orchestrator submits a goal via CLI (`hermes -p orchestrator -m "..."`)
2. **Research**: Researcher explores the problem, produces a spec
3. **Implementation**: Builder writes code based on the spec
4. **Review**: Reviewer checks quality, security, architecture
5. **Testing**: QA verifies functionality with tests
6. **Documentation**: Scribe documents the changes

Parallel execution: Multiple features can be implemented simultaneously. Review and QA run in parallel.

## Cost Optimization

- Each agent has only necessary skills enabled
- Compression enabled (target ratio 0.2)
- Prompt caching enabled
- Short max_turns per agent to limit token waste
- Tool-use enforcement to prevent redundant API calls

## File Structure

```
zerofactory/
├── README.md                  # Project overview
├── CONVENTIONS.md             # Shared conventions (single source of truth)
├── ORCHESTRATION.md           # Team structure details
├── Makefile                   # Build/management shortcuts
├── LICENSE
├── docs/                      # Documentation suite (this directory)
├── hermes/
│   ├── config.yaml            # Main agent config
│   └── profiles/              # Agent-specific configs
│       ├── orchestrator/
│       ├── researcher/
│       ├── builder/
│       ├── reviewer/
│       ├── qa/
│       └── scribe/
├── systemd/                   # Systemd service files
│   ├── README.md
│   ├── *.service              # Generated services
│   └── *.service.template     # Service templates
```

See [CONVENTIONS.md](../CONVENTIONS.md) for naming conventions and coding standards.
