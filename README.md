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

- Paperclip: The multi agent orchestration framework for building controllable agents.
- pi: The main AI agent for background tasks and multi-agent workflows.

## Large language models (LLM)

Only use local LLM and monthly subscription models to avoid high costs from pay-per-use pricing.

- VLLM (OpenAI Compatible)
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

- Paperclip Issues: Built-in paperclip Issues and Projects.
- GitHub Projects and Issues: Use GitHub Issues and Projects.

## Paperclip Multi-Agent Starter

This repository now includes a TypeScript Paperclip-style agent implementation that follows the core principles above.

### Workflow

- Manager agent: creates a compact plan.
- Specialist agents in parallel: researcher, developer, tester, designer.
- Synthesis agent: combines outputs into a single recommendation.
- Hybrid review gate: output is prepared for human review before execution.
