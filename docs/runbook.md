# Zero Factory Operations Runbook

Complete operational runbook for Zero Factory — the AI multi-agent orchestration system.

## Table of Contents

1. [Getting Started](#getting-started)
2. [Config Merge Step](#config-merge-step)
3. [Agent Profiles](#agent-profiles)
4. [Configuration Reference](#configuration-reference)
5. [Daily Operations](#daily-operations)
6. [Maintenance Procedures](#maintenance-procedures)
7. [Emergency Procedures](#emergency-procedures)
8. [Monitoring & Alerting](#monitoring--alerting)
9. [Agent Communication Protocol](#agent-communication-protocol)
10. [Task Lifecycle](#task-lifecycle)
11. [Agent Dispatch Reference](#agent-dispatch-reference)
12. [Appendix](#appendix)

---

## Getting Started

### Quick Reference

| Component | Port | Service Name |
|-----------|------|-------------|
| Gateway (API) | 8642 | hermes-gateway |
| Dashboard (Web UI) | 9119 | hermes-dashboard |
| Workspace | 3000 | hermes-workspace |
| Model API | 8000 | spark.ntsd.dev (custom provider) |

### First-Time Setup

```bash
# 1. Clone the repository
cd ~
git clone <repo-url> zerofactory
cd zerofactory

# 2. Link Hermes config to standard location
make hermes-link

```

### Basic Usage

```bash
# Launch an agent with a task
hermes -p orchestrator -m "Research and implement real-time notifications"

# Check if a specific agent is available
hermes -p builder -m "Implement the notification endpoint"

# View kanban board tasks
hermes -p orchestrator -m "Show me the current kanban board"
```

### Key File Locations

| Purpose | Path |
|---------|------|
| Base config | `~/.hermes/profiles/common/config.yaml` |
| Agent profiles | `~/.hermes/profiles/` (symlinked from `profiles/`) |
| Agent SOUL files | `~/.hermes/profiles/<profile>/SOUL.md` |
| Kanban database | `~/.hermes/kanban.db` |
| Environment files | `~/hermes-gateway.env`, `~/hermes-workspace.env` |
|| Project root | `/home/ntsd/git/hotcode/zerofactory` |

---

## Config Merge Step

Any change to `profiles/<profile>/config.custom.yaml` (including MCP server changes) requires regenerating merged runtime configs.

Run:

```bash
make merge-all
```

If this step is skipped, Hermes continues using stale `config.yaml` values.

## Agent Profiles Reference

### Orchestrator (CEO)

Launch with: `hermes -p orchestrator`

- **Role**: Task decomposition, kanban management, agent dispatch
- **Toolsets**: kanban, delegation, cronjob
- **Config**: max_turns=120, gateway_timeout=3600s
- **Key file**: `profiles/orchestrator/SOUL.md`

### Researcher (CTO)

Launch with: `hermes -p researcher`

- **Role**: Technical research, architecture design, feasibility analysis
- **Toolsets**: web, browser, file, search_files
- **Config**: Uses model catalog for latest research
- **Key file**: `profiles/researcher/SOUL.md`

### Builder (Lead Engineer)

Launch with: `hermes -p builder`

- **Role**: Feature implementation, bug fixes, refactoring
- **Toolsets**: file, terminal, search_files, web
- **Config**: max_turns=90, compression enabled
- **Stack**: TypeScript (Bun), PostgreSQL, Redis
- **Key file**: `profiles/builder/SOUL.md`

### Reviewer (Code Reviewer)

Launch with: `hermes -p reviewer`

- **Role**: Code quality gates, security audit, performance review
- **Toolsets**: file, terminal, search_files, web
- **Config**: max_turns=90, compression enabled
- **Key file**: `profiles/reviewer/SOUL.md`

### QA (Quality Assurance)

Launch with: `hermes -p qa`

- **Role**: Test design, integration testing, regression testing
- **Toolsets**: file, terminal, search_files, web
- **Config**: max_turns=90, compression enabled
- **Key file**: `profiles/qa/SOUL.md`

### Scribe (Documentation)

Launch with: `hermes -p scribe`

- **Role**: Technical documentation, API docs, changelogs
- **Toolsets**: file, terminal, search_files, web
- **Config**: max_turns=90, compression enabled
- **Key file**: `profiles/scribe/SOUL.md`

---

## Configuration Reference

### Model Configuration

Primary model: `qwen36-fast` via custom provider at `http://spark.ntsd.dev:8000/v1`

```yaml
custom_providers:
  - name: Spark.ntsd.dev:8000
    base_url: http://spark.ntsd.dev:8000/v1
    model: qwen36-fast
```

### Config Merge Process

Each profile's config is built from two files:
1. `profiles/common/config.yaml` — Base configuration (shared by all agents)
2. `profiles/<profile>/config.custom.yaml` — Profile-specific overrides

Run `bin/merge-config.sh` to rebuild all profiles.

### Key Settings by Profile

| Setting | Orchestrator | Builder | Reviewer | QA | Scribe |
|---------|-------------|---------|----------|-----|--------|
| max_turns | 120 | 90 | 90 | 90 | 90 |
| gateway_timeout | 3600s | 1800s | 1800s | 1800s | 1800s |
| compression.threshold | 0.3 | 0.5 | 0.5 | 0.5 | 0.5 |
| protect_last_n | 30 | 20 | 20 | 20 | 20 |

Orchestrator has longer timeout (1 hour) for complex orchestration tasks.
Lower compression threshold preserves context for complex task trees.

### Toolsets by Profile

| Profile | Tools |
|---------|-------|
| orchestrator | kanban, delegation, cronjob |
| researcher | web, browser, file, search_files |
| builder | file, terminal, search_files, web |
| reviewer | file, terminal, search_files, web |
| qa | file, terminal, search_files, web |
| scribe | file, terminal, search_files, web |

### Environment Files

**hermes-gateway.env** (at `~/hermes-gateway.env`):
```bash
API_SERVER_ENABLED=true
API_SERVER_HOST=0.0.0.0
API_SERVER_KEY=
GATEWAY_ALLOW_ALL_USERS=true
```

**hermes-workspace.env** (at `~/hermes-workspace.env`):
```bash
PORT=3000
HOST=0.0.0.0
HERMES_DASHBOARD_URL=http://127.0.0.1:9119
HERMES_API_URL=http://127.0.0.1:8642
HERMES_PASSWORD=***
```

### MCP Servers

Each profile defines MCP servers in `config.custom.yaml`.

To add or update MCP servers for any profile:
1. Edit `profiles/<profile>/config.custom.yaml`
2. Regenerate merged runtime configs:

```bash
make merge-all
```

Hermes reads per-profile `config.yaml`, which is generated from `config.custom.yaml`.

---

## 5. Daily Operations

### Morning Routine

1. Verify kanban board has pending tasks:
   ```bash
   hermes -p orchestrator -m "Show kanban board status"
   ```

### Managing Agent Work

- Monitor kanban board:
  ```bash
  hermes -p orchestrator -m "What tasks are currently running?"
  ```
- Add tasks for agents:
  ```bash
  hermes -p orchestrator -m "Add task: optimize database queries"
  ```


---

## 6. Maintenance Procedures

### Disk Space Management

```bash
# Check disk usage
du -sh ~/.hermes/

# Prune old kanban tasks
hermes -p orchestrator -m "Archive completed kanban tasks from last week"
```

### Config Updates

```bash
# 1. Edit config at source
cd /home/ntsd/git/hotcode/zerofactory
vim profiles/<profile>/config.custom.yaml

# 2. Regenerate merged config
make merge-all
```

### Profile Additions

To add a new profile:
```bash
mkdir -p profiles/<new-profile>
cp profiles/common/SOUL.md profiles/<new-profile>/
cp profiles/common/config.yaml profiles/<new-profile>/config.custom.yaml
# Edit SOUL.md and config.custom.yaml with profile-specific settings
```

---

## 7. Emergency Procedures




### Hardware Issues

- **OOM Kill**: Check `free -h`, reduce `max_turns` or compression threshold
- **Disk full**: `df -h`


---

## 8. Monitoring & Alerting

### Health Checks

```bash
# Gateway alive
curl -s http://localhost:8642/health > /dev/null && echo "OK" || echo "DOWN"

# Workspace UI
curl -s http://localhost:3000 > /dev/null && echo "OK" || echo "DOWN"

# Dashboard
curl -s http://localhost:9119 > /dev/null && echo "OK" || echo "DOWN"

# Model API
curl -s http://spark.ntsd.dev:8000/v1/models > /dev/null && echo "OK" || echo "DOWN"
```

### Key Metrics

| Metric | Check Command | Alert Threshold |
|--------|---------------|-----------------|
| Disk usage | `df -h` | > 85% |
| Memory usage | `free -h` | > 90% |
| Active kanban tasks | `hermes -p orchestrator -m "kanban"` | > 0 stuck > 1h |

### Cron Monitoring (Optional)

```bash
# Add to crontab for periodic health checks
*/5 * * * * curl -s http://localhost:8642/health > /dev/null
```

---

## 9. Agent Communication Protocol

### How Agents Talk

Agents communicate through three channels:

1. **Kanban Board** (`~/.hermes/kanban.db`) — task handoffs and status
2. **File System** — shared output files in `docs/` and project directories
3. **Hermis Gateway** — real-time messaging via the API server

### Task Handoff Flow

```
Orchestrator → assigns task on kanban → Agent claims task → works → marks done
```

- Tasks flow through states: `todo` → `running` → `done` (or `blocked`)
- When blocked, the human agent reviews and provides guidance
- Each task has a parent → child chain for traceability

### Naming Conventions

| Entity | Format | Example |
|--------|--------|---------|
| Task IDs | `t_<hex>` | `t_85207e5d` |
| Profiles | kebab-case | `hermes-gateway` |
| Files | kebab-case | `user-auth-docs.md` |

---

## 10. Task Lifecycle

### States

```
todo → running → done
  ↘       ↘
   blocked (← human unblocks → running)
```

### Task States Explained

| State | Description | Action |
|-------|-------------|--------|
| `todo` | Queued, not yet started | Wait for agent |
| `running` | Agent actively working | Monitor progress |
| `blocked` | Waiting on human input | Provide guidance |
| `done` | Task completed | Archive or review |

### Task Dependencies

Tasks can have parent-child relationships:
- Child tasks stay in `blocked` until **all** parents are `done`
- Use `--parent` flag when creating dependent tasks
- The Orchestrator manages dependency chains automatically

### Archiving

Old completed tasks can be archived:
```bash
hermes -p orchestrator -m "Archive all 'done' tasks from last month"
```

---

## 11. Agent Dispatch Reference

See [zerofactory-orchestration](../profiles/common/skills/zerofactory-orchestration/SKILL.md) for the complete task-to-agent mapping.

**Quick summary:**

| Task Type | Correct Agent |
|-----------|--------------|
| Research, architecture, specs | Researcher |
| Code implementation, bug fixes | Builder |
| Code quality review, security audit | Reviewer |
| Test design, verification | QA |
| Documentation, API reference, changelogs | Scribe |
| Task decomposition, coordination | Orchestrator |

See the full dispatch reference for decision flowcharts, anti-patterns, and parallel assignment guidance.

## 12. Appendix

### A. Quick Command Reference

```bash
# Agent commands
hermes -p <profile> -m "<task>"              # Launch agent
hermes -p orchestrator -m "show kanban"       # Check tasks

# Service commands
make hermes-link          # Link config

```

### B. Configuration Hierarchy

```
profiles/common/config.yaml    ← Base config (all agents share)
         ↓ + profile override
profiles/<profile>/config.custom.yaml  ← Profile-specific overrides
         ↓ merge-config.sh
profiles/<profile>/config.yaml  ← Merged final config
```

### C. File Structure Map

```
hermes/
├── common/           ← Shared base config
│   ├── config.yaml   ← Base config for all agents
│   └── SOUL.md       ← Base identity
├── orchestrator/     ← CEO — task management
│   ├── config.yaml   ← Merged config
│   ├── config.custom.yaml ← Profile overrides
│   ├── SOUL.md       ← Agent identity
├── researcher/       ← CTO — research & architecture
├── builder/          ← Lead Engineer — implementation
├── reviewer/         ← Code Reviewer — quality gates
├── qa/               ← QA — testing
└── scribe/           ← Documentation specialist
```

### D. Service Ports

| Service | Port | Protocol | Purpose |
|---------|------|----------|---------|
| hermes-gateway | 8642 | HTTP/REST | Agent API server |
| hermes-dashboard | 9119 | HTTP/Web | Dashboard web UI |
| hermes-workspace | 3000 | HTTP/Web | Workspace chat/terminal |

### E. Configuration Keys Quick Reference

| Setting | Purpose | Default |
|---------|---------|---------|
| `agent.max_turns` | Max API calls per task | 60 (default) |
| `agent.gateway_timeout` | Connection timeout (seconds) | 1800 |
| `compression.enabled` | Context compression on/off | true |
| `compression.threshold` | Trigger compression at char count | 0.5 |
| `compression.target_ratio` | Target compression ratio | 0.2 |
| `prompt_caching.enabled` | LLM prompt caching | true |
| `terminal.timeout` | Terminal command timeout (seconds) | 180 |
| `memory.enabled` | AI memory system | true |

### F. Glossary

| Term | Definition |
|------|------------|
| **Kanban** | SQLite-based task board for agent coordination |
| **Profile** | A named agent configuration with SOUL.md and config |
| **Toolset** | A set of tools available to a specific profile |
| **SOUL** | Agent's identity file defining role, constraints, responsibilities |
| **DFlash** | Dynamic Flash for speculative decoding acceleration |
| **NVFP4** | NVIDIA FP4 quantization format |
| **TIR** | Tool-input-response, the agent interaction loop |
| **MCP** | Model Context Protocol for tool integration |
