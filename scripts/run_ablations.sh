#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

SEEDS="${SEEDS:-1,2,3,4,5}"
OUT="${OUT:-runs/ablations}"
BENCHMARKS="${BENCHMARKS:-math500 aime uot llmsrbench}"

run () {
  local name="$1" bench="$2"; shift 2
  python -m trope.cli run \
    --config "configs/benchmarks/${bench}.yaml" \
    --seeds "$SEEDS" --out "${OUT}/${bench}/${name}" "$@"
}

for bench in $BENCHMARKS; do
  run tok        "$bench" --set 'operators.levels=["token"]'
  run mut        "$bench" --set 'operators.levels=["mutation"]'
  run cross      "$bench" --set 'operators.levels=["crossover"]'
  run tok_mut    "$bench" --set 'operators.levels=["token","mutation"]'
  run tok_cross  "$bench" --set 'operators.levels=["token","crossover"]'
  run mut_cross  "$bench" --set 'operators.levels=["mutation","crossover"]'
  run full       "$bench"

  run no_parser     "$bench" --set 'run.parser_retries=0'
  run no_heavytail  "$bench" --set 'sampling.alpha=2.0'
  run no_novelty    "$bench" --set 'novelty.threshold=-1e9'
  run no_divctrl    "$bench" --set 'controller.kp=0.0' --set 'controller.ki=0.0'
  run no_rejection  "$bench" --set 'sampling.max_rejections=1'
  run no_mapelites  "$bench" --set 'objective.lambda_coverage=0.0'

  for op in temperature_scaling nucleus_truncation entropy_bounded \
            assumption_violation type_shifting foundational_negation reification \
            structural_transplant categorical_import role_swap goal_pareto_inversion; do
    python - "$op" <<'PY' > /tmp/trope_loo.json
import json, sys
sys.path.insert(0, "src")
from trope.operators.base import catalog
keep = [o.name for o in catalog() if o.name != sys.argv[1]]
print(json.dumps(keep))
PY
    run "loo_${op}" "$bench" --set "operators.enabled=$(cat /tmp/trope_loo.json)"
  done
done

python -m trope.cli tables --runs "$OUT" --out tables --which ablations
