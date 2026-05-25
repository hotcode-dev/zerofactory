SHELL := /bin/bash

HERMES_SRC := $(CURDIR)/hermes
HERMES_DEST := $(HOME)/.hermes

.PHONY: hermes-link
hermes-link:
	@mkdir -p "$(HERMES_DEST)"
	@rm -f "$(HERMES_DEST)/config.yaml"
	@rm -rf "$(HERMES_DEST)/profiles"
	@ln -sfnT "$(HERMES_SRC)/config.yaml" "$(HERMES_DEST)/config.yaml"
	@ln -sfnT "$(HERMES_SRC)/profiles" "$(HERMES_DEST)/profiles"
	@echo "Linked Hermes config and profiles to $(HERMES_DEST)"
