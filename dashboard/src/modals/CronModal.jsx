import React from "react";
import { timeAgo } from "../utils/formatters.js";

export function CronModal(props) {
  const {
    showCronModal,
    setShowCronModal,
    cronJobs = [],
    cronSchedulerEnabled = true,
    loadingCron = false,
    cronFilterTab = "all",
    setCronFilterTab = () => {},
    cronSearchQuery = "",
    setCronSearchQuery = () => {},
    runningCronId,
    handleTriggerCron,
    handleRunCronJob = handleTriggerCron || (() => {}),
    editingCronId,
    setEditingCronId = () => {},
    cronEditForms = {},
    setCronEditForms = () => {},
    handleSaveCronEdit,
    handleSaveCronJob = handleSaveCronEdit || (() => {}),
    handleToggleCron,
    handleToggleCronJob = handleToggleCron || (() => {}),
    handleToggleScheduler,
    handleToggleCronScheduler = handleToggleScheduler || (() => {}),
    handleResetCronJob = () => {},
    handleSyncAllCron = () => {},
    loadCronJobs = () => {}
  } = props;

  const filteredCronJobs = React.useMemo(() => {
    return (cronJobs || []).filter((job) => {
      if (cronFilterTab === "core") {
        const isScanner = job.id.startsWith("zero-factory-improvement-scanner-") || job.category === "scanner";
        const isOpenWiki = job.id.startsWith("zero-factory-openwiki-update-") || job.category === "openwiki";
        if (isScanner || isOpenWiki) return false;
      } else if (cronFilterTab === "scanners") {
        const isScanner = job.id.startsWith("zero-factory-improvement-scanner-") || job.category === "scanner";
        if (!isScanner) return false;
      } else if (cronFilterTab === "openwiki") {
        const isOpenWiki = job.id.startsWith("zero-factory-openwiki-update-") || job.category === "openwiki";
        if (!isOpenWiki) return false;
      }
      if (cronSearchQuery && cronSearchQuery.trim()) {
        const q = cronSearchQuery.toLowerCase().trim();
        const matchesName = (job.name || "").toLowerCase().includes(q);
        const matchesId = (job.id || "").toLowerCase().includes(q);
        const matchesWorkdir = (job.workdir || "").toLowerCase().includes(q);
        return Boolean(matchesName || matchesId || matchesWorkdir);
      }
      return true;
    });
  }, [cronJobs, cronFilterTab, cronSearchQuery]);

  if (!showCronModal) return null;

  return React.createElement(
    "div",
    {
              className: "fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-xs p-4 overflow-y-auto",
              onClick: () => setShowCronModal(false)
            },
            React.createElement(
              "div",
              {
                className: "bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl max-w-4xl w-full max-h-[92vh] flex flex-col overflow-hidden text-slate-100",
                onClick: (e) => e.stopPropagation()
              },
              // Modal Header
              React.createElement(
                "div",
                { className: "flex items-center justify-between px-6 py-4 border-b border-slate-800 shrink-0 bg-slate-900/60" },
                React.createElement(
                  "div",
                  { className: "flex items-center gap-3" },
                  React.createElement("div", { className: "w-9 h-9 rounded-xl bg-gradient-to-br from-amber-500 to-indigo-600 flex items-center justify-center font-bold text-white shadow-md text-base shrink-0" }, "⏰"),
                  React.createElement(
                    "div",
                    null,
                    React.createElement("h2", { className: "text-base font-bold text-white m-0 flex items-center gap-2" }, "Zero Factory Cron Automation"),
                    React.createElement("p", { className: "text-xs text-slate-400 font-medium m-0" }, "Manage periodic health checks, daily metrics, and per-board improvement scanners")
                  )
                ),
                React.createElement(
                  "div",
                  { className: "flex items-center gap-2" },
                  React.createElement(
                    "button",
                    {
                      className: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors cursor-pointer",
                      onClick: handleSyncAllCron,
                      title: "Synchronize all built-in jobs across active profiles"
                    },
                    "🔄 Sync All"
                  ),
                  React.createElement(
                    "button",
                    {
                      className: "text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors text-lg leading-none cursor-pointer w-8 h-8 flex items-center justify-center",
                      onClick: () => setShowCronModal(false)
                    },
                    "✕"
                  )
                )
              ),
              // Master Scheduler Engine Control Banner
              React.createElement(
                "div",
                { className: "px-6 py-3.5 bg-slate-950/70 border-b border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shrink-0" },
                React.createElement(
                  "div",
                  { className: "flex items-center gap-3" },
                  React.createElement(
                    "div",
                    { className: "w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold " + (cronSchedulerEnabled ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30" : "bg-rose-500/10 text-rose-400 border border-rose-500/30") },
                    cronSchedulerEnabled ? "⚡" : "⏸"
                  ),
                  React.createElement(
                    "div",
                    null,
                    React.createElement(
                      "div",
                      { className: "flex items-center gap-2" },
                      React.createElement("span", { className: "text-xs font-bold text-white tracking-wide" }, "Periodic Cron Scheduler Engine"),
                      React.createElement("span", { className: "px-2 py-0.5 rounded-full text-[10px] font-bold " + (cronSchedulerEnabled ? "bg-emerald-950 text-emerald-300 border border-emerald-800/60" : "bg-rose-950 text-rose-300 border border-rose-800/60") }, cronSchedulerEnabled ? "Running (15s Ticks)" : "Disabled / Paused")
                    ),
                    React.createElement("p", { className: "text-[11px] text-slate-400 m-0 mt-0.5" },
                      cronSchedulerEnabled
                        ? "Background daemon actively ticks due jobs and spawns idle improvement scanners."
                        : "Master cron scheduler is disabled. All background ticking and autonomous scans are halted."
                    )
                  )
                ),
                React.createElement(
                  "div",
                  { className: "flex items-center gap-2.5 shrink-0 self-end sm:self-auto" },
                  React.createElement("span", { className: "text-xs font-semibold " + (cronSchedulerEnabled ? "text-emerald-400" : "text-slate-500") }, cronSchedulerEnabled ? "Active" : "Disabled"),
                  React.createElement(
                    "button",
                    {
                      type: "button",
                      role: "switch",
                      "aria-checked": cronSchedulerEnabled,
                      onClick: () => handleToggleCronScheduler(cronSchedulerEnabled),
                      className: "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none " + (cronSchedulerEnabled ? "bg-emerald-600" : "bg-slate-700")
                    },
                    React.createElement("span", {
                      className: "pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out " + (cronSchedulerEnabled ? "translate-x-4" : "translate-x-0")
                    })
                  )
                )
              ),
              // Filter Tabs & Search Bar
              React.createElement(
                "div",
                { className: "px-6 py-3 border-b border-slate-800/80 bg-slate-950/40 flex flex-col sm:flex-row items-center justify-between gap-3 shrink-0" },
                React.createElement(
                  "div",
                  { className: "flex items-center gap-1.5 bg-slate-900 p-1 rounded-lg border border-slate-800 text-xs" },
                  React.createElement(
                    "button",
                    {
                      className: "px-2.5 py-1 rounded-md font-medium transition-colors cursor-pointer " + (cronFilterTab === "all" ? "bg-indigo-600 text-white shadow-xs" : "text-slate-400 hover:text-slate-200"),
                      onClick: () => setCronFilterTab("all")
                    },
                    "All (" + cronJobs.length + ")"
                  ),
                  React.createElement(
                    "button",
                    {
                      className: "px-2.5 py-1 rounded-md font-medium transition-colors cursor-pointer " + (cronFilterTab === "core" ? "bg-indigo-600 text-white shadow-xs" : "text-slate-400 hover:text-slate-200"),
                      onClick: () => setCronFilterTab("core")
                    },
                    "Core (" + cronJobs.filter(j => !j.id.startsWith("zero-factory-improvement-scanner-") && !j.id.startsWith("zero-factory-openwiki-update-") && j.category !== "scanner" && j.category !== "openwiki").length + ")"
                  ),
                  React.createElement(
                    "button",
                    {
                      className: "px-2.5 py-1 rounded-md font-medium transition-colors cursor-pointer " + (cronFilterTab === "scanners" ? "bg-indigo-600 text-white shadow-xs" : "text-slate-400 hover:text-slate-200"),
                      onClick: () => setCronFilterTab("scanners")
                    },
                    "Scanners (" + cronJobs.filter(j => j.id.startsWith("zero-factory-improvement-scanner-") || j.category === "scanner").length + ")"
                  ),
                  React.createElement(
                    "button",
                    {
                      className: "px-2.5 py-1 rounded-md font-medium transition-colors cursor-pointer " + (cronFilterTab === "openwiki" ? "bg-indigo-600 text-white shadow-xs" : "text-slate-400 hover:text-slate-200"),
                      onClick: () => setCronFilterTab("openwiki")
                    },
                    "OpenWiki (" + cronJobs.filter(j => j.id.startsWith("zero-factory-openwiki-update-") || j.category === "openwiki").length + ")"
                  )
                ),
                React.createElement(
                  "input",
                  {
                    className: "w-full sm:w-64 bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 transition-colors",
                    placeholder: "Search jobs by name or ID...",
                    value: cronSearchQuery,
                    onChange: (e) => setCronSearchQuery(e.target.value)
                  }
                )
              ),
              // Job Cards List
              React.createElement(
                "div",
                { className: "p-6 space-y-4 overflow-y-auto zfk-scrollbar flex-1 bg-slate-950/20" },
                loadingCron && React.createElement("div", { className: "text-center py-12 text-slate-400 text-xs" }, React.createElement("span", { className: "zfk-spinning inline-block mr-2" }, "⏳"), "Loading cron schedules..."),
                !loadingCron && filteredCronJobs.length === 0 && React.createElement("div", { className: "text-center py-12 text-slate-500 text-xs" }, "No cron jobs match the selected filter."),
                !loadingCron && filteredCronJobs.map(job => {
                  const isEditing = editingCronId === job.id;
                  const form = cronEditForms[job.id] || {};
                  const isScanner = job.id.startsWith("zero-factory-improvement-scanner-") || job.category === "scanner";
                  const isOpenWiki = job.id.startsWith("zero-factory-openwiki-update-") || job.category === "openwiki";
                  const boardSlug = isScanner
                    ? job.id.replace("zero-factory-improvement-scanner-", "")
                    : (isOpenWiki ? job.id.replace("zero-factory-openwiki-update-", "") : null);
                  const isRunning = runningCronId === job.id;

                  return React.createElement(
                    "div",
                    {
                      key: job.id,
                      className: "bg-slate-900/90 border " + (job.enabled ? "border-slate-700/80 shadow-sm" : "border-slate-800/50 opacity-75") + " rounded-xl p-4 transition-all duration-150"
                    },
                    // Card Header Row
                    React.createElement(
                      "div",
                      { className: "flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800/80" },
                      React.createElement(
                        "div",
                        { className: "flex items-start gap-2.5" },
                        React.createElement(
                          "span",
                          {
                            className: "px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider shrink-0 mt-0.5 " +
                              (isScanner
                                ? "bg-purple-950/80 text-purple-300 border border-purple-800/60"
                                : isOpenWiki
                                  ? "bg-sky-950/80 text-sky-300 border border-sky-800/60"
                                  : "bg-indigo-950/80 text-indigo-300 border border-indigo-800/60")
                          },
                          isScanner ? "Scanner" : isOpenWiki ? "OpenWiki" : "Core"
                        ),
                        React.createElement(
                          "div",
                          null,
                          React.createElement("h3", { className: "text-sm font-semibold text-white m-0" }, job.name),
                          React.createElement(
                            "div",
                            { className: "flex flex-wrap items-center gap-2 mt-1 text-[11px] text-slate-400" },
                            React.createElement("span", { className: "text-[10px] text-slate-400 bg-slate-950/80 px-1.5 py-0.5 rounded border border-slate-800" }, job.id),
                            boardSlug && React.createElement("span", { className: "text-amber-400/90 font-medium" }, "Board: " + boardSlug),
                            job.workdir && React.createElement("span", { className: "truncate max-w-xs text-slate-400 font-mono text-[10px]" }, "📁 " + job.workdir)
                          )
                        )
                      ),
                      // Toggle Active / Paused switch
                      React.createElement(
                        "div",
                        { className: "flex items-center gap-2.5 shrink-0 self-end sm:self-auto" },
                        React.createElement("span", { className: "text-xs font-semibold " + (job.enabled ? "text-emerald-400" : "text-slate-500") }, job.enabled ? "Active" : "Paused"),
                        React.createElement(
                          "button",
                          {
                            type: "button",
                            role: "switch",
                            "aria-checked": job.enabled,
                            onClick: () => handleToggleCronJob(job.id, job.enabled),
                            className: "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none " + (job.enabled ? "bg-emerald-600" : "bg-slate-700")
                          },
                          React.createElement("span", {
                            className: "pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out " + (job.enabled ? "translate-x-4" : "translate-x-0")
                          })
                        )
                      )
                    ),
                    // Metadata / Runtime Status Row
                    React.createElement(
                      "div",
                      { className: "flex flex-wrap items-center justify-between gap-2 pt-3 text-xs" },
                      React.createElement(
                        "div",
                        { className: "flex flex-wrap items-center gap-2" },
                        // Schedule badge
                        React.createElement(
                          "span",
                          { className: "px-2 py-0.5 rounded-md bg-slate-950 border border-slate-800 font-mono text-[11px] text-indigo-300 font-medium" },
                          "⏱️ " + (
                            (job.scan_on_idle || job.schedule_display === "every 10080m" || (job.schedule && job.schedule.minutes === 10080))
                              ? "on idle"
                              : (job.schedule_display || "on idle")
                          )
                        ),
                        // Status pill
                        React.createElement(
                          "span",
                          {
                            className: "px-2 py-0.5 rounded-md text-[11px] font-medium border " +
                              (!job.enabled ? "bg-amber-950/60 text-amber-300 border-amber-800/60"
                                : job.last_status === "ok" ? "bg-emerald-950/60 text-emerald-300 border-emerald-800/60"
                                  : job.last_status === "error" ? "bg-rose-950/60 text-rose-300 border-rose-800/60"
                                    : "bg-slate-950 text-slate-300 border-slate-800")
                          },
                          !job.enabled ? "⏸ Paused" : job.last_status === "ok" ? "✓ OK" : job.last_status === "error" ? "✕ Failed" : "⏳ Scheduled"
                        ),
                        // Last Run
                        job.last_run_at && React.createElement("span", { className: "text-slate-400 text-[11px]" }, "Last: " + timeAgo(new Date(job.last_run_at).getTime() / 1000)),
                        // Customized badge
                        job.custom_config && React.createElement("span", { className: "px-1.5 py-0.5 rounded text-[10px] font-semibold bg-sky-950 text-sky-300 border border-sky-800/60" }, "Customized")
                      ),
                      // Action Buttons
                      React.createElement(
                        "div",
                        { className: "flex items-center gap-2 shrink-0 ml-auto" },
                        React.createElement(
                          "button",
                          {
                            className: "inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-emerald-600/90 hover:bg-emerald-600 text-white shadow-xs transition-colors cursor-pointer disabled:opacity-50",
                            disabled: isRunning,
                            onClick: () => handleRunCronJob(job.id),
                            title: "Run this job immediately"
                          },
                          isRunning ? React.createElement("span", { className: "zfk-spinning" }, "⏳") : "▶",
                          isRunning ? " Running..." : " Run Now"
                        ),
                        React.createElement(
                          "button",
                          {
                            className: "inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold " +
                              (job.enabled
                                ? "bg-slate-800 hover:bg-rose-950/50 text-slate-300 hover:text-rose-300 border border-slate-700 hover:border-rose-800/60"
                                : "bg-emerald-950/80 hover:bg-emerald-900 text-emerald-300 border border-emerald-700/80") +
                              " transition-colors cursor-pointer",
                            onClick: () => handleToggleCronJob(job.id, job.enabled),
                            title: job.enabled ? "Pause scheduled automation for this job" : "Resume scheduled automation for this job"
                          },
                          job.enabled ? "⏸ Pause" : "▶ Resume"
                        ),
                        React.createElement(
                          "button",
                          {
                            className: "inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors cursor-pointer",
                            onClick: () => setEditingCronId(isEditing ? null : job.id),
                            title: isEditing ? "Close configuration editor" : "Edit schedule and parameters"
                          },
                          isEditing ? "▲ Close" : "⚙ Edit"
                        ),
                        job.custom_config && React.createElement(
                          "button",
                          {
                            className: "inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-semibold text-slate-400 hover:text-amber-300 hover:bg-amber-950/30 border border-transparent hover:border-amber-800/40 transition-colors cursor-pointer",
                            onClick: () => handleResetCronJob(job.id),
                            title: "Reset schedule and settings to built-in default"
                          },
                          "↺ Reset"
                        )
                      )
                    ),
                    // Last Error Box if failed
                    job.last_error && React.createElement(
                      "div",
                      { className: "mt-2.5 p-2 rounded-lg bg-rose-950/40 border border-rose-900/60 text-xs text-rose-300 font-mono break-all" },
                      "⚠️ " + job.last_error
                    ),
                    // Inline Edit Drawer
                    isEditing && React.createElement(
                      "div",
                      { className: "mt-3.5 pt-3.5 border-t border-slate-800/80 space-y-3.5 bg-slate-950/40 -mx-4 -mb-4 p-4 rounded-b-xl" },
                      React.createElement(
                        "div",
                        { className: "space-y-1.5" },
                        React.createElement("label", { className: "block text-xs font-semibold text-slate-300" }, "Schedule Presets"),
                        React.createElement(
                          "div",
                          { className: "flex flex-wrap gap-1.5" },
                          [
                            ...(isScanner ? [{ label: "⚡ On Idle", kind: "idle" }] : []),
                            { label: "Every 15m", kind: "interval", minutes: 15 },
                            { label: "Every 30m", kind: "interval", minutes: 30 },
                            { label: "Every 60m", kind: "interval", minutes: 60 },
                            { label: "Every 120m", kind: "interval", minutes: 120 },
                            { label: "Daily (24h)", kind: "interval", minutes: 1440 },
                            { label: "Daily 09:00", kind: "cron", expr: "0 9 * * *" },
                            { label: "Custom Interval", kind: "interval", custom: true },
                            { label: "Custom Cron", kind: "cron", custom: true },
                            { label: form.enabled === false ? "⏸ Paused (Selected)" : "⏸ Pause Schedule", kind: "pause_toggle" }
                          ].map((preset, pIdx) => {
                            const isSel = preset.kind === "pause_toggle"
                              ? form.enabled === false
                              : preset.kind === "idle"
                                ? form.enabled !== false && form.scan_on_idle === true
                                : form.enabled !== false && (!isScanner || form.scan_on_idle !== true) && (preset.custom
                                  ? form.schedule_kind === preset.kind && form.is_custom_mode === preset.kind
                                  : form.schedule_kind === preset.kind && (preset.kind === "interval" ? parseInt(form.minutes, 10) === preset.minutes : form.cron_expr === preset.expr));
                            return React.createElement(
                              "button",
                              {
                                key: pIdx,
                                type: "button",
                                className: "px-2.5 py-1 rounded-md text-xs font-medium border transition-colors cursor-pointer " +
                                  (isSel
                                    ? (preset.kind === "pause_toggle" ? "bg-rose-600 text-white border-rose-500 shadow-xs" : preset.kind === "idle" ? "bg-purple-600 text-white border-purple-500 shadow-xs" : "bg-indigo-600 text-white border-indigo-500 shadow-xs")
                                    : (preset.kind === "pause_toggle" ? "bg-rose-950/40 text-rose-300 border-rose-900/60 hover:bg-rose-900/60" : preset.kind === "idle" ? "bg-purple-950/40 text-purple-300 border-purple-800/60 hover:bg-purple-500/30" : "bg-slate-900 text-slate-300 border-slate-700 hover:bg-slate-800")),
                                onClick: () => {
                                  if (preset.kind === "pause_toggle") {
                                    setCronEditForms({
                                      ...cronEditForms,
                                      [job.id]: { ...form, enabled: form.enabled === false }
                                    });
                                  } else if (preset.kind === "idle") {
                                    setCronEditForms({
                                      ...cronEditForms,
                                      [job.id]: { ...form, scan_on_idle: true, schedule_kind: "idle", is_custom_mode: null, enabled: true }
                                    });
                                  } else if (preset.custom) {
                                    setCronEditForms({
                                      ...cronEditForms,
                                      [job.id]: { ...form, scan_on_idle: false, schedule_kind: preset.kind, is_custom_mode: preset.kind, enabled: true }
                                    });
                                  } else if (preset.kind === "interval") {
                                    setCronEditForms({
                                      ...cronEditForms,
                                      [job.id]: { ...form, scan_on_idle: false, schedule_kind: "interval", minutes: preset.minutes, is_custom_mode: null, enabled: true }
                                    });
                                  } else {
                                    setCronEditForms({
                                      ...cronEditForms,
                                      [job.id]: { ...form, scan_on_idle: false, schedule_kind: "cron", cron_expr: preset.expr, is_custom_mode: null, enabled: true }
                                    });
                                  }
                                }
                              },
                              preset.label
                            );
                          })
                        )
                      ),
                      // Specific schedule inputs
                      (isScanner && form.scan_on_idle === true)
                        ? null
                        : (form.schedule_kind === "interval"
                          ? React.createElement(
                            "div",
                            { className: "space-y-1" },
                            React.createElement("label", { className: "block text-xs font-medium text-slate-400" }, "Interval (Minutes)"),
                            React.createElement("input", {
                              type: "number",
                              min: 1,
                              max: 10080,
                              className: "w-full max-w-xs bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 outline-none focus:border-indigo-500",
                              value: form.minutes || 60,
                              onChange: (e) => setCronEditForms({
                                ...cronEditForms,
                                [job.id]: { ...form, minutes: e.target.value }
                              })
                            })
                          )
                          : React.createElement(
                            "div",
                            { className: "space-y-1" },
                            React.createElement("label", { className: "block text-xs font-medium text-slate-400" }, "Standard Cron Expression (minute hour dom month dow)"),
                            React.createElement("input", {
                              type: "text",
                              placeholder: "e.g. 0 9 * * *",
                              className: "w-full max-w-xs bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs font-mono text-slate-200 outline-none focus:border-indigo-500",
                              value: form.cron_expr || "0 9 * * *",
                              onChange: (e) => setCronEditForms({
                                ...cronEditForms,
                                [job.id]: { ...form, cron_expr: e.target.value }
                              })
                            })
                          )
                        ),
                      // Model override & Workdir
                      React.createElement(
                        "div",
                        { className: "grid grid-cols-1 sm:grid-cols-2 gap-3" },
                        React.createElement(
                          "div",
                          { className: "space-y-1" },
                          React.createElement("label", { className: "block text-xs font-medium text-slate-400" }, "Model Override (optional)"),
                          React.createElement("input", {
                            type: "text",
                            placeholder: "Inherit environment default",
                            className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 outline-none focus:border-indigo-500",
                            value: form.model || "",
                            onChange: (e) => setCronEditForms({
                              ...cronEditForms,
                              [job.id]: { ...form, model: e.target.value }
                            })
                          })
                        ),
                        React.createElement(
                          "div",
                          { className: "space-y-1" },
                          React.createElement("label", { className: "block text-xs font-medium text-slate-400" }, "Working Directory (Worktree Root)"),
                          React.createElement("input", {
                            type: "text",
                            placeholder: "/path/to/workspace",
                            className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs font-mono text-slate-200 outline-none focus:border-indigo-500",
                            value: form.workdir || "",
                            onChange: (e) => setCronEditForms({
                              ...cronEditForms,
                              [job.id]: { ...form, workdir: e.target.value }
                            })
                          })
                        )
                      ),
                      // Schedule Status control in Edit Drawer
                      React.createElement(
                        "div",
                        { className: "flex items-center justify-between p-3 rounded-xl bg-slate-900/90 border border-slate-800" },
                        React.createElement(
                          "div",
                          null,
                          React.createElement("span", { className: "text-xs font-semibold text-white block" }, "Schedule Status"),
                          React.createElement("span", { className: "text-[11px] text-slate-400 block mt-0.5" }, form.enabled !== false ? "Job runs periodically according to schedule." : "Schedule is paused — job will not trigger automatically.")
                        ),
                        React.createElement(
                          "button",
                          {
                            type: "button",
                            className: "px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer border " +
                              (form.enabled !== false
                                ? "bg-emerald-950 text-emerald-300 border-emerald-700/80 hover:bg-emerald-900"
                                : "bg-rose-950 text-rose-300 border-rose-700/80 hover:bg-rose-900"),
                            onClick: () => setCronEditForms({
                              ...cronEditForms,
                              [job.id]: { ...form, enabled: form.enabled === false }
                            })
                          },
                          form.enabled !== false ? "✓ Scheduled (Active)" : "⏸ Paused (Disabled)"
                        )
                      ),
                      // Capacity-Driven Idle Scanning (only for improvement scanner jobs)
                      isScanner && React.createElement(
                        "div",
                        { className: "p-3 rounded-xl bg-slate-900/90 border border-slate-800 space-y-3" },
                        React.createElement(
                          "div",
                          { className: "flex items-center justify-between" },
                          React.createElement(
                            "div",
                            null,
                            React.createElement("label", { className: "block text-xs font-semibold text-purple-300" }, "⚡ Capacity-Driven Idle Scanning"),
                            React.createElement("p", { className: "text-[11px] text-slate-400 m-0" }, "Autonomously scan codebase when running agent workers are below board capacity.")
                          ),
                          React.createElement("input", {
                            type: "checkbox",
                            className: "h-4 w-4 rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500 cursor-pointer",
                            checked: Boolean(form.scan_on_idle !== false),
                            onChange: (e) => setCronEditForms({
                              ...cronEditForms,
                              [job.id]: {
                                ...form,
                                scan_on_idle: e.target.checked,
                                schedule_kind: e.target.checked ? "idle" : (form.schedule_kind === "idle" ? "interval" : form.schedule_kind)
                              }
                            })
                          })
                        ),
                        form.scan_on_idle !== false && React.createElement(
                          "div",
                          { className: "grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1 border-t border-slate-800/80" },
                            React.createElement("div", { className: "space-y-1" },
                              React.createElement("label", { className: "block text-[11px] font-medium text-slate-300" }, "Cooldown (Minutes)"),
                              React.createElement("input", {
                                type: "number",
                                min: 1,
                                step: 1,
                                className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-indigo-500",
                                value: form.idle_scan_cooldown_minutes ?? 15,
                                onChange: (e) => setCronEditForms({
                                  ...cronEditForms,
                                  [job.id]: { ...form, idle_scan_cooldown_minutes: e.target.value }
                                })
                              }),
                              React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Minimum interval between scans.")
                            ),
                            React.createElement("div", { className: "space-y-1" },
                              React.createElement("label", { className: "block text-[11px] font-medium text-slate-300" }, "Max Todo Limit"),
                              React.createElement("input", {
                                type: "number",
                                min: 0,
                                step: 1,
                                className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-indigo-500",
                                value: form.idle_scan_max_todo ?? 2,
                              onChange: (e) => setCronEditForms({
                                ...cronEditForms,
                                [job.id]: { ...form, idle_scan_max_todo: e.target.value }
                              })
                            }),
                            React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Suppresses scan if todo backlog >= this.")
                          )
                        )
                      ),
                      // Prompt Editor
                      React.createElement(
                        "div",
                        { className: "space-y-1" },
                        React.createElement("label", { className: "block text-xs font-medium text-slate-400" }, "Task Prompt Instructions"),
                        React.createElement("textarea", {
                          rows: 5,
                          className: "w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-[11px] font-mono text-slate-300 outline-none focus:border-indigo-500 zfk-scrollbar leading-relaxed",
                          value: form.prompt || "",
                          onChange: (e) => setCronEditForms({
                            ...cronEditForms,
                            [job.id]: { ...form, prompt: e.target.value }
                          })
                        })
                      ),
                      // Drawer Action Buttons
                      React.createElement(
                        "div",
                        { className: "flex items-center justify-end gap-2 pt-2" },
                        React.createElement(
                          "button",
                          {
                            type: "button",
                            className: "px-3 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 transition-colors cursor-pointer",
                            onClick: () => setEditingCronId(null)
                          },
                          "Cancel"
                        ),
                        React.createElement(
                          "button",
                          {
                            type: "button",
                            className: "px-3.5 py-1.5 rounded-lg text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 shadow-xs transition-colors cursor-pointer",
                            onClick: () => handleSaveCronJob(job.id)
                          },
                          "💾 Save Configuration"
                        )
                      )
                    )
                  );
                })
        )
      )
  );
}
