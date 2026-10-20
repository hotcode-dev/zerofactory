import React, { useState, useRef, useEffect } from "react";

export function BoardSelector(props) {
  const {
    boards = [],
    selectedBoard = "all",
    onSelectBoard,
    onOpenNewBoard,
    onOpenEditBoard,
    liveSessions = []
  } = props;

  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");
  const dropdownRef = useRef(null);
  const searchInputRef = useRef(null);

  // Close when clicking outside or pressing Escape
  useEffect(() => {
    function handleClickOutside(event) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target)) {
        setIsOpen(false);
      }
    }
    function handleKeyDown(event) {
      if (event.key === "Escape") {
        setIsOpen(false);
      }
    }
    if (isOpen) {
      document.addEventListener("mousedown", handleClickOutside);
      document.addEventListener("keydown", handleKeyDown);
      setTimeout(() => {
        if (searchInputRef.current) searchInputRef.current.focus();
      }, 50);
    }
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
      document.removeEventListener("keydown", handleKeyDown);
    };
  }, [isOpen]);

  if (boards.length === 0) {
    return React.createElement(
      "button",
      {
        type: "button",
        onClick: onOpenNewBoard,
        className:
          "inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-semibold text-amber-300 bg-amber-950/60 hover:bg-amber-900/60 border border-amber-800/60 hover:border-amber-700 transition-all cursor-pointer",
        title: "No boards configured. Click to create a board."
      },
      React.createElement("span", { className: "text-amber-400" }, "⚠"),
      "No Boards (Click to + Create)"
    );
  }

  const isAll = selectedBoard === "all" || !selectedBoard;
  const currentBoard = boards.find((b) => b.slug === selectedBoard);
  const totalTasksAllBoards = boards.reduce((acc, b) => acc + (b.task_count || 0), 0);

  // Count active live workers per board from liveSessions & board metadata
  const activeWorkersByBoard = {};
  if (Array.isArray(liveSessions)) {
    liveSessions.forEach((s) => {
      if (s.is_alive || s.status === "ongoing" || s.status === "running" || s.is_active) {
        const b = s.board_slug || "unknown";
        activeWorkersByBoard[b] = (activeWorkersByBoard[b] || 0) + 1;
      }
    });
  }

  const getRunningCount = (b) => {
    const fromSessions = activeWorkersByBoard[b.slug] || 0;
    return Math.max(b.running_count || 0, fromSessions);
  };

  const totalRunningAllBoards = boards.reduce((acc, b) => acc + getRunningCount(b), 0);
  const currentRunningWorkers = isAll
    ? totalRunningAllBoards
    : currentBoard
      ? getRunningCount(currentBoard)
      : activeWorkersByBoard[selectedBoard] || 0;

  const filteredBoards = boards.filter((b) => {
    if (!search.trim()) return true;
    const q = search.toLowerCase();
    const slugMatch = b.slug.toLowerCase().includes(q);
    const descMatch = (b.description || "").toLowerCase().includes(q);
    const repoMatch = (b.repositories || []).some(
      (r) =>
        (r.repo_alias || "").toLowerCase().includes(q) ||
        (r.git_url || "").toLowerCase().includes(q)
    );
    const branchMatch = (b.target_branch || "").toLowerCase().includes(q);
    return slugMatch || descMatch || repoMatch || branchMatch;
  });

  const handleSelect = (slug) => {
    onSelectBoard(slug);
    setIsOpen(false);
    setSearch("");
  };

  return React.createElement(
    "div",
    { className: "relative inline-block text-left z-30", ref: dropdownRef },
    // Main Selector Trigger Button
    React.createElement(
      "button",
      {
        type: "button",
        onClick: () => setIsOpen((prev) => !prev),
        className:
          "group inline-flex items-center gap-2 px-3 py-1.5 rounded-lg text-xs font-medium bg-slate-900/90 hover:bg-slate-800/90 text-slate-200 border border-slate-700/80 hover:border-slate-600 transition-all shadow-sm focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer"
      },
      // Left Icon / Indicator
      isAll
        ? React.createElement(
            "span",
            {
              className:
                "w-5 h-5 rounded-md bg-indigo-950/80 border border-indigo-700/60 text-indigo-400 flex items-center justify-center text-[10px] font-bold"
            },
            "🌐"
          )
        : React.createElement(
            "span",
            {
              className:
                "w-5 h-5 rounded-md bg-purple-950/80 border border-purple-700/60 text-purple-300 flex items-center justify-center text-[10px] font-bold"
            },
            currentBoard?.slug?.slice(0, 2).toUpperCase() || "BD"
          ),

      // Label & Task Count
      React.createElement(
        "div",
        { className: "flex items-center gap-1.5 text-left" },
        React.createElement(
          "span",
          { className: "font-semibold text-slate-100 max-w-[140px] truncate" },
          isAll ? "All Boards" : currentBoard?.slug || selectedBoard
        ),
        React.createElement(
          "span",
          {
            className:
              "text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 border border-slate-700/70 text-slate-400"
          },
          isAll ? totalTasksAllBoards : currentBoard?.task_count || 0
        )
      ),

      // Live Active Worker Pulse if running
      currentRunningWorkers > 0 &&
        React.createElement(
          "span",
          {
            className:
              "inline-flex items-center gap-1 text-[10px] font-medium text-amber-300 bg-amber-950/60 border border-amber-800/60 px-1.5 py-0.5 rounded-full",
            title: `${currentRunningWorkers} active worker(s) running`
          },
          React.createElement("span", {
            className: "w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse"
          }),
          currentRunningWorkers
        ),

      // Auto-Merge Badge on trigger if enabled for this board
      !isAll &&
        currentBoard?.automerge &&
        React.createElement(
          "span",
          {
            className:
              "text-[10px] font-bold px-1.5 py-0.5 rounded bg-emerald-950/80 border border-emerald-800/70 text-emerald-300",
            title: "Auto-Merge is active on this board"
          },
          "⚡ Auto-Merge"
        ),

      // Chevron
      React.createElement(
        "svg",
        {
          className:
            "w-3.5 h-3.5 text-slate-400 group-hover:text-slate-200 transition-transform duration-150 " +
            (isOpen ? "rotate-180" : ""),
          fill: "none",
          viewBox: "0 0 24 24",
          stroke: "currentColor",
          strokeWidth: 2
        },
        React.createElement("path", {
          strokeLinecap: "round",
          strokeLinejoin: "round",
          d: "M19 9l-7 7-7-7"
        })
      )
    ),

    // Dropdown Popover Menu
    isOpen &&
      React.createElement(
        "div",
        {
          className:
            "absolute left-0 mt-1.5 w-76 sm:w-84 rounded-xl bg-slate-900/95 backdrop-blur-xl border border-slate-700/80 shadow-2xl shadow-black/90 z-50 overflow-hidden flex flex-col max-h-[460px]"
        },
        // Search Input Header (shown if more than 2 boards)
        boards.length > 2 &&
          React.createElement(
            "div",
            { className: "p-2.5 border-b border-slate-800 bg-slate-950/60" },
            React.createElement(
              "div",
              { className: "relative flex items-center" },
              React.createElement(
                "span",
                { className: "absolute left-2.5 text-slate-500 text-xs" },
                "🔍"
              ),
              React.createElement("input", {
                ref: searchInputRef,
                type: "text",
                value: search,
                onChange: (e) => setSearch(e.target.value),
                placeholder: "Search boards or repos...",
                className:
                  "w-full bg-slate-900 border border-slate-800 rounded-lg pl-8 pr-7 py-1.5 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors"
              }),
              search &&
                React.createElement(
                  "button",
                  {
                    type: "button",
                    onClick: () => setSearch(""),
                    className:
                      "absolute right-2 text-slate-400 hover:text-slate-200 text-xs px-1 cursor-pointer"
                  },
                  "✕"
                )
            )
          ),

        // Scrollable List of Boards
        React.createElement(
          "div",
          { className: "overflow-y-auto flex-1 p-1.5 space-y-1 zfk-scrollbar" },
          // Option: "All Boards"
          (!search || "all boards".includes(search.toLowerCase())) &&
            React.createElement(
              "button",
              {
                type: "button",
                onClick: () => handleSelect("all"),
                className:
                  "w-full flex items-center justify-between px-2.5 py-2 rounded-lg text-xs text-left transition-colors cursor-pointer " +
                  (isAll
                    ? "bg-indigo-600/15 border border-indigo-500/30 text-indigo-200 font-semibold"
                    : "hover:bg-slate-800/60 text-slate-300 border border-transparent")
              },
              React.createElement(
                "div",
                { className: "flex items-center gap-2.5 min-w-0" },
                React.createElement(
                  "span",
                  {
                    className:
                      "w-6 h-6 rounded-lg bg-indigo-950/80 border border-indigo-700/60 text-indigo-400 flex items-center justify-center text-xs shrink-0"
                  },
                  "🌐"
                ),
                React.createElement(
                  "div",
                  { className: "min-w-0" },
                  React.createElement(
                    "div",
                    { className: "font-medium text-slate-200 truncate" },
                    "All Boards"
                  ),
                  React.createElement(
                    "div",
                    { className: "text-[10px] text-slate-400" },
                    `${boards.length} active project board${boards.length === 1 ? "" : "s"}`
                  )
                )
              ),
              React.createElement(
                "div",
                { className: "flex items-center gap-1.5 shrink-0 ml-2" },
                totalRunningAllBoards > 0 &&
                  React.createElement(
                    "span",
                    {
                      className:
                        "w-2 h-2 rounded-full bg-amber-400 animate-pulse",
                      title: `${totalRunningAllBoards} worker(s) active across all boards`
                    }
                  ),
                React.createElement(
                  "span",
                  {
                    className:
                      "text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300"
                  },
                  totalTasksAllBoards
                )
              )
            ),

          // Divider
          boards.length > 0 &&
            React.createElement("div", {
              className: "my-1 border-t border-slate-800/80"
            }),

          // Specific Board Items
          filteredBoards.length === 0
            ? React.createElement(
                "div",
                { className: "py-6 text-center text-xs text-slate-400" },
                "No boards match your search"
              )
            : filteredBoards.map((b) => {
                const isSelected = selectedBoard === b.slug;
                const repoCount = b.repositories?.length || (b.git_url ? 1 : 0);
                const runningWorkers = getRunningCount(b);

                return React.createElement(
                  "div",
                  {
                    key: b.slug,
                    className:
                      "group/item w-full flex items-center justify-between px-2.5 py-2 rounded-lg text-xs text-left transition-all " +
                      (isSelected
                        ? "bg-indigo-600/15 border border-indigo-500/30"
                        : "hover:bg-slate-800/60 border border-transparent")
                  },
                  // Clickable area for selecting the board
                  React.createElement(
                    "button",
                    {
                      type: "button",
                      onClick: () => handleSelect(b.slug),
                      className: "flex items-center gap-2.5 flex-1 min-w-0 text-left cursor-pointer"
                    },
                    React.createElement(
                      "span",
                      {
                        className:
                          "w-6 h-6 rounded-lg bg-slate-800 border border-slate-700/80 text-slate-300 flex items-center justify-center text-[10px] font-bold font-mono shrink-0 " +
                          (isSelected ? "border-indigo-500/50 text-indigo-300 bg-indigo-950/40" : "")
                      },
                      b.slug.slice(0, 2).toUpperCase()
                    ),
                    React.createElement(
                      "div",
                      { className: "min-w-0 flex-1" },
                      React.createElement(
                        "div",
                        { className: "flex items-center gap-1.5" },
                        React.createElement(
                          "span",
                          {
                            className:
                              "font-semibold truncate " +
                              (isSelected ? "text-indigo-200" : "text-slate-200 group-hover/item:text-white")
                          },
                          b.slug
                        ),
                        b.automerge &&
                          React.createElement(
                            "span",
                            {
                              className:
                                "text-[9px] px-1 py-0.5 rounded font-bold bg-emerald-950/80 text-emerald-300 border border-emerald-800/60",
                              title: "Auto-Merge enabled"
                            },
                            "⚡"
                          ),
                        runningWorkers > 0 &&
                          React.createElement(
                            "span",
                            {
                              className:
                                "w-1.5 h-1.5 rounded-full bg-amber-400 animate-pulse",
                              title: `${runningWorkers} worker(s) active`
                            }
                          )
                      ),
                      React.createElement(
                        "div",
                        { className: "text-[10px] text-slate-400 flex items-center gap-2 mt-0.5" },
                        React.createElement(
                          "span",
                          null,
                          `${repoCount} repo${repoCount === 1 ? "" : "s"}`
                        ),
                        b.target_branch &&
                          React.createElement(
                            "span",
                            { className: "font-mono text-slate-400" },
                            `⎇ ${b.target_branch}`
                          )
                      )
                    )
                  ),

                  // Right side: Task count badge & Quick Settings Gear
                  React.createElement(
                    "div",
                    { className: "flex items-center gap-1.5 shrink-0 ml-2" },
                    React.createElement(
                      "span",
                      {
                        className:
                          "text-[10px] font-mono px-1.5 py-0.5 rounded bg-slate-800 text-slate-300"
                      },
                      b.task_count || 0
                    ),
                    onOpenEditBoard &&
                      React.createElement(
                        "button",
                        {
                          type: "button",
                          onClick: (e) => {
                            e.stopPropagation();
                            onSelectBoard(b.slug);
                            setIsOpen(false);
                            if (typeof onOpenEditBoard === "function") {
                              onOpenEditBoard(b.slug);
                            }
                          },
                          className:
                            "p-1 rounded hover:bg-slate-700/80 text-slate-400 hover:text-slate-200 transition-colors opacity-70 group-hover/item:opacity-100 cursor-pointer",
                          title: `Edit settings for ${b.slug}`
                        },
                        "⚙️"
                      )
                  )
                );
              })
        ),

        // Dropdown Footer with "+ New Board" Action
        React.createElement(
          "div",
          {
            className:
              "p-2 border-t border-slate-800/80 bg-slate-950/60 flex items-center justify-between"
          },
          React.createElement(
            "button",
            {
              type: "button",
              onClick: () => {
                setIsOpen(false);
                if (onOpenNewBoard) onOpenNewBoard();
              },
              className:
                "w-full flex items-center justify-center gap-1.5 py-1.5 px-3 rounded-lg text-xs font-semibold text-slate-300 hover:text-white bg-slate-800/70 hover:bg-slate-700/80 border border-slate-700/60 transition-colors cursor-pointer"
            },
            React.createElement("span", { className: "text-indigo-400 font-bold" }, "+"),
            "Create New Board"
          )
        )
      )
  );
}
