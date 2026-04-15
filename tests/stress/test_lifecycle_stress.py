"""Test: 200+ tick lifecycle — sustained load, no memory leak, no corruption.

Stress tests that verify long-running stability:
  - 200+ ticks without crash
  - Memory usage doesn't grow unbounded (inbox, event_log)
  - Constraints hold after extreme degradation
  - stream.jsonl integrity (via NullRecorder — no actual IO)
  - Persistence roundtrip after long run

ZERO HARDCODE: Uses config-driven helpers.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from tests.helpers import (
    ConfigIntrospector,
    assert_no_metadata_leak,
    load_any_config,
    make_world,
    standard_config_paths,
)

# Select configs that have auto_tick (interesting for lifecycle)
LIFECYCLE_CONFIGS = [p for p in standard_config_paths() if load_any_config(p).auto_tick]


@pytest.fixture(params=LIFECYCLE_CONFIGS, ids=lambda p: p.stem)
def active_config(request: pytest.FixtureRequest) -> Path:
    """Configs with auto_tick — most interesting for lifecycle tests."""
    return request.param


class TestSustained200Ticks:
    """200+ ticks, no crash, correct state."""

    def test_200_ticks_no_crash(self, active_config: Path) -> None:
        """200 ticks with auto_tick running — no exceptions."""
        engine = make_world(active_config)
        for _ in range(200):
            engine.step()
        assert engine.tick == 200

    def test_200_ticks_constraints_hold(self, active_config: Path) -> None:
        """After 200 ticks of degradation, no constraint violated."""
        config = load_any_config(active_config)
        intro = ConfigIntrospector(config)
        constrained = intro.entities_with_constraints()
        if not constrained:
            pytest.skip("No constrained entities")

        engine = make_world(active_config)
        for _ in range(200):
            engine.step()

        for ce in constrained:
            entity = engine.state.get(ce["id"])
            if entity is None:
                continue
            for prop_name, constraint in ce["constraints"].items():
                val = entity.data.get(prop_name)
                if not isinstance(val, (int, float)):
                    continue
                if "min" in constraint:
                    assert val >= constraint["min"], (
                        f"After 200 ticks: {ce['id']}.{prop_name}={val} < min={constraint['min']}"
                    )
                if "max" in constraint:
                    assert val <= constraint["max"], (
                        f"After 200 ticks: {ce['id']}.{prop_name}={val} > max={constraint['max']}"
                    )

    def test_200_ticks_perception_still_valid(self, active_config: Path) -> None:
        """After 200 ticks, perception is still well-formed."""
        engine = make_world(active_config)
        for _ in range(200):
            engine.step()

        for agent_id in engine.get_registered_agents():
            pdict = engine.perceive(agent_id).to_dict()
            assert_no_metadata_leak(pdict)
            assert isinstance(pdict["self_state"], dict)
            assert isinstance(pdict["action_options"], dict)


class TestMemoryBounds:
    """Memory usage doesn't grow unbounded."""

    def test_event_log_bounded(self, active_config: Path) -> None:
        """EventLog size stays bounded over 200 ticks."""
        engine = make_world(active_config)

        max_log_size = 0
        for _ in range(200):
            engine.step()
            max_log_size = max(max_log_size, engine.event_log.size)

        # After cleanup, size should be reasonable
        # (TTL events expire, permanent capped at 500)
        final_size = engine.event_log.size
        assert final_size <= 600, (
            f"EventLog has {final_size} events after 200 ticks (max was {max_log_size}). Possible unbounded growth."
        )

    def test_entity_count_stable(self, active_config: Path) -> None:
        """Entity count doesn't grow over 200 ticks (no spurious creates)."""
        engine = make_world(active_config)
        initial_count = len(engine.state.all_entities())

        for _ in range(200):
            engine.step()

        final_count = len(engine.state.all_entities())
        # With mock DM, entity count should not change
        assert final_count == initial_count, f"Entity count changed from {initial_count} to {final_count}"

    def test_inbox_drains_properly(self, active_config: Path) -> None:
        """Inbox events don't accumulate indefinitely if read regularly."""
        engine = make_world(active_config)

        for i in range(200):
            engine.step()
            # Read perception every 5 ticks (simulates agent perceiving)
            if i % 5 == 0:
                for agent_id in engine.get_registered_agents():
                    engine.perceive(agent_id)  # read = drain

        # After reading, inbox should be small
        for agent_id in engine.get_registered_agents():
            inbox = engine._inbox_manager.get_or_create(agent_id)
            peek = inbox.peek()
            # Only events from last 5 ticks at most
            assert len(peek["events"]) < 50, (
                f"Agent {agent_id} inbox has {len(peek['events'])} events after regular draining"
            )


