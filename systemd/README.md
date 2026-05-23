# Systemd

To make all the agent service always run 24/7 and automated start we need systemd setup on Linux.

## Installation

1. Link systemd file to /etc/systemd/system

```
sudo ln -sf ./hermes-gateway.service /etc/systemd/system/hermes-gateway.service
sudo ln -sf ./hermes-dashboard.service /etc/systemd/system/hermes-dashboard.service
sudo ln -sf ./hermes-workspace.service /etc/systemd/system/hermes-workspace.service
```

2. Create env file for additional environments

```
touch ~/hermes-gateway.env
touch ~/hermes-dashboard.env
touch ~/hermes-workspace.env
```

3. Start systemd by systemctl

```
sudo systemctl daemon-reload
sudo systemctl enable --now hermes-gateway
sudo systemctl enable --now hermes-dashboard
sudo systemctl enable --now hermes-workspace
```
