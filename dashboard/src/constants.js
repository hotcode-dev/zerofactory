export const API_BASE = "/api/plugins/zerofactory";

export const COLUMNS = [
  { id: "triage", title: "Triage", icon: "📥", dotColor: "#818cf8", desc: "Raw backlog & epics" },
  { id: "todo", title: "Todo", icon: "📋", dotColor: "#38bdf8", desc: "Prioritized queue ready for pickup" },
  { id: "running", title: "Running", icon: "⚡", dotColor: "#fbbf24", desc: "Autonomous AI agents" },
  { id: "blocked", title: "Blocked", icon: "🛑", dotColor: "#f43f5e", desc: "Human action required" },
  { id: "done", title: "Done", icon: "✅", dotColor: "#a78bfa", desc: "Completed & merged" },
];

export const NEXT_STATUS_MAP = {
  triage: "todo",
  todo: "running",
  ready: "running",
  running: "blocked",
  blocked: "done",
  done: "triage"
};
