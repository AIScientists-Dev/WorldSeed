"""ConnectorProvider protocol — push notifications to agents.

Push model: tick runner checks each tick, calls
connector.notify() to tell agents something happened.
Wake includes perception data so agent can act immediately.
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ConnectorProvider(Protocol):
    """Interface for pushing notifications to external agents."""

    async def notify(self, agent_id: str, reason: str, perception: dict[str, Any] | None = None) -> None:
        """Notify an agent with reason + optional perception data."""
        ...

    async def close(self) -> None:
        """Clean up resources (e.g. HTTP sessions)."""
        ...
