"""Determinism, and the source-level discipline that makes it hold."""

from __future__ import annotations

import re
from pathlib import Path

import pytest

from trope.config import Config
from trope.rng import RngTree

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src" / "trope"

BANNED = [
    (
        "numpy-global",
        re.compile(r"np\.random\.(?!default_rng|Generator|PCG64|SeedSequence|BitGenerator)"),
        "np.random global state",
    ),
    (
        "stdlib-random",
        re.compile(r"(?<![\w.])random\.(?!Generator)\w"),
        "the stdlib random module",
    ),
    (
        "builtin-hash",
        re.compile(r"(?<![\w.])hash\("),
        "hash(), which is salted per process",
    ),
]

EXEMPT = {("builtin-hash", "backends/base.py")}


_OPEN_CALL = re.compile(r"(?:(\w+)\.)?(read_text|write_text|open)\(")


def _is_file_open(text: str, match: re.Match[str]) -> bool:
    receiver, name = match.group(1), match.group(2)
    if receiver and receiver[:1].isupper():
        return False
    if name == "open" and receiver is None:
        before = text[max(0, match.start() - 4) : match.start()]
        if before.endswith("def "):
            return False
    return True


def _sources() -> list[Path]:
    return sorted(p for p in SRC.rglob("*.py") if "__pycache__" not in p.parts)


@pytest.mark.parametrize("path", _sources(), ids=lambda p: str(p.name))
def test_no_global_randomness(path: Path) -> None:
    rel = path.relative_to(SRC).as_posix()
    text = path.read_text(encoding="utf-8")
    body = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    for rule, pattern, why in BANNED:
        if (rule, rel) in EXEMPT:
            continue
        match = pattern.search(body)
        assert match is None, f"{rel} uses {why}: {match.group(0)!r}"


@pytest.mark.parametrize("path", _sources(), ids=lambda p: str(p.name))
def test_files_are_opened_as_utf8(path: Path) -> None:
    text = path.read_text(encoding="utf-8")
    for call in re.finditer(_OPEN_CALL, text):
        if not _is_file_open(text, call):
            continue
        tail = text[call.end() : call.end() + 200]
        depth, arg = 1, []
        for ch in tail:
            if ch == "(":
                depth += 1
            elif ch == ")":
                depth -= 1
                if depth == 0:
                    break
            arg.append(ch)
        args = "".join(arg)
        if '"rb"' in args or '"wb"' in args or "'rb'" in args or "'wb'" in args:
            continue
        assert "encoding=" in args, (
            f"{path.name}: {text[call.start() - 20 : call.end() + 40]!r} has no encoding"
        )


def test_named_streams_are_order_independent() -> None:
    a = RngTree(7)
    b = RngTree(7)
    first = a.stream("alpha").random(4).tolist()
    b.stream("beta").random(4)
    b.stream("gamma").random(4)
    assert b.stream("alpha").random(4).tolist() == first


def test_streams_are_independent_across_names() -> None:
    tree = RngTree(11)
    assert tree.stream("x").random(8).tolist() != tree.stream("y").random(8).tolist()


def test_different_seeds_give_different_streams() -> None:
    assert (
        RngTree(1).stream("op").random(8).tolist()
        != RngTree(2).stream("op").random(8).tolist()
    )


def test_stream_is_stable_across_calls() -> None:
    tree = RngTree(3)
    first = tree.stream("s")
    second = tree.stream("s")
    assert first is second


def test_fresh_resets_a_stream() -> None:
    tree = RngTree(3)
    a = tree.stream("s").random(3).tolist()
    b = tree.fresh("s").random(3).tolist()
    assert a == b


def test_search_is_bit_reproducible(tmp_path) -> None:
    from trope.data.synthetic import synthetic_dataset
    from trope.pipeline import Pipeline

    cfg = Config()
    cfg.apply(
        {
            "run.backend": "mock",
            "run.benchmark": "synthetic",
            "run.budget": 16,
            "run.max_problems": 2,
            "distance.encoder": "hash",
        }
    )
    cfg.decoding = Config.load().decoding
    dataset = synthetic_dataset(n=2, seed=0)

    def trace_for(seed: int, tag: str) -> bytes:
        pipeline = Pipeline.build(cfg, problems=dataset)
        pipeline.run(dataset, seed=seed, out_dir=tmp_path / tag)
        return (tmp_path / tag / "trace.jsonl").read_bytes()

    assert trace_for(1, "a") == trace_for(1, "b")
    assert trace_for(1, "a") != trace_for(2, "c")


TEXT_SUFFIXES = {".py", ".txt", ".yaml", ".yml", ".json", ".md", ".sh", ".toml", ".cff"}
SKIP_DIRS = {".git", "__pycache__", ".pytest_cache", ".ruff_cache", "runs", "data"}


def _text_files() -> list[Path]:
    return sorted(
        p
        for p in ROOT.rglob("*")
        if p.is_file()
        and p.suffix in TEXT_SUFFIXES
        and not SKIP_DIRS & set(p.relative_to(ROOT).parts)
    )


@pytest.mark.parametrize("path", _text_files(), ids=lambda p: p.name)
def test_no_crlf_anywhere(path: Path) -> None:
    assert b"\r\n" not in path.read_bytes(), f"{path.relative_to(ROOT)} has CRLF line endings"
