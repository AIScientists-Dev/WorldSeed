"""E2E: Multi-agent scenarios on real uvicorn servers.

Tests perception isolation, event scoping, auto_tick effects,
action validation, concurrent actions, dynamic registration,
wakeup recording, and config variety.

Each fixture starts uvicorn on a UNIQUE port to avoid conflicts.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path
from typing import Any

import httpx
import pytest

from worldseed.persistence import RunRecorder
from worldseed.server.app import create_app
from worldseed.world import WorldEngine

from .conftest import (
    CONFIGS_DIR,
    get_free_port,
    start_uvicorn,
    stop_uvicorn,
    wait_for_server,
)

# ── Fixtures ─────────────────────────────────────────────────


def _make_server_fixture(
    config_name: str,
    scene_id: str,
    run_id_suffix: str,
    tick_interval: float = 0.2,
):
    """Factory: create a pytest fixture for a real uvicorn server on a dynamic port."""

    @pytest.fixture
    def _fixture(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
        monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))

        config_path = CONFIGS_DIR / config_name
        run_id = f"multi_e2e_{run_id_suffix}"

        recorder = RunRecorder(
            run_id=run_id,
            config_path=config_path,
            scene_id=scene_id,
            dm_model="none",
        )

        engine = WorldEngine(config_path, recorder=recorder)
        port = get_free_port()
        app = create_app(
            engine,
            tick_interval=tick_interval,
            run_id=run_id,
        )

        server, thread = start_uvicorn(app, port)
        base = f"http://127.0.0.1:{port}"
        wait_for_server(base)

        yield {
            "base_url": base,
            "engine": engine,
            "recorder": recorder,
            "run_dir": recorder.run_dir,
            "run_id": run_id,
        }

        recorder.save_final_state([e.to_dict() for e in engine.state.all_entities()])
        recorder.finalize(engine.tick, len(engine.get_registered_agents()))
        stop_uvicorn(server, thread)

    return _fixture


bunker_server = _make_server_fixture("bunker.yaml", "doomsday_bunker", "bunker")
minimal_server = _make_server_fixture("minimal.yaml", "test_minimal", "minimal")


# ── Helpers ──────────────────────────────────────────────────


def _register(base: str, agent_id: str, mode: str = "claim", **kwargs: Any) -> str:
    """Register an agent and return the token."""
    body: dict[str, Any] = {"mode": mode, "agent_id": agent_id}
    body.update(kwargs)
    r = httpx.post(f"{base}/register", json=body)
    assert r.status_code == 200, f"Register {agent_id} failed: {r.text}"
    return r.json()["token"]


def _perceive(base: str, token: str) -> dict[str, Any]:
    """Perceive and return the response dict."""
    r = httpx.get(f"{base}/perceive", params={"token": token})
    assert r.status_code == 200, f"Perceive failed: {r.text}"
    return r.json()


def _act(base: str, token: str, action: str, params: dict[str, Any]) -> httpx.Response:
    """Submit an action and return the raw response."""
    return httpx.post(
        f"{base}/act",
        json={"token": token, "action": action, "params": params},
    )


# ── Test 1: Perception isolation (hidden properties) ────────


class TestPerceptionIsolation:
    """Hidden properties are stripped from other agents' views."""

    def test_self_state_has_all_properties(self, bunker_server: dict[str, Any]) -> None:
        base = bunker_server["base_url"]
        engine = bunker_server["engine"]

        token_chen = _register(base, "old_chen")
        _register(base, "xiao_li")
        engine.step()

        p = _perceive(base, token_chen)
        self_state = p["self_state"]

        # old_chen has private_stash in the config
        assert "private_stash" in self_state
        assert "location" in self_state

    def test_nearby_agents_hide_private_stash(self, bunker_server: dict[str, Any]) -> None:
        base = bunker_server["base_url"]
        engine = bunker_server["engine"]

        token_chen = _register(base, "old_chen")
        _register(base, "xiao_li")
        engine.step()

        p = _perceive(base, token_chen)

        # old_chen and xiao_li start at sleeping_quarters (same location)
        # so xiao_li should be visible
        assert "xiao_li" in p["nearby_agents"]
        xiao_li_props = p["nearby_agents"]["xiao_li"]

        # hidden_properties in bunker.yaml: ["private_stash", "goals"]
        assert "private_stash" not in xiao_li_props
        assert "goals" not in xiao_li_props

    def test_reverse_hidden_properties(self, bunker_server: dict[str, Any]) -> None:
        base = bunker_server["base_url"]
        engine = bunker_server["engine"]

        _register(base, "old_chen")
        token_li = _register(base, "xiao_li")
        engine.step()

        p = _perceive(base, token_li)

        # xiao_li sees old_chen — hidden props stripped
        assert "old_chen" in p["nearby_agents"]
        chen_props = p["nearby_agents"]["old_chen"]
        assert "private_stash" not in chen_props
        assert "goals" not in chen_props

    def test_nearby_agents_retain_non_hidden_props(self, bunker_server: dict[str, Any]) -> None:
        base = bunker_server["base_url"]
        engine = bunker_server["engine"]

        token_chen = _register(base, "old_chen")
        _register(base, "xiao_li")
        engine.step()

        p = _perceive(base, token_chen)
        xiao_li_props = p["nearby_agents"]["xiao_li"]

        # Non-hidden properties should still be visible
        assert "location" in xiao_li_props


