#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TMP_DIR="${TMPDIR:-/tmp}/agent-harness-test-$$"
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
"$ROOT/bin/agent-harness" install --workspace demo --repo "$REPO" --runtime-root "$RUNTIME" --no-register --json >/dev/null
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" self-check --json >/dev/null
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

echo "agent-harness tests passed"
