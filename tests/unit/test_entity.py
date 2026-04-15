"""Tests for data models."""

from worldseed.models import (
    ActionSubmission,
    Entity,
    Event,
)


class TestEntity:
    def test_create_full(self) -> None:
        entity = Entity(
            id="old_chen",
            type="agent",
            _data={
                "location": "sleeping_quarters",
                "private_stash": 0,
                "trusts": {"xiao_li": 40},
            },
        )
        assert entity.id == "old_chen"
        assert entity.type == "agent"
        assert entity["location"] == "sleeping_quarters"
        assert entity["trusts"]["xiao_li"] == 40

    def test_defaults(self) -> None:
        entity = Entity(id="hallway", type="space")
        assert entity.data == {}

    def test_mutable_defaults_not_shared(self) -> None:
        a = Entity(id="a", type="space")
        b = Entity(id="b", type="space")
        a["x"] = 1
        assert "x" not in b


class TestEvent:
    def test_create(self) -> None:
        event = Event(
            tick=5,
            type="move",
            source="old_chen",
            detail="old_chen moved to hallway",
            ttl=1,
            scope="same_location",
        )
        assert event.tick == 5
        assert event.ttl == 1

    def test_permanent_ttl(self) -> None:
        event = Event(
            tick=1,
            type="landmark",
            source="system",
            detail="world created",
            ttl="permanent",
            scope="global",
        )
        assert event.ttl == "permanent"


class TestActionSubmission:
    def test_create_full(self) -> None:
        action = ActionSubmission(
            agent_id="old_chen",
            action_type="move",
            params={"to": "hallway"},
            tick_submitted=3,
        )
        assert action.agent_id == "old_chen"
        assert action.params["to"] == "hallway"

    def test_defaults(self) -> None:
        action = ActionSubmission(agent_id="chen", action_type="wait")
        assert action.params == {}
        assert action.tick_submitted == 0
