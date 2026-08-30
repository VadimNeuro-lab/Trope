"""The optional backends: their sampling rules, and how they fail when absent."""

from __future__ import annotations

import importlib
import importlib.util
import math
import sys
from types import SimpleNamespace

import numpy as np
import pytest

from trope.backends.base import DecodingParams
from trope.backends.hf import (
    DEFAULT_CONTEXT_TOKENS,
    HFBackend,
    eta_mask,
    min_p_mask,
    resolve_context_tokens,
    score_blocks,
    scoring_window,
    tokenizer_vocabulary,
    top_h_mask,
    truncation_mask,
)
from trope.backends.registry import BACKENDS, MissingDependency, make_backend
from trope.backends.vllm import VLLMBackend

HAS_TORCH = importlib.util.find_spec("torch") is not None
HAS_TRANSFORMERS = importlib.util.find_spec("transformers") is not None
HAS_SENTENCE = importlib.util.find_spec("sentence_transformers") is not None

UNIFORM = np.full(8, 0.125)
PEAKED = np.array([0.97, 0.02, 0.006, 0.003, 0.001])
GRADED = np.array([0.4, 0.3, 0.2, 0.07, 0.03])
DISTRIBUTIONS = (UNIFORM, PEAKED, GRADED)
BUDGETS = (0.0, 0.1, 0.25, 0.5, 1.0, 1.5, 2.0, 2.9, 3.0, 8.0)


def entropy_bits(probs: np.ndarray) -> float:
    p = np.asarray(probs, dtype=np.float64)
    p = p[p > 0.0]
    p = p / p.sum()
    return float(-np.sum(p * np.log2(p)))


def entropy_nats(probs: np.ndarray) -> float:
    return sum(-float(p) * math.log(float(p)) for p in probs if p > 0.0)


@pytest.mark.parametrize("probs", DISTRIBUTIONS)
@pytest.mark.parametrize("bits", BUDGETS)
def test_top_h_keeps_at_least_one_token(probs: np.ndarray, bits: float) -> None:
    assert int(top_h_mask(probs, bits).sum()) >= 1


@pytest.mark.parametrize("probs", DISTRIBUTIONS)
@pytest.mark.parametrize("bits", BUDGETS)
def test_top_h_kept_mass_is_within_the_budget(probs: np.ndarray, bits: float) -> None:
    kept = probs[top_h_mask(probs, bits)]
    assert entropy_bits(kept) <= bits + 1e-9


@pytest.mark.parametrize("probs", DISTRIBUTIONS)
def test_top_h_is_monotone_in_the_budget(probs: np.ndarray) -> None:
    counts = [int(top_h_mask(probs, b).sum()) for b in BUDGETS]
    assert counts == sorted(counts)


def test_top_h_at_zero_bits_is_greedy() -> None:
    mask = top_h_mask(PEAKED, 0.0)
    assert mask.tolist() == [True, False, False, False, False]


def test_top_h_on_a_uniform_distribution_tracks_log2_k() -> None:
    assert int(top_h_mask(UNIFORM, 3.0).sum()) == 8
    assert int(top_h_mask(UNIFORM, 2.9).sum()) == 7
    assert int(top_h_mask(UNIFORM, 1.0).sum()) == 2


def test_top_h_none_keeps_everything() -> None:
    assert bool(top_h_mask(GRADED, None).all())


BUDGETS = tuple(round(0.1 * i, 2) for i in range(1, 61))


@pytest.mark.parametrize("probs", DISTRIBUTIONS)
def test_top_h_head_size_grows_with_the_budget(probs: np.ndarray) -> None:
    """The head size is what rho moves, which is the whole point of the operator."""
    sizes = [int(top_h_mask(probs, bits).sum()) for bits in BUDGETS]
    assert sizes == sorted(sizes)
    assert len(set(sizes)) > 1
    assert sizes[-1] == probs.size


