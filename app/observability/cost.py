"""LLM token and cost tracking via LangChain callbacks.

Attaches to a workflow invocation and accumulates prompt + completion tokens
across every LLM call.  Cost is estimated post-hoc using a per-model pricing
table (USD per 1 000 tokens).
"""

from __future__ import annotations

from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

# ── Pricing table: (input $/1k tokens, output $/1k tokens) ──────────────────
# Prices sourced from provider docs; update as needed.
_PRICING: dict[str, tuple[float, float]] = {
    # OpenAI
    "gpt-4o":                (0.0025,  0.010),
    "gpt-4o-mini":           (0.00015, 0.0006),
    "gpt-4-turbo":           (0.010,   0.030),
    "gpt-4":                 (0.030,   0.060),
    "gpt-3.5-turbo":         (0.0005,  0.0015),
    # DeepSeek
    "deepseek-chat":         (0.00014, 0.00028),
    "deepseek-reasoner":     (0.00055, 0.00219),
}

_DEFAULT_PRICING = (0.002, 0.002)  # conservative fallback


def _pricing_for(model_name: str | None) -> tuple[float, float]:
    if not model_name:
        return _DEFAULT_PRICING
    key = model_name.lower()
    for name, rates in _PRICING.items():
        if key.startswith(name):
            return rates
    return _DEFAULT_PRICING


def estimate_cost_usd(
    prompt_tokens: int,
    completion_tokens: int,
    model_name: str | None,
) -> float:
    """Return an estimated USD cost for the given token counts."""
    input_rate, output_rate = _pricing_for(model_name)
    return (prompt_tokens * input_rate + completion_tokens * output_rate) / 1000.0


class TokenCostCallback(BaseCallbackHandler):
    """Accumulates token usage across all LLM calls in a single workflow run."""

    def __init__(self) -> None:
        super().__init__()
        self.prompt_tokens: int = 0
        self.completion_tokens: int = 0
        self._last_model: str | None = None

    # LangChain fires this after every LLM response
    def on_llm_end(self, response: LLMResult, **kwargs: Any) -> None:
        usage = (response.llm_output or {}).get("token_usage", {})
        self.prompt_tokens += int(usage.get("prompt_tokens", 0))
        self.completion_tokens += int(usage.get("completion_tokens", 0))
        # Keep track of the last model used (for cost estimation)
        model = (response.llm_output or {}).get("model_name")
        if model:
            self._last_model = model

    @property
    def total_tokens(self) -> int:
        return self.prompt_tokens + self.completion_tokens

    def cost_usd(self, model_name: str | None = None) -> float:
        return estimate_cost_usd(
            self.prompt_tokens,
            self.completion_tokens,
            model_name or self._last_model,
        )
