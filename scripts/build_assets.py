"""Rebuild the derived assets from their sources."""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from trope.backends.base import HashEncoder
from trope.config import ASSET_DIR


def frame_documents(frames: dict) -> dict[str, str]:
    docs = {}
    for name, spec in frames.items():
        parts = list(spec.get("keywords", []))
        parts += list(spec.get("sorts", []))
        parts += [a["text"] for a in spec.get("axioms", [])]
        docs[name] = " ".join(parts)
    return docs


def tfidf_vectors(docs: dict[str, str]) -> np.ndarray:
    """Exact TF-IDF over the frame reference corpora, no hashing collisions."""
    names = sorted(docs)
    tokens = {n: docs[n].lower().split() for n in names}
    vocab = sorted({t for toks in tokens.values() for t in toks})
    index = {t: i for i, t in enumerate(vocab)}
    counts = np.zeros((len(names), len(vocab)), dtype=np.float64)
    for i, n in enumerate(names):
        for t in tokens[n]:
            counts[i, index[t]] += 1.0
    df = (counts > 0).sum(axis=0)
    idf = np.log((1.0 + len(names)) / (1.0 + df)) + 1.0
    return counts * idf


def build_matrix(docs: dict[str, str], encoder) -> dict[str, dict[str, float]]:
    names = sorted(docs)
    vectors = (
        tfidf_vectors(docs) if encoder is None else encoder.encode([docs[n] for n in names])
    )
    norms = np.linalg.norm(vectors, axis=1, keepdims=True)
    norms[norms == 0] = 1.0
    unit = vectors / norms
    sim = unit @ unit.T
    if sim.min() < 0:
        sim = (sim + 1.0) / 2.0
    np.fill_diagonal(sim, 1.0)
    return {
        a: {b: round(float(sim[i, j]), 6) for j, b in enumerate(names)}
        for i, a in enumerate(names)
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--encoder", choices=("tfidf", "hash", "sentence"), default="tfidf")
    ap.add_argument("--model", default="sentence-transformers/all-MiniLM-L6-v2")
    ap.add_argument("--dim", type=int, default=256)
    ap.add_argument("--out", default=str(ASSET_DIR / "disciplinary_similarity.json"))
    args = ap.parse_args()

    source = ASSET_DIR / "frames.json"
    raw = source.read_text(encoding="utf-8")
    frames = json.loads(raw)["frames"]

    if args.encoder == "sentence":
        from trope.backends.sentence import SentenceEncoder

        encoder = SentenceEncoder(args.model)
        encoder_id = f"sentence:{args.model}"
    elif args.encoder == "hash":
        encoder = HashEncoder(dim=args.dim)
        encoder_id = f"hash:dim={args.dim}"
    else:
        encoder = None
        encoder_id = "tfidf"

    docs = frame_documents(frames)
    matrix = build_matrix(docs, encoder)
    payload = {
        "_comment": (
            "Pairwise similarity over disciplinary frames, read by categorical "
            "import (rho indexes increasingly distant frames) and by "
            "foundational negation when it needs a nearby frame. Rebuild with "
            "scripts/build_assets.py."
        ),
        "encoder": encoder_id,
        "source": "assets/frames.json",
        "source_sha256": hashlib.sha256(raw.encode("utf-8")).hexdigest(),
        "frames": sorted(matrix),
        "similarity": matrix,
    }
    out = Path(args.out)
    out.write_text(json.dumps(payload, indent=1, sort_keys=True), encoding="utf-8")
    print(f"wrote {out} ({len(matrix)} frames, encoder {encoder_id})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
