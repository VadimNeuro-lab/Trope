# Windows equivalent of scripts/smoke.sh.
$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

python -m pytest -q
python -m trope.cli info
python -m trope.cli run --config configs/smoke.yaml --seeds 1,2 --out runs/smoke/trope
foreach ($b in @("greedy", "self_consistency", "tot", "funsearch", "uot")) {
    python -m trope.cli baseline --config configs/smoke.yaml --name $b --out "runs/smoke/$b"
}
python -m trope.cli calibrate --config configs/smoke.yaml --n 200 --out runs/smoke/calibration.json
python -m trope.cli nullcheck --config configs/smoke.yaml --samples 100 --out runs/smoke/nullcheck.json
python -m trope.cli tables --runs runs/smoke --out runs/smoke/tables
Write-Host "smoke run complete"
