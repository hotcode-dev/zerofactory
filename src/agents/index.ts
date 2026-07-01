import { StateGraph, START, END, MemorySaver } from "@langchain/langgraph";
import { AgentState } from "../state.js";
import { SystemMessage, HumanMessage, AIMessage, ToolMessage } from "@langchain/core/messages";
import { ChatOpenAI } from "@langchain/openai";
import { tool } from "@langchain/core/tools";
import { z } from "zod";
import { exec } from "child_process";
import { promisify } from "util";
import { loadMcpTools } from "../tools/mcp.js";

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
    // If we have an LLM configured (API key exists), use it to decompose tasks
    if (process.env.OPENAI_API_KEY || process.env.ANTHROPIC_API_KEY) {
      try {
        const TaskSchema = z.object({
          todoList: z.array(z.string()).describe("A list of decomposed subtasks to achieve the goal"),
        });
        
        const structuredLlm = llm.withStructuredOutput(TaskSchema);
        const result = await structuredLlm.invoke([
          new SystemMessage("You are the Orchestrator. Break down the user's goal into a sequential list of concrete subtasks."),
          new HumanMessage(`Goal: ${state.goal}`)
        ]);
        
        return {
          status: "Todo",
          todoList: result.todoList,
          messages: [new AIMessage(`I have decomposed the goal into ${result.todoList.length} tasks using the LLM.`)]
        };
      } catch (e: any) {
        console.error("LLM Error:", e.message);
        // Fallback if LLM fails
      }
    }
    
    // Mock fallback
    return {
      status: "Todo",
      todoList: ["Setup project structure", "Implement feature logic", "Write unit tests"],
      messages: [new AIMessage("I have decomposed the goal into tasks (Mock).")]
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
  const safeTaskName = state.currentTask?.replace(/[^a-zA-Z0-9]/g, "-").toLowerCase() || "default";
  const branchName = `task/${safeTaskName}-${Date.now()}`;
  const worktreePath = `../.worktrees/${branchName}`;
  
  await createWorktreeTool.invoke({ branchName, path: worktreePath });

  let actionLog = "";
  const builderMessages = [];
  
  if (process.env.OPENAI_API_KEY || process.env.ANTHROPIC_API_KEY) {
    try {
      const mcpTools = await loadMcpTools("npx", ["-y", "@modelcontextprotocol/server-filesystem", "/"]);
      const allTools = [createWorktreeTool, ...mcpTools];
      const builderLlm = llm.bindTools(allTools);
      
      let contextMessages: any[] = [
        new SystemMessage("You are the Builder. Use the provided tools to implement the task. When you are finished, return a standard text response explaining what you did."),
        new HumanMessage(`Task: ${state.currentTask}. Please implement this in ${worktreePath}.`)
      ];
      
      let response = await builderLlm.invoke(contextMessages);
      contextMessages.push(response);
      builderMessages.push(new AIMessage(`Started task execution...`));
      
      // ReAct Loop for Tool Execution
      let executionCount = 0;
      while (response.tool_calls && response.tool_calls.length > 0 && executionCount < 10) {
        executionCount++;
        actionLog = `Executing ${response.tool_calls.length} tool calls...`;
        console.log(actionLog);
        
        for (const toolCall of response.tool_calls) {
          const tool = allTools.find((t) => t.name === toolCall.name);
          if (tool) {
            try {
              const toolResult = await tool.invoke(toolCall.args);
              contextMessages.push(new ToolMessage({
                content: typeof toolResult === 'string' ? toolResult : JSON.stringify(toolResult),
                name: toolCall.name,
                tool_call_id: toolCall.id,
              }));
              builderMessages.push(new AIMessage(`Tool [${toolCall.name}] succeeded.`));
            } catch (err: any) {
              contextMessages.push(new ToolMessage({
                content: `Error executing tool: ${err.message}`,
                name: toolCall.name,
                tool_call_id: toolCall.id,
              }));
              builderMessages.push(new AIMessage(`Tool [${toolCall.name}] failed.`));
            }
          }
        }
        
        // Re-invoke the LLM with the tool results
        response = await builderLlm.invoke(contextMessages);
        contextMessages.push(response);
      }
      
      actionLog = `LLM completed after ${executionCount} tool execution rounds.`;
    } catch (e: any) {
      console.error("MCP LLM Error:", e.message);
      actionLog = "Mock builder execution (MCP failed to load or LLM error).";
    }
  } else {
    actionLog = "Mock builder execution.";
  }
  
  return {
    status: "Blocked",
    prUrl: `https://github.com/ntsd/zerofactory/pull/${Math.floor(Math.random()*1000)}`,
    messages: [
      new AIMessage(`Created worktree at ${worktreePath}`),
      ...builderMessages,
      new AIMessage(`Builder Final Action: ${actionLog}`),
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
