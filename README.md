# Zero Factory

A 24/7 AI multi-agent orchestration system built on Hermes Agent. Six specialized agents form a complete software factory — from research to deployment.

## Quick Start

```bash
# 1. Clone the repo
git clone <repo-url> zerofactory
cd zerofactory

# 2. Link Hermes config
make hermes-link

# 3. Launch an agent
hermes -p orchestrator -m "Research how to implement real-time notifications with WebSockets and PostgreSQL"

# 4. The Orchestrator delegates to Researcher, who produces a spec
#    then Builder implements, Reviewer checks quality, QA tests, Scribe documents
```

Full setup guide: [docs/setup-guide.md](docs/setup-guide.md)

## Config Merge Step

Any time you change a profile config (including MCP server settings), you must rebuild merged runtime configs:

```bash
make config-merge
```

Why this matters:
- Hermes reads `hermes/profiles/<profile>/config.yaml` at runtime
- `config.yaml` is generated from `config.custom.yaml`
- If you skip merge, your config changes will not be applied

## Core Principles

| Pillar | Description |
|--------|-------------|
| **24/7 Development** | Continuous iterations with frequent reprioritization, rolling handoffs, and parallel execution |
| **Productivity & Automation** | Multi-agent workflows that automate routine tasks end-to-end |
| **Quality & Reliability** | High-quality, maintainable, secure software with layered review |
| **Cost Efficiency** | Optimized token usage — each agent has only the skills it needs |
| **Hybrid Review** | Human insight combined with AI-assisted review at every stage |
| **Single Source of Truth** | One canonical location for shared info. Link, don't copy. |
| **Minimalist** | Everything as small, simple, clean, and usable as possible |

## Orchestration & Team Structure

Zero Factory operates using a specialized team of Hermes agents (Orchestrator, Researcher, Builder, Reviewer, QA, Scribe) following an agile parallel pipeline.

The single source of truth for the team structure, pipeline architecture, and agent rules is defined in the [multi-agent-orchestration](hermes/profiles/common/skills/multi-agent-orchestration/SKILL.md) skill. Please refer to it for comprehensive details on how the factory operates.

## Project Structure

```
zerofactory/
├── Makefile              # Build & management shortcuts
├── README.md             # You are here
├── LICENSE
├── docs/                 # Documentation suite
│   ├── architecture.md   # System design and data flows
│   ├── api.md            # CLI interface and configuration reference
│   ├── setup-guide.md    # Installation and configuration
│   ├── troubleshooting.md # Common issues and solutions
│   ├── changelog.md      # Version history
│   └── runbook.md        # Operations runbook
├── hermes/               # Agent configuration
│   ├── profiles/         # Agent profiles
│   │   ├── common/       # Base config shared by all agents (source of truth)
│   │   ├── orchestrator/ # CEO — task decomposition & dispatch
│   │   ├── researcher/   # CTO — research & architecture
│   │   ├── builder/      # Lead Engineer — implementation
│   │   ├── reviewer/     # Code Reviewer — quality gates
│   │   ├── qa/           # QA — testing & verification
│   │   └── scribe/       # Documentation specialist
│   └── bin/              # Helper scripts (merge-config.sh)
```

## Documentation

Full documentation suite: [docs/](docs/)

|| Document | Description |
|----------|-------------|
| [README.md](README.md) | Project overview and quick start |
| [architecture.md](docs/architecture.md) | System design and data flows |
| [api.md](docs/api.md) | CLI interface and configuration reference |
| [setup-guide.md](docs/setup-guide.md) | Setup: hermes-link |
| [changelog.md](docs/changelog.md) | Version history and change log |
| [troubleshooting.md](docs/troubleshooting.md) | Common issues and solutions |
| [runbook.md](docs/runbook.md) | Operations runbook |

## Agent Configuration

### Toolsets by Profile

Toolsets and configuration constraints are defined in the [multi-agent-orchestration](hermes/profiles/common/skills/multi-agent-orchestration/SKILL.md) skill document. Please reference it for the canonical list of tools allowed per agent.

### Configuration Hierarchy

```
profiles/common/config.yaml    ← Base config (all agents share)
         ↓ + profile override
profiles/<profile>/config.custom.yaml  ← Profile-specific overrides
         ↓ merge-config.sh
hermes/profiles/<profile>/config.yaml  ← Merged final config
```

## Makefile Commands

| Command | Description |
|---------|-------------|
| `make hermes-link` | Link `~/.hermes/profiles/` only |
| `make config-merge` | Merge config for all profiles |
| `make skills-link` | Link common skills to all profiles |

## AI Agent & Workspace

- [Hermes Agent](https://hermes-agent.nousresearch.com/): Primary orchestrator for long-running background tasks and coordination across specialist agents.
- [Hermes Workspace](https://github.com/outsourc-e/hermes-workspace): Native web workspace for Hermes Agent — chat, terminal, memory, skills, inspector.

## Service Ports

| Service | Port | Purpose |
|---------|------|---------|
| hermes-gateway | 8642 | API server for agent communication |
| hermes-dashboard | 9119 | Web UI for monitoring |
| hermes-workspace | 3000 | Workspace management (chat, terminal, files) |
| hermes-webui | 8787 | Native web interface for Hermes |

## License

See [LICENSE](LICENSE).
