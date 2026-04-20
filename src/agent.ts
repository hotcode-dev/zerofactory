import { spawn } from "node:child_process";
import { Annotation, END, START, StateGraph } from "@langchain/langgraph";

import { BASE_SYSTEM_PROMPT } from "./principles.js";

type AgentRole = "manager" | "researcher" | "developer" | "tester" | "designer";

type SpecialistOutput = {
  role: AgentRole;
  content: string;
};

type RuntimeRole = AgentRole | "synthesis" | "executor";

const GraphState = Annotation.Root({
  objective: Annotation<string>,
  assumptions: Annotation<string[]>({
    reducer: (left, right) => [...left, ...right],
    default: () => [],
  }),
  managerPlan: Annotation<string>,
  specialistOutputs: Annotation<SpecialistOutput[]>({
    reducer: (left, right) => [...left, ...right],
    default: () => [],
  }),
  finalOutput: Annotation<string>,
  needsHumanReview: Annotation<boolean>,
});

export type ZeroFactoryInput = {
  objective: string;
  assumptions?: string[];
  needsHumanReview?: boolean;
};

export type ZeroFactoryResult = {
  plan: string;
  specialists: SpecialistOutput[];
  result: string;
};

const LOG_PROGRESS = process.env.ZEROFACTORY_LOG_PROGRESS !== "0";
const REQUESTED_TIMEOUT_MS = Number(process.env.ZEROFACTORY_PI_TIMEOUT_MS ?? 60000);
const MAX_TIMEOUT_MS = 60000;
const DEFAULT_TIMEOUT_MS =
  Number.isFinite(REQUESTED_TIMEOUT_MS) && REQUESTED_TIMEOUT_MS > 0
    ? Math.min(REQUESTED_TIMEOUT_MS, MAX_TIMEOUT_MS)
    : MAX_TIMEOUT_MS;
const DEFAULT_MAX_BUFFER_BYTES = 1024 * 1024;
const DEFAULT_PI_PROVIDER = process.env.ZEROFACTORY_PI_PROVIDER ?? "github-copilot";
const DEFAULT_PI_MODEL = process.env.ZEROFACTORY_PI_MODEL ?? "gpt-5.3-codex";
const DEFAULT_PI_THINKING = process.env.ZEROFACTORY_PI_THINKING ?? "low";

async function runPiCommand(args: string[], env: NodeJS.ProcessEnv): Promise<{ stdout: string; stderr: string }> {
  return new Promise((resolvePromise, rejectPromise) => {
    const child = spawn("pi", args, {
      env,
      stdio: ["ignore", "pipe", "pipe"],
    });

    let stdout = "";
    let stderr = "";
    let timedOut = false;

    const timeoutId = setTimeout(() => {
      timedOut = true;
      child.kill("SIGTERM");
    }, DEFAULT_TIMEOUT_MS);

    child.stdout.on("data", (chunk: Buffer | string) => {
      stdout += String(chunk);
      if (stdout.length > DEFAULT_MAX_BUFFER_BYTES) {
        child.kill("SIGTERM");
      }
    });

    child.stderr.on("data", (chunk: Buffer | string) => {
      stderr += String(chunk);
      if (stderr.length > DEFAULT_MAX_BUFFER_BYTES) {
        child.kill("SIGTERM");
      }
    });

    child.on("error", (error) => {
      clearTimeout(timeoutId);
      rejectPromise(error);
    });

    child.on("close", (code, signal) => {
      clearTimeout(timeoutId);

      if (code === 0) {
        resolvePromise({ stdout, stderr });
        return;
      }

      const timeoutText = timedOut
        ? `timed out after ${DEFAULT_TIMEOUT_MS}ms`
        : `exited with code ${code ?? "null"}${signal ? ` (signal: ${signal})` : ""}`;
      rejectPromise(new Error(`pi ${timeoutText}${stderr ? ` | stderr: ${stderr.trim()}` : ""}${stdout ? ` | stdout: ${stdout.trim()}` : ""}`));
    });
  });
}

function logProgress(message: string) {
  if (LOG_PROGRESS) {
    console.log(`[zerofactory] ${message}`);
  }
}

async function invokePi(
  role: RuntimeRole,
  systemPrompt: string,
  userPrompt: string,
): Promise<string> {
  const args = [
    "--print",
    "--mode",
    "text",
    "--no-session",
    "--provider",
    DEFAULT_PI_PROVIDER,
    "--model",
    DEFAULT_PI_MODEL,
    "--thinking",
    DEFAULT_PI_THINKING,
  ];

  args.push(`${systemPrompt}\n\n${userPrompt}`);

  try {
    logProgress(`[${role}] Running pi request...`);
    const { stdout, stderr } = await runPiCommand(args, process.env);

    const output = stdout.trim();
    if (!output) {
      const errorSuffix = stderr ? `: ${stderr}` : "";
      throw new Error(`pi returned empty output${errorSuffix}`);
    }

    return output;
  } catch (error) {
    const message = error instanceof Error ? error.message : String(error);
    throw new Error(`pi invocation failed: ${message}`);
  }
}

