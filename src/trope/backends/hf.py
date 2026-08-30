"""HuggingFace `transformers` backend: sampling and reference-LM scoring."""

from __future__ import annotations

import math
from collections.abc import Mapping, Sequence
from typing import Any

import numpy as np

from trope.backends.base import DecodingParams, Generation, ScoreResult
from trope.backends.registry import MissingDependency

DELIMITER = "\n\n"
MIN_TEMPERATURE = 1e-5
ENTROPY_TOLERANCE = 1e-9

DEFAULT_CONTEXT_TOKENS = 2048

CONTEXT_FIELDS: tuple[str, ...] = (
    "max_position_embeddings",
    "n_positions",
    "n_ctx",
    "seq_length",
    "max_sequence_length",
    "max_seq_len",
)

NESTED_CONFIG_FIELDS: tuple[str, ...] = ("text_config", "llm_config", "decoder")

IMPLAUSIBLE_CONTEXT = 1 << 25


def top_k_mask(probs: np.ndarray, top_k: int | None) -> np.ndarray:
    """Keep the `top_k` most probable tokens."""
    p = np.asarray(probs, dtype=np.float64)
    if not top_k or top_k <= 0 or top_k >= p.size:
        return np.ones(p.shape, dtype=bool)
    mask = np.zeros(p.shape, dtype=bool)
    mask[np.argsort(-p, kind="stable")[: int(top_k)]] = True
    return mask


def top_p_mask(probs: np.ndarray, top_p: float | None) -> np.ndarray:
    """Keep the smallest head of the sorted distribution with mass >= `top_p`."""
    p = np.asarray(probs, dtype=np.float64)
    if top_p is None or top_p >= 1.0:
        return np.ones(p.shape, dtype=bool)
    order = np.argsort(-p, kind="stable")
    csum = np.cumsum(p[order])
    total = csum[-1]
    if total <= 0.0:
        return np.ones(p.shape, dtype=bool)
    k = int(np.searchsorted(csum, float(top_p) * total, side="left")) + 1
    mask = np.zeros(p.shape, dtype=bool)
    mask[order[: min(max(k, 1), p.size)]] = True
    return mask


def min_p_mask(probs: np.ndarray, min_p: float | None) -> np.ndarray:
    """Keep tokens with `p >= min_p * max(p)` (Nguyen et al., 2025)."""
    p = np.asarray(probs, dtype=np.float64)
    if min_p is None or min_p <= 0.0:
        return np.ones(p.shape, dtype=bool)
    return p >= float(min_p) * float(p.max())


def eta_mask(probs: np.ndarray, eta: float | None) -> np.ndarray:
    """Keep tokens above `min(eta, sqrt(eta) * exp(-H(p)))` (Hewitt et al., 2022)."""
    p = np.asarray(probs, dtype=np.float64)
    if eta is None or eta <= 0.0:
        return np.ones(p.shape, dtype=bool)
    safe = np.where(p > 0.0, p, 1.0)
    entropy = float(-np.sum(np.where(p > 0.0, p * np.log(safe), 0.0)))
    threshold = min(float(eta), math.sqrt(float(eta)) * math.exp(-entropy))
    mask = p >= threshold
    mask[int(np.argmax(p))] = True
    return mask


def top_h_mask(probs: np.ndarray, bits: float | None) -> np.ndarray:
    """Keep the largest head whose renormalised entropy is within `bits`."""
    p = np.asarray(probs, dtype=np.float64)
    if bits is None:
        return np.ones(p.shape, dtype=bool)
    order = np.argsort(-p, kind="stable")
    q = p[order]
    positive = q > 0.0
    head_mass = np.cumsum(q)
    plogp = np.cumsum(np.where(positive, q * np.log2(np.where(positive, q, 1.0)), 0.0))
    safe = np.where(head_mass > 0.0, head_mass, 1.0)
    entropy = np.log2(safe) - plogp / safe
    within = entropy <= float(bits) + ENTROPY_TOLERANCE
    k = p.size if bool(within.all()) else int(np.argmin(within))
    mask = np.zeros(p.shape, dtype=bool)
    mask[order[: max(k, 1)]] = True
    return mask


def truncation_mask(probs: np.ndarray, params: DecodingParams) -> np.ndarray:
    """Every truncation `params` asks for, in a fixed order."""
    p = np.asarray(probs, dtype=np.float64)
    keep = np.ones(p.shape, dtype=bool)
    rules = (
        (top_k_mask, params.top_k),
        (top_p_mask, params.top_p),
        (min_p_mask, params.min_p),
        (eta_mask, params.eta),
        (top_h_mask, params.entropy_budget),
    )
    for rule, value in rules:
        if value is None:
            continue
        current = np.where(keep, p, 0.0)
        total = float(current.sum())
        if total <= 0.0:
            break
        keep = keep & rule(current / total, value)
    if not keep.any():
        keep[int(np.argmax(p))] = True
    return keep


