#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."

CONFIG="${CONFIG:-configs/paper.yaml}"
N="${N:-1000}"

python -m trope.cli calibrate --config "$CONFIG" --n "$N" --out runs/calibration.json
python -m trope.cli nullcheck --config "$CONFIG" --samples 1000 --out runs/nullcheck.json
python -m trope.cli figures --runs runs --out figures
