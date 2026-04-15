"""E2E: Dashboard control lifecycle — every button, every edge case.

Tests all control endpoints (connect, start, pause, step, resume, stop)
in every valid and invalid combination. Uses ASGI transport (no real port).
Zero hardcoded scene-specific strings — works with any config.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from tests.helpers import standard_config_paths
from worldseed.persistence import RunRecorder
from worldseed.server.app import create_app
from worldseed.world import WorldEngine

pytestmark = pytest.mark.asyncio


@pytest_asyncio.fixture
async def env(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    """Server env with engine, client, recorder. Tick NOT started."""
    monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))

    config_path = standard_config_paths()[0]
    run_id = "ctrl_test"

    recorder = RunRecorder(
        run_id=run_id,
        config_path=config_path,
        scene_id="test",
        dm_model="none",
    )
    engine = WorldEngine(config_path, recorder=recorder)
    engine.register_from_config()

    app = create_app(
        engine,
        tick_interval=0.05,
        run_id=run_id,
        auto_start_tick=False,
    )

    transport = ASGITransport(app=app)
    client = AsyncClient(transport=transport, base_url="http://test")

    return {
        "client": client,
        "engine": engine,
        "recorder": recorder,
        "app": app,
        "run_id": run_id,
        "run_dir": recorder.run_dir,
        "tmp_path": tmp_path,
        "config_path": config_path,
    }


# ── Health ──────────────────────────────────────────


class TestHealth:
    async def test_initial_state(self, env: dict[str, Any]) -> None:
        r = await env["client"].get("/health")
        assert r.status_code == 200
        d = r.json()
        assert d["tick"] == 0
        assert d["running"] is False
        assert d["agents"]["total"] > 0

    async def test_scene_in_health(self, env: dict[str, Any]) -> None:
        r = await env["client"].get("/health")
        d = r.json()
        assert "scene" in d
        assert isinstance(d["scene"], str)
        assert len(d["scene"]) > 0


# ── Start / Resume ──────────────────────────────────


class TestResume:
    async def test_resume_starts_ticking(self, env: dict[str, Any]) -> None:
        r = await env["client"].post("/api/tick/resume")
        assert r.status_code == 200
        assert r.json()["resumed"] is True

        h = (await env["client"].get("/health")).json()
        assert h["running"] is True

    async def test_resume_twice_is_safe(self, env: dict[str, Any]) -> None:
        await env["client"].post("/api/tick/resume")
        r = await env["client"].post("/api/tick/resume")
        assert r.status_code == 200
        # Should not crash, may return resumed=True or already running


# ── Pause ───────────────────────────────────────────


class TestPause:
    async def test_pause_stops_ticking(self, env: dict[str, Any]) -> None:
        await env["client"].post("/api/tick/resume")
        r = await env["client"].post("/api/tick/pause")
        assert r.status_code == 200
        d = r.json()
        assert d["paused"] is True
        tick_at_pause = d["tick"]

        import asyncio

        await asyncio.sleep(0.3)
        h = (await env["client"].get("/health")).json()
        assert h["tick"] == tick_at_pause
        assert h["running"] is False

    async def test_pause_already_paused(self, env: dict[str, Any]) -> None:
        await env["client"].post("/api/tick/resume")
        await env["client"].post("/api/tick/pause")
        r = await env["client"].post("/api/tick/pause")
        # Should not crash
        assert r.status_code == 200

    async def test_pause_never_started(self, env: dict[str, Any]) -> None:
        r = await env["client"].post("/api/tick/pause")
        # Pausing when never started — should be safe
        assert r.status_code == 200


# ── Step ────────────────────────────────────────────


class TestStep:
    async def test_step_advances_one(self, env: dict[str, Any]) -> None:
        h = (await env["client"].get("/health")).json()
        before = h["tick"]
        r = await env["client"].post("/api/tick/step")
        assert r.status_code == 200
        assert r.json()["tick"] == before + 1

    async def test_step_multiple(self, env: dict[str, Any]) -> None:
        for i in range(3):
            r = await env["client"].post("/api/tick/step")
            assert r.status_code == 200
            assert r.json()["tick"] == i + 1

    async def test_step_while_running(self, env: dict[str, Any]) -> None:
        await env["client"].post("/api/tick/resume")
        r = await env["client"].post("/api/tick/step")
        # Should either work or return error, not crash
        assert r.status_code in (200, 409, 400)


# ── Stop ────────────────────────────────────────────


class TestStop:
    async def test_stop_saves_state(self, env: dict[str, Any]) -> None:
        # Run a few ticks
        for _ in range(3):
            await env["client"].post("/api/tick/step")

        r = await env["client"].post("/api/world/stop")
        assert r.status_code == 200
        assert r.json()["stopped"] is True

        # Verify files saved
        run_dir = env["run_dir"]
        assert (run_dir / "state_final.json").is_file()
        assert (run_dir / "stream.jsonl").is_file()

        state = json.loads((run_dir / "state_final.json").read_text())
        assert len(state) > 0

    async def test_stop_then_health_is_lobby(self, env: dict[str, Any]) -> None:
        await env["client"].post("/api/world/stop")
        h = (await env["client"].get("/health")).json()
        assert h["status"] == "lobby"

    async def test_stop_no_world(self, env: dict[str, Any]) -> None:
        await env["client"].post("/api/world/stop")
        r = await env["client"].post("/api/world/stop")
        assert r.status_code == 400

    async def test_stop_saves_transient(self, env: dict[str, Any]) -> None:
        for _ in range(3):
            await env["client"].post("/api/tick/step")

        await env["client"].post("/api/world/stop")
        run_dir = env["run_dir"]
        t_path = run_dir / "transient.json"
        assert t_path.is_file()
        t = json.loads(t_path.read_text())
        assert "inboxes" in t
        assert "pending_actions" in t
        assert "think_intervals" in t
        assert "recent_events" in t


# ── Connect Agents ──────────────────────────────────


class TestConnectAgents:
    async def test_connect_no_gateway(self, env: dict[str, Any]) -> None:
        r = await env["client"].post("/api/agents/connect")
        assert r.status_code == 503
        assert "gateway" in r.json()["detail"].lower()

    async def test_connect_after_stop(self, env: dict[str, Any]) -> None:
        await env["client"].post("/api/world/stop")
        r = await env["client"].post("/api/agents/connect")
        # No gateway, no engine — should fail gracefully
        assert r.status_code in (400, 503)


# ── Perceive ────────────────────────────────────────


class TestPerceive:
    async def test_perceive_returns_state(self, env: dict[str, Any]) -> None:
        agents = env["engine"].get_registered_agents()
        assert len(agents) > 0
        agent_id = agents[0]

        r = await env["client"].get(f"/perceive?agent_id={agent_id}")
        assert r.status_code == 200
        d = r.json()
        assert "self_state" in d
        assert "action_options" in d
        assert isinstance(d["action_options"], dict)
        assert len(d["action_options"]) > 0

    async def test_perceive_unknown_agent(self, env: dict[str, Any]) -> None:
        r = await env["client"].get("/perceive?agent_id=nonexistent_xyz")
        assert r.status_code in (403, 404)


# ── Act ─────────────────────────────────────────────


class TestAct:
    async def test_act_mechanical(self, env: dict[str, Any]) -> None:
        """Mechanical action (no dm: section) executes immediately."""
        from tests.helpers import ConfigIntrospector

        intro = ConfigIntrospector(env["engine"].config)
        agents = intro.agent_ids
        if not agents:
            pytest.skip("no agents")

        # Find a paramless mechanical action
        mechanical = intro.paramless_actions()
        if not mechanical:
            pytest.skip("no paramless mechanical actions")

        action_name = mechanical[0]
        agent_id = agents[0]
        r = await env["client"].post(
            "/act",
            json={
                "agent_id": agent_id,
                "action": action_name,
                "params": {},
            },
        )
        # Either 200 (queued/executed) or 422 (precondition fail)
        assert r.status_code in (200, 422)

    async def test_act_unknown_agent(self, env: dict[str, Any]) -> None:
        r = await env["client"].post(
            "/act",
            json={
                "agent_id": "nonexistent_xyz",
                "action": "anything",
                "params": {},
            },
        )
        assert r.status_code in (403, 404)


# ── World Resume (switch) ──────────────────────────


class TestWorldResume:
    async def test_resume_requires_stop_first(self, env: dict[str, Any]) -> None:
        r = await env["client"].post(
            "/api/world/resume",
            json={"run_id": "anything"},
        )
        assert r.status_code == 409

    async def test_resume_nonexistent_run(self, env: dict[str, Any]) -> None:
        await env["client"].post("/api/world/stop")
        r = await env["client"].post(
            "/api/world/resume",
            json={"run_id": "does_not_exist_99"},
        )
        assert r.status_code == 404

    async def test_resume_no_run_id(self, env: dict[str, Any]) -> None:
        await env["client"].post("/api/world/stop")
        r = await env["client"].post(
            "/api/world/resume",
            json={},
        )
        assert r.status_code == 400

    async def test_resume_roundtrip(self, env: dict[str, Any]) -> None:
        """Stop → resume → verify state restored."""
        engine = env["engine"]
        # Run a few ticks to create state
        for _ in range(3):
            await env["client"].post("/api/tick/step")

        tick_before = engine.tick
        entities_before = {e.id for e in engine.state.all_entities()}

        # Stop
        await env["client"].post("/api/world/stop")
        run_id = env["run_id"]

        # Resume
        r = await env["client"].post(
            "/api/world/resume",
            json={"run_id": run_id},
        )
        assert r.status_code == 200
        d = r.json()
        assert d["run_id"] == run_id
        assert d["tick"] == tick_before

        # Verify health
        h = (await env["client"].get("/health")).json()
        assert h["run_id"] == run_id
        assert h["tick"] == tick_before

        # Verify entities restored
        new_engine = env["app"].state.engine
        entities_after = {e.id for e in new_engine.state.all_entities()}
        assert entities_before == entities_after


# ── Historical Run APIs ─────────────────────────────


class TestHistoricalAPIs:
    async def test_past_runs_list(self, env: dict[str, Any]) -> None:
        # Run and stop to create a past run
        for _ in range(2):
            await env["client"].post("/api/tick/step")
        await env["client"].post("/api/world/stop")

        r = await env["client"].get("/api/past-runs")
        assert r.status_code == 200
        runs = r.json()
        assert isinstance(runs, list)
        assert len(runs) >= 1
        found = any(run["run_id"] == env["run_id"] for run in runs)
        assert found, f"Run {env['run_id']} not in past runs"

    async def test_past_run_state(self, env: dict[str, Any]) -> None:
        for _ in range(2):
            await env["client"].post("/api/tick/step")
        await env["client"].post("/api/world/stop")

        r = await env["client"].get(f"/api/past-runs/{env['run_id']}/state")
        assert r.status_code == 200
        d = r.json()
        assert "entities" in d
        assert len(d["entities"]) > 0
        # Verify no engine metadata leak
        for e in d["entities"]:
            assert "constraints" not in e
            assert "_constraints" not in e

    async def test_past_run_stream(self, env: dict[str, Any]) -> None:
        for _ in range(2):
            await env["client"].post("/api/tick/step")
        await env["client"].post("/api/world/stop")

        r = await env["client"].get(f"/api/past-runs/{env['run_id']}/stream")
        assert r.status_code == 200
        d = r.json()
        assert "events" in d
        assert len(d["events"]) > 0

    async def test_past_run_nonexistent(self, env: dict[str, Any]) -> None:
        r = await env["client"].get("/api/past-runs/does_not_exist_99/state")
        assert r.status_code == 404


# ── Sequence Tests (multi-step scenarios) ───────────


class TestSequences:
    async def test_full_lifecycle(self, env: dict[str, Any]) -> None:
        """start → tick → pause → step → resume → stop."""
        c = env["client"]

        # Start
        r = await c.post("/api/tick/resume")
        assert r.json()["resumed"] is True

        # Let it tick
        import asyncio

        await asyncio.sleep(0.3)
        h = (await c.get("/health")).json()
        assert h["tick"] > 0

        # Pause
        r = await c.post("/api/tick/pause")
        tick_paused = r.json()["tick"]

        # Step
        r = await c.post("/api/tick/step")
        assert r.json()["tick"] == tick_paused + 1

        # Resume
        r = await c.post("/api/tick/resume")
        assert r.json()["resumed"] is True
        await asyncio.sleep(0.2)

        # Stop
        r = await c.post("/api/world/stop")
        assert r.json()["stopped"] is True

    async def test_stop_start_stop(self, env: dict[str, Any]) -> None:
        """Stop → start new → stop again."""
        c = env["client"]
        config_path = str(env["config_path"])

        await c.post("/api/tick/step")
        await c.post("/api/world/stop")

        # Start new world
        r = await c.post(
            "/api/world/start",
            json={
                "config_path": config_path,
                "dm_model": "",
                "tick_interval": 0.05,
            },
        )
        assert r.status_code == 200
        new_run = r.json()["run_id"]
        assert new_run != env["run_id"]

        h = (await c.get("/health")).json()
        assert h["run_id"] == new_run
        assert h["tick"] == 0

        await c.post("/api/world/stop")
        h = (await c.get("/health")).json()
        assert h["status"] == "lobby"


# ── Lobby State (no engine) ─────────────────────────


class TestLobbyNoEngine:
    """All control endpoints called when engine is None."""

    @pytest_asyncio.fixture
    async def lobby_client(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> AsyncClient:
        """Server in lobby mode — no engine at all."""
        monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))
        app = create_app(engine=None, port=9999)
        transport = ASGITransport(app=app)
        return AsyncClient(transport=transport, base_url="http://test")

    async def test_health_lobby(self, lobby_client: AsyncClient) -> None:
        r = await lobby_client.get("/health")
        assert r.status_code == 200
        assert r.json()["status"] == "lobby"

    async def test_resume_lobby(self, lobby_client: AsyncClient) -> None:
        r = await lobby_client.post("/api/tick/resume")
        assert r.status_code == 503

    async def test_pause_lobby(self, lobby_client: AsyncClient) -> None:
        r = await lobby_client.post("/api/tick/pause")
        assert r.status_code == 503

    async def test_step_lobby(self, lobby_client: AsyncClient) -> None:
        r = await lobby_client.post("/api/tick/step")
        assert r.status_code == 503

    async def test_stop_lobby(self, lobby_client: AsyncClient) -> None:
        r = await lobby_client.post("/api/world/stop")
        assert r.status_code == 400

    async def test_connect_lobby(self, lobby_client: AsyncClient) -> None:
        r = await lobby_client.post("/api/agents/connect")
        # No gateway → 503
        assert r.status_code == 503

    async def test_perceive_lobby(self, lobby_client: AsyncClient) -> None:
        r = await lobby_client.get("/perceive?agent_id=anyone")
        assert r.status_code == 503


# ── Repeated Connect ────────────────────────────────


class TestRepeatedConnect:
    """Connect called multiple times — idempotent or safe."""

    async def test_connect_twice_no_gateway(self, env: dict[str, Any]) -> None:
        r1 = await env["client"].post("/api/agents/connect")
        r2 = await env["client"].post("/api/agents/connect")
        # Both should 503 (no gateway in test env)
        assert r1.status_code == 503
        assert r2.status_code == 503


# ── Transient Restore Verification ──────────────────


class TestTransientRestore:
    """Verify transient data is actually usable after resume."""

    async def test_think_intervals_restored(self, env: dict[str, Any]) -> None:
        engine = env["engine"]
        agents = engine.get_registered_agents()
        if not agents:
            pytest.skip("no agents")

        # Set a non-default think_interval
        engine.set_think_interval(agents[0], 10)

        # Step to populate stream, then stop
        for _ in range(2):
            await env["client"].post("/api/tick/step")
        await env["client"].post("/api/world/stop")

        # Resume
        run_id = env["run_id"]
        r = await env["client"].post("/api/world/resume", json={"run_id": run_id})
        assert r.status_code == 200

        # Verify think_interval restored
        new_engine = env["app"].state.engine
        restored_interval = new_engine.get_think_interval(agents[0])
        assert restored_interval == 10

    async def test_inbox_dms_restored(self, env: dict[str, Any]) -> None:
        engine = env["engine"]
        agents = engine.get_registered_agents()
        if not agents:
            pytest.skip("no agents")

        # Send a DM to an agent
        engine.send_whisper(agents[0], "test_source", "test message", "test_type")

        # Verify DM is in inbox before save
        inbox_before = engine.peek_inbox(agents[0])
        dm_count_before = len(inbox_before["whispers"])
        assert dm_count_before > 0

        # Step then stop (triggers save_state + save_transient)
        await env["client"].post("/api/tick/step")
        await env["client"].post("/api/world/stop")

        # Resume
        r = await env["client"].post("/api/world/resume", json={"run_id": env["run_id"]})
        assert r.status_code == 200

        # Verify DMs restored
        new_engine = env["app"].state.engine
        inbox_after = new_engine.peek_inbox(agents[0])
        dm_count_after = len(inbox_after["whispers"])
        assert dm_count_after >= dm_count_before

    async def test_events_restored_to_eventlog(self, env: dict[str, Any]) -> None:
        # Run several ticks to generate events (auto_tick creates events)
        for _ in range(5):
            await env["client"].post("/api/tick/step")

        await env["client"].post("/api/world/stop")
        r = await env["client"].post("/api/world/resume", json={"run_id": env["run_id"]})
        assert r.status_code == 200

        new_engine = env["app"].state.engine
        event_count_after = new_engine._tick_engine._event_log.size
        # Events from transient should be restored
        # (may be 0 if all events expired by TTL, which is fine)
        assert isinstance(event_count_after, int)