def score_blocks(
    prefix_ids: Sequence[int],
    cont_ids: Sequence[int],
    *,
    bos_id: int | None,
    delimiter_ids: Sequence[int],
    window: int,
    stride: int,
) -> list[tuple[list[int], int]]:
    """Forward passes that score `cont_ids` in the context of `prefix_ids`."""
    lead_fixed = (1 if bos_id is not None else 0) + len(delimiter_ids)
    budget = max(0, int(window) - int(stride) - lead_fixed)
    head = [bos_id] if bos_id is not None else []
    kept_prefix = list(prefix_ids[-budget:]) if budget else []
    lead = head + kept_prefix + list(delimiter_ids)
    if not lead:
        raise ValueError("scoring needs at least one leading token before the continuation")
    cont = list(cont_ids)
    return [
        (lead + cont[start : start + int(stride)], len(lead))
        for start in range(0, len(cont), int(stride))
    ]


def resolve_context_tokens(config: Any, *, default: int = DEFAULT_CONTEXT_TOKENS) -> int:
    """The context length a model config declares, in tokens."""
    fields = _config_fields(config)
    for name in CONTEXT_FIELDS:
        found = _positive_int(fields.get(name))
        if found is not None:
            return found
    for name in NESTED_CONFIG_FIELDS:
        nested = fields.get(name)
        if nested is not None and (found := resolve_context_tokens(nested, default=0)):
            return found
    return int(default)


def scoring_window(
    config: Any, requested: int | None, *, default: int = DEFAULT_CONTEXT_TOKENS
) -> int:
    """Tokens `HFBackend.score` works in: the model's context, capped by `requested`."""
    context = resolve_context_tokens(config, default=default)
    return min(int(requested), context) if requested else context


def tokenizer_vocabulary(tokenizer: Any) -> tuple[str, ...]:
    """The tokenizer's vocabulary in id order, special tokens dropped."""
    special = {str(t) for t in (getattr(tokenizer, "all_special_tokens", None) or ())}
    mapping = _vocab_mapping(tokenizer)
    if mapping is not None:
        ordered = sorted(mapping.items(), key=lambda item: (int(item[1]), str(item[0])))
        tokens = [str(token) for token, _ in ordered]
    else:
        tokens = _vocab_by_id(tokenizer)
    return tuple(token for token in tokens if token and token not in special)


def _config_fields(config: Any) -> Mapping[str, Any]:
    if isinstance(config, Mapping):
        return config
    to_dict = getattr(config, "to_dict", None)
    if callable(to_dict):
        fields = to_dict()
        if isinstance(fields, Mapping):
            return fields
    return dict(vars(config)) if hasattr(config, "__dict__") else {}


def _positive_int(value: Any) -> int | None:
    if isinstance(value, bool) or not isinstance(value, int | float):
        return None
    return int(value) if 0 < value < IMPLAUSIBLE_CONTEXT else None


def _vocab_mapping(tokenizer: Any) -> Mapping[str, Any] | None:
    getter = getattr(tokenizer, "get_vocab", None)
    raw = getter() if callable(getter) else getattr(tokenizer, "vocab", None)
    return raw if isinstance(raw, Mapping) else None


def _vocab_by_id(tokenizer: Any) -> list[str]:
    """Last resort: a tokenizer that reports a size but exposes no mapping."""
    size = _positive_int(getattr(tokenizer, "vocab_size", None))
    convert = getattr(tokenizer, "convert_ids_to_tokens", None)
    if size is None or not callable(convert):
        return []
    return [str(token) for token in convert(list(range(size))) if token is not None]


def logits_processors(
    params: DecodingParams
) -> list[Any]:
    """The `LogitsProcessor` list implementing `params`."""
    import torch
    from transformers import LogitsProcessor

    class TropeTruncation(LogitsProcessor):
        """Temperature, then `truncation_mask`, on the raw model logits."""

        def __init__(self, params: DecodingParams) -> None:
            self.params = params
            self.temperature = max(float(params.temperature), MIN_TEMPERATURE)

        def __call__(self, input_ids: Any, scores: Any) -> Any:
            scaled = scores.float() / self.temperature
            probs = torch.softmax(scaled, dim=-1).detach().cpu().numpy()
            keep = np.stack(
                [
                    truncation_mask(row, self.params)
                    for row in probs
                ]
            )
            blocked = torch.as_tensor(~keep, device=scores.device)
            return scaled.masked_fill(blocked, float("-inf"))

    return [TropeTruncation(params)]


