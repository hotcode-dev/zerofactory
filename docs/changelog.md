# Changelog

All notable changes to the Zero Factory project.

## [Unreleased]

### Added
- 6-agent orchestration system with specialized roles
- systemd integration for 24/7 operation
- Kanban board for task management
- Compression and prompt caching for cost efficiency
- Personalities support (kawaii, technical, creative, etc.)
- Tool-use enforcement to prevent redundant calls

### Changed
- Migrated from LangGraph to Hermes Agent
- Improved systemd service integration
- Enhanced profile configurations

### Fixed
- Systemd source .bashrc for PATH setup
- hermes-link symlink resolution
- Systemd path relations

## [v0.1.0] - 2026-05-26

### Initial Release

- Core 6-agent architecture (orchestrator, researcher, builder, reviewer, qa, scribe)
- Hermes Agent integration
- Systemd service files (gateway, dashboard, workspace)
- Makefile with management shortcuts
- CONVENTIONS.md with coding standards
- ORCHESTRATION.md with team structure
- Basic README.md

### Added
- `hermes/config.yaml` — Main configuration
- `hermes/profiles/*/` — Agent profiles with SOUL.md, system_prompt.txt, config.yaml
- `systemd/*.service` — Systemd service units
- `systemd/*.service.template` — Service templates
- `CONVENTIONS.md` — Shared conventions
- `ORCHESTRATION.md` — Team structure documentation
- `Makefile` — Build automation

### Configuration
- Model: qwen36-fast via custom provider
- Provider: http://spark.ntsd.dev:8000/v1
- Compression: enabled (threshold 0.5, target ratio 0.2)
- Agent max turns: 60
- Gateway timeout: 1800s
