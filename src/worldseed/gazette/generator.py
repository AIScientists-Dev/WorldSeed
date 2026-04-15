"""LLM gazette generator using LiteLLM + Instructor."""

from __future__ import annotations

import time
from typing import Any

import structlog

from worldseed.gazette.schema import GazetteContent

log = structlog.get_logger()


async def generate_gazette(
    context: str,
    system_prompt: str,
    model: str,
    timeout: float = 120.0,
    max_retries: int = 2,
) -> tuple[GazetteContent, dict[str, Any]]:
    """Call LLM to generate gazette content.

    Returns (parsed_content, metadata) where metadata includes
    model, elapsed_s, tokens_in, tokens_out, cost_usd.
    """
    import instructor
    import litellm

    client = instructor.from_litellm(litellm.acompletion, mode=instructor.Mode.JSON)

    start = time.monotonic()
    result = await client.chat.completions.create(
        model=model,
        response_model=GazetteContent,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": context},
        ],
        max_retries=max_retries,
        timeout=timeout,
    )
    elapsed = time.monotonic() - start

    # Extract token usage from Instructor's raw response
    tokens_in = tokens_out = 0
    raw = getattr(result, "_raw_response", None)
    if raw is not None:
        u = getattr(raw, "usage", None)
        if u is not None:
            tokens_in = getattr(u, "prompt_tokens", 0)
            tokens_out = getattr(u, "completion_tokens", 0)

    # Compute cost via LiteLLM's price database
    cost_usd = 0.0
    if raw is not None:
        try:
            cost_usd = litellm.completion_cost(completion_response=raw)
        except Exception:
            log.warning("gazette_cost_failed", model=model)

    meta: dict[str, Any] = {
        "model": model,
        "elapsed_s": round(elapsed, 2),
        "tokens_in": tokens_in,
        "tokens_out": tokens_out,
        "cost_usd": round(cost_usd, 6),
    }

    log.info(
        "gazette_generated",
        model=model,
        elapsed_s=meta["elapsed_s"],
        tokens_in=tokens_in,
        tokens_out=tokens_out,
        cost_usd=meta["cost_usd"],
    )

    return result, meta


def estimate_tokens(
    context: str,
    system_prompt: str,
    model: str,
) -> dict[str, Any]:
    """Estimate input tokens and cost without making an LLM call."""
    import litellm

    input_tokens = litellm.token_counter(model=model, text=system_prompt + context)
    estimated_output = 3000  # typical gazette output

    # Look up pricing from LiteLLM's model cost map
    cost_usd = 0.0
    try:
        cost_map = litellm.get_model_cost_map("")  # type: ignore[attr-defined]
        # Search for model in cost map (handles provider prefixes)
        model_name = model.split("/")[-1]
        matched_info: dict[str, Any] | None = None
        for key in cost_map:
            if model_name in key:
                matched_info = cost_map[key]
                break
        if matched_info:
            input_rate = matched_info.get("input_cost_per_token", 0)
            output_rate = matched_info.get("output_cost_per_token", 0)
            cost_usd = input_tokens * input_rate + estimated_output * output_rate
    except Exception:
        pass

    return {
        "input_tokens": input_tokens,
        "estimated_output_tokens": estimated_output,
        "estimated_cost_usd": round(cost_usd, 4),
        "model": model,
    }
