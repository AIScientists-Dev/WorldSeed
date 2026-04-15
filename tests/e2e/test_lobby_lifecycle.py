"""E2E: Lobby → Start → Run → Stop → Restart lifecycle on a REAL uvicorn server.

Tests the full server lifecycle starting from lobby mode (no engine),
through world start/stop/restart, GM controls, settings, and stress.
Uses real uvicorn in a thread with real httpx calls.
"""

from __future__ import annotations

import json
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
def lobby_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    """Start a real uvicorn server in LOBBY mode (engine=None), yield env, shut down."""
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
    return r.json()


def _stop_world(base: str) -> dict[str, Any]:
    """Helper: POST /api/world/stop."""
    r = httpx.post(f"{base}/api/world/stop", timeout=10)
    assert r.status_code == 200, f"Stop failed: {r.status_code} {r.text}"
    return r.json()


# ── Lifecycle Tests ──────────────────────────────────────────────────


class TestLifecycle:
    """Test world start/stop/restart lifecycle."""

    def test_health_returns_lobby(self, lobby_server: dict[str, Any]) -> None:
        """In lobby mode, /health returns status=lobby, tick=0, running=False."""
        r = httpx.get(f"{lobby_server['base_url']}/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] == "lobby"
        assert data["tick"] == 0
        assert data["running"] is False

    def test_world_start_from_lobby(self, lobby_server: dict[str, Any]) -> None:
        """POST /api/world/start with bunker.yaml returns run_id, scene_id, agents."""
        base = lobby_server["base_url"]
        data = _start_world(base)
        assert "run_id" in data
        assert data["scene_id"] == "doomsday_bunker"
        assert data["agents"] >= 1
        assert data["tick_interval"] == 60.0

    def test_health_after_start(self, lobby_server: dict[str, Any]) -> None:
        """/health returns ready (ticks not started yet) after world/start."""
        base = lobby_server["base_url"]
        _start_world(base)

        r = httpx.get(f"{base}/health")
        data = r.json()
        assert data["status"] in ("ready", "live", "paused")
        assert isinstance(data["tick"], int)
        assert data["tick"] >= 0
        assert data["scene"] == "doomsday_bunker"

        # Start ticks manually

        httpx.post(f"{base}/api/tick/resume")
        time.sleep(1)
        r = httpx.get(f"{base}/health")
        assert r.json()["running"] is True

    def test_agents_auto_registered(self, lobby_server: dict[str, Any]) -> None:
        """After start, GET /characters shows agents as claimed."""
        base = lobby_server["base_url"]
        _start_world(base)

        r = httpx.get(f"{base}/characters")
        assert r.status_code == 200
        chars = r.json()
        assert len(chars) >= 1
        # Bunker has old_chen, xiao_li, doctor_wang
        ids = {c["id"] for c in chars}
        assert "old_chen" in ids
        # All should be claimed since register_from_config runs on start
        for c in chars:
            assert c["claimed"] is True, f"Agent {c['id']} should be claimed"

    def test_world_stop(self, lobby_server: dict[str, Any]) -> None:
        """POST /api/world/stop returns stopped=True and run_id."""
        base = lobby_server["base_url"]
        start_data = _start_world(base)
        run_id = start_data["run_id"]

        data = _stop_world(base)
        assert data["stopped"] is True
        assert data["run_id"] == run_id

    def test_health_after_stop(self, lobby_server: dict[str, Any]) -> None:
        """/health returns status=lobby after stop."""
        base = lobby_server["base_url"]
        _start_world(base)
        _stop_world(base)

        r = httpx.get(f"{base}/health")
        data = r.json()
        assert data["status"] == "lobby"
        assert data["tick"] == 0
        assert data["running"] is False

    def test_restart_different_config(self, lobby_server: dict[str, Any]) -> None:
        """Start bunker -> stop -> start minimal -> verify different scene_id."""
        base = lobby_server["base_url"]
        data1 = _start_world(base, "bunker.yaml")
        assert data1["scene_id"] == "doomsday_bunker"
        _stop_world(base)

        data2 = _start_world(base, "minimal.yaml")
        assert data2["scene_id"] == "test_minimal"
        assert data2["run_id"] != data1["run_id"]

        r = httpx.get(f"{base}/health")
        assert r.json()["scene"] == "test_minimal"

    def test_double_start_returns_409(self, lobby_server: dict[str, Any]) -> None:
        """POST /api/world/start twice -> second returns 409."""
        base = lobby_server["base_url"]
        _start_world(base)

        config_path = str(CONFIGS_DIR / "bunker.yaml")
        r = httpx.post(
            f"{base}/api/world/start",
            json={"config_path": config_path, "tick_interval": 60.0},
            timeout=10,
        )
        assert r.status_code == 409

    def test_stop_without_start_returns_400(self, lobby_server: dict[str, Any]) -> None:
        """POST /api/world/stop in lobby -> 400."""
        base = lobby_server["base_url"]
        r = httpx.post(f"{base}/api/world/stop", timeout=10)
        assert r.status_code == 400


# ── Settings Tests ───────────────────────────────────────────────────


class TestSettings:
    """Test settings get/update."""

    def test_get_settings(self, lobby_server: dict[str, Any]) -> None:
        """GET /api/settings returns current settings dict."""
        base = lobby_server["base_url"]
        r = httpx.get(f"{base}/api/settings")
        assert r.status_code == 200
        data = r.json()
        assert "settings" in data
        assert "tick_interval" in data["settings"]
        assert data["running"] is False

    def test_update_hot_settings(self, lobby_server: dict[str, Any]) -> None:
        """PATCH /api/settings with tick_interval, max_ticks -> verify changed."""
        base = lobby_server["base_url"]
        _start_world(base, tick_interval=60.0)

        r = httpx.patch(
            f"{base}/api/settings",
            json={"tick_interval": 30.0, "max_ticks": 100},
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert "tick_interval" in data["changed"]
        assert "max_ticks" in data["changed"]
        assert data["settings"]["tick_interval"] == 30.0
        assert data["settings"]["max_ticks"] == 100

    def test_update_dm_model(self, lobby_server: dict[str, Any]) -> None:
        """PATCH /api/settings with dm_model -> verify stored."""
        base = lobby_server["base_url"]
        r = httpx.patch(
            f"{base}/api/settings",
            json={"dm_model": "gpt-4o-mini"},
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert "dm_model" in data["changed"]
        assert data["settings"]["dm_model"] == "gpt-4o-mini"


# ── GM Tests ─────────────────────────────────────────────────────────


class TestGMMode:
    """Test GM entity/tick control (world must be started)."""

    def test_entity_set(self, lobby_server: dict[str, Any]) -> None:
        """POST /api/entity/set -> verify property changed in state."""
        base = lobby_server["base_url"]
        _start_world(base)
        httpx.post(f"{base}/api/tick/pause", timeout=10)

        # Set food_supply quantity to 999
        r = httpx.post(
            f"{base}/api/entity/set",
            json={"entity_id": "food_supply", "property": "quantity", "value": 999},
            timeout=10,
        )
        assert r.status_code == 200
        data = r.json()
        assert data["new"] == 999
        assert data["entity_id"] == "food_supply"

        # Step to apply queued change (auto_tick may modify slightly)
        httpx.post(f"{base}/api/tick/step", timeout=10)

        # Verify GM set was applied (auto_tick may decrement slightly)
        run_id = httpx.get(f"{base}/health").json()["run_id"]
        r = httpx.get(f"{base}/api/runs/{run_id}/state")
        entities = r.json()["entities"]
        food = next(e for e in entities if e["id"] == "food_supply")
        assert food["quantity"] >= 990, f"Expected ~999, got {food['quantity']}"

    def test_entity_set_nonexistent(self, lobby_server: dict[str, Any]) -> None:
        """POST /api/entity/set for missing entity -> 404."""
        base = lobby_server["base_url"]
        _start_world(base)

        r = httpx.post(
            f"{base}/api/entity/set",
            json={
                "entity_id": "nonexistent_entity",
                "property": "foo",
                "value": 1,
            },
            timeout=10,
        )
        assert r.status_code == 404

    def test_entity_remove(self, lobby_server: dict[str, Any]) -> None:
        """POST /api/entity/remove -> verify entity gone from state."""
        base = lobby_server["base_url"]
        _start_world(base)

        # Verify food_supply exists first
        run_id = httpx.get(f"{base}/health").json()["run_id"]
        r = httpx.get(f"{base}/api/runs/{run_id}/state")
        ids = {e["id"] for e in r.json()["entities"]}
        assert "food_supply" in ids

        # Remove it
        r = httpx.post(
            f"{base}/api/entity/remove",
            json={"entity_id": "food_supply"},
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["queued"] is True

        # Step to apply queued removal
        httpx.post(f"{base}/api/tick/step", timeout=10)

        # Verify gone
        r = httpx.get(f"{base}/api/runs/{run_id}/state")
        ids = {e["id"] for e in r.json()["entities"]}
        assert "food_supply" not in ids

    def test_tick_step(self, lobby_server: dict[str, Any]) -> None:
        """POST /api/tick/step -> tick advances by 1."""
        base = lobby_server["base_url"]
        _start_world(base)

        # Pause first to have predictable tick values
        httpx.post(f"{base}/api/tick/pause", timeout=10)

        r = httpx.get(f"{base}/health")
        tick_before = r.json()["tick"]

        r = httpx.post(f"{base}/api/tick/step", timeout=10)
        assert r.status_code == 200
        data = r.json()
        assert data["tick"] == tick_before + 1

    def test_tick_interval_change(self, lobby_server: dict[str, Any]) -> None:
        """PATCH /api/tick/interval -> verify accepted."""
        base = lobby_server["base_url"]
        _start_world(base)

        r = httpx.patch(
            f"{base}/api/tick/interval",
            json={"interval": 5.0},
            timeout=10,
        )
        assert r.status_code == 200
        assert r.json()["interval"] == 5.0

    def test_tick_interval_zero_rejected(self, lobby_server: dict[str, Any]) -> None:
        """PATCH /api/tick/interval with 0 -> 400."""
        base = lobby_server["base_url"]
        _start_world(base)

        r = httpx.patch(
            f"{base}/api/tick/interval",
            json={"interval": 0},
            timeout=10,
        )
        assert r.status_code == 400


# ── Endpoints-return-503-in-lobby Tests ──────────────────────────────


class TestLobby503:
    """Endpoints that require a running world return 503 in lobby mode."""

    def test_perceive_in_lobby_503(self, lobby_server: dict[str, Any]) -> None:
        """GET /perceive in lobby -> 503."""
        r = httpx.get(
            f"{lobby_server['base_url']}/perceive",
            params={"agent_id": "old_chen"},
        )
        assert r.status_code == 503

    def test_act_in_lobby_503(self, lobby_server: dict[str, Any]) -> None:
        """POST /act in lobby -> 503."""
        r = httpx.post(
            f"{lobby_server['base_url']}/act",
            json={"agent_id": "old_chen", "action": "wait", "params": {}},
        )
        assert r.status_code == 503

    def test_state_in_lobby_404(self, lobby_server: dict[str, Any]) -> None:
        """GET /api/runs/{fake_id}/state in lobby -> 404 (no run)."""
        r = httpx.get(f"{lobby_server['base_url']}/api/runs/nonexistent/state")
        assert r.status_code == 404

    def test_characters_in_lobby_503(self, lobby_server: dict[str, Any]) -> None:
        """GET /characters in lobby -> 503."""
        r = httpx.get(f"{lobby_server['base_url']}/characters")
        assert r.status_code == 503


# ── Available Configs ────────────────────────────────────────────────


class TestConfigs:
    """Test config listing."""

    def test_list_configs(self, lobby_server: dict[str, Any]) -> None:
        """GET /api/configs -> returns list of yaml files."""
        r = httpx.get(f"{lobby_server['base_url']}/api/configs")
        assert r.status_code == 200
        configs = r.json()
        assert isinstance(configs, list)
        assert len(configs) > 0
        names = {c["name"] for c in configs}
        assert "bunker.yaml" in names
        assert "minimal.yaml" in names
        # Each entry has name and path
        for c in configs:
            assert "name" in c
            assert "path" in c
            assert c["name"].endswith(".yaml")


# ── Persistence in Lifecycle ─────────────────────────────────────────


class TestPersistenceLifecycle:
    """Test persistence files created during start/stop lifecycle."""

    def test_start_stop_creates_run_files(self, lobby_server: dict[str, Any]) -> None:
        """Start -> do stuff -> stop -> verify persistence files exist."""
        base = lobby_server["base_url"]
        tmp_path = lobby_server["tmp_path"]

        start_data = _start_world(base)
        run_id = start_data["run_id"]

        # Pause ticks to make step deterministic
        httpx.post(f"{base}/api/tick/pause", timeout=10)

        # Do a tick step to generate events
        httpx.post(f"{base}/api/tick/step", timeout=10)

        # Stop world (triggers finalize)
        _stop_world(base)

        # Check files
        run_dir = tmp_path / ".worldseed" / "runs" / run_id
        assert run_dir.is_dir(), f"Run directory should exist: {run_dir}"
        assert (run_dir / "stream.jsonl").is_file()
        assert (run_dir / "meta.json").is_file()
        assert (run_dir / "state_final.json").is_file()
        assert (run_dir / "summary.json").is_file()
        assert (run_dir / "config.yaml").is_file()

        # Verify meta.json has end_time set
        meta = json.loads((run_dir / "meta.json").read_text())
        assert meta["end_time"] is not None
        assert meta["scene_id"] == "doomsday_bunker"

    def test_past_runs_shows_after_stop(self, lobby_server: dict[str, Any]) -> None:
        """Stop -> GET /api/past-runs -> run appears."""
        base = lobby_server["base_url"]
        start_data = _start_world(base)
        run_id = start_data["run_id"]
        _stop_world(base)

        r = httpx.get(f"{base}/api/past-runs")
        assert r.status_code == 200
        runs = r.json()
        run_ids = {run["run_id"] for run in runs}
        assert run_id in run_ids

    def test_config_reload_preserves_old_run(self, lobby_server: dict[str, Any]) -> None:
        """Start bunker -> reload to minimal -> old run finalized, new run started."""
        base = lobby_server["base_url"]
        tmp_path = lobby_server["tmp_path"]

        data1 = _start_world(base, "bunker.yaml")
        run_id_1 = data1["run_id"]

        # Reload to minimal
        r = httpx.post(
            f"{base}/api/config/reload",
            json={"config_path": str(CONFIGS_DIR / "minimal.yaml")},
            timeout=10,
        )
        assert r.status_code == 200
        reload_data = r.json()
        run_id_2 = reload_data["run_id"]
        assert reload_data["scene_id"] == "test_minimal"
        assert run_id_2 != run_id_1

        # Old run should be finalized
        old_run_dir = tmp_path / ".worldseed" / "runs" / run_id_1
        assert (old_run_dir / "meta.json").is_file()
        old_meta = json.loads((old_run_dir / "meta.json").read_text())
        assert old_meta["end_time"] is not None

        # New run should be active
        r = httpx.get(f"{base}/health")
        assert r.json()["scene"] == "test_minimal"
        assert r.json()["status"] != "lobby"


# ── Stress Tests ─────────────────────────────────────────────────────


class TestStress:
    """Stress tests for rapid operations."""

    def test_rapid_start_stop_cycle(self, lobby_server: dict[str, Any]) -> None:
        """Start -> stop -> start -> stop x3, no crashes."""
        base = lobby_server["base_url"]
        configs = ["bunker.yaml", "minimal.yaml", "bunker.yaml"]
        expected_scenes = ["doomsday_bunker", "test_minimal", "doomsday_bunker"]

        for config_name, expected_scene in zip(configs, expected_scenes):
            data = _start_world(base, config_name)
            assert data["scene_id"] == expected_scene

            r = httpx.get(f"{base}/health")
            assert r.json()["status"] != "lobby"

            _stop_world(base)

            r = httpx.get(f"{base}/health")
            assert r.json()["status"] == "lobby"

    def test_many_entity_edits(self, lobby_server: dict[str, Any]) -> None:
        """Start -> 50 rapid entity/set calls -> verify last value persisted."""
        base = lobby_server["base_url"]
        _start_world(base)

        # Pause ticks to avoid interference
        httpx.post(f"{base}/api/tick/pause", timeout=10)

        for i in range(50):
            r = httpx.post(
                f"{base}/api/entity/set",
                json={
                    "entity_id": "food_supply",
                    "property": "quantity",
                    "value": i,
                },
                timeout=10,
            )
            assert r.status_code == 200

        # Step to apply all queued changes (auto_tick may modify slightly)
        httpx.post(f"{base}/api/tick/step", timeout=10)

        # Verify final value (auto_tick may decrement slightly from 49)
        run_id = httpx.get(f"{base}/health").json()["run_id"]
        r = httpx.get(f"{base}/api/runs/{run_id}/state")
        entities = r.json()["entities"]
        food = next(e for e in entities if e["id"] == "food_supply")
        assert food["quantity"] >= 40, f"Expected ~49, got {food['quantity']}"

    def test_many_tick_steps(self, lobby_server: dict[str, Any]) -> None:
        """Pause -> 20 rapid tick/step calls -> verify tick advanced by 20."""
        base = lobby_server["base_url"]
        _start_world(base)

        # Pause auto-ticks
        httpx.post(f"{base}/api/tick/pause", timeout=10)

        r = httpx.get(f"{base}/health")
        tick_before = r.json()["tick"]

        for _ in range(20):
            r = httpx.post(f"{base}/api/tick/step", timeout=10)
            assert r.status_code == 200

        r = httpx.get(f"{base}/health")
        tick_after = r.json()["tick"]
        assert tick_after == tick_before + 20
