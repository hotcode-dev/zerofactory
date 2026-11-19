export const API_BASE = "/api/plugins/zerofactory";

export const ZEROFACTORY_REPO = "hotcode-dev/zerofactory";
export const ZEROFACTORY_GITHUB_URL = `https://github.com/${ZEROFACTORY_REPO}`;
export const ZEROFACTORY_ISSUES_URL = `https://github.com/${ZEROFACTORY_REPO}/issues`;

export const COLUMNS = [
  {
    id: "human",
    title: "Human",
    icon: "👤",
    dotColor: "#f43f5e",
    role: "All Human Gates (0 Tokens)",
    desc: "Human decision gates and escalations sorted by urgency. Consumes zero LLM tokens until activated or merged.",
    stages: ["awaiting_merge", "spec_approval", "interview", "blocked", "triage"]
  },
  {
    id: "todo",
    title: "Todo",
    icon: "📋",
    dotColor: "#38bdf8",
    role: "AI Execution Queue",
    desc: "Queued AI tasks waiting for available concurrency slots across specialist agents.",
    stages: ["grill", "spec_draft", "spec_audit", "building", "review", "recovery"]
  },
  {
    id: "running",
    title: "Running",
    icon: "⚡",
    dotColor: "#fbbf24",
    role: "Active AI & Packaging",
    desc: "Active worker sessions inside isolated Git worktrees plus deterministic precommit and PR packaging.",
    stages: ["grill", "spec_draft", "spec_audit", "building", "packaging", "review", "recovery"]
  },
  {
    id: "done",
    title: "Done",
    icon: "✅",
    dotColor: "#a78bfa",
    role: "Terminal Completed",
    desc: "PR merged on GitHub or task closed. Worktree is pruned and repository memory is extracted.",
    stages: ["done"]
  },
];

export const NEXT_STATUS_MAP = {
  human: "todo",
  triage: "todo",
  todo: "running",
  running: "human",
  blocked: "done",
  done: "human"
};

export const STAGE_META = {
  triage:         { label: "Triage",             actor: "human",           icon: "📥", badgeClass: "bg-indigo-500/15 border-indigo-500/30 text-indigo-300", dotClass: "bg-indigo-400", urgency: 4 },
  grill:          { label: "Grill Me",           actor: "zf-orchestrator", icon: "🧭", badgeClass: "bg-purple-500/15 border-purple-500/30 text-purple-300", dotClass: "bg-purple-400 zfk-pulse-active", urgency: 99 },
  interview:      { label: "Interview",          actor: "human",           icon: "🎯", badgeClass: "bg-indigo-500/20 border-indigo-500/40 text-indigo-200", dotClass: "bg-indigo-400 zfk-pulse-active", urgency: 2 },
  spec_draft:     { label: "Spec Drafting",      actor: "zf-orchestrator", icon: "🐘", badgeClass: "bg-purple-500/15 border-purple-500/30 text-purple-300", dotClass: "bg-purple-400 zfk-pulse-active", urgency: 99 },
  spec_audit:     { label: "Spec Audit",         actor: "zf-goldfish",     icon: "🐠", badgeClass: "bg-amber-500/15 border-amber-500/30 text-amber-300",   dotClass: "bg-amber-400 zfk-pulse-active", urgency: 99 },
  spec_approval:  { label: "Spec Approval",      actor: "human",           icon: "📋", badgeClass: "bg-purple-500/20 border-purple-500/40 text-purple-200", dotClass: "bg-purple-400 zfk-pulse-active", urgency: 1 },
  building:       { label: "Building",           actor: "zf-builder",      icon: "🔨", badgeClass: "bg-emerald-500/15 border-emerald-500/30 text-emerald-300", dotClass: "bg-emerald-400 zfk-pulse-active", urgency: 99 },
  packaging:      { label: "Precommit & PR",     actor: "dispatcher",      icon: "📦", badgeClass: "bg-sky-500/15 border-sky-500/30 text-sky-300",         dotClass: "bg-sky-400 zfk-pulse-active", urgency: 99 },
  review:         { label: "PR Review",          actor: "zf-reviewer",     icon: "🔍", badgeClass: "bg-cyan-500/15 border-cyan-500/30 text-cyan-300",      dotClass: "bg-cyan-400 zfk-pulse-active", urgency: 99 },
  recovery:       { label: "AI Recovery",        actor: "zf-orchestrator", icon: "🩺", badgeClass: "bg-amber-500/20 border-amber-500/40 text-amber-200",   dotClass: "bg-amber-400 zfk-pulse-active", urgency: 99 },
  awaiting_merge: { label: "Waiting for Merge",  actor: "human",           icon: "🟢", badgeClass: "bg-teal-500/15 border-teal-500/30 text-teal-300",      dotClass: "bg-teal-400 zfk-pulse-active", urgency: 0 },
  blocked:        { label: "Blocked",            actor: "human",           icon: "🛑", badgeClass: "bg-rose-500/15 border-rose-500/30 text-rose-300",      dotClass: "bg-rose-400 zfk-pulse-active", urgency: 3 },
  done:           { label: "Done",               actor: "human",           icon: "✅", badgeClass: "bg-violet-500/15 border-violet-500/30 text-violet-300", dotClass: "bg-violet-400", urgency: 99 }
};

