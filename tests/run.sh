#!/usr/bin/env bash
set -euo pipefail
trap 'echo "TEST FAILED at ${BASH_SOURCE[0]}:${LINENO}: ${BASH_COMMAND}" >&2' ERR

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TMP_BASE="${TMPDIR:-/tmp}"
TMP_DIR="${TMP_BASE%/}/agent-harness-test-$$"
RUNTIME="$TMP_DIR/runtime"
REPO="$TMP_DIR/repo"

cleanup() {
  rm -rf "$TMP_DIR"
}
trap cleanup EXIT

mkdir -p "$REPO/.github" "$REPO/.agentflow/rules"
git -C "$REPO" init >/dev/null
git -C "$REPO" config user.email "agent@example.invalid"
git -C "$REPO" config user.name "Agent Harness Test"
printf '# Test Repo\n' > "$REPO/AGENTS.md"
printf '/src/** @team/example\n' > "$REPO/.github/CODEOWNERS"
printf '# Agentflow\n' > "$REPO/.agentflow/README.md"
mkdir -p "$REPO/src"
printf 'export const value = 1;\n' > "$REPO/src/index.ts"
git -C "$REPO" add .
git -C "$REPO" commit -m "init" >/dev/null

python3 -m py_compile "$ROOT/src/agent_harness.py"
chmod +x "$ROOT/bin/agent-harness"
"$ROOT/bin/agent-harness" --version >/dev/null
test -f "$ROOT/INSTALL.md"
"$ROOT/bin/agent-harness" install-prompt | grep -q "INSTALL.md"
"$ROOT/bin/agent-harness" verify-gates --json | grep -q '"ok": true'
"$ROOT/bin/agent-harness" --runtime-root "$TMP_DIR/not-installed" where --json | grep -q '"installed": false'
if "$ROOT/bin/agent-harness" --runtime-root "$TMP_DIR/not-installed" doctor --json >/dev/null 2>&1; then
  echo "expected doctor to fail before setup" >&2
  exit 1
fi
npm exec --yes --package "$ROOT" -- agent-harness setup --workspace demo --repo "$REPO" --runtime-root "$RUNTIME" --shim-dir "$TMP_DIR/bin" --yes --no-register --json >/dev/null
test -x "$RUNTIME/source/agent-harness/bin/agent-harness"
grep -q "source/agent-harness" "$RUNTIME/bin/harness"
"$RUNTIME/bin/harness" doctor --json >/dev/null
"$RUNTIME/bin/harness" verify-gates --json | grep -q '"ok": true'
"$TMP_DIR/bin/agent-harness" doctor --json >/dev/null
"$TMP_DIR/bin/agent-harness" where --runtime-root "$RUNTIME" --json >/dev/null
"$TMP_DIR/bin/ah" examples >/dev/null
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" start demo --prompt "Inspect the sample repo" --task-id sample-task --risk green --mode run --json >/dev/null
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" record-progress sample-task --note "Started sample task." --json >/dev/null
if "$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" evidence doctor sample-task --json >/dev/null 2>&1; then
  echo "expected evidence doctor to fail before evidence exists" >&2
  exit 1
fi
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" evidence write sample-task --summary "Inspection complete." --positive-proof "Read sample file." --negative-proof "No edits made." --commands-run "py_compile and harness smoke tests" --json >/dev/null
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" evidence doctor sample-task --json >/dev/null
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" external-write intent sample-task --provider confluence --operation update --target "page 1" --summary "Smoke write intent" >/dev/null
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" external-write doctor sample-task >/dev/null
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" pr-review start feature/ref --repo demo --base HEAD --task-id pr-sample >/dev/null
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" pr-review run pr-sample --lane auto --dry-run >/dev/null
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" pr-review synthesize pr-sample >/dev/null
node "$RUNTIME/mcp/server.mjs" --self-test >/dev/null
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" metrics export >/dev/null
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" eval run all --no-record >/dev/null
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" upgrade --dry-run --json >/dev/null
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" uninstall --restore-adapters --dry-run --json >/dev/null

