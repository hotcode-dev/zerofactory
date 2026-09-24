# Zero Factory

A 24/7 AI multi-agent orchestration system built as a native **Hermes Agent Plugin**. Three specialized agents form an autonomous software factory — from goal decomposition to implementation, testing, and continuous code review.

```mermaid
graph TD
    classDef kanban fill:#f9d0c4,stroke:#333,stroke-width:2px,color:#000;
    
    User([User / Goal]) --> Triage[Kanban: Triage]:::kanban
    Triage -->|zf-orchestrator decomposes| Todo[Kanban: Todo]:::kanban
    Scanner["zf-orchestrator (Improvement Scanner)"] -->|Scans Project & Creates Task| Todo
    Todo -->|Dispatcher Assigns, Provisions Worktree & Dispatches| Running[Kanban: Running]:::kanban
    
    subgraph Zero Factory Agents
        Running --> Builder["zf-builder (Code & Tests)"]
        Running --> Reviewer["zf-reviewer (Review Rounds)"]
    end
    
    Builder -->|Work Done| PR[Dispatcher Pushes & Opens PR]
    PR --> Reviewer
    Reviewer -->|Changes Requested| Builder
    Reviewer -->|Approved| Blocked[Kanban: Blocked / Human Action]:::kanban
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
hermes zerofactory move <task_id> running          # Transition task status
hermes zerofactory block <task_id> --reason "..." # Block a task
hermes zerofactory comment <task_id> "Note..."    # Post a comment to a ticket

# Board operations
hermes zerofactory board list                     # List all project boards
hermes zerofactory board create <git_url>         # Add a new codebase board from Remote Git URL
hermes zerofactory board delete <slug>            # Delete a board and clear its scanner job

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
   (Dispatcher provisions worktree & launches zf-builder)
          │
          ▼
       [Running] (zf-builder: Code & Tests)
          │
   (zf-builder finishes; Dispatcher creates GitHub PR)
          │
       [Running] (zf-reviewer: Multi-round Review)
          │
       Approved?
       ├── Yes ──► [Blocked] (Human Action: Review & Merge)
       │                         │
       │                  (Merged on GitHub)
       │                         │
       │                         ▼
       │                      [Done]
       │
       └── Changes Requested ──► [Todo] (Re-assigned to zf-builder)
```

1. **Goal Ingestion (`Triage`)**: Submit a high-level goal or feature request via CLI or web UI.
2. **Decomposition & Codebase Scanning (`Todo`)**: `zf-orchestrator` breaks `Triage` goals down into atomic sub-tasks, and runs periodic codebase scans to directly file actionable `Todo` improvement tasks for `zf-builder`.
3. **Autonomous Execution (`Running`)**: The dispatcher validates dependencies, provisions an isolated Git worktree, and launches `zf-builder` to write code and tests.
   - **Global LLM capacity**: Settings → Global Max Concurrent LLM Workers caps running task agents and in-flight improvement scanners across all boards. For example, with a cap of 3, two running tasks on one board and one on another leave no slot for further tasks or scanners. The per-board running limits and Max Active Tasks (task WIP) apply independently. No-Agent queue checks do not consume LLM capacity.
4. **PR Creation & Agent Review (`Running`)**: When `zf-builder` finishes, the dispatcher commits the branch, opens a GitHub Pull Request, and routes it to `zf-reviewer` in `Running` across 3 continuous review rounds (Correctness ➔ Performance ➔ Clean Code).
5. **Human Action & Merge (`Blocked`)**: Approved PRs move to `Blocked` awaiting human merge. Any crashed workers or merge conflict escalations also move to `Blocked` for operator review.
6. **Completion (`Done`)**: The human merges the PR on GitHub, and the dispatcher automatically marks the ticket as `Done` and prunes the worktree.

---

## Session Lifecycle & Architecture

Zero Factory implements a **Session-per-Handoff (Stateless Workers, Stateful Substrate)** model rather than maintaining a single monolithic session per task or per agent.

### How Sessions Work Across Handoffs

1. **Initial Implementation (`zf-builder`)**:
   - The dispatcher provisions an isolated Git worktree and executes `hermes -p zf-builder --yolo --cli --accept-hooks chat -q <prompt>`.
   - Hermes initializes a dedicated session recorded in `~/.hermes/profiles/zf-builder/state.db` and tracked in task metadata (`metadata["sessions"]`).
2. **Review Handoff (`zf-reviewer`)**:
   - When implementation finishes, the dispatcher terminates the builder process (`SIGTERM`/`SIGKILL`), commits the branch, opens a GitHub Pull Request, and routes the ticket to `zf-reviewer`.
   - The dispatcher pre-digests the git diff and commit log in Python, then launches `hermes -p zf-reviewer ...`, creating a **brand new session** under `~/.hermes/profiles/zf-reviewer/state.db`.