@pytest.mark.parametrize("probs", DISTRIBUTIONS)
def test_the_kept_head_stays_within_its_entropy_budget(probs: np.ndarray) -> None:
    for bits in BUDGETS:
        kept = np.sort(probs[top_h_mask(probs, bits)])[::-1]
        if kept.size == probs.size:
            continue
        q = kept / kept.sum()
        entropy = float(-(q * np.log2(q)).sum())
        assert entropy <= bits + 1e-9, f"{bits} bits kept {kept.size} tokens"


def test_top_h_does_not_invent_a_budget() -> None:
    assert bool(top_h_mask(GRADED, None).all())


def test_truncation_mask_applies_the_entropy_budget() -> None:
    params = DecodingParams(temperature=1.0, entropy_budget=3.0)
    assert int(truncation_mask(UNIFORM, params).sum()) == 8


QUARTERS = np.array([0.5, 0.25, 0.125, 0.125])

MIN_P_CASES = [
    (QUARTERS, 0.5, [True, True, False, False]),
    (QUARTERS, 0.25, [True, True, True, True]),
    (QUARTERS, 1.0, [True, False, False, False]),
    (QUARTERS, 0.0, [True, True, True, True]),
    (np.array([0.9, 0.1]), 0.5, [True, False]),
    (np.array([0.9, 0.1]), 0.1, [True, True]),
    (UNIFORM, 1.0, [True] * 8),
    (PEAKED, 0.5, [True, False, False, False, False]),
]


@pytest.mark.parametrize(("probs", "min_p", "kept"), MIN_P_CASES)
def test_min_p_matches_its_definition(
    probs: np.ndarray, min_p: float, kept: list[bool]
) -> None:
    assert min_p_mask(probs, min_p).tolist() == kept


@pytest.mark.parametrize("probs", DISTRIBUTIONS)
def test_min_p_none_keeps_everything(probs: np.ndarray) -> None:
    assert bool(min_p_mask(probs, None).all())


ETAS = (1e-6, 1e-4, 3e-4, 0.01, 0.1, 0.5, 1.0)


@pytest.mark.parametrize("probs", DISTRIBUTIONS)
@pytest.mark.parametrize("eta", ETAS)
def test_eta_always_keeps_the_argmax(probs: np.ndarray, eta: float) -> None:
    assert bool(eta_mask(probs, eta)[int(np.argmax(probs))])


@pytest.mark.parametrize("probs", DISTRIBUTIONS)
@pytest.mark.parametrize("eta", ETAS)
def test_eta_matches_the_threshold_formula(probs: np.ndarray, eta: float) -> None:
    threshold = min(eta, math.sqrt(eta) * math.exp(-entropy_nats(probs)))
    expected = [bool(p >= threshold) for p in probs]
    expected[int(np.argmax(probs))] = True
    assert eta_mask(probs, eta).tolist() == expected


@pytest.mark.parametrize("probs", DISTRIBUTIONS)
def test_eta_truncates_more_as_eta_grows(probs: np.ndarray) -> None:
    counts = [int(eta_mask(probs, e).sum()) for e in ETAS]
    assert counts == sorted(counts, reverse=True)


def test_eta_degenerates_to_greedy_at_one() -> None:
    assert eta_mask(PEAKED, 1.0).tolist() == [True, False, False, False, False]
    assert eta_mask(GRADED, 1.0).tolist() == [True, True, False, False, False]


def test_eta_at_a_paper_scale_value_keeps_the_flat_tail() -> None:
    assert bool(eta_mask(UNIFORM, 3e-4).all())


def test_truncation_mask_delegates_to_one_rule() -> None:
    params = DecodingParams(temperature=1.0, min_p=0.5)
    assert truncation_mask(QUARTERS, params).tolist() == min_p_mask(QUARTERS, 0.5).tolist()


def test_truncation_mask_is_never_empty() -> None:
    params = DecodingParams(temperature=1.0, min_p=1.0, entropy_budget=0.0, eta=1.0)
    mask = truncation_mask(GRADED, params)
    assert mask.tolist() == [True, False, False, False, False]


