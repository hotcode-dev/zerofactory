# Zero Factory - AI Company Orchestration System

This orchestration system manages a team of AI agents that work in parallel to deliver software products.

## Team Structure

### CEO (Orchestrator)

**Role**: Strategic oversight and workflow management

**SOUL**: `profiles/orchestrator/SOUL.md` — Defines decision-making framework and communication style

**Config**: `profiles/orchestrator/config.custom.yaml`

**Toolsets**: kanban, delegation, cronjob, file, terminal, search_files, web, skills, mcp

**Settings**: max_turns=120, gateway_timeout=3600s, compression threshold=0.3

**Responsibilities**:
- Decompose complex goals into parallelizable work packages
- Dispatch tasks to specialist agents
- Monitor kanban board progress
- Coordinate handoffs between development stages
- Report concise status to human

### Researcher (CTO)

**Role**: Technical research and analysis

**SOUL**: `profiles/researcher/SOUL.md`

**Config**: `profiles/researcher/config.custom.yaml`

**Toolsets**: file, terminal, search_files, web, skills, mcp

**Responsibilities**:
- Research APIs, frameworks, and best practices
- Create technical specifications and architecture documents
- Analyze competitive landscape and trade-offs
- Provide actionable recommendations to Builder

### Builder (Lead Engineer)

**Role**: Code implementation

**SOUL**: `profiles/builder/SOUL.md`

**Config**: `profiles/builder/config.custom.yaml`

**Toolsets**: file, terminal, search_files, web, kanban, skills, mcp

**Responsibilities**:
- Implement features from design specifications
- Write clean, efficient TypeScript (Bun) code
- Write comprehensive tests
- Maintain code quality standards

### Reviewer (Code Reviewer)

**Role**: Code review and quality gatekeeper

**SOUL**: `profiles/reviewer/SOUL.md`

**Config**: `profiles/reviewer/config.custom.yaml`

**Toolsets**: file, terminal, search_files, web, skills, mcp

**Responsibilities**:
- Review code for correctness, style, performance, maintainability
- Assess architecture decisions
- Check for security vulnerabilities
- Verify test coverage

### QA (Quality Assurance)

**Role**: Quality assurance and testing

**SOUL**: `profiles/qa/SOUL.md`

**Config**: `profiles/qa/config.custom.yaml`

**Toolsets**: file, terminal, search_files, web, skills, mcp

**Responsibilities**:
- Create and execute comprehensive test suites
- Verify edge cases and error handling
- Write test plans and run them methodically
- Report bugs with clear reproduction steps

### Scribe (Documentation)

**Role**: Technical documentation

**SOUL**: `profiles/scribe/SOUL.md`

**Config**: `profiles/scribe/config.custom.yaml`

**Toolsets**: file, terminal, search_files, web

**Responsibilities**:
- Create and maintain technical documentation
- Write API docs, READMEs, user guides
- Update changelogs
- Maintain internal knowledge base

## Workflow Pipeline

```
Goal → Researcher (research) → Builder (implement) → Reviewer (review) → QA (test) → Scribe (document) → Done
```

The Orchestrator manages this pipeline, parallelizing where possible:
- Research and Design can happen in parallel
- Multiple features can be implemented simultaneously by different Builder instances
- Review happens after implementation but before QA
- Documentation happens after features are complete

## Core Principles

1. **24/7 Development**: Operate continuously with short iterations and frequent reprioritization
2. **Productivity & Automation**: Build efficient multi-agent workflows
3. **Quality**: Deliver high-quality, maintainable, secure software
4. **Cost Efficiency**: Optimize token usage and keep workflows minimal
5. **Hybrid Review**: Combine human insight with AI review
6. **Single Source of Truth**: One canonical location for shared info. Link, don't copy — edit one, update all.
7. **Minimalist**: Keep everything small, simple, clean, and usable

## Tools & Skills

Each agent has access only to the tools it needs:
- **file**: Read/write project files
- **terminal**: Execute commands and build projects
- **search_files**: Find code patterns and dependencies
- **web**: Browse documentation and resources
- **browser**: Interact with dynamic web content
- **kanban**: Track project progress
- **delegation**: Spawn subagent tasks
- **cronjob**: Schedule recurring tasks

## Configuration

Each agent has its own `SOUL.md` and `config.custom.yaml` in the `profiles/` directory. The base config from `profiles/common/config.yaml` is merged with each profile's overrides to produce the final configuration.

## Making Tasks

Tasks are created by the Orchestrator and assigned to appropriate agents based on their expertise through the kanban board.

## Status Reporting

The Orchestrator provides status reports at key milestones:
- Task assignment and delegation
- Progress updates during development
- Review results and changes
- QA test results
- Documentation updates
