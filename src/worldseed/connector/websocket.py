"""WebSocket connector — push wake signals through gateway connections.

Instead of POSTing to an external gateway, this connector sends wake
signals through the WebSocket connections managed by ConnectionManager.
Wake signals are broadcast to all connected gateways — the gateway
that manages the agent will handle it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from worldseed.server.websocket import ConnectionManager

log = structlog.get_logger()


class WebSocketConnector:
    """Push wake signals through active gateway WebSocket connections."""

    def __init__(self, manager: ConnectionManager) -> None:
        self._manager = manager

    async def notify(self, agent_id: str, reason: str, perception: dict[str, Any] | None = None) -> None:
        """Send wake signal + perception data to gateways via WebSocket.

        Raises ConnectionError if no gateway is connected, so the caller
        (tick_runner) knows delivery failed and can retry or log.
        """
        delivered = await self._manager.send_wake(agent_id, reason, perception)
        if delivered:
            log.info("ws_wake_sent", agent=agent_id, reason=reason)
        else:
            raise ConnectionError(f"No gateway connection for wake to {agent_id}")

    async def close(self) -> None:
        """Nothing to clean up — connections are managed by the server."""
