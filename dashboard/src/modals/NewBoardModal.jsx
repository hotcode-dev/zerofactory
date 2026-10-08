import React from "react";
import { computeGitSlug } from "../utils/formatters.js";
import { Modal } from "../components/Modal.jsx";

export function NewBoardModal(props) {
  const {
    showNewBoardModal,
    setShowNewBoardModal,
    newBoardForm,
    setNewBoardForm,
    handleCreateBoard,
    handleCreateBoardSubmit = handleCreateBoard,
    isSubmittingBoard,
    boards = [],
    setActiveView = () => {},
    createBoardError = "",
    setCreateBoardError = () => {},
    isTestingClone = false,
    handleTestClone = () => {},
    cloneTestResult = null,
    setCloneTestResult = () => {}
  } = props;

  if (!showNewBoardModal) return null;

  // Ensure repositories list has at least one item
  const repos = (newBoardForm.repositories && newBoardForm.repositories.length > 0)
    ? newBoardForm.repositories
    : [
        {
          repo_alias: computeGitSlug(newBoardForm.git_url || "") || "main",
          git_url: newBoardForm.git_url || "",
          target_branch: newBoardForm.target_branch || "main",
          additional_reviewer_usernames: newBoardForm.additional_reviewer_usernames || ""
        }
      ];

  const updateRepo = (index, field, value) => {
    const updated = [...repos];
    const current = { ...updated[index], [field]: value };
    if (field === "git_url" && (!current.repo_alias || current.repo_alias === "main")) {
      const slug = computeGitSlug(value);
      if (slug) current.repo_alias = slug;
    }
    updated[index] = current;

    // Keep primary board fields in sync with first repo for backward safety
    const updates = { ...newBoardForm, repositories: updated };
    if (field === "git_url" && !newBoardForm.slug) {
      const autoSlug = computeGitSlug(value);
      if (autoSlug) updates.slug = autoSlug;
    }
    if (index === 0) {
      if (field === "git_url") updates.git_url = value;
      if (field === "target_branch") updates.target_branch = value;
      if (field === "additional_reviewer_usernames") updates.additional_reviewer_usernames = value;
    }
    setNewBoardForm(updates);
  };

  const addRepo = () => {
    const updated = [
      ...repos,
      {
        repo_alias: "",
        git_url: "",
        target_branch: "main",
        additional_reviewer_usernames: ""
      }
    ];
    setNewBoardForm({ ...newBoardForm, repositories: updated });
  };

  const removeRepo = (index) => {
    if (repos.length <= 1) return;
    const updated = repos.filter((_, idx) => idx !== index);
    const updates = { ...newBoardForm, repositories: updated };
    if (index === 0 && updated.length > 0) {
      updates.git_url = updated[0].git_url;
      updates.target_branch = updated[0].target_branch;
      updates.additional_reviewer_usernames = updated[0].additional_reviewer_usernames;
    }
    setNewBoardForm(updates);
  };

  const suggestedSlug = computeGitSlug(repos[0]?.git_url || newBoardForm.git_url || "") || (repos[0]?.repo_alias || "");
  const currentSlug = (newBoardForm.slug || "").trim();
  const effectiveSlug = currentSlug || suggestedSlug;

  return React.createElement(
    Modal,
    {
      isOpen: showNewBoardModal,
      onClose: boards.length > 0 ? () => setShowNewBoardModal(false) : undefined,
      title: boards.length === 0 ? "Create First Project Board (Required)" : "Create New Project Board",
      subtitle: boards.length === 0 ? "A project board is required to use Zero Factory Kanban" : undefined,
      bodyClassName: "p-0 flex flex-col flex-1 overflow-hidden"
    },
    React.createElement(
      "form",
      { onSubmit: handleCreateBoardSubmit, className: "flex flex-col flex-1 overflow-hidden m-0" },
      React.createElement(
        "div",
        { className: "p-4 sm:p-6 space-y-5 overflow-y-auto zfk-scrollbar flex-1" },
        boards.length === 0 &&
          React.createElement(
            "div",
            { className: "p-3 rounded-lg bg-indigo-950/60 border border-indigo-500/30 text-xs text-indigo-200 leading-relaxed flex items-start gap-2.5" },
            React.createElement("span", { className: "text-base leading-none shrink-0 mt-0.5" }, "ℹ️"),
            React.createElement(
              "div",
              null,
              React.createElement("p", { className: "font-semibold mb-0.5 text-white" }, "Initial Board Setup"),
              React.createElement(
                "p",
                { className: "text-indigo-200/90" },
                "Register a project workspace with one or more repositories to start orchestrating tickets, assigning autonomous agents, and managing side-by-side Git worktrees. You can also review the ",
                React.createElement(
                  "button",
                  {
                    type: "button",
                    className: "underline text-indigo-300 hover:text-white font-medium cursor-pointer",
                    onClick: () => {
                      setShowNewBoardModal(false);
                      setActiveView("instructions");
                    }
                  },
                  "Zero Factory Instructions"
                ),
                "."
              )
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

        // Section: Board Slug Identifier
        React.createElement(
          "div",
          { className: "space-y-1.5 p-3 rounded-lg bg-slate-900/60 border border-slate-800" },
          React.createElement(
            "div",
            { className: "flex items-center justify-between" },
            React.createElement(
              "label",
              { className: "block text-xs font-bold text-slate-200 tracking-wide uppercase" },
              "🏷️ Board Slug",
              React.createElement("span", { className: "text-rose-400 ml-1" }, "*")
            ),
            suggestedSlug && currentSlug !== suggestedSlug &&
              React.createElement(
                "button",
                {
                  type: "button",
                  onClick: () => setNewBoardForm({ ...newBoardForm, slug: suggestedSlug }),
                  className: "text-[11px] text-indigo-400 hover:text-indigo-300 transition-colors cursor-pointer"
                },
                "Use suggested: " + suggestedSlug
              )
          ),
          React.createElement("input", {
            className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors font-mono",
            placeholder: suggestedSlug || "e.g. checkout-platform, order-service",
            value: newBoardForm.slug || "",
            onChange: (e) => setNewBoardForm({
              ...newBoardForm,
              slug: e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, "-")
            })
          }),
          React.createElement(
            "div",
            { className: "flex items-center justify-between gap-2 text-[10px] text-slate-400" },
            React.createElement(
              "span",
              null,
              "Unique board identifier for CLI, URLs, and multi-repo task orchestration."
            ),
            effectiveSlug &&
              React.createElement(
                "span",
                { className: "font-mono text-slate-500 shrink-0" },
                "Slug: ",
                React.createElement("span", { className: "text-indigo-300 font-semibold" }, effectiveSlug)
              )
          ),
          effectiveSlug && boards.some((b) => b.slug === effectiveSlug) &&
            React.createElement(
              "div",
              { className: "p-2 rounded bg-amber-950/60 border border-amber-500/40 text-[11px] text-amber-300 flex items-center gap-1.5" },
              React.createElement("span", null, "⚠️"),
              "A board with slug '",
              React.createElement("span", { className: "font-mono font-bold text-amber-200" }, effectiveSlug),
              "' already exists."
            )
        ),

        // Section: Repositories
        React.createElement(
          "div",
          { className: "space-y-3" },
          React.createElement(
            "div",
            { className: "flex items-center justify-between" },
            React.createElement(
              "label",
              { className: "block text-xs font-bold text-slate-200 tracking-wide uppercase" },
              "📦 Project Repositories (" + repos.length + ")"
            ),
            React.createElement(
              "button",
              {
                type: "button",
                onClick: addRepo,
                className: "text-xs font-medium text-indigo-400 hover:text-indigo-300 transition-colors cursor-pointer flex items-center gap-1"
              },
              "+ Add Another Repo"
            )
          ),
          React.createElement(
            "p",
            { className: "text-[11px] text-slate-400 m-0" },
            "All repositories are equal peers with remote URLs, branches, reviewers, and precommit verification. Sibling repositories check out side-by-side in workspaces."
          ),

          React.createElement(
            "div",
            { className: "space-y-3 pt-1" },
            repos.map((repo, idx) =>
              React.createElement(
                "div",
                {
                  key: idx,
                  className: "p-3.5 rounded-lg bg-slate-900/80 border border-slate-800 space-y-3 relative group"
                },
                React.createElement(
                  "div",
                  { className: "flex items-center justify-between gap-2" },
                  React.createElement(
                    "div",
                    { className: "flex items-center gap-2" },
                    React.createElement(
                      "span",
                      { className: "font-semibold text-xs text-indigo-300 font-mono bg-slate-800 px-2 py-0.5 rounded" },
                      repo.repo_alias || "Repo #" + (idx + 1)
                    )
                  ),
                  repos.length > 1 &&
                    React.createElement(
                      "button",
                      {
                        type: "button",
                        onClick: () => removeRepo(idx),
                        className: "text-rose-400 hover:text-rose-300 text-xs font-medium px-2 py-0.5 rounded hover:bg-rose-950/40 transition-colors cursor-pointer"
                      },
                      "✕ Remove"
                    )
                ),

                React.createElement(
                  "div",
                  { className: "space-y-1.5" },
                  React.createElement(
                    "div",
                    { className: "flex items-center justify-between" },
                    React.createElement("label", { className: "block text-[11px] font-semibold text-slate-300" }, "Remote Git URL *"),
                    React.createElement(
                      "button",
                      {
                        type: "button",
                        disabled: isTestingClone || !repo.git_url,
                        onClick: () => handleTestClone(repo.git_url, repo.repo_alias || computeGitSlug(repo.git_url)),
                        className: "text-[11px] font-medium text-indigo-400 hover:text-indigo-300 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer flex items-center gap-1 transition-colors"
                      },
                      isTestingClone ? "Testing..." : "🧪 Test Clone"
                    )
                  ),
                  React.createElement("input", {
                    className: "w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 font-mono outline-none focus:border-indigo-500",
                    required: true,
                    placeholder: "git@github.com:org/repo.git or https://github.com/org/repo.git",
                    value: repo.git_url || "",
                    onChange: (e) => {
                      setCreateBoardError("");
                      setCloneTestResult(null);
                      updateRepo(idx, "git_url", e.target.value);
                    }
                  })
                ),

                React.createElement(
                  "div",
                  { className: "grid grid-cols-1 sm:grid-cols-3 gap-2.5" },
                  React.createElement(
                    "div",
                    { className: "space-y-1" },
                    React.createElement("label", { className: "block text-[10px] font-semibold text-slate-400" }, "Repo Alias *"),
                    React.createElement("input", {
                      className: "w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-xs text-slate-200 font-mono placeholder-slate-500 outline-none focus:border-indigo-500",
                      required: true,
                      placeholder: "e.g. core-api",
                      value: repo.repo_alias || "",
                      onChange: (e) => updateRepo(idx, "repo_alias", e.target.value)
                    })
                  ),
                  React.createElement(
                    "div",
                    { className: "space-y-1" },
                    React.createElement("label", { className: "block text-[10px] font-semibold text-slate-400" }, "Target Branch"),
                    React.createElement("input", {
                      className: "w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-xs text-slate-200 font-mono placeholder-slate-500 outline-none focus:border-indigo-500",
                      placeholder: "main",
                      value: repo.target_branch || "main",
                      onChange: (e) => updateRepo(idx, "target_branch", e.target.value)
                    })
                  ),
                  React.createElement(
                    "div",
                    { className: "space-y-1" },
                    React.createElement("label", { className: "block text-[10px] font-semibold text-slate-400" }, "Reviewers (Optional)"),
                    React.createElement("input", {
                      className: "w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500",
                      placeholder: "alice, bob",
                      value: typeof repo.additional_reviewer_usernames === "string" ? repo.additional_reviewer_usernames : (repo.additional_reviewer_usernames || []).join(", "),
                      onChange: (e) => updateRepo(idx, "additional_reviewer_usernames", e.target.value)
                    })
                  )
                )
              )
            )
          ),

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

        // Section: Architecture & Contracts
        React.createElement(
          "div",
          { className: "space-y-1.5 pt-2 border-t border-slate-800/80" },
          React.createElement("label", { className: "block text-xs font-semibold text-slate-300 tracking-wide" }, "🌐 System Architecture Notes (Optional)"),
          React.createElement("textarea", {
            className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors font-mono min-h-[90px] resize-y leading-relaxed",
            placeholder: "# System Architecture & Contracts\n- common-lib: Shared protobuf & business models\n- api-gateway: Reverse proxy routing to order-service\n- order-service: Core transaction handling",
            value: newBoardForm.architecture || "",
            onChange: (e) => setNewBoardForm({ ...newBoardForm, architecture: e.target.value })
          }),
          React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "High-level service contracts and boundaries injected into agent prompts.")
        ),

        // Section: Board Scope & Jira
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
          React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Jira Cloud Link (Optional)"),
          React.createElement("input", {
            className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors font-mono",
            placeholder: "https://your-domain.atlassian.net or project link",
            value: newBoardForm.jira_url || "",
            onChange: (e) => setNewBoardForm({ ...newBoardForm, jira_url: e.target.value })
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
            value: newBoardForm.max_concurrent_running ?? 1,
            onChange: (e) => setNewBoardForm({ ...newBoardForm, max_concurrent_running: e.target.value })
          }),
          React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Caps how many of this board's tasks the dispatcher can run at once.")
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
        { className: "flex items-center justify-end gap-2.5 px-4 sm:px-6 py-3 sm:py-3.5 border-t border-slate-800 bg-slate-900/50 shrink-0" },
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
  );
}
