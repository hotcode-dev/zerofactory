/**
 * Parser for Grill-with-Docs interview questions and human replies.
 */

export function parseActiveGrillQuestion(comments = [], task = {}) {
  if (!comments || comments.length === 0) {
    // Check if task metadata has an active interview state
    const meta = typeof task.metadata === "string" ? safeJsonParse(task.metadata) : (task.metadata || {});
    if (meta.active_interview && !meta.last_interview_reply) {
      return {
        questionText: meta.active_interview.question || "Technical Decision Required",
        options: meta.active_interview.options || [],
        contextText: meta.active_interview.context || "",
        hasReplied: false
      };
    }
    return null;
  }

  // Scan backwards from newest to oldest comment
  for (let i = comments.length - 1; i >= 0; i--) {
    const c = comments[i];
    const body = c.body || "";

    const isQuestion =
      body.includes("Grill-with-Docs: Decision Required") ||
      (body.includes("Grill-with-Docs") && (body.includes("Option A") || body.includes("Question:")));

    if (isQuestion) {
      // Check if subsequent comment is a human reply
      const subsequentComments = comments.slice(i + 1);
      const replyComment = subsequentComments.find(
        (sub) =>
          (sub.body || "").includes("[Grill-with-Docs Human Response]") ||
          (sub.body || "").includes("Grill-with-Docs Response") ||
          sub.author === "human" ||
          sub.author === "user"
      );
      const hasReplied = Boolean(replyComment);

      // Extract Question
      let questionText = "";
      const qMatch = body.match(/\*\*Question:\*\*\s*(.+?)(?=\n\s*[-*0-9]|\n\*\*|$)/s);
      if (qMatch) {
        questionText = qMatch[1].trim();
      } else {
        const lines = body.split("\n");
        const qLine = lines.find(
          (l) => l.toLowerCase().includes("question:") || l.startsWith("###")
        );
        questionText = qLine
          ? qLine.replace(/^###\s*|^\*\*Question:\*\*\s*/i, "").trim()
          : "Technical & Architectural Decision Required";
      }

      // Extract Options
      const options = [];
      const optionRegex =
        /(?:[-*]\s*(?:\[[\sXx]?\]\s*)?|\d+\.\s*)\*\*Option\s+([A-Z0-9]+):\*\*\s*([^\n]+)/gi;
      let optMatch;
      while ((optMatch = optionRegex.exec(body)) !== null) {
        options.push({
          id: optMatch[1].trim(),
          key: `Option ${optMatch[1].trim()}`,
          label: `Option ${optMatch[1].trim()}: ${optMatch[2].trim()}`,
          details: optMatch[2].trim()
        });
      }

      // Fallback extraction if bold formatting differs
      if (options.length === 0) {
        const fallbackRegex =
          /(?:[-*]\s*|\d+\.\s*)Option\s+([A-Z0-9]+)[:\s-]+([^\n]+)/gi;
        let fbMatch;
        while ((fbMatch = fallbackRegex.exec(body)) !== null) {
          options.push({
            id: fbMatch[1].trim(),
            key: `Option ${fbMatch[1].trim()}`,
            label: `Option ${fbMatch[1].trim()}: ${fbMatch[2].trim()}`,
            details: fbMatch[2].trim()
          });
        }
      }

      // Extract documentation context
      let contextText = "";
      const ctxMatch = body.match(
        /\*\*Documentation Context:\*\*\s*(.+?)(?=\n\n|$)/s
      );
      if (ctxMatch) {
        contextText = ctxMatch[1].trim();
      }

      return {
        commentId: c.id,
        author: c.author,
        createdAt: c.created_at,
        questionText,
        options,
        contextText,
        rawBody: body,
        hasReplied,
        lastReply: replyComment ? replyComment.body : null
      };
    }
  }

  return null;
}

function safeJsonParse(val) {
  try {
    return JSON.parse(val);
  } catch {
    return {};
  }
}
