import React from "react";
import { renderPrIcon } from "../utils/icons.js";

export function InstructionsView({ instructionTab, setInstructionTab, setActiveView }) {
    const renderOverviewSection = () => {
      return React.createElement(
        "div",
        { className: "space-y-6" },
        React.createElement(
          "div",
          { className: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4" },
          [
            {
              icon: "🏭",
              title: "24/7 Autonomous Factory",
              desc: "Continuous agile iterations with rolling handoffs and parallel worker execution across multiple tasks."
            },
            {
              icon: "🌳",
              title: "Isolated Git Worktrees",
              desc: "Every task executes in its own dedicated Git worktree (~/git/<repo>-worktrees/<task_id>). Main is never touched directly."
            },
            {
              icon: "🔍",
              title: "Thematic Code Review",
              desc: "Layered code review (Correctness ➔ Performance ➔ Clean Code / Ponytail), capped at up to 3 rounds before human merge."
            },
            {
              icon: "⚡",
              title: "Zero-Token Idle Watchdogs",
              desc: "Hermes No-Agent Mode and Wake-Gate suppress LLM queries when repositories are idle, saving up to 95% token usage."
            },
            {
              icon: "🧠",
              title: "Native Repository Memory",
              desc: "Durable SQLite knowledge substrate (kanban.db) persisting conventions, gotchas, and architectural decisions."
            }
          ].map((card, idx) =>
            React.createElement(
              "div",
              { key: idx, className: "bg-slate-900/80 border border-slate-700/80 rounded-xl p-5 space-y-2 hover:border-slate-600 transition-colors shadow-sm" },
              React.createElement("div", { className: "text-2xl mb-1" }, card.icon),
              React.createElement("h3", { className: "text-sm font-bold text-white m-0 tracking-wide" }, card.title),
              React.createElement("p", { className: "text-xs text-slate-200 leading-relaxed m-0 font-normal" }, card.desc)
            )
          )
        ),
        React.createElement(
          "div",
          { className: "bg-slate-900/70 border border-slate-700/80 rounded-2xl p-6 space-y-6 shadow-md" },
          React.createElement(
            "div",
            { className: "flex items-center justify-between flex-wrap gap-2 pb-3 border-b border-slate-800" },
            React.createElement("h3", { className: "text-sm font-bold uppercase tracking-wider text-indigo-300 m-0 flex items-center gap-2" }, "🏗️ High-Level Architecture & Workflow"),
            React.createElement("span", { className: "text-xs font-mono text-indigo-100 bg-indigo-900/80 px-3 py-1 rounded-md border border-indigo-500/70 font-semibold shadow-xs" }, "5 Kanban States • 3 Specialist Agents • HITL Merge Gate")
          ),

          // 1. The 5 Kanban Status Columns
          React.createElement(
            "div",
            { className: "space-y-3" },
            React.createElement("div", { className: "text-xs font-bold text-slate-200 uppercase tracking-wider" }, "Kanban Column States & Roles"),
            React.createElement(
              "div",
              { className: "grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5 text-xs" },
              [
                { step: "1. Triage", color: "bg-indigo-950/90 border-indigo-500/70 text-indigo-100", role: "Intake & Epics", actor: "User / Operator", desc: "Raw user goals and high-level feature epics. Ignored by dispatcher until decomposed into Todo." },
                { step: "2. Todo", color: "bg-sky-950/90 border-sky-500/70 text-sky-100", role: "Actionable Queue", actor: "Queue", desc: "Prioritized, actionable tasks ready for autonomous execution. Isolated Git worktree provisioned on pickup." },
                { step: "3. Running", color: "bg-emerald-950/90 border-emerald-500/70 text-emerald-100", role: "Autonomous AI", actor: "zf-builder / reviewer", desc: "Subprocess actively executing. zf-builder coding or zf-reviewer evaluating PR across continuous review rounds." },
                { step: "4. Blocked", color: "bg-purple-950/90 border-purple-500/70 text-purple-100", role: "Human Action (HITL)", actor: "Human Operator", desc: "Action required: PR approved waiting for human merge, crashed worker retry, or merge conflict resolution." },
                { step: "5. Done", color: "bg-slate-900 border-emerald-500/70 text-emerald-200", role: "PR Merged & Pruned", actor: "System (Closed)", desc: "PR merged on GitHub. Worktree pruned and metrics recorded." }
              ].map((col, idx) =>
                React.createElement(
                  "div",
                  { key: idx, className: "flex flex-col p-3.5 rounded-xl border text-center space-y-2 shadow-sm " + col.color },
                  React.createElement("span", { className: "font-bold font-mono text-xs text-white" }, col.step),
                  React.createElement("span", { className: "text-[11px] font-bold uppercase tracking-wider text-slate-100 truncate" }, col.role),
                  React.createElement("span", { className: "text-[10px] font-mono px-2 py-0.5 rounded bg-slate-950 border border-slate-700 text-slate-200 font-semibold truncate" }, col.actor),
                  React.createElement("p", { className: "text-xs text-slate-200 leading-snug m-0 text-left pt-1.5 border-t border-slate-700/60 font-normal" }, col.desc)
                )
              )
            )
          ),

          // 2. The 7-Step End-to-End Autonomous Lifecycle
          React.createElement(
            "div",
            { className: "space-y-3 pt-3 border-t border-slate-800" },
            React.createElement("div", { className: "text-xs font-bold text-slate-200 uppercase tracking-wider" }, "End-to-End Autonomous Execution Flow"),
            React.createElement(
              "div",
              { className: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-7 gap-2.5 text-xs" },
              [
                {
                  num: "1",
                  title: "Goal Ingestion",
                  badge: "Triage",
                  bcolor: "text-indigo-100 bg-indigo-900/90 border-indigo-500/70",
                  desc: "User submits high-level goals or epics via CLI or dashboard UI. Raw triage goals are unrefined and ignored by the dispatcher."
                },
                {
                  num: "2",
                  title: "Decompose & Scan",
                  badge: "Todo",
                  bcolor: "text-sky-100 bg-sky-900/90 border-sky-500/70",
                  desc: "zf-orchestrator decomposes Triage epics AND scans the codebase project on idle to create actionable TODO tasks."
                },
                {
                  num: "3",
                  title: "Worktree & Launch",
                  badge: "Running",
                  bcolor: "text-emerald-100 bg-emerald-900/90 border-emerald-500/70",
                  desc: "Dispatcher verifies capacity & WIP limits, allocates isolated Git worktree (~/git/<repo>-worktrees/<task_id>), and spawns zf-builder in Running."
                },
                {
                  num: "4",
                  title: "Code & Tests",
                  badge: "Running",
                  bcolor: "text-emerald-100 bg-emerald-900/90 border-emerald-500/70",
                  desc: "zf-builder inspects OpenWiki/AGENTS.md, writes code & tests applying the Ponytail Ladder of Laziness, and executes .zerofactory/precommit.sh."
                },
                {
                  num: "5",
                  title: "Precommit & PR",
                  badge: "Running",
                  bcolor: "text-emerald-100 bg-emerald-900/90 border-emerald-500/70",
                  desc: "Dispatcher runs precommit (format ➔ build ➔ tests), stages formatted files, self-heals any test regressions, opens GitHub PR, and routes to zf-reviewer."
                },
                {
                  num: "6",
                  title: "Thematic Review",
                  badge: "Running",
                  bcolor: "text-emerald-100 bg-emerald-900/90 border-emerald-500/70",
                  desc: "zf-reviewer runs in Running (Correctness ➔ Performance ➔ Ponytail / Clean Code, up to 3 rounds). Requests changes or approves."
                },
                {
                  num: "7",
                  title: "Human Merge",
                  badge: "Blocked ➔ Done",
                  bcolor: "text-rose-100 bg-rose-900/90 border-rose-500/70",
                  desc: "Approved PR waits in Blocked. Once human merges on GitHub, dispatcher marks task Done and prunes the worktree."
                }
              ].map((step, idx) =>
                React.createElement(
                  "div",
                  { key: idx, className: "bg-slate-950/80 border border-slate-700/80 rounded-xl p-3.5 flex flex-col justify-between space-y-2 relative group hover:border-slate-500 transition-colors shadow-sm" },
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement(
                      "div",
                      { className: "flex items-center justify-between gap-1" },
                      React.createElement("span", { className: "w-6 h-6 rounded-full bg-indigo-900/90 text-indigo-100 font-mono font-bold text-xs flex items-center justify-center shrink-0 border border-indigo-500/60 shadow-xs" }, step.num),
                      React.createElement("span", { className: "text-xs font-mono px-2 py-0.5 rounded border font-bold truncate shadow-xs " + step.bcolor }, step.badge)
                    ),
                    React.createElement("div", { className: "text-xs font-bold text-white leading-tight pt-0.5" }, step.title),
                    React.createElement("p", { className: "text-xs text-slate-200 leading-snug m-0 font-normal" }, step.desc)
                  )
                )
              )
            )
          ),

          // 3. Two Callouts: Feedback Loop + HITL Gates
          React.createElement(
            "div",
            { className: "grid grid-cols-1 md:grid-cols-2 gap-3.5 pt-2" },
            // Loopback Callout
            React.createElement(
              "div",
              { className: "p-4.5 bg-purple-950/50 border border-purple-600/70 rounded-xl space-y-2 text-xs shadow-sm" },
              React.createElement("div", { className: "font-bold flex items-center gap-2 text-purple-200 text-sm" }, "↩️ Reviewer Feedback Loop:"),
              React.createElement(
                "p",
                { className: "text-slate-100 text-xs leading-relaxed m-0 font-normal" },
                "When ",
                React.createElement("span", { className: "font-mono text-purple-200 bg-slate-900 px-1.5 py-0.5 rounded border border-purple-500/60 font-bold" }, "zf-reviewer"),
                " requests changes during rounds 1-3 in ",
                React.createElement("span", { className: "font-mono text-emerald-200 bg-slate-900 px-1.5 py-0.5 rounded border border-emerald-500/60 font-bold" }, "Running"),
                ", the dispatcher routes the ticket back to ",
                React.createElement("span", { className: "font-mono text-sky-200 bg-slate-900 px-1.5 py-0.5 rounded border border-sky-500/60 font-bold" }, "Todo"),
                " assigned to ",
                React.createElement("span", { className: "font-mono text-emerald-200 bg-slate-900 px-1.5 py-0.5 rounded border border-emerald-500/60 font-bold" }, "zf-builder"),
                ". The builder updates code and tests on the same branch, triggering automatic re-review."
              )
            ),
            // HITL Safety Gates
            React.createElement(
              "div",
              { className: "p-4.5 bg-amber-950/40 border border-amber-600/70 rounded-xl space-y-2 text-xs shadow-sm" },
              React.createElement("div", { className: "font-bold flex items-center gap-2 text-amber-200 text-sm" }, "🛡️ Human-in-the-Loop (HITL) Safety Gates:"),
              React.createElement(
                "p",
                { className: "text-slate-100 text-xs leading-relaxed m-0 font-normal" },
                React.createElement("strong", { className: "text-amber-200 font-bold" }, "PR Merge Gate: "),
                "Agents NEVER auto-merge to main. Every task produces an isolated PR; approved tasks pause in ",
                React.createElement("span", { className: "font-mono text-purple-200 bg-slate-900 px-1.5 py-0.5 rounded border border-purple-500/60 font-bold" }, "Blocked"),
                " until a human reviews and merges on GitHub. ",
                React.createElement("strong", { className: "text-amber-200 font-bold" }, "Escalation Gate: "),
                "Crashed workers, timeouts, or unresolvable merge conflicts route directly to ",
                React.createElement("span", { className: "font-mono text-purple-200 bg-slate-900 px-1.5 py-0.5 rounded border border-purple-500/60 font-bold" }, "Blocked"),
                " for operator resolution."
              )
            )
          )
        )
      );
    };

    const renderSpecialistsSection = () => {
      const specialists = [
        {
          name: "zf-orchestrator",
          title: "Pipeline Overseer & Coordinator",
          color: "border-indigo-500/70 bg-indigo-950/40 text-indigo-100",
          badge: "Indigo Profile (Pipeline Overseer)",
          desc: "Supervises the Kanban board, decomposes user epics into atomic tickets, schedules task execution, and detects stuck or hung worker processes.",
          responsibilities: [
            "Autonomously scans projects via Codebase Improvement Scanner using the Ponytail ladder of laziness to create actionable TODO tasks",
            "Audits repository for dead code (Rung 1), stdlib reuse (Rungs 2-3), and anti-overengineering (Rung 6)",
            "Decomposes high-level goals into structured sub-tasks using kanban_decomposer",
            "Manages ticket handoffs between zf-builder and zf-reviewer",
            "Escalates unresolvable blockers and human reviews",
            "Monitors queue health via zero-factory-task-queue-check"
          ],
          dir: "~/.hermes/profiles/zf-orchestrator/"
        },
        {
          name: "zf-builder",
          title: "Senior Software Engineer",
          color: "border-emerald-500/70 bg-emerald-950/40 text-emerald-100",
          badge: "Emerald Profile (Senior Engineer)",
          desc: "Takes tickets from Todo into Running, operating in an isolated Git worktree. Writes clean code and tests applying the Ponytail Ladder of Laziness.",
          responsibilities: [
            "Operates inside dedicated Git worktrees (~/git/<repo>-worktrees/<task_id>)",
            "Never touches or modifies the repository main branch directly",
            "Applies the 7-rung Ladder of Laziness: stdlib-first, surgical diffs, and zero package bloat",
            "Writes production code alongside automated unit and integration tests",
            "Verifies test suites pass cleanly before committing and opening PRs"
          ],
          dir: "~/.hermes/profiles/zf-builder/"
        },
        {
          name: "zf-reviewer",
          title: "Quality Gatekeeper",
          color: "border-purple-500/70 bg-purple-950/40 text-purple-100",
          badge: "Purple Profile (Quality Gatekeeper)",
          desc: "Conducts thematic code reviews on open Pull Requests. Capped strictly at 3 progressive rounds (Correctness ➔ Performance ➔ Ponytail / Clean Code) to eliminate infinite loops.",
          responsibilities: [
            "Round 1: Testing coverage, edge cases, and functional correctness",
            "Round 2: Performance, memory overhead, and algorithmic efficiency",
            "Round 3: Clean code & Ponytail anti-overengineering review (vetoing dependency bloat, diff creep, and premature abstractions)",
            "Pre-digested git diff and commit history provided directly in prompt context to minimize redundant exploration",
            "Approves PR and moves task to Blocked [Human Review] for merge"
          ],
          dir: "~/.hermes/profiles/zf-reviewer/"
        }
      ];

      return React.createElement(
        "div",
        { className: "grid grid-cols-1 lg:grid-cols-3 gap-5" },
        specialists.map((agent, i) =>
          React.createElement(
            "div",
            { key: i, className: "flex flex-col bg-slate-900/80 border rounded-2xl p-5 space-y-4 shadow-lg " + agent.color.split(" ")[0] },
            React.createElement(
              "div",
              { className: "flex items-center justify-between gap-2" },
              React.createElement("h3", { className: "text-base font-bold text-white font-mono m-0" }, agent.name),
              React.createElement("span", { className: "text-xs font-bold px-2.5 py-1 rounded-full border shadow-xs " + agent.color }, agent.badge)
            ),
            React.createElement("p", { className: "text-xs font-bold text-slate-200 m-0" }, agent.title),
            React.createElement("p", { className: "text-xs text-slate-100 leading-relaxed m-0 flex-1 font-normal" }, agent.desc),
            React.createElement(
              "div",
              { className: "space-y-2 pt-3 border-t border-slate-700/80" },
              React.createElement("span", { className: "text-xs font-bold text-slate-200 uppercase tracking-wider block" }, "Core Responsibilities:"),
              React.createElement(
                "ul",
                { className: "list-disc list-inside space-y-1.5 text-xs text-slate-200 m-0 p-0 leading-relaxed font-normal" },
                agent.responsibilities.map((r, idx) =>
                  React.createElement("li", { key: idx, className: "leading-relaxed" }, r)
                )
              )
            ),
            React.createElement(
              "div",
              { className: "pt-3 text-xs font-mono text-slate-300 border-t border-slate-700/70 flex items-center justify-between gap-2" },
              React.createElement("span", { className: "font-semibold text-slate-300" }, "Profile Path:"),
              React.createElement("span", { className: "text-indigo-200 bg-slate-950 px-2 py-1 rounded-md border border-slate-700 font-bold select-all" }, agent.dir)
            )
          )
        )
      );
    };

    const renderLifecycleSection = () => {
      const columns = [
        { id: "triage", title: "Triage", desc: "Incoming raw user goals, feature requests, or epics awaiting decomposition.", trigger: "Submitted via CLI or Board UI" },
        { id: "todo", title: "Todo", desc: "Actionable backlog: Decomposed tickets from Triage, improvement tasks filed by scanner, or reviewer rework.", trigger: "zf-orchestrator decomposes or scans" },
        { id: "running", title: "Running", desc: "Dedicated worker executing inside isolated Git worktree. zf-builder coding or zf-reviewer reviewing PR diff.", trigger: "Autonomous pickup by dispatcher" },
        { id: "blocked", title: "Blocked", desc: "Human action required: PR approved waiting for human merge, worker crash retry, or merge conflict resolution.", trigger: "Awaiting Human Merge, Crash, or Conflict" },
        { id: "done", title: "Done", desc: "Completed and merged tickets. Worktrees pruned and metrics updated.", trigger: "PR merged on GitHub" }
      ];

      return React.createElement(
        "div",
        { className: "space-y-6" },
        React.createElement(
          "div",
          { className: "bg-slate-900/70 border border-slate-700/80 rounded-2xl p-6 space-y-4 shadow-md" },
          React.createElement("h3", { className: "text-sm font-bold text-white m-0 flex items-center gap-2 tracking-wide" }, "🔄 Kanban Column Workflow"),
          React.createElement(
            "div",
            { className: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pt-1" },
            columns.map((c) =>
              React.createElement(
                "div",
                { key: c.id, className: "bg-slate-950/80 border border-slate-700/80 rounded-xl p-4.5 space-y-2.5 shadow-sm" },
                React.createElement(
                  "div",
                  { className: "flex items-center justify-between gap-2" },
                  React.createElement("span", { className: "text-sm font-bold uppercase tracking-wider text-indigo-300" }, c.title),
                  React.createElement("span", { className: "text-xs font-mono font-semibold px-2 py-0.5 rounded bg-slate-900 border border-slate-700 text-slate-200" }, c.id)
                ),
                React.createElement("p", { className: "text-xs text-slate-100 leading-relaxed m-0 font-normal" }, c.desc),
                React.createElement(
                  "div",
                  { className: "text-xs text-slate-300 pt-2 border-t border-slate-800 font-medium flex items-center justify-between gap-2 flex-wrap" },
                  React.createElement("span", null, "Trigger:"),
                  React.createElement("span", { className: "text-white font-semibold bg-slate-900 px-2 py-0.5 rounded border border-slate-700/80" }, c.trigger)
                )
              )
            )
          )
        ),
        React.createElement(
          "div",
          { className: "bg-gradient-to-br from-purple-950/50 via-slate-900/80 to-slate-900/80 border border-purple-600/70 rounded-2xl p-6 space-y-3 shadow-md" },
          React.createElement(
            "div",
            { className: "flex items-center gap-3" },
            React.createElement("div", { className: "p-2.5 rounded-xl bg-purple-900/80 text-purple-200 border border-purple-500/50 shadow-xs" }, renderPrIcon("w-4 h-4")),
            React.createElement("h3", { className: "text-base font-bold text-white m-0 tracking-wide" }, "Pull Request Tracking & Verification")
          ),
          React.createElement(
            "p",
            { className: "text-xs text-slate-100 leading-relaxed m-0 font-normal" },
            "Tasks with active GitHub Pull Requests display an interactive PR link badge directly on the Kanban card. You can click the badge to jump straight to the GitHub review interface. Use the toolbar's ",
            React.createElement("span", { className: "font-mono text-purple-200 bg-slate-900 px-1.5 py-0.5 rounded border border-purple-500/60 font-bold text-xs" }, "Has PR"),
            " filter button to instantly isolate all tickets currently under active Pull Request review."
          )
        )
      );
    };

    const renderWorktreesSection = () => {
      return React.createElement(
        "div",
        { className: "space-y-6" },
        React.createElement(
          "div",
          { className: "bg-slate-900/70 border border-slate-700/80 rounded-2xl p-6 space-y-4 shadow-md" },
          React.createElement("h3", { className: "text-sm font-bold text-white m-0 tracking-wide" }, "🌳 The Git Worktree Isolation Model"),
          React.createElement(
            "p",
            { className: "text-xs text-slate-100 leading-relaxed m-0 font-normal" },
            "In traditional multi-agent systems, agents operate on the primary repository directory. This causes uncommitted file clashes, stash corruptions, and broken builds when parallel tasks run. Zero Factory completely eliminates this failure mode using dedicated Git worktrees."
          ),
          React.createElement(
            "div",
            { className: "p-4.5 bg-slate-950 border border-slate-700 rounded-xl space-y-2 font-mono text-xs text-slate-100 shadow-inner" },
            React.createElement("div", { className: "text-indigo-300 font-bold" }, "# Worktree Directory Structure"),
            React.createElement("div", { className: "text-white font-bold" }, "~/git/"),
            React.createElement("div", { className: "pl-4 text-slate-300" }, "├── my-repo/                    # Main repository (untouched by workers)"),
            React.createElement("div", { className: "pl-4 text-emerald-300 font-bold" }, "└── my-repo-worktrees/"),
            React.createElement("div", { className: "pl-8 text-emerald-300 font-semibold" }, "├── zf-dev-9a4f210b/        # Isolated worktree for Task 1 (board code prefix)"),
            React.createElement("div", { className: "pl-8 text-emerald-300 font-semibold" }, "└── zf-dev-b72e189c/        # Isolated worktree for Task 2 (board code prefix)")
          ),
          React.createElement(
            "div",
            { className: "grid grid-cols-1 md:grid-cols-3 gap-4 pt-2" },
            [
              { title: "No Branch Conflicts", desc: "Workers branch cleanly from main without touching your active unstaged edits." },
              { title: "Parallel Test Suites", desc: "Multiple test runs execute simultaneously without file lock collisions." },
              { title: "Automated Cleanup", desc: "When the PR is merged, the worktree is automatically pruned from disk." }
            ].map((item, idx) =>
              React.createElement(
                "div",
                { key: idx, className: "p-4 bg-slate-950/80 border border-slate-700/80 rounded-xl space-y-1.5 shadow-sm" },
                React.createElement("h4", { className: "text-xs font-bold text-white m-0" }, item.title),
                React.createElement("p", { className: "text-xs text-slate-200 leading-relaxed m-0 font-normal" }, item.desc)
              )
            )
          )
        )
      );
    };

    const renderQualitySection = () => {
      return React.createElement(
        "div",
        { className: "space-y-6" },

        // 1. Precommit Pipeline Card
        React.createElement(
          "div",
          { className: "bg-slate-900/70 border border-slate-700/80 rounded-2xl p-6 space-y-5 shadow-md" },
          React.createElement(
            "div",
            { className: "flex items-center justify-between flex-wrap gap-2 pb-3 border-b border-slate-800" },
            React.createElement(
              "h3",
              { className: "text-base font-bold text-white m-0 flex items-center gap-2 tracking-wide" },
              React.createElement("span", null, "⚡"),
              "Deterministic Precommit Pipeline (.zerofactory/precommit.sh)"
            ),
            React.createElement(
              "span",
              { className: "text-xs font-mono px-2.5 py-0.5 rounded-full font-bold bg-amber-950/80 text-amber-300 border border-amber-800/60" },
              "Automated Quality Gate"
            )
          ),
          React.createElement(
            "p",
            { className: "text-xs text-slate-100 leading-relaxed m-0 font-normal" },
            "Zero Factory guarantees that no broken code, unformatted files, or failing tests reach a Pull Request. Before any commit or PR is generated, the dispatcher deterministically executes ",
            React.createElement("span", { className: "font-mono text-amber-300 bg-slate-950 px-1.5 py-0.5 rounded border border-slate-700 font-semibold" }, ".zerofactory/precommit.sh"),
            " inside the task's isolated Git worktree across three standard verification phases:"
          ),
          React.createElement(
            "div",
            { className: "grid grid-cols-1 md:grid-cols-3 gap-4" },
            [
              {
                phase: "1. Format & Lint",
                icon: "🎨",
                desc: "Runs automated linters (e.g. ruff check --fix, ruff format for Python; Prettier/ESLint for JS). Auto-installs missing tools to the system automatically and stages all formatted files."
              },
              {
                phase: "2. Build & Typecheck",
                icon: "🔨",
                desc: "Performs static syntax verification or bytecode compilation (e.g. python3 -m compileall, tsc --noEmit, cargo check) to guarantee zero syntax or import errors."
              },
              {
                phase: "3. Hermetic Tests",
                icon: "🧪",
                desc: "Executes the automated test suite (e.g. python3 -m pytest tests/ -q). Pull Requests are blocked from creation until all unit and integration tests pass cleanly with exit code 0."
              }
            ].map((p, idx) =>
              React.createElement(
                "div",
                { key: idx, className: "bg-slate-950/80 border border-slate-700/80 rounded-xl p-4.5 space-y-2 shadow-sm" },
                React.createElement(
                  "div",
                  { className: "flex items-center gap-2 font-bold text-white text-xs" },
                  React.createElement("span", null, p.icon),
                  p.phase
                ),
                React.createElement("p", { className: "text-xs text-slate-200 leading-relaxed m-0 font-normal" }, p.desc)
              )
            )
          ),
          React.createElement(
            "div",
            { className: "p-4.5 bg-amber-950/40 border border-amber-600/70 rounded-xl space-y-2 text-xs shadow-sm" },
            React.createElement("div", { className: "font-bold flex items-center gap-2 text-amber-200 text-sm" }, "🔁 Self-Healing Auto-Fix Feedback Loop:"),
            React.createElement(
              "p",
              { className: "text-slate-100 text-xs leading-relaxed m-0 font-normal" },
              "If precommit checks fail, the dispatcher does ",
              React.createElement("strong", { className: "text-white" }, "not"),
              " abandon the task or bother human reviewers. It captures the exact terminal stdout/stderr failure logs and re-spawns ",
              React.createElement("span", { className: "font-mono text-emerald-200 bg-slate-900 px-1.5 py-0.5 rounded border border-emerald-500/60 font-bold" }, "zf-builder"),
              " with the error trace to auto-fix regressions (up to 3 retries) before opening the PR."
            )
          ),
          React.createElement(
            "div",
            { className: "flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2 text-xs text-slate-300 font-medium" },
            React.createElement("span", null, "Setup trigger: 1-click warning banner on Kanban board, Board Settings modal, or CLI:"),
            React.createElement("span", { className: "font-mono text-amber-300 bg-slate-950 px-2.5 py-1 rounded-lg border border-slate-700 select-all shrink-0" }, "hermes zerofactory setup-repo --board <slug>")
          )
        ),

        // 2. OpenWiki Context Optimization Card
        React.createElement(
          "div",
          { className: "bg-slate-900/70 border border-slate-700/80 rounded-2xl p-6 space-y-5 shadow-md" },
          React.createElement(
            "div",
            { className: "flex items-center justify-between flex-wrap gap-2 pb-3 border-b border-slate-800" },
            React.createElement(
              "h3",
              { className: "text-base font-bold text-white m-0 flex items-center gap-2 tracking-wide" },
              React.createElement("span", null, "📖"),
              "OpenWiki Architecture Knowledge Base (openwiki/)"
            ),
            React.createElement(
              "span",
              { className: "text-xs font-mono px-2.5 py-0.5 rounded-full font-bold bg-sky-950/80 text-sky-300 border border-sky-800/60" },
              "Context Optimization (30–40% Token Savings)"
            )
          ),
          React.createElement(
            "p",
            { className: "text-xs text-slate-100 leading-relaxed m-0 font-normal" },
            "Autonomous coding agents frequently burn thousands of unnecessary tokens by blindly grepping directories and reading irrelevant source files. Zero Factory adopts the ",
            React.createElement("strong", { className: "text-white" }, "OpenWiki / Docs for Agents"),
            " standard: a pre-digested, machine-readable architectural knowledge base located in ",
            React.createElement("span", { className: "font-mono text-sky-300 bg-slate-950 px-1.5 py-0.5 rounded border border-slate-700 font-semibold" }, "openwiki/"),
            " and referenced in ",
            React.createElement("span", { className: "font-mono text-sky-300 bg-slate-950 px-1.5 py-0.5 rounded border border-slate-700 font-semibold" }, "AGENTS.md"),
            "."
          ),
          React.createElement(
            "div",
            { className: "grid grid-cols-1 md:grid-cols-3 gap-4" },
            [
              {
                title: "openwiki/index.md",
                icon: "🗺️",
                desc: "Master system map: Subsystem catalog, database models, background services, API route trees, and cross-module contracts."
              },
              {
                title: "Module Guides",
                icon: "📦",
                desc: "High-signal architectural summaries explaining component boundaries, entrypoints, and design decisions without raw source noise."
              },
              {
                title: "AGENTS.md Linking",
                icon: "🔗",
                desc: "Explicit instructions directing zf-builder and zf-reviewer to read openwiki/index.md first before performing expensive exploratory tool calls."
              }
            ].map((w, idx) =>
              React.createElement(
                "div",
                { key: idx, className: "bg-slate-950/80 border border-slate-700/80 rounded-xl p-4.5 space-y-2 shadow-sm" },
                React.createElement(
                  "div",
                  { className: "flex items-center gap-2 font-bold text-white text-xs font-mono" },
                  React.createElement("span", null, w.icon),
                  w.title
                ),
                React.createElement("p", { className: "text-xs text-slate-200 leading-relaxed m-0 font-normal" }, w.desc)
              )
            )
          ),
          React.createElement(
            "div",
            { className: "p-4.5 bg-sky-950/50 border border-sky-500/70 rounded-xl space-y-2 text-xs shadow-sm" },
            React.createElement("div", { className: "font-bold flex items-center gap-2 text-sky-200 text-sm" }, "🎯 Key Agent Benefits:"),
            React.createElement(
              "ul",
              { className: "text-slate-100 text-xs leading-relaxed m-0 pl-4 space-y-1 font-normal list-disc" },
              React.createElement("li", null, React.createElement("strong", { className: "text-white" }, "30–40% Token Savings:"), " Slashes exploratory grep_search, find_by_name, and random file reads by up to 40%."),
              React.createElement("li", null, React.createElement("strong", { className: "text-white" }, "Prevents Context Drift:"), " Prevents agents from hallucinating outdated conventions or diverging from established patterns."),
              React.createElement("li", null, React.createElement("strong", { className: "text-white" }, "Native MCP Tools (Zero ENV):"), " Pre-configured stdio MCP server (openwiki_begin, openwiki_submit_page, openwiki_search) with 0 external API keys or manual exports required."),
              React.createElement("li", null, React.createElement("strong", { className: "text-white" }, "Fast Onboarding:"), " New tasks start immediately with full architectural orientation in a single compact markdown read.")
            )
          ),
          React.createElement(
            "div",
            { className: "flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2 text-xs text-slate-300 font-medium" },
            React.createElement("span", null, "Setup trigger: 1-click recommendation banner on Kanban board, Board Settings modal, or CLI:"),
            React.createElement("span", { className: "font-mono text-sky-300 bg-slate-950 px-2.5 py-1 rounded-lg border border-slate-700 select-all shrink-0" }, "hermes zerofactory setup-openwiki --board <slug>")
          )
        )
      );
    };

    const renderCliSection = () => {
      const cliGroups = [
        {
          group: "Profile & System Setup",
          cmds: [
            { cmd: "hermes zerofactory setup", desc: "Bootstrap or inspect zf-* profiles and script symlinks" },
            { cmd: "hermes zerofactory sync-profiles", desc: "Update profile system prompts from plugin templates" }
          ]
        },
        {
          group: "Task Management",
          cmds: [
            { cmd: "hermes zerofactory list", desc: "List all active tickets across all boards" },
            { cmd: "hermes zerofactory list --board <slug> --status running", desc: "Filter tickets by board and status" },
            { cmd: "hermes zerofactory create \"<title>\" --description \"<desc>\" --board <slug> --priority P1", desc: "Create a new ticket" },
            { cmd: "hermes zerofactory move <task_id> running", desc: "Transition ticket status" },
            { cmd: "hermes zerofactory block <task_id> --reason \"<reason>\"", desc: "Mark ticket as blocked with explanation" },
            { cmd: "hermes zerofactory comment <task_id> \"<message>\"", desc: "Post a comment to a ticket" },
            { cmd: "hermes zerofactory import-gh-issue <issue> [--force]", desc: "Import GitHub issue into human-gated Triage task" },
            { cmd: "hermes zerofactory import-gh-issue --sync", desc: "Batch import open issues requested for AI investigation" },
            { cmd: "hermes zerofactory import-jira-issue <key-or-url> [--board <slug>]", desc: "Import Jira Cloud issue into human-gated Triage task" }
          ]
        },
        {
          group: "Board & Dispatcher Operations",
          cmds: [
            { cmd: "hermes zerofactory board list", desc: "List all registered project boards" },
            { cmd: "hermes zerofactory board create <git_url>", desc: "Register a new codebase board from Remote Git URL" },
            { cmd: "hermes zerofactory board delete <slug>", desc: "Delete a board and clear its scheduled scanner job" },
            { cmd: "hermes zerofactory setup-repo --board <slug>", desc: "Create P0 setup task to generate .zerofactory/precommit.sh" },
            { cmd: "hermes zerofactory setup-openwiki --board <slug>", desc: "Create P0 setup task to generate openwiki/ architecture docs" },
            { cmd: "hermes zerofactory setup-gh-issues --board <slug>", desc: "Create P0 setup task to generate GitHub Issue templates & labels" },
            { cmd: "hermes zerofactory setup-jira --board <slug> [--url <jira_url>]", desc: "Configure Jira Cloud instance link and test connectivity for a board" },
            { cmd: "hermes zerofactory stats", desc: "Show Kanban metrics, throughput, and worker states" },
            { cmd: "hermes zerofactory dispatch", desc: "Trigger an immediate autonomous dispatch cycle" },
            { cmd: "hermes zerofactory check-stuck", desc: "Audit and reap long-running or hung worker processes" }
          ]
        },
        {
          group: "Memory & Repository Knowledge",
          cmds: [
            { cmd: "hermes zerofactory memory list --board <slug>", desc: "List persistent repository memories and conventions" },
            { cmd: "hermes zerofactory memory add --board <slug> \"<content>\" --category convention", desc: "Record a new repository memory or gotcha" },
            { cmd: "hermes zerofactory memory delete <memory_id>", desc: "Delete a repository memory by ID" }
          ]
        },
        {
          group: "Cron Automation & Migrations",
          cmds: [
            { cmd: "hermes zerofactory cron list", desc: "View active periodic health & scanner jobs" },
            { cmd: "hermes zerofactory cron sync", desc: "Sync cron definitions with Hermes scheduler" },
            { cmd: "hermes zerofactory cron run <job_id>", desc: "Execute a scheduled scanner or watchdog immediately" },
            { cmd: "hermes zerofactory migrate [--status]", desc: "Inspect or execute pending SQLite database migrations" }
          ]
        }
      ];

      return React.createElement(
        "div",
        { className: "space-y-5" },
        cliGroups.map((g, idx) =>
          React.createElement(
            "div",
            { key: idx, className: "bg-slate-900/70 border border-slate-700/80 rounded-2xl p-5 space-y-3.5 shadow-md" },
            React.createElement("h3", { className: "text-sm font-bold uppercase tracking-wider text-indigo-300 m-0" }, g.group),
            React.createElement(
              "div",
              { className: "space-y-2.5" },
              g.cmds.map((item, cIdx) =>
                React.createElement(
                  "div",
                  { key: cIdx, className: "flex flex-col md:flex-row md:items-center justify-between gap-3 p-3.5 bg-slate-950 border border-slate-800 rounded-xl hover:border-slate-700 transition-colors shadow-xs" },
                  React.createElement("span", { className: "text-xs font-mono text-emerald-300 font-bold bg-slate-900 px-3 py-1.5 rounded-lg border border-slate-700 break-all select-all shadow-xs" }, item.cmd),
                  React.createElement("span", { className: "text-xs text-slate-200 font-medium shrink-0" }, item.desc)
                )
              )
            )
          )
        )
      );
    };

    const renderCronsSection = () => {
      const crons = [
        {
          id: "zero-factory-task-queue-check",
          title: "Queue Health & Worker Watchdog",
          interval: "Every 120 minutes",
          tokens: "0 Tokens (No-Agent Mode)",
          desc: "Runs purely in Python using Hermes No-Agent Mode via scripts/zf_queue_watchdog.py (0 LLM tokens). Audits running tasks, reaps hung worker subprocesses, and automatically triggers run_dispatch_cycle().",
          badge: "No-Agent Mode"
        },
        {
          id: "zero-factory-improvement-scanner-{slug}",
          title: "Codebase Improvement Scanner (zf-orchestrator)",
          interval: "On Idle (Active < 2)",
          tokens: "0 Tokens when Busy / Cooldown",
          desc: "Executed autonomously by zf-orchestrator inside the codebase workdir with wake-gate change detection (scripts/zf_scanner_gate.py) and independent sessions (continuity: false). When the pipeline is busy (running >= 2 or todo >= 2) or during the 15-minute cooldown, it emits {'wakeAgent': false} (0 tokens). When the board is idle, it wakes zf-orchestrator to audit the codebase for tech debt, refactoring, or missing tests, creating at most 1 actionable TODO task on the board assigned to zf-builder.",
          badge: "Wake-Gate • zf-orchestrator"
        }
      ];

      return React.createElement(
        "div",
        { className: "space-y-5" },
        crons.map((job) =>
          React.createElement(
            "div",
            { key: job.id, className: "bg-slate-900/70 border border-slate-700/80 rounded-2xl p-5 space-y-3 shadow-md" },
            React.createElement(
              "div",
              { className: "flex flex-col md:flex-row md:items-center justify-between gap-2.5" },
              React.createElement(
                "div",
                { className: "space-y-1.5" },
                React.createElement("h3", { className: "text-base font-bold text-white m-0 tracking-wide" }, job.title),
                React.createElement("span", { className: "text-xs font-mono text-indigo-200 bg-slate-950 px-2.5 py-1 rounded-md border border-slate-700 font-bold select-all inline-block" }, job.id)
              ),
              React.createElement(
                "div",
                { className: "flex items-center gap-2.5 flex-wrap" },
                React.createElement("span", { className: "text-xs font-bold px-3 py-1 rounded-full bg-emerald-900/90 text-emerald-100 border border-emerald-500/70 font-mono shadow-xs" }, job.tokens),
                React.createElement("span", { className: "text-xs font-bold px-3 py-1 rounded-full bg-slate-800 text-slate-100 border border-slate-600 font-mono shadow-xs" }, job.interval)
              )
            ),
            React.createElement("p", { className: "text-xs text-slate-100 leading-relaxed m-0 font-normal" }, job.desc)
          )
        )
      );
    };

      const tabs = [
        { id: "overview", label: "Architecture", icon: "🌟" },
        { id: "specialists", label: "Agent Specialists", icon: "🤖" },
        { id: "lifecycle", label: "Kanban & PR Lifecycle", icon: "🔄" },
        { id: "worktrees", label: "Git Worktree Isolation", icon: "🌳" },
        { id: "quality", label: "Precommit & OpenWiki", icon: "🛡️" },
        { id: "cli", label: "CLI Cheat Sheet", icon: "💻" },
        { id: "crons", label: "Scheduled Automation", icon: "⏰" }
      ];

      return React.createElement(
        "div",
        { className: "space-y-6 pb-12 max-w-[1400px] mx-auto" },

        // Instruction Hero Banner
        React.createElement(
          "div",
          { className: "relative overflow-hidden bg-gradient-to-br from-indigo-950/70 via-slate-900/90 to-purple-950/60 border border-slate-700/90 rounded-2xl p-6 md:p-8 shadow-2xl" },
          React.createElement(
            "div",
            { className: "flex flex-col md:flex-row md:items-center justify-between gap-6 relative z-10" },
            React.createElement(
              "div",
              { className: "space-y-3.5" },
              React.createElement(
                "div",
                { className: "flex items-center gap-2.5 flex-wrap" },
                React.createElement("span", { className: "px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-amber-950/80 text-amber-300 border border-amber-600/70 font-mono shadow-xs" }, "⚡ Active Beta"),
                React.createElement("span", { className: "px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-indigo-900/80 text-indigo-100 border border-indigo-500/60 font-mono shadow-xs" }, "Hermes Plugin"),
                React.createElement("span", { className: "px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-emerald-900/80 text-emerald-100 border border-emerald-500/60 font-mono shadow-xs" }, "Zero-Token Idle Watchdogs"),
                React.createElement("span", { className: "px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-purple-900/80 text-purple-100 border border-purple-500/60 font-mono shadow-xs" }, "Thematic Review")
              ),
              React.createElement("h2", { className: "text-2xl md:text-3xl font-extrabold text-white tracking-tight m-0" }, "Zero Factory Architecture & User Guide"),
              React.createElement("p", { className: "text-xs md:text-sm text-slate-200 max-w-2xl leading-relaxed m-0 font-normal" }, "A 24/7 autonomous multi-agent software engineering factory built natively for Hermes Agent. Three specialist agent profiles collaborate through a durable SQLite Kanban board to decompose goals, implement features inside isolated Git worktrees, and conduct thematic PR reviews.")
            ),
            React.createElement(
              "div",
              { className: "flex items-center gap-3 shrink-0" },
              React.createElement(
                "button",
                {
                  type: "button",
                  className: "inline-flex items-center gap-2 px-4.5 py-2.5 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/40 transition-all duration-150 cursor-pointer",
                  onClick: () => setActiveView("board")
                },
                "📋 Return to Kanban Board"
              )
            )
          )
        ),

        // Beta Notice & High-Frequency Change Warning Banner
        React.createElement(
          "div",
          { className: "flex items-start gap-3.5 p-4 md:p-6 rounded-2xl bg-amber-950/40 border border-amber-600/70 text-amber-200 text-xs md:text-sm leading-relaxed shadow-lg" },
          React.createElement("span", { className: "text-2xl shrink-0 select-none mt-0.5" }, "⚠️"),
          React.createElement(
            "div",
            { className: "space-y-1" },
            React.createElement("p", { className: "font-bold text-amber-200 text-sm m-0 flex items-center gap-2" }, "Beta Notice & High-Frequency Changes"),
            React.createElement("p", { className: "text-amber-300 text-xs md:text-sm m-0 leading-normal" }, "Zero Factory is currently in active beta and undergoing rapid evolution with high-frequency changes. APIs, CLI flags, configuration schemas, agent prompt templates, and internal orchestration mechanics evolve frequently. Please keep your plugin updated regularly.")
          )
        ),

        // Sub-Navigation Tabs
        React.createElement(
          "div",
          { className: "flex items-center gap-2 overflow-x-auto zfk-scrollbar pb-2 border-b border-slate-800" },
          tabs.map((tab) =>
            React.createElement(
              "button",
              {
                key: tab.id,
                type: "button",
                className: "flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold whitespace-nowrap transition-all duration-150 cursor-pointer " +
                  (instructionTab === tab.id
                    ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30 border border-indigo-400"
                    : "bg-slate-900/80 text-slate-200 hover:text-white hover:bg-slate-800 border border-slate-700/80 font-medium"),
                onClick: () => setInstructionTab(tab.id)
              },
              React.createElement("span", null, tab.icon),
              tab.label
            )
          )
        ),

        // Content for Selected Tab
        instructionTab === "overview" && renderOverviewSection(),
        instructionTab === "specialists" && renderSpecialistsSection(),
        instructionTab === "lifecycle" && renderLifecycleSection(),
        instructionTab === "worktrees" && renderWorktreesSection(),
        instructionTab === "quality" && renderQualitySection(),
        instructionTab === "cli" && renderCliSection(),
        instructionTab === "crons" && renderCronsSection()
      );
}