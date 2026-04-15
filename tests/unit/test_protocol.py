"""Tests for protocol data structures."""

from __future__ import annotations

from worldseed.models.action import ActionSubmission
from worldseed.models.config_schema import EffectConfig
from worldseed.protocol.agent import AgentAction, AgentPerception
from worldseed.protocol.dm import DMContext, DMResponse


class TestDMContext:
    def test_construct(self) -> None:
        action = ActionSubmission(agent_id="chen", action_type="observe")
        ctx = DMContext(
            action=action,
            world_state="old_chen (agent):\n  hp: 100",
            recent_events="  (none)",
            scene_description="A bunker.",
            hint="Judge physical plausibility",
            allowed_ops=["set", "increment"],
            max_effects=5,
        )
        assert ctx.action.agent_id == "chen"
        assert ctx.scene_description == "A bunker."
        assert ctx.hint == "Judge physical plausibility"
        assert ctx.allowed_ops == ["set", "increment"]
        assert ctx.max_effects == 5

    def test_empty_context(self) -> None:
        ctx = DMContext(
            action=ActionSubmission(agent_id="x", action_type="attempt"),
            world_state="",
            recent_events="  (none)",
            scene_description="",
            hint="",
            allowed_ops=[],
            max_effects=0,
        )
        assert ctx.world_state == ""


class TestDMResponse:
    def test_narrative_only(self) -> None:
        resp = DMResponse(narrative="Nothing happens.")
        assert resp.narrative == "Nothing happens."
        assert resp.effects == []

    def test_with_effects(self) -> None:
        effects = [
            EffectConfig(
                operator="set",
                target="food.quantity",
                value=10,
            ),
            EffectConfig(
                operator="emit_event",
                type="discovery",
                detail="Found something",
                ttl=2,
            ),
        ]
        resp = DMResponse(narrative="You find food.", effects=effects)
        assert len(resp.effects) == 2
        assert resp.effects[0].operator == "set"
        assert resp.effects[1].operator == "emit_event"


class TestAgentPerception:
    def test_construct(self) -> None:
        p = AgentPerception(
            self_state={"hp": 100},
            nearby_entities={"food": {"quantity": 20}},
            nearby_agents={"li": {"mood": "calm"}},
            events=[{"type": "say", "detail": "hello"}],
            whispers=[],
        )
        assert p.self_state["hp"] == 100
        assert "food" in p.nearby_entities
        assert len(p.events) == 1
        assert p.whispers == []

    def test_defaults(self) -> None:
        p = AgentPerception(
            self_state={},
            nearby_entities={},
            nearby_agents={},
            events=[],
            whispers=[],
        )
        assert p.action_options == {}

    def test_with_action_options(self) -> None:
        p = AgentPerception(
            self_state={},
            nearby_entities={},
            nearby_agents={},
            events=[],
            whispers=[],
            action_options={
                "move": {"to": ["hallway", "entrance"]},
                "say": {"message": "free_text"},
                "attempt": {"description": "free_text"},
            },
        )
        assert "attempt" in p.action_options
        assert p.action_options["move"]["to"] == ["hallway", "entrance"]


class TestAgentAction:
    def test_construct(self) -> None:
        a = AgentAction(
            thought="I should move.",
            action_type="move",
            params={"to": "hallway"},
        )
        assert a.thought == "I should move."
        assert a.action_type == "move"
        assert a.params["to"] == "hallway"

    def test_default_think_interval(self) -> None:
        a = AgentAction(thought="", action_type="wait")
        assert a.think_interval == 5

    def test_custom_think_interval(self) -> None:
        a = AgentAction(
            thought="urgent",
            action_type="say",
            think_interval=1,
        )
        assert a.think_interval == 1

    def test_empty_params_default(self) -> None:
        a = AgentAction(thought="", action_type="wait")
        assert a.params == {}
