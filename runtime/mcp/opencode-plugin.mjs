/**
 * opencode plugin bridge for the Agent Harness pre-tool policy gate.
 *
 * Installed (with __AGENT_HARNESS_ROOT__ substituted) to
 * ~/.config/opencode/plugins/agent-harness.js by `agent-harness setup`.
 *
 * Routes every tool execution through runtime/hooks/pre-tool-policy.py — the
 * same policy engine Claude Code and Cursor use — and blocks on deny.
 * Fails open on infrastructure errors so a policy bug never bricks opencode.
 */
export const AgentHarnessPlugin = async ({ directory }) => {
  const ROOT = "__AGENT_HARNESS_ROOT__";
  const { spawnSync } = await import("node:child_process");

  const decide = (toolName, args, cwd) => {
    const payload = JSON.stringify({ tool_name: toolName || "", tool_input: args || {}, cwd: cwd || directory || process.cwd() });
    const result = spawnSync("python3", [`${ROOT}/hooks/pre-tool-policy.py`], {
      input: payload,
      encoding: "utf8",
      timeout: 15000,
      env: { ...process.env, AGENT_HARNESS_ROOT: ROOT },
    });
    if (result.error || typeof result.stdout !== "string") return null;
    for (const line of result.stdout.split("\n")) {
      const trimmed = line.trim();
      if (!trimmed.startsWith("{")) continue;
      try {
        const data = JSON.parse(trimmed);
        const specific = data && data.hookSpecificOutput;
        if (specific && specific.permissionDecision) {
          return { decision: specific.permissionDecision, reason: specific.permissionDecisionReason || "Blocked by agent harness policy." };
        }
      } catch {
        // tolerate non-JSON diagnostic lines
      }
    }
    return null;
  };

  return {
    "tool.execute.before": async (input, output) => {
      let verdict = null;
      try {
        verdict = decide(input && input.tool, output && output.args, directory);
      } catch {
        return; // fail open on bridge errors
      }
      if (verdict && verdict.decision === "deny") {
        throw new Error(verdict.reason);
      }
    },
  };
};
