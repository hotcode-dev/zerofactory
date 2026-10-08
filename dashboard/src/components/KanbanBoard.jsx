import React from "react";
import { COLUMNS } from "../constants.js";
import { formatPrLabel, timeAgo } from "../utils/formatters.js";
import { renderPrIcon } from "../utils/icons.js";

export function KanbanBoard(props) {
  const {
    tasksByColumn,
    dragOverCol,
    handleDragOver,
    handleDragLeave,
    handleDrop,
    handleDragStart,
    loadTaskDetails,
    selectedBoard,
    stoppingSessionId,
    handleStopTaskSession,
    handleAdvanceTask
  } = props;

  return (
                    React.createElement(
                      "div",
                      { className: "overflow-x-auto pb-4 -mx-1 px-1 zfk-scrollbar" },
                      React.createElement(
                        "div",
                        {
                          className: "grid grid-cols-5 gap-3.5 items-start min-w-[1100px] w-full",
                          style: { display: "grid", gridTemplateColumns: "repeat(5, minmax(220px, 1fr))" }
                        },
                        COLUMNS.map((col) => {
                          const colTasks = tasksByColumn[col.id] || [];
                          const isOver = dragOverCol === col.id;

                          return React.createElement(
                            "div",
                            {
                              key: col.id,
                              className: "flex flex-col gap-2.5 bg-slate-900/50 backdrop-blur-md border rounded-xl p-2.5 min-h-[520px] transition-all duration-150 " + (isOver ? "border-indigo-500 bg-indigo-950/20 ring-2 ring-indigo-500/30" : "border-slate-800/80"),
                              onDragOver: (e) => handleDragOver(e, col.id),
                              onDragLeave: handleDragLeave,
                              onDrop: (e) => handleDrop(e, col.id)
                            },
                            React.createElement(
                              "div",
                              { className: "flex items-center justify-between px-1.5 py-1 select-none" },
                              React.createElement(
                                "div",
                                { className: "flex items-center gap-2 min-w-0" },
                                React.createElement("div", { className: "w-2.5 h-2.5 rounded-full shrink-0 shadow-xs", style: { backgroundColor: col.dotColor, boxShadow: "0 0 6px " + col.dotColor + "88" } }),
                                React.createElement("h3", { className: "text-xs font-semibold uppercase tracking-wider text-slate-300 truncate m-0" }, col.title)
                              ),
                              React.createElement("span", { className: "text-[0.6875rem] font-bold px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700/60 text-slate-400 font-mono" }, colTasks.length)
                            ),

                            React.createElement(
                              "div",
                              { className: "flex flex-col gap-2.5 flex-1 min-h-[120px]" },
                              colTasks.length === 0
                                ? React.createElement(
                                  "div",
                                  { className: "flex flex-col items-center justify-center p-6 text-center text-xs text-slate-500 border border-dashed border-slate-800/80 rounded-lg bg-slate-900/20 my-auto select-none" },
                                  "No " + col.title + " tasks",
                                  React.createElement("br", null),
                                  React.createElement("span", { className: "text-[0.6875rem] opacity-60 mt-1" }, "Drop tasks here")
                                )
                                : colTasks.map((t) => {
                                  const isRunning = t.status === "running";
                                  const prioClass = t.priority === "P0"
                                    ? "bg-rose-500/15 text-rose-300 border-rose-500/30"
                                    : t.priority === "P1"
                                      ? "bg-amber-500/15 text-amber-300 border-amber-500/30"
                                      : t.priority === "P3"
                                        ? "bg-slate-700/40 text-slate-400 border-slate-600/30"
                                        : "bg-sky-500/15 text-sky-300 border-sky-500/30";

                                  const roleClass = t.assignee === "zf-builder"
                                    ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                                    : t.assignee === "zf-reviewer"
                                      ? "bg-cyan-500/15 text-cyan-300 border-cyan-500/30"
                                      : t.assignee === "zf-orchestrator"
                                        ? "bg-purple-500/15 text-purple-300 border-purple-500/30"
                                        : t.assignee === "human"
                                          ? "bg-violet-500/15 text-violet-300 border-violet-500/30 font-semibold"
                                          : "bg-slate-700/30 text-slate-400 border-slate-700/40";

                                  return React.createElement(
                                    "div",
                                    {
                                      key: t.id,
                                      className: "group bg-slate-800/70 hover:bg-slate-800/95 border rounded-lg p-3 space-y-2.5 shadow-xs hover:shadow-md transition-all duration-150 cursor-grab active:cursor-grabbing hover:-translate-y-0.5 " + (isRunning ? "border-emerald-500/60 shadow-[0_0_12px_rgba(16,185,129,0.25)]" : "border-slate-700/60 hover:border-slate-600"),
                                      draggable: true,
                                      onDragStart: (e) => handleDragStart(e, t),
                                      onClick: () => loadTaskDetails(t.id)
                                    },
                                    React.createElement(
                                      "div",
                                      { className: "flex items-center justify-between gap-2" },
                                      React.createElement("span", { className: "font-mono text-[0.6875rem] font-semibold text-slate-400 tracking-wider" }, t.id),
                                      React.createElement(
                                        "div",
                                        { className: "flex items-center gap-1.5 flex-wrap" },
                                        React.createElement(
                                          "span",
                                          { className: "text-[0.625rem] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border " + prioClass },
                                          t.priority || "P2"
                                        ),
                                        React.createElement(
                                          "span",
                                          { className: "text-[0.625rem] font-medium capitalize px-1.5 py-0.5 rounded border " + roleClass },
                                          t.assignee || "unassigned"
                                        )
                                      )
                                    ),
                                    React.createElement("h4", { className: "text-xs font-semibold text-slate-200 leading-snug line-clamp-2 m-0 group-hover:text-white" }, t.title),
                                    React.createElement(
                                      "div",
                                      { className: "flex items-center gap-2 text-[0.6875rem] text-slate-400 flex-wrap" },
                                      selectedBoard === "all" && t.board_slug && React.createElement("span", { className: "inline-flex items-center gap-1 text-sky-400 font-mono text-[0.625rem] bg-sky-950/50 border border-sky-800/50 px-1.5 py-0.5 rounded truncate max-w-[130px]" }, "📋 " + t.board_slug),
                                      t.repo_alias && React.createElement("span", { className: "inline-flex items-center gap-1 text-teal-300 font-mono text-[0.625rem] bg-teal-950/60 border border-teal-800/60 px-1.5 py-0.5 rounded truncate max-w-[130px]" }, "📦 " + t.repo_alias),
                                      t.tenant && !t.repo_alias && React.createElement("span", { className: "inline-flex items-center gap-1 truncate max-w-[140px]" }, "📁 " + t.tenant),
                                      t.branch_name && React.createElement("span", { className: "inline-flex items-center gap-1 text-indigo-300 font-mono truncate max-w-[120px]" }, "🌿 " + t.branch_name),
                                      t.pr_url &&
                                      React.createElement(
                                        "a",
                                        {
                                          href: t.pr_url,
                                          target: "_blank",
                                          rel: "noopener noreferrer",
                                          onClick: (e) => e.stopPropagation(),
                                          className: "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[0.625rem] font-mono font-semibold bg-purple-500/15 hover:bg-purple-500/30 text-purple-300 hover:text-purple-100 border border-purple-500/30 transition-all duration-150 truncate max-w-[140px] shadow-xs cursor-pointer",
                                          title: "Pull Request: " + t.pr_url
                                        },
                                        renderPrIcon("w-2.5 h-2.5 shrink-0 text-purple-400"),
                                        formatPrLabel(t.pr_url)
                                      ),
                                      t.blocking_parent_count > 0 &&
                                      React.createElement(
                                        "span",
                                        { className: "text-[0.625rem] font-medium px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20" },
                                        "⏳ " + t.blocking_parent_count + " blocker"
                                      )
                                    ),
                                    (t.status === "running" || (t.session_progress && (t.session_progress.has_session || (t.session_progress.sessions && t.session_progress.sessions.length > 0)))) &&
                                    (() => {
                                      const tSessions = (t.session_progress && t.session_progress.sessions) || [];
                                      const isRunning = t.status === "running";
                                      const ongoingSess = isRunning
                                        ? (tSessions.find(s => s.status === "ongoing" || s.is_active) || t.session_progress)
                                        : null;
                                      const activeAgent = t.assignee || (ongoingSess && ongoingSess.agent) || "zf-builder";
                                      const agentIcon = activeAgent === "zf-reviewer" ? "🔍" : activeAgent === "zf-orchestrator" ? "🧭" : "🔨";
                                      const agentLabel = activeAgent === "zf-reviewer" ? "Reviewing PR" : activeAgent === "zf-orchestrator" ? "Orchestrating" : "Implementing";

                                      if (isRunning) {
                                        return React.createElement(
                                          "div",
                                          { className: "flex items-center justify-between gap-1.5 p-1.5 rounded-md border text-xs " + (activeAgent === "zf-reviewer" ? "bg-cyan-500/10 border-cyan-500/25 text-cyan-300" : "bg-emerald-500/10 border-emerald-500/20 text-emerald-300") },
                                          React.createElement(
                                            "div",
                                            { className: "flex items-center gap-1.5 min-w-0" },
                                            React.createElement("span", {
                                              className: "w-2 h-2 rounded-full shrink-0 " + (t.session_progress && t.session_progress.is_alive ? (activeAgent === "zf-reviewer" ? "bg-cyan-400 zfk-pulse-active" : "bg-emerald-400 zfk-pulse-active") : "bg-slate-500")
                                            }),
                                            React.createElement(
                                              "span",
                                              { className: "text-[0.6875rem] truncate font-medium" },
                                              agentIcon + " " + agentLabel +
                                              (t.session_progress && t.session_progress.turn_count ? " • " + t.session_progress.turn_count + " turns" : "") +
                                              (t.session_progress && t.session_progress.last_action ? " • " + t.session_progress.last_action : "")
                                            )
                                          ),
                                          React.createElement(
                                            "div",
                                            { className: "flex items-center gap-1 shrink-0" },
                                            tSessions.length > 1 &&
                                            React.createElement("span", { className: "text-[0.625rem] font-mono px-1.5 py-0.2 rounded bg-slate-800/80 text-slate-300 border border-slate-700/60" }, tSessions.length + " sess"),
                                            React.createElement(
                                              "button",
                                              {
                                                type: "button",
                                                disabled: stoppingSessionId === ((ongoingSess && ongoingSess.session_id) || t.id),
                                                className: "p-0.5 px-1 rounded text-[10px] font-semibold bg-rose-950/70 hover:bg-rose-900 text-rose-300 border border-rose-800/70 hover:border-rose-800/60 transition-colors cursor-pointer shadow-xs disabled:opacity-50",
                                                title: "Stop running AI session",
                                                onClick: (e) => {
                                                  e.stopPropagation();
                                                  handleStopTaskSession(t.id, ongoingSess && ongoingSess.session_id);
                                                }
                                              },
                                              stoppingSessionId === ((ongoingSess && ongoingSess.session_id) || t.id) ? "..." : "⏹"
                                            )
                                          )
                                        );
                                      }

                                      // Completed sessions on non-running task
                                      if (tSessions.length > 0) {
                                        const uniqueAgents = Array.from(new Set(tSessions.map(s => s.agent || t.assignee)));
                                        const iconMap = { "zf-reviewer": "🔍", "zf-orchestrator": "🧭", "zf-builder": "🔨" };
                                        const iconsStr = uniqueAgents.map(a => iconMap[a] || "🤖").join(" ");
                                        return React.createElement(
                                          "div",
                                          { className: "flex items-center justify-between gap-1.5 p-1.5 rounded-md border border-slate-800/80 bg-slate-900/50 text-slate-400 text-xs" },
                                          React.createElement(
                                            "span",
                                            { className: "text-[0.6875rem] truncate font-medium flex items-center gap-1 text-slate-300" },
                                            React.createElement("span", { className: "w-1.5 h-1.5 rounded-full bg-slate-500 shrink-0" }),
                                            tSessions.length + " AI session" + (tSessions.length > 1 ? "s" : "") + ": " + iconsStr
                                          ),
                                          t.session_progress && t.session_progress.turn_count ?
                                            React.createElement("span", { className: "text-[0.625rem] text-slate-500 font-mono shrink-0" }, t.session_progress.turn_count + "t") : null
                                        );
                                      }
                                      return null;
                                    })(),
                                    // Status bar for tasks requiring human attention or blocked
                                    t.status !== "running" &&
                                    (() => {
                                      const metaStr = typeof t.metadata === "string" ? t.metadata : JSON.stringify(t.metadata || {});
                                      const descStr = typeof t.description === "string" ? t.description : "";
                                      const titleStr = typeof t.title === "string" ? t.title : "";

                                      const isGrillInterview =
                                        metaStr.includes("Grill-with-Docs") ||
                                        metaStr.includes("Awaiting Human Input") ||
                                        metaStr.includes("awaiting_interview") ||
                                        descStr.includes("Grill-with-Docs") ||
                                        titleStr.toLowerCase().includes("grill");

                                      const isHumanTriage = t.status === "triage" && (t.assignee === "human" || isGrillInterview);
                                      const hasPr = Boolean(t.pr_url && String(t.pr_url).trim().length > 0);
                                      // "Awaiting merge" requires an actual PR URL; blocked without PR is a human gate or action item.
                                      const isHumanReview = t.status === "blocked" && t.assignee === "human" && hasPr;
                                      const isHumanBlockedNoPr = t.status === "blocked" && t.assignee === "human" && !hasPr;
                                      const isBlocked = t.status === "blocked";

                                      if (!isBlocked && !isHumanTriage && !isHumanReview && !isHumanBlockedNoPr) {
                                        return null;
                                      }

                                      let badgeClass = "";
                                      let dotClass = "";
                                      let labelText = "";

                                      if (isGrillInterview || (t.status === "triage" && t.assignee === "human")) {
                                        badgeClass = "bg-indigo-500/20 border-indigo-500/40 text-indigo-200";
                                        dotClass = "bg-indigo-400 zfk-pulse-active";
                                        labelText = isGrillInterview
                                          ? "🎯 Waiting for Human Decision • Grill Interview"
                                          : "🎯 Waiting for Human Input";
                                      } else if (metaStr.includes("\"conflict_retries\"")) {
                                        badgeClass = "bg-amber-500/15 border-amber-500/30 text-amber-300";
                                        dotClass = "bg-amber-400";
                                        labelText = "🟠 Merge Conflict";
                                      } else if (isHumanReview) {
                                        badgeClass = "bg-teal-500/15 border-teal-500/30 text-teal-300";
                                        dotClass = "bg-teal-400 zfk-pulse-active";
                                        labelText = "🟢 Waiting for Human to Merge";
                                      } else if (isHumanBlockedNoPr) {
                                        badgeClass = "bg-amber-500/15 border-amber-500/30 text-amber-300";
                                        dotClass = "bg-amber-400 zfk-pulse-active";
                                        labelText = "🛑 Waiting for Human Action";
                                      } else if (t.blocking_parent_count > 0) {
                                        badgeClass = "bg-slate-800 border-slate-700 text-slate-300";
                                        dotClass = "bg-slate-400";
                                        labelText = "⏳ Blocked by Parent Task";
                                      } else if (isBlocked) {
                                        badgeClass = "bg-rose-500/15 border-rose-500/30 text-rose-300";
                                        dotClass = "bg-rose-400 zfk-pulse-active";
                                        labelText = "🛑 Action Required / Stuck";
                                      } else {
                                        return null;
                                      }

                                      return React.createElement(
                                        "div",
                                        { className: "flex items-center gap-2 p-1.5 rounded-md border text-xs " + badgeClass },
                                        React.createElement("span", { className: "w-2 h-2 rounded-full shrink-0 " + dotClass }),
                                        React.createElement("span", { className: "text-[0.6875rem] truncate font-medium" }, labelText)
                                      );
                                    })(),
                                    React.createElement(
                                      "div",
                                      { className: "flex items-center justify-between pt-1 border-t border-slate-700/40 text-[0.6875rem] text-slate-400" },
                                      React.createElement(
                                        "span",
                                        { className: "text-[0.6875rem] text-slate-500" },
                                        timeAgo(t.updated_at || t.created_at)
                                      ),
                                      React.createElement(
                                        "div",
                                        { className: "flex items-center gap-1.5" },
                                        t.comment_count > 0 &&
                                        React.createElement(
                                          "span",
                                          { className: "inline-flex items-center px-1.5 py-0.5 rounded text-[0.6875rem] bg-slate-700/50 text-slate-300 hover:text-white cursor-pointer", title: t.comment_count + " comments" },
                                          "💬 " + t.comment_count
                                        ),
                                        React.createElement(
                                          "button",
                                          {
                                            type: "button",
                                            className: "inline-flex items-center justify-center w-5 h-5 rounded bg-slate-700/60 hover:bg-indigo-600 text-slate-300 hover:text-white transition-colors cursor-pointer text-xs leading-none font-bold",
                                            onClick: (e) => handleAdvanceTask(t, e),
                                            title: "Move to next column"
                                          },
                                          "→"
                                        )
                                      )
                                    )
                                  );
                                })
                            )
                          );
                        })
                      )
                    )
  );
}
