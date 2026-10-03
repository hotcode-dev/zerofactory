import React, { useState } from "react";
import { parseActiveGrillQuestion } from "../utils/grillParser.js";
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
  const metaStr = typeof task.metadata === "string" ? task.metadata : JSON.stringify(task.metadata || {});
  const descStr = typeof task.description === "string" ? task.description : "";
  const isAwaitingInput =
    (interview && !interview.hasReplied) ||
    (task.status === "blocked" && (descStr.includes("Grill-with-Docs") || metaStr.includes("Grill-with-Docs")));

  const [selectedOption, setSelectedOption] = useState("");
  const [customNotes, setCustomNotes] = useState("");
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

  // Submit human interview reply
  const handleSubmitReply = async (e) => {
    if (e) e.preventDefault();
    if (!selectedOption && !customNotes.trim()) {
      showToast("Please choose an option or enter notes before submitting", "warning");
      return;
    }

    setIsSubmitting(true);
    try {
      const finalSelection = selectedOption || customNotes.trim();
      await fetchJSON(`${API_BASE}/tasks/${task.id}/interview-reply`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          selection: finalSelection,
          notes: customNotes.trim(),
          advance: true
        })
      });
      showToast("Selection submitted! zf-orchestrator resuming triage...", "success");
      setSelectedOption("");
      setCustomNotes("");
      await loadTaskDetails(task.id);
      loadTasksAndStats();
    } catch (err) {
      showToast(`Failed to submit response: ${err.message}`, "error");
    } finally {
      setIsSubmitting(false);
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

      // Question Box
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
          { className: "text-xs text-slate-100 font-medium leading-relaxed pl-5 whitespace-pre-wrap" },
          interview.questionText
        ),
        interview.contextText &&
          React.createElement(
            "div",
            { className: "mt-2 pt-2 border-t border-slate-800 text-[0.6875rem] text-slate-400 flex items-center gap-1.5" },
            React.createElement("span", null, "📚"),
            React.createElement("span", { className: "font-mono" }, interview.contextText)
          )
      ),

      // When answered: show settled note
      interview.hasReplied &&
        React.createElement(
          "div",
          {
            className:
              "p-2.5 rounded-lg bg-emerald-950/30 border border-emerald-500/30 text-xs text-emerald-300 flex items-center justify-between gap-2"
          },
          React.createElement(
            "span",
            { className: "truncate" },
            "✓ Latest choice submitted. zf-orchestrator is grounding decisions into repository documentation."
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

      // When awaiting input: render interactive options & response form
      !interview.hasReplied &&
        React.createElement(
          "form",
          { onSubmit: handleSubmitReply, className: "space-y-3" },
          // Options choices
          interview.options && interview.options.length > 0 &&
            React.createElement(
              "div",
              { className: "space-y-2" },
              React.createElement(
                "label",
                { className: "block text-[0.6875rem] font-semibold uppercase tracking-wider text-slate-400" },
                "Select Recommended Option:"
              ),
              React.createElement(
                "div",
                { className: "grid grid-cols-1 gap-2" },
                interview.options.map((opt) => {
                  const isSelected = selectedOption === opt.label || selectedOption === opt.key;
                  return React.createElement(
                    "div",
                    {
                      key: opt.id,
                      onClick: () => setSelectedOption(opt.label),
                      className:
                        "flex items-start gap-3 p-3 rounded-lg border text-xs cursor-pointer transition-all duration-150 " +
                        (isSelected
                          ? "bg-indigo-600/20 border-indigo-400 text-white shadow-xs ring-1 ring-indigo-400/50"
                          : "bg-slate-900/60 border-slate-800 hover:border-slate-700 text-slate-300 hover:text-white")
                    },
                    React.createElement(
                      "div",
                      { className: "pt-0.5 shrink-0" },
                      React.createElement("div", {
                        className:
                          "w-4 h-4 rounded-full border flex items-center justify-center " +
                          (isSelected
                            ? "border-indigo-400 bg-indigo-500 text-white font-bold text-[10px]"
                            : "border-slate-600 bg-slate-800")
                      }, isSelected ? "✓" : "")
                    ),
                    React.createElement(
                      "div",
                      { className: "flex-1 space-y-0.5" },
                      React.createElement(
                        "div",
                        { className: "font-semibold text-slate-100 flex items-center gap-2" },
                        React.createElement(
                          "span",
                          { className: "px-1.5 py-0.2 rounded bg-indigo-500/20 text-indigo-300 font-mono text-[0.625rem] border border-indigo-500/30" },
                          opt.key
                        ),
                        React.createElement("span", null, opt.details)
                      )
                    )
                  );
                })
              )
            ),

          // Custom feedback / modifications
          React.createElement(
            "div",
            { className: "space-y-1.5" },
            React.createElement(
              "label",
              { className: "block text-[0.6875rem] font-semibold uppercase tracking-wider text-slate-400" },
              "Custom Notes, Modifications, or Alternative Choice (Optional):"
            ),
            React.createElement("textarea", {
              rows: 2,
              value: customNotes,
              onChange: (e) => setCustomNotes(e.target.value),
              placeholder: "e.g. Prefer Option A, but ensure backwards compatibility with legacy API endpoints...",
              className:
                "w-full bg-slate-950 border border-slate-800 rounded-lg px-3 py-2 text-xs text-slate-200 placeholder-slate-500 outline-none focus:border-indigo-500 focus:ring-1 focus:ring-indigo-500 transition-colors zfk-scrollbar"
            })
          ),

          // Submit button
          React.createElement(
            "div",
            { className: "flex items-center justify-between gap-2 pt-1" },
            React.createElement(
              "span",
              { className: "text-[0.6875rem] text-slate-400" },
              selectedOption ? "Selected: " + selectedOption.split(":")[0] : "Click an option above or type notes"
            ),
            React.createElement(
              "button",
              {
                type: "submit",
                disabled: isSubmitting || (!selectedOption && !customNotes.trim()),
                className:
                  "px-4 py-2 rounded-lg text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 active:bg-indigo-700 transition-colors cursor-pointer shadow-md shadow-indigo-600/30 disabled:opacity-50 disabled:cursor-not-allowed flex items-center gap-1.5"
              },
              isSubmitting ? "Submitting..." : "Submit Selection & Continue Triage →"
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
