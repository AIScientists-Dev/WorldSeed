"""Adversarial tests -- probe edge cases, injection attempts, malicious input.

Tests verify the engine handles hostile or unexpected input gracefully:
no crashes, no silent corruption, clear error reporting.
"""

from __future__ import annotations

import time

from fastapi.testclient import TestClient

from worldseed.engine.inbox import (
    Inbox,
    InboxEvent,
    InboxManager,
)
from worldseed.engine.wakeup import WakeupEvaluator
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


def _mini_config(
    *,
    actions: dict[str, ActionConfig] | None = None,
    agents: list[AgentConfig] | None = None,
) -> SceneConfig:
    """Build a minimal inline SceneConfig."""
    return SceneConfig(
        scene=SceneMetaConfig(
            id="adversarial_test",
            description="Adversarial test scene",
        ),
        entities=[
            EntityConfig(
                id="room",
                type="space",
                properties={"description": "A room"},
            ),
        ],
        agents=agents
        or [
            AgentConfig(
                id="alice",
                properties={"location": "room", "hp": 100},
                character={"personality": "tester"},
            ),
        ],
        actions=actions
        or {
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
            "give": ActionConfig(
                description="Give something",
                params=[
                    ParamConfig(name="target", type="entity_ref", required=True),
                    ParamConfig(name="amount", type="number", required=True),
                ],
            ),
            "wait": ActionConfig(description="Do nothing"),
        },
    )


def _build_engine(config: SceneConfig | None = None) -> WorldEngine:
    config = config or _mini_config()
    engine = WorldEngine(config=config)
    engine.register_from_config()
    return engine


def _make_app(
    config: SceneConfig | None = None,
) -> tuple[TestClient, WorldEngine]:
    config = config or _mini_config()
    engine = WorldEngine(config=config)
    engine.register_from_config()
    app = create_app(engine)
    client = TestClient(app)
    return client, engine


def _auth_ws(ws: object) -> dict:
    ws.send_json({"type": "auth", "gateway_token": GW_TOKEN})  # type: ignore[union-attr]
    return ws.receive_json()  # type: ignore[union-attr]


class TestInjectionViaParams:
    """$-prefixed param values cannot inject into path resolution."""

    def test_dollar_prefixed_param_value_no_injection(self) -> None:
        """A param value like "$agent.hp" is treated as a
        literal string, not resolved as a path."""
        engine = _build_engine()
        engine.submit("alice", "say", {"message": "$agent.hp"})
        engine.step()  # must not crash
        entity = engine.state.get("alice")
        assert entity is not None
        assert entity["hp"] == 100

    def test_dollar_agent_in_message(self) -> None:
        """$agent in a free_text param is a string, not entity ref."""
        engine = _build_engine()
        engine.submit("alice", "say", {"message": "$agent"})
        engine.step()  # must not crash

    def test_path_traversal_in_param(self) -> None:
        """Path traversal chars in param should not cause issues."""
        engine = _build_engine()
        engine.submit("alice", "say", {"message": "../../etc/passwd"})
        engine.step()  # must not crash

    def test_null_byte_in_param(self) -> None:
        """Null byte in a param value should not cause issues."""
        engine = _build_engine()
        engine.submit("alice", "say", {"message": "hello\x00world"})
        engine.step()  # must not crash


class TestHugeParams:
    """Very large param dicts do not crash the engine."""

    def test_1000_extra_params(self) -> None:
        """Action with 1000 extra params should not crash."""
        engine = _build_engine()
        params = {"message": "hello"}
        for i in range(1000):
            params[f"extra_{i}"] = f"value_{i}"
        result = engine.validate_params("say", params)
        assert result is None  # valid (extra params allowed)

        engine.submit("alice", "say", params)
        engine.step()  # must not crash

    def test_large_param_values(self) -> None:
        """Param with very large string value should not crash."""
        engine = _build_engine()
        huge_msg = "x" * 100_000
        result = engine.validate_params("say", {"message": huge_msg})
        assert result is None

        engine.submit("alice", "say", {"message": huge_msg})
        engine.step()  # must not crash


class TestEmptyActionString:
    """Behavior with empty or missing action strings."""

    def test_empty_action_returns_unknown(self) -> None:
        """action="" should return unknown_action error."""
        engine = _build_engine()
        result = engine.validate_params("", {})
        assert result is not None
        assert result["code"] == "unknown_action"
        assert result["available_actions"]

    def test_whitespace_action_returns_unknown(self) -> None:
        """action="  " should return unknown_action error."""
        engine = _build_engine()
        result = engine.validate_params("   ", {})
        assert result is not None
        assert result["code"] == "unknown_action"

    def test_ws_empty_action_returns_error(self) -> None:
        """WebSocket act with empty action returns error."""
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            _auth_ws(ws)
            ws.send_json(
                {
                    "type": "act",
                    "request_id": "ea1",
                    "agent_id": "alice",
                    "action": "",
                }
            )
            msg = ws.receive_json()
            assert msg["type"] == "error"
            assert "action is required" in msg["detail"]


