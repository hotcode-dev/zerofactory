import React from "react";

export function NewTaskModal(props) {
  const {
    showNewTaskModal,
    setShowNewTaskModal,
    newTaskForm,
    setNewTaskForm,
    handleCreateTask,
    isSubmittingTask,
    boards,
    selectedBoard
  } = props;

  if (!showNewTaskModal) return null;

  return (
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
                  boards.length > 0 &&
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Target Board *"),
                    React.createElement(
                      "select",
                      {
                        className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors cursor-pointer",
                        value: newTaskForm.board_slug || (selectedBoard && selectedBoard !== "all" ? selectedBoard : (boards[0] ? boards[0].slug : "")),
                        onChange: (e) => setNewTaskForm({ ...newTaskForm, board_slug: e.target.value })
                      },
                      boards.map(b => React.createElement("option", { key: b.slug, value: b.slug }, b.slug))
                    )
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
                        React.createElement("option", { value: "human" }, "Human (Manual Action)"),
                        React.createElement("option", { value: "zf-builder" }, "ZF Builder"),
                        React.createElement("option", { value: "zf-reviewer" }, "ZF Reviewer"),
                        React.createElement("option", { value: "zf-orchestrator" }, "ZF Orchestrator")
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
                    React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Pull Request URL (Optional)"),
                    React.createElement("input", {
                      className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors font-mono",
                      placeholder: "e.g. https://github.com/owner/repo/pull/123",
                      value: newTaskForm.pr_url || "",
                      onChange: (e) => setNewTaskForm({ ...newTaskForm, pr_url: e.target.value })
                    })
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

          // Record Memory Modal
          showAddMemoryModal &&
          React.createElement(
            "div",
            {
              className: "fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4 overflow-y-auto",
              onClick: () => setShowAddMemoryModal(false)
            },
            React.createElement(
              "div",
              {
                className: "bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl max-w-lg w-full max-h-[90vh] flex flex-col overflow-hidden text-slate-100 animate-fade-in",
                onClick: (e) => e.stopPropagation()
              },
              React.createElement(
                "div",
                { className: "flex items-center justify-between px-6 py-4 border-b border-slate-800 shrink-0" },
                React.createElement(
                  "div",
                  null,
                  React.createElement("h2", { className: "text-base font-semibold text-white m-0" }, "🧠 Record Repository Memory"),
                  React.createElement("p", { className: "text-xs text-slate-400 font-normal m-0 mt-0.5" }, "Persist decisions, conventions, and gotchas for " + (selectedBoard === "all" ? "all boards" : (selectedBoard || "board")))
                ),
                React.createElement(
                  "button",
                  {
                    type: "button",
                    className: "text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors text-lg leading-none cursor-pointer w-8 h-8 flex items-center justify-center",
                    onClick: () => setShowAddMemoryModal(false)
                  },
                  "✕"
                )
              ),
              React.createElement(
                "form",
                { onSubmit: handleCreateMemorySubmit, className: "flex flex-col flex-1 overflow-hidden m-0" },
                React.createElement(
                  "div",
                  { className: "p-6 space-y-4 overflow-y-auto zfk-scrollbar flex-1" },
                  (selectedBoard === "all" || !selectedBoard) && boards.length > 0 &&
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement("label", { className: "block text-xs font-medium text-slate-300" }, "Target Board *"),
                    React.createElement(
                      "select",
                      {
                        className: "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer",
                        value: newMemoryForm.board_slug || (boards[0] ? boards[0].slug : ""),
                        onChange: (e) => setNewMemoryForm({ ...newMemoryForm, board_slug: e.target.value })
                      },
                      boards.map((b) => React.createElement("option", { key: b.slug, value: b.slug }, b.slug))
                    )
                  ),
                  // Category
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement("label", { className: "block text-xs font-medium text-slate-300" }, "Category"),
                    React.createElement(
                      "select",
                      {
                        className: "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer",
                        value: newMemoryForm.category,
                        onChange: (e) => setNewMemoryForm({ ...newMemoryForm, category: e.target.value })
                      },
                      React.createElement("option", { value: "convention" }, "📐 Convention (Architecture / Style / Code Rules)"),
                      React.createElement("option", { value: "gotcha" }, "⚠️ Gotcha (Pitfall / Bug to Avoid)"),
                      React.createElement("option", { value: "decision" }, "💡 Decision (Key Architectural Decision)"),
                      React.createElement("option", { value: "rejected_path" }, "🚫 Rejected Path (Alternative Tried & Discarded)"),
                      React.createElement("option", { value: "general" }, "📝 General Knowledge")
                    )
                  ),
                  // Content
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement("label", { className: "block text-xs font-medium text-slate-300" }, "Memory / Knowledge Content *"),
                    React.createElement("textarea", {
                      required: true,
                      rows: 4,
                      placeholder: "e.g. Always run 'python3 -m unittest test_plugin.py' before marking tasks done, as SQLite cascade triggers are verified there.",
                      className: "w-full bg-slate-800 border border-slate-700 rounded-lg p-3 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-none font-sans",
                      value: newMemoryForm.content,
                      onChange: (e) => setNewMemoryForm({ ...newMemoryForm, content: e.target.value })
                    })
                  ),
                  // Tags
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement("label", { className: "block text-xs font-medium text-slate-300" }, "Tags (comma-separated)"),
                    React.createElement("input", {
                      type: "text",
                      placeholder: "sqlite, tests, git, caching",
                      className: "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500",
                      value: newMemoryForm.tags,
                      onChange: (e) => setNewMemoryForm({ ...newMemoryForm, tags: e.target.value })
                    })
                  ),
                  // Author & Task ID
                  React.createElement(
                    "div",
                    { className: "grid grid-cols-2 gap-3" },
                    React.createElement(
                      "div",
                      { className: "space-y-1.5" },
                      React.createElement("label", { className: "block text-xs font-medium text-slate-300" }, "Author"),
                      React.createElement("input", {
                        type: "text",
                        placeholder: "user",
                        className: "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500",
                        value: newMemoryForm.author,
                        onChange: (e) => setNewMemoryForm({ ...newMemoryForm, author: e.target.value })
                      })
                    ),
                    React.createElement(
                      "div",
                      { className: "space-y-1.5" },
                      React.createElement("label", { className: "block text-xs font-medium text-slate-300" }, "Related Task ID (Optional)"),
                      React.createElement("input", {
                        type: "text",
                        placeholder: "zf-xxxxxxxx",
                        className: "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono",
                        value: newMemoryForm.task_id || "",
                        onChange: (e) => setNewMemoryForm({ ...newMemoryForm, task_id: e.target.value })
                      })
                    )
                  )
                ),
                React.createElement(
                  "div",
                  { className: "px-6 py-3.5 bg-slate-950/60 border-t border-slate-800 flex items-center justify-end gap-2.5 shrink-0" },
                  React.createElement(
                    "button",
                    {
                      type: "button",
                      className: "px-4 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors cursor-pointer",
                      onClick: () => setShowAddMemoryModal(false)
                    },
                    "Cancel"
                  ),
                  React.createElement(
                    "button",
                    {
                      type: "submit",
                      disabled: submittingMemory,
                      className: "inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-500 transition-colors cursor-pointer shadow-xs shadow-indigo-600/30 disabled:opacity-50"
                    },
                    submittingMemory && React.createElement("span", { className: "zfk-spinning" }, "⏳"),
                    "Save Memory"
                  )
                )
              )
            )
          )
  );
}