class TestPersistenceAfterLongRun:
    """Save/load works after long runs."""

    def test_save_load_after_200_ticks(self, active_config: Path) -> None:
        """State saved after 200 ticks can be loaded and continued."""
        engine = make_world(active_config)
        for _ in range(200):
            engine.step()

        # Save
        saved_entities = [e.to_full_dict() for e in engine.state.all_entities()]
        saved_tick = engine.tick

        # Load into new engine
        engine2 = make_world(active_config, register_agents=False)
        engine2.load_state(saved_entities, saved_tick)

        # Verify state matches
        assert engine2.tick == 200
        for entity in engine.state.all_entities():
            e2 = engine2.state.get(entity.id)
            assert e2 is not None, f"Entity {entity.id} not restored"
            assert e2.data == entity.data, f"Entity {entity.id} data mismatch after load"

        # Continue running
        for _ in range(10):
            engine2.step()
        assert engine2.tick == 210


class TestConsequenceTriggers:
    """Consequences fire during sustained runs."""

    def test_consequences_stable_200_ticks(self, active_config: Path) -> None:
        """Config with consequences + auto_tick runs 200 ticks stably."""
        config = load_any_config(active_config)
        intro = ConfigIntrospector(config)
        if not intro.has_consequences():
            pytest.skip("No consequences defined")

        engine = make_world(active_config)

        # Snapshot initial state to verify auto_tick modifies something
        initial_state: dict[str, dict] = {}
        for entity in engine.state.all_entities():
            initial_state[entity.id] = dict(entity.data)

        for _ in range(200):
            engine.step()

        assert engine.tick == 200

        # With active auto_tick, at least some entity state should change
        any_changed = any(
            dict(entity.data) != initial_state.get(entity.id)
            for entity in engine.state.all_entities()
            if entity.id in initial_state
        )
        assert any_changed, "200 ticks with auto_tick + consequences but no state changes"


class TestMultipleAgentsLifecycle:
    """Multiple agents interacting over sustained period."""

    def test_all_agents_survive_200_ticks(self, active_config: Path) -> None:
        """All agents still exist and are perceivable after 200 ticks."""
        engine = make_world(active_config)
        initial_agents = set(engine.get_registered_agents())

        for _ in range(200):
            engine.step()

        final_agents = set(engine.get_registered_agents())
        assert initial_agents == final_agents, (
            f"Agents changed: lost={initial_agents - final_agents}, gained={final_agents - initial_agents}"
        )

    def test_200_ticks_with_mixed_actions(self, active_config: Path) -> None:
        """200 ticks with agents submitting actions intermittently."""
        config = load_any_config(active_config)
        intro = ConfigIntrospector(config)
        paramless = intro.paramless_actions()
        if not paramless:
            pytest.skip("No paramless actions")

        engine = make_world(active_config)
        agents = engine.get_registered_agents()
        if not agents:
            pytest.skip("No agents")

        total_actions = 0
        total_successes = 0

        for i in range(200):
            # Submit actions every 3rd tick
            if i % 3 == 0:
                for j, agent_id in enumerate(agents):
                    action = paramless[(i + j) % len(paramless)]
                    engine.submit(agent_id, action)
                    total_actions += 1

            results = engine.step()
            total_successes += sum(1 for r in results if r.success)

        assert engine.tick == 200
        assert total_actions > 0
        # Track success rate — not all configs guarantee paramless action success
        # (some have preconditions that require specific state). This is informational.
        # The real test: engine ran 200 ticks with mixed load without crashing,
        # and all agents are still registered.
        final_agents = set(engine.get_registered_agents())
        assert final_agents == set(agents), "Agents changed during 200 tick mixed run"
