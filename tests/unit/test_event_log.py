"""Tests for EventLog."""

from __future__ import annotations

from worldseed.engine.event_log import EventLog
from worldseed.models import Event


class TestEventLog:
    def test_append_and_retrieve(self, event_log: EventLog) -> None:
        event = Event(
            tick=1,
            type="move",
            source="chen",
            detail="moved",
            ttl=1,
            scope="same_location",
        )
        event_log.append(event)
        assert len(event_log.get_events()) == 1

    def test_filter_since_tick(self, event_log: EventLog) -> None:
        for tick in [1, 2, 3]:
            event_log.append(
                Event(
                    tick=tick,
                    type="move",
                    source="chen",
                    detail=f"tick {tick}",
                    ttl=5,
                    scope="global",
                )
            )
        assert len(event_log.get_events(since_tick=2)) == 2

    def test_filter_by_type(self, event_log: EventLog) -> None:
        event_log.append(
            Event(
                tick=1,
                type="move",
                source="chen",
                detail="moved",
                ttl=5,
                scope="global",
            )
        )
        event_log.append(
            Event(
                tick=1,
                type="say",
                source="chen",
                detail="hello",
                ttl=5,
                scope="global",
            )
        )
        assert len(event_log.get_events(event_type="move")) == 1

    def test_ttl_cleanup(self, event_log: EventLog) -> None:
        event_log.append(
            Event(
                tick=5,
                type="move",
                source="chen",
                detail="moved",
                ttl=2,
                scope="global",
            )
        )
        event_log.cleanup(current_tick=7)  # 5 + 2 = 7, still alive
        assert len(event_log.get_events()) == 1
        event_log.cleanup(current_tick=8)  # 5 + 2 < 8, expired
        assert len(event_log.get_events()) == 0

    def test_ttl_zero_expires_next_tick(self, event_log: EventLog) -> None:
        event_log.append(
            Event(
                tick=5,
                type="sound",
                source="system",
                detail="creak",
                ttl=0,
                scope="same_location",
            )
        )
        event_log.cleanup(current_tick=5)  # 5 + 0 = 5, still alive
        assert len(event_log.get_events()) == 1
        event_log.cleanup(current_tick=6)  # 5 + 0 < 6, expired
        assert len(event_log.get_events()) == 0

    def test_permanent_never_expires(self, event_log: EventLog) -> None:
        event_log.append(
            Event(
                tick=1,
                type="landmark",
                source="system",
                detail="world created",
                ttl="permanent",
                scope="global",
            )
        )
        event_log.cleanup(current_tick=99999)
        assert len(event_log.get_events()) == 1
