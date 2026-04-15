"""Route package — registers all HTTP/WS routes on the FastAPI app."""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles

from worldseed.server.routes._shared import _UI_DIR
from worldseed.server.routes.agents import create_agents_router, register_websocket
from worldseed.server.routes.dashboard import create_dashboard_router
from worldseed.server.routes.gateway import create_gateway_router
from worldseed.server.routes.gazette import create_gazette_router
from worldseed.server.routes.gm import create_gm_router
from worldseed.server.routes.intro import create_intro_router
from worldseed.server.routes.runs import create_runs_router
from worldseed.server.routes.settings import create_settings_router
from worldseed.server.routes.world import create_world_router
from worldseed.server.websocket import ConnectionManager


def register_all_routes(app: FastAPI, ws_manager: ConnectionManager) -> None:
    """Mount static files, include all routers, register WebSocket endpoint."""

    # Static files — Vite build output (frontend/dist/)
    # Mount assets + configs at their expected paths
    _assets = _UI_DIR / "assets"
    _configs = _UI_DIR / "configs"
    if _assets.is_dir():
        app.mount("/assets", StaticFiles(directory=str(_assets)), name="assets")
    if _configs.is_dir():
        app.mount("/configs", StaticFiles(directory=str(_configs)), name="configs")

    # Include all routers
    app.include_router(create_dashboard_router(app, ws_manager))
    app.include_router(create_world_router(app, ws_manager))
    app.include_router(create_gateway_router(app, ws_manager))
    app.include_router(create_settings_router(app, ws_manager))
    app.include_router(create_agents_router(app, ws_manager))
    app.include_router(create_gm_router(app, ws_manager))
    app.include_router(create_gazette_router(app, ws_manager))
    app.include_router(create_runs_router(app, ws_manager))
    app.include_router(create_intro_router(app, ws_manager))
    # WebSocket must be registered directly on the app
    register_websocket(app, ws_manager)
