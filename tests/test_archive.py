"""MAP-Elites archive and the per-benchmark behavioral descriptors."""

from __future__ import annotations

import itertools
import math

import numpy as np
import pytest

from trope.archive import Archive
from trope.backends.base import CallCounter, Generation, MeteredBackend
from trope.backends.mock import MockBackend
from trope.descriptors import (
    EmbeddingDescriptor,
    GridDescriptor,
    KeywordTagger,
    LLMTagger,
    TagAxis,
    available,
    axis_for_vocabulary,
    flat_index,
    get_descriptor,
    is_recursive,
    parse_tag,
    tag_vocabulary,
)
from trope.types import Candidate, Goal, Representation

PAPER_GRID: dict[str, int] = {
    "math500": 48,
    "aime": 36,
    "usamo": 25,
    "livecodebench": 64,
    "humaneval_plus": 40,
    "noveltybench": 80,
    "creativityprism": 60,
    "uot": 30,
    "llmsrbench": 56,
    "researchbench": 72,
}


def rep(frame: str = "algebra") -> Representation:
    return Representation(goal=Goal("solve it"), frame=frame)


def candidate(
    text: str, *, verdict: float = 1.0, novelty: float = 1.0, iteration: int = 0
) -> Candidate:
    return Candidate(
        text=text,
        representation=rep(),
        operator="test_op",
        radicality=0.5,
        novelty=novelty,
        verdict=verdict,
        iteration=iteration,
    )


class ParsedDescriptor:
    """delta reads its cell out of the candidate text, so a test can choose it."""

    name = "parsed"
    shape = (4, 5)
    n_cells = 20

    def __call__(self, candidate_text: str, representation=None) -> tuple[int, ...]:
        i, j = candidate_text.split()[0].split(":")[1:]
        return (int(i), int(j))

    def cell_index(self, desc) -> int:
        return flat_index(desc, self.shape)


def cell_text(i: int, j: int) -> str:
    return f"cell:{i}:{j} a solution"


class ScriptedBackend:
    """Returns the queued answers and records how each call was tagged."""

    name = "scripted"

    def __init__(self, answers) -> None:
        self.answers = list(answers)
        self.prompts: list[str] = []
        self.roles: list[str] = []

    def generate(self, prompt, params, *, seed=None, role="generator") -> Generation:
        self.prompts.append(prompt)
        self.roles.append(role)
        text = self.answers.pop(0) if self.answers else ""
        return Generation(text=text, meta={"role": role})


def test_grid_sizes_match_the_paper_table():
    assert set(available()) - {"synthetic"} == set(PAPER_GRID)
    for benchmark, m in PAPER_GRID.items():
        descriptor = get_descriptor(benchmark)
        assert math.prod(descriptor.shape) == m, benchmark
        assert descriptor.n_cells == m, benchmark


def test_cell_index_enumerates_the_grid_exactly_once():
    for benchmark in ("math500", "creativityprism", "usamo"):
        descriptor = get_descriptor(benchmark)
        indices = [
            descriptor.cell_index(cell)
            for cell in itertools.product(*(range(n) for n in descriptor.shape))
        ]
        assert sorted(indices) == list(range(descriptor.n_cells)), benchmark


def test_flat_index_rejects_out_of_range_cells():
    descriptor = get_descriptor("math500")
    with pytest.raises(ValueError):
        descriptor.cell_index((12, 0))
    with pytest.raises(ValueError):
        descriptor.cell_index((1, 1, 1))


def test_descriptors_are_deterministic_and_in_range():
    text = (
        "Working in the combinatorics frame.\n"
        "Step 1: count the arrangements with a binomial coefficient.\n"
        "def solve(n):\n    for i in range(n):\n        if i % 2:\n            return i\n"
    )
    for benchmark in PAPER_GRID:
        if benchmark == "usamo":
            continue
        descriptor = get_descriptor(benchmark)
        first = descriptor(text, rep("combinatorics"))
        second = get_descriptor(benchmark)(text, rep("combinatorics"))
        assert first == second, benchmark
        assert len(first) == len(descriptor.shape)
        assert all(0 <= v < n for v, n in zip(first, descriptor.shape, strict=False)), benchmark
        assert 0 <= descriptor.cell_index(first) < descriptor.n_cells


