import React from "react";

export function StatsBar({ stats }) {
  if (!stats) return null;
  return (
                    React.createElement(
                      "div",
                      { className: "grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 pt-1" },
                      React.createElement(
                        "div",
                        { className: "bg-slate-900/60 backdrop-blur-md border border-slate-800/80 hover:border-slate-700/80 rounded-xl p-3 flex items-center gap-3 shadow-sm transition-all duration-150" },
                        React.createElement("div", { className: "w-9 h-9 rounded-lg flex items-center justify-center text-base shrink-0 bg-indigo-500/15 text-indigo-400" }, "📊"),
                        React.createElement(
                          "div",
                          { className: "flex flex-col min-w-0" },
                          React.createElement("span", { className: "text-lg font-bold text-white tracking-tight leading-none" }, stats.total || 0),
                          React.createElement("span", { className: "text-[11px] text-slate-400 font-medium truncate mt-1" }, "Total Tasks")
                        )
                      ),
                      React.createElement(
                        "div",
                        { className: "bg-slate-900/60 backdrop-blur-md border border-slate-800/80 hover:border-slate-700/80 rounded-xl p-3 flex items-center gap-3 shadow-sm transition-all duration-150" },
                        React.createElement("div", { className: "w-9 h-9 rounded-lg flex items-center justify-center text-base shrink-0 bg-amber-500/15 text-amber-400" }, "⚡"),
                        React.createElement(
                          "div",
                          { className: "flex flex-col min-w-0" },
                          React.createElement("span", { className: "text-lg font-bold text-white tracking-tight leading-none" }, (stats.columns && stats.columns.running) || 0),
                          React.createElement("span", { className: "text-[11px] text-slate-400 font-medium truncate mt-1" }, "Active In Progress")
                        )
                      ),
                      React.createElement(
                        "div",
                        { className: "bg-slate-900/60 backdrop-blur-md border border-slate-800/80 hover:border-slate-700/80 rounded-xl p-3 flex items-center gap-3 shadow-sm transition-all duration-150" },
                        React.createElement("div", { className: "w-9 h-9 rounded-lg flex items-center justify-center text-base shrink-0 bg-rose-500/15 text-rose-400" }, "🛑"),
                        React.createElement(
                          "div",
                          { className: "flex flex-col min-w-0" },
                          React.createElement("span", { className: "text-lg font-bold text-white tracking-tight leading-none" }, (stats.columns && stats.columns.blocked) || 0),
                          React.createElement("span", { className: "text-[11px] text-slate-400 font-medium truncate mt-1" }, "Blocked / Action")
                        )
                      ),
                      React.createElement(
                        "div",
                        { className: "bg-slate-900/60 backdrop-blur-md border border-slate-800/80 hover:border-slate-700/80 rounded-xl p-3 flex items-center gap-3 shadow-sm transition-all duration-150" },
                        React.createElement("div", { className: "w-9 h-9 rounded-lg flex items-center justify-center text-base shrink-0 bg-purple-500/15 text-purple-400" }, "✅"),
                        React.createElement(
                          "div",
                          { className: "flex flex-col min-w-0" },
                          React.createElement("span", { className: "text-lg font-bold text-white tracking-tight leading-none" }, (stats.columns && stats.columns.done) || 0),
                          React.createElement("span", { className: "text-[11px] text-slate-400 font-medium truncate mt-1" }, "Completed")
                        )
                      ),
                      React.createElement(
                        "div",
                        { className: "bg-slate-900/60 backdrop-blur-md border border-slate-800/80 hover:border-slate-700/80 rounded-xl p-3 flex items-center gap-3 shadow-sm transition-all duration-150" },
                        React.createElement("div", { className: "w-9 h-9 rounded-lg flex items-center justify-center text-base shrink-0 bg-emerald-500/15 text-emerald-400" }, "🌿"),
                        React.createElement(
                          "div",
                          { className: "flex flex-col min-w-0" },
                          React.createElement("span", { className: "text-lg font-bold text-white tracking-tight leading-none" }, stats.active_worktrees || 0),
                          React.createElement("span", { className: "text-[11px] text-slate-400 font-medium truncate mt-1" }, "Git Worktrees")
                        )
                      ),
                      React.createElement(
                        "div",
                        {
                          className: "bg-slate-900/60 backdrop-blur-md border border-slate-800/80 hover:border-slate-700/80 rounded-xl p-3 flex items-center gap-3 shadow-sm transition-all duration-150 cursor-pointer " + (prFilter === "has_pr" ? "ring-1 ring-purple-500/50 bg-purple-950/20" : ""),
                          onClick: () => setPrFilter(prFilter === "has_pr" ? "all" : "has_pr"),
                          title: "Filter by tasks with Pull Requests"
                        },
                        React.createElement("div", { className: "w-9 h-9 rounded-lg flex items-center justify-center text-base shrink-0 bg-purple-500/15 text-purple-400" }, renderPrIcon("w-4 h-4 text-purple-400")),
                        React.createElement(
                          "div",
                          { className: "flex flex-col min-w-0" },
                          React.createElement("span", { className: "text-lg font-bold text-white tracking-tight leading-none" }, stats.pr_count || 0),
                          React.createElement("span", { className: "text-[11px] text-slate-400 font-medium truncate mt-1" }, "Pull Requests")
                        )
                      )
                    )
  );
}
