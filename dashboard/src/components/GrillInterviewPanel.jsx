import React, { useState } from "react";
import { parseActiveGrillQuestion } from "../utils/grillParser.js";
import { MarkdownView } from "./MarkdownView.jsx";
import { API_BASE } from "../constants.js";
import { fetchJSON } from "../sdk.js";

export function GrillInterviewPanel({
  task,
  loadTaskDetails,
  loadTasksAndStats,
  showToast = () => {}
}) {
  if (!task) return null;

  const interview = parseActiveGrillQuestion(task.comments || [], task);
  const isTriage = task.status === "triage";

  const [customNotes, setCustomNotes] = useState("");
  const [submittingKey, setSubmittingKey] = useState(null); // which option key is currently submitting
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [isDispatchingTriage, setIsDispatchingTriage] = useState(false);

  // Trigger Grill-with-Docs triage dispatch
  const handleStartTriage = async () => {
    setIsDispatchingTriage(true);
    try {
      await fetchJSON(`${API_BASE}/tasks/${task.id}/triage`, {
        method: "POST"
      });
      showToast("🧭 Grill-with-Docs triage dispatched to zf-orchestrator", "success");
      await loadTaskDetails(task.id);
      loadTasksAndStats();
    } catch (err) {
      showToast(`Failed to dispatch triage: ${err.message}`, "error");
    } finally {
      setIsDispatchingTriage(false);
    }
  };

  // Submit human interview reply for a direct option button
  const handleOptionSubmit = async (opt) => {
    setIsSubmitting(true);
    setSubmittingKey(opt.key);
    try {
      await fetchJSON(`${API_BASE}/tasks/${task.id}/interview-reply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          selection: opt.label,
          notes: "",
          advance: true
        })
      });
      showToast(`Selected ${opt.key}! zf-orchestrator resuming triage...`, "success");
      await loadTaskDetails(task.id);
      loadTasksAndStats();
    } catch (err) {
      showToast(`Failed to submit response: ${err.message}`, "error");
    } finally {
      setIsSubmitting(false);
      setSubmittingKey(null);
    }
  };

  // Submit custom notes / other answer
  const handleCustomSubmit = async (e) => {
    if (e) e.preventDefault();
    if (!customNotes.trim()) {
      showToast("Please enter your custom answer before submitting", "warning");
      return;
    }

    setIsSubmitting(true);
    setSubmittingKey("custom");
    try {
      await fetchJSON(`${API_BASE}/tasks/${task.id}/interview-reply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          selection: `Custom / Other: ${customNotes.trim()}`,
          notes: customNotes.trim(),
          advance: true
        })
      });
      showToast("Custom answer submitted! zf-orchestrator resuming triage...", "success");
      setCustomNotes("");
      await loadTaskDetails(task.id);
      loadTasksAndStats();
    } catch (err) {
      showToast(`Failed to submit custom answer: ${err.message}`, "error");
    } finally {
      setIsSubmitting(false);
      setSubmittingKey(null);
    }
  };

  // If there's an active or prior interview question
  if (interview) {
    return React.createElement(
      "div",
      {
        className:
          "rounded-xl border p-4 space-y-4 shadow-sm transition-all " +
          (interview.hasReplied
            ? "bg-slate-950/60 border-slate-800"
            : "bg-indigo-950/30 border-indigo-500/40 shadow-indigo-950/20")
      },
      // Header row
      React.createElement(
        "div",
        { className: "flex items-center justify-between gap-2 flex-wrap" },
        React.createElement(
          "div",
          { className: "flex items-center gap-2" },
          React.createElement("span", { className: "text-base" }, "🧭"),
          React.createElement(
            "span",
            { className: "font-semibold text-xs text-indigo-200 tracking-wide uppercase" },
            "Grill-with-Docs • Requirements & Design Interview"
          )
        ),
        React.createElement(
          "span",
          {
            className:
              "inline-flex items-center gap-1.5 text-[0.6875rem] font-semibold px-2.5 py-0.5 rounded-full border " +
              (interview.hasReplied
                ? "bg-emerald-500/15 border-emerald-500/30 text-emerald-300"
                : "bg-amber-500/20 border-amber-500/40 text-amber-300 animate-pulse")
          },
          React.createElement("span", {
            className:
              "w-2 h-2 rounded-full " +
              (interview.hasReplied ? "bg-emerald-400" : "bg-amber-400")
          }),
          interview.hasReplied ? "Decision Recorded" : "Awaiting Human Input"
        )
      ),

      // Question Box with Markdown rendering
      React.createElement(
        "div",
        {
          className:
            "bg-slate-900/90 border border-slate-800 rounded-lg p-3.5 space-y-2 text-xs text-slate-200"
        },
        React.createElement(
          "div",
          { className: "font-semibold text-indigo-300 flex items-center gap-1.5" },
          React.createElement("span", null, "🎯"),
          React.createElement("span", null, "Design Decision / Clarification Question:")
        ),
        React.createElement(
          "div",
          { className: "pl-5" },
          React.createElement(MarkdownView, { content: interview.questionText })
        ),
        interview.contextText &&
          React.createElement(
            "div",
            { className: "mt-2 pt-2 border-t border-slate-800 text-[0.6875rem] text-slate-400 space-y-1" },
            React.createElement(
              "div",
              { className: "flex items-center gap-1.5 font-semibold text-slate-400" },
              React.createElement("span", null, "📚"),
              React.createElement("span", null, "Documentation Context:")
            ),
            React.createElement("div", { className: "pl-5 font-mono text-[0.625rem] text-slate-300" },
              React.createElement(MarkdownView, { content: interview.contextText })
            )
          )
      ),

      // When answered: show settled note with recorded answer
      interview.hasReplied &&
        React.createElement(
          "div",
          { className: "space-y-2.5" },
          React.createElement(
            "div",
            {
              className:
                "p-3 rounded-lg bg-emerald-950/30 border border-emerald-500/30 text-xs text-emerald-300 space-y-1.5"
            },
            React.createElement(
              "div",
              { className: "flex items-center justify-between gap-2" },
              React.createElement(
                "span",
                { className: "font-semibold flex items-center gap-1.5" },
                React.createElement("span", null, "✓"),
                React.createElement("span", null, "Decision recorded. zf-orchestrator is grounding decisions into repository substrate.")
              ),
              React.createElement(
                "button",
                {
                  type: "button",
                  onClick: handleStartTriage,
                  disabled: isDispatchingTriage,
                  className:
                    "shrink-0 px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-[0.6875rem] text-slate-200 border border-slate-700 cursor-pointer"
                },
                isDispatchingTriage ? "Running..." : "Re-run Triage ↻"
              )
            ),
            interview.lastReply &&
              React.createElement(
                "div",
                { className: "pt-1 text-[0.6875rem] text-slate-300 border-t border-emerald-500/20" },
                React.createElement(MarkdownView, { content: interview.lastReply })
              )
          )
        ),

      // When awaiting input: render interactive option buttons & custom other input
      !interview.hasReplied &&
        React.createElement(
          "div",
          { className: "space-y-3" },
          // Predefined Options
          interview.options && interview.options.length > 0 &&
            React.createElement(
              "div",
              { className: "space-y-2" },
              React.createElement(
                "div",
                { className: "flex items-center justify-between gap-2" },
                React.createElement(
                  "label",
                  { className: "block text-[0.6875rem] font-semibold uppercase tracking-wider text-slate-400" },
                  "Click an Option Button to Choose:"
                ),
                React.createElement(
                  "span",
                  { className: "text-[0.625rem] text-slate-500" },
                  "1-click selection • no typing required"
                )
              ),
              React.createElement(
                "div",
                { className: "grid grid-cols-1 gap-2.5" },
                interview.options.map((opt) => {
                  const isThisSubmitting = isSubmitting && submittingKey === opt.key;
                  return React.createElement(
                    "div",
                    {
                      key: opt.id,
                      className:
                        "p-3.5 rounded-lg border text-xs transition-all duration-150 space-y-2 " +
                        (opt.isRecommended
                          ? "bg-indigo-950/25 border-indigo-500/40 hover:border-indigo-400/80 shadow-xs"
                          : "bg-slate-900/60 border-slate-800 hover:border-slate-700 text-slate-300")
                    },
                    // Header of option card
                    React.createElement(
                      "div",
                      { className: "flex items-center justify-between gap-2 flex-wrap" },
                      React.createElement(
                        "div",
                        { className: "flex items-center gap-2" },
                        React.createElement(
                          "span",
                          {
                            className:
                              "px-2 py-0.5 rounded font-mono text-[0.6875rem] font-bold border " +
                              (opt.isRecommended
                                ? "bg-indigo-500/30 text-indigo-200 border-indigo-500/50"
                                : "bg-slate-800 text-slate-300 border-slate-700")
                          },
                          opt.key
                        ),
                        opt.isRecommended &&
                          React.createElement(
                            "span",
                            { className: "px-2 py-0.5 rounded-full text-[0.625rem] font-bold bg-emerald-500/15 text-emerald-300 border border-emerald-500/30 flex items-center gap-1" },
                            "⭐ Recommended"
                          )
                      ),
                      // Direct Click-to-Submit Button
                      React.createElement(
                        "button",
                        {
                          type: "button",
                          onClick: () => handleOptionSubmit(opt),
                          disabled: isSubmitting,
                          className:
                            "inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white transition-all cursor-pointer shadow-xs disabled:opacity-50 disabled:cursor-not-allowed " +
                            (opt.isRecommended
                              ? "bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 shadow-indigo-600/30"
                              : "bg-slate-800 hover:bg-slate-700 border border-slate-700 hover:border-slate-600 text-slate-200")
                        },
                        isThisSubmitting
                          ? "Submitting..."
                          : `Choose ${opt.key} ${opt.isRecommended ? "★" : ""} →`
                      )
                    ),
                    // Markdown rendered option details, pros, cons, and trade-offs
                    React.createElement(
                      "div",
                      { className: "pt-1 text-slate-300" },
                      React.createElement(MarkdownView, { content: opt.content })
                    )
                  );
                })
              )
            ),

          // Other / Custom Answer section
          React.createElement(
            "form",
            {
              onSubmit: handleCustomSubmit,
              className: "p-3.5 rounded-lg border border-slate-800 bg-slate-900/50 space-y-2.5 text-xs"
            },
            React.createElement(
              "div",
              { className: "flex items-center justify-between gap-2" },
              React.createElement(
                "div",
                { className: "font-semibold text-slate-300 flex items-center gap-1.5" },
                React.createElement("span", null, "✏️"),
                React.createElement("span", null, "Other Answer / Custom Specifications:")
              ),
              React.createElement(
                "span",
                { className: "text-[0.625rem] text-slate-500" },
                "Optional • for custom constraints or alternative ideas"
              )
            ),
            React.createElement("textarea", {
              rows: 2,
              value: customNotes,
              onChange: (e) => setCustomNotes(e.target.value),
              placeholder: "Type your custom decision, hybrid preference, or specific trade-offs here...",
              className:
                "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors zfk-scrollbar"
            }),
            React.createElement(
              "div",
              { className: "flex items-center justify-end gap-2" },
              React.createElement(
                "button",
                {
                  type: "submit",
                  disabled: isSubmitting || !customNotes.trim(),
                  className:
                    "px-3.5 py-1.5 rounded-lg text-xs font-semibold text-white bg-slate-800 hover:bg-slate-700 active:bg-slate-800 border border-slate-700 transition-colors cursor-pointer shadow-xs disabled:opacity-40 disabled:cursor-not-allowed flex items-center gap-1.5"
                },
                isSubmitting && submittingKey === "custom"
                  ? "Submitting..."
                  : "Submit Custom Answer →"
              )
            )
          )
        )
    );
  }

  // If in Triage and no interview has been requested yet: show Quick Triage Dispatch CTA
  if (isTriage) {
    return React.createElement(
      "div",
      {
        className:
          "rounded-xl border border-indigo-500/30 bg-indigo-950/20 p-3.5 flex items-center justify-between gap-3 flex-wrap"
      },
      React.createElement(
        "div",
        { className: "space-y-0.5 min-w-0" },
        React.createElement(
          "div",
          { className: "text-xs font-semibold text-indigo-300 flex items-center gap-1.5" },
          React.createElement("span", null, "🧭"),
          React.createElement("span", null, "Grill-with-Docs Triage Available")
        ),
        React.createElement(
          "div",
          { className: "text-[0.6875rem] text-slate-400 leading-snug" },
          "Dispatch zf-orchestrator to inspect repo docs, interview trade-offs, and formulate acceptance criteria for zf-builder."
        )
      ),
      React.createElement(
        "button",
        {
          type: "button",
          onClick: handleStartTriage,
          disabled: isDispatchingTriage,
          className:
            "shrink-0 inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 transition-colors shadow-xs shadow-indigo-600/30 cursor-pointer disabled:opacity-50"
        },
        React.createElement("span", null, "🧭"),
        React.createElement("span", null, isDispatchingTriage ? "Dispatching..." : "Triage with Grill-with-Docs")
      )
    );
  }

  return null;
}