SKIP_RUNTIME="$TMP_DIR/runtime-skip-deps"
npm exec --yes --package "$ROOT" -- agent-harness setup --workspace demo-skip --repo "$REPO" --runtime-root "$SKIP_RUNTIME" --shim-dir "$TMP_DIR/bin-skip" --yes --no-register --skip-deps --json >/dev/null
"$TMP_DIR/bin-skip/agent-harness" where --json | grep -q '"installed": true'

FAKE_HOME="$TMP_DIR/home"
FAKE_BIN="$TMP_DIR/fake-bin"
ADAPTER_RUNTIME="$TMP_DIR/runtime-adapters"
mkdir -p "$FAKE_HOME" "$FAKE_BIN"
printf '#!/usr/bin/env bash\ncase "$1" in --version) echo codex-test ;; *) exit 0 ;; esac\n' > "$FAKE_BIN/codex"
printf '#!/usr/bin/env bash\nif [ "$1" = "mcp" ]; then exit 0; fi\ncase "$1" in --version) echo claude-test ;; *) exit 0 ;; esac\n' > "$FAKE_BIN/claude"
printf '#!/usr/bin/env bash\ncase "$1" in --version) echo cursor-test ;; *) exit 0 ;; esac\n' > "$FAKE_BIN/cursor-agent"
printf '#!/usr/bin/env bash\ncase "$1" in --version) echo opencode-test ;; *) exit 0 ;; esac\n' > "$FAKE_BIN/opencode"
printf '#!/usr/bin/env bash\ncase "$1" in --version) echo pi-test ;; *) exit 0 ;; esac\n' > "$FAKE_BIN/pi"
chmod +x "$FAKE_BIN/codex" "$FAKE_BIN/claude" "$FAKE_BIN/cursor-agent" "$FAKE_BIN/opencode" "$FAKE_BIN/pi"
HOME="$FAKE_HOME" XDG_CONFIG_HOME="$FAKE_HOME/.config" PATH="$FAKE_BIN:$PATH" "$ROOT/bin/agent-harness" setup --workspace demo-adapters --repo "$REPO" --runtime-root "$ADAPTER_RUNTIME" --shim-dir "$TMP_DIR/bin-adapters" --yes --json >/dev/null
grep -q "Agent Harness" "$FAKE_HOME/.codex/AGENTS.md"
grep -q "mcp_servers.demo-adapters-agent-harness" "$FAKE_HOME/.codex/config.toml"
test -f "$FAKE_HOME/.codex/skills/agent-harness/task-packet/SKILL.md"
grep -q "Agent Harness" "$FAKE_HOME/.claude/CLAUDE.md"
grep -q "demo-adapters-agent-harness" "$FAKE_HOME/.cursor/mcp.json"
# Gate wiring: Claude settings hooks + deny seeds
grep -q "pre-tool-policy.py" "$FAKE_HOME/.claude/settings.json"
grep -q "stop-requires-evidence.py" "$FAKE_HOME/.claude/settings.json"
grep -q 'Read(~/.ssh/\*\*)' "$FAKE_HOME/.claude/settings.json"
test -f "$FAKE_HOME/.claude/skills/evidence-gate/SKILL.md"
test -f "$FAKE_HOME/.claude/agents/agent-harness-reviewer.md"
# Cursor hooks + CLI deny seeds
grep -q "cursor-bridge.py" "$FAKE_HOME/.cursor/hooks.json"
grep -q "beforeShellExecution" "$FAKE_HOME/.cursor/hooks.json"
grep -q 'Read(\*\*/.env)' "$FAKE_HOME/.cursor/cli-config.json"
# opencode: MCP entry, AGENTS.md block, plugin, skills
grep -q "demo-adapters-agent-harness" "$FAKE_HOME/.config/opencode/opencode.json"
grep -q "Agent Harness" "$FAKE_HOME/.config/opencode/AGENTS.md"
grep -q "tool.execute.before" "$FAKE_HOME/.config/opencode/plugins/agent-harness.js"
# Root substitution happened (macOS resolves /var -> /private/var, so match the marker, not the raw path)
grep -q "hooks/pre-tool-policy.py" "$FAKE_HOME/.config/opencode/plugins/agent-harness.js"
if grep -q "__AGENT_HARNESS_ROOT__" "$FAKE_HOME/.config/opencode/plugins/agent-harness.js"; then
  echo "opencode plugin still contains the unsubstituted root placeholder" >&2
  exit 1
