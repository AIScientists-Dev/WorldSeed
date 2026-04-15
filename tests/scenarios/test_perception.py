"""Integration tests for the perception system."""

from __future__ import annotations

import pytest

from tests.helpers import CONFIGS_DIR
from worldseed.world import WorldEngine


@pytest.fixture
def world() -> WorldEngine:
    w = WorldEngine(CONFIGS_DIR / "bunker.yaml")
    w.register_from_config()
    return w


class TestPerceptionScenario:
    def test_theft_with_perception(self, world: WorldEngine) -> None:
        """old_chen moves to storage + takes food.

        The new Perceiver no longer filters same_location events, so xiao_li
        receives the take event (scope filtering is now scene-level, not in
        Perceiver). However, spatial *visibility* still works: xiao_li cannot
        see food_supply in her snapshot (different location).
        """
        # sleeping_quarters -> hallway -> storage_room (two moves needed)
        world.submit("old_chen", "move", {"to": "hallway"})
        world.step()
        world.submit("old_chen", "move", {"to": "storage_room"})
        world.step()
        # Drain xiao_li's inbox so far (move events)
        world.read_inbox("xiao_li")
        world.submit("old_chen", "take", {"target": "food_supply", "amount": 3})
        world.step()

        # xiao_li (sleeping_quarters) does NOT see take event
        # (old_chen is in storage_room, same_location scope filters it)
        li_data = world.read_inbox("xiao_li")
        take_events = [e for e in li_data["events"] if e.type == "take"]
        assert len(take_events) == 0

        # old_chen should see food_supply in visible_entities (spatial visibility)
        chen_data = world.read_inbox("old_chen")
        assert "food_supply" in chen_data["current_state"].visible_entities

        # xiao_li should NOT see food_supply in snapshot (different location)
        li_data2 = world.read_inbox("xiao_li")
        assert "food_supply" not in li_data2["current_state"].visible_entities

    def test_say_same_location_only(self, world: WorldEngine) -> None:
        """old_chen (sleeping_quarters) says hello.

        xiao_li (sleeping_quarters) receives it — same location.
        doctor_wang (hallway) does NOT — different location.
        Event scope filtering uses DSL rules from config.
        """
        world.submit("old_chen", "say", {"message": "hello everyone"})
        world.step()

        li_data = world.read_inbox("xiao_li")
        say_events = [e for e in li_data["events"] if e.type == "say"]
        assert len(say_events) == 1

        wang_data = world.read_inbox("doctor_wang")
        say_events_wang = [e for e in wang_data["events"] if e.type == "say"]
        assert len(say_events_wang) == 0  # different location

    def test_shout_adjacent(self, world: WorldEngine) -> None:
        """Add shout action and test adjacent scope."""
        # We'll use say with a manual event emission for adjacent scope
        # Instead, let's just test the perceiver directly with adjacent event
        # doctor_wang is in hallway, old_chen is in sleeping_quarters (adjacent)
        # Emit a global event from hallway to test adjacency
        from worldseed.models.event import Event

        world.event_log.append(
            Event(
                tick=1,
                type="shout",
                source="doctor_wang",
                detail="Everyone listen!",
                ttl=5,
                scope="adjacent",
            )
        )
        world.step()

        # old_chen (sleeping_quarters, adjacent to hallway) should hear
        chen_data = world.read_inbox("old_chen")
        shout_events = [e for e in chen_data["events"] if e.type == "shout"]
        assert len(shout_events) == 1

    def test_scarcity_consequence_triggers(self, world: WorldEngine) -> None:
        """Run ticks until food < 5, verify scarcity event."""
        # Food starts at 20, auto_tick decrements by 0.3 per tick (3 agents * 0.1)
        # Need food < 5, so need > 50 ticks
        for _ in range(55):
            world.step()
        food = world.state.get("food_supply")
        assert food is not None
        assert food["quantity"] < 5

        # Check that scarcity event was delivered
        chen_data = world.read_inbox("old_chen")
        scarcity = [e for e in chen_data["events"] if e.type == "scarcity"]
        assert len(scarcity) >= 1

    def test_full_tick_cycle(self, world: WorldEngine) -> None:
        """Submit action + auto_tick + consequence + perceiver + wakeup."""
        from worldseed.engine.rules_engine import ActionResult

        result = world.submit("old_chen", "say", {"message": "test"})
        assert isinstance(result, ActionResult) and result.success
        world.step()  # run auto_tick, consequences, perceiver

        # Perceiver should have delivered
        chen_data = world.read_inbox("old_chen")
        assert chen_data["current_state"] is not None

        # Wakeup evaluation works
        wakeups = world.get_wakeup_results()
        assert len(wakeups) > 0

    def test_inbox_accumulates_between_reads(self, world: WorldEngine) -> None:
        """Step 3 ticks without reading. Events accumulate."""
        world.submit("old_chen", "say", {"message": "msg1"})
        world.step()
        world.submit("old_chen", "say", {"message": "msg2"})
        world.step()
        world.submit("old_chen", "say", {"message": "msg3"})
        world.step()

        li_data = world.read_inbox("xiao_li")
        say_events = [e for e in li_data["events"] if e.type == "say"]
        assert len(say_events) == 3

    def test_whisper_persists(self, world: WorldEngine) -> None:
        """DM persists across ticks even when not read."""
        from worldseed.models.event import Event

        world.event_log.append(
            Event(
                tick=1,
                type="whisper",
                source="xiao_li",
                detail="secret info",
                ttl="permanent",
                scope="same_location",
                target="old_chen",
            )
        )
        world.step()
        # Run 10 more ticks without reading
        for _ in range(10):
            world.step()

        chen_data = world.read_inbox("old_chen")
        assert len(chen_data["whispers"]) == 1
        assert chen_data["whispers"][0].detail == "secret info"

    def test_hidden_properties_across_agents(self, world: WorldEngine) -> None:
        """private_stash hidden from others, visible to self."""
        world.step()

        chen_data = world.read_inbox("old_chen")
        assert "private_stash" in chen_data["current_state"].self_state

        li_data = world.read_inbox("xiao_li")
        if "old_chen" in li_data["current_state"].visible_agents:
            chen_props = li_data["current_state"].visible_agents["old_chen"]
            assert "private_stash" not in chen_props

    def test_action_failure_no_explicit_feedback(self, world: WorldEngine) -> None:
        """Move to unconnected room fails. Inbox shows same location."""
        from worldseed.engine.rules_engine import ActionResult

        # sleeping_quarters only connects to hallway, not storage_room
        result = world.submit("old_chen", "move", {"to": "storage_room"})
        assert isinstance(result, ActionResult) and not result.success
        world.step()  # still needed for perceiver delivery

        chen_data = world.read_inbox("old_chen")
        # Still in sleeping_quarters
        assert chen_data["current_state"].self_state["location"] == "sleeping_quarters"
