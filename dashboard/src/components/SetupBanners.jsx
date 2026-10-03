import React from "react";

export function SetupBanners(props) {
  const {
    selectedBoard,
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

  return React.createElement(
    React.Fragment,
    null,
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
                              { className: "px-1.5 py-0.2 rounded-full text-[9px] font-bold bg-sky-950/80 text-sky-300 border border-sky-800/60" },
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
                              { className: "px-1.5 py-0.2 rounded-full text-[9px] font-bold bg-purple-950/80 text-purple-300 border border-purple-800/60" },
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
