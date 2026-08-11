#!/bin/bash
# Runner-side agent invocation. Executed INSIDE the per-run mount-namespace
# sandbox, with cwd = the run directory.
#
# Identical for both variants: same model, effort, tool surface, permission
# mode, timeout, and configuration. The ONLY difference between variants is the
# content of prompt.md, which run_live_ab.py generates.
#
# Usage: agent-run.sh <prompt_file> <output_dir>
set -uo pipefail

PROMPT_FILE="$1"
OUTPUT_DIR="$2"
RUN_DIR="$(dirname "$OUTPUT_DIR")"

: "${AB_MODEL:?AB_MODEL must be set}"
: "${AB_EFFORT:?AB_EFFORT must be set}"

mkdir -p "$OUTPUT_DIR"

# Tool surface pinned identically for both variants:
#   allowed  : Read Write Edit Glob Grep Bash Agent TodoWrite
#   denied   : network, publishing, scheduling, messaging, plugin/skill discovery
DENY=(WebSearch WebFetch Artifact SendUserFile SendMessage Workflow
      ScheduleWakeup PushNotification ShowOnboardingRolePicker SuggestSkills
      SuggestConnectors SuggestPluginInstall DesignSync Monitor ListAgents
      ReportFindings Skill ToolSearch NotebookEdit EnterWorktree ExitWorktree
      SearchSkills SearchPlugins SearchMcpRegistry ListSkills ListPlugins
      ListConnectors CronCreate CronDelete CronList)

started_ns=$(date +%s%N)

# Scrub host session identity so each run is a fresh, unlinked context.
env -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_REMOTE_SESSION_ID \
    -u CLAUDE_EFFORT -u CLAUDE_EFFORT_LEVEL \
    -u CLAUDE_CODE_CHILD_SESSION -u CLAUDE_ADDITIONAL_DIRECTORIES \
    -u CLAUDE_CODE_ADDITIONAL_DIRECTORIES_CLAUDE_MD \
    -u CLAUDE_CODE_ENTRYPOINT -u CLAUDE_CODE_BASE_REF \
  claude -p "$(cat "$PROMPT_FILE")" \
    --model "$AB_MODEL" \
    --effort "$AB_EFFORT" \
    --permission-mode acceptEdits \
    --allowedTools Read Write Edit Glob Grep Bash Agent TodoWrite \
    --disallowedTools "${DENY[@]}" \
    --safe-mode \
    --strict-mcp-config \
    --no-session-persistence \
    --output-format json \
    > "$RUN_DIR/telemetry.json" 2> "$RUN_DIR/agent-stderr.txt"

rc=$?
ended_ns=$(date +%s%N)
echo "{\"wrapper_exit\": $rc, \"wall_ms\": $(( (ended_ns - started_ns) / 1000000 ))}" \
  > "$RUN_DIR/wrapper.json"

exit $rc
