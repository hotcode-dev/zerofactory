import React from "react";

export function NewBoardModal(props) {
  const {
    showNewBoardModal,
    setShowNewBoardModal,
    newBoardForm,
    setNewBoardForm,
    handleCreateBoard,
    isSubmittingBoard
  } = props;

  if (!showNewBoardModal) return null;

  return (
          React.createElement(
            "div",
            {
              className: "fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4 overflow-y-auto",
              onClick: () => {
                if (boards.length > 0) setShowNewBoardModal(false);
              }
            },
            React.createElement(
              "div",
              { className: "bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl max-w-xl w-full max-h-[90vh] flex flex-col overflow-hidden text-slate-100", onClick: (e) => e.stopPropagation() },
              React.createElement(
                "div",
                { className: "flex items-center justify-between px-6 py-4 border-b border-slate-800 shrink-0" },
                React.createElement(
                  "div",
                  null,
                  React.createElement("h2", { className: "text-base font-semibold text-white m-0" }, boards.length === 0 ? "Create First Project Board (Required)" : "Create New Project Board"),
                  boards.length === 0 &&
                  React.createElement("p", { className: "text-xs text-indigo-400 font-normal m-0 mt-0.5" }, "A project board is required to use Zero Factory Kanban")
                ),
                boards.length > 0 &&
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
                  boards.length === 0 &&
                  React.createElement(
                    "div",
                    { className: "p-3 rounded-lg bg-indigo-950/60 border border-indigo-500/30 text-xs text-indigo-200 leading-relaxed flex items-start gap-2.5" },
                    React.createElement("span", { className: "text-base leading-none shrink-0 mt-0.5" }, "ℹ️"),
                    React.createElement(
                      "div",
                      null,
                      React.createElement("p", { className: "font-semibold mb-0.5 text-white" }, "Initial Board Setup"),
                      React.createElement("p", { className: "text-indigo-200/90" }, "Please register a project board for your codebase to begin creating tickets, assigning autonomous agents, and orchestrating Git worktrees. You can also explore the ", React.createElement("button", { type: "button", className: "underline text-indigo-300 hover:text-white font-medium cursor-pointer", onClick: () => { setShowNewBoardModal(false); setActiveView("instructions"); } }, "Zero Factory Instructions"), ".")
                    )
                  ),
                  createBoardError &&
                  React.createElement(
                    "div",
                    { className: "p-3 rounded-lg bg-rose-950/90 border border-rose-500/60 text-xs text-rose-200 leading-relaxed flex items-start gap-2.5 shadow-sm" },
                    React.createElement("span", { className: "text-base leading-none shrink-0 mt-0.5" }, "⚠️"),
                    React.createElement(
                      "div",
                      null,
                      React.createElement("p", { className: "font-semibold mb-0.5 text-white" }, "Could Not Create Board"),
                      React.createElement("p", { className: "text-rose-200/90 m-0" }, createBoardError)
                    )
                  ),
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement(
                      "div",
                      { className: "flex items-center justify-between" },
                      React.createElement("label", { className: "block text-xs font-semibold text-slate-300 tracking-wide" }, "Remote Git URL *"),
                      React.createElement(
                        "button",
                        {
                          type: "button",
                          disabled: isTestingClone || !newBoardForm.git_url,
                          onClick: () => handleTestClone(newBoardForm.git_url, computeGitSlug(newBoardForm.git_url)),
                          className: "text-[11px] font-medium text-indigo-400 hover:text-indigo-300 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer flex items-center gap-1 transition-colors"
                        },
                        isTestingClone ? "Testing Clone..." : "🧪 Test Clone Git"
                      )
                    ),
                    React.createElement("input", {
                      className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors font-mono",
                      required: true,
                      autoFocus: true,
                      placeholder: "https://github.com/hotcode-dev/zerofactory.git or git@github.com:hotcode-dev/zerofactory.git",
                      value: newBoardForm.git_url || "",
                      onChange: (e) => {
                        setCreateBoardError("");
                        setCloneTestResult(null);
                        setNewBoardForm({ ...newBoardForm, git_url: e.target.value });
                      }
                    }),
                    cloneTestResult &&
                    React.createElement(
                      "div",
                      {
                        className: `text-[11px] px-2.5 py-1.5 rounded border flex items-start gap-1.5 ${
                          cloneTestResult.ok
                            ? "bg-emerald-950/40 border-emerald-800/60 text-emerald-300"
                            : "bg-rose-950/40 border-rose-800/60 text-rose-300"
                        }`
                      },
                      React.createElement("span", { className: "shrink-0 font-bold" }, cloneTestResult.ok ? "✓" : "✕"),
                      React.createElement("span", { className: "break-all" }, cloneTestResult.message)
                    ),
                    (() => {
                      const autoSlug = computeGitSlug(newBoardForm.git_url || "");
                      if (autoSlug) {
                        const exists = boards.some((b) => b.slug === autoSlug);
                        return React.createElement(
                          "div",
                          { className: "space-y-1 pt-1" },
                          React.createElement(
                            "div",
                            { className: "flex items-center gap-2 text-[11px] text-slate-400 font-mono" },
                            React.createElement("span", { className: "text-slate-500" }, "Board Slug:"),
                            React.createElement("span", { className: "px-1.5 py-0.5 rounded bg-slate-800 text-indigo-300 font-medium" }, autoSlug)
                          ),
                          exists &&
                          React.createElement(
                            "div",
                            { className: "text-[11px] text-amber-400 flex items-center gap-1.5 font-sans" },
                            React.createElement("span", null, "⚠️"),
                            "A board with slug '",
                            React.createElement("span", { className: "font-mono font-bold text-amber-300" }, autoSlug),
                            "' already exists."
                          )
                        );
                      }
                      return null;
                    })()
                  ),
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Description (Optional)"),
                    React.createElement("input", {
                      className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
                      placeholder: "Short description of this board's scope (optional)",
                      value: newBoardForm.description || "",
                      onChange: (e) => setNewBoardForm({ ...newBoardForm, description: e.target.value })
                    })
                  ),
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Target Branch / PR Base (Optional)"),
                    React.createElement("input", {
                      className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors font-mono",
                      placeholder: "main (default if empty)",
                      value: newBoardForm.target_branch || "",
                      onChange: (e) => setNewBoardForm({ ...newBoardForm, target_branch: e.target.value })
                    }),
                    React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "The branch agent will branch off from and create PRs to merge to.")
                  ),
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Additional Trusted Reviewers (Optional)"),
                    React.createElement("input", {
                      className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
                      placeholder: "alice, bob (GitHub usernames)",
                      value: newBoardForm.additional_reviewer_usernames || "",
                      onChange: (e) => setNewBoardForm({ ...newBoardForm, additional_reviewer_usernames: e.target.value })
                    }),
                    React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Comma-separated usernames trusted to submit automation-relevant PR feedback.")
                  ),
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Max Concurrent Running (Default: 1)"),
                    React.createElement("input", {
                      type: "number",
                      min: 1,
                      step: 1,
                      className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
                      placeholder: "Max tasks running in parallel on this board (minimum 1)",
                      value: newBoardForm.max_concurrent_running ?? 1,
                      onChange: (e) => setNewBoardForm({ ...newBoardForm, max_concurrent_running: e.target.value })
                    }),
                    React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Caps how many of this board's tasks the dispatcher can run at once. Other boards keep their own limits.")
                  ),
                  React.createElement(
                    "div",
                    { className: "pt-1 flex items-center justify-between" },
                    React.createElement(
                      "div",
                      null,
                      React.createElement("label", { className: "block text-xs font-semibold text-slate-300" }, "🧠 Auto-Record Memory"),
                      React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Capture gotchas & conventions automatically from reviewer feedback.")
                    ),
                    React.createElement("input", {
                      type: "checkbox",
                      className: "h-4 w-4 rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500 cursor-pointer",
                      checked: Boolean(newBoardForm.auto_record_memory !== false),
                      onChange: (e) => setNewBoardForm({ ...newBoardForm, auto_record_memory: e.target.checked })
                    })
                  ),
                  React.createElement(
                    "div",
                    { className: "pt-1 flex items-center justify-between" },
                    React.createElement(
                      "div",
                      null,
                      React.createElement("label", { className: "block text-xs font-semibold text-slate-300" }, "⚡ Auto-Setup Precommit"),
                      React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Generate .zerofactory/precommit.sh with automated test, build, and format verification.")
                    ),
                    React.createElement("input", {
                      type: "checkbox",
                      className: "h-4 w-4 rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500 cursor-pointer",
                      checked: Boolean(newBoardForm.auto_setup_precommit !== false),
                      onChange: (e) => setNewBoardForm({ ...newBoardForm, auto_setup_precommit: e.target.checked })
                    })
                  )
                ),
                React.createElement(
                  "div",
                  { className: "flex items-center justify-end gap-2.5 px-6 py-3.5 border-t border-slate-800 bg-slate-900/50 shrink-0" },
                  boards.length > 0 &&
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
                      disabled: isSubmittingBoard,
                      className: "px-4 py-1.5 rounded-lg text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-500 transition-colors cursor-pointer shadow-xs shadow-indigo-600/30 disabled:opacity-50 disabled:cursor-not-allowed"
                    },
                    isSubmittingBoard
                      ? "Creating..."
                      : (boards.length === 0 ? "Create & Get Started" : "Create Board")
                  )
                )
              )
            )
          )
  );
}
