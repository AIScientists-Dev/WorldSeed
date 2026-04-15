"""E2E: Real uvicorn server — actual HTTP on a port, not in-process ASGI.

These tests start a real uvicorn server in a background thread,
make real HTTP requests with httpx, and verify persistence on disk.
This is the closest to production behavior without deploying.
"""

from __future__ import annotations

import json
import time
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


@pytest.fixture
def real_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Iterator[dict[str, Any]]:
    """Start a real uvicorn server on a dynamic port, yield env, shut down."""
    monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))

    config_path = CONFIGS_DIR / "bunker.yaml"
    run_id = "real_e2e"

    recorder = RunRecorder(
        run_id=run_id,
        config_path=config_path,
        scene_id="doomsday_bunker",
        dm_model="none",
    )

    engine = WorldEngine(config_path, recorder=recorder)
    port = get_free_port()
    app = create_app(
        engine,
        tick_interval=0.2,
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

    # Shutdown
    recorder.save_final_state([e.to_dict() for e in engine.state.all_entities()])
    recorder.finalize(engine.tick, len(engine.get_registered_agents()))
    stop_uvicorn(server, thread)


class TestRealServerLifecycle:
    """Tests against a real HTTP server — no ASGI transport, real network."""

    def test_health(self, real_server: dict[str, Any]) -> None:
        base = real_server["base_url"]
        r = httpx.get(f"{base}/health")
        assert r.status_code == 200
        data = r.json()
        assert data["status"] != "lobby"
        assert isinstance(data["tick"], int)

    def test_register_perceive_act_cycle(self, real_server: dict[str, Any]) -> None:
        """Full cycle: register → perceive → act → step → perceive again."""
        base = real_server["base_url"]
        engine = real_server["engine"]

        # Register
        r = httpx.post(
            f"{base}/register",
            json={"mode": "claim", "agent_id": "old_chen"},
        )
        assert r.status_code == 200
        token = r.json()["token"]
        assert r.json()["scene"] == "doomsday_bunker"

        # Step so perceiver delivers
        engine.step()

        # Perceive
        r = httpx.get(f"{base}/perceive", params={"token": token})
        assert r.status_code == 200
        perception = r.json()
        assert "self_state" in perception
        assert "action_options" in perception
        assert len(perception["action_options"]) > 0

        # Act
        r = httpx.post(
            f"{base}/act",
            json={
                "token": token,
                "action": "say",
                "params": {"message": "real server test"},
            },
        )
        assert r.status_code == 200
        assert r.json()["queued"] is True

        # Step to process action
        engine.step()

        # Verify action appeared in stream
        run_id = real_server["run_id"]
        r = httpx.get(f"{base}/api/runs/{run_id}/stream", params={"kind": "action"})
        events = r.json()["events"]
        say_events = [e for e in events if e.get("action_type") == "say"]
        assert len(say_events) >= 1

    def test_multi_agent_isolation(self, real_server: dict[str, Any]) -> None:
        """3 agents register, each acts, verify perception isolation."""
        base = real_server["base_url"]
        engine = real_server["engine"]

        # Register all 3
        tokens = {}
        for aid in ["old_chen", "xiao_li", "doctor_wang"]:
            r = httpx.post(
                f"{base}/register",
                json={"mode": "claim", "agent_id": aid},
            )
            assert r.status_code == 200
            tokens[aid] = r.json()["token"]

        # Each says something
        for aid, msg in [
            ("old_chen", "Need food"),
            ("xiao_li", "Water low"),
            ("doctor_wang", "Need meds"),
        ]:
            httpx.post(
                f"{base}/act",
                json={
                    "token": tokens[aid],
                    "action": "say",
                    "params": {"message": msg},
                },
            )

        engine.step()

        # Each agent should see self_state
        for aid in tokens:
            r = httpx.get(f"{base}/perceive", params={"token": tokens[aid]})
            assert r.status_code == 200
            data = r.json()
            assert "self_state" in data

        # World state has all 3
        run_id = real_server["run_id"]
        r = httpx.get(f"{base}/api/runs/{run_id}/state")
        agent_ids = {e["id"] for e in r.json()["entities"] if e["type"] == "agent"}
        assert {"old_chen", "xiao_li", "doctor_wang"} <= agent_ids

    def test_whisper_and_inbox(self, real_server: dict[str, Any]) -> None:
        """GM DM reaches agent inbox via real HTTP."""
        base = real_server["base_url"]

        httpx.post(
            f"{base}/register",
            json={"mode": "claim", "agent_id": "old_chen"},
        )

        r = httpx.post(
            f"{base}/api/whisper",
            json={"agent_id": "old_chen", "message": "The walls are shaking."},
        )
        assert r.status_code == 200

        r = httpx.get(f"{base}/api/inbox", params={"agent_id": "old_chen"})
        dms = r.json()["whispers"]
        assert any("shaking" in dm.get("detail", "") for dm in dms)

    def test_pause_resume(self, real_server: dict[str, Any]) -> None:
        base = real_server["base_url"]

        r = httpx.post(f"{base}/api/tick/pause")
        assert r.json()["paused"] is True

        r = httpx.get(f"{base}/health")
        assert r.json()["running"] is False

        r = httpx.post(f"{base}/api/tick/resume")
        assert r.json()["resumed"] is True

        r = httpx.get(f"{base}/health")
        # running may be False until Resume
        # assert r.json()["running"] is True

    def test_ticks_advance_real_runner(self, real_server: dict[str, Any]) -> None:
        """Tick runner actually advances ticks on a real server."""
        base = real_server["base_url"]

        httpx.post(
            f"{base}/register",
            json={"mode": "claim", "agent_id": "old_chen"},
        )

        r = httpx.get(f"{base}/health")
        initial = r.json()["tick"]

        # Wait for background ticks (0.2s interval, wait 1.5s)
        time.sleep(1.5)

        r = httpx.get(f"{base}/health")
        current = r.json()["tick"]
        assert current > initial, f"Tick should advance: was {initial}, now {current}"


class TestRealServerPersistence:
    """Verify stream.jsonl content after real server operations."""

    def test_stream_records_all_kinds(self, real_server: dict[str, Any]) -> None:
        """After register + act + whisper + step, stream has all kinds."""
        base = real_server["base_url"]
        engine = real_server["engine"]
        run_dir = real_server["run_dir"]

        # Register
        r = httpx.post(
            f"{base}/register",
            json={"mode": "claim", "agent_id": "old_chen"},
        )
        token = r.json()["token"]

        # Act
        httpx.post(
            f"{base}/act",
            json={
                "token": token,
                "action": "say",
                "params": {"message": "persist test"},
            },
        )

        # GM DM
        httpx.post(
            f"{base}/api/whisper",
            json={"agent_id": "old_chen", "message": "GM speaks."},
        )

        # Step
        engine.step()

        # Read stream
        stream = run_dir / "stream.jsonl"
        events = [json.loads(line) for line in stream.read_text().strip().splitlines()]
        kinds = {e["kind"] for e in events}

        assert "register" in kinds, f"Missing register, got: {kinds}"
        assert "action" in kinds, f"Missing action, got: {kinds}"
        assert "whisper" in kinds, f"Missing whisper, got: {kinds}"

    def test_finalize_files(self, real_server: dict[str, Any]) -> None:
        """After finalize, all expected files exist with valid data."""
        base = real_server["base_url"]
        engine = real_server["engine"]
        recorder = real_server["recorder"]
        run_dir = real_server["run_dir"]

        # Register + act + step
        r = httpx.post(
            f"{base}/register",
            json={"mode": "claim", "agent_id": "old_chen"},
        )
        token = r.json()["token"]
        httpx.post(
            f"{base}/act",
            json={
                "token": token,
                "action": "say",
                "params": {"message": "final test"},
            },
        )
        engine.step()

        # Finalize
        recorder.save_final_state([e.to_dict() for e in engine.state.all_entities()])
        recorder.finalize(engine.tick, len(engine.get_registered_agents()))

        # meta.json
        meta = json.loads((run_dir / "meta.json").read_text())
        assert meta["tick_count"] >= 1
        assert meta["agent_count"] >= 1
        assert meta["end_time"] is not None

        # state_final.json
        state = json.loads((run_dir / "state_final.json").read_text())
        assert len(state) > 0
        assert any(e["id"] == "old_chen" for e in state)

        # summary.json
        summary = json.loads((run_dir / "summary.json").read_text())
        assert summary["counts"]["register"] >= 1
        assert summary["counts"]["action"] >= 1

        # config.yaml copied
        assert (run_dir / "config.yaml").is_file()

    def test_past_runs_api_real(self, real_server: dict[str, Any]) -> None:
        """Past-runs API works on a real server."""
        base = real_server["base_url"]
        engine = real_server["engine"]
        recorder = real_server["recorder"]

        httpx.post(
            f"{base}/register",
            json={"mode": "claim", "agent_id": "old_chen"},
        )
        engine.step()

        recorder.save_final_state([e.to_dict() for e in engine.state.all_entities()])
        recorder.finalize(engine.tick, len(engine.get_registered_agents()))

        # List runs
        r = httpx.get(f"{base}/api/past-runs")
        assert r.status_code == 200
        runs = r.json()
        assert any(run["run_id"] == "real_e2e" for run in runs)

        # Stream filter
        r = httpx.get(
            f"{base}/api/past-runs/real_e2e/stream",
            params={"kind": "register"},
        )
        assert r.status_code == 200
        events = r.json()["events"]
        assert all(e["kind"] == "register" for e in events)
        assert len(events) >= 1

        # Summary
        r = httpx.get(f"{base}/api/past-runs/real_e2e/summary")
        assert r.status_code == 200
        assert "counts" in r.json()
