"""Tests for Perceiver — DSL-based visibility filtering and inbox delivery."""

from __future__ import annotations

from worldseed.engine.event_log import EventLog
from worldseed.engine.inbox import InboxManager
from worldseed.engine.perceiver import Perceiver
from worldseed.engine.state_store import StateStore
from worldseed.models.config_schema import PerceptionConfig, PreconditionConfig
from worldseed.models.entity import Entity
from worldseed.models.event import Event


def _bunker_store() -> StateStore:
    """Set up the bunker scenario."""
    store = StateStore()
    # Spaces
    store.add(
        Entity(
            id="storage_room",
            type="space",
            _data={
                "description": "Supply storage room",
                "connects_to": ["hallway"],
            },
        )
    )
    store.add(
        Entity(
            id="hallway",
            type="space",
            _data={
                "description": "Central corridor",
                "connects_to": ["storage_room", "sleeping_quarters", "entrance"],
            },
        )
    )
    store.add(
        Entity(
            id="sleeping_quarters",
            type="space",
            _data={
                "description": "Shared sleeping area",
                "connects_to": ["hallway"],
            },
        )
    )
    store.add(
        Entity(
            id="entrance",
            type="space",
            _data={
                "description": "Heavy metal door",
                "connects_to": ["hallway"],
            },
        )
    )
    # Resources (location property needed for DSL visibility rules)
    store.add(
        Entity(
            id="food_supply",
            type="resource",
            _data={
                "quantity": 20,
                "unit": "person-days",
                "location": "storage_room",
                "located_in": ["storage_room"],
            },
        )
    )
    store.add(
        Entity(
            id="water_supply",
            type="resource",
            _data={
                "quantity": 15,
                "unit": "liters",
                "location": "storage_room",
                "located_in": ["storage_room"],
            },
        )
    )
    # Agents
    store.add(
        Entity(
            id="old_chen",
            type="agent",
            _data={"location": "sleeping_quarters", "private_stash": 0},
        )
    )
    store.add(
        Entity(
            id="xiao_li",
            type="agent",
            _data={"location": "sleeping_quarters"},
        )
    )
    store.add(
        Entity(
            id="doctor_wang",
            type="agent",
            _data={"location": "hallway"},
        )
    )
    return store


# Perception config with location-based visibility (spatial filtering).
BUNKER_PERCEPTION = PerceptionConfig(
    visibility=[
        PreconditionConfig(
            operator="check",
            left="$observer.location",
            op="==",
            right="$entity.location",
        )
    ],
    hidden_properties=["private_stash", "goals"],
)

# Perception config with no visibility rules (everything visible).
GLOBAL_PERCEPTION = PerceptionConfig(
    hidden_properties=["private_stash", "goals"],
)


class TestSnapshot:
    def test_snapshot_self_sees_all_properties(self) -> None:
        store = _bunker_store()
        mgr = InboxManager()
        p = Perceiver(store, EventLog(), mgr, BUNKER_PERCEPTION)
        p.deliver(1)
        inbox = mgr.get_or_create("old_chen")
        data = inbox.read()
        assert "private_stash" in data["current_state"].self_state

    def test_snapshot_hidden_properties_filtered(self) -> None:
        store = _bunker_store()
        mgr = InboxManager()
        p = Perceiver(store, EventLog(), mgr, BUNKER_PERCEPTION)
        p.deliver(1)
        inbox = mgr.get_or_create("xiao_li")
        data = inbox.read()
        # xiao_li sees old_chen but not private_stash
        assert "old_chen" in data["current_state"].visible_agents
        assert "private_stash" not in data["current_state"].visible_agents["old_chen"]

    def test_snapshot_visible_entities_same_location(self) -> None:
        store = _bunker_store()
        # Move old_chen to storage_room
        store.update_property("old_chen", "location", "storage_room")
        mgr = InboxManager()
        p = Perceiver(store, EventLog(), mgr, BUNKER_PERCEPTION)
        p.deliver(1)
        inbox = mgr.get_or_create("old_chen")
        data = inbox.read()
        assert "food_supply" in data["current_state"].visible_entities
        assert "water_supply" in data["current_state"].visible_entities

    def test_snapshot_visible_agents_excludes_self(self) -> None:
        store = _bunker_store()
        mgr = InboxManager()
        p = Perceiver(store, EventLog(), mgr, BUNKER_PERCEPTION)
        p.deliver(1)
        inbox = mgr.get_or_create("old_chen")
        data = inbox.read()
        assert "xiao_li" in data["current_state"].visible_agents
        assert "old_chen" not in data["current_state"].visible_agents

    def test_snapshot_no_entities_from_other_locations(self) -> None:
        store = _bunker_store()
        mgr = InboxManager()
        p = Perceiver(store, EventLog(), mgr, BUNKER_PERCEPTION)
        p.deliver(1)
        inbox = mgr.get_or_create("old_chen")
        data = inbox.read()
        # old_chen is in sleeping_quarters, should NOT see food_supply (storage_room)
        assert "food_supply" not in data["current_state"].visible_entities


