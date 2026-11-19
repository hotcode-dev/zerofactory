import React from "react";
import { renderPrIcon } from "../utils/icons.js";

export function InstructionsView({ instructionTab, setInstructionTab, setActiveView }) {
    const renderOverviewSection = () => {
      return React.createElement(
        "div",
        { className: "space-y-6" },
        React.createElement(
          "div",
          { className: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4" },
          [
            {
              icon: "🏭",
              title: "24/7 Autonomous Factory",
              desc: "Continuous agile iterations with rolling handoffs and parallel worker execution across multiple tasks."
            },
            {
              icon: "🌳",
              title: "Isolated Git Worktrees",
              desc: "Every task executes in its own dedicated Git worktree (~/.zerofactory/workspaces/<board>/worktrees/<task_id>). Main is never touched directly."
            },
            {
              icon: "🔍",
              title: "Thematic Code Review",
              desc: "Layered code review (Correctness & Tests ➔ Verification & Polish), capped at up to 2 focused rounds before human merge."
            },
            {
              icon: "⚡",
              title: "Zero-Token Idle Watchdogs",
              desc: "Hermes No-Agent Mode and Wake-Gate suppress LLM queries when repositories are idle, saving up to 95% token usage."
            },
            {
              icon: "🛠️",
              title: "Autonomous Self-Recovery",
              desc: "3-tier self-healing: zero-token orphan process reaper, 1-shot zf-orchestrator diagnostic recovery, and human override."
            },
            {
              icon: "🧠",
              title: "Mem0 Vector Memory",
              desc: "Hybrid semantic vector memory via Mem0 + Qdrant (FastEmbed ONNX CPU / OpenAI), auto-recorded on task completion."
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
            React.createElement("span", { className: "text-xs font-mono text-indigo-100 bg-indigo-900/80 px-3 py-1 rounded-md border border-indigo-500/70 font-semibold shadow-xs" }, "4 Actor Columns • 13 Stages • 4 Specialist Agents • HITL Gates")
          ),

          // 1. The 4 Actor-Based Kanban Columns
          React.createElement(
            "div",
            { className: "space-y-3" },
            React.createElement("div", { className: "text-xs font-bold text-slate-200 uppercase tracking-wider" }, "4 Actor-Based Kanban Columns & 13 Stages"),
            React.createElement(
              "div",
              { className: "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-2.5 text-xs" },
              [
                { step: "1. Human", color: "bg-rose-950/80 border-rose-500/70 text-rose-100", role: "All Human Gates (0 Tokens)", actor: "human", desc: "Sorted by urgency: awaiting_merge (PR ready), spec_approval, interview, blocked, and triage. Consumes zero LLM tokens until activated or merged." },
                { step: "2. Todo", color: "bg-sky-950/90 border-sky-500/70 text-sky-100", role: "AI Execution Queue", actor: "zf-* (Queued)", desc: "Tasks waiting for concurrency slots across 6 AI stages: grill, spec_draft, spec_audit, building, review, and recovery." },
                { step: "3. Running", color: "bg-emerald-950/90 border-emerald-500/70 text-emerald-100", role: "Active AI & Packaging", actor: "zf-* / dispatcher", desc: "Active worker subprocesses inside isolated Git worktrees (grill, spec_draft, spec_audit, building, review, recovery) plus deterministic packaging (precommit & PR)." },
                { step: "4. Done", color: "bg-slate-900 border-violet-500/70 text-violet-200", role: "Terminal Completed", actor: "System (Closed)", desc: "PR merged on GitHub or task closed terminally. Worktree pruned and background Mem0 repository memory extracted." }
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

          // 1b. Interactive SVG State Machine Diagram (4 Columns • 13 Stages)
          React.createElement(
            "div",
            { className: "space-y-3 pt-3 border-t border-slate-800" },
            React.createElement(
              "div",
              { className: "flex items-center justify-between flex-wrap gap-2" },
              React.createElement("div", { className: "text-xs font-bold text-slate-200 uppercase tracking-wider" }, "🗺️ State Machine Diagram (13 Stages & Transitions)"),
              React.createElement(
                "div",
                { className: "flex items-center gap-3 flex-wrap text-[11px] font-mono text-slate-300" },
                React.createElement("span", { className: "inline-flex items-center gap-1.5" }, React.createElement("span", { className: "w-2.5 h-2.5 rounded-sm bg-rose-500/80 border border-rose-300" }), "Human (0 tok)"),
                React.createElement("span", { className: "inline-flex items-center gap-1.5" }, React.createElement("span", { className: "w-2.5 h-2.5 rounded-sm bg-emerald-500/80 border border-emerald-300" }), "Todo / Running (AI)"),
                React.createElement("span", { className: "inline-flex items-center gap-1.5" }, React.createElement("span", { className: "w-2.5 h-2.5 rounded-sm bg-sky-500/80 border border-sky-300" }), "Dispatcher (0 tok)"),
                React.createElement("span", { className: "inline-flex items-center gap-1.5" }, React.createElement("span", { className: "w-2.5 h-2.5 rounded-sm bg-violet-500/80 border border-violet-300" }), "Done")
              )
            ),
            React.createElement(
              "div",
              { className: "w-full overflow-x-auto zfk-scrollbar bg-slate-950/90 border border-slate-800 rounded-xl p-4 shadow-inner" },
              (() => {
                const svgEl = React.createElement;
                const node = (x, y, w, h, fill, stroke, title, subtitle, badge) =>
                  svgEl(
                    "g",
                    { key: title + x + y },
                    svgEl("rect", { x, y, width: w, height: h, rx: 10, fill, stroke, strokeWidth: 1.5 }),
                    svgEl("text", { x: x + w / 2, y: y + 19, textAnchor: "middle", fill: "#f8fafc", fontSize: 12, fontWeight: "700", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }, title),
                    svgEl("text", { x: x + w / 2, y: y + 35, textAnchor: "middle", fill: "#cbd5e1", fontSize: 10, fontFamily: "ui-sans-serif, system-ui, sans-serif" }, subtitle),
                    badge && svgEl("text", { x: x + w / 2, y: y + 48, textAnchor: "middle", fill: "#94a3b8", fontSize: 9, fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }, badge)
                  );

                const pill = (cx, cy, w, text, textColor = "#e2e8f0", borderColor = "#334155") =>
                  svgEl(
                    "g",
                    { key: text + cx + cy },
                    svgEl("rect", { x: cx - w / 2, y: cy - 9, width: w, height: 18, rx: 9, fill: "#020617", stroke: borderColor, strokeWidth: 1 }),
                    svgEl("text", { x: cx, y: cy + 3, textAnchor: "middle", fill: textColor, fontSize: 9.5, fontWeight: "600", fontFamily: "ui-monospace, SFMono-Regular, Menlo, monospace" }, text)
                  );

                return svgEl(
                  "svg",
                  {
                    viewBox: "0 0 1160 572",
                    className: "w-full min-w-[920px] h-auto block select-none",
                    role: "img",
                    "aria-label": "Zero Factory 13-stage state machine diagram across Human, Todo, Running, and Done columns"
                  },
                  svgEl(
                    "defs",
                    null,
                    svgEl("marker", { id: "zfk-arrow", viewBox: "0 0 10 10", refX: 8, refY: 5, markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse" },
                      svgEl("path", { d: "M 0 1 L 10 5 L 0 9 z", fill: "#94a3b8" })
                    ),
                    svgEl("marker", { id: "zfk-arrow-amber", viewBox: "0 0 10 10", refX: 8, refY: 5, markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse" },
                      svgEl("path", { d: "M 0 1 L 10 5 L 0 9 z", fill: "#fbbf24" })
                    ),
                    svgEl("marker", { id: "zfk-arrow-emerald", viewBox: "0 0 10 10", refX: 8, refY: 5, markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse" },
                      svgEl("path", { d: "M 0 1 L 10 5 L 0 9 z", fill: "#34d399" })
                    ),
                    svgEl("marker", { id: "zfk-arrow-rose", viewBox: "0 0 10 10", refX: 8, refY: 5, markerWidth: 6, markerHeight: 6, orient: "auto-start-reverse" },
                      svgEl("path", { d: "M 0 1 L 10 5 L 0 9 z", fill: "#fb7185" })
                    )
                  ),

                  // Phase 1 Swimlane (y: 12..210)
                  svgEl("rect", { x: 14, y: 12, width: 1132, height: 198, rx: 12, fill: "#0f172a", stroke: "#1e293b", strokeWidth: 1 }),
                  svgEl("text", { x: 30, y: 31, fill: "#818cf8", fontSize: 10, fontWeight: "700", letterSpacing: "0.08em" }, "PHASE 1 • INTAKE & SEQUENTIAL EGM TRIAGE"),

                  // Phase 2 Swimlane (y: 246..412)
                  svgEl("rect", { x: 14, y: 246, width: 1132, height: 166, rx: 12, fill: "#0f172a", stroke: "#1e293b", strokeWidth: 1 }),
                  svgEl("text", { x: 224, y: 265, fill: "#34d399", fontSize: 10, fontWeight: "700", letterSpacing: "0.08em" }, "PHASE 2 • AUTONOMOUS BUILD, PRECOMMIT, PR REVIEW & HUMAN MERGE"),

                  // Phase 3 Swimlane (y: 446..562)
                  svgEl("rect", { x: 14, y: 446, width: 1132, height: 116, rx: 12, fill: "#0f172a", stroke: "#1e293b", strokeWidth: 1 }),
                  svgEl("text", { x: 500, y: 465, fill: "#fbbf24", fontSize: 10, fontWeight: "700", letterSpacing: "0.08em" }, "PHASE 3 • SELF-HEALING RECOVERY & HUMAN ESCALATION"),

                  // --- PHASE 1 ARROWS (drawn behind pills/nodes where appropriate) ---
                  // triage -> grill / spec_draft
                  svgEl("path", { d: "M 182 100 L 244 100", stroke: "#94a3b8", strokeWidth: 1.5, fill: "none", markerEnd: "url(#zfk-arrow)" }),
                  svgEl("text", { x: 213, y: 92, textAnchor: "middle", fill: "#cbd5e1", fontSize: 9 }, "Grill / EGM"),

                  // grill/spec_draft <-> interview
                  svgEl("path", { d: "M 320 128 L 320 150", stroke: "#94a3b8", strokeWidth: 1.4, strokeDasharray: "4 3", fill: "none", markerEnd: "url(#zfk-arrow)" }),
                  svgEl("text", { x: 294, y: 143, textAnchor: "middle", fill: "#94a3b8", fontSize: 9 }, "ask Q"),
                  svgEl("path", { d: "M 368 152 L 368 130", stroke: "#94a3b8", strokeWidth: 1.4, strokeDasharray: "4 3", fill: "none", markerEnd: "url(#zfk-arrow)" }),
                  svgEl("text", { x: 396, y: 143, textAnchor: "middle", fill: "#94a3b8", fontSize: 9 }, "reply"),

                  // grill / spec_draft -> spec_audit
                  svgEl("path", { d: "M 442 100 L 506 100", stroke: "#94a3b8", strokeWidth: 1.5, fill: "none", markerEnd: "url(#zfk-arrow)" }),
                  svgEl("text", { x: 474, y: 92, textAnchor: "middle", fill: "#cbd5e1", fontSize: 9 }, "spec ready"),

                  // spec_audit -> spec_approval
                  svgEl("path", { d: "M 686 100 L 752 100", stroke: "#94a3b8", strokeWidth: 1.5, fill: "none", markerEnd: "url(#zfk-arrow)" }),
                  svgEl("text", { x: 719, y: 92, textAnchor: "middle", fill: "#cbd5e1", fontSize: 9 }, "audited"),

                  // Reject loop: spec_approval -> spec_draft (dedicated top channel y=50)
                  svgEl("path", { d: "M 847 72 L 847 50 L 344 50 L 344 70", stroke: "#fb7185", strokeWidth: 1.4, strokeDasharray: "4 3", fill: "none", markerEnd: "url(#zfk-arrow-rose)" }),
                  pill(595, 50, 146, "reject (max 2 rounds)", "#fda4af", "#881337"),

                  // Approve path: spec_approval -> building (dedicated inter-phase channel y=228)
                  svgEl("path", { d: "M 847 128 L 847 228 L 119 228 L 119 300", stroke: "#34d399", strokeWidth: 1.8, fill: "none", markerEnd: "url(#zfk-arrow-emerald)" }),
                  pill(495, 228, 224, "approve [--split] ➔ Todo (building)", "#6ee7b7", "#065f46"),

                  // --- PHASE 1 NODES ---
                  node(32, 72, 150, 56, "#3b0724", "#f43f5e", "triage", "Human Column", "human • 0 tokens"),
                  node(246, 72, 196, 56, "#064e3b", "#10b981", "grill / spec_draft", "Todo ➔ Running", "zf-orchestrator"),
                  node(246, 152, 196, 48, "#3b0724", "#f43f5e", "interview", "Human Column • Q&A", null),
                  node(508, 72, 178, 56, "#064e3b", "#10b981", "spec_audit", "Todo ➔ Running", "zf-goldfish"),
                  node(754, 72, 186, 56, "#3b0724", "#f43f5e", "spec_approval", "Human Column", "human • approve/reject"),

                  // --- PHASE 2 ARROWS ---
                  // building -> packaging
                  svgEl("path", { d: "M 206 331 L 274 331", stroke: "#94a3b8", strokeWidth: 1.5, fill: "none", markerEnd: "url(#zfk-arrow)" }),
                  svgEl("text", { x: 240, y: 323, textAnchor: "middle", fill: "#cbd5e1", fontSize: 9 }, "exit 0"),

                  // packaging -> review
                  svgEl("path", { d: "M 456 331 L 524 331", stroke: "#94a3b8", strokeWidth: 1.5, fill: "none", markerEnd: "url(#zfk-arrow)" }),
                  svgEl("text", { x: 490, y: 323, textAnchor: "middle", fill: "#cbd5e1", fontSize: 9 }, "PR opened"),

                  // review -> awaiting_merge
                  svgEl("path", { d: "M 706 331 L 774 331", stroke: "#34d399", strokeWidth: 1.6, fill: "none", markerEnd: "url(#zfk-arrow-emerald)" }),
                  svgEl("text", { x: 740, y: 323, textAnchor: "middle", fill: "#6ee7b7", fontSize: 9 }, "approved"),

                  // awaiting_merge -> done
                  svgEl("path", { d: "M 950 331 L 1008 331", stroke: "#34d399", strokeWidth: 1.6, fill: "none", markerEnd: "url(#zfk-arrow-emerald)" }),
                  svgEl("text", { x: 979, y: 323, textAnchor: "middle", fill: "#6ee7b7", fontSize: 9 }, "merged"),

                  // Precommit fail loop: packaging -> building (y=282)
                  svgEl("path", { d: "M 366 302 L 366 282 L 166 282 L 166 300", stroke: "#fbbf24", strokeWidth: 1.4, strokeDasharray: "4 3", fill: "none", markerEnd: "url(#zfk-arrow-amber)" }),
                  pill(266, 282, 134, "precommit fail (≤3x)", "#fde68a", "#78350f"),

                  // Changes requested loop: review -> building (y=390)
                  svgEl("path", { d: "M 616 360 L 616 390 L 162 390 L 162 362", stroke: "#fbbf24", strokeWidth: 1.4, strokeDasharray: "4 3", fill: "none", markerEnd: "url(#zfk-arrow-amber)" }),
                  pill(505, 390, 198, "changes requested ➔ building", "#fde68a", "#78350f"),

                  // --- PHASE 2->3 & PHASE 3 ARROWS ---
                  // 3x retries exhausted: packaging -> recovery (inter-phase channel y=429)
                  svgEl("path", { d: "M 366 360 L 366 429 L 465 429 L 465 474", stroke: "#fbbf24", strokeWidth: 1.6, fill: "none", markerEnd: "url(#zfk-arrow-amber)" }),
                  pill(465, 429, 236, "3x retries exhausted (recovery = 0)", "#fde68a", "#78350f"),

                  // Recovery -> building (recover --guidance, vertical at x=112, clear of headers)
                  svgEl("path", { d: "M 340 504 L 112 504 L 112 362", stroke: "#34d399", strokeWidth: 1.6, fill: "none", markerEnd: "url(#zfk-arrow-emerald)" }),
                  pill(226, 504, 134, "recover --guidance", "#6ee7b7", "#065f46"),

                  // Recovery -> blocked
                  svgEl("path", { d: "M 590 504 L 774 504", stroke: "#fb7185", strokeWidth: 1.6, fill: "none", markerEnd: "url(#zfk-arrow-rose)" }),
                  pill(682, 504, 166, "report-bug / block / 2nd", "#fda4af", "#881337"),

                  // Human override: blocked -> building (bottom channel y=549, vertical at x=62)
                  svgEl("path", { d: "M 863 532 L 863 549 L 62 549 L 62 362", stroke: "#94a3b8", strokeWidth: 1.3, strokeDasharray: "4 3", fill: "none", markerEnd: "url(#zfk-arrow)" }),
                  pill(465, 549, 224, "human ⚡ Recover Task ➔ building", "#cbd5e1", "#334155"),

                  // --- PHASE 2 NODES ---
                  node(32, 302, 174, 58, "#064e3b", "#10b981", "building", "Todo ➔ Running", "zf-builder"),
                  node(276, 302, 180, 58, "#0c4a6e", "#38bdf8", "packaging", "Running (awaiting_pr)", "dispatcher • 0 tokens"),
                  node(526, 302, 180, 58, "#064e3b", "#10b981", "review", "Todo ➔ Running", "zf-reviewer (≤2 rnds)"),
                  node(776, 302, 174, 58, "#134e4a", "#14b8a6", "awaiting_merge", "Human Column (Top)", "human • PR ready"),
                  node(1010, 302, 118, 58, "#2e1065", "#a78bfa", "done", "Done Column", "terminal • Mem0"),

                  // --- PHASE 3 NODES ---
                  node(340, 476, 250, 56, "#78350f", "#f59e0b", "recovery", "Todo ➔ Running (Max 1x)", "zf-orchestrator"),
                  node(776, 476, 174, 56, "#4c0519", "#f43f5e", "blocked", "Human Column", "human • escalation")
                );
              })()
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
                  badge: "Human: triage",
                  bcolor: "text-indigo-100 bg-indigo-900/90 border-indigo-500/70",
                  desc: "Submit goals, epics, or synced GitHub issues via CLI or UI. Parked in Human (triage) with 0 tokens until you click Grill Me or Run EGM Spec."
                },
                {
                  num: "2",
                  title: "Sequential EGM",
                  badge: "Todo ➔ Running",
                  bcolor: "text-purple-100 bg-purple-900/90 border-purple-500/70",
                  desc: "zf-orchestrator drafts the technical spec (spec_draft, pausing in Human: interview if needed), then zf-goldfish runs a zero-context audit (spec_audit)."
                },
                {
                  num: "3",
                  title: "Human Release Gate",
                  badge: "Human ➔ Todo",
                  bcolor: "text-sky-100 bg-sky-900/90 border-sky-500/70",
                  desc: "Operator approves in Human (spec_approval) via UI or CLI (approve [--split]), promoting single-repo tasks to Todo (building) or splitting multi-repo epics."
                },
                {
                  num: "4",
                  title: "Worktree & Build",
                  badge: "Running: building",
                  bcolor: "text-emerald-100 bg-emerald-900/90 border-emerald-500/70",
                  desc: "Dispatcher enforces capacity & (status, assignee) invariants, provisions ~/.zerofactory/workspaces/<board>/worktrees/<task_id>, and launches zf-builder."
                },
                {
                  num: "5",
                  title: "Precommit & PR",
                  badge: "Running: packaging",
                  bcolor: "text-sky-100 bg-sky-900/90 border-sky-500/70",
                  desc: "Dispatcher runs .zerofactory/precommit.sh (format ➔ build ➔ tests, up to 3 retries), merges latest main, pushes, and opens a GitHub PR (0 LLM tokens)."
                },
                {
                  num: "6",
                  title: "Thematic Review",
                  badge: "Running: review",
                  bcolor: "text-cyan-100 bg-cyan-900/90 border-cyan-500/70",
                  desc: "zf-reviewer conducts up to 2 thematic rounds (Correctness & Tests ➔ Verification & Polish). Rework loops back to Todo (building); approval moves to Human."
                },
                {
                  num: "7",
                  title: "Human Merge",
                  badge: "Human ➔ Done",
                  bcolor: "text-teal-100 bg-teal-900/90 border-teal-500/70",
                  desc: "Approved PRs surface at the top of Human (awaiting_merge). Once merged on GitHub, dispatcher marks Done, prunes the worktree, and extracts Mem0 memory."
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
                    React.createElement("p", { className: "text-xs text-slate-200 leading-snug m-0 font-normal break-words" }, step.desc)
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
                " requests changes during review rounds in ",
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
                "Agents NEVER auto-merge to main. Every task produces an isolated PR; approved tasks surface at the top of ",
                React.createElement("span", { className: "font-mono text-teal-200 bg-slate-900 px-1.5 py-0.5 rounded border border-teal-500/60 font-bold" }, "Human (awaiting_merge)"),
                " until a human reviews and merges on GitHub. ",
                React.createElement("strong", { className: "text-amber-200 font-bold" }, "Autonomous Recovery & Escalation: "),
                "3× failure-exhausted tasks route once to ",
                React.createElement("span", { className: "font-mono text-amber-200 bg-slate-900 px-1.5 py-0.5 rounded border border-amber-500/60 font-bold" }, "Todo (recovery)"),
                " for ",
                React.createElement("span", { className: "font-mono text-purple-200 bg-slate-900 px-1.5 py-0.5 rounded border border-purple-500/60 font-bold" }, "zf-orchestrator"),
                " diagnosis before escalating to ",
                React.createElement("span", { className: "font-mono text-rose-200 bg-slate-900 px-1.5 py-0.5 rounded border border-rose-500/60 font-bold" }, "Human (blocked)"),
                "."
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
          title: "Pipeline Overseer & Elephant Planner",
          color: "border-indigo-500/70 bg-indigo-950/40 text-indigo-100",
          badge: "Indigo Profile (Pipeline Overseer)",
          desc: "Supervises the Kanban board, drafts technical specifications in triage, decomposes user epics into atomic tickets, schedules task execution, and detects stuck or hung worker processes.",
          responsibilities: [
            "Drafts end-to-end technical specifications, system contracts, and acceptance criteria in Triage",
            "Autonomously scans projects via Codebase Improvement Scanner using the Ponytail ladder of laziness to create actionable TODO tasks",
            "Audits repository for dead code (Rung 1), stdlib reuse (Rungs 2-3), and anti-overengineering (Rung 6)",
            "Decomposes high-level goals into structured sub-tasks using kanban_decomposer",
            "Diagnoses failure logs and executes autonomous self-recovery for stuck tasks (strictly capped at 1 attempt)",
            "Manages ticket handoffs between zf-builder and zf-reviewer",
            "Escalates unresolvable blockers and human reviews",
            "Monitors queue health & executes 1-shot autonomous recovery (recovery stage) on 3x failure-exhausted tasks"
          ],
          dir: "~/.hermes/profiles/zf-orchestrator/"
        },
        {
          name: "zf-goldfish",
          title: "Spec Auditor & Gatekeeper",
          color: "border-amber-500/70 bg-amber-950/40 text-amber-100",
          badge: "Amber Profile (Spec Auditor)",
          desc: "Conducts zero-context adversarial reviews on drafted specifications during sequential triage, enforcing the Ponytail 7-Rung Ladder of Laziness and concrete testability criteria.",
          responsibilities: [
            "Performs zero-context adversarial audits on specifications drafted by zf-orchestrator",
            "Enforces Ponytail 7-rung Ladder of Laziness: stdlib-first, surgical minimal diffs, zero package bloat",
            "Verifies explicit acceptance criteria, clear contract boundaries, and edge-case coverage",
            "Flags architectural ambiguities and unmitigated risks before human sign-off",
            "Surfaces blockers and actionable nits back to the operator or planner"
          ],
          dir: "~/.hermes/profiles/zf-goldfish/"
        },
        {
          name: "zf-builder",
          title: "Senior Software Engineer",
          color: "border-emerald-500/70 bg-emerald-950/40 text-emerald-100",
          badge: "Emerald Profile (Senior Engineer)",
          desc: "Takes tickets from Todo into Running, operating in an isolated Git worktree. Writes clean code and tests applying the Ponytail Ladder of Laziness.",
          responsibilities: [
            "Operates inside dedicated Git worktrees (~/.zerofactory/workspaces/<board>/worktrees/<task_id>)",
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
          desc: "Conducts thematic code reviews on open Pull Requests. Capped strictly at 2 progressive rounds (Correctness & Tests ➔ Verification & Polish) before human merge.",
          responsibilities: [
            "Round 1: Testing coverage, edge cases, and functional correctness",
            "Round 2: Verification, polish, clean code & Ponytail anti-overengineering review",
            "Pre-digested git diff and commit history provided directly in prompt context to minimize redundant exploration",
            "Approves PR and moves task to Human (awaiting_merge) for merge"
          ],
          dir: "~/.hermes/profiles/zf-reviewer/"
        }
      ];

      return React.createElement(
        "div",
        { className: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-2 xl:grid-cols-4 gap-5" },
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
        { id: "human", title: "Human", desc: "All human decision gates & escalations (0 LLM tokens), sorted by urgency: awaiting_merge, spec_approval, interview, blocked, triage.", trigger: "Goal created, PR approved, or escalation" },
        { id: "todo", title: "Todo", desc: "AI execution queue waiting for concurrency slots across 6 stages: grill, spec_draft, spec_audit, building, review, and recovery.", trigger: "Activated by human, approved, scanner, or rework" },
        { id: "running", title: "Running", desc: "Active AI worker sessions inside isolated Git worktrees plus deterministic packaging (precommit & PR, 0 LLM tokens).", trigger: "Autonomous pickup by dispatcher" },
        { id: "done", title: "Done", desc: "Terminal completed & merged tickets. Worktrees pruned and background Mem0 repository memory extracted.", trigger: "PR merged on GitHub or closed" }
      ];

      return React.createElement(
        "div",
        { className: "space-y-6" },
        React.createElement(
          "div",
          { className: "bg-slate-900/70 border border-slate-700/80 rounded-2xl p-6 space-y-4 shadow-md" },
          React.createElement("h3", { className: "text-sm font-bold text-white m-0 flex items-center gap-2 tracking-wide" }, "🔄 4-Column Actor-Based Kanban Workflow"),
          React.createElement(
            "div",
            { className: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 pt-1" },
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
        ),
        React.createElement(
          "div",
          { className: "bg-slate-900/70 border border-slate-700/80 rounded-2xl p-6 space-y-4 shadow-md" },
          React.createElement(
            "div",
            { className: "flex items-center justify-between flex-wrap gap-2 pb-2 border-b border-slate-800" },
            React.createElement("h3", { className: "text-sm font-bold text-white m-0 flex items-center gap-2 tracking-wide" }, "🛠️ Self-Healing, Process Reaping & Autonomous Recovery"),
            React.createElement("span", { className: "text-xs font-mono text-emerald-200 bg-emerald-950/80 px-3 py-1 rounded-md border border-emerald-500/60 font-semibold" }, "3-Tier Fault Tolerance")
          ),
          React.createElement(
            "p",
            { className: "text-xs text-slate-100 leading-relaxed m-0 font-normal" },
            "Tasks that fail build or test gates, hit worker crashes, or hang never get silently stranded. Zero Factory employs a three-tier recovery model combining deterministic zero-token process reaping, autonomous agent diagnosis, and human override gates:"
          ),
          React.createElement(
            "div",
            { className: "grid grid-cols-1 md:grid-cols-3 gap-4 pt-1 text-xs" },
            [
              {
                title: "1. Deterministic Reaper (0 Tokens)",
                badge: "Dispatcher Reaper",
                badgeColor: "bg-emerald-950 border-emerald-500/70 text-emerald-200",
                desc: "The built-in dispatcher reaper (dispatcher/reaper.py) audits active processes every 30s without invoking LLMs. Dead or orphaned sessions are reaped and restored to Todo (worker_recovered), and invalid (status, assignee) pairs are auto-repaired."
              },
              {
                title: "2. Autonomous Recovery Stage (Max 1)",
                badge: "zf-orchestrator",
                badgeColor: "bg-indigo-950 border-indigo-500/70 text-indigo-200",
                desc: "When a task exhausts 3 retries (worker crash/timeout, precommit, or merge conflict) and orchestrator_recovery_count < 1, it routes to Todo (recovery). zf-orchestrator inspects failure logs and runs recover --guidance, report-bug, or block."
              },
              {
                title: "3. Operator Rescue & HITL Gate",
                badge: "Human Column",
                badgeColor: "bg-purple-950 border-purple-500/70 text-purple-200",
                desc: "Post-recovery failures or external blockers escalate to Human (blocked). Operators can inspect diagnostics and click '⚡ Recover Task' in the Task Detail modal or run hermes zerofactory recover <task_id> [--guidance] to re-dispatch."
              }
            ].map((tier, idx) =>
              React.createElement(
                "div",
                { key: idx, className: "bg-slate-950/80 border border-slate-700/80 rounded-xl p-4.5 space-y-2.5 shadow-sm" },
                React.createElement(
                  "div",
                  { className: "flex items-center justify-between gap-2" },
                  React.createElement("span", { className: "text-xs font-bold text-white tracking-wide" }, tier.title),
                  React.createElement("span", { className: "text-[10px] font-mono px-2 py-0.5 rounded border font-semibold " + tier.badgeColor }, tier.badge)
                ),
                React.createElement("p", { className: "text-xs text-slate-200 leading-relaxed m-0 font-normal" }, tier.desc)
              )
            )
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
            React.createElement("div", { className: "text-indigo-300 font-bold" }, "# Workspace Directory Structure"),
            React.createElement("div", { className: "text-white font-bold" }, "~/.zerofactory/workspaces/<board_slug>/"),
            React.createElement("div", { className: "pl-4 text-slate-300" }, "├── repos/"),
            React.createElement("div", { className: "pl-8 text-slate-300" }, "└── my-repo/              # Pristine origin mirror (untouched by workers)"),
            React.createElement("div", { className: "pl-4 text-emerald-300 font-bold" }, "└── worktrees/"),
            React.createElement("div", { className: "pl-8 text-emerald-300 font-semibold" }, "├── zf-dev-9a4f210b/      # Isolated worktree for Task 1"),
            React.createElement("div", { className: "pl-12 text-slate-400" }, "└── my-repo/"),
            React.createElement("div", { className: "pl-8 text-emerald-300 font-semibold" }, "└── zf-dev-b72e189c/      # Isolated worktree for Task 2"),
            React.createElement("div", { className: "pl-12 text-slate-400" }, "└── my-repo/")
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

    const renderMemorySection = () => {
      return React.createElement(
        "div",
        { className: "space-y-6" },

        // 1. Architecture Hero Card
        React.createElement(
          "div",
          { className: "bg-slate-900/70 border border-slate-700/80 rounded-2xl p-6 space-y-5 shadow-md" },
          React.createElement(
            "div",
            { className: "flex items-center justify-between flex-wrap gap-2 pb-3 border-b border-slate-800" },
            React.createElement(
              "h3",
              { className: "text-base font-bold text-white m-0 flex items-center gap-2 tracking-wide" },
              React.createElement("span", null, "🧠"),
              "Mem0 Hybrid Vector Memory Substrate"
            ),
            React.createElement(
              "span",
              { className: "text-xs font-mono px-2.5 py-0.5 rounded-full font-bold bg-indigo-950/80 text-indigo-300 border border-indigo-800/60" },
              "Qdrant Vector DB • SQLite Dual-Write"
            )
          ),
          React.createElement(
            "p",
            { className: "text-xs text-slate-100 leading-relaxed m-0 font-normal" },
            "Zero Factory integrates ",
            React.createElement("strong", { className: "text-white" }, "Mem0"),
            " alongside an embedded ",
            React.createElement("strong", { className: "text-white" }, "Qdrant"),
            " vector database and local SQLite storage. Specialist agents and developers persist repository conventions, architectural decisions, and bug gotchas scoped per board. When tasks execute, relevant memories are semantically queried and injected into prompts so agents never repeat past mistakes."
          ),
          React.createElement(
            "div",
            { className: "grid grid-cols-1 md:grid-cols-3 gap-4" },
            [
              {
                title: "FastEmbed (Local ONNX CPU)",
                badge: "100% Local • Default",
                badgeColor: "text-emerald-300 bg-emerald-950/80 border-emerald-800/60",
                icon: "⚡",
                desc: "Runs locally on CPU via onnxruntime using BAAI/bge-small-en-v1.5 (384-dim). Zero external OpenAI API keys needed."
              },
              {
                title: "OpenAI / Compatible Embeddings",
                badge: "Cloud / Custom",
                badgeColor: "text-amber-300 bg-amber-950/80 border-amber-800/60",
                icon: "🌐",
                desc: "Supports OpenAI embeddings (text-embedding-3-small, 1536-dim) or any OpenAI-compatible embedding API with API key override."
              },
              {
                title: "Direct Vectorization (infer=False)",
                badge: "Zero Hallucination",
                badgeColor: "text-sky-300 bg-sky-950/80 border-sky-800/60",
                icon: "🎯",
                desc: "Clean structured memory statements are vectorized directly without LLM re-inference, ensuring high-fidelity extraction without hallucinations."
              }
            ].map((item, idx) =>
              React.createElement(
                "div",
                { key: idx, className: "bg-slate-950/80 border border-slate-700/80 rounded-xl p-4.5 space-y-2 shadow-sm" },
                React.createElement(
                  "div",
                  { className: "flex items-center justify-between gap-1" },
                  React.createElement(
                    "div",
                    { className: "flex items-center gap-2 font-bold text-white text-xs font-mono" },
                    React.createElement("span", null, item.icon),
                    item.title
                  ),
                  React.createElement("span", { className: "text-[10px] font-mono px-1.5 py-0.5 rounded border font-semibold " + item.badgeColor }, item.badge)
                ),
                React.createElement("p", { className: "text-xs text-slate-200 leading-relaxed m-0 font-normal" }, item.desc)
              )
            )
          )
        ),

        // 2. Automated Background Recording Card
        React.createElement(
          "div",
          { className: "bg-slate-900/70 border border-slate-700/80 rounded-2xl p-6 space-y-4 shadow-md" },
          React.createElement(
            "div",
            { className: "flex items-center justify-between flex-wrap gap-2 pb-3 border-b border-slate-800" },
            React.createElement(
              "h3",
              { className: "text-base font-bold text-white m-0 flex items-center gap-2 tracking-wide" },
              React.createElement("span", null, "🔄"),
              "Automated Background Recording (No Manual Tasks Needed)"
            ),
            React.createElement(
              "span",
              { className: "text-xs font-mono px-2.5 py-0.5 rounded-full font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-800/60" },
              "Zero Token Overhead"
            )
          ),
          React.createElement(
            "p",
            { className: "text-xs text-slate-100 leading-relaxed m-0 font-normal" },
            "Unlike traditional tools that require filing separate chore tickets to record memories, Zero Factory records repository knowledge automatically in the background:"
          ),
          React.createElement(
            "div",
            { className: "grid grid-cols-1 md:grid-cols-2 gap-4" },
            React.createElement(
              "div",
              { className: "p-4.5 bg-slate-950/80 border border-slate-700/80 rounded-xl space-y-2 shadow-sm" },
              React.createElement("div", { className: "font-bold text-emerald-300 text-xs flex items-center gap-2" }, "🎉 On PR Merge / Task Completion (Done):"),
              React.createElement(
                "p",
                { className: "text-slate-200 text-xs leading-relaxed m-0 font-normal" },
                "When a PR merges on GitHub and the dispatcher marks the ticket as ",
                React.createElement("span", { className: "font-mono text-emerald-300 bg-slate-900 px-1 py-0.5 rounded border border-slate-700" }, "Done"),
                ", key architectural implementations, conventions, and test patterns are parsed and automatically committed to Mem0 vector storage and SQLite."
              )
            ),
            React.createElement(
              "div",
              { className: "p-4.5 bg-slate-950/80 border border-slate-700/80 rounded-xl space-y-2 shadow-sm" },
              React.createElement("div", { className: "font-bold text-purple-300 text-xs flex items-center gap-2" }, "🔍 On Review Feedback & Blockers:"),
              React.createElement(
                "p",
                { className: "text-slate-200 text-xs leading-relaxed m-0 font-normal" },
                "When reviewers leave feedback or tasks are blocked with review reasons, structured prefixes like ",
                React.createElement("span", { className: "font-mono text-indigo-300 bg-slate-900 px-1 py-0.5 rounded border border-slate-700" }, "GOTCHA:"),
                ", ",
                React.createElement("span", { className: "font-mono text-indigo-300 bg-slate-900 px-1 py-0.5 rounded border border-slate-700" }, "CONVENTION:"),
                ", or ",
                React.createElement("span", { className: "font-mono text-indigo-300 bg-slate-900 px-1 py-0.5 rounded border border-slate-700" }, "DECISION:"),
                " are automatically captured."
              )
            )
          )
        ),

        // 3. Structured Taxonomy & Injection Card
        React.createElement(
          "div",
          { className: "bg-slate-900/70 border border-slate-700/80 rounded-2xl p-6 space-y-4 shadow-md" },
          React.createElement("h3", { className: "text-base font-bold text-white m-0 flex items-center gap-2 tracking-wide" },
            React.createElement("span", null, "🏷️"),
            "Structured Taxonomy & Prompt Pre-Digestion"
          ),
          React.createElement(
            "div",
            { className: "grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5 text-xs" },
            [
              { cat: "convention", color: "text-indigo-300 bg-indigo-950/80 border-indigo-800/60", desc: "Coding styles, project layouts, test frameworks" },
              { cat: "gotcha", color: "text-rose-300 bg-rose-950/80 border-rose-800/60", desc: "Concurrency race conditions, fragile mocks, edge cases" },
              { cat: "decision", color: "text-emerald-300 bg-emerald-950/80 border-emerald-800/60", desc: "Key design choices that govern future implementations" },
              { cat: "rejected_path", color: "text-amber-300 bg-amber-950/80 border-amber-800/60", desc: "Discarded attempts to prevent repeating failed paths" },
              { cat: "general", color: "text-slate-300 bg-slate-950/80 border-slate-700/80", desc: "Broad repository context and dependency nuances" }
            ].map((t, idx) =>
              React.createElement(
                "div",
                { key: idx, className: "p-3 rounded-xl border space-y-1.5 shadow-sm " + t.color },
                React.createElement("span", { className: "font-bold font-mono text-xs block" }, t.cat),
                React.createElement("p", { className: "text-[11px] text-slate-200 leading-snug m-0 font-normal" }, t.desc)
              )
            )
          ),
          React.createElement(
            "div",
            { className: "p-4 bg-indigo-950/40 border border-indigo-600/60 rounded-xl space-y-2 text-xs" },
            React.createElement("div", { className: "font-bold text-indigo-200 text-xs flex items-center gap-2" }, "🎯 Automatic Agent Injection:"),
            React.createElement(
              "p",
              { className: "text-slate-100 text-xs leading-relaxed m-0 font-normal" },
              "Before ",
              React.createElement("strong", { className: "text-white" }, "zf-builder"),
              " or ",
              React.createElement("strong", { className: "text-white" }, "zf-reviewer"),
              " launches, the dispatcher performs semantic cosine retrieval matching the current task's title and description against the board's memories. Relevant conventions and gotchas are injected into the prompt under ",
              React.createElement("span", { className: "font-mono text-indigo-300 bg-slate-950 px-1 py-0.5 rounded border border-slate-700" }, "## Repository Memory & Conventions"),
              "."
            )
          )
        ),

        // 4. Configuration & Controls Card
        React.createElement(
          "div",
          { className: "bg-slate-900/70 border border-slate-700/80 rounded-2xl p-6 space-y-4 shadow-md" },
          React.createElement("h3", { className: "text-base font-bold text-white m-0 flex items-center gap-2 tracking-wide" },
            React.createElement("span", null, "⚙️"),
            "Configuration & Settings"
          ),
          React.createElement(
            "p",
            { className: "text-xs text-slate-100 leading-relaxed m-0 font-normal" },
            "Memory engine settings are easily accessible in the Dashboard ",
            React.createElement("strong", { className: "text-white" }, "Settings Modal"),
            " (top navigation bar):"
          ),
          React.createElement(
            "div",
            { className: "grid grid-cols-1 md:grid-cols-2 gap-3 text-xs" },
            React.createElement(
              "div",
              { className: "p-3.5 bg-slate-950/80 border border-slate-700/80 rounded-xl space-y-1" },
              React.createElement("div", { className: "font-mono font-bold text-indigo-300" }, "mem0_enabled"),
              React.createElement("p", { className: "text-slate-200 m-0 font-normal" }, "Master switch to turn Mem0 vector memory on or off across all boards.")
            ),
            React.createElement(
              "div",
              { className: "p-3.5 bg-slate-950/80 border border-slate-700/80 rounded-xl space-y-1" },
              React.createElement("div", { className: "font-mono font-bold text-indigo-300" }, "mem0_embedder_provider"),
              React.createElement("p", { className: "text-slate-200 m-0 font-normal" }, "Toggle between FastEmbed (Local ONNX CPU, no API key) and OpenAI.")
            ),
            React.createElement(
              "div",
              { className: "p-3.5 bg-slate-950/80 border border-slate-700/80 rounded-xl space-y-1" },
              React.createElement("div", { className: "font-mono font-bold text-indigo-300" }, "mem0_model & mem0_base_url"),
              React.createElement("p", { className: "text-slate-200 m-0 font-normal" }, "Used in OpenAI mode (defaults to ~/.hermes/config.yaml; hidden when FastEmbed is active).")
            ),
            React.createElement(
              "div",
              { className: "p-3.5 bg-slate-950/80 border border-slate-700/80 rounded-xl space-y-1" },
              React.createElement("div", { className: "font-mono font-bold text-indigo-300" }, "Auto-Record Toggle"),
              React.createElement("p", { className: "text-slate-200 m-0 font-normal" }, "Per-board override button in Agents -> Repository Memory sub-tab header.")
            )
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
            { cmd: "hermes zerofactory approve <task_id> [--split]", desc: "Approve triage specification and promote/split to Todo" },
            { cmd: "hermes zerofactory reject <task_id> --feedback \"...\"", desc: "Request spec revision back to zf-orchestrator" },
            { cmd: "hermes zerofactory split <task_id> [--repos api,web]", desc: "Decompose multi-repo triage into sibling Todo tasks" },
            { cmd: "hermes zerofactory move <task_id> running", desc: "Transition ticket status" },
            { cmd: "hermes zerofactory recover <task_id> [--guidance \"...\"]", desc: "Recover stuck task to Todo with builder advice" },
            { cmd: "hermes zerofactory report-bug --task <task_id> --title \"...\"", desc: "Report internal Zero Factory defect to GitHub issues" },
            { cmd: "hermes zerofactory block <task_id> --reason \"<reason>\"", desc: "Mark ticket as blocked with explanation" },
            { cmd: "hermes zerofactory comment <task_id> \"<message>\"", desc: "Post a comment to a ticket" },
            { cmd: "hermes zerofactory import-gh-issue <issue> [--force]", desc: "Import GitHub issue into human-gated Triage task" },
            { cmd: "hermes zerofactory import-gh-issue --sync", desc: "Batch import open issues requested for AI investigation" }
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
          id: "dispatcher-loop (built-in)",
          title: "Dispatcher Loop, Process Reaper & Recovery Router",
          interval: "Every 30 seconds",
          tokens: "0 Tokens when Idle",
          desc: "Runs purely in Python inside the dispatcher thread (0 LLM tokens). Audits running tasks, reaps crashed/timed-out subprocesses, recovers orphaned tasks, repairs invalid (status, assignee) pairs, and routes 3× failure-exhausted tasks into the recovery stage (zf-orchestrator, capped at 1 autonomous attempt).",
          badge: "Deterministic Engine"
        },
        {
          id: "zero-factory-improvement-scanner-{slug}",
          title: "Codebase Improvement Scanner (zf-orchestrator)",
          interval: "On Idle (Active < 2)",
          tokens: "0 Tokens when Busy / Cooldown",
          desc: "Executed autonomously by zf-orchestrator inside the codebase workdir with wake-gate change detection (scripts/zf_scanner_gate.py) and independent sessions (continuity: false). When the pipeline is busy (running >= 2 or todo >= 2) or during the 15-minute cooldown, it emits {'wakeAgent': false} (0 tokens). When the board is idle, it wakes zf-orchestrator to audit the codebase for tech debt, refactoring, or missing tests, creating at most 1 actionable TODO task on the board assigned to zf-builder.",
          badge: "Wake-Gate • zf-orchestrator"
        },
        {
          id: "zero-factory-openwiki-update-{slug}",
          title: "OpenWiki Drift Detector & Refresh Gate",
          interval: "Daily",
          tokens: "0 Tokens (No-Agent Mode)",
          desc: "Runs via scripts/zf_openwiki_gate.py. Synchronizes ~/.openwiki/wiki-workspaces.json across all sibling repositories on a board and checks commit drift against openwiki/ docs. When non-doc code changes accumulate, files a deterministic Todo refresh task for zf-builder.",
          badge: "No-Agent Mode"
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
        { id: "memory", label: "Mem0 Repository Memory", icon: "🧠" },
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
              React.createElement("p", { className: "text-xs md:text-sm text-slate-200 max-w-2xl leading-relaxed m-0 font-normal" }, "A 24/7 autonomous multi-agent software engineering factory built natively for Hermes Agent. Four specialist agent profiles collaborate through a durable SQLite Kanban board to decompose goals, implement features inside isolated Git worktrees, and conduct thematic PR reviews.")
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
        instructionTab === "memory" && renderMemorySection(),
        instructionTab === "cli" && renderCliSection(),
        instructionTab === "crons" && renderCronsSection()
      );
}