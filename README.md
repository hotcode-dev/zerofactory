# Zero Factory

A 24/7 AI multi-agent orchestration setup that works in parallel. Include project manager, researcher, coder, tester, designer, reviewer, etc., agents.

## Core Principles

This AI setup focuses on these pillars:

- 24/7 agile non-stop development cycle: Operate in continuous short iterations with frequent reprioritization, quick feedback, rolling handoffs, parallel execution, automated checks, and immediate follow-up on blockers.
- Productivity & automation: Build efficient multi-agent workflows and automate routine.
- Quality, performance, reliability & security: Deliver high-quality, maintainable, stable, dependable, secure, and high-performance software outcomes.
- Cost efficiency: Reduce cost by optimizing token usage and keeping workflows to as few steps as possible, disable all skills/plugins by default then ask human to turn it on or create if need, specific purpose agent only have skills relate to them.
- Hybrid Review: Combine human insight with AI-assisted review to validate plans early and review code thoroughly for better outcomes.
- Minimalist: Keep everything as small, simple, clean, and usable as possible.

## AI Agent & Workspace

- [Hermes Agent](https://hermes-agent.nousresearch.com/): Primary orchestrator for long-running background tasks and coordination across specialist agents.
- [Hermes Workspace](https://github.com/outsourc-e/hermes-workspace): Native web workspace for Hermes Agent — chat, terminal, memory, skills, inspector.

## Project Structure

```
zerofactory/
├── Makefile
├── README.md
├── hermes/
│   ├── config.yaml
│   └── profiles/
│       └── profile/
│           ├── config.yaml
│           └── SOUL.md
└── vllm/
    └── qwen3.6-35b-a3b/
        └── docker-compose.yml
```

## Large language models (LLM)

Only use local LLM and monthly subscription models to avoid high costs from pay-per-use pricing.

- VLLM (OpenAI Compatible) [Qwen3.6-27B-AEON](https://github.com/AEON-7/Qwen3.6-27B-AEON-Ultimate-Uncensored-DFlash)
- Github Copilot, Gemini (Google One), etc.

### Model setup

- Use OpenAI Responses API: instead of Chat Completions use the new Responses API.
- Always use 0 temperature: Always be logical, This is for the fastest agent response and no feeling need.
- Maximum concurrency: Control the maximum concurrency of the model and agent call to prevent out-of-memory error or GPU deadlock based on the hardware limit, also to prevent timeout error when the task is on the queue.

## Programming Languages

The AI will only generate code in these languages, which helps me review the code more effectively.

- TypeScript: For frontend development (web, mobile, desktop), CLI tools, and Bun backend servers.
- Go: For high-performance, concurrent backend servers and CLI tools.

## Tools

CLI and MCP tools we can install to help AI agents take actions, access resources, and maintain context.
Agent will only access the tools and skill that it need for the role.

## Project Management

- Hermes Workspace Built-in: use Hermes Workspace built-in Kanban board.
- GitHub Projects and Issues: Use GitHub Issues and Projects.
