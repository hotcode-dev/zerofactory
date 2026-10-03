import { utils } from "../sdk.js";

export const timeAgo = utils.timeAgo || function (ts) {
  if (!ts) return "";
  const diff = Math.floor(Date.now() / 1000 - ts);
  if (diff < 60) return "just now";
  if (diff < 3600) return Math.floor(diff / 60) + "m ago";
  if (diff < 86400) return Math.floor(diff / 3600) + "h ago";
  return Math.floor(diff / 86400) + "d ago";
};

export const formatPrLabel = function (url) {
  if (!url) return "";
  const trimmed = String(url).trim();
  if (/^#?\d+$/.test(trimmed)) return "PR #" + trimmed.replace(/^#/, "");
  const m = trimmed.match(/\/(?:pull|merge_requests)\/(\d+)/i);
  if (m) return "PR #" + m[1];
  return "PR ↗";
};

export const computeGitSlug = function (gitUrl) {
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
  const repo = parts.length >= 1 ? parts[parts.length - 1].replace(/[^a-zA-Z0-9_\-.]/g, "") : "";
  const owner = parts.length >= 2 ? parts[parts.length - 2].replace(/[^a-zA-Z0-9_\-.]/g, "") : "";
  if (owner && repo) {
    return (owner + "-" + repo).toLowerCase().replace(/[^a-zA-Z0-9_\-]/g, "-").replace(/^-+|-+$/g, "");
  }
  if (repo) {
    return repo.toLowerCase().replace(/[^a-zA-Z0-9_\-]/g, "-").replace(/^-+|-+$/g, "");
  }
  return "";
};