def test_keyword_tagger_picks_the_matching_tag():
    vocab = tag_vocabulary("math_method")
    axis = TagAxis("math_method")
    assert axis("the remainder is divisible by a prime modulo n", None) == vocab.index(
        "number-theoretic"
    )
    assert axis("by induction on n, the base case holds", None) == vocab.index("inductive")


def test_tagger_fallback_stays_inside_the_closed_vocabulary():
    axis = TagAxis("math_method")
    for text in ("", "qqqq wwww eeee", "..."):
        assert 0 <= axis(text, None) < axis.size


def test_injected_tagger_overrides_the_keyword_table():
    calls: list[tuple[str, tuple[str, ...]]] = []

    def tagger(text: str, vocabulary):
        calls.append((text, tuple(vocabulary)))
        return "extremal"

    descriptor = get_descriptor("math500", tagger=tagger)
    assert descriptor("the remainder modulo a prime", None)[0] == tag_vocabulary(
        "math_method"
    ).index("extremal")
    assert calls and calls[0][1] == tag_vocabulary("math_method")


def test_injected_tagger_must_return_a_vocabulary_member():
    descriptor = get_descriptor("math500", tagger=lambda text, vocab: "not-a-tag")
    with pytest.raises(ValueError, match="closed"):
        descriptor("anything", None)


def test_parse_tag_tolerates_the_packaging_and_nothing_else():
    vocab = tag_vocabulary("math_method")
    assert parse_tag("number-theoretic", vocab) == "number-theoretic"
    assert parse_tag(' "Number Theoretic." ', vocab) == "number-theoretic"
    assert parse_tag("Label: inductive\n", vocab) == "inductive"
    assert parse_tag("I would call this casework, myself", vocab) == "casework"
    assert parse_tag("either algebraic or geometric", vocab) is None
    assert parse_tag("stochastic-differential", vocab) is None
    assert parse_tag("", vocab) is None


def test_llm_tagger_uses_an_in_vocabulary_answer():
    """Appendix: an additional LLM call under a closed-vocabulary instruction."""
    vocab = tag_vocabulary("math_method")
    backend = ScriptedBackend(["extremal"])
    tagger = LLMTagger(backend)
    descriptor = get_descriptor("math500", tagger=tagger)
    assert descriptor("the remainder modulo a prime", None)[0] == vocab.index("extremal")
    assert backend.roles == ["tagger"]
    prompt = backend.prompts[0]
    assert all(tag in prompt for tag in vocab)
    assert "the remainder modulo a prime" in prompt
    assert tagger.stats() == {"calls": 1, "retries": 0, "fallbacks": 0, "cached": 1}


def test_llm_tagger_retries_once_and_then_falls_back_to_keywords():
    vocab = tag_vocabulary("math_method")
    backend = ScriptedBackend(["banana", "still banana"])
    tagger = LLMTagger(backend)
    text = "the remainder is divisible by a prime modulo n"
    assert tagger(text, vocab) == "number-theoretic"
    assert tagger(text, vocab) == KeywordTagger("math_method")(text)
    assert backend.roles == ["tagger", "tagger"]
    assert "banana" in backend.prompts[1]
    assert tagger.stats() == {"calls": 2, "retries": 1, "fallbacks": 1, "cached": 1}


def test_llm_tagger_caches_by_axis_and_text():
    backend = ScriptedBackend(["extremal", "invariant", "physics", "geometric"])
    tagger = LLMTagger(backend)
    method, field = tag_vocabulary("math_method"), tag_vocabulary("field")
    assert tagger("a proof", method) == "extremal"
    assert tagger("a proof", method) == "extremal"
    assert tagger.calls == 1
    assert tagger("another proof", method) == "invariant"
    assert tagger("a proof", field) == "physics"
    assert (tagger.calls, tagger.cache_size) == (3, 3)
    assert axis_for_vocabulary(method) != axis_for_vocabulary(field)


def test_llm_tagger_is_metered_under_its_own_role():
    """Tagging is not a generator call: the matched budget must not move."""
    counter = CallCounter()
    backend = MeteredBackend(ScriptedBackend(["extremal"]), counter, budget=0)
    LLMTagger(backend)("a proof", tag_vocabulary("math_method"))
    assert counter.counts == {"tagger": 1}
    assert counter.get("generator") == 0


