# Zero Factory

A 24/7 AI multi-agent orchestration setup that works in parallel. Six specialized agents form a complete software factory — from research to deployment.

## Core Principles

This AI setup focuses on these pillars:

- **24/7 agile non-stop development**: Operate in continuous short iterations with frequent reprioritization, quick feedback, rolling handoffs, parallel execution, automated checks, and immediate follow-up on blockers.
- **Productivity & automation**: Build efficient multi-agent workflows and automate routine tasks.
- **Quality, performance, reliability & security**: Deliver high-quality, maintainable, stable, dependable, secure, and high-performance software outcomes.
- **Cost efficiency**: Reduce cost by optimizing token usage and keeping workflows to as few steps as possible. Each agent only has skills related to their specific role.
- **Hybrid Review**: Combine human insight with AI-assisted review to validate plans early and review code thoroughly for better outcomes.
- **Single source of truth**: One canonical location for shared info. Link, don't copy — edit one, update all.
- **Minimalist**: Keep everything as small, simple, clean, and usable as possible.

## The Team

| Agent | Role | Specialization |
|-------|------|----------------|
| **Orchestrator** | CEO | Task decomposition, agent dispatch, progress tracking, kanban management |
| **Researcher** | Architect | Technical research, architecture design, feasibility analysis, specs |
| **Builder** | Engineer | Feature implementation, bug fixes, refactoring, test writing |
| **Reviewer** | Code Reviewer | Code quality, architecture review, security audit, performance analysis |
| **QA** | Quality Assurance | Test design, integration testing, regression testing, bug tracking |
| **Scribe** | Documentation | API docs, architecture docs, changelogs, tutorials, knowledge base |

## Workflow Pipeline

```
Goal → Researcher (research & specs) → Builder (implement) → Reviewer (review) → QA (test) → Scribe (document) → Done
```

Each stage can parallelize:
- Researcher works independently while Builder handles other tasks
- Reviewer can review code as soon as Builder finishes a module
- QA tests in parallel with Reviewer reviewing
- Scribe documents as work progresses, not just at the end

## Project Structure

```
zerofactory/
├── Makefile
├── README.md
├── hermes/
│   ├── config.yaml
│   └── profiles/
│       ├── orchestrator/
│       │   ├── SOUL.md
│       │   ├── system_prompt.txt
│       │   └── config.yaml
│       ├── builder/
│       │   ├── SOUL.md
│       │   ├── system_prompt.txt
│       │   └── config.yaml
│       ├── researcher/
│       │   ├── SOUL.md
│       │   ├── system_prompt.txt
│       │   └── config.yaml
│       ├── reviewer/
│       │   ├── SOUL.md
│       │   ├── system_prompt.txt
│       │   └── config.yaml
│       ├── qa/
│       │   ├── SOUL.md
│       │   ├── system_prompt.txt
│       │   └── config.yaml
│       └── scribe/
│           ├── SOUL.md
│           ├── system_prompt.txt
│           └── config.yaml
```

## AI Agent & Workspace

- [Hermes Agent](https://hermes-agent.nousresearch.com/): Primary orchestrator for long-running background tasks and coordination across specialist agents.
- [Hermes Workspace](https://github.com/outsourc-e/heres-workspace): Native web workspace for Hermes Agent — chat, terminal, memory, skills, inspector.

## Agent Configuration

Each profile has three key files:

1. **SOUL.md** — Agent identity, responsibilities, tools, constraints
2. **system_prompt.txt** — Concise prompt for immediate context injection
3. **config.yaml** — Full runtime configuration (toolsets, timeouts, capabilities)

Profile-specific toolsets:
- **Orchestrator**: hermes-cli, delegation, kanban, cronjob (coordinator)
- **Researcher**: web, browser, file, terminal, search_files (research)
- **Builder**: file, terminal, search_files, web (coding)
- **Reviewer**: file, terminal, search_files, web (review)
- **QA**: file, terminal, search_files, web (testing)
- **Scribe**: file, terminal, search_files, web (documentation)

## Quick Start

1. Set up a project directory
2. Run a command: `hermes -p orchestrator -m "Research how to implement real-time notifications with WebSockets and PostgreSQL"`
3. The Orchestrator delegates to Researcher, who produces a spec
4. Builder implements based on the spec
5. Reviewer and QA run in parallel
6. Scribe documents everything

## Cost Optimization

- Each agent has only the skills relevant to their role
- All non-essential skills/plugins disabled by default
- Compression enabled for context efficiency
- Prompt caching enabled
- Short max_turns per agent (reduces token waste)