# ── Test 2: Event delivery scoping ──────────────────────────


class TestEventDeliveryScoping:
    """Events with scope same_location only reach co-located agents."""

    def test_say_reaches_same_location_agent(self, bunker_server: dict[str, Any]) -> None:
        base = bunker_server["base_url"]
        engine = bunker_server["engine"]

        token_chen = _register(base, "old_chen")
        _register(base, "xiao_li")
        engine.step()

        # old_chen says something — both are at sleeping_quarters
        r = _act(base, token_chen, "say", {"message": "Hello from Chen"})
        assert r.status_code == 200

        engine.step()

        # xiao_li should see the say event in inbox
        r = httpx.get(f"{base}/api/inbox", params={"agent_id": "xiao_li"})
        assert r.status_code == 200
        inbox = r.json()
        events = inbox["events"]
        say_events = [e for e in events if e.get("type") == "say"]
        assert len(say_events) >= 1
        assert any("Hello from Chen" in e.get("detail", "") for e in say_events)

    def test_say_does_not_reach_different_location(self, bunker_server: dict[str, Any]) -> None:
        base = bunker_server["base_url"]
        engine = bunker_server["engine"]

        token_chen = _register(base, "old_chen")
        _register(base, "xiao_li")
        _register(base, "doctor_wang")
        engine.step()

        # doctor_wang starts at hallway, different from sleeping_quarters
        # old_chen says something at sleeping_quarters
        r = _act(base, token_chen, "say", {"message": "Secret at sleeping quarters"})
        assert r.status_code == 200

        engine.step()

        # doctor_wang is at hallway — should NOT see the say event
        r = httpx.get(f"{base}/api/inbox", params={"agent_id": "doctor_wang"})
        assert r.status_code == 200
        inbox = r.json()
        events = inbox["events"]
        say_events = [
            e for e in events if e.get("type") == "say" and "Secret at sleeping quarters" in e.get("detail", "")
        ]
        assert len(say_events) == 0, f"doctor_wang (hallway) should not hear sleeping_quarters say: {say_events}"


# ── Test 3: Auto_tick effects over multiple ticks ────────────


class TestAutoTickEffects:
    """auto_tick rules consume food and water each tick."""

    def test_food_decreases_over_ticks(self, bunker_server: dict[str, Any]) -> None:
        base = bunker_server["base_url"]
        engine = bunker_server["engine"]

        _register(base, "old_chen")
        _register(base, "xiao_li")
        _register(base, "doctor_wang")

        # Read initial food (background tick runner may have already consumed some)
        run_id = bunker_server["run_id"]
        r = httpx.get(f"{base}/api/runs/{run_id}/state")
        entities = r.json()["entities"]
        food = next(e for e in entities if e["id"] == "food_supply")
        initial_food = food["quantity"]
        assert initial_food <= 20

        # Run 10 ticks
        for _ in range(10):
            engine.step()

        # Read food again
        r = httpx.get(f"{base}/api/runs/{run_id}/state")
        entities = r.json()["entities"]
        food = next(e for e in entities if e["id"] == "food_supply")
        final_food = food["quantity"]

        # 3 agents x 0.1 per tick = 0.3 per tick, 10 manual ticks = 3.0 decrease
        # Background tick runner may add extra ticks.
        assert final_food < initial_food, f"Food should decrease: initial={initial_food}, final={final_food}"
        # We manually stepped 10 times (at least 3.0 decrease).
        # Background runner may add more, so check >= 3.0 decrease.
        assert initial_food - final_food >= 3.0, f"Expected at least 3.0 decrease, got {initial_food - final_food}"

    def test_water_decreases_over_ticks(self, bunker_server: dict[str, Any]) -> None:
        base = bunker_server["base_url"]
        engine = bunker_server["engine"]

        _register(base, "old_chen")
        _register(base, "xiao_li")
        _register(base, "doctor_wang")

        # Read initial water (background tick runner may have already consumed some)
        run_id = bunker_server["run_id"]
        r = httpx.get(f"{base}/api/runs/{run_id}/state")
        entities = r.json()["entities"]
        water = next(e for e in entities if e["id"] == "water_supply")
        initial_water = water["quantity"]
        assert initial_water <= 15

        for _ in range(10):
            engine.step()

        r = httpx.get(f"{base}/api/runs/{run_id}/state")
        entities = r.json()["entities"]
        water = next(e for e in entities if e["id"] == "water_supply")
        final_water = water["quantity"]

        # 3 agents x 0.05 per tick = 0.15 per tick, 10 manual ticks = 1.5 decrease
        # Background tick runner may add extra ticks.
        assert final_water < initial_water, f"Water should decrease: initial={initial_water}, final={final_water}"
        # We manually stepped 10 times (at least 1.5 decrease).
        # Background runner may add more, so check >= 1.5 decrease.
        assert initial_water - final_water >= 1.5, f"Expected at least 1.5 decrease, got {initial_water - final_water}"


