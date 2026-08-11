#!/bin/bash
# Blind judge invocation, called by grade_live_ab.py via --judge-command.
#
# Builds a minimal isolated judge workspace containing ONLY what this judge role is
# allowed to see, then runs the judge inside the same mount-namespace sandbox used for
# runners. This matters: the runner workspace contains per-variant prompt.md files that
# name the variant, so an unsandboxed judge could de-blind itself by reading them.
#
#   technical : output-a.md, output-b.md, case.json, ground-truth.json
#   author    : output-a.md, output-b.md          (final payloads only)
#
# Usage: judge-run.sh <output_a> <output_b> <case_file> <judge_case_file> <judge_output>
set -uo pipefail

OUT_A="$1"; OUT_B="$2"; CASE_FILE="$3"; JUDGE_CASE_FILE="$4"; JUDGE_OUTPUT="$5"

: "${JUDGE_ROLE:?JUDGE_ROLE must be technical or author}"
: "${JUDGE_MODEL:?JUDGE_MODEL must be set}"
: "${JUDGE_EFFORT:?JUDGE_EFFORT must be set}"

WORK="/srv/ab/judgework/${JUDGE_ROLE}/$(printf '%s' "$JUDGE_OUTPUT" | sha256sum | cut -c1-16)"
rm -rf "$WORK"; mkdir -p "$WORK"

cp "$OUT_A" "$WORK/output-a.md"
cp "$OUT_B" "$WORK/output-b.md"
cp "/opt/ab-bin/judge-${JUDGE_ROLE}.md" "$WORK/instructions.md"

if [[ "$JUDGE_ROLE" == technical* ]]; then
  cp "$CASE_FILE" "$WORK/case.json"
  if [[ -f "$JUDGE_CASE_FILE" ]]; then
    cp "$JUDGE_CASE_FILE" "$WORK/ground-truth.json"
  else
    echo "judge-run: missing ground truth: $JUDGE_CASE_FILE" >&2
    exit 65
  fi
fi

DENY=(WebSearch WebFetch Artifact SendUserFile SendMessage Workflow ScheduleWakeup
      PushNotification ShowOnboardingRolePicker SuggestSkills SuggestConnectors
      SuggestPluginInstall DesignSync Monitor ListAgents ReportFindings Skill ToolSearch
      NotebookEdit EnterWorktree ExitWorktree SearchSkills SearchPlugins SearchMcpRegistry
      ListSkills ListPlugins ListConnectors CronCreate CronDelete CronList Agent)

/opt/ab-bin/sandbox-run.sh "$WORK" /bin/bash -c "
  cd '$WORK'
  env -u CLAUDE_CODE_SESSION_ID -u CLAUDE_CODE_REMOTE_SESSION_ID -u CLAUDE_EFFORT \
      -u CLAUDE_CODE_CHILD_SESSION -u CLAUDE_ADDITIONAL_DIRECTORIES \
    claude -p \"\$(cat instructions.md)\" \
      --model '$JUDGE_MODEL' \
      --effort '$JUDGE_EFFORT' \
      --permission-mode acceptEdits \
      --allowedTools Read Write Edit Glob Grep \
      --disallowedTools ${DENY[*]} \
      --safe-mode --strict-mcp-config --no-session-persistence \
      --output-format json
" > "$WORK/telemetry.json" 2> "$WORK/stderr.txt"
rc=$?

if [[ -s "$WORK/verdict.json" ]]; then
  cp "$WORK/verdict.json" "${JUDGE_OUTPUT}.${JUDGE_ROLE}.json"
else
  echo "{\"error\": \"no verdict written\", \"exit\": $rc}" > "${JUDGE_OUTPUT}.${JUDGE_ROLE}.json"
fi
cp "$WORK/telemetry.json" "${JUDGE_OUTPUT}.${JUDGE_ROLE}.telemetry.json" 2>/dev/null

exit $rc
