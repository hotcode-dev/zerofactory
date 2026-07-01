import { StateGraph, START, END, MemorySaver } from "@langchain/langgraph";
import { AgentState } from "../state.js";
import { SystemMessage, HumanMessage, AIMessage } from "@langchain/core/messages";
import { ChatOpenAI } from "@langchain/openai";
import { tool } from "@langchain/core/tools";
import { z } from "zod";
import { exec } from "child_process";
import { promisify } from "util";

const execAsync = promisify(exec);

// Initialize persistence (in-memory for Bun compatibility)
const checkpointer = new MemorySaver();


// Mock LLM or real LLM if key is present
const llm = new ChatOpenAI({
  modelName: "gpt-4o-mini",
  temperature: 0,
});

// A tool to create a git worktree
const createWorktreeTool = tool(
  async ({ branchName, path }) => {
    try {
      await execAsync(`git worktree add -b ${branchName} ${path}`);
      return `Created worktree at ${path} on branch ${branchName}`;
    } catch (e: any) {
      return `Error creating worktree: ${e.message}`;
    }
  },
  {
    name: "create_git_worktree",
    description: "Create an isolated git worktree for a task",
    schema: z.object({
      branchName: z.string(),
      path: z.string(),
    }),
  }
);

export async function orchestratorNode(state: typeof AgentState.State) {
  console.log("Orchestrator: analyzing current state...", state.status);
  
  if (state.status === "Triage") {
    // In a real implementation, we would call the LLM to decompose the goal
    // For now, we will simulate the LLM decomposing it into subtasks
    return {
      status: "Todo",
      todoList: ["Setup project structure", "Implement feature logic", "Write unit tests"],
      messages: [new AIMessage("I have decomposed the goal into tasks.")]
    };
  }

  if (state.status === "Todo") {
    if (state.todoList.length > 0) {
      const nextTask = state.todoList[0];
      return {
        status: "Ready",
        currentTask: nextTask,
        todoList: state.todoList.slice(1),
        messages: [new AIMessage(`Assigned task: ${nextTask}`)]
      };
    } else {
      return { status: "Done" };
    }
  }

  return {};
}

export async function builderNode(state: typeof AgentState.State) {
  console.log("Builder: working on task", state.currentTask);
  
  // Create worktree for task isolation
  const safeTaskName = state.currentTask?.replace(/[^a-zA-Z0-9]/g, "-").toLowerCase();
  const branchName = `task/${safeTaskName}-${Date.now()}`;
  const worktreePath = `../.worktrees/${branchName}`;
  
  await createWorktreeTool.invoke({ branchName, path: worktreePath });
  
  return {
    status: "Blocked",
    prUrl: `https://github.com/ntsd/zerofactory/pull/${Math.floor(Math.random()*1000)}`,
    messages: [
      new AIMessage(`Created worktree at ${worktreePath}`),
      new AIMessage(`Created PR for task: ${state.currentTask}`)
    ]
  };
}

export async function reviewerNode(state: typeof AgentState.State) {
  console.log("Reviewer: reviewing PR", state.prUrl);
  
  const reviews = state.reviewCount || 0;
  if (reviews < 1) {
    return {
      status: "Ready",
      reviewCount: reviews + 1,
      messages: [new AIMessage("Requested changes on PR.")]
    };
  } else {
    return {
      status: "Done",
      messages: [new AIMessage("PR approved and merged!")]
    };
  }
}

// Build the graph
export const workflow = new StateGraph(AgentState)
  .addNode("orchestrator", orchestratorNode)
  .addNode("builder", builderNode)
  .addNode("reviewer", reviewerNode)
  
  .addEdge(START, "orchestrator")
  .addConditionalEdges("orchestrator", (state) => {
    if (state.status === "Ready") return "builder";
    if (state.status === "Done") return END;
    return "orchestrator";
  })
  .addEdge("builder", "reviewer") // Handoff to reviewer (which simulates HITL by becoming Blocked)
  .addConditionalEdges("reviewer", (state) => {
    if (state.status === "Ready") return "builder"; // Go back to builder
    if (state.status === "Done") return "orchestrator"; // Back to orchestrator
    return END;
  });

// Compile with sqlite checkpointer for persistence
export const app = workflow.compile({ checkpointer });
