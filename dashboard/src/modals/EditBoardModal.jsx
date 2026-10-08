import React from "react";
import { computeGitSlug } from "../utils/formatters.js";
import { Modal } from "../components/Modal.jsx";

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
    isTestingClone = false,
    handleTestClone = () => {},
    cloneTestResult = null,
    setCloneTestResult = () => {},
    precommitStatuses = {},
    precommitStatus = null,
    isSettingUpPrecommit = false,
    handleTriggerPrecommitSetup = () => {},
    openwikiStatuses = {},
    openwikiStatus = null,
    isSettingUpOpenwiki = false,
    handleTriggerOpenwikiSetup = () => {},
    ghIssuesStatuses = {},
    ghIssuesStatus = null,
    isSettingUpGhIssues = false,
    handleTriggerGhIssuesSetup = () => {},
    isSettingUpJira = false,
    handleTriggerJiraSetup = () => {},
    isTestingJira = false,
    handleTriggerJiraTest = () => {},
    handleAddBoardRepo = () => {},
    handleDeleteBoardRepo = () => {}
  } = props;

  const [newRepoAlias, setNewRepoAlias] = React.useState("");
  const [newRepoUrl, setNewRepoUrl] = React.useState("");
  const [newRepoBranch, setNewRepoBranch] = React.useState("main");
  const [newRepoReviewers, setNewRepoReviewers] = React.useState("");

  if (!showEditBoardModal) return null;

  const repos = editBoardForm.repositories || [];

  const updateRepoField = (idx, field, value) => {
    const updated = [...repos];
    updated[idx] = { ...updated[idx], [field]: value };
    const updates = { ...editBoardForm, repositories: updated };
    if (idx === 0) {
      if (field === "git_url") updates.git_url = value;
      if (field === "target_branch") updates.target_branch = value;
      if (field === "additional_reviewer_usernames") updates.additional_reviewer_usernames = value;
    }
    setEditBoardForm(updates);
  };

  const getRepoPrecommit = (alias) => {
    if (precommitStatuses && precommitStatuses[alias]) return precommitStatuses[alias];
    return precommitStatus;
  };

  const getRepoOpenwiki = (alias) => {
    if (openwikiStatuses && openwikiStatuses[alias]) return openwikiStatuses[alias];
    return openwikiStatus;
  };

  const getRepoGhIssues = (alias) => {
    if (ghIssuesStatuses && ghIssuesStatuses[alias]) return ghIssuesStatuses[alias];
    return ghIssuesStatus;
  };

  return React.createElement(
    Modal,
    {
      isOpen: showEditBoardModal,
      onClose: () => setShowEditBoardModal(false),
      title: "Edit Project Board: " + editBoardForm.slug,
      bodyClassName: "p-0 flex flex-col flex-1 overflow-hidden"
    },
    React.createElement(
      "form",
      { onSubmit: handleUpdateBoardSubmit, className: "flex flex-col flex-1 overflow-hidden m-0" },
      React.createElement(
        "div",
        { className: "p-4 sm:p-6 space-y-5 overflow-y-auto zfk-scrollbar flex-1" },
        // Board Slug Identifier
        React.createElement(
          "div",
          { className: "space-y-1.5" },
          React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Board Slug (Identifier)"),
          React.createElement("input", {
            className: "w-full bg-slate-950/60 border border-slate-800/60 rounded-lg px-3 py-2 text-xs text-slate-400 cursor-not-allowed opacity-60 outline-none font-mono",
            disabled: true,
            value: editBoardForm.slug
          })
        ),

        // Repositories Section
        React.createElement(
          "div",
          { className: "space-y-3" },
          React.createElement(
            "div",
            { className: "flex items-center justify-between" },
            React.createElement(
              "label",
              { className: "block text-xs font-bold text-slate-200 tracking-wide uppercase" },
              "📦 Linked Repositories (" + repos.length + ")"
            ),
            React.createElement(
              "span",
              { className: "text-[11px] text-slate-500" },
              "Equal first-class configuration & automations"
            )
          ),

          React.createElement(
            "div",
            { className: "space-y-3.5" },
            repos.map((r, idx) => {
              const pStatus = getRepoPrecommit(r.repo_alias);
              const wStatus = getRepoOpenwiki(r.repo_alias);
              const gStatus = getRepoGhIssues(r.repo_alias);

              const reviewersDisplay = Array.isArray(r.additional_reviewer_usernames)
                ? r.additional_reviewer_usernames.join(", ")
                : (r.additional_reviewer_usernames || "");

              return React.createElement(
                "div",
                {
                  key: r.repo_alias || idx,
                  className: "p-4 rounded-lg bg-slate-900/90 border border-slate-800 space-y-3.5"
                },
                // Card Header
                React.createElement(
                  "div",
                  { className: "flex items-center justify-between gap-2 border-b border-slate-800/80 pb-2.5" },
                  React.createElement(
                    "div",
                    { className: "flex items-center gap-2" },
                    React.createElement(
                      "span",
                      { className: "font-mono font-bold text-sm text-indigo-300 bg-slate-800 px-2 py-0.5 rounded" },
                      r.repo_alias
                    ),
                    React.createElement(
                      "span",
                      { className: "text-[11px] text-slate-400 bg-slate-800/80 px-2 py-0.5 rounded font-mono" },
                      "branch: " + (r.target_branch || "main")
                    )
                  ),
                  repos.length > 1 &&
                    React.createElement(
                      "button",
                      {
                        type: "button",
                        className: "px-2 py-0.5 rounded text-xs font-medium text-rose-300 bg-rose-950/60 hover:bg-rose-900/60 border border-rose-800/60 transition-colors cursor-pointer",
                        onClick: () => {
                          if (window.confirm("Remove repository '" + r.repo_alias + "' from this board?")) {
                            handleDeleteBoardRepo(editBoardForm.slug, r.repo_alias);
                          }
                        },
                        title: "Remove repository from board"
                      },
                      "✕ Remove Repo"
                    )
                ),

                // Git URL input
                React.createElement(
                  "div",
                  { className: "space-y-1" },
                  React.createElement(
                    "div",
                    { className: "flex items-center justify-between" },
                    React.createElement("label", { className: "block text-[11px] font-semibold text-slate-300" }, "Remote Git URL"),
                    React.createElement(
                      "button",
                      {
                        type: "button",
                        disabled: isTestingClone || !r.git_url,
                        onClick: () => handleTestClone(r.git_url, r.repo_alias),
                        className: "text-[11px] font-medium text-indigo-400 hover:text-indigo-300 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer flex items-center gap-1 transition-colors"
                      },
                      isTestingClone ? "Testing..." : "🧪 Test Clone"
                    )
                  ),
                  React.createElement("input", {
                    className: "w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 font-mono outline-none focus:border-indigo-500",
                    value: r.git_url || "",
                    onChange: (e) => updateRepoField(idx, "git_url", e.target.value)
                  })
                ),

                // Target Branch & Additional Reviewers
                React.createElement(
                  "div",
                  { className: "grid grid-cols-1 sm:grid-cols-2 gap-3" },
                  React.createElement(
                    "div",
                    { className: "space-y-1" },
                    React.createElement("label", { className: "block text-[11px] font-semibold text-slate-400" }, "Target Branch / PR Base"),
                    React.createElement("input", {
                      className: "w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-xs text-slate-200 font-mono placeholder-slate-500 outline-none focus:border-indigo-500",
                      value: r.target_branch || "main",
                      onChange: (e) => updateRepoField(idx, "target_branch", e.target.value)
                    })
                  ),
                  React.createElement(
                    "div",
                    { className: "space-y-1" },
                    React.createElement("label", { className: "block text-[11px] font-semibold text-slate-400" }, "Additional Trusted Reviewers"),
                    React.createElement("input", {
                      className: "w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500",
                      placeholder: "alice, bob (GitHub usernames)",
                      value: reviewersDisplay,
                      onChange: (e) => updateRepoField(idx, "additional_reviewer_usernames", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))
                    })
                  )
                ),

                // Automations Panel (Precommit, OpenWiki, GitHub Issues)
                React.createElement(
                  "div",
                  { className: "p-3 rounded-lg bg-slate-950/70 border border-slate-800/80 space-y-2.5" },
                  React.createElement(
                    "span",
                    { className: "block text-[10px] font-bold text-slate-400 uppercase tracking-wider" },
                    "🛠️ Repository Automations & Verification"
                  ),

                  // Precommit
                  React.createElement(
                    "div",
                    { className: "flex items-center justify-between gap-2 text-xs" },
                    React.createElement(
                      "div",
                      { className: "min-w-0 flex items-center gap-2" },
                      React.createElement("span", { className: "font-medium text-slate-300 text-xs shrink-0" }, "⚡ Precommit:"),
                      React.createElement(
                        "span",
                        {
                          className:
                            "px-2 py-0.5 rounded text-[10px] font-semibold " +
                            (pStatus && pStatus.has_precommit
                              ? "bg-emerald-950/80 text-emerald-300 border border-emerald-800/60"
                              : pStatus && pStatus.pending_task_id
                              ? "bg-sky-950/80 text-sky-300 border border-sky-800/60"
                              : "bg-amber-950/80 text-amber-300 border border-amber-800/60")
                        },
                        pStatus && pStatus.has_precommit
                          ? "Configured ✓"
                          : pStatus && pStatus.pending_task_id
                          ? "Setup in Progress ⏳"
                          : "Not Configured ⚠️"
                      )
                    ),
                    React.createElement(
                      "button",
                      {
                        type: "button",
                        disabled: isSettingUpPrecommit,
                        onClick: () => handleTriggerPrecommitSetup(editBoardForm.slug, r.repo_alias),
                        className: "px-2.5 py-1 rounded text-[11px] font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 transition-colors cursor-pointer disabled:opacity-50 shrink-0"
                      },
                      isSettingUpPrecommit
                        ? "Initiating..."
                        : (pStatus && pStatus.has_precommit ? "🔄 Regenerate" : "⚡ Setup Precommit")
                    )
                  ),

                  // OpenWiki
                  React.createElement(
                    "div",
                    { className: "flex items-center justify-between gap-2 text-xs" },
                    React.createElement(
                      "div",
                      { className: "min-w-0 flex items-center gap-2" },
                      React.createElement("span", { className: "font-medium text-slate-300 text-xs shrink-0" }, "📖 OpenWiki:"),
                      React.createElement(
                        "span",
                        {
                          className:
                            "px-2 py-0.5 rounded text-[10px] font-semibold " +
                            (wStatus && wStatus.has_openwiki
                              ? "bg-emerald-950/80 text-emerald-300 border border-emerald-800/60"
                              : wStatus && wStatus.pending_task_id
                              ? "bg-sky-950/80 text-sky-300 border border-sky-800/60"
                              : "bg-amber-950/80 text-amber-300 border border-amber-800/60")
                        },
                        wStatus && wStatus.has_openwiki
                          ? "Generated ✓"
                          : wStatus && wStatus.pending_task_id
                          ? "Setup in Progress ⏳"
                          : "Not Generated ⚠️"
                      )
                    ),
                    React.createElement(
                      "button",
                      {
                        type: "button",
                        disabled: isSettingUpOpenwiki,
                        onClick: () => handleTriggerOpenwikiSetup(editBoardForm.slug, r.repo_alias),
                        className: "px-2.5 py-1 rounded text-[11px] font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 transition-colors cursor-pointer disabled:opacity-50 shrink-0"
                      },
                      isSettingUpOpenwiki
                        ? "Initiating..."
                        : (wStatus && wStatus.has_openwiki ? "🔄 Regenerate" : "📖 Setup OpenWiki")
                    )
                  ),

                  // GitHub Issues
                  React.createElement(
                    "div",
                    { className: "flex items-center justify-between gap-2 text-xs" },
                    React.createElement(
                      "div",
                      { className: "min-w-0 flex items-center gap-2" },
                      React.createElement("span", { className: "font-medium text-slate-300 text-xs shrink-0" }, "🏷️ Issue Templates:"),
                      React.createElement(
                        "span",
                        {
                          className:
                            "px-2 py-0.5 rounded text-[10px] font-semibold " +
                            (gStatus && gStatus.has_gh_issues
                              ? "bg-emerald-950/80 text-emerald-300 border border-emerald-800/60"
                              : gStatus && gStatus.pending_task_id
                              ? "bg-purple-950/80 text-purple-300 border border-purple-800/60"
                              : "bg-amber-950/80 text-amber-300 border border-amber-800/60")
                        },
                        gStatus && gStatus.has_gh_issues
                          ? "Configured ✓"
                          : gStatus && gStatus.pending_task_id
                          ? "Setup in Progress ⏳"
                          : "Not Configured ⚠️"
                      )
                    ),
                    React.createElement(
                      "button",
                      {
                        type: "button",
                        disabled: isSettingUpGhIssues,
                        onClick: () => handleTriggerGhIssuesSetup(editBoardForm.slug, r.repo_alias),
                        className: "px-2.5 py-1 rounded text-[11px] font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 transition-colors cursor-pointer disabled:opacity-50 shrink-0"
                      },
                      isSettingUpGhIssues
                        ? "Initiating..."
                        : (gStatus && gStatus.has_gh_issues ? "🔄 Regenerate" : "🏷️ Setup Issues")
                    )
                  )
                )
              );
            })
          ),

          // Add New Repository Card
          React.createElement(
            "div",
            { className: "p-3.5 rounded-lg bg-slate-950/70 border border-slate-800/90 space-y-3" },
            React.createElement(
              "label",
              { className: "block text-xs font-semibold text-slate-300" },
              "+ Add Repository to Board"
            ),
            React.createElement(
              "div",
              { className: "grid grid-cols-1 sm:grid-cols-4 gap-2" },
              React.createElement("input", {
                className: "bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 font-mono outline-none focus:border-indigo-500",
                placeholder: "Alias (e.g. auth-svc)",
                value: newRepoAlias,
                onChange: (e) => setNewRepoAlias(e.target.value)
              }),
              React.createElement("input", {
                className: "bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 font-mono outline-none focus:border-indigo-500 sm:col-span-2",
                placeholder: "Git URL (remote or local path)",
                value: newRepoUrl,
                onChange: (e) => {
                  setNewRepoUrl(e.target.value);
                  if (!newRepoAlias && e.target.value) {
                    const slug = computeGitSlug(e.target.value);
                    if (slug) setNewRepoAlias(slug);
                  }
                }
              }),
              React.createElement("input", {
                className: "bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 font-mono outline-none focus:border-indigo-500",
                placeholder: "Branch (main)",
                value: newRepoBranch,
                onChange: (e) => setNewRepoBranch(e.target.value)
              })
            ),
            React.createElement(
              "div",
              { className: "flex items-center justify-between gap-2" },
              React.createElement("input", {
                className: "bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 flex-1",
                placeholder: "Additional Reviewers (e.g. alice, bob; optional)",
                value: newRepoReviewers,
                onChange: (e) => setNewRepoReviewers(e.target.value)
              }),
              React.createElement(
                "button",
                {
                  type: "button",
                  disabled: !newRepoUrl || !newRepoAlias,
                  className: "px-3 py-1.5 rounded-md text-xs font-medium text-indigo-300 bg-indigo-950/70 hover:bg-indigo-900 border border-indigo-500/40 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed shrink-0",
                  onClick: async () => {
                    if (!newRepoUrl || !newRepoAlias) return;
                    await handleAddBoardRepo(editBoardForm.slug, {
                      repo_alias: newRepoAlias.trim(),
                      git_url: newRepoUrl.trim(),
                      target_branch: newRepoBranch.trim() || "main",
                      additional_reviewer_usernames: newRepoReviewers.split(",").map((x) => x.trim()).filter(Boolean)
                    });
                    setNewRepoAlias("");
                    setNewRepoUrl("");
                    setNewRepoBranch("main");
                    setNewRepoReviewers("");
                  }
                },
                "+ Add Repository"
              )
            )
          )
        ),

        // Architecture Notes
        React.createElement(
          "div",
          { className: "space-y-1.5 pt-2 border-t border-slate-800/80" },
          React.createElement("label", { className: "block text-xs font-semibold text-slate-300 tracking-wide" }, "🌐 System Architecture Notes (architecture)"),
          React.createElement("textarea", {
            className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors font-mono min-h-[90px] resize-y leading-relaxed",
            placeholder: "# System Architecture & Contracts\n- common-lib: Shared protobuf & business models\n- api-gateway: Reverse proxy routing to order-service\n- order-service: Core transaction handling",
            value: editBoardForm.architecture || "",
            onChange: (e) => setEditBoardForm({ ...editBoardForm, architecture: e.target.value })
          }),
          React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "High-level architecture contracts and service topology injected into agent prompts.")
        ),

        // Description
        React.createElement(
          "div",
          { className: "space-y-1.5" },
          React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Description"),
          React.createElement("input", {
            className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
            placeholder: "Short description of this board's scope",
            value: editBoardForm.description || "",
            onChange: (e) => setEditBoardForm({ ...editBoardForm, description: e.target.value })
          })
        ),

        // Jira Cloud Integration
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

        // Max Concurrent Running
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
          React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Caps how many of this board's tasks the dispatcher can run at once.")
        ),

        // Auto-Record Memory
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
        )
      ),

      // Footer
      React.createElement(
        "div",
        { className: "flex items-center justify-end gap-2.5 px-4 sm:px-6 py-3 sm:py-3.5 border-t border-slate-800 bg-slate-900/50 shrink-0" },
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
  );
}