class TestSpecialCharsInAction:
    """Action names with special characters."""

    def test_shell_injection_action_name(self) -> None:
        """action="say; rm -rf /" returns unknown_action error."""
        engine = _build_engine()
        result = engine.validate_params("say; rm -rf /", {})
        assert result is not None
        assert result["code"] == "unknown_action"
        assert "say; rm -rf /" in result["message"]

    def test_sql_injection_action_name(self) -> None:
        """SQL injection in action name returns unknown_action."""
        engine = _build_engine()
        result = engine.validate_params("say' OR '1'='1", {})
        assert result is not None
        assert result["code"] == "unknown_action"

    def test_newline_in_action_name(self) -> None:
        """Newline in action name returns unknown_action error."""
        engine = _build_engine()
        result = engine.validate_params("say\nrm -rf /", {})
        assert result is not None
        assert result["code"] == "unknown_action"

    def test_unicode_action_name(self) -> None:
        """Unicode action name returns unknown_action error."""
        engine = _build_engine()
        result = engine.validate_params("\u6d4b\u8bd5\u52a8\u4f5c", {})
        assert result is not None
        assert result["code"] == "unknown_action"


class TestNestedParamsBomb:
    """Deeply nested dicts in params."""

    def test_deeply_nested_params(self) -> None:
        """Deeply nested dict in params should not crash."""
        engine = _build_engine()
        nested: dict = {"value": "deep"}
        for _ in range(100):
            nested = {"inner": nested}
        params = {"message": "hi", "metadata": nested}
        result = engine.validate_params("say", params)
        assert result is None

        engine.submit("alice", "say", params)
        engine.step()  # must not crash

    def test_circular_like_params(self) -> None:
        """Self-referential-looking strings should not crash."""
        engine = _build_engine()
        params = {
            "message": "hello",
            "ref": "$agent.$agent.$agent",
        }
        result = engine.validate_params("say", params)
        assert result is None

        engine.submit("alice", "say", params)
        engine.step()  # must not crash


class TestPushEventSpam:
    """WakeupEvaluator performance with massive inbox."""

    def test_10000_push_events_wakeup_fast(self) -> None:
        """10000 push events -- evaluator short-circuits fast."""
        evaluator = WakeupEvaluator()
        inbox = Inbox("agent_1")

        for i in range(10_000):
            inbox.append_event(
                InboxEvent(
                    tick=i,
                    type=f"event_{i}",
                    source="spammer",
                    detail=f"spam {i}",
                    push=True,
                )
            )

        start = time.monotonic()
        result = evaluator.evaluate(inbox)
        elapsed = time.monotonic() - start

        assert result.should_wake is True
        assert elapsed < 1.0, f"Took {elapsed:.3f}s"

    def test_10000_non_push_events_wakeup_fast(self) -> None:
        """10000 non-push events -- full scan still fast."""
        evaluator = WakeupEvaluator()
        inbox = Inbox("agent_1")

        for i in range(10_000):
            inbox.append_event(
                InboxEvent(
                    tick=i,
                    type=f"event_{i}",
                    source="spammer",
                    detail=f"spam {i}",
                    push=False,
                )
            )

        start = time.monotonic()
        result = evaluator.evaluate(inbox)
        elapsed = time.monotonic() - start

        assert result.should_wake is False
        assert elapsed < 1.0, f"Took {elapsed:.3f}s"

    def test_evaluate_all_many_inboxes(self) -> None:
        """100 inboxes each with 100 push events."""
        evaluator = WakeupEvaluator()
        mgr = InboxManager()

        for agent_idx in range(100):
            inbox = mgr.get_or_create(f"agent_{agent_idx}")
            for i in range(100):
                inbox.append_event(
                    InboxEvent(
                        tick=i,
                        type="spam",
                        source="spammer",
                        detail="",
                        push=True,
                    )
                )

        start = time.monotonic()
        results = evaluator.evaluate_all(mgr)
        elapsed = time.monotonic() - start

        assert len(results) == 100
        assert all(r.should_wake for r in results)
        assert elapsed < 1.0, f"Took {elapsed:.3f}s"


