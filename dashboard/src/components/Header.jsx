import React from "react";

export function Header(props) {
  const {
    activeView,
    setActiveView,
    hasActiveAgents,
    sessionsList = [],
    agentsList = [],
    loadSessions,
    loadAgents,
    loadMemories,
    boards = [],
    selectedBoard,
    setSelectedBoard,
    handleOpenEditBoard,
    handleOpenEditBoardModal,
    handleOpenNewBoardModal,
    handleOpenCronModal,
    setShowCronModal,
    loadCronJobs,
    cronSchedulerEnabled = true,
    cronJobs = [],
    handleOpenSettingsModal,
    setShowSettingsModal,
    loadSettings,
    setShowNewTaskModal,
    setNewTaskForm,
    isDispatching,
    handleRunDispatcher,
    handleDispatch,
    loadBoards,
    loadTasksAndStats
  } = props;

  return React.createElement(
    "header",
    { className: "space-y-4 pb-5 border-b border-slate-800/80" },
          React.createElement(
            "div",
            { className: "flex flex-col lg:flex-row lg:items-center justify-between gap-4" },
            React.createElement(
              "div",
              { className: "flex items-center gap-4 flex-wrap" },
              React.createElement(
                "div",
                { className: "flex items-center gap-3.5" },
                React.createElement("div", { className: "w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center font-bold text-white shadow-lg shadow-indigo-500/25 text-sm tracking-wider shrink-0" }, "ZF"),
                React.createElement(
                  "div",
                  null,
                  React.createElement("h1", { className: "text-xl font-bold tracking-tight text-white flex items-center gap-2" }, "Zero Factory Kanban"),
                  React.createElement("p", { className: "text-xs text-slate-400 font-medium" }, "Autonomous Multi-Agent Coordination Engine")
                )
              ),
              // Navigation Tabs: Board vs Activities vs Instructions
              React.createElement(
                "div",
                { className: "flex items-center bg-slate-900/90 border border-slate-800 rounded-xl p-1 gap-1" },
                React.createElement(
                  "button",
                  {
                    type: "button",
                    className: "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer " +
                      (activeView === "board"
                        ? "bg-indigo-600 text-white shadow-xs shadow-indigo-600/30"
                        : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"),
                    onClick: () => setActiveView("board")
                  },
                  "📋 Board"
                ),
                React.createElement(
                  "button",
                  {
                    type: "button",
                    className: "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer relative " +
                      (activeView === "activities"
                        ? "bg-indigo-600 text-white shadow-xs shadow-indigo-600/30"
                        : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"),
                    onClick: () => setActiveView("activities")
                  },
                  "⚡ Activities",
                  hasActiveAgents &&
                  React.createElement("span", {
                    className: "w-2 h-2 rounded-full bg-emerald-400 zfk-pulse-active shrink-0 ml-0.5"
                  })
                ),
                React.createElement(
                  "button",
                  {
                    type: "button",
                    className: "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer relative " +
                      (activeView === "sessions" || activeView === "agents"
                        ? "bg-indigo-600 text-white shadow-xs shadow-indigo-600/30"
                        : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"),
                    onClick: () => {
                      setActiveView("agents");
                      loadSessions();
                      loadAgents();
                      loadMemories(selectedBoard);
                    }
                  },
                  "🤖 Agents",
                  (hasActiveAgents || sessionsList.some(s => s.status === "ongoing" || s.is_active) || agentsList.some(a => a.is_active)) &&
                  React.createElement("span", {
                    className: "w-2 h-2 rounded-full bg-emerald-400 zfk-pulse-active shrink-0 ml-0.5"
                  })
                ),
                React.createElement(
                  "button",
                  {
                    type: "button",
                    className: "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer " +
                      (activeView === "instructions"
                        ? "bg-indigo-600 text-white shadow-xs shadow-indigo-600/30"
                        : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"),
                    onClick: () => setActiveView("instructions")
                  },
                  "📖 Instructions"
                )
              )
            ),
            React.createElement(
              "div",
              { className: "flex flex-wrap items-center gap-2.5" },
              (activeView === "instructions" || activeView === "activities" || activeView === "sessions" || activeView === "agents") &&
              React.createElement(
                "button",
                {
                  type: "button",
                  className: "inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/25 transition-all duration-150 cursor-pointer",
                  onClick: () => setActiveView("board")
                },
                "← Back to Board"
              ),
              // Board Switcher (if boards exist)
              boards.length > 0
                ? React.createElement(
                  "select",
                  {
                    className: "bg-slate-900/90 border border-slate-700/80 hover:border-slate-600 rounded-lg px-3 py-1.5 text-xs font-medium text-slate-200 focus:ring-1 focus:ring-indigo-500 focus:outline-none cursor-pointer transition-colors shadow-sm",
                    value: selectedBoard,
                    onChange: (e) => {
                      const val = e.target.value;
                      setSelectedBoard(val);
                      loadTasksAndStats(val);
                      loadMemories(val);
                      loadSessions(val);
                      loadAgents(val);
                    }
                  },
                  React.createElement(
                    "option",
                    { key: "all", value: "all" },
                    "All Boards (" + boards.reduce((acc, b) => acc + (b.task_count || 0), 0) + ")"
                  ),
                  boards.map((b) =>
                    React.createElement(
                      "option",
                      { key: b.slug, value: b.slug },
                      b.slug + (b.task_count ? " (" + b.task_count + ")" : "")
                    )
                  )
                )
                : React.createElement(
                  "span",
                  { className: "px-2.5 py-1 text-xs font-semibold text-amber-300 bg-amber-950/60 border border-amber-800/60 rounded-lg" },
                  "No Boards Configured"
                ),
              React.createElement(
                "button",
                {
                  className: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold " +
                    (boards.length === 0
                      ? "bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/30"
                      : "bg-slate-800/80 hover:bg-slate-700/90 text-slate-200 border border-slate-700/80 hover:border-slate-600 shadow-sm") +
                    " transition-all duration-150 cursor-pointer",
                  onClick: handleOpenNewBoardModal,
                  title: "Create New Board"
                },
                "+ Board"
              ),
              selectedBoard && selectedBoard !== "all" &&
              React.createElement(
                "button",
                {
                  className: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800/80 hover:bg-slate-700/90 text-slate-200 border border-slate-700/80 hover:border-slate-600 shadow-sm transition-all duration-150 cursor-pointer",
                  onClick: handleOpenEditBoard || handleOpenEditBoardModal,
                  title: "Edit board settings and manage board"
                },
                "⚙️ Edit Board"
              ),
              React.createElement(
                "button",
                {
                  className: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800/80 hover:bg-slate-700/90 text-slate-200 border border-slate-700/80 hover:border-slate-600 shadow-sm transition-all duration-150 cursor-pointer",
                  onClick: () => {
                    if (handleOpenCronModal) {
                      handleOpenCronModal();
                    } else {
                      if (setShowCronModal) setShowCronModal(true);
                      if (loadCronJobs) loadCronJobs();
                    }
                  },
                  title: "Configure built-in Cron schedules and periodic automation"
                },
                "⏰ Cron Config",
                React.createElement(
                  "span",
                  {
                    className:
                      "px-1.5 py-0.5 rounded-full text-[10px] font-bold " +
                      (!cronSchedulerEnabled
                        ? "bg-rose-950/90 text-rose-300 border border-rose-800/80 shadow-xs"
                        : cronJobs.some((j) => j.enabled)
                          ? "bg-emerald-950/80 text-emerald-300 border border-emerald-800/60"
                          : "bg-slate-800 text-slate-400")
                  },
                  !cronSchedulerEnabled
                    ? "PAUSED"
                    : cronJobs.length > 0
                      ? cronJobs.filter((j) => j.enabled).length + "/" + cronJobs.length
                      : "CRON"
                )
              ),
              React.createElement(
                "button",
                {
                  className: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800/80 hover:bg-slate-700/90 text-slate-200 border border-slate-700/80 hover:border-slate-600 shadow-sm transition-all duration-150 cursor-pointer",
                  onClick: () => {
                    if (handleOpenSettingsModal) {
                      handleOpenSettingsModal();
                    } else {
                      if (loadSettings) loadSettings();
                      if (setShowSettingsModal) setShowSettingsModal(true);
                    }
                  },
                  title: "Global Zero Factory configuration (WIP limits, worker caps)"
                },
                "⚙️ Settings"
              ),
              React.createElement(
                "button",
                {
                  className: "inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white shadow-md shadow-emerald-600/25 transition-all duration-150 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed" + (isDispatching ? " opacity-70 cursor-wait" : ""),
                  onClick: handleRunDispatcher || handleDispatch,
                  disabled: isDispatching || boards.length === 0,
                  title: boards.length === 0 ? "Create a board first" : "Trigger Zero Factory Dispatcher Cycle"
                },
                isDispatching
                  ? React.createElement("span", { className: "zfk-spinning" }, "⏳")
                  : "⚡",
                isDispatching ? " Dispatching..." : " Dispatch"
              ),
              React.createElement(
                "button",
                {
                  className: "inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/25 transition-all duration-150 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed",
                  onClick: () => {
                    if (boards.length === 0) {
                      if (handleOpenNewBoardModal) handleOpenNewBoardModal();
                    } else {
                      if (setNewTaskForm) {
                        setNewTaskForm(prev => ({
                          ...prev,
                          board_slug: (selectedBoard && selectedBoard !== "all") ? selectedBoard : (boards[0] ? boards[0].slug : "")
                        }));
                      }
                      if (setShowNewTaskModal) setShowNewTaskModal(true);
                    }
                  },
                  disabled: boards.length === 0,
                  title: boards.length === 0 ? "Create a board first" : "Create New Task"
                },
                "+ New Task"
              ),
              React.createElement(
                "button",
                {
                  className: "inline-flex items-center justify-center p-2 rounded-lg text-xs font-semibold bg-slate-800/80 hover:bg-slate-700/90 text-slate-200 border border-slate-700/80 hover:border-slate-600 shadow-sm transition-all duration-150 cursor-pointer",
                  onClick: () => {
                    loadBoards();
                    loadTasksAndStats();
                  },
                  title: "Refresh Board"
                },
                "🔄"
              )
            )
          )
  );
}
