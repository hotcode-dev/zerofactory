# Zero Factory - AI Company Orchestration System

This orchestration system manages a team of AI agents that work in parallel to deliver software products.

## Team Structure

### CEO (Orchestrator)
**Role**: Strategic oversight and workflow management
**SOUL**: Defines decision-making framework and communication style
**Config**: Toolsets: kanban, delegation, cronjob
**Responsibilities**:
- Decompose complex goals into parallelizable work packages
- Dispatch tasks to specialist agents
- Monitor kanban board progress
- Coordinate handoffs between development stages
- Report concise status to human

### CTO (Researcher)
**Role**: Technical research and analysis
**SOUL**: Defines research methodology and output format
**Config**: Toolsets: web, browser, file, search_files
**Responsibilities**:
- Research APIs, frameworks, and best practices
- Explore multiple solutions and compare trade-offs
- Create comprehensive research reports
- Analyze competitive landscape

### Lead Engineer (Builder)
**Role**: Code implementation
**SOUL**: Defines coding standards and development workflow
**Config**: Toolsets: file, terminal, search_files, web
**Responsibilities**:
- Implement features from design specifications
- Write clean, efficient TypeScript and Go code
- Write comprehensive tests
- Maintain code quality standards

### QA Engineer
**Role**: Quality assurance and testing
**SOUL**: Defines testing methodology and reporting format
**Config**: Toolsets: file, terminal, search_files, web
**Responsibilities**:
- Create and execute comprehensive test suites
- Verify edge cases and error handling
- Write test plans and run them methodically
- Report bugs with clear reproduction steps

### Reviewer
**Role**: Code review and quality gatekeeper
**SOUL**: Defines review process and feedback format
**Config**: Toolsets: file, terminal, search_files, web
**Responsibilities**:
- Review code for correctness, style, performance, maintainability
- Assess architecture decisions
- Check for security vulnerabilities
- Verify test coverage

### Scribe
**Role**: Technical documentation
**SOUL**: Defines writing standards and documentation categories
**Config**: Toolsets: file, terminal, search_files, web
**Responsibilities**:
- Create and maintain technical documentation
- Write API docs, READMEs, user guides
- Update changelogs
- Maintain internal knowledge base

## Workflow Pipeline

```
Goal → Researcher (analyze) → Architect (design) → Builder (implement) → 
Reviewer (review) → QA (test) → Scribe (document) → Deploy
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

Each agent has its own `SOUL.md` and `config.yaml` in the `profiles/` directory.

## Making Tasks

Tasks are created by the Orchestrator and assigned to appropriate agents based on their expertise.

## Status Reporting

The Orchestrator provides status reports at key milestones:
- Task assignment and delegation
- Progress updates during development
- Review results and changes
- QA test results
- Documentation updates
