---
name: zerofactory-orchestration
category: architecture
description: Set up specialized AI agent teams with role-specific toolsets, identities, and continuous agile workflows.
---

# Multi-Agent Orchestration with Zero Factory

Zero Factory manages a team of specialized AI agents that operate in a continuous 24/7 agile loop, each with distinct identity, tools, and responsibilities.

## Team Roles

Zero Factory automatically provisions and maintains the following specialist profiles in `~/.hermes/profiles/`:

| Profile | Role | Identity / Responsibilities |
| :--- | :--- | :--- |
| **`zf-orchestrator`** | Pipeline Overseer | Master coordinator — manages the Kanban board, oversees goal decomposition, manages handoffs, and escalates blockers to human review. |
| **`zf-builder`** | Senior Software Engineer | Writes clean code and tests, operates inside automated Git worktrees, and ships features rapidly. |
| **`zf-reviewer`** | Quality Gatekeeper | Conducts thematic, capped 3-round code reviews on GitHub Pull Requests, verifying test adequacy, performance, and architecture. |

## Profile Management

Profiles are managed natively by the **Zero Factory plugin** (`zerofactory`):
- Run `hermes zerofactory setup` to inspect or create the profiles.
- Run `hermes zerofactory sync-profiles` to synchronize system prompts from plugin templates.
- Profiles live in `~/.hermes/profiles/zf-*/` and inherit your default LLM settings.

## Pipeline Architecture

The workflow is managed via the **Zero Factory Kanban** system with explicit Human-in-the-Loop (HITL) gates:

1. **Goal & Triage**: User or cron job drops a goal in `Triage`. The `kanban_decomposer` automatically breaks the goal into child tasks and routes them to specialist agents.
2. **Plan Review (HITL)**: The auto-generated child tasks enter `Todo`. A human reviews the plan, edits if needed, and approves tasks to `Ready`.
3. **Ready Queue**: Approved tasks whose dependencies are met are automatically promoted to `Ready`.
4. **Task Delegation**: The kanban dispatcher automatically provisions isolated Git worktrees and spawns `zf-builder`, moving tasks to `Running`.
5. **PR Creation & Review**: When `zf-builder` completes the work, the dispatcher commits the branch, opens a GitHub Pull Request, and routes the ticket to `zf-reviewer`.
6. **Iterative Polish (up to 3 rounds)**: `zf-reviewer` examines the PR diff and either requests changes (routed back to `zf-builder`) or approves the PR.
7. **Human Merge (HITL)**: Approved tasks move to `Blocked` for final human review. Once the PR is merged on GitHub, the dispatcher marks the task as `Done`.

## Best Practices
- **Never commit directly to `main`**: All agent development happens in isolated Git worktrees (`~/git/<repo>-worktrees/<task_id>`).
- **Use `hermes zerofactory` CLI**: Inspect tasks, trigger manual dispatch cycles, and check queue health anytime.
