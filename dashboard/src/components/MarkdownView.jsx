import React from "react";

/**
 * Lightweight, zero-dependency Markdown renderer for Zero Factory dashboard.
 * Parses headers, bold, italics, inline code, links, lists, and Pros/Cons callouts.
 */

// Helper to parse inline markdown (bold, italic, code, links)
function parseInline(text) {
  if (!text) return null;

  // Split by inline markdown tokens: `code`, **bold**, *italic*, [link](url)
  const tokenRegex = /(`[^`]+`|\*\*[^*]+\*\*|\*[^*]+\*|\[[^\]]+\]\([^)]+\))/g;
  const parts = text.split(tokenRegex);

  return parts.map((part, index) => {
    if (!part) return null;

    // Inline code: `code`
    if (part.startsWith("`") && part.endsWith("`") && part.length >= 2) {
      const code = part.slice(1, -1);
      return React.createElement(
        "code",
        {
          key: index,
          className:
            "px-1.5 py-0.5 mx-0.5 rounded font-mono text-[0.6875rem] bg-slate-800 text-indigo-200 border border-slate-700/60 font-medium"
        },
        code
      );
    }

    // Bold: **bold**
    if (part.startsWith("**") && part.endsWith("**") && part.length >= 4) {
      const boldText = part.slice(2, -2);
      return React.createElement(
        "strong",
        { key: index, className: "font-semibold text-white" },
        parseInline(boldText)
      );
    }

    // Italic: *italic*
    if (part.startsWith("*") && part.endsWith("*") && part.length >= 2) {
      const italicText = part.slice(1, -1);
      return React.createElement(
        "em",
        { key: index, className: "italic text-slate-200" },
        parseInline(italicText)
      );
    }

    // Link: [label](url)
    const linkMatch = part.match(/^\[([^\]]+)\]\(([^)]+)\)$/);
    if (linkMatch) {
      return React.createElement(
        "a",
        {
          key: index,
          href: linkMatch[2],
          target: "_blank",
          rel: "noopener noreferrer",
          className: "text-indigo-400 hover:text-indigo-300 underline underline-offset-2 transition-colors",
          onClick: (e) => e.stopPropagation()
        },
        linkMatch[1]
      );
    }

    return part;
  });
}

export function MarkdownView({ content = "", className = "" }) {
  if (!content) return null;

  const rawLines = content.split("\n");
  const elements = [];
  let currentList = null; // { type: 'ul' | 'ol', items: [] }

  const flushList = () => {
    if (currentList) {
      elements.push(
        React.createElement(
          currentList.type,
          {
            key: `list-${elements.length}`,
            className: "space-y-1 my-1.5 pl-4 list-outside text-slate-300 " + (currentList.type === "ul" ? "list-disc" : "list-decimal")
          },
          currentList.items.map((item, idx) => {
            // Check for special Pros / Cons highlighting
            const isPros = item.trim().startsWith("Pros:") || item.trim().startsWith("- Pros:");
            const isCons = item.trim().startsWith("Cons:") || item.trim().startsWith("- Cons:");

            if (isPros) {
              return React.createElement(
                "li",
                { key: idx, className: "leading-relaxed text-slate-200" },
                React.createElement(
                  "span",
                  { className: "inline-flex items-center gap-1 font-semibold text-emerald-400 bg-emerald-950/40 border border-emerald-500/30 px-1.5 py-0.5 rounded text-[0.6875rem] mr-1.5" },
                  "✓ Pros:"
                ),
                parseInline(item.replace(/^[-*]?\s*Pros:\s*/i, ""))
              );
            }

            if (isCons) {
              return React.createElement(
                "li",
                { key: idx, className: "leading-relaxed text-slate-200" },
                React.createElement(
                  "span",
                  { className: "inline-flex items-center gap-1 font-semibold text-rose-300 bg-rose-950/40 border border-rose-500/30 px-1.5 py-0.5 rounded text-[0.6875rem] mr-1.5" },
                  "✗ Cons:"
                ),
                parseInline(item.replace(/^[-*]?\s*Cons:\s*/i, ""))
              );
            }

            return React.createElement(
              "li",
              { key: idx, className: "leading-relaxed text-slate-300" },
              parseInline(item)
            );
          })
        )
      );
      currentList = null;
    }
  };

  for (let i = 0; i < rawLines.length; i++) {
    const line = rawLines[i];
    const trimmed = line.trim();

    if (!trimmed) {
      flushList();
      continue;
    }

    // Headers: ### Header
    if (trimmed.startsWith("### ")) {
      flushList();
      elements.push(
        React.createElement(
          "h4",
          { key: `h3-${i}`, className: "text-xs font-bold text-indigo-300 mt-2.5 mb-1 flex items-center gap-1.5" },
          parseInline(trimmed.replace(/^###\s+/, ""))
        )
      );
      continue;
    }

    if (trimmed.startsWith("## ")) {
      flushList();
      elements.push(
        React.createElement(
          "h3",
          { key: `h2-${i}`, className: "text-sm font-bold text-slate-100 mt-3 mb-1" },
          parseInline(trimmed.replace(/^##\s+/, ""))
        )
      );
      continue;
    }

    if (trimmed.startsWith("# ")) {
      flushList();
      elements.push(
        React.createElement(
          "h2",
          { key: `h1-${i}`, className: "text-base font-bold text-white mt-3.5 mb-1.5" },
          parseInline(trimmed.replace(/^#\s+/, ""))
        )
      );
      continue;
    }

    // Bullet List Item: - or *
    const bulletMatch = trimmed.match(/^[-*]\s+(.*)$/);
    if (bulletMatch) {
      if (!currentList || currentList.type !== "ul") {
        flushList();
        currentList = { type: "ul", items: [] };
      }
      currentList.items.push(bulletMatch[1]);
      continue;
    }

    // Numbered List Item: 1. or 2.
    const numMatch = trimmed.match(/^\d+\.\s+(.*)$/);
    if (numMatch) {
      if (!currentList || currentList.type !== "ol") {
        flushList();
        currentList = { type: "ol", items: [] };
      }
      currentList.items.push(numMatch[1]);
      continue;
    }

    // Regular paragraph
    flushList();
    elements.push(
      React.createElement(
        "p",
        { key: `p-${i}`, className: "my-1 leading-relaxed text-slate-300" },
        parseInline(trimmed)
      )
    );
  }

  flushList();

  return React.createElement("div", { className: `text-xs leading-relaxed space-y-1 ${className}` }, elements);
}
