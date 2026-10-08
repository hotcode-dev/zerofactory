import React from "react";
import { formatPrLabel, timeAgo } from "../utils/formatters.js";
import { renderPrIcon } from "../utils/icons.js";
import { API_BASE, COLUMNS } from "../constants.js";
import { fetchJSON } from "../sdk.js";
import { Modal } from "../components/Modal.jsx";
import { GrillInterviewPanel } from "../components/GrillInterviewPanel.jsx";

export function TaskDetailModal(props) {
  const {
    selectedTask,
    setSelectedTask,
    boards = [],
    handleUpdateTask,
    handleDeleteTask,
    handleRunAgent,
    handleStopTaskSession,
    stoppingSessionId,
    activeRunningTaskId,
    newCommentText,
    setNewCommentText,
    handleAddComment,
    handleAddCommentSubmit = handleAddComment,
    loadTasksAndStats,
    loadTaskDetails,
    showToast = () => {},
    selectedSessionIdx = null,
    setSelectedSessionIdx = () => {},
    refreshSessionProgress = () => {},
    handleAdvanceTask = () => {},
    tasks = []
  } = props;

  const [depTaskId, setDepTaskId] = React.useState("");
  const [depLinkType, setDepLinkType] = React.useState("blocks");

  const handleLinkDependency = async () => {
    if (!depTaskId || !selectedTask) return;
    try {
      await fetchJSON(API_BASE + "/tasks/" + selectedTask.id + "/dependencies", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ parent_id: depTaskId, link_type: depLinkType })
      });
      showToast("Linked dependency #" + depTaskId + " (" + depLinkType + ")", "success");
      setDepTaskId("");
      loadTaskDetails(selectedTask.id);
      loadTasksAndStats();
    } catch (err) {
      showToast("Failed to link dependency: " + err.message, "error");
    }
  };

  const handleRemoveDependency = async (parentId) => {
    if (!selectedTask) return;
    try {
      await fetchJSON(API_BASE + "/tasks/" + selectedTask.id + "/dependencies/" + parentId, {
        method: "DELETE"
      });
      showToast("Removed dependency link #" + parentId, "info");
      loadTaskDetails(selectedTask.id);
      loadTasksAndStats();
    } catch (err) {
      showToast("Failed to unlink: " + err.message, "error");
    }
  };

  if (!selectedTask) return null;

  return React.createElement(
    Modal,
    {
      isOpen: Boolean(selectedTask),
      onClose: () => setSelectedTask(null),
      title: React.createElement(
        "div",
        { className: "flex items-center gap-3 min-w-0" },
        React.createElement("span", { className: "font-mono text-xs font-semibold px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700/60" }, selectedTask.id),
        React.createElement("h2", { className: "text-base font-semibold text-white truncate m-0" }, selectedTask.title)
      ),
      bodyClassName: "p-6 space-y-5 overflow-y-auto zfk-scrollbar flex-1",
      footerClassName: "flex items-center justify-between px-6 py-3.5 border-t border-slate-800 bg-slate-900/50 shrink-0",
      footer: React.createElement(
        React.Fragment,
        null,
        React.createElement(
          "button",
          {
            type: "button",
            className: "px-3.5 py-1.5 rounded-lg text-xs font-medium text-rose-400 hover:text-rose-300 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 transition-colors cursor-pointer",
            onClick: () => handleDeleteTask(selectedTask.id)
          },
          "Delete Task"
        ),
        React.createElement(
          "div",
          { className: "flex items-center gap-2" },
          selectedTask.status === "triage" &&
            React.createElement(
              "button",
              {
                type: "button",
                className: "px-3.5 py-1.5 rounded-lg text-xs font-semibold text-indigo-300 hover:text-white bg-indigo-950/70 hover:bg-indigo-900 border border-indigo-500/40 transition-colors cursor-pointer flex items-center gap-1.5 shadow-xs",
                onClick: async () => {
                  try {
                    await fetchJSON(API_BASE + "/tasks/" + selectedTask.id + "/triage", { method: "POST" });
                    showToast("🧭 Grill-with-Docs triage dispatched to zf-orchestrator", "success");
                    loadTaskDetails(selectedTask.id);
                    loadTasksAndStats();
                  } catch (err) {
                    showToast("Triage dispatch failed: " + err.message, "error");
                  }
                }
              },
              "🧭 Grill Triage"
            ),
          React.createElement(
            "button",
            {
              type: "button",
              className: "px-4 py-1.5 rounded-lg text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-500 transition-colors cursor-pointer shadow-xs shadow-indigo-600/30",
              onClick: () => handleAdvanceTask(selectedTask)
            },
            "Advance Stage →"
          )
        )
      )
    },

                // Status & Controls Row
                React.createElement(
                  "div",
                  { className: "grid grid-cols-1 sm:grid-cols-2 gap-4" },
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Status"),
                    React.createElement(
                      "select",
                      {
                        className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors cursor-pointer",
                        value: selectedTask.status,
                        onChange: async (e) => {
                          const newStatus = e.target.value;
                          await fetchJSON(API_BASE + "/tasks/" + selectedTask.id + "/move", {
                            method: "POST",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ status: newStatus })
                          });
                          loadTaskDetails(selectedTask.id);
                          loadTasksAndStats();
                        }
                      },
                      COLUMNS.map((c) => React.createElement("option", { key: c.id, value: c.id }, c.title))
                    )
                  ),
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Assignee"),
                    React.createElement(
                      "select",
                      {
                        className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors cursor-pointer",
                        value: selectedTask.assignee || "unassigned",
                        onChange: async (e) => {
                          const newAssignee = e.target.value;
                          await fetchJSON(API_BASE + "/tasks/" + selectedTask.id, {
                            method: "PATCH",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ assignee: newAssignee })
                          });
                          loadTaskDetails(selectedTask.id);
                          loadTasksAndStats();
                        }
                      },
                      [
                        { id: "unassigned", label: "Unassigned" },
                        { id: "human", label: "Human" },
                        { id: "zf-builder", label: "ZF Builder" },
                        { id: "zf-reviewer", label: "ZF Reviewer" },
                        { id: "zf-orchestrator", label: "ZF Orchestrator" }
                      ].map((r) =>
                        React.createElement("option", { key: r.id, value: r.id }, r.label)
                      )
                    )
                  )
                ),

                React.createElement(
                  "div",
                  { className: "grid grid-cols-1 sm:grid-cols-2 gap-4" },
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Priority"),
                    React.createElement(
                      "select",
                      {
                        className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors cursor-pointer",
                        value: selectedTask.priority || "P2",
                        onChange: async (e) => {
                          const newPrio = e.target.value;
                          await fetchJSON(API_BASE + "/tasks/" + selectedTask.id, {
                            method: "PATCH",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ priority: newPrio })
                          });
                          loadTaskDetails(selectedTask.id);
                          loadTasksAndStats();
                        }
                      },
                      ["P0", "P1", "P2", "P3"].map((p) => React.createElement("option", { key: p, value: p }, p))
                    )
                  ),
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Target Repository & Board"),
                    React.createElement(
                      "div",
                      { className: "flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono min-h-[34px]" },
                      selectedTask.repo_alias ?
                        React.createElement("span", { className: "px-2 py-0.5 rounded font-semibold bg-teal-950/80 text-teal-300 border border-teal-800/60" }, "📦 " + selectedTask.repo_alias) :
                        React.createElement("span", { className: "text-slate-400" }, "Default Repo"),
                      selectedTask.board_slug &&
                        React.createElement("span", { className: "text-slate-500 text-[11px]" }, "(" + selectedTask.board_slug + ")")
                    )
                  )
                ),

                // Pull Request URL Row
                React.createElement(
                  "div",
                  { className: "space-y-1.5" },
                  React.createElement(
                    "div",
                    { className: "flex items-center justify-between" },
                    React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Pull Request URL"),
                    selectedTask.pr_url &&
                    React.createElement(
                      "a",
                      {
                        href: selectedTask.pr_url,
                        target: "_blank",
                        rel: "noopener noreferrer",
                        className: "inline-flex items-center gap-1 text-[11px] text-purple-400 hover:text-purple-300 font-medium transition-colors"
                      },
                      renderPrIcon("w-2.5 h-2.5 shrink-0"),
                      "Open Link ↗"
                    )
                  ),
                  React.createElement(
                    "div",
                    { className: "flex items-center gap-2" },
                    React.createElement("input", {
                      key: selectedTask.id + (selectedTask.pr_url || ""),
                      defaultValue: selectedTask.pr_url || "",
                      placeholder: "e.g. https://github.com/owner/repo/pull/123",
                      className: "flex-1 bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 transition-colors font-mono",
                      onBlur: async (e) => {
                        const newPr = e.target.value.trim();
                        if (newPr !== (selectedTask.pr_url || "")) {
                          try {
                            await fetchJSON(API_BASE + "/tasks/" + selectedTask.id, {
                              method: "PATCH",
                              headers: { "Content-Type": "application/json" },
                              body: JSON.stringify({ pr_url: newPr || null })
                            });
                            loadTaskDetails(selectedTask.id);
                            loadTasksAndStats();
                            showToast("Updated Pull Request URL", "success");
                          } catch (err) {
                            showToast("Failed to update PR URL: " + err.message, "error");
                          }
                        }
                      },
                      onKeyDown: (e) => {
                        if (e.key === "Enter") {
                          e.target.blur();
                        }
                      }
                    })
                  )
                ),

                // Description
                React.createElement(
                  "div",
                  { className: "space-y-1.5" },
                  React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Description / Acceptance Criteria"),
                  React.createElement(
                    "div",
                    {
                      className: "bg-slate-950/60 border border-slate-800/80 rounded-lg p-3.5 text-xs leading-relaxed text-slate-300 whitespace-pre-wrap"
                    },
                    selectedTask.description || "(No description provided)"
                  )
                ),

                // Grill-with-Docs Interactive Requirements & Decision Panel
                React.createElement(GrillInterviewPanel, {
                  task: selectedTask,
                  loadTaskDetails,
                  loadTasksAndStats,
                  showToast
                }),

                // Worktree & Branch Info
                selectedTask.workspace_path &&
                React.createElement(
                  "div",
                  {
                    className: "p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-xs space-y-1"
                  },
                  React.createElement("strong", { className: "text-emerald-400 font-semibold" }, "Git Worktree Active: "),
                  React.createElement("span", { className: "text-indigo-300 font-mono text-[0.6875rem] break-all" }, selectedTask.workspace_path),
                  selectedTask.branch_name &&
                  React.createElement("div", { className: "text-slate-400 text-[0.6875rem] mt-0.5" }, "Branch: " + selectedTask.branch_name)
                ),

                // Pull Request Banner
                selectedTask.pr_url &&
                React.createElement(
                  "div",
                  {
                    className: "p-3.5 bg-purple-500/10 border border-purple-500/25 rounded-lg text-xs space-y-2 shadow-xs"
                  },
                  React.createElement(
                    "div",
                    { className: "flex items-center justify-between gap-2 flex-wrap" },
                    React.createElement(
                      "div",
                      { className: "flex items-center gap-2 text-purple-300 font-semibold" },
                      renderPrIcon("w-4 h-4 text-purple-400 shrink-0"),
                      React.createElement("span", null, "Pull Request:"),
                      React.createElement(
                        "span",
                        { className: "font-mono font-bold bg-purple-500/20 px-2 py-0.5 rounded border border-purple-500/30 text-purple-200" },
                        formatPrLabel(selectedTask.pr_url)
                      )
                    ),
                    React.createElement(
                      "a",
                      {
                        href: selectedTask.pr_url,
                        target: "_blank",
                        rel: "noopener noreferrer",
                        className: "inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-purple-600 hover:bg-purple-500 text-white font-semibold text-xs shadow-md shadow-purple-600/20 transition-all duration-150 cursor-pointer"
                      },
                      "View on GitHub ↗"
                    )
                  ),
                  React.createElement(
                    "div",
                    { className: "flex items-center justify-between gap-2 pt-1 border-t border-purple-500/20 text-slate-300" },
                    React.createElement(
                      "a",
                      {
                        href: selectedTask.pr_url,
                        target: "_blank",
                        rel: "noopener noreferrer",
                        className: "text-purple-300 hover:text-purple-200 font-mono text-[0.6875rem] break-all underline decoration-purple-500/50 hover:decoration-purple-300 transition-colors"
                      },
                      selectedTask.pr_url
                    ),
                    React.createElement(
                      "button",
                      {
                        type: "button",
                        onClick: () => {
                          if (navigator.clipboard) {
                            navigator.clipboard.writeText(selectedTask.pr_url);
                          }
                          showToast("Copied PR URL to clipboard!", "success");
                        },
                        className: "shrink-0 px-2 py-0.5 rounded text-[0.625rem] bg-purple-500/20 hover:bg-purple-500/30 text-purple-300 border border-purple-500/30 cursor-pointer transition-colors",
                        title: "Copy PR URL"
                      },
                      "Copy"
                    )
                  )
                ),

                // Multi-Agent Execution Sessions Panel
                (() => {
                  const prog = selectedTask.session_progress;
                  const rawSessions = (prog && prog.sessions && prog.sessions.length > 0)
                    ? prog.sessions
                    : (prog && prog.has_session ? [prog] : []);

                  if (rawSessions.length === 0 && selectedTask.status !== "running") return null;

                  // Reorder backward (latest session first)
                  const taskSessions = rawSessions.slice().reverse();

                  const activeIdx = (selectedSessionIdx >= 0 && selectedSessionIdx < taskSessions.length)
                    ? selectedSessionIdx
                    : 0;
                  const currentSession = taskSessions[activeIdx] || prog || {};
                  const isOngoing = currentSession.status === "ongoing" || currentSession.is_active || (prog && prog.is_alive && (currentSession.session_id ? currentSession.session_id === prog.session_id : activeIdx === 0));
                  const agentRole = currentSession.agent || selectedTask.assignee || "zf-builder";
                  const agentIcon = currentSession.agent_icon || (agentRole === "zf-reviewer" ? "🔍" : agentRole === "zf-orchestrator" ? "🧭" : "🔨");
                  const agentLabel = currentSession.agent_label || (agentRole === "zf-reviewer" ? "Reviewer" : agentRole === "zf-orchestrator" ? "Orchestrator" : "Builder");

                  const basePath = (typeof window !== "undefined" && window.__HERMES_BASE_PATH__)
                    ? ("/" + String(window.__HERMES_BASE_PATH__).replace(/^\/|\/$/g, ""))
                    : "";
                  const curSid = currentSession.session_id || (prog && prog.session_id);
                  const chatUrl = curSid ? (basePath + "/chat?resume=" + encodeURIComponent(curSid) + (agentRole ? "&profile=" + encodeURIComponent(agentRole) : "")) : null;

                  return React.createElement(
                    "div",
                    { className: "bg-slate-950/80 border border-indigo-500/30 rounded-xl p-4 space-y-3.5 shadow-sm" },
                    // Multi-Session Pill Tabs
                    taskSessions.length > 1 &&
                    React.createElement(
                      "div",
                      { className: "space-y-1.5 pb-3 border-b border-slate-800/80" },
                      React.createElement("div", { className: "text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center justify-between" },
                        React.createElement("span", null, "AI Sessions (" + taskSessions.length + ")"),
                        React.createElement("span", { className: "text-slate-500 font-normal lowercase" }, "click session to inspect")
                      ),
                      React.createElement(
                        "div",
                        { className: "flex items-center gap-1.5 overflow-x-auto pb-1 zfk-scrollbar" },
                        taskSessions.map((s, sIdx) => {
                          const sIsOngoing = s.status === "ongoing" || s.is_active || (prog && prog.is_alive && (s.session_id ? s.session_id === prog.session_id : sIdx === 0));
                          const sIcon = s.agent_icon || (s.agent === "zf-reviewer" ? "🔍" : s.agent === "zf-orchestrator" ? "🧭" : "🔨");
                          const sLabel = s.agent_label || (s.agent === "zf-reviewer" ? "Reviewer" : s.agent === "zf-orchestrator" ? "Orchestrator" : "Builder");
                          const sNum = taskSessions.length - sIdx;
                          return React.createElement(
                            "button",
                            {
                              key: s.session_id || sIdx,
                              type: "button",
                              className: "flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border transition-all cursor-pointer shrink-0 " +
                                (sIdx === activeIdx
                                  ? "bg-indigo-600/30 border-indigo-400 text-white font-semibold shadow-xs"
                                  : "bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-800/80"),
                              onClick: () => setSelectedSessionIdx(sIdx)
                            },
                            React.createElement("span", null, sIcon),
                            React.createElement("span", null, sLabel + " #" + sNum),
                            React.createElement("span", {
                              className: "w-2 h-2 rounded-full " + (sIsOngoing ? "bg-emerald-400 zfk-pulse-active" : "bg-slate-600")
                            }),
                            s.turn_count ? React.createElement("span", { className: "text-[10px] text-slate-400 font-mono" }, s.turn_count + "t") : null
                          );
                        })
                      )
                    ),

                    // Session Header
                    React.createElement(
                      "div",
                      { className: "flex flex-wrap items-center justify-between gap-2 pb-2" },
                      React.createElement(
                        "div",
                        { className: "flex items-center gap-2 flex-wrap" },
                        React.createElement("span", {
                          className: "w-2.5 h-2.5 rounded-full shrink-0 " + (isOngoing ? "bg-emerald-400 zfk-pulse-active" : "bg-slate-500")
                        }),
                        React.createElement(
                          "span",
                          { className: "font-semibold text-xs text-white flex items-center gap-1.5" },
                          agentIcon,
                          agentLabel,
                          React.createElement("span", { className: "font-normal text-slate-400" }, isOngoing ? "• Ongoing Execution" : "• Finished Session")
                        ),
                        prog && prog.worker_pid && isOngoing &&
                        React.createElement("span", { className: "text-[0.625rem] font-mono px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700/60" }, "PID: " + prog.worker_pid),
                        curSid &&
                        React.createElement(
                          "span",
                          {
                            className: "text-xs font-mono font-medium text-purple-300 truncate max-w-[160px]",
                            title: "Session ID: " + curSid
                          },
                          curSid
                        )
                      ),
                      React.createElement(
                        "div",
                        { className: "flex items-center gap-2" },
                        isOngoing && React.createElement(
                          "button",
                          {
                            type: "button",
                            disabled: stoppingSessionId === (curSid || selectedTask.id),
                            className: "inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-rose-950/70 hover:bg-rose-900 text-rose-300 border border-rose-800/80 hover:border-rose-800/60 transition-colors cursor-pointer shadow-xs disabled:opacity-50",
                            onClick: () => handleStopTaskSession(selectedTask.id, curSid),
                            title: "Safely terminate worker process group and stop session"
                          },
                          React.createElement("span", null, "⏹"),
                          React.createElement("span", null, stoppingSessionId === (curSid || selectedTask.id) ? "Stopping..." : "Stop Session")
                        ),
                        chatUrl &&
                        React.createElement(
                          "a",
                          {
                            href: chatUrl,
                            className: "inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white transition-colors cursor-pointer shadow-xs",
                            target: "_blank",
                            rel: "noreferrer",
                            title: "Open session in Hermes Chat"
                          },
                          "Open Chat ↗"
                        ),
                        React.createElement(
                          "button",
                          {
                            type: "button",
                            className: "inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700/60 transition-colors cursor-pointer",
                            onClick: () => refreshSessionProgress(selectedTask.id),
                            title: "Refresh session status"
                          },
                          "🔄 Refresh"
                        )
                      )
                    ),

                    // Session Stats Summary Grid
                    React.createElement(
                      "div",
                      { className: "grid grid-cols-2 sm:grid-cols-4 gap-2.5" },
                      React.createElement(
                        "div",
                        { className: "bg-slate-900/80 border border-slate-800/80 rounded-lg p-2.5 flex flex-col gap-1" },
                        React.createElement("span", { className: "text-[0.625rem] font-semibold uppercase tracking-wider text-purple-400/90" }, "Session ID"),
                        React.createElement("span", { className: "text-xs font-medium text-purple-300 font-mono truncate", title: curSid }, curSid || "Detecting...")
                      ),
                      React.createElement(
                        "div",
                        { className: "bg-slate-900/80 border border-slate-800/80 rounded-lg p-2.5 flex flex-col gap-1" },
                        React.createElement("span", { className: "text-[0.625rem] font-semibold uppercase tracking-wider text-slate-400" }, "Model"),
                        React.createElement("span", { className: "text-xs font-medium text-slate-200 truncate" }, currentSession.model || (prog && prog.model) || "Default")
                      ),
                      React.createElement(
                        "div",
                        { className: "bg-slate-900/80 border border-slate-800/80 rounded-lg p-2.5 flex flex-col gap-1" },
                        React.createElement("span", { className: "text-[0.625rem] font-semibold uppercase tracking-wider text-slate-400" }, "Turns / Msgs"),
                        React.createElement(
                          "span",
                          { className: "text-xs font-semibold text-emerald-400 truncate" },
                          (currentSession.turn_count || 0) + " turns (" + (currentSession.message_count || 0) + " msgs)"
                        )
                      ),
                      React.createElement(
                        "div",
                        { className: "bg-slate-900/80 border border-slate-800/80 rounded-lg p-2.5 flex flex-col gap-1" },
                        React.createElement("span", { className: "text-[0.625rem] font-semibold uppercase tracking-wider text-slate-400" }, "Duration / Time"),
                        React.createElement(
                          "span",
                          { className: "text-xs font-medium text-slate-200 truncate" },
                          currentSession.duration_seconds
                            ? `${Math.floor(currentSession.duration_seconds / 60)}m ${currentSession.duration_seconds % 60}s`
                            : timeAgo(currentSession.ended_at || currentSession.started_at || (prog && prog.last_active)) || "Just now"
                        )
                      )
                    ),

                    // Recent Agent Execution Steps
                    currentSession.recent_steps && currentSession.recent_steps.length > 0 &&
                    React.createElement(
                      "div",
                      { className: "mt-3 space-y-2" },
                      React.createElement(
                        "div",
                        { className: "text-xs font-semibold text-slate-400" },
                        "Recent Agent Actions & Tool Executions"
                      ),
                      React.createElement(
                        "div",
                        { className: "space-y-1.5 max-h-48 overflow-y-auto zfk-scrollbar pr-1" },
                        currentSession.recent_steps.map((st) =>
                          React.createElement(
                            "div",
                            { key: st.id, className: "bg-slate-900/60 border border-slate-800/70 rounded-md p-2 text-xs space-y-1" },
                            React.createElement(
                              "div",
                              { className: "flex items-center gap-2" },
                              React.createElement(
                                "span",
                                { className: "text-[0.625rem] font-mono uppercase px-1.5 py-0.5 rounded bg-slate-800 text-indigo-300 border border-slate-700/60" },
                                st.tool_name ? "tool: " + st.tool_name : st.role
                              ),
                              React.createElement(
                                "span",
                                { className: "text-[0.6875rem] text-slate-500" },
                                timeAgo(st.timestamp)
                              )
                            ),
                            React.createElement("div", { className: "text-[0.6875rem] text-slate-400 font-mono break-all line-clamp-2" }, st.snippet)
                          )
                        )
                      )
                    ),

                    // Worker Log Tail (Collapsible)
                    prog && prog.log_tail && isOngoing &&
                    React.createElement(
                      "details",
                      { className: "mt-3 text-xs" },
                      React.createElement(
                        "summary",
                        { className: "cursor-pointer text-slate-400 hover:text-slate-200 font-medium select-none outline-none py-1" },
                        "📄 Show Worker Process Log Output"
                      ),
                      React.createElement(
                        "pre",
                        { className: "mt-2 p-3 bg-black/60 border border-slate-800 rounded-lg text-[0.6875rem] font-mono text-emerald-400/90 whitespace-pre-wrap max-h-56 overflow-y-auto zfk-scrollbar" },
                        prog.log_tail
                      )
                    )
                  );
                })(),

                // Dependencies & Relationships Section
                React.createElement(
                  "div",
                  { className: "p-3.5 rounded-lg bg-slate-950/70 border border-slate-800/90 space-y-3" },
                  React.createElement(
                    "div",
                    { className: "flex items-center justify-between" },
                    React.createElement("label", { className: "block text-xs font-semibold text-slate-300" }, "🔗 Task Dependencies & Sequential Relations"),
                    React.createElement("span", { className: "text-[10px] text-slate-500" }, "Parent blockers vs Peer related features")
                  ),

                  // Parent Links (Upstream)
                  selectedTask.parents && selectedTask.parents.length > 0 &&
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement("span", { className: "text-[11px] font-semibold text-slate-400" }, "Upstream Dependencies:"),
                    React.createElement(
                      "div",
                      { className: "flex flex-col gap-1.5" },
                      selectedTask.parents.map((p) =>
                        React.createElement(
                          "div",
                          {
                            key: p.id,
                            className: "flex items-center justify-between p-2 rounded-md bg-slate-900 border border-slate-800 text-xs text-slate-300 gap-2"
                          },
                          React.createElement(
                            "div",
                            { className: "flex items-center gap-2 min-w-0 flex-wrap" },
                            p.link_type === "relates_to" ?
                              React.createElement("span", { className: "px-1.5 py-0.5 rounded text-[10px] font-bold bg-sky-950/80 text-sky-300 border border-sky-800/60" }, "🔵 Relates to") :
                              React.createElement("span", { className: "px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-950/80 text-rose-300 border border-rose-800/60" }, "🔴 Blocks"),
                            p.repo_alias && React.createElement("span", { className: "px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold bg-slate-800 text-teal-300 border border-slate-700/60" }, "📦 " + p.repo_alias),
                            React.createElement("span", { className: "font-mono font-semibold text-indigo-300" }, "#" + p.id),
                            React.createElement("span", { className: "truncate max-w-[240px]" }, p.title)
                          ),
                          React.createElement(
                            "div",
                            { className: "flex items-center gap-1.5 shrink-0" },
                            React.createElement("span", { className: "text-[0.625rem] font-medium capitalize px-1.5 py-0.5 rounded border border-slate-700 bg-slate-800 text-slate-400" }, p.status),
                            React.createElement(
                              "button",
                              {
                                type: "button",
                                className: "text-rose-400 hover:text-rose-300 px-1 text-xs font-semibold cursor-pointer",
                                onClick: () => handleRemoveDependency(p.id),
                                title: "Remove dependency"
                              },
                              "✕"
                            )
                          )
                        )
                      )
                    )
                  ),

                  // Child Links (Downstream)
                  selectedTask.children && selectedTask.children.length > 0 &&
                  React.createElement(
                    "div",
                    { className: "space-y-1.5 pt-1" },
                    React.createElement("span", { className: "text-[11px] font-semibold text-slate-400" }, "Downstream Blocked / Related Tasks:"),
                    React.createElement(
                      "div",
                      { className: "flex flex-col gap-1.5" },
                      selectedTask.children.map((c) =>
                        React.createElement(
                          "div",
                          {
                            key: c.id,
                            className: "flex items-center justify-between p-2 rounded-md bg-slate-900 border border-slate-800 text-xs text-slate-300 gap-2"
                          },
                          React.createElement(
                            "div",
                            { className: "flex items-center gap-2 min-w-0 flex-wrap" },
                            c.link_type === "relates_to" ?
                              React.createElement("span", { className: "px-1.5 py-0.5 rounded text-[10px] font-bold bg-sky-950/80 text-sky-300 border border-sky-800/60" }, "🔵 Relates to") :
                              React.createElement("span", { className: "px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-950/80 text-amber-300 border border-amber-800/60" }, "⏳ Blocked by this"),
                            c.repo_alias && React.createElement("span", { className: "px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold bg-slate-800 text-teal-300 border border-slate-700/60" }, "📦 " + c.repo_alias),
                            React.createElement("span", { className: "font-mono font-semibold text-indigo-300" }, "#" + c.id),
                            React.createElement("span", { className: "truncate max-w-[240px]" }, c.title)
                          ),
                          React.createElement("span", { className: "text-[0.625rem] font-medium capitalize px-1.5 py-0.5 rounded border border-slate-700 bg-slate-800 text-slate-400" }, c.status)
                        )
                      )
                    )
                  ),

                  // Add Link Form
                  React.createElement(
                    "div",
                    { className: "flex items-center gap-2 pt-2 border-t border-slate-800/80 flex-wrap sm:flex-nowrap" },
                    React.createElement(
                      "select",
                      {
                        className: "flex-1 bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-indigo-500 cursor-pointer min-w-[180px]",
                        value: depTaskId,
                        onChange: (e) => setDepTaskId(e.target.value)
                      },
                      React.createElement("option", { value: "" }, "-- Link to another task --"),
                      (tasks || [])
                        .filter((t) => t.id !== selectedTask.id && (!selectedTask.parents || !selectedTask.parents.some((p) => p.id === t.id)))
                        .map((t) =>
                          React.createElement(
                            "option",
                            { key: t.id, value: t.id },
                            "#" + t.id + " " + (t.repo_alias ? "[" + t.repo_alias + "] " : "") + t.title + " (" + t.status + ")"
                          )
                        )
                    ),
                    React.createElement(
                      "select",
                      {
                        className: "bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-indigo-500 cursor-pointer shrink-0",
                        value: depLinkType,
                        onChange: (e) => setDepLinkType(e.target.value)
                      },
                      React.createElement("option", { value: "blocks" }, "🔴 Blocks (Hard Blocker)"),
                      React.createElement("option", { value: "relates_to" }, "🔵 Relates to (Soft Peer)")
                    ),
                    React.createElement(
                      "button",
                      {
                        type: "button",
                        disabled: !depTaskId,
                        className: "px-3 py-1.5 rounded text-xs font-medium text-indigo-300 bg-indigo-950/70 hover:bg-indigo-900 border border-indigo-500/40 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed shrink-0",
                        onClick: handleLinkDependency
                      },
                      "+ Link"
                    )
                  )
                ),

                // Comments Section
                React.createElement(
                  "div",
                  { className: "space-y-2" },
                  React.createElement(
                    "label",
                    { className: "block text-xs font-semibold text-slate-400 tracking-wide" },
                    "Discussion & Activity (" + ((selectedTask.comments && selectedTask.comments.length) || 0) + ")"
                  ),
                  React.createElement(
                    "div",
                    { className: "space-y-2 max-h-52 overflow-y-auto zfk-scrollbar pr-1" },
                    (!selectedTask.comments || selectedTask.comments.length === 0)
                      ? React.createElement("div", { className: "text-xs text-slate-500 italic py-2" }, "No comments yet.")
                      : selectedTask.comments.map((c) =>
                        React.createElement(
                          "div",
                          { key: c.id, className: "bg-slate-950/60 border border-slate-800/80 rounded-lg p-3 space-y-1.5" },
                          React.createElement(
                            "div",
                            { className: "flex items-center justify-between text-xs" },
                            React.createElement("span", { className: "font-semibold text-indigo-400" }, "@" + c.author),
                            React.createElement("span", { className: "text-[0.6875rem] text-slate-500" }, timeAgo(c.created_at))
                          ),
                          React.createElement("div", { className: "text-xs text-slate-300 whitespace-pre-wrap leading-relaxed" }, c.body)
                        )
                      )
                  ),
                  React.createElement(
                    "form",
                    { onSubmit: handleAddCommentSubmit, className: "flex gap-2 mt-2" },
                    React.createElement("input", {
                      className: "flex-1 bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
                      placeholder: "Write a note or comment...",
                      value: newCommentText,
                      onChange: (e) => setNewCommentText(e.target.value)
                    }),
                    React.createElement("button", { type: "submit", className: "px-3.5 py-2 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 hover:text-white border border-slate-700 transition-colors cursor-pointer" }, "Post")
                  )
                )
  );
}
