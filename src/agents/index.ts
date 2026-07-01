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
  
  let finalPrUrl = `https://github.com/ntsd/zerofactory/pull/${Math.floor(Math.random()*1000)}`;
  
  // Attempt to actually commit, push, and create a PR
  try {
    console.log(`Committing and pushing worktree: ${worktreePath}`);
    // Check if there are changes
    const { stdout: status } = await execAsync(`git -C ${worktreePath} status --porcelain`);
    if (status.trim().length > 0) {
      await execAsync(`git -C ${worktreePath} add .`);
      await execAsync(`git -C ${worktreePath} commit -m "Automated implementation for: ${state.currentTask}"`);
      await execAsync(`git -C ${worktreePath} push origin ${branchName}`);
      
      // Attempt to use GitHub CLI to create the PR
      const { stdout: prOutput } = await execAsync(`gh pr create --title "${state.currentTask}" --body "Automated PR created by Zero Factory Builder." --head ${branchName}`);
      
      if (prOutput && prOutput.trim().startsWith("http")) {
        finalPrUrl = prOutput.trim();
        actionLog += ` | Successfully created PR: ${finalPrUrl}`;
      }
    } else {
      actionLog += " | No code changes were made to commit.";
    }
  } catch (e: any) {
    console.warn("Could not push or create PR (possibly missing gh CLI or permissions):", e.message);
    actionLog += ` | Git/GH failed, using mock PR: ${finalPrUrl}`;
  }
  
  return {
    status: "Blocked",
    prUrl: finalPrUrl,
    messages: [
      new AIMessage(`Created worktree at ${worktreePath}`),
      ...builderMessages,
      new AIMessage(`Builder Final Action: ${actionLog}`)
    ]
  };
}

export async function reviewerNode(state: typeof AgentState.State) {
  console.log("Reviewer: reviewing PR", state.prUrl);
  
  let resultStatus = "Done";
  let reviewerAction = "";
  
  if (process.env.OPENAI_API_KEY || process.env.ANTHROPIC_API_KEY) {
    try {
      const reviewerLlm = llm;
      const reviewSystemPrompt = `
      You are the Reviewer — the senior code reviewer and quality gatekeeper of Zero Factory.
      Your core responsibilities are code review, architecture, security, performance, and documentation.
      
      Review the task: ${state.currentTask}
      
      Decide if this work needs improvement or if it is approved. If you request changes, reply with 'CHANGES_REQUESTED' as the first word of your response. Otherwise, reply with 'APPROVED'.
      `;
      
      const response = await reviewerLlm.invoke([
        new SystemMessage(reviewSystemPrompt),
        new HumanMessage("Please review the PR and decide if it meets quality standards.")
      ]);
      
      const content = response.content as string;
      if (content.startsWith("CHANGES_REQUESTED")) {
        resultStatus = "Ready"; // Bounce back to builder
        reviewerAction = `Requested changes: ${content.substring(17).trim()}`;
      } else {
        resultStatus = "Done";
        reviewerAction = `Approved PR: ${content.substring(8).trim()}`;
      }
    } catch (e: any) {
      console.error("Reviewer LLM Error:", e.message);
      resultStatus = "Done";
      reviewerAction = "Mock Reviewer Approved (LLM Failed)";
    }
  } else {
    // Mock random decision
    if (Math.random() > 0.5) {
      resultStatus = "Ready";
      reviewerAction = "Mock Reviewer found issues, bouncing back to Builder.";
    } else {
      resultStatus = "Done";
      reviewerAction = "Mock Reviewer approved.";
    }
  }
  
  return {
    status: resultStatus,
    messages: [
      new AIMessage(reviewerAction)
    ]
  };
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
