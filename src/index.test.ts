import { expect, test, describe, mock } from "bun:test";
import { AgentState } from "./state.js";
import { orchestratorNode, reviewerNode } from "./agents/index.js";
import { HumanMessage } from "@langchain/core/messages";

describe("Zero Factory Agents", () => {
  test("Orchestrator Node - Triage -> Todo", async () => {
    // Mock the state
    const initialState = {
      goal: "Test goal",
      status: "Triage",
      todoList: [],
      currentTask: "",
      prUrl: "",
      reviewCount: 0,
      messages: []
    };

    // If no API key is present, it uses the mock logic
    const result = await orchestratorNode(initialState);
    
    expect(result.status).toBe("Todo");
    expect(result.todoList).toBeDefined();
    expect(result.todoList.length).toBeGreaterThan(0);
  });

  test("Orchestrator Node - Todo -> Ready", async () => {
    const todoState = {
      goal: "Test goal",
      status: "Todo",
      todoList: ["Task 1", "Task 2"],
      currentTask: "",
      prUrl: "",
      reviewCount: 0,
      messages: []
    };

    const result = await orchestratorNode(todoState);
    
    expect(result.status).toBe("Ready");
    expect(result.currentTask).toBe("Task 1");
    expect(result.todoList).toEqual(["Task 2"]);
  });

  test("Reviewer Node - Mock Fallback", async () => {
    const blockedState = {
      goal: "Test goal",
      status: "Blocked",
      todoList: [],
      currentTask: "Task 1",
      prUrl: "http://github.com/mock/1",
      reviewCount: 0,
      messages: []
    };

    const result = await reviewerNode(blockedState);
    
    // The mock logic randomly returns 'Ready' or 'Done', but we can just check it returns a valid status
    expect(["Ready", "Done"]).toContain(result.status);
    expect(result.messages.length).toBeGreaterThan(0);
  });
});
