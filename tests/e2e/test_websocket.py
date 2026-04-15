"""Tests for WebSocket gateway endpoint and connector."""

from __future__ import annotations

import asyncio

from fastapi.testclient import TestClient

from tests.helpers import CONFIGS_DIR
from worldseed.connector.websocket import WebSocketConnector
from worldseed.server.app import create_app
from worldseed.server.websocket import ConnectionManager, GatewayConnection
from worldseed.world import WorldEngine

GW_TOKEN = "worldseed-gw-token"


def _make_app() -> tuple[TestClient, WorldEngine]:
    """Create a test app with the minimal config."""
    engine = WorldEngine(CONFIGS_DIR / "minimal.yaml")
    engine.register_from_config()
    app = create_app(engine)
    client = TestClient(app)
    return client, engine


class TestWebSocketAuth:
    def test_auth_success(self) -> None:
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "gateway_token": GW_TOKEN})
            msg = ws.receive_json()
            assert msg["type"] == "auth_ok"
            assert "scene" in msg
            assert "agents" in msg
            agent_ids = [a["id"] if isinstance(a, dict) else a for a in msg["agents"]]
            assert "agent_1" in agent_ids

    def test_auth_invalid_token(self) -> None:
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "gateway_token": "bad_token"})
            msg = ws.receive_json()
            assert msg["type"] == "auth_error"
            assert "invalid gateway token" in msg["detail"]

    def test_auth_wrong_first_message(self) -> None:
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "perceive", "agent_id": "agent_1"})
            msg = ws.receive_json()
            assert msg["type"] == "auth_error"
            assert "first message must be auth" in msg["detail"]


class TestWebSocketPerceive:
    def test_perceive(self) -> None:
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "gateway_token": GW_TOKEN})
            ws.receive_json()  # auth_ok

            ws.send_json(
                {
                    "type": "perceive",
                    "request_id": "r1",
                    "agent_id": "agent_1",
                }
            )
            msg = ws.receive_json()
            assert msg["type"] == "perception"
            assert msg["request_id"] == "r1"
            assert msg["agent_id"] == "agent_1"
            assert "tick" in msg
            assert "self_state" in msg
            assert "nearby_entities" in msg
            assert "nearby_agents" in msg
            assert "events" in msg
            assert "whispers" in msg
            assert "action_options" in msg

    def test_perceive_missing_agent_id(self) -> None:
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "gateway_token": GW_TOKEN})
            ws.receive_json()  # auth_ok

            ws.send_json({"type": "perceive", "request_id": "r1"})
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "agent_id is required" in msg["detail"]

    def test_perceive_unknown_agent(self) -> None:
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "gateway_token": GW_TOKEN})
            ws.receive_json()  # auth_ok

            ws.send_json(
                {
                    "type": "perceive",
                    "request_id": "r1",
                    "agent_id": "nonexistent",
                }
            )
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "not found" in msg["detail"]


class TestWebSocketAct:
    def test_act(self) -> None:
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "gateway_token": GW_TOKEN})
            ws.receive_json()  # auth_ok

            ws.send_json(
                {
                    "type": "act",
                    "request_id": "r2",
                    "agent_id": "agent_1",
                    "action": "move",
                    "params": {"to": "room_b"},
                }
            )
            msg = ws.receive_json()
            assert msg["type"] == "act_ok"
            assert msg["request_id"] == "r2"
            assert msg["agent_id"] == "agent_1"
            assert "tick" in msg

    def test_act_missing_agent_id(self) -> None:
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "gateway_token": GW_TOKEN})
            ws.receive_json()  # auth_ok

            ws.send_json(
                {
                    "type": "act",
                    "request_id": "r3",
                    "action": "move",
                    "params": {},
                }
            )
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "agent_id is required" in msg["detail"]

    def test_act_missing_action(self) -> None:
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "gateway_token": GW_TOKEN})
            ws.receive_json()  # auth_ok

            ws.send_json(
                {
                    "type": "act",
                    "request_id": "r3",
                    "agent_id": "agent_1",
                    "params": {},
                }
            )
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "action is required" in msg["detail"]


