import React, { useState, useEffect, useMemo, useCallback, useRef } from "react";
import { fetchJSON } from "./sdk.js";
import { API_BASE, COLUMNS, NEXT_STATUS_MAP } from "./constants.js";
import { Header } from "./components/Header.jsx";
import { StatsBar } from "./components/StatsBar.jsx";
import { FilterBar } from "./components/FilterBar.jsx";
import { SetupBanners } from "./components/SetupBanners.jsx";
import { KanbanBoard } from "./components/KanbanBoard.jsx";
import { EmptyBoardState } from "./components/EmptyBoardState.jsx";
import { Toast } from "./components/Toast.jsx";
import { ActivitiesView } from "./views/ActivitiesView.jsx";
import { SessionsView } from "./views/SessionsView.jsx";
import { InstructionsView } from "./views/InstructionsView.jsx";
import { TaskDetailModal } from "./modals/TaskDetailModal.jsx";
import { NewTaskModal } from "./modals/NewTaskModal.jsx";
import { NewBoardModal } from "./modals/NewBoardModal.jsx";
import { EditBoardModal } from "./modals/EditBoardModal.jsx";
import { SettingsModal } from "./modals/SettingsModal.jsx";
import { CronModal } from "./modals/CronModal.jsx";
import { AddMemoryModal } from "./modals/AddMemoryModal.jsx";

