#!/bin/bash
set -uo pipefail
SCRATCH=/tmp/claude-0/-home-user-agent-harness/cbc35b25-cb62-50a3-9344-ad41a21f17c4/scratchpad
until grep -q "STAGE4 RECOVERED" "$SCRATCH/logs/stage4-recover.log" 2>/dev/null; do
  pgrep -f stage4-recover.sh >/dev/null 2>&1 || { echo "recover exited early"; break; }
  sleep 30
done
echo "[$(date -u +%H:%M:%S)] assembling stage 4"
python3 /opt/ab-bin/assemble_paired.py \
  --workspace-glob '/srv/ab/live/prbench/shard-*' \
  --judge-private-glob "$SCRATCH/judge-private/prbench/shard-*" \
  --technical-role technical-prbench --metrics prbench \
  --out "$SCRATCH/report/results/prbench-paired" > "$SCRATCH/logs/prbench-assemble.log" 2>&1
echo "[$(date -u +%H:%M:%S)] analyzing stage 4"
/opt/ab-bin/run_analysis.sh "$SCRATCH/report/results/prbench-paired" \
  "$SCRATCH/report/results/prbench-analysis" prbench > "$SCRATCH/logs/prbench-analysis.log" 2>&1
python3 /opt/ab-bin/summarize_telemetry.py --stage prbench \
  --out "$SCRATCH/report/results/telemetry-prbench.json" > /dev/null 2>&1
echo "STAGE4 FINALIZED"