async function runRole(role: AgentRole, objective: string, plan: string) {
  const response = await invokePi(
    role,
    `${BASE_SYSTEM_PROMPT}\n\nYou are the ${role} agent.`,
    `Objective:\n${objective}\n\nManager Plan:\n${plan}\n\nReturn only the most critical recommendations for your role in <= 120 words.`,
  );

  return {
    role,
    content: response.trim(),
  } satisfies SpecialistOutput;
}

export function createZeroFactoryGraph() {
  const managerNode = async (state: typeof GraphState.State) => {
    logProgress("Manager agent started");
    const response = await invokePi(
      "manager",
      `${BASE_SYSTEM_PROMPT}\n\nYou are the manager agent.`,
      `Create a compact execution plan for this objective in 4 bullet points max.\n\nObjective:\n${state.objective}\n\nAssumptions:\n${state.assumptions.join("; ") || "None"}`,
    );

    logProgress("Manager agent finished");
    return { managerPlan: response.trim() };
  };

  const specialistNode = async (state: typeof GraphState.State) => {
    logProgress("Specialist agents started");
    const roles: AgentRole[] = [
      "researcher",
      "developer",
      "tester",
      "designer",
    ];
    const outputs: SpecialistOutput[] = [];
    for (const role of roles) {
      outputs.push(await runRole(role, state.objective, state.managerPlan));
    }
    logProgress("Specialist agents finished");
    return { specialistOutputs: outputs };
  };

  const synthNode = async (state: typeof GraphState.State) => {
    logProgress("Synthesis agent started");
    const compiledFindings = state.specialistOutputs
      .map((output) => `- ${output.role}: ${output.content}`)
      .join("\n");

    const response = await invokePi(
      "synthesis",
      `${BASE_SYSTEM_PROMPT}\n\nYou are the synthesis agent.`,
      `Merge the manager plan and specialist outputs into a final answer.\n` +
        `Structure:\n1) Short plan\n2) Implementation details\n3) Risks and checks\n\n` +
        `Objective:\n${state.objective}\n\nPlan:\n${state.managerPlan}\n\nSpecialists:\n${compiledFindings}`,
    );

    logProgress("Synthesis agent finished");
    return { finalOutput: response.trim() };
  };

  const executeNode = async (state: typeof GraphState.State) => {
    logProgress("Execution agent started");
    const compiledFindings = state.specialistOutputs
      .map((output) => `- ${output.role}: ${output.content}`)
      .join("\n");

    const response = await invokePi(
      "executor",
      `${BASE_SYSTEM_PROMPT}\n\nYou are the execution agent.`,
      `Implement the objective directly in the current workspace by creating/updating files and running the minimum validation commands.\n` +
        `Do the work now; do not stop at planning.\n\n` +
        `Objective:\n${state.objective}\n\nPlan:\n${state.managerPlan}\n\nSpecialists:\n${compiledFindings}\n\n` +
        `After execution, return:\n1) Files changed\n2) Commands run and outcomes\n3) Remaining risks or TODOs`,
    );

    logProgress("Execution agent finished");
    return { finalOutput: response.trim() };
  };

  const reviewGate = (state: typeof GraphState.State) => {
    if (state.needsHumanReview) {
      return "await_review";
    }
    return "execute";
  };

  const graph = new StateGraph(GraphState)
    .addNode("manager", managerNode)
    .addNode("specialists", specialistNode)
    .addNode("synthesis", synthNode)
    .addNode("execute", executeNode)
    .addNode("await_review", async (state: typeof GraphState.State) => state)
    .addEdge(START, "manager")
    .addEdge("manager", "specialists")
    .addEdge("specialists", "synthesis")
    .addConditionalEdges("synthesis", reviewGate, {
      await_review: "await_review",
      execute: "execute",
    })
    .addEdge("execute", END)
    .addEdge("await_review", END);

  return graph.compile();
}

export async function runZeroFactory(
  input: ZeroFactoryInput,
): Promise<ZeroFactoryResult> {
  logProgress("runZeroFactory invoked");
  const app = createZeroFactoryGraph();

  const state = await app.invoke({
    objective: input.objective,
    assumptions: input.assumptions ?? [],
    managerPlan: "",
    specialistOutputs: [],
    finalOutput: "",
    needsHumanReview: input.needsHumanReview ?? true,
  });

  logProgress("runZeroFactory completed");

  return {
    plan: state.managerPlan,
    specialists: state.specialistOutputs,
    result: state.finalOutput,
  };
}
