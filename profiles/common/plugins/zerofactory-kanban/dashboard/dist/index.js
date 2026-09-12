(function () {
  "use strict";

  const SDK = window.__HERMES_PLUGIN_SDK__;
  if (!SDK || !window.__HERMES_PLUGINS__) return;

  const React = SDK.React;
  const { useState, useEffect, useMemo, useCallback, useRef } = SDK.hooks;
  const { fetchJSON } = SDK;
  const utils = SDK.utils || {};
  const timeAgo = utils.timeAgo || function (ts) {
    if (!ts) return "";
    const diff = Math.floor(Date.now() / 1000 - ts);
    if (diff < 60) return "just now";
    if (diff < 3600) return Math.floor(diff / 60) + "m ago";
    if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
    return Math.floor(diff / 86400) + "d ago";
  };

  const API_BASE = "/api/plugins/zerofactory-kanban";

  const COLUMNS = [
    { id: "triage", title: "Triage", icon: "📥", dotColor: "#818cf8", desc: "Initial requirements" },
    { id: "todo", title: "Todo", icon: "📋", dotColor: "#38bdf8", desc: "Backlog for dispatch" },
    { id: "ready", title: "Ready", icon: "🚀", dotColor: "#34d399", desc: "Assigned & worktree ready" },
    { id: "running", title: "Running", icon: "⚡", dotColor: "#fbbf24", desc: "Agent actively executing" },
    { id: "blocked", title: "Blocked", icon: "🛑", dotColor: "#f43f5e", desc: "PR / Human review needed" },
    { id: "done", title: "Done", icon: "✅", dotColor: "#a78bfa", desc: "Completed & merged" },
  ];

  const NEXT_STATUS_MAP = {
    triage: "todo",
    todo: "ready",
    ready: "running",
    running: "blocked",
    blocked: "done",
    done: "triage"
  };

  function ZeroFactoryKanbanApp() {
    const [boards, setBoards] = useState([]);
    const [selectedBoard, setSelectedBoard] = useState("");
    const [tasks, setTasks] = useState([]);
    const [stats, setStats] = useState(null);
    const [loading, setLoading] = useState(true);
    const [searchQuery, setSearchQuery] = useState("");
    const [assigneeFilter, setAssigneeFilter] = useState("all");
    const [priorityFilter, setPriorityFilter] = useState("all");
    const [autoRefresh, setAutoRefresh] = useState(true);
    const [isDispatching, setIsDispatching] = useState(false);
    const [dragOverCol, setDragOverCol] = useState(null);
    const [toast, setToast] = useState(null);

    // Modals
    const [selectedTask, setSelectedTask] = useState(null);
    const [showNewTaskModal, setShowNewTaskModal] = useState(false);
    const [showNewBoardModal, setShowNewBoardModal] = useState(false);
    const [showEditBoardModal, setShowEditBoardModal] = useState(false);
    const [newCommentText, setNewCommentText] = useState("");

    // Form States
    const [newTaskForm, setNewTaskForm] = useState({
      title: "",
      description: "",
      status: "triage",
      priority: "P2",
      assignee: "unassigned",
      tenant: ""
    });

    const [newBoardForm, setNewBoardForm] = useState({
      name: "",
      slug: "",
      description: "",
      git_url: ""
    });

    const [editBoardForm, setEditBoardForm] = useState({
      name: "",
      slug: "",
      description: "",
      git_url: ""
    });

    // Toast helper
    const showToast = useCallback((msg, type = "info") => {
      setToast({ message: msg, msg, type });
      setTimeout(() => setToast(null), 3500);
    }, []);

    // Load Boards
    const loadBoards = useCallback(async () => {
      try {
        const data = await fetchJSON(API_BASE + "/boards");
        if (data && data.boards) {
          setBoards(data.boards);
          if (data.boards.length > 0) {
            setSelectedBoard(prev => {
              if (prev && data.boards.some(b => b.slug === prev)) return prev;
              return data.boards[0].slug;
            });
          }
        }
      } catch (err) {
        console.error("Failed to fetch boards:", err);
      }
    }, [fetchJSON]);

    // Load Tasks & Stats
    const loadTasksAndStats = useCallback(async (boardSlug = selectedBoard) => {
      if (!boardSlug) return;
      try {
        const [tasksData, statsData] = await Promise.all([
          fetchJSON(API_BASE + "/tasks?board=" + encodeURIComponent(boardSlug)),
          fetchJSON(API_BASE + "/stats?board=" + encodeURIComponent(boardSlug))
        ]);

        if (tasksData && tasksData.tasks) {
          setTasks(tasksData.tasks);
        }
        if (statsData) {
          setStats(statsData);
        }
      } catch (err) {
        console.error("Failed to load kanban data:", err);
      } finally {
        setLoading(false);
      }
    }, [fetchJSON, selectedBoard]);

    // Initial load
    useEffect(() => {
      loadBoards();
      loadTasksAndStats(selectedBoard);
    }, [loadBoards, loadTasksAndStats, selectedBoard]);

    // Auto-refresh interval
    useEffect(() => {
      if (!autoRefresh) return;
      const timer = setInterval(() => {
        loadTasksAndStats(selectedBoard);
      }, 10000);
      return () => clearInterval(timer);
    }, [autoRefresh, loadTasksAndStats, selectedBoard]);

    // Filtered Tasks
    const filteredTasks = useMemo(() => {
      return tasks.filter((t) => {
        if (assigneeFilter !== "all" && t.assignee !== assigneeFilter) return false;
        if (priorityFilter !== "all" && t.priority !== priorityFilter) return false;
        if (searchQuery.trim()) {
          const q = searchQuery.toLowerCase();
          const matchTitle = (t.title || "").toLowerCase().includes(q);
          const matchDesc = (t.description || "").toLowerCase().includes(q);
          const matchId = (t.id || "").toLowerCase().includes(q);
          if (!matchTitle && !matchDesc && !matchId) return false;
        }
        return true;
      });
    }, [tasks, assigneeFilter, priorityFilter, searchQuery]);

    // Tasks grouped by column
    const tasksByColumn = useMemo(() => {
      const map = { triage: [], todo: [], ready: [], running: [], blocked: [], done: [] };
      filteredTasks.forEach((t) => {
        const col = t.status || "triage";
        if (map[col]) {
          map[col].push(t);
        } else {
          map["triage"].push(t);
        }
      });
      return map;
    }, [filteredTasks]);

    // Drag & Drop Handlers
    const handleDragStart = (e, task) => {
      e.dataTransfer.setData("text/plain", task.id);
      e.dataTransfer.effectAllowed = "move";
    };

    const handleDragOver = (e, colId) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      if (dragOverCol !== colId) {
        setDragOverCol(colId);
      }
    };

    const handleDragLeave = (e) => {
      e.preventDefault();
      setDragOverCol(null);
    };

    const handleDrop = async (e, targetStatus) => {
      e.preventDefault();
      setDragOverCol(null);
      const taskId = e.dataTransfer.getData("text/plain");
      if (!taskId) return;

      const current = tasks.find((t) => t.id === taskId);
      if (current && current.status === targetStatus) return;

      // Optimistic update
      setTasks((prev) =>
        prev.map((t) => (t.id === taskId ? { ...t, status: targetStatus } : t))
      );

      try {
        await fetchJSON(API_BASE + "/tasks/" + taskId + "/move", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: targetStatus, actor: "ui" })
        });
        showToast("Task " + taskId + " moved to " + targetStatus, "success");
        loadTasksAndStats();
      } catch (err) {
        showToast("Failed to move task: " + err.message, "error");
        loadTasksAndStats();
      }
    };

    // Advance task to next stage
    const handleAdvanceTask = async (task, e) => {
      if (e) e.stopPropagation();
      const nextStatus = NEXT_STATUS_MAP[task.status] || "todo";
      try {
        await fetchJSON(API_BASE + "/tasks/" + task.id + "/move", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: nextStatus, actor: "ui" })
        });
        showToast("Task " + task.id + " advanced to " + nextStatus, "success");
        loadTasksAndStats();
        if (selectedTask && selectedTask.id === task.id) {
          loadTaskDetails(task.id);
        }
      } catch (err) {
        showToast("Error advancing task: " + err.message, "error");
      }
    };

    // Task Details
    const loadTaskDetails = async (taskId) => {
      try {
        const res = await fetchJSON(API_BASE + "/tasks/" + taskId);
        if (res && res.task) {
          setSelectedTask(res.task);
        }
      } catch (err) {
        showToast("Failed to load task details", "error");
      }
    };

    // Refresh Session Progress
    const refreshSessionProgress = async (taskId) => {
      try {
        let prog = null;
        try {
          const res = await fetchJSON(API_BASE + "/tasks/" + taskId + "/session");
          if (res && res.session_progress) {
            prog = res.session_progress;
          }
        } catch (subErr) {
          // Fallback to task details if /session endpoint is unavailable
          const tRes = await fetchJSON(API_BASE + "/tasks/" + taskId);
          if (tRes && tRes.task && tRes.task.session_progress) {
            prog = tRes.task.session_progress;
          }
        }

        if (prog) {
          setSelectedTask(prev => prev && prev.id === taskId ? { ...prev, session_progress: prog } : prev);
          showToast("Session progress updated", "success");
        } else {
          showToast("No active session details found", "info");
        }
      } catch (err) {
        showToast("Failed to refresh session: " + (err.message || err), "error");
      }
    };

    // Auto-poll session progress while modal is open for a running task
    const activeRunningTaskId = (selectedTask && selectedTask.status === "running") ? selectedTask.id : null;
    useEffect(() => {
      if (!activeRunningTaskId) return;
      const timer = setInterval(async () => {
        try {
          const res = await fetchJSON(API_BASE + "/tasks/" + activeRunningTaskId + "/session");
          if (res && res.session_progress) {
            setSelectedTask(prev => prev && prev.id === activeRunningTaskId ? { ...prev, session_progress: res.session_progress } : prev);
          }
        } catch (e) {
          // Fallback poll
          try {
            const tRes = await fetchJSON(API_BASE + "/tasks/" + activeRunningTaskId);
            if (tRes && tRes.task && tRes.task.session_progress) {
              setSelectedTask(prev => prev && prev.id === activeRunningTaskId ? { ...prev, session_progress: tRes.task.session_progress } : prev);
            }
          } catch (_) {}
        }
      }, 3500);
      return () => clearInterval(timer);
    }, [activeRunningTaskId]);

    // Create Task
    const handleCreateTaskSubmit = async (e) => {
      e.preventDefault();
      if (!newTaskForm.title.trim()) return;

      try {
        const payload = {
          ...newTaskForm,
          board_slug: selectedBoard
        };
        const res = await fetchJSON(API_BASE + "/tasks", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        showToast("Task " + res.id + " created!", "success");
        setShowNewTaskModal(false);
        setNewTaskForm({
          title: "",
          description: "",
          status: "triage",
          priority: "P2",
          assignee: "unassigned",
          tenant: ""
        });
        loadTasksAndStats();
      } catch (err) {
        showToast("Failed to create task: " + err.message, "error");
      }
    };

    // Create Board
    const handleCreateBoardSubmit = async (e) => {
      e.preventDefault();
      if (!newBoardForm.slug.trim() || !newBoardForm.name.trim()) return;

      try {
        await fetchJSON(API_BASE + "/boards", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(newBoardForm)
        });
        showToast("Board '" + newBoardForm.slug + "' created!", "success");
        setShowNewBoardModal(false);
        const slug = newBoardForm.slug;
        setNewBoardForm({ name: "", slug: "", description: "", git_url: "" });
        await loadBoards();
        setSelectedBoard(slug);
      } catch (err) {
        showToast("Failed to create board: " + err.message, "error");
      }
    };

    // Open Edit Board Modal
    const handleOpenEditBoard = () => {
      if (!selectedBoard) return;
      const curr = boards.find((b) => b.slug === selectedBoard);
      if (curr) {
        setEditBoardForm({
          name: curr.name || "",
          slug: curr.slug || "",
          description: curr.description || "",
          git_url: curr.git_url || ""
        });
        setShowEditBoardModal(true);
      }
    };

    // Update Board Submit
    const handleUpdateBoardSubmit = async (e) => {
      e.preventDefault();
      if (!editBoardForm.slug || !editBoardForm.name.trim()) return;

      try {
        await fetchJSON(API_BASE + "/boards/" + encodeURIComponent(editBoardForm.slug), {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            name: editBoardForm.name.trim(),
            description: (editBoardForm.description || "").trim(),
            git_url: (editBoardForm.git_url || "").trim()
          })
        });
        showToast("Board '" + editBoardForm.slug + "' updated!", "success");
        setShowEditBoardModal(false);
        await loadBoards();
      } catch (err) {
        showToast("Failed to update board: " + err.message, "error");
      }
    };

    // Delete Board
    const handleDeleteBoard = async () => {
      if (!selectedBoard) return;
      const curr = boards.find((b) => b.slug === selectedBoard);
      const name = curr ? curr.name : selectedBoard;
      if (
        !window.confirm(
          "Are you sure you want to delete board \"" + name + "\" (" + selectedBoard + ")?\n\nThis will permanently remove the board, all its tasks, and clear its scheduled improvement scanner job."
        )
      ) {
        return;
      }

      try {
        await fetchJSON(API_BASE + "/boards/" + encodeURIComponent(selectedBoard), {
          method: "DELETE"
        });
        showToast("Board '" + name + "' deleted and scanner cron cleared", "info");
        setShowEditBoardModal(false);
        const remaining = boards.filter((b) => b.slug !== selectedBoard);
        setBoards(remaining);
        const nextSlug = remaining.length > 0 ? remaining[0].slug : "";
        setSelectedBoard(nextSlug);
        await loadBoards();
      } catch (err) {
        showToast("Failed to delete board: " + err.message, "error");
      }
    };

    // Add Comment
    const handleAddCommentSubmit = async (e) => {
      e.preventDefault();
      if (!newCommentText.trim() || !selectedTask) return;

      try {
        await fetchJSON(API_BASE + "/tasks/" + selectedTask.id + "/comments", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ author: "user", body: newCommentText.trim() })
        });
        setNewCommentText("");
        loadTaskDetails(selectedTask.id);
        showToast("Comment posted", "success");
      } catch (err) {
        showToast("Failed to post comment: " + err.message, "error");
      }
    };

    // Delete Task
    const handleDeleteTask = async (taskId) => {
      if (!window.confirm("Are you sure you want to delete task " + taskId + "?")) return;
      try {
        await fetchJSON(API_BASE + "/tasks/" + taskId, { method: "DELETE" });
        showToast("Task " + taskId + " deleted", "info");
        setSelectedTask(null);
        loadTasksAndStats();
      } catch (err) {
        showToast("Failed to delete task: " + err.message, "error");
      }
    };

    // Run Dispatcher
    const handleRunDispatcher = async () => {
      setIsDispatching(true);
      try {
        const res = await fetchJSON(API_BASE + "/dispatch/run", { method: "POST" });
        showToast(res.message || "Dispatch cycle finished", "success");
        loadTasksAndStats();
      } catch (err) {
        showToast("Dispatch error: " + err.message, "error");
      } finally {
        setIsDispatching(false);
      }
    };

    return React.createElement(
      "div",
      { className: "max-w-[1600px] mx-auto p-4 md:p-6 space-y-6 text-slate-100 font-sans antialiased min-h-screen" },

      // Toast Notification
      toast &&
        React.createElement(
          "div",
          {
            className: "fixed top-6 right-6 z-50 px-4 py-3 rounded-xl font-semibold text-sm shadow-2xl flex items-center gap-2.5 transition-all duration-200 border " +
              (toast.type === "error"
                ? "bg-rose-950/90 text-rose-200 border-rose-800 shadow-rose-950/50"
                : toast.type === "success"
                ? "bg-emerald-950/90 text-emerald-200 border-emerald-800 shadow-emerald-950/50"
                : "bg-indigo-950/90 text-indigo-200 border-indigo-800 shadow-indigo-950/50")
          },
          toast.message
        ),

      // Header Section
      React.createElement(
        "header",
        { className: "space-y-4 pb-5 border-b border-slate-800/80" },
        React.createElement(
          "div",
          { className: "flex flex-col lg:flex-row lg:items-center justify-between gap-4" },
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
          React.createElement(
            "div",
            { className: "flex flex-wrap items-center gap-2.5" },
            // Board Switcher
            React.createElement(
              "select",
              {
                className: "bg-slate-900/90 border border-slate-700/80 hover:border-slate-600 rounded-lg px-3 py-1.5 text-xs font-medium text-slate-200 focus:ring-1 focus:ring-indigo-500 focus:outline-none cursor-pointer transition-colors shadow-sm",
                value: selectedBoard,
                onChange: (e) => setSelectedBoard(e.target.value)
              },
              boards.map((b) =>
                React.createElement(
                  "option",
                  { key: b.slug, value: b.slug },
                  b.name + (b.task_count ? " (" + b.task_count + ")" : "")
                )
              )
            ),
            React.createElement(
              "button",
              {
                className: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800/80 hover:bg-slate-700/90 text-slate-200 border border-slate-700/80 hover:border-slate-600 shadow-sm transition-all duration-150 cursor-pointer",
                onClick: () => setShowNewBoardModal(true),
                title: "Create New Board"
              },
              "+ Board"
            ),
            selectedBoard &&
              React.createElement(
                "button",
                {
                  className: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800/80 hover:bg-slate-700/90 text-slate-200 border border-slate-700/80 hover:border-slate-600 shadow-sm transition-all duration-150 cursor-pointer",
                  onClick: handleOpenEditBoard,
                  title: "Edit board settings and manage board"
                },
                "⚙️ Edit Board"
              ),
            React.createElement(
              "button",
              {
                className: "inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white shadow-md shadow-emerald-600/25 transition-all duration-150 cursor-pointer disabled:opacity-60 disabled:cursor-wait" + (isDispatching ? " opacity-70 cursor-wait" : ""),
                onClick: handleRunDispatcher,
                disabled: isDispatching,
                title: "Trigger Zero Factory Dispatcher Cycle"
              },
              isDispatching
                ? React.createElement("span", { className: "zfk-spinning" }, "⏳")
                : "⚡",
              isDispatching ? " Dispatching..." : " Dispatch"
            ),
            React.createElement(
              "button",
              {
                className: "inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/25 transition-all duration-150 cursor-pointer",
                onClick: () => setShowNewTaskModal(true)
              },
              "+ New Task"
            ),
            React.createElement(
              "button",
              {
                className: "inline-flex items-center justify-center p-2 rounded-lg text-xs font-semibold bg-slate-800/80 hover:bg-slate-700/90 text-slate-200 border border-slate-700/80 hover:border-slate-600 shadow-sm transition-all duration-150 cursor-pointer",
                onClick: () => loadTasksAndStats(),
                title: "Refresh Board"
              },
              "🔄"
            )
          )
        ),

        // Metrics Banner
        stats &&
          React.createElement(
            "div",
            { className: "grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 pt-1" },
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
                React.createElement("span", { className: "text-[11px] text-slate-400 font-medium truncate mt-1" }, "Blocked / Review")
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
            )
          )
      ),

      // Toolbar (Search & Filter)
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
            placeholder: "Search tasks by title, description or ID...",
            value: searchQuery,
            onChange: (e) => setSearchQuery(e.target.value)
          })
        ),
        React.createElement(
          "div",
          { className: "flex items-center gap-1.5 flex-wrap" },
          React.createElement("span", { className: "text-xs text-slate-400 mr-1" }, "Role:"),
          ["all", "builder", "reviewer", "orchestrator", "unassigned"].map((role) =>
            React.createElement(
              "button",
              {
                key: role,
                type: "button",
                className: (assigneeFilter === role
                  ? "bg-indigo-600 text-white border-indigo-500 shadow-xs shadow-indigo-600/30"
                  : "bg-slate-800/70 text-slate-400 border-slate-700/60 hover:text-slate-200 hover:bg-slate-800") +
                  " px-2.5 py-1 rounded-md text-xs font-medium cursor-pointer transition-colors border text-center capitalize",
                onClick: () => setAssigneeFilter(role)
              },
              role
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
      ),

      // Main Kanban Board Grid
      React.createElement(
        "div",
        { className: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 xl:grid-cols-6 gap-3.5 items-start" },
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

                    const roleClass = t.assignee === "builder"
                      ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
                      : t.assignee === "reviewer"
                      ? "bg-cyan-500/15 text-cyan-300 border-cyan-500/30"
                      : t.assignee === "orchestrator"
                      ? "bg-purple-500/15 text-purple-300 border-purple-500/30"
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
                        t.tenant && React.createElement("span", { className: "inline-flex items-center gap-1 truncate max-w-[140px]" }, "📁 " + t.tenant),
                        t.branch_name && React.createElement("span", { className: "inline-flex items-center gap-1 text-indigo-300 font-mono truncate max-w-[120px]" }, "🌿 " + t.branch_name),
                        t.blocking_parent_count > 0 &&
                          React.createElement(
                            "span",
                            { className: "text-[0.625rem] font-medium px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20" },
                            "⏳ " + t.blocking_parent_count + " blocker"
                          )
                      ),
                      (t.status === "running" || (t.session_progress && t.session_progress.has_session)) &&
                        React.createElement(
                          "div",
                          { className: "flex items-center gap-2 p-1.5 rounded-md bg-emerald-500/10 border border-emerald-500/20 text-emerald-300 text-xs" },
                          React.createElement("span", {
                            className: "w-2 h-2 rounded-full shrink-0 " + (t.session_progress && t.session_progress.is_alive ? "bg-emerald-400 zfk-pulse-active" : "bg-slate-500")
                          }),
                          React.createElement(
                            "span",
                            { className: "text-[0.6875rem] truncate font-medium" },
                            (t.session_progress && t.session_progress.turn_count ? t.session_progress.turn_count + " turns" : "Executing") +
                            (t.session_progress && t.session_progress.last_action ? " • " + t.session_progress.last_action : "")
                          )
                        ),
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
      ),

      // Task Details Modal / Drawer
      selectedTask &&
        React.createElement(
          "div",
          { className: "fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4 overflow-y-auto", onClick: () => setSelectedTask(null) },
          React.createElement(
            "div",
            { className: "bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl max-w-2xl w-full max-h-[90vh] flex flex-col overflow-hidden text-slate-100", onClick: (e) => e.stopPropagation() },
            React.createElement(
              "div",
              { className: "flex items-center justify-between px-6 py-4 border-b border-slate-800 shrink-0" },
              React.createElement(
                "div",
                { className: "flex items-center gap-3 min-w-0" },
                React.createElement("span", { className: "font-mono text-xs font-semibold px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700/60" }, selectedTask.id),
                React.createElement("h2", { className: "text-base font-semibold text-white truncate m-0" }, selectedTask.title)
              ),
              React.createElement(
                "button",
                {
                  className: "text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors text-lg leading-none cursor-pointer w-8 h-8 flex items-center justify-center",
                  onClick: () => setSelectedTask(null)
                },
                "✕"
              )
            ),
            React.createElement(
              "div",
              { className: "p-6 space-y-5 overflow-y-auto zfk-scrollbar flex-1" },

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
                    ["unassigned", "builder", "reviewer", "orchestrator"].map((r) =>
                      React.createElement("option", { key: r, value: r }, r.charAt(0).toUpperCase() + r.slice(1))
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
                  React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Project / Tenant"),
                  React.createElement("input", {
                    className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none opacity-80 cursor-default",
                    value: selectedTask.tenant || "",
                    placeholder: "e.g. ~/git/hotcode-dev/zerofactory",
                    readOnly: true
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

              // Worktree & Branch Info
              selectedTask.workspace_path &&
                React.createElement(
                  "div",
                  {
                    className: "p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-xs space-y-1"
                  },
                  React.createElement("strong", { className: "text-emerald-400 font-semibold" }, "Git Worktree Active: "),
                  React.createElement("code", { className: "text-indigo-300 font-mono text-[0.6875rem] break-all" }, selectedTask.workspace_path),
                  selectedTask.branch_name &&
                    React.createElement("div", { className: "text-slate-400 text-[0.6875rem] mt-0.5" }, "Branch: " + selectedTask.branch_name)
                ),

              // Agent Session Progress Panel
              (selectedTask.status === "running" || (selectedTask.session_progress && selectedTask.session_progress.has_session)) &&
                React.createElement(
                  "div",
                  { className: "bg-slate-950/80 border border-indigo-500/30 rounded-xl p-4 space-y-3.5 shadow-sm" },
                  React.createElement(
                    "div",
                    { className: "flex flex-wrap items-center justify-between gap-2 pb-3 border-b border-slate-800/80" },
                    React.createElement(
                      "div",
                      { className: "flex items-center gap-2 flex-wrap" },
                      React.createElement("span", {
                        className: "w-2.5 h-2.5 rounded-full shrink-0 " + (selectedTask.session_progress && selectedTask.session_progress.is_alive ? "bg-emerald-400 zfk-pulse-active" : "bg-slate-500")
                      }),
                      React.createElement(
                        "span",
                        { className: "font-semibold text-xs text-white" },
                        selectedTask.session_progress && selectedTask.session_progress.is_alive
                          ? "⚡ Active Agent Execution"
                          : "⏹ Agent Session"
                      ),
                      selectedTask.session_progress && selectedTask.session_progress.worker_pid &&
                        React.createElement("span", { className: "text-[0.625rem] font-mono px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700/60" }, "PID: " + selectedTask.session_progress.worker_pid)
                    ),
                    React.createElement(
                      "div",
                      { className: "flex items-center gap-2" },
                      selectedTask.session_progress && selectedTask.session_progress.session_id &&
                        (() => {
                          const basePath = (typeof window !== "undefined" && window.__HERMES_BASE_PATH__)
                            ? ("/" + String(window.__HERMES_BASE_PATH__).replace(/^\/|\/$/g, ""))
                            : "";
                          const sId = selectedTask.session_progress.session_id;
                          const prof = selectedTask.session_progress.assignee || selectedTask.assignee || "";
                          const chatUrl = basePath + "/chat?resume=" + encodeURIComponent(sId) + (prof ? "&profile=" + encodeURIComponent(prof) : "");
                          return React.createElement(
                            "a",
                            {
                              href: chatUrl,
                              className: "inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white transition-colors cursor-pointer shadow-xs",
                              target: "_blank",
                              rel: "noreferrer",
                              title: "Open session in Hermes Chat"
                            },
                            "Open Chat ↗"
                          );
                        })(),
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
                  selectedTask.session_progress &&
                    React.createElement(
                      "div",
                      { className: "grid grid-cols-2 sm:grid-cols-4 gap-2.5" },
                      React.createElement(
                        "div",
                        { className: "bg-slate-900/80 border border-slate-800/80 rounded-lg p-2.5 flex flex-col gap-1" },
                        React.createElement("span", { className: "text-[0.625rem] font-semibold uppercase tracking-wider text-slate-400" }, "Session ID"),
                        React.createElement("code", { className: "text-xs font-medium text-indigo-300 font-mono truncate" }, selectedTask.session_progress.session_id || "Detecting...")
                      ),
                      React.createElement(
                        "div",
                        { className: "bg-slate-900/80 border border-slate-800/80 rounded-lg p-2.5 flex flex-col gap-1" },
                        React.createElement("span", { className: "text-[0.625rem] font-semibold uppercase tracking-wider text-slate-400" }, "Model"),
                        React.createElement("span", { className: "text-xs font-medium text-slate-200 truncate" }, selectedTask.session_progress.model || "Default")
                      ),
                      React.createElement(
                        "div",
                        { className: "bg-slate-900/80 border border-slate-800/80 rounded-lg p-2.5 flex flex-col gap-1" },
                        React.createElement("span", { className: "text-[0.625rem] font-semibold uppercase tracking-wider text-slate-400" }, "Turns / Msgs"),
                        React.createElement(
                          "span",
                          { className: "text-xs font-semibold text-emerald-400 truncate" },
                          (selectedTask.session_progress.turn_count || 0) + " turns (" + (selectedTask.session_progress.message_count || 0) + " msgs)"
                        )
                      ),
                      React.createElement(
                        "div",
                        { className: "bg-slate-900/80 border border-slate-800/80 rounded-lg p-2.5 flex flex-col gap-1" },
                        React.createElement("span", { className: "text-[0.625rem] font-semibold uppercase tracking-wider text-slate-400" }, "Last Activity"),
                        React.createElement("span", { className: "text-xs font-medium text-slate-200 truncate" }, timeAgo(selectedTask.session_progress.last_active) || "Just now")
                      )
                    ),

                  // Recent Agent Execution Steps
                  selectedTask.session_progress && selectedTask.session_progress.recent_steps && selectedTask.session_progress.recent_steps.length > 0 &&
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
                        selectedTask.session_progress.recent_steps.map((st) =>
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
                  selectedTask.session_progress && selectedTask.session_progress.log_tail &&
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
                        selectedTask.session_progress.log_tail
                      )
                    )
                ),

              // Dependencies List
              selectedTask.parents &&
                selectedTask.parents.length > 0 &&
                React.createElement(
                  "div",
                  { className: "space-y-1.5" },
                  React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Parent Dependencies (Must complete first)"),
                  React.createElement(
                    "div",
                    { className: "flex flex-col gap-1.5" },
                    selectedTask.parents.map((p) =>
                      React.createElement(
                        "div",
                        {
                          key: p.id,
                          className: "flex items-center justify-between p-2 rounded-md bg-slate-800/40 border border-slate-800 text-xs text-slate-300"
                        },
                        React.createElement("span", null, p.id + ": " + p.title),
                        React.createElement("span", { className: "text-[0.625rem] font-medium capitalize px-1.5 py-0.5 rounded border border-slate-700 bg-slate-800 text-slate-400" }, p.status)
                      )
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
            ),

            React.createElement(
              "div",
              { className: "flex items-center justify-between px-6 py-3.5 border-t border-slate-800 bg-slate-900/50 shrink-0" },
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
        ),

      // New Task Modal
      showNewTaskModal &&
        React.createElement(
          "div",
          { className: "fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4 overflow-y-auto", onClick: () => setShowNewTaskModal(false) },
          React.createElement(
            "div",
            { className: "bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl max-w-xl w-full max-h-[90vh] flex flex-col overflow-hidden text-slate-100", onClick: (e) => e.stopPropagation() },
            React.createElement(
              "div",
              { className: "flex items-center justify-between px-6 py-4 border-b border-slate-800 shrink-0" },
              React.createElement("h2", { className: "text-base font-semibold text-white m-0" }, "Create New Zero Factory Task"),
              React.createElement(
                "button",
                {
                  className: "text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors text-lg leading-none cursor-pointer w-8 h-8 flex items-center justify-center",
                  onClick: () => setShowNewTaskModal(false)
                },
                "✕"
              )
            ),
            React.createElement(
              "form",
              { onSubmit: handleCreateTaskSubmit, className: "flex flex-col flex-1 overflow-hidden m-0" },
              React.createElement(
                "div",
                { className: "p-6 space-y-4 overflow-y-auto zfk-scrollbar flex-1" },
                React.createElement(
                  "div",
                  { className: "space-y-1.5" },
                  React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Task Title *"),
                  React.createElement("input", {
                    className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
                    required: true,
                    placeholder: "e.g. Implement caching layer for Redis",
                    value: newTaskForm.title,
                    onChange: (e) => setNewTaskForm({ ...newTaskForm, title: e.target.value })
                  })
                ),
                React.createElement(
                  "div",
                  { className: "grid grid-cols-1 sm:grid-cols-2 gap-4" },
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Assignee"),
                    React.createElement(
                      "select",
                      {
                        className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors cursor-pointer",
                        value: newTaskForm.assignee,
                        onChange: (e) => setNewTaskForm({ ...newTaskForm, assignee: e.target.value })
                      },
                      React.createElement("option", { value: "unassigned" }, "Unassigned (Auto-Assign)"),
                      React.createElement("option", { value: "builder" }, "Builder"),
                      React.createElement("option", { value: "reviewer" }, "Reviewer"),
                      React.createElement("option", { value: "orchestrator" }, "Orchestrator")
                    )
                  ),
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Priority"),
                    React.createElement(
                      "select",
                      {
                        className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors cursor-pointer",
                        value: newTaskForm.priority,
                        onChange: (e) => setNewTaskForm({ ...newTaskForm, priority: e.target.value })
                      },
                      React.createElement("option", { value: "P0" }, "P0 - Critical / Blocker"),
                      React.createElement("option", { value: "P1" }, "P1 - High"),
                      React.createElement("option", { value: "P2" }, "P2 - Normal"),
                      React.createElement("option", { value: "P3" }, "P3 - Low")
                    )
                  )
                ),
                React.createElement(
                  "div",
                  { className: "grid grid-cols-1 sm:grid-cols-2 gap-4" },
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Initial Column"),
                    React.createElement(
                      "select",
                      {
                        className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors cursor-pointer",
                        value: newTaskForm.status,
                        onChange: (e) => setNewTaskForm({ ...newTaskForm, status: e.target.value })
                      },
                      COLUMNS.map((c) => React.createElement("option", { key: c.id, value: c.id }, c.title))
                    )
                  ),
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Repository / Tenant"),
                    React.createElement("input", {
                      className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
                      placeholder: "e.g. zerofactory or git repo path",
                      value: newTaskForm.tenant,
                      onChange: (e) => setNewTaskForm({ ...newTaskForm, tenant: e.target.value })
                    })
                  )
                ),
                React.createElement(
                  "div",
                  { className: "space-y-1.5" },
                  React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Description & Acceptance Criteria"),
                  React.createElement("textarea", {
                    className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors min-h-[100px] resize-y leading-relaxed",
                    placeholder: "Provide context, requirements, edge cases, and steps for the agent...",
                    value: newTaskForm.description,
                    onChange: (e) => setNewTaskForm({ ...newTaskForm, description: e.target.value })
                  })
                )
              ),
              React.createElement(
                "div",
                { className: "flex items-center justify-end gap-2.5 px-6 py-3.5 border-t border-slate-800 bg-slate-900/50 shrink-0" },
                React.createElement(
                  "button",
                  {
                    type: "button",
                    className: "px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 transition-colors cursor-pointer",
                    onClick: () => setShowNewTaskModal(false)
                  },
                  "Cancel"
                ),
                React.createElement(
                  "button",
                  {
                    type: "submit",
                    className: "px-4 py-1.5 rounded-lg text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-500 transition-colors cursor-pointer shadow-xs shadow-indigo-600/30"
                  },
                  "Create Task"
                )
              )
            )
          )
        ),

      // New Board Modal
      showNewBoardModal &&
        React.createElement(
          "div",
          { className: "fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4 overflow-y-auto", onClick: () => setShowNewBoardModal(false) },
          React.createElement(
            "div",
            { className: "bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl max-w-xl w-full max-h-[90vh] flex flex-col overflow-hidden text-slate-100", onClick: (e) => e.stopPropagation() },
            React.createElement(
              "div",
              { className: "flex items-center justify-between px-6 py-4 border-b border-slate-800 shrink-0" },
              React.createElement("h2", { className: "text-base font-semibold text-white m-0" }, "Create New Project Board"),
              React.createElement(
                "button",
                {
                  className: "text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors text-lg leading-none cursor-pointer w-8 h-8 flex items-center justify-center",
                  onClick: () => setShowNewBoardModal(false)
                },
                "✕"
              )
            ),
            React.createElement(
              "form",
              { onSubmit: handleCreateBoardSubmit, className: "flex flex-col flex-1 overflow-hidden m-0" },
              React.createElement(
                "div",
                { className: "p-6 space-y-4 overflow-y-auto zfk-scrollbar flex-1" },
                React.createElement(
                  "div",
                  { className: "space-y-1.5" },
                  React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Board Name *"),
                  React.createElement("input", {
                    className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
                    required: true,
                    placeholder: "e.g. ZeroHub Project",
                    value: newBoardForm.name,
                    onChange: (e) => {
                      const name = e.target.value;
                      const slug = name.toLowerCase().replace(/[^a-z0-9]/g, "-").replace(/-+/g, "-");
                      setNewBoardForm({ ...newBoardForm, name, slug: newBoardForm.slug || slug });
                    }
                  })
                ),
                React.createElement(
                  "div",
                  { className: "space-y-1.5" },
                  React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Slug (URL identifier) *"),
                  React.createElement("input", {
                    className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
                    required: true,
                    placeholder: "e.g. zerohub",
                    value: newBoardForm.slug,
                    onChange: (e) => setNewBoardForm({ ...newBoardForm, slug: e.target.value })
                  })
                ),
                React.createElement(
                  "div",
                  { className: "space-y-1.5" },
                  React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Remote Git URL"),
                  React.createElement("input", {
                    className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
                    placeholder: "https://github.com/org/repo.git",
                    value: newBoardForm.git_url,
                    onChange: (e) => setNewBoardForm({ ...newBoardForm, git_url: e.target.value })
                  })
                ),
                React.createElement(
                  "div",
                  { className: "space-y-1.5" },
                  React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Description"),
                  React.createElement("input", {
                    className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
                    placeholder: "Short description of this board's scope",
                    value: newBoardForm.description,
                    onChange: (e) => setNewBoardForm({ ...newBoardForm, description: e.target.value })
                  })
                )
              ),
              React.createElement(
                "div",
                { className: "flex items-center justify-end gap-2.5 px-6 py-3.5 border-t border-slate-800 bg-slate-900/50 shrink-0" },
                React.createElement(
                  "button",
                  {
                    type: "button",
                    className: "px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 transition-colors cursor-pointer",
                    onClick: () => setShowNewBoardModal(false)
                  },
                  "Cancel"
                ),
                React.createElement(
                  "button",
                  {
                    type: "submit",
                    className: "px-4 py-1.5 rounded-lg text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-500 transition-colors cursor-pointer shadow-xs shadow-indigo-600/30"
                  },
                  "Create Board"
                )
              )
            )
          )
        ),

      // Edit Board Modal
      showEditBoardModal &&
        React.createElement(
          "div",
          { className: "fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4 overflow-y-auto", onClick: () => setShowEditBoardModal(false) },
          React.createElement(
            "div",
            { className: "bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl max-w-xl w-full max-h-[90vh] flex flex-col overflow-hidden text-slate-100", onClick: (e) => e.stopPropagation() },
            React.createElement(
              "div",
              { className: "flex items-center justify-between px-6 py-4 border-b border-slate-800 shrink-0" },
              React.createElement("h2", { className: "text-base font-semibold text-white m-0" }, "Edit Board: " + (editBoardForm.name || editBoardForm.slug)),
              React.createElement(
                "button",
                {
                  className: "text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors text-lg leading-none cursor-pointer w-8 h-8 flex items-center justify-center",
                  onClick: () => setShowEditBoardModal(false)
                },
                "✕"
              )
            ),
            React.createElement(
              "form",
              { onSubmit: handleUpdateBoardSubmit, className: "flex flex-col flex-1 overflow-hidden m-0" },
              React.createElement(
                "div",
                { className: "p-6 space-y-4 overflow-y-auto zfk-scrollbar flex-1" },
                React.createElement(
                  "div",
                  { className: "space-y-1.5" },
                  React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Board Name *"),
                  React.createElement("input", {
                    className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
                    required: true,
                    placeholder: "e.g. ZeroHub Project",
                    value: editBoardForm.name,
                    onChange: (e) => setEditBoardForm({ ...editBoardForm, name: e.target.value })
                  })
                ),
                React.createElement(
                  "div",
                  { className: "space-y-1.5" },
                  React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Slug (URL identifier)"),
                  React.createElement("input", {
                    className: "w-full bg-slate-950/60 border border-slate-800/60 rounded-lg px-3 py-2 text-xs text-slate-400 cursor-not-allowed opacity-60 outline-none",
                    disabled: true,
                    value: editBoardForm.slug
                  })
                ),
                React.createElement(
                  "div",
                  { className: "space-y-1.5" },
                  React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Remote Git URL"),
                  React.createElement("input", {
                    className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
                    placeholder: "https://github.com/org/repo.git",
                    value: editBoardForm.git_url,
                    onChange: (e) => setEditBoardForm({ ...editBoardForm, git_url: e.target.value })
                  })
                ),
                React.createElement(
                  "div",
                  { className: "space-y-1.5" },
                  React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Description"),
                  React.createElement("input", {
                    className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
                    placeholder: "Short description of this board's scope",
                    value: editBoardForm.description,
                    onChange: (e) => setEditBoardForm({ ...editBoardForm, description: e.target.value })
                  })
                )
              ),
              React.createElement(
                "div",
                { className: "flex items-center justify-end gap-2.5 px-6 py-3.5 border-t border-slate-800 bg-slate-900/50 shrink-0" },
                React.createElement(
                  "button",
                  {
                    type: "button",
                    className: "mr-auto px-3.5 py-1.5 rounded-lg text-xs font-medium text-rose-400 hover:text-rose-300 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 transition-colors cursor-pointer",
                    onClick: handleDeleteBoard,
                    title: "Delete this board and its scheduled scanner job"
                  },
                  "🗑️ Remove Board"
                ),
                React.createElement(
                  "button",
                  {
                    type: "button",
                    className: "px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 transition-colors cursor-pointer",
                    onClick: () => setShowEditBoardModal(false)
                  },
                  "Cancel"
                ),
                React.createElement(
                  "button",
                  {
                    type: "submit",
                    className: "px-4 py-1.5 rounded-lg text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-500 transition-colors cursor-pointer shadow-xs shadow-indigo-600/30"
                  },
                  "Save Changes"
                )
              )
            )
          )
        )
    );
  }

  // Register in Hermes Plugins Registry
  window.__HERMES_PLUGINS__.register("zerofactory-kanban", ZeroFactoryKanbanApp);
})();
