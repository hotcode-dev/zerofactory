SHELL := /bin/bash

HERMES_SRC := $(CURDIR)/hermes
HERMES_DEST := $(HOME)/.hermes
SYSTEMD_SERVICES := hermes-gateway hermes-dashboard hermes-workspace
SYSTEMD_DIR := $(CURDIR)/systemd

.PHONY: hermes-link systemd-link systemd-enable systemd-disable systemd-start systemd-stop systemd-status
hermes-link:
	@mkdir -p "$(HERMES_DEST)"
	@rm -f "$(HERMES_DEST)/config.yaml"
	@rm -rf "$(HERMES_DEST)/profiles"
	@ln -sfnT "$(HERMES_SRC)/config.yaml" "$(HERMES_DEST)/config.yaml"
	@ln -sfnT "$(HERMES_SRC)/profiles" "$(HERMES_DEST)/profiles"
	@echo "Linked Hermes config and profiles to $(HERMES_DEST)"

systemd-link:
	@sudo ln -sf "$(SYSTEMD_DIR)/hermes-gateway.service" /etc/systemd/system/hermes-gateway.service
	@sudo ln -sf "$(SYSTEMD_DIR)/hermes-dashboard.service" /etc/systemd/system/hermes-dashboard.service
	@sudo ln -sf "$(SYSTEMD_DIR)/hermes-workspace.service" /etc/systemd/system/hermes-workspace.service
	@echo "Linked systemd unit files from $(SYSTEMD_DIR)"

systemd-enable:
	@sudo systemctl enable $(SYSTEMD_SERVICES)
	@echo "Enabled: $(SYSTEMD_SERVICES)"

systemd-disable:
	@sudo systemctl disable $(SYSTEMD_SERVICES)
	@echo "Disabled: $(SYSTEMD_SERVICES)"

systemd-start:
	@sudo systemctl daemon-reload
	@sudo systemctl start $(SYSTEMD_SERVICES)
	@echo "Started: $(SYSTEMD_SERVICES)"

systemd-stop:
	@sudo systemctl stop $(SYSTEMD_SERVICES)
	@$(MAKE) systemd-disable
	@echo "Stopped and disabled: $(SYSTEMD_SERVICES)"

systemd-status:
	@sudo systemctl status $(SYSTEMD_SERVICES)
