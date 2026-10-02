import React from "react";
import { renderPrIcon } from "../utils/icons.js";

export function FilterBar(props) {
  const {
    searchQuery,
    setSearchQuery,
    assigneeFilter,
    setAssigneeFilter,
    priorityFilter,
    setPriorityFilter,
    prFilter,
    setPrFilter,
    stats,
    autoRefresh,
    setAutoRefresh
  } = props;

  return (
                    React.createElement(
                      "div",
                      { className: "flex flex-wrap items-center justify-between gap-3 bg-slate-900/40 backdrop-blur-sm border border-slate-800/70 p-3 rounded-xl" },
                      React.createElement(
                        "div",
                        { className: "flex items-center gap-2 bg-slate-950/60 border border-slate-800 focus-within:border-indigo-500/80 focus-within:ring-1 focus-within:ring-indigo-500/40 rounded-lg px-3 py-1.5 min-w-[240px] md:w-80 transition-all" },
                        React.createElement("span", { className: "text-xs text-slate-500 shrink-0" }, "🔍"),
                        React.createElement("input", {
                          type: "text",
                          className: "bg-transparent text-xs text-slate-100 placeholder-slate-500 outline-none w-full",
                          placeholder: "Search tasks by title, description, ID or PR...",
                          value: searchQuery,
                          onChange: (e) => setSearchQuery(e.target.value)
                        })
                      ),
                      React.createElement(
                        "div",
                        { className: "flex items-center gap-1.5 flex-wrap" },
                        React.createElement("span", { className: "text-xs text-slate-400 mr-1" }, "Role:"),
                        [
                          { id: "all", label: "All" },
                          { id: "zf-builder", label: "ZF Builder" },
                          { id: "zf-reviewer", label: "ZF Reviewer" },
                          { id: "zf-orchestrator", label: "ZF Orchestrator" },
                          { id: "human", label: "Human" },
                          { id: "unassigned", label: "Unassigned" }
                        ].map((roleObj) =>
                          React.createElement(
                            "button",
                            {
                              key: roleObj.id,
                              type: "button",
                              className: (assigneeFilter === roleObj.id
                                ? "bg-indigo-600 text-white border-indigo-500 shadow-xs shadow-indigo-600/30"
                                : "bg-slate-800/70 text-slate-400 border-slate-700/60 hover:text-slate-200 hover:bg-slate-800") +
                                " px-2.5 py-1 rounded-md text-xs font-medium cursor-pointer transition-colors border text-center",
                              onClick: () => setAssigneeFilter(roleObj.id)
                            },
                            roleObj.label
                          )
                        )
                      ),
                      React.createElement(
                        "div",
                        { className: "flex items-center gap-1.5 flex-wrap" },
                        React.createElement("span", { className: "text-xs text-slate-400 mr-1" }, "Prio:"),
                        ["all", "P0", "P1", "P2", "P3"].map((prio) =>
                          React.createElement(
                            "button",
                            {
                              key: prio,
                              type: "button",
                              className: (priorityFilter === prio
                                ? "bg-indigo-600 text-white border-indigo-500 shadow-xs shadow-indigo-600/30"
                                : "bg-slate-800/70 text-slate-400 border-slate-700/60 hover:text-slate-200 hover:bg-slate-800") +
                                " px-2.5 py-1 rounded-md text-xs font-medium cursor-pointer transition-colors border text-center",
                              onClick: () => setPriorityFilter(prio)
                            },
                            prio
                          )
                        )
                      ),
                      React.createElement(
                        "div",
                        { className: "flex items-center gap-1.5 flex-wrap" },
                        React.createElement("span", { className: "text-xs text-slate-400 mr-1" }, "PR:"),
                        [
                          { id: "all", label: "All" },
                          { id: "has_pr", label: "Has PR" }
                        ].map((item) =>
                          React.createElement(
                            "button",
                            {
                              key: item.id,
                              type: "button",
                              className: (prFilter === item.id
                                ? "bg-purple-600 text-white border-purple-500 shadow-xs shadow-purple-600/30"
                                : "bg-slate-800/70 text-slate-400 border-slate-700/60 hover:text-slate-200 hover:bg-slate-800") +
                                " px-2.5 py-1 rounded-md text-xs font-medium cursor-pointer transition-colors border text-center inline-flex items-center gap-1.5",
                              onClick: () => setPrFilter(item.id)
                            },
                            item.id === "has_pr" && renderPrIcon("w-3 h-3 shrink-0"),
                            item.label,
                            item.id === "has_pr" && stats && stats.pr_count > 0 &&
                            React.createElement(
                              "span",
                              { className: "px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-purple-950/80 text-purple-300 border border-purple-800/60" },
                              stats.pr_count
                            )
                          )
                        )
                      ),
                      React.createElement(
                        "label",
                        { className: "flex items-center gap-2 text-xs text-slate-400 hover:text-slate-200 cursor-pointer select-none" },
                        React.createElement("input", {
                          type: "checkbox",
                          className: "rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500 cursor-pointer",
                          checked: autoRefresh,
                          onChange: (e) => setAutoRefresh(e.target.checked)
                        }),
                        "Live 10s Poll"
                      )
                    )
  );
}
