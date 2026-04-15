"""DM Provider protocol — the interface any DM implementation must satisfy.

Zero imports beyond typing. Zero logic. Just the contract.
"""

from __future__ import annotations

from typing import Protocol

from worldseed.protocol.dm import DMContext, DMResponse


class DMProvider(Protocol):
    """Any object with an async judge() method is a DM.

    Implementations:
      - mock.py: deterministic (Phase 3, done)
      - DM currently uses mock; real LLM deferred (agents use OpenClaw's LLM)
    """

    async def judge(self, context: DMContext) -> DMResponse: ...
