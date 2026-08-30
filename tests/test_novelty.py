"""Compression novelty (Eq. 5) and the evidence corpus that feeds it."""

from __future__ import annotations

import math

import numpy as np
import pytest

from trope.backends.base import CallCounter, MeteredBackend, ScoreResult
from trope.corpus import (
    BM25Index,
    Document,
    GoldAnswerFilter,
    RetrievalError,
    answer_variants,
    build_corpus,
    fallback_index,
    frame_passages,
    tokenise,
)
from trope.data.base import Problem
from trope.novelty import (
    CompressionNovelty,
    NoveltyResult,
    model_vocabulary,
    null_check,
    reported_context,
)

CORPUS = (
    "alpha beta gamma alpha",
    "delta alpha epsilon",
    "beta beta zeta",
)


class AnalyticScorer:
    """Every token costs 1 nat, except one already seen in the prefix: 0.5."""

    name = "analytic"

    def __init__(self) -> None:
        self.score_calls = 0

    def score(self, continuation: str, prefix: str = "") -> ScoreResult:
        self.score_calls += 1
        tokens = continuation.split()
        seen = set(prefix.split())
        lp = np.array([-0.5 if t in seen else -1.0 for t in tokens], dtype=np.float64)
        return ScoreResult(float(lp.sum()), len(tokens), lp)

    def count_tokens(self, text: str) -> int:
        return len(text.split())


class ContextScorer(AnalyticScorer):
    """A scorer that reports its own context length, as the `hf` backend does."""

    context_window = 64


class VocabularyScorer(AnalyticScorer):
    """A scorer exposing the model vocabulary the paper draws the null from."""

    def vocabulary(self) -> tuple[str, ...]:
        return ("mu", "nu", "xi")


class _Tokenizer:
    all_special_tokens = ("<pad>",)

    def get_vocab(self) -> dict[str, int]:
        return {"mu": 0, "nu": 1, "<pad>": 2}


class TokenizerScorer(AnalyticScorer):
    """A scorer exposing a tokenizer instead, as a transformers backend does."""

    tokenizer = _Tokenizer()


class DriftingScorer(AnalyticScorer):

    def score(self, continuation: str, prefix: str = "") -> ScoreResult:
        res = super().score(continuation, prefix)
        if prefix:
            return ScoreResult(res.total_logprob, res.n_tokens - 1, res.token_logprobs)
        return res


def test_novelty_matches_the_closed_form():
    scorer = AnalyticScorer()
    nov = CompressionNovelty(scorer, CORPUS, normalise="total")
    result = nov.score("alpha zeta")
    assert result.value == pytest.approx(0.5 * 4)
    assert result.baseline_logprob == pytest.approx(-10.0)
    assert result.n_tokens == 10


def test_per_token_normalisation_divides_by_corpus_tokens():
    scorer = AnalyticScorer()
    total = CompressionNovelty(scorer, CORPUS, normalise="total").score("alpha")
    per_token = CompressionNovelty(scorer, CORPUS, normalise="per_token").score("alpha")
    assert per_token.n_tokens == total.n_tokens == 10
    assert per_token.value == pytest.approx(total.value / total.n_tokens)
    assert per_token.gain == pytest.approx(total.value)


def test_novelty_is_not_clipped_at_zero():
    """Proposition 3.3 bounds E[Nov]; a single candidate may exceed 0."""
    nov = CompressionNovelty(AnalyticScorer(), CORPUS)
    assert nov.score("alpha beta gamma delta epsilon zeta").value > 0.0
    assert nov.score("nothing in common here").value == pytest.approx(0.0)


def test_baseline_is_computed_once_per_corpus():
    scorer = AnalyticScorer()
    nov = CompressionNovelty(scorer, CORPUS)
    first = nov.baseline()
    for text in ("alpha", "beta", "gamma"):
        nov.score(text)
    assert scorer.score_calls == len(CORPUS) * 4
    assert nov.baseline() == first


def test_baseline_does_not_depend_on_the_candidate():
    nov = CompressionNovelty(AnalyticScorer(), CORPUS)
    short = nov.score("alpha")
    long = nov.score("alpha " * 400)
    assert short.baseline_logprob == long.baseline_logprob
    assert short.n_tokens == long.n_tokens


def test_same_corpus_tokens_are_dropped_in_both_conditions():
    scorer = AnalyticScorer()
    nov = CompressionNovelty(scorer, CORPUS, window_tokens=6, prefix_tokens=3)
    assert nov.passage_tokens == 3
    assert nov.passages() == ("alpha beta gamma", "delta alpha epsilon", "beta beta zeta")
    result = nov.score("alpha beta gamma delta epsilon zeta extra words here")
    assert result.n_tokens == 9
    assert result.gain == pytest.approx(0.5 * 6)


