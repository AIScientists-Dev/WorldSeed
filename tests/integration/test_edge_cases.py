"""Edge case tests for Phase 2 perception system."""

from __future__ import annotations

from worldseed.engine.action_queue import ActionQueue
from worldseed.engine.consequence_scanner import ConsequenceScanner
from worldseed.engine.event_log import EventLog
from worldseed.engine.inbox import Inbox, InboxEvent, InboxManager
from worldseed.engine.perceiver import Perceiver
from worldseed.engine.state_store import StateStore
from worldseed.engine.tick import TickEngine
from worldseed.engine.wakeup import WakeupEvaluator
from worldseed.models.config_schema import (
    ConsequenceConfig,
    EffectConfig,
    PerceptionConfig,
    PreconditionConfig,
    SceneConfig,
    SceneMetaConfig,
)
from worldseed.models.entity import Entity
from worldseed.models.event import Event

# ---------------------------------------------------------------------------
# Perceiver edge cases
# ---------------------------------------------------------------------------


def _simple_store() -> StateStore:
    """Store with one room and one agent."""
    store = StateStore()
    store.add(
        Entity(
            id="room_a",
            type="space",
            _data={"description": "A room", "connects_to": ["room_b"]},
        )
    )
    store.add(
        Entity(
            id="room_b",
            type="space",
            _data={"description": "B room", "connects_to": ["room_a"]},
        )
    )
    return store


class TestPerceiverAgentNoLocation:
    """Agent with no location property at all."""

    def test_agent_no_location_snapshot_with_visibility_rules(self) -> None:
        """With location-based visibility rules, a locationless agent sees other
        locationless entities (None == None), but not located ones."""
        store = _simple_store()
        store.add(Entity(id="ghost", type="agent", _data={"name": "nobody"}))
        store.add(Entity(id="alice", type="agent", _data={"location": "room_a"}))
        location_visibility = PerceptionConfig(
            visibility=[
                PreconditionConfig(
                    operator="check",
                    left="$observer.location",
                    op="==",
                    right="$entity.location",
                )
            ],
        )
        mgr = InboxManager()
        p = Perceiver(store, EventLog(), mgr, location_visibility)
        p.deliver(1)
        data = mgr.get_or_create("ghost").read()
        snap = data["current_state"]
        # Spaces (room_a, room_b) have no location property either
        # → None == None → visible
        assert "room_a" in snap.visible_entities
        assert "room_b" in snap.visible_entities
        # alice has location="room_a" → "room_a" != None → not visible
        assert "alice" not in snap.visible_agents
        # self_state still includes own properties
        assert snap.self_state == {"name": "nobody"}

    def test_agent_no_location_sees_everything_without_visibility_rules(self) -> None:
        """With no visibility rules (empty PerceptionConfig), everything is visible."""
        store = _simple_store()
        store.add(Entity(id="ghost", type="agent", _data={"name": "nobody"}))
        store.add(Entity(id="alice", type="agent", _data={"location": "room_a"}))
        mgr = InboxManager()
        p = Perceiver(store, EventLog(), mgr, PerceptionConfig())
        p.deliver(1)
        ghost_data = mgr.get_or_create("ghost").read()
        # No visibility rules means everything is visible
        assert "alice" in ghost_data["current_state"].visible_agents

    def test_agent_no_location_does_not_see_located_agents(self) -> None:
        """With location-based visibility, ghost (no location) cannot see alice."""
        store = _simple_store()
        store.add(Entity(id="ghost", type="agent", _data={}))
        store.add(Entity(id="alice", type="agent", _data={"location": "room_a"}))
        location_visibility = PerceptionConfig(
            visibility=[
                PreconditionConfig(
                    operator="check",
                    left="$observer.location",
                    op="==",
                    right="$entity.location",
                )
            ],
        )
        mgr = InboxManager()
        p = Perceiver(store, EventLog(), mgr, location_visibility)
        p.deliver(1)
        ghost_data = mgr.get_or_create("ghost").read()
        assert "alice" not in ghost_data["current_state"].visible_agents


