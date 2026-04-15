"""Tests for inbox event persistence across EventLog cleanup.

Inbox events persist until consumed by read(), independent of
EventLog TTL expiry. This ensures agents always see events
delivered to them, even if the EventLog cleans up first.
"""

from __future__ import annotations

from worldseed.engine.event_log import EventLog
from worldseed.engine.inbox import (
    Inbox,
    InboxEvent,
    InboxManager,
)
from worldseed.engine.perceiver import Perceiver
from worldseed.engine.state_store import StateStore
from worldseed.models.config_schema import (
    ActionConfig,
    AgentConfig,
    EntityConfig,
    EventConfig,
    PerceptionConfig,
    SceneConfig,
    SceneMetaConfig,
)
from worldseed.models.entity import Entity
from worldseed.models.event import Event
from worldseed.world import WorldEngine


def _mini_config(
    *,
    actions: dict[str, ActionConfig] | None = None,
) -> SceneConfig:
    """Build a minimal inline SceneConfig."""
    return SceneConfig(
        scene=SceneMetaConfig(
            id="inbox_persistence_test",
            description="Inbox persistence test scene",
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
                id="alice",
                properties={"location": "room"},
                character={"personality": "tester"},
            ),
        ],
        actions=actions
        or {
            "say": ActionConfig(
                description="Speak",
                events=[
                    EventConfig(
                        type="say",
                        detail="$agent says something",
                        ttl=1,
                        scope="global",
                        push=True,
                    ),
                ],
            ),
            "wait": ActionConfig(description="Do nothing"),
        },
    )


def _build_engine(config: SceneConfig) -> WorldEngine:
    engine = WorldEngine(config=config)
    engine.register_from_config()
    return engine


class TestInboxPersistence:
    """Inbox events survive EventLog cleanup."""

    def test_inbox_event_survives_eventlog_cleanup(self) -> None:
        """Create event with ttl=1, deliver to inbox, advance tick so EventLog
        cleans it up, verify inbox still has it."""
        store = StateStore()
        event_log = EventLog()
        inbox_manager = InboxManager()
        perception = PerceptionConfig()

        # Create agent entity in state store
        store.add(Entity(id="alice", type="agent", _data={"location": "room"}))
        store.add(Entity(id="room", type="space", _data={}))

        perceiver = Perceiver(store, event_log, inbox_manager, perception)

        # Add an event with ttl=1 at tick 1
        event = Event(
            tick=1,
            type="shout",
            source="bob",
            detail="hello",
            ttl=1,
            scope="global",
            push=True,
        )
        event_log.append(event)

        # Deliver at tick 1 — event is alive (tick 1 + ttl 1 >= tick 1)
        perceiver.deliver(tick=1)

        # Verify event is in inbox
        inbox = inbox_manager.get_or_create("alice")
        peeked = inbox.peek()
        assert len(peeked["events"]) == 1
        assert peeked["events"][0].type == "shout"
        assert peeked["events"][0].push is True

        # Now advance to tick 3, clean up EventLog
        # Event at tick 1 with ttl 1 expires when current_tick > 1 + 1 = 2
        event_log.cleanup(current_tick=3)

        # EventLog should be empty
        assert len(event_log.get_events()) == 0

        # BUT inbox still has the event (no external cleanup on inbox)
        peeked_after = inbox.peek()
        assert len(peeked_after["events"]) == 1
        assert peeked_after["events"][0].type == "shout"

    def test_inbox_read_drains_persisted_events(self) -> None:
        """After EventLog cleanup, inbox.read() still returns and drains events."""
        store = StateStore()
        event_log = EventLog()
        inbox_manager = InboxManager()
        perception = PerceptionConfig()

        store.add(Entity(id="alice", type="agent", _data={"location": "room"}))
        store.add(Entity(id="room", type="space", _data={}))

        perceiver = Perceiver(store, event_log, inbox_manager, perception)

        event = Event(
            tick=1,
            type="whisper",
            source="bob",
            detail="secret",
            ttl=1,
            scope="global",
        )
        event_log.append(event)
        perceiver.deliver(tick=1)

        # Clean up EventLog
        event_log.cleanup(current_tick=3)

        # Read inbox — should have the event
        inbox = inbox_manager.get_or_create("alice")
        data = inbox.read()
        assert len(data["events"]) == 1
        assert data["events"][0].type == "whisper"
        assert data["events"][0].detail == "secret"

        # Second read should be empty (drained)
        data2 = inbox.read()
        assert len(data2["events"]) == 0

    def test_push_flag_preserved_through_delivery(self) -> None:
        """The push flag on events is preserved when delivered to inbox."""
        store = StateStore()
        event_log = EventLog()
        inbox_manager = InboxManager()
        perception = PerceptionConfig()

        store.add(Entity(id="alice", type="agent", _data={}))

        perceiver = Perceiver(store, event_log, inbox_manager, perception)

        push_event = Event(
            tick=1,
            type="alert",
            source="system",
            detail="important",
            ttl=1,
            scope="global",
            push=True,
        )
        non_push_event = Event(
            tick=1,
            type="ambient",
            source="system",
            detail="background",
            ttl=1,
            scope="global",
            push=False,
        )
        event_log.append(push_event)
        event_log.append(non_push_event)

        perceiver.deliver(tick=1)

        inbox = inbox_manager.get_or_create("alice")
        events = inbox.peek()["events"]
        assert len(events) == 2

        event_types = {e.type: e for e in events}
        assert event_types["alert"].push is True
        assert event_types["ambient"].push is False

    def test_engine_integration_inbox_survives_tick(self) -> None:
        """Full engine: submit action, step, verify inbox has events after
        multiple ticks where EventLog might expire them."""
        engine = _build_engine(_mini_config())

        # Submit say action and step
        engine.submit("alice", "say", {})
        engine.step()  # tick 1 — events created, delivered to inbox

        # Step several more ticks so EventLog cleans up ttl=1 events
        engine.step()  # tick 2
        engine.step()  # tick 3

        # Perceive should still include events from tick 1
        # (they were delivered to inbox and persist there)
        inbox_data = engine.peek_inbox("alice")
        # The say event should still be in inbox since nobody read() it
        # Note: perceiver delivers NEW events each tick too, so state gets updated
        # The key check is that events are not removed by EventLog cleanup
        events = inbox_data["events"]
        say_events = [e for e in events if e.type == "say"]
        assert len(say_events) >= 1, f"Expected at least one say event in inbox, got: {events}"

    def test_multiple_events_persist_independently(self) -> None:
        """Multiple events with different TTLs all persist in inbox regardless."""
        inbox = Inbox("alice")

        # Add events that would have different TTLs in EventLog
        inbox.append_event(InboxEvent(tick=1, type="short_lived", source="a", detail="", push=False))
        inbox.append_event(InboxEvent(tick=2, type="medium_lived", source="b", detail="", push=True))
        inbox.append_event(InboxEvent(tick=3, type="long_lived", source="c", detail="", push=False))

        # All three survive regardless of what EventLog does
        peeked = inbox.peek()
        assert len(peeked["events"]) == 3

        # Read drains all at once
        data = inbox.read()
        assert len(data["events"]) == 3
        assert len(inbox.read()["events"]) == 0
