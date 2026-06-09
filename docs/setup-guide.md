# Setup Guide

Step-by-step guide to install and configure Zero Factory.

## Prerequisites

- Linux machine (Raspberry Pi or x86_64)
- Python 3.11+
- Node.js (for hermes-workspace)
- Hermes Agent installed
- GPU (optional, for LLM inference)

## Step 1: Clone and Setup

```bash
cd ~
git clone <repo-url> zerofactory
cd zerofactory
```

## Step 2: Link Hermes Profiles

Link profiles to the standard Hermes location:

```bash
make hermes-link
```

This creates:
- `~/.hermes/profiles/` → symlink to `zerofactory/profiles/`

## Merge Step

After any edit to `profiles/<profile>/config.custom.yaml` (including MCP server changes) or when adding custom skills, regenerate merged runtime files and links:

```bash
make merge-all
```

If you only want to merge configs, you can run `make config-merge`. Do not edit `config.yaml` directly; it is generated output.

### Configuration Hierarchy

```
profiles/common/config.yaml    ← Base config (shared by all agents)
         ↓ + profile override
profiles/<profile>/config.custom.yaml  ← Profile-specific overrides
         ↓ merge-config.sh
profiles/<profile>/config.yaml  ← Merged final config
```

Each profile extends the base config with its own overrides. To manually merge configurations across all profiles:

```bash
./bin/merge-config.sh
```

You can also link common skills using:

```bash
./bin/link-skills.sh
```

## Step 4: Configure Environment Files

### hermes-gateway.env

Create at `~/hermes-gateway.env`:

```bash
API_SERVER_ENABLED=true
API_SERVER_HOST=0.0.0.0
API_SERVER_KEY=
GATEWAY_ALLOW_ALL_USERS=true
```

### hermes-workspace.env

Create at `~/hermes-workspace.env`:

```bash
PORT=3000
HOST=0.0.0.0
HERMES_DASHBOARD_URL=http://127.0.0.1:9119
HERMES_API_URL=http://127.0.0.1:8642
HERMES_PASSWORD=***
```

## Step 5: Configure Agent Profiles

### Base Configuration

All agents share the base config at `profiles/common/config.yaml`:

```yaml
model:
  default: qwen36-fast
  provider: custom
agent:
  max_turns: 90
  gateway_timeout: 1800
compression:
  enabled: true
  threshold: 0.5
```

### Profile Overrides

Each profile can override settings via `config.custom.yaml`:

| Profile | max_turns | Key Differences |
|---------|-----------|-----------------|
| orchestrator | 120 | Longer timeout (3600s), higher compression protection |
| builder | 90 | Terminal-heavy, file output |
| researcher | 60 | Web browser, file I/O |
| reviewer | 60 | File-heavy review checks |
| qa | 60 | Terminal testing |
| scribe | 60 | File I/O only (no terminal) |

Example — orchestrator custom config:

```yaml
agent:
  max_turns: 120
  gateway_timeout: 3600
compression:
  threshold: 0.3  # Lower threshold for complex task trees
```

### Toolset Management

Each profile has a specific toolset:

```yaml
# orchestrator — full orchestration
toolsets:
  - kanban
  - delegation
  - cronjob
  - file
  - terminal
  - search_files
  - web
  - skills
  - mcp

# builder — coding focused
toolsets:
  - file
  - terminal
  - search_files
  - web
  - kanban
  - skills
  - mcp

# scribe — documentation only
toolsets:
  - file
  - terminal
  - search_files
  - web
```

### Adding MCP Servers

Configure MCP servers in each profile's `config.custom.yaml`:

```bash
# Edit profile override
vim profiles/<profile>/config.custom.yaml
```

Then run `make merge-all` (see "Merge Step" above). Do not edit `config.yaml` directly; it is generated.

## Step 8: Verify

```bash
# Check all services running
sudo systemctl status hermes-gateway
sudo systemctl status hermes-dashboard
sudo systemctl status hermes-workspace
sudo systemctl status hermes-webui

# Check logs
sudo journalctl -u hermes-gateway -f
sudo journalctl -u hermes-workspace -f
```

## Using the System

### Launch an Agent

```bash
hermes -p orchestrator -m "Research how to implement real-time notifications with WebSockets"
```

The Orchestrator will:
1. Decompose the task
2. Dispatch to Researcher (research) → Builder (implement)
3. Run Reviewer and QA in parallel
4. Scribe documents everything

## Maintenance

```bash
# Update from git
cd /path/to/zerofactory
git pull

# Regenerate links
make hermes-link
```

## File Locations

| Component | Path |
|-----------|------|
| Profiles | `~/.hermes/profiles/` (symlink → `profiles/`) |
| Environment | `~/hermes-gateway.env`, `~/hermes-workspace.env` |
| Logs | `journalctl -u hermes-<service>` |
| Kanban DB | `~/.hermes/kanban.db` |
| Profile config | `profiles/<agent>/config.custom.yaml` |
| Base config | `~/.hermes/profiles/common/config.yaml` |

## Troubleshooting

- **Services not starting**: Check env files exist and have correct paths
- **Config changes not reflected**: Run `make hermes-link` to re-link
- **Agent not responding**: Check gateway is running, model endpoint is reachable
- **Disk space issues**: Check `df -h`, clean journal logs with `journalctl --vacuum-time=7d`

See [troubleshooting.md](troubleshooting.md) for detailed issue resolution.
