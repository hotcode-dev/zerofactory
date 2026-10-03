import React from "react";

export function EditBoardModal(props) {
  const {
    showEditBoardModal,
    setShowEditBoardModal,
    editBoardForm,
    setEditBoardForm,
    handleUpdateBoard,
    handleUpdateBoardSubmit = handleUpdateBoard,
    handleDeleteBoard,
    isSubmittingBoard,
    selectedBoard,
    isTestingClone = false,
    handleTestClone = () => {},
    cloneTestResult = null,
    setCloneTestResult = () => {},
    precommitStatus = null,
    isSettingUpPrecommit = false,
    handleTriggerPrecommitSetup = () => {},
    openwikiStatus = null,
    isSettingUpOpenwiki = false,
    handleTriggerOpenwikiSetup = () => {},
    ghIssuesStatus = null,
    isSettingUpGhIssues = false,
    handleTriggerGhIssuesSetup = () => {}
  } = props;

  if (!showEditBoardModal) return null;

  return (
          React.createElement(
            "div",
            { className: "fixed inset-0 z-50 flex items-center justify-center bg-black/70 backdrop-blur-xs p-4 overflow-y-auto", onClick: () => setShowEditBoardModal(false) },
            React.createElement(
              "div",
              { className: "bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl max-w-xl w-full max-h-[90vh] flex flex-col overflow-hidden text-slate-100", onClick: (e) => e.stopPropagation() },
              React.createElement(
                "div",
                { className: "flex items-center justify-between px-6 py-4 border-b border-slate-800 shrink-0" },
                React.createElement("h2", { className: "text-base font-semibold text-white m-0" }, "Edit Board: " + editBoardForm.slug),
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
                    React.createElement(
                      "div",
                      { className: "flex items-center justify-between" },
                      React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Remote Git URL"),
                      React.createElement(
                        "button",
                        {
                          type: "button",
                          disabled: isTestingClone || !editBoardForm.git_url,
                          onClick: () => handleTestClone(editBoardForm.git_url, editBoardForm.slug),
                          className: "text-[11px] font-medium text-indigo-400 hover:text-indigo-300 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer flex items-center gap-1 transition-colors"
                        },
                        isTestingClone ? "Testing Clone..." : "🧪 Test Clone Git"
                      )
                    ),
                    React.createElement("input", {
                      className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
                      placeholder: "https://github.com/org/repo.git or git@github.com:org/repo.git",
                      value: editBoardForm.git_url,
                      onChange: (e) => {
                        setCloneTestResult(null);
                        setEditBoardForm({ ...editBoardForm, git_url: e.target.value });
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
                    )
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
                  ),
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Target Branch / PR Base (Optional)"),
                    React.createElement("input", {
                      className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors font-mono",
                      placeholder: "main (default if empty)",
                      value: editBoardForm.target_branch || "",
                      onChange: (e) => setEditBoardForm({ ...editBoardForm, target_branch: e.target.value })
                    }),
                    React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "The branch agent will branch off from and create PRs to merge to.")
                  ),
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Additional Trusted Reviewers"),
                    React.createElement("input", {
                      className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
                      placeholder: "alice, bob (GitHub usernames; optional)",
                      value: editBoardForm.additional_reviewer_usernames || "",
                      onChange: (e) => setEditBoardForm({ ...editBoardForm, additional_reviewer_usernames: e.target.value })
                    }),
                    React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Only repository owners, members, collaborators, and these usernames can route PR feedback.")
                  ),
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement(
                      "div",
                      { className: "flex items-center justify-between" },
                      React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Jira Cloud Link (Optional)"),
                      editBoardForm.jira_url &&
                      React.createElement(
                        "a",
                        {
                          href: editBoardForm.jira_url.startsWith("http") ? editBoardForm.jira_url : `https://${editBoardForm.jira_url}`,
                          target: "_blank",
                          rel: "noreferrer",
                          className: "text-[11px] font-medium text-sky-400 hover:text-sky-300 cursor-pointer flex items-center gap-1 transition-colors"
                        },
                        "↗ Open Jira Cloud"
                      )
                    ),
                    React.createElement("input", {
                      className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors font-mono",
                      placeholder: "https://your-domain.atlassian.net or project link",
                      value: editBoardForm.jira_url || "",
                      onChange: (e) => setEditBoardForm({ ...editBoardForm, jira_url: e.target.value })
                    }),
                    React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Link your Jira Cloud instance or project to this board for Jira issue references and triage.")
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
                      value: editBoardForm.max_concurrent_running ?? 1,
                      onChange: (e) => setEditBoardForm({ ...editBoardForm, max_concurrent_running: e.target.value })
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
                      checked: Boolean(editBoardForm.auto_record_memory !== false),
                      onChange: (e) => setEditBoardForm({ ...editBoardForm, auto_record_memory: e.target.checked })
                    })
                  ),
                  React.createElement(
                    "div",
                    { className: "pt-2 border-t border-slate-800/80 flex flex-col gap-2" },
                    React.createElement(
                      "div",
                      { className: "flex items-center justify-between" },
                      React.createElement(
                        "div",
                        null,
                        React.createElement("label", { className: "block text-xs font-semibold text-slate-300" }, "⚡ Repository Precommit"),
                        React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Deterministic test, build, and format check script (.zerofactory/precommit.sh).")
                      ),
                      React.createElement(
                        "span",
                        {
                          className: "px-2 py-0.5 rounded-full text-[10px] font-semibold " +
                            (precommitStatus && precommitStatus.has_precommit
                              ? "bg-emerald-950/80 text-emerald-300 border border-emerald-800/60"
                              : precommitStatus && precommitStatus.pending_task_id
                              ? "bg-sky-950/80 text-sky-300 border border-sky-800/60"
                              : "bg-amber-950/80 text-amber-300 border border-amber-800/60")
                        },
                        precommitStatus && precommitStatus.has_precommit
                          ? "Configured ✓"
                          : precommitStatus && precommitStatus.pending_task_id
                          ? "Setup in Progress ⏳"
                          : "Not Configured ⚠️"
                      )
                    ),
                    React.createElement(
                      "div",
                      { className: "flex items-center justify-between gap-2" },
                      React.createElement(
                        "span",
                        { className: "text-[11px] text-slate-400 font-mono truncate" },
                        precommitStatus && precommitStatus.precommit_path
                          ? precommitStatus.precommit_path
                          : ".zerofactory/precommit.sh"
                      ),
                      React.createElement(
                        "button",
                        {
                          type: "button",
                          disabled: isSettingUpPrecommit,
                          onClick: () => handleTriggerPrecommitSetup(editBoardForm.slug),
                          className: "px-2.5 py-1 rounded-md text-[11px] font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 transition-colors cursor-pointer disabled:opacity-50 shrink-0"
                        },
                        isSettingUpPrecommit
                          ? "Initiating..."
                          : (precommitStatus && precommitStatus.has_precommit
                              ? "🔄 Regenerate Precommit"
                              : "⚡ Setup Repo Precommit")
                      )
                    ),
                    React.createElement(
                      "div",
                      { className: "pt-2 border-t border-slate-800/80 flex flex-col gap-2" },
                      React.createElement(
                        "div",
                        { className: "flex items-center justify-between" },
                        React.createElement(
                          "div",
                          null,
                          React.createElement("label", { className: "block text-xs font-semibold text-slate-300" }, "📖 OpenWiki Agent Docs"),
                          React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Machine-readable repository architecture wiki for coding agents (openwiki/).")
                        ),
                        React.createElement(
                          "span",
                          {
                            className: "px-2 py-0.5 rounded-full text-[10px] font-semibold " +
                              (openwikiStatus && openwikiStatus.has_openwiki
                                ? "bg-emerald-950/80 text-emerald-300 border border-emerald-800/60"
                                : openwikiStatus && openwikiStatus.pending_task_id
                                ? "bg-sky-950/80 text-sky-300 border border-sky-800/60"
                                : "bg-amber-950/80 text-amber-300 border border-amber-800/60")
                          },
                          openwikiStatus && openwikiStatus.has_openwiki
                            ? "Generated ✓"
                            : openwikiStatus && openwikiStatus.pending_task_id
                            ? "Setup in Progress ⏳"
                            : "Not Generated ⚠️"
                        )
                      ),
                      React.createElement(
                        "div",
                        { className: "flex items-center justify-between gap-2" },
                        React.createElement(
                          "span",
                          { className: "text-[11px] text-slate-400 font-mono truncate" },
                          openwikiStatus && openwikiStatus.openwiki_path
                            ? openwikiStatus.openwiki_path
                            : "openwiki/"
                        ),
                        React.createElement(
                          "button",
                          {
                            type: "button",
                            disabled: isSettingUpOpenwiki,
                            onClick: () => handleTriggerOpenwikiSetup(editBoardForm.slug),
                            className: "px-2.5 py-1 rounded-md text-[11px] font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 transition-colors cursor-pointer disabled:opacity-50 shrink-0"
                          },
                          isSettingUpOpenwiki
                            ? "Initiating..."
                            : (openwikiStatus && openwikiStatus.has_openwiki
                                ? "🔄 Regenerate OpenWiki"
                                : "📖 Setup OpenWiki")
                        )
                      )
                    ),
                    React.createElement(
                      "div",
                      { className: "pt-2 border-t border-slate-800/80 flex flex-col gap-2" },
                      React.createElement(
                        "div",
                        { className: "flex items-center justify-between" },
                        React.createElement(
                          "div",
                          null,
                          React.createElement("label", { className: "block text-xs font-semibold text-slate-300" }, "🏷️ GitHub Issue Templates & Labels"),
                          React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Bug/Feature templates with 'zerofactory' AI triage labels (.github/ISSUE_TEMPLATE/).")
                        ),
                        React.createElement(
                          "span",
                          {
                            className: "px-2 py-0.5 rounded-full text-[10px] font-semibold " +
                              (ghIssuesStatus && ghIssuesStatus.has_gh_issues
                                ? "bg-emerald-950/80 text-emerald-300 border border-emerald-800/60"
                                : ghIssuesStatus && ghIssuesStatus.pending_task_id
                                ? "bg-purple-950/80 text-purple-300 border border-purple-800/60"
                                : "bg-amber-950/80 text-amber-300 border border-amber-800/60")
                          },
                          ghIssuesStatus && ghIssuesStatus.has_gh_issues
                            ? "Configured ✓"
                            : ghIssuesStatus && ghIssuesStatus.pending_task_id
                            ? "Setup in Progress ⏳"
                            : "Not Configured ⚠️"
                        )
                      ),
                      React.createElement(
                        "div",
                        { className: "flex items-center justify-between gap-2" },
                        React.createElement(
                          "span",
                          { className: "text-[11px] text-slate-400 font-mono truncate" },
                          ghIssuesStatus && ghIssuesStatus.gh_issues_path
                            ? ghIssuesStatus.gh_issues_path
                            : ".github/ISSUE_TEMPLATE/"
                        ),
                        React.createElement(
                          "button",
                          {
                            type: "button",
                            disabled: isSettingUpGhIssues,
                            onClick: () => handleTriggerGhIssuesSetup(editBoardForm.slug),
                            className: "px-2.5 py-1 rounded-md text-[11px] font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 transition-colors cursor-pointer disabled:opacity-50 shrink-0"
                          },
                          isSettingUpGhIssues
                            ? "Initiating..."
                            : (ghIssuesStatus && ghIssuesStatus.has_gh_issues
                                ? "🔄 Regenerate Templates"
                                : "🏷️ Setup GitHub Issues")
                        )
                      )
                    ),
                    React.createElement(
                      "div",
                      { className: "pt-2 border-t border-slate-800/80 flex flex-col gap-2" },
                      React.createElement(
                        "div",
                        { className: "flex items-center justify-between" },
                        React.createElement(
                          "div",
                          null,
                          React.createElement("label", { className: "block text-xs font-semibold text-slate-300" }, "🔷 Jira Cloud Integration"),
                          React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Link Atlassian Jira Cloud instance/project for deterministic issue import into triage.")
                        ),
                        React.createElement(
                          "span",
                          {
                            className: "px-2 py-0.5 rounded-full text-[10px] font-semibold " +
                              (editBoardForm.jira_url && editBoardForm.jira_url.trim()
                                ? "bg-emerald-950/80 text-emerald-300 border border-emerald-800/60"
                                : "bg-slate-800 text-slate-400 border border-slate-700/60")
                          },
                          editBoardForm.jira_url && editBoardForm.jira_url.trim()
                            ? "Linked ✓"
                            : "Optional ⚪"
                        )
                      ),
                      React.createElement(
                        "div",
                        { className: "flex items-center justify-between gap-2" },
                        React.createElement(
                          "span",
                          { className: "text-[11px] text-slate-400 font-mono truncate" },
                          editBoardForm.jira_url && editBoardForm.jira_url.trim()
                            ? editBoardForm.jira_url.trim()
                            : "No Jira link configured (optional)"
                        ),
                        editBoardForm.jira_url && editBoardForm.jira_url.trim() ? (
                          React.createElement(
                            "a",
                            {
                              href: editBoardForm.jira_url.startsWith("http") ? editBoardForm.jira_url : `https://${editBoardForm.jira_url}`,
                              target: "_blank",
                              rel: "noreferrer",
                              className: "px-2.5 py-1 rounded-md text-[11px] font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 transition-colors cursor-pointer shrink-0 inline-flex items-center gap-1"
                            },
                            "🔗 Open Jira"
                          )
                        ) : null
                      )
                    )
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