class TestPerceiverResourceLocatedIn:
    """Resources using located_in relationship (not location property).

    With DSL-based visibility, the location check is $observer.location
    == $entity.location. Resources use located_in *relationships* (not a
    location property), so the standard location visibility rule won't match them.
    We use PerceptionConfig() (no visibility rules) for the "visible" test, and
    location-based rules for the "not visible" test.
    """

    def test_resource_visible_without_visibility_rules(self) -> None:
        """With no visibility rules, all entities are visible."""
        store = _simple_store()
        store.add(
            Entity(
                id="chest",
                type="resource",
                _data={"contents": "gold", "located_in": ["room_a"]},
            )
        )
        store.add(Entity(id="alice", type="agent", _data={"location": "room_a"}))
        mgr = InboxManager()
        p = Perceiver(store, EventLog(), mgr, PerceptionConfig())
        p.deliver(1)
        data = mgr.get_or_create("alice").read()
        assert "chest" in data["current_state"].visible_entities
        assert data["current_state"].visible_entities["chest"]["contents"] == "gold"

    def test_resource_with_location_property_visible_same_room(self) -> None:
        """Resource with a location property visible under location-based rules."""
        store = _simple_store()
        store.add(
            Entity(
                id="chest",
                type="resource",
                _data={
                    "contents": "gold",
                    "location": "room_a",
                    "located_in": ["room_a"],
                },
            )
        )
        store.add(Entity(id="alice", type="agent", _data={"location": "room_a"}))
        location_visibility = PerceptionConfig(
            visibility=[
                PreconditionConfig(
                    operator="check",
                    left="$observer.location",
                    op="==",
                    right="$entity.location",
                )
            ],
        )
        mgr = InboxManager()
        p = Perceiver(store, EventLog(), mgr, location_visibility)
        p.deliver(1)
        data = mgr.get_or_create("alice").read()
        assert "chest" in data["current_state"].visible_entities
        assert data["current_state"].visible_entities["chest"]["contents"] == "gold"

    def test_resource_not_visible_from_other_room(self) -> None:
        """Resource in room_a not visible to agent in room_b under location rules."""
        store = _simple_store()
        store.add(
            Entity(
                id="chest",
                type="resource",
                _data={
                    "contents": "gold",
                    "location": "room_a",
                    "located_in": ["room_a"],
                },
            )
        )
        store.add(Entity(id="bob", type="agent", _data={"location": "room_b"}))
        location_visibility = PerceptionConfig(
            visibility=[
                PreconditionConfig(
                    operator="check",
                    left="$observer.location",
                    op="==",
                    right="$entity.location",
                )
            ],
        )
        mgr = InboxManager()
        p = Perceiver(store, EventLog(), mgr, location_visibility)
        p.deliver(1)
        data = mgr.get_or_create("bob").read()
        assert "chest" not in data["current_state"].visible_entities


class TestPerceiverUnknownScope:
    """Events with invalid/unknown scope values.

    The new Perceiver delivers unknown scopes to all agents (catch-all).
    """

    def test_unknown_scope_delivered_to_all(self) -> None:
        """Unknown scope falls through to the catch-all branch (delivers to all)."""
        store = _simple_store()
        store.add(Entity(id="alice", type="agent", _data={"location": "room_a"}))
        event_log = EventLog()
        event_log.append(
            Event(
                tick=1,
                type="mystery",
                source="system",
                detail="???",
                ttl=5,
                scope="unknown_scope",
            )
        )
        mgr = InboxManager()
        p = Perceiver(store, event_log, mgr, PerceptionConfig())
        p.deliver(1)
        data = mgr.get_or_create("alice").read()
        assert len(data["events"]) == 1


