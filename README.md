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
make config-merge-all
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

## The Team

|| Agent | Role | Toolsets | Key Tools |
|---|-------|--------|----------|-----------|
| 1️⃣ | **Orchestrator** | CEO | kanban, delegation, cronjob | task decomposition, agent dispatch, progress tracking |
| 2️⃣ | **Researcher** | CTO | web, browser, file, search_files | technical research, architecture design, specs |
| 3️⃣ | **Builder** | Lead Engineer | file, terminal, search_files, web | feature implementation, bug fixes, refactoring |
| 4️⃣ | **Reviewer** | Code Reviewer | file, terminal, search_files, web | code quality, security audit, performance review |
| 5️⃣ | **QA** | QA Engineer | file, terminal, search_files, web | test design, integration testing, regression testing |
| 6️⃣ | **Scribe** | Documentation | file, terminal, search_files, web | API docs, architecture docs, changelogs, tutorials |

### Agent Profiles

Each profile has three files:

| File | Purpose |
|------|---------|
| `SOUL.md` | Agent identity, responsibilities, tools, constraints |
| `config.custom.yaml` | Profile-specific overrides (merged with common/config.yaml) |

## Workflow Pipeline

```
Goal → Researcher (research) → Builder (implement) → Reviewer (review) → QA (test) → Scribe (document) → Done
```

Each stage can parallelize:
- **Researcher** works independently while **Builder** handles other tasks
- **Reviewer** reviews code as soon as **Builder** finishes a module
- **QA** tests in parallel with **Reviewer** reviewing
- **Scribe** documents as work progresses, not just at the end

## Project Structure

```
zerofactory/
├── Makefile              # Build & management shortcuts
├── README.md             # You are here
├── CONVENTIONS.md        # Shared conventions (single source of truth)
├── ORCHESTRATION.md      # Team structure details
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
│   │   ├── common/       # Base config shared by all agents
│   │   ├── orchestrator/ # CEO — task decomposition & dispatch
│   │   ├── researcher/   # CTO — research & architecture
│   │   ├── builder/      # Lead Engineer — implementation
│   │   ├── reviewer/     # Code Reviewer — quality gates
│   │   ├── qa/           # QA — testing & verification
│   │   └── scribe/       # Documentation specialist
│   └── bin/              # Helper scripts (merge-config.sh)
├── systemd/              # Systemd service files for 24/7 operation
│   ├── README.md         # Systemd setup guide
│   ├── *.service.template # Service unit templates
│   └── *.service          # Generated service units
└── vllm/                 # Docker Compose LLM inference configs
    ├── qwen3.6-35b-a3b/  # NVFP4 35B with DFlash on DGX Spark
    └── qwen3.6-27b/      # Qwen3.6-27B v4 on DGX Spark
```

## Documentation

Full documentation suite: [docs/](docs/)

|| Document | Description |
|----------|-------------|
| [README.md](README.md) | Project overview and quick start |
| [architecture.md](docs/architecture.md) | System design and data flows |
| [api.md](docs/api.md) | CLI interface and configuration reference |
| [setup-guide.md](docs/setup-guide.md) | Setup: hermes-link, systemd, vLLM |
| [changelog.md](docs/changelog.md) | Version history and change log |
| [troubleshooting.md](docs/troubleshooting.md) | Common issues and solutions |
| [CONVENTIONS.md](CONVENTIONS.md) | Shared conventions and standards |
| [ORCHESTRATION.md](ORCHESTRATION.md) | Team structure and workflow details |
| [runbook.md](docs/runbook.md) | Operations runbook |
| [systemd/README.md](systemd/README.md) | Systemd service configuration |

## vLLM Inference (Optional)

GPU-based LLM inference runs via Docker Compose in `vllm/`:

| Setup | Model | GPU | Details |
|-------|-------|-----|---------|
| `vllm/qwen3.6-35b-a3b/` | Qwen3.6-35B-A3B | DGX Spark (NVFP4 + DFlash) | Speculative decoding with AEON-7 |
| `vllm/qwen3.6-27b/` | Qwen3.6-27B v4 | DGX Spark (GB10) | Multimodal with DFlash |

Both expose the OpenAI-compatible API at `http://localhost:8000/v1`.

## Agent Configuration

### Toolsets by Profile

| Agent | Tools | max_turns |
|-------|-------|-----------|
| orchestrator | kanban, delegation, cronjob, file, terminal, web, search_files, skills, mcp | 120 |
| researcher | file, terminal, search_files, web, skills, mcp | 60 |
| builder | file, terminal, search_files, web, kanban, skills, mcp | 90 |
| reviewer | file, terminal, search_files, web, skills, mcp | 60 |
| qa | file, terminal, search_files, web, skills, mcp | 60 |
| scribe | file, terminal, search_files, web | 60 |

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
| `make config-merge` | Merge config for a specific profile (`MERGE_PROFILE=builder make config-merge`) |
| `make systemd-link` | Link systemd services to `/etc/systemd/system/` |
| `make systemd-enable` | Enable all services on boot |
| `make systemd-start` | Start all services |
| `make systemd-stop` | Stop all services |
| `make systemd-status` | Show service status |
| `make systemd-logs` | Show service logs |
| `make systemd-refresh` | Full refresh (generate → link → enable → start) |

## AI Agent & Workspace

- [Hermes Agent](https://hermes-agent.nousresearch.com/): Primary orchestrator for long-running background tasks and coordination across specialist agents.
- [Hermes Workspace](https://github.com/outsourc-e/hermes-workspace): Native web workspace for Hermes Agent — chat, terminal, memory, skills, inspector.

## Service Ports

| Service | Port | Purpose |
|---------|------|---------|
| hermes-gateway | 8642 | API server for agent communication |
| hermes-dashboard | 9119 | Web UI for monitoring |
| hermes-workspace | 3000 | Workspace management (chat, terminal, files) |

## License

See [LICENSE](LICENSE).
