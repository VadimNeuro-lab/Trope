"""Build the ACL supplementary archive."""

from __future__ import annotations

import argparse
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

REQUIRED = [
    "prompts/parser.txt",
    "prompts/generator.txt",
    "schemas/representation.json",
    "configs/decoding.yaml",
]

EXPECTED = [
    "README.md",
    "LICENSE",
    "pyproject.toml",
    "requirements.txt",
    "assets/frames.json",
    "assets/type_similarity.json",
    "assets/disciplinary_similarity.json",
    "assets/descriptor_vocabularies.json",
]

INCLUDE_TREES = ["src", "prompts", "schemas", "configs", "assets", "scripts", "tests"]
EXCLUDE_PARTS = {"__pycache__", ".pytest_cache", ".ruff_cache", ".git"}
EXCLUDE_ROOTS = {"runs", "data"}


def operator_prompt_files() -> list[str]:
    """One prompt file per operator, checked against the live catalog."""
    from trope.operators.base import catalog

    return [f"prompts/operators/{op.name}.txt" for op in catalog()]


def _lf(data: bytes) -> bytes:
    """Normalise CRLF to LF."""
    return data.replace(bytes([13, 10]), bytes([10]))


def collect() -> list[Path]:
    files: list[Path] = []
    for tree in INCLUDE_TREES:
        for path in sorted((ROOT / tree).rglob("*")):
            if not path.is_file():
                continue
            parts = path.relative_to(ROOT).parts
            if EXCLUDE_PARTS & set(parts) or parts[0] in EXCLUDE_ROOTS:
                continue
            if path.suffix in {".pyc", ".pyo"}:
                continue
            files.append(path)
    for name in ("README.md", "LICENSE", "pyproject.toml", "requirements.txt", "Makefile"):
        candidate = ROOT / name
        if candidate.is_file():
            files.append(candidate)
    return sorted(set(files))


def missing_modules(files: list[Path]) -> list[str]:
    """Python modules under `src/` that `collect` would leave out."""
    packaged = set(files)
    return sorted(
        str(path.relative_to(ROOT)).replace("\\", "/")
        for path in (ROOT / "src").rglob("*.py")
        if "__pycache__" not in path.parts and path not in packaged
    )


def check() -> tuple[list[str], list[str]]:
    required = REQUIRED + operator_prompt_files()
    missing_required = [p for p in required if not (ROOT / p).is_file()]
    missing_required += [f"{p} (in src/, dropped by an exclusion rule)"
                         for p in missing_modules(collect())]
    missing_expected = [p for p in EXPECTED if not (ROOT / p).is_file()]
    return missing_required, missing_expected


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="trope_supplementary.zip")
    ap.add_argument("--check-only", action="store_true")
    args = ap.parse_args()

    missing_required, missing_expected = check()
    for path in missing_required:
        print(f"MISSING (promised by path in the paper): {path}", file=sys.stderr)
    for path in missing_expected:
        print(f"missing (expected): {path}", file=sys.stderr)
    if missing_required:
        print(
            "\nRefusing to build: the camera-ready names these files explicitly, so "
            "an archive without them leaves an unmet promise in the published paper.",
            file=sys.stderr,
        )
        return 1
    if args.check_only:
        print("all promised files present")
        return 0

    files = collect()
    out = Path(args.out)
    manifest = {
        "required": REQUIRED + operator_prompt_files(),
        "n_files": len(files),
        "trees": INCLUDE_TREES,
    }
    with zipfile.ZipFile(out, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        for path in files:
            arcname = str(Path("trope") / path.relative_to(ROOT))
            if path.suffix == ".sh":
                zf.writestr(arcname, _lf(path.read_bytes()))
            else:
                zf.write(path, arcname=arcname)
        zf.writestr("trope/ARCHIVE_MANIFEST.json", json.dumps(manifest, indent=2))
    size = out.stat().st_size / 1e6
    print(f"wrote {out} ({len(files)} files, {size:.1f} MB)")
    if missing_expected:
        print(f"note: {len(missing_expected)} expected files were absent, see above")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
