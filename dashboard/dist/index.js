var ZeroFactoryDashboard = (function(exports) {
	Object.defineProperty(exports, Symbol.toStringTag, { value: "Module" });
	//#region dashboard/src/react-shim.js
	var SDK$1 = typeof window !== "undefined" && window.__HERMES_PLUGIN_SDK__ || {};
	var React = SDK$1.React || {};
	var { useState, useEffect, useMemo, useCallback, useRef, useContext, useReducer, createElement, Fragment } = SDK$1.hooks ? {
		...React,
		...SDK$1.hooks
	} : React;
	//#endregion
	//#region dashboard/src/sdk.js
	var SDK = typeof window !== "undefined" && window.__HERMES_PLUGIN_SDK__ || {
		React: {},
		hooks: {},
		fetchJSON: () => Promise.resolve({}),
		utils: {}
	};
	var fetchJSON = SDK.fetchJSON;
	var utils = SDK.utils || {};
	//#endregion
	//#region dashboard/src/constants.js
	var API_BASE = "/api/plugins/zerofactory";
	var COLUMNS = [
		{
			id: "triage",
			title: "Triage",
			icon: "📥",
			dotColor: "#818cf8",
			desc: "Raw backlog & epics"
		},
		{
			id: "todo",
			title: "Todo",
			icon: "📋",
			dotColor: "#38bdf8",
			desc: "Prioritized queue ready for pickup"
		},
		{
			id: "running",
			title: "Running",
			icon: "⚡",
			dotColor: "#fbbf24",
			desc: "Autonomous AI agents"
		},
		{
			id: "blocked",
			title: "Blocked",
			icon: "🛑",
			dotColor: "#f43f5e",
			desc: "Human action required"
		},
		{
			id: "done",
			title: "Done",
			icon: "✅",
			dotColor: "#a78bfa",
			desc: "Completed & merged"
		}
	];
	var NEXT_STATUS_MAP = {
		triage: "todo",
		todo: "running",
		running: "blocked",
		blocked: "done",
		done: "triage"
	};
	//#endregion
	//#region dashboard/src/components/Header.jsx
	function Header(props) {
		const { activeView, setActiveView, hasActiveAgents, sessionsList = [], agentsList = [], loadSessions, loadAgents, loadMemories, boards = [], selectedBoard, setSelectedBoard, handleOpenEditBoard, handleOpenEditBoardModal, handleOpenNewBoardModal, handleOpenCronModal, setShowCronModal, loadCronJobs, cronSchedulerEnabled = true, cronJobs = [], handleOpenSettingsModal, setShowSettingsModal, loadSettings, setShowNewTaskModal, setNewTaskForm, isDispatching, handleRunDispatcher, handleDispatch, loadBoards, loadTasksAndStats } = props;
		return React.createElement("header", { className: "space-y-4 pb-5 border-b border-slate-800/80" }, React.createElement("div", { className: "flex flex-col lg:flex-row lg:items-center justify-between gap-4" }, React.createElement("div", { className: "flex items-center gap-4 flex-wrap" }, React.createElement("div", { className: "flex items-center gap-3.5" }, React.createElement("div", { className: "w-10 h-10 rounded-xl bg-gradient-to-br from-indigo-500 to-purple-600 flex items-center justify-center font-bold text-white shadow-lg shadow-indigo-500/25 text-sm tracking-wider shrink-0" }, "ZF"), React.createElement("div", null, React.createElement("h1", { className: "text-xl font-bold tracking-tight text-white flex items-center gap-2" }, "Zero Factory Kanban"), React.createElement("p", { className: "text-xs text-slate-400 font-medium" }, "Autonomous Multi-Agent Coordination Engine"))), React.createElement("div", { className: "flex items-center bg-slate-900/90 border border-slate-800 rounded-xl p-1 gap-1" }, React.createElement("button", {
			type: "button",
			className: "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer " + (activeView === "board" ? "bg-indigo-600 text-white shadow-xs shadow-indigo-600/30" : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"),
			onClick: () => setActiveView("board")
		}, "📋 Board"), React.createElement("button", {
			type: "button",
			className: "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer relative " + (activeView === "activities" ? "bg-indigo-600 text-white shadow-xs shadow-indigo-600/30" : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"),
			onClick: () => setActiveView("activities")
		}, "⚡ Activities", hasActiveAgents && React.createElement("span", { className: "w-2 h-2 rounded-full bg-emerald-400 zfk-pulse-active shrink-0 ml-0.5" })), React.createElement("button", {
			type: "button",
			className: "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer relative " + (activeView === "sessions" || activeView === "agents" ? "bg-indigo-600 text-white shadow-xs shadow-indigo-600/30" : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"),
			onClick: () => {
				setActiveView("agents");
				loadSessions();
				loadAgents();
				loadMemories(selectedBoard);
			}
		}, "🤖 Agents", (hasActiveAgents || sessionsList.some((s) => s.status === "ongoing" || s.is_active) || agentsList.some((a) => a.is_active)) && React.createElement("span", { className: "w-2 h-2 rounded-full bg-emerald-400 zfk-pulse-active shrink-0 ml-0.5" })), React.createElement("button", {
			type: "button",
			className: "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold transition-all cursor-pointer " + (activeView === "instructions" ? "bg-indigo-600 text-white shadow-xs shadow-indigo-600/30" : "text-slate-400 hover:text-slate-200 hover:bg-slate-800/60"),
			onClick: () => setActiveView("instructions")
		}, "📖 Instructions"))), React.createElement("div", { className: "flex flex-wrap items-center gap-2.5" }, (activeView === "instructions" || activeView === "activities" || activeView === "sessions" || activeView === "agents") && React.createElement("button", {
			type: "button",
			className: "inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/25 transition-all duration-150 cursor-pointer",
			onClick: () => setActiveView("board")
		}, "← Back to Board"), boards.length > 0 ? React.createElement("select", {
			className: "bg-slate-900/90 border border-slate-700/80 hover:border-slate-600 rounded-lg px-3 py-1.5 text-xs font-medium text-slate-200 focus:ring-1 focus:ring-indigo-500 focus:outline-none cursor-pointer transition-colors shadow-sm",
			value: selectedBoard,
			onChange: (e) => {
				const val = e.target.value;
				setSelectedBoard(val);
				loadTasksAndStats(val);
				loadMemories(val);
				loadSessions(val);
				loadAgents(val);
			}
		}, React.createElement("option", {
			key: "all",
			value: "all"
		}, "All Boards (" + boards.reduce((acc, b) => acc + (b.task_count || 0), 0) + ")"), boards.map((b) => React.createElement("option", {
			key: b.slug,
			value: b.slug
		}, b.slug + (b.task_count ? " (" + b.task_count + ")" : "")))) : React.createElement("span", { className: "px-2.5 py-1 text-xs font-semibold text-amber-300 bg-amber-950/60 border border-amber-800/60 rounded-lg" }, "No Boards Configured"), React.createElement("button", {
			className: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold " + (boards.length === 0 ? "bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/30" : "bg-slate-800/80 hover:bg-slate-700/90 text-slate-200 border border-slate-700/80 hover:border-slate-600 shadow-sm") + " transition-all duration-150 cursor-pointer",
			onClick: handleOpenNewBoardModal,
			title: "Create New Board"
		}, "+ Board"), selectedBoard && selectedBoard !== "all" && React.createElement("button", {
			className: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800/80 hover:bg-slate-700/90 text-slate-200 border border-slate-700/80 hover:border-slate-600 shadow-sm transition-all duration-150 cursor-pointer",
			onClick: handleOpenEditBoard || handleOpenEditBoardModal,
			title: "Edit board settings and manage board"
		}, "⚙️ Edit Board"), React.createElement("button", {
			className: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800/80 hover:bg-slate-700/90 text-slate-200 border border-slate-700/80 hover:border-slate-600 shadow-sm transition-all duration-150 cursor-pointer",
			onClick: () => {
				if (handleOpenCronModal) handleOpenCronModal();
				else {
					if (setShowCronModal) setShowCronModal(true);
					if (loadCronJobs) loadCronJobs();
				}
			},
			title: "Configure built-in Cron schedules and periodic automation"
		}, "⏰ Cron Config", React.createElement("span", { className: "px-1.5 py-0.5 rounded-full text-[10px] font-bold " + (!cronSchedulerEnabled ? "bg-rose-950/90 text-rose-300 border border-rose-800/80 shadow-xs" : cronJobs.some((j) => j.enabled) ? "bg-emerald-950/80 text-emerald-300 border border-emerald-800/60" : "bg-slate-800 text-slate-400") }, !cronSchedulerEnabled ? "PAUSED" : cronJobs.length > 0 ? cronJobs.filter((j) => j.enabled).length + "/" + cronJobs.length : "CRON")), React.createElement("button", {
			className: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800/80 hover:bg-slate-700/90 text-slate-200 border border-slate-700/80 hover:border-slate-600 shadow-sm transition-all duration-150 cursor-pointer",
			onClick: () => {
				if (handleOpenSettingsModal) handleOpenSettingsModal();
				else {
					if (loadSettings) loadSettings();
					if (setShowSettingsModal) setShowSettingsModal(true);
				}
			},
			title: "Global Zero Factory configuration (WIP limits, worker caps)"
		}, "⚙️ Settings"), React.createElement("button", {
			className: "inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-emerald-600 hover:bg-emerald-500 text-white shadow-md shadow-emerald-600/25 transition-all duration-150 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed" + (isDispatching ? " opacity-70 cursor-wait" : ""),
			onClick: handleRunDispatcher || handleDispatch,
			disabled: isDispatching || boards.length === 0,
			title: boards.length === 0 ? "Create a board first" : "Trigger Zero Factory Dispatcher Cycle"
		}, isDispatching ? React.createElement("span", { className: "zfk-spinning" }, "⏳") : "⚡", isDispatching ? " Dispatching..." : " Dispatch"), React.createElement("button", {
			className: "inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-md shadow-indigo-600/25 transition-all duration-150 cursor-pointer disabled:opacity-50 disabled:cursor-not-allowed",
			onClick: () => {
				if (boards.length === 0) {
					if (handleOpenNewBoardModal) handleOpenNewBoardModal();
				} else {
					if (setNewTaskForm) setNewTaskForm((prev) => ({
						...prev,
						board_slug: selectedBoard && selectedBoard !== "all" ? selectedBoard : boards[0] ? boards[0].slug : ""
					}));
					if (setShowNewTaskModal) setShowNewTaskModal(true);
				}
			},
			disabled: boards.length === 0,
			title: boards.length === 0 ? "Create a board first" : "Create New Task"
		}, "+ New Task"), React.createElement("button", {
			className: "inline-flex items-center justify-center p-2 rounded-lg text-xs font-semibold bg-slate-800/80 hover:bg-slate-700/90 text-slate-200 border border-slate-700/80 hover:border-slate-600 shadow-sm transition-all duration-150 cursor-pointer",
			onClick: () => {
				loadBoards();
				loadTasksAndStats();
			},
			title: "Refresh Board"
		}, "🔄"))));
	}
	//#endregion
	//#region dashboard/src/utils/icons.js
	var renderPrIcon = function(className = "w-3 h-3 shrink-0") {
		return React.createElement("svg", {
			className,
			viewBox: "0 0 16 16",
			fill: "currentColor",
			xmlns: "http://www.w3.org/2000/svg"
		}, React.createElement("path", { d: "M7.177 3.073L9.573.677A.25.25 0 0110 .854v4.792a.25.25 0 01-.427.177L7.177 3.427a.25.25 0 010-.354zM3.75 2.5a.75.75 0 100 1.5.75.75 0 000-1.5zm-2.25.75a2.25 2.25 0 113 2.122v5.256a2.251 2.251 0 11-1.5 0V5.372A2.25 2.25 0 011.5 3.25zM11 2.5h-1V4h1a1 1 0 011 1v5.628a2.251 2.251 0 101.5 0V5A2.5 2.5 0 0011 2.5zm1 10.25a.75.75 0 111.5 0 .75.75 0 01-1.5 0zM3.75 12a.75.75 0 100 1.5.75.75 0 000-1.5z" }));
	};
	//#endregion
	//#region dashboard/src/components/StatsBar.jsx
	function StatsBar(props) {
		const { stats, prFilter, setPrFilter } = props;
		if (!stats) return null;
		return React.createElement("div", { className: "grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3 pt-1" }, React.createElement("div", { className: "bg-slate-900/60 backdrop-blur-md border border-slate-800/80 hover:border-slate-700/80 rounded-xl p-3 flex items-center gap-3 shadow-sm transition-all duration-150" }, React.createElement("div", { className: "w-9 h-9 rounded-lg flex items-center justify-center text-base shrink-0 bg-indigo-500/15 text-indigo-400" }, "📊"), React.createElement("div", { className: "flex flex-col min-w-0" }, React.createElement("span", { className: "text-lg font-bold text-white tracking-tight leading-none" }, stats.total || 0), React.createElement("span", { className: "text-[11px] text-slate-400 font-medium truncate mt-1" }, "Total Tasks"))), React.createElement("div", { className: "bg-slate-900/60 backdrop-blur-md border border-slate-800/80 hover:border-slate-700/80 rounded-xl p-3 flex items-center gap-3 shadow-sm transition-all duration-150" }, React.createElement("div", { className: "w-9 h-9 rounded-lg flex items-center justify-center text-base shrink-0 bg-amber-500/15 text-amber-400" }, "⚡"), React.createElement("div", { className: "flex flex-col min-w-0" }, React.createElement("span", { className: "text-lg font-bold text-white tracking-tight leading-none" }, stats.columns && stats.columns.running || 0), React.createElement("span", { className: "text-[11px] text-slate-400 font-medium truncate mt-1" }, "Active In Progress"))), React.createElement("div", { className: "bg-slate-900/60 backdrop-blur-md border border-slate-800/80 hover:border-slate-700/80 rounded-xl p-3 flex items-center gap-3 shadow-sm transition-all duration-150" }, React.createElement("div", { className: "w-9 h-9 rounded-lg flex items-center justify-center text-base shrink-0 bg-rose-500/15 text-rose-400" }, "🛑"), React.createElement("div", { className: "flex flex-col min-w-0" }, React.createElement("span", { className: "text-lg font-bold text-white tracking-tight leading-none" }, stats.columns && stats.columns.blocked || 0), React.createElement("span", { className: "text-[11px] text-slate-400 font-medium truncate mt-1" }, "Blocked / Action"))), React.createElement("div", { className: "bg-slate-900/60 backdrop-blur-md border border-slate-800/80 hover:border-slate-700/80 rounded-xl p-3 flex items-center gap-3 shadow-sm transition-all duration-150" }, React.createElement("div", { className: "w-9 h-9 rounded-lg flex items-center justify-center text-base shrink-0 bg-purple-500/15 text-purple-400" }, "✅"), React.createElement("div", { className: "flex flex-col min-w-0" }, React.createElement("span", { className: "text-lg font-bold text-white tracking-tight leading-none" }, stats.columns && stats.columns.done || 0), React.createElement("span", { className: "text-[11px] text-slate-400 font-medium truncate mt-1" }, "Completed"))), React.createElement("div", { className: "bg-slate-900/60 backdrop-blur-md border border-slate-800/80 hover:border-slate-700/80 rounded-xl p-3 flex items-center gap-3 shadow-sm transition-all duration-150" }, React.createElement("div", { className: "w-9 h-9 rounded-lg flex items-center justify-center text-base shrink-0 bg-emerald-500/15 text-emerald-400" }, "🌿"), React.createElement("div", { className: "flex flex-col min-w-0" }, React.createElement("span", { className: "text-lg font-bold text-white tracking-tight leading-none" }, stats.active_worktrees || 0), React.createElement("span", { className: "text-[11px] text-slate-400 font-medium truncate mt-1" }, "Git Worktrees"))), React.createElement("div", {
			className: "bg-slate-900/60 backdrop-blur-md border border-slate-800/80 hover:border-slate-700/80 rounded-xl p-3 flex items-center gap-3 shadow-sm transition-all duration-150 cursor-pointer " + (prFilter === "has_pr" ? "ring-1 ring-purple-500/50 bg-purple-950/20" : ""),
			onClick: () => setPrFilter && setPrFilter(prFilter === "has_pr" ? "all" : "has_pr"),
			title: "Filter by tasks with Pull Requests"
		}, React.createElement("div", { className: "w-9 h-9 rounded-lg flex items-center justify-center text-base shrink-0 bg-purple-500/15 text-purple-400" }, renderPrIcon("w-4 h-4 text-purple-400")), React.createElement("div", { className: "flex flex-col min-w-0" }, React.createElement("span", { className: "text-lg font-bold text-white tracking-tight leading-none" }, stats.pr_count || 0), React.createElement("span", { className: "text-[11px] text-slate-400 font-medium truncate mt-1" }, "Pull Requests"))));
	}
	//#endregion
	//#region dashboard/src/components/FilterBar.jsx
	function FilterBar(props) {
		const { searchQuery, setSearchQuery, assigneeFilter, setAssigneeFilter, priorityFilter, setPriorityFilter, prFilter, setPrFilter, stats, autoRefresh, setAutoRefresh, isSyncingIssues, onSyncIssues } = props;
		return React.createElement("div", { className: "flex flex-wrap items-center justify-between gap-3 bg-slate-900/40 backdrop-blur-sm border border-slate-800/70 p-3 rounded-xl" }, React.createElement("div", { className: "flex items-center gap-2 bg-slate-950/60 border border-slate-800 focus-within:border-indigo-500/80 focus-within:ring-1 focus-within:ring-indigo-500/40 rounded-lg px-3 py-1.5 min-w-[240px] md:w-80 transition-all" }, React.createElement("span", { className: "text-xs text-slate-500 shrink-0" }, "🔍"), React.createElement("input", {
			type: "text",
			className: "bg-transparent text-xs text-slate-100 placeholder-slate-500 outline-none w-full",
			placeholder: "Search tasks by title, description, ID or PR...",
			value: searchQuery,
			onChange: (e) => setSearchQuery(e.target.value)
		})), React.createElement("div", { className: "flex items-center gap-1.5 flex-wrap" }, React.createElement("span", { className: "text-xs text-slate-400 mr-1" }, "Role:"), [
			{
				id: "all",
				label: "All"
			},
			{
				id: "zf-builder",
				label: "ZF Builder"
			},
			{
				id: "zf-reviewer",
				label: "ZF Reviewer"
			},
			{
				id: "zf-orchestrator",
				label: "ZF Orchestrator"
			},
			{
				id: "human",
				label: "Human"
			},
			{
				id: "unassigned",
				label: "Unassigned"
			}
		].map((roleObj) => React.createElement("button", {
			key: roleObj.id,
			type: "button",
			className: (assigneeFilter === roleObj.id ? "bg-indigo-600 text-white border-indigo-500 shadow-xs shadow-indigo-600/30" : "bg-slate-800/70 text-slate-400 border-slate-700/60 hover:text-slate-200 hover:bg-slate-800") + " px-2.5 py-1 rounded-md text-xs font-medium cursor-pointer transition-colors border text-center",
			onClick: () => setAssigneeFilter(roleObj.id)
		}, roleObj.label))), React.createElement("div", { className: "flex items-center gap-1.5 flex-wrap" }, React.createElement("span", { className: "text-xs text-slate-400 mr-1" }, "Prio:"), [
			"all",
			"P0",
			"P1",
			"P2",
			"P3"
		].map((prio) => React.createElement("button", {
			key: prio,
			type: "button",
			className: (priorityFilter === prio ? "bg-indigo-600 text-white border-indigo-500 shadow-xs shadow-indigo-600/30" : "bg-slate-800/70 text-slate-400 border-slate-700/60 hover:text-slate-200 hover:bg-slate-800") + " px-2.5 py-1 rounded-md text-xs font-medium cursor-pointer transition-colors border text-center",
			onClick: () => setPriorityFilter(prio)
		}, prio))), React.createElement("div", { className: "flex items-center gap-1.5 flex-wrap" }, React.createElement("span", { className: "text-xs text-slate-400 mr-1" }, "PR:"), [{
			id: "all",
			label: "All"
		}, {
			id: "has_pr",
			label: "Has PR"
		}].map((item) => React.createElement("button", {
			key: item.id,
			type: "button",
			className: (prFilter === item.id ? "bg-purple-600 text-white border-purple-500 shadow-xs shadow-purple-600/30" : "bg-slate-800/70 text-slate-400 border-slate-700/60 hover:text-slate-200 hover:bg-slate-800") + " px-2.5 py-1 rounded-md text-xs font-medium cursor-pointer transition-colors border text-center inline-flex items-center gap-1.5",
			onClick: () => setPrFilter(item.id)
		}, item.id === "has_pr" && renderPrIcon("w-3 h-3 shrink-0"), item.label, item.id === "has_pr" && stats && stats.pr_count > 0 && React.createElement("span", { className: "px-1.5 py-0.2 rounded-full text-[10px] font-bold bg-purple-950/80 text-purple-300 border border-purple-800/60" }, stats.pr_count)))), React.createElement("div", { className: "flex items-center gap-3" }, onSyncIssues && React.createElement("button", {
			type: "button",
			disabled: isSyncingIssues,
			onClick: onSyncIssues,
			className: "px-2.5 py-1 rounded-md text-xs font-medium text-slate-300 hover:text-white bg-slate-800/80 hover:bg-slate-700/80 border border-slate-700/80 transition-all flex items-center gap-1.5 cursor-pointer disabled:opacity-50 shrink-0 shadow-xs",
			title: "Sync open GitHub issues requested for AI investigation into Triage"
		}, React.createElement("span", { className: isSyncingIssues ? "animate-spin inline-block text-xs" : "text-xs" }, isSyncingIssues ? "🔄" : "🐙"), isSyncingIssues ? "Syncing..." : "Sync GitHub Issues"), React.createElement("label", { className: "flex items-center gap-2 text-xs text-slate-400 hover:text-slate-200 cursor-pointer select-none" }, React.createElement("input", {
			type: "checkbox",
			className: "rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500 cursor-pointer",
			checked: autoRefresh,
			onChange: (e) => setAutoRefresh(e.target.checked)
		}), "Live 10s Poll")));
	}
	//#endregion
	//#region dashboard/src/components/SetupBanners.jsx
	function SetupBanners(props) {
		const { selectedBoard, precommitStatus, openwikiStatus, ghIssuesStatus, isSettingUpPrecommit, handleTriggerPrecommitSetup, isSettingUpOpenwiki, handleTriggerOpenwikiSetup, isSettingUpGhIssues, handleTriggerGhIssuesSetup } = props;
		return React.createElement(React.Fragment, null, Boolean(selectedBoard && selectedBoard !== "all" && precommitStatus && !precommitStatus.has_precommit) && React.createElement("div", { className: "mb-3.5 px-4 py-2.5 rounded-xl border border-amber-500/30 bg-amber-950/20 backdrop-blur-md flex flex-wrap items-center justify-between gap-3 text-xs" }, React.createElement("div", { className: "flex items-center gap-2.5 text-amber-200" }, React.createElement("span", { className: "text-base" }, precommitStatus.pending_task_id ? "⚡" : "⚠️"), React.createElement("div", null, React.createElement("div", { className: "font-semibold text-slate-100" }, precommitStatus.pending_task_id ? "Precommit Setup Task in Progress" : "Precommit Verification Not Configured"), React.createElement("div", { className: "text-slate-400 text-[11px]" }, precommitStatus.pending_task_id ? "Task " + precommitStatus.pending_task_id + " (" + precommitStatus.pending_task_status + ") is generating .zerofactory/precommit.sh" : "This board lacks .zerofactory/precommit.sh. Set up standard automated test, build, and format verification for commits."))), !precommitStatus.pending_task_id && React.createElement("button", {
			type: "button",
			className: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-semibold text-xs bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm transition-all duration-150 cursor-pointer disabled:opacity-50",
			disabled: isSettingUpPrecommit,
			onClick: () => handleTriggerPrecommitSetup(selectedBoard)
		}, isSettingUpPrecommit ? "Initiating Setup..." : "⚡ Setup Repo for Zero Factory")), Boolean(selectedBoard && selectedBoard !== "all" && openwikiStatus && !openwikiStatus.has_openwiki) && React.createElement("div", { className: "mb-3.5 px-4 py-2.5 rounded-xl border border-sky-500/30 bg-sky-950/20 backdrop-blur-md flex flex-wrap items-center justify-between gap-3 text-xs" }, React.createElement("div", { className: "flex items-center gap-2.5 text-sky-200" }, React.createElement("span", { className: "text-base" }, openwikiStatus.pending_task_id ? "⏳" : "📖"), React.createElement("div", null, React.createElement("div", { className: "font-semibold text-slate-100 flex items-center gap-1.5" }, openwikiStatus.pending_task_id ? "OpenWiki Setup Task in Progress" : "Recommended: OpenWiki Architecture Docs Not Generated", React.createElement("span", { className: "px-1.5 py-0.2 rounded-full text-[9px] font-bold bg-sky-950/80 text-sky-300 border border-sky-800/60" }, "Context Optimization")), React.createElement("div", { className: "text-slate-400 text-[11px]" }, openwikiStatus.pending_task_id ? "Task " + openwikiStatus.pending_task_id + " (" + openwikiStatus.pending_task_status + ") is generating openwiki/ documentation." : "Generate a machine-readable architecture wiki (openwiki/) to cut exploratory agent tool calls and token bloat by 30–40%."))), !openwikiStatus.pending_task_id && React.createElement("button", {
			type: "button",
			className: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-semibold text-xs bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm transition-all duration-150 cursor-pointer disabled:opacity-50",
			disabled: isSettingUpOpenwiki,
			onClick: () => handleTriggerOpenwikiSetup(selectedBoard)
		}, isSettingUpOpenwiki ? "Initiating Setup..." : "📖 Setup OpenWiki")), Boolean(selectedBoard && selectedBoard !== "all" && ghIssuesStatus && !ghIssuesStatus.has_gh_issues) && React.createElement("div", { className: "mb-3.5 px-4 py-2.5 rounded-xl border border-purple-500/30 bg-purple-950/20 backdrop-blur-md flex flex-wrap items-center justify-between gap-3 text-xs" }, React.createElement("div", { className: "flex items-center gap-2.5 text-purple-200" }, React.createElement("span", { className: "text-base" }, ghIssuesStatus.pending_task_id ? "⏳" : "🏷️"), React.createElement("div", null, React.createElement("div", { className: "font-semibold text-slate-100 flex items-center gap-1.5" }, ghIssuesStatus.pending_task_id ? "GitHub Issues Setup Task in Progress" : "Recommended: GitHub Issue Templates & AI Labels Not Configured", React.createElement("span", { className: "px-1.5 py-0.2 rounded-full text-[9px] font-bold bg-purple-950/80 text-purple-300 border border-purple-800/60" }, "AI Triage & Classification")), React.createElement("div", { className: "text-slate-400 text-[11px]" }, ghIssuesStatus.pending_task_id ? "Task " + ghIssuesStatus.pending_task_id + " (" + ghIssuesStatus.pending_task_status + ") is generating .github/ISSUE_TEMPLATE/ and triage labels." : "Set up standardized GitHub Issue templates (Bug Report, Feature Request) with 'zerofactory' human investigation labels."))), !ghIssuesStatus.pending_task_id && React.createElement("button", {
			type: "button",
			className: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg font-semibold text-xs bg-indigo-600 hover:bg-indigo-500 text-white shadow-sm transition-all duration-150 cursor-pointer disabled:opacity-50",
			disabled: isSettingUpGhIssues,
			onClick: () => handleTriggerGhIssuesSetup(selectedBoard)
		}, isSettingUpGhIssues ? "Initiating Setup..." : "🏷️ Setup GitHub Issues")));
	}
	//#endregion
	//#region dashboard/src/utils/formatters.js
	var timeAgo = utils.timeAgo || function(ts) {
		if (!ts) return "";
		const diff = Math.floor(Date.now() / 1e3 - ts);
		if (diff < 60) return "just now";
		if (diff < 3600) return Math.floor(diff / 60) + "m ago";
		if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
		return Math.floor(diff / 86400) + "d ago";
	};
	var formatPrLabel = function(url) {
		if (!url) return "";
		const trimmed = String(url).trim();
		if (/^#?\d+$/.test(trimmed)) return "PR #" + trimmed.replace(/^#/, "");
		const m = trimmed.match(/\/(?:pull|merge_requests)\/(\d+)/i);
		if (m) return "PR #" + m[1];
		return "PR ↗";
	};
	var computeGitSlug = function(gitUrl) {
		if (!gitUrl) return "";
		let cleaned = gitUrl.trim().replace(/\.git$/, "").replace(/\/+$/, "");
		cleaned = cleaned.replace(/^[a-zA-Z]+:\/\//, "");
		if (cleaned.includes("@")) {
			cleaned = cleaned.split("@")[1];
			if (cleaned.includes(":")) cleaned = cleaned.split(":")[1];
			else if (cleaned.includes("/")) cleaned = cleaned.split("/").slice(1).join("/");
		} else if (cleaned.includes("/")) {
			const first = cleaned.split("/")[0];
			if (first.includes(".") || first.includes(":")) cleaned = cleaned.split("/").slice(1).join("/");
		}
		const parts = cleaned.split("/").filter(Boolean);
		const repo = parts.length >= 1 ? parts[parts.length - 1].replace(/[^a-zA-Z0-9_\-.]/g, "") : "";
		const owner = parts.length >= 2 ? parts[parts.length - 2].replace(/[^a-zA-Z0-9_\-.]/g, "") : "";
		if (owner && repo) return (owner + "-" + repo).toLowerCase().replace(/[^a-zA-Z0-9_\-]/g, "-").replace(/^-+|-+$/g, "");
		if (repo) return repo.toLowerCase().replace(/[^a-zA-Z0-9_\-]/g, "-").replace(/^-+|-+$/g, "");
		return "";
	};
	//#endregion
	//#region dashboard/src/components/KanbanBoard.jsx
	function KanbanBoard(props) {
		const { tasksByColumn, dragOverCol, handleDragOver, handleDragLeave, handleDrop, handleDragStart, loadTaskDetails, selectedBoard, stoppingSessionId, handleStopTaskSession, handleAdvanceTask } = props;
		return React.createElement("div", { className: "overflow-x-auto pb-4 -mx-1 px-1 zfk-scrollbar" }, React.createElement("div", {
			className: "grid grid-cols-5 gap-3.5 items-start min-w-[1100px] w-full",
			style: {
				display: "grid",
				gridTemplateColumns: "repeat(5, minmax(220px, 1fr))"
			}
		}, COLUMNS.map((col) => {
			const colTasks = tasksByColumn[col.id] || [];
			const isOver = dragOverCol === col.id;
			return React.createElement("div", {
				key: col.id,
				className: "flex flex-col gap-2.5 bg-slate-900/50 backdrop-blur-md border rounded-xl p-2.5 min-h-[520px] transition-all duration-150 " + (isOver ? "border-indigo-500 bg-indigo-950/20 ring-2 ring-indigo-500/30" : "border-slate-800/80"),
				onDragOver: (e) => handleDragOver(e, col.id),
				onDragLeave: handleDragLeave,
				onDrop: (e) => handleDrop(e, col.id)
			}, React.createElement("div", { className: "flex items-center justify-between px-1.5 py-1 select-none" }, React.createElement("div", { className: "flex items-center gap-2 min-w-0" }, React.createElement("div", {
				className: "w-2.5 h-2.5 rounded-full shrink-0 shadow-xs",
				style: {
					backgroundColor: col.dotColor,
					boxShadow: "0 0 6px " + col.dotColor + "88"
				}
			}), React.createElement("h3", { className: "text-xs font-semibold uppercase tracking-wider text-slate-300 truncate m-0" }, col.title)), React.createElement("span", { className: "text-[0.6875rem] font-bold px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700/60 text-slate-400 font-mono" }, colTasks.length)), React.createElement("div", { className: "flex flex-col gap-2.5 flex-1 min-h-[120px]" }, colTasks.length === 0 ? React.createElement("div", { className: "flex flex-col items-center justify-center p-6 text-center text-xs text-slate-500 border border-dashed border-slate-800/80 rounded-lg bg-slate-900/20 my-auto select-none" }, "No " + col.title + " tasks", React.createElement("br", null), React.createElement("span", { className: "text-[0.6875rem] opacity-60 mt-1" }, "Drop tasks here")) : colTasks.map((t) => {
				const isRunning = t.status === "running";
				const prioClass = t.priority === "P0" ? "bg-rose-500/15 text-rose-300 border-rose-500/30" : t.priority === "P1" ? "bg-amber-500/15 text-amber-300 border-amber-500/30" : t.priority === "P3" ? "bg-slate-700/40 text-slate-400 border-slate-600/30" : "bg-sky-500/15 text-sky-300 border-sky-500/30";
				const roleClass = t.assignee === "zf-builder" ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30" : t.assignee === "zf-reviewer" ? "bg-cyan-500/15 text-cyan-300 border-cyan-500/30" : t.assignee === "zf-orchestrator" ? "bg-purple-500/15 text-purple-300 border-purple-500/30" : t.assignee === "human" ? "bg-violet-500/15 text-violet-300 border-violet-500/30 font-semibold" : "bg-slate-700/30 text-slate-400 border-slate-700/40";
				return React.createElement("div", {
					key: t.id,
					className: "group bg-slate-800/70 hover:bg-slate-800/95 border rounded-lg p-3 space-y-2.5 shadow-xs hover:shadow-md transition-all duration-150 cursor-grab active:cursor-grabbing hover:-translate-y-0.5 " + (isRunning ? "border-emerald-500/60 shadow-[0_0_12px_rgba(16,185,129,0.25)]" : "border-slate-700/60 hover:border-slate-600"),
					draggable: true,
					onDragStart: (e) => handleDragStart(e, t),
					onClick: () => loadTaskDetails(t.id)
				}, React.createElement("div", { className: "flex items-center justify-between gap-2" }, React.createElement("span", { className: "font-mono text-[0.6875rem] font-semibold text-slate-400 tracking-wider" }, t.id), React.createElement("div", { className: "flex items-center gap-1.5 flex-wrap" }, React.createElement("span", { className: "text-[0.625rem] font-bold uppercase tracking-wider px-1.5 py-0.5 rounded border " + prioClass }, t.priority || "P2"), React.createElement("span", { className: "text-[0.625rem] font-medium capitalize px-1.5 py-0.5 rounded border " + roleClass }, t.assignee || "unassigned"))), React.createElement("h4", { className: "text-xs font-semibold text-slate-200 leading-snug line-clamp-2 m-0 group-hover:text-white" }, t.title), React.createElement("div", { className: "flex items-center gap-2 text-[0.6875rem] text-slate-400 flex-wrap" }, selectedBoard === "all" && t.board_slug && React.createElement("span", { className: "inline-flex items-center gap-1 text-sky-400 font-mono text-[0.625rem] bg-sky-950/50 border border-sky-800/50 px-1.5 py-0.5 rounded truncate max-w-[130px]" }, "📋 " + t.board_slug), t.repo_alias && React.createElement("span", { className: "inline-flex items-center gap-1 text-teal-300 font-mono text-[0.625rem] bg-teal-950/60 border border-teal-800/60 px-1.5 py-0.5 rounded truncate max-w-[130px]" }, "📦 " + t.repo_alias), t.tenant && !t.repo_alias && React.createElement("span", { className: "inline-flex items-center gap-1 truncate max-w-[140px]" }, "📁 " + t.tenant), t.branch_name && React.createElement("span", { className: "inline-flex items-center gap-1 text-indigo-300 font-mono truncate max-w-[120px]" }, "🌿 " + t.branch_name), t.pr_url && React.createElement("a", {
					href: t.pr_url,
					target: "_blank",
					rel: "noopener noreferrer",
					onClick: (e) => e.stopPropagation(),
					className: "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[0.625rem] font-mono font-semibold bg-purple-500/15 hover:bg-purple-500/30 text-purple-300 hover:text-purple-100 border border-purple-500/30 transition-all duration-150 truncate max-w-[140px] shadow-xs cursor-pointer",
					title: "Pull Request: " + t.pr_url
				}, renderPrIcon("w-2.5 h-2.5 shrink-0 text-purple-400"), formatPrLabel(t.pr_url)), t.blocking_parent_count > 0 && React.createElement("span", { className: "text-[0.625rem] font-medium px-1.5 py-0.5 rounded bg-amber-500/10 text-amber-300 border border-amber-500/20" }, "⏳ " + t.blocking_parent_count + " blocker")), (t.status === "running" || t.session_progress && (t.session_progress.has_session || t.session_progress.sessions && t.session_progress.sessions.length > 0)) && (() => {
					const tSessions = t.session_progress && t.session_progress.sessions || [];
					const isRunning = t.status === "running";
					const ongoingSess = isRunning ? tSessions.find((s) => s.status === "ongoing" || s.is_active) || t.session_progress : null;
					const activeAgent = t.assignee || ongoingSess && ongoingSess.agent || "zf-builder";
					const agentIcon = activeAgent === "zf-reviewer" ? "🔍" : activeAgent === "zf-orchestrator" ? "🧭" : "🔨";
					const agentLabel = activeAgent === "zf-reviewer" ? "Reviewing PR" : activeAgent === "zf-orchestrator" ? "Orchestrating" : "Implementing";
					if (isRunning) return React.createElement("div", { className: "flex items-center justify-between gap-1.5 p-1.5 rounded-md border text-xs " + (activeAgent === "zf-reviewer" ? "bg-cyan-500/10 border-cyan-500/25 text-cyan-300" : "bg-emerald-500/10 border-emerald-500/20 text-emerald-300") }, React.createElement("div", { className: "flex items-center gap-1.5 min-w-0" }, React.createElement("span", { className: "w-2 h-2 rounded-full shrink-0 " + (t.session_progress && t.session_progress.is_alive ? activeAgent === "zf-reviewer" ? "bg-cyan-400 zfk-pulse-active" : "bg-emerald-400 zfk-pulse-active" : "bg-slate-500") }), React.createElement("span", { className: "text-[0.6875rem] truncate font-medium" }, agentIcon + " " + agentLabel + (t.session_progress && t.session_progress.turn_count ? " • " + t.session_progress.turn_count + " turns" : "") + (t.session_progress && t.session_progress.last_action ? " • " + t.session_progress.last_action : ""))), React.createElement("div", { className: "flex items-center gap-1 shrink-0" }, tSessions.length > 1 && React.createElement("span", { className: "text-[0.625rem] font-mono px-1.5 py-0.2 rounded bg-slate-800/80 text-slate-300 border border-slate-700/60" }, tSessions.length + " sess"), React.createElement("button", {
						type: "button",
						disabled: stoppingSessionId === (ongoingSess && ongoingSess.session_id || t.id),
						className: "p-0.5 px-1 rounded text-[10px] font-semibold bg-rose-950/70 hover:bg-rose-900 text-rose-300 border border-rose-800/70 hover:border-rose-800/60 transition-colors cursor-pointer shadow-xs disabled:opacity-50",
						title: "Stop running AI session",
						onClick: (e) => {
							e.stopPropagation();
							handleStopTaskSession(t.id, ongoingSess && ongoingSess.session_id);
						}
					}, stoppingSessionId === (ongoingSess && ongoingSess.session_id || t.id) ? "..." : "⏹")));
					if (tSessions.length > 0) {
						const uniqueAgents = Array.from(new Set(tSessions.map((s) => s.agent || t.assignee)));
						const iconMap = {
							"zf-reviewer": "🔍",
							"zf-orchestrator": "🧭",
							"zf-builder": "🔨"
						};
						const iconsStr = uniqueAgents.map((a) => iconMap[a] || "🤖").join(" ");
						return React.createElement("div", { className: "flex items-center justify-between gap-1.5 p-1.5 rounded-md border border-slate-800/80 bg-slate-900/50 text-slate-400 text-xs" }, React.createElement("span", { className: "text-[0.6875rem] truncate font-medium flex items-center gap-1 text-slate-300" }, React.createElement("span", { className: "w-1.5 h-1.5 rounded-full bg-slate-500 shrink-0" }), tSessions.length + " AI session" + (tSessions.length > 1 ? "s" : "") + ": " + iconsStr), t.session_progress && t.session_progress.turn_count ? React.createElement("span", { className: "text-[0.625rem] text-slate-500 font-mono shrink-0" }, t.session_progress.turn_count + "t") : null);
					}
					return null;
				})(), t.status !== "running" && (() => {
					const metaStr = typeof t.metadata === "string" ? t.metadata : JSON.stringify(t.metadata || {});
					const descStr = typeof t.description === "string" ? t.description : "";
					const titleStr = typeof t.title === "string" ? t.title : "";
					const isGrillInterview = metaStr.includes("Grill-with-Docs") || metaStr.includes("Awaiting Human Input") || metaStr.includes("awaiting_interview") || descStr.includes("Grill-with-Docs") || titleStr.toLowerCase().includes("grill");
					const isHumanTriage = t.status === "triage" && (t.assignee === "human" || isGrillInterview);
					const isHumanReview = t.status === "blocked" && t.assignee === "human";
					const isBlocked = t.status === "blocked";
					if (!isBlocked && !isHumanTriage && !isHumanReview) return null;
					let badgeClass = "";
					let dotClass = "";
					let labelText = "";
					if (isGrillInterview || t.status === "triage" && t.assignee === "human") {
						badgeClass = "bg-indigo-500/20 border-indigo-500/40 text-indigo-200";
						dotClass = "bg-indigo-400 zfk-pulse-active";
						labelText = isGrillInterview ? "🎯 Waiting for Human Decision • Grill Interview" : "🎯 Waiting for Human Input";
					} else if (metaStr.includes("\"conflict_retries\"")) {
						badgeClass = "bg-amber-500/15 border-amber-500/30 text-amber-300";
						dotClass = "bg-amber-400";
						labelText = "🟠 Merge Conflict";
					} else if (isHumanReview) {
						badgeClass = "bg-teal-500/15 border-teal-500/30 text-teal-300";
						dotClass = "bg-teal-400 zfk-pulse-active";
						labelText = "🟢 Waiting for Human to Merge";
					} else if (t.blocking_parent_count > 0) {
						badgeClass = "bg-slate-800 border-slate-700 text-slate-300";
						dotClass = "bg-slate-400";
						labelText = "⏳ Blocked by Parent Task";
					} else if (isBlocked) {
						badgeClass = "bg-rose-500/15 border-rose-500/30 text-rose-300";
						dotClass = "bg-rose-400 zfk-pulse-active";
						labelText = "🛑 Action Required / Stuck";
					} else return null;
					return React.createElement("div", { className: "flex items-center gap-2 p-1.5 rounded-md border text-xs " + badgeClass }, React.createElement("span", { className: "w-2 h-2 rounded-full shrink-0 " + dotClass }), React.createElement("span", { className: "text-[0.6875rem] truncate font-medium" }, labelText));
				})(), React.createElement("div", { className: "flex items-center justify-between pt-1 border-t border-slate-700/40 text-[0.6875rem] text-slate-400" }, React.createElement("span", { className: "text-[0.6875rem] text-slate-500" }, timeAgo(t.updated_at || t.created_at)), React.createElement("div", { className: "flex items-center gap-1.5" }, t.comment_count > 0 && React.createElement("span", {
					className: "inline-flex items-center px-1.5 py-0.5 rounded text-[0.6875rem] bg-slate-700/50 text-slate-300 hover:text-white cursor-pointer",
					title: t.comment_count + " comments"
				}, "💬 " + t.comment_count), React.createElement("button", {
					type: "button",
					className: "inline-flex items-center justify-center w-5 h-5 rounded bg-slate-700/60 hover:bg-indigo-600 text-slate-300 hover:text-white transition-colors cursor-pointer text-xs leading-none font-bold",
					onClick: (e) => handleAdvanceTask(t, e),
					title: "Move to next column"
				}, "→"))));
			})));
		})));
	}
	//#endregion
	//#region dashboard/src/components/EmptyBoardState.jsx
	function EmptyBoardState({ onNewBoard, onInstructions }) {
		return React.createElement("div", { className: "flex flex-col items-center justify-center py-20 px-6 text-center bg-slate-900/40 backdrop-blur-sm border border-slate-800/80 rounded-2xl max-w-2xl mx-auto my-8 space-y-6 shadow-2xl" }, React.createElement("div", { className: "w-20 h-20 rounded-2xl bg-gradient-to-br from-indigo-500/20 to-purple-500/20 border border-indigo-500/30 flex items-center justify-center text-4xl shadow-inner shadow-indigo-500/10" }, "📋"), React.createElement("div", { className: "space-y-2 max-w-lg" }, React.createElement("h2", { className: "text-xl font-bold text-white tracking-tight" }, "No Kanban Boards Configured"), React.createElement("p", { className: "text-xs text-slate-400 leading-relaxed" }, "Zero Factory requires at least one project board to organize tasks, track GitHub Pull Requests, and orchestrate autonomous AI agents. Please create a board to get started.")), React.createElement("div", { className: "flex flex-wrap items-center justify-center gap-3 pt-2" }, React.createElement("button", {
			type: "button",
			className: "inline-flex items-center gap-2 px-5 py-2.5 rounded-xl text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/30 transition-all duration-150 cursor-pointer",
			onClick: onNewBoard
		}, "✨ Create First Board"), React.createElement("button", {
			type: "button",
			className: "inline-flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-all duration-150 cursor-pointer",
			onClick: onInstructions
		}, "📖 Read Instructions & Architecture")));
	}
	//#endregion
	//#region dashboard/src/components/Toast.jsx
	function Toast({ toast }) {
		if (!toast) return null;
		return React.createElement("div", {
			style: { zIndex: 999999 },
			className: "fixed top-6 right-6 px-4 py-3 rounded-xl font-semibold text-sm shadow-2xl flex items-center gap-2.5 transition-all duration-200 border pointer-events-auto " + (toast.type === "error" ? "bg-rose-950/95 text-rose-200 border-rose-700 shadow-rose-950/80" : toast.type === "success" ? "bg-emerald-950/95 text-emerald-200 border-emerald-700 shadow-emerald-950/80" : "bg-indigo-950/95 text-indigo-200 border-indigo-700 shadow-indigo-950/80")
		}, toast.message);
	}
	//#endregion
	//#region dashboard/src/views/ActivitiesView.jsx
	function ActivitiesView(props) {
		const { activities, activitiesTotal, activitiesAgents, activitiesStats, activitiesFilterOptions, activitiesLoading, activityActorFilter, setActivityActorFilter, activityActionFilter, setActivityActionFilter, activityBoardFilter, setActivityBoardFilter, activityAssigneeFilter, setActivityAssigneeFilter, activitySearchQuery, setActivitySearchQuery, loadActivities, boards, setActiveView, loadTaskDetails, tasks, liveAgents = [], effectiveActivities = [], effectiveStats = {}, effectiveFilterOptions = {
			actors: [],
			actions: [],
			boards: []
		}, activityPage = 0, setActivityPage = () => {}, activityLimit = 15, activityViewMode = "timeline", setActivityViewMode = () => {}, autoRefresh = false, setAutoRefresh = () => {}, expandedActivityId = null, setExpandedActivityId = () => {}, isDispatching = false, handleRunDispatcher = () => {} } = props;
		const getActionBadge = (action) => {
			switch (action) {
				case "start": return {
					label: "Dispatched",
					icon: "🚀",
					bg: "bg-indigo-500/15 text-indigo-300 border-indigo-500/30"
				};
				case "worker_done": return {
					label: "Completed",
					icon: "✅",
					bg: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
				};
				case "worker_failed": return {
					label: "Worker Failed",
					icon: "❌",
					bg: "bg-rose-500/15 text-rose-300 border-rose-500/30"
				};
				case "worker_timeout": return {
					label: "Timeout",
					icon: "⏱️",
					bg: "bg-red-500/15 text-red-300 border-red-500/30"
				};
				case "worker_lost": return {
					label: "Worker Lost",
					icon: "⚠️",
					bg: "bg-amber-500/15 text-amber-300 border-amber-500/30"
				};
				case "pr_conflict": return {
					label: "Git Conflict",
					icon: "🛑",
					bg: "bg-amber-500/15 text-amber-300 border-amber-500/30"
				};
				case "conflict_fixing": return {
					label: "Fixing Conflict",
					icon: "🔧",
					bg: "bg-amber-500/15 text-amber-300 border-amber-500/30"
				};
				case "conflict_resolved": return {
					label: "Conflict Resolved",
					icon: "🛠️",
					bg: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
				};
				case "pr_conflict_failed": return {
					label: "Conflict Failed",
					icon: "💥",
					bg: "bg-rose-500/15 text-rose-300 border-rose-500/30"
				};
				case "conflict_unverifiable": return {
					label: "Conflict Unverifiable",
					icon: "⚠️",
					bg: "bg-rose-500/15 text-rose-300 border-rose-500/30"
				};
				case "pr_opened": return {
					label: "PR Opened",
					icon: "🔍",
					bg: "bg-blue-500/15 text-blue-300 border-blue-500/30"
				};
				case "approved": return {
					label: "PR Approved",
					icon: "👁️",
					bg: "bg-purple-500/15 text-purple-300 border-purple-500/30"
				};
				case "changes_requested": return {
					label: "Changes Req.",
					icon: "💬",
					bg: "bg-orange-500/15 text-orange-300 border-orange-500/30"
				};
				case "merged": return {
					label: "PR Merged",
					icon: "🎉",
					bg: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30"
				};
				case "promote": return {
					label: "Promoted Ready",
					icon: "⚡",
					bg: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30"
				};
				case "unblock": return {
					label: "Unblocked",
					icon: "🔓",
					bg: "bg-teal-500/15 text-teal-300 border-teal-500/30"
				};
				case "move": return {
					label: "Status Move",
					icon: "📦",
					bg: "bg-slate-500/15 text-slate-300 border-slate-500/30"
				};
				case "create": return {
					label: "Created",
					icon: "✨",
					bg: "bg-sky-500/15 text-sky-300 border-sky-500/30"
				};
				case "comment": return {
					label: "Comment",
					icon: "💬",
					bg: "bg-violet-500/15 text-violet-300 border-violet-500/30"
				};
				default: return {
					label: action || "Event",
					icon: "⚡",
					bg: "bg-slate-700/40 text-slate-300 border-slate-600/40"
				};
			}
		};
		const getActorBadge = (actor) => {
			if (actor === "zf-builder") return {
				label: "zf-builder",
				icon: "🔨",
				role: "Builder",
				color: "text-amber-300 bg-amber-500/10 border-amber-500/30"
			};
			if (actor === "zf-reviewer") return {
				label: "zf-reviewer",
				icon: "🔍",
				role: "Reviewer",
				color: "text-purple-300 bg-purple-500/10 border-purple-500/30"
			};
			if (actor === "zf-orchestrator") return {
				label: "zf-orchestrator",
				icon: "🎯",
				role: "Orchestrator",
				color: "text-indigo-300 bg-indigo-500/10 border-indigo-500/30"
			};
			if (actor === "dispatcher") return {
				label: "dispatcher",
				icon: "⚙️",
				role: "Dispatcher Engine",
				color: "text-cyan-300 bg-cyan-500/10 border-cyan-500/30"
			};
			if (actor === "user") return {
				label: "user",
				icon: "👤",
				role: "User",
				color: "text-sky-300 bg-sky-500/10 border-sky-500/30"
			};
			return {
				label: "other",
				icon: "📦",
				role: "Other",
				color: "text-slate-400 bg-slate-700/30 border-slate-600/30"
			};
		};
		const effectiveTotal = activityActorFilter !== "all" || activityActionFilter !== "all" || activityBoardFilter !== "all" || Boolean(activitySearchQuery.trim()) ? effectiveActivities.length : activitiesTotal || effectiveActivities.length;
		const totalPages = Math.ceil(effectiveTotal / activityLimit) || 1;
		const startIdx = effectiveTotal === 0 ? 0 : activityPage * activityLimit + 1;
		const endIdx = Math.min((activityPage + 1) * activityLimit, effectiveTotal);
		return React.createElement("div", { className: "space-y-6 pb-12 max-w-[1600px] mx-auto" }, React.createElement("div", { className: "relative overflow-hidden bg-gradient-to-br from-indigo-950/70 via-slate-900/90 to-purple-950/60 border border-slate-700/90 rounded-2xl p-6 md:p-8 shadow-2xl space-y-6" }, React.createElement("div", { className: "flex flex-col md:flex-row md:items-center justify-between gap-4 relative z-10" }, React.createElement("div", { className: "space-y-2" }, React.createElement("div", { className: "flex items-center gap-2.5 flex-wrap" }, React.createElement("span", { className: "px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-indigo-900/80 text-indigo-100 border border-indigo-500/60 font-mono shadow-xs" }, "Live Telemetry Feed"), React.createElement("span", { className: "px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-emerald-900/80 text-emerald-100 border border-emerald-500/60 font-mono shadow-xs flex items-center gap-1.5" }, React.createElement("span", { className: "w-1.5 h-1.5 rounded-full bg-emerald-400 zfk-pulse-active" }), "Real-Time Stream")), React.createElement("h2", { className: "text-2xl md:text-3xl font-extrabold text-white tracking-tight m-0 flex items-center gap-2.5" }, "⚡ Agent Recent Activities"), React.createElement("p", { className: "text-xs md:text-sm text-slate-200 max-w-3xl leading-relaxed m-0 font-normal" }, "Live execution log, process dispatch states, Git worktree lifecycle events, PR review outcomes, and tool invocation telemetry across all autonomous Zero Factory specialists.")), React.createElement("div", { className: "flex items-center gap-2.5 shrink-0 flex-wrap" }, React.createElement("button", {
			type: "button",
			className: "inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-600/80 shadow-md transition-all cursor-pointer",
			onClick: () => loadActivities()
		}, React.createElement("span", { className: activitiesLoading ? "zfk-spinning" : "" }, "🔄"), "Refresh Feed"), React.createElement("button", {
			type: "button",
			className: "inline-flex items-center gap-1.5 px-4 py-2 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/30 transition-all cursor-pointer " + (isDispatching ? "opacity-75 cursor-not-allowed" : ""),
			disabled: isDispatching,
			onClick: async () => {
				await handleRunDispatcher();
				loadActivities();
			}
		}, isDispatching ? "⏳ Running..." : "⚡ Run Dispatcher"), React.createElement("button", {
			type: "button",
			className: "inline-flex items-center gap-1.5 px-3.5 py-2 rounded-xl text-xs font-bold bg-slate-800/90 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-all cursor-pointer",
			onClick: () => setActiveView("board")
		}, "📋 Kanban Board"))), React.createElement("div", { className: "grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-3.5 pt-2" }, liveAgents.map((agent) => {
			const b = getActorBadge(agent.id);
			const isAgentActive = agent.status === "active";
			const isAgentStuck = agent.status === "stuck";
			const currTask = agent.current_task;
			const sess = agent.session_progress;
			const lastAct = agent.last_activity;
			return React.createElement("div", {
				key: agent.id,
				className: "bg-slate-900/85 backdrop-blur-md border rounded-xl p-4 flex flex-col justify-between gap-3 shadow-md transition-all duration-150 " + (isAgentActive ? "border-emerald-500/50 shadow-emerald-950/30 ring-1 ring-emerald-500/30" : isAgentStuck ? "border-rose-500/50 shadow-rose-950/30 ring-1 ring-rose-500/30" : "border-slate-800 hover:border-slate-700")
			}, React.createElement("div", { className: "flex items-start justify-between gap-2" }, React.createElement("div", { className: "flex items-center gap-2.5 min-w-0" }, React.createElement("div", { className: "w-8 h-8 rounded-lg flex items-center justify-center text-sm shrink-0 " + b.color }, b.icon), React.createElement("div", { className: "min-w-0" }, React.createElement("h4", { className: "text-xs font-bold text-white truncate m-0 font-mono" }, agent.id), React.createElement("p", { className: "text-[11px] text-slate-400 truncate m-0" }, agent.role || b.role))), isAgentActive ? React.createElement("span", { className: "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30 shrink-0" }, React.createElement("span", { className: "w-1.5 h-1.5 rounded-full bg-emerald-400 zfk-pulse-active" }), "Active") : isAgentStuck ? React.createElement("span", { className: "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-500/15 text-rose-400 border border-rose-500/30 shrink-0" }, "⚠️ Stuck") : React.createElement("span", { className: "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-800 text-slate-400 border border-slate-700 shrink-0" }, "⚪ Idle")), React.createElement("div", { className: "space-y-1.5 bg-slate-950/60 rounded-lg p-2.5 border border-slate-800/70 text-xs min-h-[58px] flex flex-col justify-center" }, currTask ? React.createElement("div", { className: "space-y-1" }, React.createElement("div", { className: "flex items-center gap-1.5" }, React.createElement("span", { className: "text-[10px] font-bold uppercase tracking-wider text-amber-400" }, "Running Task:"), React.createElement("span", { className: "text-[10px] font-mono px-1 rounded bg-indigo-900/60 text-indigo-200 border border-indigo-700/50 font-bold" }, currTask.priority || "P2")), React.createElement("button", {
				type: "button",
				className: "text-left text-xs font-semibold text-indigo-300 hover:text-indigo-200 hover:underline truncate block w-full cursor-pointer",
				onClick: () => loadTaskDetails(currTask.id),
				title: currTask.title
			}, `#${currTask.id} ${currTask.title}`), sess && React.createElement("div", { className: "text-[10px] text-slate-400 flex items-center gap-2 pt-0.5" }, React.createElement("span", null, `💬 ${sess.turn_count || 0} turns`), React.createElement("span", null, `🔧 ${sess.tool_calls_count || 0} tools`), currTask.running_seconds > 0 && React.createElement("span", { className: "text-emerald-400 font-medium" }, `${Math.floor(currTask.running_seconds / 60)}m active`))) : lastAct ? React.createElement("div", { className: "space-y-0.5" }, React.createElement("div", { className: "flex items-center justify-between text-[10px] text-slate-400" }, React.createElement("span", { className: "font-semibold uppercase tracking-wider text-slate-300" }, "Latest Activity:"), React.createElement("span", null, timeAgo(lastAct.created_at))), React.createElement("p", {
				className: "text-xs text-slate-300 truncate m-0",
				title: lastAct.details || lastAct.action
			}, lastAct.action.replace("_", " ") + (lastAct.details ? `: ${lastAct.details}` : ""))) : React.createElement("p", { className: "text-xs text-slate-500 m-0 italic" }, "Awaiting task dispatch")), React.createElement("div", { className: "flex items-center justify-between text-[11px] text-slate-400 pt-1 border-t border-slate-800/80" }, React.createElement("span", null, `${agent.actions_today || 0} actions today`), React.createElement("button", {
				type: "button",
				className: "text-indigo-400 hover:text-indigo-300 text-[11px] font-semibold transition-colors cursor-pointer",
				onClick: () => {
					setActivityActorFilter(agent.id);
					setActivityPage(0);
				}
			}, activityActorFilter === agent.id ? "✓ Filtering" : "Filter →")));
		}))), React.createElement("div", { className: "grid grid-cols-2 sm:grid-cols-4 gap-3.5" }, React.createElement("div", { className: "bg-slate-900/70 border border-slate-800/90 rounded-xl p-3.5 flex items-center gap-3.5 shadow-sm" }, React.createElement("div", { className: "w-10 h-10 rounded-xl flex items-center justify-center text-lg shrink-0 bg-indigo-500/15 text-indigo-400" }, "📋"), React.createElement("div", { className: "flex flex-col min-w-0" }, React.createElement("span", { className: "text-xl font-extrabold text-white tracking-tight leading-none" }, effectiveStats.total_activities || effectiveTotal || 0), React.createElement("span", { className: "text-xs text-slate-400 font-medium truncate mt-1" }, "Total Logged Events"))), React.createElement("div", { className: "bg-slate-900/70 border border-slate-800/90 rounded-xl p-3.5 flex items-center gap-3.5 shadow-sm" }, React.createElement("div", { className: "w-10 h-10 rounded-xl flex items-center justify-center text-lg shrink-0 bg-emerald-500/15 text-emerald-400" }, "⚡"), React.createElement("div", { className: "flex flex-col min-w-0" }, React.createElement("span", { className: "text-xl font-extrabold text-white tracking-tight leading-none" }, effectiveStats.active_agents || 0), React.createElement("span", { className: "text-xs text-slate-400 font-medium truncate mt-1" }, "Active Specialists"))), React.createElement("div", { className: "bg-slate-900/70 border border-slate-800/90 rounded-xl p-3.5 flex items-center gap-3.5 shadow-sm" }, React.createElement("div", { className: "w-10 h-10 rounded-xl flex items-center justify-center text-lg shrink-0 bg-purple-500/15 text-purple-400" }, "🕒"), React.createElement("div", { className: "flex flex-col min-w-0" }, React.createElement("span", { className: "text-xl font-extrabold text-white tracking-tight leading-none" }, effectiveStats.actions_today || 0), React.createElement("span", { className: "text-xs text-slate-400 font-medium truncate mt-1" }, "Actions Past 24h"))), React.createElement("div", { className: "bg-slate-900/70 border border-slate-800/90 rounded-xl p-3.5 flex items-center gap-3.5 shadow-sm" }, React.createElement("div", { className: "w-10 h-10 rounded-xl flex items-center justify-center text-lg shrink-0 bg-amber-500/15 text-amber-400" }, "🎯"), React.createElement("div", { className: "flex flex-col min-w-0" }, React.createElement("span", { className: "text-xl font-extrabold text-white tracking-tight leading-none" }, effectiveStats.action_breakdown && effectiveStats.action_breakdown.worker_done || 0), React.createElement("span", { className: "text-xs text-slate-400 font-medium truncate mt-1" }, "Tasks Completed")))), React.createElement("div", { className: "bg-slate-900/80 border border-slate-800 rounded-2xl p-4 shadow-md space-y-3.5" }, React.createElement("div", { className: "flex flex-col lg:flex-row lg:items-center justify-between gap-3" }, React.createElement("div", { className: "flex flex-wrap items-center gap-2.5" }, React.createElement("select", {
			className: "bg-slate-950 border border-slate-700/80 rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer",
			value: activityActorFilter,
			onChange: (e) => {
				setActivityActorFilter(e.target.value);
				setActivityPage(0);
			}
		}, React.createElement("option", { value: "all" }, "🤖 All Agents / Actors"), (effectiveFilterOptions.actors || []).map((act) => React.createElement("option", {
			key: act,
			value: act
		}, `Agent: ${act}`))), React.createElement("select", {
			className: "bg-slate-950 border border-slate-700/80 rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer",
			value: activityActionFilter,
			onChange: (e) => {
				setActivityActionFilter(e.target.value);
				setActivityPage(0);
			}
		}, React.createElement("option", { value: "all" }, "⚡ All Event Types"), (effectiveFilterOptions.actions || []).map((act) => {
			const b = getActionBadge(act);
			return React.createElement("option", {
				key: act,
				value: act
			}, `${b.icon} ${act} (${b.label})`);
		})), React.createElement("select", {
			className: "bg-slate-950 border border-slate-700/80 rounded-lg px-3 py-1.5 text-xs font-semibold text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer",
			value: activityBoardFilter,
			onChange: (e) => {
				setActivityBoardFilter(e.target.value);
				setActivityPage(0);
			}
		}, React.createElement("option", { value: "all" }, "📦 All Boards"), (effectiveFilterOptions.boards || []).map((b) => React.createElement("option", {
			key: b,
			value: b
		}, `Board: ${b}`))), (activityActorFilter !== "all" || activityActionFilter !== "all" || activityBoardFilter !== "all" || activitySearchQuery.trim()) && React.createElement("button", {
			type: "button",
			className: "text-xs font-semibold text-rose-400 hover:text-rose-300 px-2 py-1 rounded hover:bg-rose-950/30 transition-colors cursor-pointer",
			onClick: () => {
				setActivityActorFilter("all");
				setActivityActionFilter("all");
				setActivityBoardFilter("all");
				setActivitySearchQuery("");
				setActivityPage(0);
			}
		}, "✕ Reset Filters")), React.createElement("div", { className: "flex items-center gap-2.5 flex-wrap" }, React.createElement("div", { className: "relative min-w-[240px] flex-1 sm:flex-initial" }, React.createElement("input", {
			type: "text",
			className: "w-full bg-slate-950 border border-slate-700/80 rounded-lg pl-8 pr-7 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500",
			placeholder: "Search details, task ID, title...",
			value: activitySearchQuery,
			onChange: (e) => {
				setActivitySearchQuery(e.target.value);
				setActivityPage(0);
			}
		}), React.createElement("span", { className: "absolute left-2.5 top-1.5 text-slate-500 text-xs" }, "🔍"), activitySearchQuery && React.createElement("button", {
			type: "button",
			className: "absolute right-2.5 top-1.5 text-slate-500 hover:text-slate-300 text-xs cursor-pointer",
			onClick: () => {
				setActivitySearchQuery("");
				setActivityPage(0);
			}
		}, "✕")), React.createElement("div", { className: "flex items-center bg-slate-950 border border-slate-800 rounded-lg p-0.5" }, React.createElement("button", {
			type: "button",
			className: "px-2.5 py-1 rounded text-xs font-semibold transition-all cursor-pointer " + (activityViewMode === "timeline" ? "bg-indigo-600 text-white shadow-xs" : "text-slate-400 hover:text-slate-200"),
			onClick: () => setActivityViewMode("timeline")
		}, "📋 Timeline"), React.createElement("button", {
			type: "button",
			className: "px-2.5 py-1 rounded text-xs font-semibold transition-all cursor-pointer " + (activityViewMode === "agents" ? "bg-indigo-600 text-white shadow-xs" : "text-slate-400 hover:text-slate-200"),
			onClick: () => setActivityViewMode("agents")
		}, "🤖 By Agent")), React.createElement("label", { className: "flex items-center gap-1.5 text-xs text-slate-300 cursor-pointer select-none font-medium ml-1" }, React.createElement("input", {
			type: "checkbox",
			checked: autoRefresh,
			onChange: (e) => setAutoRefresh(e.target.checked),
			className: "rounded border-slate-700 text-indigo-600 focus:ring-0 focus:ring-offset-0 bg-slate-950 cursor-pointer"
		}), React.createElement("span", { className: "text-[11px]" }, "Auto-poll"))))), activityViewMode === "agents" ? React.createElement("div", { className: "grid grid-cols-1 lg:grid-cols-2 gap-4" }, liveAgents.map((agent) => {
			const b = getActorBadge(agent.id);
			const agentActivities = effectiveActivities.filter((act) => act.actor === agent.id || act.task_assignee === agent.id && act.actor === "dispatcher");
			return React.createElement("div", {
				key: agent.id,
				className: "bg-slate-900/80 border border-slate-800 rounded-2xl p-5 space-y-4 shadow-md flex flex-col"
			}, React.createElement("div", { className: "flex items-center justify-between pb-3 border-b border-slate-800" }, React.createElement("div", { className: "flex items-center gap-3" }, React.createElement("div", { className: "w-9 h-9 rounded-xl flex items-center justify-center text-base " + b.color }, b.icon), React.createElement("div", null, React.createElement("h3", { className: "text-sm font-bold text-white m-0 font-mono" }, agent.id), React.createElement("p", { className: "text-xs text-slate-400 m-0" }, agent.role || b.role))), agent.status === "active" ? React.createElement("span", { className: "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-500/15 text-emerald-400 border border-emerald-500/30" }, React.createElement("span", { className: "w-1.5 h-1.5 rounded-full bg-emerald-400 zfk-pulse-active" }), "Executing") : React.createElement("span", { className: "text-xs text-slate-400 font-medium px-2 py-0.5 rounded-full bg-slate-800 border border-slate-700" }, "Idle")), agent.current_task && React.createElement("div", { className: "bg-indigo-950/40 border border-indigo-500/30 rounded-xl p-3 space-y-1.5" }, React.createElement("div", { className: "flex items-center justify-between text-xs" }, React.createElement("span", { className: "font-bold text-indigo-300" }, "⚡ Active Task:"), React.createElement("button", {
				type: "button",
				className: "font-semibold text-indigo-400 hover:text-indigo-200 underline cursor-pointer",
				onClick: () => loadTaskDetails(agent.current_task.id)
			}, `#${agent.current_task.id} ↗`)), React.createElement("p", { className: "text-xs font-medium text-white truncate m-0" }, agent.current_task.title), agent.session_progress && React.createElement("div", { className: "text-[11px] text-indigo-200/80 flex items-center gap-3 pt-1 border-t border-indigo-900/50" }, React.createElement("span", null, `Model: ${agent.session_progress.model || "Hermes"}`), React.createElement("span", null, `Turns: ${agent.session_progress.turn_count || 0}`), React.createElement("span", null, `Tools: ${agent.session_progress.tool_calls_count || 0}`))), React.createElement("div", { className: "space-y-2 flex-1" }, React.createElement("h4", { className: "text-xs font-bold text-slate-400 uppercase tracking-wider m-0" }, "Recent Actions"), agentActivities.length === 0 ? React.createElement("p", { className: "text-xs text-slate-500 italic py-4 text-center m-0" }, "No recent events recorded for this agent") : React.createElement("div", { className: "space-y-2" }, agentActivities.slice(0, 6).map((item) => {
				const actBadge = getActionBadge(item.action);
				return React.createElement("div", {
					key: item.id,
					className: "bg-slate-950/60 border border-slate-800/80 rounded-xl p-3 flex flex-col gap-1.5 hover:border-slate-700 transition-colors"
				}, React.createElement("div", { className: "flex items-center justify-between gap-2" }, React.createElement("div", { className: "flex items-center gap-2" }, React.createElement("span", { className: `inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-[11px] font-bold border ${actBadge.bg}` }, actBadge.icon, actBadge.label), item.task_id && React.createElement("button", {
					type: "button",
					className: "text-xs font-mono font-bold text-indigo-400 hover:text-indigo-300 hover:underline cursor-pointer",
					onClick: () => loadTaskDetails(item.task_id)
				}, `#${item.task_id}`)), React.createElement("span", { className: "text-[11px] text-slate-400" }, timeAgo(item.created_at))), item.task_title && React.createElement("p", { className: "text-xs font-medium text-slate-200 truncate m-0" }, item.task_title), item.details && React.createElement("p", { className: "text-[11px] font-mono text-slate-400 truncate m-0 bg-slate-900/60 px-2 py-1 rounded" }, item.details));
			}))));
		})) : effectiveActivities.length === 0 ? React.createElement("div", { className: "bg-slate-900/60 border border-slate-800 rounded-2xl p-12 text-center space-y-4 shadow-sm" }, React.createElement("div", { className: "w-14 h-14 rounded-2xl bg-indigo-500/10 text-indigo-400 flex items-center justify-center text-2xl mx-auto" }, "🔍"), React.createElement("h3", { className: "text-lg font-bold text-white m-0" }, "No Activities Match Your Filters"), React.createElement("p", { className: "text-xs text-slate-400 max-w-md mx-auto m-0" }, "There are no agent events matching the selected filters. Try broadening your actor, action, or search parameters."), React.createElement("button", {
			type: "button",
			className: "inline-flex items-center gap-2 px-4 py-2 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white shadow-md transition-all cursor-pointer",
			onClick: () => {
				setActivityActorFilter("all");
				setActivityActionFilter("all");
				setActivityBoardFilter("all");
				setActivitySearchQuery("");
				setActivityPage(0);
			}
		}, "Reset All Filters")) : React.createElement("div", { className: "space-y-4" }, React.createElement("div", { className: "relative pl-6 sm:pl-8 border-l-2 border-slate-800/90 space-y-4 ml-3" }, effectiveActivities.map((item) => {
			const actBadge = getActionBadge(item.action);
			const actorBadge = getActorBadge(item.actor);
			const isExpanded = expandedActivityId === item.id;
			const isLongDetails = item.details && item.details.length > 130;
			return React.createElement("div", {
				key: item.id,
				className: "relative group"
			}, React.createElement("div", { className: `absolute -left-[31px] sm:-left-[39px] top-3.5 w-7 h-7 rounded-full flex items-center justify-center text-xs font-bold border-2 bg-slate-950 shadow-md ${actBadge.bg}` }, actBadge.icon), React.createElement("div", { className: "bg-slate-900/80 backdrop-blur-md border border-slate-800/90 hover:border-slate-700 rounded-2xl p-4.5 space-y-3 shadow-sm transition-all duration-150" }, React.createElement("div", { className: "flex flex-wrap items-center justify-between gap-2.5" }, React.createElement("div", { className: "flex flex-wrap items-center gap-2" }, React.createElement("span", { className: `inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-bold border shadow-xs ${actBadge.bg}` }, React.createElement("span", null, actBadge.icon), actBadge.label), React.createElement("span", { className: `inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-mono font-bold border ${actorBadge.color}` }, React.createElement("span", null, actorBadge.icon), actorBadge.label), item.task_id && React.createElement("button", {
				type: "button",
				className: "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-950 hover:bg-slate-800 text-indigo-300 hover:text-indigo-200 border border-slate-700/80 shadow-xs transition-colors cursor-pointer group/task",
				onClick: () => loadTaskDetails(item.task_id),
				title: "Click to open full task details modal"
			}, React.createElement("span", { className: "font-mono font-bold text-indigo-400" }, `#${item.task_id}`), item.task_title && React.createElement("span", { className: "truncate max-w-[200px] sm:max-w-[320px]" }, item.task_title), React.createElement("span", { className: "text-slate-500 group-hover/task:text-slate-300" }, "↗")), item.task_priority && React.createElement("span", { className: "px-2 py-0.5 rounded text-[10px] font-bold font-mono bg-slate-800 text-slate-300 border border-slate-700" }, item.task_priority), item.task_status && React.createElement("span", { className: "px-2 py-0.5 rounded text-[10px] font-semibold uppercase tracking-wider bg-slate-800/60 text-slate-400 border border-slate-700/60" }, item.task_status)), React.createElement("div", { className: "flex items-center gap-2 text-xs text-slate-400 shrink-0" }, item.board_slug && React.createElement("span", { className: "px-2 py-0.5 rounded text-[11px] font-mono bg-slate-950 text-slate-400 border border-slate-800" }, item.board_slug), React.createElement("span", {
				className: "font-medium text-slate-400 hover:text-slate-200 transition-colors",
				title: item.created_at ? (/* @__PURE__ */ new Date(item.created_at * 1e3)).toLocaleString() : ""
			}, timeAgo(item.created_at)))), item.details && React.createElement("div", { className: "space-y-1.5" }, React.createElement("div", { className: "bg-slate-950/80 border border-slate-800/90 rounded-xl p-3 text-xs font-mono text-slate-300 leading-relaxed break-words whitespace-pre-wrap " + (!isExpanded && isLongDetails ? "max-h-20 overflow-hidden relative" : "") }, item.details, !isExpanded && isLongDetails && React.createElement("div", { className: "absolute inset-x-0 bottom-0 h-10 bg-gradient-to-t from-slate-950 to-transparent pointer-events-none" })), isLongDetails && React.createElement("button", {
				type: "button",
				className: "text-xs font-semibold text-indigo-400 hover:text-indigo-300 cursor-pointer pt-0.5",
				onClick: () => setExpandedActivityId(isExpanded ? null : item.id)
			}, isExpanded ? "▲ Collapse details" : "▼ Show full details / trace")), React.createElement("div", { className: "flex items-center justify-between text-xs text-slate-500 pt-1 border-t border-slate-800/60" }, React.createElement("div", { className: "flex items-center gap-3" }, React.createElement("span", { className: "text-[11px] text-slate-500 font-mono" }, `Event #${item.id}`), item.task_assignee && React.createElement("span", { className: "text-[11px] text-slate-400" }, `Assignee: ${item.task_assignee}`)), item.task_id && React.createElement("button", {
				type: "button",
				className: "inline-flex items-center gap-1 text-xs font-semibold text-indigo-400 hover:text-indigo-300 transition-colors cursor-pointer",
				onClick: () => loadTaskDetails(item.task_id)
			}, "Inspect Task Modal ↗"))));
		})), React.createElement("div", { className: "bg-slate-900/80 border border-slate-800 rounded-2xl p-4 flex flex-col sm:flex-row items-center justify-between gap-3 shadow-md" }, React.createElement("div", { className: "text-xs text-slate-400 font-medium" }, `Showing ${startIdx}–${endIdx} of ${effectiveTotal} events`), React.createElement("div", { className: "flex items-center gap-2" }, React.createElement("button", {
			type: "button",
			className: "px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-950 border border-slate-700/80 text-slate-300 hover:text-white hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer",
			disabled: activityPage === 0 || activitiesLoading,
			onClick: () => setActivityPage((p) => Math.max(0, p - 1))
		}, "← Previous"), React.createElement("span", { className: "px-3 py-1 text-xs font-bold font-mono text-indigo-300 bg-indigo-950/60 border border-indigo-700/60 rounded-lg" }, `Page ${activityPage + 1} of ${totalPages}`), React.createElement("button", {
			type: "button",
			className: "px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-950 border border-slate-700/80 text-slate-300 hover:text-white hover:bg-slate-800 disabled:opacity-40 disabled:cursor-not-allowed transition-all cursor-pointer",
			disabled: (activityPage + 1) * activityLimit >= effectiveTotal || activitiesLoading,
			onClick: () => setActivityPage((p) => p + 1)
		}, "Next →")))));
	}
	//#endregion
	//#region dashboard/src/views/SessionsView.jsx
	function SessionsView(props) {
		const { selectedBoard, sessionsList = [], sessionsLoading, sessionsAgentFilter, setSessionsAgentFilter, sessionsStatusFilter, setSessionsStatusFilter, sessionsSearchQuery, setSessionsSearchQuery, stoppingSessionId, handleStopSession, handleStopTaskSession = handleStopSession || (() => {}), loadSessions, tasks = [], agentsSubTab, setAgentsSubTab, boardMemories, memoriesLoading, memoriesTotal, loadBoardMemories, loadMemories = loadBoardMemories || (() => {}), memoryCategoryFilter, setMemoryCategoryFilter, memorySearchQuery, setMemorySearchQuery, showAddMemoryModal, setShowAddMemoryModal, newMemoryForm, setNewMemoryForm, handleCreateMemory, submittingMemory, handleDeleteMemory, setActiveView, selectedSessionIdx, setSelectedSessionIdx, agentsList = [], agentsLoading = false, loadAgents = () => {}, loadTaskDetails = () => {}, boards = [], showToast = () => {}, loadBoards = () => {} } = props;
		const boardFilteredSessions = sessionsList.filter((s) => {
			if (!selectedBoard || selectedBoard === "all") return true;
			if (s.board_slug) return s.board_slug === selectedBoard;
			const cwdOrTitle = (s.cwd || "") + " " + (s.title || "");
			const taskMatch = cwdOrTitle.match(/zf-[a-z0-9_-]+/i) || cwdOrTitle.match(/task-[a-z0-9_-]+/i);
			if (taskMatch) {
				const tid = taskMatch[0].toLowerCase();
				const matchedTask = tasks.find((t) => t.id && t.id.toLowerCase() === tid);
				if (matchedTask) return matchedTask.board_slug === selectedBoard;
			}
			if (s.cwd && (s.cwd.includes(selectedBoard) || s.cwd.includes(selectedBoard.replace(/-/g, "/")))) return true;
			return false;
		});
		const effectiveSessions = boardFilteredSessions.filter((s) => {
			if (sessionsAgentFilter !== "all" && s.agent !== sessionsAgentFilter) return false;
			if (sessionsStatusFilter !== "all" && s.status !== sessionsStatusFilter) return false;
			if (sessionsSearchQuery.trim()) {
				const q = sessionsSearchQuery.toLowerCase();
				const matchTitle = (s.title || "").toLowerCase().includes(q);
				const matchId = (s.session_id || "").toLowerCase().includes(q);
				const matchModel = (s.model || "").toLowerCase().includes(q);
				const matchAgent = (s.agent || "").toLowerCase().includes(q);
				const matchCwd = (s.cwd || "").toLowerCase().includes(q);
				const matchBoard = (s.board_slug || "").toLowerCase().includes(q);
				if (!matchTitle && !matchId && !matchModel && !matchAgent && !matchCwd && !matchBoard) return false;
			}
			return true;
		});
		const filteredMemories = boardMemories.filter((m) => {
			if (memoryCategoryFilter !== "all" && m.category !== memoryCategoryFilter) return false;
			if (memorySearchQuery.trim()) {
				const q = memorySearchQuery.toLowerCase();
				const matchContent = (m.content || "").toLowerCase().includes(q);
				const matchTags = (m.tags || []).some((t) => String(t).toLowerCase().includes(q));
				const matchAuthor = (m.author || "").toLowerCase().includes(q);
				const matchTask = (m.task_id || "").toLowerCase().includes(q);
				if (!matchContent && !matchTags && !matchAuthor && !matchTask) return false;
			}
			return true;
		});
		const totalCount = boardFilteredSessions.length;
		const ongoingCount = boardFilteredSessions.filter((s) => s.status === "ongoing" || s.is_active).length;
		const finishedCount = boardFilteredSessions.filter((s) => s.status === "finished" && !s.is_active).length;
		const totalTurns = boardFilteredSessions.reduce((acc, s) => acc + (s.turn_count || 0), 0);
		const agentTabs = [
			{
				id: "all",
				label: "All Agents",
				count: totalCount
			},
			{
				id: "zf-orchestrator",
				label: "🧭 Orchestrator",
				count: boardFilteredSessions.filter((s) => s.agent === "zf-orchestrator").length
			},
			{
				id: "zf-builder",
				label: "🔨 Builder",
				count: boardFilteredSessions.filter((s) => s.agent === "zf-builder").length
			},
			{
				id: "zf-reviewer",
				label: "🔍 Reviewer",
				count: boardFilteredSessions.filter((s) => s.agent === "zf-reviewer").length
			}
		];
		const memoryCategories = [
			{
				id: "all",
				label: "All",
				icon: "📚",
				count: boardMemories.length
			},
			{
				id: "convention",
				label: "Convention",
				icon: "📐",
				count: boardMemories.filter((m) => m.category === "convention").length
			},
			{
				id: "gotcha",
				label: "Gotcha",
				icon: "⚠️",
				count: boardMemories.filter((m) => m.category === "gotcha").length
			},
			{
				id: "decision",
				label: "Decision",
				icon: "💡",
				count: boardMemories.filter((m) => m.category === "decision").length
			},
			{
				id: "rejected_path",
				label: "Rejected Path",
				icon: "🚫",
				count: boardMemories.filter((m) => m.category === "rejected_path").length
			},
			{
				id: "general",
				label: "General",
				icon: "📝",
				count: boardMemories.filter((m) => m.category === "general").length
			}
		];
		return React.createElement("div", { className: "space-y-6 animate-fade-in" }, React.createElement("div", { className: "flex flex-wrap items-center justify-between gap-4 bg-slate-900/60 backdrop-blur-md border border-slate-800/80 p-5 rounded-2xl shadow-sm" }, React.createElement("div", { className: "flex items-center gap-3" }, React.createElement("div", { className: "w-11 h-11 rounded-xl bg-indigo-500/15 border border-indigo-500/30 flex items-center justify-center text-2xl shadow-xs" }, "🤖"), React.createElement("div", null, React.createElement("h2", { className: "text-base font-bold text-white tracking-tight flex items-center gap-2" }, "Specialist Agents & Memory", ongoingCount > 0 && React.createElement("span", { className: "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-full text-[11px] font-medium bg-emerald-500/15 text-emerald-300 border border-emerald-500/30" }, React.createElement("span", { className: "w-1.5 h-1.5 rounded-full bg-emerald-400 zfk-pulse-active" }), ongoingCount + " Active")), React.createElement("p", { className: "text-xs text-slate-400 mt-0.5" }, "Live status of 3 specialist agents, session telemetry, and persistent repository memory."))), React.createElement("div", { className: "flex items-center gap-2" }, React.createElement("button", {
			type: "button",
			className: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800/90 hover:bg-slate-700 text-slate-200 border border-slate-700 hover:border-slate-600 shadow-sm transition-all cursor-pointer",
			onClick: () => {
				loadSessions(selectedBoard);
				loadAgents(selectedBoard);
				loadMemories(selectedBoard);
			},
			disabled: sessionsLoading || agentsLoading || memoriesLoading
		}, sessionsLoading || agentsLoading || memoriesLoading ? React.createElement("span", { className: "zfk-spinning" }, "⏳") : "🔄", " Refresh"))), React.createElement("div", { className: "grid grid-cols-1 md:grid-cols-3 gap-4" }, [
			{
				id: "zf-orchestrator",
				label: "Orchestrator",
				icon: "🧭",
				role: "Planning, Triage & Improvement Scans"
			},
			{
				id: "zf-builder",
				label: "Builder",
				icon: "🔨",
				role: "Implementation, Bug Fixing & Pull Requests"
			},
			{
				id: "zf-reviewer",
				label: "Reviewer",
				icon: "🔍",
				role: "Code Review, Testing & Quality Verification"
			}
		].map((meta) => {
			const agentInfo = agentsList.find((a) => a.name === meta.id) || {};
			const agentSessions = boardFilteredSessions.filter((s) => s.agent === meta.id);
			const isAgentActive = agentInfo.is_active || agentInfo.status === "active" || agentSessions.some((s) => s.status === "ongoing" || s.is_active);
			const currentTask = agentInfo.current_task;
			const activeSession = agentInfo.active_session || agentSessions.find((s) => s.status === "ongoing" || s.is_active);
			const totalAgentTurns = agentSessions.reduce((acc, s) => acc + (s.turn_count || 0), 0);
			return React.createElement("div", {
				key: meta.id,
				className: "bg-slate-900/70 backdrop-blur-md border border-slate-800/90 hover:border-slate-700/80 rounded-2xl p-4.5 transition-all shadow-sm flex flex-col justify-between space-y-4"
			}, React.createElement("div", { className: "space-y-3" }, React.createElement("div", { className: "flex items-center justify-between gap-2" }, React.createElement("div", { className: "flex items-center gap-2.5" }, React.createElement("div", { className: "w-9 h-9 rounded-xl flex items-center justify-center text-xl bg-slate-800/90 border border-slate-700/60 shadow-xs" }, meta.icon), React.createElement("div", null, React.createElement("h3", { className: "text-sm font-bold text-white tracking-tight leading-none" }, meta.label), React.createElement("span", { className: "text-[10px] text-slate-500 font-mono" }, meta.id))), React.createElement("div", { className: "flex items-center gap-1.5" }, React.createElement("span", { className: "inline-flex items-center gap-1.5 px-2.5 py-0.5 rounded-full text-[11px] font-semibold border " + (isAgentActive ? "bg-emerald-500/15 text-emerald-300 border-emerald-500/30" : "bg-slate-800/80 text-slate-400 border-slate-700/60") }, React.createElement("span", { className: "w-1.5 h-1.5 rounded-full " + (isAgentActive ? "bg-emerald-400 zfk-pulse-active" : "bg-slate-500") }), isAgentActive ? "Active" : "Idle"), isAgentActive && (currentTask || activeSession) && React.createElement("button", {
				type: "button",
				disabled: stoppingSessionId === (activeSession && activeSession.session_id || currentTask && currentTask.id),
				className: "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-rose-950/70 hover:bg-rose-900 text-rose-300 border border-rose-800/80 hover:border-rose-800/60 transition-colors shadow-xs cursor-pointer disabled:opacity-50",
				title: "Stop running AI session for this agent",
				onClick: (e) => {
					e.stopPropagation();
					handleStopTaskSession(currentTask && currentTask.id, activeSession && activeSession.session_id);
				}
			}, React.createElement("span", { className: "text-[9px]" }, "⏹"), React.createElement("span", null, stoppingSessionId === (activeSession && activeSession.session_id || currentTask && currentTask.id) ? "Stopping..." : "Stop")))), React.createElement("p", { className: "text-xs text-slate-400 leading-relaxed" }, meta.role), React.createElement("div", { className: "bg-slate-950/60 p-3 rounded-xl border border-slate-800/80 space-y-1.5" }, React.createElement("div", { className: "text-[10px] font-semibold text-slate-400 uppercase tracking-wider flex items-center justify-between" }, React.createElement("span", null, isAgentActive ? "Current Work" : "Status"), isAgentActive && React.createElement("span", { className: "text-emerald-400 font-mono text-[10px]" }, "Executing")), currentTask ? React.createElement("button", {
				type: "button",
				className: "text-left text-xs font-semibold text-indigo-300 hover:text-indigo-200 transition-colors line-clamp-1 cursor-pointer",
				onClick: () => {
					setActiveView("board");
					loadTaskDetails(currentTask.id);
				}
			}, "📋 " + currentTask.title + " ↗") : activeSession ? React.createElement("div", {
				className: "text-xs text-slate-300 truncate",
				title: activeSession.last_action || activeSession.title
			}, "⚡ " + (activeSession.last_action || activeSession.title || "Working on session...")) : React.createElement("div", { className: "text-xs text-slate-500 italic" }, "Ready for next dispatch cycle"))), React.createElement("div", { className: "grid grid-cols-3 gap-2 pt-2 border-t border-slate-800/80 text-center" }, React.createElement("div", null, React.createElement("span", { className: "text-[10px] text-slate-500 uppercase tracking-wider block" }, "Sessions"), React.createElement("span", { className: "text-xs font-bold text-slate-200" }, agentSessions.length)), React.createElement("div", null, React.createElement("span", { className: "text-[10px] text-slate-500 uppercase tracking-wider block" }, "Turns"), React.createElement("span", { className: "text-xs font-bold text-amber-300" }, totalAgentTurns)), React.createElement("div", null, React.createElement("span", { className: "text-[10px] text-slate-500 uppercase tracking-wider block" }, "State"), React.createElement("span", { className: "text-xs font-bold " + (isAgentActive ? "text-emerald-400" : "text-slate-400") }, isAgentActive ? "Busy" : "Ready"))));
		})), React.createElement("div", { className: "flex items-center gap-2 border-b border-slate-800 pb-3" }, React.createElement("button", {
			type: "button",
			className: "px-4 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center gap-2 " + (agentsSubTab === "sessions" ? "bg-indigo-600 text-white shadow-sm shadow-indigo-600/30" : "bg-slate-900/60 text-slate-400 hover:text-slate-200 hover:bg-slate-800 border border-slate-800/80"),
			onClick: () => {
				setAgentsSubTab("sessions");
				loadSessions(selectedBoard);
			}
		}, "💬 AI Sessions", React.createElement("span", { className: "px-2 py-0.5 rounded-full text-[10px] " + (agentsSubTab === "sessions" ? "bg-indigo-700 text-indigo-100" : "bg-slate-800 text-slate-400") }, boardFilteredSessions.length)), React.createElement("button", {
			type: "button",
			className: "px-4 py-2 rounded-xl text-xs font-semibold transition-all cursor-pointer flex items-center gap-2 " + (agentsSubTab === "memory" ? "bg-indigo-600 text-white shadow-sm shadow-indigo-600/30" : "bg-slate-900/60 text-slate-400 hover:text-slate-200 hover:bg-slate-800 border border-slate-800/80"),
			onClick: () => {
				setAgentsSubTab("memory");
				loadMemories(selectedBoard);
			}
		}, "🧠 Repository Memory", React.createElement("span", { className: "px-2 py-0.5 rounded-full text-[10px] " + (agentsSubTab === "memory" ? "bg-indigo-700 text-indigo-100" : "bg-slate-800 text-slate-400") }, boardMemories.length))), agentsSubTab === "sessions" ? React.createElement("div", { className: "space-y-6" }, React.createElement("div", { className: "grid grid-cols-2 sm:grid-cols-4 gap-3.5" }, React.createElement("div", { className: "bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-xl p-3.5 flex items-center gap-3 shadow-sm" }, React.createElement("div", { className: "w-10 h-10 rounded-lg flex items-center justify-center text-lg shrink-0 bg-indigo-500/15 text-indigo-400 border border-indigo-500/25" }, "🤖"), React.createElement("div", { className: "min-w-0" }, React.createElement("span", { className: "text-xl font-bold text-white tracking-tight leading-none block" }, totalCount), React.createElement("span", { className: "text-[11px] text-slate-400 font-medium truncate mt-1 block" }, "Total AI Sessions"))), React.createElement("div", { className: "bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-xl p-3.5 flex items-center gap-3 shadow-sm" }, React.createElement("div", { className: "w-10 h-10 rounded-lg flex items-center justify-center text-lg shrink-0 bg-emerald-500/15 text-emerald-400 border border-emerald-500/25" }, "⚡"), React.createElement("div", { className: "min-w-0" }, React.createElement("span", { className: "text-xl font-bold text-emerald-400 tracking-tight leading-none block" }, ongoingCount), React.createElement("span", { className: "text-[11px] text-slate-400 font-medium truncate mt-1 block" }, "Ongoing / Active"))), React.createElement("div", { className: "bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-xl p-3.5 flex items-center gap-3 shadow-sm" }, React.createElement("div", { className: "w-10 h-10 rounded-lg flex items-center justify-center text-lg shrink-0 bg-slate-800/60 text-slate-300 border border-slate-700/50" }, "✅"), React.createElement("div", { className: "min-w-0" }, React.createElement("span", { className: "text-xl font-bold text-white tracking-tight leading-none block" }, finishedCount), React.createElement("span", { className: "text-[11px] text-slate-400 font-medium truncate mt-1 block" }, "Completed Sessions"))), React.createElement("div", { className: "bg-slate-900/60 backdrop-blur-md border border-slate-800/80 rounded-xl p-3.5 flex items-center gap-3 shadow-sm" }, React.createElement("div", { className: "w-10 h-10 rounded-lg flex items-center justify-center text-lg shrink-0 bg-amber-500/15 text-amber-400 border border-amber-500/25" }, "🔄"), React.createElement("div", { className: "min-w-0" }, React.createElement("span", { className: "text-xl font-bold text-amber-300 tracking-tight leading-none block" }, totalTurns), React.createElement("span", { className: "text-[11px] text-slate-400 font-medium truncate mt-1 block" }, "Total Agent Turns")))), React.createElement("div", { className: "flex flex-col md:flex-row md:items-center justify-between gap-3 bg-slate-900/40 p-3 rounded-xl border border-slate-800/80" }, React.createElement("div", { className: "flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0 zfk-scrollbar" }, agentTabs.map((tab) => React.createElement("button", {
			key: tab.id,
			type: "button",
			className: "px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 " + (sessionsAgentFilter === tab.id ? "bg-indigo-600 text-white shadow-xs" : "bg-slate-800/60 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-700/60"),
			onClick: () => setSessionsAgentFilter(tab.id)
		}, tab.label, React.createElement("span", { className: "text-[0.625rem] px-1.5 py-0.2 rounded-full " + (sessionsAgentFilter === tab.id ? "bg-indigo-700 text-indigo-100" : "bg-slate-700 text-slate-400") }, tab.count)))), React.createElement("div", { className: "flex items-center gap-2" }, React.createElement("select", {
			className: "bg-slate-800 border border-slate-700 rounded-lg px-2.5 py-1.5 text-xs text-slate-300 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer",
			value: sessionsStatusFilter,
			onChange: (e) => setSessionsStatusFilter(e.target.value)
		}, React.createElement("option", { value: "all" }, "All Statuses"), React.createElement("option", { value: "ongoing" }, "🟢 Ongoing"), React.createElement("option", { value: "finished" }, "⚪ Finished")), React.createElement("input", {
			type: "text",
			placeholder: "Search sessions, models, tasks...",
			className: "bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 w-48 md:w-56",
			value: sessionsSearchQuery,
			onChange: (e) => setSessionsSearchQuery(e.target.value)
		}))), effectiveSessions.length === 0 ? React.createElement("div", { className: "bg-slate-900/30 border border-dashed border-slate-800 rounded-2xl p-12 text-center" }, React.createElement("div", { className: "w-12 h-12 rounded-full bg-slate-800/80 flex items-center justify-center text-2xl mx-auto mb-3 text-slate-500" }, "🤖"), React.createElement("h3", { className: "text-sm font-semibold text-slate-300" }, "No AI Sessions Found"), React.createElement("p", { className: "text-xs text-slate-500 mt-1 max-w-sm mx-auto" }, sessionsSearchQuery || sessionsAgentFilter !== "all" || sessionsStatusFilter !== "all" ? "No sessions match your filter criteria. Try resetting the filters." : selectedBoard && selectedBoard !== "all" ? "No AI agent sessions recorded yet for board '" + selectedBoard + "'. Sessions will appear as tasks run on this board." : "AI agent sessions will appear here as Orchestrator, Builder, and Reviewer execute tasks.")) : React.createElement("div", { className: "grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4" }, effectiveSessions.map((s) => {
			const isOngoing = s.status === "ongoing" || s.is_active;
			const agentRole = s.agent || "zf-builder";
			const agentBadge = agentRole === "zf-reviewer" ? {
				icon: "🔍",
				label: "Reviewer",
				border: "border-cyan-500/30",
				bg: "bg-cyan-500/10 text-cyan-300"
			} : agentRole === "zf-orchestrator" ? {
				icon: "🧭",
				label: "Orchestrator",
				border: "border-indigo-500/30",
				bg: "bg-indigo-500/10 text-indigo-300"
			} : {
				icon: "🔨",
				label: "Builder",
				border: "border-amber-500/30",
				bg: "bg-amber-500/10 text-amber-300"
			};
			const lastUpdateTs = s.last_activity_at || s.ended_at || s.started_at;
			const lastUpdateStr = lastUpdateTs ? timeAgo(lastUpdateTs) : null;
			const lastUpdateFull = lastUpdateTs ? (/* @__PURE__ */ new Date(lastUpdateTs * 1e3)).toLocaleString() : null;
			let matchedTaskId = s.task_id || null;
			let matchedBoardSlug = s.board_slug || null;
			if (!matchedTaskId) {
				const cwdOrTitle = (s.cwd || "") + " " + (s.title || "");
				const taskMatch = cwdOrTitle.match(/zf-[a-z0-9_-]+/i) || cwdOrTitle.match(/task-[a-z0-9_-]+/i);
				if (taskMatch) matchedTaskId = taskMatch[0];
			}
			if (!matchedBoardSlug && matchedTaskId) {
				const matchedTask = tasks.find((t) => t.id && t.id.toLowerCase() === matchedTaskId.toLowerCase());
				if (matchedTask && matchedTask.board_slug) matchedBoardSlug = matchedTask.board_slug;
			}
			const chatUrl = (typeof window !== "undefined" && window.__HERMES_BASE_PATH__ ? "/" + String(window.__HERMES_BASE_PATH__).replace(/^\/|\/$/g, "") : "") + "/chat?resume=" + encodeURIComponent(s.session_id) + (s.agent ? "&profile=" + encodeURIComponent(s.agent) : "");
			return React.createElement("div", {
				key: s.session_id,
				className: "bg-slate-900/70 backdrop-blur-md border border-slate-800/90 hover:border-slate-700/80 rounded-xl p-4 transition-all duration-150 shadow-sm space-y-3 flex flex-col justify-between"
			}, React.createElement("div", { className: "space-y-2.5" }, React.createElement("div", { className: "flex items-center justify-between gap-2" }, React.createElement("div", { className: "flex items-center gap-2" }, React.createElement("span", { className: "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-semibold border " + agentBadge.bg + " " + agentBadge.border }, agentBadge.icon + " " + (s.agent_label || agentBadge.label)), React.createElement("span", { className: "inline-flex items-center gap-1 text-[11px] font-medium " + (isOngoing ? "text-emerald-400" : "text-slate-400") }, React.createElement("span", { className: "w-2 h-2 rounded-full " + (isOngoing ? "bg-emerald-400 zfk-pulse-active" : "bg-slate-500") }), isOngoing ? "Ongoing" : "Finished"), isOngoing && React.createElement("button", {
				type: "button",
				disabled: stoppingSessionId === (s.session_id || matchedTaskId),
				className: "inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-rose-950/70 hover:bg-rose-900 text-rose-300 border border-rose-800/80 hover:border-rose-800/60 transition-colors shadow-xs cursor-pointer disabled:opacity-50",
				title: "Kill / Stop running AI session",
				onClick: (e) => {
					e.stopPropagation();
					handleStopTaskSession(matchedTaskId, s.session_id);
				}
			}, React.createElement("span", { className: "text-[9px]" }, "⏹"), React.createElement("span", null, stoppingSessionId === (s.session_id || matchedTaskId) ? "Stopping..." : "Stop"))), React.createElement("div", {
				className: "flex flex-col shrink-0",
				style: {
					alignItems: "flex-end",
					textAlign: "right"
				}
			}, lastUpdateStr ? React.createElement("span", {
				className: "text-[11px] text-slate-300 font-mono flex items-center gap-1",
				title: lastUpdateFull ? "Last updated: " + lastUpdateFull : void 0
			}, React.createElement("span", { className: "text-slate-500 text-[10px]" }, "Updated"), lastUpdateStr) : React.createElement("span", { className: "text-[11px] text-slate-400 font-mono" }, "No activity"), s.duration_seconds != null && s.duration_seconds > 0 ? React.createElement("span", { className: "text-[10px] text-slate-500 font-mono" }, `${Math.floor(s.duration_seconds / 60)}m ${s.duration_seconds % 60}s duration`) : null)), React.createElement("div", { className: "space-y-1" }, React.createElement("div", {
				className: "text-xs font-semibold text-white line-clamp-1",
				title: s.title
			}, s.title || "Autonomous Agent Execution"), React.createElement("div", { className: "flex flex-wrap items-center gap-2 pt-0.5" }, matchedTaskId && React.createElement("button", {
				type: "button",
				className: "inline-flex items-center gap-1 text-[11px] font-mono text-indigo-400 hover:text-indigo-300 hover:underline cursor-pointer",
				onClick: () => {
					setActiveView("board");
					loadTaskDetails(matchedTaskId);
				}
			}, "📋 Task " + matchedTaskId + " ↗"), selectedBoard === "all" && matchedBoardSlug && React.createElement("span", {
				className: "inline-flex items-center gap-1 text-sky-400 font-mono text-[10px] bg-sky-950/50 border border-sky-800/50 px-1.5 py-0.5 rounded truncate max-w-[150px]",
				title: "Board: " + matchedBoardSlug
			}, "🏷️ " + matchedBoardSlug))), React.createElement("div", { className: "grid grid-cols-3 gap-2 bg-slate-950/60 p-2 rounded-lg border border-slate-800/80 text-center" }, React.createElement("div", null, React.createElement("span", { className: "text-[10px] text-slate-500 uppercase tracking-wider block" }, "Turns"), React.createElement("span", { className: "text-xs font-bold text-slate-200" }, s.turn_count || 0)), React.createElement("div", null, React.createElement("span", { className: "text-[10px] text-slate-500 uppercase tracking-wider block" }, "Tool Calls"), React.createElement("span", { className: "text-xs font-bold text-indigo-300" }, s.tool_calls_count || 0)), React.createElement("div", null, React.createElement("span", { className: "text-[10px] text-slate-500 uppercase tracking-wider block" }, "Messages"), React.createElement("span", { className: "text-xs font-bold text-slate-200" }, s.message_count || 0))), s.last_action && React.createElement("div", {
				className: "text-[11px] text-slate-400 bg-slate-950/40 px-2.5 py-1.5 rounded-lg border border-slate-800/60 font-mono truncate",
				title: s.last_action
			}, "⚡ " + s.last_action)), React.createElement("div", { className: "pt-2 border-t border-slate-800/80 flex items-center justify-between gap-2" }, React.createElement("div", { className: "flex items-center gap-1.5 min-w-0" }, React.createElement("span", {
				className: "text-xs font-mono font-medium text-purple-300 truncate max-w-[160px]",
				title: "Session ID: " + s.session_id
			}, s.session_id), lastUpdateStr && React.createElement("span", {
				className: "text-[10px] text-slate-500 font-mono shrink-0 flex items-center gap-1",
				title: lastUpdateFull ? "Last updated: " + lastUpdateFull : void 0
			}, "• updated " + lastUpdateStr)), React.createElement("a", {
				href: chatUrl,
				target: "_blank",
				rel: "noreferrer",
				className: "inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium bg-indigo-600/90 hover:bg-indigo-600 text-white transition-colors cursor-pointer shadow-xs shrink-0"
			}, "Open Chat ↗")));
		}))) : React.createElement("div", { className: "space-y-6" }, React.createElement("div", { className: "flex flex-col md:flex-row md:items-center justify-between gap-3 bg-slate-900/40 p-3 rounded-xl border border-slate-800/80" }, React.createElement("div", { className: "flex items-center gap-1.5 overflow-x-auto pb-1 md:pb-0 zfk-scrollbar" }, memoryCategories.map((cat) => React.createElement("button", {
			key: cat.id,
			type: "button",
			className: "px-3 py-1.5 rounded-lg text-xs font-medium transition-all cursor-pointer whitespace-nowrap flex items-center gap-1.5 " + (memoryCategoryFilter === cat.id ? "bg-indigo-600 text-white shadow-xs" : "bg-slate-800/60 hover:bg-slate-800 text-slate-400 hover:text-slate-200 border border-slate-700/60"),
			onClick: () => setMemoryCategoryFilter(cat.id)
		}, cat.icon + " " + cat.label, React.createElement("span", { className: "text-[0.625rem] px-1.5 py-0.2 rounded-full " + (memoryCategoryFilter === cat.id ? "bg-indigo-700 text-indigo-100" : "bg-slate-700 text-slate-400") }, cat.count)))), (() => {
			const currentBoard = boards.find((b) => b.slug === selectedBoard);
			const isAutoRecordOn = currentBoard ? currentBoard.auto_record_memory !== false : true;
			return React.createElement("div", { className: "flex flex-wrap items-center gap-2" }, currentBoard && React.createElement("button", {
				type: "button",
				className: "inline-flex items-center gap-1.5 px-2.5 py-1.5 rounded-lg text-xs font-medium border transition-all cursor-pointer shrink-0 " + (isAutoRecordOn ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-300 hover:text-white hover:bg-slate-800/80 shadow-xs" : "bg-slate-800/80 border-slate-700 text-slate-400 hover:text-slate-200 hover:bg-slate-800"),
				title: "Click to toggle automatic memory recording from reviewer feedback for " + currentBoard.slug,
				onClick: async () => {
					const nextVal = !isAutoRecordOn;
					try {
						await fetchJSON("/api/plugins/zerofactory/boards/" + encodeURIComponent(currentBoard.slug), {
							method: "PATCH",
							headers: { "Content-Type": "application/json" },
							body: JSON.stringify({ auto_record_memory: nextVal })
						});
						showToast(`Auto-record memory ${nextVal ? "enabled" : "disabled"} for ${currentBoard.slug}`, "success");
						await loadBoards();
					} catch (err) {
						showToast("Failed to toggle auto-record: " + (err.message || String(err)), "error");
					}
				}
			}, React.createElement("span", { className: "w-2 h-2 rounded-full " + (isAutoRecordOn ? "bg-emerald-400 zfk-pulse-active" : "bg-slate-500") }), "Auto-Record: " + (isAutoRecordOn ? "ON" : "OFF")), React.createElement("input", {
				type: "text",
				placeholder: "Search memories, tags, author...",
				className: "bg-slate-800 border border-slate-700 rounded-lg px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 w-44 md:w-56",
				value: memorySearchQuery,
				onChange: (e) => setMemorySearchQuery(e.target.value)
			}), React.createElement("button", {
				type: "button",
				className: "inline-flex items-center gap-1 px-3 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-xs shadow-indigo-600/30 transition-all cursor-pointer shrink-0",
				onClick: () => setShowAddMemoryModal(true)
			}, "➕ Add Memory"));
		})()), filteredMemories.length === 0 ? React.createElement("div", { className: "bg-slate-900/30 border border-dashed border-slate-800 rounded-2xl p-12 text-center" }, React.createElement("div", { className: "w-12 h-12 rounded-full bg-slate-800/80 flex items-center justify-center text-2xl mx-auto mb-3 text-slate-500" }, "🧠"), React.createElement("h3", { className: "text-sm font-semibold text-slate-300" }, "No Repository Memories Found"), React.createElement("p", { className: "text-xs text-slate-500 mt-1 max-w-md mx-auto" }, memorySearchQuery || memoryCategoryFilter !== "all" ? "No memories match your filter criteria. Try resetting the category or search." : "Repository memories persist architectural decisions, conventions, gotchas, and rejected paths for " + (selectedBoard || "this board") + " so future agent workers avoid repeat mistakes."), React.createElement("button", {
			type: "button",
			className: "mt-4 inline-flex items-center gap-1.5 px-3.5 py-1.5 rounded-lg text-xs font-semibold bg-indigo-600 hover:bg-indigo-500 text-white shadow-xs transition-all cursor-pointer",
			onClick: () => setShowAddMemoryModal(true)
		}, "➕ Record First Memory")) : React.createElement("div", { className: "grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4" }, filteredMemories.map((m) => {
			const catBadges = {
				decision: {
					icon: "💡",
					label: "Decision",
					bg: "bg-emerald-500/10 text-emerald-300 border-emerald-500/30"
				},
				gotcha: {
					icon: "⚠️",
					label: "Gotcha",
					bg: "bg-amber-500/10 text-amber-300 border-amber-500/30"
				},
				convention: {
					icon: "📐",
					label: "Convention",
					bg: "bg-sky-500/10 text-sky-300 border-sky-500/30"
				},
				rejected_path: {
					icon: "🚫",
					label: "Rejected Path",
					bg: "bg-purple-500/10 text-purple-300 border-purple-500/30"
				},
				general: {
					icon: "📝",
					label: "General",
					bg: "bg-slate-700/40 text-slate-300 border-slate-600/50"
				}
			};
			const badge = catBadges[m.category] || catBadges.general;
			return React.createElement("div", {
				key: m.id,
				className: "bg-slate-900/70 backdrop-blur-md border border-slate-800/90 hover:border-slate-700/80 rounded-xl p-4 transition-all duration-150 shadow-sm flex flex-col justify-between space-y-3"
			}, React.createElement("div", { className: "space-y-2.5" }, React.createElement("div", { className: "flex items-center justify-between gap-2" }, React.createElement("span", { className: "inline-flex items-center gap-1.5 px-2 py-0.5 rounded-md text-xs font-semibold border " + badge.bg }, badge.icon + " " + badge.label), React.createElement("div", { className: "flex items-center gap-2" }, React.createElement("span", { className: "text-[11px] text-slate-500 font-mono" }, timeAgo(m.created_at)), React.createElement("button", {
				type: "button",
				title: "Delete Memory",
				className: "text-slate-500 hover:text-rose-300 p-1 rounded-md hover:bg-rose-500/20 transition-colors text-xs cursor-pointer",
				onClick: () => handleDeleteMemory(m.id)
			}, "🗑️"))), React.createElement("div", { className: "text-xs text-slate-200 leading-relaxed whitespace-pre-wrap select-text font-normal" }, m.content)), React.createElement("div", { className: "pt-2.5 border-t border-slate-800/80 flex flex-wrap items-center justify-between gap-2" }, React.createElement("div", { className: "flex flex-wrap items-center gap-1.5" }, selectedBoard === "all" && m.board_slug && React.createElement("span", { className: "inline-flex items-center gap-1 text-[10px] text-sky-400 font-mono bg-sky-950/60 px-2 py-0.5 rounded-md border border-sky-800/60" }, "📋 " + m.board_slug), React.createElement("span", { className: "inline-flex items-center gap-1 text-[10px] text-slate-400 font-mono bg-slate-950/60 px-2 py-0.5 rounded-md border border-slate-800" }, "👤 " + (m.author || "user")), (m.tags || []).map((t, idx) => React.createElement("span", {
				key: idx,
				className: "text-[10px] font-mono px-1.5 py-0.5 rounded-md bg-indigo-500/10 text-indigo-300 border border-indigo-500/20"
			}, "#" + t))), m.task_id && React.createElement("button", {
				type: "button",
				className: "inline-flex items-center gap-1 text-[11px] font-mono text-indigo-400 hover:text-indigo-300 hover:underline cursor-pointer",
				onClick: () => {
					setActiveView("board");
					loadTaskDetails(m.task_id);
				}
			}, "📋 " + m.task_id + " ↗")));
		}))));
	}
	//#endregion
	//#region dashboard/src/views/InstructionsView.jsx
	function InstructionsView({ instructionTab, setInstructionTab, setActiveView }) {
		const renderOverviewSection = () => {
			return React.createElement("div", { className: "space-y-6" }, React.createElement("div", { className: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-5 gap-4" }, [
				{
					icon: "🏭",
					title: "24/7 Autonomous Factory",
					desc: "Continuous agile iterations with rolling handoffs and parallel worker execution across multiple tasks."
				},
				{
					icon: "🌳",
					title: "Isolated Git Worktrees",
					desc: "Every task executes in its own dedicated Git worktree (~/git/<repo>-worktrees/<task_id>). Main is never touched directly."
				},
				{
					icon: "🔍",
					title: "Thematic Code Review",
					desc: "Layered code review (Correctness ➔ Performance ➔ Clean Code / Ponytail), capped at up to 3 rounds before human merge."
				},
				{
					icon: "⚡",
					title: "Zero-Token Idle Watchdogs",
					desc: "Hermes No-Agent Mode and Wake-Gate suppress LLM queries when repositories are idle, saving up to 95% token usage."
				},
				{
					icon: "🧠",
					title: "Native Repository Memory",
					desc: "Durable SQLite knowledge substrate (kanban.db) persisting conventions, gotchas, and architectural decisions."
				}
			].map((card, idx) => React.createElement("div", {
				key: idx,
				className: "bg-slate-900/80 border border-slate-700/80 rounded-xl p-5 space-y-2 hover:border-slate-600 transition-colors shadow-sm"
			}, React.createElement("div", { className: "text-2xl mb-1" }, card.icon), React.createElement("h3", { className: "text-sm font-bold text-white m-0 tracking-wide" }, card.title), React.createElement("p", { className: "text-xs text-slate-200 leading-relaxed m-0 font-normal" }, card.desc)))), React.createElement("div", { className: "bg-slate-900/70 border border-slate-700/80 rounded-2xl p-6 space-y-6 shadow-md" }, React.createElement("div", { className: "flex items-center justify-between flex-wrap gap-2 pb-3 border-b border-slate-800" }, React.createElement("h3", { className: "text-sm font-bold uppercase tracking-wider text-indigo-300 m-0 flex items-center gap-2" }, "🏗️ High-Level Architecture & Workflow"), React.createElement("span", { className: "text-xs font-mono text-indigo-100 bg-indigo-900/80 px-3 py-1 rounded-md border border-indigo-500/70 font-semibold shadow-xs" }, "5 Kanban States • 3 Specialist Agents • HITL Merge Gate")), React.createElement("div", { className: "space-y-3" }, React.createElement("div", { className: "text-xs font-bold text-slate-200 uppercase tracking-wider" }, "Kanban Column States & Roles"), React.createElement("div", { className: "grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2.5 text-xs" }, [
				{
					step: "1. Triage",
					color: "bg-indigo-950/90 border-indigo-500/70 text-indigo-100",
					role: "Intake & Epics",
					actor: "User / Operator",
					desc: "Raw user goals and high-level feature epics. Ignored by dispatcher until decomposed into Todo."
				},
				{
					step: "2. Todo",
					color: "bg-sky-950/90 border-sky-500/70 text-sky-100",
					role: "Actionable Queue",
					actor: "Queue",
					desc: "Prioritized, actionable tasks ready for autonomous execution. Isolated Git worktree provisioned on pickup."
				},
				{
					step: "3. Running",
					color: "bg-emerald-950/90 border-emerald-500/70 text-emerald-100",
					role: "Autonomous AI",
					actor: "zf-builder / reviewer",
					desc: "Subprocess actively executing. zf-builder coding or zf-reviewer evaluating PR across continuous review rounds."
				},
				{
					step: "4. Blocked",
					color: "bg-purple-950/90 border-purple-500/70 text-purple-100",
					role: "Human Action (HITL)",
					actor: "Human Operator",
					desc: "Action required: PR approved waiting for human merge, crashed worker retry, or merge conflict resolution."
				},
				{
					step: "5. Done",
					color: "bg-slate-900 border-emerald-500/70 text-emerald-200",
					role: "PR Merged & Pruned",
					actor: "System (Closed)",
					desc: "PR merged on GitHub. Worktree pruned and metrics recorded."
				}
			].map((col, idx) => React.createElement("div", {
				key: idx,
				className: "flex flex-col p-3.5 rounded-xl border text-center space-y-2 shadow-sm " + col.color
			}, React.createElement("span", { className: "font-bold font-mono text-xs text-white" }, col.step), React.createElement("span", { className: "text-[11px] font-bold uppercase tracking-wider text-slate-100 truncate" }, col.role), React.createElement("span", { className: "text-[10px] font-mono px-2 py-0.5 rounded bg-slate-950 border border-slate-700 text-slate-200 font-semibold truncate" }, col.actor), React.createElement("p", { className: "text-xs text-slate-200 leading-snug m-0 text-left pt-1.5 border-t border-slate-700/60 font-normal" }, col.desc))))), React.createElement("div", { className: "space-y-3 pt-3 border-t border-slate-800" }, React.createElement("div", { className: "text-xs font-bold text-slate-200 uppercase tracking-wider" }, "End-to-End Autonomous Execution Flow"), React.createElement("div", { className: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-7 gap-2.5 text-xs" }, [
				{
					num: "1",
					title: "Goal Ingestion",
					badge: "Triage",
					bcolor: "text-indigo-100 bg-indigo-900/90 border-indigo-500/70",
					desc: "User submits high-level goals or epics via CLI or dashboard UI. Raw triage goals are unrefined and ignored by the dispatcher."
				},
				{
					num: "2",
					title: "Decompose & Scan",
					badge: "Todo",
					bcolor: "text-sky-100 bg-sky-900/90 border-sky-500/70",
					desc: "zf-orchestrator decomposes Triage epics AND scans the codebase project on idle to create actionable TODO tasks."
				},
				{
					num: "3",
					title: "Worktree & Launch",
					badge: "Running",
					bcolor: "text-emerald-100 bg-emerald-900/90 border-emerald-500/70",
					desc: "Dispatcher verifies capacity & WIP limits, allocates isolated Git worktree (~/git/<repo>-worktrees/<task_id>), and spawns zf-builder in Running."
				},
				{
					num: "4",
					title: "Code & Tests",
					badge: "Running",
					bcolor: "text-emerald-100 bg-emerald-900/90 border-emerald-500/70",
					desc: "zf-builder inspects OpenWiki/AGENTS.md, writes code & tests applying the Ponytail Ladder of Laziness, and executes .zerofactory/precommit.sh."
				},
				{
					num: "5",
					title: "Precommit & PR",
					badge: "Running",
					bcolor: "text-emerald-100 bg-emerald-900/90 border-emerald-500/70",
					desc: "Dispatcher runs precommit (format ➔ build ➔ tests), stages formatted files, self-heals any test regressions, opens GitHub PR, and routes to zf-reviewer."
				},
				{
					num: "6",
					title: "Thematic Review",
					badge: "Running",
					bcolor: "text-emerald-100 bg-emerald-900/90 border-emerald-500/70",
					desc: "zf-reviewer runs in Running (Correctness ➔ Performance ➔ Ponytail / Clean Code, up to 3 rounds). Requests changes or approves."
				},
				{
					num: "7",
					title: "Human Merge",
					badge: "Blocked ➔ Done",
					bcolor: "text-rose-100 bg-rose-900/90 border-rose-500/70",
					desc: "Approved PR waits in Blocked. Once human merges on GitHub, dispatcher marks task Done and prunes the worktree."
				}
			].map((step, idx) => React.createElement("div", {
				key: idx,
				className: "bg-slate-950/80 border border-slate-700/80 rounded-xl p-3.5 flex flex-col justify-between space-y-2 relative group hover:border-slate-500 transition-colors shadow-sm"
			}, React.createElement("div", { className: "space-y-1.5" }, React.createElement("div", { className: "flex items-center justify-between gap-1" }, React.createElement("span", { className: "w-6 h-6 rounded-full bg-indigo-900/90 text-indigo-100 font-mono font-bold text-xs flex items-center justify-center shrink-0 border border-indigo-500/60 shadow-xs" }, step.num), React.createElement("span", { className: "text-xs font-mono px-2 py-0.5 rounded border font-bold truncate shadow-xs " + step.bcolor }, step.badge)), React.createElement("div", { className: "text-xs font-bold text-white leading-tight pt-0.5" }, step.title), React.createElement("p", { className: "text-xs text-slate-200 leading-snug m-0 font-normal" }, step.desc)))))), React.createElement("div", { className: "grid grid-cols-1 md:grid-cols-2 gap-3.5 pt-2" }, React.createElement("div", { className: "p-4.5 bg-purple-950/50 border border-purple-600/70 rounded-xl space-y-2 text-xs shadow-sm" }, React.createElement("div", { className: "font-bold flex items-center gap-2 text-purple-200 text-sm" }, "↩️ Reviewer Feedback Loop:"), React.createElement("p", { className: "text-slate-100 text-xs leading-relaxed m-0 font-normal" }, "When ", React.createElement("span", { className: "font-mono text-purple-200 bg-slate-900 px-1.5 py-0.5 rounded border border-purple-500/60 font-bold" }, "zf-reviewer"), " requests changes during rounds 1-3 in ", React.createElement("span", { className: "font-mono text-emerald-200 bg-slate-900 px-1.5 py-0.5 rounded border border-emerald-500/60 font-bold" }, "Running"), ", the dispatcher routes the ticket back to ", React.createElement("span", { className: "font-mono text-sky-200 bg-slate-900 px-1.5 py-0.5 rounded border border-sky-500/60 font-bold" }, "Todo"), " assigned to ", React.createElement("span", { className: "font-mono text-emerald-200 bg-slate-900 px-1.5 py-0.5 rounded border border-emerald-500/60 font-bold" }, "zf-builder"), ". The builder updates code and tests on the same branch, triggering automatic re-review.")), React.createElement("div", { className: "p-4.5 bg-amber-950/40 border border-amber-600/70 rounded-xl space-y-2 text-xs shadow-sm" }, React.createElement("div", { className: "font-bold flex items-center gap-2 text-amber-200 text-sm" }, "🛡️ Human-in-the-Loop (HITL) Safety Gates:"), React.createElement("p", { className: "text-slate-100 text-xs leading-relaxed m-0 font-normal" }, React.createElement("strong", { className: "text-amber-200 font-bold" }, "PR Merge Gate: "), "Agents NEVER auto-merge to main. Every task produces an isolated PR; approved tasks pause in ", React.createElement("span", { className: "font-mono text-purple-200 bg-slate-900 px-1.5 py-0.5 rounded border border-purple-500/60 font-bold" }, "Blocked"), " until a human reviews and merges on GitHub. ", React.createElement("strong", { className: "text-amber-200 font-bold" }, "Escalation Gate: "), "Crashed workers, timeouts, or unresolvable merge conflicts route directly to ", React.createElement("span", { className: "font-mono text-purple-200 bg-slate-900 px-1.5 py-0.5 rounded border border-purple-500/60 font-bold" }, "Blocked"), " for operator resolution.")))));
		};
		const renderSpecialistsSection = () => {
			return React.createElement("div", { className: "grid grid-cols-1 lg:grid-cols-3 gap-5" }, [
				{
					name: "zf-orchestrator",
					title: "Pipeline Overseer & Coordinator",
					color: "border-indigo-500/70 bg-indigo-950/40 text-indigo-100",
					badge: "Indigo Profile (Pipeline Overseer)",
					desc: "Supervises the Kanban board, decomposes user epics into atomic tickets, schedules task execution, and detects stuck or hung worker processes.",
					responsibilities: [
						"Autonomously scans projects via Codebase Improvement Scanner using the Ponytail ladder of laziness to create actionable TODO tasks",
						"Audits repository for dead code (Rung 1), stdlib reuse (Rungs 2-3), and anti-overengineering (Rung 6)",
						"Decomposes high-level goals into structured sub-tasks using kanban_decomposer",
						"Manages ticket handoffs between zf-builder and zf-reviewer",
						"Escalates unresolvable blockers and human reviews",
						"Monitors queue health via zero-factory-task-queue-check"
					],
					dir: "~/.hermes/profiles/zf-orchestrator/"
				},
				{
					name: "zf-builder",
					title: "Senior Software Engineer",
					color: "border-emerald-500/70 bg-emerald-950/40 text-emerald-100",
					badge: "Emerald Profile (Senior Engineer)",
					desc: "Takes tickets from Todo into Running, operating in an isolated Git worktree. Writes clean code and tests applying the Ponytail Ladder of Laziness.",
					responsibilities: [
						"Operates inside dedicated Git worktrees (~/git/<repo>-worktrees/<task_id>)",
						"Never touches or modifies the repository main branch directly",
						"Applies the 7-rung Ladder of Laziness: stdlib-first, surgical diffs, and zero package bloat",
						"Writes production code alongside automated unit and integration tests",
						"Verifies test suites pass cleanly before committing and opening PRs"
					],
					dir: "~/.hermes/profiles/zf-builder/"
				},
				{
					name: "zf-reviewer",
					title: "Quality Gatekeeper",
					color: "border-purple-500/70 bg-purple-950/40 text-purple-100",
					badge: "Purple Profile (Quality Gatekeeper)",
					desc: "Conducts thematic code reviews on open Pull Requests. Capped strictly at 3 progressive rounds (Correctness ➔ Performance ➔ Ponytail / Clean Code) to eliminate infinite loops.",
					responsibilities: [
						"Round 1: Testing coverage, edge cases, and functional correctness",
						"Round 2: Performance, memory overhead, and algorithmic efficiency",
						"Round 3: Clean code & Ponytail anti-overengineering review (vetoing dependency bloat, diff creep, and premature abstractions)",
						"Pre-digested git diff and commit history provided directly in prompt context to minimize redundant exploration",
						"Approves PR and moves task to Blocked (assigned to human) for merge"
					],
					dir: "~/.hermes/profiles/zf-reviewer/"
				}
			].map((agent, i) => React.createElement("div", {
				key: i,
				className: "flex flex-col bg-slate-900/80 border rounded-2xl p-5 space-y-4 shadow-lg " + agent.color.split(" ")[0]
			}, React.createElement("div", { className: "flex items-center justify-between gap-2" }, React.createElement("h3", { className: "text-base font-bold text-white font-mono m-0" }, agent.name), React.createElement("span", { className: "text-xs font-bold px-2.5 py-1 rounded-full border shadow-xs " + agent.color }, agent.badge)), React.createElement("p", { className: "text-xs font-bold text-slate-200 m-0" }, agent.title), React.createElement("p", { className: "text-xs text-slate-100 leading-relaxed m-0 flex-1 font-normal" }, agent.desc), React.createElement("div", { className: "space-y-2 pt-3 border-t border-slate-700/80" }, React.createElement("span", { className: "text-xs font-bold text-slate-200 uppercase tracking-wider block" }, "Core Responsibilities:"), React.createElement("ul", { className: "list-disc list-inside space-y-1.5 text-xs text-slate-200 m-0 p-0 leading-relaxed font-normal" }, agent.responsibilities.map((r, idx) => React.createElement("li", {
				key: idx,
				className: "leading-relaxed"
			}, r)))), React.createElement("div", { className: "pt-3 text-xs font-mono text-slate-300 border-t border-slate-700/70 flex items-center justify-between gap-2" }, React.createElement("span", { className: "font-semibold text-slate-300" }, "Profile Path:"), React.createElement("span", { className: "text-indigo-200 bg-slate-950 px-2 py-1 rounded-md border border-slate-700 font-bold select-all" }, agent.dir)))));
		};
		const renderLifecycleSection = () => {
			return React.createElement("div", { className: "space-y-6" }, React.createElement("div", { className: "bg-slate-900/70 border border-slate-700/80 rounded-2xl p-6 space-y-4 shadow-md" }, React.createElement("h3", { className: "text-sm font-bold text-white m-0 flex items-center gap-2 tracking-wide" }, "🔄 Kanban Column Workflow"), React.createElement("div", { className: "grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-4 pt-1" }, [
				{
					id: "triage",
					title: "Triage",
					desc: "Incoming raw user goals, feature requests, or epics awaiting decomposition.",
					trigger: "Submitted via CLI or Board UI"
				},
				{
					id: "todo",
					title: "Todo",
					desc: "Actionable backlog: Decomposed tickets from Triage, improvement tasks filed by scanner, or reviewer rework.",
					trigger: "zf-orchestrator decomposes or scans"
				},
				{
					id: "running",
					title: "Running",
					desc: "Dedicated worker executing inside isolated Git worktree. zf-builder coding or zf-reviewer reviewing PR diff.",
					trigger: "Autonomous pickup by dispatcher"
				},
				{
					id: "blocked",
					title: "Blocked",
					desc: "Human action required: PR approved waiting for human merge, worker crash retry, or merge conflict resolution.",
					trigger: "Awaiting Human Merge, Crash, or Conflict"
				},
				{
					id: "done",
					title: "Done",
					desc: "Completed and merged tickets. Worktrees pruned and metrics updated.",
					trigger: "PR merged on GitHub"
				}
			].map((c) => React.createElement("div", {
				key: c.id,
				className: "bg-slate-950/80 border border-slate-700/80 rounded-xl p-4.5 space-y-2.5 shadow-sm"
			}, React.createElement("div", { className: "flex items-center justify-between gap-2" }, React.createElement("span", { className: "text-sm font-bold uppercase tracking-wider text-indigo-300" }, c.title), React.createElement("span", { className: "text-xs font-mono font-semibold px-2 py-0.5 rounded bg-slate-900 border border-slate-700 text-slate-200" }, c.id)), React.createElement("p", { className: "text-xs text-slate-100 leading-relaxed m-0 font-normal" }, c.desc), React.createElement("div", { className: "text-xs text-slate-300 pt-2 border-t border-slate-800 font-medium flex items-center justify-between gap-2 flex-wrap" }, React.createElement("span", null, "Trigger:"), React.createElement("span", { className: "text-white font-semibold bg-slate-900 px-2 py-0.5 rounded border border-slate-700/80" }, c.trigger)))))), React.createElement("div", { className: "bg-gradient-to-br from-purple-950/50 via-slate-900/80 to-slate-900/80 border border-purple-600/70 rounded-2xl p-6 space-y-3 shadow-md" }, React.createElement("div", { className: "flex items-center gap-3" }, React.createElement("div", { className: "p-2.5 rounded-xl bg-purple-900/80 text-purple-200 border border-purple-500/50 shadow-xs" }, renderPrIcon("w-4 h-4")), React.createElement("h3", { className: "text-base font-bold text-white m-0 tracking-wide" }, "Pull Request Tracking & Verification")), React.createElement("p", { className: "text-xs text-slate-100 leading-relaxed m-0 font-normal" }, "Tasks with active GitHub Pull Requests display an interactive PR link badge directly on the Kanban card. You can click the badge to jump straight to the GitHub review interface. Use the toolbar's ", React.createElement("span", { className: "font-mono text-purple-200 bg-slate-900 px-1.5 py-0.5 rounded border border-purple-500/60 font-bold text-xs" }, "Has PR"), " filter button to instantly isolate all tickets currently under active Pull Request review.")));
		};
		const renderWorktreesSection = () => {
			return React.createElement("div", { className: "space-y-6" }, React.createElement("div", { className: "bg-slate-900/70 border border-slate-700/80 rounded-2xl p-6 space-y-4 shadow-md" }, React.createElement("h3", { className: "text-sm font-bold text-white m-0 tracking-wide" }, "🌳 The Git Worktree Isolation Model"), React.createElement("p", { className: "text-xs text-slate-100 leading-relaxed m-0 font-normal" }, "In traditional multi-agent systems, agents operate on the primary repository directory. This causes uncommitted file clashes, stash corruptions, and broken builds when parallel tasks run. Zero Factory completely eliminates this failure mode using dedicated Git worktrees."), React.createElement("div", { className: "p-4.5 bg-slate-950 border border-slate-700 rounded-xl space-y-2 font-mono text-xs text-slate-100 shadow-inner" }, React.createElement("div", { className: "text-indigo-300 font-bold" }, "# Worktree Directory Structure"), React.createElement("div", { className: "text-white font-bold" }, "~/git/"), React.createElement("div", { className: "pl-4 text-slate-300" }, "├── my-repo/                    # Main repository (untouched by workers)"), React.createElement("div", { className: "pl-4 text-emerald-300 font-bold" }, "└── my-repo-worktrees/"), React.createElement("div", { className: "pl-8 text-emerald-300 font-semibold" }, "├── zf-dev-9a4f210b/        # Isolated worktree for Task 1 (board code prefix)"), React.createElement("div", { className: "pl-8 text-emerald-300 font-semibold" }, "└── zf-dev-b72e189c/        # Isolated worktree for Task 2 (board code prefix)")), React.createElement("div", { className: "grid grid-cols-1 md:grid-cols-3 gap-4 pt-2" }, [
				{
					title: "No Branch Conflicts",
					desc: "Workers branch cleanly from main without touching your active unstaged edits."
				},
				{
					title: "Parallel Test Suites",
					desc: "Multiple test runs execute simultaneously without file lock collisions."
				},
				{
					title: "Automated Cleanup",
					desc: "When the PR is merged, the worktree is automatically pruned from disk."
				}
			].map((item, idx) => React.createElement("div", {
				key: idx,
				className: "p-4 bg-slate-950/80 border border-slate-700/80 rounded-xl space-y-1.5 shadow-sm"
			}, React.createElement("h4", { className: "text-xs font-bold text-white m-0" }, item.title), React.createElement("p", { className: "text-xs text-slate-200 leading-relaxed m-0 font-normal" }, item.desc))))));
		};
		const renderQualitySection = () => {
			return React.createElement("div", { className: "space-y-6" }, React.createElement("div", { className: "bg-slate-900/70 border border-slate-700/80 rounded-2xl p-6 space-y-5 shadow-md" }, React.createElement("div", { className: "flex items-center justify-between flex-wrap gap-2 pb-3 border-b border-slate-800" }, React.createElement("h3", { className: "text-base font-bold text-white m-0 flex items-center gap-2 tracking-wide" }, React.createElement("span", null, "⚡"), "Deterministic Precommit Pipeline (.zerofactory/precommit.sh)"), React.createElement("span", { className: "text-xs font-mono px-2.5 py-0.5 rounded-full font-bold bg-amber-950/80 text-amber-300 border border-amber-800/60" }, "Automated Quality Gate")), React.createElement("p", { className: "text-xs text-slate-100 leading-relaxed m-0 font-normal" }, "Zero Factory guarantees that no broken code, unformatted files, or failing tests reach a Pull Request. Before any commit or PR is generated, the dispatcher deterministically executes ", React.createElement("span", { className: "font-mono text-amber-300 bg-slate-950 px-1.5 py-0.5 rounded border border-slate-700 font-semibold" }, ".zerofactory/precommit.sh"), " inside the task's isolated Git worktree across three standard verification phases:"), React.createElement("div", { className: "grid grid-cols-1 md:grid-cols-3 gap-4" }, [
				{
					phase: "1. Format & Lint",
					icon: "🎨",
					desc: "Runs automated linters (e.g. ruff check --fix, ruff format for Python; Prettier/ESLint for JS). Auto-installs missing tools to the system automatically and stages all formatted files."
				},
				{
					phase: "2. Build & Typecheck",
					icon: "🔨",
					desc: "Performs static syntax verification or bytecode compilation (e.g. python3 -m compileall, tsc --noEmit, cargo check) to guarantee zero syntax or import errors."
				},
				{
					phase: "3. Hermetic Tests",
					icon: "🧪",
					desc: "Executes the automated test suite (e.g. python3 -m pytest tests/ -q). Pull Requests are blocked from creation until all unit and integration tests pass cleanly with exit code 0."
				}
			].map((p, idx) => React.createElement("div", {
				key: idx,
				className: "bg-slate-950/80 border border-slate-700/80 rounded-xl p-4.5 space-y-2 shadow-sm"
			}, React.createElement("div", { className: "flex items-center gap-2 font-bold text-white text-xs" }, React.createElement("span", null, p.icon), p.phase), React.createElement("p", { className: "text-xs text-slate-200 leading-relaxed m-0 font-normal" }, p.desc)))), React.createElement("div", { className: "p-4.5 bg-amber-950/40 border border-amber-600/70 rounded-xl space-y-2 text-xs shadow-sm" }, React.createElement("div", { className: "font-bold flex items-center gap-2 text-amber-200 text-sm" }, "🔁 Self-Healing Auto-Fix Feedback Loop:"), React.createElement("p", { className: "text-slate-100 text-xs leading-relaxed m-0 font-normal" }, "If precommit checks fail, the dispatcher does ", React.createElement("strong", { className: "text-white" }, "not"), " abandon the task or bother human reviewers. It captures the exact terminal stdout/stderr failure logs and re-spawns ", React.createElement("span", { className: "font-mono text-emerald-200 bg-slate-900 px-1.5 py-0.5 rounded border border-emerald-500/60 font-bold" }, "zf-builder"), " with the error trace to auto-fix regressions (up to 3 retries) before opening the PR.")), React.createElement("div", { className: "flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2 text-xs text-slate-300 font-medium" }, React.createElement("span", null, "Setup trigger: 1-click warning banner on Kanban board, Board Settings modal, or CLI:"), React.createElement("span", { className: "font-mono text-amber-300 bg-slate-950 px-2.5 py-1 rounded-lg border border-slate-700 select-all shrink-0" }, "hermes zerofactory setup-repo --board <slug>"))), React.createElement("div", { className: "bg-slate-900/70 border border-slate-700/80 rounded-2xl p-6 space-y-5 shadow-md" }, React.createElement("div", { className: "flex items-center justify-between flex-wrap gap-2 pb-3 border-b border-slate-800" }, React.createElement("h3", { className: "text-base font-bold text-white m-0 flex items-center gap-2 tracking-wide" }, React.createElement("span", null, "📖"), "OpenWiki Architecture Knowledge Base (openwiki/)"), React.createElement("span", { className: "text-xs font-mono px-2.5 py-0.5 rounded-full font-bold bg-sky-950/80 text-sky-300 border border-sky-800/60" }, "Context Optimization (30–40% Token Savings)")), React.createElement("p", { className: "text-xs text-slate-100 leading-relaxed m-0 font-normal" }, "Autonomous coding agents frequently burn thousands of unnecessary tokens by blindly grepping directories and reading irrelevant source files. Zero Factory adopts the ", React.createElement("strong", { className: "text-white" }, "OpenWiki / Docs for Agents"), " standard: a pre-digested, machine-readable architectural knowledge base located in ", React.createElement("span", { className: "font-mono text-sky-300 bg-slate-950 px-1.5 py-0.5 rounded border border-slate-700 font-semibold" }, "openwiki/"), " and referenced in ", React.createElement("span", { className: "font-mono text-sky-300 bg-slate-950 px-1.5 py-0.5 rounded border border-slate-700 font-semibold" }, "AGENTS.md"), "."), React.createElement("div", { className: "grid grid-cols-1 md:grid-cols-3 gap-4" }, [
				{
					title: "openwiki/index.md",
					icon: "🗺️",
					desc: "Master system map: Subsystem catalog, database models, background services, API route trees, and cross-module contracts."
				},
				{
					title: "Module Guides",
					icon: "📦",
					desc: "High-signal architectural summaries explaining component boundaries, entrypoints, and design decisions without raw source noise."
				},
				{
					title: "AGENTS.md Linking",
					icon: "🔗",
					desc: "Explicit instructions directing zf-builder and zf-reviewer to read openwiki/index.md first before performing expensive exploratory tool calls."
				}
			].map((w, idx) => React.createElement("div", {
				key: idx,
				className: "bg-slate-950/80 border border-slate-700/80 rounded-xl p-4.5 space-y-2 shadow-sm"
			}, React.createElement("div", { className: "flex items-center gap-2 font-bold text-white text-xs font-mono" }, React.createElement("span", null, w.icon), w.title), React.createElement("p", { className: "text-xs text-slate-200 leading-relaxed m-0 font-normal" }, w.desc)))), React.createElement("div", { className: "p-4.5 bg-sky-950/50 border border-sky-500/70 rounded-xl space-y-2 text-xs shadow-sm" }, React.createElement("div", { className: "font-bold flex items-center gap-2 text-sky-200 text-sm" }, "🎯 Key Agent Benefits:"), React.createElement("ul", { className: "text-slate-100 text-xs leading-relaxed m-0 pl-4 space-y-1 font-normal list-disc" }, React.createElement("li", null, React.createElement("strong", { className: "text-white" }, "30–40% Token Savings:"), " Slashes exploratory grep_search, find_by_name, and random file reads by up to 40%."), React.createElement("li", null, React.createElement("strong", { className: "text-white" }, "Prevents Context Drift:"), " Prevents agents from hallucinating outdated conventions or diverging from established patterns."), React.createElement("li", null, React.createElement("strong", { className: "text-white" }, "Native MCP Tools (Zero ENV):"), " Pre-configured stdio MCP server (openwiki_begin, openwiki_submit_page, openwiki_search) with 0 external API keys or manual exports required."), React.createElement("li", null, React.createElement("strong", { className: "text-white" }, "Fast Onboarding:"), " New tasks start immediately with full architectural orientation in a single compact markdown read."))), React.createElement("div", { className: "flex flex-col sm:flex-row sm:items-center justify-between gap-3 pt-2 text-xs text-slate-300 font-medium" }, React.createElement("span", null, "Setup trigger: 1-click recommendation banner on Kanban board, Board Settings modal, or CLI:"), React.createElement("span", { className: "font-mono text-sky-300 bg-slate-950 px-2.5 py-1 rounded-lg border border-slate-700 select-all shrink-0" }, "hermes zerofactory setup-openwiki --board <slug>"))));
		};
		const renderCliSection = () => {
			return React.createElement("div", { className: "space-y-5" }, [
				{
					group: "Profile & System Setup",
					cmds: [{
						cmd: "hermes zerofactory setup",
						desc: "Bootstrap or inspect zf-* profiles and script symlinks"
					}, {
						cmd: "hermes zerofactory sync-profiles",
						desc: "Update profile system prompts from plugin templates"
					}]
				},
				{
					group: "Task Management",
					cmds: [
						{
							cmd: "hermes zerofactory list",
							desc: "List all active tickets across all boards"
						},
						{
							cmd: "hermes zerofactory list --board <slug> --status running",
							desc: "Filter tickets by board and status"
						},
						{
							cmd: "hermes zerofactory create \"<title>\" --description \"<desc>\" --board <slug> --priority P1",
							desc: "Create a new ticket"
						},
						{
							cmd: "hermes zerofactory move <task_id> running",
							desc: "Transition ticket status"
						},
						{
							cmd: "hermes zerofactory block <task_id> --reason \"<reason>\"",
							desc: "Mark ticket as blocked with explanation"
						},
						{
							cmd: "hermes zerofactory comment <task_id> \"<message>\"",
							desc: "Post a comment to a ticket"
						},
						{
							cmd: "hermes zerofactory import-gh-issue <issue> [--force]",
							desc: "Import GitHub issue into human-gated Triage task"
						},
						{
							cmd: "hermes zerofactory import-gh-issue --sync",
							desc: "Batch import open issues requested for AI investigation"
						},
						{
							cmd: "hermes zerofactory import-jira-issue <key-or-url> [--board <slug>]",
							desc: "Import Jira Cloud issue into human-gated Triage task"
						}
					]
				},
				{
					group: "Board & Dispatcher Operations",
					cmds: [
						{
							cmd: "hermes zerofactory board list",
							desc: "List all registered project boards"
						},
						{
							cmd: "hermes zerofactory board create <git_url>",
							desc: "Register a new codebase board from Remote Git URL"
						},
						{
							cmd: "hermes zerofactory board delete <slug>",
							desc: "Delete a board and clear its scheduled scanner job"
						},
						{
							cmd: "hermes zerofactory setup-repo --board <slug>",
							desc: "Create P0 setup task to generate .zerofactory/precommit.sh"
						},
						{
							cmd: "hermes zerofactory setup-openwiki --board <slug>",
							desc: "Create P0 setup task to generate openwiki/ architecture docs"
						},
						{
							cmd: "hermes zerofactory setup-gh-issues --board <slug>",
							desc: "Create P0 setup task to generate GitHub Issue templates & labels"
						},
						{
							cmd: "hermes zerofactory setup-jira --board <slug> [--url <jira_url>]",
							desc: "Configure Jira Cloud instance link and test connectivity for a board"
						},
						{
							cmd: "hermes zerofactory stats",
							desc: "Show Kanban metrics, throughput, and worker states"
						},
						{
							cmd: "hermes zerofactory dispatch",
							desc: "Trigger an immediate autonomous dispatch cycle"
						},
						{
							cmd: "hermes zerofactory check-stuck",
							desc: "Audit and reap long-running or hung worker processes"
						}
					]
				},
				{
					group: "Memory & Repository Knowledge",
					cmds: [
						{
							cmd: "hermes zerofactory memory list --board <slug>",
							desc: "List persistent repository memories and conventions"
						},
						{
							cmd: "hermes zerofactory memory add --board <slug> \"<content>\" --category convention",
							desc: "Record a new repository memory or gotcha"
						},
						{
							cmd: "hermes zerofactory memory delete <memory_id>",
							desc: "Delete a repository memory by ID"
						}
					]
				},
				{
					group: "Cron Automation & Migrations",
					cmds: [
						{
							cmd: "hermes zerofactory cron list",
							desc: "View active periodic health & scanner jobs"
						},
						{
							cmd: "hermes zerofactory cron sync",
							desc: "Sync cron definitions with Hermes scheduler"
						},
						{
							cmd: "hermes zerofactory cron run <job_id>",
							desc: "Execute a scheduled scanner or watchdog immediately"
						},
						{
							cmd: "hermes zerofactory migrate [--status]",
							desc: "Inspect or execute pending SQLite database migrations"
						}
					]
				}
			].map((g, idx) => React.createElement("div", {
				key: idx,
				className: "bg-slate-900/70 border border-slate-700/80 rounded-2xl p-5 space-y-3.5 shadow-md"
			}, React.createElement("h3", { className: "text-sm font-bold uppercase tracking-wider text-indigo-300 m-0" }, g.group), React.createElement("div", { className: "space-y-2.5" }, g.cmds.map((item, cIdx) => React.createElement("div", {
				key: cIdx,
				className: "flex flex-col md:flex-row md:items-center justify-between gap-3 p-3.5 bg-slate-950 border border-slate-800 rounded-xl hover:border-slate-700 transition-colors shadow-xs"
			}, React.createElement("span", { className: "text-xs font-mono text-emerald-300 font-bold bg-slate-900 px-3 py-1.5 rounded-lg border border-slate-700 break-all select-all shadow-xs" }, item.cmd), React.createElement("span", { className: "text-xs text-slate-200 font-medium shrink-0" }, item.desc)))))));
		};
		const renderCronsSection = () => {
			return React.createElement("div", { className: "space-y-5" }, [{
				id: "zero-factory-task-queue-check",
				title: "Queue Health & Worker Watchdog",
				interval: "Every 120 minutes",
				tokens: "0 Tokens (No-Agent Mode)",
				desc: "Runs purely in Python using Hermes No-Agent Mode via scripts/zf_queue_watchdog.py (0 LLM tokens). Audits running tasks, reaps hung worker subprocesses, and automatically triggers run_dispatch_cycle().",
				badge: "No-Agent Mode"
			}, {
				id: "zero-factory-improvement-scanner-{slug}",
				title: "Codebase Improvement Scanner (zf-orchestrator)",
				interval: "On Idle (Active < 2)",
				tokens: "0 Tokens when Busy / Cooldown",
				desc: "Executed autonomously by zf-orchestrator inside the codebase workdir with wake-gate change detection (scripts/zf_scanner_gate.py) and independent sessions (continuity: false). When the pipeline is busy (running >= 2 or todo >= 2) or during the 15-minute cooldown, it emits {'wakeAgent': false} (0 tokens). When the board is idle, it wakes zf-orchestrator to audit the codebase for tech debt, refactoring, or missing tests, creating at most 1 actionable TODO task on the board assigned to zf-builder.",
				badge: "Wake-Gate • zf-orchestrator"
			}].map((job) => React.createElement("div", {
				key: job.id,
				className: "bg-slate-900/70 border border-slate-700/80 rounded-2xl p-5 space-y-3 shadow-md"
			}, React.createElement("div", { className: "flex flex-col md:flex-row md:items-center justify-between gap-2.5" }, React.createElement("div", { className: "space-y-1.5" }, React.createElement("h3", { className: "text-base font-bold text-white m-0 tracking-wide" }, job.title), React.createElement("span", { className: "text-xs font-mono text-indigo-200 bg-slate-950 px-2.5 py-1 rounded-md border border-slate-700 font-bold select-all inline-block" }, job.id)), React.createElement("div", { className: "flex items-center gap-2.5 flex-wrap" }, React.createElement("span", { className: "text-xs font-bold px-3 py-1 rounded-full bg-emerald-900/90 text-emerald-100 border border-emerald-500/70 font-mono shadow-xs" }, job.tokens), React.createElement("span", { className: "text-xs font-bold px-3 py-1 rounded-full bg-slate-800 text-slate-100 border border-slate-600 font-mono shadow-xs" }, job.interval))), React.createElement("p", { className: "text-xs text-slate-100 leading-relaxed m-0 font-normal" }, job.desc))));
		};
		return React.createElement("div", { className: "space-y-6 pb-12 max-w-[1400px] mx-auto" }, React.createElement("div", { className: "relative overflow-hidden bg-gradient-to-br from-indigo-950/70 via-slate-900/90 to-purple-950/60 border border-slate-700/90 rounded-2xl p-6 md:p-8 shadow-2xl" }, React.createElement("div", { className: "flex flex-col md:flex-row md:items-center justify-between gap-6 relative z-10" }, React.createElement("div", { className: "space-y-3.5" }, React.createElement("div", { className: "flex items-center gap-2.5 flex-wrap" }, React.createElement("span", { className: "px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-amber-950/80 text-amber-300 border border-amber-600/70 font-mono shadow-xs" }, "⚡ Active Beta"), React.createElement("span", { className: "px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-indigo-900/80 text-indigo-100 border border-indigo-500/60 font-mono shadow-xs" }, "Hermes Plugin"), React.createElement("span", { className: "px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-emerald-900/80 text-emerald-100 border border-emerald-500/60 font-mono shadow-xs" }, "Zero-Token Idle Watchdogs"), React.createElement("span", { className: "px-3 py-1 rounded-full text-xs font-bold uppercase tracking-wider bg-purple-900/80 text-purple-100 border border-purple-500/60 font-mono shadow-xs" }, "Thematic Review")), React.createElement("h2", { className: "text-2xl md:text-3xl font-extrabold text-white tracking-tight m-0" }, "Zero Factory Architecture & User Guide"), React.createElement("p", { className: "text-xs md:text-sm text-slate-200 max-w-2xl leading-relaxed m-0 font-normal" }, "A 24/7 autonomous multi-agent software engineering factory built natively for Hermes Agent. Three specialist agent profiles collaborate through a durable SQLite Kanban board to decompose goals, implement features inside isolated Git worktrees, and conduct thematic PR reviews.")), React.createElement("div", { className: "flex items-center gap-3 shrink-0" }, React.createElement("button", {
			type: "button",
			className: "inline-flex items-center gap-2 px-4.5 py-2.5 rounded-xl text-xs font-bold bg-indigo-600 hover:bg-indigo-500 text-white shadow-lg shadow-indigo-600/40 transition-all duration-150 cursor-pointer",
			onClick: () => setActiveView("board")
		}, "📋 Return to Kanban Board")))), React.createElement("div", { className: "flex items-start gap-3.5 p-4 md:p-6 rounded-2xl bg-amber-950/40 border border-amber-600/70 text-amber-200 text-xs md:text-sm leading-relaxed shadow-lg" }, React.createElement("span", { className: "text-2xl shrink-0 select-none mt-0.5" }, "⚠️"), React.createElement("div", { className: "space-y-1" }, React.createElement("p", { className: "font-bold text-amber-200 text-sm m-0 flex items-center gap-2" }, "Beta Notice & High-Frequency Changes"), React.createElement("p", { className: "text-amber-300 text-xs md:text-sm m-0 leading-normal" }, "Zero Factory is currently in active beta and undergoing rapid evolution with high-frequency changes. APIs, CLI flags, configuration schemas, agent prompt templates, and internal orchestration mechanics evolve frequently. Please keep your plugin updated regularly."))), React.createElement("div", { className: "flex items-center gap-2 overflow-x-auto zfk-scrollbar pb-2 border-b border-slate-800" }, [
			{
				id: "overview",
				label: "Architecture",
				icon: "🌟"
			},
			{
				id: "specialists",
				label: "Agent Specialists",
				icon: "🤖"
			},
			{
				id: "lifecycle",
				label: "Kanban & PR Lifecycle",
				icon: "🔄"
			},
			{
				id: "worktrees",
				label: "Git Worktree Isolation",
				icon: "🌳"
			},
			{
				id: "quality",
				label: "Precommit & OpenWiki",
				icon: "🛡️"
			},
			{
				id: "cli",
				label: "CLI Cheat Sheet",
				icon: "💻"
			},
			{
				id: "crons",
				label: "Scheduled Automation",
				icon: "⏰"
			}
		].map((tab) => React.createElement("button", {
			key: tab.id,
			type: "button",
			className: "flex items-center gap-2 px-4 py-2.5 rounded-xl text-xs font-bold whitespace-nowrap transition-all duration-150 cursor-pointer " + (instructionTab === tab.id ? "bg-indigo-600 text-white shadow-md shadow-indigo-600/30 border border-indigo-400" : "bg-slate-900/80 text-slate-200 hover:text-white hover:bg-slate-800 border border-slate-700/80 font-medium"),
			onClick: () => setInstructionTab(tab.id)
		}, React.createElement("span", null, tab.icon), tab.label))), instructionTab === "overview" && renderOverviewSection(), instructionTab === "specialists" && renderSpecialistsSection(), instructionTab === "lifecycle" && renderLifecycleSection(), instructionTab === "worktrees" && renderWorktreesSection(), instructionTab === "quality" && renderQualitySection(), instructionTab === "cli" && renderCliSection(), instructionTab === "crons" && renderCronsSection());
	}
	//#endregion
	//#region dashboard/src/components/Modal.jsx
	/**
	* Standard reusable Modal dialog for Zero Factory Dashboard.
	* Enforces uniform responsive sizing, backdrop, mobile padding, and Escape-key listener.
	*/
	function Modal(props) {
		const { isOpen = true, onClose, title, subtitle, icon, iconBg, header, headerExtra, subHeader, footer, maxWidth = "max-w-4xl", children, className = "", bodyClassName = "p-6 space-y-4 overflow-y-auto zfk-scrollbar flex-1", footerClassName = "flex items-center justify-end gap-2.5 px-6 py-3.5 border-t border-slate-800 bg-slate-900/50 shrink-0", onSubmit } = props;
		if (!isOpen) return null;
		useEffect(() => {
			const handleKeyDown = (e) => {
				if (e.key === "Escape" && onClose) onClose();
			};
			window.addEventListener("keydown", handleKeyDown);
			return () => window.removeEventListener("keydown", handleKeyDown);
		}, [onClose]);
		return React.createElement("div", {
			className: "fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-xs p-3 sm:p-4 overflow-y-auto",
			onClick: () => onClose && onClose()
		}, React.createElement(onSubmit ? "form" : "div", {
			onSubmit,
			className: `bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl w-full ${maxWidth} max-h-[92vh] flex flex-col overflow-hidden text-slate-100 ${className}`,
			onClick: (e) => e.stopPropagation()
		}, header !== void 0 ? header : title || onClose ? React.createElement("div", { className: "flex items-center justify-between px-6 py-4 border-b border-slate-800 shrink-0 bg-slate-900/60" }, React.createElement("div", { className: "flex items-center gap-3 min-w-0 pr-2" }, icon && React.createElement("div", { className: `w-9 h-9 rounded-xl ${iconBg || "bg-gradient-to-br from-indigo-500 to-indigo-700"} flex items-center justify-center font-bold text-white shadow-md text-base shrink-0` }, icon), React.createElement("div", { className: "min-w-0" }, typeof title === "string" ? React.createElement("h2", { className: "text-base font-bold text-white m-0 truncate" }, title) : title, subtitle && React.createElement("p", { className: "text-xs text-slate-400 font-medium m-0 truncate" }, subtitle))), React.createElement("div", { className: "flex items-center gap-2 shrink-0" }, headerExtra, onClose && React.createElement("button", {
			type: "button",
			className: "text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors text-lg leading-none cursor-pointer w-8 h-8 flex items-center justify-center",
			onClick: onClose,
			title: "Close"
		}, "✕"))) : null, subHeader, React.createElement("div", { className: bodyClassName }, children), footer && React.createElement("div", { className: footerClassName }, footer)));
	}
	//#endregion
	//#region dashboard/src/utils/grillParser.js
	/**
	* Parser for Grill-with-Docs interview questions and human replies.
	*/
	function parseActiveGrillQuestion(comments = [], task = {}) {
		if (!comments || comments.length === 0) {
			const meta = typeof task.metadata === "string" ? safeJsonParse(task.metadata) : task.metadata || {};
			if (meta.active_interview && !meta.last_interview_reply) return {
				questionText: meta.active_interview.question || "Technical Decision Required",
				options: meta.active_interview.options || [],
				contextText: meta.active_interview.context || "",
				hasReplied: false
			};
			return null;
		}
		for (let i = comments.length - 1; i >= 0; i--) {
			const c = comments[i];
			const body = c.body || "";
			if (body.includes("Grill-with-Docs: Decision Required") || body.includes("Grill-with-Docs") && (body.includes("Option A") || body.includes("Question:"))) {
				const replyComment = comments.slice(i + 1).find((sub) => (sub.body || "").includes("[Grill-with-Docs Human Response]") || (sub.body || "").includes("Grill-with-Docs Response") || sub.author === "human" || sub.author === "user");
				const hasReplied = Boolean(replyComment);
				let questionText = "";
				const qMatch = body.match(/\*\*Question:\*\*\s*(.+?)(?=\n\s*[-*0-9]|\n\*\*|$)/s);
				if (qMatch) questionText = qMatch[1].trim();
				else {
					const qLine = body.split("\n").find((l) => l.toLowerCase().includes("question:") || l.startsWith("###"));
					questionText = qLine ? qLine.replace(/^###\s*|^\*\*Question:\*\*\s*/i, "").trim() : "Technical & Architectural Decision Required";
				}
				const options = [];
				const optionHeaderRegex = /(?:^|\n)(?:[-*]\s*(?:\[[\sXx]?\]\s*)?|\d+\.\s*)\*\*Option\s+([A-Z0-9]+):\*\*\s*/gi;
				const matches = [];
				let m;
				while ((m = optionHeaderRegex.exec(body)) !== null) matches.push({
					id: m[1].trim(),
					index: m.index,
					headerEnd: m.index + m[0].length
				});
				const docContextIdx = body.search(/\n\s*\*\*Documentation Context:\*\*/i);
				const endLimit = docContextIdx !== -1 ? docContextIdx : body.length;
				if (matches.length > 0) matches.forEach((cur, idx) => {
					const nextStart = idx + 1 < matches.length ? matches[idx + 1].index : endLimit;
					const rawChunk = body.slice(cur.headerEnd, nextStart).trim();
					const firstLine = rawChunk.split("\n")[0].trim();
					const isRecommended = rawChunk.includes("(Recommended)") || firstLine.includes("(Recommended)");
					options.push({
						id: cur.id,
						key: `Option ${cur.id}`,
						label: `Option ${cur.id}: ${firstLine.replace(/\(Recommended\)/i, "").trim()}`,
						details: firstLine,
						content: rawChunk,
						isRecommended
					});
				});
				else {
					const fallbackRegex = /(?:[-*]\s*|\d+\.\s*)Option\s+([A-Z0-9]+)[:\s-]+([^\n]+)/gi;
					let fbMatch;
					while ((fbMatch = fallbackRegex.exec(body)) !== null) options.push({
						id: fbMatch[1].trim(),
						key: `Option ${fbMatch[1].trim()}`,
						label: `Option ${fbMatch[1].trim()}: ${fbMatch[2].trim()}`,
						details: fbMatch[2].trim(),
						content: fbMatch[2].trim(),
						isRecommended: fbMatch[2].includes("(Recommended)")
					});
				}
				let contextText = "";
				const ctxMatch = body.match(/\*\*Documentation Context:\*\*\s*(.+?)(?=\n\n|$)/s);
				if (ctxMatch) contextText = ctxMatch[1].trim();
				return {
					commentId: c.id,
					author: c.author,
					createdAt: c.created_at,
					questionText,
					options,
					contextText,
					rawBody: body,
					hasReplied,
					lastReply: replyComment ? replyComment.body : null
				};
			}
		}
		return null;
	}
	function safeJsonParse(val) {
		try {
			return JSON.parse(val);
		} catch {
			return {};
		}
	}
	//#endregion
	//#region dashboard/src/components/MarkdownView.jsx
	/**
	* Lightweight, zero-dependency Markdown renderer for Zero Factory dashboard.
	* Parses headers, bold, italics, inline code, links, lists, and Pros/Cons callouts.
	*/
	function parseInline(text) {
		if (!text) return null;
		return text.split(/(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g).map((part, index) => {
			if (!part) return null;
			if (part.startsWith("`") && part.endsWith("`") && part.length >= 2) {
				const code = part.slice(1, -1);
				return React.createElement("code", {
					key: index,
					className: "px-1.5 py-0.5 mx-0.5 rounded font-mono text-[0.6875rem] bg-slate-800 text-indigo-200 border border-slate-700/60 font-medium"
				}, code);
			}
			if (part.startsWith("**") && part.endsWith("**") && part.length >= 4) {
				const boldText = part.slice(2, -2);
				return React.createElement("strong", {
					key: index,
					className: "font-semibold text-white"
				}, parseInline(boldText));
			}
			if (part.startsWith("*") && part.endsWith("*") && part.length >= 2) {
				const italicText = part.slice(1, -1);
				return React.createElement("em", {
					key: index,
					className: "italic text-slate-200"
				}, parseInline(italicText));
			}
			const linkMatch = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
			if (linkMatch) return React.createElement("a", {
				key: index,
				href: linkMatch[2],
				target: "_blank",
				rel: "noopener noreferrer",
				className: "text-indigo-400 hover:text-indigo-300 underline underline-offset-2 transition-colors",
				onClick: (e) => e.stopPropagation()
			}, linkMatch[1]);
			return part;
		});
	}
	function MarkdownView({ content = "", className = "" }) {
		if (!content) return null;
		const rawLines = content.split("\n");
		const elements = [];
		let currentList = null;
		const flushList = () => {
			if (currentList) {
				elements.push(React.createElement(currentList.type, {
					key: `list-${elements.length}`,
					className: "space-y-1 my-1.5 pl-4 list-outside text-slate-300 " + (currentList.type === "ul" ? "list-disc" : "list-decimal")
				}, currentList.items.map((item, idx) => {
					const isPros = item.trim().startsWith("Pros:") || item.trim().startsWith("- Pros:");
					const isCons = item.trim().startsWith("Cons:") || item.trim().startsWith("- Cons:");
					if (isPros) return React.createElement("li", {
						key: idx,
						className: "leading-relaxed text-slate-200"
					}, React.createElement("span", { className: "inline-flex items-center gap-1 font-semibold text-emerald-400 bg-emerald-950/40 border border-emerald-500/30 px-1.5 py-0.5 rounded text-[0.6875rem] mr-1.5" }, "✓ Pros:"), parseInline(item.replace(/^[-*]?\s*Pros:\s*/i, "")));
					if (isCons) return React.createElement("li", {
						key: idx,
						className: "leading-relaxed text-slate-200"
					}, React.createElement("span", { className: "inline-flex items-center gap-1 font-semibold text-rose-300 bg-rose-950/40 border border-rose-500/30 px-1.5 py-0.5 rounded text-[0.6875rem] mr-1.5" }, "✗ Cons:"), parseInline(item.replace(/^[-*]?\s*Cons:\s*/i, "")));
					return React.createElement("li", {
						key: idx,
						className: "leading-relaxed text-slate-300"
					}, parseInline(item));
				})));
				currentList = null;
			}
		};
		for (let i = 0; i < rawLines.length; i++) {
			const trimmed = rawLines[i].trim();
			if (!trimmed) {
				flushList();
				continue;
			}
			if (trimmed.startsWith("### ")) {
				flushList();
				elements.push(React.createElement("h4", {
					key: `h3-${i}`,
					className: "text-xs font-bold text-indigo-300 mt-2.5 mb-1 flex items-center gap-1.5"
				}, parseInline(trimmed.replace(/^###\s+/, ""))));
				continue;
			}
			if (trimmed.startsWith("## ")) {
				flushList();
				elements.push(React.createElement("h3", {
					key: `h2-${i}`,
					className: "text-sm font-bold text-slate-100 mt-3 mb-1"
				}, parseInline(trimmed.replace(/^##\s+/, ""))));
				continue;
			}
			if (trimmed.startsWith("# ")) {
				flushList();
				elements.push(React.createElement("h2", {
					key: `h1-${i}`,
					className: "text-base font-bold text-white mt-3.5 mb-1.5"
				}, parseInline(trimmed.replace(/^#\s+/, ""))));
				continue;
			}
			const bulletMatch = trimmed.match(/^[-*]\s+(.*)$/);
			if (bulletMatch) {
				if (!currentList || currentList.type !== "ul") {
					flushList();
					currentList = {
						type: "ul",
						items: []
					};
				}
				currentList.items.push(bulletMatch[1]);
				continue;
			}
			const numMatch = trimmed.match(/^\d+\.\s+(.*)$/);
			if (numMatch) {
				if (!currentList || currentList.type !== "ol") {
					flushList();
					currentList = {
						type: "ol",
						items: []
					};
				}
				currentList.items.push(numMatch[1]);
				continue;
			}
			flushList();
			elements.push(React.createElement("p", {
				key: `p-${i}`,
				className: "my-1 leading-relaxed text-slate-300"
			}, parseInline(trimmed)));
		}
		flushList();
		return React.createElement("div", { className: `text-xs leading-relaxed space-y-1 ${className}` }, elements);
	}
	//#endregion
	//#region dashboard/src/components/GrillInterviewPanel.jsx
	function GrillInterviewPanel({ task, loadTaskDetails, loadTasksAndStats, showToast = () => {} }) {
		if (!task) return null;
		const interview = parseActiveGrillQuestion(task.comments || [], task);
		const isTriage = task.status === "triage";
		const [customNotes, setCustomNotes] = useState("");
		const [submittingKey, setSubmittingKey] = useState(null);
		const [isSubmitting, setIsSubmitting] = useState(false);
		const [isDispatchingTriage, setIsDispatchingTriage] = useState(false);
		const handleStartTriage = async () => {
			setIsDispatchingTriage(true);
			try {
				await fetchJSON(`${API_BASE}/tasks/${task.id}/triage`, { method: "POST" });
				showToast("🧭 Grill-with-Docs triage dispatched to zf-orchestrator", "success");
				await loadTaskDetails(task.id);
				loadTasksAndStats();
			} catch (err) {
				showToast(`Failed to dispatch triage: ${err.message}`, "error");
			} finally {
				setIsDispatchingTriage(false);
			}
		};
		const handleOptionSubmit = async (opt) => {
			setIsSubmitting(true);
			setSubmittingKey(opt.key);
			try {
				await fetchJSON(`${API_BASE}/tasks/${task.id}/interview-reply`, {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({
						selection: opt.label,
						notes: "",
						advance: true
					})
				});
				showToast(`Selected ${opt.key}! zf-orchestrator resuming triage...`, "success");
				await loadTaskDetails(task.id);
				loadTasksAndStats();
			} catch (err) {
				showToast(`Failed to submit response: ${err.message}`, "error");
			} finally {
				setIsSubmitting(false);
				setSubmittingKey(null);
			}
		};
		const handleCustomSubmit = async (e) => {
			if (e) e.preventDefault();
			if (!customNotes.trim()) {
				showToast("Please enter your custom answer before submitting", "warning");
				return;
			}
			setIsSubmitting(true);
			setSubmittingKey("custom");
			try {
				await fetchJSON(`${API_BASE}/tasks/${task.id}/interview-reply`, {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({
						selection: `Custom / Other: ${customNotes.trim()}`,
						notes: customNotes.trim(),
						advance: true
					})
				});
				showToast("Custom answer submitted! zf-orchestrator resuming triage...", "success");
				setCustomNotes("");
				await loadTaskDetails(task.id);
				loadTasksAndStats();
			} catch (err) {
				showToast(`Failed to submit custom answer: ${err.message}`, "error");
			} finally {
				setIsSubmitting(false);
				setSubmittingKey(null);
			}
		};
		if (interview) return React.createElement("div", { className: "rounded-xl border p-4 space-y-4 shadow-sm transition-all " + (interview.hasReplied ? "bg-slate-950/60 border-slate-800" : "bg-indigo-950/30 border-indigo-500/40 shadow-indigo-950/20") }, React.createElement("div", { className: "flex items-center justify-between gap-2 flex-wrap" }, React.createElement("div", { className: "flex items-center gap-2" }, React.createElement("span", { className: "text-base" }, "🧭"), React.createElement("span", { className: "font-semibold text-xs text-indigo-200 tracking-wide uppercase" }, "Grill-with-Docs • Requirements & Design Interview")), React.createElement("span", { className: "inline-flex items-center gap-1.5 text-[0.6875rem] font-semibold px-2.5 py-0.5 rounded-full border " + (interview.hasReplied ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-300" : "bg-amber-500/20 border-amber-500/40 text-amber-300 animate-pulse") }, React.createElement("span", { className: "w-2 h-2 rounded-full " + (interview.hasReplied ? "bg-emerald-400" : "bg-amber-400") }), interview.hasReplied ? "Decision Recorded" : "Awaiting Human Input")), React.createElement("div", { className: "bg-slate-900/90 border border-slate-800 rounded-lg p-3.5 space-y-2 text-xs text-slate-200" }, React.createElement("div", { className: "font-semibold text-indigo-300 flex items-center gap-1.5" }, React.createElement("span", null, "🎯"), React.createElement("span", null, "Design Decision / Clarification Question:")), React.createElement("div", { className: "pl-5" }, React.createElement(MarkdownView, { content: interview.questionText })), interview.contextText && React.createElement("div", { className: "mt-2 pt-2 border-t border-slate-800 text-[0.6875rem] text-slate-400 space-y-1" }, React.createElement("div", { className: "flex items-center gap-1.5 font-semibold text-slate-400" }, React.createElement("span", null, "📚"), React.createElement("span", null, "Documentation Context:")), React.createElement("div", { className: "pl-5 font-mono text-[0.625rem] text-slate-300" }, React.createElement(MarkdownView, { content: interview.contextText })))), interview.hasReplied && React.createElement("div", { className: "space-y-2.5" }, React.createElement("div", { className: "p-3 rounded-lg bg-emerald-950/30 border border-emerald-500/30 text-xs text-emerald-300 space-y-1.5" }, React.createElement("div", { className: "flex items-center justify-between gap-2" }, React.createElement("span", { className: "font-semibold flex items-center gap-1.5" }, React.createElement("span", null, "✓"), React.createElement("span", null, "Decision recorded. zf-orchestrator is grounding decisions into repository substrate.")), React.createElement("button", {
			type: "button",
			onClick: handleStartTriage,
			disabled: isDispatchingTriage,
			className: "shrink-0 px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-[0.6875rem] text-slate-200 border border-slate-700 cursor-pointer"
		}, isDispatchingTriage ? "Running..." : "Re-run Triage ↻")), interview.lastReply && React.createElement("div", { className: "pt-1 text-[0.6875rem] text-slate-300 border-t border-emerald-500/20" }, React.createElement(MarkdownView, { content: interview.lastReply })))), !interview.hasReplied && React.createElement("div", { className: "space-y-3" }, interview.options && interview.options.length > 0 && React.createElement("div", { className: "space-y-2" }, React.createElement("div", { className: "flex items-center justify-between gap-2" }, React.createElement("label", { className: "block text-[0.6875rem] font-semibold uppercase tracking-wider text-slate-400" }, "Click an Option Button to Choose:"), React.createElement("span", { className: "text-[0.625rem] text-slate-500" }, "1-click selection • no typing required")), React.createElement("div", { className: "grid grid-cols-1 gap-2.5" }, interview.options.map((opt) => {
			const isThisSubmitting = isSubmitting && submittingKey === opt.key;
			return React.createElement("div", {
				key: opt.id,
				className: "p-3.5 rounded-lg border text-xs transition-all duration-150 space-y-2 " + (opt.isRecommended ? "bg-indigo-950/25 border-indigo-500/40 hover:border-indigo-400/80 shadow-xs" : "bg-slate-900/60 border-slate-800 hover:border-slate-700 text-slate-300")
			}, React.createElement("div", { className: "flex items-center justify-between gap-2 flex-wrap" }, React.createElement("div", { className: "flex items-center gap-2" }, React.createElement("span", { className: "px-2 py-0.5 rounded font-mono text-[0.6875rem] font-bold border " + (opt.isRecommended ? "bg-indigo-500/30 text-indigo-200 border-indigo-500/50" : "bg-slate-800 text-slate-300 border-slate-700") }, opt.key), opt.isRecommended && React.createElement("span", { className: "px-2 py-0.5 rounded-full text-[0.625rem] font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 flex items-center gap-1" }, "⭐ Recommended")), React.createElement("button", {
				type: "button",
				onClick: () => handleOptionSubmit(opt),
				disabled: isSubmitting,
				className: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white transition-all cursor-pointer shadow-xs disabled:opacity-50 disabled:cursor-not-allowed " + (opt.isRecommended ? "bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 shadow-indigo-600/30" : "bg-slate-800 hover:bg-slate-700 border border-slate-700 hover:border-slate-600 text-slate-200")
			}, isThisSubmitting ? "Submitting..." : `Choose ${opt.key} ${opt.isRecommended ? "★" : ""} →`)), React.createElement("div", { className: "pt-1 text-slate-300" }, React.createElement(MarkdownView, { content: opt.content })));
		}))), React.createElement("form", {
			onSubmit: handleCustomSubmit,
			className: "p-3.5 rounded-lg border border-slate-800 bg-slate-900/50 space-y-2.5 text-xs"
		}, React.createElement("div", { className: "flex items-center justify-between gap-2" }, React.createElement("div", { className: "font-semibold text-slate-300 flex items-center gap-1.5" }, React.createElement("span", null, "✏️"), React.createElement("span", null, "Other Answer / Custom Specifications:")), React.createElement("span", { className: "text-[0.625rem] text-slate-500" }, "Optional • for custom constraints or alternative ideas")), React.createElement("textarea", {
			rows: 2,
			value: customNotes,
			onChange: (e) => setCustomNotes(e.target.value),
			placeholder: "Type your custom decision, hybrid preference, or specific trade-offs here...",
			className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors zfk-scrollbar"
		}), React.createElement("div", { className: "flex items-center justify-end gap-2" }, React.createElement("button", {
			type: "submit",
			disabled: isSubmitting || !customNotes.trim(),
			className: "px-3.5 py-1.5 rounded-lg text-xs font-semibold text-white bg-slate-800 hover:bg-slate-700 active:bg-slate-800 border border-slate-700 transition-colors cursor-pointer shadow-xs disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
		}, isSubmitting && submittingKey === "custom" ? "Submitting..." : "Submit Custom Answer →")))));
		if (isTriage) return React.createElement("div", { className: "rounded-xl border border-indigo-500/30 bg-indigo-950/20 p-3.5 flex items-center justify-between gap-3 flex-wrap" }, React.createElement("div", { className: "space-y-0.5 min-w-0" }, React.createElement("div", { className: "text-xs font-semibold text-indigo-300 flex items-center gap-1.5" }, React.createElement("span", null, "🧭"), React.createElement("span", null, "Grill-with-Docs Triage Available")), React.createElement("div", { className: "text-[0.6875rem] text-slate-400 leading-snug" }, "Dispatch zf-orchestrator to inspect repo docs, interview trade-offs, and formulate acceptance criteria for zf-builder.")), React.createElement("button", {
			type: "button",
			onClick: handleStartTriage,
			disabled: isDispatchingTriage,
			className: "shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 transition-colors shadow-xs shadow-indigo-600/30 cursor-pointer disabled:opacity-50"
		}, React.createElement("span", null, "🧭"), React.createElement("span", null, isDispatchingTriage ? "Dispatching..." : "Triage with Grill-with-Docs")));
		return null;
	}
	//#endregion
	//#region dashboard/src/modals/TaskDetailModal.jsx
	function TaskDetailModal(props) {
		const { selectedTask, setSelectedTask, boards = [], handleUpdateTask, handleDeleteTask, handleRunAgent, handleStopTaskSession, stoppingSessionId, activeRunningTaskId, newCommentText, setNewCommentText, handleAddComment, handleAddCommentSubmit = handleAddComment, loadTasksAndStats, loadTaskDetails, showToast = () => {}, selectedSessionIdx = null, setSelectedSessionIdx = () => {}, refreshSessionProgress = () => {}, handleAdvanceTask = () => {}, tasks = [] } = props;
		const [depTaskId, setDepTaskId] = React.useState("");
		const [depLinkType, setDepLinkType] = React.useState("blocks");
		const handleLinkDependency = async () => {
			if (!depTaskId || !selectedTask) return;
			try {
				await fetchJSON(API_BASE + "/tasks/" + selectedTask.id + "/dependencies", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({
						parent_id: depTaskId,
						link_type: depLinkType
					})
				});
				showToast("Linked dependency #" + depTaskId + " (" + depLinkType + ")", "success");
				setDepTaskId("");
				loadTaskDetails(selectedTask.id);
				loadTasksAndStats();
			} catch (err) {
				showToast("Failed to link dependency: " + err.message, "error");
			}
		};
		const handleRemoveDependency = async (parentId) => {
			if (!selectedTask) return;
			try {
				await fetchJSON(API_BASE + "/tasks/" + selectedTask.id + "/dependencies/" + parentId, { method: "DELETE" });
				showToast("Removed dependency link #" + parentId, "info");
				loadTaskDetails(selectedTask.id);
				loadTasksAndStats();
			} catch (err) {
				showToast("Failed to unlink: " + err.message, "error");
			}
		};
		if (!selectedTask) return null;
		return React.createElement(Modal, {
			isOpen: Boolean(selectedTask),
			onClose: () => setSelectedTask(null),
			title: React.createElement("div", { className: "flex items-center gap-3 min-w-0" }, React.createElement("span", { className: "font-mono text-xs font-semibold px-2 py-0.5 rounded bg-slate-800 text-slate-400 border border-slate-700/60" }, selectedTask.id), React.createElement("h2", { className: "text-base font-semibold text-white truncate m-0" }, selectedTask.title)),
			bodyClassName: "p-6 space-y-5 overflow-y-auto zfk-scrollbar flex-1",
			footerClassName: "flex items-center justify-between px-6 py-3.5 border-t border-slate-800 bg-slate-900/50 shrink-0",
			footer: React.createElement(React.Fragment, null, React.createElement("button", {
				type: "button",
				className: "px-3.5 py-1.5 rounded-lg text-xs font-medium text-rose-400 hover:text-rose-300 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 transition-colors cursor-pointer",
				onClick: () => handleDeleteTask(selectedTask.id)
			}, "Delete Task"), React.createElement("div", { className: "flex items-center gap-2" }, selectedTask.status === "triage" && React.createElement("button", {
				type: "button",
				className: "px-3.5 py-1.5 rounded-lg text-xs font-semibold text-indigo-300 hover:text-white bg-indigo-950/70 hover:bg-indigo-900 border border-indigo-500/40 transition-colors cursor-pointer flex items-center gap-1.5 shadow-xs",
				onClick: async () => {
					try {
						await fetchJSON("/api/plugins/zerofactory/tasks/" + selectedTask.id + "/triage", { method: "POST" });
						showToast("🧭 Grill-with-Docs triage dispatched to zf-orchestrator", "success");
						loadTaskDetails(selectedTask.id);
						loadTasksAndStats();
					} catch (err) {
						showToast("Triage dispatch failed: " + err.message, "error");
					}
				}
			}, "🧭 Grill Triage"), React.createElement("button", {
				type: "button",
				className: "px-4 py-1.5 rounded-lg text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-500 transition-colors cursor-pointer shadow-xs shadow-indigo-600/30",
				onClick: () => handleAdvanceTask(selectedTask)
			}, "Advance Stage →")))
		}, React.createElement("div", { className: "grid grid-cols-1 sm:grid-cols-2 gap-4" }, React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Status"), React.createElement("select", {
			className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors cursor-pointer",
			value: selectedTask.status,
			onChange: async (e) => {
				const newStatus = e.target.value;
				await fetchJSON(API_BASE + "/tasks/" + selectedTask.id + "/move", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({ status: newStatus })
				});
				loadTaskDetails(selectedTask.id);
				loadTasksAndStats();
			}
		}, COLUMNS.map((c) => React.createElement("option", {
			key: c.id,
			value: c.id
		}, c.title)))), React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Assignee"), React.createElement("select", {
			className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors cursor-pointer",
			value: selectedTask.assignee || "unassigned",
			onChange: async (e) => {
				const newAssignee = e.target.value;
				await fetchJSON(API_BASE + "/tasks/" + selectedTask.id, {
					method: "PATCH",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({ assignee: newAssignee })
				});
				loadTaskDetails(selectedTask.id);
				loadTasksAndStats();
			}
		}, [
			{
				id: "unassigned",
				label: "Unassigned"
			},
			{
				id: "human",
				label: "Human"
			},
			{
				id: "zf-builder",
				label: "ZF Builder"
			},
			{
				id: "zf-reviewer",
				label: "ZF Reviewer"
			},
			{
				id: "zf-orchestrator",
				label: "ZF Orchestrator"
			}
		].map((r) => React.createElement("option", {
			key: r.id,
			value: r.id
		}, r.label))))), React.createElement("div", { className: "grid grid-cols-1 sm:grid-cols-2 gap-4" }, React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Priority"), React.createElement("select", {
			className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors cursor-pointer",
			value: selectedTask.priority || "P2",
			onChange: async (e) => {
				const newPrio = e.target.value;
				await fetchJSON(API_BASE + "/tasks/" + selectedTask.id, {
					method: "PATCH",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({ priority: newPrio })
				});
				loadTaskDetails(selectedTask.id);
				loadTasksAndStats();
			}
		}, [
			"P0",
			"P1",
			"P2",
			"P3"
		].map((p) => React.createElement("option", {
			key: p,
			value: p
		}, p)))), React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Target Repository & Board"), React.createElement("div", { className: "flex items-center gap-2 px-3 py-2 rounded-lg bg-slate-950 border border-slate-800 text-xs font-mono min-h-[34px]" }, selectedTask.repo_alias ? React.createElement("span", { className: "px-2 py-0.5 rounded font-semibold bg-teal-950/80 text-teal-300 border border-teal-800/60" }, "📦 " + selectedTask.repo_alias) : React.createElement("span", { className: "text-slate-400" }, "Default Repo"), selectedTask.board_slug && React.createElement("span", { className: "text-slate-500 text-[11px]" }, "(" + selectedTask.board_slug + ")")))), React.createElement("div", { className: "space-y-1.5" }, React.createElement("div", { className: "flex items-center justify-between" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Pull Request URL"), selectedTask.pr_url && React.createElement("a", {
			href: selectedTask.pr_url,
			target: "_blank",
			rel: "noopener noreferrer",
			className: "inline-flex items-center gap-1 text-[11px] text-purple-400 hover:text-purple-300 font-medium transition-colors"
		}, renderPrIcon("w-2.5 h-2.5 shrink-0"), "Open Link ↗")), React.createElement("div", { className: "flex items-center gap-2" }, React.createElement("input", {
			key: selectedTask.id + (selectedTask.pr_url || ""),
			defaultValue: selectedTask.pr_url || "",
			placeholder: "e.g. https://github.com/owner/repo/pull/123",
			className: "flex-1 bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-purple-500 focus:ring-1 focus:ring-purple-500 transition-colors font-mono",
			onBlur: async (e) => {
				const newPr = e.target.value.trim();
				if (newPr !== (selectedTask.pr_url || "")) try {
					await fetchJSON(API_BASE + "/tasks/" + selectedTask.id, {
						method: "PATCH",
						headers: { "Content-Type": "application/json" },
						body: JSON.stringify({ pr_url: newPr || null })
					});
					loadTaskDetails(selectedTask.id);
					loadTasksAndStats();
					showToast("Updated Pull Request URL", "success");
				} catch (err) {
					showToast("Failed to update PR URL: " + err.message, "error");
				}
			},
			onKeyDown: (e) => {
				if (e.key === "Enter") e.target.blur();
			}
		}))), React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Description / Acceptance Criteria"), React.createElement("div", { className: "bg-slate-950/60 border border-slate-800/80 rounded-lg p-3.5 text-xs leading-relaxed text-slate-300 whitespace-pre-wrap" }, selectedTask.description || "(No description provided)")), React.createElement(GrillInterviewPanel, {
			task: selectedTask,
			loadTaskDetails,
			loadTasksAndStats,
			showToast
		}), selectedTask.workspace_path && React.createElement("div", { className: "p-3 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-xs space-y-1" }, React.createElement("strong", { className: "text-emerald-400 font-semibold" }, "Git Worktree Active: "), React.createElement("span", { className: "text-indigo-300 font-mono text-[0.6875rem] break-all" }, selectedTask.workspace_path), selectedTask.branch_name && React.createElement("div", { className: "text-slate-400 text-[0.6875rem] mt-0.5" }, "Branch: " + selectedTask.branch_name)), selectedTask.pr_url && React.createElement("div", { className: "p-3.5 bg-purple-500/10 border border-purple-500/25 rounded-lg text-xs space-y-2 shadow-xs" }, React.createElement("div", { className: "flex items-center justify-between gap-2 flex-wrap" }, React.createElement("div", { className: "flex items-center gap-2 text-purple-300 font-semibold" }, renderPrIcon("w-4 h-4 text-purple-400 shrink-0"), React.createElement("span", null, "Pull Request:"), React.createElement("span", { className: "font-mono font-bold bg-purple-500/20 px-2 py-0.5 rounded border border-purple-500/30 text-purple-200" }, formatPrLabel(selectedTask.pr_url))), React.createElement("a", {
			href: selectedTask.pr_url,
			target: "_blank",
			rel: "noopener noreferrer",
			className: "inline-flex items-center gap-1.5 px-3 py-1 rounded-lg bg-purple-600 hover:bg-purple-500 text-white font-semibold text-xs shadow-md shadow-purple-600/20 transition-all duration-150 cursor-pointer"
		}, "View on GitHub ↗")), React.createElement("div", { className: "flex items-center justify-between gap-2 pt-1 border-t border-purple-500/20 text-slate-300" }, React.createElement("a", {
			href: selectedTask.pr_url,
			target: "_blank",
			rel: "noopener noreferrer",
			className: "text-purple-300 hover:text-purple-200 font-mono text-[0.6875rem] break-all underline decoration-purple-500/50 hover:decoration-purple-300 transition-colors"
		}, selectedTask.pr_url), React.createElement("button", {
			type: "button",
			onClick: () => {
				if (navigator.clipboard) navigator.clipboard.writeText(selectedTask.pr_url);
				showToast("Copied PR URL to clipboard!", "success");
			},
			className: "shrink-0 px-2 py-0.5 rounded text-[0.625rem] bg-purple-500/20 hover:bg-purple-500/30 text-purple-300 border border-purple-500/30 cursor-pointer transition-colors",
			title: "Copy PR URL"
		}, "Copy"))), (() => {
			const prog = selectedTask.session_progress;
			const rawSessions = prog && prog.sessions && prog.sessions.length > 0 ? prog.sessions : prog && prog.has_session ? [prog] : [];
			if (rawSessions.length === 0 && selectedTask.status !== "running") return null;
			const taskSessions = rawSessions.slice().reverse();
			const activeIdx = selectedSessionIdx >= 0 && selectedSessionIdx < taskSessions.length ? selectedSessionIdx : 0;
			const currentSession = taskSessions[activeIdx] || prog || {};
			const isOngoing = currentSession.status === "ongoing" || currentSession.is_active || prog && prog.is_alive && (currentSession.session_id ? currentSession.session_id === prog.session_id : activeIdx === 0);
			const agentRole = currentSession.agent || selectedTask.assignee || "zf-builder";
			const agentIcon = currentSession.agent_icon || (agentRole === "zf-reviewer" ? "🔍" : agentRole === "zf-orchestrator" ? "🧭" : "🔨");
			const agentLabel = currentSession.agent_label || (agentRole === "zf-reviewer" ? "Reviewer" : agentRole === "zf-orchestrator" ? "Orchestrator" : "Builder");
			const basePath = typeof window !== "undefined" && window.__HERMES_BASE_PATH__ ? "/" + String(window.__HERMES_BASE_PATH__).replace(/^\/|\/$/g, "") : "";
			const curSid = currentSession.session_id || prog && prog.session_id;
			const chatUrl = curSid ? basePath + "/chat?resume=" + encodeURIComponent(curSid) + (agentRole ? "&profile=" + encodeURIComponent(agentRole) : "") : null;
			return React.createElement("div", { className: "bg-slate-950/80 border border-indigo-500/30 rounded-xl p-4 space-y-3.5 shadow-sm" }, taskSessions.length > 1 && React.createElement("div", { className: "space-y-1.5 pb-3 border-b border-slate-800/80" }, React.createElement("div", { className: "text-[11px] font-semibold text-slate-400 uppercase tracking-wider flex items-center justify-between" }, React.createElement("span", null, "AI Sessions (" + taskSessions.length + ")"), React.createElement("span", { className: "text-slate-500 font-normal lowercase" }, "click session to inspect")), React.createElement("div", { className: "flex items-center gap-1.5 overflow-x-auto pb-1 zfk-scrollbar" }, taskSessions.map((s, sIdx) => {
				const sIsOngoing = s.status === "ongoing" || s.is_active || prog && prog.is_alive && (s.session_id ? s.session_id === prog.session_id : sIdx === 0);
				const sIcon = s.agent_icon || (s.agent === "zf-reviewer" ? "🔍" : s.agent === "zf-orchestrator" ? "🧭" : "🔨");
				const sLabel = s.agent_label || (s.agent === "zf-reviewer" ? "Reviewer" : s.agent === "zf-orchestrator" ? "Orchestrator" : "Builder");
				const sNum = taskSessions.length - sIdx;
				return React.createElement("button", {
					key: s.session_id || sIdx,
					type: "button",
					className: "flex items-center gap-1.5 px-2.5 py-1 rounded-lg text-xs font-medium border transition-all cursor-pointer shrink-0 " + (sIdx === activeIdx ? "bg-indigo-600/30 border-indigo-400 text-white font-semibold shadow-xs" : "bg-slate-900 border-slate-800 text-slate-400 hover:text-slate-200 hover:bg-slate-800/80"),
					onClick: () => setSelectedSessionIdx(sIdx)
				}, React.createElement("span", null, sIcon), React.createElement("span", null, sLabel + " #" + sNum), React.createElement("span", { className: "w-2 h-2 rounded-full " + (sIsOngoing ? "bg-emerald-400 zfk-pulse-active" : "bg-slate-600") }), s.turn_count ? React.createElement("span", { className: "text-[10px] text-slate-400 font-mono" }, s.turn_count + "t") : null);
			}))), React.createElement("div", { className: "flex flex-wrap items-center justify-between gap-2 pb-2" }, React.createElement("div", { className: "flex items-center gap-2 flex-wrap" }, React.createElement("span", { className: "w-2.5 h-2.5 rounded-full shrink-0 " + (isOngoing ? "bg-emerald-400 zfk-pulse-active" : "bg-slate-500") }), React.createElement("span", { className: "font-semibold text-xs text-white flex items-center gap-1.5" }, agentIcon, agentLabel, React.createElement("span", { className: "font-normal text-slate-400" }, isOngoing ? "• Ongoing Execution" : "• Finished Session")), prog && prog.worker_pid && isOngoing && React.createElement("span", { className: "text-[0.625rem] font-mono px-2 py-0.5 rounded-full bg-slate-800 text-slate-400 border border-slate-700/60" }, "PID: " + prog.worker_pid), curSid && React.createElement("span", {
				className: "text-xs font-mono font-medium text-purple-300 truncate max-w-[160px]",
				title: "Session ID: " + curSid
			}, curSid)), React.createElement("div", { className: "flex items-center gap-2" }, isOngoing && React.createElement("button", {
				type: "button",
				disabled: stoppingSessionId === (curSid || selectedTask.id),
				className: "inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-semibold bg-rose-950/70 hover:bg-rose-900 text-rose-300 border border-rose-800/80 hover:border-rose-800/60 transition-colors cursor-pointer shadow-xs disabled:opacity-50",
				onClick: () => handleStopTaskSession(selectedTask.id, curSid),
				title: "Safely terminate worker process group and stop session"
			}, React.createElement("span", null, "⏹"), React.createElement("span", null, stoppingSessionId === (curSid || selectedTask.id) ? "Stopping..." : "Stop Session")), chatUrl && React.createElement("a", {
				href: chatUrl,
				className: "inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium bg-indigo-600 hover:bg-indigo-500 text-white transition-colors cursor-pointer shadow-xs",
				target: "_blank",
				rel: "noreferrer",
				title: "Open session in Hermes Chat"
			}, "Open Chat ↗"), React.createElement("button", {
				type: "button",
				className: "inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-300 hover:text-white border border-slate-700/60 transition-colors cursor-pointer",
				onClick: () => refreshSessionProgress(selectedTask.id),
				title: "Refresh session status"
			}, "🔄 Refresh"))), React.createElement("div", { className: "grid grid-cols-2 sm:grid-cols-4 gap-2.5" }, React.createElement("div", { className: "bg-slate-900/80 border border-slate-800/80 rounded-lg p-2.5 flex flex-col gap-1" }, React.createElement("span", { className: "text-[0.625rem] font-semibold uppercase tracking-wider text-purple-400/90" }, "Session ID"), React.createElement("span", {
				className: "text-xs font-medium text-purple-300 font-mono truncate",
				title: curSid
			}, curSid || "Detecting...")), React.createElement("div", { className: "bg-slate-900/80 border border-slate-800/80 rounded-lg p-2.5 flex flex-col gap-1" }, React.createElement("span", { className: "text-[0.625rem] font-semibold uppercase tracking-wider text-slate-400" }, "Model"), React.createElement("span", { className: "text-xs font-medium text-slate-200 truncate" }, currentSession.model || prog && prog.model || "Default")), React.createElement("div", { className: "bg-slate-900/80 border border-slate-800/80 rounded-lg p-2.5 flex flex-col gap-1" }, React.createElement("span", { className: "text-[0.625rem] font-semibold uppercase tracking-wider text-slate-400" }, "Turns / Msgs"), React.createElement("span", { className: "text-xs font-semibold text-emerald-400 truncate" }, (currentSession.turn_count || 0) + " turns (" + (currentSession.message_count || 0) + " msgs)")), React.createElement("div", { className: "bg-slate-900/80 border border-slate-800/80 rounded-lg p-2.5 flex flex-col gap-1" }, React.createElement("span", { className: "text-[0.625rem] font-semibold uppercase tracking-wider text-slate-400" }, "Duration / Time"), React.createElement("span", { className: "text-xs font-medium text-slate-200 truncate" }, currentSession.duration_seconds ? `${Math.floor(currentSession.duration_seconds / 60)}m ${currentSession.duration_seconds % 60}s` : timeAgo(currentSession.ended_at || currentSession.started_at || prog && prog.last_active) || "Just now"))), currentSession.recent_steps && currentSession.recent_steps.length > 0 && React.createElement("div", { className: "mt-3 space-y-2" }, React.createElement("div", { className: "text-xs font-semibold text-slate-400" }, "Recent Agent Actions & Tool Executions"), React.createElement("div", { className: "space-y-1.5 max-h-48 overflow-y-auto zfk-scrollbar pr-1" }, currentSession.recent_steps.map((st) => React.createElement("div", {
				key: st.id,
				className: "bg-slate-900/60 border border-slate-800/70 rounded-md p-2 text-xs space-y-1"
			}, React.createElement("div", { className: "flex items-center gap-2" }, React.createElement("span", { className: "text-[0.625rem] font-mono uppercase px-1.5 py-0.5 rounded bg-slate-800 text-indigo-300 border border-slate-700/60" }, st.tool_name ? "tool: " + st.tool_name : st.role), React.createElement("span", { className: "text-[0.6875rem] text-slate-500" }, timeAgo(st.timestamp))), React.createElement("div", { className: "text-[0.6875rem] text-slate-400 font-mono break-all line-clamp-2" }, st.snippet))))), prog && prog.log_tail && isOngoing && React.createElement("details", { className: "mt-3 text-xs" }, React.createElement("summary", { className: "cursor-pointer text-slate-400 hover:text-slate-200 font-medium select-none outline-none py-1" }, "📄 Show Worker Process Log Output"), React.createElement("pre", { className: "mt-2 p-3 bg-black/60 border border-slate-800 rounded-lg text-[0.6875rem] font-mono text-emerald-400/90 whitespace-pre-wrap max-h-56 overflow-y-auto zfk-scrollbar" }, prog.log_tail)));
		})(), React.createElement("div", { className: "p-3.5 rounded-lg bg-slate-950/70 border border-slate-800/90 space-y-3" }, React.createElement("div", { className: "flex items-center justify-between" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-300" }, "🔗 Task Dependencies & Sequential Relations"), React.createElement("span", { className: "text-[10px] text-slate-500" }, "Parent blockers vs Peer related features")), selectedTask.parents && selectedTask.parents.length > 0 && React.createElement("div", { className: "space-y-1.5" }, React.createElement("span", { className: "text-[11px] font-semibold text-slate-400" }, "Upstream Dependencies:"), React.createElement("div", { className: "flex flex-col gap-1.5" }, selectedTask.parents.map((p) => React.createElement("div", {
			key: p.id,
			className: "flex items-center justify-between p-2 rounded-md bg-slate-900 border border-slate-800 text-xs text-slate-300 gap-2"
		}, React.createElement("div", { className: "flex items-center gap-2 min-w-0 flex-wrap" }, p.link_type === "relates_to" ? React.createElement("span", { className: "px-1.5 py-0.5 rounded text-[10px] font-bold bg-sky-950/80 text-sky-300 border border-sky-800/60" }, "🔵 Relates to") : React.createElement("span", { className: "px-1.5 py-0.5 rounded text-[10px] font-bold bg-rose-950/80 text-rose-300 border border-rose-800/60" }, "🔴 Blocks"), p.repo_alias && React.createElement("span", { className: "px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold bg-slate-800 text-teal-300 border border-slate-700/60" }, "📦 " + p.repo_alias), React.createElement("span", { className: "font-mono font-semibold text-indigo-300" }, "#" + p.id), React.createElement("span", { className: "truncate max-w-[240px]" }, p.title)), React.createElement("div", { className: "flex items-center gap-1.5 shrink-0" }, React.createElement("span", { className: "text-[0.625rem] font-medium capitalize px-1.5 py-0.5 rounded border border-slate-700 bg-slate-800 text-slate-400" }, p.status), React.createElement("button", {
			type: "button",
			className: "text-rose-400 hover:text-rose-300 px-1 text-xs font-semibold cursor-pointer",
			onClick: () => handleRemoveDependency(p.id),
			title: "Remove dependency"
		}, "✕")))))), selectedTask.children && selectedTask.children.length > 0 && React.createElement("div", { className: "space-y-1.5 pt-1" }, React.createElement("span", { className: "text-[11px] font-semibold text-slate-400" }, "Downstream Blocked / Related Tasks:"), React.createElement("div", { className: "flex flex-col gap-1.5" }, selectedTask.children.map((c) => React.createElement("div", {
			key: c.id,
			className: "flex items-center justify-between p-2 rounded-md bg-slate-900 border border-slate-800 text-xs text-slate-300 gap-2"
		}, React.createElement("div", { className: "flex items-center gap-2 min-w-0 flex-wrap" }, c.link_type === "relates_to" ? React.createElement("span", { className: "px-1.5 py-0.5 rounded text-[10px] font-bold bg-sky-950/80 text-sky-300 border border-sky-800/60" }, "🔵 Relates to") : React.createElement("span", { className: "px-1.5 py-0.5 rounded text-[10px] font-bold bg-amber-950/80 text-amber-300 border border-amber-800/60" }, "⏳ Blocked by this"), c.repo_alias && React.createElement("span", { className: "px-1.5 py-0.5 rounded text-[10px] font-mono font-semibold bg-slate-800 text-teal-300 border border-slate-700/60" }, "📦 " + c.repo_alias), React.createElement("span", { className: "font-mono font-semibold text-indigo-300" }, "#" + c.id), React.createElement("span", { className: "truncate max-w-[240px]" }, c.title)), React.createElement("span", { className: "text-[0.625rem] font-medium capitalize px-1.5 py-0.5 rounded border border-slate-700 bg-slate-800 text-slate-400" }, c.status))))), React.createElement("div", { className: "flex items-center gap-2 pt-2 border-t border-slate-800/80 flex-wrap sm:flex-nowrap" }, React.createElement("select", {
			className: "flex-1 bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-indigo-500 cursor-pointer min-w-[180px]",
			value: depTaskId,
			onChange: (e) => setDepTaskId(e.target.value)
		}, React.createElement("option", { value: "" }, "-- Link to another task --"), (tasks || []).filter((t) => t.id !== selectedTask.id && (!selectedTask.parents || !selectedTask.parents.some((p) => p.id === t.id))).map((t) => React.createElement("option", {
			key: t.id,
			value: t.id
		}, "#" + t.id + " " + (t.repo_alias ? "[" + t.repo_alias + "] " : "") + t.title + " (" + t.status + ")"))), React.createElement("select", {
			className: "bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-indigo-500 cursor-pointer shrink-0",
			value: depLinkType,
			onChange: (e) => setDepLinkType(e.target.value)
		}, React.createElement("option", { value: "blocks" }, "🔴 Blocks (Hard Blocker)"), React.createElement("option", { value: "relates_to" }, "🔵 Relates to (Soft Peer)")), React.createElement("button", {
			type: "button",
			disabled: !depTaskId,
			className: "px-3 py-1.5 rounded text-xs font-medium text-indigo-300 bg-indigo-950/70 hover:bg-indigo-900 border border-indigo-500/40 transition-colors cursor-pointer disabled:opacity-40 disabled:cursor-not-allowed shrink-0",
			onClick: handleLinkDependency
		}, "+ Link"))), React.createElement("div", { className: "space-y-2" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Discussion & Activity (" + (selectedTask.comments && selectedTask.comments.length || 0) + ")"), React.createElement("div", { className: "space-y-2 max-h-52 overflow-y-auto zfk-scrollbar pr-1" }, !selectedTask.comments || selectedTask.comments.length === 0 ? React.createElement("div", { className: "text-xs text-slate-500 italic py-2" }, "No comments yet.") : selectedTask.comments.map((c) => React.createElement("div", {
			key: c.id,
			className: "bg-slate-950/60 border border-slate-800/80 rounded-lg p-3 space-y-1.5"
		}, React.createElement("div", { className: "flex items-center justify-between text-xs" }, React.createElement("span", { className: "font-semibold text-indigo-400" }, "@" + c.author), React.createElement("span", { className: "text-[0.6875rem] text-slate-500" }, timeAgo(c.created_at))), React.createElement("div", { className: "text-xs text-slate-300 whitespace-pre-wrap leading-relaxed" }, c.body)))), React.createElement("form", {
			onSubmit: handleAddCommentSubmit,
			className: "flex gap-2 mt-2"
		}, React.createElement("input", {
			className: "flex-1 bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
			placeholder: "Write a note or comment...",
			value: newCommentText,
			onChange: (e) => setNewCommentText(e.target.value)
		}), React.createElement("button", {
			type: "submit",
			className: "px-3.5 py-2 rounded-lg text-xs font-medium bg-slate-800 hover:bg-slate-700 text-slate-200 hover:text-white border border-slate-700 transition-colors cursor-pointer"
		}, "Post"))));
	}
	//#endregion
	//#region dashboard/src/modals/NewTaskModal.jsx
	function NewTaskModal(props) {
		const { showNewTaskModal, setShowNewTaskModal, newTaskForm, setNewTaskForm, handleCreateTaskSubmit, handleCreateTask, isSubmittingTask, boards, selectedBoard } = props;
		const onSubmitHandler = handleCreateTaskSubmit || handleCreateTask;
		const chosenBoardSlug = newTaskForm.board_slug || (selectedBoard && selectedBoard !== "all" ? selectedBoard : boards[0] ? boards[0].slug : "");
		const activeBoardObj = (boards || []).find((b) => b.slug === chosenBoardSlug);
		const boardRepos = activeBoardObj && activeBoardObj.repositories || [];
		const defaultRepo = boardRepos[0];
		const currentRepoAlias = newTaskForm.repo_alias || (defaultRepo ? defaultRepo.repo_alias : "");
		return React.createElement(Modal, {
			isOpen: showNewTaskModal,
			onClose: () => setShowNewTaskModal(false),
			title: "Create New Zero Factory Task",
			bodyClassName: "p-0 flex flex-col flex-1 overflow-hidden"
		}, React.createElement("form", {
			onSubmit: onSubmitHandler,
			className: "flex flex-col flex-1 overflow-hidden m-0"
		}, React.createElement("div", { className: "p-4 sm:p-6 space-y-4 overflow-y-auto zfk-scrollbar flex-1" }, React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Task Title *"), React.createElement("input", {
			className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
			required: true,
			placeholder: "e.g. Implement caching layer for Redis",
			value: newTaskForm.title,
			onChange: (e) => setNewTaskForm({
				...newTaskForm,
				title: e.target.value
			})
		})), boards && boards.length > 0 && React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Target Board *"), React.createElement("select", {
			className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors cursor-pointer",
			value: chosenBoardSlug,
			onChange: (e) => {
				const bSlug = e.target.value;
				const bObj = (boards || []).find((x) => x.slug === bSlug);
				const dRepo = (bObj && bObj.repositories || [])[0];
				setNewTaskForm({
					...newTaskForm,
					board_slug: bSlug,
					repo_alias: dRepo ? dRepo.repo_alias : ""
				});
			}
		}, boards.map((b) => React.createElement("option", {
			key: b.slug,
			value: b.slug
		}, b.slug)))), boardRepos.length > 0 && React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Target Repository (Multi-Repo Architecture) *"), React.createElement("select", {
			className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors cursor-pointer font-mono",
			value: currentRepoAlias,
			onChange: (e) => setNewTaskForm({
				...newTaskForm,
				repo_alias: e.target.value
			})
		}, boardRepos.map((r) => React.createElement("option", {
			key: r.repo_alias,
			value: r.repo_alias
		}, r.repo_alias + " (" + (r.target_branch || "main") + ")"))), React.createElement("p", { className: "text-[10px] text-slate-500 m-0 font-sans" }, "Repository checked out as writable worktree (task/<id> branch). Sibling repos are checked out side-by-side.")), React.createElement("div", { className: "grid grid-cols-1 sm:grid-cols-2 gap-4" }, React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Assignee"), React.createElement("select", {
			className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors cursor-pointer",
			value: newTaskForm.assignee,
			onChange: (e) => setNewTaskForm({
				...newTaskForm,
				assignee: e.target.value
			})
		}, React.createElement("option", { value: "unassigned" }, "Unassigned (Auto-Assign)"), React.createElement("option", { value: "human" }, "Human (Manual Action)"), React.createElement("option", { value: "zf-builder" }, "ZF Builder"), React.createElement("option", { value: "zf-reviewer" }, "ZF Reviewer"), React.createElement("option", { value: "zf-orchestrator" }, "ZF Orchestrator"))), React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Priority"), React.createElement("select", {
			className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors cursor-pointer",
			value: newTaskForm.priority,
			onChange: (e) => setNewTaskForm({
				...newTaskForm,
				priority: e.target.value
			})
		}, React.createElement("option", { value: "P0" }, "P0 - Critical / Blocker"), React.createElement("option", { value: "P1" }, "P1 - High"), React.createElement("option", { value: "P2" }, "P2 - Normal"), React.createElement("option", { value: "P3" }, "P3 - Low")))), React.createElement("div", { className: "grid grid-cols-1 sm:grid-cols-2 gap-4" }, React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Initial Column"), React.createElement("select", {
			className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors cursor-pointer",
			value: newTaskForm.status,
			onChange: (e) => setNewTaskForm({
				...newTaskForm,
				status: e.target.value
			})
		}, COLUMNS.map((c) => React.createElement("option", {
			key: c.id,
			value: c.id
		}, c.title)))), React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Repository / Tenant"), React.createElement("input", {
			className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
			placeholder: "e.g. zerofactory or git repo path",
			value: newTaskForm.tenant,
			onChange: (e) => setNewTaskForm({
				...newTaskForm,
				tenant: e.target.value
			})
		}))), React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Pull Request URL (Optional)"), React.createElement("input", {
			className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors font-mono",
			placeholder: "e.g. https://github.com/owner/repo/pull/123",
			value: newTaskForm.pr_url || "",
			onChange: (e) => setNewTaskForm({
				...newTaskForm,
				pr_url: e.target.value
			})
		})), React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Description & Acceptance Criteria"), React.createElement("textarea", {
			className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors min-h-[100px] resize-y leading-relaxed",
			placeholder: "Provide context, requirements, edge cases, and steps for the agent...",
			value: newTaskForm.description,
			onChange: (e) => setNewTaskForm({
				...newTaskForm,
				description: e.target.value
			})
		}))), React.createElement("div", { className: "flex items-center justify-end gap-2.5 px-4 sm:px-6 py-3 sm:py-3.5 border-t border-slate-800 bg-slate-900/50 shrink-0" }, React.createElement("button", {
			type: "button",
			className: "px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 transition-colors cursor-pointer",
			onClick: () => setShowNewTaskModal(false)
		}, "Cancel"), React.createElement("button", {
			type: "submit",
			disabled: isSubmittingTask,
			className: "px-4 py-1.5 rounded-lg text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-500 transition-colors cursor-pointer shadow-xs shadow-indigo-600/30 disabled:opacity-50"
		}, isSubmittingTask ? "Creating..." : "Create Task"))));
	}
	//#endregion
	//#region dashboard/src/modals/NewBoardModal.jsx
	function NewBoardModal(props) {
		const { showNewBoardModal, setShowNewBoardModal, newBoardForm, setNewBoardForm, handleCreateBoard, handleCreateBoardSubmit = handleCreateBoard, isSubmittingBoard, boards = [], setActiveView = () => {}, createBoardError = "", setCreateBoardError = () => {}, isTestingClone = false, handleTestClone = () => {}, cloneTestResult = null, setCloneTestResult = () => {} } = props;
		if (!showNewBoardModal) return null;
		const repos = newBoardForm.repositories && newBoardForm.repositories.length > 0 ? newBoardForm.repositories : [{
			repo_alias: computeGitSlug(newBoardForm.git_url || "") || "main",
			git_url: newBoardForm.git_url || "",
			target_branch: newBoardForm.target_branch || "main",
			additional_reviewer_usernames: newBoardForm.additional_reviewer_usernames || ""
		}];
		const updateRepo = (index, field, value) => {
			const updated = [...repos];
			const current = {
				...updated[index],
				[field]: value
			};
			if (field === "git_url" && (!current.repo_alias || current.repo_alias === "main")) {
				const slug = computeGitSlug(value);
				if (slug) current.repo_alias = slug;
			}
			updated[index] = current;
			const updates = {
				...newBoardForm,
				repositories: updated
			};
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
			const updated = [...repos, {
				repo_alias: "",
				git_url: "",
				target_branch: "main",
				additional_reviewer_usernames: ""
			}];
			setNewBoardForm({
				...newBoardForm,
				repositories: updated
			});
		};
		const removeRepo = (index) => {
			if (repos.length <= 1) return;
			const updated = repos.filter((_, idx) => idx !== index);
			const updates = {
				...newBoardForm,
				repositories: updated
			};
			if (index === 0 && updated.length > 0) {
				updates.git_url = updated[0].git_url;
				updates.target_branch = updated[0].target_branch;
				updates.additional_reviewer_usernames = updated[0].additional_reviewer_usernames;
			}
			setNewBoardForm(updates);
		};
		const suggestedSlug = computeGitSlug(repos[0]?.git_url || newBoardForm.git_url || "") || repos[0]?.repo_alias || "";
		const currentSlug = (newBoardForm.slug || "").trim();
		const effectiveSlug = currentSlug || suggestedSlug;
		return React.createElement(Modal, {
			isOpen: showNewBoardModal,
			onClose: boards.length > 0 ? () => setShowNewBoardModal(false) : void 0,
			title: boards.length === 0 ? "Create First Project Board (Required)" : "Create New Project Board",
			subtitle: boards.length === 0 ? "A project board is required to use Zero Factory Kanban" : void 0,
			bodyClassName: "p-0 flex flex-col flex-1 overflow-hidden"
		}, React.createElement("form", {
			onSubmit: handleCreateBoardSubmit,
			className: "flex flex-col flex-1 overflow-hidden m-0"
		}, React.createElement("div", { className: "p-4 sm:p-6 space-y-5 overflow-y-auto zfk-scrollbar flex-1" }, boards.length === 0 && React.createElement("div", { className: "p-3 rounded-lg bg-indigo-950/60 border border-indigo-500/30 text-xs text-indigo-200 leading-relaxed flex items-start gap-2.5" }, React.createElement("span", { className: "text-base leading-none shrink-0 mt-0.5" }, "ℹ️"), React.createElement("div", null, React.createElement("p", { className: "font-semibold mb-0.5 text-white" }, "Initial Board Setup"), React.createElement("p", { className: "text-indigo-200/90" }, "Register a project workspace with one or more repositories to start orchestrating tickets, assigning autonomous agents, and managing side-by-side Git worktrees. You can also review the ", React.createElement("button", {
			type: "button",
			className: "underline text-indigo-300 hover:text-white font-medium cursor-pointer",
			onClick: () => {
				setShowNewBoardModal(false);
				setActiveView("instructions");
			}
		}, "Zero Factory Instructions"), "."))), createBoardError && React.createElement("div", { className: "p-3 rounded-lg bg-rose-950/90 border border-rose-500/60 text-xs text-rose-200 leading-relaxed flex items-start gap-2.5 shadow-sm" }, React.createElement("span", { className: "text-base leading-none shrink-0 mt-0.5" }, "⚠️"), React.createElement("div", null, React.createElement("p", { className: "font-semibold mb-0.5 text-white" }, "Could Not Create Board"), React.createElement("p", { className: "text-rose-200/90 m-0" }, createBoardError))), React.createElement("div", { className: "space-y-1.5 p-3 rounded-lg bg-slate-900/60 border border-slate-800" }, React.createElement("div", { className: "flex items-center justify-between" }, React.createElement("label", { className: "block text-xs font-bold text-slate-200 tracking-wide uppercase" }, "🏷️ Board Slug", React.createElement("span", { className: "text-rose-400 ml-1" }, "*")), suggestedSlug && currentSlug !== suggestedSlug && React.createElement("button", {
			type: "button",
			onClick: () => setNewBoardForm({
				...newBoardForm,
				slug: suggestedSlug
			}),
			className: "text-[11px] text-indigo-400 hover:text-indigo-300 transition-colors cursor-pointer"
		}, "Use suggested: " + suggestedSlug)), React.createElement("input", {
			className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors font-mono",
			placeholder: suggestedSlug || "e.g. checkout-platform, order-service",
			value: newBoardForm.slug || "",
			onChange: (e) => setNewBoardForm({
				...newBoardForm,
				slug: e.target.value.toLowerCase().replace(/[^a-z0-9_-]/g, "-")
			})
		}), React.createElement("div", { className: "flex items-center justify-between gap-2 text-[10px] text-slate-400" }, React.createElement("span", null, "Unique board identifier for CLI, URLs, and multi-repo task orchestration."), effectiveSlug && React.createElement("span", { className: "font-mono text-slate-500 shrink-0" }, "Slug: ", React.createElement("span", { className: "text-indigo-300 font-semibold" }, effectiveSlug))), effectiveSlug && boards.some((b) => b.slug === effectiveSlug) && React.createElement("div", { className: "p-2 rounded bg-amber-950/60 border border-amber-500/40 text-[11px] text-amber-300 flex items-center gap-1.5" }, React.createElement("span", null, "⚠️"), "A board with slug '", React.createElement("span", { className: "font-mono font-bold text-amber-200" }, effectiveSlug), "' already exists.")), React.createElement("div", { className: "space-y-3" }, React.createElement("div", { className: "flex items-center justify-between" }, React.createElement("label", { className: "block text-xs font-bold text-slate-200 tracking-wide uppercase" }, "📦 Project Repositories (" + repos.length + ")"), React.createElement("button", {
			type: "button",
			onClick: addRepo,
			className: "text-xs font-medium text-indigo-400 hover:text-indigo-300 transition-colors cursor-pointer flex items-center gap-1"
		}, "+ Add Another Repo")), React.createElement("p", { className: "text-[11px] text-slate-400 m-0" }, "All repositories are equal peers with remote URLs, branches, reviewers, and precommit verification. Sibling repositories check out side-by-side in workspaces."), React.createElement("div", { className: "space-y-3 pt-1" }, repos.map((repo, idx) => React.createElement("div", {
			key: idx,
			className: "p-3.5 rounded-lg bg-slate-900/80 border border-slate-800 space-y-3 relative group"
		}, React.createElement("div", { className: "flex items-center justify-between gap-2" }, React.createElement("div", { className: "flex items-center gap-2" }, React.createElement("span", { className: "font-semibold text-xs text-indigo-300 font-mono bg-slate-800 px-2 py-0.5 rounded" }, repo.repo_alias || "Repo #" + (idx + 1))), repos.length > 1 && React.createElement("button", {
			type: "button",
			onClick: () => removeRepo(idx),
			className: "text-rose-400 hover:text-rose-300 text-xs font-medium px-2 py-0.5 rounded hover:bg-rose-950/40 transition-colors cursor-pointer"
		}, "✕ Remove")), React.createElement("div", { className: "space-y-1.5" }, React.createElement("div", { className: "flex items-center justify-between" }, React.createElement("label", { className: "block text-[11px] font-semibold text-slate-300" }, "Remote Git URL *"), React.createElement("button", {
			type: "button",
			disabled: isTestingClone || !repo.git_url,
			onClick: () => handleTestClone(repo.git_url, repo.repo_alias || computeGitSlug(repo.git_url)),
			className: "text-[11px] font-medium text-indigo-400 hover:text-indigo-300 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer flex items-center gap-1 transition-colors"
		}, isTestingClone ? "Testing..." : "🧪 Test Clone")), React.createElement("input", {
			className: "w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 font-mono outline-none focus:border-indigo-500",
			required: true,
			placeholder: "git@github.com:org/repo.git or https://github.com/org/repo.git",
			value: repo.git_url || "",
			onChange: (e) => {
				setCreateBoardError("");
				setCloneTestResult(null);
				updateRepo(idx, "git_url", e.target.value);
			}
		})), React.createElement("div", { className: "grid grid-cols-1 sm:grid-cols-3 gap-2.5" }, React.createElement("div", { className: "space-y-1" }, React.createElement("label", { className: "block text-[10px] font-semibold text-slate-400" }, "Repo Alias *"), React.createElement("input", {
			className: "w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-xs text-slate-200 font-mono placeholder-slate-500 outline-none focus:border-indigo-500",
			required: true,
			placeholder: "e.g. core-api",
			value: repo.repo_alias || "",
			onChange: (e) => updateRepo(idx, "repo_alias", e.target.value)
		})), React.createElement("div", { className: "space-y-1" }, React.createElement("label", { className: "block text-[10px] font-semibold text-slate-400" }, "Target Branch"), React.createElement("input", {
			className: "w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-xs text-slate-200 font-mono placeholder-slate-500 outline-none focus:border-indigo-500",
			placeholder: "main",
			value: repo.target_branch || "main",
			onChange: (e) => updateRepo(idx, "target_branch", e.target.value)
		})), React.createElement("div", { className: "space-y-1" }, React.createElement("label", { className: "block text-[10px] font-semibold text-slate-400" }, "Reviewers (Optional)"), React.createElement("input", {
			className: "w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500",
			placeholder: "alice, bob",
			value: typeof repo.additional_reviewer_usernames === "string" ? repo.additional_reviewer_usernames : (repo.additional_reviewer_usernames || []).join(", "),
			onChange: (e) => updateRepo(idx, "additional_reviewer_usernames", e.target.value)
		})))))), cloneTestResult && React.createElement("div", { className: `text-[11px] px-2.5 py-1.5 rounded border flex items-start gap-1.5 ${cloneTestResult.ok ? "bg-emerald-950/40 border-emerald-800/60 text-emerald-300" : "bg-rose-950/40 border-rose-800/60 text-rose-300"}` }, React.createElement("span", { className: "shrink-0 font-bold" }, cloneTestResult.ok ? "✓" : "✕"), React.createElement("span", { className: "break-all" }, cloneTestResult.message))), React.createElement("div", { className: "space-y-1.5 pt-2 border-t border-slate-800/80" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-300 tracking-wide" }, "🌐 System Architecture Notes (Optional)"), React.createElement("textarea", {
			className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors font-mono min-h-[90px] resize-y leading-relaxed",
			placeholder: "# System Architecture & Contracts\n- common-lib: Shared protobuf & business models\n- api-gateway: Reverse proxy routing to order-service\n- order-service: Core transaction handling",
			value: newBoardForm.architecture || "",
			onChange: (e) => setNewBoardForm({
				...newBoardForm,
				architecture: e.target.value
			})
		}), React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "High-level service contracts and boundaries injected into agent prompts.")), React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Description (Optional)"), React.createElement("input", {
			className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
			placeholder: "Short description of this board's scope (optional)",
			value: newBoardForm.description || "",
			onChange: (e) => setNewBoardForm({
				...newBoardForm,
				description: e.target.value
			})
		})), React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Jira Cloud Link (Optional)"), React.createElement("input", {
			className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors font-mono",
			placeholder: "https://your-domain.atlassian.net or project link",
			value: newBoardForm.jira_url || "",
			onChange: (e) => setNewBoardForm({
				...newBoardForm,
				jira_url: e.target.value
			})
		}), React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Link your Jira Cloud instance or project to this board for Jira issue references and triage.")), React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Max Concurrent Running (Default: 1)"), React.createElement("input", {
			type: "number",
			min: 1,
			step: 1,
			className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
			placeholder: "Max tasks running in parallel on this board (minimum 1)",
			value: newBoardForm.max_concurrent_running ?? 1,
			onChange: (e) => setNewBoardForm({
				...newBoardForm,
				max_concurrent_running: e.target.value
			})
		}), React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Caps how many of this board's tasks the dispatcher can run at once.")), React.createElement("div", { className: "pt-1 flex items-center justify-between" }, React.createElement("div", null, React.createElement("label", { className: "block text-xs font-semibold text-slate-300" }, "🧠 Auto-Record Memory"), React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Capture gotchas & conventions automatically from reviewer feedback.")), React.createElement("input", {
			type: "checkbox",
			className: "h-4 w-4 rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500 cursor-pointer",
			checked: Boolean(newBoardForm.auto_record_memory !== false),
			onChange: (e) => setNewBoardForm({
				...newBoardForm,
				auto_record_memory: e.target.checked
			})
		})), React.createElement("div", { className: "pt-1 flex items-center justify-between" }, React.createElement("div", null, React.createElement("label", { className: "block text-xs font-semibold text-slate-300" }, "⚡ Auto-Setup Precommit"), React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Generate .zerofactory/precommit.sh with automated test, build, and format verification.")), React.createElement("input", {
			type: "checkbox",
			className: "h-4 w-4 rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500 cursor-pointer",
			checked: Boolean(newBoardForm.auto_setup_precommit !== false),
			onChange: (e) => setNewBoardForm({
				...newBoardForm,
				auto_setup_precommit: e.target.checked
			})
		}))), React.createElement("div", { className: "flex items-center justify-end gap-2.5 px-4 sm:px-6 py-3 sm:py-3.5 border-t border-slate-800 bg-slate-900/50 shrink-0" }, boards.length > 0 && React.createElement("button", {
			type: "button",
			className: "px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 transition-colors cursor-pointer",
			onClick: () => setShowNewBoardModal(false)
		}, "Cancel"), React.createElement("button", {
			type: "submit",
			disabled: isSubmittingBoard,
			className: "px-4 py-1.5 rounded-lg text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-500 transition-colors cursor-pointer shadow-xs shadow-indigo-600/30 disabled:opacity-50 disabled:cursor-not-allowed"
		}, isSubmittingBoard ? "Creating..." : boards.length === 0 ? "Create & Get Started" : "Create Board"))));
	}
	//#endregion
	//#region dashboard/src/modals/EditBoardModal.jsx
	function EditBoardModal(props) {
		const { showEditBoardModal, setShowEditBoardModal, editBoardForm, setEditBoardForm, handleUpdateBoard, handleUpdateBoardSubmit = handleUpdateBoard, handleDeleteBoard, isSubmittingBoard, isTestingClone = false, handleTestClone = () => {}, cloneTestResult = null, setCloneTestResult = () => {}, precommitStatuses = {}, precommitStatus = null, isSettingUpPrecommit = false, handleTriggerPrecommitSetup = () => {}, openwikiStatuses = {}, openwikiStatus = null, isSettingUpOpenwiki = false, handleTriggerOpenwikiSetup = () => {}, ghIssuesStatuses = {}, ghIssuesStatus = null, isSettingUpGhIssues = false, handleTriggerGhIssuesSetup = () => {}, isSettingUpJira = false, handleTriggerJiraSetup = () => {}, isTestingJira = false, handleTriggerJiraTest = () => {}, handleAddBoardRepo = () => {}, handleDeleteBoardRepo = () => {} } = props;
		const [newRepoAlias, setNewRepoAlias] = React.useState("");
		const [newRepoUrl, setNewRepoUrl] = React.useState("");
		const [newRepoBranch, setNewRepoBranch] = React.useState("main");
		const [newRepoReviewers, setNewRepoReviewers] = React.useState("");
		if (!showEditBoardModal) return null;
		const repos = editBoardForm.repositories || [];
		const updateRepoField = (idx, field, value) => {
			const updated = [...repos];
			updated[idx] = {
				...updated[idx],
				[field]: value
			};
			const updates = {
				...editBoardForm,
				repositories: updated
			};
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
		return React.createElement(Modal, {
			isOpen: showEditBoardModal,
			onClose: () => setShowEditBoardModal(false),
			title: "Edit Project Board: " + editBoardForm.slug,
			bodyClassName: "p-0 flex flex-col flex-1 overflow-hidden"
		}, React.createElement("form", {
			onSubmit: handleUpdateBoardSubmit,
			className: "flex flex-col flex-1 overflow-hidden m-0"
		}, React.createElement("div", { className: "p-4 sm:p-6 space-y-5 overflow-y-auto zfk-scrollbar flex-1" }, React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Board Slug (Identifier)"), React.createElement("input", {
			className: "w-full bg-slate-950/60 border border-slate-800/60 rounded-lg px-3 py-2 text-xs text-slate-400 cursor-not-allowed opacity-60 outline-none font-mono",
			disabled: true,
			value: editBoardForm.slug
		})), React.createElement("div", { className: "space-y-3" }, React.createElement("div", { className: "flex items-center justify-between" }, React.createElement("label", { className: "block text-xs font-bold text-slate-200 tracking-wide uppercase" }, "📦 Linked Repositories (" + repos.length + ")"), React.createElement("span", { className: "text-[11px] text-slate-500" }, "Equal first-class configuration & automations")), React.createElement("div", { className: "space-y-3.5" }, repos.map((r, idx) => {
			const pStatus = getRepoPrecommit(r.repo_alias);
			const wStatus = getRepoOpenwiki(r.repo_alias);
			const gStatus = getRepoGhIssues(r.repo_alias);
			const reviewersDisplay = Array.isArray(r.additional_reviewer_usernames) ? r.additional_reviewer_usernames.join(", ") : r.additional_reviewer_usernames || "";
			return React.createElement("div", {
				key: r.repo_alias || idx,
				className: "p-4 rounded-lg bg-slate-900/90 border border-slate-800 space-y-3.5"
			}, React.createElement("div", { className: "flex items-center justify-between gap-2 border-b border-slate-800/80 pb-2.5" }, React.createElement("div", { className: "flex items-center gap-2" }, React.createElement("span", { className: "font-mono font-bold text-sm text-indigo-300 bg-slate-800 px-2 py-0.5 rounded" }, r.repo_alias), React.createElement("span", { className: "text-[11px] text-slate-400 bg-slate-800/80 px-2 py-0.5 rounded font-mono" }, "branch: " + (r.target_branch || "main"))), repos.length > 1 && React.createElement("button", {
				type: "button",
				className: "px-2 py-0.5 rounded text-xs font-medium text-rose-300 bg-rose-950/60 hover:bg-rose-900/60 border border-rose-800/60 transition-colors cursor-pointer",
				onClick: () => {
					if (window.confirm("Remove repository '" + r.repo_alias + "' from this board?")) handleDeleteBoardRepo(editBoardForm.slug, r.repo_alias);
				},
				title: "Remove repository from board"
			}, "✕ Remove Repo")), React.createElement("div", { className: "space-y-1" }, React.createElement("div", { className: "flex items-center justify-between" }, React.createElement("label", { className: "block text-[11px] font-semibold text-slate-300" }, "Remote Git URL"), React.createElement("button", {
				type: "button",
				disabled: isTestingClone || !r.git_url,
				onClick: () => handleTestClone(r.git_url, r.repo_alias),
				className: "text-[11px] font-medium text-indigo-400 hover:text-indigo-300 disabled:opacity-50 disabled:cursor-not-allowed cursor-pointer flex items-center gap-1 transition-colors"
			}, isTestingClone ? "Testing..." : "🧪 Test Clone")), React.createElement("input", {
				className: "w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 font-mono outline-none focus:border-indigo-500",
				value: r.git_url || "",
				onChange: (e) => updateRepoField(idx, "git_url", e.target.value)
			})), React.createElement("div", { className: "grid grid-cols-1 sm:grid-cols-2 gap-3" }, React.createElement("div", { className: "space-y-1" }, React.createElement("label", { className: "block text-[11px] font-semibold text-slate-400" }, "Target Branch / PR Base"), React.createElement("input", {
				className: "w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-xs text-slate-200 font-mono placeholder-slate-500 outline-none focus:border-indigo-500",
				value: r.target_branch || "main",
				onChange: (e) => updateRepoField(idx, "target_branch", e.target.value)
			})), React.createElement("div", { className: "space-y-1" }, React.createElement("label", { className: "block text-[11px] font-semibold text-slate-400" }, "Additional Trusted Reviewers"), React.createElement("input", {
				className: "w-full bg-slate-950 border border-slate-800 rounded px-2.5 py-1 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500",
				placeholder: "alice, bob (GitHub usernames)",
				value: reviewersDisplay,
				onChange: (e) => updateRepoField(idx, "additional_reviewer_usernames", e.target.value.split(",").map((s) => s.trim()).filter(Boolean))
			}))), React.createElement("div", { className: "p-3 rounded-lg bg-slate-950/70 border border-slate-800/80 space-y-2.5" }, React.createElement("span", { className: "block text-[10px] font-bold text-slate-400 uppercase tracking-wider" }, "🛠️ Repository Automations & Verification"), React.createElement("div", { className: "flex items-center justify-between gap-2 text-xs" }, React.createElement("div", { className: "min-w-0 flex items-center gap-2" }, React.createElement("span", { className: "font-medium text-slate-300 text-xs shrink-0" }, "⚡ Precommit:"), React.createElement("span", { className: "px-2 py-0.5 rounded text-[10px] font-semibold " + (pStatus && pStatus.has_precommit ? "bg-emerald-950/80 text-emerald-300 border border-emerald-800/60" : pStatus && pStatus.pending_task_id ? "bg-sky-950/80 text-sky-300 border border-sky-800/60" : "bg-amber-950/80 text-amber-300 border border-amber-800/60") }, pStatus && pStatus.has_precommit ? "Configured ✓" : pStatus && pStatus.pending_task_id ? "Setup in Progress ⏳" : "Not Configured ⚠️")), React.createElement("button", {
				type: "button",
				disabled: isSettingUpPrecommit,
				onClick: () => handleTriggerPrecommitSetup(editBoardForm.slug, r.repo_alias),
				className: "px-2.5 py-1 rounded text-[11px] font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 transition-colors cursor-pointer disabled:opacity-50 shrink-0"
			}, isSettingUpPrecommit ? "Initiating..." : pStatus && pStatus.has_precommit ? "🔄 Regenerate" : "⚡ Setup Precommit")), React.createElement("div", { className: "flex items-center justify-between gap-2 text-xs" }, React.createElement("div", { className: "min-w-0 flex items-center gap-2" }, React.createElement("span", { className: "font-medium text-slate-300 text-xs shrink-0" }, "📖 OpenWiki:"), React.createElement("span", { className: "px-2 py-0.5 rounded text-[10px] font-semibold " + (wStatus && wStatus.has_openwiki ? "bg-emerald-950/80 text-emerald-300 border border-emerald-800/60" : wStatus && wStatus.pending_task_id ? "bg-sky-950/80 text-sky-300 border border-sky-800/60" : "bg-amber-950/80 text-amber-300 border border-amber-800/60") }, wStatus && wStatus.has_openwiki ? "Generated ✓" : wStatus && wStatus.pending_task_id ? "Setup in Progress ⏳" : "Not Generated ⚠️")), React.createElement("button", {
				type: "button",
				disabled: isSettingUpOpenwiki,
				onClick: () => handleTriggerOpenwikiSetup(editBoardForm.slug, r.repo_alias),
				className: "px-2.5 py-1 rounded text-[11px] font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 transition-colors cursor-pointer disabled:opacity-50 shrink-0"
			}, isSettingUpOpenwiki ? "Initiating..." : wStatus && wStatus.has_openwiki ? "🔄 Regenerate" : "📖 Setup OpenWiki")), React.createElement("div", { className: "flex items-center justify-between gap-2 text-xs" }, React.createElement("div", { className: "min-w-0 flex items-center gap-2" }, React.createElement("span", { className: "font-medium text-slate-300 text-xs shrink-0" }, "🏷️ Issue Templates:"), React.createElement("span", { className: "px-2 py-0.5 rounded text-[10px] font-semibold " + (gStatus && gStatus.has_gh_issues ? "bg-emerald-950/80 text-emerald-300 border border-emerald-800/60" : gStatus && gStatus.pending_task_id ? "bg-purple-950/80 text-purple-300 border border-purple-800/60" : "bg-amber-950/80 text-amber-300 border border-amber-800/60") }, gStatus && gStatus.has_gh_issues ? "Configured ✓" : gStatus && gStatus.pending_task_id ? "Setup in Progress ⏳" : "Not Configured ⚠️")), React.createElement("button", {
				type: "button",
				disabled: isSettingUpGhIssues,
				onClick: () => handleTriggerGhIssuesSetup(editBoardForm.slug, r.repo_alias),
				className: "px-2.5 py-1 rounded text-[11px] font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 transition-colors cursor-pointer disabled:opacity-50 shrink-0"
			}, isSettingUpGhIssues ? "Initiating..." : gStatus && gStatus.has_gh_issues ? "🔄 Regenerate" : "🏷️ Setup Issues"))));
		})), React.createElement("div", { className: "p-3.5 rounded-lg bg-slate-950/70 border border-slate-800/90 space-y-3" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-300" }, "+ Add Repository to Board"), React.createElement("div", { className: "grid grid-cols-1 sm:grid-cols-4 gap-2" }, React.createElement("input", {
			className: "bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 font-mono outline-none focus:border-indigo-500",
			placeholder: "Alias (e.g. auth-svc)",
			value: newRepoAlias,
			onChange: (e) => setNewRepoAlias(e.target.value)
		}), React.createElement("input", {
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
		}), React.createElement("input", {
			className: "bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 font-mono outline-none focus:border-indigo-500",
			placeholder: "Branch (main)",
			value: newRepoBranch,
			onChange: (e) => setNewRepoBranch(e.target.value)
		})), React.createElement("div", { className: "flex items-center justify-between gap-2" }, React.createElement("input", {
			className: "bg-slate-900 border border-slate-800 rounded px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 flex-1",
			placeholder: "Additional Reviewers (e.g. alice, bob; optional)",
			value: newRepoReviewers,
			onChange: (e) => setNewRepoReviewers(e.target.value)
		}), React.createElement("button", {
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
		}, "+ Add Repository")))), React.createElement("div", { className: "space-y-1.5 pt-2 border-t border-slate-800/80" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-300 tracking-wide" }, "🌐 System Architecture Notes (architecture)"), React.createElement("textarea", {
			className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors font-mono min-h-[90px] resize-y leading-relaxed",
			placeholder: "# System Architecture & Contracts\n- common-lib: Shared protobuf & business models\n- api-gateway: Reverse proxy routing to order-service\n- order-service: Core transaction handling",
			value: editBoardForm.architecture || "",
			onChange: (e) => setEditBoardForm({
				...editBoardForm,
				architecture: e.target.value
			})
		}), React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "High-level architecture contracts and service topology injected into agent prompts.")), React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Description"), React.createElement("input", {
			className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
			placeholder: "Short description of this board's scope",
			value: editBoardForm.description || "",
			onChange: (e) => setEditBoardForm({
				...editBoardForm,
				description: e.target.value
			})
		})), React.createElement("div", { className: "space-y-1.5" }, React.createElement("div", { className: "flex items-center justify-between" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Jira Cloud Link (Optional)"), editBoardForm.jira_url && React.createElement("a", {
			href: editBoardForm.jira_url.startsWith("http") ? editBoardForm.jira_url : `https://${editBoardForm.jira_url}`,
			target: "_blank",
			rel: "noreferrer",
			className: "text-[11px] font-medium text-sky-400 hover:text-sky-300 cursor-pointer flex items-center gap-1 transition-colors"
		}, "↗ Open Jira Cloud")), React.createElement("input", {
			className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors font-mono",
			placeholder: "https://your-domain.atlassian.net or project link",
			value: editBoardForm.jira_url || "",
			onChange: (e) => setEditBoardForm({
				...editBoardForm,
				jira_url: e.target.value
			})
		}), React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Link your Jira Cloud instance or project to this board for Jira issue references and triage.")), React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-400 tracking-wide" }, "Max Concurrent Running (Default: 1)"), React.createElement("input", {
			type: "number",
			min: 1,
			step: 1,
			className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
			placeholder: "Max tasks running in parallel on this board (minimum 1)",
			value: editBoardForm.max_concurrent_running ?? 1,
			onChange: (e) => setEditBoardForm({
				...editBoardForm,
				max_concurrent_running: e.target.value
			})
		}), React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Caps how many of this board's tasks the dispatcher can run at once.")), React.createElement("div", { className: "pt-1 flex items-center justify-between" }, React.createElement("div", null, React.createElement("label", { className: "block text-xs font-semibold text-slate-300" }, "🧠 Auto-Record Memory"), React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Capture gotchas & conventions automatically from reviewer feedback.")), React.createElement("input", {
			type: "checkbox",
			className: "h-4 w-4 rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500 cursor-pointer",
			checked: Boolean(editBoardForm.auto_record_memory !== false),
			onChange: (e) => setEditBoardForm({
				...editBoardForm,
				auto_record_memory: e.target.checked
			})
		}))), React.createElement("div", { className: "flex items-center justify-end gap-2.5 px-4 sm:px-6 py-3 sm:py-3.5 border-t border-slate-800 bg-slate-900/50 shrink-0" }, React.createElement("button", {
			type: "button",
			className: "mr-auto px-3.5 py-1.5 rounded-lg text-xs font-medium text-rose-400 hover:text-rose-300 bg-rose-500/10 hover:bg-rose-500/20 border border-rose-500/30 transition-colors cursor-pointer",
			onClick: handleDeleteBoard,
			title: "Delete this board and its scheduled scanner job"
		}, "🗑️ Remove Board"), React.createElement("button", {
			type: "button",
			className: "px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 transition-colors cursor-pointer",
			onClick: () => setShowEditBoardModal(false)
		}, "Cancel"), React.createElement("button", {
			type: "submit",
			className: "px-4 py-1.5 rounded-lg text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-500 transition-colors cursor-pointer shadow-xs shadow-indigo-600/30"
		}, "Save Changes"))));
	}
	//#endregion
	//#region dashboard/src/modals/SettingsModal.jsx
	function SettingsModal(props) {
		const { showSettingsModal, setShowSettingsModal, settingsForm, setSettingsForm, handleSaveSettings, isSavingSettings, isTestingLangfuse, handleTestLangfuse, langfuseTestResult, showLangfuseSecret, setShowLangfuseSecret, isSyncingProfiles, handleSyncProfiles, syncProfilesResult, syncForce, setSyncForce } = props;
		if (!showSettingsModal) return null;
		return React.createElement(Modal, {
			isOpen: showSettingsModal,
			onClose: () => setShowSettingsModal(false),
			onSubmit: handleSaveSettings,
			title: "Zero Factory Global Settings",
			subtitle: "System-wide orchestration limits and defaults",
			icon: "⚙️",
			bodyClassName: "p-6 space-y-4 text-xs overflow-y-auto zfk-scrollbar flex-1",
			footerClassName: "flex items-center justify-end gap-2.5 px-6 py-3.5 border-t border-slate-800 bg-slate-900/50 shrink-0",
			footer: React.createElement(React.Fragment, null, React.createElement("button", {
				type: "button",
				className: "px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 transition-colors cursor-pointer",
				onClick: () => setShowSettingsModal(false)
			}, "Cancel"), React.createElement("button", {
				type: "submit",
				disabled: isSavingSettings,
				className: "px-4 py-1.5 rounded-lg text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-500 transition-colors cursor-pointer shadow-xs shadow-indigo-600/30 disabled:opacity-50"
			}, isSavingSettings ? "Saving..." : "Save Settings"))
		}, React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-300 tracking-wide" }, "Max Active Tasks (WIP Limit)"), React.createElement("input", {
			type: "number",
			min: 1,
			step: 1,
			className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
			value: settingsForm.max_active_tasks ?? 10,
			onChange: (e) => setSettingsForm({
				...settingsForm,
				max_active_tasks: e.target.value
			})
		}), React.createElement("p", { className: "text-[11px] text-slate-400 m-0 leading-relaxed" }, "Caps total tasks allowed in 'running' across all boards combined. Controls how many git worktrees are prepared from 'todo' to prevent queue and disk flooding. Default: 10.")), React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-300 tracking-wide" }, "Global Max Concurrent LLM Workers"), React.createElement("input", {
			type: "number",
			min: 1,
			step: 1,
			className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors",
			value: settingsForm.max_concurrent_llm_workers ?? 10,
			onChange: (e) => setSettingsForm({
				...settingsForm,
				max_concurrent_llm_workers: e.target.value
			})
		}), React.createElement("p", { className: "text-[11px] text-slate-400 m-0 leading-relaxed" }, "Caps task workers and improvement scans combined across all boards; per-board limits and task WIP still apply. Default: 10.")), React.createElement("div", { className: "pt-2 border-t border-slate-800/80 space-y-3" }, React.createElement("div", { className: "flex items-center justify-between" }, React.createElement("div", null, React.createElement("div", { className: "flex items-center gap-1.5" }, React.createElement("span", { className: "text-sm" }, "🧠"), React.createElement("label", { className: "block text-xs font-semibold text-slate-200 tracking-wide" }, "Auto-Record Repository Memory")), React.createElement("p", { className: "text-[11px] text-slate-400 m-0 leading-relaxed mt-0.5" }, "Automatically extract and persist gotchas, conventions, and rules from reviewer feedback and rejections.")), React.createElement("input", {
			type: "checkbox",
			className: "h-4 w-4 rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500 cursor-pointer",
			checked: Boolean(settingsForm.auto_record_memory !== false),
			onChange: (e) => setSettingsForm({
				...settingsForm,
				auto_record_memory: e.target.checked
			})
		}))), React.createElement("div", { className: "pt-2 border-t border-slate-800/80 space-y-3" }, React.createElement("div", { className: "flex items-start justify-between gap-3" }, React.createElement("div", null, React.createElement("div", { className: "flex items-center gap-1.5" }, React.createElement("span", { className: "text-sm" }, "🤖"), React.createElement("label", { className: "block text-xs font-semibold text-slate-200 tracking-wide" }, "Agent Profiles & Skills")), React.createElement("p", { className: "text-[11px] text-slate-400 m-0 leading-relaxed mt-0.5" }, "Synchronize SOUL.md system prompts, skills, and templates across zf-orchestrator, zf-builder, and zf-reviewer in ~/.hermes/profiles/.")), React.createElement("button", {
			type: "button",
			disabled: isSyncingProfiles,
			onClick: handleSyncProfiles,
			className: "px-3 py-1.5 rounded-lg bg-indigo-600/90 hover:bg-indigo-600 text-white font-medium text-xs border border-indigo-500/30 flex items-center gap-1.5 transition-colors cursor-pointer disabled:opacity-50 shrink-0 shadow-xs shadow-indigo-600/20"
		}, isSyncingProfiles ? React.createElement("span", { className: "animate-spin text-xs inline-block" }, "⏳") : React.createElement("span", { className: "text-xs" }, "🔄"), isSyncingProfiles ? "Syncing..." : "Sync Profiles")), React.createElement("div", { className: "flex items-center justify-between text-[11px] text-slate-400 pt-0.5" }, React.createElement("label", { className: "flex items-center gap-1.5 cursor-pointer hover:text-slate-300 transition-colors" }, React.createElement("input", {
			type: "checkbox",
			className: "h-3.5 w-3.5 rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500 cursor-pointer",
			checked: Boolean(syncForce),
			onChange: (e) => setSyncForce(e.target.checked)
		}), React.createElement("span", null, "Force overwrite config.yaml with defaults")), React.createElement("span", { className: "text-[10px] text-slate-500 font-mono" }, "hermes zerofactory sync-profiles")), syncProfilesResult && React.createElement("div", { className: `text-[11px] px-2.5 py-1.5 rounded border ${syncProfilesResult.ok ? "bg-emerald-950/40 border-emerald-800/60 text-emerald-300" : "bg-rose-950/40 border-rose-800/60 text-rose-300"}` }, (syncProfilesResult.ok ? "✓ " : "✕ ") + syncProfilesResult.message)), React.createElement("div", { className: "pt-2 border-t border-slate-800/80 space-y-3" }, React.createElement("div", { className: "flex items-center justify-between" }, React.createElement("div", null, React.createElement("div", { className: "flex items-center gap-1.5" }, React.createElement("span", { className: "text-sm" }, "🔭"), React.createElement("label", { className: "block text-xs font-semibold text-slate-200 tracking-wide" }, "Langfuse Observability & Tracing")), React.createElement("p", { className: "text-[11px] text-slate-400 m-0 leading-relaxed mt-0.5" }, "Trace LLM calls, tool executions, latencies, and token costs across all agent profiles.")), React.createElement("input", {
			type: "checkbox",
			className: "h-4 w-4 rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500 cursor-pointer",
			checked: Boolean(settingsForm.langfuse_enabled),
			onChange: (e) => setSettingsForm({
				...settingsForm,
				langfuse_enabled: e.target.checked
			})
		})), settingsForm.langfuse_enabled && React.createElement("div", { className: "space-y-3 pt-1 bg-slate-950/60 p-3 rounded-lg border border-slate-800/70" }, React.createElement("div", { className: "space-y-1" }, React.createElement("label", { className: "block text-[11px] font-medium text-slate-300" }, "Langfuse Host / Base URL"), React.createElement("input", {
			type: "text",
			placeholder: "https://cloud.langfuse.com",
			className: "w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 font-mono",
			value: settingsForm.langfuse_base_url ?? "https://cloud.langfuse.com",
			onChange: (e) => setSettingsForm({
				...settingsForm,
				langfuse_base_url: e.target.value
			})
		}), React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Cloud instance (https://cloud.langfuse.com) or self-hosted URL (e.g. http://localhost:3000).")), React.createElement("div", { className: "grid grid-cols-1 sm:grid-cols-2 gap-2.5" }, React.createElement("div", { className: "space-y-1" }, React.createElement("label", { className: "block text-[11px] font-medium text-slate-300" }, "Public Key"), React.createElement("input", {
			type: "text",
			placeholder: "pk-lf-...",
			className: "w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 font-mono",
			value: settingsForm.langfuse_public_key ?? "",
			onChange: (e) => setSettingsForm({
				...settingsForm,
				langfuse_public_key: e.target.value
			})
		})), React.createElement("div", { className: "space-y-1" }, React.createElement("div", { className: "flex items-center justify-between" }, React.createElement("label", { className: "block text-[11px] font-medium text-slate-300" }, "Secret Key"), React.createElement("button", {
			type: "button",
			className: "text-[10px] text-slate-400 hover:text-slate-200 cursor-pointer",
			onClick: () => setShowLangfuseSecret(!showLangfuseSecret)
		}, showLangfuseSecret ? "Hide" : "Show")), React.createElement("input", {
			type: showLangfuseSecret ? "text" : "password",
			placeholder: "sk-lf-...",
			className: "w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 font-mono",
			value: settingsForm.langfuse_secret_key ?? "",
			onChange: (e) => setSettingsForm({
				...settingsForm,
				langfuse_secret_key: e.target.value
			})
		}))), React.createElement("div", { className: "grid grid-cols-1 sm:grid-cols-2 gap-2.5" }, React.createElement("div", { className: "space-y-1" }, React.createElement("label", { className: "block text-[11px] font-medium text-slate-300" }, "Environment Tag"), React.createElement("input", {
			type: "text",
			placeholder: "zerofactory",
			className: "w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-indigo-500 font-mono",
			value: settingsForm.langfuse_env ?? "zerofactory",
			onChange: (e) => setSettingsForm({
				...settingsForm,
				langfuse_env: e.target.value
			})
		})), React.createElement("div", { className: "space-y-1" }, React.createElement("label", { className: "block text-[11px] font-medium text-slate-300" }, "Content Capture Mode"), React.createElement("select", {
			className: "w-full bg-slate-900 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-indigo-500 cursor-pointer",
			value: settingsForm.langfuse_capture_mode ?? "sanitized",
			onChange: (e) => setSettingsForm({
				...settingsForm,
				langfuse_capture_mode: e.target.value
			})
		}, React.createElement("option", { value: "sanitized" }, "Sanitized (Redact secrets & truncate)"), React.createElement("option", { value: "metadata" }, "Metadata Only (No prompts/outputs)"), React.createElement("option", { value: "full" }, "Full Content (Raw payloads)")))), React.createElement("div", { className: "pt-2 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-2 border-t border-slate-800/60" }, React.createElement("div", { className: "flex items-center gap-1.5 text-[11px]" }, React.createElement("span", { className: "text-emerald-400" }, "✓"), React.createElement("span", { className: "text-slate-400" }, "Syncs to zf-orchestrator, zf-builder, zf-reviewer & root")), React.createElement("div", { className: "flex items-center gap-2" }, React.createElement("button", {
			type: "button",
			disabled: isTestingLangfuse,
			onClick: handleTestLangfuse,
			className: "px-2.5 py-1 rounded bg-slate-800 hover:bg-slate-700 border border-slate-700 text-slate-200 text-[11px] font-medium transition-colors cursor-pointer disabled:opacity-50"
		}, isTestingLangfuse ? "Testing..." : "Test Connection"))), langfuseTestResult && React.createElement("div", { className: `text-[11px] px-2.5 py-1.5 rounded border ${langfuseTestResult.ok ? "bg-emerald-950/40 border-emerald-800/60 text-emerald-300" : "bg-rose-950/40 border-rose-800/60 text-rose-300"}` }, (langfuseTestResult.ok ? "✓ " : "✕ ") + langfuseTestResult.message))));
	}
	//#endregion
	//#region dashboard/src/modals/CronModal.jsx
	function CronModal(props) {
		const { showCronModal, setShowCronModal, cronJobs = [], cronSchedulerEnabled = true, loadingCron = false, cronFilterTab = "all", setCronFilterTab = () => {}, cronSearchQuery = "", setCronSearchQuery = () => {}, runningCronId, handleTriggerCron, handleRunCronJob = handleTriggerCron || (() => {}), editingCronId, setEditingCronId = () => {}, cronEditForms = {}, setCronEditForms = () => {}, handleSaveCronEdit, handleSaveCronJob = handleSaveCronEdit || (() => {}), handleToggleCron, handleToggleCronJob = handleToggleCron || (() => {}), handleToggleScheduler, handleToggleCronScheduler = handleToggleScheduler || (() => {}), handleResetCronJob = () => {}, handleSyncAllCron = () => {}, loadCronJobs = () => {} } = props;
		const filteredCronJobs = React.useMemo(() => {
			return (cronJobs || []).filter((job) => {
				if (cronFilterTab === "core") {
					const isScanner = job.id.startsWith("zero-factory-improvement-scanner-") || job.category === "scanner";
					const isOpenWiki = job.id.startsWith("zero-factory-openwiki-update-") || job.category === "openwiki";
					if (isScanner || isOpenWiki) return false;
				} else if (cronFilterTab === "scanners") {
					if (!(job.id.startsWith("zero-factory-improvement-scanner-") || job.category === "scanner")) return false;
				} else if (cronFilterTab === "openwiki") {
					if (!(job.id.startsWith("zero-factory-openwiki-update-") || job.category === "openwiki")) return false;
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
		}, [
			cronJobs,
			cronFilterTab,
			cronSearchQuery
		]);
		if (!showCronModal) return null;
		return React.createElement(Modal, {
			isOpen: showCronModal,
			onClose: () => setShowCronModal(false),
			title: "Zero Factory Cron Automation",
			subtitle: "Manage periodic health checks, daily metrics, and per-board improvement scanners",
			icon: "⏰",
			iconBg: "bg-gradient-to-br from-amber-500 to-indigo-600",
			headerExtra: React.createElement("button", {
				className: "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors cursor-pointer",
				onClick: handleSyncAllCron,
				title: "Synchronize all built-in jobs across active profiles"
			}, "🔄 Sync All"),
			subHeader: React.createElement(React.Fragment, null, React.createElement("div", { className: "px-6 py-3.5 bg-slate-950/70 border-b border-slate-800 flex flex-col sm:flex-row sm:items-center justify-between gap-3 shrink-0" }, React.createElement("div", { className: "flex items-center gap-3" }, React.createElement("div", { className: "w-8 h-8 rounded-lg flex items-center justify-center text-sm font-bold " + (cronSchedulerEnabled ? "bg-emerald-500/10 text-emerald-400 border border-emerald-500/30" : "bg-rose-500/10 text-rose-400 border border-rose-500/30") }, cronSchedulerEnabled ? "⚡" : "⏸"), React.createElement("div", null, React.createElement("div", { className: "flex items-center gap-2" }, React.createElement("span", { className: "text-xs font-bold text-white tracking-wide" }, "Periodic Cron Scheduler Engine"), React.createElement("span", { className: "px-2 py-0.5 rounded-full text-[10px] font-bold " + (cronSchedulerEnabled ? "bg-emerald-950 text-emerald-300 border border-emerald-800/60" : "bg-rose-950 text-rose-300 border border-rose-800/60") }, cronSchedulerEnabled ? "Running (15s Ticks)" : "Disabled / Paused")), React.createElement("p", { className: "text-[11px] text-slate-400 m-0 mt-0.5" }, cronSchedulerEnabled ? "Background daemon actively ticks due jobs and spawns idle improvement scanners." : "Master cron scheduler is disabled. All background ticking and autonomous scans are halted."))), React.createElement("div", { className: "flex items-center gap-2.5 shrink-0 self-end sm:self-auto" }, React.createElement("span", { className: "text-xs font-semibold " + (cronSchedulerEnabled ? "text-emerald-400" : "text-slate-500") }, cronSchedulerEnabled ? "Active" : "Disabled"), React.createElement("button", {
				type: "button",
				role: "switch",
				"aria-checked": cronSchedulerEnabled,
				onClick: () => handleToggleCronScheduler(cronSchedulerEnabled),
				className: "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none " + (cronSchedulerEnabled ? "bg-emerald-600" : "bg-slate-700")
			}, React.createElement("span", { className: "pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out " + (cronSchedulerEnabled ? "translate-x-4" : "translate-x-0") })))), React.createElement("div", { className: "px-6 py-3 border-b border-slate-800/80 bg-slate-950/40 flex flex-col sm:flex-row items-center justify-between gap-3 shrink-0" }, React.createElement("div", { className: "flex items-center gap-1.5 bg-slate-900 p-1 rounded-lg border border-slate-800 text-xs" }, React.createElement("button", {
				className: "px-2.5 py-1 rounded-md font-medium transition-colors cursor-pointer " + (cronFilterTab === "all" ? "bg-indigo-600 text-white shadow-xs" : "text-slate-400 hover:text-slate-200"),
				onClick: () => setCronFilterTab("all")
			}, "All (" + cronJobs.length + ")"), React.createElement("button", {
				className: "px-2.5 py-1 rounded-md font-medium transition-colors cursor-pointer " + (cronFilterTab === "core" ? "bg-indigo-600 text-white shadow-xs" : "text-slate-400 hover:text-slate-200"),
				onClick: () => setCronFilterTab("core")
			}, "Core (" + cronJobs.filter((j) => !j.id.startsWith("zero-factory-improvement-scanner-") && !j.id.startsWith("zero-factory-openwiki-update-") && j.category !== "scanner" && j.category !== "openwiki").length + ")"), React.createElement("button", {
				className: "px-2.5 py-1 rounded-md font-medium transition-colors cursor-pointer " + (cronFilterTab === "scanners" ? "bg-indigo-600 text-white shadow-xs" : "text-slate-400 hover:text-slate-200"),
				onClick: () => setCronFilterTab("scanners")
			}, "Scanners (" + cronJobs.filter((j) => j.id.startsWith("zero-factory-improvement-scanner-") || j.category === "scanner").length + ")"), React.createElement("button", {
				className: "px-2.5 py-1 rounded-md font-medium transition-colors cursor-pointer " + (cronFilterTab === "openwiki" ? "bg-indigo-600 text-white shadow-xs" : "text-slate-400 hover:text-slate-200"),
				onClick: () => setCronFilterTab("openwiki")
			}, "OpenWiki (" + cronJobs.filter((j) => j.id.startsWith("zero-factory-openwiki-update-") || j.category === "openwiki").length + ")")), React.createElement("input", {
				className: "w-full sm:w-64 bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 transition-colors",
				placeholder: "Search jobs by name or ID...",
				value: cronSearchQuery,
				onChange: (e) => setCronSearchQuery(e.target.value)
			}))),
			bodyClassName: "p-6 space-y-4 overflow-y-auto zfk-scrollbar flex-1 bg-slate-950/20"
		}, loadingCron && React.createElement("div", { className: "text-center py-12 text-slate-400 text-xs" }, React.createElement("span", { className: "zfk-spinning inline-block mr-2" }, "⏳"), "Loading cron schedules..."), !loadingCron && filteredCronJobs.length === 0 && React.createElement("div", { className: "text-center py-12 text-slate-500 text-xs" }, "No cron jobs match the selected filter."), !loadingCron && filteredCronJobs.map((job) => {
			const isEditing = editingCronId === job.id;
			const form = cronEditForms[job.id] || {};
			const isScanner = job.id.startsWith("zero-factory-improvement-scanner-") || job.category === "scanner";
			const isOpenWiki = job.id.startsWith("zero-factory-openwiki-update-") || job.category === "openwiki";
			const boardSlug = isScanner ? job.id.replace("zero-factory-improvement-scanner-", "") : isOpenWiki ? job.id.replace("zero-factory-openwiki-update-", "") : null;
			const isRunning = runningCronId === job.id;
			return React.createElement("div", {
				key: job.id,
				className: "bg-slate-900/90 border " + (job.enabled ? "border-slate-700/80 shadow-sm" : "border-slate-800/50 opacity-75") + " rounded-xl p-4 transition-all duration-150"
			}, React.createElement("div", { className: "flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-slate-800/80" }, React.createElement("div", { className: "flex items-start gap-2.5" }, React.createElement("span", { className: "px-2 py-0.5 rounded-md text-[10px] font-bold uppercase tracking-wider shrink-0 mt-0.5 " + (isScanner ? "bg-purple-950/80 text-purple-300 border border-purple-800/60" : isOpenWiki ? "bg-sky-950/80 text-sky-300 border border-sky-800/60" : "bg-indigo-950/80 text-indigo-300 border border-indigo-800/60") }, isScanner ? "Scanner" : isOpenWiki ? "OpenWiki" : "Core"), React.createElement("div", null, React.createElement("h3", { className: "text-sm font-semibold text-white m-0" }, job.name), React.createElement("div", { className: "flex flex-wrap items-center gap-2 mt-1 text-[11px] text-slate-400" }, React.createElement("span", { className: "text-[10px] text-slate-400 bg-slate-950/80 px-1.5 py-0.5 rounded border border-slate-800" }, job.id), boardSlug && React.createElement("span", { className: "text-amber-400/90 font-medium" }, "Board: " + boardSlug), job.workdir && React.createElement("span", { className: "truncate max-w-xs text-slate-400 font-mono text-[10px]" }, "📁 " + job.workdir)))), React.createElement("div", { className: "flex items-center gap-2.5 shrink-0 self-end sm:self-auto" }, React.createElement("span", { className: "text-xs font-semibold " + (job.enabled ? "text-emerald-400" : "text-slate-500") }, job.enabled ? "Active" : "Paused"), React.createElement("button", {
				type: "button",
				role: "switch",
				"aria-checked": job.enabled,
				onClick: () => handleToggleCronJob(job.id, job.enabled),
				className: "relative inline-flex h-5 w-9 shrink-0 cursor-pointer rounded-full border-2 border-transparent transition-colors duration-200 ease-in-out focus:outline-none " + (job.enabled ? "bg-emerald-600" : "bg-slate-700")
			}, React.createElement("span", { className: "pointer-events-none inline-block h-4 w-4 transform rounded-full bg-white shadow-md ring-0 transition duration-200 ease-in-out " + (job.enabled ? "translate-x-4" : "translate-x-0") })))), React.createElement("div", { className: "flex flex-wrap items-center justify-between gap-2 pt-3 text-xs" }, React.createElement("div", { className: "flex flex-wrap items-center gap-2" }, React.createElement("span", { className: "px-2 py-0.5 rounded-md bg-slate-950 border border-slate-800 font-mono text-[11px] text-indigo-300 font-medium" }, "⏱️ " + (job.scan_on_idle || job.schedule_display === "every 10080m" || job.schedule && job.schedule.minutes === 10080 ? "on idle" : job.schedule_display || "on idle")), React.createElement("span", { className: "px-2 py-0.5 rounded-md text-[11px] font-medium border " + (!job.enabled ? "bg-amber-950/60 text-amber-300 border-amber-800/60" : job.last_status === "ok" ? "bg-emerald-950/60 text-emerald-300 border-emerald-800/60" : job.last_status === "error" ? "bg-rose-950/60 text-rose-300 border-rose-800/60" : "bg-slate-950 text-slate-300 border-slate-800") }, !job.enabled ? "⏸ Paused" : job.last_status === "ok" ? "✓ OK" : job.last_status === "error" ? "✕ Failed" : "⏳ Scheduled"), job.last_run_at && React.createElement("span", { className: "text-slate-400 text-[11px]" }, "Last: " + timeAgo(new Date(job.last_run_at).getTime() / 1e3)), job.custom_config && React.createElement("span", { className: "px-1.5 py-0.5 rounded text-[10px] font-semibold bg-sky-950 text-sky-300 border border-sky-800/60" }, "Customized")), React.createElement("div", { className: "flex items-center gap-2 shrink-0 ml-auto" }, React.createElement("button", {
				className: "inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-emerald-600/90 hover:bg-emerald-600 text-white shadow-xs transition-colors cursor-pointer disabled:opacity-50",
				disabled: isRunning,
				onClick: () => handleRunCronJob(job.id),
				title: "Run this job immediately"
			}, isRunning ? React.createElement("span", { className: "zfk-spinning" }, "⏳") : "▶", isRunning ? " Running..." : " Run Now"), React.createElement("button", {
				className: "inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold " + (job.enabled ? "bg-slate-800 hover:bg-rose-950/50 text-slate-300 hover:text-rose-300 border border-slate-700 hover:border-rose-800/60" : "bg-emerald-950/80 hover:bg-emerald-900 text-emerald-300 border border-emerald-700/80") + " transition-colors cursor-pointer",
				onClick: () => handleToggleCronJob(job.id, job.enabled),
				title: job.enabled ? "Pause scheduled automation for this job" : "Resume scheduled automation for this job"
			}, job.enabled ? "⏸ Pause" : "▶ Resume"), React.createElement("button", {
				className: "inline-flex items-center gap-1 px-2.5 py-1 rounded-lg text-xs font-semibold bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700 transition-colors cursor-pointer",
				onClick: () => setEditingCronId(isEditing ? null : job.id),
				title: isEditing ? "Close configuration editor" : "Edit schedule and parameters"
			}, isEditing ? "▲ Close" : "⚙ Edit"), job.custom_config && React.createElement("button", {
				className: "inline-flex items-center gap-1 px-2 py-1 rounded-lg text-[11px] font-semibold text-slate-400 hover:text-amber-300 hover:bg-amber-950/30 border border-transparent hover:border-amber-800/40 transition-colors cursor-pointer",
				onClick: () => handleResetCronJob(job.id),
				title: "Reset schedule and settings to built-in default"
			}, "↺ Reset"))), job.last_error && React.createElement("div", { className: "mt-2.5 p-2 rounded-lg bg-rose-950/40 border border-rose-900/60 text-xs text-rose-300 font-mono break-all" }, "⚠️ " + job.last_error), isEditing && React.createElement("div", { className: "mt-3.5 pt-3.5 border-t border-slate-800/80 space-y-3.5 bg-slate-950/40 -mx-4 -mb-4 p-4 rounded-b-xl" }, React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-semibold text-slate-300" }, "Schedule Presets"), React.createElement("div", { className: "flex flex-wrap gap-1.5" }, [
				...isScanner ? [{
					label: "⚡ On Idle",
					kind: "idle"
				}] : [],
				{
					label: "Every 15m",
					kind: "interval",
					minutes: 15
				},
				{
					label: "Every 30m",
					kind: "interval",
					minutes: 30
				},
				{
					label: "Every 60m",
					kind: "interval",
					minutes: 60
				},
				{
					label: "Every 120m",
					kind: "interval",
					minutes: 120
				},
				{
					label: "Daily (24h)",
					kind: "interval",
					minutes: 1440
				},
				{
					label: "Daily 09:00",
					kind: "cron",
					expr: "0 9 * * *"
				},
				{
					label: "Custom Interval",
					kind: "interval",
					custom: true
				},
				{
					label: "Custom Cron",
					kind: "cron",
					custom: true
				},
				{
					label: form.enabled === false ? "⏸ Paused (Selected)" : "⏸ Pause Schedule",
					kind: "pause_toggle"
				}
			].map((preset, pIdx) => {
				const isSel = preset.kind === "pause_toggle" ? form.enabled === false : preset.kind === "idle" ? form.enabled !== false && form.scan_on_idle === true : form.enabled !== false && (!isScanner || form.scan_on_idle !== true) && (preset.custom ? form.schedule_kind === preset.kind && form.is_custom_mode === preset.kind : form.schedule_kind === preset.kind && (preset.kind === "interval" ? parseInt(form.minutes, 10) === preset.minutes : form.cron_expr === preset.expr));
				return React.createElement("button", {
					key: pIdx,
					type: "button",
					className: "px-2.5 py-1 rounded-md text-xs font-medium border transition-colors cursor-pointer " + (isSel ? preset.kind === "pause_toggle" ? "bg-rose-600 text-white border-rose-500 shadow-xs" : preset.kind === "idle" ? "bg-purple-600 text-white border-purple-500 shadow-xs" : "bg-indigo-600 text-white border-indigo-500 shadow-xs" : preset.kind === "pause_toggle" ? "bg-rose-950/40 text-rose-300 border-rose-900/60 hover:bg-rose-900/60" : preset.kind === "idle" ? "bg-purple-950/40 text-purple-300 border-purple-800/60 hover:bg-purple-500/30" : "bg-slate-900 text-slate-300 border-slate-700 hover:bg-slate-800"),
					onClick: () => {
						if (preset.kind === "pause_toggle") setCronEditForms({
							...cronEditForms,
							[job.id]: {
								...form,
								enabled: form.enabled === false
							}
						});
						else if (preset.kind === "idle") setCronEditForms({
							...cronEditForms,
							[job.id]: {
								...form,
								scan_on_idle: true,
								schedule_kind: "idle",
								is_custom_mode: null,
								enabled: true
							}
						});
						else if (preset.custom) setCronEditForms({
							...cronEditForms,
							[job.id]: {
								...form,
								scan_on_idle: false,
								schedule_kind: preset.kind,
								is_custom_mode: preset.kind,
								enabled: true
							}
						});
						else if (preset.kind === "interval") setCronEditForms({
							...cronEditForms,
							[job.id]: {
								...form,
								scan_on_idle: false,
								schedule_kind: "interval",
								minutes: preset.minutes,
								is_custom_mode: null,
								enabled: true
							}
						});
						else setCronEditForms({
							...cronEditForms,
							[job.id]: {
								...form,
								scan_on_idle: false,
								schedule_kind: "cron",
								cron_expr: preset.expr,
								is_custom_mode: null,
								enabled: true
							}
						});
					}
				}, preset.label);
			}))), isScanner && form.scan_on_idle === true ? null : form.schedule_kind === "interval" ? React.createElement("div", { className: "space-y-1" }, React.createElement("label", { className: "block text-xs font-medium text-slate-400" }, "Interval (Minutes)"), React.createElement("input", {
				type: "number",
				min: 1,
				max: 10080,
				className: "w-full max-w-xs bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 outline-none focus:border-indigo-500",
				value: form.minutes || 60,
				onChange: (e) => setCronEditForms({
					...cronEditForms,
					[job.id]: {
						...form,
						minutes: e.target.value
					}
				})
			})) : React.createElement("div", { className: "space-y-1" }, React.createElement("label", { className: "block text-xs font-medium text-slate-400" }, "Standard Cron Expression (minute hour dom month dow)"), React.createElement("input", {
				type: "text",
				placeholder: "e.g. 0 9 * * *",
				className: "w-full max-w-xs bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs font-mono text-slate-200 outline-none focus:border-indigo-500",
				value: form.cron_expr || "0 9 * * *",
				onChange: (e) => setCronEditForms({
					...cronEditForms,
					[job.id]: {
						...form,
						cron_expr: e.target.value
					}
				})
			})), React.createElement("div", { className: "grid grid-cols-1 sm:grid-cols-2 gap-3" }, React.createElement("div", { className: "space-y-1" }, React.createElement("label", { className: "block text-xs font-medium text-slate-400" }, "Model Override (optional)"), React.createElement("input", {
				type: "text",
				placeholder: "Inherit environment default",
				className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs text-slate-200 outline-none focus:border-indigo-500",
				value: form.model || "",
				onChange: (e) => setCronEditForms({
					...cronEditForms,
					[job.id]: {
						...form,
						model: e.target.value
					}
				})
			})), React.createElement("div", { className: "space-y-1" }, React.createElement("label", { className: "block text-xs font-medium text-slate-400" }, "Working Directory (Worktree Root)"), React.createElement("input", {
				type: "text",
				placeholder: "/path/to/workspace",
				className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-1.5 text-xs font-mono text-slate-200 outline-none focus:border-indigo-500",
				value: form.workdir || "",
				onChange: (e) => setCronEditForms({
					...cronEditForms,
					[job.id]: {
						...form,
						workdir: e.target.value
					}
				})
			}))), React.createElement("div", { className: "flex items-center justify-between p-3 rounded-xl bg-slate-900/90 border border-slate-800" }, React.createElement("div", null, React.createElement("span", { className: "text-xs font-semibold text-white block" }, "Schedule Status"), React.createElement("span", { className: "text-[11px] text-slate-400 block mt-0.5" }, form.enabled !== false ? "Job runs periodically according to schedule." : "Schedule is paused — job will not trigger automatically.")), React.createElement("button", {
				type: "button",
				className: "px-3 py-1.5 rounded-lg text-xs font-semibold transition-colors cursor-pointer border " + (form.enabled !== false ? "bg-emerald-950 text-emerald-300 border-emerald-700/80 hover:bg-emerald-900" : "bg-rose-950 text-rose-300 border-rose-700/80 hover:bg-rose-900"),
				onClick: () => setCronEditForms({
					...cronEditForms,
					[job.id]: {
						...form,
						enabled: form.enabled === false
					}
				})
			}, form.enabled !== false ? "✓ Scheduled (Active)" : "⏸ Paused (Disabled)")), isScanner && React.createElement("div", { className: "p-3 rounded-xl bg-slate-900/90 border border-slate-800 space-y-3" }, React.createElement("div", { className: "flex items-center justify-between" }, React.createElement("div", null, React.createElement("label", { className: "block text-xs font-semibold text-purple-300" }, "⚡ Capacity-Driven Idle Scanning"), React.createElement("p", { className: "text-[11px] text-slate-400 m-0" }, "Autonomously scan codebase when running agent workers are below board capacity.")), React.createElement("input", {
				type: "checkbox",
				className: "h-4 w-4 rounded border-slate-700 bg-slate-950 text-indigo-600 focus:ring-indigo-500 cursor-pointer",
				checked: Boolean(form.scan_on_idle !== false),
				onChange: (e) => setCronEditForms({
					...cronEditForms,
					[job.id]: {
						...form,
						scan_on_idle: e.target.checked,
						schedule_kind: e.target.checked ? "idle" : form.schedule_kind === "idle" ? "interval" : form.schedule_kind
					}
				})
			})), form.scan_on_idle !== false && React.createElement("div", { className: "grid grid-cols-1 sm:grid-cols-2 gap-3 pt-1 border-t border-slate-800/80" }, React.createElement("div", { className: "space-y-1" }, React.createElement("label", { className: "block text-[11px] font-medium text-slate-300" }, "Cooldown (Minutes)"), React.createElement("input", {
				type: "number",
				min: 1,
				step: 1,
				className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-indigo-500",
				value: form.idle_scan_cooldown_minutes ?? 15,
				onChange: (e) => setCronEditForms({
					...cronEditForms,
					[job.id]: {
						...form,
						idle_scan_cooldown_minutes: e.target.value
					}
				})
			}), React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Minimum interval between scans.")), React.createElement("div", { className: "space-y-1" }, React.createElement("label", { className: "block text-[11px] font-medium text-slate-300" }, "Max Todo Limit"), React.createElement("input", {
				type: "number",
				min: 0,
				step: 1,
				className: "w-full bg-slate-950 border border-slate-800 rounded-lg px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-indigo-500",
				value: form.idle_scan_max_todo ?? 2,
				onChange: (e) => setCronEditForms({
					...cronEditForms,
					[job.id]: {
						...form,
						idle_scan_max_todo: e.target.value
					}
				})
			}), React.createElement("p", { className: "text-[10px] text-slate-500 m-0" }, "Suppresses scan if todo backlog >= this.")))), React.createElement("div", { className: "space-y-1" }, React.createElement("label", { className: "block text-xs font-medium text-slate-400" }, "Task Prompt Instructions"), React.createElement("textarea", {
				rows: 5,
				className: "w-full bg-slate-950 border border-slate-800 rounded-lg p-2.5 text-[11px] font-mono text-slate-300 outline-none focus:border-indigo-500 zfk-scrollbar leading-relaxed",
				value: form.prompt || "",
				onChange: (e) => setCronEditForms({
					...cronEditForms,
					[job.id]: {
						...form,
						prompt: e.target.value
					}
				})
			})), React.createElement("div", { className: "flex items-center justify-end gap-2 pt-2" }, React.createElement("button", {
				type: "button",
				className: "px-3 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 transition-colors cursor-pointer",
				onClick: () => setEditingCronId(null)
			}, "Cancel"), React.createElement("button", {
				type: "button",
				className: "px-3.5 py-1.5 rounded-lg text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 shadow-xs transition-colors cursor-pointer",
				onClick: () => handleSaveCronJob(job.id)
			}, "💾 Save Configuration"))));
		}));
	}
	//#endregion
	//#region dashboard/src/modals/AddMemoryModal.jsx
	function AddMemoryModal(props) {
		const { showAddMemoryModal, setShowAddMemoryModal, newMemoryForm, setNewMemoryForm, handleCreateMemorySubmit, submittingMemory, selectedBoard, boards } = props;
		if (!showAddMemoryModal) return null;
		return React.createElement(Modal, {
			isOpen: showAddMemoryModal,
			onClose: () => setShowAddMemoryModal(false),
			onSubmit: handleCreateMemorySubmit,
			title: "Record Repository Memory",
			subtitle: "Persist decisions, conventions, and gotchas for " + (selectedBoard === "all" ? "all boards" : selectedBoard || "board"),
			icon: "🧠",
			footerClassName: "px-6 py-3.5 bg-slate-900/50 border-t border-slate-800 flex items-center justify-end gap-2.5 shrink-0",
			footer: React.createElement(React.Fragment, null, React.createElement("button", {
				type: "button",
				className: "px-4 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors cursor-pointer",
				onClick: () => setShowAddMemoryModal(false)
			}, "Cancel"), React.createElement("button", {
				type: "submit",
				disabled: submittingMemory,
				className: "inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-500 transition-colors cursor-pointer shadow-xs shadow-indigo-600/30 disabled:opacity-50"
			}, submittingMemory && React.createElement("span", { className: "zfk-spinning" }, "⏳"), "Save Memory"))
		}, (selectedBoard === "all" || !selectedBoard) && boards && boards.length > 0 && React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-medium text-slate-300" }, "Target Board *"), React.createElement("select", {
			className: "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer",
			value: newMemoryForm.board_slug || (boards[0] ? boards[0].slug : ""),
			onChange: (e) => setNewMemoryForm({
				...newMemoryForm,
				board_slug: e.target.value
			})
		}, boards.map((b) => React.createElement("option", {
			key: b.slug,
			value: b.slug
		}, b.slug)))), React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-medium text-slate-300" }, "Category"), React.createElement("select", {
			className: "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer",
			value: newMemoryForm.category,
			onChange: (e) => setNewMemoryForm({
				...newMemoryForm,
				category: e.target.value
			})
		}, React.createElement("option", { value: "convention" }, "📐 Convention (Architecture / Style / Code Rules)"), React.createElement("option", { value: "gotcha" }, "⚠️ Gotcha (Pitfall / Bug to Avoid)"), React.createElement("option", { value: "decision" }, "💡 Decision (Key Architectural Decision)"), React.createElement("option", { value: "rejected_path" }, "🚫 Rejected Path (Alternative Tried & Discarded)"), React.createElement("option", { value: "general" }, "📝 General Knowledge"))), React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-medium text-slate-300" }, "Memory / Knowledge Content *"), React.createElement("textarea", {
			required: true,
			rows: 4,
			placeholder: "e.g. Always run 'python3 -m unittest test_plugin.py' before marking tasks done, as SQLite cascade triggers are verified there.",
			className: "w-full bg-slate-800 border border-slate-700 rounded-lg p-3 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-none font-sans",
			value: newMemoryForm.content,
			onChange: (e) => setNewMemoryForm({
				...newMemoryForm,
				content: e.target.value
			})
		})), React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-medium text-slate-300" }, "Tags (comma-separated)"), React.createElement("input", {
			type: "text",
			placeholder: "sqlite, tests, git, caching",
			className: "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500",
			value: newMemoryForm.tags,
			onChange: (e) => setNewMemoryForm({
				...newMemoryForm,
				tags: e.target.value
			})
		})), React.createElement("div", { className: "grid grid-cols-2 gap-3" }, React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-medium text-slate-300" }, "Author"), React.createElement("input", {
			type: "text",
			placeholder: "user",
			className: "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500",
			value: newMemoryForm.author,
			onChange: (e) => setNewMemoryForm({
				...newMemoryForm,
				author: e.target.value
			})
		})), React.createElement("div", { className: "space-y-1.5" }, React.createElement("label", { className: "block text-xs font-medium text-slate-300" }, "Related Task ID (Optional)"), React.createElement("input", {
			type: "text",
			placeholder: "zf-xxxxxxxx",
			className: "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono",
			value: newMemoryForm.task_id || "",
			onChange: (e) => setNewMemoryForm({
				...newMemoryForm,
				task_id: e.target.value
			})
		}))));
	}
	//#endregion
	//#region dashboard/src/App.jsx
	function ZeroFactoryKanbanApp() {
		const [boards, setBoards] = useState([]);
		const [selectedBoard, setSelectedBoard] = useState("all");
		const boardsRef = useRef(boards);
		boardsRef.current = boards;
		const selectedBoardRef = useRef(selectedBoard);
		selectedBoardRef.current = selectedBoard;
		const [tasks, setTasks] = useState([]);
		const [stats, setStats] = useState(null);
		const [loading, setLoading] = useState(true);
		const [searchQuery, setSearchQuery] = useState("");
		const [assigneeFilter, setAssigneeFilter] = useState("all");
		const [priorityFilter, setPriorityFilter] = useState("all");
		const [prFilter, setPrFilter] = useState("all");
		const [autoRefresh, setAutoRefresh] = useState(true);
		const [isDispatching, setIsDispatching] = useState(false);
		const [dragOverCol, setDragOverCol] = useState(null);
		const [toast, setToast] = useState(null);
		const [selectedTask, setSelectedTask] = useState(null);
		const [showNewTaskModal, setShowNewTaskModal] = useState(false);
		const [showNewBoardModal, setShowNewBoardModal] = useState(false);
		const [showEditBoardModal, setShowEditBoardModal] = useState(false);
		const [showCronModal, setShowCronModal] = useState(false);
		const [showSettingsModal, setShowSettingsModal] = useState(false);
		const [settingsForm, setSettingsForm] = useState({
			max_active_tasks: 10,
			max_concurrent_llm_workers: 10,
			langfuse_enabled: false,
			langfuse_base_url: "https://cloud.langfuse.com",
			langfuse_public_key: "",
			langfuse_secret_key: "",
			langfuse_capture_mode: "sanitized",
			langfuse_env: "zerofactory",
			auto_record_memory: true
		});
		const [isSavingSettings, setIsSavingSettings] = useState(false);
		const [isSyncingProfiles, setIsSyncingProfiles] = useState(false);
		const [syncProfilesResult, setSyncProfilesResult] = useState(null);
		const [syncForce, setSyncForce] = useState(false);
		const [isTestingLangfuse, setIsTestingLangfuse] = useState(false);
		const [langfuseTestResult, setLangfuseTestResult] = useState(null);
		const [showLangfuseSecret, setShowLangfuseSecret] = useState(false);
		const [cronJobs, setCronJobs] = useState([]);
		const [cronSchedulerEnabled, setCronSchedulerEnabled] = useState(true);
		const [loadingCron, setLoadingCron] = useState(false);
		const [cronFilterTab, setCronFilterTab] = useState("all");
		const [runningCronId, setRunningCronId] = useState(null);
		const [editingCronId, setEditingCronId] = useState(null);
		const [cronEditForms, setCronEditForms] = useState({});
		const [cronSearchQuery, setCronSearchQuery] = useState("");
		const [newCommentText, setNewCommentText] = useState("");
		const [activeView, setActiveView] = useState("board");
		const [instructionTab, setInstructionTab] = useState("overview");
		const [selectedSessionIdx, setSelectedSessionIdx] = useState(0);
		const [sessionsList, setSessionsList] = useState([]);
		const [sessionsLoading, setSessionsLoading] = useState(false);
		const [sessionsAgentFilter, setSessionsAgentFilter] = useState("all");
		const [sessionsStatusFilter, setSessionsStatusFilter] = useState("all");
		const [sessionsSearchQuery, setSessionsSearchQuery] = useState("");
		const [stoppingSessionId, setStoppingSessionId] = useState(null);
		const [agentsList, setAgentsList] = useState([]);
		const [agentsLoading, setAgentsLoading] = useState(false);
		const [agentsSubTab, setAgentsSubTab] = useState("sessions");
		const [boardMemories, setBoardMemories] = useState([]);
		const [memoriesLoading, setMemoriesLoading] = useState(false);
		const [memoriesTotal, setMemoriesTotal] = useState(0);
		const [memoryCategoryFilter, setMemoryCategoryFilter] = useState("all");
		const [memorySearchQuery, setMemorySearchQuery] = useState("");
		const [showAddMemoryModal, setShowAddMemoryModal] = useState(false);
		const [newMemoryForm, setNewMemoryForm] = useState({
			category: "general",
			content: "",
			tags: "",
			author: "user",
			task_id: ""
		});
		const [submittingMemory, setSubmittingMemory] = useState(false);
		const [activities, setActivities] = useState([]);
		const [activitiesTotal, setActivitiesTotal] = useState(0);
		const [activitiesAgents, setActivitiesAgents] = useState([]);
		const [activitiesStats, setActivitiesStats] = useState(null);
		const [activitiesFilterOptions, setActivitiesFilterOptions] = useState({
			actors: [],
			actions: [],
			boards: [],
			assignees: []
		});
		const [activitiesLoading, setActivitiesLoading] = useState(false);
		const [activityActorFilter, setActivityActorFilter] = useState("all");
		const [activityActionFilter, setActivityActionFilter] = useState("all");
		const [activityBoardFilter, setActivityBoardFilter] = useState("all");
		const [activitySearchQuery, setActivitySearchQuery] = useState("");
		const [activityPage, setActivityPage] = useState(0);
		const [activityLimit, setActivityLimit] = useState(15);
		const [activityViewMode, setActivityViewMode] = useState("timeline");
		const [expandedActivityId, setExpandedActivityId] = useState(null);
		const [newTaskForm, setNewTaskForm] = useState({
			title: "",
			description: "",
			status: "triage",
			priority: "P2",
			assignee: "unassigned",
			tenant: "",
			pr_url: "",
			board_slug: "",
			repo_alias: ""
		});
		const [newBoardForm, setNewBoardForm] = useState({
			slug: "",
			git_url: "",
			description: "",
			target_branch: "main",
			repositories: [{
				repo_alias: "",
				git_url: "",
				target_branch: "main",
				additional_reviewer_usernames: ""
			}],
			architecture: "",
			max_concurrent_running: 1,
			auto_record_memory: true,
			additional_reviewer_usernames: "",
			jira_url: "",
			auto_setup_precommit: true
		});
		const [editBoardForm, setEditBoardForm] = useState({
			slug: "",
			git_url: "",
			description: "",
			target_branch: "main",
			architecture: "",
			repositories: [],
			max_concurrent_running: 1,
			auto_record_memory: true,
			additional_reviewer_usernames: "",
			jira_url: ""
		});
		const [precommitStatus, setPrecommitStatus] = useState(null);
		const [precommitStatuses, setPrecommitStatuses] = useState({});
		const [isLoadingPrecommit, setIsLoadingPrecommit] = useState(false);
		const [isSettingUpPrecommit, setIsSettingUpPrecommit] = useState(false);
		const [openwikiStatus, setOpenwikiStatus] = useState(null);
		const [openwikiStatuses, setOpenwikiStatuses] = useState({});
		const [isLoadingOpenwiki, setIsLoadingOpenwiki] = useState(false);
		const [isSettingUpOpenwiki, setIsSettingUpOpenwiki] = useState(false);
		const [ghIssuesStatus, setGhIssuesStatus] = useState(null);
		const [ghIssuesStatuses, setGhIssuesStatuses] = useState({});
		const [isLoadingGhIssues, setIsLoadingGhIssues] = useState(false);
		const [isSettingUpGhIssues, setIsSettingUpGhIssues] = useState(false);
		const [isSyncingIssues, setIsSyncingIssues] = useState(false);
		const [isSettingUpJira, setIsSettingUpJira] = useState(false);
		const [isTestingJira, setIsTestingJira] = useState(false);
		const [createBoardError, setCreateBoardError] = useState("");
		const [isSubmittingBoard, setIsSubmittingBoard] = useState(false);
		const [isSubmittingTask, setIsSubmittingTask] = useState(false);
		const [isTestingClone, setIsTestingClone] = useState(false);
		const [cloneTestResult, setCloneTestResult] = useState(null);
		const handleOpenNewBoardModal = () => {
			setCreateBoardError("");
			setCloneTestResult(null);
			setNewBoardForm({
				git_url: "",
				description: "",
				target_branch: "",
				max_concurrent_running: 1,
				auto_record_memory: true,
				additional_reviewer_usernames: "",
				auto_setup_precommit: true
			});
			setShowNewBoardModal(true);
		};
		const loadSettings = useCallback(async () => {
			try {
				const data = await fetchJSON(API_BASE + "/settings");
				if (data && data.settings) {
					const isCronEnabled = data.settings.enable_cron_scheduler ?? true;
					setSettingsForm({
						max_active_tasks: data.settings.max_active_tasks ?? 10,
						max_concurrent_llm_workers: data.settings.max_concurrent_llm_workers ?? 10,
						langfuse_enabled: Boolean(data.settings.langfuse_enabled),
						langfuse_base_url: data.settings.langfuse_base_url ?? "https://cloud.langfuse.com",
						langfuse_public_key: data.settings.langfuse_public_key ?? "",
						langfuse_secret_key: data.settings.langfuse_secret_key ?? "",
						langfuse_capture_mode: data.settings.langfuse_capture_mode ?? "sanitized",
						langfuse_env: data.settings.langfuse_env ?? "zerofactory",
						auto_record_memory: data.settings.auto_record_memory ?? true
					});
					setCronSchedulerEnabled(isCronEnabled);
				}
			} catch (e) {
				console.error("Failed to load settings", e);
			}
		}, []);
		const handleSaveSettings = async (e) => {
			if (e && e.preventDefault) e.preventDefault();
			setIsSavingSettings(true);
			try {
				const payload = {
					max_active_tasks: Math.max(1, parseInt(settingsForm.max_active_tasks, 10) || 10),
					max_concurrent_llm_workers: Math.max(1, parseInt(settingsForm.max_concurrent_llm_workers, 10) || 10),
					langfuse_enabled: Boolean(settingsForm.langfuse_enabled),
					langfuse_base_url: String(settingsForm.langfuse_base_url || "").trim(),
					langfuse_public_key: String(settingsForm.langfuse_public_key || "").trim(),
					langfuse_secret_key: String(settingsForm.langfuse_secret_key || "").trim(),
					langfuse_capture_mode: String(settingsForm.langfuse_capture_mode || "sanitized").trim(),
					langfuse_env: String(settingsForm.langfuse_env || "zerofactory").trim(),
					auto_record_memory: Boolean(settingsForm.auto_record_memory !== false)
				};
				const res = await fetchJSON(API_BASE + "/settings", {
					method: "PATCH",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify(payload)
				});
				if (res && res.settings) {
					res.settings.enable_cron_scheduler;
					setSettingsForm({
						max_active_tasks: res.settings.max_active_tasks ?? 10,
						max_concurrent_llm_workers: res.settings.max_concurrent_llm_workers ?? 10,
						langfuse_enabled: Boolean(res.settings.langfuse_enabled),
						langfuse_base_url: res.settings.langfuse_base_url ?? "https://cloud.langfuse.com",
						langfuse_public_key: res.settings.langfuse_public_key ?? "",
						langfuse_secret_key: res.settings.langfuse_secret_key ?? "",
						langfuse_capture_mode: res.settings.langfuse_capture_mode ?? "sanitized",
						langfuse_env: res.settings.langfuse_env ?? "zerofactory",
						auto_record_memory: res.settings.auto_record_memory ?? true
					});
				}
				showToast("Global settings saved successfully!", "success");
				setShowSettingsModal(false);
			} catch (err) {
				showToast("Failed to save settings: " + (err.message || String(err)), "error");
			} finally {
				setIsSavingSettings(false);
			}
		};
		const handleTestLangfuse = async () => {
			setIsTestingLangfuse(true);
			setLangfuseTestResult(null);
			try {
				const res = await fetchJSON(API_BASE + "/settings/langfuse/test", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({
						base_url: settingsForm.langfuse_base_url,
						public_key: settingsForm.langfuse_public_key,
						secret_key: settingsForm.langfuse_secret_key
					})
				});
				if (res && res.ok) setLangfuseTestResult({
					ok: true,
					message: res.message || "Connected successfully!"
				});
				else setLangfuseTestResult({
					ok: false,
					message: res && res.error || "Connection failed"
				});
			} catch (err) {
				setLangfuseTestResult({
					ok: false,
					message: err.message || String(err)
				});
			} finally {
				setIsTestingLangfuse(false);
			}
		};
		const handleSyncProfiles = async () => {
			setIsSyncingProfiles(true);
			setSyncProfilesResult(null);
			try {
				const queryParams = syncForce ? "?force=true" : "";
				const res = await fetchJSON(API_BASE + "/settings/profiles/sync" + queryParams, { method: "POST" });
				if (res && res.ok) {
					const detail = res.result;
					let msg = res.message || "Profiles synced successfully!";
					if (detail) {
						const parts = [];
						if (detail.updated && detail.updated.length) parts.push("Updated: " + detail.updated.join(", "));
						if (detail.created && detail.created.length) parts.push("Created: " + detail.created.join(", "));
						if (detail.existing && detail.existing.length) parts.push("Verified: " + detail.existing.join(", "));
						if (parts.length) msg = parts.join(" | ");
					}
					setSyncProfilesResult({
						ok: true,
						message: msg
					});
					showToast("Agent profiles synchronized successfully!", "success");
				} else {
					const errMsg = res && res.error || "Failed to sync profiles";
					setSyncProfilesResult({
						ok: false,
						message: errMsg
					});
					showToast(errMsg, "error");
				}
			} catch (err) {
				const errMsg = err.message || String(err);
				setSyncProfilesResult({
					ok: false,
					message: errMsg
				});
				showToast("Error syncing profiles: " + errMsg, "error");
			} finally {
				setIsSyncingProfiles(false);
			}
		};
		const showToast = useCallback((msg, type = "info") => {
			setToast({
				message: msg,
				msg,
				type
			});
			setTimeout(() => setToast(null), 3500);
		}, []);
		const loadBoards = useCallback(async () => {
			try {
				const data = await fetchJSON(API_BASE + "/boards");
				if (data && data.boards) {
					setBoards(data.boards);
					if (data.boards.length > 0) setSelectedBoard((prev) => {
						if (prev === "all") return "all";
						if (prev && data.boards.some((b) => b.slug === prev)) return prev;
						return "all";
					});
					else {
						setSelectedBoard("");
						setTasks([]);
						setStats(null);
						setShowNewBoardModal(true);
					}
				}
			} catch (err) {
				console.error("Failed to fetch boards:", err);
			}
		}, [fetchJSON]);
		const loadPrecommitStatus = useCallback(async (boardSlug, repoAlias) => {
			const bSlug = boardSlug !== void 0 ? boardSlug : selectedBoardRef.current;
			if (!bSlug || bSlug === "all") {
				setPrecommitStatus(null);
				return;
			}
			setIsLoadingPrecommit(true);
			try {
				const res = await fetchJSON(repoAlias ? API_BASE + "/boards/" + encodeURIComponent(bSlug) + "/repositories/" + encodeURIComponent(repoAlias) + "/precommit-status" : API_BASE + "/boards/" + encodeURIComponent(bSlug) + "/precommit-status");
				if (res && res.ok) {
					if (!repoAlias) setPrecommitStatus(res);
					const alias = repoAlias || res.repo_alias;
					if (alias) setPrecommitStatuses((prev) => ({
						...prev,
						[alias]: res
					}));
				} else if (!repoAlias) setPrecommitStatus(null);
			} catch (err) {
				if (!repoAlias) setPrecommitStatus(null);
			} finally {
				setIsLoadingPrecommit(false);
			}
		}, [fetchJSON]);
		const handleTriggerPrecommitSetup = async (boardSlug, repoAlias) => {
			const bSlug = boardSlug || selectedBoard;
			if (!bSlug || bSlug === "all") return;
			setIsSettingUpPrecommit(true);
			try {
				const res = await fetchJSON(repoAlias ? API_BASE + "/boards/" + encodeURIComponent(bSlug) + "/repositories/" + encodeURIComponent(repoAlias) + "/setup-precommit" : API_BASE + "/boards/" + encodeURIComponent(bSlug) + "/setup-precommit", { method: "POST" });
				if (res && res.ok) {
					showToast(res.message || "Created setup task for .zerofactory/precommit.sh!", "success");
					await Promise.all([loadPrecommitStatus(bSlug, repoAlias), loadTasksAndStats(bSlug)]);
				} else showToast(res && (res.detail || res.error || res.message) || "Failed to trigger precommit setup", "error");
			} catch (err) {
				showToast("Error initiating setup: " + (err.message || String(err)), "error");
			} finally {
				setIsSettingUpPrecommit(false);
			}
		};
		const loadOpenwikiStatus = useCallback(async (boardSlug, repoAlias) => {
			const bSlug = boardSlug !== void 0 ? boardSlug : selectedBoardRef.current;
			if (!bSlug || bSlug === "all") {
				setOpenwikiStatus(null);
				return;
			}
			setIsLoadingOpenwiki(true);
			try {
				const res = await fetchJSON(repoAlias ? API_BASE + "/boards/" + encodeURIComponent(bSlug) + "/repositories/" + encodeURIComponent(repoAlias) + "/openwiki-status" : API_BASE + "/boards/" + encodeURIComponent(bSlug) + "/openwiki-status");
				if (res && res.ok) {
					if (!repoAlias) setOpenwikiStatus(res);
					const alias = repoAlias || res.repo_alias;
					if (alias) setOpenwikiStatuses((prev) => ({
						...prev,
						[alias]: res
					}));
				} else if (!repoAlias) setOpenwikiStatus(null);
			} catch (err) {
				if (!repoAlias) setOpenwikiStatus(null);
			} finally {
				setIsLoadingOpenwiki(false);
			}
		}, [fetchJSON]);
		const handleTriggerOpenwikiSetup = async (boardSlug, repoAlias) => {
			const bSlug = boardSlug || selectedBoard;
			if (!bSlug || bSlug === "all") return;
			setIsSettingUpOpenwiki(true);
			try {
				const res = await fetchJSON(repoAlias ? API_BASE + "/boards/" + encodeURIComponent(bSlug) + "/repositories/" + encodeURIComponent(repoAlias) + "/setup-openwiki" : API_BASE + "/boards/" + encodeURIComponent(bSlug) + "/setup-openwiki", { method: "POST" });
				if (res && res.ok) {
					showToast(res.message || "Created setup task for OpenWiki!", "success");
					await Promise.all([loadOpenwikiStatus(bSlug, repoAlias), loadTasksAndStats(bSlug)]);
				} else showToast(res && (res.detail || res.error || res.message) || "Failed to trigger OpenWiki setup", "error");
			} catch (err) {
				showToast("Error initiating setup: " + (err.message || String(err)), "error");
			} finally {
				setIsSettingUpOpenwiki(false);
			}
		};
		const loadGhIssuesStatus = useCallback(async (boardSlug, repoAlias) => {
			const bSlug = boardSlug !== void 0 ? boardSlug : selectedBoardRef.current;
			if (!bSlug || bSlug === "all") {
				setGhIssuesStatus(null);
				return;
			}
			setIsLoadingGhIssues(true);
			try {
				const res = await fetchJSON(repoAlias ? API_BASE + "/boards/" + encodeURIComponent(bSlug) + "/repositories/" + encodeURIComponent(repoAlias) + "/gh-issues-status" : API_BASE + "/boards/" + encodeURIComponent(bSlug) + "/gh-issues-status");
				if (res && res.ok) {
					if (!repoAlias) setGhIssuesStatus(res);
					const alias = repoAlias || res.repo_alias;
					if (alias) setGhIssuesStatuses((prev) => ({
						...prev,
						[alias]: res
					}));
				} else if (!repoAlias) setGhIssuesStatus(null);
			} catch (err) {
				if (!repoAlias) setGhIssuesStatus(null);
			} finally {
				setIsLoadingGhIssues(false);
			}
		}, [fetchJSON]);
		const handleTriggerGhIssuesSetup = async (boardSlug, repoAlias) => {
			const bSlug = boardSlug || selectedBoard;
			if (!bSlug || bSlug === "all") return;
			setIsSettingUpGhIssues(true);
			try {
				const res = await fetchJSON(repoAlias ? API_BASE + "/boards/" + encodeURIComponent(bSlug) + "/repositories/" + encodeURIComponent(repoAlias) + "/setup-gh-issues" : API_BASE + "/boards/" + encodeURIComponent(bSlug) + "/setup-gh-issues", { method: "POST" });
				if (res && res.ok) {
					showToast(res.message || "Created setup task for GitHub Issue templates & labels!", "success");
					await Promise.all([loadGhIssuesStatus(bSlug, repoAlias), loadTasksAndStats(bSlug)]);
				} else showToast(res && (res.detail || res.error || res.message) || "Failed to trigger GitHub issues setup", "error");
			} catch (err) {
				showToast("Error initiating setup: " + (err.message || String(err)), "error");
			} finally {
				setIsSettingUpGhIssues(false);
			}
		};
		const handleSyncIssues = async (boardSlug) => {
			const bSlug = boardSlug || selectedBoard;
			if (!bSlug || bSlug === "all") {
				showToast("Please select a specific board to sync issues", "info");
				return;
			}
			setIsSyncingIssues(true);
			try {
				const res = await fetchJSON(API_BASE + "/boards/" + encodeURIComponent(bSlug) + "/sync-gh-issues", { method: "POST" });
				if (res && res.ok) {
					showToast(res.message || `Synced ${res.imported_count || 0} issues!`, "success");
					await loadTasksAndStats(bSlug);
				} else showToast(res && (res.detail || res.error || res.message) || "Failed to sync GitHub issues", "error");
			} catch (err) {
				showToast("Error syncing issues: " + (err.message || String(err)), "error");
			} finally {
				setIsSyncingIssues(false);
			}
		};
		const handleTriggerJiraSetup = async (boardSlug, jiraUrl) => {
			const bSlug = boardSlug || selectedBoard;
			if (!bSlug || bSlug === "all") return;
			setIsSettingUpJira(true);
			try {
				const res = await fetchJSON(API_BASE + "/boards/" + encodeURIComponent(bSlug) + "/setup-jira", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({ jira_url: jiraUrl !== void 0 ? jiraUrl : editBoardForm.jira_url || "" })
				});
				if (res && res.ok) {
					setEditBoardForm((prev) => ({
						...prev,
						jira_url: res.jira_url || ""
					}));
					const conn = res.connection || {};
					const msg = conn.message || res.message || "Jira Cloud link configured";
					showToast(msg, conn.connected ? "success" : "info");
					await loadBoards();
				} else showToast(res && (res.detail || res.error || res.message) || "Failed to configure Jira", "error");
			} catch (err) {
				showToast("Error configuring Jira: " + (err.message || String(err)), "error");
			} finally {
				setIsSettingUpJira(false);
			}
		};
		const handleTriggerJiraTest = async (boardSlug) => {
			const bSlug = boardSlug || selectedBoard;
			if (!bSlug || bSlug === "all") return;
			setIsTestingJira(true);
			try {
				const res = await fetchJSON(API_BASE + "/boards/" + encodeURIComponent(bSlug) + "/test-jira", { method: "POST" });
				if (res && res.ok) {
					const conn = res.connection || {};
					const msg = conn.message || res.message || "Jira tested";
					showToast(msg, conn.connected ? "success" : "warning");
				} else showToast(res && (res.detail || res.error || res.message) || "Jira test failed", "error");
			} catch (err) {
				showToast("Error testing Jira: " + (err.message || String(err)), "error");
			} finally {
				setIsTestingJira(false);
			}
		};
		const loadTasksAndStats = useCallback(async (boardSlug) => {
			const bSlug = boardSlug !== void 0 ? boardSlug : selectedBoardRef.current;
			if (!bSlug) {
				setLoading(false);
				setTasks([]);
				setStats(null);
				return;
			}
			try {
				const bParam = bSlug && bSlug !== "all" ? "?board=" + encodeURIComponent(bSlug) : "";
				const [tasksData, statsData] = await Promise.all([fetchJSON(API_BASE + "/tasks" + bParam), fetchJSON(API_BASE + "/stats" + bParam)]);
				if (tasksData && tasksData.tasks) setTasks(tasksData.tasks);
				if (statsData) setStats(statsData);
				if (bSlug && bSlug !== "all") {
					loadPrecommitStatus(bSlug);
					loadOpenwikiStatus(bSlug);
					loadGhIssuesStatus(bSlug);
				} else {
					setPrecommitStatus(null);
					setOpenwikiStatus(null);
					setGhIssuesStatus(null);
				}
			} catch (err) {
				console.error("Failed to load kanban data:", err);
			} finally {
				setLoading(false);
			}
		}, [
			fetchJSON,
			loadPrecommitStatus,
			loadOpenwikiStatus
		]);
		const loadCronJobs = useCallback(async () => {
			try {
				setLoadingCron(true);
				const data = await fetchJSON(API_BASE + "/cron");
				if (data) {
					if (typeof data.scheduler_enabled === "boolean") setCronSchedulerEnabled(data.scheduler_enabled);
					if (data.jobs) {
						setCronJobs(data.jobs);
						const forms = {};
						data.jobs.forEach((j) => {
							const sched = j.schedule || {};
							forms[j.id] = {
								minutes: sched.kind === "interval" && sched.minutes && sched.minutes !== 10080 ? sched.minutes : 60,
								cron_expr: sched.kind === "cron" ? sched.expr : "0 9 * * *",
								schedule_kind: sched.kind === "idle" ? "idle" : sched.kind || "interval",
								prompt: j.prompt || "",
								model: j.model || "",
								workdir: j.workdir || "",
								name: j.name || "",
								enabled: j.enabled !== false,
								scan_on_idle: j.scan_on_idle !== void 0 ? Boolean(j.scan_on_idle) : true,
								idle_scan_cooldown_minutes: j.idle_scan_cooldown_minutes !== void 0 ? j.idle_scan_cooldown_minutes : 15,
								idle_scan_max_todo: j.idle_scan_max_todo !== void 0 ? j.idle_scan_max_todo : 2
							};
						});
						setCronEditForms(forms);
					}
				}
			} catch (err) {
				showToast("Failed to load cron automation jobs: " + err.message, "error");
			} finally {
				setLoadingCron(false);
			}
		}, [showToast]);
		const handleToggleCronScheduler = useCallback(async (currentEnabled) => {
			try {
				const nextEnabled = !currentEnabled;
				const res = await fetchJSON(API_BASE + "/cron/scheduler/toggle", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({ enabled: nextEnabled })
				});
				if (res && res.ok) {
					showToast(nextEnabled ? "Cron scheduler activated" : "Cron scheduler paused", "success");
					setCronSchedulerEnabled(nextEnabled);
					loadCronJobs();
					loadSettings();
				} else showToast("Failed to toggle cron scheduler: " + (res.error || "Unknown error"), "error");
			} catch (err) {
				showToast("Error toggling cron scheduler: " + err.message, "error");
			}
		}, [
			loadCronJobs,
			loadSettings,
			showToast
		]);
		const handleToggleCronJob = useCallback(async (jobId, currentEnabled) => {
			try {
				const nextEnabled = !currentEnabled;
				const res = await fetchJSON(API_BASE + `/cron/${jobId}/toggle`, {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({ enabled: nextEnabled })
				});
				if (res && res.ok) {
					showToast(nextEnabled ? "Cron job activated" : "Cron job paused", "success");
					loadCronJobs();
				} else showToast("Failed to toggle cron job: " + (res.error || "Unknown error"), "error");
			} catch (err) {
				showToast("Error toggling cron job: " + err.message, "error");
			}
		}, [loadCronJobs, showToast]);
		const handleRunCronJob = useCallback(async (jobId) => {
			try {
				setRunningCronId(jobId);
				showToast(`Triggering execution for ${jobId}...`, "info");
				const res = await fetchJSON(API_BASE + `/cron/${jobId}/run`, { method: "POST" });
				if (res && res.ok) {
					const detail = res.message && res.returncode !== void 0 ? res.message : res.pid ? `PID: ${res.pid}` : "running";
					showToast(`Job completed successfully (${detail})`, "success");
					setTimeout(() => loadCronJobs(), 1500);
				} else showToast("Failed to run cron job: " + (res.error || res && res.message || "Unknown error"), "error");
			} catch (err) {
				showToast("Error running cron job: " + err.message, "error");
			} finally {
				setRunningCronId(null);
			}
		}, [loadCronJobs, showToast]);
		const handleSaveCronJob = useCallback(async (jobId) => {
			const form = cronEditForms[jobId];
			if (!form) return;
			try {
				const payload = {
					name: form.name,
					prompt: form.prompt,
					model: form.model || null,
					workdir: form.workdir || null,
					enabled: form.enabled !== false
				};
				if (form.scan_on_idle !== void 0) payload.scan_on_idle = Boolean(form.scan_on_idle);
				if (form.idle_scan_cooldown_minutes !== void 0) payload.idle_scan_cooldown_minutes = parseInt(form.idle_scan_cooldown_minutes, 10) || 15;
				if (form.idle_scan_max_todo !== void 0) payload.idle_scan_max_todo = parseInt(form.idle_scan_max_todo, 10) >= 0 ? parseInt(form.idle_scan_max_todo, 10) : 0;
				if (form.scan_on_idle) {
					payload.scan_on_idle = true;
					payload.schedule = {
						kind: "idle",
						display: "on idle"
					};
					payload.schedule_display = "on idle";
				} else {
					if (form.scan_on_idle !== void 0) payload.scan_on_idle = false;
					if (form.schedule_kind === "interval") payload.minutes = parseInt(form.minutes, 10) || 60;
					else payload.cron_expr = form.cron_expr;
				}
				const res = await fetchJSON(API_BASE + `/cron/${jobId}`, {
					method: "PUT",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify(payload)
				});
				if (res && res.ok) {
					showToast("Cron schedule & configuration saved", "success");
					setEditingCronId(null);
					loadCronJobs();
				} else showToast("Failed to save cron job: " + (res.error || "Unknown error"), "error");
			} catch (err) {
				showToast("Error saving cron job: " + err.message, "error");
			}
		}, [
			cronEditForms,
			loadCronJobs,
			showToast
		]);
		const handleResetCronJob = useCallback(async (jobId) => {
			if (!window.confirm("Reset this cron job configuration back to built-in defaults?")) return;
			try {
				const res = await fetchJSON(API_BASE + `/cron/${jobId}/reset`, { method: "POST" });
				if (res && res.ok) {
					showToast("Job reset to default configuration", "success");
					setEditingCronId(null);
					loadCronJobs();
				} else showToast("Failed to reset cron job: " + (res.error || "Unknown error"), "error");
			} catch (err) {
				showToast("Error resetting cron job: " + err.message, "error");
			}
		}, [loadCronJobs, showToast]);
		const handleSyncAllCron = useCallback(async () => {
			try {
				showToast("Synchronizing cron jobs across all stores...", "info");
				const res = await fetchJSON(API_BASE + "/cron/sync", { method: "POST" });
				if (res && res.ok) {
					showToast("Cron jobs synchronized successfully", "success");
					loadCronJobs();
				} else showToast("Failed to sync cron jobs: " + (res.error || "Unknown error"), "error");
			} catch (err) {
				showToast("Error syncing cron jobs: " + err.message, "error");
			}
		}, [loadCronJobs, showToast]);
		const loadActivities = useCallback(async (opts = {}) => {
			try {
				setActivitiesLoading(true);
				const limit = opts.limit !== void 0 ? opts.limit : activityLimit;
				const page = opts.page !== void 0 ? opts.page : activityPage;
				const actor = opts.actor !== void 0 ? opts.actor : activityActorFilter;
				const action = opts.action !== void 0 ? opts.action : activityActionFilter;
				const board = opts.board !== void 0 ? opts.board : activityBoardFilter;
				const search = opts.search !== void 0 ? opts.search : activitySearchQuery;
				const params = new URLSearchParams();
				params.set("limit", String(limit));
				params.set("offset", String(page * limit));
				if (actor && actor !== "all") params.set("actor", actor);
				if (action && action !== "all") params.set("action", action);
				if (board && board !== "all") params.set("board_slug", board);
				if (search && search.trim()) params.set("search", search.trim());
				const res = await fetchJSON(API_BASE + "/activities?" + params.toString());
				if (res && res.ok) {
					setActivities(res.activities || []);
					setActivitiesTotal(res.total || 0);
					if (res.agents) setActivitiesAgents(res.agents);
					if (res.stats) setActivitiesStats(res.stats);
					if (res.filter_options) setActivitiesFilterOptions(res.filter_options);
				}
			} catch (err) {
				console.error("Failed to load activities:", err);
			} finally {
				setActivitiesLoading(false);
			}
		}, [
			fetchJSON,
			activityLimit,
			activityPage,
			activityActorFilter,
			activityActionFilter,
			activityBoardFilter,
			activitySearchQuery
		]);
		const loadSessions = useCallback(async (boardSlug) => {
			const bSlug = boardSlug !== void 0 ? boardSlug : selectedBoardRef.current;
			try {
				setSessionsLoading(true);
				const query = bSlug && bSlug !== "all" ? "?limit=15&board_slug=" + encodeURIComponent(bSlug) : "?limit=15";
				const res = await fetchJSON(API_BASE + "/sessions" + query);
				if (res && res.ok && res.sessions) setSessionsList(res.sessions);
			} catch (err) {
				console.error("Failed to load AI sessions:", err);
			} finally {
				setSessionsLoading(false);
			}
		}, [fetchJSON]);
		const loadAgents = useCallback(async (boardSlug) => {
			const bSlug = boardSlug !== void 0 ? boardSlug : selectedBoardRef.current;
			try {
				setAgentsLoading(true);
				const query = bSlug && bSlug !== "all" ? "?board_slug=" + encodeURIComponent(bSlug) : "";
				const res = await fetchJSON(API_BASE + "/agents" + query);
				if (res && res.ok && res.agents) setAgentsList(res.agents);
			} catch (err) {
				console.error("Failed to load agents status:", err);
			} finally {
				setAgentsLoading(false);
			}
		}, [fetchJSON]);
		const loadMemories = useCallback(async (slug) => {
			const bSlug = slug !== void 0 ? slug : selectedBoardRef.current;
			if (!bSlug) return;
			try {
				setMemoriesLoading(true);
				if (bSlug === "all") {
					let allMems = [];
					let totalCount = 0;
					let fetchedViaAll = false;
					try {
						const res = await fetchJSON(API_BASE + "/boards/all/memories?limit=100");
						if (res && res.ok && Array.isArray(res.memories)) {
							allMems = res.memories;
							totalCount = res.total || allMems.length;
							fetchedViaAll = true;
						}
					} catch (_) {}
					if (!fetchedViaAll) {
						let activeBoards = boardsRef.current;
						if (!activeBoards || activeBoards.length === 0) try {
							const bData = await fetchJSON(API_BASE + "/boards");
							if (bData && bData.boards) activeBoards = bData.boards;
						} catch (_) {}
						if (activeBoards && activeBoards.length > 0) {
							const results = await Promise.all(activeBoards.map((b) => fetchJSON(API_BASE + "/boards/" + encodeURIComponent(b.slug) + "/memories?limit=100").catch(() => null)));
							const combined = [];
							const seen = /* @__PURE__ */ new Set();
							results.forEach((r) => {
								if (r && r.memories) r.memories.forEach((m) => {
									if (!seen.has(m.id)) {
										seen.add(m.id);
										combined.push(m);
									}
								});
							});
							combined.sort((a, b) => (b.created_at || 0) - (a.created_at || 0));
							allMems = combined;
							totalCount = combined.length;
						}
					}
					setBoardMemories(allMems);
					setMemoriesTotal(totalCount);
				} else {
					const res = await fetchJSON(API_BASE + "/boards/" + encodeURIComponent(bSlug) + "/memories?limit=100");
					if (res && res.ok && res.memories) {
						setBoardMemories(res.memories);
						setMemoriesTotal(res.total || res.memories.length);
					}
				}
			} catch (err) {
				console.error("Failed to load board memories:", err);
			} finally {
				setMemoriesLoading(false);
			}
		}, [fetchJSON]);
		const handleDeleteMemory = useCallback(async (memId) => {
			if (!window.confirm("Are you sure you want to delete this repository memory?")) return;
			try {
				const res = await fetchJSON(API_BASE + "/memories/" + encodeURIComponent(memId), { method: "DELETE" });
				if (res && res.ok) {
					setBoardMemories((prev) => prev.filter((m) => m.id !== memId));
					setMemoriesTotal((prev) => Math.max(0, prev - 1));
				}
			} catch (err) {
				console.error("Failed to delete memory:", err);
				window.alert("Failed to delete memory: " + (err.message || err));
			}
		}, [fetchJSON]);
		const handleCreateMemorySubmit = useCallback(async (e) => {
			if (e && e.preventDefault) e.preventDefault();
			if (!newMemoryForm.content.trim()) {
				window.alert("Memory content is required");
				return;
			}
			try {
				setSubmittingMemory(true);
				const tagList = newMemoryForm.tags ? newMemoryForm.tags.split(",").map((t) => t.trim()).filter(Boolean) : [];
				const payload = {
					category: newMemoryForm.category || "general",
					content: newMemoryForm.content.trim(),
					tags: tagList,
					author: newMemoryForm.author || "user",
					task_id: newMemoryForm.task_id || null
				};
				const targetBoard = selectedBoard && selectedBoard !== "all" ? selectedBoard : newMemoryForm.board_slug || (boards[0] ? boards[0].slug : "");
				const res = await fetchJSON(API_BASE + "/boards/" + encodeURIComponent(targetBoard) + "/memories", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify(payload)
				});
				if (res && res.ok && res.memory) {
					setBoardMemories((prev) => [res.memory, ...prev]);
					setMemoriesTotal((prev) => prev + 1);
					setShowAddMemoryModal(false);
					setNewMemoryForm({
						category: "general",
						content: "",
						tags: "",
						author: "user",
						task_id: "",
						board_slug: ""
					});
				}
			} catch (err) {
				console.error("Failed to create memory:", err);
				window.alert("Failed to create memory: " + (err.message || err));
			} finally {
				setSubmittingMemory(false);
			}
		}, [
			fetchJSON,
			newMemoryForm,
			selectedBoard,
			boards
		]);
		const initialLoadDone = useRef(false);
		useEffect(() => {
			if (initialLoadDone.current) return;
			initialLoadDone.current = true;
			loadBoards();
			loadTasksAndStats("all");
			loadCronJobs();
			loadSettings();
			loadActivities();
			loadSessions();
			loadAgents();
			loadMemories("all");
		}, [
			loadBoards,
			loadTasksAndStats,
			loadCronJobs,
			loadSettings,
			loadActivities,
			loadSessions,
			loadAgents,
			loadMemories
		]);
		const prevSelectedBoard = useRef(selectedBoard);
		useEffect(() => {
			if (prevSelectedBoard.current === selectedBoard) return;
			prevSelectedBoard.current = selectedBoard;
			if (selectedBoard) {
				loadTasksAndStats(selectedBoard);
				loadMemories(selectedBoard);
				loadSessions(selectedBoard);
				loadAgents(selectedBoard);
			}
		}, [
			selectedBoard,
			loadTasksAndStats,
			loadMemories,
			loadSessions,
			loadAgents
		]);
		useEffect(() => {
			if (activeView === "activities") loadActivities();
			else if (activeView === "sessions" || activeView === "agents") {
				loadSessions(selectedBoard);
				loadAgents(selectedBoard);
				loadMemories(selectedBoard);
				const sTimer = setInterval(() => {
					loadSessions(selectedBoard);
					loadAgents(selectedBoard);
				}, 3500);
				return () => clearInterval(sTimer);
			}
		}, [
			activeView,
			activityActorFilter,
			activityActionFilter,
			activityBoardFilter,
			activityPage,
			loadActivities,
			loadSessions,
			loadAgents,
			loadMemories,
			selectedBoard
		]);
		useEffect(() => {
			if (!autoRefresh) return;
			const timer = setInterval(() => {
				if (activeView === "activities") loadActivities();
				else if (activeView === "sessions" || activeView === "agents") {
					loadSessions(selectedBoard);
					loadAgents(selectedBoard);
				} else loadTasksAndStats(selectedBoard);
			}, 8e3);
			return () => clearInterval(timer);
		}, [
			autoRefresh,
			activeView,
			selectedBoard,
			loadTasksAndStats,
			loadActivities,
			loadSessions,
			loadAgents
		]);
		const liveAgents = useMemo(() => {
			return (activitiesAgents.length > 0 ? activitiesAgents : [
				{
					id: "zf-orchestrator",
					name: "zf-orchestrator",
					role: "Architecture & Scanner",
					status: "idle"
				},
				{
					id: "zf-builder",
					name: "zf-builder",
					role: "Implementation & Tests",
					status: "idle"
				},
				{
					id: "zf-reviewer",
					name: "zf-reviewer",
					role: "PR & Quality Gate",
					status: "idle"
				},
				{
					id: "dispatcher",
					name: "dispatcher",
					role: "Supervisor Engine",
					status: "active"
				}
			]).map((agent) => {
				const runningTask = tasks.find((t) => {
					if (t.status !== "running") return false;
					const ass = (t.assignee || "").toLowerCase();
					const aid = agent.id.toLowerCase();
					return ass === aid || ass.includes(aid);
				});
				if (runningTask && !agent.current_task) {
					const startedAt = runningTask.metadata?.started_at;
					const runningSec = startedAt ? Math.max(0, Math.floor(Date.now() / 1e3) - startedAt) : 0;
					return {
						...agent,
						status: "active",
						current_task: {
							id: runningTask.id,
							title: runningTask.title,
							board_slug: runningTask.board_slug || selectedBoard,
							priority: runningTask.priority,
							running_seconds: runningSec
						}
					};
				}
				return agent;
			});
		}, [
			activitiesAgents,
			tasks,
			selectedBoard
		]);
		const hasActiveAgents = useMemo(() => {
			return liveAgents.some((a) => a.status === "active" && a.id !== "dispatcher") || tasks.some((t) => t.status === "running");
		}, [liveAgents, tasks]);
		const effectiveActivities = useMemo(() => {
			let list = activities || [];
			if (activityActorFilter && activityActorFilter !== "all") list = list.filter((item) => {
				if (activityActorFilter === "user") return item.actor === "user";
				if (activityActorFilter === "other") return item.actor === "other" || ![
					"zf-orchestrator",
					"zf-builder",
					"zf-reviewer",
					"dispatcher",
					"user"
				].includes(item.actor);
				return item.actor === activityActorFilter;
			});
			if (activityActionFilter && activityActionFilter !== "all") list = list.filter((item) => item.action === activityActionFilter);
			if (activityBoardFilter && activityBoardFilter !== "all") list = list.filter((item) => item.board_slug === activityBoardFilter);
			if (activitySearchQuery && activitySearchQuery.trim()) {
				const q = activitySearchQuery.toLowerCase().trim();
				list = list.filter((item) => (item.details || "").toLowerCase().includes(q) || (item.task_title || "").toLowerCase().includes(q) || (item.task_id || "").toLowerCase().includes(q) || (item.actor || "").toLowerCase().includes(q) || (item.action || "").toLowerCase().includes(q));
			}
			return list;
		}, [
			activities,
			activityActorFilter,
			activityActionFilter,
			activityBoardFilter,
			activitySearchQuery
		]);
		const effectiveFilterOptions = useMemo(() => {
			const opts = {
				actors: [
					"zf-orchestrator",
					"zf-builder",
					"zf-reviewer",
					"dispatcher",
					"user",
					"other"
				],
				actions: [
					"start",
					"worker_done",
					"pr_opened",
					"merged",
					"scan",
					"comment",
					"move",
					"unblock",
					"promote",
					"approved",
					"changes_requested"
				],
				boards: boards.map((b) => typeof b === "string" ? b : b.slug || b.name).filter(Boolean)
			};
			if (activitiesFilterOptions.actions && activitiesFilterOptions.actions.length > 0) opts.actions = Array.from(/* @__PURE__ */ new Set([...opts.actions, ...activitiesFilterOptions.actions]));
			if (activitiesFilterOptions.boards && activitiesFilterOptions.boards.length > 0) opts.boards = Array.from(/* @__PURE__ */ new Set([...opts.boards, ...activitiesFilterOptions.boards]));
			if (activities && activities.length > 0) activities.forEach((a) => {
				if (a.board_slug && !opts.boards.includes(a.board_slug)) opts.boards.push(a.board_slug);
				if (a.action && !opts.actions.includes(a.action)) opts.actions.push(a.action);
			});
			return opts;
		}, [
			activitiesFilterOptions,
			boards,
			activities
		]);
		const effectiveStats = useMemo(() => {
			if (activitiesStats && activitiesStats.total_activities !== void 0) return activitiesStats;
			return {
				total_activities: effectiveActivities.length,
				actions_today: effectiveActivities.length,
				active_agents: liveAgents.filter((a) => a.status === "active" && a.id !== "dispatcher").length,
				action_breakdown: {}
			};
		}, [
			activitiesStats,
			effectiveActivities.length,
			liveAgents
		]);
		const filteredTasks = useMemo(() => {
			return tasks.filter((t) => {
				if (assigneeFilter !== "all" && t.assignee !== assigneeFilter) return false;
				if (priorityFilter !== "all" && t.priority !== priorityFilter) return false;
				if (prFilter === "has_pr" && (!t.pr_url || !t.pr_url.trim())) return false;
				if (searchQuery.trim()) {
					const q = searchQuery.toLowerCase();
					const matchTitle = (t.title || "").toLowerCase().includes(q);
					const matchDesc = (t.description || "").toLowerCase().includes(q);
					const matchId = (t.id || "").toLowerCase().includes(q);
					const matchPr = (t.pr_url || "").toLowerCase().includes(q);
					const matchBranch = (t.branch_name || "").toLowerCase().includes(q);
					if (!matchTitle && !matchDesc && !matchId && !matchPr && !matchBranch) return false;
				}
				return true;
			});
		}, [
			tasks,
			assigneeFilter,
			priorityFilter,
			prFilter,
			searchQuery
		]);
		useMemo(() => {
			return cronJobs.filter((job) => {
				const isScanner = job.id.startsWith("zero-factory-improvement-scanner-") || job.category === "scanner";
				const isOpenWiki = job.id.startsWith("zero-factory-openwiki-update-") || job.category === "openwiki";
				if (cronFilterTab === "core" && (isScanner || isOpenWiki)) return false;
				if (cronFilterTab === "scanners" && !isScanner) return false;
				if (cronFilterTab === "openwiki" && !isOpenWiki) return false;
				if (cronSearchQuery.trim()) {
					const q = cronSearchQuery.toLowerCase();
					const matchName = (job.name || "").toLowerCase().includes(q);
					const matchId = (job.id || "").toLowerCase().includes(q);
					const matchWorkdir = (job.workdir || "").toLowerCase().includes(q);
					if (!matchName && !matchId && !matchWorkdir) return false;
				}
				return true;
			});
		}, [
			cronJobs,
			cronFilterTab,
			cronSearchQuery
		]);
		const tasksByColumn = useMemo(() => {
			const map = {
				triage: [],
				todo: [],
				running: [],
				blocked: [],
				done: []
			};
			filteredTasks.forEach((t) => {
				let col = t.status || "triage";
				if (map[col]) map[col].push(t);
				else map["triage"].push(t);
			});
			return map;
		}, [filteredTasks]);
		const handleDragStart = (e, task) => {
			e.dataTransfer.setData("text/plain", task.id);
			e.dataTransfer.effectAllowed = "move";
		};
		const handleDragOver = (e, colId) => {
			e.preventDefault();
			e.dataTransfer.dropEffect = "move";
			if (dragOverCol !== colId) setDragOverCol(colId);
		};
		const handleDragLeave = (e) => {
			e.preventDefault();
			setDragOverCol(null);
		};
		const handleDrop = async (e, targetStatus) => {
			e.preventDefault();
			setDragOverCol(null);
			const taskId = e.dataTransfer.getData("text/plain");
			if (!taskId) return;
			const current = tasks.find((t) => t.id === taskId);
			if (current && current.status === targetStatus) return;
			setTasks((prev) => prev.map((t) => t.id === taskId ? {
				...t,
				status: targetStatus
			} : t));
			try {
				await fetchJSON(API_BASE + "/tasks/" + taskId + "/move", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({
						status: targetStatus,
						actor: "user"
					})
				});
				showToast("Task " + taskId + " moved to " + targetStatus, "success");
				loadTasksAndStats();
			} catch (err) {
				showToast("Failed to move task: " + err.message, "error");
				loadTasksAndStats();
			}
		};
		const handleAdvanceTask = async (task, e) => {
			if (e) e.stopPropagation();
			const nextStatus = NEXT_STATUS_MAP[task.status] || "todo";
			try {
				await fetchJSON(API_BASE + "/tasks/" + task.id + "/move", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({
						status: nextStatus,
						actor: "user"
					})
				});
				showToast("Task " + task.id + " advanced to " + nextStatus, "success");
				loadTasksAndStats();
				if (selectedTask && selectedTask.id === task.id) loadTaskDetails(task.id);
			} catch (err) {
				showToast("Error advancing task: " + err.message, "error");
			}
		};
		const loadTaskDetails = async (taskId) => {
			try {
				const res = await fetchJSON(API_BASE + "/tasks/" + taskId);
				if (res && res.task) {
					setSelectedSessionIdx(0);
					setSelectedTask(res.task);
				}
			} catch (err) {
				showToast("Failed to load task details", "error");
			}
		};
		const refreshSessionProgress = async (taskId) => {
			try {
				let prog = null;
				try {
					const res = await fetchJSON(API_BASE + "/tasks/" + taskId + "/session");
					if (res && res.session_progress) prog = res.session_progress;
				} catch (subErr) {
					const tRes = await fetchJSON(API_BASE + "/tasks/" + taskId);
					if (tRes && tRes.task && tRes.task.session_progress) prog = tRes.task.session_progress;
				}
				if (prog) {
					setSelectedTask((prev) => prev && prev.id === taskId ? {
						...prev,
						session_progress: prog
					} : prev);
					showToast("Session progress updated", "success");
				} else showToast("No active session details found", "info");
			} catch (err) {
				showToast("Failed to refresh session: " + (err.message || err), "error");
			}
		};
		const activeRunningTaskId = selectedTask && selectedTask.status === "running" ? selectedTask.id : null;
		useEffect(() => {
			if (!activeRunningTaskId) return;
			const timer = setInterval(async () => {
				try {
					const res = await fetchJSON(API_BASE + "/tasks/" + activeRunningTaskId + "/session");
					if (res && res.session_progress) setSelectedTask((prev) => prev && prev.id === activeRunningTaskId ? {
						...prev,
						session_progress: res.session_progress
					} : prev);
				} catch (e) {
					try {
						const tRes = await fetchJSON(API_BASE + "/tasks/" + activeRunningTaskId);
						if (tRes && tRes.task && tRes.task.session_progress) setSelectedTask((prev) => prev && prev.id === activeRunningTaskId ? {
							...prev,
							session_progress: tRes.task.session_progress
						} : prev);
					} catch (_) {}
				}
			}, 3500);
			return () => clearInterval(timer);
		}, [activeRunningTaskId]);
		const handleCreateTaskSubmit = async (e) => {
			e.preventDefault();
			if (!newTaskForm.title.trim()) return;
			try {
				setIsSubmittingTask(true);
				const chosenBoard = newTaskForm.board_slug && newTaskForm.board_slug !== "all" ? newTaskForm.board_slug : selectedBoard && selectedBoard !== "all" ? selectedBoard : boards[0] ? boards[0].slug : "";
				(boards || []).find((b) => b.slug === chosenBoard);
				const defaultRepo = chosenRepos[0];
				const targetRepoAlias = (newTaskForm.repo_alias || (defaultRepo ? defaultRepo.repo_alias : "")).trim() || void 0;
				const payload = {
					...newTaskForm,
					repo_alias: targetRepoAlias,
					pr_url: newTaskForm.pr_url && newTaskForm.pr_url.trim() ? newTaskForm.pr_url.trim() : null,
					board_slug: chosenBoard
				};
				const res = await fetchJSON(API_BASE + "/tasks", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify(payload)
				});
				showToast("Task " + res.id + " created!", "success");
				setShowNewTaskModal(false);
				setNewTaskForm({
					title: "",
					description: "",
					status: "triage",
					priority: "P2",
					assignee: "unassigned",
					tenant: "",
					pr_url: "",
					board_slug: "",
					repo_alias: ""
				});
				loadTasksAndStats();
			} catch (err) {
				showToast("Failed to create task: " + err.message, "error");
			} finally {
				setIsSubmittingTask(false);
			}
		};
		const computeGitSlug = (gitUrl) => {
			if (!gitUrl) return "";
			let cleaned = gitUrl.trim().replace(/\.git$/, "").replace(/\/+$/, "");
			cleaned = cleaned.replace(/^[a-zA-Z]+:\/\//, "");
			if (cleaned.includes("@")) {
				cleaned = cleaned.split("@")[1];
				if (cleaned.includes(":")) cleaned = cleaned.split(":")[1];
				else if (cleaned.includes("/")) cleaned = cleaned.split("/").slice(1).join("/");
			} else if (cleaned.includes("/")) {
				const first = cleaned.split("/")[0];
				if (first.includes(".") || first.includes(":")) cleaned = cleaned.split("/").slice(1).join("/");
			}
			const parts = cleaned.split("/").filter(Boolean);
			let repo = parts.length >= 1 ? parts[parts.length - 1].replace(/[^a-zA-Z0-9_\-.]/g, "") : "";
			let owner = parts.length >= 2 ? parts[parts.length - 2].replace(/[^a-zA-Z0-9_\-.]/g, "") : "";
			if (owner && repo) return (owner + "-" + repo).toLowerCase().replace(/[^a-zA-Z0-9_\-]/g, "-").replace(/^-+|-+$/g, "");
			if (repo) return repo.toLowerCase().replace(/[^a-zA-Z0-9_\-]/g, "-").replace(/^-+|-+$/g, "");
			return "";
		};
		const handleCreateBoardSubmit = async (e) => {
			e.preventDefault();
			const validRepos = (newBoardForm.repositories || []).filter((r) => r.git_url && r.git_url.trim());
			const firstUrl = validRepos[0]?.git_url || (newBoardForm.git_url || "").trim();
			if (!firstUrl && validRepos.length === 0) {
				showToast("Please enter at least one Remote Git URL", "warning");
				return;
			}
			const explicitSlug = (newBoardForm.slug || "").trim().toLowerCase().replace(/[^a-z0-9_-]/g, "-").replace(/-+/g, "-").replace(/^-|-$/g, "");
			const fallbackSlug = computeGitSlug(firstUrl) || (validRepos[0]?.repo_alias || "").trim();
			const targetSlug = explicitSlug || fallbackSlug;
			if (!targetSlug) {
				const msg = "Please enter a valid Board Slug or Git URL.";
				setCreateBoardError(msg);
				showToast(msg, "warning");
				return;
			}
			if (boards.some((b) => b.slug === targetSlug)) {
				const msg = "Board '" + targetSlug + "' already exists. Please choose a different board slug.";
				setCreateBoardError(msg);
				showToast(msg, "warning");
				return;
			}
			setCreateBoardError("");
			setIsSubmittingBoard(true);
			try {
				const formattedRepos = validRepos.map((r) => ({
					repo_alias: (r.repo_alias || computeGitSlug(r.git_url) || "main").trim(),
					git_url: r.git_url.trim(),
					target_branch: (r.target_branch || "main").trim(),
					additional_reviewer_usernames: typeof r.additional_reviewer_usernames === "string" ? r.additional_reviewer_usernames.split(",").map((name) => name.trim()).filter(Boolean) : r.additional_reviewer_usernames || []
				}));
				const res = await fetchJSON(API_BASE + "/boards", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({
						slug: targetSlug,
						description: (newBoardForm.description || "").trim(),
						architecture: (newBoardForm.architecture || "").trim(),
						max_concurrent_running: Math.max(1, parseInt(newBoardForm.max_concurrent_running, 10) || 1),
						auto_record_memory: Boolean(newBoardForm.auto_record_memory !== false),
						jira_url: (newBoardForm.jira_url || "").trim(),
						auto_setup_precommit: Boolean(newBoardForm.auto_setup_precommit !== false),
						repositories: formattedRepos.length > 0 ? formattedRepos : [{
							repo_alias: targetSlug,
							git_url: firstUrl,
							target_branch: (newBoardForm.target_branch || "main").trim(),
							additional_reviewer_usernames: (newBoardForm.additional_reviewer_usernames || "").split(",").map((name) => name.trim()).filter(Boolean)
						}]
					})
				});
				const createdSlug = res && res.slug ? res.slug : targetSlug;
				showToast("Board '" + createdSlug + "' created!", "success");
				setShowNewBoardModal(false);
				setNewBoardForm({
					slug: "",
					git_url: "",
					description: "",
					target_branch: "main",
					repositories: [{
						repo_alias: "",
						git_url: "",
						target_branch: "main",
						additional_reviewer_usernames: ""
					}],
					architecture: "",
					max_concurrent_running: 1,
					auto_record_memory: true,
					additional_reviewer_usernames: "",
					jira_url: "",
					auto_setup_precommit: true
				});
				setCreateBoardError("");
				await loadBoards();
				setSelectedBoard(createdSlug);
			} catch (err) {
				const msg = err && err.message ? err.message : "Failed to create board";
				setCreateBoardError(msg);
				showToast("Failed to create board: " + msg, "error");
			} finally {
				setIsSubmittingBoard(false);
			}
		};
		const handleTestClone = async (gitUrl, slug) => {
			const url = (gitUrl || "").trim();
			if (!url) {
				setCloneTestResult({
					ok: false,
					message: "Please enter a Remote Git URL to test"
				});
				return;
			}
			setIsTestingClone(true);
			setCloneTestResult(null);
			try {
				const res = await fetchJSON(API_BASE + "/boards/test-clone", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({
						git_url: url,
						slug: slug || void 0
					})
				});
				if (res && res.ok) setCloneTestResult({
					ok: true,
					message: res.message || "Git clone verified successfully!"
				});
				else setCloneTestResult({
					ok: false,
					message: res && (res.detail || res.error || res.message) || "Git clone test failed"
				});
			} catch (err) {
				setCloneTestResult({
					ok: false,
					message: err && (err.detail || err.message) || String(err)
				});
			} finally {
				setIsTestingClone(false);
			}
		};
		const handleOpenEditBoard = () => {
			if (!selectedBoard) return;
			const curr = boards.find((b) => b.slug === selectedBoard);
			if (curr) {
				setCloneTestResult(null);
				setEditBoardForm({
					slug: curr.slug || "",
					description: curr.description || "",
					git_url: curr.git_url || "",
					target_branch: curr.target_branch || "main",
					architecture: curr.architecture || "",
					repositories: curr.repositories || [],
					max_concurrent_running: typeof curr.max_concurrent_running === "number" && curr.max_concurrent_running >= 1 ? curr.max_concurrent_running : 1,
					auto_record_memory: curr.auto_record_memory !== false,
					additional_reviewer_usernames: Array.isArray(curr.additional_reviewer_usernames) ? curr.additional_reviewer_usernames.join(", ") : "",
					jira_url: curr.jira_url || ""
				});
				(curr.repositories || []).forEach((r) => {
					loadPrecommitStatus(curr.slug, r.repo_alias);
					loadOpenwikiStatus(curr.slug, r.repo_alias);
					loadGhIssuesStatus(curr.slug, r.repo_alias);
				});
				loadPrecommitStatus(curr.slug);
				loadOpenwikiStatus(curr.slug);
				loadGhIssuesStatus(curr.slug);
				setShowEditBoardModal(true);
			}
		};
		const handleUpdateBoardSubmit = async (e) => {
			e.preventDefault();
			if (!editBoardForm.slug) return;
			try {
				const formattedRepos = (editBoardForm.repositories || []).map((r) => ({
					repo_alias: (r.repo_alias || "").trim(),
					git_url: (r.git_url || "").trim(),
					target_branch: (r.target_branch || "main").trim(),
					additional_reviewer_usernames: typeof r.additional_reviewer_usernames === "string" ? r.additional_reviewer_usernames.split(",").map((name) => name.trim()).filter(Boolean) : r.additional_reviewer_usernames || []
				}));
				await fetchJSON(API_BASE + "/boards/" + encodeURIComponent(editBoardForm.slug), {
					method: "PATCH",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({
						description: (editBoardForm.description || "").trim(),
						architecture: (editBoardForm.architecture || "").trim(),
						max_concurrent_running: Math.max(1, parseInt(editBoardForm.max_concurrent_running, 10) || 1),
						auto_record_memory: Boolean(editBoardForm.auto_record_memory !== false),
						jira_url: (editBoardForm.jira_url || "").trim(),
						repositories: formattedRepos
					})
				});
				showToast("Board '" + editBoardForm.slug + "' updated!", "success");
				setShowEditBoardModal(false);
				await loadBoards();
			} catch (err) {
				showToast("Failed to update board: " + err.message, "error");
			}
		};
		const handleAddBoardRepo = async (slug, repoData) => {
			try {
				await fetchJSON(API_BASE + "/boards/" + encodeURIComponent(slug) + "/repositories", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify(repoData)
				});
				showToast("Repository '" + repoData.repo_alias + "' added to board", "success");
				await loadBoards();
				const updatedBoards = await fetchJSON(API_BASE + "/boards");
				if (updatedBoards && updatedBoards.boards) {
					const b = updatedBoards.boards.find((x) => x.slug === slug);
					if (b) setEditBoardForm((prev) => ({
						...prev,
						repositories: b.repositories || []
					}));
				}
			} catch (err) {
				showToast("Failed to add repository: " + err.message, "error");
			}
		};
		const handleDeleteBoardRepo = async (slug, repoAlias) => {
			try {
				await fetchJSON(API_BASE + "/boards/" + encodeURIComponent(slug) + "/repositories/" + encodeURIComponent(repoAlias), { method: "DELETE" });
				showToast("Repository '" + repoAlias + "' removed from board", "info");
				await loadBoards();
				const updatedBoards = await fetchJSON(API_BASE + "/boards");
				if (updatedBoards && updatedBoards.boards) {
					const b = updatedBoards.boards.find((x) => x.slug === slug);
					if (b) setEditBoardForm((prev) => ({
						...prev,
						repositories: b.repositories || []
					}));
				}
			} catch (err) {
				showToast("Failed to remove repository: " + err.message, "error");
			}
		};
		const handleDeleteBoard = async () => {
			if (!selectedBoard || selectedBoard === "all") return;
			if (!window.confirm("Are you sure you want to delete board \"" + selectedBoard + "\"?\n\nThis will permanently remove the board, all its tasks, and clear its scheduled improvement scanner job.")) return;
			try {
				await fetchJSON(API_BASE + "/boards/" + encodeURIComponent(selectedBoard), { method: "DELETE" });
				showToast("Board '" + selectedBoard + "' deleted and scanner cron cleared", "info");
				setShowEditBoardModal(false);
				const remaining = boards.filter((b) => b.slug !== selectedBoard);
				setBoards(remaining);
				const nextSlug = remaining.length > 0 ? "all" : "";
				setSelectedBoard(nextSlug);
				if (remaining.length === 0) {
					setTasks([]);
					setStats(null);
					setShowNewBoardModal(true);
				}
				await loadBoards();
			} catch (err) {
				showToast("Failed to delete board: " + err.message, "error");
			}
		};
		const handleAddCommentSubmit = async (e) => {
			e.preventDefault();
			if (!newCommentText.trim() || !selectedTask) return;
			try {
				await fetchJSON(API_BASE + "/tasks/" + selectedTask.id + "/comments", {
					method: "POST",
					headers: { "Content-Type": "application/json" },
					body: JSON.stringify({
						author: "user",
						body: newCommentText.trim()
					})
				});
				setNewCommentText("");
				loadTaskDetails(selectedTask.id);
				showToast("Comment posted", "success");
			} catch (err) {
				showToast("Failed to post comment: " + err.message, "error");
			}
		};
		const handleDeleteTask = async (taskId) => {
			if (!window.confirm("Are you sure you want to delete task " + taskId + "?")) return;
			try {
				await fetchJSON(API_BASE + "/tasks/" + taskId, { method: "DELETE" });
				showToast("Task " + taskId + " deleted", "info");
				setSelectedTask(null);
				loadTasksAndStats();
			} catch (err) {
				showToast("Failed to delete task: " + err.message, "error");
			}
		};
		const handleStopTaskSession = async (taskId, sessionId) => {
			const targetLabel = taskId ? "Task " + taskId : "Session " + (sessionId ? sessionId.slice(0, 8) + "..." : "");
			if (!window.confirm("Are you sure you want to stop this running AI session for " + targetLabel + "? The active worker process group will be safely terminated.")) return;
			setStoppingSessionId(sessionId || taskId);
			try {
				let res;
				if (taskId) res = await fetchJSON(API_BASE + "/tasks/" + encodeURIComponent(taskId) + "/stop", { method: "POST" });
				else if (sessionId) res = await fetchJSON(API_BASE + "/sessions/" + encodeURIComponent(sessionId) + "/stop", { method: "POST" });
				showToast(res?.message || "AI session stopped successfully", "info");
				loadTasksAndStats();
				if (activeView === "sessions") loadSessions();
				if (activeView === "agents") loadAgents();
				if (selectedTask && (!taskId || selectedTask.id === taskId)) loadTaskDetails(selectedTask.id);
			} catch (err) {
				showToast("Failed to stop session: " + err.message, "error");
			} finally {
				setStoppingSessionId(null);
			}
		};
		const handleRunDispatcher = async () => {
			setIsDispatching(true);
			try {
				const res = await fetchJSON(API_BASE + "/dispatch/run", { method: "POST" });
				showToast(res.message || "Dispatch cycle finished", "success");
				loadTasksAndStats();
			} catch (err) {
				showToast("Dispatch error: " + err.message, "error");
			} finally {
				setIsDispatching(false);
			}
		};
		return React.createElement("div", { className: "zerofactory-root w-full" }, React.createElement("div", { className: "max-w-[1600px] mx-auto p-4 md:p-6 space-y-6 text-slate-100 font-sans antialiased min-h-screen" }, React.createElement(Header, {
			activeView,
			setActiveView,
			hasActiveAgents,
			sessionsList,
			agentsList,
			loadSessions,
			loadAgents,
			loadMemories,
			boards,
			selectedBoard,
			setSelectedBoard,
			handleOpenEditBoard,
			handleOpenNewBoardModal,
			setShowCronModal,
			loadCronJobs,
			cronSchedulerEnabled,
			cronJobs,
			setShowSettingsModal,
			loadSettings,
			setShowNewTaskModal,
			setNewTaskForm,
			isDispatching,
			handleRunDispatcher,
			loadBoards,
			loadTasksAndStats
		}), activeView === "activities" ? React.createElement(ActivitiesView, {
			activities,
			activitiesTotal,
			activitiesAgents,
			activitiesStats,
			activitiesFilterOptions,
			activitiesLoading,
			activityActorFilter,
			setActivityActorFilter,
			activityActionFilter,
			setActivityActionFilter,
			activityBoardFilter,
			setActivityBoardFilter,
			activitySearchQuery,
			setActivitySearchQuery,
			loadActivities,
			boards,
			setActiveView,
			loadTaskDetails,
			tasks,
			liveAgents,
			effectiveActivities,
			effectiveStats,
			effectiveFilterOptions,
			activityPage,
			setActivityPage,
			activityLimit,
			activityViewMode,
			setActivityViewMode,
			autoRefresh,
			setAutoRefresh,
			expandedActivityId,
			setExpandedActivityId,
			isDispatching,
			handleRunDispatcher
		}) : activeView === "instructions" ? React.createElement(InstructionsView, {
			instructionTab,
			setInstructionTab,
			setActiveView
		}) : activeView === "sessions" || activeView === "agents" ? React.createElement(SessionsView, {
			selectedBoard,
			sessionsList,
			sessionsLoading,
			sessionsAgentFilter,
			setSessionsAgentFilter,
			sessionsStatusFilter,
			setSessionsStatusFilter,
			sessionsSearchQuery,
			setSessionsSearchQuery,
			stoppingSessionId,
			handleStopTaskSession,
			loadSessions,
			tasks,
			agentsSubTab,
			setAgentsSubTab,
			boardMemories,
			memoriesLoading,
			memoriesTotal,
			loadMemories,
			memoryCategoryFilter,
			setMemoryCategoryFilter,
			memorySearchQuery,
			setMemorySearchQuery,
			showAddMemoryModal,
			setShowAddMemoryModal,
			newMemoryForm,
			setNewMemoryForm,
			handleCreateMemorySubmit,
			submittingMemory,
			handleDeleteMemory,
			setActiveView,
			selectedSessionIdx,
			setSelectedSessionIdx,
			agentsList,
			agentsLoading,
			loadAgents,
			loadTaskDetails,
			boards,
			showToast,
			loadBoards
		}) : boards.length === 0 ? React.createElement(EmptyBoardState, {
			onNewBoard: () => setShowNewBoardModal(true),
			onInstructions: () => setActiveView("instructions")
		}) : React.createElement("div", { className: "space-y-6" }, React.createElement(StatsBar, {
			stats,
			prFilter,
			setPrFilter
		}), React.createElement(FilterBar, {
			searchQuery,
			setSearchQuery,
			assigneeFilter,
			setAssigneeFilter,
			priorityFilter,
			setPriorityFilter,
			prFilter,
			setPrFilter,
			stats,
			autoRefresh,
			setAutoRefresh,
			isSyncingIssues,
			onSyncIssues: handleSyncIssues
		}), React.createElement(SetupBanners, {
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
		}), React.createElement(KanbanBoard, {
			tasksByColumn,
			dragOverCol,
			handleDragOver,
			handleDragLeave,
			handleDrop,
			handleDragStart,
			loadTaskDetails,
			selectedBoard,
			stoppingSessionId,
			handleStopTaskSession,
			handleAdvanceTask
		})), React.createElement(TaskDetailModal, {
			selectedTask,
			setSelectedTask,
			boards,
			tasks,
			handleDeleteTask,
			handleStopTaskSession,
			stoppingSessionId,
			activeRunningTaskId,
			newCommentText,
			setNewCommentText,
			handleAddCommentSubmit,
			loadTasksAndStats,
			loadTaskDetails,
			showToast,
			selectedSessionIdx,
			setSelectedSessionIdx,
			refreshSessionProgress,
			handleAdvanceTask
		}), React.createElement(NewTaskModal, {
			showNewTaskModal,
			setShowNewTaskModal,
			newTaskForm,
			setNewTaskForm,
			handleCreateTaskSubmit,
			isSubmittingTask,
			boards,
			selectedBoard
		}), React.createElement(NewBoardModal, {
			showNewBoardModal,
			setShowNewBoardModal,
			newBoardForm,
			setNewBoardForm,
			handleCreateBoardSubmit,
			isSubmittingBoard,
			boards,
			setActiveView,
			createBoardError,
			setCreateBoardError,
			isTestingClone,
			handleTestClone,
			cloneTestResult,
			setCloneTestResult
		}), React.createElement(EditBoardModal, {
			showEditBoardModal,
			setShowEditBoardModal,
			editBoardForm,
			setEditBoardForm,
			handleUpdateBoardSubmit,
			handleDeleteBoard,
			isSubmittingBoard,
			selectedBoard,
			isTestingClone,
			handleTestClone,
			cloneTestResult,
			setCloneTestResult,
			precommitStatuses,
			precommitStatus,
			isSettingUpPrecommit,
			handleTriggerPrecommitSetup,
			openwikiStatuses,
			openwikiStatus,
			isSettingUpOpenwiki,
			handleTriggerOpenwikiSetup,
			ghIssuesStatuses,
			ghIssuesStatus,
			isSettingUpGhIssues,
			handleTriggerGhIssuesSetup,
			isSettingUpJira,
			handleTriggerJiraSetup,
			isTestingJira,
			handleTriggerJiraTest,
			handleAddBoardRepo,
			handleDeleteBoardRepo
		}), React.createElement(SettingsModal, {
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
		}), React.createElement(CronModal, {
			showCronModal,
			setShowCronModal,
			cronJobs,
			cronSchedulerEnabled,
			loadingCron,
			cronFilterTab,
			setCronFilterTab,
			cronSearchQuery,
			setCronSearchQuery,
			runningCronId,
			handleRunCronJob,
			editingCronId,
			setEditingCronId,
			cronEditForms,
			setCronEditForms,
			handleSaveCronJob,
			handleToggleCronJob,
			handleToggleCronScheduler,
			handleResetCronJob,
			handleSyncAllCron,
			loadCronJobs
		}), React.createElement(AddMemoryModal, {
			showAddMemoryModal,
			setShowAddMemoryModal,
			newMemoryForm,
			setNewMemoryForm,
			handleCreateMemorySubmit,
			submittingMemory,
			selectedBoard,
			boards
		}), React.createElement(Toast, { toast })));
	}
	//#endregion
	//#region dashboard/src/index.js
	if (typeof window !== "undefined" && window.__HERMES_PLUGINS__) window.__HERMES_PLUGINS__.register("zerofactory", ZeroFactoryKanbanApp);
	//#endregion
	exports.ZeroFactoryKanbanApp = ZeroFactoryKanbanApp;
	return exports;
})({});
