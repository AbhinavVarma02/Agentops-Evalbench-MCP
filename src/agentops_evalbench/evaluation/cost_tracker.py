"""Token counting and cost estimation.

Two responsibilities:

1. ``count_tokens`` — count tokens with ``tiktoken`` when available, else a
   deterministic heuristic (so cost tracking works without the dependency).
2. ``estimate_cost`` — turn a token-usage dict into a USD estimate using a small
   pricing table. Prices are approximate public OpenAI list prices and live in
   one place (``MODEL_PRICING``) so they are easy to update.

Cost is one of the deployment-readiness signals: switching to a bigger model
raises both latency and cost per answer, and this module makes that visible.
"""

from __future__ import annotations

# USD price per 1,000 tokens as (input, output). Output is None for embeddings.
# Source: approximate OpenAI list pricing; adjust here if prices change.
MODEL_PRICING: dict[str, tuple[float, float | None]] = {
    "gpt-4o-mini": (0.00015, 0.00060),
    "gpt-4o": (0.00250, 0.01000),
    "gpt-4.1-mini": (0.00040, 0.00160),
    "gpt-4.1": (0.00200, 0.00800),
    "gpt-4-turbo": (0.01000, 0.03000),
    "gpt-3.5-turbo": (0.00050, 0.00150),
    "text-embedding-3-small": (0.00002, None),
    "text-embedding-3-large": (0.00013, None),
}

# Used when a model is not found in the table (keeps estimates non-zero).
_FALLBACK_PRICING: tuple[float, float] = (0.00050, 0.00150)


def _normalize_model(model: str) -> str:
    """Map a raw model string to a pricing key.

    Strips decorations like the "(offline-extractive)" suffix the RAG pipeline
    adds, then prefers an exact match, else the longest matching known prefix.
    """
    name = (model or "").split("(")[0].strip().lower()
    if name in MODEL_PRICING:
        return name
    candidates = [key for key in MODEL_PRICING if name.startswith(key)]
    if candidates:
        return max(candidates, key=len)
    return name


def count_tokens(text: str, model: str = "gpt-4o-mini") -> int:
    """Return the number of tokens in ``text`` for ``model``.

    Uses tiktoken's model-specific encoding when possible, falling back to the
    ``o200k_base``/``cl100k_base`` encodings, and finally to a ~1.3-tokens-per-word
    heuristic if tiktoken is not installed.
    """
    if not text:
        return 0
    try:
        import tiktoken  # lazy import (optional dependency)

        try:
            enc = tiktoken.encoding_for_model(_normalize_model(model))
        except Exception:
            try:
                enc = tiktoken.get_encoding("o200k_base")
            except Exception:
                enc = tiktoken.get_encoding("cl100k_base")
        return len(enc.encode(text))
    except Exception:
        return max(1, round(len(text.split()) * 1.3))


def estimate_cost_from_counts(
    prompt_tokens: int, completion_tokens: int, model: str = "gpt-4o-mini"
) -> float:
    """Estimate USD cost from explicit prompt/completion token counts."""
    key = _normalize_model(model)
    input_price, output_price = MODEL_PRICING.get(key, _FALLBACK_PRICING)
    output_price = output_price if output_price is not None else 0.0
    cost = (prompt_tokens / 1000.0) * input_price + (completion_tokens / 1000.0) * output_price
    return round(cost, 8)


def estimate_cost(token_usage: dict | None, model: str = "gpt-4o-mini") -> float:
    """Estimate USD cost from a ``{"prompt", "completion", "total"}`` dict."""
    if not token_usage:
        return 0.0
    prompt = int(token_usage.get("prompt", 0) or 0)
    completion = int(token_usage.get("completion", 0) or 0)
    return estimate_cost_from_counts(prompt, completion, model)


def build_token_usage(prompt_text: str, completion_text: str, model: str) -> dict[str, int]:
    """Convenience: count tokens for a prompt/completion pair into a usage dict."""
    prompt = count_tokens(prompt_text, model)
    completion = count_tokens(completion_text, model)
    return {"prompt": prompt, "completion": completion, "total": prompt + completion}
