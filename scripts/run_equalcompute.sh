#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

MAIN="${MAIN:-runs/main}"
OUT="${OUT:-runs/equalcompute}"
SEEDS="${SEEDS:-1,2,3,4,5}"

for pair in "math500:self_consistency" "aime:self_consistency" "uot:uot"; do
  bench="${pair%%:*}"; baseline="${pair##*:}"
  effk="$(python -m trope.analysis.equalcompute --runs "$MAIN" \
            --benchmark "$bench" --baseline "$baseline")"
  echo "=== $bench / $baseline at effective K=${effk} ==="
  python -m trope.cli baseline \
    --config "configs/benchmarks/${bench}.yaml" \
    --name "$baseline" --seeds "$SEEDS" \
    --set "run.budget=${effk}" \
    --out "${OUT}/${bench}/${baseline}"
done

python -m trope.cli tables --runs "$OUT" --out tables --which equalcompute
