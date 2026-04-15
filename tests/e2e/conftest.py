"""Shared fixtures for end-to-end tests."""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import AsyncIterator
from pathlib import Path
from typing import Any

import httpx
import pytest
import pytest_asyncio
import uvicorn
from httpx import ASGITransport, AsyncClient

from tests.helpers import CONFIGS_DIR
from worldseed.persistence import RunRecorder
from worldseed.server.app import create_app
from worldseed.world import WorldEngine


def get_free_port() -> int:
    """Return an available TCP port selected by the OS."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def wait_for_server(base_url: str, timeout: float = 10.0) -> None:
    """Poll server /health until 200 or raise."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            r = httpx.get(f"{base_url}/health", timeout=0.5)
            if r.status_code == 200:
                return
        except Exception:
            pass
        time.sleep(0.1)
    raise RuntimeError(f"Server at {base_url} did not start within {timeout}s")


def start_uvicorn(app: Any, port: int) -> tuple[uvicorn.Server, threading.Thread]:
    """Start uvicorn in a daemon thread. Returns (server, thread)."""
    uvi_config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(uvi_config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    return server, thread


def stop_uvicorn(server: uvicorn.Server, thread: threading.Thread) -> None:
    """Signal uvicorn to exit and wait for the thread."""
    server.should_exit = True
    thread.join(timeout=5)


@pytest_asyncio.fixture
async def e2e_env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncIterator[dict[str, Any]]:
    """Full server environment: engine + app + async client + recorder.

    Starts the tick runner (real background ticks). Yields a dict with:
      client: httpx.AsyncClient (talks to the app via ASGI)
      engine: WorldEngine
      recorder: RunRecorder
      app: FastAPI app
      run_id: str
    """
    monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))

    config_path = CONFIGS_DIR / "bunker.yaml"
    run_id = "e2e_test"

    recorder = RunRecorder(
        run_id=run_id,
        config_path=config_path,
        scene_id="doomsday_bunker",
        dm_model="none",
    )

    engine = WorldEngine(config_path, recorder=recorder)
    app = create_app(
        engine,
        tick_interval=0.1,
        run_id=run_id,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        yield {
            "client": client,
            "engine": engine,
            "recorder": recorder,
            "app": app,
            "run_id": run_id,
            "run_dir": recorder.run_dir,
        }

    # Finalize after test
    recorder.save_final_state([e.to_dict() for e in engine.state.all_entities()])
    recorder.finalize(
        tick_count=engine.tick,
        agent_count=len(engine.get_registered_agents()),
    )
