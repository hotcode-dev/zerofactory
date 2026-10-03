import React, { useEffect } from "react";

/**
 * Standard reusable Modal dialog for Zero Factory Dashboard.
 * Enforces uniform responsive sizing, backdrop, mobile padding, and Escape-key listener.
 */
export function Modal(props) {
  const {
    isOpen = true,
    onClose,
    title,
    subtitle,
    icon,
    iconBg,
    header,
    headerExtra,
    subHeader,
    footer,
    maxWidth = "max-w-4xl",
    children,
    className = "",
    bodyClassName = "p-6 space-y-4 overflow-y-auto zfk-scrollbar flex-1",
    footerClassName = "flex items-center justify-end gap-2.5 px-6 py-3.5 border-t border-slate-800 bg-slate-900/50 shrink-0",
    onSubmit
  } = props;

  if (!isOpen) return null;

  useEffect(() => {
    const handleKeyDown = (e) => {
      if (e.key === "Escape" && onClose) {
        onClose();
      }
    };
    window.addEventListener("keydown", handleKeyDown);
    return () => window.removeEventListener("keydown", handleKeyDown);
  }, [onClose]);

  return React.createElement(
    "div",
    {
      className: "fixed inset-0 z-50 flex items-center justify-center bg-black/75 backdrop-blur-xs p-3 sm:p-4 overflow-y-auto",
      onClick: () => onClose && onClose()
    },
    React.createElement(
      onSubmit ? "form" : "div",
      {
        onSubmit: onSubmit,
        className: `bg-slate-900 border border-slate-800 rounded-2xl shadow-2xl w-full ${maxWidth} max-h-[92vh] flex flex-col overflow-hidden text-slate-100 ${className}`,
        onClick: (e) => e.stopPropagation()
      },
      header !== undefined
        ? header
        : (title || onClose
            ? React.createElement(
                "div",
                { className: "flex items-center justify-between px-6 py-4 border-b border-slate-800 shrink-0 bg-slate-900/60" },
                React.createElement(
                  "div",
                  { className: "flex items-center gap-3 min-w-0 pr-2" },
                  icon && React.createElement(
                    "div",
                    {
                      className: `w-9 h-9 rounded-xl ${iconBg || "bg-gradient-to-br from-indigo-500 to-indigo-700"} flex items-center justify-center font-bold text-white shadow-md text-base shrink-0`
                    },
                    icon
                  ),
                  React.createElement(
                    "div",
                    { className: "min-w-0" },
                    typeof title === "string"
                      ? React.createElement("h2", { className: "text-base font-bold text-white m-0 truncate" }, title)
                      : title,
                    subtitle && React.createElement("p", { className: "text-xs text-slate-400 font-medium m-0 truncate" }, subtitle)
                  )
                ),
                React.createElement(
                  "div",
                  { className: "flex items-center gap-2 shrink-0" },
                  headerExtra,
                  onClose && React.createElement(
                    "button",
                    {
                      type: "button",
                      className: "text-slate-400 hover:text-white p-1 rounded-lg hover:bg-slate-800 transition-colors text-lg leading-none cursor-pointer w-8 h-8 flex items-center justify-center",
                      onClick: onClose,
                      title: "Close"
                    },
                    "✕"
                  )
                )
              )
            : null),
      subHeader,
      React.createElement(
        "div",
        { className: bodyClassName },
        children
      ),
      footer && React.createElement(
        "div",
        { className: footerClassName },
        footer
      )
    )
  );
}
