"""Tests for Event target field."""

from __future__ import annotations

from worldseed.models.event import Event


class TestEventTarget:
    def test_event_with_target(self) -> None:
        event = Event(
            tick=1,
            type="say",
            source="a",
            detail="hello",
            ttl=1,
            scope="target_only",
            target="b",
        )
        assert event.target == "b"
        assert event.scope == "target_only"

    def test_event_target_defaults_none(self) -> None:
        event = Event(
            tick=1,
            type="move",
            source="a",
            detail="moved",
            ttl=1,
            scope="same_location",
        )
        assert event.target is None

    def test_event_target_with_non_target_scope(self) -> None:
        """Target can be set with non-target_only scope (used for DM routing)."""
        event = Event(
            tick=1,
            type="say",
            source="a",
            detail="hello",
            ttl=1,
            scope="same_location",
            target="b",
        )
        assert event.target == "b"
        assert event.scope == "same_location"
