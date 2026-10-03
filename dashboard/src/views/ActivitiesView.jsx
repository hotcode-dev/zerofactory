import React from "react";
import { timeAgo } from "../utils/formatters.js";

export function ActivitiesView(props) {
  const {
    activities,
    activitiesTotal,
    activitiesAgents,
    activitiesStats,
    activitiesFilterOptions,
    activitiesLoading,
    activityActorFilter,
    setActivityActorFilter,
    activityActionFilter,
    setActivityActionFilter,
    activityBoardFilter,
    setActivityBoardFilter,
    activityAssigneeFilter,
    setActivityAssigneeFilter,
    activitySearchQuery,
    setActivitySearchQuery,
    loadActivities,
    boards,
    setActiveView,
    loadTaskDetails,
    tasks,
    liveAgents = [],
    effectiveActivities = [],
    effectiveStats = {},
    effectiveFilterOptions = { actors: [], actions: [], boards: [] },
    activityPage = 0,
    setActivityPage = () => {},
    activityLimit = 15,
    activityViewMode = "timeline",
    setActivityViewMode = () => {},
    autoRefresh = false,
    setAutoRefresh = () => {},
    expandedActivityId = null,
    setExpandedActivityId = () => {},
    isDispatching = false,
    handleRunDispatcher = () => {}
  } = props;

      const getActionBadge = (action) => {
        switch (action) {
          case "start":
            return { label: "Dispatched", icon: "🚀", bg: "bg-indigo-500/15 text-indigo-300 border-indigo-500/30" };
          case "worker_done":
            return { label: "Completed", icon: "✅", bg: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30" };
          case "worker_failed":
            return { label: "Worker Failed", icon: "❌", bg: "bg-rose-500/15 text-rose-300 border-rose-500/30" };
          case "worker_timeout":
            return { label: "Timeout", icon: "⏱️", bg: "bg-red-500/15 text-red-300 border-red-500/30" };
          case "worker_lost":
            return { label: "Worker Lost", icon: "⚠️", bg: "bg-amber-500/15 text-amber-300 border-amber-500/30" };
          case "pr_conflict":
            return { label: "Git Conflict", icon: "🛑", bg: "bg-amber-500/15 text-amber-300 border-amber-500/30" };
          case "conflict_fixing":
            return { label: "Fixing Conflict", icon: "🔧", bg: "bg-amber-500/15 text-amber-300 border-amber-500/30" };
          case "conflict_resolved":
            return { label: "Conflict Resolved", icon: "🛠️", bg: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30" };
          case "pr_conflict_failed":
            return { label: "Conflict Failed", icon: "💥", bg: "bg-rose-500/15 text-rose-300 border-rose-500/30" };
          case "conflict_unverifiable":
            return { label: "Conflict Unverifiable", icon: "⚠️", bg: "bg-rose-500/15 text-rose-300 border-rose-500/30" };
          case "pr_opened":
            return { label: "PR Opened", icon: "🔍", bg: "bg-blue-500/15 text-blue-300 border-blue-500/30" };
          case "approved":
            return { label: "PR Approved", icon: "👁️", bg: "bg-purple-500/15 text-purple-300 border-purple-500/30" };
          case "changes_requested":
            return { label: "Changes Req.", icon: "💬", bg: "bg-orange-500/15 text-orange-300 border-orange-500/30" };
          case "merged":
            return { label: "PR Merged", icon: "🎉", bg: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30" };
          case "promote":
            return { label: "Promoted Ready", icon: "⚡", bg: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30" };
          case "unblock":
            return { label: "Unblocked", icon: "🔓", bg: "bg-teal-500/15 text-teal-300 border-teal-500/30" };
          case "move":
            return { label: "Status Move", icon: "📦", bg: "bg-slate-500/15 text-slate-300 border-slate-500/30" };
          case "create":
            return { label: "Created", icon: "✨", bg: "bg-sky-500/15 text-sky-300 border-sky-500/30" };
          case "comment":
            return { label: "Comment", icon: "💬", bg: "bg-violet-500/15 text-violet-300 border-violet-500/30" };
          default:
            return { label: action || "Event", icon: "⚡", bg: "bg-slate-700/40 text-slate-300 border-slate-600/40" };
        }
      };

      const getActorBadge = (actor) => {
        if (actor === "zf-builder") {
          return { label: "zf-builder", icon: "🔨", role: "Builder", color: "text-amber-300 bg-amber-500/10 border-amber-500/30" };
        }
        if (actor === "zf-reviewer") {
          return { label: "zf-reviewer", icon: "🔍", role: "Reviewer", color: "text-purple-300 bg-purple-500/10 border-purple-500/30" };
        }
        if (actor === "zf-orchestrator") {
          return { label: "zf-orchestrator", icon: "🎯", role: "Orchestrator", color: "text-indigo-300 bg-indigo-500/10 border-indigo-500/30" };
        }
        if (actor === "dispatcher") {
          return { label: "dispatcher", icon: "⚙️", role: "Dispatcher Engine", color: "text-cyan-300 bg-cyan-500/10 border-cyan-500/30" };
        }
        if (actor === "user") {
          return { label: "user", icon: "👤", role: "User", color: "text-sky-300 bg-sky-500/10 border-sky-500/30" };
        }
        return { label: "other", icon: "📦", role: "Other", color: "text-slate-400 bg-slate-700/30 border-slate-600/30" };
      };

      const hasActiveClientFilters = activityActorFilter !== "all" || activityActionFilter !== "all" || activityBoardFilter !== "all" || Boolean(activitySearchQuery.trim());
      const effectiveTotal = hasActiveClientFilters ? effectiveActivities.length : (activitiesTotal || effectiveActivities.length);
      const totalPages = Math.ceil(effectiveTotal / activityLimit) || 1;
      const startIdx = effectiveTotal === 0 ? 0 : activityPage * activityLimit + 1;
      const endIdx = Math.min((activityPage + 1) * activityLimit, effectiveTotal);

      return React.createElement(
        "div",
        { className: "space-y-6 pb-12 max-w-[1600px] mx-auto" },

        // 1. Hero Header & Agent Telemetry Overview
        React.createElement(
          "div",
          { className: "relative overflow-hidden bg-gradient-to-br from-indigo-950/70 via-slate-900/90 to-purple-950/60 border border-slate-700/90 rounded-2xl p-6 md:p-8 shadow-2xl space-y-6" },
          React.createElement(
            "div",
            { className: "flex flex-col md:flex-row md:items-center justify-between gap-4 relative z-10" },
            React.createElement(
              "div",
              { className: "space-y-2" },
              React.createElement(
                "div",
                { className: "flex items-center gap-2.5 flex-wrap" },
                React.createElement("span", { className: "px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-indigo-900/80 text-indigo-100 border border-indigo-500/60 font-mono shadow-xs" }, "Live Telemetry Feed"),
                React.createElement(
                  "span",
                  { className: "px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-emerald-900/80 text-emerald-100 border border-emerald-500/60 font-mono shadow-xs flex items-center gap-1.5" },
                  React.createElement("span", { className: "w-1.5 h-1.5 rounded-full bg-emerald-400 zfk-pulse-active" }),
                  "Real-Time Stream"
                )
              ),
              React.createElement(
                "h2",
                { className: "text-2xl md:text-3xl font-extrabold text-white tracking-tight m-0 flex items-center gap-2.5" },
                "⚡ Agent Recent Activities"
              ),
              React.createElement(
                "p",
                { className: "text-xs md:text-sm text-slate-200 max-w-3xl leading-relaxed m-0 font-normal" },
                "Live execution log, process dispatch states, Git worktree lifecycle events, PR review outcomes, and tool invocation telemetry across all autonomous Zero Factory specialists."
              )
            ),
            React.createElement(
              "div",
              { className: "flex items-center gap-2.5 shrink-0 flex-wrap" },
              React.createElement(
                "button",
                {
                  type: "button",
                  className: "inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-600/80 shadow-md transition-all cursor-pointer",
                  onClick: () => loadActivities()
                },
                React.createElement("span", { className: activitiesLoading ? "zfk-spinning" : "" }, "🔄"),
                "Refresh Feed"
              ),
              React.createElement(
                "button",
                {
                  type: "button",
                  className: "inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/30 transition-all cursor-pointer " +
                    (isDispatching ? "opacity-75 cursor-not-allowed" : ""),
                  disabled: isDispatching,
                  onClick: async () => {
                    await handleRunDispatcher();
                    loadActivities();
                  }
                },
                isDispatching ? "⏳ Running..." : "⚡ Run Dispatcher"
              ),
              React.createElement(
                "button",
                {
                  type: "button",
                  className: "inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold bg-slate-800/90 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-all cursor-pointer",
                  onClick: () => setActiveView("board")
                },
                "📋 Kanban Board"
              )
            )
          ),

          // Agent Specialist Status Cards Grid
          React.createElement(
            "div",
            { className: "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 pt-2" },
            liveAgents.map((agent) => {
              const b = getActorBadge(agent.id);
              const isAgentActive = agent.status === "active";
              const isAgentStuck = agent.status === "stuck";
              const currTask = agent.current_task;
              const sess = agent.session_progress;
              const lastAct = agent.last_activity;

              return React.createElement(
                "div",
                {
                  key: agent.id,
                  className: "bg-slate-900/85 backdrop-blur-md border rounded-xl p-4 flex flex-col justify-between gap-3 shadow-md transition-all duration-150 " +
                    (isAgentActive
                      ? "border-emerald-500/50 shadow-emerald-950/30 ring-1 ring-emerald-500/30"
                      : isAgentStuck
                        ? "border-rose-500/50 shadow-rose-950/30 ring-1 ring-rose-500/30"
                        : "border-slate-800 hover:border-slate-700")
                },
                // Top row: Avatar, Name, Status Pill
                React.createElement(
                  "div",
                  { className: "flex items-start justify-between gap-2" },
                  React.createElement(
                    "div",
                    { className: "flex items-center gap-2.5 min-w-0" },
                    React.createElement("div", { className: "w-8 h-8 rounded-lg flex items-center justify-center text-sm shrink-0 " + b.color }, b.icon),
                    React.createElement(
                      "div",
                      { className: "min-w-0" },
                      React.createElement("h4", { className: "text-xs font-bold text-white truncate m-0 font-mono" }, agent.id),
                      React.createElement("p", { className: "text-[11px] text-slate-400 truncate m-0" }, agent.role || b.role)
                    )
                  ),
                  isAgentActive
                    ? React.createElement(
                      "span",
                      { className: "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 shrink-0" },
                      React.createElement("span", { className: "w-1.5 h-1.5 rounded-full bg-emerald-400 zfk-pulse-active" }),
                      "Active"
                    )
                    : isAgentStuck
                      ? React.createElement(
                        "span",
                        { className: "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/15 text-rose-400 border border-rose-500/30 shrink-0" },
                        "⚠️ Stuck"
                      )
                      : React.createElement(
                        "span",
                        { className: "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-800 text-slate-400 border border-slate-700 shrink-0" },
                        "⚪ Idle"
                      )
                ),

                // Middle: Current Task or Latest Action
                React.createElement(
                  "div",
                  { className: "space-y-1.5 bg-slate-950/60 rounded-lg p-2.5 border border-slate-800/70 text-xs min-h-[58px] flex flex-col justify-center" },
                  currTask
                    ? React.createElement(
                      "div",
                      { className: "space-y-1" },
                      React.createElement(
                        "div",
                        { className: "flex items-center gap-1.5" },
                        React.createElement("span", { className: "text-[10px] font-bold uppercase tracking-wider text-amber-400" }, "Running Task:"),
                        React.createElement("span", { className: "text-[10px] font-mono px-1 rounded bg-indigo-900/60 text-indigo-200 border border-indigo-700/50 font-bold" }, currTask.priority || "P2")
                      ),
                      React.createElement(
                        "button",
                        {
                          type: "button",
                          className: "text-left text-xs font-semibold text-indigo-300 hover:text-indigo-200 hover:underline truncate block w-full cursor-pointer",
                          onClick: () => loadTaskDetails(currTask.id),
                          title: currTask.title
                        },
                        `#${currTask.id} ${currTask.title}`
                      ),
                      sess &&
                      React.createElement(
                        "div",
                        { className: "text-[10px] text-slate-400 flex items-center gap-2 pt-0.5" },
                        React.createElement("span", null, `💬 ${sess.turn_count || 0} turns`),
                        React.createElement("span", null, `🔧 ${sess.tool_calls_count || 0} tools`),
                        currTask.running_seconds > 0 &&
                        React.createElement("span", { className: "text-emerald-400 font-medium" }, `${Math.floor(currTask.running_seconds / 60)}m active`)
                      )
                    )
                    : lastAct
                      ? React.createElement(
                        "div",
                        { className: "space-y-0.5" },
                        React.createElement(
                          "div",
                          { className: "flex items-center justify-between text-[10px] text-slate-400" },
                          React.createElement("span", { className: "font-semibold uppercase tracking-wider text-slate-300" }, "Latest Activity:"),
                          React.createElement("span", null, timeAgo(lastAct.created_at))
                        ),
                        React.createElement(
                          "p",
                          { className: "text-xs text-slate-300 truncate m-0", title: lastAct.details || lastAct.action },
                          lastAct.action.replace("_", " ") + (lastAct.details ? `: ${lastAct.details}` : "")
                        )
                      )
                      : React.createElement("p", { className: "text-xs text-slate-500 m-0 italic" }, "Awaiting task dispatch")
                ),

                // Bottom row: Today's actions & quick filter button
                React.createElement(
                  "div",
                  { className: "flex items-center justify-between text-[11px] text-slate-400 pt-1 border-t border-slate-800/80" },
                  React.createElement("span", null, `${agent.actions_today || 0} actions today`),
                  React.createElement(
                    "button",
                    {
                      type: "button",
                      className: "text-indigo-400 hover:text-indigo-300 text-[11px] font-semibold transition-colors cursor-pointer",
                      onClick: () => {
                        setActivityActorFilter(agent.id);
                        setActivityPage(0);
                      }
                    },
                    activityActorFilter === agent.id ? "✓ Filtering" : "Filter →"
                  )
                )
              );
            })
          )
        ),

        // 2. Metrics KPI Row
        React.createElement(
          "div",
          { className: "grid grid-cols-2 sm:grid-cols-4 gap-3.5" },
          React.createElement(
            "div",
            { className: "bg-slate-900/70 border border-slate-800/90 rounded-xl p-3.5 flex items-center gap-3.5 shadow-sm" },
            React.createElement("div", { className: "w-10 h-10 rounded-xl flex items-center justify-center text-lg shrink-0 bg-indigo-500/15 text-indigo-400" }, "📋"),
            React.createElement(
              "div",
              { className: "flex flex-col min-w-0" },
              React.createElement("span", { className: "text-xl font-extrabold text-white tracking-tight leading-none" }, effectiveStats.total_activities || effectiveTotal || 0),
              React.createElement("span", { className: "text-xs text-slate-400 font-medium truncate mt-1" }, "Total Logged Events")
            )
          ),
          React.createElement(
            "div",
            { className: "bg-slate-900/70 border border-slate-800/90 rounded-xl p-3.5 flex items-center gap-3.5 shadow-sm" },
            React.createElement("div", { className: "w-10 h-10 rounded-xl flex items-center justify-center text-lg shrink-0 bg-emerald-500/15 text-emerald-400" }, "⚡"),
            React.createElement(
              "div",
              { className: "flex flex-col min-w-0" },
              React.createElement("span", { className: "text-xl font-extrabold text-white tracking-tight leading-none" }, effectiveStats.active_agents || 0),
              React.createElement("span", { className: "text-xs text-slate-400 font-medium truncate mt-1" }, "Active Specialists")
            )
          ),
          React.createElement(
            "div",
            { className: "bg-slate-900/70 border border-slate-800/90 rounded-xl p-3.5 flex items-center gap-3.5 shadow-sm" },
            React.createElement("div", { className: "w-10 h-10 rounded-xl flex items-center justify-center text-lg shrink-0 bg-purple-500/15 text-purple-400" }, "🕒"),
            React.createElement(
              "div",
              { className: "flex flex-col min-w-0" },
              React.createElement("span", { className: "text-xl font-extrabold text-white tracking-tight leading-none" }, effectiveStats.actions_today || 0),
              React.createElement("span", { className: "text-xs text-slate-400 font-medium truncate mt-1" }, "Actions Past 24h")
            )
          ),
          React.createElement(
            "div",
            { className: "bg-slate-900/70 border border-slate-800/90 rounded-xl p-3.5 flex items-center gap-3.5 shadow-sm" },
            React.createElement("div", { className: "w-10 h-10 rounded-xl flex items-center justify-center text-lg shrink-0 bg-amber-500/15 text-amber-400" }, "🎯"),
            React.createElement(
              "div",
              { className: "flex flex-col min-w-0" },
              React.createElement(
                "span",
                { className: "text-xl font-extrabold text-white tracking-tight leading-none" },
                (effectiveStats.action_breakdown && effectiveStats.action_breakdown.worker_done) || 0
              ),
              React.createElement("span", { className: "text-xs text-slate-400 font-medium truncate mt-1" }, "Tasks Completed")
            )
          )
        ),

        // 3. Interactive Filter & Search Toolbar
        React.createElement(
          "div",
          { className: "bg-slate-900/80 border border-slate-800 rounded-2xl p-4 shadow-md space-y-3.5" },
          React.createElement(
            "div",
            { className: "flex flex-col lg:flex-row lg:items-center justify-between gap-3" },
            // Left Filters: Actor, Action, Board
            React.createElement(
              "div",
              { className: "flex flex-wrap items-center gap-2.5" },
              // Actor Filter
              React.createElement(
                "select",
                {
                  className: "bg-slate-950 border border-slate-700/80 rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer",
                  value: activityActorFilter,
                  onChange: (e) => {
                    setActivityActorFilter(e.target.value);
                    setActivityPage(0);
                  }
                },
                React.createElement("option", { value: "all" }, "🤖 All Agents / Actors"),
                (effectiveFilterOptions.actors || []).map((act) =>
                  React.createElement("option", { key: act, value: act }, `Agent: ${act}`)
                )
              ),

              // Action Filter
              React.createElement(
                "select",
                {
                  className: "bg-slate-950 border border-slate-700/80 rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer",
                  value: activityActionFilter,
                  onChange: (e) => {
                    setActivityActionFilter(e.target.value);
                    setActivityPage(0);
                  }
                },
                React.createElement("option", { value: "all" }, "⚡ All Event Types"),
                (effectiveFilterOptions.actions || []).map((act) => {
                  const b = getActionBadge(act);
                  return React.createElement("option", { key: act, value: act }, `${b.icon} ${act} (${b.label})`);
                })
              ),

              // Board Filter
              React.createElement(
                "select",
                {
                  className: "bg-slate-950 border border-slate-700/80 rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer",
                  value: activityBoardFilter,
                  onChange: (e) => {
                    setActivityBoardFilter(e.target.value);
                    setActivityPage(0);
                  }
                },
                React.createElement("option", { value: "all" }, "📦 All Boards"),
                (effectiveFilterOptions.boards || []).map((b) =>
                  React.createElement("option", { key: b, value: b }, `Board: ${b}`)
                )
              ),

              // Clear Filters button if any active
              (activityActorFilter !== "all" || activityActionFilter !== "all" || activityBoardFilter !== "all" || activitySearchQuery.trim()) &&
              React.createElement(
                "button",
                {
                  type: "button",
                  className: "text-xs font-semibold text-rose-400 hover:text-rose-300 px-2 py-1 rounded hover:bg-rose-950/30 transition-colors cursor-pointer",
                  onClick: () => {
                    setActivityActorFilter("all");
                    setActivityActionFilter("all");
                    setActivityBoardFilter("all");
                    setActivitySearchQuery("");
                    setActivityPage(0);
                  }
                },
                "✕ Reset Filters"
              )
            ),

            // Right Search & View Mode Switcher
            React.createElement(
              "div",
              { className: "flex items-center gap-2.5 flex-wrap" },
              // Search Input
              React.createElement(
                "div",
                { className: "relative min-w-[240px] flex-1 sm:flex-initial" },
                React.createElement("input", {
                  type: "text",
                  className: "w-full bg-slate-950 border border-slate-700/80 rounded-lg pl-8 pr-7 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500",
                  placeholder: "Search details, task ID, title...",
                  value: activitySearchQuery,
                  onChange: (e) => {
                    setActivitySearchQuery(e.target.value);
                    setActivityPage(0);
                  }
                }),
                React.createElement("span", { className: "absolute left-2.5 top-1.5 text-slate-500 text-xs" }, "🔍"),
                activitySearchQuery &&
                React.createElement(
                  "button",
                  {
                    type: "button",
                    className: "absolute right-2.5 top-1.5 text-slate-500 hover:text-slate-300 text-xs cursor-pointer",
                    onClick: () => {
                      setActivitySearchQuery("");
                      setActivityPage(0);
                    }
                  },
                  "✕"
                )
              ),

              // View Mode Switcher (Timeline vs Agent Cards)
              React.createElement(
                "div",
                { className: "flex items-center bg-slate-950 border border-slate-800 rounded-lg p-0.5" },
                React.createElement(
                  "button",
                  {
                    type: "button",
                    className: "px-2.5 py-1 rounded text-xs font-semibold transition-all cursor-pointer " +
                      (activityViewMode === "timeline"
                        ? "bg-indigo-600 text-white shadow-xs"
                        : "text-slate-400 hover:text-slate-200"),
                    onClick: () => setActivityViewMode("timeline")
                  },
                  "📋 Timeline"
                ),
                React.createElement(
                  "button",
                  {
                    type: "button",
                    className: "px-2.5 py-1 rounded text-xs font-semibold transition-all cursor-pointer " +
                      (activityViewMode === "agents"
                        ? "bg-indigo-600 text-white shadow-xs"
                        : "text-slate-400 hover:text-slate-200"),
                    onClick: () => setActivityViewMode("agents")
                  },
                  "🤖 By Agent"
                )
              ),

              // Auto-refresh switch
              React.createElement(
                "label",
                { className: "flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer select-none font-medium ml-1" },
                React.createElement("input", {
                  type: "checkbox",
                  checked: autoRefresh,
                  onChange: (e) => setAutoRefresh(e.target.checked),
                  className: "rounded border-slate-700 text-indigo-600 focus:ring-0 focus:ring-offset-0 bg-slate-950 cursor-pointer"
                }),
                React.createElement("span", { className: "text-[11px]" }, "Auto-poll")
              )
            )
          )
        ),

        // 4. Main Activity Feed Content
        activityViewMode === "agents"
          ? // View Mode 2: By Agent Grouped Panels
          React.createElement(
            "div",
            { className: "grid grid-cols-1 lg:grid-cols-2 gap-4" },
            liveAgents.map((agent) => {
              const b = getActorBadge(agent.id);
              const agentActivities = effectiveActivities.filter((act) =>
                act.actor === agent.id || (act.task_assignee === agent.id && act.actor === "dispatcher")
              );

              return React.createElement(
                "div",
                { key: agent.id, className: "bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-4 shadow-md flex flex-col" },
                // Agent Panel Header
                React.createElement(
                  "div",
                  { className: "flex items-center justify-between pb-3 border-b border-slate-800" },
                  React.createElement(
                    "div",
                    { className: "flex items-center gap-3" },
                    React.createElement("div", { className: "w-9 h-9 rounded-xl flex items-center justify-center text-base " + b.color }, b.icon),
                    React.createElement(
                      "div",
                      null,
                      React.createElement("h3", { className: "text-sm font-bold text-white m-0 font-mono" }, agent.id),
                      React.createElement("p", { className: "text-xs text-slate-400 m-0" }, agent.role || b.role)
                    )
                  ),
                  agent.status === "active"
                    ? React.createElement(
                      "span",
                      { className: "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30" },
                      React.createElement("span", { className: "w-1.5 h-1.5 rounded-full bg-emerald-400 zfk-pulse-active" }),
                      "Executing"
                    )
                    : React.createElement(
                      "span",
                      { className: "text-xs text-slate-400 font-medium px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700" },
                      "Idle"
                    )
                ),

                // Session Telemetry (if active)
                agent.current_task &&
                React.createElement(
                  "div",
                  { className: "bg-indigo-950/40 border border-indigo-500/30 rounded-xl p-3 space-y-1.5" },
                  React.createElement(
                    "div",
                    { className: "flex items-center justify-between text-xs" },
                    React.createElement("span", { className: "font-bold text-indigo-300" }, "⚡ Active Task:"),
                    React.createElement(
                      "button",
                      {
                        type: "button",
                        className: "font-semibold text-indigo-400 hover:text-indigo-200 underline cursor-pointer",
                        onClick: () => loadTaskDetails(agent.current_task.id)
                      },
                      `#${agent.current_task.id} ↗`
                    )
                  ),
                  React.createElement("p", { className: "text-xs font-medium text-white truncate m-0" }, agent.current_task.title),
                  agent.session_progress &&
                  React.createElement(
                    "div",
                    { className: "text-[11px] text-indigo-200/80 flex items-center gap-3 pt-1 border-t border-indigo-900/50" },
                    React.createElement("span", null, `Model: ${agent.session_progress.model || "Hermes"}`),
                    React.createElement("span", null, `Turns: ${agent.session_progress.turn_count || 0}`),
                    React.createElement("span", null, `Tools: ${agent.session_progress.tool_calls_count || 0}`)
                  )
                ),

                // Recent Actions list for this agent
                React.createElement(
                  "div",
                  { className: "space-y-2 flex-1" },
                  React.createElement("h4", { className: "text-xs font-bold text-slate-400 uppercase tracking-wider m-0" }, "Recent Actions"),
                  agentActivities.length === 0
                    ? React.createElement("p", { className: "text-xs text-slate-500 italic py-4 text-center m-0" }, "No recent events recorded for this agent")
                    : React.createElement(
                      "div",
                      { className: "space-y-2" },
                      agentActivities.slice(0, 6).map((item) => {
                        const actBadge = getActionBadge(item.action);
                        return React.createElement(
                          "div",
                          {
                            key: item.id,
                            className: "bg-slate-950/60 border border-slate-800/80 rounded-xl p-3 flex flex-col gap-1.5 hover:border-slate-700 transition-colors"
                          },
                          React.createElement(
                            "div",
                            { className: "flex items-center justify-between gap-2" },
                            React.createElement(
                              "div",
                              { className: "flex items-center gap-2" },
                              React.createElement(
                                "span",
                                { className: `inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-bold border ${actBadge.bg}` },
                                actBadge.icon,
                                actBadge.label
                              ),
                              item.task_id &&
                              React.createElement(
                                "button",
                                {
                                  type: "button",
                                  className: "text-xs font-mono font-bold text-indigo-400 hover:text-indigo-300 hover:underline cursor-pointer",
                                  onClick: () => loadTaskDetails(item.task_id)
                                },
                                `#${item.task_id}`
                              )
                            ),
                            React.createElement("span", { className: "text-[11px] text-slate-400" }, timeAgo(item.created_at))
                          ),
                          item.task_title &&
                          React.createElement("p", { className: "text-xs font-medium text-slate-200 truncate m-0" }, item.task_title),
                          item.details &&
                          React.createElement("p", { className: "text-[11px] font-mono text-slate-400 truncate m-0 bg-slate-900/60 px-2 py-1 rounded" }, item.details)
                        );
                      })
                    )
                )
              );
            })
          )
          : // View Mode 1: Unified Timeline Feed
          effectiveActivities.length === 0
            ? React.createElement(
              "div",
              { className: "bg-slate-900/60 border border-slate-800 rounded-2xl p-12 text-center space-y-4 shadow-sm" },
              React.createElement("div", { className: "w-14 h-14 rounded-2xl bg-indigo-500/10 text-indigo-400 flex items-center justify-center text-2xl mx-auto" }, "🔍"),
              React.createElement("h3", { className: "text-lg font-bold text-white m-0" }, "No Activities Match Your Filters"),
              React.createElement("p", { className: "text-xs text-slate-400 max-w-md mx-auto m-0" }, "There are no agent events matching the selected filters. Try broadening your actor, action, or search parameters."),
              React.createElement(
                "button",
                {
                  type: "button",
                  className: "inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white shadow-md transition-all cursor-pointer",
                  onClick: () => {
                    setActivityActorFilter("all");
                    setActivityActionFilter("all");
                    setActivityBoardFilter("all");
                    setActivitySearchQuery("");
                    setActivityPage(0);
                  }
                },
                "Reset All Filters"
              )
            )
            : React.createElement(
              "div",
              { className: "space-y-4" },
              // Timeline Items List
              React.createElement(
                "div",
                { className: "relative pl-6 sm:pl-8 border-l-2 border-slate-800/90 space-y-4 ml-3" },
                effectiveActivities.map((item) => {
                  const actBadge = getActionBadge(item.action);
                  const actorBadge = getActorBadge(item.actor);
                  const isExpanded = expandedActivityId === item.id;
                  const isLongDetails = item.details && item.details.length > 130;

                  return React.createElement(
                    "div",
                    { key: item.id, className: "relative group" },
                    // Connecting Timeline Node Dot
                    React.createElement(
                      "div",
                      {
                        className: `absolute -left-[31px] sm:-left-[39px] top-3.5 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold border-2 bg-slate-950 shadow-md ${actBadge.bg}`
                      },
                      actBadge.icon
                    ),

                    // Activity Card
                    React.createElement(
                      "div",
                      {
                        className: "bg-slate-900/80 backdrop-blur-md border border-slate-800/90 hover:border-slate-700 rounded-2xl p-4.5 space-y-3 shadow-sm transition-all duration-150"
                      },
                      // Header Row: Action badge, Actor, Target Task Link, Board, Timestamp
                      React.createElement(
                        "div",
                        { className: "flex flex-wrap items-center justify-between gap-2.5" },
                        React.createElement(
                          "div",
                          { className: "flex flex-wrap items-center gap-2" },
                          // Action Badge
                          React.createElement(
                            "span",
                            { className: `inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-bold border shadow-xs ${actBadge.bg}` },
                            React.createElement("span", null, actBadge.icon),
                            actBadge.label
                          ),
                          // Actor Chip
                          React.createElement(
                            "span",
                            { className: `inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-mono font-bold border ${actorBadge.color}` },
                            React.createElement("span", null, actorBadge.icon),
                            actorBadge.label
                          ),
                          // Task Link Pill (if associated with a task)
                          item.task_id &&
                          React.createElement(
                            "button",
                            {
                              type: "button",
                              className: "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-950 hover:bg-slate-800 text-indigo-300 hover:text-indigo-200 border border-slate-700/80 shadow-xs transition-colors cursor-pointer group/task",
                              onClick: () => loadTaskDetails(item.task_id),
                              title: "Click to open full task details modal"
                            },
                            React.createElement("span", { className: "font-mono font-bold text-indigo-400" }, `#${item.task_id}`),
                            item.task_title &&
                            React.createElement("span", { className: "truncate max-w-[200px] sm:max-w-[320px]" }, item.task_title),
                            React.createElement("span", { className: "text-slate-500 group-hover/task:text-slate-300" }, "↗")
                          ),
                          // Task Priority Pill
                          item.task_priority &&
                          React.createElement(
                            "span",
                            { className: "px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-slate-800 text-slate-300 border border-slate-700" },
                            item.task_priority
                          ),
                          // Task Status Pill
                          item.task_status &&
                          React.createElement(
                            "span",
                            { className: "px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider bg-slate-800/60 text-slate-400 border border-slate-700/60" },
                            item.task_status
                          )
                        ),

                        // Right: Board & Timestamp
                        React.createElement(
                          "div",
                          { className: "flex items-center gap-2 text-xs text-slate-400 shrink-0" },
                          item.board_slug &&
                          React.createElement(
                            "span",
                            { className: "px-2 py-0.5 rounded text-[11px] font-mono bg-slate-950 text-slate-400 border border-slate-800" },
                            item.board_slug
                          ),
                          React.createElement(
                            "span",
                            {
                              className: "font-medium text-slate-400 hover:text-slate-200 transition-colors",
                              title: item.created_at ? new Date(item.created_at * 1000).toLocaleString() : ""
                            },
                            timeAgo(item.created_at)
                          )
                        )
                      ),

                      // Details Box
                      item.details &&
                      React.createElement(
                        "div",
                        { className: "space-y-1.5" },
                        React.createElement(
                          "div",
                          {
                            className: "bg-slate-950/80 border border-slate-800/90 rounded-xl p-3 text-xs font-mono text-slate-300 leading-relaxed break-words whitespace-pre-wrap " +
                              (!isExpanded && isLongDetails ? "max-h-20 overflow-hidden relative" : "")
                          },
                          item.details,
                          !isExpanded && isLongDetails &&
                          React.createElement("div", {
                            className: "absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-slate-950 to-transparent pointer-events-none"
                          })
                        ),
                        isLongDetails &&
                        React.createElement(
                          "button",
                          {
                            type: "button",
                            className: "text-xs font-semibold text-indigo-400 hover:text-indigo-300 cursor-pointer pt-0.5",
                            onClick: () => setExpandedActivityId(isExpanded ? null : item.id)
                          },
                          isExpanded ? "▲ Collapse details" : "▼ Show full details / trace"
                        )
                      ),

                      // Footer Quick Actions
                      React.createElement(
                        "div",
                        { className: "flex items-center justify-between text-xs text-slate-500 pt-1 border-t border-slate-800/60" },
                        React.createElement(
                          "div",
                          { className: "flex items-center gap-3" },
                          React.createElement("span", { className: "text-[11px] text-slate-500 font-mono" }, `Event #${item.id}`),
                          item.task_assignee &&
                          React.createElement("span", { className: "text-[11px] text-slate-400" }, `Assignee: ${item.task_assignee}`)
                        ),
                        item.task_id &&
                        React.createElement(
                          "button",
                          {
                            type: "button",
                            className: "inline-flex items-center gap-1 text-xs font-semibold text-indigo-400 hover:text-indigo-300 transition-colors cursor-pointer",
                            onClick: () => loadTaskDetails(item.task_id)
                          },
                          "Inspect Task Modal ↗"
                        )
                      )
                    )
                  );
                })
              ),

              // Pagination Controls
              React.createElement(
                "div",
                { className: "bg-slate-900/80 border border-slate-800 rounded-2xl p-4 flex flex-col sm:flex-row items-center justify-between gap-3 shadow-md" },
                React.createElement(
                  "div",
                  { className: "text-xs text-slate-400 font-medium" },
                  `Showing ${startIdx}–${endIdx} of ${effectiveTotal} events`
                ),
                React.createElement(
                  "div",
                  { className: "flex items-center gap-2" },
                  React.createElement(
                    "button",
                    {
                      type: "button",
                      className: "px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-950 border border-slate-700/80 text-slate-300 hover:text-white hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer",
                      disabled: activityPage === 0 || activitiesLoading,
                      onClick: () => setActivityPage((p) => Math.max(0, p - 1))
                    },
                    "← Previous"
                  ),
                  React.createElement(
                    "span",
                    { className: "px-3 py-1 text-xs font-bold font-mono text-indigo-300 bg-indigo-950/60 border border-indigo-700/60 rounded-lg" },
                    `Page ${activityPage + 1} of ${totalPages}`
                  ),
                  React.createElement(
                    "button",
                    {
                      type: "button",
                      className: "px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-950 border border-slate-700/80 text-slate-300 hover:text-white hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer",
                      disabled: (activityPage + 1) * activityLimit >= effectiveTotal || activitiesLoading,
                      onClick: () => setActivityPage((p) => p + 1)
                    },
                    "Next →"
                  )
                )
              )
            )
      );
}