import { DynamicTool } from "@langchain/core/tools";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

/**
 * Connects to a local MCP server (like the ones used by Hermes)
 * and returns an array of LangChain DynamicTools.
 */
export async function loadMcpTools(command: string, args: string[]): Promise<DynamicTool[]> {
  const transport = new StdioClientTransport({
    command,
    args,
  });

  const client = new Client(
    {
      name: "langgraph-zerofactory",
      version: "1.0.0",
    },
    {
      capabilities: {
        tools: {},
      },
    }
  );

  await client.connect(transport);
  
  // List tools from the MCP server
  const response = await client.listTools();
  
  const langchainTools = response.tools.map((tool) => {
    return new DynamicTool({
      name: tool.name,
      description: tool.description || "",
      // Assume the input schema matches what the LLM generates
      schema: tool.inputSchema as any,
      func: async (input) => {
        const result = await client.callTool({
          name: tool.name,
          arguments: input,
        });
        
        // MCP tool results are typically an array of content objects
        if (result.content && result.content.length > 0) {
            const textContent = result.content.filter(c => c.type === 'text').map(c => (c as any).text).join('\n');
            return textContent;
        }
        return JSON.stringify(result);
      },
    });
  });

  return langchainTools;
}
