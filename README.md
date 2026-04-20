# Zero Factory

An AI multi-agent workflow setup that works in parallel. Include manager, researcher, developer, tester, designer, etc., agents.

## Core Principles

This AI setup focuses on these pillars:

- Productivity & automation: Build efficient multi-agent workflows and automate routine, low-priority tasks.
- Quality & performance: Deliver high-quality, maintainable code, high performance.
- Reliability & security: Prioritize stable, dependable, and secure software outcomes.
- Cost efficiency: Reduce cost by optimizing token usage and keeping workflows to as few steps as possible.
- Hybrid Review: Combine human insight with AI-assisted review to validate plans early and review code thoroughly for better outcomes.

## Agent & Framework

Use multiple AI agents for different purposes.

- LangGraph: The multi agent orchestration framework for building controllable agents.
- pi: The main AI agent for background tasks and multi-agent workflows.

## Large language models (LLM)

Only use monthly subscription models to avoid high costs from pay-per-use pricing.

- Gemini (Google One)
- Github Copilot

## Programming Languages

The AI will only generate code in these languages because I am most familiar with them, which helps me review the code more effectively.

- TypeScript: For frontend development (web, mobile, desktop), CLI tools, and Bun backend servers.
- Go: For high-performance, concurrent backend servers and CLI tools.

## Tools

These are CLI and MCP tools we can install to help AI agents take actions, access resources, and maintain context.

### GitHub CLI (gh)

GitHub CLI helps manage GitHub issues, pull requests, and projects. It also enables AI agents to check pull requests and submit reviews.

### Ripgrep (rg)

Ripgrep recursively searches directories for a regex pattern while respecting your gitignore

## Project Management

- GitHub Projects and Issues: Use GitHub Issues and Projects.

## LangGraph.js Multi-Agent Starter

This repository now includes a TypeScript LangGraph.js agent implementation that follows the core principles above.

### Workflow

- Manager agent: creates a compact plan.
- Specialist agents in parallel: researcher, developer, tester, designer.
- Synthesis agent: combines outputs into a single recommendation.
- Hybrid review gate: output is prepared for human review before execution.

### Files

- `src/principles.ts`: central principle definitions and base behavior prompt.
- `src/agent.ts`: LangGraph state, nodes, routing, and `runZeroFactory` runner.
- `src/index.ts`: CLI entrypoint.

### Setup

```bash
npm install
cp .env.example .env
```

Authenticate `pi` on your machine before running.

Per-agent Pi settings are now loaded from role-specific files:

- `src/agents/manager/settings.json`
- `src/agents/researcher/settings.json`
- `src/agents/developer/settings.json`
- `src/agents/tester/settings.json`
- `src/agents/designer/settings.json`
- `src/agents/synthesis/settings.json`

Each `settings.json` supports Pi's documented settings keys such as:

- `defaultModel`: primary model for that agent
- `enabledModels`: model list available for cycling

At runtime, each graph node is executed with its own config by setting `PI_CODING_AGENT_DIR` to that role's directory before calling `pi run`.

### Run

```bash
npm run dev -- "Design a TypeScript CLI architecture for issue triage"
```

### Build

```bash
npm run build
```
