"""E2E: Gateway management APIs + health status states on a REAL uvicorn server.

Tests gateway process lifecycle (start/stop/restart), health status
transitions (lobby/ready/live/paused), and world start/resume/step
interactions with tick state.

Uses real uvicorn in a thread with real httpx calls on a dynamic port.
"""

from __future__ import annotations

import time
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from worldseed.server.app import create_app

from .conftest import (
    CONFIGS_DIR,
    get_free_port,
    start_uvicorn,
    stop_uvicorn,
    wait_for_server,
)


@pytest.fixture
def gateway_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    """Start a real uvicorn server in LOBBY mode, yield env, shut down."""
    monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))

    port = get_free_port()
    app = create_app(engine=None, port=port)

    server, thread = start_uvicorn(app, port)
    base_url = f"http://127.0.0.1:{port}"
    wait_for_server(base_url)

    yield {
        "base_url": base_url,
        "tmp_path": tmp_path,
        "app": app,
    }

    # Shutdown
    stop_uvicorn(server, thread)


def _start_world(
    base: str,
    config_name: str = "bunker.yaml",
    tick_interval: float = 60.0,
) -> dict[str, Any]:
    """Helper: POST /api/world/start with the given config."""
    config_path = str(CONFIGS_DIR / config_name)
    r = httpx.post(
        f"{base}/api/world/start",
        json={
            "config_path": config_path,
            "tick_interval": tick_interval,
        },
        timeout=10,
    )
    assert r.status_code == 200, f"Start failed: {r.status_code} {r.text}"
    result: dict[str, Any] = r.json()
    return result


def _stop_world(base: str) -> dict[str, Any]:
    """Helper: POST /api/world/stop."""
    r = httpx.post(f"{base}/api/world/stop", timeout=10)
    assert r.status_code == 200, f"Stop failed: {r.status_code} {r.text}"
    result: dict[str, Any] = r.json()
    return result


# ── Health Status States ─────────────────────────────────────────────


