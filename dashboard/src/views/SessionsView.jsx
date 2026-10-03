import React, { useState } from "react";
import { timeAgo } from "../utils/formatters.js";
import { API_BASE } from "../constants.js";
import { fetchJSON } from "../sdk.js";

export function SessionsView(props) {
  const {
    selectedBoard,
    sessionsList = [],
    sessionsLoading,
    sessionsAgentFilter,
    setSessionsAgentFilter,
    sessionsStatusFilter,
    setSessionsStatusFilter,
    sessionsSearchQuery,
    setSessionsSearchQuery,
    stoppingSessionId,
    handleStopSession,
    handleStopTaskSession = handleStopSession || (() => {}),
    loadSessions,
    tasks = [],
    agentsSubTab,
    setAgentsSubTab,
    boardMemories,
    memoriesLoading,
    memoriesTotal,
    loadBoardMemories,
    loadMemories = loadBoardMemories || (() => {}),
    memoryCategoryFilter,
    setMemoryCategoryFilter,
    memorySearchQuery,
    setMemorySearchQuery,
    showAddMemoryModal,
    setShowAddMemoryModal,
    newMemoryForm,
    setNewMemoryForm,
    handleCreateMemory,
    submittingMemory,
    handleDeleteMemory,
    setActiveView,
    selectedSessionIdx,
    setSelectedSessionIdx,
    agentsList = [],
    agentsLoading = false,
    loadAgents = () => {},
    loadTaskDetails = () => {},
    boards = [],
    showToast = () => {},
    loadBoards = () => {}
  } = props;

      // Filter sessions by selected board first (if not 'all')
      const boardFilteredSessions = sessionsList.filter((s) => {
        if (!selectedBoard || selectedBoard === "all") return true;
        if (s.board_slug) return s.board_slug === selectedBoard;
        const cwdOrTitle = (s.cwd || "") + " " + (s.title || "");
        const taskMatch = cwdOrTitle.match(/zf-[a-z0-9_-]+/i) || cwdOrTitle.match(/task-[a-z0-9_-]+/i);
        if (taskMatch) {
          const tid = taskMatch[0].toLowerCase();
          const matchedTask = tasks.find(t => t.id && t.id.toLowerCase() === tid);
          if (matchedTask) {
            return matchedTask.board_slug === selectedBoard;
          }
        }
        if (s.cwd && (s.cwd.includes(selectedBoard) || s.cwd.includes(selectedBoard.replace(/-/g, "/")))) return true;
        return false;
      });

      // Filter effective sessions by agent role, status, and search query
      const effectiveSessions = boardFilteredSessions.filter((s) => {
        if (sessionsAgentFilter !== "all" && s.agent !== sessionsAgentFilter) return false;
        if (sessionsStatusFilter !== "all" && s.status !== sessionsStatusFilter) return false;
        if (sessionsSearchQuery.trim()) {
          const q = sessionsSearchQuery.toLowerCase();
          const matchTitle = (s.title || "").toLowerCase().includes(q);
          const matchId = (s.session_id || "").toLowerCase().includes(q);
          const matchModel = (s.model || "").toLowerCase().includes(q);
          const matchAgent = (s.agent || "").toLowerCase().includes(q);
          const matchCwd = (s.cwd || "").toLowerCase().includes(q);
          const matchBoard = (s.board_slug || "").toLowerCase().includes(q);
          if (!matchTitle && !matchId && !matchModel && !matchAgent && !matchCwd && !matchBoard) return false;
        }
        return true;
      });

      // Filter memories
      const filteredMemories = boardMemories.filter((m) => {
        if (memoryCategoryFilter !== "all" && m.category !== memoryCategoryFilter) return false;
        if (memorySearchQuery.trim()) {
          const q = memorySearchQuery.toLowerCase();
          const matchContent = (m.content || "").toLowerCase().includes(q);
          const matchTags = (m.tags || []).some(t => String(t).toLowerCase().includes(q));
          const matchAuthor = (m.author || "").toLowerCase().includes(q);
          const matchTask = (m.task_id || "").toLowerCase().includes(q);
          if (!matchContent && !matchTags && !matchAuthor && !matchTask) return false;
        }
        return true;
      });

      const totalCount = boardFilteredSessions.length;
      const ongoingCount = boardFilteredSessions.filter(s => s.status === "ongoing" || s.is_active).length;
      const finishedCount = boardFilteredSessions.filter(s => s.status === "finished" && !s.is_active).length;
      const totalTurns = boardFilteredSessions.reduce((acc, s) => acc + (s.turn_count || 0), 0);

      const agentTabs = [
        { id: "all", label: "All Agents", count: totalCount },
        { id: "zf-orchestrator", label: "🧭 Orchestrator", count: boardFilteredSessions.filter(s => s.agent === "zf-orchestrator").length },
        { id: "zf-builder", label: "🔨 Builder", count: boardFilteredSessions.filter(s => s.agent === "zf-builder").length },
        { id: "zf-reviewer", label: "🔍 Reviewer", count: boardFilteredSessions.filter(s => s.agent === "zf-reviewer").length },
      ];

      const memoryCategories = [
        { id: "all", label: "All", icon: "📚", count: boardMemories.length },
        { id: "convention", label: "Convention", icon: "📐", count: boardMemories.filter(m => m.category === "convention").length },
        { id: "gotcha", label: "Gotcha", icon: "⚠️", count: boardMemories.filter(m => m.category === "gotcha").length },
        { id: "decision", label: "Decision", icon: "💡", count: boardMemories.filter(m => m.category === "decision").length },
        { id: "rejected_path", label: "Rejected Path", icon: "🚫", count: boardMemories.filter(m => m.category === "rejected_path").length },
        { id: "general", label: "General", icon: "📝", count: boardMemories.filter(m => m.category === "general").length },
      ];

      const agentMetas = [
        { id: "zf-orchestrator", label: "Orchestrator", icon: "🧭", role: "Planning, Triage & Improvement Scans" },
        { id: "zf-builder", label: "Builder", icon: "🔨", role: "Implementation, Bug Fixing & Pull Requests" },
        { id: "zf-reviewer", label: "Reviewer", icon: "🔍", role: "Code Review, Testing & Quality Verification" },
      ];

      return React.createElement(
        "div",
        { className: "space-y-6 animate-fade-in" },
        // Top Header
        React.createElement(
          "div",
          { className: "flex flex-wrap items-center justify-between gap-4 bg-slate-900/60 backdrop-blur-md border border-slate-800/80 p-5 rounded-2xl shadow-sm" },
          React.createElement(
            "div",
            { className: "flex items-center gap-3" },
            React.createElement("div", { className: "w-11 h-11 rounded-xl bg-indigo-500/15 border border-indigo-500/30 flex items-center justify-center text-2xl shadow-xs" }, "🤖"),
            React.createElement(
              "div",
              null,
              React.createElement("h2", { className: "text-base font-bold text-white tracking-tight flex items-center gap-2" },
                "Specialist Agents & Memory",
                ongoingCount > 0 &&
                React.createElement("span", { className: "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-500/15 text-emerald-300 border border-emerald-500/30" },
                  React.createElement("span", { className: "w-1.5 h-1.5 rounded-full bg-emerald-400 zfk-pulse-active" }),
                  ongoingCount + " Active"
                )
              ),
              React.createElement("p", { className: "text-xs text-slate-400 mt-0.5" }, "Live status of 3 specialist agents, session telemetry, and persistent repository memory.")
            )
          ),
          React.createElement(
            "div",
            { className: "flex items-center gap-2" },
            React.createElement(
              "button",
              {
                type: "button",
                className: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800/90 hover:bg-slate-700 text-slate-200 border border-slate-700 hover:border-slate-600 shadow-sm transition-all cursor-pointer",
                onClick: () => {
                  loadSessions(selectedBoard);
                  loadAgents(selectedBoard);
                  loadMemories(selectedBoard);
                },
                disabled: sessionsLoading || agentsLoading || memoriesLoading
              },
              (sessionsLoading || agentsLoading || memoriesLoading) ? React.createElement("span", { className: "zfk-spinning" }, "⏳") : "🔄",
              " Refresh"
            )
          )
        ),

        // Section 1: 3 Specialist Agent Cards
        React.createElement(
          "div",
          { className: "grid grid-cols-1 md:grid-cols-3 gap-4" },
          agentMetas.map((meta) => {
            const agentInfo = agentsList.find(a => a.name === meta.id) || {};
            const agentSessions = boardFilteredSessions.filter(s => s.agent === meta.id);
            const isAgentActive = agentInfo.is_active || (agentInfo.status === "active") || agentSessions.some(s => s.status === "ongoing" || s.is_active);
            const currentTask = agentInfo.current_task;
            const activeSession = agentInfo.active_session || agentSessions.find(s => s.status === "ongoing" || s.is_active);
            const totalAgentTurns = agentSessions.reduce((acc, s) => acc + (s.turn_count || 0), 0);

            return React.createElement(
              "div",
              {
                key: meta.id,
                className: "bg-slate-900/70 backdrop-blur-md border border-slate-800/90 hover:border-slate-700/80 rounded-2xl p-4.5 transition-all shadow-sm flex flex-col justify-between space-y-4"
              },
              React.createElement(
                "div",
                { className: "space-y-3" },
                // Header row
                React.createElement(
                  "div",
                  { className: "flex items-center justify-between gap-2" },
                  React.createElement(
                    "div",
                    { className: "flex items-center gap-2.5" },
                    React.createElement(
                      "div",
                      { className: "w-9 h-9 rounded-xl flex items-center justify-center text-xl bg-slate-800/90 border border-slate-700/60 shadow-xs" },
                      meta.icon
                    ),
                    React.createElement(
                      "div",
                      null,
                      React.createElement("h3", { className: "text-sm font-bold text-white tracking-tight leading-none" }, meta.label),
                      React.createElement("span", { className: "text-[10px] text-slate-500 font-mono" }, meta.id)
                    )
                  ),
                  React.createElement(
                    "div",
                    { className: "flex items-center gap-1.5" },
                    React.createElement(
                      "span",
                      {
                        className: "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold border " +
                          (isAgentActive
                            ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                            : "bg-slate-800/80 text-slate-400 border-slate-700/60")
                      },
                      React.createElement("span", {
                        className: "w-1.5 h-1.5 rounded-full " + (isAgentActive ? "bg-emerald-400 zfk-pulse-active" : "bg-slate-500")
                      }),
                      isAgentActive ? "Active" : "Idle"
                    ),
                    isAgentActive && (currentTask || activeSession) && React.createElement(
                      "button",
                      {
                        type: "button",
                        disabled: stoppingSessionId === ((activeSession && activeSession.session_id) || (currentTask && currentTask.id)),
                        className: "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-rose-950/70 hover:bg-rose-900 text-rose-300 border border-rose-800/80 hover:border-rose-800/60 transition-colors shadow-xs cursor-pointer disabled:opacity-50",
                        title: "Stop running AI session for this agent",
                        onClick: (e) => {
                          e.stopPropagation();
                          handleStopTaskSession(currentTask && currentTask.id, activeSession && activeSession.session_id);
                        }
                      },
                      React.createElement("span", { className: "text-[9px]" }, "⏹"),
                      React.createElement("span", null, stoppingSessionId === ((activeSession && activeSession.session_id) || (currentTask && currentTask.id)) ? "Stopping..." : "Stop")
                    )
                  )
                ),
                // Role description
                React.createElement("p", { className: "text-xs text-slate-400 leading-relaxed" }, meta.role),
                // Live Activity / Task Box
                React.createElement(
                  "div",
                  { className: "bg-slate-950/60 p-3 rounded-xl border border-slate-800/80 space-y-1.5" },
                  React.createElement(
                    "div",
                    { className: "text-[10px] font-semibold text-slate-400 uppercase tracking-wider flex items-center justify-between" },
                    React.createElement("span", null, isAgentActive ? "Current Work" : "Status"),
                    isAgentActive && React.createElement("span", { className: "text-emerald-400 font-mono text-[10px]" }, "Executing")
                  ),
                  currentTask
                    ? React.createElement(
                      "button",
                      {
                        type: "button",
                        className: "text-left text-xs font-semibold text-indigo-300 hover:text-indigo-200 transition-colors line-clamp-1 cursor-pointer",
                        onClick: () => {
                          setActiveView("board");
                          loadTaskDetails(currentTask.id);
                        }
                      },
                      "📋 " + currentTask.title + " ↗"
                    )
                    : activeSession
                      ? React.createElement(
                        "div",
                        { className: "text-xs text-slate-300 truncate", title: activeSession.last_action || activeSession.title },
                        "⚡ " + (activeSession.last_action || activeSession.title || "Working on session...")
                      )
                      : React.createElement(
                        "div",
                        { className: "text-xs text-slate-500 italic" },
                        "Ready for next dispatch cycle"
                      )
                )
              ),
              // Bottom stats
              React.createElement(
                "div",
                { className: "grid grid-cols-3 gap-2 pt-2 border-t border-slate-800/80 text-center" },
                React.createElement(
                  "div",
                  null,
                  React.createElement("span", { className: "text-[10px] text-slate-500 uppercase tracking-wider block" }, "Sessions"),
                  React.createElement("span", { className: "text-xs font-bold text-slate-200" }, agentSessions.length)
                ),
                React.createElement(
                  "div",
                  null,
                  React.createElement("span", { className: "text-[10px] text-slate-500 uppercase tracking-wider block" }, "Turns"),
                  React.createElement("span", { className: "text-xs font-bold text-amber-300" }, totalAgentTurns)
                ),
                React.createElement(
                  "div",
                  null,
                  React.createElement("span", { className: "text-[10px] text-slate-500 uppercase tracking-wider block" }, "State"),
                  React.createElement("span", { className: "text-xs font-bold " + (isAgentActive ? "text-emerald-400" : "text-slate-400") }, isAgentActive ? "Busy" : "Ready")
                )
              )
            );
          })
        ),

        // Section 2: Sub-Tab Switcher
        React.createElement(
          "div",
          { className: "flex items-center gap-2 border-b border-slate-800 pb-3" },
          React.createElement(
            "button",
            {
              type: "button",
              className: "px-4 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center gap-2 " +
                (agentsSubTab === "sessions"
                  ? "bg-indigo-600 text-white shadow-sm shadow-indigo-600/30"
                  : "bg-slate-900/60 text-slate-400 hover:text-slate-200 hover:bg-slate-800 border border-slate-800/80"),
              onClick: () => {
                setAgentsSubTab("sessions");
                loadSessions(selectedBoard);
              }
            },
            "💬 AI Sessions",
            React.createElement("span", {
              className: "px-2 py-0.5 rounded-full text-[10px] " +
                (agentsSubTab === "sessions" ? "bg-indigo-700 text-indigo-100" : "bg-slate-800 text-slate-400")
            }, boardFilteredSessions.length)
          ),
          React.createElement(
            "button",
            {
              type: "button",
              className: "px-4 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center gap-2 " +
                (agentsSubTab === "memory"
                  ? "bg-indigo-600 text-white shadow-sm shadow-indigo-600/30"
                  : "bg-slate-900/60 text-slate-400 hover:text-slate-200 hover:bg-slate-800 border border-slate-800/80"),
              onClick: () => {
                setAgentsSubTab("memory");
                loadMemories(selectedBoard);
              }
            },
            "🧠 Repository Memory",
            React.createElement("span", {
              className: "px-2 py-0.5 rounded-full text-[10px] " +
                (agentsSubTab === "memory" ? "bg-indigo-700 text-indigo-100" : "bg-slate-800 text-slate-400")
            }, boardMemories.length)
          )
        ),

        // Section 3: Sub-View Content
        agentsSubTab === "sessions"
          ? React.createElement(
            "div",
            { className: "space-y-6" },
            // Summary Metric Cards
            React.createElement(
              "div",
              { className: "grid grid-cols-2 sm:grid-cols-4 gap-3.5" },
              React.createElement(
                "div",
                { className: "bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-xl p-3.5 flex items-center gap-3 shadow-sm" },
                React.createElement("div", { className: "w-10 h-10 rounded-lg flex items-center justify-center text-lg shrink-0 bg-indigo-500/15 text-indigo-400 border border-indigo-500/25" }, "🤖"),
                React.createElement(
                  "div",
                  { className: "min-w-0" },
                  React.createElement("span", { className: "text-xl font-bold text-white tracking-tight leading-none block" }, totalCount),
                  React.createElement("span", { className: "text-[11px] text-slate-400 font-medium truncate mt-1 block" }, "Total AI Sessions")
                )
              ),
              React.createElement(
                "div",
                { className: "bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-xl p-3.5 flex items-center gap-3 shadow-sm" },
                React.createElement("div", { className: "w-10 h-10 rounded-lg flex items-center justify-center text-lg shrink-0 bg-emerald-500/15 text-emerald-400 border border-emerald-500/25" }, "⚡"),
                React.createElement(
                  "div",
                  { className: "min-w-0" },
                  React.createElement("span", { className: "text-xl font-bold text-emerald-400 tracking-tight leading-none block" }, ongoingCount),
                  React.createElement("span", { className: "text-[11px] text-slate-400 font-medium truncate mt-1 block" }, "Ongoing / Active")
                )
              ),
              React.createElement(
                "div",
                { className: "bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-xl p-3.5 flex items-center gap-3 shadow-sm" },
                React.createElement("div", { className: "w-10 h-10 rounded-lg flex items-center justify-center text-lg shrink-0 bg-slate-800/60 text-slate-300 border border-slate-700/50" }, "✅"),
                React.createElement(
                  "div",
                  { className: "min-w-0" },
                  React.createElement("span", { className: "text-xl font-bold text-white tracking-tight leading-none block" }, finishedCount),
                  React.createElement("span", { className: "text-[11px] text-slate-400 font-medium truncate mt-1 block" }, "Completed Sessions")
                )
              ),
              React.createElement(
                "div",
                { className: "bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-xl p-3.5 flex items-center gap-3 shadow-sm" },
                React.createElement("div", { className: "w-10 h-10 rounded-lg flex items-center justify-center text-lg shrink-0 bg-amber-500/15 text-amber-400 border border-amber-500/25" }, "🔄"),
                React.createElement(
                  "div",
                  { className: "min-w-0" },
                  React.createElement("span", { className: "text-xl font-bold text-amber-300 tracking-tight leading-none block" }, totalTurns),
                  React.createElement("span", { className: "text-[11px] text-slate-400 font-medium truncate mt-1 block" }, "Total Agent Turns")
                )
              )
            ),

            // Controls Bar: Agent Pills, Status Filter, Search
            React.createElement(
              "div",
              { className: "flex flex-col md:flex-row md:items-center justify-between gap-3 bg-slate-900/40 p-3 rounded-xl border border-slate-800/80" },
              // Agent Pills
              React.createElement(
                "div",
                { className: "flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0 zfk-scrollbar" },
                agentTabs.map(tab =>
                  React.createElement(
                    "button",
                    {
                      key: tab.id,
                      type: "button",
                      className: "px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 " +
                        (sessionsAgentFilter === tab.id
                          ? "bg-indigo-600 text-white shadow-xs"
                          : "bg-slate-800/60 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-700/60"),
                      onClick: () => setSessionsAgentFilter(tab.id)
                    },
                    tab.label,
                    React.createElement("span", { className: "text-[0.625rem] px-1.5 py-0.2 rounded-full " + (sessionsAgentFilter === tab.id ? "bg-indigo-700 text-indigo-100" : "bg-slate-700 text-slate-400") }, tab.count)
                  )
                )
              ),
              // Right Controls: Status & Search
              React.createElement(
                "div",
                { className: "flex items-center gap-2" },
                React.createElement(
                  "select",
                  {
                    className: "bg-slate-800 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer",
                    value: sessionsStatusFilter,
                    onChange: (e) => setSessionsStatusFilter(e.target.value)
                  },
                  React.createElement("option", { value: "all" }, "All Statuses"),
                  React.createElement("option", { value: "ongoing" }, "🟢 Ongoing"),
                  React.createElement("option", { value: "finished" }, "⚪ Finished")
                ),
                React.createElement(
                  "input",
                  {
                    type: "text",
                    placeholder: "Search sessions, models, tasks...",
                    className: "bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 w-48 md:w-56",
                    value: sessionsSearchQuery,
                    onChange: (e) => setSessionsSearchQuery(e.target.value)
                  }
                )
              )
            ),

            // Session Cards Grid
            effectiveSessions.length === 0
              ? React.createElement(
                "div",
                { className: "bg-slate-900/30 border border-dashed border-slate-800 rounded-2xl p-12 text-center" },
                React.createElement("div", { className: "w-12 h-12 rounded-full bg-slate-800/80 flex items-center justify-center text-2xl mx-auto mb-3 text-slate-500" }, "🤖"),
                React.createElement("h3", { className: "text-sm font-semibold text-slate-300" }, "No AI Sessions Found"),
                React.createElement("p", { className: "text-xs text-slate-500 mt-1 max-w-sm mx-auto" },
                  sessionsSearchQuery || sessionsAgentFilter !== "all" || sessionsStatusFilter !== "all"
                    ? "No sessions match your filter criteria. Try resetting the filters."
                    : (selectedBoard && selectedBoard !== "all")
                      ? "No AI agent sessions recorded yet for board '" + selectedBoard + "'. Sessions will appear as tasks run on this board."
                      : "AI agent sessions will appear here as Orchestrator, Builder, and Reviewer execute tasks."
                )
              )
              : React.createElement(
                "div",
                { className: "grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4" },
                effectiveSessions.map((s) => {
                  const isOngoing = s.status === "ongoing" || s.is_active;
                  const agentRole = s.agent || "zf-builder";
                  const agentBadge = agentRole === "zf-reviewer"
                    ? { icon: "🔍", label: "Reviewer", border: "border-cyan-500/30", bg: "bg-cyan-500/10 text-cyan-300" }
                    : agentRole === "zf-orchestrator"
                      ? { icon: "🧭", label: "Orchestrator", border: "border-indigo-500/30", bg: "bg-indigo-500/10 text-indigo-300" }
                      : { icon: "🔨", label: "Builder", border: "border-amber-500/30", bg: "bg-amber-500/10 text-amber-300" };

                  const lastUpdateTs = s.last_activity_at || s.ended_at || s.started_at;
                  const lastUpdateStr = lastUpdateTs ? timeAgo(lastUpdateTs) : null;
                  const lastUpdateFull = lastUpdateTs ? new Date(lastUpdateTs * 1000).toLocaleString() : null;

                  // Extract task ID and board slug
                  let matchedTaskId = s.task_id || null;
                  let matchedBoardSlug = s.board_slug || null;
                  if (!matchedTaskId) {
                    const cwdOrTitle = (s.cwd || "") + " " + (s.title || "");
                    const taskMatch = cwdOrTitle.match(/zf-[a-z0-9_-]+/i) || cwdOrTitle.match(/task-[a-z0-9_-]+/i);
                    if (taskMatch) {
                      matchedTaskId = taskMatch[0];
                    }
                  }
                  if (!matchedBoardSlug && matchedTaskId) {
                    const matchedTask = tasks.find(t => t.id && t.id.toLowerCase() === matchedTaskId.toLowerCase());
                    if (matchedTask && matchedTask.board_slug) {
                      matchedBoardSlug = matchedTask.board_slug;
                    }
                  }

                  const basePath = (typeof window !== "undefined" && window.__HERMES_BASE_PATH__)
                    ? ("/" + String(window.__HERMES_BASE_PATH__).replace(/^\/|\/$/g, ""))
                    : "";
                  const chatUrl = basePath + "/chat?resume=" + encodeURIComponent(s.session_id) + (s.agent ? "&profile=" + encodeURIComponent(s.agent) : "");

                  return React.createElement(
                    "div",
                    {
                      key: s.session_id,
                      className: "bg-slate-900/70 backdrop-blur-md border border-slate-800/90 hover:border-slate-700/80 rounded-xl p-4 transition-all duration-150 shadow-sm space-y-3 flex flex-col justify-between"
                    },
                    React.createElement(
                      "div",
                      { className: "space-y-2.5" },
                      // Card Top Row
                      React.createElement(
                        "div",
                        { className: "flex items-center justify-between gap-2" },
                        React.createElement(
                          "div",
                          { className: "flex items-center gap-2" },
                          React.createElement(
                            "span",
                            { className: "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-semibold border " + agentBadge.bg + " " + agentBadge.border },
                            agentBadge.icon + " " + (s.agent_label || agentBadge.label)
                          ),
                          React.createElement(
                            "span",
                            { className: "inline-flex items-center gap-1 text-[11px] font-medium " + (isOngoing ? "text-emerald-400" : "text-slate-400") },
                            React.createElement("span", { className: "w-2 h-2 rounded-full " + (isOngoing ? "bg-emerald-400 zfk-pulse-active" : "bg-slate-500") }),
                            isOngoing ? "Ongoing" : "Finished"
                          ),
                          isOngoing && React.createElement(
                            "button",
                            {
                              type: "button",
                              disabled: stoppingSessionId === (s.session_id || matchedTaskId),
                              className: "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-rose-950/70 hover:bg-rose-900 text-rose-300 border border-rose-800/80 hover:border-rose-800/60 transition-colors shadow-xs cursor-pointer disabled:opacity-50",
                              title: "Kill / Stop running AI session",
                              onClick: (e) => {
                                e.stopPropagation();
                                handleStopTaskSession(matchedTaskId, s.session_id);
                              }
                            },
                            React.createElement("span", { className: "text-[9px]" }, "⏹"),
                            React.createElement("span", null, stoppingSessionId === (s.session_id || matchedTaskId) ? "Stopping..." : "Stop")
                          )
                        ),
                        React.createElement(
                          "div",
                          { className: "flex flex-col shrink-0", style: { alignItems: "flex-end", textAlign: "right" } },
                          lastUpdateStr
                            ? React.createElement(
                              "span",
                              {
                                className: "text-[11px] text-slate-300 font-mono flex items-center gap-1",
                                title: lastUpdateFull ? ("Last updated: " + lastUpdateFull) : undefined
                              },
                              React.createElement("span", { className: "text-slate-500 text-[10px]" }, "Updated"),
                              lastUpdateStr
                            )
                            : React.createElement("span", { className: "text-[11px] text-slate-400 font-mono" }, "No activity"),
                          s.duration_seconds != null && s.duration_seconds > 0
                            ? React.createElement(
                              "span",
                              { className: "text-[10px] text-slate-500 font-mono" },
                              `${Math.floor(s.duration_seconds / 60)}m ${s.duration_seconds % 60}s duration`
                            )
                            : null
                        )
                      ),

                      // Title & Associated Task
                      React.createElement(
                        "div",
                        { className: "space-y-1" },
                        React.createElement(
                          "div",
                          { className: "text-xs font-semibold text-white line-clamp-1", title: s.title },
                          s.title || "Autonomous Agent Execution"
                        ),
                        React.createElement(
                          "div",
                          { className: "flex flex-wrap items-center gap-2 pt-0.5" },
                          matchedTaskId &&
                          React.createElement(
                            "button",
                            {
                              type: "button",
                              className: "inline-flex items-center gap-1 text-[11px] font-mono text-indigo-400 hover:text-indigo-300 hover:underline cursor-pointer",
                              onClick: () => {
                                setActiveView("board");
                                loadTaskDetails(matchedTaskId);
                              }
                            },
                            "📋 Task " + matchedTaskId + " ↗"
                          ),
                          (selectedBoard === "all" && matchedBoardSlug) &&
                          React.createElement(
                            "span",
                            {
                              className: "inline-flex items-center gap-1 text-sky-400 font-mono text-[10px] bg-sky-950/50 border border-sky-800/50 px-1.5 py-0.5 rounded truncate max-w-[150px]",
                              title: "Board: " + matchedBoardSlug
                            },
                            "🏷️ " + matchedBoardSlug
                          )
                        )
                      ),

                      // Telemetry Grid
                      React.createElement(
                        "div",
                        { className: "grid grid-cols-3 gap-2 bg-slate-950/60 p-2 rounded-lg border border-slate-800/80 text-center" },
                        React.createElement(
                          "div",
                          null,
                          React.createElement("span", { className: "text-[10px] text-slate-500 uppercase tracking-wider block" }, "Turns"),
                          React.createElement("span", { className: "text-xs font-bold text-slate-200" }, s.turn_count || 0)
                        ),
                        React.createElement(
                          "div",
                          null,
                          React.createElement("span", { className: "text-[10px] text-slate-500 uppercase tracking-wider block" }, "Tool Calls"),
                          React.createElement("span", { className: "text-xs font-bold text-indigo-300" }, s.tool_calls_count || 0)
                        ),
                        React.createElement(
                          "div",
                          null,
                          React.createElement("span", { className: "text-[10px] text-slate-500 uppercase tracking-wider block" }, "Messages"),
                          React.createElement("span", { className: "text-xs font-bold text-slate-200" }, s.message_count || 0)
                        )
                      ),

                      // Last Action / Snippet
                      s.last_action &&
                      React.createElement(
                        "div",
                        { className: "text-[11px] text-slate-400 bg-slate-950/40 px-2.5 py-1.5 rounded-lg border border-slate-800/60 font-mono truncate", title: s.last_action },
                        "⚡ " + s.last_action
                      )
                    ),

                    // Bottom Action: Session ID & Open Chat
                    React.createElement(
                      "div",
                      { className: "pt-2 border-t border-slate-800/80 flex items-center justify-between gap-2" },
                      React.createElement(
                        "div",
                        { className: "flex items-center gap-1.5 min-w-0" },
                        React.createElement(
                          "span",
                          {
                            className: "text-xs font-mono font-medium text-purple-300 truncate max-w-[160px]",
                            title: "Session ID: " + s.session_id
                          },
                          s.session_id
                        ),
                        lastUpdateStr &&
                        React.createElement(
                          "span",
                          {
                            className: "text-[10px] text-slate-500 font-mono shrink-0 flex items-center gap-1",
                            title: lastUpdateFull ? ("Last updated: " + lastUpdateFull) : undefined
                          },
                          "• updated " + lastUpdateStr
                        )
                      ),
                      React.createElement(
                        "a",
                        {
                          href: chatUrl,
                          target: "_blank",
                          rel: "noreferrer",
                          className: "inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium bg-indigo-600/90 hover:bg-indigo-600 text-white transition-colors cursor-pointer shadow-xs shrink-0"
                        },
                        "Open Chat ↗"
                      )
                    )
                  );
                })
              )
          )
          : React.createElement(
            "div",
            { className: "space-y-6" },
            // Memory Action Bar: Category Filter Pills, Search, Add Memory
            React.createElement(
              "div",
              { className: "flex flex-col md:flex-row md:items-center justify-between gap-3 bg-slate-900/40 p-3 rounded-xl border border-slate-800/80" },
              // Category Pills
              React.createElement(
                "div",
                { className: "flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0 zfk-scrollbar" },
                memoryCategories.map(cat =>
                  React.createElement(
                    "button",
                    {
                      key: cat.id,
                      type: "button",
                      className: "px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 " +
                        (memoryCategoryFilter === cat.id
                          ? "bg-indigo-600 text-white shadow-xs"
                          : "bg-slate-800/60 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-700/60"),
                      onClick: () => setMemoryCategoryFilter(cat.id)
                    },
                    cat.icon + " " + cat.label,
                    React.createElement("span", {
                      className: "text-[0.625rem] px-1.5 py-0.2 rounded-full " +
                        (memoryCategoryFilter === cat.id ? "bg-indigo-700 text-indigo-100" : "bg-slate-700 text-slate-400")
                    }, cat.count)
                  )
                )
              ),
              // Search & Actions
              (() => {
                const currentBoard = boards.find(b => b.slug === selectedBoard);
                const isAutoRecordOn = currentBoard ? (currentBoard.auto_record_memory !== false) : true;
                return React.createElement(
                  "div",
                  { className: "flex flex-wrap items-center gap-2" },
                  currentBoard && React.createElement(
                    "button",
                    {
                      type: "button",
                      className: "inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium border transition-all cursor-pointer shrink-0 " +
                        (isAutoRecordOn
                          ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-300 hover:text-white hover:bg-slate-800/80 shadow-xs"
                          : "bg-slate-800/80 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800"),
                      title: "Click to toggle automatic memory recording from reviewer feedback for " + currentBoard.slug,
                      onClick: async () => {
                        const nextVal = !isAutoRecordOn;
                        try {
                          await fetchJSON(API_BASE + "/boards/" + encodeURIComponent(currentBoard.slug), {
                            method: "PATCH",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ auto_record_memory: nextVal })
                          });
                          showToast(`Auto-record memory ${nextVal ? "enabled" : "disabled"} for ${currentBoard.slug}`, "success");
                          await loadBoards();
                        } catch (err) {
                          showToast("Failed to toggle auto-record: " + (err.message || String(err)), "error");
                        }
                      }
                    },
                    React.createElement("span", {
                      className: "w-2 h-2 rounded-full " + (isAutoRecordOn ? "bg-emerald-400 zfk-pulse-active" : "bg-slate-500")
                    }),
                    "Auto-Record: " + (isAutoRecordOn ? "ON" : "OFF")
                  ),
                  React.createElement(
                    "input",
                    {
                      type: "text",
                      placeholder: "Search memories, tags, author...",
                      className: "bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 w-44 md:w-56",
                      value: memorySearchQuery,
                      onChange: (e) => setMemorySearchQuery(e.target.value)
                    }
                  ),
                  React.createElement(
                    "button",
                    {
                      type: "button",
                      className: "inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-xs shadow-indigo-600/30 transition-all cursor-pointer shrink-0",
                      onClick: () => setShowAddMemoryModal(true)
                    },
                    "➕ Add Memory"
                  )
                );
              })()
            ),

            // Memory Cards Grid
            filteredMemories.length === 0
              ? React.createElement(
                "div",
                { className: "bg-slate-900/30 border border-dashed border-slate-800 rounded-2xl p-12 text-center" },
                React.createElement("div", { className: "w-12 h-12 rounded-full bg-slate-800/80 flex items-center justify-center text-2xl mx-auto mb-3 text-slate-500" }, "🧠"),
                React.createElement("h3", { className: "text-sm font-semibold text-slate-300" }, "No Repository Memories Found"),
                React.createElement("p", { className: "text-xs text-slate-500 mt-1 max-w-md mx-auto" },
                  memorySearchQuery || memoryCategoryFilter !== "all"
                    ? "No memories match your filter criteria. Try resetting the category or search."
                    : "Repository memories persist architectural decisions, conventions, gotchas, and rejected paths for " + (selectedBoard || "this board") + " so future agent workers avoid repeat mistakes."
                ),
                React.createElement(
                  "button",
                  {
                    type: "button",
                    className: "mt-4 inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-xs transition-all cursor-pointer",
                    onClick: () => setShowAddMemoryModal(true)
                  },
                  "➕ Record First Memory"
                )
              )
              : React.createElement(
                "div",
                { className: "grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4" },
                filteredMemories.map((m) => {
                  const catBadges = {
                    decision: { icon: "💡", label: "Decision", bg: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30" },
                    gotcha: { icon: "⚠️", label: "Gotcha", bg: "bg-amber-500/10 text-amber-300 border-amber-500/30" },
                    convention: { icon: "📐", label: "Convention", bg: "bg-sky-500/10 text-sky-300 border-sky-500/30" },
                    rejected_path: { icon: "🚫", label: "Rejected Path", bg: "bg-purple-500/10 text-purple-300 border-purple-500/30" },
                    general: { icon: "📝", label: "General", bg: "bg-slate-700/40 text-slate-300 border-slate-600/50" }
                  };
                  const badge = catBadges[m.category] || catBadges.general;

                  return React.createElement(
                    "div",
                    {
                      key: m.id,
                      className: "bg-slate-900/70 backdrop-blur-md border border-slate-800/90 hover:border-slate-700/80 rounded-xl p-4 transition-all duration-150 shadow-sm flex flex-col justify-between space-y-3"
                    },
                    React.createElement(
                      "div",
                      { className: "space-y-2.5" },
                      // Card Top Row: Badge, Created At, Delete Button
                      React.createElement(
                        "div",
                        { className: "flex items-center justify-between gap-2" },
                        React.createElement(
                          "span",
                          { className: "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-semibold border " + badge.bg },
                          badge.icon + " " + badge.label
                        ),
                        React.createElement(
                          "div",
                          { className: "flex items-center gap-2" },
                          React.createElement(
                            "span",
                            { className: "text-[11px] text-slate-500 font-mono" },
                            timeAgo(m.created_at)
                          ),
                          React.createElement(
                            "button",
                            {
                              type: "button",
                              title: "Delete Memory",
                              className: "text-slate-500 hover:text-rose-300 p-1 rounded-md hover:bg-rose-500/20 transition-colors text-xs cursor-pointer",
                              onClick: () => handleDeleteMemory(m.id)
                            },
                            "🗑️"
                          )
                        )
                      ),
                      // Content
                      React.createElement(
                        "div",
                        { className: "text-xs text-slate-200 leading-relaxed whitespace-pre-wrap select-text font-normal" },
                        m.content
                      )
                    ),
                    // Card Bottom Row: Author, Tags, Task Link
                    React.createElement(
                      "div",
                      { className: "pt-2.5 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-2" },
                      React.createElement(
                        "div",
                        { className: "flex flex-wrap items-center gap-1.5" },
                        selectedBoard === "all" && m.board_slug && React.createElement(
                          "span",
                          { className: "inline-flex items-center gap-1 text-[10px] text-sky-400 font-mono bg-sky-950/60 px-2 py-0.5 rounded-md border border-sky-800/60" },
                          "📋 " + m.board_slug
                        ),
                        React.createElement(
                          "span",
                          { className: "inline-flex items-center gap-1 text-[10px] text-slate-400 font-mono bg-slate-950/60 px-2 py-0.5 rounded-md border border-slate-800" },
                          "👤 " + (m.author || "user")
                        ),
                        (m.tags || []).map((t, idx) =>
                          React.createElement(
                            "span",
                            {
                              key: idx,
                              className: "text-[10px] font-mono px-1.5 py-0.5 rounded-md bg-indigo-500/10 text-indigo-300 border border-indigo-500/20"
                            },
                            "#" + t
                          )
                        )
                      ),
                      m.task_id &&
                      React.createElement(
                        "button",
                        {
                          type: "button",
                          className: "inline-flex items-center gap-1 text-[11px] font-mono text-indigo-400 hover:text-indigo-300 hover:underline cursor-pointer",
                          onClick: () => {
                            setActiveView("board");
                            loadTaskDetails(m.task_id);
                          }
                        },
                        "📋 " + m.task_id + " ↗"
                      )
                    )
                  );
                })
              )
          )
      );
}