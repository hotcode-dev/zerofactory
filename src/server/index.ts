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
      const repoUrl = body.repoUrl;
      
      if (!repoUrl) {
        return new Response("Missing repoUrl", { status: 400 });
      }

      // Generate a deterministic thread ID for this repository
      const threadId = "repo-" + Buffer.from(repoUrl).toString('base64url');
      
      console.log(`Starting/updating thread ${threadId} for repo: ${repoUrl} with goal: ${goal}`);
      
      let existingState = null;
      try {
        existingState = await app.getState({ configurable: { thread_id: threadId } });
      } catch (e) {
        // Ignored
      }
      
      let initialState;
      if (existingState && existingState.values && existingState.values.status) {
        // Append to existing repo thread
        const updatedGoal = existingState.values.goal ? `${existingState.values.goal} | ${goal}` : goal;
        initialState = {
          goal: updatedGoal,
          status: "Triage",
          messages: [new HumanMessage(`New Goal Added: ${goal}`)]
        };
      } else {
        // Create new thread
        initialState = {
          goal,
          repoUrl,
          status: "Triage",
          messages: [new HumanMessage(goal)]
        };
      }
      
      // We invoke the graph asynchronously
      const result = await app.invoke(initialState, { configurable: { thread_id: threadId } });

      return new Response(JSON.stringify({ threadId, result }), {
        headers: { "Content-Type": "application/json", "Access-Control-Allow-Origin": "*" },
      });
    }

    // API to get all threads
    if (url.pathname === "/api/threads" && req.method === "GET") {
      const { checkpointer } = await import("../agents/index.js");
      const threads = checkpointer.getAllThreads();
      const threadsData = [];
      
      for (const threadId of threads) {
        try {
          const state = await app.getState({ configurable: { thread_id: threadId } });
          if (state && state.values) {
            threadsData.push({
              threadId,
              goal: state.values.goal,
              repoUrl: state.values.repoUrl,
              status: state.values.status
            });
          }
        } catch (e) {
          // Ignore state fetch errors for individual threads
        }
      }
      
      // Sort newest first based on threadId (which is Date.now().toString() or UUID)
      // Actually UUIDs aren't chronological, but we changed it to crypto.randomUUID() earlier.
      return new Response(JSON.stringify(threadsData), {
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

    // Server-Sent Events (SSE) for real-time status updates
    if (url.pathname === "/api/stream" && req.method === "GET") {
      const threadId = url.searchParams.get("threadId");
      if (!threadId) {
        return new Response("Missing threadId", { status: 400 });
      }

      return new Response(
        new ReadableStream({
          async start(controller) {
            // Send initial connection message
            controller.enqueue(`data: ${JSON.stringify({ type: 'connected', threadId })}\n\n`);

            // Poll state every 2 seconds and stream it (in a real app, you'd use graph.stream)
            const interval = setInterval(async () => {
              try {
                const state = await app.getState({ configurable: { thread_id: threadId } });
                if (state && state.values) {
                  controller.enqueue(`data: ${JSON.stringify({ type: 'state', values: state.values })}\n\n`);
                }
              } catch (e) {
                // Ignore state fetch errors (thread might not exist yet)
              }
            }, 2000);

            // Cleanup on disconnect
            req.signal.addEventListener("abort", () => {
              clearInterval(interval);
              controller.close();
            });
          }
        }),
        {
          headers: {
            "Content-Type": "text/event-stream",
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "Access-Control-Allow-Origin": "*"
          },
        }
      );
    }

    // Serve Static Astro Dashboard
    if (!url.pathname.startsWith("/api")) {
      let filePath = `../dashboard/dist${url.pathname}`;
      if (url.pathname === "/") {
        filePath = "../dashboard/dist/index.html";
      }

      const file = Bun.file(filePath);
      if (await file.exists()) {
        return new Response(file);
      } else {
        // Fallback for SPA routing
        const indexFile = Bun.file("../dashboard/dist/index.html");
        if (await indexFile.exists()) {
          return new Response(indexFile);
        }
      }
    }

    return new Response("Not Found", { status: 404 });
  },
});

console.log(`Zero Factory API server running at http://localhost:${PORT}`);
