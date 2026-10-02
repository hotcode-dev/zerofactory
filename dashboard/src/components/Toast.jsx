import React from "react";

export function Toast({ toast }) {
  if (!toast) return null;
  return React.createElement(
    "div",
    {
      style: { zIndex: 999999 },
      className: "fixed top-6 right-6 px-4 py-3 rounded-xl font-semibold text-sm shadow-2xl flex items-center gap-2.5 transition-all duration-200 border pointer-events-auto " +
        (toast.type === "error"
          ? "bg-rose-950/95 text-rose-200 border-rose-700 shadow-rose-950/80"
          : toast.type === "success"
            ? "bg-emerald-950/95 text-emerald-200 border-emerald-700 shadow-emerald-950/80"
            : "bg-indigo-950/95 text-indigo-200 border-indigo-700 shadow-indigo-950/80")
    },
    toast.message
  );
}
