import { StateGraph, Annotation, messagesStateReducer } from "@langchain/langgraph";
import { BaseMessage } from "@langchain/core/messages";

// Define the state for the Zero Factory Kanban board
export const AgentState = Annotation.Root({
  // Built-in messages list reducer
  messages: Annotation<BaseMessage[]>({
    reducer: messagesStateReducer,
    default: () => [],
  }),
  
  // The original goal from the user
  goal: Annotation<string>({
    reducer: (x, y) => y ?? x,
  }),
  
  // Task state representing the Kanban column
  status: Annotation<"Triage" | "Todo" | "Ready" | "Running" | "Blocked" | "Done">({
    reducer: (x, y) => y ?? x,
    default: () => "Triage"
  }),
  
  // List of decomposed subtasks
  todoList: Annotation<string[]>({
    reducer: (x, y) => y ?? x,
    default: () => []
  }),
  
  // Currently active subtask being worked on
  currentTask: Annotation<string | null>({
    reducer: (x, y) => y !== undefined ? y : x,
    default: () => null
  }),
  
  // PR URL if waiting on Human-In-The-Loop review
  prUrl: Annotation<string | null>({
    reducer: (x, y) => y !== undefined ? y : x,
    default: () => null
  }),

  // Number of times the PR has bounced between Reviewer and Builder
  reviewCount: Annotation<number>({
    reducer: (x, y) => (y !== undefined ? y : x),
    default: () => 0
  }),

  // Target GitHub Repository URL
  repoUrl: Annotation<string | null>({
    reducer: (x, y) => y !== undefined ? y : x,
    default: () => null
  }),

  // Local path where the repository is cloned
  repoPath: Annotation<string | null>({
    reducer: (x, y) => y !== undefined ? y : x,
    default: () => null
  })
});
