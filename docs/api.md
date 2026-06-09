# Zero Factory — API Reference

Reference for the Hermes CLI interface, configuration, and system commands used in Zero Factory.

## CLI Usage

### Launch an Agent

```bash
# Launch an agent with a goal
hermes -p <profile> -m "Your task description here"

# Example: Launch the orchestrator
hermes -p orchestrator -m "Research how to implement real-time notifications with WebSockets"

# Example: Launch the builder
hermes -p builder -m "Implement the notification endpoint based on the spec"
```

### Profile Flags

| Flag | Description | Valid Values |
|------|-------------|--------------|
| `-p` | Profile to launch | `orchestrator`, `researcher`, `builder`, `reviewer`, `qa`, `scribe` |
| `-m` | Task description / goal | Free-form text |

### Common Orchestrator Commands

```bash
# Show kanban board
hermes -p orchestrator -m "Show me the current kanban board"

# Check running tasks
hermes -p orchestrator -m "What tasks are currently running?"

# Add a task
hermes -p orchestrator -m "Create task: implement user authentication with JWT"
```

## Configuration File

The base config is at `~/.hermes/profiles/common/config.yaml`.

### Model Configuration

```yaml
model:
  default: qwen36-fast
  provider: custom
custom_providers:
  - name: Spark.ntsd.dev:8000
    base_url: http://spark.ntsd.dev:8000/v1
    model: qwen36-fast
```

### Common Base Settings (profiles/common/config.yaml)

```yaml
agent:
  max_turns: 90
  gateway_timeout: 1800
  api_max_retries: 3
toolsets:
  - hermes-cli
compression:
  enabled: true
  threshold: 0.5
  target_ratio: 0.2
prompt_caching:
  cache_ttl: 5m
```

### Per-Profile Overrides (profiles/<profile>/config.custom.yaml)

Each profile extends the base config with its own overrides. 

For specific toolsets and limits per profile, please consult the [multi-agent-orchestration](../hermes/profiles/common/skills/multi-agent-orchestration/SKILL.md) skill document, which serves as the single source of truth for agent configurations.

### Terminal Configuration

```yaml
terminal:
  backend: local
  timeout: 180
  auto_source_bashrc: true
  docker_image: nikolaik/python-nodejs:python3.11-nodejs20
  persistent_shell: true
```

### Compression Settings

```yaml
compression:
  enabled: true
  threshold: 0.5    # Trigger compression at 0.5M characters
  target_ratio: 0.2  # Target 20% of original size
  protect_last_n: 20 # Keep last 20 messages uncompressed
```

### Memory Configuration

```yaml
memory:
  enabled: true
  user_profile_enabled: true
  memory_char_limit: 2200
  user_char_limit: 1375
```

## Environment Files

### hermes-gateway.env

```bash
API_SERVER_ENABLED=true
API_SERVER_HOST=0.0.0.0
API_SERVER_KEY=
GATEWAY_ALLOW_ALL_USERS=true
```

### hermes-workspace.env

```bash
PORT=3000
HOST=0.0.0.0
HERMES_DASHBOARD_URL=http://127.0.0.1:9119
HERMES_API_URL=http://127.0.0.1:8642
HERMES_PASSWORD=
```

## Agent Profiles Structure

Each profile directory contains:

```
hermes/profiles/<profile>/
├── config.yaml              ← Merged config (base + custom)
├── config.custom.yaml       ← Profile-specific overrides (edit this)
├── SOUL.md                  ← Agent identity and responsibilities
```

### Configuration Merging

```bash
# Merge all profiles' config, jobs, soul, and link skills
make merge-all

# Or manually:
./hermes/bin/merge-config.sh
```

## Quick Reference

| Item | Path |
|------|------|
| Base config | `~/.hermes/profiles/common/config.yaml` |
| Profiles | `hermes/profiles/<agent>/` |
| Base config | `hermes/profiles/common/config.yaml` |
| Profile overrides | `hermes/profiles/<profile>/config.custom.yaml` |
| Config Merge script | `hermes/bin/merge-config.sh` |
| Skills Link script | `hermes/bin/link-skills.sh` |
| Environment files | `~/hermes-gateway.env`, `~/hermes-workspace.env` |
| Kanban DB | `~/.hermes/kanban.db` |
| Architecture | `docs/architecture.md` |
