import React from "react";
import { COLUMNS } from "../constants.js";
import { Modal } from "../components/Modal.jsx";

export function NewTaskModal(props) {
  const {
    showNewTaskModal,
    setShowNewTaskModal,
    newTaskForm,
    setNewTaskForm,
    handleCreateTaskSubmit,
    handleCreateTask,
    isSubmittingTask,
    boards,
    selectedBoard
  } = props;

  const onSubmitHandler = handleCreateTaskSubmit || handleCreateTask;

  const chosenBoardSlug = newTaskForm.board_slug || (selectedBoard && selectedBoard !== "all" ? selectedBoard : boards[0] ? boards[0].slug : "");
  const activeBoardObj = (boards || []).find((b) => b.slug === chosenBoardSlug);
  const boardRepos = (activeBoardObj && activeBoardObj.repositories) || [];
  const defaultRepo = boardRepos[0];
  const currentRepoAlias = newTaskForm.repo_alias || (defaultRepo ? defaultRepo.repo_alias : "");

  return React.createElement(
    Modal,
    {
      isOpen: showNewTaskModal,
      onClose: () => setShowNewTaskModal(false),
      title: "Create New Zero Factory Task",
      bodyClassName: "p-0 flex flex-col flex-1 overflow-hidden"
    },
    React.createElement(
      "form",
      { onSubmit: onSubmitHandler, className: "flex flex-col flex-1 overflow-hidden m-0" },
      React.createElement(
        "div",
        { className: "p-4 sm:p-6 space-y-4 overflow-y-auto zfk-scrollbar flex-1" },
          React.createElement(
            "div",
            { className: "space-y-1.5" },
            React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Task Title *"),
            React.createElement("input", {
              className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
              required: true,
              placeholder: "e.g. Implement caching layer for Redis",
              value: newTaskForm.title,
              onChange: (e) => setNewTaskForm({
                ...newTaskForm,
                title: e.target.value
              })
            })
          ),
          boards && boards.length > 0 &&
          React.createElement(
            "div",
            { className: "space-y-1.5" },
            React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Target Board *"),
            React.createElement(
              "select",
              {
                className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors cursor-pointer",
                value: chosenBoardSlug,
                onChange: (e) => {
                  const bSlug = e.target.value;
                  const bObj = (boards || []).find((x) => x.slug === bSlug);
                  const bRepos = (bObj && bObj.repositories) || [];
                  const dRepo = bRepos[0];
                  setNewTaskForm({
                    ...newTaskForm,
                    board_slug: bSlug,
                    repo_alias: dRepo ? dRepo.repo_alias : ""
                  });
                }
              },
              boards.map((b) => React.createElement("option", { key: b.slug, value: b.slug }, b.slug))
            )
          ),
          boardRepos.length > 0 &&
          React.createElement(
            "div",
            { className: "space-y-1.5" },
            React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Target Repository (Multi-Repo Architecture) *"),
            React.createElement(
              "select",
              {
                className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors cursor-pointer font-mono",
                value: currentRepoAlias,
                onChange: (e) => setNewTaskForm({
                  ...newTaskForm,
                  repo_alias: e.target.value
                })
              },
              boardRepos.map((r) =>
                React.createElement(
                  "option",
                  { key: r.repo_alias, value: r.repo_alias },
                  r.repo_alias + " (" + (r.target_branch || "main") + ")"
                )
              )
            ),
            React.createElement("p", { className: "text-[10px] text-slate-500 m-0 font-sans" }, "Repository checked out as writable worktree (task/<id> branch). Sibling repos are checked out side-by-side.")
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
                  onChange: (e) => setNewTaskForm({
                    ...newTaskForm,
                    assignee: e.target.value
                  })
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
                  onChange: (e) => setNewTaskForm({
                    ...newTaskForm,
                    priority: e.target.value
                  })
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
                  onChange: (e) => setNewTaskForm({
                    ...newTaskForm,
                    status: e.target.value
                  })
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
                onChange: (e) => setNewTaskForm({
                  ...newTaskForm,
                  tenant: e.target.value
                })
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
              onChange: (e) => setNewTaskForm({
                ...newTaskForm,
                pr_url: e.target.value
              })
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
              onChange: (e) => setNewTaskForm({
                ...newTaskForm,
                description: e.target.value
              })
            })
          )
        ),
        React.createElement(
          "div",
          { className: "flex items-center justify-end gap-2.5 px-4 sm:px-6 py-3 sm:py-3.5 border-t border-slate-800 bg-slate-900/50 shrink-0" },
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
              disabled: isSubmittingTask,
              className: "px-4 py-1.5 rounded-lg text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-500 transition-colors cursor-pointer shadow-xs shadow-indigo-600/30 disabled:opacity-50"
            },
            isSubmittingTask ? "Creating..." : "Create Task"
          )
        )
      )
  );
}
