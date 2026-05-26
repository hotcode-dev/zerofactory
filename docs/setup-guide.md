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

## Step 2: Link Hermes Config

Link the config and profiles to the standard Hermes location:

```bash
make hermes-link
```

This creates:
- `~/.hermes/config.yaml` → symlink to `zerofactory/hermes/config.yaml`
- `~/.hermes/profiles/` → symlink to `zerofactory/hermes/profiles/`

## Step 3: Configure Systemd

Generate systemd services from templates:

```bash
cd systemd
env USER="$USER" HOME="$HOME" \
  envsubst < "$(pwd)/hermes-gateway.service.template" > "$(pwd)/hermes-gateway.service"
env USER="$USER" HOME="$HOME" \
  envsubst < "$(pwd)/hermes-dashboard.service.template" > "$(pwd)/hermes-dashboard.service"
env USER="$USER" HOME="$HOME" \
  envsubst < "$(pwd)/hermes-workspace.service.template" > "$(pwd)/hermes-workspace.service"
```

Link and enable:

```bash
make systemd-link
make systemd-enable
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

## Step 5: vLLM GPU Setup

If running LLM inference locally:

1. Install vLLM: `pip install vllm`
2. Configure GPU memory in `hermes/config.yaml`:
   ```yaml
   model:
     default: qwen36-fast
     provider: custom
     base_url: http://.spark.ntsd.dev:8000/v1
   ```
3. Ensure CUDA drivers are installed: `nvidia-smi`
4. Test inference: `vllm serve model-name`

See [troubleshooting.md](troubleshooting.md) for GPU issues.

## Step 6: Start Services

```bash
# Start all services
make systemd-start

# Check status
make systemd-status
```

Expected output:
- `hermes-gateway` — API server on port 8642
- `hermes-dashboard` — Dashboard on port 9119
- `hermes-workspace` — Workspace on port 3000

## Step 7: Verify

```bash
# Check all services running
sudo systemctl status hermes-gateway
sudo systemctl status hermes-dashboard
sudo systemctl status hermes-workspace

# Check logs
sudo journalctl -u hermes-gateway -f
sudo journalctl -u hermes-workspace -f
```

## Maintenance

```bash
# Update from git
cd /path/to/zerofactory
git pull

# Restart services
make systemd-stop
make systemd-link
make systemd-enable
make systemd-start
```

## File Locations

| Component | Path |
|-----------|------|
| Config | `~/.hermes/config.yaml` (symlink → `hermes/config.yaml`) |
| Profiles | `~/.hermes/profiles/` (symlink → `hermes/profiles/`) |
| Systemd units | `/etc/systemd/system/hermes-*.service` |
| Environment | `~/hermes-gateway.env`, `~/hermes-workspace.env` |
| Logs | `journalctl -u hermes-<service>` |
| Kanban DB | `~/.hermes/kanban.db` |

See [systemd/README.md](../systemd/README.md) for detailed systemd configuration.
See [architecture.md](architecture.md) for system overview.
