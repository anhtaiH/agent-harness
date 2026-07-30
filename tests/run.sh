#!/usr/bin/env bash
set -euo pipefail
trap 'echo "TEST FAILED at ${BASH_SOURCE[0]}:${LINENO}: ${BASH_COMMAND}" >&2' ERR

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"

python_binding_error() {
  echo "$1" >&2
  exit 1
}

[ -n "${AGENT_HARNESS_PYTHON:-}" ] ||
  python_binding_error "AGENT_HARNESS_PYTHON must be set"
case "$AGENT_HARNESS_PYTHON" in
  /*) ;;
  *) python_binding_error "AGENT_HARNESS_PYTHON must be an absolute path" ;;
esac
[ -x "$AGENT_HARNESS_PYTHON" ] ||
  python_binding_error "AGENT_HARNESS_PYTHON must be executable"

PYTHON_REAL="$(
  cd "$(dirname "$AGENT_HARNESS_PYTHON")" &&
    printf '%s/%s\n' "$PWD" "$(basename "$AGENT_HARNESS_PYTHON")"
)" || python_binding_error "AGENT_HARNESS_PYTHON path resolution failed"
[ ! -L "$AGENT_HARNESS_PYTHON" ] ||
  python_binding_error "AGENT_HARNESS_PYTHON must be its canonical real path"
[ "$PYTHON_REAL" = "$AGENT_HARNESS_PYTHON" ] ||
  python_binding_error "AGENT_HARNESS_PYTHON must be its canonical real path"

python_identity() {
  if /usr/bin/stat -f '%d:%i' "$AGENT_HARNESS_PYTHON" 2>/dev/null; then
    return
  fi
  /usr/bin/stat -Lc '%d:%i' "$AGENT_HARNESS_PYTHON" 2>/dev/null
}

PYTHON_IDENTITY="$(python_identity)" ||
  python_binding_error "AGENT_HARNESS_PYTHON identity unavailable"
readonly AGENT_HARNESS_PYTHON
readonly PYTHON_IDENTITY

validate_python_identity() {
  local current_python_identity
  current_python_identity="$(python_identity)" ||
    python_binding_error "AGENT_HARNESS_PYTHON changed after validation"
  [ "$current_python_identity" = "$PYTHON_IDENTITY" ] ||
    python_binding_error "AGENT_HARNESS_PYTHON changed after validation"
}

run_bound_python() {
  validate_python_identity
  "$AGENT_HARNESS_PYTHON" "$@"
}

PYTHON_VERSION="$(
  run_bound_python -c \
    'import sys; print(f"{sys.version_info.major}\t{sys.version_info.minor}")'
)" || python_binding_error "AGENT_HARNESS_PYTHON probe failed"
IFS=$'\t' read -r PYTHON_MAJOR PYTHON_MINOR <<<"$PYTHON_VERSION"
if ! [[ "$PYTHON_MAJOR" =~ ^[0-9]+$ && "$PYTHON_MINOR" =~ ^[0-9]+$ ]] ||
   [ "$PYTHON_MAJOR" -lt 3 ] ||
   { [ "$PYTHON_MAJOR" -eq 3 ] && [ "$PYTHON_MINOR" -lt 10 ]; }; then
  python_binding_error "AGENT_HARNESS_PYTHON requires Python 3.10 or newer"
fi
PYTHONPATH="$ROOT/src" run_bound_python -m unittest discover \
  -s "$ROOT/tests/unit" -p 'test_*.py'

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

run_bound_python -m py_compile "$ROOT/src/agent_harness.py"
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

# Hook-root derivation: a hook invoked with NO AGENT_HARNESS_ROOT env must read
# state from ITS OWN runtime (parents[1]), not a hardcoded "default" workspace.
# RUNTIME here is a non-"default" path, so this fails if the hooks regress.
HOOK_REPO="$TMP_DIR/hookroot-repo"
mkdir -p "$HOOK_REPO"
"$RUNTIME/bin/harness" start demo --prompt "hook root probe" --task-id hookroot-probe --json >/dev/null
run_bound_python -c "
import json, pathlib
p = pathlib.Path('$RUNTIME/state/active-tasks.json')
d = json.loads(p.read_text()) if p.exists() else {}
d['$HOOK_REPO'] = {'task_id': 'hookroot-probe', 'mode': 'run', 'updated_at': '2099-01-01T00:00:00Z'}
p.write_text(json.dumps(d))
"
# No AGENT_HARNESS_ROOT in env; the hook must still find hookroot-probe (no evidence) and block.
validate_python_identity
hook_out="$(env -u AGENT_HARNESS_ROOT "$AGENT_HARNESS_PYTHON" "$RUNTIME/hooks/stop-requires-evidence.py" <<JSON
{"cwd": "$HOOK_REPO"}
JSON
)" || true
echo "$hook_out" | grep -q "hookroot-probe" || { echo "stop hook did not derive its runtime root from __file__" >&2; exit 1; }
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

# Orchestration conductor: dynamic plan, gated dry-run to autonomous finish
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" start demo --prompt "Orchestrated demo task" --task-id orch-task --risk red --mode run --json >/dev/null
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" orchestrate plan orch-task --dry-run --json | grep -q '"security-review"'
# With the finish knob, the deterministic path runs all the way to finish
AGENT_HARNESS_ORCH_DRYRUN_FINISH=1 "$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" orchestrate run orch-task --dry-run --json | grep -q '"finished": true'
test -f "$RUNTIME/tasks/orch-task/orchestration/ledger.jsonl"
grep -q "run-complete" "$RUNTIME/tasks/orch-task/orchestration/ledger.jsonl"
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" orchestrate status orch-task | grep -q '"plan"'
# A plain dry run is a rehearsal: it must NOT finish or write the real evidence.md
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" start demo --prompt "Rehearsal task" --task-id orch-rehearse --risk green --mode run --json >/dev/null
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" orchestrate run orch-rehearse --dry-run --json | grep -q '"finished": false'
if [ -f "$RUNTIME/tasks/orch-rehearse/evidence.md" ]; then
  echo "dry-run rehearsal must not write the real evidence.md" >&2
  exit 1
fi
test -f "$RUNTIME/tasks/orch-rehearse/orchestration/dry-run/evidence-preview.md"
run_bound_python -c "import json,sys; m=json.load(open('$RUNTIME/tasks/orch-rehearse/task.json')); sys.exit(0 if m['status'] != 'finished' else 1)"
# Fix loop recovers from a transient QA failure
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" start demo --prompt "Orchestrated fix-loop task" --task-id orch-fix --risk green --mode run --json >/dev/null
AGENT_HARNESS_ORCH_DRYRUN_FINISH=1 AGENT_HARNESS_ORCH_FAIL_STEPS=verify AGENT_HARNESS_ORCH_FAIL_ATTEMPTS=1 "$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" orchestrate run orch-fix --dry-run --json | grep -q '"finished": true'
# Persistent reviewer rejection ends blocked, never finishes
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" start demo --prompt "Orchestrated blocked task" --task-id orch-block --risk green --mode run --json >/dev/null
if AGENT_HARNESS_ORCH_DRYRUN_FINISH=1 AGENT_HARNESS_ORCH_FAIL_STEPS=review "$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" orchestrate run orch-block --dry-run --max-attempts 2 --json | grep -q '"finished": true'; then
  echo "blocked orchestration run must not finish the task" >&2
  exit 1
fi

# Anti-hallucination: evidence must not fabricate PASS; strict tasks need a real check
# (doctor exits 2 on failure; capture-then-grep so pipefail does not trip set -e)
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" start demo --prompt "strict task" --task-id ah-strict --risk yellow --json >/dev/null
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" evidence write ah-strict --summary "did work" --json >/dev/null
grep -q "NOT VERIFIED" "$RUNTIME/tasks/ah-strict/evidence.md"  # omitted results are honest, not fabricated PASS
strict_out="$("$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" evidence doctor ah-strict --json || true)"
echo "$strict_out" | grep -q '"ok": false'  # strict blocks: no recorded check
validate_python_identity
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" run-check --json ah-strict -- "$AGENT_HARNESS_PYTHON" -c "print('real'); exit(0)" | grep -q '"ok": true'
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" evidence write ah-strict --summary "did work" --positive-result PASS --commands-run "bound Python -c ..." --json >/dev/null
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" evidence doctor ah-strict --json | grep -q '"ok": true'  # now backed by a passing check
# A FAILING check must not satisfy strict PASS
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" start demo --prompt "liar task" --task-id ah-liar --risk red --json >/dev/null
validate_python_identity
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" run-check --json ah-liar -- "$AGENT_HARNESS_PYTHON" -c "exit(1)" >/dev/null 2>&1 || true
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" evidence write ah-liar --summary lies --positive-result PASS --commands-run x --json >/dev/null
liar_out="$("$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" evidence doctor ah-liar --json || true)"
echo "$liar_out" | grep -q '"ok": false'
# Memory loop: candidate -> inbox -> queryable -> promote -> claims.jsonl
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" memory candidate --claim "widget cache needs invalidation" --source "src/w.py:5" >/dev/null
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" memory query widget | grep -q '"results"'
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" memory query widget | grep -q "widget cache"  # inbox is searchable
promote_file="$(ls "$RUNTIME/memory/inbox" | head -1)"
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" memory promote "$promote_file" --json | grep -q '"ok": true'
grep -q "widget cache" "$RUNTIME/memory/claims.jsonl"
# Conductor deterministic verify command: PASS gates finish, FAIL never finishes and ends blocked
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" start demo --prompt "verify pass" --task-id ah-vpass --risk yellow --verify-cmd "true" --json >/dev/null
AGENT_HARNESS_ORCH_DRYRUN_FINISH=1 "$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" orchestrate run ah-vpass --dry-run --json | grep -q '"finished": true'
grep -q '"command": "true"' "$RUNTIME/tasks/ah-vpass/checks.jsonl"  # the real command was executed and recorded
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" start demo --prompt "verify fail" --task-id ah-vfail --risk green --verify-cmd "false" --json >/dev/null
for _ in 1 2 3; do
  # a blocked/unfinished run exits non-zero by design; capture with || true
  vfail_out="$(AGENT_HARNESS_ORCH_DRYRUN_FINISH=1 "$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" orchestrate run ah-vfail --dry-run --max-attempts 1 --json || true)"
  echo "$vfail_out" | grep -q '"finished": true' && { echo "failing verify-cmd must never finish the task" >&2; exit 1; }
done
echo "$vfail_out" | grep -q "retry-blocked"
# --retry-blocked resets and is recorded
AGENT_HARNESS_ORCH_DRYRUN_FINISH=1 "$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" orchestrate run ah-vfail --dry-run --retry-blocked --max-attempts 1 --json >/dev/null 2>&1 || true
grep -q "retry-blocked" "$RUNTIME/tasks/ah-vfail/orchestration/ledger.jsonl"
# Atomic writes leave no temp files behind
if ls "$RUNTIME"/tasks/*/.task.json.tmp-* >/dev/null 2>&1; then echo "atomic write left temp files" >&2; exit 1; fi
# Concurrency: a second conductor cannot acquire a held run lock
run_bound_python - "$RUNTIME" <<'PY'
import sys; sys.path.insert(0, "src")
import agent_harness as a
from pathlib import Path
root = Path(sys.argv[1]); (root/"tasks"/"locktest").mkdir(parents=True, exist_ok=True)
h = a.acquire_run_lock(root, "locktest")
assert h is not None, "lock not acquired"
try:
    a.acquire_run_lock(root, "locktest"); print("BUG: second lock acquired"); sys.exit(1)
