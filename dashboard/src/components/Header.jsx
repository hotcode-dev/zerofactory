import React from "react";
import { BoardSelector } from "./BoardSelector.jsx";

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
    setupStatus,
    isTogglingDispatcher,
    handleStartDispatcher,
    handleStopDispatcher,
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
              // Board Selector Dropdown
              React.createElement(BoardSelector, {
                boards,
                selectedBoard,
                onSelectBoard: (val) => {
                  setSelectedBoard(val);
                  loadTasksAndStats(val);
                  loadMemories(val);
                  loadSessions(val);
                  loadAgents(val);
                },
                onOpenNewBoard: handleOpenNewBoardModal,
                onOpenEditBoard: handleOpenEditBoard || handleOpenEditBoardModal,
                liveSessions: sessionsList
              }),
              // Navigation Tabs: Board vs Activities vs Instructions
              React.createElement(
                "nav",
                { "aria-label": "Primary navigation", className: "flex items-center bg-slate-900/90 border border-slate-800 rounded-xl p-1 gap-1" },
                React.createElement(
                  "button",
                  {
                    type: "button",
                    "aria-current": activeView === "board" ? "page" : undefined,
                    className: "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 transition-all cursor-pointer " +
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
                    "aria-current": activeView === "activities" ? "page" : undefined,
                    className: "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 transition-all cursor-pointer relative " +
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
                    "aria-current": (activeView === "sessions" || activeView === "agents") ? "page" : undefined,
                    className: "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 transition-all cursor-pointer relative " +
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
                    "aria-current": activeView === "instructions" ? "page" : undefined,
                    className: "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 transition-all cursor-pointer " +
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
              { className: "flex flex-wrap items-center justify-end gap-2.5 lg:ml-auto" },
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
              setupStatus && (handleStartDispatcher || handleStopDispatcher) &&
              React.createElement(
                "button",
                {
                  className:
                    "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold border shadow-sm transition-all duration-150 " +
                    (setupStatus.dispatcher_running
                      ? setupStatus.dispatcher_in_process
                        ? "bg-emerald-950/70 hover:bg-rose-950/70 text-emerald-300 hover:text-rose-200 border-emerald-700/60 hover:border-rose-700/70 cursor-pointer"
                        : "bg-emerald-950/50 text-emerald-300 border-emerald-800/60 cursor-default"
                      : "bg-slate-800/80 hover:bg-emerald-700/80 text-slate-200 hover:text-white border-slate-700/80 hover:border-emerald-600/80 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"),
                  onClick: () => {
                    if (setupStatus.dispatcher_running) {
                      if (setupStatus.dispatcher_in_process && handleStopDispatcher) {
                        handleStopDispatcher();
                      }
                    } else if (handleStartDispatcher) {
                      handleStartDispatcher();
                    }
                  },
                  disabled: Boolean(isTogglingDispatcher) || (!setupStatus.dispatcher_running && !setupStatus.profiles_ready) || (setupStatus.dispatcher_running && !setupStatus.dispatcher_in_process),
                  title: setupStatus.dispatcher_running
                    ? setupStatus.dispatcher_in_process
                      ? "Background dispatcher loop is running in this server. Click to stop."
                      : "Background dispatcher is running externally via 'hermes zerofactory start'."
                    : !setupStatus.profiles_ready
                      ? "Run 'hermes zerofactory setup' first to initialize profiles"
                      : "Start the continuous background dispatcher loop (30s interval)"
                },
                React.createElement("span", {
                  className:
                    "w-2 h-2 rounded-full " +
                    (setupStatus.dispatcher_running
                      ? "bg-emerald-400 animate-pulse"
                      : "bg-slate-500")
                }),
                isTogglingDispatcher
                  ? (setupStatus.dispatcher_running ? "Stopping..." : "Starting...")
                  : setupStatus.dispatcher_running
                    ? (setupStatus.dispatcher_in_process ? "Dispatcher: ON" : "Dispatcher: CLI")
                    : "Start Dispatcher"
              ),
              React.createElement(
                "button",
                {
                  className: "inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white shadow-md shadow-emerald-600/25 transition-all duration-150 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed" + (isDispatching ? " opacity-70 cursor-wait" : ""),
                  onClick: handleRunDispatcher || handleDispatch,
                  disabled: isDispatching || boards.length === 0,
                  title: boards.length === 0 ? "Create a board first" : "Trigger a single Zero Factory Dispatcher Cycle now"
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
              )
            )
          )
  );
}