fi
test -f "$FAKE_HOME/.config/opencode/skills/task-packet/SKILL.md"
# pi: APPEND_SYSTEM.md block + extension + repo-local .agents/skills (git-excluded)
grep -q "Agent Harness" "$FAKE_HOME/.pi/agent/APPEND_SYSTEM.md"
grep -q "tool_call" "$FAKE_HOME/.pi/agent/extensions/agent-harness.ts"
test -f "$REPO/.agents/skills/task-packet/SKILL.md"
grep -q "CLAUDE.local.md" "$REPO/.git/info/exclude"
grep -q ".cursor/rules/agent-harness.mdc" "$REPO/.git/info/exclude"
grep -q ".agents/skills/" "$REPO/.git/info/exclude"
if git -C "$REPO" status --short | grep -E 'CLAUDE.local.md|\\.cursor/rules/agent-harness\\.mdc|\\.agents/'; then
  echo "local adapter files should be ignored" >&2
  exit 1
fi
# End-to-end gate check against the installed adapter runtime
HOME="$FAKE_HOME" "$ROOT/bin/agent-harness" --runtime-root "$ADAPTER_RUNTIME" verify-gates --json | grep -q '"ok": true'
HOME="$FAKE_HOME" XDG_CONFIG_HOME="$FAKE_HOME/.config" PATH="$FAKE_BIN:$PATH" "$ROOT/bin/agent-harness" --runtime-root "$ADAPTER_RUNTIME" uninstall --restore-adapters --json >/dev/null
if grep -q "Agent Harness" "$FAKE_HOME/.codex/AGENTS.md"; then
  echo "Codex managed instructions should be removed on restore" >&2
  exit 1
fi
if grep -q "Agent Harness" "$FAKE_HOME/.claude/CLAUDE.md"; then
  echo "Claude managed instructions should be removed on restore" >&2
  exit 1
fi
if grep -q "agent-harness" "$FAKE_HOME/.claude/settings.json"; then
  echo "Claude settings hooks should be removed on restore" >&2
  exit 1
fi
if [ -e "$FAKE_HOME/.claude/skills/evidence-gate/SKILL.md" ] || [ -e "$FAKE_HOME/.claude/agents/agent-harness-reviewer.md" ]; then
  echo "Claude skills/agents should be removed on restore" >&2
  exit 1
fi
if grep -q "cursor-bridge.py" "$FAKE_HOME/.cursor/hooks.json"; then
  echo "Cursor hooks should be removed on restore" >&2
  exit 1
fi
if grep -q 'Read(\*\*/.env)' "$FAKE_HOME/.cursor/cli-config.json"; then
  echo "Cursor CLI deny seeds should be removed on restore" >&2
  exit 1
fi
if grep -q "demo-adapters-agent-harness" "$FAKE_HOME/.config/opencode/opencode.json"; then
  echo "opencode MCP entry should be removed on restore" >&2
  exit 1
fi
if [ -e "$FAKE_HOME/.config/opencode/plugins/agent-harness.js" ] || [ -e "$FAKE_HOME/.pi/agent/extensions/agent-harness.ts" ]; then
  echo "opencode plugin / pi extension should be removed on restore" >&2
  exit 1
fi
if [ -e "$REPO/.agents/skills/task-packet/SKILL.md" ]; then
  echo "repo-local pi skills should be removed on restore" >&2
  exit 1
fi
if [ -e "$REPO/CLAUDE.local.md" ] || [ -e "$REPO/.cursor/rules/agent-harness.mdc" ]; then
  echo "repo-local adapter files should be removed on restore" >&2
  exit 1
fi

echo "agent-harness tests passed"