class TestPerceiverEmptySource:
    """Event with empty source and same_location scope.

    The new Perceiver delivers same_location events to all agents (no location
    filtering for events).
    """

    def test_empty_source_delivered_to_all(self) -> None:
        """same_location scope no longer filtered.

        All agents receive it (Perceiver delegates to event_scopes).
        """
        store = _simple_store()
        store.add(Entity(id="alice", type="agent", _data={"location": "room_a"}))
        event_log = EventLog()
        event_log.append(
            Event(
                tick=1,
                type="system_msg",
                source="",
                detail="system event",
                ttl=5,
                scope="same_location",
            )
        )
        mgr = InboxManager()
        p = Perceiver(store, event_log, mgr, PerceptionConfig())
        p.deliver(1)
        data = mgr.get_or_create("alice").read()
        # New Perceiver delivers same_location to all agents
        assert len(data["events"]) == 1

    def test_global_scope_with_empty_source_still_delivered(self) -> None:
        store = _simple_store()
        store.add(Entity(id="alice", type="agent", _data={"location": "room_a"}))
        event_log = EventLog()
        event_log.append(
            Event(
                tick=1,
                type="announcement",
                source="system",
                detail="hello world",
                ttl=5,
                scope="global",
            )
        )
        mgr = InboxManager()
        p = Perceiver(store, event_log, mgr, PerceptionConfig())
        p.deliver(1)
        data = mgr.get_or_create("alice").read()
        assert len(data["events"]) == 1


# ---------------------------------------------------------------------------
# Wakeup edge cases
# ---------------------------------------------------------------------------


class TestWakeupPushFlag:
    """Push-based wakeup: push=True triggers wake, push=False does not."""

    def test_push_event_wakes(self) -> None:
        evaluator = WakeupEvaluator()
        inbox = Inbox("agent1")
        inbox.append_event(
            InboxEvent(
                tick=1,
                type="shout",
                source="x",
                detail="",
                push=True,
            )
        )
        result = evaluator.evaluate(inbox)
        assert result.should_wake is True


class TestWakeupNoRules:
    """WakeupEvaluator with no push events."""

    def test_no_events_no_wake(self) -> None:
        evaluator = WakeupEvaluator()
        inbox = Inbox("agent1")
        result = evaluator.evaluate(inbox)
        assert result.should_wake is False

    def test_non_push_events_no_wake(self) -> None:
        """Without push, events alone don't wake."""
        evaluator = WakeupEvaluator()
        inbox = Inbox("agent1")
        inbox.append_event(InboxEvent(tick=1, type="shout", source="x", detail=""))
        result = evaluator.evaluate(inbox)
        assert result.should_wake is False

    def test_dm_still_wakes(self) -> None:
        """Direct messages always wake."""
        from worldseed.engine.inbox import InboxWhisper

        evaluator = WakeupEvaluator()
        inbox = Inbox("agent1")
        inbox.append_whisper(InboxWhisper(tick=1, source="b", detail="hi", type="say"))
        result = evaluator.evaluate(inbox)
        assert result.should_wake is True


# ---------------------------------------------------------------------------
# Consequence Scanner edge cases
# ---------------------------------------------------------------------------


def _empty_config() -> SceneConfig:
    return SceneConfig(
        scene=SceneMetaConfig(id="test", description="test"),
        entities=[],
        actions={},
    )


class TestConsequenceMultipleTriggers:
    """Consequence with multiple trigger conditions (AND)."""

    def test_fires_only_when_all_triggers_true(self) -> None:
        config = SceneConfig(
            scene=SceneMetaConfig(id="test", description="test"),
            entities=[],
            actions={},
            consequences={
                "crisis": ConsequenceConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left="food.quantity",
                            op="<",
                            right=5,
                        ),
                        PreconditionConfig(
                            operator="check",
                            left="water.quantity",
                            op="<",
                            right=3,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="emit_event",
                            type="crisis",
                            detail="Both low",
                            ttl=5,
                            scope="global",
                        )
                    ],
                ),
            },
        )
        store = StateStore()
        store.add(Entity(id="food", type="resource", _data={"quantity": 4}))
        store.add(Entity(id="water", type="resource", _data={"quantity": 10}))
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        # Only food is low → should NOT fire
        assert scanner.scan(1)[0] == []
        assert len(event_log.get_events()) == 0

        # Now both are low → should fire
        store.update_property("water", "quantity", 2)
        assert scanner.scan(2)[0] == ["crisis"]
        assert len(event_log.get_events()) == 1


