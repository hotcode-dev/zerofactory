import "dotenv/config";

import { runZeroFactory } from "./agent.js";

function shouldRequireHumanReview(): boolean {
  const value = (process.env.ZEROFACTORY_HUMAN_REVIEW ?? "0").toLowerCase();
  return value === "1" || value === "true" || value === "yes";
}

async function main() {
  const objective = process.argv.slice(2).join(" ").trim();
  const needsHumanReview = shouldRequireHumanReview();

  if (!objective) {
    throw new Error('Usage: npm run dev -- "<objective>"');
  }

  console.log("[zerofactory] Starting runZeroFactory...");
  const result = await runZeroFactory({
    objective,
    assumptions: [
      "Use TypeScript-first implementation",
      "Minimize tokens and unnecessary agent turns",
    ],
    needsHumanReview,
  });
  console.log("[zerofactory] runZeroFactory returned successfully.");

  console.log("\n=== Manager Plan ===\n");
  console.log(result.plan);

  console.log("\n=== Specialist Outputs ===\n");
  for (const item of result.specialists) {
    console.log(`- ${item.role}: ${item.content}`);
  }

  console.log("\n=== Final Output ===\n");
  console.log(result.result);

  if (needsHumanReview) {
    console.log("\n=== Hybrid Review Gate ===\n");
    console.log(
      "This run stopped after synthesis-ready output. Human review is expected before execution.",
    );
  }
}

try {
  await main();
} catch (error) {
  console.error(error instanceof Error ? error.message : error);
  process.exitCode = 1;
}
