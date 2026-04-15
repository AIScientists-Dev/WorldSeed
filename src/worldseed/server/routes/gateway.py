"""Gateway management routes: /api/gateway/status, start, stop, restart."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI

from worldseed.server.routes._shared import (
    _gateway_status,
    _kill_gateway,
    _spawn_gateway,
)
from worldseed.server.websocket import ConnectionManager


def create_gateway_router(app: FastAPI, ws_manager: ConnectionManager) -> APIRouter:
    router = APIRouter()

    @router.get("/api/gateway/status")
    async def gateway_status() -> dict[str, Any]:
        """Get gateway process and connection status."""
        return _gateway_status(app, ws_manager)

    @router.post("/api/gateway/start")
    async def gateway_start() -> dict[str, Any]:
        """Start the OpenClaw gateway subprocess."""
        _spawn_gateway(app)
        return _gateway_status(app, ws_manager)

    @router.post("/api/gateway/stop")
    async def gateway_stop() -> dict[str, Any]:
        """Stop the OpenClaw gateway subprocess."""
        _kill_gateway(app)
        return _gateway_status(app, ws_manager)

    @router.post("/api/gateway/restart")
    async def gateway_restart() -> dict[str, Any]:
        """Restart the OpenClaw gateway subprocess."""
        _kill_gateway(app)
        _spawn_gateway(app)
        return _gateway_status(app, ws_manager)

    return router
