#!/bin/bash
# Per-run OS sandbox for live A/B agent runs.
#
# Provides a mount-namespace boundary so a runner agent can read ONLY its own
# run directory plus the system toolchain. The eval source set, judge-private
# ground truth, blind mappings, sibling variant outputs, and every other run
# directory are removed from the namespace entirely -- they are not merely
# permission-denied, they do not exist in the runner's filesystem view.
#
# The run directory is re-bound at its ORIGINAL absolute path so that absolute
# paths embedded in the generated prompt (e.g. the runtime skill location)
# resolve identically inside and outside the sandbox. No prompt rewriting.
#
# Usage: sandbox-run.sh <run_dir> <command...>
set -euo pipefail

RUN_DIR="$(readlink -f "$1")"; shift

if [[ ! -d "$RUN_DIR" ]]; then
  echo "sandbox: run dir missing: $RUN_DIR" >&2
  exit 64
fi

export SANDBOX_RUN_DIR="$RUN_DIR"
export SANDBOX_CMD_B64="$(printf '%s\0' "$@" | base64 -w0)"

exec unshare --mount --propagation private -- /bin/bash -euo pipefail -c '
  # 1. Stage this run directory, BEFORE its parent tree is hidden.
  mkdir -p /mnt/.stage
  mount --bind "$SANDBOX_RUN_DIR" /mnt/.stage

  # 2. Erase every sensitive tree from this namespace.
  #    /srv/ab       : all other runs + the sibling variant of the same case
  #    /tmp/claude-0 : eval source package, judge-private ground truth, blind map
  #    /home/user    : host repository/workspace
  #    /root/.claude : host skills, hooks, projects, session transcripts
  for target in /srv/ab /tmp/claude-0 /home/user /root/.claude; do
    [[ -d "$target" ]] && mount -t tmpfs -o size=8m,mode=0755 tmpfs "$target"
  done

  # 3. Restore ONLY this run directory, at its original absolute path.
  mkdir -p "$SANDBOX_RUN_DIR"
  mount --bind /mnt/.stage "$SANDBOX_RUN_DIR"
  umount /mnt/.stage

  # 4. Private config/home for this run only (fresh context, no persistence,
  #    no host settings, no host skills).
  mkdir -p "$SANDBOX_RUN_DIR/.agent-config"
  export CLAUDE_CONFIG_DIR="$SANDBOX_RUN_DIR/.agent-config"
  export HOME="$SANDBOX_RUN_DIR"

  cd "$SANDBOX_RUN_DIR"

  # 5. Drop all capabilities: uid 0 without CAP_SYS_ADMIN cannot remount, and
  #    without CAP_DAC_OVERRIDE/CAP_DAC_READ_SEARCH is subject to normal DAC.
  mapfile -d "" -t argv < <(printf %s "$SANDBOX_CMD_B64" | base64 -d)
  exec setpriv --no-new-privs --bounding-set=-all -- "${argv[@]}"
'
