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

The config file is symlinked to `hermes/config.yaml`. Changes should appear immediately. If not:

```bash
# Force re-link
make hermes-link
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

- Check `max_turns` in `hermes/config.yaml` (default: 60)
- Review compression settings (default: enabled)
- Check prompt caching is enabled

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

- Terminal timeout defaults to 180s (configurable in `hermes/config.yaml`)
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

## GPU Issues (vLLM)

### vLLM not finding GPU

```bash
nvidia-smi
pip list | grep vllm
```

### OOM errors

Reduce context window or batch size in config.

## General Debugging

### Full service restart

```bash
make systemd-stop
make systemd-start
```

### Reset configuration

```bash
# Stop services
make systemd-stop

# Re-link
make hermes-link
make systemd-link

# Start fresh
make systemd-start
```

## Common Errors

| Error | Cause | Fix |
|-------|-------|-----|
| Service not found | Symlink broken | Run `make systemd-link` |
| Connection refused | Gateway not running | `systemctl start hermes-gateway` |
| Agent timeout | `max_turns` too low | Increase in config.yaml |
| Empty kanban board | Workspace not running | `systemctl start hermes-workspace` |
| Config not applied | Symlink stale | `make hermes-link` |

## Get Help

- Architecture: [docs/architecture.md](architecture.md)
- Setup: [docs/setup-guide.md](setup-guide.md)
- CLI reference: [docs/api.md](api.md)
- Systemd: [systemd/README.md](../systemd/README.md)