class TestHealthStates:
    """Test /health status transitions: lobby → ready → live → paused."""

    def test_health_lobby_state(self, gateway_server: dict[str, Any]) -> None:
        """No world started → status='lobby'."""
        r = httpx.get(f"{gateway_server['base_url']}/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "lobby"
        assert data["tick"] == 0
        assert data["running"] is False

    def test_health_ready_state(self, gateway_server: dict[str, Any]) -> None:
        """After world/start but before resume → status='ready'."""
        base = gateway_server["base_url"]
        _start_world(base)

        r = httpx.get(f"{base}/health")
        data = r.json()
        assert data["status"] == "ready"
        assert data["tick"] == 0
        assert data["running"] is False

    def test_health_live_state(self, gateway_server: dict[str, Any]) -> None:
        """After resume → status='live'."""
        base = gateway_server["base_url"]
        _start_world(base)

        # Resume ticks
        r = httpx.post(f"{base}/api/tick/resume", timeout=10)
        assert r.status_code == 200

        # Give tick runner a moment to start
        time.sleep(0.5)

        r = httpx.get(f"{base}/health")
        data = r.json()
        assert data["status"] == "live"
        assert data["running"] is True

    def test_health_paused_state(self, gateway_server: dict[str, Any]) -> None:
        """After pause → status='paused'."""
        base = gateway_server["base_url"]
        _start_world(base)

        # Resume then pause — need at least one tick so we get 'paused' not 'ready'
        httpx.post(f"{base}/api/tick/resume", timeout=10)
        time.sleep(0.5)
        httpx.post(f"{base}/api/tick/pause", timeout=10)

        # Wait for tick runner to stop
        time.sleep(0.3)

        r = httpx.get(f"{base}/health")
        data = r.json()
        assert data["status"] == "paused"
        assert data["running"] is False

    def test_health_has_gateway_field(self, gateway_server: dict[str, Any]) -> None:
        """Health response always includes 'gateway' object."""
        base = gateway_server["base_url"]
        r = httpx.get(f"{base}/health")
        data = r.json()
        assert "gateway" in data
        gw = data["gateway"]
        assert "process_alive" in gw
        assert "pid" in gw
        assert "ws_connections" in gw
        assert "connected" in gw

    def test_health_has_run_id(self, gateway_server: dict[str, Any]) -> None:
        """Health response includes run_id when running."""
        base = gateway_server["base_url"]

        # In lobby, run_id is None
        r = httpx.get(f"{base}/health")
        assert r.json()["run_id"] is None

        # After start, run_id is set
        start_data = _start_world(base)
        r = httpx.get(f"{base}/health")
        data = r.json()
        assert data["run_id"] is not None
        assert data["run_id"] == start_data["run_id"]


# ── Gateway Management ───────────────────────────────────────────────


class TestGatewayManagement:
    """Test gateway process management endpoints."""

    def test_gateway_status_in_lobby(self, gateway_server: dict[str, Any]) -> None:
        """GET /api/gateway/status in lobby → process_alive=False, connected=False."""
        base = gateway_server["base_url"]
        r = httpx.get(f"{base}/api/gateway/status")
        assert r.status_code == 200
        data = r.json()
        assert data["process_alive"] is False
        assert data["connected"] is False
        assert data["pid"] is None
        assert data["ws_connections"] == 0

    def test_gateway_start_spawns_process(self, gateway_server: dict[str, Any]) -> None:
        """POST /api/gateway/start → either process_alive=True (openclaw installed)
        or process_alive=False (not installed). Both are acceptable."""
        base = gateway_server["base_url"]
        r = httpx.post(f"{base}/api/gateway/start", timeout=10)
        assert r.status_code == 200
        data = r.json()
        # openclaw may or may not be installed — both outcomes valid
        assert isinstance(data["process_alive"], bool)
        assert isinstance(data["connected"], bool)
        if data["process_alive"]:
            assert data["pid"] is not None
        else:
            assert data["pid"] is None

    def test_gateway_stop(self, gateway_server: dict[str, Any]) -> None:
        """Start then stop → process_alive=False."""
        base = gateway_server["base_url"]
        httpx.post(f"{base}/api/gateway/start", timeout=10)
        r = httpx.post(f"{base}/api/gateway/stop", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["process_alive"] is False
        assert data["pid"] is None

    def test_gateway_restart(self, gateway_server: dict[str, Any]) -> None:
        """Restart → process_alive stays True (or False if not installed)."""
        base = gateway_server["base_url"]
        r = httpx.post(f"{base}/api/gateway/restart", timeout=10)
        assert r.status_code == 200
        data = r.json()
        # Same as start: accept both outcomes
        assert isinstance(data["process_alive"], bool)
        assert isinstance(data["connected"], bool)

    def test_gateway_status_after_world_start(self, gateway_server: dict[str, Any]) -> None:
        """world/start auto-spawns gateway → check status reflects it."""
        base = gateway_server["base_url"]
        _start_world(base)

        r = httpx.get(f"{base}/api/gateway/status")
        assert r.status_code == 200
        data = r.json()
        # tick/resume calls _spawn_gateway, so it attempted to start
        # If openclaw not installed, process_alive=False is fine
        assert isinstance(data["process_alive"], bool)
        assert isinstance(data["ws_connections"], int)

    def test_world_stop_kills_gateway(self, gateway_server: dict[str, Any]) -> None:
        """Stop world → gateway process killed."""
        base = gateway_server["base_url"]
        _start_world(base)

        # Verify gateway was at least attempted
        r = httpx.get(f"{base}/api/gateway/status")
        assert r.status_code == 200

        _stop_world(base)

        r = httpx.get(f"{base}/api/gateway/status")
        data = r.json()
        assert data["process_alive"] is False
        assert data["pid"] is None


# ── World Start Does NOT Auto-tick ───────────────────────────────────


class TestWorldStartNoAutoTick:
    """Verify that world/start creates engine but does NOT auto-start ticks."""

    def test_world_start_no_auto_tick(self, gateway_server: dict[str, Any]) -> None:
        """After world/start, tick=0, running=False."""
        base = gateway_server["base_url"]
        _start_world(base)

        r = httpx.get(f"{base}/health")
        data = r.json()
        assert data["tick"] == 0
        assert data["running"] is False
        assert data["status"] == "ready"

    def test_resume_starts_ticks(self, gateway_server: dict[str, Any]) -> None:
        """POST /api/tick/resume → running=True, ticks advance."""
        base = gateway_server["base_url"]
        # Use short interval so ticks actually advance
        _start_world(base, tick_interval=0.1)

        r = httpx.get(f"{base}/health")
        assert r.json()["tick"] == 0
        assert r.json()["running"] is False

        # Resume
        r = httpx.post(f"{base}/api/tick/resume", timeout=10)
        assert r.status_code == 200

        # Wait for some ticks to advance
        time.sleep(1.0)

        r = httpx.get(f"{base}/health")
        data = r.json()
        assert data["running"] is True
        assert data["tick"] > 0, "Ticks should have advanced after resume"

    def test_step_works_in_ready_state(self, gateway_server: dict[str, Any]) -> None:
        """POST /api/tick/step in ready state → tick=1."""
        base = gateway_server["base_url"]
        _start_world(base)

        # Confirm ready state (tick=0, not running)
        r = httpx.get(f"{base}/health")
        assert r.json()["tick"] == 0
        assert r.json()["running"] is False

        # Step manually
        r = httpx.post(f"{base}/api/tick/step", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["tick"] == 1

        # Health confirms tick advanced but still not auto-running
        r = httpx.get(f"{base}/health")
        assert r.json()["tick"] == 1
        assert r.json()["running"] is False


# ── Gateway + WS Connection ──────────────────────────────────────────


class TestGatewayConnection:
    """Test gateway.connected field reflects actual WS state."""

    def test_gateway_connected_field(self, gateway_server: dict[str, Any]) -> None:
        """gateway.connected is False since no real OpenClaw connects in tests."""
        base = gateway_server["base_url"]
        _start_world(base)

        r = httpx.get(f"{base}/api/gateway/status")
        data = r.json()
        # No real gateway WS connection in test environment
        assert data["connected"] is False
        assert data["ws_connections"] == 0

        # Also verify via /health gateway sub-object
        r = httpx.get(f"{base}/health")
        gw = r.json()["gateway"]
        assert gw["connected"] is False
        assert gw["ws_connections"] == 0
