# Zero Factory

A 24/7 AI multi-agent orchestration setup that works in parallel. Include manager, researcher, developer, tester, designer, etc., agents.

## Core Principles

This AI setup focuses on these pillars:

- 24/7 agile non-stop development cycle: Operate in continuous short iterations with frequent reprioritization, quick feedback, rolling handoffs, parallel execution, automated checks, and immediate follow-up on blockers.
- Productivity & automation: Build efficient multi-agent workflows and automate routine, low-priority tasks.
- Quality & performance: Deliver high-quality, maintainable code, high performance.
- Reliability & security: Prioritize stable, dependable, and secure software outcomes.
- Cost efficiency: Reduce cost by optimizing token usage and keeping workflows to as few steps as possible.
- Hybrid Review: Combine human insight with AI-assisted review to validate plans early and review code thoroughly for better outcomes.
- Minimal and reviewable output: Keep plans and changes small, clear, and scoped so humans can review quickly and confidently.

## Agent & Framework

Use multiple AI agents for different purposes.

- Paperclip: The multi agent orchestration framework for building controllable agents.
- [Hermes Agent](https://hermes-agent.nousresearch.com/): The main AI agent for background tasks and multi-agent workflows.

## Large language models (LLM)

Only use local LLM and monthly subscription models to avoid high costs from pay-per-use pricing.

- VLLM (OpenAI Compatible) [Qwen3.6-27B-AEON](https://github.com/AEON-7/Qwen3.6-27B-AEON-Ultimate-Uncensored-DFlash)
- Github Copilot
- Gemini (Google One)

## Programming Languages

The AI will only generate code in these languages because I am most familiar with them, which helps me review the code more effectively.

- TypeScript: For frontend development (web, mobile, desktop), CLI tools, and Bun backend servers.
- Go: For high-performance, concurrent backend servers and CLI tools.

## Tools

These are CLI and MCP tools we can install to help AI agents take actions, access resources, and maintain context.

## Project Management

- Paperclip Issues: Built-in paperclip Issues and Projects.
- GitHub Projects and Issues: Use GitHub Issues and Projects.
