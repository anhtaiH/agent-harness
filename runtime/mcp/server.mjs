#!/usr/bin/env node
import { execFile } from "node:child_process";
import { promisify } from "node:util";
import { readFileSync } from "node:fs";
import { promises as fs } from "node:fs";
import path from "node:path";
import os from "node:os";
import { fileURLToPath, pathToFileURL } from "node:url";

const SCRIPT_DIR = path.dirname(fileURLToPath(import.meta.url));
const ROOT = process.env.AGENT_HARNESS_ROOT || path.resolve(SCRIPT_DIR, "..");

function configuredSourceRoot() {
  try {
    const data = JSON.parse(readFileSync(path.join(ROOT, "config.json"), "utf8"));
    return typeof data.source_root === "string" ? data.source_root : null;
  } catch {
    return null;
  }
}

function packageVersion() {
  const sourceRoot = configuredSourceRoot();
  for (const candidate of [sourceRoot ? path.join(sourceRoot, "package.json") : null].filter(Boolean)) {
    try {
      const data = JSON.parse(readFileSync(candidate, "utf8"));
      if (typeof data.version === "string") return data.version;
    } catch {
      // fall through to the static fallback
    }
  }
  return "0.0.0";
}

const VERSION = packageVersion();

async function importPackage(packageName, relativePaths) {
  try {
    return await import(packageName);
  } catch {
    const sourceRoot = configuredSourceRoot();
    const paths = Array.isArray(relativePaths?.[0]) ? relativePaths : [relativePaths];
    const candidates = paths.flatMap((relativePath) =>
      [
        sourceRoot ? path.join(sourceRoot, "node_modules", ...relativePath) : null,
        // Installed layout: <runtime>/mcp/server.mjs next to <runtime>/source/agent-harness/node_modules
        path.join(SCRIPT_DIR, "..", "source", "agent-harness", "node_modules", ...relativePath),
        // Source-repo layout: <repo>/runtime/mcp/server.mjs next to <repo>/node_modules
        path.join(SCRIPT_DIR, "..", "..", "node_modules", ...relativePath),
        path.join(os.homedir(), "node_modules", ...relativePath),
      ].filter(Boolean)
    );
    let lastError;
    for (const candidate of candidates) {
      try {
        return await import(pathToFileURL(candidate).href);
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError;
  }
}

const fastMcp = await importPackage("fastmcp", ["fastmcp", "dist", "FastMCP.js"]);
const { FastMCP, UserError } = fastMcp;
const zod = await importPackage("zod", [["zod", "index.js"], ["zod", "dist", "esm", "index.js"]]);
const { z } = zod;

const execFileAsync = promisify(execFile);
const HARNESS = path.join(ROOT, "bin", "harness");
const STATUS_DIR = path.join(ROOT, "state", "status");
const MEMORY_INDEX = path.join(ROOT, "memory", "index.md");
const toolNames = [
  "start_task",
  "resume_task",
  "status",
  "read_artifact",
  "record_progress",
  "write_evidence",
  "evidence_doctor",
  "finish_task",
  "agent_capabilities",
  "agent_run",
  "review_plan",
  "review_run",
  "review_status",
  "review_synthesize",
  "pr_review_start",
  "pr_review_run",
  "pr_review_synthesize",
  "pr_review_feedback",
  "external_write_intent",
  "external_write_status",
  "external_write_doctor",
  "memory_query",
  "memory_candidate",
  "profile_generate",
  "self_check",
  "verify_gates",
];
const resourceUris = ["agent-harness://tasks/latest", "agent-harness://dashboard", "agent-harness://memory/index"];
const promptNames = ["start-from-description", "resume-latest", "finish-with-evidence", "review-pr"];
const taskId = z.string().regex(/^(latest|[A-Za-z0-9][A-Za-z0-9-]{0,95})$/);
const safeText = z.string().min(1).max(256000);
const agentName = z.enum(["codex", "claude", "cursor"]);

const defaultPatterns = [
  "gh[pousr]_[0-9A-Za-z_]{24,}",
  "sk-[0-9A-Za-z]{24,}",
  "AKIA[0-9A-Z]{16}",
  "xox[baprs]-[0-9A-Za-z-]{24,}",
  "-----BEGIN (?:RSA |EC |OPENSSH |)PRIVATE KEY-----",
  "eyJ[A-Za-z0-9_\\-]{10,}\\.[A-Za-z0-9_\\-]{10,}\\.[A-Za-z0-9_\\-]{10,}",
];

function loadPatterns() {
  try {
    const raw = JSON.parse(readFileSync(path.join(ROOT, "policy", "redaction-patterns.json"), "utf8"));
    if (Array.isArray(raw) && raw.length > 0 && raw.every((item) => typeof item === "string")) {
      return raw.map((item) => new RegExp(item, "i"));
    }
  } catch {
    // Use conservative built-ins.
  }
  return defaultPatterns.map((item) => new RegExp(item, "i"));
}

const redactionPatterns = loadPatterns();

function assertNoSensitive(value, label) {
  const text = typeof value === "string" ? value : JSON.stringify(value);
  if (redactionPatterns.some((pattern) => pattern.test(text))) {
    throw new UserError(`Refusing ${label}: text appears to contain sensitive raw material.`);
  }
}

function scrubbedEnv() {
  const allowed = new Set(["HOME", "PATH", "SHELL", "TMPDIR", "USER", "LOGNAME", "LANG", "LC_ALL", "LC_CTYPE", "TERM", "TERM_PROGRAM", "XDG_CONFIG_HOME", "XDG_CACHE_HOME", "XDG_DATA_HOME", "NODE_ENV"]);
  const prefixes = ["NVM_", "PYENV_", "VOLTA_", "PNPM_", "COREPACK_"];
  const sensitiveName = /(^|_)(TOKEN|SECRET|PASSWORD|PRIVATE_KEY|API_KEY|KEY|AUTHORIZATION|COOKIE|SESSION)$/;
  const env = {};
  for (const [key, value] of Object.entries(process.env)) {
    if ((allowed.has(key) || prefixes.some((prefix) => key.startsWith(prefix))) && !sensitiveName.test(key) && !(key.startsWith("NODE_") && key !== "NODE_ENV")) {
      env[key] = value;
    }
  }
  env.AGENT_HARNESS_ROOT = ROOT;
  return env;
}

async function runHarness(args, options = {}) {
  assertNoSensitive(args.join("\n"), "harness command");
  try {
    const result = await execFileAsync(HARNESS, args, {
      cwd: ROOT,
      env: scrubbedEnv(),
      timeout: options.timeoutMs || 120000,
      maxBuffer: options.maxBuffer || 10 * 1024 * 1024,
    });
    const stdout = result.stdout.trim();
    if (options.json) {
      try {
        const parsed = JSON.parse(stdout || "{}");
        assertNoSensitive(parsed, "harness output");
        return JSON.stringify(parsed, null, 2);
      } catch (error) {
        throw new UserError(`Harness command did not return JSON: ${error.message}`);
      }
    }
    assertNoSensitive(stdout, "harness output");
    return stdout || result.stderr.trim() || "ok";
  } catch (error) {
    const stdout = error.stdout ? String(error.stdout).trim() : "";
    const stderr = error.stderr ? String(error.stderr).trim() : "";
    throw new UserError(`Harness command failed: ${stderr || stdout || error.message}`);
  }
}

async function readIfExists(filePath, fallback) {
  try {
    const text = await fs.readFile(filePath, "utf8");
    assertNoSensitive(text, "resource content");
    return text;
  } catch (error) {
    if (error.code === "ENOENT") return fallback;
    throw error;
  }
}

const server = new FastMCP({
  name: "agent-harness",
  version: VERSION,
  instructions: "Local agent harness control plane. Use task packets, generated profiles, evidence, review lanes, and write intents. Do not use this server as a generic shell.",
  roots: { enabled: false },
});

server.addTool({
  name: "start_task",
  description: "Create a local harness task from a plain-English request.",
  parameters: z.object({
    repo: z.string().optional(),
    description: safeText,
    task_id: z.string().optional(),
    kind: z.string().optional(),
    risk: z.string().optional(),
    mode: z.enum(["plan", "run", "yolo"]).optional(),
  }),
  execute: async (args) => {
    const command = ["start"];
    if (args.repo) command.push(args.repo);
    command.push("--prompt", args.description, "--kind", args.kind || "general", "--risk", args.risk || "auto", "--mode", args.mode || "run", "--json");
    if (args.task_id) command.push("--task-id", args.task_id);
    return runHarness(command, { json: true });
  },
});

server.addTool({
  name: "resume_task",
  description: "Resume a harness task by id or latest.",
  parameters: z.object({ task_id: taskId.optional() }),
  execute: async (args) => runHarness(["resume", args.task_id || "latest", "--json"], { json: true }),
});

server.addTool({
  name: "status",
  description: "Return recent task status and refresh dashboard artifacts.",
  parameters: z.object({}),
  execute: async () => runHarness(["status", "--json"], { json: true }),
});

server.addTool({
  name: "read_artifact",
  description: "Read a safe task artifact.",
  parameters: z.object({ task_id: taskId, artifact: z.enum(["packet", "progress", "contract", "evidence", "task-json", "pr-comments-draft", "pr-risk", "pr-brief"]) }),
  execute: async (args) => runHarness(["read-artifact", args.task_id, args.artifact]),
});

server.addTool({
  name: "record_progress",
  description: "Append a checkpoint to task progress.",
  parameters: z.object({ task_id: taskId, note: safeText }),
  execute: async (args) => runHarness(["record-progress", args.task_id, "--note", args.note, "--json"], { json: true }),
});

server.addTool({
  name: "write_evidence",
  description: "Write or replace task evidence.",
  parameters: z.object({ task_id: taskId, content: safeText.optional(), summary: z.string().optional(), positive_proof: z.string().optional(), negative_proof: z.string().optional(), commands_run: z.string().optional() }),
  execute: async (args) => {
    const command = ["evidence", "write", args.task_id, "--json"];
    if (args.content) command.push("--content", args.content);
    if (args.summary) command.push("--summary", args.summary);
    if (args.positive_proof) command.push("--positive-proof", args.positive_proof);
    if (args.negative_proof) command.push("--negative-proof", args.negative_proof);
    if (args.commands_run) command.push("--commands-run", args.commands_run);
    return runHarness(command, { json: true });
  },
});

server.addTool({ name: "evidence_doctor", description: "Validate evidence for a task.", parameters: z.object({ task_id: taskId.optional() }), execute: async (args) => runHarness(["evidence", "doctor", args.task_id || "latest", "--json"], { json: true }) });
server.addTool({ name: "finish_task", description: "Finish a task after evidence passes.", parameters: z.object({ task_id: taskId.optional(), force: z.boolean().optional() }), execute: async (args) => runHarness(["finish", args.task_id || "latest", ...(args.force ? ["--force"] : []), "--json"], { json: true }) });
server.addTool({ name: "agent_capabilities", description: "List peer agent CLI availability.", parameters: z.object({}), execute: async () => runHarness(["agent", "capabilities"], { json: true }) });

server.addTool({
  name: "agent_run",
  description: "Run or dry-run a bounded peer agent lane.",
  parameters: z.object({ task_id: taskId, agent: agentName, role: z.string().optional(), prompt: safeText, dry_run: z.boolean().optional(), timeout: z.number().int().min(10).max(1800).optional() }),
  execute: async (args) => runHarness(["agent", "run", args.task_id, "--agent", args.agent, "--role", args.role || "reviewer", "--prompt", args.prompt, "--timeout", String(args.timeout || 120), ...(args.dry_run ? ["--dry-run"] : []), "--json"], { json: true, timeoutMs: (args.timeout || 120) * 1000 + 10000 }),
});

server.addTool({ name: "review_plan", description: "Create a review plan for a task.", parameters: z.object({ task_id: taskId.optional() }), execute: async (args) => runHarness(["review", "plan", args.task_id || "latest"], { json: true }) });
server.addTool({ name: "review_run", description: "Run or dry-run one review lane.", parameters: z.object({ task_id: taskId, lane: z.string().optional(), agent: agentName.optional(), dry_run: z.boolean().optional() }), execute: async (args) => runHarness(["review", "run", args.task_id, "--lane", args.lane || "scope", "--agent", args.agent || "codex", ...(args.dry_run ? ["--dry-run"] : [])], { json: true }) });
server.addTool({ name: "review_status", description: "Inspect peer review run status.", parameters: z.object({ task_id: taskId.optional() }), execute: async (args) => runHarness(["review", "status", args.task_id || "latest"], { json: true }) });
server.addTool({ name: "review_synthesize", description: "Synthesize review lanes.", parameters: z.object({ task_id: taskId.optional() }), execute: async (args) => runHarness(["review", "synthesize", args.task_id || "latest"], { json: true }) });

server.addTool({ name: "pr_review_start", description: "Build a PR review packet from a PR number, URL, or local ref.", parameters: z.object({ source: z.string(), repo: z.string().optional(), base: z.string().optional(), task_id: z.string().optional() }), execute: async (args) => runHarness(["pr-review", "start", args.source, ...(args.repo ? ["--repo", args.repo] : []), ...(args.base ? ["--base", args.base] : []), ...(args.task_id ? ["--task-id", args.task_id] : [])], { json: true, timeoutMs: 180000 }) });
server.addTool({ name: "pr_review_run", description: "Run or dry-run fast PR review lanes.", parameters: z.object({ task_id: taskId, lane: z.string().optional(), agent: agentName.optional(), max_lanes: z.number().int().optional(), dry_run: z.boolean().optional() }), execute: async (args) => runHarness(["pr-review", "run", args.task_id, "--lane", args.lane || "auto", "--agent", args.agent || "codex", ...(args.max_lanes ? ["--max-lanes", String(args.max_lanes)] : []), ...(args.dry_run ? ["--dry-run"] : [])], { json: true }) });
server.addTool({ name: "pr_review_synthesize", description: "Synthesize PR review findings into a draft.", parameters: z.object({ task_id: taskId }), execute: async (args) => runHarness(["pr-review", "synthesize", args.task_id], { json: true }) });
server.addTool({ name: "pr_review_feedback", description: "Record local outcome feedback for a drafted PR review finding.", parameters: z.object({ task_id: taskId, finding_id: z.string(), outcome: z.enum(["posted", "accepted", "fixed", "rejected", "ignored"]), note: z.string().optional() }), execute: async (args) => runHarness(["pr-review", "feedback", args.task_id, "--finding-id", args.finding_id, "--outcome", args.outcome, ...(args.note ? ["--note", args.note] : [])], { json: true }) });

server.addTool({ name: "external_write_intent", description: "Record a task-scoped connector write intent.", parameters: z.object({ task_id: taskId, provider: z.enum(["confluence", "jira", "slack", "github"]), operation: z.enum(["create", "update", "comment", "review-comment", "send", "schedule", "transition", "maintenance"]), target: z.string(), summary: z.string(), content_preview: z.string().optional(), ttl_hours: z.number().int().optional() }), execute: async (args) => runHarness(["external-write", "intent", args.task_id, "--provider", args.provider, "--operation", args.operation, "--target", args.target, "--summary", args.summary, ...(args.content_preview ? ["--content-preview", args.content_preview] : []), "--ttl-hours", String(args.ttl_hours || 24)], { json: true }) });
server.addTool({ name: "external_write_status", description: "List task-scoped connector write intents.", parameters: z.object({ task_id: taskId.optional() }), execute: async (args) => runHarness(["external-write", "status", args.task_id || "latest"], { json: true }) });
server.addTool({ name: "external_write_doctor", description: "Validate task-scoped connector write intents.", parameters: z.object({ task_id: taskId.optional() }), execute: async (args) => runHarness(["external-write", "doctor", args.task_id || "latest"], { json: true }) });

server.addTool({ name: "memory_query", description: "Query curated local memory.", parameters: z.object({ query: z.string() }), execute: async (args) => runHarness(["memory", "query", args.query], { json: true }) });
server.addTool({ name: "memory_candidate", description: "Append a source-backed local memory candidate.", parameters: z.object({ claim: z.string(), source: z.string(), confidence: z.string().optional() }), execute: async (args) => runHarness(["memory", "candidate", "--claim", args.claim, "--source", args.source, "--confidence", args.confidence || "medium"], { json: true }) });
server.addTool({ name: "profile_generate", description: "Generate or refresh the local workspace profile from a repo checkout.", parameters: z.object({ repo: z.string(), repo_alias: z.string().optional() }), execute: async (args) => runHarness(["profile", "generate", "--repo", args.repo, ...(args.repo_alias ? ["--repo-alias", args.repo_alias] : []), "--json"], { json: true }) });
server.addTool({ name: "self_check", description: "Run harness self-check.", parameters: z.object({}), execute: async () => runHarness(["self-check", "--json"], { json: true, timeoutMs: 300000 }) });
server.addTool({
  name: "verify_gates",
  description: "Prove the guardrail hooks fire: run canned allow/ask/deny payloads through every policy hook and return the case-by-case results.",
  parameters: z.object({ record: z.boolean().optional() }),
  execute: async (args) => runHarness(["verify-gates", ...(args.record ? ["--record"] : []), "--json"], { json: true, timeoutMs: 120000 }),
});

server.addResource({ uri: "agent-harness://tasks/latest", name: "Latest Agent Harness Task", mimeType: "text/markdown", load: async () => ({ text: await readIfExists(path.join(STATUS_DIR, "latest.md"), "No latest task status has been generated yet.\n") }) });
server.addResource({ uri: "agent-harness://dashboard", name: "Agent Harness Dashboard", mimeType: "text/html", load: async () => ({ text: await readIfExists(path.join(STATUS_DIR, "index.html"), "Run the status tool to generate the dashboard.\n") }) });
server.addResource({ uri: "agent-harness://memory/index", name: "Agent Harness Memory Index", mimeType: "text/markdown", load: async () => ({ text: await readIfExists(MEMORY_INDEX, "No memory index found.\n") }) });

server.addPrompt({ name: "start-from-description", description: "Start an agent harness task from a plain-English request.", arguments: [{ name: "description", required: true }], load: async ({ description }) => `Use the agent harness MCP tools. Infer repo, kind, risk, and mode, call start_task, work from the generated packet, and finish through evidence.\n\nRequest: ${description}` });
server.addPrompt({ name: "resume-latest", description: "Resume the latest harness task.", load: async () => "Call resume_task with task_id=latest, read packet/progress/evidence, continue, and update progress/evidence before finishing." });
server.addPrompt({ name: "finish-with-evidence", description: "Finish a task with evidence.", arguments: [{ name: "task_id", required: true }], load: async ({ task_id }) => `For ${task_id}, run needed review lanes, call evidence_doctor, write complete evidence if needed, then call finish_task.` });
server.addPrompt({ name: "review-pr", description: "Review a PR through the draft-only PR review flow.", arguments: [{ name: "source", required: true }], load: async ({ source }) => `Call pr_review_start for ${source}, run pr_review_run lane=auto for a fast private pass, then pr_review_synthesize. Keep comments draft-only unless explicitly told to post and an external_write_intent is active.` });

if (process.argv.includes("--self-test")) {
  const envProbe = scrubbedEnv();
  console.log(JSON.stringify({ name: "agent-harness", version: VERSION, tools: toolNames, resources: resourceUris, prompts: promptNames, redaction_patterns_nonempty: redactionPatterns.length > 0, env_scrub: { root_set: envProbe.AGENT_HARNESS_ROOT === ROOT } }, null, 2));
} else {
  server.start({ transportType: "stdio" });
}
