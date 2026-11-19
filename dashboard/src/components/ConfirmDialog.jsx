import React, { useState, useEffect, useRef } from "react";
import { Modal } from "./Modal.jsx";

/**
 * Lightweight in-app confirmation / prompt dialog replacing native window.confirm() and prompt().
 */
export function ConfirmDialog({ dialog, onResolve }) {
  const [inputValue, setInputValue] = useState("");
  const inputRef = useRef(null);

  useEffect(() => {
    if (dialog) {
      setInputValue(dialog.defaultValue || "");
      if (dialog.mode === "prompt") {
        setTimeout(() => inputRef.current && inputRef.current.focus(), 30);
      }
    }
  }, [dialog]);

  if (!dialog) return null;

  const isPrompt = dialog.mode === "prompt";
  const isDanger = dialog.variant === "danger";

  const handleSubmit = (e) => {
    if (e && e.preventDefault) e.preventDefault();
    if (isPrompt) {
      if (!inputValue.trim()) return;
      onResolve(inputValue.trim());
    } else {
      onResolve(true);
    }
  };

  return React.createElement(
    Modal,
    {
      isOpen: Boolean(dialog),
      onClose: () => onResolve(isPrompt ? null : false),
      onSubmit: handleSubmit,
      title: dialog.title || (isPrompt ? "Provide Input" : "Confirm Action"),
      icon: dialog.icon || (isDanger ? "⚠️" : "💬"),
      iconBg: isDanger
        ? "bg-gradient-to-br from-rose-600 to-rose-800"
        : "bg-gradient-to-br from-indigo-500 to-indigo-700",
      maxWidth: "max-w-md",
      footer: React.createElement(
        React.Fragment,
        null,
        React.createElement(
          "button",
          {
            type: "button",
            onClick: () => onResolve(isPrompt ? null : false),
            className: "px-3.5 py-1.5 rounded-lg text-xs font-medium text-slate-300 hover:text-white bg-slate-800 hover:bg-slate-700 border border-slate-700 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 transition-colors cursor-pointer"
          },
          dialog.cancelLabel || "Cancel"
        ),
        React.createElement(
          "button",
          {
            type: "submit",
            disabled: isPrompt && !inputValue.trim(),
            className:
              "px-4 py-1.5 rounded-lg text-xs font-semibold text-white transition-colors cursor-pointer focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-indigo-500 disabled:opacity-50 disabled:cursor-not-allowed " +
              (isDanger
                ? "bg-rose-600 hover:bg-rose-500 shadow-xs shadow-rose-600/30"
                : "bg-indigo-600 hover:bg-indigo-500 shadow-xs shadow-indigo-600/30")
          },
          dialog.confirmLabel || (isDanger ? "Confirm" : "Submit")
        )
      )
    },
    dialog.message &&
      React.createElement(
        "p",
        { className: "text-xs text-slate-300 leading-relaxed whitespace-pre-line m-0" },
        dialog.message
      ),
    isPrompt &&
      React.createElement("textarea", {
        ref: inputRef,
        rows: 3,
        value: inputValue,
        onChange: (e) => setInputValue(e.target.value),
        placeholder: dialog.placeholder || "Enter details...",
        className: "w-full bg-slate-950 border border-slate-700 rounded-lg px-3 py-2 text-xs text-slate-100 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors resize-y"
      })
  );
}
