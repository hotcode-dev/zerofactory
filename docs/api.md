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

### Configuration File

The configuration file is at `hermes/config.yaml`. Key sections:

#### Model Configuration

```yaml
model:
  default: qwen36-fast
  provider: custom
  base_url: http://spark.ntsd.dev:8000/v1
```

#### Agent Settings

```yaml
agent:
  max_turns: 60           # Maximum API calls per task
  gateway_timeout: 1800   # Connection timeout (seconds)
  api_max_retries: 3      # Retry attempts on failure
```

#### Terminal Configuration

```yaml
terminal:
  backend: local
  timeout: 180            # Command timeout (seconds)
  auto_source_bashrc: true
```

#### Compression

```yaml
compression:
  enabled: true
  threshold: 0.5
  target_ratio: 0.2
```

## Environment Variables

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

## Systemd Commands

```bash
# Link services (creates symlinks to /etc/systemd/system)
make systemd-link

# Enable all services
make systemd-enable

# Start all services
make systemd-start

# Stop and disable
make systemd-stop

# Check status
make systemd-status
```

## Makefile Targets

| Target | Description |
|--------|-------------|
| `hermes-link` | Symlink config and profiles to `~/.hermes/` |
| `systemd-link` | Link systemd unit files to `/etc/systemd/system/` |
| `systemd-enable` | Enable all three services |
| `systemd-disable` | Disable all three services |
| `systemd-start` | Start all three services |
| `systemd-stop` | Stop and disable all services |
| `systemd-status` | Show status of all services |

## Agent Toolsets

| Agent | Tools Available |
|-------|----------------|
| orchestrator | kanban, delegation, cronjob |
| researcher | web, browser, file, search_files |
| builder | file, terminal, search_files, web |
| reviewer | file, terminal, search_files, web |
| qa | file, terminal, search_files, web |
| scribe | file, terminal, search_files, web |

## Personality Modes

The TUI supports different personalities (configurable in `config.yaml`):

```yaml
display:
  personality: kawaii  # or: helpful, concise, technical, creative,
                       # teacher, kawaii, catgirl, pirate, shakespeare,
                       # surfer, noir, uwu, philosopher, hype
```

## Status Commands

```bash
# Check gateway status
sudo systemctl status hermes-gateway

# Monitor logs
sudo journalctl -u hermes-gateway -f
sudo journalctl -u hermes-workspace -f

# Check workspace
sudo systemctl status hermes-workspace
```

## Quick Reference

- Config: `hermes/config.yaml`
- Profiles: `hermes/profiles/<agent>/`
- Services: `systemd/`
- Conventions: `CONVENTIONS.md`
- Architecture: `docs/architecture.md`
- Setup: `docs/setup-guide.md`
- Troubleshooting: `docs/troubleshooting.md`
