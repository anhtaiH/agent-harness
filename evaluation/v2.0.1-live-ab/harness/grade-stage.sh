#!/bin/bash
# Grade one stage: blind pairing + mechanical grading + two blind judges, sharded.
#
# grade_live_ab.py is run once per judge role. Both runs use the SAME --seed, so the
# blind A/B assignment is identical across roles, and the blind key is written by the
# shipped grader only after its judge pass completes.
#
# Usage: grade-stage.sh <stage_name> <shards>
set -euo pipefail

STAGE="$1"; SHARDS="$2"

SCRATCH=/tmp/claude-0/-home-user-agent-harness/cbc35b25-cb62-50a3-9344-ad41a21f17c4/scratchpad
PKG="$SCRATCH/handoff/agentic-code-review-live-eval-handoff-v2.0.1/pkg/agentic-code-review-skills-v2.0.1"
WS_ROOT="/srv/ab/live/$STAGE"
JP_ROOT="$SCRATCH/judge-private/$STAGE"
LOG_ROOT="$SCRATCH/logs/$STAGE"
mkdir -p "$LOG_ROOT"

JUDGE_CMD='/opt/ab-bin/judge-run.sh {output_a} {output_b} {case_file} {judge_case_file} {judge_output}'

for n in $(seq 1 "$SHARDS"); do
  i=$(printf '%02d' "$n")
  (
    cd "$PKG"
    for role in technical author; do
      JUDGE_ROLE="$role" \
      JUDGE_MODEL="${JUDGE_MODEL:-claude-opus-5}" \
      JUDGE_EFFORT="${JUDGE_EFFORT:-high}" \
      python3 evaluation/scripts/grade_live_ab.py "$WS_ROOT/shard-$i" \
        --judge-private "$JP_ROOT/shard-$i" \
        --judge-command "$JUDGE_CMD" \
        --seed 20260811 \
        --output "$WS_ROOT/shard-$i/grade-report.json"
    done
  ) > "$LOG_ROOT/grade-shard-$i.log" 2>&1 &
  echo "grading shard-$i (pid $!)"
done

wait
echo "GRADING $STAGE COMPLETE"