export function ZeroFactoryKanbanApp() {
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

    // Modals
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
    const [activeView, setActiveView] = useState("board"); // "board" | "activities" | "sessions" | "instructions"
    const [instructionTab, setInstructionTab] = useState("overview");
    const [selectedSessionIdx, setSelectedSessionIdx] = useState(0);

    // AI Sessions View State
    const [sessionsList, setSessionsList] = useState([]);
    const [sessionsLoading, setSessionsLoading] = useState(false);
    const [sessionsAgentFilter, setSessionsAgentFilter] = useState("all");
    const [sessionsStatusFilter, setSessionsStatusFilter] = useState("all");
    const [sessionsSearchQuery, setSessionsSearchQuery] = useState("");
    const [stoppingSessionId, setStoppingSessionId] = useState(null);

    // Agents & Memory View State
    const [agentsList, setAgentsList] = useState([]);
    const [agentsLoading, setAgentsLoading] = useState(false);
    const [agentsSubTab, setAgentsSubTab] = useState("sessions"); // "sessions" | "memory"
    const [boardMemories, setBoardMemories] = useState([]);
    const [memoriesLoading, setMemoriesLoading] = useState(false);
    const [memoriesTotal, setMemoriesTotal] = useState(0);
    const [memoryCategoryFilter, setMemoryCategoryFilter] = useState("all");
    const [memorySearchQuery, setMemorySearchQuery] = useState("");
    const [showAddMemoryModal, setShowAddMemoryModal] = useState(false);
    const [newMemoryForm, setNewMemoryForm] = useState({ category: "general", content: "", tags: "", author: "user", task_id: "" });
    const [submittingMemory, setSubmittingMemory] = useState(false);

    // Activities View State
    const [activities, setActivities] = useState([]);
    const [activitiesTotal, setActivitiesTotal] = useState(0);
    const [activitiesAgents, setActivitiesAgents] = useState([]);
    const [activitiesStats, setActivitiesStats] = useState(null);
    const [activitiesFilterOptions, setActivitiesFilterOptions] = useState({ actors: [], actions: [], boards: [], assignees: [] });
    const [activitiesLoading, setActivitiesLoading] = useState(false);
    const [activityActorFilter, setActivityActorFilter] = useState("all");
    const [activityActionFilter, setActivityActionFilter] = useState("all");
    const [activityBoardFilter, setActivityBoardFilter] = useState("all");
    const [activitySearchQuery, setActivitySearchQuery] = useState("");
    const [activityPage, setActivityPage] = useState(0);
    const [activityLimit, setActivityLimit] = useState(15);
    const [activityViewMode, setActivityViewMode] = useState("timeline"); // "timeline" | "agents"
    const [expandedActivityId, setExpandedActivityId] = useState(null);

    // Form States
    const [newTaskForm, setNewTaskForm] = useState({
      title: "",
      description: "",
      status: "triage",
      priority: "P2",
      assignee: "unassigned",
      tenant: "",
      pr_url: ""
    });

    const [newBoardForm, setNewBoardForm] = useState({
      git_url: "",
      description: "",
      target_branch: "",
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
      target_branch: "",
      max_concurrent_running: 1,
      auto_record_memory: true,
      additional_reviewer_usernames: "",
      jira_url: ""
    });

    const [precommitStatus, setPrecommitStatus] = useState(null);
    const [isLoadingPrecommit, setIsLoadingPrecommit] = useState(false);
    const [isSettingUpPrecommit, setIsSettingUpPrecommit] = useState(false);

    const [openwikiStatus, setOpenwikiStatus] = useState(null);
    const [isLoadingOpenwiki, setIsLoadingOpenwiki] = useState(false);
    const [isSettingUpOpenwiki, setIsSettingUpOpenwiki] = useState(false);

    const [ghIssuesStatus, setGhIssuesStatus] = useState(null);
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
          const isCronEnabled = res.settings.enable_cron_scheduler ?? true;
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
        if (res && res.ok) {
          setLangfuseTestResult({ ok: true, message: res.message || "Connected successfully!" });
        } else {
          setLangfuseTestResult({ ok: false, message: (res && res.error) || "Connection failed" });
        }
      } catch (err) {
        setLangfuseTestResult({ ok: false, message: err.message || String(err) });
      } finally {
        setIsTestingLangfuse(false);
      }
    };

    const handleSyncProfiles = async () => {
      setIsSyncingProfiles(true);
      setSyncProfilesResult(null);
      try {
        const queryParams = syncForce ? "?force=true" : "";
        const res = await fetchJSON(API_BASE + "/settings/profiles/sync" + queryParams, {
          method: "POST"
        });
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
          setSyncProfilesResult({ ok: true, message: msg });
          showToast("Agent profiles synchronized successfully!", "success");
        } else {
          const errMsg = (res && res.error) || "Failed to sync profiles";
          setSyncProfilesResult({ ok: false, message: errMsg });
          showToast(errMsg, "error");
        }
      } catch (err) {
        const errMsg = err.message || String(err);
        setSyncProfilesResult({ ok: false, message: errMsg });
        showToast("Error syncing profiles: " + errMsg, "error");
      } finally {
        setIsSyncingProfiles(false);
      }
    };

    // Toast helper
    const showToast = useCallback((msg, type = "info") => {
      setToast({ message: msg, msg, type });
      setTimeout(() => setToast(null), 3500);
    }, []);

    // Load Boards
    const loadBoards = useCallback(async () => {
      try {
        const data = await fetchJSON(API_BASE + "/boards");
        if (data && data.boards) {
          setBoards(data.boards);
          if (data.boards.length > 0) {
            setSelectedBoard(prev => {
              if (prev === "all") return "all";
              if (prev && data.boards.some(b => b.slug === prev)) return prev;
              return "all";
            });
          } else {
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

    // Precommit status loader
    const loadPrecommitStatus = useCallback(async (boardSlug) => {
      const bSlug = boardSlug !== undefined ? boardSlug : selectedBoardRef.current;
      if (!bSlug || bSlug === "all") {
        setPrecommitStatus(null);
        return;
      }
      setIsLoadingPrecommit(true);
      try {
        const res = await fetchJSON(API_BASE + "/boards/" + encodeURIComponent(bSlug) + "/precommit-status");
        if (res && res.ok) {
          setPrecommitStatus(res);
        } else {
          setPrecommitStatus(null);
        }
      } catch (err) {
        setPrecommitStatus(null);
      } finally {
        setIsLoadingPrecommit(false);
      }
    }, [fetchJSON]);

    const handleTriggerPrecommitSetup = async (boardSlug) => {
      const bSlug = boardSlug || selectedBoard;
      if (!bSlug || bSlug === "all") return;
      setIsSettingUpPrecommit(true);
      try {
        const res = await fetchJSON(API_BASE + "/boards/" + encodeURIComponent(bSlug) + "/setup-precommit", {
          method: "POST"
        });
        if (res && res.ok) {
          showToast(res.message || "Created setup task for .zerofactory/precommit.sh!", "success");
          await Promise.all([loadPrecommitStatus(bSlug), loadTasksAndStats(bSlug)]);
        } else {
          showToast((res && (res.detail || res.error || res.message)) || "Failed to trigger precommit setup", "error");
        }
      } catch (err) {
        showToast("Error initiating setup: " + (err.message || String(err)), "error");
      } finally {
        setIsSettingUpPrecommit(false);
      }
    };

    // OpenWiki status loader
    const loadOpenwikiStatus = useCallback(async (boardSlug) => {
      const bSlug = boardSlug !== undefined ? boardSlug : selectedBoardRef.current;
      if (!bSlug || bSlug === "all") {
        setOpenwikiStatus(null);
        return;
      }
      setIsLoadingOpenwiki(true);
      try {
        const res = await fetchJSON(API_BASE + "/boards/" + encodeURIComponent(bSlug) + "/openwiki-status");
        if (res && res.ok) {
          setOpenwikiStatus(res);
        } else {
          setOpenwikiStatus(null);
        }
      } catch (err) {
        setOpenwikiStatus(null);
      } finally {
        setIsLoadingOpenwiki(false);
      }
    }, [fetchJSON]);

    const handleTriggerOpenwikiSetup = async (boardSlug) => {
      const bSlug = boardSlug || selectedBoard;
      if (!bSlug || bSlug === "all") return;
      setIsSettingUpOpenwiki(true);
      try {
        const res = await fetchJSON(API_BASE + "/boards/" + encodeURIComponent(bSlug) + "/setup-openwiki", {
          method: "POST"
        });
        if (res && res.ok) {
          showToast(res.message || "Created setup task for OpenWiki!", "success");
          await Promise.all([loadOpenwikiStatus(bSlug), loadTasksAndStats(bSlug)]);
        } else {
          showToast((res && (res.detail || res.error || res.message)) || "Failed to trigger OpenWiki setup", "error");
        }
      } catch (err) {
        showToast("Error initiating setup: " + (err.message || String(err)), "error");
      } finally {
        setIsSettingUpOpenwiki(false);
      }
    };

    // GitHub Issues status loader
    const loadGhIssuesStatus = useCallback(async (boardSlug) => {
      const bSlug = boardSlug !== undefined ? boardSlug : selectedBoardRef.current;
      if (!bSlug || bSlug === "all") {
        setGhIssuesStatus(null);
        return;
      }
      setIsLoadingGhIssues(true);
      try {
        const res = await fetchJSON(API_BASE + "/boards/" + encodeURIComponent(bSlug) + "/gh-issues-status");
        if (res && res.ok) {
          setGhIssuesStatus(res);
        } else {
          setGhIssuesStatus(null);
        }
      } catch (err) {
        setGhIssuesStatus(null);
      } finally {
        setIsLoadingGhIssues(false);
      }
    }, [fetchJSON]);

    const handleTriggerGhIssuesSetup = async (boardSlug) => {
      const bSlug = boardSlug || selectedBoard;
      if (!bSlug || bSlug === "all") return;
      setIsSettingUpGhIssues(true);
      try {
        const res = await fetchJSON(API_BASE + "/boards/" + encodeURIComponent(bSlug) + "/setup-gh-issues", {
          method: "POST"
        });
        if (res && res.ok) {
          showToast(res.message || "Created setup task for GitHub Issue templates & labels!", "success");
          await Promise.all([loadGhIssuesStatus(bSlug), loadTasksAndStats(bSlug)]);
        } else {
          showToast((res && (res.detail || res.error || res.message)) || "Failed to trigger GitHub issues setup", "error");
        }
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
        const res = await fetchJSON(API_BASE + "/boards/" + encodeURIComponent(bSlug) + "/sync-gh-issues", {
          method: "POST"
        });
        if (res && res.ok) {
          showToast(res.message || `Synced ${res.imported_count || 0} issues!`, "success");
          await loadTasksAndStats(bSlug);
        } else {
          showToast((res && (res.detail || res.error || res.message)) || "Failed to sync GitHub issues", "error");
        }
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
          body: JSON.stringify({ jira_url: jiraUrl !== undefined ? jiraUrl : (editBoardForm.jira_url || "") })
        });
        if (res && res.ok) {
          setEditBoardForm((prev) => ({ ...prev, jira_url: res.jira_url || "" }));
          const conn = res.connection || {};
          const msg = conn.message || res.message || "Jira Cloud link configured";
          showToast(msg, conn.connected ? "success" : "info");
          await loadBoards();
        } else {
          showToast((res && (res.detail || res.error || res.message)) || "Failed to configure Jira", "error");
        }
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
        const res = await fetchJSON(API_BASE + "/boards/" + encodeURIComponent(bSlug) + "/test-jira", {
          method: "POST"
        });
        if (res && res.ok) {
          const conn = res.connection || {};
          const msg = conn.message || res.message || "Jira tested";
          showToast(msg, conn.connected ? "success" : "warning");
        } else {
          showToast((res && (res.detail || res.error || res.message)) || "Jira test failed", "error");
        }
      } catch (err) {
        showToast("Error testing Jira: " + (err.message || String(err)), "error");
      } finally {
        setIsTestingJira(false);
      }
    };

    // Load Tasks & Stats
    const loadTasksAndStats = useCallback(async (boardSlug) => {
      const bSlug = boardSlug !== undefined ? boardSlug : selectedBoardRef.current;
      if (!bSlug) {
        setLoading(false);
        setTasks([]);
        setStats(null);
        return;
      }
      try {
        const bParam = (bSlug && bSlug !== "all") ? ("?board=" + encodeURIComponent(bSlug)) : "";
        const [tasksData, statsData] = await Promise.all([
          fetchJSON(API_BASE + "/tasks" + bParam),
          fetchJSON(API_BASE + "/stats" + bParam)
        ]);

        if (tasksData && tasksData.tasks) {
          setTasks(tasksData.tasks);
        }
        if (statsData) {
          setStats(statsData);
        }
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
    }, [fetchJSON, loadPrecommitStatus, loadOpenwikiStatus]);

    // Cron management handlers
    const loadCronJobs = useCallback(async () => {
      try {
        setLoadingCron(true);
        const data = await fetchJSON(API_BASE + "/cron");
        if (data) {
          if (typeof data.scheduler_enabled === "boolean") {
            setCronSchedulerEnabled(data.scheduler_enabled);
          }
          if (data.jobs) {
            setCronJobs(data.jobs);
            const forms = {};
            data.jobs.forEach(j => {
              const sched = j.schedule || {};
              forms[j.id] = {
                minutes: (sched.kind === "interval" && sched.minutes && sched.minutes !== 10080) ? sched.minutes : 60,
                cron_expr: sched.kind === "cron" ? sched.expr : "0 9 * * *",
                schedule_kind: sched.kind === "idle" ? "idle" : (sched.kind || "interval"),
                prompt: j.prompt || "",
                model: j.model || "",
                workdir: j.workdir || "",
                name: j.name || "",
                enabled: j.enabled !== false,
                scan_on_idle: j.scan_on_idle !== undefined ? Boolean(j.scan_on_idle) : true,
                idle_scan_cooldown_minutes: j.idle_scan_cooldown_minutes !== undefined ? j.idle_scan_cooldown_minutes : 15,
                idle_scan_max_todo: j.idle_scan_max_todo !== undefined ? j.idle_scan_max_todo : 2
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
        } else {
          showToast("Failed to toggle cron scheduler: " + (res.error || "Unknown error"), "error");
        }
      } catch (err) {
        showToast("Error toggling cron scheduler: " + err.message, "error");
      }
    }, [loadCronJobs, loadSettings, showToast]);

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
        } else {
          showToast("Failed to toggle cron job: " + (res.error || "Unknown error"), "error");
        }
      } catch (err) {
        showToast("Error toggling cron job: " + err.message, "error");
      }
    }, [loadCronJobs, showToast]);

    const handleRunCronJob = useCallback(async (jobId) => {
      try {
        setRunningCronId(jobId);
        showToast(`Triggering execution for ${jobId}...`, "info");
        const res = await fetchJSON(API_BASE + `/cron/${jobId}/run`, {
          method: "POST"
        });
        if (res && res.ok) {
          const detail = (res.message && res.returncode !== undefined) ? res.message : (res.pid ? `PID: ${res.pid}` : "running");
          showToast(`Job completed successfully (${detail})`, "success");
          setTimeout(() => loadCronJobs(), 1500);
        } else {
          showToast("Failed to run cron job: " + (res.error || (res && res.message) || "Unknown error"), "error");
        }
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
        if (form.scan_on_idle !== undefined) {
          payload.scan_on_idle = Boolean(form.scan_on_idle);
        }
        if (form.idle_scan_cooldown_minutes !== undefined) {
          payload.idle_scan_cooldown_minutes = parseInt(form.idle_scan_cooldown_minutes, 10) || 15;
        }
        if (form.idle_scan_max_todo !== undefined) {
          payload.idle_scan_max_todo = parseInt(form.idle_scan_max_todo, 10) >= 0 ? parseInt(form.idle_scan_max_todo, 10) : 0;
        }
        if (form.scan_on_idle) {
          payload.scan_on_idle = true;
          payload.schedule = { kind: "idle", display: "on idle" };
          payload.schedule_display = "on idle";
        } else {
          if (form.scan_on_idle !== undefined) {
            payload.scan_on_idle = false;
          }
          if (form.schedule_kind === "interval") {
            payload.minutes = parseInt(form.minutes, 10) || 60;
          } else {
            payload.cron_expr = form.cron_expr;
          }
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
        } else {
          showToast("Failed to save cron job: " + (res.error || "Unknown error"), "error");
        }
      } catch (err) {
        showToast("Error saving cron job: " + err.message, "error");
      }
    }, [cronEditForms, loadCronJobs, showToast]);

    const handleResetCronJob = useCallback(async (jobId) => {
      if (!window.confirm("Reset this cron job configuration back to built-in defaults?")) return;
      try {
        const res = await fetchJSON(API_BASE + `/cron/${jobId}/reset`, {
          method: "POST"
        });
        if (res && res.ok) {
          showToast("Job reset to default configuration", "success");
          setEditingCronId(null);
          loadCronJobs();
        } else {
          showToast("Failed to reset cron job: " + (res.error || "Unknown error"), "error");
        }
      } catch (err) {
        showToast("Error resetting cron job: " + err.message, "error");
      }
    }, [loadCronJobs, showToast]);

    const handleSyncAllCron = useCallback(async () => {
      try {
        showToast("Synchronizing cron jobs across all stores...", "info");
        const res = await fetchJSON(API_BASE + "/cron/sync", {
          method: "POST"
        });
        if (res && res.ok) {
          showToast("Cron jobs synchronized successfully", "success");
          loadCronJobs();
        } else {
          showToast("Failed to sync cron jobs: " + (res.error || "Unknown error"), "error");
        }
      } catch (err) {
        showToast("Error syncing cron jobs: " + err.message, "error");
      }
    }, [loadCronJobs, showToast]);

    // Load Activities
    const loadActivities = useCallback(async (opts = {}) => {
      try {
        setActivitiesLoading(true);
        const limit = opts.limit !== undefined ? opts.limit : activityLimit;
        const page = opts.page !== undefined ? opts.page : activityPage;
        const actor = opts.actor !== undefined ? opts.actor : activityActorFilter;
        const action = opts.action !== undefined ? opts.action : activityActionFilter;
        const board = opts.board !== undefined ? opts.board : activityBoardFilter;
        const search = opts.search !== undefined ? opts.search : activitySearchQuery;

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
    }, [fetchJSON, activityLimit, activityPage, activityActorFilter, activityActionFilter, activityBoardFilter, activitySearchQuery]);

    // Load AI Agent Sessions
    const loadSessions = useCallback(async (boardSlug) => {
      const bSlug = boardSlug !== undefined ? boardSlug : selectedBoardRef.current;
      try {
        setSessionsLoading(true);
        const query = (bSlug && bSlug !== "all") ? ("?limit=15&board_slug=" + encodeURIComponent(bSlug)) : "?limit=15";
        const res = await fetchJSON(API_BASE + "/sessions" + query);
        if (res && res.ok && res.sessions) {
          setSessionsList(res.sessions);
        }
      } catch (err) {
        console.error("Failed to load AI sessions:", err);
      } finally {
        setSessionsLoading(false);
      }
    }, [fetchJSON]);

    // Load 3 Specialist Agents Status
    const loadAgents = useCallback(async (boardSlug) => {
      const bSlug = boardSlug !== undefined ? boardSlug : selectedBoardRef.current;
      try {
        setAgentsLoading(true);
        const query = (bSlug && bSlug !== "all") ? ("?board_slug=" + encodeURIComponent(bSlug)) : "";
        const res = await fetchJSON(API_BASE + "/agents" + query);
        if (res && res.ok && res.agents) {
          setAgentsList(res.agents);
        }
      } catch (err) {
        console.error("Failed to load agents status:", err);
      } finally {
        setAgentsLoading(false);
      }
    }, [fetchJSON]);

    // Load Board Memories
    const loadMemories = useCallback(async (slug) => {
      const bSlug = slug !== undefined ? slug : selectedBoardRef.current;
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
          } catch (_) { }

          if (!fetchedViaAll) {
            let activeBoards = boardsRef.current;
            if (!activeBoards || activeBoards.length === 0) {
              try {
                const bData = await fetchJSON(API_BASE + "/boards");
                if (bData && bData.boards) activeBoards = bData.boards;
              } catch (_) { }
            }
            if (activeBoards && activeBoards.length > 0) {
              const results = await Promise.all(
                activeBoards.map((b) =>
                  fetchJSON(API_BASE + "/boards/" + encodeURIComponent(b.slug) + "/memories?limit=100")
                    .catch(() => null)
                )
              );
              const combined = [];
              const seen = new Set();
              results.forEach((r) => {
                if (r && r.memories) {
                  r.memories.forEach((m) => {
                    if (!seen.has(m.id)) {
                      seen.add(m.id);
                      combined.push(m);
                    }
                  });
                }
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
          setBoardMemories(prev => prev.filter(m => m.id !== memId));
          setMemoriesTotal(prev => Math.max(0, prev - 1));
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
        const tagList = newMemoryForm.tags ? newMemoryForm.tags.split(",").map(t => t.trim()).filter(Boolean) : [];
        const payload = {
          category: newMemoryForm.category || "general",
          content: newMemoryForm.content.trim(),
          tags: tagList,
          author: newMemoryForm.author || "user",
          task_id: newMemoryForm.task_id || null
        };
        const targetBoard = (selectedBoard && selectedBoard !== "all")
          ? selectedBoard
          : (newMemoryForm.board_slug || (boards[0] ? boards[0].slug : ""));
        const res = await fetchJSON(API_BASE + "/boards/" + encodeURIComponent(targetBoard) + "/memories", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload)
        });
        if (res && res.ok && res.memory) {
          setBoardMemories(prev => [res.memory, ...prev]);
          setMemoriesTotal(prev => prev + 1);
          setShowAddMemoryModal(false);
          setNewMemoryForm({ category: "general", content: "", tags: "", author: "user", task_id: "", board_slug: "" });
        }
      } catch (err) {
        console.error("Failed to create memory:", err);
        window.alert("Failed to create memory: " + (err.message || err));
      } finally {
        setSubmittingMemory(false);
      }
    }, [fetchJSON, newMemoryForm, selectedBoard, boards]);

    // Initial load: mount only
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
    }, [loadBoards, loadTasksAndStats, loadCronJobs, loadSettings, loadActivities, loadSessions, loadAgents, loadMemories]);

    // On selectedBoard change: reload board-specific data (tasks, stats, memories, sessions, agents)
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
    }, [selectedBoard, loadTasksAndStats, loadMemories, loadSessions, loadAgents]);

    // Fetch activities on view switch or filter changes
    useEffect(() => {
      if (activeView === "activities") {
        loadActivities();
      } else if (activeView === "sessions" || activeView === "agents") {
        loadSessions(selectedBoard);
        loadAgents(selectedBoard);
        loadMemories(selectedBoard);
        const sTimer = setInterval(() => {
          loadSessions(selectedBoard);
          loadAgents(selectedBoard);
        }, 3500);
        return () => clearInterval(sTimer);
      }
    }, [activeView, activityActorFilter, activityActionFilter, activityBoardFilter, activityPage, loadActivities, loadSessions, loadAgents, loadMemories, selectedBoard]);

    // Auto-refresh interval
    useEffect(() => {
      if (!autoRefresh) return;
      const timer = setInterval(() => {
        if (activeView === "activities") {
          loadActivities();
        } else if (activeView === "sessions" || activeView === "agents") {
          loadSessions(selectedBoard);
          loadAgents(selectedBoard);
        } else {
          loadTasksAndStats(selectedBoard);
        }
      }, 8000);
      return () => clearInterval(timer);
    }, [autoRefresh, activeView, selectedBoard, loadTasksAndStats, loadActivities, loadSessions, loadAgents]);

    const liveAgents = useMemo(() => {
      const baseAgents = activitiesAgents.length > 0 ? activitiesAgents : [
        { id: "zf-orchestrator", name: "zf-orchestrator", role: "Architecture & Scanner", status: "idle" },
        { id: "zf-builder", name: "zf-builder", role: "Implementation & Tests", status: "idle" },
        { id: "zf-reviewer", name: "zf-reviewer", role: "PR & Quality Gate", status: "idle" },
        { id: "dispatcher", name: "dispatcher", role: "Supervisor Engine", status: "active" }
      ];

      return baseAgents.map((agent) => {
        // Look up running task from tasks state matching this agent
        const runningTask = tasks.find((t) => {
          if (t.status !== "running") return false;
          const ass = (t.assignee || "").toLowerCase();
          const aid = agent.id.toLowerCase();
          return (
            ass === aid ||
            ass.includes(aid)
          );
        });

        if (runningTask && !agent.current_task) {
          const startedAt = runningTask.metadata?.started_at;
          const runningSec = startedAt ? Math.max(0, Math.floor(Date.now() / 1000) - startedAt) : 0;
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
    }, [activitiesAgents, tasks, selectedBoard]);

    const hasActiveAgents = useMemo(() => {
      return (
        liveAgents.some((a) => a.status === "active" && a.id !== "dispatcher") ||
        tasks.some((t) => t.status === "running")
      );
    }, [liveAgents, tasks]);

    const effectiveActivities = useMemo(() => {
      let list = activities || [];

      if (activityActorFilter && activityActorFilter !== "all") {
        list = list.filter((item) => {
          if (activityActorFilter === "user") {
            return item.actor === "user";
          }
          if (activityActorFilter === "other") {
            return item.actor === "other" || !["zf-orchestrator", "zf-builder", "zf-reviewer", "dispatcher", "user"].includes(item.actor);
          }
          return item.actor === activityActorFilter;
        });
      }
      if (activityActionFilter && activityActionFilter !== "all") {
        list = list.filter((item) => item.action === activityActionFilter);
      }
      if (activityBoardFilter && activityBoardFilter !== "all") {
        list = list.filter((item) => item.board_slug === activityBoardFilter);
      }
      if (activitySearchQuery && activitySearchQuery.trim()) {
        const q = activitySearchQuery.toLowerCase().trim();
        list = list.filter((item) =>
          (item.details || "").toLowerCase().includes(q) ||
          (item.task_title || "").toLowerCase().includes(q) ||
          (item.task_id || "").toLowerCase().includes(q) ||
          (item.actor || "").toLowerCase().includes(q) ||
          (item.action || "").toLowerCase().includes(q)
        );
      }
      return list;
    }, [activities, activityActorFilter, activityActionFilter, activityBoardFilter, activitySearchQuery]);

    const effectiveFilterOptions = useMemo(() => {
      const opts = {
        actors: ["zf-orchestrator", "zf-builder", "zf-reviewer", "dispatcher", "user", "other"],
        actions: ["start", "worker_done", "pr_opened", "merged", "scan", "comment", "move", "unblock", "promote", "approved", "changes_requested"],
        boards: boards.map((b) => (typeof b === "string" ? b : b.slug || b.name)).filter(Boolean)
      };
      if (activitiesFilterOptions.actions && activitiesFilterOptions.actions.length > 0) {
        opts.actions = Array.from(new Set([...opts.actions, ...activitiesFilterOptions.actions]));
      }
      if (activitiesFilterOptions.boards && activitiesFilterOptions.boards.length > 0) {
        opts.boards = Array.from(new Set([...opts.boards, ...activitiesFilterOptions.boards]));
      }
      if (activities && activities.length > 0) {
        activities.forEach((a) => {
          if (a.board_slug && !opts.boards.includes(a.board_slug)) opts.boards.push(a.board_slug);
          if (a.action && !opts.actions.includes(a.action)) opts.actions.push(a.action);
        });
      }
      return opts;
    }, [activitiesFilterOptions, boards, activities]);

    const effectiveStats = useMemo(() => {
      if (activitiesStats && activitiesStats.total_activities !== undefined) {
        return activitiesStats;
      }
      return {
        total_activities: effectiveActivities.length,
        actions_today: effectiveActivities.length,
        active_agents: liveAgents.filter((a) => a.status === "active" && a.id !== "dispatcher").length,
        action_breakdown: {}
      };
    }, [activitiesStats, effectiveActivities.length, liveAgents]);

    // Filtered Tasks
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
    }, [tasks, assigneeFilter, priorityFilter, prFilter, searchQuery]);

    // Filtered Cron Jobs
    const filteredCronJobs = useMemo(() => {
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
    }, [cronJobs, cronFilterTab, cronSearchQuery]);

    // Tasks grouped by column
    const tasksByColumn = useMemo(() => {
      const map = { triage: [], todo: [], running: [], blocked: [], done: [] };
      filteredTasks.forEach((t) => {
        let col = t.status || "triage";
        if (col === "ready") {
          col = "todo";
        }
        if (map[col]) {
          map[col].push(t);
        } else {
          map["triage"].push(t);
        }
      });
      return map;
    }, [filteredTasks]);

    // Drag & Drop Handlers
    const handleDragStart = (e, task) => {
      e.dataTransfer.setData("text/plain", task.id);
      e.dataTransfer.effectAllowed = "move";
    };

    const handleDragOver = (e, colId) => {
      e.preventDefault();
      e.dataTransfer.dropEffect = "move";
      if (dragOverCol !== colId) {
        setDragOverCol(colId);
      }
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

      // Optimistic update
      setTasks((prev) =>
        prev.map((t) => (t.id === taskId ? { ...t, status: targetStatus } : t))
      );

      try {
        await fetchJSON(API_BASE + "/tasks/" + taskId + "/move", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: targetStatus, actor: "user" })
        });
        showToast("Task " + taskId + " moved to " + targetStatus, "success");
        loadTasksAndStats();
      } catch (err) {
        showToast("Failed to move task: " + err.message, "error");
        loadTasksAndStats();
      }
    };

    // Advance task to next stage
    const handleAdvanceTask = async (task, e) => {
      if (e) e.stopPropagation();
      const nextStatus = NEXT_STATUS_MAP[task.status] || "todo";
      try {
        await fetchJSON(API_BASE + "/tasks/" + task.id + "/move", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ status: nextStatus, actor: "user" })
        });
        showToast("Task " + task.id + " advanced to " + nextStatus, "success");
        loadTasksAndStats();
        if (selectedTask && selectedTask.id === task.id) {
          loadTaskDetails(task.id);
        }
      } catch (err) {
        showToast("Error advancing task: " + err.message, "error");
      }
    };

    // Task Details
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

    // Refresh Session Progress
    const refreshSessionProgress = async (taskId) => {
      try {
        let prog = null;
        try {
          const res = await fetchJSON(API_BASE + "/tasks/" + taskId + "/session");
          if (res && res.session_progress) {
            prog = res.session_progress;
          }
        } catch (subErr) {
          // Fallback to task details if /session endpoint is unavailable
          const tRes = await fetchJSON(API_BASE + "/tasks/" + taskId);
          if (tRes && tRes.task && tRes.task.session_progress) {
            prog = tRes.task.session_progress;
          }
        }

        if (prog) {
          setSelectedTask(prev => prev && prev.id === taskId ? { ...prev, session_progress: prog } : prev);
          showToast("Session progress updated", "success");
        } else {
          showToast("No active session details found", "info");
        }
      } catch (err) {
        showToast("Failed to refresh session: " + (err.message || err), "error");
      }
    };

    // Auto-poll session progress while modal is open for a running task
    const activeRunningTaskId = (selectedTask && selectedTask.status === "running") ? selectedTask.id : null;
    useEffect(() => {
      if (!activeRunningTaskId) return;
      const timer = setInterval(async () => {
        try {
          const res = await fetchJSON(API_BASE + "/tasks/" + activeRunningTaskId + "/session");
          if (res && res.session_progress) {
            setSelectedTask(prev => prev && prev.id === activeRunningTaskId ? { ...prev, session_progress: res.session_progress } : prev);
          }
        } catch (e) {
          // Fallback poll
          try {
            const tRes = await fetchJSON(API_BASE + "/tasks/" + activeRunningTaskId);
            if (tRes && tRes.task && tRes.task.session_progress) {
              setSelectedTask(prev => prev && prev.id === activeRunningTaskId ? { ...prev, session_progress: tRes.task.session_progress } : prev);
            }
          } catch (_) { }
        }
      }, 3500);
      return () => clearInterval(timer);
    }, [activeRunningTaskId]);

    // Create Task
    const handleCreateTaskSubmit = async (e) => {
      e.preventDefault();
      if (!newTaskForm.title.trim()) return;

      try {
        setIsSubmittingTask(true);
        const chosenBoard = (newTaskForm.board_slug && newTaskForm.board_slug !== "all")
          ? newTaskForm.board_slug
          : (selectedBoard && selectedBoard !== "all"
            ? selectedBoard
            : (boards[0] ? boards[0].slug : ""));
        const payload = {
          ...newTaskForm,
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
          board_slug: ""
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
        if (first.includes(".") || first.includes(":")) {
          cleaned = cleaned.split("/").slice(1).join("/");
        }
      }
      const parts = cleaned.split("/").filter(Boolean);
      let repo = parts.length >= 1 ? parts[parts.length - 1].replace(/[^a-zA-Z0-9_\-.]/g, "") : "";
      let owner = parts.length >= 2 ? parts[parts.length - 2].replace(/[^a-zA-Z0-9_\-.]/g, "") : "";
      if (owner && repo) {
        return (owner + "-" + repo).toLowerCase().replace(/[^a-zA-Z0-9_\-]/g, "-").replace(/^-+|-+$/g, "");
      }
      if (repo) {
        return repo.toLowerCase().replace(/[^a-zA-Z0-9_\-]/g, "-").replace(/^-+|-+$/g, "");
      }
      return "";
    };

    // Create Board
    const handleCreateBoardSubmit = async (e) => {
      e.preventDefault();
      const gitUrl = (newBoardForm.git_url || "").trim();
      if (!gitUrl) {
        showToast("Please enter a Remote Git URL", "warning");
        return;
      }

      const autoSlug = computeGitSlug(gitUrl);
      if (!autoSlug) {
        const msg = "Could not derive a board slug from the URL. Please enter a valid Git URL.";
        setCreateBoardError(msg);
        showToast(msg, "warning");
        return;
      }

      if (boards.some((b) => b.slug === autoSlug)) {
        const msg = "Board '" + autoSlug + "' already exists. Please enter a different repository URL.";
        setCreateBoardError(msg);
        showToast(msg, "warning");
        return;
      }

      setCreateBoardError("");
      setIsSubmittingBoard(true);

      try {
        const res = await fetchJSON(API_BASE + "/boards", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            git_url: gitUrl,
            description: (newBoardForm.description || "").trim(),
            target_branch: (newBoardForm.target_branch || "").trim(),
            max_concurrent_running: Math.max(1, parseInt(newBoardForm.max_concurrent_running, 10) || 1),
            auto_record_memory: Boolean(newBoardForm.auto_record_memory !== false),
            additional_reviewer_usernames: (newBoardForm.additional_reviewer_usernames || "").split(",").map((name) => name.trim()).filter(Boolean),
            jira_url: (newBoardForm.jira_url || "").trim(),
            auto_setup_precommit: Boolean(newBoardForm.auto_setup_precommit !== false)
          })
        });
        const createdSlug = (res && res.slug) ? res.slug : autoSlug;
        showToast("Board '" + createdSlug + "' created!", "success");
        setShowNewBoardModal(false);
        setNewBoardForm({ git_url: "", description: "", target_branch: "", max_concurrent_running: 1, auto_record_memory: true, additional_reviewer_usernames: "", jira_url: "", auto_setup_precommit: true });
        setCreateBoardError("");
        await loadBoards();
        setSelectedBoard(createdSlug);
      } catch (err) {
        const msg = (err && err.message) ? err.message : "Failed to create board";
        setCreateBoardError(msg);
        showToast("Failed to create board: " + msg, "error");
      } finally {
        setIsSubmittingBoard(false);
      }
    };

    // Test Git Clone
    const handleTestClone = async (gitUrl, slug) => {
      const url = (gitUrl || "").trim();
      if (!url) {
        setCloneTestResult({ ok: false, message: "Please enter a Remote Git URL to test" });
        return;
      }
      setIsTestingClone(true);
      setCloneTestResult(null);
      try {
        const res = await fetchJSON(API_BASE + "/boards/test-clone", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ git_url: url, slug: slug || undefined })
        });
        if (res && res.ok) {
          setCloneTestResult({ ok: true, message: res.message || "Git clone verified successfully!" });
        } else {
          setCloneTestResult({ ok: false, message: (res && (res.detail || res.error || res.message)) || "Git clone test failed" });
        }
      } catch (err) {
        setCloneTestResult({ ok: false, message: (err && (err.detail || err.message)) || String(err) });
      } finally {
        setIsTestingClone(false);
      }
    };

    // Open Edit Board Modal
    const handleOpenEditBoard = () => {
      if (!selectedBoard) return;
      const curr = boards.find((b) => b.slug === selectedBoard);
      if (curr) {
        setCloneTestResult(null);
        setEditBoardForm({
          slug: curr.slug || "",
          description: curr.description || "",
          git_url: curr.git_url || "",
          target_branch: curr.target_branch || "",
          max_concurrent_running: (typeof curr.max_concurrent_running === "number" && curr.max_concurrent_running >= 1) ? curr.max_concurrent_running : 1,
          auto_record_memory: curr.auto_record_memory !== false,
          additional_reviewer_usernames: Array.isArray(curr.additional_reviewer_usernames) ? curr.additional_reviewer_usernames.join(", ") : "",
          jira_url: curr.jira_url || ""
        });
        loadPrecommitStatus(curr.slug);
        loadOpenwikiStatus(curr.slug);
        loadGhIssuesStatus(curr.slug);
        setShowEditBoardModal(true);
      }
    };

    // Update Board Submit
    const handleUpdateBoardSubmit = async (e) => {
      e.preventDefault();
      if (!editBoardForm.slug) return;

      try {
        await fetchJSON(API_BASE + "/boards/" + encodeURIComponent(editBoardForm.slug), {
          method: "PATCH",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({
            description: (editBoardForm.description || "").trim(),
            git_url: (editBoardForm.git_url || "").trim(),
            target_branch: (editBoardForm.target_branch || "").trim(),
            max_concurrent_running: Math.max(1, parseInt(editBoardForm.max_concurrent_running, 10) || 1),
            auto_record_memory: Boolean(editBoardForm.auto_record_memory !== false),
            additional_reviewer_usernames: (editBoardForm.additional_reviewer_usernames || "").split(",").map((name) => name.trim()).filter(Boolean),
            jira_url: (editBoardForm.jira_url || "").trim()
          })
        });
        showToast("Board '" + editBoardForm.slug + "' updated!", "success");
        setShowEditBoardModal(false);
        await loadBoards();
      } catch (err) {
        showToast("Failed to update board: " + err.message, "error");
      }
    };

    // Delete Board
    const handleDeleteBoard = async () => {
      if (!selectedBoard || selectedBoard === "all") return;
      if (
        !window.confirm(
          "Are you sure you want to delete board \"" + selectedBoard + "\"?\n\nThis will permanently remove the board, all its tasks, and clear its scheduled improvement scanner job."
        )
      ) {
        return;
      }

      try {
        await fetchJSON(API_BASE + "/boards/" + encodeURIComponent(selectedBoard), {
          method: "DELETE"
        });
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

    // Add Comment
    const handleAddCommentSubmit = async (e) => {
      e.preventDefault();
      if (!newCommentText.trim() || !selectedTask) return;

      try {
        await fetchJSON(API_BASE + "/tasks/" + selectedTask.id + "/comments", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ author: "user", body: newCommentText.trim() })
        });
        setNewCommentText("");
        loadTaskDetails(selectedTask.id);
        showToast("Comment posted", "success");
      } catch (err) {
        showToast("Failed to post comment: " + err.message, "error");
      }
    };

    // Delete Task
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

    // Stop / Abort AI Session
    const handleStopTaskSession = async (taskId, sessionId) => {
      const targetLabel = taskId ? ("Task " + taskId) : ("Session " + (sessionId ? sessionId.slice(0, 8) + "..." : ""));
      if (!window.confirm("Are you sure you want to stop this running AI session for " + targetLabel + "? The active worker process group will be safely terminated.")) {
        return;
      }
      const stopKey = sessionId || taskId;
      setStoppingSessionId(stopKey);
      try {
        let res;
        if (taskId) {
          res = await fetchJSON(API_BASE + "/tasks/" + encodeURIComponent(taskId) + "/stop", { method: "POST" });
        } else if (sessionId) {
          res = await fetchJSON(API_BASE + "/sessions/" + encodeURIComponent(sessionId) + "/stop", { method: "POST" });
        }
        showToast(res?.message || "AI session stopped successfully", "info");
        loadTasksAndStats();
        if (activeView === "sessions") {
          loadSessions();
        }
        if (activeView === "agents") {
          loadAgents();
        }
        if (selectedTask && (!taskId || selectedTask.id === taskId)) {
          loadTaskDetails(selectedTask.id);
        }
      } catch (err) {
        showToast("Failed to stop session: " + err.message, "error");
      } finally {
        setStoppingSessionId(null);
      }
    };

    // Run Dispatcher
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


  return React.createElement(
    "div",
    { className: "zerofactory-root w-full" },
    React.createElement(
      "div",
      { className: "max-w-[1600px] mx-auto p-4 md:p-6 space-y-6 text-slate-100 font-sans antialiased min-h-screen" },
      React.createElement(Header, {
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
      }),
      activeView === "activities"
        ? React.createElement(ActivitiesView, {
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
          })
        : activeView === "instructions"
          ? React.createElement(InstructionsView, {
              instructionTab,
              setInstructionTab,
              setActiveView
            })
          : (activeView === "sessions" || activeView === "agents")
            ? React.createElement(SessionsView, {
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
              })
            : boards.length === 0
              ? React.createElement(EmptyBoardState, {
                  onNewBoard: () => setShowNewBoardModal(true),
                  onInstructions: () => setActiveView("instructions")
                })
              : React.createElement(
                  "div",
                  { className: "space-y-6" },
                  React.createElement(StatsBar, { stats, prFilter, setPrFilter }),
                  React.createElement(FilterBar, {
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
                  }),
                  React.createElement(SetupBanners, {
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
                  }),
                  React.createElement(KanbanBoard, {
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
                  })
                ),
      React.createElement(TaskDetailModal, {
        selectedTask,
        setSelectedTask,
        boards,
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
      }),
      React.createElement(NewTaskModal, {
        showNewTaskModal,
        setShowNewTaskModal,
        newTaskForm,
        setNewTaskForm,
        handleCreateTaskSubmit,
        isSubmittingTask,
        boards,
        selectedBoard
      }),
      React.createElement(NewBoardModal, {
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
      }),
      React.createElement(EditBoardModal, {
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
        precommitStatus,
        isSettingUpPrecommit,
        handleTriggerPrecommitSetup,
        openwikiStatus,
        isSettingUpOpenwiki,
        handleTriggerOpenwikiSetup,
        ghIssuesStatus,
        isSettingUpGhIssues,
        handleTriggerGhIssuesSetup,
        isSettingUpJira,
        handleTriggerJiraSetup,
        isTestingJira,
        handleTriggerJiraTest
      }),
      React.createElement(SettingsModal, {
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
      }),
      React.createElement(CronModal, {
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
      }),
      React.createElement(AddMemoryModal, {
        showAddMemoryModal,
        setShowAddMemoryModal,
        newMemoryForm,
        setNewMemoryForm,
        handleCreateMemorySubmit,
        submittingMemory,
        selectedBoard,
        boards
      }),
      React.createElement(Toast, { toast })
    )
  );
}
