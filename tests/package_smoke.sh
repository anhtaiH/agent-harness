#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
ORIGINAL_HOME="$HOME"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

PACKAGE_NAME="$(cd "$ROOT" && npm pack --silent --pack-destination "$WORK")"
PACKAGE="$WORK/$PACKAGE_NAME"
HOME_DIR="$WORK/home-portable-a7"
REPO="$WORK/project-portable-b9"
RUNTIME="$HOME_DIR/.agent-harness/test"
TOOLCHAIN_PROFILE="${AGENT_HARNESS_TEST_TOOLCHAIN:-none}"
REQUIRE_TOOLCHAIN_ACTIONS="${AGENT_HARNESS_REQUIRE_TOOLCHAIN_ACTIONS:-0}"
TEST_REGISTER="${AGENT_HARNESS_TEST_REGISTER:-0}"
FAKE_BIN="$WORK/fake-clients"
mkdir -p "$HOME_DIR" "$REPO" "$FAKE_BIN"
git -C "$REPO" init -q

REGISTER_ARGS=(--no-register)
if [ "$TEST_REGISTER" = "1" ]; then
  REGISTER_ARGS=()
  for client in codex claude cursor-agent; do
    printf '%s\n' '#!/bin/sh' 'if [ "${1:-}" = "--version" ]; then echo fake-client; fi' 'exit 0' >"$FAKE_BIN/$client"
    chmod +x "$FAKE_BIN/$client"
  done
fi

TEST_PATH="$FAKE_BIN:$PATH"
if [ "$REQUIRE_TOOLCHAIN_ACTIONS" = "1" ]; then
  FILTERED_PATH=""
  IFS=':' read -r -a PATH_PARTS <<<"$PATH"
  for part in "${PATH_PARTS[@]}"; do
    if [ "$part" != "$ORIGINAL_HOME/.local/bin" ]; then
      FILTERED_PATH="${FILTERED_PATH:+$FILTERED_PATH:}$part"
    fi
  done
  TEST_PATH="$FAKE_BIN:$FILTERED_PATH"
fi

python3 "$ROOT/tests/portability_gate.py" --package "$PACKAGE" --self-test
SETUP_JSON="$WORK/setup.json"
if ! HOME="$HOME_DIR" PATH="$TEST_PATH" npm_config_ignore_scripts=true npm exec --yes --package "$PACKAGE" -- agent-harness setup --workspace test --repo "$REPO" --runtime-root "$RUNTIME" --shim-dir "$HOME_DIR/.local/bin" --yes "${REGISTER_ARGS[@]}" --toolchain "$TOOLCHAIN_PROFILE" --json >"$SETUP_JSON"; then
  sed -n '1,240p' "$SETUP_JSON" >&2
  exit 1
fi
python3 - "$SETUP_JSON" "$TOOLCHAIN_PROFILE" "$REQUIRE_TOOLCHAIN_ACTIONS" "$TEST_REGISTER" <<'PY'
import json
from pathlib import Path
import sys

data = json.loads(Path(sys.argv[1]).read_text())
assert data["ok"], data
if sys.argv[2] == "full":
    toolchain = data["toolchain"]
    assert not [name for name, state in toolchain["tools"].items() if not state["available"]], toolchain
    if sys.argv[3] == "1":
        assert toolchain["actions"], toolchain
        assert toolchain["owned"], toolchain
if sys.argv[4] == "1":
    adapters = data["user_adapters"]
    for client in ("codex", "claude", "cursor"):
        assert client in adapters and not adapters[client].get("skipped"), adapters
    if sys.argv[2] == "full":
        encoded = json.dumps(adapters)
        for name in ("agent-harness-semble", "agent-harness-serena", "agent-harness-headroom", "agent-harness-context7"):
            assert name in encoded, (name, adapters)
PY
HOME="$HOME_DIR" PATH="$TEST_PATH" "$HOME_DIR/.local/bin/agent-harness" doctor --runtime-root "$RUNTIME" --json >/dev/null
HOME="$HOME_DIR" PATH="$TEST_PATH" npm_config_ignore_scripts=true npm exec --yes --package "$PACKAGE" -- agent-harness setup --workspace test --repo "$REPO" --runtime-root "$RUNTIME" --shim-dir "$HOME_DIR/.local/bin" --yes "${REGISTER_ARGS[@]}" --toolchain "$TOOLCHAIN_PROFILE" --json >/dev/null
touch "$RUNTIME/source/agent-harness/stale-release-marker"
HOME="$HOME_DIR" PATH="$TEST_PATH" npm_config_ignore_scripts=true npm exec --yes --package "$PACKAGE" -- agent-harness upgrade --runtime-root "$RUNTIME" --json >/dev/null
test ! -e "$RUNTIME/source/agent-harness/stale-release-marker"
HOME="$HOME_DIR" PATH="$TEST_PATH" "$HOME_DIR/.local/bin/agent-harness" uninstall --runtime-root "$RUNTIME" --json >/dev/null
test ! -e "$RUNTIME"
if [ "$TEST_REGISTER" = "1" ]; then
  python3 - "$HOME_DIR" <<'PY'
from pathlib import Path
import sys

home = Path(sys.argv[1])
for relative in (".codex", ".claude", ".cursor"):
    root = home / relative
    if root.exists():
        for path in root.rglob("*"):
            if path.is_file():
                assert "agent-harness-" not in path.read_text(errors="ignore"), path
PY
fi
echo "packed randomized-home lifecycle: PASS"