class TestConcurrentActSubmissions:
    """Multiple agents submitting actions in the same tick."""

    def test_multiple_agents_same_tick(self) -> None:
        """10 agents submit mechanical actions, all execute immediately."""
        from worldseed.engine.rules_engine import ActionResult

        agents = [
            AgentConfig(
                id=f"agent_{i}",
                properties={"location": "room"},
                character={"personality": "tester"},
            )
            for i in range(10)
        ]
        config = _mini_config(agents=agents)
        engine = _build_engine(config)

        results = []
        for i in range(10):
            r = engine.submit(f"agent_{i}", "say", {"message": f"hello from {i}"})
            results.append(r)

        assert len(results) == 10
        assert all(isinstance(r, ActionResult) and r.success for r in results)
        engine.step()  # still needed for auto_tick/consequences/perceiver

    def test_same_agent_multiple_mechanical_actions_all_succeed(self) -> None:
        """Same agent submits 3 mechanical actions — all execute immediately.
        Mechanical actions bypass the ActionQueue (no one-per-tick limit)."""
        from worldseed.engine.rules_engine import ActionResult

        engine = _build_engine()

        r1 = engine.submit("alice", "say", {"message": "first"})
        r2 = engine.submit("alice", "say", {"message": "second"})
        r3 = engine.submit("alice", "say", {"message": "third"})

        assert isinstance(r1, ActionResult) and r1.success
        assert isinstance(r2, ActionResult) and r2.success
        assert isinstance(r3, ActionResult) and r3.success

        engine.step()  # still needed for auto_tick/consequences/perceiver


class TestParamTypeMismatch:
    """Param type mismatches -- should not crash the engine."""

    def test_number_param_gets_string(self) -> None:
        """number param receiving string should not crash."""
        engine = _build_engine()
        result = engine.validate_params("give", {"target": "bob", "amount": "not_a_number"})
        assert result is None  # checks presence only

        engine.submit("alice", "give", {"target": "bob", "amount": "not_a_number"})
        engine.step()  # must not crash

    def test_entity_ref_param_gets_nonexistent(self) -> None:
        """entity_ref to nonexistent entity should not crash."""
        engine = _build_engine()
        result = engine.validate_params("give", {"target": "nonexistent", "amount": 5})
        assert result is None

        engine.submit("alice", "give", {"target": "nonexistent", "amount": 5})
        engine.step()  # must not crash

    def test_bool_in_number_param(self) -> None:
        """Bool in a number param should not crash."""
        engine = _build_engine()
        engine.submit("alice", "give", {"target": "room", "amount": True})
        engine.step()  # must not crash

    def test_list_in_string_param(self) -> None:
        """List in a string param should not crash."""
        engine = _build_engine()
        engine.submit("alice", "say", {"message": ["a", "b", "c"]})
        engine.step()  # must not crash

    def test_none_in_required_param(self) -> None:
        """None value for a required param should not crash."""
        engine = _build_engine()
        result = engine.validate_params("say", {"message": None})
        assert result is None  # key is present

        engine.submit("alice", "say", {"message": None})
        engine.step()  # must not crash


class TestWSAdversarial:
    """Adversarial tests through the WebSocket handler."""

    def test_ws_huge_message(self) -> None:
        """Very large JSON message should not crash the server."""
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            _auth_ws(ws)
            ws.send_json(
                {
                    "type": "act",
                    "request_id": "huge",
                    "agent_id": "alice",
                    "action": "say",
                    "params": {"message": "x" * 50_000},
                }
            )
            msg = ws.receive_json()
            assert msg["type"] == "act_ok"

    def test_ws_rapid_fire_messages(self) -> None:
        """Rapid-fire mechanical actions should all get responses.
        Mechanical actions execute immediately — all succeed (no queue limit)."""
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            _auth_ws(ws)

            for i in range(50):
                ws.send_json(
                    {
                        "type": "act",
                        "request_id": f"rf_{i}",
                        "agent_id": "alice",
                        "action": "wait",
                    }
                )

            for i in range(50):
                msg = ws.receive_json()
                assert msg["request_id"] == f"rf_{i}"
                assert msg["type"] == "act_ok"

    def test_ws_mixed_valid_and_invalid(self) -> None:
        """Mix of valid and invalid -- each gets appropriate response.
        Mechanical actions execute immediately (no per-tick limit).
        Invalid action names are still rejected via ValueError."""
        client, engine = _make_app()

        with client.websocket_connect("/ws") as ws:
            _auth_ws(ws)

            # Valid mechanical action
            ws.send_json(
                {
                    "type": "act",
                    "request_id": "v1",
                    "agent_id": "alice",
                    "action": "wait",
                }
            )
            msg = ws.receive_json()
            assert msg["type"] == "act_ok"

            # Invalid action name — rejected by validate_params (ValueError)
            ws.send_json(
                {
                    "type": "act",
                    "request_id": "i1",
                    "agent_id": "alice",
                    "action": "nonexistent_action",
                }
            )
            msg = ws.receive_json()
            assert msg["type"] == "act_error"
            assert "nonexistent_action" in msg["detail"]

            # Another valid mechanical action — succeeds (no per-tick limit)
            ws.send_json(
                {
                    "type": "act",
                    "request_id": "v2",
                    "agent_id": "alice",
                    "action": "say",
                    "params": {"message": "still working"},
                }
            )
            msg = ws.receive_json()
            assert msg["type"] == "act_ok"