def test_truncation_mask_with_no_rules_keeps_everything() -> None:
    assert bool(truncation_mask(GRADED, DecodingParams(temperature=0.7)).all())


CONT = list(range(1, 40))
PREFIX = list(range(100, 160))


def scored_ids(blocks: list[tuple[list[int], int]]) -> list[int]:
    return [i for ids, offset in blocks for i in ids[offset:]]


def test_score_blocks_scores_the_same_tokens_with_and_without_a_prefix() -> None:
    kwargs = {"bos_id": 0, "delimiter_ids": [9], "window": 32, "stride": 16}
    alone = score_blocks([], CONT, **kwargs)
    conditioned = score_blocks(PREFIX, CONT, **kwargs)
    assert scored_ids(alone) == CONT
    assert scored_ids(conditioned) == CONT
    assert len(alone) == len(conditioned)


def test_score_blocks_truncates_the_prefix_not_the_continuation() -> None:
    blocks = score_blocks(
        PREFIX, CONT, bos_id=0, delimiter_ids=[9], window=32, stride=16
    )
    ids, offset = blocks[0]
    assert len(ids) == 32
    lead = ids[:offset]
    budget = 32 - 16 - len([0]) - len([9])
    assert lead == [0] + PREFIX[-budget:] + [9]


def test_score_blocks_gives_every_scored_token_a_left_context() -> None:
    for prefix in ([], PREFIX):
        for _, offset in score_blocks(
            prefix, CONT, bos_id=None, delimiter_ids=[9], window=32, stride=16
        ):
            assert offset >= 1


def test_score_blocks_cuts_the_continuation_on_stride_boundaries() -> None:
    blocks = score_blocks(
        PREFIX, CONT, bos_id=0, delimiter_ids=[9], window=32, stride=16
    )
    assert [len(ids) - offset for ids, offset in blocks] == [16, 16, 7]


def test_score_blocks_rejects_a_lead_with_no_tokens() -> None:
    with pytest.raises(ValueError, match="leading token"):
        score_blocks([], CONT, bos_id=None, delimiter_ids=[], window=32, stride=16)


QWEN = {"model_type": "qwen2", "hidden_size": 2048, "max_position_embeddings": 32768}
GPT2 = {"model_type": "gpt2", "n_positions": 1024}


def test_context_length_is_read_from_the_config() -> None:
    assert resolve_context_tokens(QWEN) == 32768
    assert resolve_context_tokens(GPT2) == 1024
    assert resolve_context_tokens({"n_ctx": 2048}) == 2048
    assert resolve_context_tokens({"seq_length": 8192}) == 8192
    assert resolve_context_tokens({"max_seq_len": 4096}) == 4096


def test_context_length_prefers_max_position_embeddings() -> None:
    config = {"n_positions": 1024, "max_position_embeddings": 4096}
    assert resolve_context_tokens(config) == 4096


def test_context_length_reads_a_nested_decoder_config() -> None:
    config = {"model_type": "mllama", "text_config": {"n_positions": 131072}}
    assert resolve_context_tokens(config) == 131072


def test_context_length_accepts_a_config_object_not_only_a_mapping() -> None:
    class Stub:
        def to_dict(self) -> dict[str, int]:
            return {"max_position_embeddings": 4096}

    assert resolve_context_tokens(Stub()) == 4096
    assert resolve_context_tokens(SimpleNamespace(n_positions=1024)) == 1024


def test_context_length_falls_back_when_the_config_is_silent() -> None:
    assert resolve_context_tokens({"model_type": "toy"}) == DEFAULT_CONTEXT_TOKENS
    assert resolve_context_tokens({}, default=777) == 777


@pytest.mark.parametrize("value", [0, -1, None, True, float("nan"), "4096", 1e30])
def test_context_length_ignores_sentinels_and_non_lengths(value: object) -> None:
    config = {"max_position_embeddings": value}
    assert resolve_context_tokens(config) == DEFAULT_CONTEXT_TOKENS