except a.HarnessError:
    pass
PY
# Fail-open: a second task in the same repo must not evict the first's gate
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" start demo --prompt "task A" --task-id failopenA --risk green --json >/dev/null
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" start demo --prompt "task B" --task-id failopenB --risk green --json >/dev/null
# The real fail-open fix: BOTH tasks are tracked (task B did not evict task A).
run_bound_python -c "import json,sys; d=json.load(open('$RUNTIME/state/active-tasks.json')); sys.exit(0 if ('failopenA' in d and 'failopenB' in d) else 1)"
# And the stop gate still fires (blocks) with multiple active evidence-less tasks in the repo.
validate_python_identity
fo_out="$(env AGENT_HARNESS_ROOT="$RUNTIME" "$AGENT_HARNESS_PYTHON" "$RUNTIME/hooks/stop-requires-evidence.py" <<JSON || true
{"cwd": "$REPO"}
JSON
)"
echo "$fo_out" | grep -q '"decision": "block"'
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" finish failopenA --force --json >/dev/null
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" finish failopenB --force --json >/dev/null
# retro reports telemetry; clean prunes under retention with a safe dry-run
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" retro --json | grep -q '"tasks_finished"'
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" clean --dry-run --json | grep -q '"dry_run": true'
"$ROOT/bin/agent-harness" --runtime-root "$RUNTIME" clean --dry-run --keep-days 0 --keep-tasks 0 --json | grep -q '"removed"'
test -d "$RUNTIME/tasks/ah-strict"  # dry-run must not delete

