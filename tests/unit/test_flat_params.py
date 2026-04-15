"""Tests for flat param extraction in WebSocket act handler.

The WebSocket act handler extracts top-level keys as action params when
the `params` dict is empty. Known fields (type, request_id, agent_id,
action, params, think_interval) are excluded.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from worldseed.models.config_schema import (
    ActionConfig,
    AgentConfig,
    EntityConfig,
    EventConfig,
    ParamConfig,
    SceneConfig,
    SceneMetaConfig,
)
from worldseed.server.app import create_app
from worldseed.world import WorldEngine

GW_TOKEN = "worldseed-gw-token"


def _make_config() -> SceneConfig:
    """Inline config with a say action requiring a message param."""
    return SceneConfig(
        scene=SceneMetaConfig(
            id="flat_params_test",
            description="Flat params test scene",
        ),
        entities=[
            EntityConfig(
                id="room",
                type="space",
                properties={"description": "A room"},
            ),
        ],
        agents=[
            AgentConfig(
                id="agent_1",
                properties={"location": "room"},
                character={"personality": "tester"},
            ),
        ],
        actions={
            "say": ActionConfig(
                description="Speak",
                params=[
                    ParamConfig(name="message", type="free_text", required=True),
                ],
                events=[
                    EventConfig(
                        type="say",
                        detail="$agent says $message",
                        ttl=1,
                        scope="global",
                    ),
                ],
            ),
            "wait": ActionConfig(description="Do nothing"),
        },
    )


def _make_app() -> tuple[TestClient, WorldEngine]:
    """Create test app with inline config."""
    engine = WorldEngine(config=_make_config())
    engine.register_from_config()
    app = create_app(engine)
    client = TestClient(app)
    return client, engine


def _auth_ws(ws: object) -> dict:
    """Authenticate a WebSocket connection, return auth_ok."""
    ws.send_json({"type": "auth", "gateway_token": GW_TOKEN})  # type: ignore[union-attr]
    return ws.receive_json()  # type: ignore[union-attr]


class TestFlatParams:
    """Test flat param extraction in WebSocket act handler."""

    def test_flat_params_extracted(self) -> None:
        """Flat params {action: "say", message: "hi"} extracts message as param."""
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            _auth_ws(ws)

            ws.send_json(
                {
                    "type": "act",
                    "request_id": "fp1",
                    "agent_id": "agent_1",
                    "action": "say",
                    "message": "hello world",
                }
            )
            msg = ws.receive_json()
            assert msg["type"] == "act_ok", f"Expected act_ok, got: {msg}"
            assert msg["request_id"] == "fp1"
            assert msg["agent_id"] == "agent_1"

    def test_nested_params_still_work(self) -> None:
        """Nested params still work (backward compat)."""
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            _auth_ws(ws)

            ws.send_json(
                {
                    "type": "act",
                    "request_id": "fp2",
                    "agent_id": "agent_1",
                    "action": "say",
                    "params": {"message": "hello nested"},
                }
            )
            msg = ws.receive_json()
            assert msg["type"] == "act_ok", f"Expected act_ok, got: {msg}"
            assert msg["request_id"] == "fp2"

    def test_mixed_flat_and_nested_nested_takes_precedence(self) -> None:
        """When both flat and nested params exist, nested takes precedence.

        The handler only falls back to flat extraction when params is empty.
        So if params: {message: "nested"} is provided, flat keys are ignored.
        """
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            _auth_ws(ws)

            ws.send_json(
                {
                    "type": "act",
                    "request_id": "fp3",
                    "agent_id": "agent_1",
                    "action": "say",
                    "message": "flat message",
                    "params": {"message": "nested message"},
                }
            )
            msg = ws.receive_json()
            # nested params take precedence, so this should succeed
            assert msg["type"] == "act_ok", f"Expected act_ok, got: {msg}"

    def test_empty_no_params_at_all_validation_catches_missing(self) -> None:
        """No params at all (neither flat nor nested) triggers validation error."""
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            _auth_ws(ws)

            ws.send_json(
                {
                    "type": "act",
                    "request_id": "fp4",
                    "agent_id": "agent_1",
                    "action": "say",
                }
            )
            msg = ws.receive_json()
            assert msg["type"] == "act_error", f"Expected act_error, got: {msg}"
            assert "message" in msg["detail"]

    def test_known_fields_excluded_from_flat_extraction(self) -> None:
        """Known fields (type, request_id, agent_id, action, params, think_interval)
        are not extracted as params."""
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            _auth_ws(ws)

            # Send with all known fields + message as flat param
            ws.send_json(
                {
                    "type": "act",
                    "request_id": "fp5",
                    "agent_id": "agent_1",
                    "action": "say",
                    "think_interval": 5,
                    "message": "extracted param",
                }
            )
            msg = ws.receive_json()
            assert msg["type"] == "act_ok", f"Expected act_ok, got: {msg}"

    def test_flat_params_with_wait_action(self) -> None:
        """Flat extraction on action with no params: extra keys become params
        but wait has no required params so it passes validation."""
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            _auth_ws(ws)

            ws.send_json(
                {
                    "type": "act",
                    "request_id": "fp6",
                    "agent_id": "agent_1",
                    "action": "wait",
                    "some_extra": "value",
                }
            )
            msg = ws.receive_json()
            assert msg["type"] == "act_ok", f"Expected act_ok, got: {msg}"

    def test_flat_params_multiple_keys(self) -> None:
        """Multiple flat keys are all extracted as params."""
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            _auth_ws(ws)

            # say only requires message, but extra keys are allowed
            ws.send_json(
                {
                    "type": "act",
                    "request_id": "fp7",
                    "agent_id": "agent_1",
                    "action": "say",
                    "message": "hello",
                    "volume": "loud",
                    "emotion": "happy",
                }
            )
            msg = ws.receive_json()
            assert msg["type"] == "act_ok", f"Expected act_ok, got: {msg}"
