SHELL := /bin/bash

HERMES_SRC := $(CURDIR)
HERMES_DEST := $(HOME)/.hermes

.PHONY: hermes-link merge-all config-merge jobs-merge soul-merge skills-link
hermes-link:
	@mkdir -p "$(HERMES_DEST)"
	@rm -rf "$(HERMES_DEST)/profiles"
	@ln -sfnT "$(HERMES_SRC)/profiles" "$(HERMES_DEST)/profiles"
	@rm -rf "$(HERMES_DEST)/plugins"
	@ln -sfnT "$(HERMES_SRC)/plugins" "$(HERMES_DEST)/plugins"
	@echo "Linked Hermes profiles and plugins to $(HERMES_DEST)"

merge-all: config-merge jobs-merge soul-merge skills-link
	@echo "Merged config, jobs, and SOUL, and linked skills for all profiles"

config-merge:
	@./bin/merge-config.sh
	@echo "Merged config for all profiles"

jobs-merge:
	@./bin/merge-jobs.sh
	@echo "Merged jobs for all profiles"

soul-merge:
	@./bin/merge-soul.sh
	@echo "Merged SOUL for all profiles"

skills-link:
	@./bin/link-skills.sh
	@echo "Linked common skills to all profiles"
