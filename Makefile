SHELL := /bin/bash

HERMES_SRC := $(CURDIR)/hermes
HERMES_DEST := $(HOME)/.hermes
SYSTEMD_SERVICES := hermes-gateway hermes-dashboard hermes-workspace
SYSTEMD_DIR := $(CURDIR)/systemd
MERGE_PROFILE ?= builder

.PHONY: hermes-link config-merge config-merge-all systemd-generate systemd-link systemd-enable systemd-disable systemd-start systemd-stop systemd-status systemd-logs systemd-refresh
hermes-link:
	@mkdir -p "$(HERMES_DEST)"
	@rm -rf "$(HERMES_DEST)/profiles"
	@ln -sfnT "$(HERMES_SRC)/profiles" "$(HERMES_DEST)/profiles"
	@echo "Linked Hermes profiles to $(HERMES_DEST)"

config-merge:
	@./hermes/bin/merge-config.sh "$(MERGE_PROFILE)"
	@echo "Merged config for profile: $(MERGE_PROFILE)"

config-merge-all:
	@./hermes/bin/merge-config.sh all
	@echo "Merged config for all profiles"

systemd-generate:
	@command -v envsubst >/dev/null 2>&1 || (echo "Error: envsubst not found. Install gettext package." && exit 1)
	@env USER="$(USER)" HOME="$(HOME)" envsubst < "$(SYSTEMD_DIR)/hermes-gateway.service.template" > "$(SYSTEMD_DIR)/hermes-gateway.service"
	@env USER="$(USER)" HOME="$(HOME)" envsubst < "$(SYSTEMD_DIR)/hermes-dashboard.service.template" > "$(SYSTEMD_DIR)/hermes-dashboard.service"
	@env USER="$(USER)" HOME="$(HOME)" envsubst < "$(SYSTEMD_DIR)/hermes-workspace.service.template" > "$(SYSTEMD_DIR)/hermes-workspace.service"
	@echo "Generated systemd service files from templates"

systemd-link: systemd-generate
	@sudo ln -sf "$(SYSTEMD_DIR)/hermes-gateway.service" /etc/systemd/system/hermes-gateway.service
	@sudo ln -sf "$(SYSTEMD_DIR)/hermes-dashboard.service" /etc/systemd/system/hermes-dashboard.service
	@sudo ln -sf "$(SYSTEMD_DIR)/hermes-workspace.service" /etc/systemd/system/hermes-workspace.service
	@sudo systemctl daemon-reload
	@echo "Linked systemd unit files from $(SYSTEMD_DIR)"

systemd-enable:
	@sudo systemctl daemon-reload
	@for svc in $(SYSTEMD_SERVICES); do \
		echo "Enabling $$svc"; \
		sudo systemctl enable "$$svc" || echo "WARN: failed to enable $$svc"; \
	done
	@echo "Enabled: $(SYSTEMD_SERVICES)"

systemd-disable:
	@for svc in $(SYSTEMD_SERVICES); do \
		echo "Disabling $$svc"; \
		sudo systemctl disable "$$svc" || echo "WARN: failed to disable $$svc"; \
	done
	@echo "Disabled: $(SYSTEMD_SERVICES)"

systemd-start:
	@sudo systemctl daemon-reload
	@for svc in $(SYSTEMD_SERVICES); do \
		echo "Starting $$svc"; \
		sudo systemctl start "$$svc" || echo "WARN: failed to start $$svc"; \
	done
	@echo "Started: $(SYSTEMD_SERVICES)"

systemd-stop:
	@for svc in $(SYSTEMD_SERVICES); do \
		echo "Stopping $$svc"; \
		sudo systemctl stop "$$svc" || echo "WARN: failed to stop $$svc"; \
	done
	@$(MAKE) systemd-disable
	@echo "Stopped and disabled: $(SYSTEMD_SERVICES)"

systemd-status:
	@for svc in $(SYSTEMD_SERVICES); do \
		echo "==== $$svc ===="; \
		sudo systemctl status "$$svc" --no-pager -l || true; \
		state="$$(sudo systemctl is-active "$$svc" 2>/dev/null || true)"; \
		if [[ -z "$$state" ]]; then state="unknown"; fi; \
		echo "State: $$state"; \
		echo; \
	done

systemd-logs:
	@for svc in $(SYSTEMD_SERVICES); do \
		echo "==== $$svc logs ===="; \
		sudo journalctl -u "$$svc" -n 120 --no-pager -l || true; \
		echo; \
	done

systemd-refresh:
	@sudo systemctl daemon-reload
	@sudo systemctl reset-failed $(SYSTEMD_SERVICES) || true
	@$(MAKE) systemd-link
	@$(MAKE) systemd-enable
	@$(MAKE) systemd-start
	@echo "Refreshed and restarted: $(SYSTEMD_SERVICES)"
