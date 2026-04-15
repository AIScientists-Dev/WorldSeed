"""Mock DM providers for deterministic testing. Zero external deps."""

from __future__ import annotations

from worldseed.protocol.dm import DMContext, DMResponse


class MockDMProvider:
    """Returns pre-configured or default responses. No LLM calls.

    Tracks call_count and last_context for test assertions.
    """

    def __init__(
        self,
        responses: dict[str, DMResponse] | None = None,
        default_narrative: str = "The action succeeds without incident.",
    ) -> None:
        self._responses = responses or {}
        self._default_narrative = default_narrative
        self.call_count: int = 0
        self.last_context: DMContext | None = None

    async def judge(self, context: DMContext) -> DMResponse:
        self.call_count += 1
        self.last_context = context

        key = context.action.action_type
        if key in self._responses:
            return self._responses[key]

        return DMResponse(narrative=self._default_narrative)


class FailingMockDMProvider:
    """Fails N times, then returns a success response.

    For testing retry and fallback logic.
    """

    def __init__(
        self,
        fail_count: int,
        success_response: DMResponse,
    ) -> None:
        self._fail_count = fail_count
        self._success = success_response
        self.call_count: int = 0

    async def judge(self, context: DMContext) -> DMResponse:
        self.call_count += 1
        if self.call_count <= self._fail_count:
            msg = f"Simulated LLM failure (call {self.call_count})"
            raise ValueError(msg)
        return self._success