3. **Changes Requested (`zf-reviewer` ➔ `zf-builder`)**:
   - When the reviewer requests changes on GitHub, the dispatcher imports comments into the SQLite `task_comments` table.
   - The reviewer worker is stopped, and the ticket routes back to `zf-builder`.
   - A **brand new session** is spawned for `zf-builder` with an injected prompt block (`🚨 CRITICAL: PULL REQUEST REVIEW COMMENTS TO ADDRESS`), allowing the builder to immediately address the feedback on the live worktree without the cognitive overhead of previous turns.

### Architectural Trade-offs: Session-per-Handoff vs. Single-Session-per-Agent-per-Task

| Dimension | **Zero Factory (Session per Handoff)** | **Single Session per Agent per Task (Resumed)** |
|---|---|---|
| **Context Window Size** | **Compact & predictable** (typically 3k–15k tokens per phase) | **Grows monotonically** (40k–100k+ tokens across review rounds) |
| **Token Cost per Review Round** | **Low & Flat** (starts clean with only review comments) | **Compounding** (re-reads entire implementation history on every turn) |
| **Context Drift & "Ghost Code"** | **Lowest** (Agent inspects current disk files in worktree) | **Higher** (Agent risks hallucinating code from early in-memory turns rather than disk) |
| **Fault Tolerance & Poisoned Loops** | **High** (Terminated workers discard bad hallucination loops) | **Lower** (Resumed session retains prior confusion or failed debugging traces) |
| **Reviewer Diff Clarity** | **High** (Reviewer receives clean, pre-digested current delta) | **Lower** (Reviewer history mixes original diff with updated diffs) |
| **Role & Profile Isolation** | **Strict** (Builder & Reviewer maintain isolated profiles, tools, and DBs) | **Strict** (Maintains role separation, but with accumulated history) |
| **Working Memory Continuity** | Persisted via **Native `kanban.db` Memory** (conventions, gotchas, decisions pre-digested into prompt) | ✅ Full conversation memory (remembers reasoning, discarded ideas, test nuances) |

### Stateless Workers, Stateful Substrate

Zero Factory intentionally externalizes durable state into **Git worktrees**, **GitHub PR review comments**, and **Kanban SQLite storage** instead of accumulating conversation memory. This guarantees deterministic handoffs, avoids token exhaustion, and eliminates "Lost in the Middle" attention degradation across iterative multi-round code reviews.

---

## Native `kanban.db` Memory & Agents Dashboard

Zero Factory features **Native `kanban.db` Memory** — a durable, local SQLite repository knowledge substrate that allows specialist agents and developers to persist conventions, gotchas, architecture decisions, and rejected paths scoped per board.

### Why Native `kanban.db` Memory?
1. **Zero External Infrastructure**: Stored directly in `kanban.db` via SQLite table `board_memories` with cascading cleanup on board deletion.
2. **Deterministic Pre-Digest**: Automatically pre-digested by `dispatcher.py` into spawned worker prompts (`zf-builder`, `zf-reviewer`, `zf-orchestrator`), ensuring agents never repeat past mistakes or violate repository conventions.
3. **Structured Taxonomy**:
   - `convention`: Coding rules, file formats, test execution expectations.
   - `gotcha`: Concurrency pitfalls, fragile mocks, subtle edge cases.
   - `decision`: Architectural and design choices that govern future work.
   - `rejected_path`: Approaches that were tried and discarded, preventing wasteful re-attempts.
   - `general`: General repository knowledge.

### Integrated "Agents" Dashboard
The dashboard navigation tab has evolved from `AI Sessions` to **`Agents`**:
- **3 Specialist Agent Cards**: Real-time status (`🟢 Active` vs `⚪ Idle`), live execution activity, active session model & duration, and direct links to active Kanban tasks.
- **Sub-Tab Switcher**: Seamlessly switch between `💬 AI Sessions` (full execution history & chat resume links) and `🧠 Repository Memory` (knowledge cards with search, category filtering, and modal CRUD).

### Memory CLI Commands
```bash
# List repository memories for a board
hermes zerofactory memory list --board <slug> [--category <cat>] [-q <query>]

# Record a new repository memory
hermes zerofactory memory add --board <slug> "<content>" --category convention --tags "test,lint"

# Delete a memory
hermes zerofactory memory delete <memory_id>
```

### Automated Memory Recording & Disable Controls
Zero Factory automatically captures repository insights during developer and agent workflows:
- **Automated Extraction**: When `zf-reviewer` leaves PR comments, a task is moved to `blocked` with a review reason, or comments are posted to a task, lines prefixed with:
  `GOTCHA:`, `CONVENTION:`, `RULE:`, `DECISION:`, `ARCH:`, `REJECTED_PATH:`, `LESSON:`, `LEARNING:`, or `TIP:`
  are automatically extracted, tagged (`auto-recorded`, `from-<actor>`), deduplicated, and persisted to `board_memories`.