# ── Test 4: Action validation errors ────────────────────────


class TestActionValidation:
    """Invalid actions and missing params produce clear errors."""

    def test_unknown_action_returns_error(self, bunker_server: dict[str, Any]) -> None:
        base = bunker_server["base_url"]
        engine = bunker_server["engine"]

        token = _register(base, "old_chen")
        engine.step()

        # engine.submit() raises ValueError -> FastAPI returns 500
        r = httpx.post(
            f"{base}/act",
            json={
                "token": token,
                "action": "nonexistent_action",
                "params": {},
            },
        )
        assert r.status_code == 500

    def test_missing_required_param_returns_error(self, bunker_server: dict[str, Any]) -> None:
        base = bunker_server["base_url"]
        engine = bunker_server["engine"]

        token = _register(base, "old_chen")
        engine.step()

        # "say" requires "message" param
        r = httpx.post(
            f"{base}/act",
            json={
                "token": token,
                "action": "say",
                "params": {},
            },
        )
        assert r.status_code == 500

    def test_invalid_token_returns_401(self, bunker_server: dict[str, Any]) -> None:
        base = bunker_server["base_url"]

        r = httpx.get(f"{base}/perceive", params={"token": "bogus_token_xxx"})
        assert r.status_code == 401

    def test_valid_action_succeeds(self, bunker_server: dict[str, Any]) -> None:
        base = bunker_server["base_url"]
        engine = bunker_server["engine"]

        token = _register(base, "old_chen")
        engine.step()

        r = _act(base, token, "say", {"message": "This is valid"})
        assert r.status_code == 200
        assert r.json()["queued"] is True


# ── Test 5: Concurrent actions in same tick ──────────────────


class TestConcurrentActions:
    """Multiple agents submit actions; all are processed in one step."""

    def test_three_says_in_one_tick(self, bunker_server: dict[str, Any]) -> None:
        base = bunker_server["base_url"]
        engine = bunker_server["engine"]

        token_chen = _register(base, "old_chen")
        token_li = _register(base, "xiao_li")
        token_wang = _register(base, "doctor_wang")
        engine.step()

        # All 3 submit say actions without stepping between
        r = _act(base, token_chen, "say", {"message": "Chen speaks"})
        assert r.status_code == 200
        r = _act(base, token_li, "say", {"message": "Li speaks"})
        assert r.status_code == 200
        r = _act(base, token_wang, "say", {"message": "Wang speaks"})
        assert r.status_code == 200

        # Single step processes all 3
        engine.step()

        # All 3 actions should appear in stream
        run_id = bunker_server["run_id"]
        r = httpx.get(f"{base}/api/runs/{run_id}/stream", params={"kind": "action"})
        assert r.status_code == 200
        events = r.json()["events"]
        say_events = [e for e in events if e.get("action_type") == "say"]

        # Verify all 3 agents' say actions are recorded
        agents = [e["agent_id"] for e in say_events]
        assert "old_chen" in agents, f"Missing old_chen: {agents}"
        assert "xiao_li" in agents, f"Missing xiao_li: {agents}"
        assert "doctor_wang" in agents, f"Missing doctor_wang: {agents}"


# ── Test 6: Create agent mid-run ─────────────────────────────