def test_a_window_that_fits_truncates_nothing():
    """The paper's Eq. (5) states no length limit; a big enough window has none."""
    nov = CompressionNovelty(AnalyticScorer(), CORPUS, window_tokens=512, normalise="total")
    result = nov.score(" ".join(["alpha"] * 200))
    assert nov.passages() == CORPUS
    assert nov.passages_truncated == 0
    assert result.truncated is False
    assert result.n_tokens == 10
    assert nov.prefix_tokens == 508


def test_truncation_is_reported_and_still_scores_the_same_tokens_in_both_terms():
    nov = CompressionNovelty(
        AnalyticScorer(), CORPUS, window_tokens=6, prefix_tokens=3, normalise="total"
    )
    assert nov.passages_truncated == 1
    result = nov.score("alpha beta gamma delta")
    assert result.truncated is True
    assert result.n_tokens == nov.n_corpus_tokens == 9


def test_the_reported_context_length_sizes_the_window():
    scorer = ContextScorer()
    assert reported_context(scorer) == 64
    nov = CompressionNovelty(scorer, CORPUS, window_tokens=8)
    assert nov.context_tokens == 64
    assert nov.window_tokens == 64
    assert CompressionNovelty(scorer, CORPUS, context_tokens=12).window_tokens == 12
    plain = CompressionNovelty(AnalyticScorer(), CORPUS, window_tokens=8)
    assert (plain.context_tokens, plain.window_tokens) == (None, 8)


def test_the_reported_context_is_read_through_a_metering_wrapper():
    wrapped = MeteredBackend(ContextScorer(), CallCounter(), role="reference")
    assert reported_context(wrapped) == 64
    assert CompressionNovelty(wrapped, CORPUS, window_tokens=8).window_tokens == 64


def test_prefix_budget_stays_proportional_when_the_corpus_fills_the_window():
    """The candidate never gets less than its share, however long the passages."""
    corpus = (" ".join(["alpha"] * 40),)
    nov = CompressionNovelty(AnalyticScorer(), corpus, window_tokens=20)
    assert nov.prefix_tokens == 10
    assert nov.passage_tokens == 10
    assert nov.passages_truncated == 1


def test_token_count_mismatch_is_an_error():
    nov = CompressionNovelty(DriftingScorer(), CORPUS)
    with pytest.raises(ValueError, match="same corpus tokens"):
        nov.score("alpha")


def test_empty_corpus_is_rejected():
    with pytest.raises(ValueError, match="empty"):
        CompressionNovelty(AnalyticScorer(), ()).baseline()


def test_unknown_normalisation_is_rejected():
    with pytest.raises(ValueError, match="normalise"):
        CompressionNovelty(AnalyticScorer(), CORPUS, normalise="zscore")


def test_gain_is_the_unnormalised_difference():
    result = NoveltyResult(value=0.25, total_logprob=-8.0, baseline_logprob=-10.0, n_tokens=8)
    assert result.gain == pytest.approx(2.0)
    assert result.value == pytest.approx(result.gain / result.n_tokens)


def test_null_check_table_shape_and_determinism():
    scorer = AnalyticScorer()
    lengths = (4, 8)
    a = null_check(
        scorer, CORPUS, np.random.default_rng(7), lengths=lengths, n=32, resamples=64
    )
    b = null_check(
        scorer, CORPUS, np.random.default_rng(7), lengths=lengths, n=32, resamples=64
    )
    assert set(a) == set(lengths)
    assert a == b
    for row in a.values():
        assert row["n"] == 32
        assert 0.0 <= row["p_nonpositive"] <= 1.0
        lo, hi = row["ci"]
        assert lo <= row["mean"] <= hi


def test_null_check_prefers_the_model_vocabulary():
    """Appendix: prefixes are drawn "uniformly from the model vocabulary"."""
    assert model_vocabulary(VocabularyScorer()) == ("mu", "nu", "xi")
    assert model_vocabulary(TokenizerScorer()) == ("mu", "nu")
    assert model_vocabulary(AnalyticScorer()) == ()

    rng = np.random.default_rng(1)
    for scorer, size in ((VocabularyScorer(), 3), (TokenizerScorer(), 2)):
        table = null_check(scorer, CORPUS, rng, lengths=(4,), n=8, resamples=16)
        assert table[4]["vocabulary"] == "model"
        assert table[4]["vocabulary_size"] == size


