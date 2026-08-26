#!/usr/bin/env bash
# Local verification authority for agent-harness.
#
# CI is best-effort; this script is the release gate. It reproduces the CI
# recipe locally and adds checks CI cannot be trusted to run:
#   1. Syntax checks across every shipped language surface.
#   2. Full test suite from a FRESH CLONE of HEAD (catches untracked-file
#      dependence and packaging gaps).
#   3. A second suite run under a symlinked, trailing-slash TMPDIR that
#      simulates macOS's /var -> /private/var + trailing-slash behavior.
#   4. Gate verification (verify-gates) from the source tree.
#
# Usage: ./tests/preflight.sh [--skip-macos-sim]
set -euo pipefail
trap 'echo "PREFLIGHT FAILED at ${BASH_SOURCE[0]}:${LINENO}: ${BASH_COMMAND}" >&2' ERR

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
TMP_BASE="${TMPDIR:-/tmp}"
WORK="${TMP_BASE%/}/agent-harness-preflight-$$"
SKIP_MACOS_SIM=0
[ "${1:-}" = "--skip-macos-sim" ] && SKIP_MACOS_SIM=1

cleanup() { rm -rf "$WORK"; }
trap cleanup EXIT
mkdir -p "$WORK"

step() { printf '\n== %s ==\n' "$1"; }

step "1/5 syntax checks"
"$AGENT_HARNESS_PYTHON" -m py_compile "$ROOT/src/agent_harness.py" "$ROOT"/runtime/hooks/*.py
node --check "$ROOT/runtime/mcp/server.mjs"
node --check "$ROOT/runtime/mcp/opencode-plugin.mjs"
for script in "$ROOT"/runtime/bin/ah-* "$ROOT/runtime/bin/env-scrub.sh" "$ROOT"/tests/*.sh; do
  bash -n "$script"
done
echo "syntax ok"

cmp -s "$ROOT/package-lock.json" "$ROOT/npm-shrinkwrap.json" || {
  echo "package-lock.json and npm-shrinkwrap.json diverged" >&2
  exit 1
}
(cd "$ROOT" && npm audit --omit=dev --audit-level=low >/dev/null)

step "2/5 gate verification (source tree)"
"$ROOT/bin/agent-harness" verify-gates --json | grep -q '"ok": true'
"$AGENT_HARNESS_PYTHON" "$ROOT/tests/portability_gate.py" --tree "$ROOT" --self-test
"$ROOT/tests/package_smoke.sh"
echo "gates ok"

step "3/5 fresh clone"
git -C "$ROOT" rev-parse --verify HEAD >/dev/null
CLONE="$WORK/clone"
git clone --quiet --local --no-hardlinks "$ROOT" "$CLONE"
echo "clone at $CLONE ($(git -C "$CLONE" rev-parse --short HEAD))"

step "4/5 full suite from the fresh clone"
(cd "$CLONE" && npm ci --silent --ignore-scripts >/dev/null && ./tests/run.sh >"$WORK/suite.log" 2>&1) || {
  tail -30 "$WORK/suite.log" >&2
  exit 1
}
tail -1 "$WORK/suite.log"

if [ "$SKIP_MACOS_SIM" -eq 1 ]; then
  step "5/5 macOS path simulation (skipped by flag)"
else
  step "5/5 full suite under simulated macOS TMPDIR (symlinked base + trailing slash)"
  mkdir -p "$WORK/private/realtmp"
  ln -s "$WORK/private/realtmp" "$WORK/tmplink"
  (cd "$CLONE" && TMPDIR="$WORK/tmplink/" ./tests/run.sh >"$WORK/suite-macsim.log" 2>&1) || {
    tail -30 "$WORK/suite-macsim.log" >&2
    exit 1
  }
  tail -1 "$WORK/suite-macsim.log"
fi

echo
echo "preflight passed: syntax, gates, fresh-clone suite$( [ "$SKIP_MACOS_SIM" -eq 1 ] || printf ', macOS-sim suite' )"
