import { app } from "../agents/index.js";
import { HumanMessage } from "@langchain/core/messages";

const PORT = process.env.PORT || 3000;

Bun.serve({
  port: PORT,
  async fetch(req) {
    const url = new URL(req.url);

    // API to start a new goal
    if (url.pathname === "/api/start" && req.method === "POST") {
      const body = await req.json();
      const goal = body.goal || "Default goal";
      const threadId = crypto.randomUUID();
      
      console.log(`Starting new thread ${threadId} for goal: ${goal}`);
      
      const initialState = {
        goal,
        status: "Triage",
        messages: [new HumanMessage(goal)]
      };
      
      // We invoke the graph asynchronously. In a real scenario, this runs in the background
      // and we just return the threadId immediately.
      // But for the dashboard to see immediate triage, we will run the first step synchronously.
      // The graph is compiled with a checkpointer in agents/index.ts.
      const result = await app.invoke(initialState, { configurable: { thread_id: threadId } });

      return new Response(JSON.stringify({ threadId, result }), {
        headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
      });
    }

    // API to get thread status
    if (url.pathname === "/api/status" && req.method === "GET") {
      const threadId = url.searchParams.get("threadId");
      if (!threadId) {
        return new Response("Not found", { status: 404, headers: { "Access-Control-Allow-Origin": "*" } });
      }
      
      const state = await app.getState({ configurable: { thread_id: threadId } });
      
      return new Response(JSON.stringify(state.values), {
        headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
      });
    }

    // API to simulate Webhook / Resume
    if (url.pathname === "/api/resume" && req.method === "POST") {
        const body = await req.json();
        const threadId = body.threadId;
        const action = body.action || "approve";
        
        console.log(`Resuming thread ${threadId} with action ${action}`);
        
        // Update the state or send a message to resume
        const result = await app.invoke(null, { configurable: { thread_id: threadId } });
        
        return new Response(JSON.stringify({ status: "Resumed", threadId, result }), {
            headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
        });
    }

    // Handle Preflight OPTIONS
    if (req.method === "OPTIONS") {
        return new Response(null, {
            headers: {
                "Access-Control-Allow-Origin": "*",
                "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
                "Access-Control-Allow-Headers": "Content-Type"
            }
        });
    }

    return new Response("Zero Factory API Running", {
        headers: { "Access-Control-Allow-Origin": "*" }
    });
  },
});

console.log(`Zero Factory API server running at http://localhost:${PORT}`);