- **Noise Protection**: Arbitrary comments and routine approvals are deliberately excluded to prevent prompt pollution and keep repository context high-signal.
- **Multi-Level Controls to Disable**:
  1. **Global Setting**: Settings Modal toggle (`Auto-record repository memory`) or `PATCH /api/plugins/zerofactory/settings`.
  2. **Per-Board Override**: Board Edit modal checkbox, or the 1-click `⚡ Auto-Record: ON/OFF` button in the `Agents` -> `Repository Memory` sub-tab header, or `PATCH /api/plugins/zerofactory/boards/<slug>`.

---

## Built-in Automation & Token-Efficient Cron Architecture

Zero Factory is architected to drastically minimize LLM token consumption (up to 95% token savings) across periodic automation cycles using Hermes Agent's **No-Agent Mode (`no_agent: true`)**, **Wake-Gate Change Detection (`{"wakeAgent": false}`)**, and **Chained LLM Jobs (`context_from`)**:

- **`zero-factory-task-queue-check`** (every 120m, **0 Tokens**):
  - Operates in Hermes **No-Agent Mode** via `scripts/zf_queue_watchdog.py`.
  - Audits running workers, reaps stuck subprocesses, and runs `run_dispatch_cycle()`.
  - When the queue is healthy, emits `{"wakeAgent": false}` to silently exit without invoking any LLM.
  - When bottlenecks occur, outputs a human-readable alert delivered to the operator.
- **`zero-factory-improvement-scanner-{board_slug}`** (on idle when active workers < 2, **0 Tokens on Idle**):
  - Executed by **`zf-orchestrator`** inside the repository workdir with wake-gate change detection via `scripts/zf_scanner_gate.py` with independent sessions (`continuity: false`).
  - Compares Git HEAD and working tree changes against `~/.hermes/scanner_state.json`.
  - Suppresses unchanged runs with `{"wakeAgent": false}` (0 LLM tokens).
  - When new commits or changes exist, pre-digests git log, diffstat, truncated diffs, and existing open board tasks, waking `zf-orchestrator` to analyze the project and file at most 1 actionable `Todo` task assigned to `zf-builder`.

---

## Repository Structure

```text
zerofactory/
├── plugin.yaml                  # Hermes plugin metadata
├── __init__.py                  # Plugin registration & CLI interface
├── dispatcher.py                # Autonomous dispatch engine & worktree manager
├── builtin_cron.py              # Periodic scanner & reporting engine
├── profile_manager.py           # Auto-provisioning for zf-* profiles & scripts
├── test_plugin.py               # Comprehensive unit & integration test suite (128 tests)
├── test_e2e.py                  # Hermetic End-to-End test suite across all subsystems (20 tests)
├── scripts/                     # No-Agent Mode scripts & LLM context pre-processors
│   ├── zf_queue_watchdog.py     # Autonomous worker reaper & queue monitor (0 tokens)
│   ├── zf_scanner_gate.py       # Codebase diff pre-screen & wake-gate
│   └── zf_daily_stats.py        # Deterministic 24h metrics & velocity calculator
├── dashboard/                   # Embedded web dashboard UI (/zerofactory)
│   ├── manifest.json            # Gateway route declaration
│   ├── plugin_api.py            # FastAPI REST backend
│   ├── build_css.mjs            # Regenerates dist/style.css (Tailwind v4, portable)
│   ├── input.css                # Tailwind entry source (bare package imports)
│   └── dist/
│       ├── index.js             # React Kanban UI
│       └── style.css            # Dark glassmorphic theme (committed build output)
├── skills/
│   └── zerofactory-orchestration/  # Multi-agent coordination skill
└── templates/                   # Version-controlled profile templates
    ├── zf-orchestrator/
    ├── zf-builder/
    └── zf-reviewer/
```

---

## Testing

Run the automated test suites against your local Hermes environment:
```bash
# 1. Run unit & integration test suite
python3 test_plugin.py

# 2. Run hermetic end-to-end (E2E) test suite (20 tests)
python3 test_e2e.py
```

### Rebuilding the dashboard stylesheet

The committed `dashboard/dist/style.css` is generated from `dashboard/input.css`
by `dashboard/build_css.mjs` (Tailwind CSS v4). It is portable — no machine-
specific paths — resolving `tailwindcss` from the project's `node_modules` or
the `ZEROFACTORY_TAILWIND_DIR` env override. To regenerate after editing the UI:
```bash
npm install            # if node_modules is not present (fresh clone)
node dashboard/build_css.mjs
```
`test_plugin.py::test_86_dashboard_css_is_portable_and_in_sync_with_js` guards
reproducibility and asserts the stylesheet carries selectors for every
variant-prefixed class the UI references (hover/focus/active/disabled).

---

## License

See [LICENSE](LICENSE).
