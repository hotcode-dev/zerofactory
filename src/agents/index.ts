import { StateGraph, START, END } from "@langchain/langgraph";
import { createReactAgent } from "@langchain/langgraph/prebuilt";
import { AgentState } from "../state.js";
import { SystemMessage, HumanMessage, AIMessage, ToolMessage } from "@langchain/core/messages";
import { ChatOpenAI } from "@langchain/openai";
import { tool } from "@langchain/core/tools";
import { z } from "zod";
import { exec } from "child_process";
import { promisify } from "util";
import { loadMcpTools } from "../tools/mcp.js";
import { DiskMemorySaver } from "../checkpointer.js";

const execAsync = promisify(exec);

// Initialize persistence (saves to disk so server restarts don't lose state)
export const checkpointer = new DiskMemorySaver("../.data/checkpoints.json");


// Initialize LLM (defaults to local vLLM if OPENAI_API_BASE is not set)
const llm = new ChatOpenAI({
  modelName: process.env.MODEL_NAME || "qwen36-fast",
  temperature: 0,
  configuration: {
    baseURL: process.env.OPENAI_API_BASE || "http://spark.ntsd.dev:8000/v1",
  },
  apiKey: process.env.OPENAI_API_KEY || "empty", // vLLM doesn't require a real API key by default
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
    // Default to using the LLM (vLLM) unless specifically mocked
    if (process.env.USE_MOCK !== 'true') {
      try {
        let enhancedGoal = state.goal;
        
        // Auto-fetch GitHub Issue context if a URL is provided
        if (state.goal.includes("github.com") && state.goal.includes("/issues/")) {
          try {
            console.log(`Fetching GitHub Issue context for: ${state.goal}`);
            const { stdout } = await execAsync(`gh issue view ${state.goal}`);
            enhancedGoal = `Original Goal: ${state.goal}\n\nGitHub Issue Context:\n${stdout}`;
          } catch (ghErr: any) {
            console.warn("Failed to fetch GitHub issue, proceeding with raw URL:", ghErr.message);
          }
        }
        
        let repoPath = state.repoPath;
        if (state.repoUrl && !repoPath) {
          const repoName = state.repoUrl.split("/").pop()?.replace(".git", "") || "repo";
          repoPath = `../.workspaces/${repoName}-${Date.now()}`;
          try {
            console.log(`Cloning ${state.repoUrl} into ${repoPath}...`);
            await execAsync(`mkdir -p ../.workspaces && git clone ${state.repoUrl} ${repoPath}`);
          } catch (e: any) {
            console.error("Failed to clone repo:", e.message);
          }
        }
        
        const TaskSchema = z.object({
          todoList: z.array(z.string()).describe("A list of decomposed subtasks to achieve the goal"),
        });
        
        const structuredLlm = llm.withStructuredOutput(TaskSchema);
        const result = await structuredLlm.invoke([
          new SystemMessage("You are the Orchestrator. Break down the user's goal into a sequential list of concrete subtasks."),
          new HumanMessage(`Goal: ${enhancedGoal}`)
        ]);
        
        return {
          status: "Todo",
          repoPath, // Return the local cloned path
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
  
  // Reuse worktree if it exists in state, otherwise create one
  const safeTaskName = state.currentTask?.replace(/[^a-zA-Z0-9]/g, "-").toLowerCase() || "default";
  const branchName = state.branchName || `task/${safeTaskName}-${Date.now()}`;
  const baseRepoPath = state.repoPath || ".."; 
  const worktreePath = state.worktreePath || `${baseRepoPath}/.worktrees/${branchName}`;
  
  // We need to run git worktree add FROM the baseRepoPath if it doesn't exist
  if (!state.worktreePath) {
    try {
      await execAsync(`git -C ${baseRepoPath} worktree add -b ${branchName} ${worktreePath.replace(baseRepoPath + '/', '')}`);
    } catch (e: any) {
      console.warn(`Failed to create worktree, using fallback: ${e.message}`);
    }
  }

  let actionLog = "";
  const builderMessages = [];
  
  if (process.env.USE_MOCK !== 'true') {
    try {
      const mcpTools = await loadMcpTools("npx", ["-y", "@modelcontextprotocol/server-filesystem", worktreePath]);
      const allTools = [...mcpTools];
      const builderAgent = createReactAgent({ llm, tools: allTools });
      
      let contextMessages: any[] = [
        new SystemMessage("You are the Builder. Use the provided tools to implement the task. When you are finished, return a standard text response explaining what you did."),
        ...state.messages.filter(m => m instanceof AIMessage || m instanceof HumanMessage),
        new HumanMessage(`Task: ${state.currentTask}. Please implement this in ${worktreePath}. If you are retrying after a test or review failure, read the history above to fix the issues.`)
      ];
      
      builderMessages.push(new AIMessage(`Started deterministic agent execution...`));
      
      // Use deterministic prebuilt LangGraph agent for tool execution instead of manual loop
      const agentState = await builderAgent.invoke({ messages: contextMessages });
      
      const finalMsg = agentState.messages[agentState.messages.length - 1];
      actionLog = `LLM completed successfully: ${finalMsg.content}`;
      builderMessages.push(new AIMessage(actionLog));
      
    } catch (e: any) {
      console.error("MCP LLM Error:", e.message);
      actionLog = `Builder execution failed: ${e.message}`;
    }
  } else {
    actionLog = "Mock builder execution.";
  }
  
  let finalPrUrl = state.prUrl || `https://github.com/ntsd/zerofactory/pull/${branchName.length * 42}`;
  
  // Attempt to actually commit, push, and create/update a PR
  try {
    console.log(`Committing and pushing worktree: ${worktreePath}`);
    // Check if there are changes
    const { stdout: status } = await execAsync(`git status --porcelain`, { cwd: worktreePath });
    if (status.trim().length > 0) {
      await execAsync(`git add .`, { cwd: worktreePath });
      await execAsync(`git commit -m "Automated implementation for: ${state.currentTask}"`, { cwd: worktreePath });
      await execAsync(`git push origin ${branchName}`, { cwd: worktreePath });
      
      // Attempt to use GitHub CLI to create the PR only if it doesn't exist
      if (!state.prUrl || state.prUrl.includes("mock")) {
        try {
          const { stdout: prOutput } = await execAsync(`gh pr create --title "${state.currentTask}" --body "Automated PR created by Zero Factory Builder." --head ${branchName}`, { cwd: worktreePath });
          if (prOutput && prOutput.trim().startsWith("http")) {
            finalPrUrl = prOutput.trim();
            actionLog += ` | Successfully created PR: ${finalPrUrl}`;
          }
        } catch (e: any) {
          console.warn("Could not create PR:", e.message);
          actionLog += ` | PR creation failed, using mock PR: ${finalPrUrl}`;
        }
      } else {
        actionLog += ` | Successfully updated existing PR: ${finalPrUrl}`;
      }
    } else {
      actionLog += " | No code changes were made to commit.";
    }
  } catch (e: any) {
    console.warn("Could not push or create PR (possibly missing gh CLI or permissions):", e.message);
    actionLog += ` | Git/GH failed, using mock PR: ${finalPrUrl}`;
  }
  
  return {
    status: "Testing", // move to Testing state
    prUrl: finalPrUrl,
    branchName,
    worktreePath,
    messages: [
      new AIMessage(`Created worktree at ${worktreePath}`),
      ...builderMessages,
      new AIMessage(`Builder Final Action: ${actionLog}`)
    ]
  };
}

export async function testerNode(state: typeof AgentState.State) {
  console.log("Tester: running tests for task", state.currentTask);
  
  if (process.env.NODE_ENV === 'test') {
    return {
      status: "Blocked",
      messages: [new AIMessage(`Tests passed (mocked for testing)`)]
    };
  }

  // Run tests inside the isolated worktree where the changes actually exist!
  const targetTestPath = state.worktreePath || state.repoPath || "..";
  
  try {
    const { stdout, stderr } = await execAsync(`bun test`, { cwd: targetTestPath });
    return {
      status: "Blocked", // Pass to reviewer
      messages: [new AIMessage(`Tests passed:\n${stdout}`)]
    };
  } catch (err: any) {
    // Tests failed! Bounce back to Builder
    return {
      status: "Ready", // Bounce to Builder
      messages: [new AIMessage(`Tests failed! Please fix the following errors:\n${err.message}\n${err.stdout}\n${err.stderr}`)]
    };
  }
}

export async function reviewerNode(state: typeof AgentState.State) {
  console.log("Reviewer: reviewing PR", state.prUrl);
  
  let resultStatus = "Done";
  let reviewerAction = "";
  
  if (process.env.USE_MOCK !== 'true') {
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
      
      let ghCommand = "";
      if (content.startsWith("CHANGES_REQUESTED")) {
        resultStatus = "Ready"; // Bounce back to builder
        const feedback = content.substring(17).trim();
        reviewerAction = `Requested changes: ${feedback}`;
        ghCommand = `gh pr review ${state.prUrl} --request-changes -b "Zero Factory AI Review:\n\n${feedback.replace(/"/g, '\\"')}"`;
      } else {
        resultStatus = "Done";
        const feedback = content.substring(8).trim();
        reviewerAction = `Approved PR: ${feedback}`;
        ghCommand = `gh pr review ${state.prUrl} --approve -b "Zero Factory AI Review:\n\nApproved! ${feedback.replace(/"/g, '\\"')}"`;
      }
      
      // Execute the GitHub Review if it's a real URL
      if (state.prUrl.startsWith("http") && !state.prUrl.includes("mock")) {
        try {
          const baseRepoPath = state.repoPath || "..";
          await execAsync(ghCommand, { cwd: baseRepoPath });
          reviewerAction += " (Pushed to GitHub)";
        } catch (ghErr: any) {
          console.warn("Could not post review to GitHub:", ghErr.message);
        }
      }
      
    } catch (e: any) {
      console.error("Reviewer LLM Error:", e.message);
      resultStatus = "Done";
      reviewerAction = "Mock Reviewer Approved (LLM Failed)";
    }
  } else {
    // Deterministic mock decision based on reviewCount to ensure predictable tests
    if (state.reviewCount < 1) {
      resultStatus = "Ready";
      reviewerAction = `Mock Reviewer found issues (Review ${state.reviewCount + 1}), bouncing back to Builder.`;
    } else {
      resultStatus = "Done";
      reviewerAction = "Mock Reviewer approved.";
    }
  }
  
  return {
    status: resultStatus,
    reviewCount: state.reviewCount + 1,
    messages: [
      new AIMessage(reviewerAction)
    ]
  };
}

// Build the graph
export const workflow = new StateGraph(AgentState)
  .addNode("orchestrator", orchestratorNode)
  .addNode("builder", builderNode)
  .addNode("tester", testerNode)
  .addNode("reviewer", reviewerNode)
  
  .addEdge(START, "orchestrator")
  .addConditionalEdges("orchestrator", (state) => {
    if (state.status === "Ready") return "builder";
    if (state.status === "Done") return END;
    return "orchestrator";
  })
  .addEdge("builder", "tester") // Handoff to tester
  .addConditionalEdges("tester", (state) => {
    if (state.status === "Ready") return "builder"; // Test failed, back to builder
    return "reviewer"; // Test passed, handoff to reviewer
  })
  .addConditionalEdges("reviewer", (state) => {
    if (state.status === "Ready") return "builder"; // Review failed, back to builder
    if (state.status === "Done") return "orchestrator"; // Review passed, back to orchestrator
    return END;
  });

// Compile with sqlite checkpointer for persistence
export const app = workflow.compile({ checkpointer });
