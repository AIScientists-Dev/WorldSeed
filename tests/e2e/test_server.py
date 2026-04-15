"""Tests for HTTP server.

Covers /health, /characters, /register,
/perceive, /act, and dashboard API.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from tests.helpers import CONFIGS_DIR
from worldseed.persistence import RunRecorder
from worldseed.server.app import create_app
from worldseed.world import WorldEngine


@pytest.fixture()
def client() -> TestClient:
    """Client with agents pre-registered from config (for perceive/act tests)."""
    engine = WorldEngine(CONFIGS_DIR / "bunker.yaml")
    engine.register_from_config()
    app = create_app(engine, tick_interval=1.0)
    return TestClient(app)


@pytest.fixture()
def empty_client() -> TestClient:
    """Client with no agents pre-registered (for claim/create tests)."""
    engine = WorldEngine(CONFIGS_DIR / "bunker.yaml")
    app = create_app(engine, tick_interval=1.0)
    return TestClient(app)


class TestHealth:
    def test_health_returns_ok(self, client: TestClient) -> None:
        resp = client.get("/health")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] != "lobby"
        assert isinstance(data["tick"], int)

    def test_health_has_running_field(self, client: TestClient) -> None:
        resp = client.get("/health")
        data = resp.json()
        assert "running" in data
        assert isinstance(data["running"], bool)


class TestCharacters:
    def test_characters_returns_list(self, empty_client: TestClient) -> None:
        resp = empty_client.get("/characters")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, list)
        assert len(data) >= 3  # bunker has old_chen, xiao_li, doctor_wang
        ids = [c["id"] for c in data]
        assert "old_chen" in ids
        assert "xiao_li" in ids

    def test_characters_shows_claimed_status(self, empty_client: TestClient) -> None:
        # Before claiming, all should be unclaimed
        data = empty_client.get("/characters").json()
        assert all(not c["claimed"] for c in data)

        # Claim one
        empty_client.post("/register", json={"mode": "claim", "agent_id": "old_chen"})

        data = empty_client.get("/characters").json()
        chen = next(c for c in data if c["id"] == "old_chen")
        assert chen["claimed"] is True


class TestRegister:
    def test_claim_preset_agent(self, empty_client: TestClient) -> None:
        resp = empty_client.post(
            "/register",
            json={"mode": "claim", "agent_id": "old_chen"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == "old_chen"
        assert "token" in data
        assert data["scene"] == "doomsday_bunker"
        assert "character" in data

    def test_claim_unknown_agent_404(self, empty_client: TestClient) -> None:
        resp = empty_client.post(
            "/register",
            json={"mode": "claim", "agent_id": "ghost"},
        )
        assert resp.status_code == 404

    def test_create_new_agent(self, empty_client: TestClient) -> None:
        resp = empty_client.post(
            "/register",
            json={
                "mode": "create",
                "agent_id": "newcomer",
                "character": {"personality": "curious"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == "newcomer"
        assert data["character"]["personality"] == "curious"

    def test_create_collides_with_preset_409(self, empty_client: TestClient) -> None:
        resp = empty_client.post(
            "/register",
            json={"mode": "create", "agent_id": "old_chen"},
        )
        assert resp.status_code == 409

    def test_register_multiple_agents(self, empty_client: TestClient) -> None:
        r1 = empty_client.post(
            "/register",
            json={"mode": "claim", "agent_id": "old_chen"},
        )
        r2 = empty_client.post(
            "/register",
            json={"mode": "claim", "agent_id": "xiao_li"},
        )
        assert r1.status_code == 200
        assert r2.status_code == 200
        assert r1.json()["token"] != r2.json()["token"]

    def test_invalid_mode_400(self, empty_client: TestClient) -> None:
        resp = empty_client.post("/register", json={"mode": "invalid", "agent_id": "x"})
        assert resp.status_code == 422  # Pydantic Literal validation


class TestPerceive:
    def test_perceive_with_agent_id(self, client: TestClient) -> None:
        """Perceive using agent_id query param (no token needed)."""
        engine = client.app.state.engine  # type: ignore[union-attr]
        engine.step()

        resp = client.get("/perceive", params={"agent_id": "old_chen"})
        assert resp.status_code == 200
        data = resp.json()
        assert "tick" in data
        assert "self_state" in data
        assert "events" in data
        assert "action_options" in data

    def test_perceive_with_token(self, empty_client: TestClient) -> None:
        """Perceive using token from claim registration."""
        token = empty_client.post("/register", json={"mode": "claim", "agent_id": "old_chen"}).json()["token"]
        engine = empty_client.app.state.engine  # type: ignore[union-attr]
        engine.step()

        resp = empty_client.get("/perceive", params={"token": token})
        assert resp.status_code == 200
        data = resp.json()
        assert "self_state" in data

    def test_perceive_invalid_token(self, client: TestClient) -> None:
        resp = client.get("/perceive", params={"token": "bad"})
        assert resp.status_code == 401

    def test_perceive_unregistered_agent_404(self, empty_client: TestClient) -> None:
        resp = empty_client.get("/perceive", params={"agent_id": "ghost"})
        assert resp.status_code == 404

    def test_perceive_has_action_options(self, client: TestClient) -> None:
        engine = client.app.state.engine  # type: ignore[union-attr]
        engine.step()

        data = client.get("/perceive", params={"agent_id": "old_chen"}).json()
        options = data["action_options"]
        assert "move" in options
        assert "say" in options
        # Verify compact format: {action: {param: type_or_enum}}
        assert isinstance(options["move"], dict)
        assert "to" in options["move"]


class TestAct:
    def test_act_with_agent_id(self, client: TestClient) -> None:
        resp = client.post(
            "/act",
            json={
                "agent_id": "old_chen",
                "action": "say",
                "params": {"message": "hello"},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["queued"] is True

    def test_act_with_token(self, empty_client: TestClient) -> None:
        token = empty_client.post("/register", json={"mode": "claim", "agent_id": "old_chen"}).json()["token"]
        resp = empty_client.post(
            "/act",
            json={
                "token": token,
                "action": "say",
                "params": {"message": "hello"},
            },
        )
        assert resp.status_code == 200
        assert resp.json()["queued"] is True

    def test_act_invalid_token(self, client: TestClient) -> None:
        resp = client.post(
            "/act",
            json={
                "token": "bad",
                "action": "move",
                "params": {},
            },
        )
        assert resp.status_code == 401

    def test_act_with_think_interval(self, client: TestClient) -> None:
        resp = client.post(
            "/act",
            json={
                "agent_id": "old_chen",
                "action": "say",
                "params": {"message": "hello"},
                "think_interval": 5,
            },
        )
        assert resp.status_code == 200
        engine = client.app.state.engine  # type: ignore[union-attr]
        assert engine.get_think_interval("old_chen") == 5

    def test_act_then_step_processes(self, client: TestClient) -> None:
        """Move is mechanical — executes immediately via submit().

        Verify via state change, not step() results.
        """
        resp = client.post(
            "/act",
            json={
                "agent_id": "old_chen",
                "action": "move",
                "params": {"to": "hallway"},
            },
        )
        assert resp.status_code == 200
        engine = client.app.state.engine  # type: ignore[union-attr]
        # Mechanical action already executed
        assert engine.state.get("old_chen")["location"] == "hallway"  # type: ignore[index]
        engine.step()  # still needed for auto_tick/consequences/perceiver


class TestEvents:
    def test_events_no_changes_field(self) -> None:
        """Verify ChangeHistory references are removed from stream endpoint."""
        import secrets
        import shutil

        run_id = "test_" + secrets.token_hex(4)
        config_path = CONFIGS_DIR / "bunker.yaml"
        recorder = RunRecorder(
            run_id=run_id,
            config_path=config_path,
            scene_id="bunker",
            dm_model="",
        )
        engine = WorldEngine(config_path, recorder=recorder)
        engine.register_from_config()
        engine.save_state()
        app = create_app(engine, tick_interval=1.0, run_id=run_id)
        client = TestClient(app)
        try:
            engine.step()
            resp = client.get(f"/api/runs/{run_id}/stream")
            assert resp.status_code == 200
            data = resp.json()
            assert "events" in data
            assert "changes" not in data
        finally:
            run_dir = Path.home() / ".worldseed" / "runs" / run_id
            if run_dir.exists():
                shutil.rmtree(run_dir)


class TestFullCycle:
    def test_register_act_perceive_cycle(self, empty_client: TestClient) -> None:
        """Full cycle: register -> act -> step -> perceive."""
        token = empty_client.post("/register", json={"mode": "claim", "agent_id": "old_chen"}).json()["token"]

        empty_client.post(
            "/act",
            json={
                "token": token,
                "action": "move",
                "params": {"to": "hallway"},
            },
        )

        engine = empty_client.app.state.engine  # type: ignore[union-attr]
        engine.step()

        data = empty_client.get("/perceive", params={"token": token}).json()
        assert data["self_state"] is not None
        # Chen moved to hallway
        assert data["self_state"].get("location") == "hallway"
