/**
 * pi extension bridge for the Agent Harness pre-tool policy gate.
 *
 * Installed (with __AGENT_HARNESS_ROOT__ substituted) to
 * ~/.pi/agent/extensions/agent-harness.ts by `agent-harness setup`.
 *
 * pi is YOLO-by-default and deliberately ships no permission prompts; its
 * documented extension point for guardrails is a tool_call listener that can
 * block the call. This bridge routes bash/write/edit calls through
 * runtime/hooks/pre-tool-policy.py — the same engine every other surface uses.
 * It fails open on infrastructure errors and feature-detects the API so an
 * extension-API change degrades to a no-op instead of breaking pi.
 */
export default function agentHarness(pi: any) {
  const ROOT = "__AGENT_HARNESS_ROOT__";
  if (!pi || typeof pi.on !== "function") return;

  pi.on("tool_call", async (event: any) => {
    try {
      const { spawnSync } = await import("node:child_process");
      const toolName = String(event?.toolName ?? event?.name ?? event?.tool ?? "");
      const args = event?.args ?? event?.params ?? {};
      const payload = JSON.stringify({
        tool_name: toolName === "bash" ? "Bash" : toolName,
        tool_input: args,
        cwd: process.cwd(),
      });
      const result = spawnSync("python3", [`${ROOT}/hooks/pre-tool-policy.py`], {
        input: payload,
        encoding: "utf8",
        timeout: 15000,
        env: { ...process.env, AGENT_HARNESS_ROOT: ROOT },
      });
      if (result.error || typeof result.stdout !== "string") return undefined;
      for (const line of result.stdout.split("\n")) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("{")) continue;
        const data = JSON.parse(trimmed);
        const decision = data?.hookSpecificOutput?.permissionDecision;
        if (decision === "deny") {
          const reason = data.hookSpecificOutput.permissionDecisionReason || "Blocked by agent harness policy.";
          return { block: true, reason };
        }
      }
    } catch {
      // fail open: never brick the session on a bridge error
    }
    return undefined;
  });
}
