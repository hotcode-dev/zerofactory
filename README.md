# Zero Factory

A 24/7 AI multi-agent orchestration system built as a native **Hermes Agent Plugin**. Three specialized agents form an autonomous software factory — from goal decomposition to implementation, testing, and continuous code review.

```mermaid
graph TD
    classDef kanban fill:#f9d0c4,stroke:#333,stroke-width:2px,color:#000;
    
    User([User / Goal]) --> Triage[Kanban: Triage]:::kanban
    Triage -->|Auto-decomposes| Todo[Kanban: Todo]:::kanban
    Todo -->|Dispatcher Assigns & Creates Worktree| Ready[Kanban: Ready]:::kanban
    Ready -->|Autonomous Pickup| Running[Kanban: Running]:::kanban
    
    subgraph Zero Factory Agents
        Running --> Builder["zf-builder (Code & Tests)"]
    end
    
    Builder -->|Work Done| PR[Dispatcher Pushes & Opens PR]
    PR --> Reviewer["zf-reviewer (3-Round Polish)"]
    Reviewer -->|Changes Requested| Ready
    Reviewer -->|Approved| Blocked[Kanban: Blocked / Human Review]:::kanban
    Blocked -->|Human Merges PR| Done[Kanban: Done]:::kanban
```

---

## Core Principles

| Pillar | Description |
|---|---|
| **24/7 Autonomous Factory** | Continuous agile iterations with rolling handoffs and parallel execution. |
| **Plugin-First Architecture** | Self-contained Hermes plugin with zero external Node.js or `hermes-profile-manager` dependencies. |
| **Isolated Profiles** | Profiles are cleanly namespaced (`zf-orchestrator`, `zf-builder`, `zf-reviewer`) in `~/.hermes/profiles/` and never clash with personal user profiles. |
| **Isolated Git Worktrees** | Every task runs in its own dedicated Git worktree (`~/git/<repo>-worktrees/<task_id>`). Agents never touch `main` directly. |
| **Thematic Continuous Review** | Layered code review capping at 3 focused rounds (Correctness → Performance → Refactoring) before handing off to human merge. |
| **Durable Kanban Storage** | Embedded SQLite backend with Write-Ahead Logging (`WAL` mode) and a glassmorphic web dashboard UI. |

---

## The Specialist Team

Zero Factory automatically provisions and maintains three specialized agent profiles:

| Profile | Role | Core Responsibilities |
|---|---|---|
| **`zf-orchestrator`** | Pipeline Overseer | Manages the Kanban board, oversees goal decomposition, manages handoffs, and escalates blockers to human review. |
| **`zf-builder`** | Senior Software Engineer | Writes clean code and tests, operates inside automated Git worktrees, and ships features rapidly. |
| **`zf-reviewer`** | Quality Gatekeeper | Conducts thematic, capped 3-round code reviews on GitHub Pull Requests, verifying test adequacy, performance, and architecture. |

---

## Quick Start & Installation

### 1. Install Plugin into Hermes
Install directly through Hermes plugin management:
```bash
hermes plugins install hotcode-dev/zerofactory
```
*(Alternatively, clone this repository directly into `~/.hermes/plugins/zerofactory`)*

### 2. Verify or Pre-Create Profiles
The plugin automatically bootstraps the required profiles on first run, inheriting your default LLM settings from `~/.hermes/config.yaml`. You can also manually inspect or create them anytime:
```bash
hermes zerofactory setup
```

### 3. Open the Kanban Dashboard
Start the Hermes Gateway or dashboard:
```bash
hermes dashboard
```
Open **`http://localhost:9119/zerofactory`** in your browser to view your boards, drag-and-drop tasks, and track agent progress.

---

## CLI Management

Zero Factory provides rich CLI commands under `hermes zerofactory`:

```bash
# Profile management
hermes zerofactory setup                          # Check or initialize zf-* profiles
hermes zerofactory sync-profiles                  # Update system prompts from plugin templates

# Task management
hermes zerofactory list                           # List all tasks
hermes zerofactory list --status running          # Filter tasks by status
hermes zerofactory list --assignee zf-builder     # Filter tasks by assignee
hermes zerofactory create "Implement Feature X"   # Create a new ticket
hermes zerofactory move <task_id> ready           # Transition task status
hermes zerofactory block <task_id> --reason "..." # Block a task
hermes zerofactory comment <task_id> "Note..."    # Post a comment to a ticket

# Board operations
hermes zerofactory board list                     # List all project boards
hermes zerofactory board create <slug> "<name>"   # Add a new codebase board

# Dispatcher & Background Crons
hermes zerofactory dispatch                       # Trigger an immediate dispatch cycle
hermes zerofactory check-stuck                    # Audit long-running or hung worker processes
hermes zerofactory cron list                      # View active periodic health & scanner jobs
hermes zerofactory cron sync                      # Sync cron jobs with Hermes scheduler
hermes zerofactory cron run <job_id>              # Run a cron scanner immediately
```

---

## Task Lifecycle & Workflow