def test_scoring_window_comes_from_the_model_not_from_a_fixed_512() -> None:
    assert scoring_window(QWEN, None) == 32768
    assert scoring_window({}, None) == DEFAULT_CONTEXT_TOKENS


def test_scoring_window_takes_a_cap_but_never_a_raise() -> None:
    assert scoring_window(QWEN, 1024) == 1024
    assert scoring_window(GPT2, 4096) == 1024


def test_context_tokens_reports_the_window_score_can_honour() -> None:
    assert HFBackend.context_tokens.fget(SimpleNamespace(window=4096)) == 4096


VOCAB = {"the": 3, "Ġcat": 1, "!": 0, "<|endoftext|>": 2}


class StubTokenizer:
    """Enough of a `PreTrainedTokenizer` to resolve a vocabulary from."""

    def __init__(self, vocab: dict[str, int], special: tuple[str, ...] = ()) -> None:
        self._vocab = dict(vocab)
        self.all_special_tokens = list(special)
        self.calls = 0

    def get_vocab(self) -> dict[str, int]:
        self.calls += 1
        return dict(self._vocab)


def test_vocabulary_is_in_id_order_with_special_tokens_dropped() -> None:
    tokenizer = StubTokenizer(VOCAB, special=("<|endoftext|>",))
    assert tokenizer_vocabulary(tokenizer) == ("!", "Ġcat", "the")


def test_vocabulary_keeps_the_surface_tokens_not_decoded_text() -> None:
    assert "Ġcat" in tokenizer_vocabulary(StubTokenizer(VOCAB))


def test_vocabulary_falls_back_to_the_vocab_attribute() -> None:
    assert tokenizer_vocabulary(SimpleNamespace(vocab={"a": 1, "b": 0})) == ("b", "a")


def test_vocabulary_falls_back_to_converting_ids() -> None:
    class Stub:
        vocab_size = 3

        def convert_ids_to_tokens(self, ids: list[int]) -> list[str]:
            return [f"t{i}" for i in ids]

    assert tokenizer_vocabulary(Stub()) == ("t0", "t1", "t2")


def test_vocabulary_is_empty_when_there_is_nothing_to_enumerate() -> None:
    assert tokenizer_vocabulary(object()) == ()


def test_hf_vocabulary_is_lazy_and_cached() -> None:
    tokenizer = StubTokenizer(VOCAB, special=("<|endoftext|>",))
    backend = SimpleNamespace(_vocabulary=None, _tokenizer=tokenizer)
    assert tokenizer.calls == 0
    first = HFBackend.vocabulary(backend)
    second = HFBackend.vocabulary(backend)
    assert first == second == ("!", "Ġcat", "the")
    assert tokenizer.calls == 1


def test_the_null_check_finds_the_backend_vocabulary() -> None:
    """The duck-typed contract `novelty.model_vocabulary` reads."""
    from trope.novelty import model_vocabulary

    backend = SimpleNamespace(_vocabulary=None, _tokenizer=StubTokenizer(VOCAB))
    backend.vocabulary = lambda: HFBackend.vocabulary(backend)
    assert set(model_vocabulary(backend)) >= {"!", "Ġcat", "the"}


def test_make_backend_mock() -> None:
    backend = make_backend("mock")
    assert backend.name == "mock"
    assert backend.count_tokens("two words") == 2


@pytest.mark.skipif(HAS_TORCH, reason="torch is installed, so its absence proves nothing")
def test_the_offline_path_never_imports_torch() -> None:
    make_backend("mock")
    importlib.import_module("trope.backends.hf")
    assert "torch" not in sys.modules


def test_importing_the_hf_module_needs_no_torch() -> None:
    module = importlib.import_module("trope.backends.hf")
    assert hasattr(module, "HFBackend")


@pytest.mark.skipif(HAS_TORCH, reason="would download and load a checkpoint")
def test_make_backend_hf_names_the_extra() -> None:
    with pytest.raises(MissingDependency) as caught:
        make_backend("hf", model="Qwen/Qwen2.5-0.5B-Instruct")
    assert "trope[hf]" in str(caught.value)
    assert caught.value.extra == "hf"


