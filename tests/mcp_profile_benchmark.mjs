#!/usr/bin/env node
import path from "node:path";
import { fileURLToPath } from "node:url";
import { Client } from "@modelcontextprotocol/sdk/client/index.js";
import { StdioClientTransport } from "@modelcontextprotocol/sdk/client/stdio.js";

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const server = path.join(root, "runtime", "mcp", "server.mjs");

async function measure(profile) {
  const client = new Client({ name: `profile-benchmark-${profile}`, version: "1.0.0" });
  const transport = new StdioClientTransport({
    command: process.execPath,
    args: [server],
    env: { ...process.env, AGENT_HARNESS_ROOT: path.join(root, "runtime"), AGENT_HARNESS_MCP_PROFILE: profile },
    stderr: "pipe",
  });
  await client.connect(transport);
  const response = await client.listTools();
  await client.close();
  return { profile, tools: response.tools.length, schema_bytes: Buffer.byteLength(JSON.stringify(response.tools)) };
}

const compact = await measure("compact");
const legacy = await measure("legacy");
const reduction = 1 - compact.schema_bytes / legacy.schema_bytes;
const result = { compact, legacy, reduction: Number(reduction.toFixed(4)), target: 0.6, ok: reduction >= 0.6 };
console.log(JSON.stringify(result, null, 2));
if (!result.ok) process.exitCode = 1;