class TestWebSocketUnknownType:
    def test_unknown_message_type(self) -> None:
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "gateway_token": GW_TOKEN})
            ws.receive_json()  # auth_ok

            ws.send_json({"type": "dance", "request_id": "r4"})
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "unknown message type" in msg["detail"]


class TestWebSocketConnector:
    def test_satisfies_protocol(self) -> None:
        from worldseed.connector.base import ConnectorProvider

        manager = ConnectionManager()
        connector = WebSocketConnector(manager)
        assert isinstance(connector, ConnectorProvider)

    def test_notify_no_connection_raises(self) -> None:
        """notify() raises ConnectionError when no gateway is connected."""
        import pytest

        async def _test() -> None:
            manager = ConnectionManager()
            connector = WebSocketConnector(manager)
            with pytest.raises(ConnectionError, match="No gateway connection"):
                await connector.notify("agent_1", "test_reason")

        asyncio.run(_test())

    def test_close(self) -> None:
        async def _test() -> None:
            manager = ConnectionManager()
            connector = WebSocketConnector(manager)
            await connector.close()

        asyncio.run(_test())


class TestWebSocketThinkInterval:
    def test_act_with_think_interval(self) -> None:
        """think_interval in act updates the engine."""
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "gateway_token": GW_TOKEN})
            ws.receive_json()  # auth_ok

            ws.send_json(
                {
                    "type": "act",
                    "request_id": "ti1",
                    "agent_id": "agent_1",
                    "action": "wait",
                    "params": {},
                    "think_interval": 10,
                }
            )
            msg = ws.receive_json()
            assert msg["type"] == "act_ok"
            assert msg["request_id"] == "ti1"

        # Engine should have stored the new interval
        assert engine.get_think_interval("agent_1") == 10

    def test_act_with_invalid_think_interval(self) -> None:
        """Non-numeric think_interval is silently ignored."""
        client, engine = _make_app()
        original = engine.get_think_interval("agent_1")

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "gateway_token": GW_TOKEN})
            ws.receive_json()  # auth_ok

            ws.send_json(
                {
                    "type": "act",
                    "request_id": "ti2",
                    "agent_id": "agent_1",
                    "action": "wait",
                    "params": {},
                    "think_interval": "not_a_number",
                }
            )
            msg = ws.receive_json()
            # Should still succeed — invalid interval is ignored
            assert msg["type"] == "act_ok"
            assert msg["request_id"] == "ti2"

        # Interval unchanged
        assert engine.get_think_interval("agent_1") == original


class TestWebSocketPerceiveNonAgent:
    def test_perceive_non_agent_entity(self) -> None:
        """Perceive with a space entity ID returns error."""
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "gateway_token": GW_TOKEN})
            ws.receive_json()  # auth_ok

            ws.send_json(
                {
                    "type": "perceive",
                    "request_id": "na1",
                    "agent_id": "room_a",
                }
            )
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "not found" in msg["detail"]
            assert msg["request_id"] == "na1"


class TestWebSocketMultiAgent:
    def test_multiple_agents_single_connection(self) -> None:
        """One WS connection can perceive/act for different agents."""
        client, engine = _make_app()

        # Register a second agent in the world
        engine.registry.register(
            agent_id="agent_2",
            properties={"location": "room_b"},
            character={"personality": "Second agent"},
        )

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "gateway_token": GW_TOKEN})
            ws.receive_json()  # auth_ok

            # Perceive as agent_1
            ws.send_json(
                {
                    "type": "perceive",
                    "request_id": "ma1",
                    "agent_id": "agent_1",
                }
            )
            p1 = ws.receive_json()
            assert p1["type"] == "perception"
            assert p1["agent_id"] == "agent_1"

            # Perceive as agent_2
            ws.send_json(
                {
                    "type": "perceive",
                    "request_id": "ma2",
                    "agent_id": "agent_2",
                }
            )
            p2 = ws.receive_json()
            assert p2["type"] == "perception"
            assert p2["agent_id"] == "agent_2"

            # Act as agent_1
            ws.send_json(
                {
                    "type": "act",
                    "request_id": "ma3",
                    "agent_id": "agent_1",
                    "action": "wait",
                    "params": {},
                }
            )
            a1 = ws.receive_json()
            assert a1["type"] == "act_ok"
            assert a1["agent_id"] == "agent_1"

            # Act as agent_2
            ws.send_json(
                {
                    "type": "act",
                    "request_id": "ma4",
                    "agent_id": "agent_2",
                    "action": "wait",
                    "params": {},
                }
            )
            a2 = ws.receive_json()
            assert a2["type"] == "act_ok"
            assert a2["agent_id"] == "agent_2"