class TestEventScope:
    def test_event_scope_same_location_delivers_to_all(self) -> None:
        """New Perceiver no longer filters same_location events; all agents receive
        them.
        """
        store = _bunker_store()
        event_log = EventLog()
        event_log.append(
            Event(
                tick=1,
                type="say",
                source="old_chen",
                detail="hello",
                ttl=5,
                scope="same_location",
            )
        )
        mgr = InboxManager()
        p = Perceiver(store, event_log, mgr, BUNKER_PERCEPTION)
        p.deliver(1)
        # All agents receive same_location events (scope filtering is scene-level)
        chen_data = mgr.get_or_create("old_chen").read()
        assert any(e.type == "say" for e in chen_data["events"])
        wang_data = mgr.get_or_create("doctor_wang").read()
        assert any(e.type == "say" for e in wang_data["events"])

    def test_event_scope_adjacent_delivers_to_all(self) -> None:
        """New Perceiver no longer filters adjacent events; all agents receive them."""
        store = _bunker_store()
        event_log = EventLog()
        event_log.append(
            Event(
                tick=1,
                type="shout",
                source="doctor_wang",
                detail="hey!",
                ttl=5,
                scope="adjacent",
            )
        )
        mgr = InboxManager()
        p = Perceiver(store, event_log, mgr, BUNKER_PERCEPTION)
        p.deliver(1)
        # All agents receive adjacent events
        for agent_id in ["old_chen", "xiao_li", "doctor_wang"]:
            data = mgr.get_or_create(agent_id).read()
            assert any(e.type == "shout" for e in data["events"])

    def test_event_scope_global(self) -> None:
        store = _bunker_store()
        event_log = EventLog()
        event_log.append(
            Event(
                tick=1,
                type="alarm",
                source="system",
                detail="alert!",
                ttl=5,
                scope="global",
            )
        )
        mgr = InboxManager()
        p = Perceiver(store, event_log, mgr, BUNKER_PERCEPTION)
        p.deliver(1)
        for agent_id in ["old_chen", "xiao_li", "doctor_wang"]:
            data = mgr.get_or_create(agent_id).read()
            assert any(e.type == "alarm" for e in data["events"])

    def test_event_scope_target_only(self) -> None:
        store = _bunker_store()
        event_log = EventLog()
        event_log.append(
            Event(
                tick=1,
                type="whisper",
                source="xiao_li",
                detail="secret",
                ttl=5,
                scope="target_only",
                target="old_chen",
            )
        )
        mgr = InboxManager()
        p = Perceiver(store, event_log, mgr, BUNKER_PERCEPTION)
        p.deliver(1)
        # old_chen gets it
        chen_data = mgr.get_or_create("old_chen").read()
        assert any(e.type == "whisper" for e in chen_data["events"])
        # xiao_li doesn't (not target)
        li_data = mgr.get_or_create("xiao_li").read()
        assert not any(e.type == "whisper" for e in li_data["events"])


class TestDirectMessage:
    def test_whisper_same_location_with_target(self) -> None:
        store = _bunker_store()
        event_log = EventLog()
        event_log.append(
            Event(
                tick=1,
                type="say",
                source="xiao_li",
                detail="hey chen",
                ttl=5,
                scope="same_location",
                target="old_chen",
            )
        )
        mgr = InboxManager()
        p = Perceiver(store, event_log, mgr, BUNKER_PERCEPTION)
        p.deliver(1)
        # old_chen gets event + DM
        chen_data = mgr.get_or_create("old_chen").read()
        assert any(e.type == "say" for e in chen_data["events"])
        assert len(chen_data["whispers"]) == 1
        # xiao_li gets event (same_location now delivers to all) but no DM
        li_data = mgr.get_or_create("xiao_li").read()
        assert any(e.type == "say" for e in li_data["events"])
        assert len(li_data["whispers"]) == 0

    def test_whisper_target_only(self) -> None:
        store = _bunker_store()
        event_log = EventLog()
        event_log.append(
            Event(
                tick=1,
                type="whisper",
                source="xiao_li",
                detail="secret",
                ttl=5,
                scope="target_only",
                target="old_chen",
            )
        )
        mgr = InboxManager()
        p = Perceiver(store, event_log, mgr, BUNKER_PERCEPTION)
        p.deliver(1)
        # old_chen gets event + DM
        chen_data = mgr.get_or_create("old_chen").read()
        assert any(e.type == "whisper" for e in chen_data["events"])
        assert len(chen_data["whispers"]) == 1
        # xiao_li gets nothing
        li_data = mgr.get_or_create("xiao_li").read()
        assert not any(e.type == "whisper" for e in li_data["events"])
        assert len(li_data["whispers"]) == 0


class TestDedup:
    def test_no_duplicate_across_ticks(self) -> None:
        store = _bunker_store()
        event_log = EventLog()
        event_log.append(
            Event(
                tick=1,
                type="say",
                source="old_chen",
                detail="hello",
                ttl=5,
                scope="same_location",
            )
        )
        mgr = InboxManager()
        p = Perceiver(store, event_log, mgr, BUNKER_PERCEPTION)
        p.deliver(1)
        p.deliver(2)  # No new events
        data = mgr.get_or_create("xiao_li").read()
        say_events = [e for e in data["events"] if e.type == "say"]
        assert len(say_events) == 1

    def test_expired_events_cleaned(self) -> None:
        store = _bunker_store()
        event_log = EventLog()
        event_log.append(
            Event(
                tick=1,
                type="say",
                source="old_chen",
                detail="hello",
                ttl=1,
                scope="same_location",
            )
        )
        mgr = InboxManager()
        p = Perceiver(store, event_log, mgr, BUNKER_PERCEPTION)
        p.deliver(1)
        # Read to drain
        mgr.get_or_create("xiao_li").read()
        # Cleanup: event at tick 1 with ttl=1 expires after tick 2
        event_log.cleanup(3)
        live = {(e.tick, e.type, e.source) for e in event_log.get_events()}
        mgr.get_or_create("xiao_li").cleanup_expired_events(live)
        data = mgr.get_or_create("xiao_li").read()
        assert len(data["events"]) == 0
