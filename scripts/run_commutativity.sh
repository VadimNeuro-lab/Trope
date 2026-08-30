#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

python -m trope.analysis.commutativity \
  --config "${CONFIG:-configs/smoke.yaml}" \
  --probes "${PROBES:-200}" \
  --seed "${SEED:-1}" \
  --out "${OUT:-runs/commutativity.json}"