def test_null_check_falls_back_to_the_corpus_and_records_the_source():
    rng = np.random.default_rng(1)
    corpus_row = null_check(
        AnalyticScorer(), CORPUS, rng, lengths=(4,), n=8, resamples=16
    )[4]
    assert corpus_row["vocabulary"] == "corpus"
    assert corpus_row["vocabulary_size"] == 6
    given_row = null_check(
        VocabularyScorer(),
        CORPUS,
        rng,
        lengths=(4,),
        n=8,
        resamples=16,
        vocabulary=("alpha", "beta"),
    )[4]
    assert given_row["vocabulary"] == "given"
    assert given_row["vocabulary_size"] == 2


def test_null_check_random_prefixes_do_not_compress_the_corpus():
    """Assumption 3.3 probed against the mock reference LM, as the appendix does."""
    from trope.backends.mock import MockBackend

    corpus = build_corpus(
        Problem(
            id="p",
            text="counting arrangements of a finite group under a prime modulus",
            benchmark="math500",
            family="math_answer",
            answer="17",
        ),
        fallback_index(),
        top_k=8,
    )
    table = null_check(
        MockBackend(seed=0),
        corpus,
        np.random.default_rng(3),
        lengths=(16, 64),
        n=24,
        resamples=128,
    )
    for row in table.values():
        assert row["mean"] < 0.0
        assert row["p_nonpositive"] > 0.5


def bm25_reference(index: BM25Index, term: str, doc: int) -> float:
    tf = tokenise(index.documents[doc].text).count(term)
    dl = len(tokenise(index.documents[doc].text))
    idf = index.idf(term)
    return idf * tf * (index.k1 + 1.0) / (
        tf + index.k1 * (1.0 - index.b + index.b * dl / index.avgdl)
    )


def test_bm25_known_answer():
    index = BM25Index([Document("d0", "cat cat dog"), Document("d1", "dog bird")])
    assert index.avgdl == pytest.approx(2.5)
    assert index.idf("cat") == pytest.approx(math.log(1.0 + 1.5 / 1.5))
    expected = math.log(2.0) * 2 * 2.5 / (2 + 1.5 * (0.25 + 0.75 * 3 / 2.5))
    assert index.score(["cat"], 0) == pytest.approx(expected)
    assert index.score(["cat"], 0) == pytest.approx(bm25_reference(index, "cat", 0))
    assert index.score(["cat"], 1) == 0.0


def test_bm25_ranks_the_document_containing_the_query_terms_first():
    index = BM25Index(
        [
            Document("d0", "the mitochondrion is the powerhouse of the cell"),
            Document("d1", "quadratic reciprocity relates two legendre symbols"),
            Document("d2", "a legendre symbol is a completely multiplicative function"),
        ]
    )
    hits = index.search("legendre symbol reciprocity", top_k=3)
    assert [doc_id for doc_id, _ in hits] == ["d1", "d2"]
    assert hits[0][1] > hits[1][1]


def test_idf_vanishes_for_a_term_in_every_document():
    index = BM25Index([Document(f"d{i}", f"common token{i}") for i in range(40)])
    assert index.idf("common") == pytest.approx(math.log(1 + 0.5 / 40.5), abs=1e-12)
    assert index.idf("common") < 0.02
    assert index.idf("common") >= 0.0
    halved = BM25Index(
        [Document(f"d{i}", "common token" if i < 20 else "token") for i in range(40)]
    )
    assert index.idf("token0") > halved.idf("common") > index.idf("common")


def test_ranking_ties_break_by_document_id():
    text = "alpha beta gamma"
    forward = BM25Index([Document("b", text), Document("a", text)])
    reverse = BM25Index([Document("a", text), Document("b", text)])
    assert forward.search("alpha", top_k=2) == reverse.search("alpha", top_k=2)
    assert [doc_id for doc_id, _ in forward.search("alpha", top_k=2)] == ["a", "b"]


def test_duplicate_document_ids_are_rejected():
    with pytest.raises(ValueError, match="unique"):
        BM25Index([Document("d", "one"), Document("d", "two")])


def test_gold_filter_drops_the_answer_and_keeps_everything_else():
    filt = GoldAnswerFilter(["42"])
    leaked = Document("d0", "the final answer is 42, as required", "wiki/proofs.txt")
    clean = Document("d1", "there are 420 ways to seat them", "wiki/counting.txt")
    assert filt(leaked) is False
    assert filt(clean) is True
    assert filt.filter_report() == {
        "seen": 2,
        "kept": 1,
        "dropped_answer": 1,
        "dropped_path": 0,
    }


