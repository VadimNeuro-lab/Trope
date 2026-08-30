#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

CONFIG="${CONFIG:-configs/paper.yaml}"
SEEDS="${SEEDS:-1,2,3,4,5}"
OUT="${OUT:-runs/main}"
BENCHMARKS="${BENCHMARKS:-math500 aime usamo livecodebench humaneval_plus noveltybench creativityprism uot llmsrbench researchbench}"
BASELINES="${BASELINES:-greedy temp_0.7 temp_1.0 temp_1.2 top_p min_p top_h eta self_consistency tot verbalized_sampling funsearch promptbreeder evoprompt eureka uot}"

for bench in $BENCHMARKS; do
  echo "=== $bench: TROPE ==="
  python -m trope.cli run \
    --config "configs/benchmarks/${bench}.yaml" \
    --seeds "$SEEDS" \
    --out "${OUT}/${bench}/trope"

  for baseline in $BASELINES; do
    echo "=== $bench: $baseline ==="
    python -m trope.cli baseline \
      --config "configs/benchmarks/${bench}.yaml" \
      --name "$baseline" \
      --seeds "$SEEDS" \
      --out "${OUT}/${bench}/${baseline}" || {
        echo "skipped ${baseline} on ${bench} (task-incompatible or failed)"
      }
  done
done

python -m trope.cli tables --runs "$OUT" --out tables
python -m trope.cli figures --runs "$OUT" --out figures