def test_llm_tagger_against_the_mock_backend_stays_in_the_vocabulary():
    """End to end offline: whatever the model answers, the axis gets a member."""
    vocab = tag_vocabulary("alg_class")
    tagger = LLMTagger(MockBackend(seed=0))
    descriptor = get_descriptor("livecodebench", tagger=tagger)
    texts = [
        "```python\ndef f(x):\n    return sorted(x)\n```",
        "```python\ndef f(n):\n    return f(n - 1) if n else 0\n```",
        "a dynamic programming table over prefixes",
    ]
    cells = [descriptor(t, None) for t in texts]
    assert all(0 <= cell[0] < len(vocab) for cell in cells)
    assert tagger.cache_size == len(texts)
    assert tagger.calls == len(texts) + tagger.retries
    assert tagger.fallbacks <= tagger.retries <= len(texts)
    assert [descriptor(t, None) for t in texts] == cells


def test_grid_sizes_are_unchanged_by_the_llm_tagger():
    tagger = LLMTagger(ScriptedBackend([]))
    for benchmark, m in PAPER_GRID.items():
        descriptor = get_descriptor(benchmark, tagger=tagger)
        assert descriptor.n_cells == m, benchmark
        assert math.prod(descriptor.shape) == m, benchmark


def test_length_and_depth_axes_separate_short_from_long():
    descriptor = get_descriptor("math500")
    short = descriptor("brief.", None)[1]
    long = descriptor("word " * 500, None)[1]
    assert short == 0
    assert long == descriptor.shape[1] - 1


def test_control_flow_signature_is_a_bit_pattern():
    descriptor = get_descriptor("humaneval_plus")
    plain = "```python\ndef f(x):\n    return x + 1\n```"
    looped = "```python\ndef f(x):\n    for i in x:\n        pass\n    return x\n```"
    branched = "```python\ndef f(x):\n    if x:\n        return 1\n    return 0\n```"
    recursive = "```python\ndef f(x):\n    return f(x - 1)\n```"
    assert descriptor(plain, None)[0] == 0
    assert descriptor(looped, None)[0] == 1
    assert descriptor(branched, None)[0] == 2
    assert descriptor(recursive, None)[0] == 4


def test_recursion_is_a_self_call_not_any_call():
    helper = "def helper(x):\n    return x + 1\n\ndef main(y):\n    return helper(y)\n"
    driver = "def solve(n):\n    return n * 2\n\nprint(solve(3))\n"
    self_call = "def f(n):\n    return 1 if n < 2 else f(n - 1)\n"
    assert is_recursive(helper) is False
    assert is_recursive(driver) is False
    assert is_recursive(self_call) is True
    truncated = "def f(n):\n    if n:\n        return f(n - 1) +\n"
    assert is_recursive(truncated) is True
    assert is_recursive("def g(n):\n    return n +\n\ng(2)\n") is False


def test_frame_deviation_axis_reads_the_representation():
    descriptor = get_descriptor("uot")
    on_frame = "group ring field polynomial ideal homomorphism commutative identity element"
    off_frame = "an unrelated musing about weather patterns"
    assert descriptor(on_frame, rep("algebra"))[0] < descriptor(off_frame, rep("algebra"))[0]
    assert descriptor(on_frame, None)[0] == descriptor.shape[0] - 1


def test_embedding_descriptor_is_reproducible_across_instances():
    texts = [f"proof by {w} of the inequality on the incircle" for w in "abcdefghij"]
    first = EmbeddingDescriptor("usamo", bins=5, components=2)
    second = EmbeddingDescriptor("usamo", bins=5, components=2)
    cells_a = [first(t) for t in texts]
    cells_b = [second(t) for t in texts]
    assert cells_a == cells_b
    assert first.n_seen == len(texts)
    assert all(0 <= v < 5 for cell in cells_a for v in cell)


def test_embedding_descriptor_pins_the_component_signs():
    """An unpinned SVD may flip a component between refits and relabel the grid."""
    descriptor = EmbeddingDescriptor("usamo", bins=5, components=2, refit_every=1)
    for i in range(12):
        descriptor(f"a proof strategy of kind {i % 4} using an auxiliary construction")
    basis = descriptor._basis
    assert basis is not None
    for column in basis.T:
        assert column[int(np.argmax(np.abs(column)))] > 0


