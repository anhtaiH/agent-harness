#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)"
WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

PACKAGE_NAME="$(cd "$ROOT" && npm pack --silent --pack-destination "$WORK")"
PACKAGE="$WORK/$PACKAGE_NAME"
HOME_DIR="$WORK/home-portable-a7"
REPO="$WORK/project-portable-b9"
RUNTIME="$HOME_DIR/.agent-harness/test"
TOOLCHAIN_PROFILE="${AGENT_HARNESS_TEST_TOOLCHAIN:-none}"
mkdir -p "$HOME_DIR" "$REPO"
git -C "$REPO" init -q

python3 "$ROOT/tests/portability_gate.py" --package "$PACKAGE" --self-test
HOME="$HOME_DIR" npm_config_ignore_scripts=true npm exec --yes --package "$PACKAGE" -- agent-harness setup --workspace test --repo "$REPO" --runtime-root "$RUNTIME" --shim-dir "$HOME_DIR/.local/bin" --yes --no-register --toolchain "$TOOLCHAIN_PROFILE" --json >/dev/null
HOME="$HOME_DIR" "$HOME_DIR/.local/bin/agent-harness" doctor --runtime-root "$RUNTIME" --json >/dev/null
HOME="$HOME_DIR" npm_config_ignore_scripts=true npm exec --yes --package "$PACKAGE" -- agent-harness setup --workspace test --repo "$REPO" --runtime-root "$RUNTIME" --shim-dir "$HOME_DIR/.local/bin" --yes --no-register --toolchain "$TOOLCHAIN_PROFILE" --json >/dev/null
HOME="$HOME_DIR" "$HOME_DIR/.local/bin/agent-harness" upgrade --runtime-root "$RUNTIME" --json >/dev/null
HOME="$HOME_DIR" "$HOME_DIR/.local/bin/agent-harness" uninstall --runtime-root "$RUNTIME" --json >/dev/null
test ! -e "$RUNTIME"
echo "packed randomized-home lifecycle: PASS"