class HFBackend:
    """Backend over a local `transformers` causal LM."""

    name = "hf"

    def __init__(
        self,
        model: str,
        *,
        revision: str | None = None,
        device: str | None = None,
        dtype: str = "auto",
        max_new_tokens: int = 1024,
        window: int | None = None,
        stride: int = 512,
        delimiter: str = DELIMITER,
        chat_template: bool = True,
        trust_remote_code: bool = False,
        cache_size: int = 4096,
    ) -> None:
        try:
            import torch
            from transformers import AutoModelForCausalLM, AutoTokenizer
        except ImportError as exc:
            raise MissingDependency("hf", "hf", exc) from exc

        self.model_id = str(model)
        self.revision = revision
        self.max_new_tokens = int(max_new_tokens)
        self.chat_template = bool(chat_template)
        self._cache_size = int(cache_size)
        self._cont_ids: dict[str, tuple[int, ...]] = {}
        self._token_counts: dict[str, int] = {}
        self._vocabulary: tuple[str, ...] | None = None
        self._torch = torch

        self._tokenizer = AutoTokenizer.from_pretrained(
            self.model_id, revision=revision, trust_remote_code=trust_remote_code
        )
        load: dict[str, Any] = {
            "revision": revision,
            "trust_remote_code": trust_remote_code,
            "torch_dtype": _torch_dtype(torch, dtype),
        }
        if device == "auto":
            load["device_map"] = "auto"
        self._model = AutoModelForCausalLM.from_pretrained(self.model_id, **load)
        if device != "auto":
            self._model.to(device or ("cuda" if torch.cuda.is_available() else "cpu"))
        self._model.eval()
        self._device = next(self._model.parameters()).device

        config = self._model.config
        self.model_context_tokens = resolve_context_tokens(config)
        self.window = scoring_window(config, window)
        self.stride = int(stride)
        self._delim_ids = self._encode(delimiter)
        if not self._delim_ids:
            raise ValueError("the scoring delimiter must tokenise to at least one token")
        bos = getattr(self._tokenizer, "bos_token_id", None)
        self._bos_id = int(bos) if bos is not None else None
        lead = (1 if self._bos_id is not None else 0) + len(self._delim_ids)
        if self.stride + lead > self.window:
            raise ValueError(
                f"a stride of {self.stride} does not fit a window of {self.window}"
            )
        self._resolved_revision = str(getattr(config, "_commit_hash", "") or revision or "")
        self._n_params, self._n_params_non_embedding = _parameter_counts(self._model)
        self._dtype_name = str(getattr(self._model, "dtype", dtype)).replace("torch.", "")

    def generate(
        self,
        prompt: str,
        params: DecodingParams,
        *,
        seed: int | None = None,
        role: str = "generator",
    ) -> Generation:
        torch = self._torch
        inputs = self._encode_prompt(prompt)
        prompt_tokens = int(inputs["input_ids"].shape[-1])
        sampling = float(params.temperature) > 0.0
        kwargs: dict[str, Any] = {
            "max_new_tokens": max(1, min(int(params.max_tokens), self.max_new_tokens)),
            "do_sample": sampling,
            "pad_token_id": self._pad_id(),
            "temperature": 1.0,
            "top_p": 1.0,
            "top_k": 0,
        }
        if sampling:
            kwargs["logits_processor"] = logits_processors(
                params
            )
        if seed is not None:
            torch.manual_seed(int(seed))
        with torch.inference_mode():
            out = self._model.generate(**inputs, **kwargs)
        new_ids = out[0, prompt_tokens:]
        text = self._tokenizer.decode(new_ids, skip_special_tokens=True)
        cut = _first_stop(text, params.stop)
        eos = bool(len(new_ids)) and int(new_ids[-1]) in self._eos_ids()
        if cut >= 0:
            text = text[:cut]
        finish = "stop" if (cut >= 0 or eos) else "length"
        return Generation(
            text=text,
            prompt_tokens=prompt_tokens,
            completion_tokens=int(len(new_ids)),
            finish_reason=finish,
            meta={"role": role, "backend": self.name, "model": self.model_id, "seed": seed},
        )

    def _encode_prompt(self, prompt: str) -> dict[str, Any]:
        tok = self._tokenizer
        if self.chat_template and getattr(tok, "chat_template", None):
            text = tok.apply_chat_template(
                [{"role": "user", "content": prompt}],
                tokenize=False,
                add_generation_prompt=True,
            )
            batch = tok(text, return_tensors="pt", add_special_tokens=False)
        else:
            batch = tok(prompt, return_tensors="pt")
        return {k: v.to(self._device) for k, v in batch.items()}

    def _pad_id(self) -> int:
        tok = self._tokenizer
        for candidate in (tok.pad_token_id, tok.eos_token_id, self._bos_id):
            if candidate is not None:
                return int(candidate)
        return 0

    def _eos_ids(self) -> tuple[int, ...]:
        eos = getattr(self._tokenizer, "eos_token_id", None)
        if eos is None:
            return ()
        return tuple(int(e) for e in eos) if isinstance(eos, list | tuple) else (int(eos),)

    def score(self, continuation: str, prefix: str = "") -> ScoreResult:
        """Summed log P(continuation | prefix) over the continuation tokens."""
        cont_ids = self._continuation_ids(continuation)
        if not cont_ids:
            return ScoreResult(0.0, 0, np.zeros(0, dtype=np.float64))
        blocks = score_blocks(
            self._encode(prefix),
            cont_ids,
            bos_id=self._bos_id,
            delimiter_ids=self._delim_ids,
            window=self.window,
            stride=self.stride,
        )
        logprobs = np.concatenate(
            [self._block_logprobs(ids, offset) for ids, offset in blocks]
        )
        assert logprobs.size == len(cont_ids), (
            f"scored {logprobs.size} positions for {len(cont_ids)} continuation tokens"
        )
        return ScoreResult(float(logprobs.sum()), int(logprobs.size), logprobs)

    def _continuation_ids(self, text: str) -> list[int]:
        """Tokenise a continuation on its own, and check that it stays put."""
        ids = self._encode(text)
        seen = self._cont_ids.get(text)
        if seen is None:
            if len(self._cont_ids) < self._cache_size:
                self._cont_ids[text] = tuple(ids)
        else:
            assert tuple(ids) == seen, (
                "the same continuation tokenised into different ids with and "
                "without a prefix; the two terms of Nov would not be over the "
                "same tokens"
            )
        return ids

    def _block_logprobs(self, ids: Sequence[int], offset: int) -> np.ndarray:
        torch = self._torch
        with torch.inference_mode():
            tensor = torch.tensor([list(ids)], dtype=torch.long, device=self._device)
            logits = self._model(tensor).logits[0].float()
            logprobs = torch.log_softmax(logits[offset - 1 : -1], dim=-1)
            targets = tensor[0, offset:]
            picked = logprobs.gather(-1, targets.unsqueeze(-1)).squeeze(-1)
            return picked.detach().cpu().numpy().astype(np.float64)

    @property
    def context_tokens(self) -> int:
        """Tokens this backend scores in one context."""
        return self.window

    def vocabulary(self) -> tuple[str, ...]:
        """The tokenizer's vocabulary, for the null check of entry 26c."""
        if self._vocabulary is None:
            self._vocabulary = tokenizer_vocabulary(self._tokenizer)
        return self._vocabulary

    def count_tokens(self, text: str) -> int:
        cached = self._token_counts.get(text)
        if cached is not None:
            return cached
        n = len(self._encode(text))
        if len(self._token_counts) < self._cache_size:
            self._token_counts[text] = n
        return n

    def _encode(self, text: str) -> list[int]:
        if not text:
            return []
        return list(self._tokenizer(text, add_special_tokens=False)["input_ids"])

    def info(self) -> dict[str, Any]:
        """Identity of the loaded checkpoint, for the run manifest."""
        return {
            "backend": self.name,
            "model": self.model_id,
            "revision": self.revision,
            "resolved_revision": self._resolved_revision,
            "dtype": self._dtype_name,
            "device": str(self._device),
            "n_parameters": self._n_params,
            "n_parameters_non_embedding": self._n_params_non_embedding,
            "context_window": self.window,
            "model_context_tokens": self.model_context_tokens,
            "context_tokens": self.context_tokens,
            "score_stride": self.stride,
        }


def _torch_dtype(torch: Any, dtype: str | None) -> Any:
    if dtype is None or dtype == "auto":
        return "auto"
    resolved = getattr(torch, str(dtype), None)
    if resolved is None:
        raise ValueError(f"unknown dtype {dtype!r}")
    return resolved


def _parameter_counts(model: Any) -> tuple[int, int]:
    """Total parameters and total minus the embedding matrices."""
    total = int(sum(p.numel() for p in model.parameters()))
    embedding = 0
    inputs = model.get_input_embeddings()
    if inputs is not None:
        embedding += int(inputs.weight.numel())
    outputs = model.get_output_embeddings()
    if outputs is not None and inputs is not None and outputs.weight is not inputs.weight:
        embedding += int(outputs.weight.numel())
    return total, total - embedding


def _first_stop(text: str, stop: Sequence[str]) -> int:
    """Index of the earliest stop sequence in `text`, or -1."""
    best = -1
    for needle in stop:
        if not needle:
            continue
        found = text.find(needle)
        if found >= 0 and (best < 0 or found < best):
            best = found
    return best