def test_embedding_descriptor_uses_the_middle_cell_before_it_can_fit():
    descriptor = EmbeddingDescriptor("usamo", bins=5, components=2, min_fit=4)
    assert descriptor("first candidate") == (2, 2)


def test_grid_descriptor_shape_follows_its_axes():
    descriptor = GridDescriptor("custom", (TagAxis("field"), TagAxis("math_method")))
    assert descriptor.shape == (6, 12)
    assert descriptor.n_cells == 72


def test_candidate_below_the_novelty_threshold_is_rejected():
    archive = Archive(ParsedDescriptor(), novelty_threshold=0.5)
    cand = candidate(cell_text(0, 0), novelty=0.49)
    result = archive.insert(cand)
    assert (result.inserted, result.reason, result.cell) == (False, "novelty", None)
    assert cand.descriptor == ()
    assert len(archive) == 0
    assert archive.insert(candidate(cell_text(0, 0), novelty=0.5)).inserted


def test_candidate_failing_verification_is_rejected():
    archive = Archive(ParsedDescriptor(), novelty_threshold=0.0)
    result = archive.insert(candidate(cell_text(1, 1), verdict=0.0))
    assert (result.inserted, result.reason) == (False, "verified")
    assert archive.coverage() == 0.0


def test_admission_is_any_positive_verdict():
    """Algorithm 1 line 11: `V_P(s) > 0`, whatever the verifier supplies."""
    archive = Archive(ParsedDescriptor(), novelty_threshold=0.0)
    assert archive.insert(candidate(cell_text(0, 0), verdict=0.05)).inserted
    assert archive.insert(candidate(cell_text(0, 1), verdict=0.0)).reason == "verified"
    assert archive.coverage() == pytest.approx(1 / archive.descriptor.n_cells)


def test_a_judged_distribution_fills_the_grid_under_the_printed_rule():
    """What `V > 0` means on a graded verifier, measured rather than asserted."""
    descriptor = ParsedDescriptor()
    archive = Archive(descriptor, novelty_threshold=0.0)
    rng = np.random.default_rng(19)
    scored: set[tuple[int, int]] = set()
    for t in range(30):
        i, j = int(rng.integers(4)), int(rng.integers(5))
        verdict = 0.0 if rng.random() < 0.25 else float(rng.beta(1.5, 4.0))
        archive.insert(candidate(cell_text(i, j), verdict=verdict, iteration=t))
        if verdict > 0.0:
            scored.add((i, j))
    assert len(archive) == len(scored) > 4
    assert archive.coverage() == pytest.approx(len(scored) / descriptor.n_cells)


def test_a_zero_verdict_is_the_only_one_refused():
    archive = Archive(ParsedDescriptor(), novelty_threshold=0.0)
    assert archive.insert(candidate(cell_text(0, 0), verdict=1e-12)).inserted
    assert archive.insert(candidate(cell_text(0, 1), verdict=-0.5)).reason == "verified"


def test_replacement_keeps_the_higher_verdict():
    archive = Archive(ParsedDescriptor(), novelty_threshold=0.0)
    weak = candidate(cell_text(2, 3), verdict=0.6, novelty=0.9, iteration=1)
    strong = candidate(cell_text(2, 3), verdict=0.9, novelty=0.1, iteration=2)
    assert archive.insert(weak).inserted
    result = archive.insert(strong)
    assert (result.inserted, result.replaced, result.cell) == (True, True, (2, 3))
    assert archive.cells()[(2, 3)].candidate is strong
    assert archive.cells()[(2, 3)].losses == 1


def test_ties_break_on_novelty_then_on_insertion_order():
    archive = Archive(ParsedDescriptor(), novelty_threshold=0.0)
    first = candidate(cell_text(1, 2), novelty=0.5, iteration=1)
    novel = candidate(cell_text(1, 2), novelty=0.7, iteration=2)
    duplicate = candidate(cell_text(1, 2), novelty=0.7, iteration=3)
    archive.insert(first)
    assert archive.insert(novel).replaced
    result = archive.insert(duplicate)
    assert (result.inserted, result.reason) == (False, "dominated")
    assert archive.cells()[(1, 2)].candidate is novel
    assert archive.losses() == 2


