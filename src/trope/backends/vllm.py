"""vLLM generation backend."""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import numpy as np

from trope.backends.base import DecodingParams, Generation, ScoreResult
from trope.backends.hf import MIN_TEMPERATURE, eta_mask, top_h_mask
from trope.backends.registry import MissingDependency


class VLLMBackend:
    """Backend over a vLLM engine, for generation."""

    name = "vllm"

    def __init__(
        self,
        model: str,
        *,
        revision: str | None = None,
        dtype: str = "auto",
        max_new_tokens: int = 1024,
        max_model_len: int | None = None,
        tensor_parallel_size: int = 1,
        gpu_memory_utilization: float = 0.90,
        chat_template: bool = True,
        trust_remote_code: bool = False,
        engine_kwargs: dict[str, Any] | None = None,
    ) -> None:
        try:
            import vllm
        except ImportError as exc:
            raise MissingDependency("vllm", "vllm", exc) from exc

        self.model_id = str(model)
        self.revision = revision
        self.max_new_tokens = int(max_new_tokens)
        self.chat_template = bool(chat_template)
        self._vllm = vllm
        self._llm = vllm.LLM(
            model=self.model_id,
            revision=revision,
            dtype=dtype,
            max_model_len=max_model_len,
            tensor_parallel_size=int(tensor_parallel_size),
            gpu_memory_utilization=float(gpu_memory_utilization),
            trust_remote_code=trust_remote_code,
            **(engine_kwargs or {}),
        )
        self._tokenizer = self._llm.get_tokenizer()

    def generate(
        self,
        prompt: str,
        params: DecodingParams,
        *,
        seed: int | None = None,
        role: str = "generator",
    ) -> Generation:
        sampling = self._sampling_params(params, seed)
        text = self._render(prompt)
        outputs = self._llm.generate([text], sampling, use_tqdm=False)
        completion = outputs[0].outputs[0]
        return Generation(
            text=completion.text,
            prompt_tokens=len(outputs[0].prompt_token_ids or ()),
            completion_tokens=len(completion.token_ids or ()),
            finish_reason=str(completion.finish_reason or "stop"),
            meta={
                "role": role,
                "backend": self.name,
                "model": self.model_id,
                "seed": seed,
                "reproducible": False,
            },
        )

    def _sampling_params(self, params: DecodingParams, seed: int | None) -> Any:
        kwargs: dict[str, Any] = {
            "n": 1,
            "temperature": max(float(params.temperature), 0.0),
            "top_p": 1.0 if params.top_p is None else float(params.top_p),
            "top_k": -1 if not params.top_k else int(params.top_k),
            "min_p": 0.0 if params.min_p is None else float(params.min_p),
            "max_tokens": max(1, min(int(params.max_tokens), self.max_new_tokens)),
            "stop": list(params.stop),
            "seed": None if seed is None else int(seed),
        }
        extra = _extra_processors(params)
        if not extra:
            return self._vllm.SamplingParams(**kwargs)
        try:
            return self._vllm.SamplingParams(logits_processors=extra, **kwargs)
        except (TypeError, ValueError) as exc:
            raise NotImplementedError(
                "top-H and eta-sampling need a vLLM build that accepts "
                f"per-request logits_processors ({exc}); run those operators on "
                "the hf backend"
            ) from exc

    def _render(self, prompt: str) -> str:
        tok = self._tokenizer
        if self.chat_template and getattr(tok, "chat_template", None):
            return tok.apply_chat_template(
                [{"role": "user", "content": prompt}],
                tokenize=False,
                add_generation_prompt=True,
            )
        return prompt

    def score(self, continuation: str, prefix: str = "") -> ScoreResult:
        raise NotImplementedError(
            "the vllm backend does not score: vLLM's prompt_logprobs path is "
            "version-dependent and the novelty score needs the tokenisation "
            "contract in backends/base.py. Run the reference LM on the hf "
            "backend (run.backend: hf)."
        )

    def count_tokens(self, text: str) -> int:
        if not text:
            return 0
        return len(self._tokenizer(text, add_special_tokens=False)["input_ids"])

    def info(self) -> dict[str, Any]:
        return {
            "backend": self.name,
            "model": self.model_id,
            "revision": self.revision,
            "vllm_version": str(getattr(self._vllm, "__version__", "")),
            "deterministic": False,
        }


def _extra_processors(
    params: DecodingParams,
) -> list[Any]:
    """Per-request processors for the two rules vLLM has no sampler for."""
    rules = [
        (eta_mask, params.eta),
        (top_h_mask, params.entropy_budget),
    ]
    active = [(rule, value) for rule, value in rules if value is not None]
    if not active:
        return []

    import torch

    temperature = max(float(params.temperature), MIN_TEMPERATURE)

    def build(rule: Any, value: float) -> Any:
        def processor(token_ids: Sequence[int], logits: Any) -> Any:
            probs = torch.softmax(logits.float() / temperature, dim=-1)
            keep = rule(probs.detach().cpu().numpy(), value)
            blocked = torch.as_tensor(~np.asarray(keep), device=logits.device)
            return logits.masked_fill(blocked, float("-inf"))

        return processor

    return [build(rule, value) for rule, value in active]
