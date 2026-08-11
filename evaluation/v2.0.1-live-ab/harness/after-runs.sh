#!/bin/bash
# Wait for both run stages, then grade both (blind pairing + two sandboxed judges).
set -uo pipefail
SCRATCH=/tmp/claude-0/-home-user-agent-harness/cbc35b25-cb62-50a3-9344-ad41a21f17c4/scratchpad

until grep -q "STAGE semantic COMPLETE" "$SCRATCH/logs/semantic-launcher.log" 2>/dev/null \
   && grep -q "STAGE policy COMPLETE" "$SCRATCH/logs/policy-launcher.log" 2>/dev/null; do
  sleep 30
done
echo "[$(date -u +%H:%M:%S)] both run stages complete; starting grading"

export JUDGE_MODEL=claude-opus-5 JUDGE_EFFORT=high
/opt/ab-bin/grade-stage.sh semantic 5 > "$SCRATCH/logs/grade-semantic.log" 2>&1
echo "[$(date -u +%H:%M:%S)] semantic grading done"
/opt/ab-bin/grade-stage.sh policy 5 > "$SCRATCH/logs/grade-policy.log" 2>&1
echo "[$(date -u +%H:%M:%S)] policy grading done"
echo "ALL GRADING COMPLETE"