class TestWebSocketEdgeCases:
    def test_invalid_json_in_message_loop(self) -> None:
        """Non-JSON text after auth returns error, not crash."""
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "gateway_token": GW_TOKEN})
            ws.receive_json()  # auth_ok

            ws.send_text("this is not json {{{")
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "invalid JSON" in msg["detail"]

    def test_pong_message_accepted(self) -> None:
        """Pong messages are silently accepted (no error)."""
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "gateway_token": GW_TOKEN})
            ws.receive_json()  # auth_ok

            # Send pong — should be accepted silently
            ws.send_json({"type": "pong"})

            # Follow up with a normal message to confirm
            # the connection is still alive and working
            ws.send_json(
                {
                    "type": "perceive",
                    "request_id": "pong1",
                    "agent_id": "agent_1",
                }
            )
            msg = ws.receive_json()
            assert msg["type"] == "perception"
            assert msg["request_id"] == "pong1"

    def test_act_no_params_key(self) -> None:
        """Act without params key defaults to {} and succeeds."""
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "gateway_token": GW_TOKEN})
            ws.receive_json()  # auth_ok

            ws.send_json(
                {
                    "type": "act",
                    "request_id": "np1",
                    "agent_id": "agent_1",
                    "action": "wait",
                }
            )
            msg = ws.receive_json()
            assert msg["type"] == "act_ok"
            assert msg["request_id"] == "np1"
            assert msg["agent_id"] == "agent_1"

    def test_perceive_without_request_id(self) -> None:
        """Perceive without request_id returns null request_id."""
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "gateway_token": GW_TOKEN})
            ws.receive_json()  # auth_ok

            ws.send_json(
                {
                    "type": "perceive",
                    "agent_id": "agent_1",
                }
            )
            msg = ws.receive_json()
            assert msg["type"] == "perception"
            assert msg["request_id"] is None
            assert msg["agent_id"] == "agent_1"

    def test_auth_ok_includes_agents_list(self) -> None:
        """auth_ok response lists all registered agents."""
        client, engine = _make_app()

        # Register a second agent before connecting
        engine.registry.register(
            agent_id="agent_2",
            properties={"location": "room_b"},
            character={"personality": "Second agent"},
        )

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "gateway_token": GW_TOKEN})
            msg = ws.receive_json()
            assert msg["type"] == "auth_ok"
            assert isinstance(msg["agents"], list)
            agent_ids = [a["id"] if isinstance(a, dict) else a for a in msg["agents"]]
            assert "agent_1" in agent_ids
            assert "agent_2" in agent_ids
            assert msg["scene"] == "test_minimal"

    def test_act_invalid_action(self) -> None:
        """Unknown action still queues (attempt fallback)."""
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "gateway_token": GW_TOKEN})
            ws.receive_json()  # auth_ok

            ws.send_json(
                {
                    "type": "act",
                    "request_id": "ia1",
                    "agent_id": "agent_1",
                    "action": "fly_to_the_moon",
                    "params": {"speed": "fast"},
                }
            )
            msg = ws.receive_json()
            # Validation now happens inside engine.submit()
            assert msg["type"] == "act_error"
            assert msg["request_id"] == "ia1"
            assert "fly_to_the_moon" in msg["detail"]


