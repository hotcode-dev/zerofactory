import React from "react";
import { Modal } from "../components/Modal.jsx";

export function SettingsModal(props) {
  const {
    showSettingsModal,
    setShowSettingsModal,
    settingsForm,
    setSettingsForm,
    handleSaveSettings,
    isSavingSettings,
    isTestingLangfuse,
    handleTestLangfuse,
    langfuseTestResult,
    showLangfuseSecret,
    setShowLangfuseSecret,
    isSyncingProfiles,
    handleSyncProfiles,
    syncProfilesResult,
    syncForce,
    setSyncForce
  } = props;

  if (!showSettingsModal) return null;

  return React.createElement(
    Modal,
    {
      isOpen: showSettingsModal,
      onClose: () => setShowSettingsModal(false),
      onSubmit: handleSaveSettings,
      title: "Zero Factory Global Settings",
      subtitle: "System-wide orchestration limits and defaults",
      icon: "⚙️",
      bodyClassName: "p-6 space-y-4 text-xs overflow-y-auto zfk-scrollbar flex-1",
      footerClassName: "flex items-center justify-end gap-2.5 px-6 py-3.5 border-t border-slate-800 bg-slate-900/50 shrink-0",
      footer: React.createElement(
        React.Fragment,
        null,
        React.createElement(
          "button",
          {
            type: "button",
            className: "px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 transition-colors cursor-pointer",
            onClick: () => setShowSettingsModal(false)
          },
          "Cancel"
        ),
        React.createElement(
          "button",
          {
            type: "submit",
            disabled: isSavingSettings,
            className: "px-4 py-1.5 rounded-lg text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-500 transition-colors cursor-pointer shadow-xs shadow-indigo-600/30 disabled:opacity-50"
          },
          isSavingSettings ? "Saving..." : "Save Settings"
        )
      )
    },
    React.createElement(
      "div",
      { className: "space-y-1.5" },
                    React.createElement("label", { className: "block text-xs font-semibold text-slate-300 tracking-wide" }, "Max Active Tasks (WIP Limit)"),
                    React.createElement("input", {
                      type: "number",
                      min: 1,
                      step: 1,
                      className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
                      value: settingsForm.max_active_tasks ?? 10,
                      onChange: (e) => setSettingsForm({ ...settingsForm, max_active_tasks: e.target.value })
                    }),
                    React.createElement("p", { className: "text-[11px] text-slate-400 m-0 leading-relaxed" }, "Caps total tasks allowed in 'running' across all boards combined. Controls how many git worktrees are prepared from 'todo' to prevent queue and disk flooding. Default: 10.")
                  ),
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement("label", { className: "block text-xs font-semibold text-slate-300 tracking-wide" }, "Global Max Concurrent LLM Workers"),
                    React.createElement("input", {
                      type: "number",
                      min: 1,
                      step: 1,
                      className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
                      value: settingsForm.max_concurrent_llm_workers ?? 10,
                      onChange: (e) => setSettingsForm({ ...settingsForm, max_concurrent_llm_workers: e.target.value })
                    }),
                    React.createElement("p", { className: "text-[11px] text-slate-400 m-0 leading-relaxed" }, "Caps task workers and improvement scans combined across all boards; per-board limits and task WIP still apply. Default: 10.")
                  ),
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement("label", { className: "block text-xs font-semibold text-slate-300 tracking-wide" }, "Task Timeout (Seconds)"),
                    React.createElement("input", {
                      type: "number",
                      min: 60,
                      step: 60,
                      className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
                      value: settingsForm.task_timeout_seconds ?? 3600,
                      onChange: (e) => setSettingsForm({ ...settingsForm, task_timeout_seconds: e.target.value })
                    }),
                    React.createElement("p", { className: "text-[11px] text-slate-400 m-0 leading-relaxed" }, "Max running time before an active task worker is considered stuck and reaped. Increase if tasks run long test suites. Default: 3600 (1 hour).")
                  ),
                  React.createElement(
                    "div",
                    { className: "space-y-1.5" },
                    React.createElement("label", { className: "block text-xs font-semibold text-slate-300 tracking-wide" }, "Inactivity Timeout (Seconds)"),
                    React.createElement("input", {
                      type: "number",
                      min: 60,
                      step: 60,
                      className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
                      value: settingsForm.inactivity_timeout_seconds ?? 900,
                      onChange: (e) => setSettingsForm({ ...settingsForm, inactivity_timeout_seconds: e.target.value })
                    }),
                    React.createElement("p", { className: "text-[11px] text-slate-400 m-0 leading-relaxed" }, "Max idle time with no log output or session update before a worker is reaped. Default: 900 (15 minutes).")
                  ),

                  React.createElement(
                    "div",
                    { className: "pt-2 border-t border-slate-800/80 space-y-3" },
                    React.createElement(
                      "div",
                      { className: "flex items-center justify-between" },
                      React.createElement(
                        "div",
                        null,
                        React.createElement(
                          "div",
                          { className: "flex items-center gap-1.5" },
                          React.createElement("span", { className: "text-sm" }, "🧠"),
                          React.createElement("label", { className: "block text-xs font-semibold text-slate-200 tracking-wide" }, "Auto-Record Repository Memory")
                        ),
                        React.createElement("p", { className: "text-[11px] text-slate-400 m-0 leading-relaxed mt-0.5" }, "Automatically extract and persist gotchas, conventions, and rules when tasks complete or receive review feedback.")
                      ),
                      React.createElement(
                        "input",
                        {
                          type: "checkbox",
                          className: "h-4 w-4 rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500 cursor-pointer",
                          checked: Boolean(settingsForm.auto_record_memory !== false),
                          onChange: (e) => setSettingsForm({ ...settingsForm, auto_record_memory: e.target.checked })
                        }
                      )
                    ),
                    React.createElement(
                      "div",
                      { className: "flex items-center justify-between pt-1" },
                      React.createElement(
                        "div",
                        null,
                        React.createElement(
                          "div",
                          { className: "flex items-center gap-1.5" },
                          React.createElement("span", { className: "text-sm" }, "🐙"),
                          React.createElement("label", { className: "block text-xs font-semibold text-slate-200 tracking-wide" }, "Auto-Create GitHub Defect Issues")
                        ),
                        React.createElement("p", { className: "text-[11px] text-slate-400 m-0 leading-relaxed mt-0.5" }, "Automatically publish GitHub issues on hotcode-dev/zerofactory when internal platform defects are reported.")
                      ),
                      React.createElement(
                        "input",
                        {
                          type: "checkbox",
                          className: "h-4 w-4 rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500 cursor-pointer",
                          checked: Boolean(settingsForm.auto_create_github_issues),
                          onChange: (e) => setSettingsForm({ ...settingsForm, auto_create_github_issues: e.target.checked })
                        }
                      )
                    ),
                    React.createElement(
                      "div",
                      { className: "flex items-center justify-between pt-1" },
                      React.createElement(
                        "div",
                        null,
                        React.createElement(
                          "div",
                          { className: "flex items-center gap-1.5" },
                          React.createElement("span", { className: "text-sm" }, "⚡"),
                          React.createElement("label", { className: "block text-xs font-semibold text-slate-200 tracking-wide" }, "Mem0 Semantic Memory Engine")
                        ),
                        React.createElement("p", { className: "text-[11px] text-slate-400 m-0 leading-relaxed mt-0.5" }, "Use Mem0 vector database for semantic retrieval of repository memories. Inherits Hermes agent model and base URL.")
                      ),
                      React.createElement(
                        "input",
                        {
                          type: "checkbox",
                          className: "h-4 w-4 rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500 cursor-pointer",
                          checked: Boolean(settingsForm.mem0_enabled !== false),
                          onChange: (e) => setSettingsForm({ ...settingsForm, mem0_enabled: e.target.checked })
                        }
                      )
                    ),
                    Boolean(settingsForm.mem0_enabled !== false) && React.createElement(
                      "div",
                      { className: "space-y-3 pt-1 bg-slate-950/60 p-3 rounded-lg border border-slate-800/70 mt-1" },
                      React.createElement(
                        "div",
                        { className: "space-y-1" },
                        React.createElement("div", { className: "flex items-center justify-between" },
                          React.createElement("label", { className: "block text-[11px] font-medium text-slate-300" }, "Embedder Engine"),
                          React.createElement(
                            "span",
                            { className: `text-[10px] font-medium ${settingsForm.mem0_embedder_provider === "openai" ? "text-amber-400" : "text-emerald-400"}` },
                            settingsForm.mem0_embedder_provider === "openai" ? "Requires OpenAI API Key" : "✓ 100% Local (No OpenAI Key Required)"
                          )
                        ),
                        React.createElement("select", {
                          className: "w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-indigo-500 font-sans cursor-pointer",
                          value: settingsForm.mem0_embedder_provider || "fastembed",
                          onChange: (e) => setSettingsForm({ ...settingsForm, mem0_embedder_provider: e.target.value })
                        },
                          React.createElement("option", { value: "fastembed" }, "FastEmbed (Local ONNX CPU - No OpenAI needed)"),
                          React.createElement("option", { value: "openai" }, "OpenAI / Compatible Embeddings")
                        )
                      ),
                      settingsForm.mem0_embedder_provider === "openai" && React.createElement(
                        React.Fragment,
                        null,
                        React.createElement(
                          "div",
                          { className: "space-y-1" },
                          React.createElement("div", { className: "flex items-center justify-between" },
                            React.createElement("label", { className: "block text-[11px] font-medium text-slate-300" }, "Mem0 LLM Model"),
                            React.createElement("span", { className: "text-[10px] text-indigo-400 font-medium" }, "Inherits from Hermes agent")
                          ),
                          React.createElement("input", {
                            type: "text",
                            placeholder: "RadixArk/Qwen3.8-27B-NVFP4 (inherited from ~/.hermes/config.yaml)",
                            className: "w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 font-mono",
                            value: settingsForm.mem0_model ?? "",
                            onChange: (e) => setSettingsForm({ ...settingsForm, mem0_model: e.target.value })
                          })
                        ),
                        React.createElement(
                          "div",
                          { className: "space-y-1" },
                          React.createElement("div", { className: "flex items-center justify-between" },
                            React.createElement("label", { className: "block text-[11px] font-medium text-slate-300" }, "Mem0 / Hermes Base URL"),
                            React.createElement("span", { className: "text-[10px] text-indigo-400 font-medium" }, "Inherits from Hermes base_url")
                          ),
                          React.createElement("input", {
                            type: "text",
                            placeholder: "https://spark.ntsd.dev:8001/v1 (inherited from ~/.hermes/config.yaml)",
                            className: "w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 font-mono",
                            value: settingsForm.mem0_base_url ?? "",
                            onChange: (e) => setSettingsForm({ ...settingsForm, mem0_base_url: e.target.value })
                          })
                        ),
                        React.createElement(
                          "div",
                          { className: "grid grid-cols-2 gap-3" },
                          React.createElement(
                            "div",
                            { className: "space-y-1" },
                            React.createElement("label", { className: "block text-[11px] font-medium text-slate-300" }, "Embedding Model"),
                            React.createElement("input", {
                              type: "text",
                              placeholder: "text-embedding-3-small",
                              className: "w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 font-mono",
                              value: settingsForm.mem0_embedder_model ?? "",
                              onChange: (e) => setSettingsForm({ ...settingsForm, mem0_embedder_model: e.target.value })
                            })
                          ),
                          React.createElement(
                            "div",
                            { className: "space-y-1" },
                            React.createElement("label", { className: "block text-[11px] font-medium text-slate-300" }, "API Key (Optional)"),
                            React.createElement("input", {
                              type: "password",
                              placeholder: "sk-...",
                              className: "w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 font-mono",
                              value: settingsForm.mem0_api_key ?? "",
                              onChange: (e) => setSettingsForm({ ...settingsForm, mem0_api_key: e.target.value })
                            })
                          )
                        )
                      ),
                      settingsForm.mem0_embedder_provider !== "openai" && React.createElement(
                        "div",
                        { className: "space-y-1" },
                        React.createElement("div", { className: "flex items-center justify-between" },
                          React.createElement("label", { className: "block text-[11px] font-medium text-slate-300" }, "FastEmbed ONNX Model"),
                          React.createElement("span", { className: "text-[10px] text-slate-400 font-medium" }, "Runs on local CPU (384-dim)")
                        ),
                        React.createElement("input", {
                          type: "text",
                          placeholder: "BAAI/bge-small-en-v1.5 (default)",
                          className: "w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 font-mono",
                          value: settingsForm.mem0_embedder_model ?? "",
                          onChange: (e) => setSettingsForm({ ...settingsForm, mem0_embedder_model: e.target.value })
                        })
                      )
                    )
                  ),

                  // Agent Profiles Sync Section (Equivalent to `hermes zerofactory sync-profiles`)
                  React.createElement(
                    "div",
                    { className: "pt-2 border-t border-slate-800/80 space-y-3" },
                    React.createElement(
                      "div",
                      { className: "flex items-start justify-between gap-3" },
                      React.createElement(
                        "div",
                        null,
                        React.createElement(
                          "div",
                          { className: "flex items-center gap-1.5" },
                          React.createElement("span", { className: "text-sm" }, "🤖"),
                          React.createElement("label", { className: "block text-xs font-semibold text-slate-200 tracking-wide" }, "Agent Profiles & Skills")
                        ),
                        React.createElement("p", { className: "text-[11px] text-slate-400 m-0 leading-relaxed mt-0.5" }, "Synchronize SOUL.md system prompts, skills, and templates across zf-orchestrator, zf-builder, and zf-reviewer in ~/.hermes/profiles/.")
                      ),
                      React.createElement(
                        "button",
                        {
                          type: "button",
                          disabled: isSyncingProfiles,
                          onClick: handleSyncProfiles,
                          className: "px-3 py-1.5 rounded-lg bg-indigo-600/90 hover:bg-indigo-600 text-white font-medium text-xs border border-indigo-500/30 flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50 shrink-0 shadow-xs shadow-indigo-600/20"
                        },
                        isSyncingProfiles ? React.createElement(
                          "span",
                          { className: "animate-spin text-xs inline-block" },
                          "⏳"
                        ) : React.createElement("span", { className: "text-xs" }, "🔄"),
                        isSyncingProfiles ? "Syncing..." : "Sync Profiles"
                      )
                    ),
                    React.createElement(
                      "div",
                      { className: "flex items-center justify-between text-[11px] text-slate-400 pt-0.5" },
                      React.createElement(
                        "label",
                        { className: "flex items-center gap-1.5 cursor-pointer hover:text-slate-300 transition-colors" },
                        React.createElement("input", {
                          type: "checkbox",
                          className: "h-3.5 w-3.5 rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500 cursor-pointer",
                          checked: Boolean(syncForce),
                          onChange: (e) => setSyncForce(e.target.checked)
                        }),
                        React.createElement("span", null, "Force overwrite config.yaml with defaults")
                      ),
                      React.createElement(
                        "span",
                        { className: "text-[10px] text-slate-500 font-mono" },
                        "hermes zerofactory sync-profiles"
                      )
                    ),
                    syncProfilesResult && React.createElement(
                      "div",
                      {
                        className: `text-[11px] px-2.5 py-1.5 rounded border ${syncProfilesResult.ok
                          ? "bg-emerald-950/40 border-emerald-800/60 text-emerald-300"
                          : "bg-rose-950/40 border-rose-800/60 text-rose-300"
                          }`
                      },
                      (syncProfilesResult.ok ? "✓ " : "✕ ") + syncProfilesResult.message
                    )
                  ),

                  React.createElement(
                    "div",
                    { className: "pt-2 border-t border-slate-800/80 space-y-3" },
                    React.createElement(
                      "div",
                      { className: "flex items-center justify-between" },
                      React.createElement(
                        "div",
                        null,
                        React.createElement(
                          "div",
                          { className: "flex items-center gap-1.5" },
                          React.createElement("span", { className: "text-sm" }, "🔭"),
                          React.createElement("label", { className: "block text-xs font-semibold text-slate-200 tracking-wide" }, "Langfuse Observability & Tracing")
                        ),
                        React.createElement("p", { className: "text-[11px] text-slate-400 m-0 leading-relaxed mt-0.5" }, "Trace LLM calls, tool executions, latencies, and token costs across all agent profiles.")
                      ),
                      React.createElement(
                        "input",
                        {
                          type: "checkbox",
                          className: "h-4 w-4 rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500 cursor-pointer",
                          checked: Boolean(settingsForm.langfuse_enabled),
                          onChange: (e) => setSettingsForm({ ...settingsForm, langfuse_enabled: e.target.checked })
                        }
                      )
                    ),
                    settingsForm.langfuse_enabled && React.createElement(
                      "div",
                      { className: "space-y-3 pt-1 bg-slate-950/60 p-3 rounded-lg border border-slate-800/70" },
                      React.createElement(
                        "div",
                        { className: "space-y-1" },
                        React.createElement("label", { className: "block text-[11px] font-medium text-slate-300" }, "Langfuse Host / Base URL"),
                        React.createElement("input", {
                          type: "text",
                          placeholder: "https://cloud.langfuse.com",
                          className: "w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 font-mono",
                          value: settingsForm.langfuse_base_url ?? "https://cloud.langfuse.com",
                          onChange: (e) => setSettingsForm({ ...settingsForm, langfuse_base_url: e.target.value })
                        }),
                        React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Cloud instance (https://cloud.langfuse.com) or self-hosted URL (e.g. http://localhost:3000).")
                      ),
                      React.createElement(
                        "div",
                        { className: "grid grid-cols-1 sm:grid-cols-2 gap-2.5" },
                        React.createElement(
                          "div",
                          { className: "space-y-1" },
                          React.createElement("label", { className: "block text-[11px] font-medium text-slate-300" }, "Public Key"),
                          React.createElement("input", {
                            type: "text",
                            placeholder: "pk-lf-...",
                            className: "w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 font-mono",
                            value: settingsForm.langfuse_public_key ?? "",
                            onChange: (e) => setSettingsForm({ ...settingsForm, langfuse_public_key: e.target.value })
                          })
                        ),
                        React.createElement(
                          "div",
                          { className: "space-y-1" },
                          React.createElement(
                            "div",
                            { className: "flex items-center justify-between" },
                            React.createElement("label", { className: "block text-[11px] font-medium text-slate-300" }, "Secret Key"),
                            React.createElement(
                              "button",
                              {
                                type: "button",
                                className: "text-[10px] text-slate-400 hover:text-slate-200 cursor-pointer",
                                onClick: () => setShowLangfuseSecret(!showLangfuseSecret)
                              },
                              showLangfuseSecret ? "Hide" : "Show"
                            )
                          ),
                          React.createElement("input", {
                            type: showLangfuseSecret ? "text" : "password",
                            placeholder: "sk-lf-...",
                            className: "w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 font-mono",
                            value: settingsForm.langfuse_secret_key ?? "",
                            onChange: (e) => setSettingsForm({ ...settingsForm, langfuse_secret_key: e.target.value })
                          })
                        )
                      ),
                      React.createElement(
                        "div",
                        { className: "grid grid-cols-1 sm:grid-cols-2 gap-2.5" },
                        React.createElement(
                          "div",
                          { className: "space-y-1" },
                          React.createElement("label", { className: "block text-[11px] font-medium text-slate-300" }, "Environment Tag"),
                          React.createElement("input", {
                            type: "text",
                            placeholder: "zerofactory",
                            className: "w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-indigo-500 font-mono",
                            value: settingsForm.langfuse_env ?? "zerofactory",
                            onChange: (e) => setSettingsForm({ ...settingsForm, langfuse_env: e.target.value })
                          })
                        ),
                        React.createElement(
                          "div",
                          { className: "space-y-1" },
                          React.createElement("label", { className: "block text-[11px] font-medium text-slate-300" }, "Content Capture Mode"),
                          React.createElement(
                            "select",
                            {
                              className: "w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-indigo-500 cursor-pointer",
                              value: settingsForm.langfuse_capture_mode ?? "sanitized",
                              onChange: (e) => setSettingsForm({ ...settingsForm, langfuse_capture_mode: e.target.value })
                            },
                            React.createElement("option", { value: "sanitized" }, "Sanitized (Redact secrets & truncate)"),
                            React.createElement("option", { value: "metadata" }, "Metadata Only (No prompts/outputs)"),
                            React.createElement("option", { value: "full" }, "Full Content (Raw payloads)")
                          )
                        )
                      ),
                      React.createElement(
                        "div",
                        { className: "pt-2 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 border-t border-slate-800/60" },
                        React.createElement(
                          "div",
                          { className: "flex items-center gap-1.5 text-[11px]" },
                          React.createElement("span", { className: "text-emerald-400" }, "✓"),
                          React.createElement("span", { className: "text-slate-400" }, "Syncs to zf-orchestrator, zf-builder, zf-reviewer & root")
                        ),
                        React.createElement(
                          "div",
                          { className: "flex items-center gap-2" },
                          React.createElement(
                            "button",
                            {
                              type: "button",
                              disabled: isTestingLangfuse,
                              onClick: handleTestLangfuse,
                              className: "px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-[11px] font-medium transition-colors cursor-pointer disabled:opacity-50"
                            },
                            isTestingLangfuse ? "Testing..." : "Test Connection"
                          )
                        )
                      ),
                      langfuseTestResult && React.createElement(
                        "div",
                        {
                          className: `text-[11px] px-2.5 py-1.5 rounded border ${langfuseTestResult.ok
                            ? "bg-emerald-950/40 border-emerald-800/60 text-emerald-300"
                            : "bg-rose-950/40 border-rose-800/60 text-rose-300"
                            }`
                        },
                        (langfuseTestResult.ok ? "✓ " : "✕ ") + langfuseTestResult.message
                      )
                    )
                  )
  );
}