@pytest.mark.skipif(HAS_SENTENCE, reason="would download the encoder")
def test_make_encoder_sentence_names_the_extra() -> None:
    from trope.backends.registry import make_encoder

    with pytest.raises(MissingDependency) as caught:
        make_encoder("sentence")
    assert "trope[encoder]" in str(caught.value)


def test_unknown_backend_lists_the_available_ones() -> None:
    with pytest.raises(KeyError) as caught:
        make_backend("gpt-9")
    message = str(caught.value)
    for name in BACKENDS:
        assert name in message


def test_vllm_refuses_to_score() -> None:
    with pytest.raises(NotImplementedError, match="hf backend"):
        VLLMBackend.score(None, "a passage of the evidence corpus")


@pytest.mark.extras
@pytest.mark.skipif(
    not (HAS_TORCH and HAS_TRANSFORMERS), reason="needs torch and transformers"
)
def test_logits_processor_applies_the_pure_rule() -> None:
    import torch

    from trope.backends.hf import logits_processors

    probs = np.array([0.5, 0.3, 0.15, 0.05])
    processor = logits_processors(DecodingParams(temperature=1.0, min_p=0.2))[0]
    scores = torch.log(torch.tensor([probs], dtype=torch.float32))
    out = processor(torch.zeros((1, 1), dtype=torch.long), scores)
    kept = np.isfinite(out.detach().numpy()[0])
    assert kept.tolist() == min_p_mask(probs, 0.2).tolist()


@pytest.mark.extras
@pytest.mark.skipif(
    not (HAS_TORCH and HAS_TRANSFORMERS), reason="needs torch and transformers"
)
def test_logits_processor_scales_by_temperature() -> None:
    import torch

    from trope.backends.hf import logits_processors

    scores = torch.tensor([[2.0, 1.0, 0.0]], dtype=torch.float32)
    processor = logits_processors(DecodingParams(temperature=0.5))[0]
    out = processor(torch.zeros((1, 1), dtype=torch.long), scores)
    assert torch.allclose(out, scores / 0.5)


@pytest.mark.extras
@pytest.mark.skipif(
    not (HAS_TORCH and HAS_TRANSFORMERS), reason="needs torch and transformers"
)
def test_logits_processor_applies_the_entropy_budget() -> None:
    import torch

    from trope.backends.hf import logits_processors

    params = DecodingParams(temperature=1.0, entropy_budget=3.0)
    scores = torch.log(torch.tensor([UNIFORM], dtype=torch.float32))
    ids = torch.zeros((1, 1), dtype=torch.long)
    kept = logits_processors(params)[0](ids, scores)
    assert int(np.isfinite(kept.detach().numpy()[0]).sum()) == 8


@pytest.mark.extras
@pytest.mark.skipif(not HAS_TORCH, reason="needs torch")
def test_the_vllm_processor_applies_the_entropy_budget() -> None:
    import torch

    from trope.backends.vllm import _extra_processors

    params = DecodingParams(temperature=1.0, entropy_budget=3.0)
    logits = torch.log(torch.tensor(UNIFORM, dtype=torch.float32))
    kept = _extra_processors(params)[0]([], logits)
    assert int(np.isfinite(kept.detach().numpy()).sum()) == 8


@pytest.mark.extras
@pytest.mark.slow
@pytest.mark.skipif(not HAS_SENTENCE, reason="needs sentence-transformers")
def test_sentence_encoder_returns_unit_rows_and_caches() -> None:
    from trope.backends.sentence import SentenceEncoder

    encoder = SentenceEncoder()
    labels = ["variable:mass", "parameter:friction", "variable:mass"]
    vectors = encoder.encode(labels)
    assert vectors.shape == (3, encoder.dim)
    assert np.allclose(np.linalg.norm(vectors, axis=1), 1.0, atol=1e-5)
    assert np.array_equal(vectors[0], vectors[2])
    assert encoder.encode([]).shape == (0, encoder.dim)