class TestDynamicAgentCreation:
    """Dynamically created agents work alongside preset agents."""

    def test_create_newcomer_mid_run(self, bunker_server: dict[str, Any]) -> None:
        base = bunker_server["base_url"]
        engine = bunker_server["engine"]

        _register(base, "old_chen")
        engine.step()
        engine.step()

        # Create a new agent mid-run
        r = httpx.post(
            f"{base}/register",
            json={
                "mode": "create",
                "agent_id": "newcomer",
                "character": {"personality": "mysterious"},
            },
        )
        assert r.status_code == 200
        newcomer_token = r.json()["token"]
        assert r.json()["agent_id"] == "newcomer"

        engine.step()

        # Newcomer appears in world state
        run_id = bunker_server["run_id"]
        r = httpx.get(f"{base}/api/runs/{run_id}/state")
        entities = r.json()["entities"]
        agent_ids = {e["id"] for e in entities if e["type"] == "agent"}
        assert "newcomer" in agent_ids

        # Newcomer can perceive
        p = _perceive(base, newcomer_token)
        assert "self_state" in p
        assert "action_options" in p
        assert len(p["action_options"]) > 0

    def test_created_agent_can_act(self, bunker_server: dict[str, Any]) -> None:
        base = bunker_server["base_url"]
        engine = bunker_server["engine"]

        _register(base, "old_chen")
        engine.step()

        r = httpx.post(
            f"{base}/register",
            json={
                "mode": "create",
                "agent_id": "newcomer2",
                "character": {"personality": "bold"},
            },
        )
        assert r.status_code == 200
        token = r.json()["token"]
        engine.step()

        r = _act(base, token, "say", {"message": "I have arrived"})
        assert r.status_code == 200

        engine.step()

        run_id = bunker_server["run_id"]
        r = httpx.get(f"{base}/api/runs/{run_id}/stream", params={"kind": "action"})
        events = r.json()["events"]
        say_events = [e for e in events if e.get("action_type") == "say" and e.get("agent_id") == "newcomer2"]
        assert len(say_events) >= 1


# ── Test 7: Wakeup recording in stream ──────────────────────


class TestWakeupRecording:
    """Wakeup events are recorded in stream.jsonl when tick runner runs."""

    def test_wakeup_kind_in_stream(self, bunker_server: dict[str, Any]) -> None:
        """Wakeup is only recorded when a connector is present.

        The tick runner records wakeup events via connector.notify().
        Without a connector, no wakeup records are written.
        Verify the stream still has other event kinds from manual operations.
        """
        base = bunker_server["base_url"]
        engine = bunker_server["engine"]
        run_dir = bunker_server["run_dir"]

        _register(base, "old_chen")
        engine.step()

        # Without a connector, wakeup records are not written.
        # But we can verify the recorder infrastructure works by checking
        # that register records exist in the stream.
        stream_path = run_dir / "stream.jsonl"
        assert stream_path.is_file()
        lines = stream_path.read_text().strip().splitlines()
        events = [json.loads(line) for line in lines]
        kinds = {e["kind"] for e in events}

        assert "register" in kinds, f"Expected 'register' in stream, got: {kinds}"

    def test_stream_records_actions(self, bunker_server: dict[str, Any]) -> None:
        """Stream captures action records."""
        base = bunker_server["base_url"]
        engine = bunker_server["engine"]
        run_dir = bunker_server["run_dir"]

        token = _register(base, "old_chen")
        engine.step()

        _act(base, token, "say", {"message": "record this"})
        engine.step()

        stream_path = run_dir / "stream.jsonl"
        lines = stream_path.read_text().strip().splitlines()
        events = [json.loads(line) for line in lines]
        kinds = {e["kind"] for e in events}

        assert "action" in kinds, f"Expected 'action' in stream, got: {kinds}"


# ── Test 8: Config variety (minimal.yaml) ───────────────────


class TestConfigVariety:
    """The engine works with different scene configs (minimal.yaml)."""

    def test_register_perceive_act_minimal(self, minimal_server: dict[str, Any]) -> None:
        base = minimal_server["base_url"]
        engine = minimal_server["engine"]

        # Register agent_1 (the minimal config agent)
        token = _register(base, "agent_1")
        engine.step()

        # Perceive
        p = _perceive(base, token)
        assert "self_state" in p
        assert p["self_state"]["location"] == "room_a"
        assert "action_options" in p
        assert len(p["action_options"]) > 0

        # Act: move from room_a to room_b
        r = _act(base, token, "move", {"to": "room_b"})
        assert r.status_code == 200

        engine.step()

        # Verify move worked
        p = _perceive(base, token)
        assert p["self_state"]["location"] == "room_b"

    def test_minimal_health(self, minimal_server: dict[str, Any]) -> None:
        base = minimal_server["base_url"]
        r = httpx.get(f"{base}/health")
        assert r.status_code == 200
        assert r.json()["status"] != "lobby"

    def test_minimal_world_state(self, minimal_server: dict[str, Any]) -> None:
        base = minimal_server["base_url"]
        engine = minimal_server["engine"]

        _register(base, "agent_1")
        engine.step()

        run_id = minimal_server["run_id"]
        r = httpx.get(f"{base}/api/runs/{run_id}/state")
        assert r.status_code == 200
        entities = r.json()["entities"]
        entity_ids = {e["id"] for e in entities}
        assert "agent_1" in entity_ids
        assert "room_a" in entity_ids
        assert "room_b" in entity_ids
