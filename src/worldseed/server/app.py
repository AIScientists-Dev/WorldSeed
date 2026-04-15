"""HTTP + WebSocket Server — FastAPI app factory.

Supports two modes:
1. Lobby mode: server starts empty, user configures via dashboard
2. Pre-configured: engine passed in (for `worldseed play` CLI)
"""

from __future__ import annotations

import json
import os
import secrets
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

from fastapi import FastAPI

from worldseed.paths import discovery_file
from worldseed.server.tick_runner import TickRunner
from worldseed.server.websocket import ConnectionManager
from worldseed.world import WorldEngine


def _write_discovery(port: int) -> None:
    """Write server.json so the OpenClaw plugin can auto-discover us."""
    from worldseed.server.routes._shared import DEFAULT_GATEWAY_TOKEN

    df = discovery_file()
    df.parent.mkdir(parents=True, exist_ok=True)
    df.write_text(
        json.dumps(
            {
                "url": f"ws://localhost:{port}/ws",
                "token": DEFAULT_GATEWAY_TOKEN,
                "pid": os.getpid(),
            }
        )
    )


def _remove_discovery() -> None:
    """Remove server.json on shutdown."""
    try:
        discovery_file().unlink(missing_ok=True)
    except OSError:
        pass


def create_app(
    engine: WorldEngine | None = None,
    tick_interval: float = 1.0,
    run_id: str = "",
    port: int = 8000,
    auto_start_tick: bool = True,
) -> FastAPI:
    """Create a FastAPI app, optionally pre-wired to an engine.

    If engine is None, starts in lobby mode — dashboard shows Setup page.
    If engine is provided, starts in running mode immediately.

    auto_start_tick: if False, tick_runner is created but NOT started on
    app startup. Used by `play` command where tick starts only after all
    agents self-register via WebSocket.
    """
    if run_id and not run_id.strip():
        run_id = ""

    tick_runner = TickRunner(engine, interval=tick_interval) if engine else None
    ws_manager = ConnectionManager()

    @asynccontextmanager
    async def lifespan(app: FastAPI) -> AsyncIterator[None]:
        _write_discovery(port)
        from worldseed.server.routes._shared import _update_openclaw_config

        _update_openclaw_config(port)
        if app.state.tick_runner is not None and app.state.auto_start_tick:
            await app.state.tick_runner.start()
        yield
        if app.state.tick_runner is not None:
            await app.state.tick_runner.stop()
            active_connector = app.state.tick_runner.connector
            if active_connector is not None:
                await active_connector.close()
        _remove_discovery()

    app = FastAPI(title="WorldSeed", lifespan=lifespan)

    # Core state — engine can be None (lobby mode)
    app.state.engine = engine
    app.state.tick_runner = tick_runner
    app.state.ws_manager = ws_manager
    app.state.run_id = run_id or (secrets.token_hex(4) if engine else "")
    app.state.port = port
    app.state.gateway_proc = None
    app.state.agents_ready = set()
    app.state.initial_wakes_sent = False
    app.state.auto_start_tick = auto_start_tick
    # Demo mode: WORLDSEED_DEMO="zh:abc123,en:def456" or "abc123" (single)
    demo_raw = os.environ.get("WORLDSEED_DEMO", "")
    demo_runs: dict[str, str] = {}
    if demo_raw:
        for part in demo_raw.split(","):
            part = part.strip()
            if ":" in part:
                lang, rid = part.split(":", 1)
                demo_runs[lang.strip()] = rid.strip()
            else:
                demo_runs["default"] = part
    app.state.demo_runs = demo_runs

    # Settings that can be changed at runtime — seed from config when available
    _scene = engine.config.scene if engine else None
    app.state.settings = {
        "dm_model": "",
        "dm_fallback": "",
        "max_ticks": _scene.max_ticks if _scene else None,
        "timeout_min": _scene.timeout_min if _scene else None,
        "max_dm_calls": _scene.max_dm_calls if _scene else None,
        "tick_interval": tick_interval,
        "narrator_style": "",
        "narrator_prompt": "",
        "openclaw_dir": "",
    }

    # Register HTTP/WS routes
    from worldseed.server.routes import register_all_routes

    register_all_routes(app, ws_manager=ws_manager)

    return app