def test_coverage_is_verified_cells_over_n_cells():
    descriptor = ParsedDescriptor()
    archive = Archive(descriptor, novelty_threshold=0.0)
    for k, (i, j) in enumerate([(0, 0), (1, 1), (2, 2)]):
        archive.insert(candidate(cell_text(i, j), iteration=k))
        assert archive.coverage() == pytest.approx((k + 1) / descriptor.n_cells)
    archive.insert(candidate(cell_text(0, 0), novelty=2.0))
    assert archive.coverage() == pytest.approx(3 / descriptor.n_cells)


def test_coverage_counts_verified_elites_not_cell_occupancy():
    """Eq. (2) counts cells holding a verified solution, not cells holding one."""
    descriptor = ParsedDescriptor()
    archive = Archive(descriptor, novelty_threshold=0.0)
    archive.insert(candidate(cell_text(0, 0), verdict=0.6))
    dumped = archive.to_dict()
    dumped["entries"][0]["verdict"] = 0.0
    restored = Archive.from_dict(dumped, descriptor)
    assert len(restored) == 1
    assert restored.coverage() == 0.0


def test_coverage_is_monotone_over_a_random_insertion_sequence():
    descriptor = ParsedDescriptor()
    archive = Archive(descriptor, novelty_threshold=0.3)
    rng = np.random.default_rng(11)
    history = [archive.coverage()]
    verified_cells: set[tuple[int, int]] = set()
    for t in range(30):
        i, j = int(rng.integers(4)), int(rng.integers(5))
        verdict = float(rng.choice([0.0, 0.5, 1.0]))
        novelty = float(rng.uniform(0.0, 1.0))
        archive.insert(
            candidate(cell_text(i, j), verdict=verdict, novelty=novelty, iteration=t)
        )
        if verdict > 0.0 and novelty >= 0.3:
            verified_cells.add((i, j))
        history.append(archive.coverage())
    assert all(b >= a for a, b in itertools.pairwise(history))
    assert archive.coverage() == pytest.approx(len(verified_cells) / descriptor.n_cells)
    assert 0.0 < archive.coverage() < 1.0


def test_best_and_elites_are_ordered():
    archive = Archive(ParsedDescriptor(), novelty_threshold=0.0)
    archive.insert(candidate(cell_text(3, 4), verdict=0.6, novelty=0.2, iteration=1))
    top = candidate(cell_text(0, 1), verdict=1.0, novelty=0.1, iteration=2)
    archive.insert(top)
    assert archive.best() is top
    assert [c.descriptor for c in archive.elites()] == [(0, 1), (3, 4)]
    assert (0, 1) in archive


def test_to_dict_round_trips():
    descriptor = ParsedDescriptor()
    archive = Archive(descriptor, novelty_threshold=0.25)
    for t, (i, j) in enumerate([(0, 0), (2, 3), (3, 4)]):
        archive.insert(
            candidate(cell_text(i, j), verdict=0.5 + 0.1 * t, novelty=0.4, iteration=t)
        )
    archive.insert(candidate(cell_text(0, 0), verdict=0.5, novelty=0.4, iteration=9))

    dumped = archive.to_dict()
    restored = Archive.from_dict(dumped, descriptor)
    assert restored.to_dict() == dumped
    assert restored.coverage() == archive.coverage()
    assert restored.novelty_threshold == archive.novelty_threshold
    assert [c.text for c in restored.elites()] == [c.text for c in archive.elites()]
    assert dumped["entries"][0]["cell_index"] == descriptor.cell_index((0, 0))
    assert dumped["occupied"] == 3
    assert dumped["losses"] == 1


def test_archive_assigns_the_cell_to_the_accepted_candidate():
    archive = Archive(get_descriptor("math500"), novelty_threshold=0.0)
    cand = candidate("by induction on n the base case holds", novelty=0.1)
    result = archive.insert(cand)
    assert result.inserted
    assert cand.descriptor == result.cell
    assert 0 <= archive.descriptor.cell_index(cand.descriptor) < 48
