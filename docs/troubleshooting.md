# Troubleshooting

Common issues and solutions for Zero Factory.

## Systemd Services

### Services not starting

```bash
# Check status
sudo systemctl status hermes-gateway
sudo systemctl status hermes-dashboard
sudo systemctl status hermes-workspace

# Check logs
sudo journalctl -u hermes-gateway -f
sudo journalctl -u hermes-workspace -f
```

**Fix:** Ensure the env files exist and have correct paths:
- `~/hermes-gateway.env`
- `~/hermes-workspace.env`

Verify systemd units point to the correct paths:
```bash
cat /etc/systemd/system/hermes-gateway.service | grep ExecStart
```

### Service won't start after reboot

```bash
sudo systemctl daemon-reload
make systemd-link
make systemd-enable
```

## Hermes Link Issues

### Symlink broken

```bash
# Re-link
make hermes-link

# Verify
ls -la ~/.hermes/config.yaml
ls -la ~/.hermes/profiles/
```

### Config changes not reflecting

The config files are symlinked from `~/.hermes/`. Changes should appear immediately. If not:

```bash
# Force re-link
make hermes-link
```

### Agent not using correct config

Each agent profile merges `common/config.yaml` with its `config.custom.yaml`. If changes aren't taking effect:

```bash
# Manually merge the profile's config
./hermes/bin/merge-config.sh <profile-name>

# Check the merged output
cat ~/.hermes/profiles/<profile>/config.yaml
```

## Agent Issues

### Agent not responding

1. Check gateway is running:
   ```bash
   sudo systemctl status hermes-gateway
   ```

2. Check logs for errors:
   ```bash
   sudo journalctl -u hermes-gateway -f
   ```

3. Verify model is accessible:
   ```bash
   curl http://spark.ntsd.dev:8000/v1/models
   ```

### Kanban board not updating

- Check hermes workspace is running: `sudo systemctl status hermes-workspace`
- Verify kanban DB exists: `ls -la ~/.hermes/kanban.db`
- Check logs: `sudo journalctl -u hermes-workspace -f`

### Agent stuck in loop

- Check `max_turns` in `hermes/profiles/<profile>/config.custom.yaml` (orchestrator: 120, others: 60-90)
- Review compression settings (default: enabled, threshold 0.5)
- Check prompt caching is enabled

### Missing tools for an agent

Check `profiles/<agent>/config.custom.yaml` → `toolsets`. Add missing tools:

```yaml
toolsets:
  - file
  - terminal
  - search_files
  - web
  - kanban    # Add if needed
  - skills
  - mcp
```

## Configuration Issues

### Config merge failures

```bash
# Check if the merge script exists
ls -la hermes/bin/merge-config.sh

# Re-link to refresh
make hermes-link

# Test merge manually
./hermes/bin/merge-config.sh <profile-name>
```

### Profile not recognized

```bash
# Verify profile directory exists
ls ~/.hermes/profiles/<profile>/

# Ensure SOUL.md and config.yaml exist
ls ~/.hermes/profiles/<profile>/SOUL.md
ls ~/.hermes/profiles/<profile>/config.yaml
```

### Config override not taking effect

1. Edit `hermes/profiles/<profile>/config.custom.yaml`
2. Merge: `./hermes/bin/merge-config.sh <profile-name>`
3. The merged config goes to `hermes/profiles/<profile>/config.yaml`
4. If symlinked, `~/.hermes/profiles/<profile>/` will reflect changes

## Network Issues

### Can't reach API server

```bash
# Check port
ss -tlnp | grep 8642

# Check firewall
sudo ufw status
```

### Workspace UI not accessible

- Default port: 3000
- Default URL: `http://localhost:3000`
- Check: `sudo systemctl status hermes-workspace`

## Terminal Issues

### Commands hang

- Terminal timeout defaults to 180s (configurable in `config.custom.yaml`)
- Increase if needed:
  ```yaml
  terminal:
    timeout: 300
  ```

### PATH not set in systemd

Services source `.bashrc`. If custom binaries are needed:

```bash
# In hermes-gateway.env or .bashrc
export PATH="$PATH:/path/to/bin"
```

### Docker containers not starting

```bash
# Check Docker is running
systemctl is-active docker

# Check specific container
docker ps -a | grep vllm
```

## GPU Issues (vLLM)

### vLLM not finding GPU

```bash
nvidia-smi
docker ps | grep vllm
```

### OOM errors

Reduce context window or batch size in `vllm/*/docker-compose.yml`.

### Docker port conflicts

```bash
# Check if port 8000 is in use
ss -tlnp | grep 8000

# Modify docker-compose.yml to use a different port
# Then update config.yaml base_url
```

## Daily Operations

### Morning checks

```bash
# 1. Service health
make systemd-status

# 2. Review logs since 06:00
sudo journalctl -u hermes-gateway --since "06:00" -n 100 --no-pager

# 3. Disk usage
df -h
du -sh ~/.hermes/
```

### Disk space cleanup

```bash
# Clean up old journal logs (keep 7 days)
sudo journalctl --vacuum-time=7d

# Check kanban DB size
ls -la ~/.hermes/kanban.db

# Check Hermes profile size
du -sh ~/.hermes/profiles/
```

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| Service not found | Symlink broken | Run `make systemd-link` |
| Connection refused | Gateway not running | `systemctl start hermes-gateway` |
| Agent timeout | `max_turns` too low | Increase in `config.custom.yaml` |
| Empty kanban board | Workspace not running | `systemctl start hermes-workspace` |
| Config not applied | Stale merged config | Run `./hermes/bin/merge-config.sh <profile>` |
| Profile missing | Profile directory empty | Check `~/.hermes/profiles/<profile>/SOUL.md` |
| Tool not found | Not in toolsets list | Add to `toolsets` in `config.custom.yaml` |
| Port conflict | Another service on same port | Change port in `docker-compose.yml` or env |
| Docker not running | Docker daemon stopped | `systemctl start docker` |
| OOM | Memory exhausted | Reduce `max_turns` or `terminal.timeout` |

## Get Help

- Architecture: [docs/architecture.md](architecture.md)
- Setup: [docs/setup-guide.md](setup-guide.md)
- CLI reference: [docs/api.md](api.md)
- Systemd: [systemd/README.md](../systemd/README.md)
- Operations: [docs/runbook.md](runbook.md)
