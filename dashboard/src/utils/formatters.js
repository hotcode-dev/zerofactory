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
