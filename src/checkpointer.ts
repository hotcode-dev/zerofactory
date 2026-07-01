import { MemorySaver } from "@langchain/langgraph";
import { writeFileSync, readFileSync, existsSync } from "fs";
import type { RunnableConfig } from "@langchain/core/runnables";
import type { Checkpoint, CheckpointMetadata, PendingWrite } from "@langchain/langgraph-checkpoint";

function replacer(key: string, value: any) {
  if (value instanceof Uint8Array) {
    return { type: 'Uint8Array', data: Array.from(value) };
  }
  return value;
}

function reviver(key: string, value: any) {
  if (value && typeof value === 'object' && value.type === 'Uint8Array') {
    return new Uint8Array(value.data);
  }
  return value;
}

import { mkdirSync } from "fs";
import { dirname } from "path";

export class DiskMemorySaver extends MemorySaver {
  private filePath: string;

  constructor(filePath: string) {
    super();
    this.filePath = filePath;
    mkdirSync(dirname(this.filePath), { recursive: true });
    this.load();
  }

  private load() {
    if (existsSync(this.filePath)) {
      try {
        const data = JSON.parse(readFileSync(this.filePath, "utf-8"), reviver);
        if (data.storage) this.storage = data.storage;
        if (data.writes) this.writes = data.writes;
        console.log(`[DiskMemorySaver] Loaded checkpoints from ${this.filePath}`);
      } catch (e: any) {
        console.error(`[DiskMemorySaver] Failed to load checkpoints: ${e.message}`);
      }
    }
  }

  private save() {
    try {
      const data = {
        storage: this.storage,
        writes: this.writes,
      };
      writeFileSync(this.filePath, JSON.stringify(data, replacer));
    } catch (e: any) {
      console.error(`[DiskMemorySaver] Failed to save checkpoints: ${e.message}`);
    }
  }

  async put(config: RunnableConfig, checkpoint: Checkpoint, metadata: CheckpointMetadata) {
    const result = await super.put(config, checkpoint, metadata);
    this.save();
    return result;
  }

  async putWrites(config: RunnableConfig, writes: PendingWrite[], taskId: string) {
    await super.putWrites(config, writes, taskId);
    this.save();
  }

  getAllThreads(): string[] {
    const threadIds = new Set<string>();
    // this.storage is typed as Record<string, Record<string, SerializedCheckpoint>>
    if (this.storage) {
      for (const threadId of Object.keys(this.storage)) {
        threadIds.add(threadId);
      }
    }
    return Array.from(threadIds);
  }
}
