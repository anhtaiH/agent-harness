#!/bin/bash
set -euo pipefail
SCRATCH=/tmp/claude-0/-home-user-agent-harness/cbc35b25-cb62-50a3-9344-ad41a21f17c4/scratchpad
REPO=/home/user/agent-harness/evaluation/v2.0.1-live-ab
mkdir -p "$REPO/results/prbench"
cp -r "$SCRATCH/report/results/prbench-paired"   "$REPO/results/prbench/paired"
cp -r "$SCRATCH/report/results/prbench-analysis" "$REPO/results/prbench/analysis"
cp    "$SCRATCH/report/results/telemetry-prbench.json" "$REPO/results/prbench/telemetry.json"
# blind keys for stage 4 (written by the shipped grader only after judging)
mkdir -p "$REPO/results/blind-keys/prbench"
for d in "$SCRATCH"/judge-private/prbench/shard-*; do
  [[ -f "$d/blind-key.json" ]] && cp "$d/blind-key.json" "$REPO/results/blind-keys/prbench/$(basename "$d").json"
done
echo "copied stage 4 results to repo"
find "$REPO/results/prbench" -type f | sort