class MockWebSocket:
    """Minimal mock for unit-testing ConnectionManager."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send_json(self, data: dict) -> None:
        self.sent.append(data)


class TestConnectionManager:
    def test_empty_manager(self) -> None:
        manager = ConnectionManager()
        assert manager._gateways == {}

    def test_send_wake_no_gateway(self) -> None:
        async def _test() -> None:
            manager = ConnectionManager()
            result = await manager.send_wake("agent_1", "test")
            assert result is False

        asyncio.run(_test())

    def test_manager_add_registers_connection(self) -> None:
        """add() stores the connection, retrievable by gateway_id."""
        manager = ConnectionManager()
        ws = MockWebSocket()
        conn = GatewayConnection(ws, "gw_1")  # type: ignore[arg-type]
        manager.add(conn)
        assert manager._gateways.get("gw_1") is conn

    def test_manager_add_replaces_duplicate(self) -> None:
        """Second add() with same gateway_id replaces the first."""
        manager = ConnectionManager()
        ws_a = MockWebSocket()
        ws_b = MockWebSocket()
        conn_a = GatewayConnection(ws_a, "gw_1")  # type: ignore[arg-type]
        conn_b = GatewayConnection(ws_b, "gw_1")  # type: ignore[arg-type]
        manager.add(conn_a)
        manager.add(conn_b)
        assert len(manager._gateways) == 1
        assert manager._gateways["gw_1"] is conn_b

    def test_manager_remove_if_current_ignores_stale(self) -> None:
        """remove_if_current with a stale conn leaves the new one."""
        manager = ConnectionManager()
        ws_a = MockWebSocket()
        ws_b = MockWebSocket()
        conn_a = GatewayConnection(ws_a, "gw_1")  # type: ignore[arg-type]
        conn_b = GatewayConnection(ws_b, "gw_1")  # type: ignore[arg-type]
        manager.add(conn_a)
        manager.add(conn_b)  # replaces conn_a
        manager.remove_if_current("gw_1", conn_a)  # stale
        assert manager._gateways.get("gw_1") is conn_b

    def test_manager_send_wake_delivers(self) -> None:
        """send_wake delivers the wake message to mock conn."""

        async def _test() -> None:
            manager = ConnectionManager()
            ws = MockWebSocket()
            conn = GatewayConnection(ws, "gw_1")  # type: ignore[arg-type]
            manager.add(conn)
            result = await manager.send_wake("agent_1", "new_event")
            assert result is True
            assert len(ws.sent) == 1
            assert ws.sent[0] == {
                "type": "wake",
                "agent_id": "agent_1",
                "reason": "new_event",
            }

        asyncio.run(_test())


class TestWebSocketConnectorNotify:
    def test_connector_notify_success(self) -> None:
        """notify() delivers wake through the manager."""

        async def _test() -> None:
            manager = ConnectionManager()
            ws = MockWebSocket()
            conn = GatewayConnection(ws, "gw_1")  # type: ignore[arg-type]
            manager.add(conn)
            connector = WebSocketConnector(manager)
            await connector.notify("agent_1", "tick_ready")
            assert len(ws.sent) == 1
            assert ws.sent[0]["type"] == "wake"
            assert ws.sent[0]["agent_id"] == "agent_1"
            assert ws.sent[0]["reason"] == "tick_ready"

        asyncio.run(_test())


class TestWebSocketDisconnectCleanup:
    def test_disconnect_cleanup(self) -> None:
        """After disconnect, send_wake returns False."""
        client, engine = _make_app()

        # Connect, auth, then disconnect
        with client.websocket_connect("/ws") as ws:
            ws.send_json({"type": "auth", "gateway_token": GW_TOKEN})
            ws.receive_json()  # auth_ok
        # exiting `with` block disconnects the WS

        # Verify the manager has no gateways left
        async def _check() -> None:
            mgr: ConnectionManager = client.app.state.ws_manager  # type: ignore[union-attr]
            result = await mgr.send_wake("agent_1", "post_dc")
            assert result is False

        asyncio.run(_check())