export const AGENT_META = {
  "zf-orchestrator": {
    label: "Orchestrator",
    role: "Orchestrator",
    icon: "🧭",
    runningLabel: "Orchestrating",
    badgeClass: "bg-indigo-500/15 text-indigo-300 border-indigo-500/30",
    runningClass: "bg-indigo-500/10 border-indigo-500/25 text-indigo-300",
    dotClass: "bg-indigo-400"
  },
  "zf-goldfish": {
    label: "Goldfish",
    role: "Spec Auditor",
    icon: "🐟",
    runningLabel: "Auditing Spec",
    badgeClass: "bg-amber-500/15 text-amber-300 border-amber-500/30",
    runningClass: "bg-amber-500/10 border-amber-500/25 text-amber-300",
    dotClass: "bg-amber-400"
  },
  "zf-builder": {
    label: "Builder",
    role: "Builder",
    icon: "🔨",
    runningLabel: "Implementing",
    badgeClass: "bg-emerald-500/15 text-emerald-300 border-emerald-500/30",
    runningClass: "bg-emerald-500/10 border-emerald-500/25 text-emerald-300",
    dotClass: "bg-emerald-400"
  },
  "zf-reviewer": {
    label: "Reviewer",
    role: "Reviewer",
    icon: "🔍",
    runningLabel: "Reviewing PR",
    badgeClass: "bg-cyan-500/15 text-cyan-300 border-cyan-500/30",
    runningClass: "bg-cyan-500/10 border-cyan-500/25 text-cyan-300",
    dotClass: "bg-cyan-400"
  },
  "human": {
    label: "Human",
    role: "Human",
    icon: "👤",
    runningLabel: "Human Review",
    badgeClass: "bg-violet-500/15 text-violet-300 border-violet-500/30 font-semibold",
    runningClass: "bg-violet-500/10 border-violet-500/25 text-violet-300",
    dotClass: "bg-violet-400"
  },
  "dispatcher": {
    label: "dispatcher",
    role: "Dispatcher Engine",
    icon: "⚙️",
    runningLabel: "Dispatching",
    badgeClass: "bg-sky-500/15 text-sky-300 border-sky-500/30",
    runningClass: "bg-sky-500/10 border-sky-500/25 text-sky-300",
    dotClass: "bg-sky-400"
  },
  "user": {
    label: "user",
    role: "User",
    icon: "👤",
    runningLabel: "User",
    badgeClass: "bg-sky-500/15 text-sky-300 border-sky-500/30",
    runningClass: "bg-sky-500/10 border-sky-500/25 text-sky-300",
    dotClass: "bg-sky-400"
  }
};

export const COLUMN_DEFAULT_PREVIEW = {
  human:   { stage: "triage",   label: "📥 Triage",    actor: "human" },
  triage:  { stage: "triage",   label: "📥 Triage",    actor: "human" },
  todo:    { stage: "building", label: "🔨 Building",  actor: "zf-builder" },
  running: { stage: "building", label: "🔨 Building",  actor: "zf-builder" },
  blocked: { stage: "blocked",  label: "🛑 Blocked",   actor: "human" },
  done:    { stage: "done",     label: "✅ Done",      actor: "human" }
};
