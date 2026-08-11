#!/bin/bash
# Launch one sharded A/B stage. Runs the SHIPPED, UNMODIFIED run_live_ab.py once per
# shard in parallel; each shard has its own runner workspace and its own judge-private
# directory. Judge-private lives in the scratchpad tree, which every runner sandbox hides.
#
# Usage: launch-stage.sh <stage_name> <shard_glob_dir> <shards> <runs> <timeout_s>
set -euo pipefail

STAGE="$1"; SHARD_DIR="$2"; SHARDS="$3"; RUNS="$4"; TIMEOUT="$5"

SCRATCH=/tmp/claude-0/-home-user-agent-harness/cbc35b25-cb62-50a3-9344-ad41a21f17c4/scratchpad
PKG="$SCRATCH/handoff/agentic-code-review-live-eval-handoff-v2.0.1/pkg/agentic-code-review-skills-v2.0.1"
WS_ROOT="/srv/ab/live/$STAGE"
JP_ROOT="$SCRATCH/judge-private/$STAGE"
LOG_ROOT="$SCRATCH/logs/$STAGE"

mkdir -p "$WS_ROOT" "$JP_ROOT" "$LOG_ROOT"

# Identical agent command template for BOTH variants. The only thing that differs
# between variants is the content of prompt.md, which run_live_ab.py generates.
CMD='/opt/ab-bin/sandbox-run.sh {workspace} /opt/ab-bin/agent-run.sh {prompt_file} {output_dir}'

for n in $(seq 1 "$SHARDS"); do
  i=$(printf '%02d' "$n")
  shard="$SHARD_DIR/shard-$i.json"
  [[ -f "$shard" ]] || { echo "missing shard: $shard" >&2; exit 66; }
  (
    cd "$PKG"
    python3 evaluation/scripts/run_live_ab.py \
      --evals "$shard" \
      --workspace "$WS_ROOT/shard-$i" \
      --judge-private "$JP_ROOT/shard-$i" \
      --old-command "$CMD" \
      --new-command "$CMD" \
      --runs "$RUNS" \
      --seed $((20260811 + 10#$i)) \
      --timeout "$TIMEOUT" \
      --overwrite
  ) > "$LOG_ROOT/shard-$i.log" 2>&1 &
  echo "launched shard-$i (pid $!)"
done

wait
echo "STAGE $STAGE COMPLETE"