class TestConsequenceEmptyConfig:
    """No consequences configured at all."""

    def test_empty_consequences_returns_empty(self) -> None:
        config = _empty_config()
        store = StateStore()
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)
        assert scanner.scan(1)[0] == []


class TestConsequenceEffectThrows:
    """Consequence effect raises — scanner should survive."""

    def test_bad_effect_does_not_crash_scanner(self) -> None:
        config = SceneConfig(
            scene=SceneMetaConfig(id="test", description="test"),
            entities=[],
            actions={},
            consequences={
                "bad": ConsequenceConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left=1,
                            op="==",
                            right=1,  # always true
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="nonexistent_entity.x",
                            value=42,
                        ),
                    ],
                ),
                "good": ConsequenceConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left=2,
                            op="==",
                            right=2,  # always true
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="emit_event",
                            type="ok",
                            detail="worked",
                            ttl=5,
                            scope="global",
                        ),
                    ],
                ),
            },
        )
        store = StateStore()
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)
        # "bad" effect targets nonexistent entity — logs warning, skips.
        # "good" consequence still fires.
        triggered, _dm_pending = scanner.scan(1)
        assert "bad" in triggered  # trigger passed, effect was a no-op
        assert "good" in triggered
        events = event_log.get_events()
        assert any(e.type == "ok" for e in events)


# ---------------------------------------------------------------------------
# Tick / Integration edge cases
# ---------------------------------------------------------------------------


class TestTickEngineNoInboxManager:
    """Phase 1 backwards compat — inbox_manager=None."""

    def test_step_without_inbox_manager(self) -> None:
        config = _empty_config()
        store = StateStore()
        store.add(Entity(id="agent1", type="agent", _data={"location": "room"}))
        store.add(Entity(id="room", type="space", _data={}))
        event_log = EventLog()
        queue = ActionQueue()
        # No inbox_manager — Phase 1 mode
        tick_engine = TickEngine(
            config,
            store,
            event_log,
            queue,
        )
        # Should run without error
        results = tick_engine.step()
        assert results == []
        assert tick_engine.tick == 1


class TestReadInboxNonExistentAgent:
    """read_inbox for agent that was never delivered to."""

    def test_returns_empty_state(self, bunker_world) -> None:  # type: ignore[no-untyped-def]
        # Don't step — just read immediately
        data = bunker_world.read_inbox("nobody")
        assert data["current_state"] is None
        assert data["events"] == []
        assert data["whispers"] == []


class TestMultipleSubmitsOneStep:
    """Multiple actions submitted before a single step."""

    def test_all_processed_in_one_tick(self, bunker_world) -> None:  # type: ignore[no-untyped-def]
        # Mechanical actions execute immediately on submit
        r1 = bunker_world.submit("old_chen", "say", {"message": "msg1"})
        r2 = bunker_world.submit("xiao_li", "say", {"message": "msg2"})
        r3 = bunker_world.submit("doctor_wang", "move", {"to": "sleeping_quarters"})
        from worldseed.engine.rules_engine import ActionResult

        assert isinstance(r1, ActionResult) and r1.success
        assert isinstance(r2, ActionResult) and r2.success
        assert isinstance(r3, ActionResult) and r3.success
        # Immediately after submit, doctor_wang is in sleeping_quarters
        wang = bunker_world.state.get("doctor_wang")
        assert wang is not None
        assert wang["location"] == "sleeping_quarters"

    def test_multiple_mechanical_actions_same_tick(self, bunker_world) -> None:  # type: ignore[no-untyped-def]
        """Mechanical actions execute immediately — multiple per tick allowed."""
        from worldseed.engine.rules_engine import ActionResult

        r1 = bunker_world.submit("old_chen", "move", {"to": "hallway"})
        assert isinstance(r1, ActionResult) and r1.success

        # old_chen is now at hallway — can take from hallway entities
        r2 = bunker_world.submit("old_chen", "say", {"message": "hello"})
        assert isinstance(r2, ActionResult) and r2.success


