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
      { className: "zfk-container" },

      // Toast Notification
      toast &&
        React.createElement(
          "div",
          {
            style: {
              position: "fixed",
              top: "1.5rem",
              right: "1.5rem",
              zIndex: 9999,
              padding: "0.75rem 1.25rem",
              borderRadius: "0.5rem",
              background: toast.type === "error" ? "#ef4444" : toast.type === "success" ? "#10b981" : "#6366f1",
              color: "#fff",
              fontWeight: 600,
              fontSize: "0.875rem",
              boxShadow: "0 10px 25px rgba(0,0,0,0.4)"
            }
          },
          toast.message
        ),

      // Header Section
      React.createElement(
        "header",
        { className: "zfk-header" },
        React.createElement(
          "div",
          { className: "zfk-header-top" },
          React.createElement(
            "div",
            { className: "zfk-title-group" },
            React.createElement("div", { className: "zfk-logo-badge" }, "ZF"),
            React.createElement(
              "div",
              null,
              React.createElement("h1", { className: "zfk-title" }, "Zero Factory Kanban"),
              React.createElement("p", { className: "zfk-subtitle" }, "Autonomous Multi-Agent Coordination Engine")
            )
          ),
          React.createElement(
            "div",
            { className: "zfk-actions-group" },
            // Board Switcher
            React.createElement(
              "select",
              {
                className: "zfk-form-select",
                style: { width: "auto", minWidth: "150px" },
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
                className: "zfk-btn zfk-btn-secondary",
                onClick: () => setShowNewBoardModal(true),
                title: "Create New Board"
              },
              "+ Board"
            ),
            React.createElement(
              "button",
              {
                className: "zfk-btn zfk-btn-dispatch" + (isDispatching ? " loading" : ""),
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
                className: "zfk-btn zfk-btn-primary",
                onClick: () => setShowNewTaskModal(true)
              },
              "+ New Task"
            ),
            React.createElement(
              "button",
              {
                className: "zfk-btn zfk-btn-secondary",
                style: { padding: "0.45rem 0.65rem" },
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
            { className: "zfk-stats-row" },
            React.createElement(
              "div",
              { className: "zfk-stat-card" },
              React.createElement("div", { className: "zfk-stat-icon", style: { background: "rgba(99, 102, 241, 0.15)", color: "#818cf8" } }, "📊"),
              React.createElement(
                "div",
                { className: "zfk-stat-info" },
                React.createElement("span", { className: "zfk-stat-value" }, stats.total || 0),
                React.createElement("span", { className: "zfk-stat-label" }, "Total Tasks")
              )
            ),
            React.createElement(
              "div",
              { className: "zfk-stat-card" },
              React.createElement("div", { className: "zfk-stat-icon", style: { background: "rgba(245, 158, 11, 0.15)", color: "#fbbf24" } }, "⚡"),
              React.createElement(
                "div",
                { className: "zfk-stat-info" },
                React.createElement("span", { className: "zfk-stat-value" }, (stats.columns && stats.columns.running) || 0),
                React.createElement("span", { className: "zfk-stat-label" }, "Active In Progress")
              )
            ),
            React.createElement(
              "div",
              { className: "zfk-stat-card" },
              React.createElement("div", { className: "zfk-stat-icon", style: { background: "rgba(244, 63, 94, 0.15)", color: "#f43f5e" } }, "🛑"),
              React.createElement(
                "div",
                { className: "zfk-stat-info" },
                React.createElement("span", { className: "zfk-stat-value" }, (stats.columns && stats.columns.blocked) || 0),
                React.createElement("span", { className: "zfk-stat-label" }, "Blocked / Review")
              )
            ),
            React.createElement(
              "div",
              { className: "zfk-stat-card" },
              React.createElement("div", { className: "zfk-stat-icon", style: { background: "rgba(139, 92, 246, 0.15)", color: "#a78bfa" } }, "✅"),
              React.createElement(
                "div",
                { className: "zfk-stat-info" },
                React.createElement("span", { className: "zfk-stat-value" }, (stats.columns && stats.columns.done) || 0),
                React.createElement("span", { className: "zfk-stat-label" }, "Completed")
              )
            ),
            React.createElement(
              "div",
              { className: "zfk-stat-card" },
              React.createElement("div", { className: "zfk-stat-icon", style: { background: "rgba(16, 185, 129, 0.15)", color: "#34d399" } }, "🌿"),
              React.createElement(
                "div",
                { className: "zfk-stat-info" },
                React.createElement("span", { className: "zfk-stat-value" }, stats.active_worktrees || 0),
                React.createElement("span", { className: "zfk-stat-label" }, "Git Worktrees")
              )
            )
          )
      ),

      // Toolbar (Search & Filter)
      React.createElement(
        "div",
        { className: "zfk-toolbar" },
        React.createElement(
          "div",
          { className: "zfk-search-box" },
          React.createElement("span", { className: "zfk-search-icon" }, "🔍"),
          React.createElement("input", {
            type: "text",
            className: "zfk-search-input",
            placeholder: "Search tasks by title, description or ID...",
            value: searchQuery,
            onChange: (e) => setSearchQuery(e.target.value)
          })
        ),
        React.createElement(
          "div",
          { className: "zfk-filter-pills" },
          React.createElement("span", { style: { fontSize: "0.75rem", color: "var(--zfk-text-muted)", marginRight: "0.25rem" } }, "Role:"),
          ["all", "builder", "reviewer", "orchestrator", "unassigned"].map((role) =>
            React.createElement(
              "div",
              {
                key: role,
                className: "zfk-pill" + (assigneeFilter === role ? " active" : ""),
                onClick: () => setAssigneeFilter(role)
              },
              role.charAt(0).toUpperCase() + role.slice(1)
            )
          )
        ),
        React.createElement(
          "div",
          { className: "zfk-filter-pills" },
          React.createElement("span", { style: { fontSize: "0.75rem", color: "var(--zfk-text-muted)", marginRight: "0.25rem" } }, "Prio:"),
          ["all", "P0", "P1", "P2", "P3"].map((prio) =>
            React.createElement(
              "div",
              {
                key: prio,
                className: "zfk-pill" + (priorityFilter === prio ? " active" : ""),
                onClick: () => setPriorityFilter(prio)
              },
              prio
            )
          )
        ),
        React.createElement(
          "label",
          { style: { display: "flex", alignItems: "center", gap: "0.4rem", fontSize: "0.75rem", color: "var(--zfk-text-secondary)", cursor: "pointer" } },
          React.createElement("input", {
            type: "checkbox",
            checked: autoRefresh,
            onChange: (e) => setAutoRefresh(e.target.checked)
          }),
          "Live 10s Poll"
        )
      ),

      // Main Kanban Board Grid
      React.createElement(
        "div",
        { className: "zfk-board" },
        COLUMNS.map((col) => {
          const colTasks = tasksByColumn[col.id] || [];
          const isOver = dragOverCol === col.id;

          return React.createElement(
            "div",
            {
              key: col.id,
              className: "zfk-column" + (isOver ? " drag-over" : ""),
              onDragOver: (e) => handleDragOver(e, col.id),
              onDragLeave: handleDragLeave,
              onDrop: (e) => handleDrop(e, col.id)
            },
            React.createElement(
              "div",
              { className: "zfk-col-header" },
              React.createElement(
                "div",
                { className: "zfk-col-title-group" },
                React.createElement("div", { className: "zfk-col-dot", style: { backgroundColor: col.dotColor, color: col.dotColor } }),
                React.createElement("h3", { className: "zfk-col-title" }, col.title)
              ),
              React.createElement("span", { className: "zfk-col-badge" }, colTasks.length)
            ),

            React.createElement(
              "div",
              { className: "zfk-card-stack" },
              colTasks.length === 0
                ? React.createElement(
                    "div",
                    { className: "zfk-col-empty" },
                    "No " + col.title + " tasks",
                    React.createElement("br", null),
                    React.createElement("span", { style: { opacity: 0.6, fontSize: "0.6875rem" } }, "Drop tasks here")
                  )
                : colTasks.map((t) => {
                    const isRunning = t.status === "running";
                    return React.createElement(
                      "div",
                      {
                        key: t.id,
                        className: "zfk-card" + (isRunning ? " zfk-running-glow" : ""),
                        draggable: true,
                        onDragStart: (e) => handleDragStart(e, t),
                        onClick: () => loadTaskDetails(t.id)
                      },
                      React.createElement(
                        "div",
                        { className: "zfk-card-top" },
                        React.createElement("span", { className: "zfk-card-id" }, t.id),
                        React.createElement(
                          "div",
                          { className: "zfk-card-badges" },
                          React.createElement(
                            "span",
                            { className: "zfk-prio-badge zfk-prio-" + (t.priority ? t.priority.toLowerCase() : "p2") },
                            t.priority || "P2"
                          ),
                          React.createElement(
                            "span",
                            { className: "zfk-role-badge zfk-role-" + (t.assignee || "unassigned") },
                            t.assignee || "unassigned"
                          )
                        )
                      ),
                      React.createElement("h4", { className: "zfk-card-title" }, t.title),
                      React.createElement(
                        "div",
                        { className: "zfk-card-meta" },
                        t.tenant && React.createElement("span", { className: "zfk-meta-item" }, "📁 " + t.tenant),
                        t.branch_name && React.createElement("span", { className: "zfk-meta-item", style: { color: "#a5b4fc" } }, "🌿 " + t.branch_name),
                        t.blocking_parent_count > 0 &&
                          React.createElement(
                            "span",
                            { className: "zfk-dep-badge" },
                            "⏳ " + t.blocking_parent_count + " blocker"
                          )
                      ),
                      (t.status === "running" || (t.session_progress && t.session_progress.has_session)) &&
                        React.createElement(
                          "div",
                          { className: "zfk-card-progress" },
                          React.createElement("span", {
                            className: "zfk-pulse-dot" + (t.session_progress && t.session_progress.is_alive ? " zfk-pulse-active" : " zfk-pulse-idle")
                          }),
                          React.createElement(
                            "span",
                            { className: "zfk-progress-text" },
                            (t.session_progress && t.session_progress.turn_count ? t.session_progress.turn_count + " turns" : "Executing") +
                            (t.session_progress && t.session_progress.last_action ? " • " + t.session_progress.last_action : "")
                          )
                        ),
                      React.createElement(
                        "div",
                        { className: "zfk-card-footer" },
                        React.createElement(
                          "span",
                          { style: { fontSize: "0.6875rem", color: "var(--zfk-text-muted)" } },
                          timeAgo(t.updated_at || t.created_at)
                        ),
                        React.createElement(
                          "div",
                          { className: "zfk-card-actions" },
                          t.comment_count > 0 &&
                            React.createElement(
                              "span",
                              { className: "zfk-btn-mini", title: t.comment_count + " comments" },
                              "💬 " + t.comment_count
                            ),
                          React.createElement(
                            "button",
                            {
                              className: "zfk-btn-mini zfk-btn-advance",
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
          { className: "zfk-modal-backdrop", onClick: () => setSelectedTask(null) },
          React.createElement(
            "div",
            { className: "zfk-modal", onClick: (e) => e.stopPropagation() },
            React.createElement(
              "div",
              { className: "zfk-modal-header" },
              React.createElement(
                "div",
                { style: { display: "flex", alignItems: "center", gap: "0.75rem" } },
                React.createElement("span", { className: "zfk-card-id", style: { fontSize: "0.8125rem" } }, selectedTask.id),
                React.createElement("h2", { className: "zfk-modal-title" }, selectedTask.title)
              ),
              React.createElement(
                "button",
                { className: "zfk-modal-close", onClick: () => setSelectedTask(null) },
                "✕"
              )
            ),
            React.createElement(
              "div",
              { className: "zfk-modal-body" },

              // Status & Controls Row
              React.createElement(
                "div",
                { className: "zfk-form-row" },
                React.createElement(
                  "div",
                  { className: "zfk-form-group" },
                  React.createElement("label", { className: "zfk-form-label" }, "Status"),
                  React.createElement(
                    "select",
                    {
                      className: "zfk-form-select",
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
                  { className: "zfk-form-group" },
                  React.createElement("label", { className: "zfk-form-label" }, "Assignee"),
                  React.createElement(
                    "select",
                    {
                      className: "zfk-form-select",
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
                { className: "zfk-form-row" },
                React.createElement(
                  "div",
                  { className: "zfk-form-group" },
                  React.createElement("label", { className: "zfk-form-label" }, "Priority"),
                  React.createElement(
                    "select",
                    {
                      className: "zfk-form-select",
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
                  { className: "zfk-form-group" },
                  React.createElement("label", { className: "zfk-form-label" }, "Project / Tenant"),
                  React.createElement("input", {
                    className: "zfk-form-input",
                    value: selectedTask.tenant || "",
                    placeholder: "e.g. ~/git/hotcode-dev/zerofactory",
                    readOnly: true
                  })
                )
              ),

              // Description
              React.createElement(
                "div",
                { className: "zfk-form-group" },
                React.createElement("label", { className: "zfk-form-label" }, "Description / Acceptance Criteria"),
                React.createElement(
                  "div",
                  {
                    style: {
                      background: "rgba(15, 23, 42, 0.6)",
                      border: "1px solid var(--zfk-border)",
                      borderRadius: "0.5rem",
                      padding: "0.75rem",
                      fontSize: "0.875rem",
                      lineHeight: "1.5",
                      whiteSpace: "pre-wrap"
                    }
                  },
                  selectedTask.description || "(No description provided)"
                )
              ),

              // Worktree & Branch Info
              selectedTask.workspace_path &&
                React.createElement(
                  "div",
                  {
                    style: {
                      padding: "0.65rem 0.85rem",
                      background: "rgba(16, 185, 129, 0.08)",
                      border: "1px solid rgba(16, 185, 129, 0.25)",
                      borderRadius: "0.5rem",
                      fontSize: "0.75rem"
                    }
                  },
                  React.createElement("strong", { style: { color: "#34d399" } }, "Git Worktree Active: "),
                  React.createElement("code", { style: { color: "#a5b4fc" } }, selectedTask.workspace_path),
                  selectedTask.branch_name &&
                    React.createElement("div", { style: { marginTop: "0.25rem", color: "var(--zfk-text-secondary)" } }, "Branch: " + selectedTask.branch_name)
                ),

              // Agent Session Progress Panel
              (selectedTask.status === "running" || (selectedTask.session_progress && selectedTask.session_progress.has_session)) &&
                React.createElement(
                  "div",
                  { className: "zfk-session-panel" },
                  React.createElement(
                    "div",
                    { className: "zfk-session-header" },
                    React.createElement(
                      "div",
                      { style: { display: "flex", alignItems: "center", gap: "0.5rem" } },
                      React.createElement("span", {
                        className: "zfk-pulse-dot" + (selectedTask.session_progress && selectedTask.session_progress.is_alive ? " zfk-pulse-active" : " zfk-pulse-idle")
                      }),
                      React.createElement(
                        "span",
                        { style: { fontWeight: "600", fontSize: "0.875rem", color: "#f8fafc" } },
                        selectedTask.session_progress && selectedTask.session_progress.is_alive
                          ? "⚡ Active Agent Execution"
                          : "⏹ Agent Session"
                      ),
                      selectedTask.session_progress && selectedTask.session_progress.worker_pid &&
                        React.createElement("span", { className: "zfk-pill-badge" }, "PID: " + selectedTask.session_progress.worker_pid)
                    ),
                    React.createElement(
                      "div",
                      { style: { display: "flex", gap: "0.5rem", alignItems: "center" } },
                      selectedTask.session_progress && selectedTask.session_progress.session_id &&
                        React.createElement(
                          "a",
                          {
                            href: "#/chat?session=" + selectedTask.session_progress.session_id,
                            className: "zfk-btn-session-link",
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
                          className: "zfk-btn-mini",
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
                      { className: "zfk-session-stats-grid" },
                      React.createElement(
                        "div",
                        { className: "zfk-session-stat" },
                        React.createElement("span", { className: "zfk-session-stat-lbl" }, "Session ID"),
                        React.createElement("code", { className: "zfk-session-stat-val", style: { color: "#a5b4fc" } }, selectedTask.session_progress.session_id || "Detecting...")
                      ),
                      React.createElement(
                        "div",
                        { className: "zfk-session-stat" },
                        React.createElement("span", { className: "zfk-session-stat-lbl" }, "Model"),
                        React.createElement("span", { className: "zfk-session-stat-val" }, selectedTask.session_progress.model || "Default")
                      ),
                      React.createElement(
                        "div",
                        { className: "zfk-session-stat" },
                        React.createElement("span", { className: "zfk-session-stat-lbl" }, "Turns / Msgs"),
                        React.createElement(
                          "span",
                          { className: "zfk-session-stat-val", style: { color: "#34d399", fontWeight: "600" } },
                          (selectedTask.session_progress.turn_count || 0) + " turns (" + (selectedTask.session_progress.message_count || 0) + " msgs)"
                        )
                      ),
                      React.createElement(
                        "div",
                        { className: "zfk-session-stat" },
                        React.createElement("span", { className: "zfk-session-stat-lbl" }, "Last Activity"),
                        React.createElement("span", { className: "zfk-session-stat-val" }, timeAgo(selectedTask.session_progress.last_active) || "Just now")
                      )
                    ),

                  // Recent Agent Execution Steps
                  selectedTask.session_progress && selectedTask.session_progress.recent_steps && selectedTask.session_progress.recent_steps.length > 0 &&
                    React.createElement(
                      "div",
                      { style: { marginTop: "0.75rem" } },
                      React.createElement(
                        "div",
                        { style: { fontSize: "0.75rem", fontWeight: "600", color: "var(--zfk-text-secondary)", marginBottom: "0.35rem" } },
                        "Recent Agent Actions & Tool Executions"
                      ),
                      React.createElement(
                        "div",
                        { className: "zfk-steps-timeline" },
                        selectedTask.session_progress.recent_steps.map((st) =>
                          React.createElement(
                            "div",
                            { key: st.id, className: "zfk-step-item" },
                            React.createElement(
                              "div",
                              { style: { display: "flex", alignItems: "center", gap: "0.4rem" } },
                              React.createElement(
                                "span",
                                { className: "zfk-step-role-badge zfk-step-" + (st.tool_name ? "tool" : st.role) },
                                st.tool_name ? "tool: " + st.tool_name : st.role
                              ),
                              React.createElement(
                                "span",
                                { style: { fontSize: "0.6875rem", color: "var(--zfk-text-muted)" } },
                                timeAgo(st.timestamp)
                              )
                            ),
                            React.createElement("div", { className: "zfk-step-snippet" }, st.snippet)
                          )
                        )
                      )
                    ),

                  // Worker Log Tail (Collapsible)
                  selectedTask.session_progress && selectedTask.session_progress.log_tail &&
                    React.createElement(
                      "details",
                      { style: { marginTop: "0.75rem", fontSize: "0.75rem" } },
                      React.createElement(
                        "summary",
                        { style: { cursor: "pointer", color: "var(--zfk-text-secondary)", fontWeight: "500" } },
                        "📄 Show Worker Process Log Output"
                      ),
                      React.createElement(
                        "pre",
                        { className: "zfk-log-tail" },
                        selectedTask.session_progress.log_tail
                      )
                    )
                ),

              // Dependencies List
              selectedTask.parents &&
                selectedTask.parents.length > 0 &&
                React.createElement(
                  "div",
                  { className: "zfk-form-group" },
                  React.createElement("label", { className: "zfk-form-label" }, "Parent Dependencies (Must complete first)"),
                  React.createElement(
                    "div",
                    { style: { display: "flex", flexDirection: "column", gap: "0.35rem" } },
                    selectedTask.parents.map((p) =>
                      React.createElement(
                        "div",
                        {
                          key: p.id,
                          style: {
                            display: "flex",
                            alignItems: "center",
                            justifyContent: "space-between",
                            padding: "0.4rem 0.6rem",
                            background: "rgba(30, 41, 59, 0.5)",
                            borderRadius: "0.35rem",
                            border: "1px solid var(--zfk-border)",
                            fontSize: "0.75rem"
                          }
                        },
                        React.createElement("span", null, p.id + ": " + p.title),
                        React.createElement("span", { className: "zfk-role-badge zfk-role-" + p.assignee }, p.status)
                      )
                    )
                  )
                ),

              // Comments Section
              React.createElement(
                "div",
                { className: "zfk-form-group" },
                React.createElement(
                  "label",
                  { className: "zfk-form-label" },
                  "Discussion & Activity (" + ((selectedTask.comments && selectedTask.comments.length) || 0) + ")"
                ),
                React.createElement(
                  "div",
                  { className: "zfk-comment-list" },
                  (!selectedTask.comments || selectedTask.comments.length === 0)
                    ? React.createElement("div", { style: { fontSize: "0.75rem", color: "var(--zfk-text-muted)" } }, "No comments yet.")
                    : selectedTask.comments.map((c) =>
                        React.createElement(
                          "div",
                          { key: c.id, className: "zfk-comment-item" },
                          React.createElement(
                            "div",
                            { className: "zfk-comment-top" },
                            React.createElement("span", { className: "zfk-comment-author" }, "@" + c.author),
                            React.createElement("span", { className: "zfk-comment-time" }, timeAgo(c.created_at))
                          ),
                          React.createElement("div", { className: "zfk-comment-body" }, c.body)
                        )
                      )
                ),
                React.createElement(
                  "form",
                  { onSubmit: handleAddCommentSubmit, style: { display: "flex", gap: "0.5rem", marginTop: "0.5rem" } },
                  React.createElement("input", {
                    className: "zfk-form-input",
                    placeholder: "Write a note or comment...",
                    value: newCommentText,
                    onChange: (e) => setNewCommentText(e.target.value)
                  }),
                  React.createElement("button", { type: "submit", className: "zfk-btn zfk-btn-secondary" }, "Post")
                )
              )
            ),

            React.createElement(
              "div",
              { className: "zfk-modal-footer" },
              React.createElement(
                "button",
                {
                  className: "zfk-btn zfk-btn-secondary",
                  style: { color: "#f87171", borderColor: "rgba(239, 68, 68, 0.3)" },
                  onClick: () => handleDeleteTask(selectedTask.id)
                },
                "Delete Task"
              ),
              React.createElement(
                "button",
                {
                  className: "zfk-btn zfk-btn-primary",
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
          { className: "zfk-modal-backdrop", onClick: () => setShowNewTaskModal(false) },
          React.createElement(
            "div",
            { className: "zfk-modal", onClick: (e) => e.stopPropagation() },
            React.createElement(
              "div",
              { className: "zfk-modal-header" },
              React.createElement("h2", { className: "zfk-modal-title" }, "Create New Zero Factory Task"),
              React.createElement("button", { className: "zfk-modal-close", onClick: () => setShowNewTaskModal(false) }, "✕")
            ),
            React.createElement(
              "form",
              { onSubmit: handleCreateTaskSubmit },
              React.createElement(
                "div",
                { className: "zfk-modal-body" },
                React.createElement(
                  "div",
                  { className: "zfk-form-group" },
                  React.createElement("label", { className: "zfk-form-label" }, "Task Title *"),
                  React.createElement("input", {
                    className: "zfk-form-input",
                    required: true,
                    placeholder: "e.g. Implement caching layer for Redis",
                    value: newTaskForm.title,
                    onChange: (e) => setNewTaskForm({ ...newTaskForm, title: e.target.value })
                  })
                ),
                React.createElement(
                  "div",
                  { className: "zfk-form-row" },
                  React.createElement(
                    "div",
                    { className: "zfk-form-group" },
                    React.createElement("label", { className: "zfk-form-label" }, "Assignee"),
                    React.createElement(
                      "select",
                      {
                        className: "zfk-form-select",
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
                    { className: "zfk-form-group" },
                    React.createElement("label", { className: "zfk-form-label" }, "Priority"),
                    React.createElement(
                      "select",
                      {
                        className: "zfk-form-select",
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
                  { className: "zfk-form-row" },
                  React.createElement(
                    "div",
                    { className: "zfk-form-group" },
                    React.createElement("label", { className: "zfk-form-label" }, "Initial Column"),
                    React.createElement(
                      "select",
                      {
                        className: "zfk-form-select",
                        value: newTaskForm.status,
                        onChange: (e) => setNewTaskForm({ ...newTaskForm, status: e.target.value })
                      },
                      COLUMNS.map((c) => React.createElement("option", { key: c.id, value: c.id }, c.title))
                    )
                  ),
                  React.createElement(
                    "div",
                    { className: "zfk-form-group" },
                    React.createElement("label", { className: "zfk-form-label" }, "Repository / Tenant"),
                    React.createElement("input", {
                      className: "zfk-form-input",
                      placeholder: "e.g. zerofactory or git repo path",
                      value: newTaskForm.tenant,
                      onChange: (e) => setNewTaskForm({ ...newTaskForm, tenant: e.target.value })
                    })
                  )
                ),
                React.createElement(
                  "div",
                  { className: "zfk-form-group" },
                  React.createElement("label", { className: "zfk-form-label" }, "Description & Acceptance Criteria"),
                  React.createElement("textarea", {
                    className: "zfk-form-textarea",
                    placeholder: "Provide context, requirements, edge cases, and steps for the agent...",
                    value: newTaskForm.description,
                    onChange: (e) => setNewTaskForm({ ...newTaskForm, description: e.target.value })
                  })
                )
              ),
              React.createElement(
                "div",
                { className: "zfk-modal-footer" },
                React.createElement(
                  "button",
                  { type: "button", className: "zfk-btn zfk-btn-secondary", onClick: () => setShowNewTaskModal(false) },
                  "Cancel"
                ),
                React.createElement("button", { type: "submit", className: "zfk-btn zfk-btn-primary" }, "Create Task")
              )
            )
          )
        ),

      // New Board Modal
      showNewBoardModal &&
        React.createElement(
          "div",
          { className: "zfk-modal-backdrop", onClick: () => setShowNewBoardModal(false) },
          React.createElement(
            "div",
            { className: "zfk-modal", onClick: (e) => e.stopPropagation() },
            React.createElement(
              "div",
              { className: "zfk-modal-header" },
              React.createElement("h2", { className: "zfk-modal-title" }, "Create New Project Board"),
              React.createElement("button", { className: "zfk-modal-close", onClick: () => setShowNewBoardModal(false) }, "✕")
            ),
            React.createElement(
              "form",
              { onSubmit: handleCreateBoardSubmit },
              React.createElement(
                "div",
                { className: "zfk-modal-body" },
                React.createElement(
                  "div",
                  { className: "zfk-form-group" },
                  React.createElement("label", { className: "zfk-form-label" }, "Board Name *"),
                  React.createElement("input", {
                    className: "zfk-form-input",
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
                  { className: "zfk-form-group" },
                  React.createElement("label", { className: "zfk-form-label" }, "Slug (URL identifier) *"),
                  React.createElement("input", {
                    className: "zfk-form-input",
                    required: true,
                    placeholder: "e.g. zerohub",
                    value: newBoardForm.slug,
                    onChange: (e) => setNewBoardForm({ ...newBoardForm, slug: e.target.value })
                  })
                ),
                React.createElement(
                  "div",
                  { className: "zfk-form-group" },
                  React.createElement("label", { className: "zfk-form-label" }, "Remote Git URL"),
                  React.createElement("input", {
                    className: "zfk-form-input",
                    placeholder: "https://github.com/org/repo.git",
                    value: newBoardForm.git_url,
                    onChange: (e) => setNewBoardForm({ ...newBoardForm, git_url: e.target.value })
                  })
                ),
                React.createElement(
                  "div",
                  { className: "zfk-form-group" },
                  React.createElement("label", { className: "zfk-form-label" }, "Description"),
                  React.createElement("input", {
                    className: "zfk-form-input",
                    placeholder: "Short description of this board's scope",
                    value: newBoardForm.description,
                    onChange: (e) => setNewBoardForm({ ...newBoardForm, description: e.target.value })
                  })
                )
              ),
              React.createElement(
                "div",
                { className: "zfk-modal-footer" },
                React.createElement(
                  "button",
                  { type: "button", className: "zfk-btn zfk-btn-secondary", onClick: () => setShowNewBoardModal(false) },
                  "Cancel"
                ),
                React.createElement("button", { type: "submit", className: "zfk-btn zfk-btn-primary" }, "Create Board")
              )
            )
          )
        )
    );
  }

  // Register in Hermes Plugins Registry
  window.__HERMES_PLUGINS__.register("zerofactory-kanban", ZeroFactoryKanbanApp);
})();