def test_gold_filter_matches_normalised_forms():
    filt = GoldAnswerFilter([r"$\boxed{1,234}$"])
    assert answer_variants(r"$\boxed{1,234}$")[0] == "1234"
    assert filt(Document("d0", "exactly 1234 configurations", "corpus/a.txt")) is False
    assert filt(Document("d1", "exactly 12345 configurations", "corpus/b.txt")) is True


def test_gold_filter_rejects_benchmark_paths_but_not_lookalike_words():
    filt = GoldAnswerFilter([])
    assert filt(Document("d0", "text", "data/aime/2025/problems.jsonl")) is False
    assert filt(Document("d1", "text", "corpus/quotient-groups.txt")) is True
    assert filt(Document("d2", "text", "benchmarks/live_code_bench/tests.py")) is False
    report = filt.filter_report()
    assert report["dropped_path"] == 2
    assert report["dropped_answer"] == 0


def test_filter_report_resets():
    filt = GoldAnswerFilter(["7"])
    filt(Document("d0", "seven is 7", "a.txt"))
    filt.reset()
    assert filt.filter_report() == {
        "seen": 0,
        "kept": 0,
        "dropped_answer": 0,
        "dropped_path": 0,
    }


def problem(text: str, answer: str = "42") -> Problem:
    return Problem(
        id="p1", text=text, benchmark="math500", family="math_answer", answer=answer
    )


def test_build_corpus_ranks_filters_and_truncates():
    index = BM25Index(
        [
            Document("d0", "prime factorisation of an integer modulus", "corpus/nt.txt"),
            Document("d1", "the integer modulus equals 42 here", "corpus/leak.txt"),
            Document("d2", "an unrelated passage about baking bread", "corpus/food.txt"),
            Document("d3", "integer arithmetic and modulus operations", "corpus/cs.txt"),
        ]
    )
    corpus = build_corpus(problem("integer modulus"), index, top_k=2)
    assert "d1" not in corpus.ids
    assert len(corpus) == 2
    assert corpus.scores[0] >= corpus.scores[1]
    assert corpus.report["dropped_answer"] == 1
    assert corpus.report["zero_scored"] == 0
    assert corpus.problem_id == "p1" and corpus.family == "math_answer"


def test_build_corpus_keeps_going_when_nothing_scores():
    """"The top N_C most-relevant passages" is defined even at score zero."""
    index = BM25Index([Document("d0", "unrelated passage", "corpus/a.txt")])
    corpus = build_corpus(problem("zzzz qqqq"), index, top_k=5)
    assert corpus.ids == ("d0",)
    assert corpus.scores == (0.0,)
    assert corpus.report["zero_scored"] == 1
    assert corpus.report["seen"] == 1


def test_build_corpus_tops_up_a_short_retrieval():
    """A retrieval shorter than top_k is filled from the rest of the index."""
    index = BM25Index(
        [
            Document("d0", "integer modulus arithmetic", "corpus/a.txt"),
            Document("d1", "an unrelated passage about bread", "corpus/b.txt"),
            Document("d2", "another unrelated passage", "corpus/c.txt"),
        ]
    )
    corpus = build_corpus(problem("integer modulus"), index, top_k=3)
    assert corpus.ids[0] == "d0" and corpus.scores[0] > 0.0
    assert set(corpus.ids) == {"d0", "d1", "d2"}
    assert corpus.report["zero_scored"] == 2


def test_build_corpus_raises_when_every_passage_is_filtered_out():
    """Nov(s|C) has nothing to compress against an empty C."""
    index = BM25Index([Document("d0", "the answer is 42", "corpus/a.txt")])
    with pytest.raises(RetrievalError, match="p1"):
        build_corpus(problem("zzzz qqqq"), index, top_k=5)


def test_fallback_index_has_one_passage_per_frame():
    docs = frame_passages()
    index = fallback_index()
    assert len(index) == len(docs) == 21
    assert index is fallback_index()
    assert all(d.source == "assets/frames.json" for d in docs)
    hits = index.search("group ring polynomial ideal homomorphism", top_k=1)
    assert hits[0][0] == "frame:algebra"


def test_corpus_export_round_trips(tmp_path):
    corpus = build_corpus(problem("prime modulus counting"), fallback_index(), top_k=3)
    path = corpus.write_jsonl(tmp_path / "corpus.jsonl")
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    assert len(lines) == len(corpus)
    first = lines[0]
    assert '"family": "math_answer"' in first
    assert '"passage_id": "' + corpus.ids[0] + '"' in first