```text
       [Triage]
          │
          ▼
        [Todo]  ◄─────── (Changes Requested by Reviewer)
          │
     (Human Approves)
          │
          ▼
        [Ready]
          │
   (Dispatcher assigns isolated Git worktree & spawns zf-builder)
          │
          ▼
       [Running]
          │
   (zf-builder finishes; Dispatcher creates GitHub PR)
          │
          ▼
       [Ready]  (Assigned to zf-reviewer)
          │
   (zf-reviewer inspects PR diff & commits)
          │
       Approved?
       ├── Yes ──► [Blocked] (Reason: Human Review & Merge)
       │                         │
       │                  (Merged on GitHub)
       │                         │
       │                         ▼
       │                      [Done]
       │
       └── Changes Requested ──► [Todo] (Re-assigned to zf-builder)
```

1. **Goal Ingestion (`Triage`)**: Submit a high-level goal or feature request via CLI or web UI.
2. **Decomposition (`Todo`)**: The `kanban_decomposer` breaks the goal down into granular sub-tasks.
3. **Dispatch & Worktree Provisioning (`Ready`)**: The dispatcher validates dependencies, assigns `zf-builder`, and creates an isolated Git worktree.
4. **Autonomous Execution (`Running`)**: `zf-builder` works in its isolated worktree, writing code and automated tests.
5. **PR Creation & Review (`Blocked / Reviewer`)**: When `zf-builder` finishes, the dispatcher commits the branch, opens a GitHub Pull Request, and routes it to `zf-reviewer`.
6. **Iterative Polish (Rounds 1-3)**:
   - **Round 1**: Testing, correctness, and edge-case handling.
   - **Round 2**: Performance, memory, and algorithmic efficiency.
   - **Round 3**: Clean code, DRY principles, and architectural polish.
   - **Round 4+**: Approved for human review.
7. **Human Merge (`Done`)**: The human merges the PR on GitHub, and the dispatcher automatically marks the ticket as `Done`.

---

## Built-in Automation & Token-Efficient Cron Architecture

Zero Factory is architected to drastically minimize LLM token consumption (up to 95% token savings) across periodic automation cycles using Hermes Agent's **No-Agent Mode (`no_agent: true`)**, **Wake-Gate Change Detection (`{"wakeAgent": false}`)**, and **Chained LLM Jobs (`context_from`)**:

- **`zero-factory-task-queue-check`** (every 120m, **0 Tokens**):
  - Operates in Hermes **No-Agent Mode** via `scripts/zf_queue_watchdog.py`.
  - Audits running workers, reaps stuck subprocesses, and runs `run_dispatch_cycle()`.
  - When the queue is healthy, emits `{"wakeAgent": false}` to silently exit without invoking any LLM.
  - When bottlenecks occur, outputs a human-readable alert delivered to the operator.
- **`zero-factory-daily-report`** (`0 9 * * *`, **Single-Turn Synthesis**):
  - Pre-computes 24h velocity, cycle time, blockers, and column distributions via `scripts/zf_daily_stats.py`.
  - Automatically chains upstream output from `zero-factory-task-queue-check` via `context_from`.
  - Pre-loads all metrics directly into prompt context, eliminating 15+ tool queries and completing in a single turn.
- **`zero-factory-improvement-scanner-{board_slug}`** (every 60m per board, **0 Tokens on Idle**):
  - Runs inside the repository workdir with wake-gate change detection via `scripts/zf_scanner_gate.py`.
  - Compares Git HEAD and working tree changes against `~/.hermes/scanner_state.json`.
  - Suppresses unchanged runs with `{"wakeAgent": false}` (0 LLM tokens).
  - When new commits or changes exist, pre-digests git log, diffstat, truncated diffs, and existing open board tasks, waking the LLM agent to file at most 1 high-priority task.

---

## Repository Structure

```text
zerofactory/
├── plugin.yaml                  # Hermes plugin metadata
├── __init__.py                  # Plugin registration & CLI interface
├── dispatcher.py                # Autonomous dispatch engine & worktree manager
├── builtin_cron.py              # Periodic scanner & reporting engine
├── profile_manager.py           # Auto-provisioning for zf-* profiles & scripts
├── test_plugin.py               # Comprehensive automated test suite (25 tests)
├── scripts/                     # No-Agent Mode scripts & LLM context pre-processors
│   ├── zf_queue_watchdog.py     # Autonomous worker reaper & queue monitor (0 tokens)
│   ├── zf_scanner_gate.py       # Codebase diff pre-screen & wake-gate
│   └── zf_daily_stats.py        # Deterministic 24h metrics & velocity calculator
├── dashboard/                   # Embedded web dashboard UI (/zerofactory)
│   ├── manifest.json            # Gateway route declaration
│   ├── plugin_api.py            # FastAPI REST backend
│   └── dist/
│       ├── index.js             # React Kanban UI
│       └── style.css            # Dark glassmorphic theme
├── skills/
│   └── zerofactory-orchestration/  # Multi-agent coordination skill
└── templates/                   # Version-controlled profile templates
    ├── zf-orchestrator/
    ├── zf-builder/
    └── zf-reviewer/
```

---

## Testing

Run the automated test suite against your local Hermes environment:
```bash
python3 test_plugin.py
```

---

## License

See [LICENSE](LICENSE).
