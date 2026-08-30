#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

SEEDS="${SEEDS:-1,2,3,4,5}"
OUT="${OUT:-runs/sensitivity}"
BENCH="${BENCH:-math500}"
CFG="configs/benchmarks/${BENCH}.yaml"

for alpha in 1.0 1.2 1.4 1.6 1.8 2.0; do
  python -m trope.cli run --config "$CFG" --seeds "$SEEDS" \
    --set "sampling.alpha=${alpha}" --out "${OUT}/${BENCH}/alpha/${alpha}"
done

for k in 16 32 64 128 256; do
  python -m trope.cli run --config "$CFG" --seeds "$SEEDS" \
    --set "run.budget=${k}" --out "${OUT}/${BENCH}/budget/${k}"
done

for ref in Qwen/Qwen2.5-3B-Instruct meta-llama/Llama-3.2-3B-Instruct mistralai/Mistral-7B-Instruct-v0.3; do
  slug="$(echo "$ref" | tr '/' '_')"
  python -m trope.cli run --config "$CFG" --seeds "$SEEDS" \
    --set "run.reference_model=${ref}" --out "${OUT}/${BENCH}/lmref/${slug}"
done

for n in 20 200 2000; do
  python -m trope.cli run --config "$CFG" --seeds "$SEEDS" \
    --set "novelty.corpus_passages=${n}" --out "${OUT}/${BENCH}/corpus/${n}"
done

BACKBONES_SMALL="${BACKBONES_SMALL:-Qwen/Qwen2.5-1.5B-Instruct}"
BACKBONES_DEFAULT="${BACKBONES_DEFAULT:-Qwen/Qwen2.5-7B-Instruct}"
BACKBONES_LARGE="${BACKBONES_LARGE:-Qwen/Qwen2.5-14B-Instruct}"

for backbone in $BACKBONES_SMALL $BACKBONES_DEFAULT $BACKBONES_LARGE; do
  slug="$(echo "$backbone" | tr '/' '_')"
  python -m trope.cli run --config "$CFG" --seeds "$SEEDS" \
    --set "run.backend_model=${backbone}" --out "${OUT}/${BENCH}/backbone/${slug}"
done

python -m trope.cli tables --runs "$OUT" --out tables --which sensitivity
