"""Test: EventLog — TTL expiry, permanent events, scopes, cap.

EventLog is in-memory event storage. Tests verify:
  - TTL events expire correctly after N ticks
  - Permanent events persist indefinitely (up to cap)
  - MAX_PERMANENT_EVENTS cap evicts oldest
  - Event scopes control agent visibility
  - Event structure and serialization

ZERO HARDCODE: Event types and scopes read from config or created generically.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import (
    make_world,
    standard_config_paths,
)
from worldseed.engine.event_log import MAX_PERMANENT_EVENTS, EventLog
from worldseed.models.event import Event

# -- Unit tests on EventLog directly (no config dependency) --


class TestEventLogTTL:
    """TTL-based event expiry."""

    def test_event_alive_within_ttl(self) -> None:
        """Event with ttl=3 at tick 5 is alive at tick 5, 6, 7, 8."""
        log = EventLog()
        log.append(Event(tick=5, type="test", source="a", detail="x", ttl=3, scope="global"))

        for t in (5, 6, 7, 8):
            log.cleanup(t)
            assert log.size == 1, f"Event should be alive at tick {t}"

    def test_event_expired_after_ttl(self) -> None:
        """Event with ttl=3 at tick 5 is dead at tick 9."""
        log = EventLog()
        log.append(Event(tick=5, type="test", source="a", detail="x", ttl=3, scope="global"))

        log.cleanup(9)
        assert log.size == 0, "Event should have expired"

    def test_ttl_zero_expires_immediately(self) -> None:
        """Event with ttl=0 expires at the next tick."""
        log = EventLog()
        log.append(Event(tick=1, type="test", source="a", detail="x", ttl=0, scope="global"))

        log.cleanup(1)
        assert log.size == 1, "TTL=0 at same tick should still be alive"
        log.cleanup(2)
        assert log.size == 0, "TTL=0 should expire at next tick"

    def test_mixed_ttl_selective_cleanup(self) -> None:
        """Events with different TTLs expire independently."""
        log = EventLog()
        log.append(Event(tick=1, type="short", source="a", detail="x", ttl=1, scope="global"))
        log.append(Event(tick=1, type="long", source="a", detail="x", ttl=10, scope="global"))
        log.append(
            Event(
                tick=1,
                type="perm",
                source="a",
                detail="x",
                ttl="permanent",
                scope="global",
            )
        )

        log.cleanup(3)
        remaining_types = {e.type for e in log.get_events()}
        assert "short" not in remaining_types, "Short TTL should expire"
        assert "long" in remaining_types, "Long TTL should survive"
        assert "perm" in remaining_types, "Permanent should survive"

    def test_negative_ttl_rejected(self) -> None:
        """Negative TTL raises ValueError."""
        with pytest.raises(ValueError, match="non-negative"):
            Event(tick=1, type="bad", source="a", detail="x", ttl=-1, scope="global")

    def test_invalid_ttl_string_rejected(self) -> None:
        """Non-'permanent' string TTL raises ValueError."""
        with pytest.raises(ValueError, match="permanent"):
            Event(
                tick=1,
                type="bad",
                source="a",
                detail="x",
                ttl="forever",
                scope="global",
            )


class TestEventLogPermanent:
    """Permanent events persist until cap."""

    def test_permanent_survives_cleanup(self) -> None:
        """Permanent events are never expired by cleanup."""
        log = EventLog()
        log.append(
            Event(
                tick=1,
                type="p",
                source="a",
                detail="x",
                ttl="permanent",
                scope="global",
            )
        )

        for t in range(1, 1000):
            log.cleanup(t)

        assert log.size == 1

    def test_permanent_cap_evicts_oldest(self) -> None:
        """When permanent events exceed cap, oldest are evicted."""
        log = EventLog()

        for i in range(MAX_PERMANENT_EVENTS + 50):
            log.append(
                Event(
                    tick=i,
                    type="perm",
                    source="a",
                    detail=f"event_{i}",
                    ttl="permanent",
                    scope="global",
                )
            )

        log.cleanup(MAX_PERMANENT_EVENTS + 100)

        assert log.size == MAX_PERMANENT_EVENTS, f"Expected {MAX_PERMANENT_EVENTS} permanent events, got {log.size}"

        # Verify oldest are dropped: earliest remaining tick should be 50
        remaining = log.get_events()
        earliest_tick = min(e.tick for e in remaining)
        assert earliest_tick == 50, f"Expected oldest remaining at tick 50, got {earliest_tick}"


class TestEventLogQueries:
    """get_events filtering."""

    def test_filter_by_since_tick(self) -> None:
        log = EventLog()
        for i in range(5):
            log.append(Event(tick=i, type="e", source="a", detail="x", ttl=10, scope="global"))

        result = log.get_events(since_tick=3)
        assert len(result) == 2
        assert all(e.tick >= 3 for e in result)

    def test_filter_by_event_type(self) -> None:
        log = EventLog()
        log.append(Event(tick=1, type="action_a", source="a", detail="x", ttl=10, scope="global"))
        log.append(Event(tick=1, type="action_b", source="b", detail="y", ttl=10, scope="global"))
        log.append(Event(tick=2, type="action_a", source="a", detail="z", ttl=10, scope="global"))

        result = log.get_events(event_type="action_a")
        assert len(result) == 2
        assert all(e.type == "action_a" for e in result)

    def test_combined_filters(self) -> None:
        log = EventLog()
        log.append(Event(tick=1, type="action_a", source="a", detail="x", ttl=10, scope="global"))
        log.append(Event(tick=5, type="action_a", source="a", detail="y", ttl=10, scope="global"))
        log.append(Event(tick=5, type="action_b", source="b", detail="z", ttl=10, scope="global"))

        result = log.get_events(since_tick=3, event_type="action_a")
        assert len(result) == 1
        assert result[0].detail == "y"


class TestEventSerialization:
    """Event.to_dict produces correct output."""

    def test_to_dict_has_required_keys(self) -> None:
        e = Event(
            tick=3,
            type="action_a",
            source="agent_a",
            detail="test detail",
            ttl=2,
            scope="global",
        )
        d = e.to_dict()
        assert d == {
            "tick": 3,
            "type": "action_a",
            "source": "agent_a",
            "detail": "test detail",
            "scope": "global",
        }

    def test_to_dict_excludes_engine_fields(self) -> None:
        """to_dict should not include ttl, target, push (engine-internal)."""
        e = Event(
            tick=1,
            type="t",
            source="s",
            detail="d",
            ttl=5,
            scope="global",
            target="victim",
            push=True,
        )
        d = e.to_dict()
        assert "ttl" not in d
        assert "target" not in d
        assert "push" not in d


# -- Integration: Event scopes with Perceiver --


@pytest.fixture(params=standard_config_paths(), ids=lambda p: p.stem)
def config_path(request: pytest.FixtureRequest) -> Path:
    return request.param


class TestEventScopesIntegration:
    """Event scopes control which agents perceive which events."""

    def test_global_scope_visible_to_all(self, config_path: Path) -> None:
        """Events with scope='global' are perceived by all agents."""
        engine = make_world(config_path)
        agents = engine.get_registered_agents()
        if len(agents) < 2:
            pytest.skip("Need 2+ agents")

        # Use a non-system agent as source so the source agent also perceives
        # its own event (system agents skip their own events by design).
        non_system = [
            a
            for a in agents
            if not (engine.get_agent_profile(a) or object()).system  # type: ignore[union-attr]
        ]
        source = non_system[0] if non_system else agents[0]

        # Inject a global event directly
        engine.event_log.append(
            Event(
                tick=engine.tick,
                type="test_global",
                source=source,
                detail="global test event",
                ttl=5,
                scope="global",
            )
        )
        engine.step()

        for agent_id in agents:
            perception = engine.perceive(agent_id)
            pdict = perception.to_dict()
            event_types = {e["type"] for e in pdict["events"]}
            assert "test_global" in event_types, f"Agent {agent_id} should see global event"

    def test_target_only_scope(self, config_path: Path) -> None:
        """Events with scope='target_only' only visible to target (and omniscient)."""
        engine = make_world(config_path)
        agents = engine.get_registered_agents()

        # Need at least 2 non-omniscient agents for a meaningful test
        non_omni = [
            a
            for a in agents
            if not (engine.get_agent_profile(a) or object()).omniscient  # type: ignore[union-attr]
        ]
        if len(non_omni) < 2:
            pytest.skip("Need 2+ non-omniscient agents")

        source = non_omni[0]
        target = non_omni[1]
        engine.event_log.append(
            Event(
                tick=engine.tick,
                type="test_targeted",
                source=source,
                detail="secret message",
                ttl=5,
                scope="target_only",
                target=target,
            )
        )
        engine.step()

        # Target should see it
        target_perception = engine.perceive(target)
        target_events = {e["type"] for e in target_perception.to_dict()["events"]}
        assert "test_targeted" in target_events

        # Non-targets (excluding omniscient agents) should NOT see it
        for agent_id in non_omni:
            if agent_id == target:
                continue
            perception = engine.perceive(agent_id)
            event_types = {e["type"] for e in perception.to_dict()["events"]}
            assert "test_targeted" not in event_types, f"Non-target {agent_id} should NOT see target_only event"

    def test_admin_scope_invisible_to_agents(self, config_path: Path) -> None:
        """Events with scope='admin' are never visible to any agent."""
        engine = make_world(config_path)
        agents = engine.get_registered_agents()
        if not agents:
            pytest.skip("No agents")

        engine.event_log.append(
            Event(
                tick=engine.tick,
                type="test_admin",
                source="system",
                detail="admin only",
                ttl=5,
                scope="admin",
            )
        )
        engine.step()

        for agent_id in agents:
            perception = engine.perceive(agent_id)
            event_types = {e["type"] for e in perception.to_dict()["events"]}
            assert "test_admin" not in event_types, f"Agent {agent_id} should NOT see admin event"


class TestEventTTLIntegration:
    """TTL expiry works correctly within the full tick cycle."""

    def test_events_expire_after_ttl_ticks(self, config_path: Path) -> None:
        """Injected event with specific TTL disappears after that many ticks."""
        engine = make_world(config_path)
        agents = engine.get_registered_agents()
        if not agents:
            pytest.skip("No agents")

        ttl = 3
        engine.step()  # tick 1
        inject_tick = engine.tick
        engine.event_log.append(
            Event(
                tick=inject_tick,
                type="test_ttl",
                source=agents[0],
                detail="ttl test",
                ttl=ttl,
                scope="global",
            )
        )

        # Should be alive for TTL ticks
        for _ in range(ttl):
            engine.step()
            events = engine.event_log.get_events(event_type="test_ttl")
            assert len(events) == 1, f"Event should be alive at tick {engine.tick}"

        # One more tick should expire it
        engine.step()
        events = engine.event_log.get_events(event_type="test_ttl")
        assert len(events) == 0, (
            f"Event should have expired at tick {engine.tick} (injected at {inject_tick}, ttl={ttl})"
        )
