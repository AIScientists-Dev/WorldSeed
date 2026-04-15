"""LiteLLM + Instructor DM provider.

Uses Instructor's response_model for structured output with
automatic Pydantic validation + intelligent retry (error feedback
sent back to LLM on validation failure).
"""

from __future__ import annotations

import time
from typing import Any

import structlog
from pydantic import BaseModel, Field

from worldseed.dm.prompt import build_system_prompt, build_user_message
from worldseed.models.config_schema import EffectConfig
from worldseed.protocol.dm import DMContext, DMResponse

log = structlog.get_logger()


class DMJudgment(BaseModel):
    """Structured DM output — validated by Instructor automatically.

    On validation failure, Instructor sends the Pydantic error back
    to the LLM and retries. This is the response_model.
    """

    narrative: str = Field(
        description=(
            "What physically happened (1-3 sentences). Describes actor + world only. NEVER mentions other agents."
        ),
    )
    effects: list[EffectConfig] = Field(
        default_factory=list,
        description="State changes to apply to the world",
    )


class LiteLLMDMProvider:
    """DM provider using LiteLLM + Instructor.

    model format: "provider/model"
    (e.g. "provider/model-name")
    """

    def __init__(
        self,
        model: str,
        timeout: float = 10.0,
        max_retries: int = 2,
        fallback_model: str | None = None,
    ) -> None:
        self._model = model
        self._timeout = timeout
        self._max_retries = max_retries
        self._fallback_model = fallback_model
        self._client: Any = None  # lazy-init Instructor client
        self.call_count: int = 0
        self.total_tokens: int = 0

    def _get_client(self) -> Any:
        """Get or create the cached Instructor client."""
        if self._client is None:
            import instructor
            import litellm

            self._client = instructor.from_litellm(
                litellm.acompletion,
                mode=instructor.Mode.TOOLS,
            )
        return self._client

    async def judge(self, context: DMContext) -> DMResponse:
        client = self._get_client()

        system = build_system_prompt(context)
        user = build_user_message(context)
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ]

        # Try primary model, fallback to secondary on failure
        models = [self._model]
        if self._fallback_model:
            models.append(self._fallback_model)

        start = time.monotonic()
        last_error: Exception | None = None

        for model in models:
            try:
                judgment = await client.chat.completions.create(
                    model=model,
                    response_model=DMJudgment,
                    messages=messages,
                    max_retries=self._max_retries,
                    timeout=self._timeout,
                )
                if model != self._model:
                    log.info("dm_fallback_used", fallback=model)
                break
            except Exception as e:
                log.warning(
                    "dm_llm_call_failed",
                    model=model,
                    elapsed_s=round(time.monotonic() - start, 2),
                    exc_info=True,
                )
                last_error = e
                continue
        else:
            raise last_error  # type: ignore[misc]

        elapsed = time.monotonic() - start

        # Extract token usage from instructor's raw response
        usage = getattr(judgment, "_raw_response", None)
        tokens_in = 0
        tokens_out = 0
        if usage is not None:
            u = getattr(usage, "usage", None)
            if u is not None:
                tokens_in = getattr(u, "prompt_tokens", 0)
                tokens_out = getattr(u, "completion_tokens", 0)

        self.call_count += 1
        self.total_tokens += tokens_in + tokens_out

        log.info(
            "dm_llm_call_ok",
            model=self._model,
            elapsed_s=round(elapsed, 2),
            effects_count=len(judgment.effects),
            narrative_len=len(judgment.narrative),
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )

        return DMResponse(
            narrative=judgment.narrative,
            effects=judgment.effects,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
        )