SKIP_RUNTIME="$TMP_DIR/runtime-skip-deps"
npm exec --yes --package "$ROOT" -- agent-harness setup --workspace demo-skip --repo "$REPO" --runtime-root "$SKIP_RUNTIME" --shim-dir "$TMP_DIR/bin-skip" --yes --no-register --skip-deps --json >/dev/null
"$TMP_DIR/bin-skip/agent-harness" where --json | grep -q '"installed": true'

FAKE_HOME="$TMP_DIR/home"
FAKE_BIN="$TMP_DIR/fake-bin"
ADAPTER_RUNTIME="$TMP_DIR/runtime-adapters"
POISON_CODEX_HOME="$TMP_DIR/poison-codex-home"
mkdir -p "$FAKE_HOME" "$FAKE_BIN" "$POISON_CODEX_HOME"
printf '%s' 'must remain the only file' > "$POISON_CODEX_HOME/sentinel"
printf '#!/usr/bin/env bash\ncase "$1" in --version) echo codex-test ;; *) exit 0 ;; esac\n' > "$FAKE_BIN/codex"
printf '#!/usr/bin/env bash\nif [ "$1" = "mcp" ]; then exit 0; fi\ncase "$1" in --version) echo claude-test ;; *) exit 0 ;; esac\n' > "$FAKE_BIN/claude"
printf '#!/usr/bin/env bash\ncase "$1" in --version) echo cursor-test ;; *) exit 0 ;; esac\n' > "$FAKE_BIN/cursor-agent"
printf '#!/usr/bin/env bash\ncase "$1" in --version) echo opencode-test ;; *) exit 0 ;; esac\n' > "$FAKE_BIN/opencode"
printf '#!/usr/bin/env bash\ncase "$1" in --version) echo pi-test ;; *) exit 0 ;; esac\n' > "$FAKE_BIN/pi"
chmod +x "$FAKE_BIN/codex" "$FAKE_BIN/claude" "$FAKE_BIN/cursor-agent" "$FAKE_BIN/opencode" "$FAKE_BIN/pi"
env CODEX_HOME="$POISON_CODEX_HOME" /usr/bin/env HOME="$FAKE_HOME" CODEX_HOME="$FAKE_HOME/.codex" XDG_CONFIG_HOME="$FAKE_HOME/.config" PATH="$FAKE_BIN:$PATH" "$ROOT/bin/agent-harness" setup --workspace demo-adapters --repo "$REPO" --runtime-root "$ADAPTER_RUNTIME" --shim-dir "$TMP_DIR/bin-adapters" --yes --json >/dev/null
if find "$POISON_CODEX_HOME" -mindepth 1 ! -name sentinel -print -quit | grep -q .; then
  echo "adapter test escaped its fake Codex home" >&2
  exit 1
fi
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
env CODEX_HOME="$POISON_CODEX_HOME" /usr/bin/env HOME="$FAKE_HOME" CODEX_HOME="$FAKE_HOME/.codex" XDG_CONFIG_HOME="$FAKE_HOME/.config" PATH="$FAKE_BIN:$PATH" "$ROOT/bin/agent-harness" --runtime-root "$ADAPTER_RUNTIME" uninstall --restore-adapters --json >/dev/null
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
