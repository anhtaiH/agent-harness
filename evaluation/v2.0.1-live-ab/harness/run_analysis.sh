#!/bin/bash
# Run the shipped paired non-inferiority analyzer for every predeclared metric.
#
# Margins and directions come from PREDECLARATION.md, frozen before inference.
# Count-valued metrics are NOT passed to the binary analyzer; they are reported
# descriptively only.
#
# Usage: run_analysis.sh <paired_csv_dir> <out_dir> [golden|prbench]
set -euo pipefail

CSV_DIR="$1"; OUT="$2"; FAMILY="${3:-golden}"
SCRATCH=/tmp/claude-0/-home-user-agent-harness/cbc35b25-cb62-50a3-9344-ad41a21f17c4/scratchpad
PKG="$SCRATCH/handoff/agentic-code-review-live-eval-handoff-v2.0.1/pkg/agentic-code-review-skills-v2.0.1"
ANALYZE="$PKG/evaluation/scripts/analyze_paired_noninferiority.py"

mkdir -p "$OUT"

if [[ "$FAMILY" == "golden" ]]; then
  # metric | direction | margin (percentage points expressed as a proportion)
  SPECS=(
    "blocker_recall|higher|0.05"
    "false_blocker|lower|0.02"
    "decision_accuracy|higher|0.05"
    "author_preference|higher|0.10"
    "readability_fail|lower|0.05"
    "technical_preference|higher|0.10"
    "useful_secondary|higher|0.05"
    "output_contract_pass|higher|0.05"
  )
else
  SPECS=(
    "human_recall|higher|0.05"
    "any_fabricated|lower|0.02"
    "author_preference|higher|0.10"
    "readability_fail|lower|0.05"
    "technical_preference|higher|0.10"
    "output_contract_pass|higher|0.05"
  )
fi

for spec in "${SPECS[@]}"; do
  IFS='|' read -r metric direction margin <<< "$spec"
  csv="$CSV_DIR/paired_${metric}.csv"
  if [[ ! -s "$csv" ]] || [[ $(wc -l < "$csv") -le 1 ]]; then
    echo "SKIP $metric (no paired rows)"
    continue
  fi
  python3 "$ANALYZE" "$csv" \
    --metric-name "$metric" \
    --direction "$direction" \
    --margin "$margin" \
    --output "$OUT/${metric}.json" > /dev/null
  python3 - "$OUT/${metric}.json" <<'PY'
import json,sys
d=json.load(open(sys.argv[1]))
lo,hi=d["confidence_interval_95"]
print(f'{d["metric"]:24} n={d["paired_n"]:3}  ctrl={d["control_rate"]:.3f}  trt={d["treatment_rate"]:.3f}  '
      f'effect={d["effect"]:+.3f}  CI=[{lo:+.3f},{hi:+.3f}]  margin={d["noninferiority_margin"]}  '
      f'-> {d["decision"].upper()}  (p={d["exact_two_sided_sign_mcnemar_p"]:.4f})')
PY
done
