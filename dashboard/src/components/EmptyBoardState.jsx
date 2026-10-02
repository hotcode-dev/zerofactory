import React from "react";

export function EmptyBoardState({ onNewBoard, onInstructions }) {
  return React.createElement(
    "div",
    { className: "flex flex-col items-center justify-center py-20 px-6 text-center bg-slate-900/40 backdrop-blur-sm border border-slate-800/80 rounded-2xl max-w-2xl mx-auto my-8 space-y-6 shadow-2xl" },
    React.createElement(
      "div",
      { className: "w-20 h-20 rounded-2xl bg-gradient-to-br from-indigo-500/20 to-purple-500/20 border border-indigo-500/30 flex items-center justify-center text-4xl shadow-inner shadow-indigo-500/10" },
      "📋"
    ),
    React.createElement(
      "div",
      { className: "space-y-2 max-w-lg" },
      React.createElement("h2", { className: "text-xl font-bold text-white tracking-tight" }, "No Kanban Boards Configured"),
      React.createElement(
        "p",
        { className: "text-xs text-slate-400 leading-relaxed" },
        "Zero Factory requires at least one project board to organize tasks, track GitHub Pull Requests, and orchestrate autonomous AI agents. Please create a board to get started."
      )
    ),
    React.createElement(
      "div",
      { className: "flex flex-wrap items-center justify-center gap-3 pt-2" },
      React.createElement(
        "button",
        {
          type: "button",
          className: "inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/30 transition-all duration-150 cursor-pointer",
          onClick: onNewBoard
        },
        "✨ Create First Board"
      ),
      React.createElement(
        "button",
        {
          type: "button",
          className: "inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-all duration-150 cursor-pointer",
          onClick: onInstructions
        },
        "📖 Read Instructions & Architecture"
      )
    )
  );
}
