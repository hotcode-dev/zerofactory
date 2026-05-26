SHELL := /bin/bash

HERMES_SRC := $(CURDIR)/hermes
HERMES_DEST := $(HOME)/.hermes
SYSTEMD_SERVICES := hermes-gateway hermes-dashboard hermes-workspace
SYSTEMD_DIR := $(CURDIR)/systemd

.PHONY: hermes-link systemd-link systemd-enable systemd-disable systemd-start systemd-stop systemd-status
hermes-link:
	@mkdir -p "$(HERMES_DEST)"
	@rm -rf "$(HERMES_DEST)/profiles"
	@ln -sfnT "$(HERMES_SRC)/profiles" "$(HERMES_DEST)/profiles"
	@echo "Linked Hermes profiles to $(HERMES_DEST)"

systemd-link:
	@sudo ln -sf "$(SYSTEMD_DIR)/hermes-gateway.service" /etc/systemd/system/hermes-gateway.service
	@sudo ln -sf "$(SYSTEMD_DIR)/hermes-dashboard.service" /etc/systemd/system/hermes-dashboard.service
	@sudo ln -sf "$(SYSTEMD_DIR)/hermes-workspace.service" /etc/systemd/system/hermes-workspace.service
	@sudo systemctl daemon-reload
	@echo "Linked systemd unit files from $(SYSTEMD_DIR)"

systemd-enable:
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
		sudo systemctl status "$$svc" --no-pager || echo "WARN: failed to get status for $$svc"; \
	done
