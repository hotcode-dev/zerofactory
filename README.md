# Zero Factory

A 24/7 AI multi-agent orchestration setup that works in parallel. Six specialized agents form a complete software factory — from research to deployment.

## Quick Start

1. Set up a project directory
2. Link the config: `make hermes-link`
3. Run a command: `hermes -p orchestrator -m "Research how to implement real-time notifications with WebSockets and PostgreSQL"`
4. The Orchestrator delegates to Researcher, who produces a spec
5. Builder implements based on the spec
6. Reviewer and QA run in parallel
7. Scribe documents everything

Full setup guide: [docs/setup-guide.md](docs/setup-guide.md)

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
├── Makefile              # Build & management shortcuts
├── README.md             # You are here
├── CONVENTIONS.md        # Shared conventions (single source of truth)
├── ORCHESTRATION.md      # Team structure details
├── docs/                 # Documentation suite
│   ├── architecture.md   # System design and data flows
│   ├── api.md            # CLI interface reference
│   ├── changelog.md      # Version history
│   ├── setup-guide.md    # Installation and configuration
│   └── troubleshooting.md # Common issues and solutions
├── hermes/
│   ├── config.yaml       # Main agent configuration
│   └── profiles/
│       ├── orchestrator/ # CEO — task decomposition, delegation
│       ├── researcher/   # CTO — research, specs, architecture
│       ├── builder/      # Lead Engineer — implementation
│       ├── reviewer/     # Code Reviewer — quality gates
│       ├── qa/           # QA Engineer — testing
│       └── scribe/       # Documentation specialist
├── systemd/              # Systemd service files
│   ├── README.md         # Systemd setup guide
│   └── *.service         # Generated service units
└── LICENSE
```

## Documentation

Full documentation suite: [docs/](docs/)

| Document | Description |
|----------|-------------|
| [README.md](README.md) | Project overview and quick start |
| [architecture.md](docs/architecture.md) | System design and data flows |
| [api.md](docs/api.md) | CLI interface and configuration reference |
| [setup-guide.md](docs/setup-guide.md) | Setup: hermes-link, systemd, vLLM |
| [changelog.md](docs/changelog.md) | Version history |
| [troubleshooting.md](docs/troubleshooting.md) | Common issues and solutions |
| [CONVENTIONS.md](CONVENTIONS.md) | Project conventions and standards |
| [ORCHESTRATION.md](ORCHESTRATION.md) | Team structure and workflow details |
| [systemd/README.md](systemd/README.md) | Systemd service configuration |

## AI Agent & Workspace

- [Hermes Agent](https://hermes-agent.nousresearch.com/): Primary orchestrator for long-running background tasks and coordination across specialist agents.
- [Hermes Workspace](https://github.com/outsourc-e/heres-workworkspace): Native web workspace for Hermes Agent — chat, terminal, memory, skills, inspector.

## Agent Configuration

Each profile has three key files:

1. **SOUL.md** — Agent identity, responsibilities, tools, constraints
2. **system_prompt.txt** — Concise prompt for immediate context injection
3. **config.yaml** — Full runtime configuration (toolsets, timeouts, capabilities)

Profile-specific toolsets:
- **Orchestrator**: hermes-cli, delegation, kanban, cronjob (coordinator)
- **Researcher**: web, browser, file, search_files (research)
- **Builder**: file, terminal, search_files, web (coding)
- **Reviewer**: file, terminal, search_files, web (review)
- **QA**: file, terminal, search_files, web (testing)
- **Scribe**: file, terminal, search_files, web (documentation)

## Makefile Commands

| Command | Description |
|---------|-------------|
| `make hermes-link` | Link config and profiles to `~/.hermes/` |
| `make systemd-link` | Link systemd services to `/etc/systemd/system/` |
| `make systemd-enable` | Enable all services on boot |
| `make systemd-start` | Start all services |
| `make systemd-stop` | Stop all services |
| `make systemd-status` | Show service status |

## Cost Optimization

- Each agent has only the skills relevant to their role
- All non-essential skills/plugins disabled by default
- Compression enabled for context efficiency
- Prompt caching enabled
- Short max_turns per agent (reduces token waste)

## License

See [LICENSE](LICENSE).
