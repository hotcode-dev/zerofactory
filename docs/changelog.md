# Changelog

All notable changes to the Zero Factory project.

## [Unreleased]

### Added
- `docs/agent-dispatch.md` — comprehensive task-to-agent mapping with decision flowchart, anti-patterns, and parallel assignment matrix
- `systemd/README.md` — detailed systemd service setup guide
- `hermes/bin/merge-config.sh` — config merge helper script
- `hermes/bin/link-skills.sh` — skills linking helper script
- `vllm/qwen3.6-35b-a3b/` — Docker Compose vLLM for Qwen3.6-35B-A3B (NVFP4 + DFlash on DGX Spark)
- `vllm/qwen3.6-27b/` — Docker Compose vLLM for Qwen3.6-27B v4 (GB10)
- `profiles/common/` — base config shared across all agent profiles
- `profiles/*/config.custom.yaml` — profile-specific configuration overrides

### Changed
- vLLM setup migrated from pip to Docker Compose
- Systemd templates use `bash -lc` for proper PATH sourcing
- Agent toolsets expanded: builder and researcher now have kanban, skills, and mcp
- Orchestrator max_turns increased to 120 with 3600s gateway timeout
- Compression tuned: orchestrator uses 0.3 threshold, others use 0.5

### Fixed
- `hermes-link` symlink resolution and idempotency
- Systemd path relations and service dependencies
- Service restart behavior and cleanup

---

## [v0.1.0] — 2026-05-26

### Initial Release

Core 6-agent architecture built on Hermes Agent: Orchestrator, Researcher, Builder, Reviewer, QA, Scribe.

### Added
- `hermes/profiles/common/config.yaml` — Base agent configuration
- `hermes/profiles/*/` — 6 agent profiles with SOUL.md, config.custom.yaml
- `systemd/*.service` — Systemd service units for gateway, dashboard, workspace
- `systemd/*.service.template` — Service unit templates with env substitution
- `ORCHESTRATION.md` — Team structure and workflow details
- `Makefile` — Build automation: hermes-link, systemd-link, systemd-status, systemd-start/stop, systemd-logs
- `README.md` — Project overview and quick start
- `docs/architecture.md` — System design and data flows
- `docs/api.md` — CLI interface and configuration reference
- `docs/setup-guide.md` — Step-by-step setup guide
- `docs/troubleshooting.md` — Common issues and solutions
- `docs/changelog.md` — Version history

### Configuration
- **Model**: `qwen36-fast` via custom provider at `http://spark.ntsd.dev:8000/v1`
- **Compression**: enabled, threshold 0.5, target ratio 0.2
- **Agent max turns**: 60 (all profiles)
- **Gateway timeout**: 1800s
