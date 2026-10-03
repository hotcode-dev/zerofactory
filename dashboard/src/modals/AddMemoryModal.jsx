import React from "react";
import { Modal } from "../components/Modal.jsx";

export function AddMemoryModal(props) {
  const {
    showAddMemoryModal,
    setShowAddMemoryModal,
    newMemoryForm,
    setNewMemoryForm,
    handleCreateMemorySubmit,
    submittingMemory,
    selectedBoard,
    boards
  } = props;

  if (!showAddMemoryModal) return null;

  return React.createElement(
    Modal,
    {
      isOpen: showAddMemoryModal,
      onClose: () => setShowAddMemoryModal(false),
      onSubmit: handleCreateMemorySubmit,
      title: "Record Repository Memory",
      subtitle: "Persist decisions, conventions, and gotchas for " + (selectedBoard === "all" ? "all boards" : (selectedBoard || "board")),
      icon: "🧠",
      footerClassName: "px-6 py-3.5 bg-slate-900/50 border-t border-slate-800 flex items-center justify-end gap-2.5 shrink-0",
      footer: React.createElement(
        React.Fragment,
        null,
        React.createElement(
          "button",
          {
            type: "button",
            className: "px-4 py-1.5 rounded-lg text-xs font-medium text-slate-400 hover:text-slate-200 hover:bg-slate-800 transition-colors cursor-pointer",
            onClick: () => setShowAddMemoryModal(false)
          },
          "Cancel"
        ),
        React.createElement(
          "button",
          {
            type: "submit",
            disabled: submittingMemory,
            className: "inline-flex items-center gap-1.5 px-4 py-1.5 rounded-lg text-xs font-medium text-white bg-indigo-600 hover:bg-indigo-500 transition-colors cursor-pointer shadow-xs shadow-indigo-600/30 disabled:opacity-50"
          },
          submittingMemory && React.createElement("span", { className: "zfk-spinning" }, "⏳"),
          "Save Memory"
        )
      )
    },
          (selectedBoard === "all" || !selectedBoard) && boards && boards.length > 0 &&
          React.createElement(
            "div",
            { className: "space-y-1.5" },
            React.createElement("label", { className: "block text-xs font-medium text-slate-300" }, "Target Board *"),
            React.createElement(
              "select",
              {
                className: "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer",
                value: newMemoryForm.board_slug || (boards[0] ? boards[0].slug : ""),
                onChange: (e) => setNewMemoryForm({ ...newMemoryForm, board_slug: e.target.value })
              },
              boards.map((b) => React.createElement("option", { key: b.slug, value: b.slug }, b.slug))
            )
          ),
          // Category
          React.createElement(
            "div",
            { className: "space-y-1.5" },
            React.createElement("label", { className: "block text-xs font-medium text-slate-300" }, "Category"),
            React.createElement(
              "select",
              {
                className: "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 focus:outline-none focus:ring-1 focus:ring-indigo-500 cursor-pointer",
                value: newMemoryForm.category,
                onChange: (e) => setNewMemoryForm({ ...newMemoryForm, category: e.target.value })
              },
              React.createElement("option", { value: "convention" }, "📐 Convention (Architecture / Style / Code Rules)"),
              React.createElement("option", { value: "gotcha" }, "⚠️ Gotcha (Pitfall / Bug to Avoid)"),
              React.createElement("option", { value: "decision" }, "💡 Decision (Key Architectural Decision)"),
              React.createElement("option", { value: "rejected_path" }, "🚫 Rejected Path (Alternative Tried & Discarded)"),
              React.createElement("option", { value: "general" }, "📝 General Knowledge")
            )
          ),
          // Content
          React.createElement(
            "div",
            { className: "space-y-1.5" },
            React.createElement("label", { className: "block text-xs font-medium text-slate-300" }, "Memory / Knowledge Content *"),
            React.createElement("textarea", {
              required: true,
              rows: 4,
              placeholder: "e.g. Always run 'python3 -m unittest test_plugin.py' before marking tasks done, as SQLite cascade triggers are verified there.",
              className: "w-full bg-slate-800 border border-slate-700 rounded-lg p-3 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 resize-none font-sans",
              value: newMemoryForm.content,
              onChange: (e) => setNewMemoryForm({ ...newMemoryForm, content: e.target.value })
            })
          ),
          // Tags
          React.createElement(
            "div",
            { className: "space-y-1.5" },
            React.createElement("label", { className: "block text-xs font-medium text-slate-300" }, "Tags (comma-separated)"),
            React.createElement("input", {
              type: "text",
              placeholder: "sqlite, tests, git, caching",
              className: "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500",
              value: newMemoryForm.tags,
              onChange: (e) => setNewMemoryForm({ ...newMemoryForm, tags: e.target.value })
            })
          ),
          // Author & Task ID
          React.createElement(
            "div",
            { className: "grid grid-cols-2 gap-3" },
            React.createElement(
              "div",
              { className: "space-y-1.5" },
              React.createElement("label", { className: "block text-xs font-medium text-slate-300" }, "Author"),
              React.createElement("input", {
                type: "text",
                placeholder: "user",
                className: "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500",
                value: newMemoryForm.author,
                onChange: (e) => setNewMemoryForm({ ...newMemoryForm, author: e.target.value })
              })
            ),
            React.createElement(
              "div",
              { className: "space-y-1.5" },
              React.createElement("label", { className: "block text-xs font-medium text-slate-300" }, "Related Task ID (Optional)"),
              React.createElement("input", {
                type: "text",
                placeholder: "zf-xxxxxxxx",
                className: "w-full bg-slate-800 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 focus:outline-none focus:ring-1 focus:ring-indigo-500 font-mono",
                value: newMemoryForm.task_id || "",
                onChange: (e) => setNewMemoryForm({ ...newMemoryForm, task_id: e.target.value })
              })
            )
          )
  );
}
