import { expect, test, describe, beforeAll, afterAll } from "bun:test";
import { Server } from "bun";

describe("Zero Factory Agents - E2E Mocked API Server", () => {
  let mockServer: Server;
  let orchestratorNode: any;
  let reviewerNode: any;

  beforeAll(async () => {
    // Unset USE_MOCK so it actually tries to use the LLM
    delete process.env.USE_MOCK;
    process.env.OPENAI_API_KEY = "mock-key";
    process.env.OPENAI_API_BASE = "http://127.0.0.1:18999/v1";

    // Start a real local HTTP server to catch LangChain/OpenAI requests
    mockServer = Bun.serve({
      port: 18999,
      async fetch(req) {
        console.log("Mock Server Received Request:", req.method, req.url);
        const url = new URL(req.url);
        if (url.pathname === "/v1/chat/completions") {
          const body = await req.json();
          console.log("Mock Server Body:", JSON.stringify(body).substring(0, 200));
          let responseBody: any = {
            id: "chatcmpl-mock",
            object: "chat.completion",
            created: Date.now(),
            model: body.model || "gpt-mock",
            choices: [{
              index: 0,
              message: {
                role: "assistant",
                content: "Mock response"
              },
              finish_reason: "stop"
            }],
            usage: { prompt_tokens: 10, completion_tokens: 10, total_tokens: 20 }
          };

          // Handle structured output (Orchestrator) using json_schema
          if (body.response_format && body.response_format.type === "json_schema") {
            responseBody.choices[0].message = {
              role: "assistant",
              content: JSON.stringify({ todoList: ["E2E Task 1", "E2E Task 2"] })
            };
          }
          // Handle standard text response (Reviewer)
          else if (body.messages && body.messages.some((m: any) => m.content?.includes("senior code reviewer"))) {
            responseBody.choices[0].message.content = "APPROVED Great work on this mocked test!";
          }

          return new Response(JSON.stringify(responseBody), {
            headers: { "Content-Type": "application/json" }
          });
        }
        return new Response("Not Found", { status: 404 });
      }
    });

    // Dynamically import the agents module AFTER setting the env vars
    // so that ChatOpenAI is initialized with the mock URL
    const agents = await import("./agents/index.js");
    orchestratorNode = agents.orchestratorNode;
    reviewerNode = agents.reviewerNode;
  });

  afterAll(() => {
    mockServer.stop();
    process.env.USE_MOCK = 'true';
  });

  test("Orchestrator Node uses LLM to break down tasks via API mock", async () => {
    const initialState = {
      goal: "Build a mocked e2e test",
      status: "Triage",
      todoList: [],
      currentTask: "",
      prUrl: "",
      reviewCount: 0,
      repoUrl: null,
      repoPath: null,
      messages: []
    };

    const result = await orchestratorNode(initialState);
    
    expect(result.status).toBe("Todo");
    expect(result.todoList).toEqual(["E2E Task 1", "E2E Task 2"]);
  }, 15000);

  test("Reviewer Node uses LLM to review code via API mock", async () => {
    const blockedState = {
      goal: "Test goal",
      status: "Blocked",
      todoList: [],
      currentTask: "Task 1",
      prUrl: "mock-url-prevent-real-github-call",
      reviewCount: 0,
      repoUrl: null,
      repoPath: null,
      messages: []
    };

    const result = await reviewerNode(blockedState);
    
    expect(result.status).toBe("Done");
    expect(result.messages.length).toBeGreaterThan(0);
    expect(result.messages[0].content).toContain("Approved PR");
  });
});
