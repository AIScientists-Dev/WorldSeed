"""Shared fixtures for Playwright browser tests.

Each test gets a real uvicorn server (lobby mode) + a Playwright browser page.
Server uses a unique port and isolated tmp_path for persistence.
"""

from __future__ import annotations

import socket
import threading
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any

import httpx
import pytest
import uvicorn
from playwright.sync_api import Page

from tests.helpers import CONFIGS_DIR
from worldseed.server.app import create_app


def _get_free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("", 0))
        return s.getsockname()[1]


def _wait_for_server(base_url: str, timeout: float = 10.0) -> None:
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


@pytest.fixture(scope="function")
def server_url(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Generator[str]:
    """Start a real uvicorn server in lobby mode. Yields base URL."""
    monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))

    port = _get_free_port()
    app = create_app(engine=None, port=port)

    config = uvicorn.Config(app, host="127.0.0.1", port=port, log_level="warning")
    server = uvicorn.Server(config)
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()

    base_url = f"http://127.0.0.1:{port}"
    _wait_for_server(base_url)

    yield base_url

    server.should_exit = True
    thread.join(timeout=5)


@pytest.fixture
def dashboard(server_url: str, page: Page) -> Page:
    """Open the dashboard in a Playwright browser page. Returns the page."""
    page.goto(server_url)
    # Wait for React app to mount and render lobby
    page.wait_for_selector("[data-testid='app-root'], .setup-page, header", timeout=10000)
    return page


def start_world(
    base_url: str,
    config_name: str = "bunker.yaml",
    tick_interval: float = 60.0,
) -> dict[str, Any]:
    """Start a world via API. Returns response data."""
    config_path = str(CONFIGS_DIR / config_name)
    r = httpx.post(
        f"{base_url}/api/world/start",
        json={
            "config_path": config_path,
            "tick_interval": tick_interval,
        },
        timeout=10,
    )
    assert r.status_code == 200, f"Start failed: {r.status_code} {r.text}"
    return r.json()


def enter_dashboard(
    server_url: str,
    page: Page,
    *,
    step_first: bool = False,
    config_name: str = "bunker.yaml",
) -> dict[str, Any]:
    """Start world, navigate to map view. Optionally step once for perception data."""
    data = start_world(server_url, config_name=config_name, tick_interval=60.0)
    run_id = data["run_id"]
    if step_first:
        httpx.post(f"{server_url}/api/tick/step", json={}, timeout=5)
    page.goto(f"{server_url}/run/{run_id}/map")
    page.wait_for_selector("header", timeout=10000)
    return data


def stop_world(base_url: str) -> dict[str, Any]:
    """Stop the world via API."""
    r = httpx.post(f"{base_url}/api/world/stop", timeout=10)
    assert r.status_code == 200, f"Stop failed: {r.status_code} {r.text}"
    return r.json()