class TestPerceiverAfterAgentMove:
    """Perceiver snapshot reflects post-move location."""

    def test_snapshot_uses_current_location(self, bunker_world) -> None:  # type: ignore[no-untyped-def]
        bunker_world.submit("old_chen", "move", {"to": "hallway"})
        bunker_world.step()
        data = bunker_world.read_inbox("old_chen")
        snap = data["current_state"]
        # old_chen moved to hallway — snapshot should reflect hallway
        assert snap.self_state["location"] == "hallway"
        # Visibility rule filters by location property
        # doctor_wang is also in hallway
        assert "doctor_wang" in snap.visible_agents


class TestDirectMessageToSelf:
    """Agent sends a targeted event to themselves."""

    def test_self_targeted_event_delivered_as_dm(self) -> None:
        store = _simple_store()
        store.add(Entity(id="alice", type="agent", _data={"location": "room_a"}))
        event_log = EventLog()
        event_log.append(
            Event(
                tick=1,
                type="think",
                source="alice",
                detail="internal thought",
                ttl=1,
                scope="target_only",
                target="alice",
            )
        )
        mgr = InboxManager()
        p = Perceiver(store, event_log, mgr, PerceptionConfig())
        p.deliver(1)
        data = mgr.get_or_create("alice").read()
        # Gets both as event (target_only -> target matches) and as DM
        assert any(e.type == "think" for e in data["events"])
        assert len(data["whispers"]) == 1
        assert data["whispers"][0].detail == "internal thought"


class TestPerceiverMultipleEventsOneTick:
    """Multiple events with different scopes in the same tick.

    The new Perceiver only filters target_only (by target). All other scopes
    (same_location, adjacent, global, unknown) deliver to all agents.
    """

    def test_mixed_scopes_filtered_correctly(self) -> None:
        store = _simple_store()
        store.add(Entity(id="alice", type="agent", _data={"location": "room_a"}))
        store.add(Entity(id="bob", type="agent", _data={"location": "room_b"}))
        event_log = EventLog()
        # same_location event at room_a
        event_log.append(
            Event(
                tick=1,
                type="whisper",
                source="alice",
                detail="quiet",
                ttl=5,
                scope="same_location",
            )
        )
        # adjacent event at room_a
        event_log.append(
            Event(
                tick=1,
                type="shout",
                source="alice",
                detail="loud",
                ttl=5,
                scope="adjacent",
            )
        )
        # global event
        event_log.append(
            Event(
                tick=1,
                type="alarm",
                source="system",
                detail="alert",
                ttl=5,
                scope="global",
            )
        )
        # target_only to bob
        event_log.append(
            Event(
                tick=1,
                type="secret",
                source="alice",
                detail="for bob only",
                ttl=5,
                scope="target_only",
                target="bob",
            )
        )
        mgr = InboxManager()
        p = Perceiver(store, event_log, mgr, PerceptionConfig())
        p.deliver(1)

        alice_data = mgr.get_or_create("alice").read()
        alice_types = {e.type for e in alice_data["events"]}
        # Alice sees: whisper, shout, alarm (all non-target_only).
        # NOT: secret (target_only, target=bob)
        assert alice_types == {"whisper", "shout", "alarm"}

        bob_data = mgr.get_or_create("bob").read()
        bob_types = {e.type for e in bob_data["events"]}
        # Bob sees: whisper, shout, alarm (all non-target_only)
        # + secret (target_only, target=bob)
        assert bob_types == {"whisper", "shout", "alarm", "secret"}
        # Bob also gets secret as a DM
        assert len(bob_data["whispers"]) == 1
