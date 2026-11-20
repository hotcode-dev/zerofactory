import React from "react";

export function SetupBanners(props) {
  const {
    selectedBoard,
    setupStatus,
    isTogglingDispatcher,
    handleStartDispatcher,
    isSyncingProfiles,
    handleSyncProfiles,
    precommitStatus,
    openwikiStatus,
    ghIssuesStatus,
    isSettingUpPrecommit,
    handleTriggerPrecommitSetup,
    isSettingUpOpenwiki,
    handleTriggerOpenwikiSetup,
    isSettingUpGhIssues,
    handleTriggerGhIssuesSetup
  } = props;

  const outdatedProfiles =
    setupStatus && setupStatus.profiles_ready && Array.isArray(setupStatus.outdated_profiles)
      ? setupStatus.outdated_profiles
      : [];

  const missingSetupSteps = [];
  if (setupStatus && !setupStatus.profiles_ready) {
    missingSetupSteps.push({
      id: "profiles",
      label: "Initialize Zero Factory profiles",
      cmd: "hermes zerofactory setup"
    });
  }
  if (setupStatus && !setupStatus.gh_authenticated) {
    missingSetupSteps.push({
      id: "gh",
      label: "Authenticate GitHub CLI",
      cmd: "gh auth login"
    });
  }
  if (setupStatus && !setupStatus.dispatcher_running) {
    missingSetupSteps.push({
      id: "dispatcher",
      label: "Start the dispatcher",
      cmd: "hermes zerofactory start"
    });
  }

  return React.createElement(
    React.Fragment,
    null,
                    missingSetupSteps.length > 0 &&
                    React.createElement(
                      "div",
                      {
                        className: "mb-3.5 px-4 py-3 rounded-xl border border-indigo-500/30 bg-indigo-950/25 backdrop-blur-md text-xs"
                      },
                      React.createElement(
                        "div",
                        { className: "font-semibold text-slate-100 mb-1" },
                        "Zero Factory Setup Checklist"
                      ),
                      React.createElement(
                        "div",
                        { className: "text-slate-400 text-[11px] mb-2" },
                        "Run the following CLI commands to complete setup:"
                      ),
                      React.createElement(
                        "div",
                        { className: "flex flex-col gap-1.5" },
                        missingSetupSteps.map((step) =>
                          React.createElement(
                            "div",
                            {
                              key: step.cmd,
                              className: "flex flex-wrap items-center justify-between gap-2 bg-slate-900/60 px-2.5 py-1.5 rounded-lg border border-slate-800/80"
                            },
                            React.createElement("span", { className: "text-slate-300" }, step.label),
                            React.createElement(
                              "div",
                              { className: "flex items-center gap-2" },
                              React.createElement(
                                "code",
                                { className: "font-mono text-[11px] text-indigo-300 select-all" },
                                step.cmd
                              ),
                              step.id === "dispatcher" && handleStartDispatcher &&
                              React.createElement(
                                "button",
                                {
                                  type: "button",
                                  onClick: handleStartDispatcher,
                                  disabled: Boolean(isTogglingDispatcher) || !setupStatus.profiles_ready,
                                  title: !setupStatus.profiles_ready
                                    ? "Run 'hermes zerofactory setup' first to initialize profiles"
                                    : "Start the background dispatcher loop in this dashboard server",
                                  className: "px-2.5 py-1 rounded-md text-[11px] font-semibold bg-emerald-600 hover:bg-emerald-500 text-white transition-colors cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed"
                                },
                                isTogglingDispatcher ? "Starting..." : "▶ Start Dispatcher"
                              )
                            )
                          )
                        )
                      )
                    ),
                    outdatedProfiles.length > 0 &&
                    React.createElement(
                      "div",
                      {
                        className: "mb-3.5 px-4 py-2.5 rounded-xl border border-amber-500/35 bg-amber-950/25 backdrop-blur-md flex flex-wrap items-center justify-between gap-3 text-xs"
                      },
                      React.createElement(
                        "div",
                        { className: "flex items-center gap-2.5 text-amber-200" },
                        React.createElement("span", { className: "text-base" }, "⚠️"),
                        React.createElement(
                          "div",
                          null,
                          React.createElement(
                            "div",
                            { className: "font-semibold text-slate-100 flex flex-wrap items-center gap-1.5" },
                            "Agent Profiles Out of Sync",
                            React.createElement(
                              "span",
                              { className: "px-1.5 py-0.5 rounded-full text-[10px] font-mono bg-amber-950/80 text-amber-300 border border-amber-700/60" },
                              outdatedProfiles.join(", ")
                            )
                          ),
                          React.createElement(
                            "div",
                            { className: "text-slate-400 text-[11px]" },
                            "Installed SOUL.md prompts in ~/.hermes/profiles/ differ from the latest plugin templates. Sync to apply updated rules (preserves config.yaml and .env)."
                          )
                        )
                      ),
                      React.createElement(
                        "div",
                        { className: "flex items-center gap-2" },
                        React.createElement(
                          "code",
                          { className: "hidden sm:inline font-mono text-[11px] text-amber-300/90 bg-slate-950/70 px-2 py-1 rounded border border-slate-800 select-all" },
                          "hermes zerofactory sync-profiles"
                        ),
                        handleSyncProfiles &&
                        React.createElement(
                          "button",
                          {
                            type: "button",
                            disabled: Boolean(isSyncingProfiles),
                            onClick: handleSyncProfiles,
                            className: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-semibold text-xs bg-amber-600 hover:bg-amber-500 text-white shadow-sm transition-all duration-150 cursor-pointer disabled:opacity-50"
                          },
                          isSyncingProfiles ? "⏳ Syncing..." : "🔄 Sync Profiles"
                        )
                      )
                    ),
                    Boolean(selectedBoard && selectedBoard !== "all" && precommitStatus && !precommitStatus.has_precommit) &&
                    React.createElement(
                      "div",
                      {
                        className: "mb-3.5 px-4 py-2.5 rounded-xl border border-amber-500/30 bg-amber-950/20 backdrop-blur-md flex flex-wrap items-center justify-between gap-3 text-xs"
                      },
                      React.createElement(
                        "div",
                        { className: "flex items-center gap-2.5 text-amber-200" },
                        React.createElement("span", { className: "text-base" }, precommitStatus.pending_task_id ? "⚡" : "⚠️"),
                        React.createElement(
                          "div",
                          null,
                          React.createElement(
                            "div",
                            { className: "font-semibold text-slate-100" },
                            precommitStatus.pending_task_id
                              ? "Precommit Setup Task in Progress"
                              : "Precommit Verification Not Configured"
                          ),
                          React.createElement(
                            "div",
                            { className: "text-slate-400 text-[11px]" },
                            precommitStatus.pending_task_id
                              ? ("Task " + precommitStatus.pending_task_id + " (" + precommitStatus.pending_task_status + ") is generating .zerofactory/precommit.sh")
                              : "This board lacks .zerofactory/precommit.sh. Set up standard automated test, build, and format verification for commits."
                          )
                        )
                      ),
                      !precommitStatus.pending_task_id &&
                      React.createElement(
                        "button",
                        {
                          type: "button",
                          className: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-semibold text-xs bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm transition-all duration-150 cursor-pointer disabled:opacity-50",
                          disabled: isSettingUpPrecommit,
                          onClick: () => handleTriggerPrecommitSetup(selectedBoard)
                        },
                        isSettingUpPrecommit ? "Initiating Setup..." : "⚡ Setup Repo for Zero Factory"
                      )
                    ),

                    // Smart OpenWiki Recommendation Banner
                    Boolean(selectedBoard && selectedBoard !== "all" && openwikiStatus && !openwikiStatus.has_openwiki) &&
                    React.createElement(
                      "div",
                      {
                        className: "mb-3.5 px-4 py-2.5 rounded-xl border border-sky-500/30 bg-sky-950/20 backdrop-blur-md flex flex-wrap items-center justify-between gap-3 text-xs"
                      },
                      React.createElement(
                        "div",
                        { className: "flex items-center gap-2.5 text-sky-200" },
                        React.createElement("span", { className: "text-base" }, openwikiStatus.pending_task_id ? "⏳" : "📖"),
                        React.createElement(
                          "div",
                          null,
                          React.createElement(
                            "div",
                            { className: "font-semibold text-slate-100 flex items-center gap-1.5" },
                            openwikiStatus.pending_task_id
                              ? "OpenWiki Setup Task in Progress"
                              : "Recommended: OpenWiki Architecture Docs Not Generated",
                            React.createElement(
                              "span",
                              { className: "px-1.5 py-0.5 rounded-full text-[9px] font-bold bg-sky-950/80 text-sky-300 border border-sky-800/60" },
                              "Context Optimization"
                            )
                          ),
                          React.createElement(
                            "div",
                            { className: "text-slate-400 text-[11px]" },
                            openwikiStatus.pending_task_id
                              ? ("Task " + openwikiStatus.pending_task_id + " (" + openwikiStatus.pending_task_status + ") is generating openwiki/ documentation.")
                              : "Generate a machine-readable architecture wiki (openwiki/) to cut exploratory agent tool calls and token bloat by 30–40%."
                          )
                        )
                      ),
                      !openwikiStatus.pending_task_id &&
                      React.createElement(
                        "button",
                        {
                          type: "button",
                          className: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-semibold text-xs bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm transition-all duration-150 cursor-pointer disabled:opacity-50",
                          disabled: isSettingUpOpenwiki,
                          onClick: () => handleTriggerOpenwikiSetup(selectedBoard)
                        },
                        isSettingUpOpenwiki ? "Initiating Setup..." : "📖 Setup OpenWiki"
                      )
                    ),

                    // Smart GitHub Issues & AI Triage Labels Recommendation Banner
                    Boolean(selectedBoard && selectedBoard !== "all" && ghIssuesStatus && !ghIssuesStatus.has_gh_issues) &&
                    React.createElement(
                      "div",
                      {
                        className: "mb-3.5 px-4 py-2.5 rounded-xl border border-purple-500/30 bg-purple-950/20 backdrop-blur-md flex flex-wrap items-center justify-between gap-3 text-xs"
                      },
                      React.createElement(
                        "div",
                        { className: "flex items-center gap-2.5 text-purple-200" },
                        React.createElement("span", { className: "text-base" }, ghIssuesStatus.pending_task_id ? "⏳" : "🏷️"),
                        React.createElement(
                          "div",
                          null,
                          React.createElement(
                            "div",
                            { className: "font-semibold text-slate-100 flex items-center gap-1.5" },
                            ghIssuesStatus.pending_task_id
                              ? "GitHub Issues Setup Task in Progress"
                              : "Recommended: GitHub Issue Templates & AI Labels Not Configured",
                            React.createElement(
                              "span",
                              { className: "px-1.5 py-0.5 rounded-full text-[9px] font-bold bg-purple-950/80 text-purple-300 border border-purple-800/60" },
                              "AI Triage & Classification"
                            )
                          ),
                          React.createElement(
                            "div",
                            { className: "text-slate-400 text-[11px]" },
                            ghIssuesStatus.pending_task_id
                              ? ("Task " + ghIssuesStatus.pending_task_id + " (" + ghIssuesStatus.pending_task_status + ") is generating .github/ISSUE_TEMPLATE/ and triage labels.")
                              : "Set up standardized GitHub Issue templates (Bug Report, Feature Request) with 'zerofactory' human investigation labels."
                          )
                        )
                      ),
                      !ghIssuesStatus.pending_task_id &&
                      React.createElement(
                        "button",
                        {
                          type: "button",
                          className: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-semibold text-xs bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm transition-all duration-150 cursor-pointer disabled:opacity-50",
                          disabled: isSettingUpGhIssues,
                          onClick: () => handleTriggerGhIssuesSetup(selectedBoard)
                        },
                        isSettingUpGhIssues ? "Initiating Setup..." : "🏷️ Setup GitHub Issues"
                      )
                    )
  );
}
