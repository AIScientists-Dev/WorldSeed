"""Chaos engineering edge-case scenarios that stress-test the engine's generality.

Each scenario targets a specific class of assumption the engine might have.
These are designed to find REAL bugs, not just prove the happy path works.

Scenarios:
1. Self-referential feedback loop — action modifies its own precondition state
2. Numeric precision hell — float drift, negative values, mixed int/float
3. Empty void — 100 ticks of absolutely nothing
4. Massive/circular relationship graph — 20+ rels, cycles, self-references
5. Entity lifecycle mid-tick — create, remove, and reference dead entities
"""

from __future__ import annotations

from worldseed.dsl.functions import relationships_of
from worldseed.engine.action_queue import ActionQueue
from worldseed.engine.event_log import EventLog
from worldseed.engine.inbox import InboxManager
from worldseed.engine.perceiver import Perceiver
from worldseed.engine.rules_engine import RulesEngine
from worldseed.engine.state_store import StateStore
from worldseed.engine.tick import TickEngine
from worldseed.models import ActionSubmission, Entity
from worldseed.models.config_schema import (
    ActionConfig,
    AutoTickConfig,
    ConsequenceConfig,
    EffectConfig,
    EventConfig,
    ParamConfig,
    PerceptionConfig,
    PreconditionConfig,
    SceneConfig,
    SceneMetaConfig,
)

# ============================================================
# SCENARIO 1: Self-Referential Feedback Loop
# ============================================================
# An agent's action drains its own "skill" property. A consequence
# flips "can_operate" to false when skill < 20. A second consequence
# flips it back when skill >= 20. The action checks both properties.
#
# What we're hunting:
# - Does on_change fire correctly when an action crosses a threshold?
# - If we boost 3 times (skill: 50 -> 35 -> 20 -> 5), does the
#   consequence fire at the right moment (tick 3, not earlier)?
# - Does the consequence flip can_operate=false AFTER the action
#   already passed the precondition (reactive, not pre-emptive)?
# ============================================================


class TestFeedbackLoop:
    """Agent action modifies its own precondition-relevant properties."""

    @staticmethod
    def _build() -> tuple[SceneConfig, StateStore]:
        config = SceneConfig(
            scene=SceneMetaConfig(id="feedback", description="Feedback loop"),
            entities=[],
            actions={
                "boost": ActionConfig(
                    description="Boost reactor, drains skill",
                    params=[],
                    preconditions=[
                        PreconditionConfig(
                            operator="check",
                            left="$agent.can_operate",
                            op="==",
                            right=True,
                        ),
                        PreconditionConfig(
                            operator="check",
                            left="$agent.skill",
                            op=">=",
                            right=20,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="increment",
                            target="reactor.power",
                            by=25,
                        ),
                        EffectConfig(
                            operator="decrement",
                            target="$agent.skill",
                            by=15,
                        ),
                    ],
                ),
                "rest": ActionConfig(
                    description="Recover skill",
                    params=[],
                    preconditions=[
                        PreconditionConfig(
                            operator="check",
                            left="$agent.fatigue",
                            op=">",
                            right=0,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="increment",
                            target="$agent.skill",
                            by=10,
                        ),
                        EffectConfig(
                            operator="decrement",
                            target="$agent.fatigue",
                            by=5,
                        ),
                    ],
                ),
            },
            consequences={
                "skill_exhaustion": ConsequenceConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left="engineer.skill",
                            op="<",
                            right=20,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="engineer.can_operate",
                            value=False,
                        ),
                    ],
                ),
                "skill_recovery": ConsequenceConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left="engineer.skill",
                            op=">=",
                            right=20,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="engineer.can_operate",
                            value=True,
                        ),
                    ],
                ),
            },
            auto_tick=[
                AutoTickConfig(
                    description="Reactor cools",
                    effects=[
                        EffectConfig(
                            operator="decrement",
                            target="reactor.power",
                            by=5,
                        ),
                    ],
                ),
            ],
        )
        store = StateStore()
        store.add(
            Entity(
                id="reactor",
                type="device",
                _data={"power": 50, "overloaded": False},
            )
        )
        store.add(
            Entity(
                id="engineer",
                type="agent",
                _data={"skill": 50, "can_operate": True, "fatigue": 0},
            )
        )
        return config, store

    def test_boost_drains_skill_progressively(self) -> None:
        """Boost 3 times: skill goes 50 -> 35 -> 20 -> 5.
        Third boost should still succeed (precond checked BEFORE effect).
        Consequence should fire after tick 3 flips skill to 5 < 20."""
        config, store = self._build()
        queue = ActionQueue()
        event_log = EventLog()
        engine = TickEngine(config, store, event_log, queue)

        # Tick 1: boost (skill 50 -> 35)
        queue.submit(ActionSubmission(agent_id="engineer", action_type="boost"))
        results = engine.step()
        assert results[0].success
        assert store.get("engineer")["skill"] == 35  # type: ignore[union-attr]
        assert store.get("engineer")["can_operate"] is True  # type: ignore[union-attr]

        # Tick 2: boost (skill 35 -> 20)
        queue.submit(ActionSubmission(agent_id="engineer", action_type="boost"))
        results = engine.step()
        assert results[0].success
        assert store.get("engineer")["skill"] == 20  # type: ignore[union-attr]
        # skill == 20, NOT < 20, so can_operate should still be True
        assert store.get("engineer")["can_operate"] is True  # type: ignore[union-attr]

        # Tick 3: boost (skill 20 -> 5). Precondition passes (skill >= 20 at check
        # time). AFTER effects run, skill = 5. Consequence should fire.
        queue.submit(ActionSubmission(agent_id="engineer", action_type="boost"))
        results = engine.step()
        assert results[0].success  # action passed precondition
        assert store.get("engineer")["skill"] == 5  # type: ignore[union-attr]
        # Consequence should have flipped can_operate to False
        assert store.get("engineer")["can_operate"] is False  # type: ignore[union-attr]

    def test_boost_rejected_after_exhaustion(self) -> None:
        """After skill_exhaustion consequence fires, next boost is rejected."""
        config, store = self._build()
        queue = ActionQueue()
        engine = TickEngine(config, store, EventLog(), queue)

        # Drain skill: 50 -> 35 -> 20 -> 5
        for _ in range(3):
            queue.submit(ActionSubmission(agent_id="engineer", action_type="boost"))
            engine.step()

        # Now can_operate is False. Next boost should fail.
        queue.submit(ActionSubmission(agent_id="engineer", action_type="boost"))
        results = engine.step()
        assert not results[0].success
        assert not results[0].success
        assert results[0].reason  # descriptive error, not empty

    def test_consequence_oscillation_across_ticks(self) -> None:
        """Drain skill below 20 (consequence fires), then rest above 20
        (recovery consequence fires). Verify on_change fires both transitions."""
        config, store = self._build()
        # Give engineer some fatigue so rest action works
        store.get("engineer")["fatigue"] = 30  # type: ignore[union-attr]
        queue = ActionQueue()
        engine = TickEngine(config, store, EventLog(), queue)

        # Drain to 5 (3 boosts)
        for _ in range(3):
            queue.submit(ActionSubmission(agent_id="engineer", action_type="boost"))
            engine.step()
        assert store.get("engineer")["can_operate"] is False  # type: ignore[union-attr]

        # Rest twice: skill 5 -> 15 -> 25
        for _ in range(2):
            queue.submit(ActionSubmission(agent_id="engineer", action_type="rest"))
            engine.step()
        assert store.get("engineer")["skill"] == 25  # type: ignore[union-attr]
        # skill_recovery consequence should have flipped can_operate back to True
        assert store.get("engineer")["can_operate"] is True  # type: ignore[union-attr]

    def test_multiple_boosts_same_tick(self) -> None:
        """Submit 3 boosts from same agent in one tick — only first accepted
        (one-action-per-agent-per-tick). Skill: 50 -> 35."""
        config, store = self._build()
        queue = ActionQueue()
        engine = TickEngine(config, store, EventLog(), queue)

        r1 = queue.submit(ActionSubmission(agent_id="engineer", action_type="boost"))
        r2 = queue.submit(ActionSubmission(agent_id="engineer", action_type="boost"))
        r3 = queue.submit(ActionSubmission(agent_id="engineer", action_type="boost"))

        assert r1 is None  # first accepted
        assert isinstance(r2, str)  # rejected
        assert isinstance(r3, str)  # rejected

        results = engine.step()
        assert len(results) == 1
        assert results[0].success
        assert store.get("engineer")["skill"] == 35  # type: ignore[union-attr]

    def test_four_boosts_same_tick_only_first_accepted(self) -> None:
        """4 boosts from same agent — only first accepted by queue
        (one-action-per-agent-per-tick). Skill: 50 -> 35."""
        config, store = self._build()
        queue = ActionQueue()
        engine = TickEngine(config, store, EventLog(), queue)

        results_submit = []
        for _ in range(4):
            results_submit.append(queue.submit(ActionSubmission(agent_id="engineer", action_type="boost")))

        assert results_submit[0] is None  # first accepted
        assert all(isinstance(r, str) for r in results_submit[1:])  # rest rejected

        results = engine.step()
        assert len(results) == 1
        assert results[0].success
        assert store.get("engineer")["skill"] == 35  # type: ignore[union-attr]


# ============================================================
# SCENARIO 2: Numeric Precision Hell
# ============================================================
# Float accumulation, negative values, mixed int/float, large numbers.
#
# What we're hunting:
# - float(0.1) + float(0.1) + ... 10 times should be ~1.0 but may not be
#   exactly 1.0 due to IEEE 754. Does the >= 1.0 comparison still work?
# - Decrementing past zero: engine has no floor, values go negative.
# - int type preservation: incrementing int by int stays int?
# - Large number comparisons: does float() lose precision above 2^53?
# ============================================================


class TestNumericPrecision:
    """Float drift, negative values, and mixed-type arithmetic."""

    @staticmethod
    def _build() -> tuple[SceneConfig, StateStore]:
        config = SceneConfig(
            scene=SceneMetaConfig(id="numeric", description="Numeric torture"),
            entities=[],
            actions={
                "nudge": ActionConfig(
                    description="Tiny float increment",
                    params=[],
                    preconditions=[],
                    effects=[
                        EffectConfig(
                            operator="increment",
                            target="acc.tiny_float",
                            by=0.1,
                        ),
                    ],
                ),
                "drain": ActionConfig(
                    description="Decrement past zero",
                    params=[],
                    preconditions=[],
                    effects=[
                        EffectConfig(
                            operator="decrement",
                            target="acc.positive_val",
                            by=3,
                        ),
                    ],
                ),
            },
            auto_tick=[
                AutoTickConfig(
                    description="Tiny accumulation",
                    effects=[
                        EffectConfig(
                            operator="increment",
                            target="acc.auto_float",
                            by=0.001,
                        ),
                    ],
                ),
            ],
            consequences={
                "threshold_check": ConsequenceConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left="acc.tiny_float",
                            op=">=",
                            right=1.0,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="emit_event",
                            type="threshold",
                            detail="reached 1.0",
                            ttl=5,
                            scope="global",
                        ),
                    ],
                ),
                "negative_check": ConsequenceConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left="acc.positive_val",
                            op="<",
                            right=0,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="emit_event",
                            type="negative",
                            detail="gone negative",
                            ttl=5,
                            scope="global",
                        ),
                    ],
                ),
            },
        )
        store = StateStore()
        store.add(
            Entity(
                id="acc",
                type="sensor",
                _data={
                    "tiny_float": 0.0,
                    "auto_float": 0.0,
                    "positive_val": 5,
                    "int_counter": 0,
                    "mixed": 10,  # int that will get float incremented
                },
            )
        )
        store.add(Entity(id="observer", type="agent", _data={"x": 0}))
        return config, store

    def test_float_accumulation_drift(self) -> None:
        """Add 0.1 ten times. Result should be close to 1.0 but may not be exact.
        The engine uses float(), so IEEE 754 drift is expected."""
        config, store = self._build()
        engine = RulesEngine(config, store, EventLog())

        for tick in range(1, 11):
            result = engine.process_action(
                ActionSubmission(agent_id="observer", action_type="nudge"),
                tick=tick,
            )
            assert result.success

        val = store.get("acc")["tiny_float"]  # type: ignore[union-attr]
        # IEEE 754: 0.1 * 10 = 0.9999999999999999 (not exactly 1.0)
        # The engine stores raw float, so this is expected behavior.
        assert abs(val - 1.0) < 1e-10, f"Float drift: {val}"
        # But the exact value is NOT 1.0:
        # This documents the precision behavior, not necessarily a bug.

    def test_float_threshold_consequence_fires(self) -> None:
        """After 10 nudges (0.1 each), does the >= 1.0 consequence fire?
        This depends on float comparison: float(0.1*10) >= 1.0."""
        config, store = self._build()
        queue = ActionQueue()
        event_log = EventLog()
        engine = TickEngine(config, store, event_log, queue)

        for _ in range(10):
            queue.submit(ActionSubmission(agent_id="observer", action_type="nudge"))
            engine.step()

        val = store.get("acc")["tiny_float"]  # type: ignore[union-attr]
        # The consequence checks >= 1.0.
        # Due to float drift, val might be 0.9999999999999999.
        # This is the KEY test: does the consequence fire or not?
        events = event_log.get_events(event_type="threshold")
        if val >= 1.0:
            assert len(events) > 0, "Consequence should have fired"
        else:
            # Float drift prevented the consequence from firing!
            # This documents a real precision issue.
            assert len(events) == 0, f"Consequence fired despite val={val} < 1.0"

    def test_decrement_past_zero(self) -> None:
        """Decrement a value of 5 by 3 twice: 5 -> 2 -> -1.
        Engine has no floor. Value should go negative."""
        config, store = self._build()
        engine = RulesEngine(config, store, EventLog())

        engine.process_action(
            ActionSubmission(agent_id="observer", action_type="drain"),
            tick=1,
        )
        assert store.get("acc")["positive_val"] == 2  # type: ignore[union-attr]

        engine.process_action(
            ActionSubmission(agent_id="observer", action_type="drain"),
            tick=2,
        )
        assert store.get("acc")["positive_val"] == -1  # type: ignore[union-attr]

    def test_negative_value_consequence(self) -> None:
        """Consequence fires when value goes negative."""
        config, store = self._build()
        queue = ActionQueue()
        event_log = EventLog()
        engine = TickEngine(config, store, event_log, queue)

        # Drain twice: 5 -> 2 -> -1
        for _ in range(2):
            queue.submit(ActionSubmission(agent_id="observer", action_type="drain"))
            engine.step()

        val = store.get("acc")["positive_val"]  # type: ignore[union-attr]
        assert val == -1
        events = event_log.get_events(event_type="negative")
        assert len(events) == 1

    def test_int_type_preservation(self) -> None:
        """Incrementing int by int should yield int, not float."""
        config, store = self._build()
        # Manual increment: int_counter (0) + 1 = should be int(1)
        store.update_property("acc", "int_counter", 0)
        engine = RulesEngine(config, store, EventLog())

        # Use a custom action that increments by integer 1
        int_config = SceneConfig(
            scene=SceneMetaConfig(id="int_test", description="int test"),
            entities=[],
            actions={
                "count": ActionConfig(
                    description="Increment int counter",
                    params=[],
                    preconditions=[],
                    effects=[
                        EffectConfig(
                            operator="increment",
                            target="acc.int_counter",
                            by=1,
                        ),
                    ],
                ),
            },
        )
        engine = RulesEngine(int_config, store, EventLog())
        engine.process_action(
            ActionSubmission(agent_id="observer", action_type="count"),
            tick=1,
        )
        val = store.get("acc")["int_counter"]  # type: ignore[union-attr]
        assert val == 1
        assert isinstance(val, int), f"Expected int, got {type(val)}"

    def test_int_becomes_float_on_float_increment(self) -> None:
        """Incrementing int(10) by float(0.1) should produce float(10.1)."""
        config, store = self._build()
        float_config = SceneConfig(
            scene=SceneMetaConfig(id="mixed", description="mixed"),
            entities=[],
            actions={
                "mix": ActionConfig(
                    description="Float increment on int",
                    params=[],
                    preconditions=[],
                    effects=[
                        EffectConfig(
                            operator="increment",
                            target="acc.mixed",
                            by=0.1,
                        ),
                    ],
                ),
            },
        )
        engine = RulesEngine(float_config, store, EventLog())
        engine.process_action(
            ActionSubmission(agent_id="observer", action_type="mix"),
            tick=1,
        )
        val = store.get("acc")["mixed"]  # type: ignore[union-attr]
        assert isinstance(val, float), f"Expected float, got {type(val)}"
        assert abs(val - 10.1) < 1e-10

    def test_auto_tick_tiny_float_accumulation_1000_ticks(self) -> None:
        """Run 1000 ticks of 0.001 auto-increment. Check for drift."""
        config, store = self._build()
        queue = ActionQueue()
        engine = TickEngine(config, store, EventLog(), queue)

        for _ in range(1000):
            engine.step()

        val = store.get("acc")["auto_float"]  # type: ignore[union-attr]
        expected = 1.0  # 0.001 * 1000
        # Float drift: 0.001 added 1000 times won't be exactly 1.0
        assert abs(val - expected) < 0.01, f"Drift too large: {val} vs {expected}"


# ============================================================
# SCENARIO 3: Empty Void (100 ticks of nothing)
# ============================================================
# No actions, no consequences, no auto_tick. Just agents existing.
#
# What we're hunting:
# - Engine crash on empty action drain
# - Perceiver crash with nothing to perceive
# - Memory leak from 100 empty ticks
# - Tick counter correctness
# ============================================================


class TestEmptyVoid:
    """Engine runs with zero config and zero actions."""

    @staticmethod
    def _build() -> tuple[SceneConfig, StateStore]:
        config = SceneConfig(
            scene=SceneMetaConfig(id="void", description="Nothing"),
            entities=[],
            actions={},
            consequences={},
            auto_tick=[],
        )
        store = StateStore()
        store.add(Entity(id="watcher", type="agent", _data={"boredom": 0}))
        store.add(Entity(id="other", type="agent", _data={"boredom": 0}))
        return config, store

    def test_100_empty_ticks_no_crash(self) -> None:
        """Engine survives 100 ticks with zero work."""
        config, store = self._build()
        queue = ActionQueue()
        engine = TickEngine(config, store, EventLog(), queue)

        for _ in range(100):
            results = engine.step()
            assert results == []

        assert engine.tick == 100

    def test_empty_ticks_with_perceiver(self) -> None:
        """Perceiver delivers empty snapshots for 100 ticks."""
        config, store = self._build()
        queue = ActionQueue()
        inbox_mgr = InboxManager()
        engine = TickEngine(
            config,
            store,
            EventLog(),
            queue,
            inbox_manager=inbox_mgr,
        )

        for _ in range(100):
            engine.step()

        # Read inbox — should have a snapshot but no events
        data = inbox_mgr.get_or_create("watcher").read()
        assert data["current_state"] is not None
        assert data["events"] == []
        assert data["whispers"] == []
        # Watcher should see "other" agent
        assert "other" in data["current_state"].visible_agents

    def test_state_unchanged_after_empty_ticks(self) -> None:
        """Properties don't change when nothing happens."""
        config, store = self._build()
        queue = ActionQueue()
        engine = TickEngine(config, store, EventLog(), queue)

        for _ in range(100):
            engine.step()

        assert store.get("watcher")["boredom"] == 0  # type: ignore[union-attr]
        assert store.get("other")["boredom"] == 0  # type: ignore[union-attr]

    def test_submitting_unknown_action_in_void(self) -> None:
        """Submitting an action that doesn't exist in config fails gracefully."""
        config, store = self._build()
        queue = ActionQueue()
        engine = TickEngine(config, store, EventLog(), queue)

        queue.submit(ActionSubmission(agent_id="watcher", action_type="scream"))
        results = engine.step()
        assert len(results) == 1
        assert not results[0].success
        assert "Unknown action" in results[0].reason

    def test_no_state_change_after_empty_ticks(self) -> None:
        """State should not change after 100 empty ticks (no auto_tick)."""
        config, store = self._build()
        queue = ActionQueue()
        engine = TickEngine(config, store, EventLog(), queue)
        boredom_before = store.get("watcher")["boredom"]  # type: ignore[union-attr]

        for _ in range(100):
            engine.step()

        assert store.get("watcher")["boredom"] == boredom_before  # type: ignore[union-attr]


# ============================================================
# SCENARIO 4: Massive/Circular Relationship Graph
# ============================================================
# Hub with 20+ relationships. Circular chains. Self-references.
# Visibility based on relationship queries.
#
# What we're hunting:
# - relationships_of() returning huge lists (20+ items)
# - "in" operator with 20+ element list
# - Self-referencing relationship (hub links to itself)
# - Circular chains (spoke_01 -> spoke_02 -> spoke_03 -> spoke_01)
# - Relationship add/remove on heavily-connected entities
# - Perception queries on relationship graphs
# ============================================================


class TestRelationshipGraph:
    """Massive, circular, self-referencing relationship graph."""

    @staticmethod
    def _build() -> tuple[SceneConfig, StateStore]:
        config = SceneConfig(
            scene=SceneMetaConfig(id="graph", description="Graph"),
            entities=[],
            actions={
                "traverse": ActionConfig(
                    description="Move to linked node",
                    params=[ParamConfig(name="destination", type="entity_ref")],
                    preconditions=[
                        PreconditionConfig(
                            operator="check",
                            left="$destination",
                            op="in",
                            right=("relationships_of($agent.current_node, type=link)"),
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="$agent.current_node",
                            value="$destination",
                        ),
                    ],
                ),
                "add_link": ActionConfig(
                    description="Add a link",
                    params=[
                        ParamConfig(name="from_node", type="entity_ref"),
                        ParamConfig(name="to_node", type="entity_ref"),
                    ],
                    preconditions=[],
                    effects=[
                        EffectConfig(
                            operator="add_relationship",
                            from_entity="$from_node",
                            type="link",
                            to="$to_node",
                        ),
                    ],
                ),
                "remove_link": ActionConfig(
                    description="Remove a link",
                    params=[
                        ParamConfig(name="from_node", type="entity_ref"),
                        ParamConfig(name="to_node", type="entity_ref"),
                    ],
                    preconditions=[],
                    effects=[
                        EffectConfig(
                            operator="remove_relationship",
                            from_entity="$from_node",
                            type="link",
                            to="$to_node",
                        ),
                    ],
                ),
            },
        )

        store = StateStore()

        # Hub with many relationships (including self-reference)
        hub_links = [f"spoke_{i:02d}" for i in range(1, 11)] + ["hub"]
        store.add(
            Entity(
                id="hub",
                type="nexus",
                _data={
                    "label": "hub",
                    "link": hub_links,
                    "power": ["spoke_01", "spoke_02"],
                    "data": ["spoke_03", "spoke_04"],
                    "control": {"spoke_05": 100},
                },
            )
        )

        # Spoke nodes: circular chain 01->02->03->01
        store.add(
            Entity(
                id="spoke_01",
                type="node",
                _data={"label": "s1", "link": ["spoke_02", "hub"]},
            )
        )
        store.add(
            Entity(
                id="spoke_02",
                type="node",
                _data={"label": "s2", "link": ["spoke_03", "hub"]},
            )
        )
        store.add(
            Entity(
                id="spoke_03",
                type="node",
                _data={"label": "s3", "link": ["spoke_01", "hub"]},
            )
        )

        # Remaining spokes
        for i in range(4, 11):
            store.add(
                Entity(
                    id=f"spoke_{i:02d}",
                    type="node",
                    _data={"label": f"s{i}", "link": ["hub"]},
                )
            )

        # Agent at hub
        store.add(
            Entity(
                id="sysadmin",
                type="agent",
                _data={"current_node": "hub"},
            )
        )

        return config, store

    def test_relationships_of_hub_returns_many(self) -> None:
        """relationships_of(hub, type=link) returns 11 targets.

        10 spokes + self-reference.
        """
        _, store = self._build()
        from worldseed.dsl.functions import relationships_of

        targets = relationships_of("hub", "link", store)
        assert len(targets) == 11
        assert "hub" in targets  # self-reference
        for i in range(1, 11):
            assert f"spoke_{i:02d}" in targets

    def test_traverse_to_spoke_from_hub(self) -> None:
        """Agent at hub can traverse to any linked spoke."""
        config, store = self._build()
        engine = RulesEngine(config, store, EventLog())

        result = engine.process_action(
            ActionSubmission(
                agent_id="sysadmin",
                action_type="traverse",
                params={"destination": "spoke_05"},
            ),
            tick=1,
        )
        assert result.success
        assert store.get("sysadmin")["current_node"] == "spoke_05"  # type: ignore[union-attr]

    def test_traverse_self_reference(self) -> None:
        """Agent at hub can 'traverse' to hub (self-link). Weird but valid."""
        config, store = self._build()
        engine = RulesEngine(config, store, EventLog())

        result = engine.process_action(
            ActionSubmission(
                agent_id="sysadmin",
                action_type="traverse",
                params={"destination": "hub"},
            ),
            tick=1,
        )
        assert result.success
        assert store.get("sysadmin")["current_node"] == "hub"  # type: ignore[union-attr]

    def test_traverse_circular_chain(self) -> None:
        """Navigate the circular chain:
        hub -> spoke_01 -> spoke_02 -> spoke_03 -> spoke_01.
        """
        config, store = self._build()
        engine = RulesEngine(config, store, EventLog())

        path = ["spoke_01", "spoke_02", "spoke_03", "spoke_01"]
        for tick, dest in enumerate(path, 1):
            result = engine.process_action(
                ActionSubmission(
                    agent_id="sysadmin",
                    action_type="traverse",
                    params={"destination": dest},
                ),
                tick=tick,
            )
            assert result.success, f"Failed traversing to {dest}"
        assert store.get("sysadmin")["current_node"] == "spoke_01"  # type: ignore[union-attr]

    def test_traverse_unlinked_fails(self) -> None:
        """Agent at spoke_04 can't traverse to spoke_05 (no direct link)."""
        config, store = self._build()
        store.get("sysadmin")["current_node"] = "spoke_04"  # type: ignore[union-attr]
        engine = RulesEngine(config, store, EventLog())

        result = engine.process_action(
            ActionSubmission(
                agent_id="sysadmin",
                action_type="traverse",
                params={"destination": "spoke_05"},
            ),
            tick=1,
        )
        assert not result.success

    def test_add_and_use_new_link(self) -> None:
        """Add a link between spoke_04 and spoke_05, then traverse it."""
        config, store = self._build()
        store.get("sysadmin")["current_node"] = "spoke_04"  # type: ignore[union-attr]
        engine = RulesEngine(config, store, EventLog())

        # Can't traverse yet
        result = engine.process_action(
            ActionSubmission(
                agent_id="sysadmin",
                action_type="traverse",
                params={"destination": "spoke_05"},
            ),
            tick=1,
        )
        assert not result.success

        # Add link
        result = engine.process_action(
            ActionSubmission(
                agent_id="sysadmin",
                action_type="add_link",
                params={"from_node": "spoke_04", "to_node": "spoke_05"},
            ),
            tick=2,
        )
        assert result.success

        # Now traverse works
        result = engine.process_action(
            ActionSubmission(
                agent_id="sysadmin",
                action_type="traverse",
                params={"destination": "spoke_05"},
            ),
            tick=3,
        )
        assert result.success

    def test_remove_link_blocks_traverse(self) -> None:
        """Remove hub->spoke_01 link, then hub can't reach spoke_01."""
        config, store = self._build()
        engine = RulesEngine(config, store, EventLog())

        # Remove the link
        result = engine.process_action(
            ActionSubmission(
                agent_id="sysadmin",
                action_type="remove_link",
                params={"from_node": "hub", "to_node": "spoke_01"},
            ),
            tick=1,
        )
        assert result.success

        # Now traverse to spoke_01 from hub should fail
        result = engine.process_action(
            ActionSubmission(
                agent_id="sysadmin",
                action_type="traverse",
                params={"destination": "spoke_01"},
            ),
            tick=2,
        )
        assert not result.success

    def test_perception_sees_linked_entities(self) -> None:
        """Visibility rule: agent sees entities linked from current_node.
        At hub, agent should see all 10 spokes + hub itself."""
        config, store = self._build()

        mgr = InboxManager()
        perception = PerceptionConfig(
            visibility=[
                PreconditionConfig(
                    operator="any",
                    conditions=[
                        PreconditionConfig(
                            operator="check",
                            left="$entity.id",
                            op="in",
                            right=("relationships_of($observer.current_node, type=link)"),
                        ),
                        PreconditionConfig(
                            operator="check",
                            left="$entity.id",
                            op="==",
                            right="$observer.current_node",
                        ),
                    ],
                ),
            ],
        )
        p = Perceiver(store, EventLog(), mgr, perception)
        p.deliver(1)

        data = mgr.get_or_create("sysadmin").read()
        snap = data["current_state"]

        visible_ids = set(snap.visible_entities.keys())
        # Hub sees all 10 spokes + hub itself
        assert "hub" in visible_ids
        for i in range(1, 11):
            assert f"spoke_{i:02d}" in visible_ids, f"spoke_{i:02d} not visible"

    def test_perception_from_spoke_limited(self) -> None:
        """Agent at spoke_04 should only see hub (spoke_04's only link target)."""
        config, store = self._build()
        store.get("sysadmin")["current_node"] = "spoke_04"  # type: ignore[union-attr]

        mgr = InboxManager()
        perception = PerceptionConfig(
            visibility=[
                PreconditionConfig(
                    operator="any",
                    conditions=[
                        PreconditionConfig(
                            operator="check",
                            left="$entity.id",
                            op="in",
                            right=("relationships_of($observer.current_node, type=link)"),
                        ),
                        PreconditionConfig(
                            operator="check",
                            left="$entity.id",
                            op="==",
                            right="$observer.current_node",
                        ),
                    ],
                ),
            ],
        )
        p = Perceiver(store, EventLog(), mgr, perception)
        p.deliver(1)

        data = mgr.get_or_create("sysadmin").read()
        snap = data["current_state"]
        visible_ids = set(snap.visible_entities.keys())
        # spoke_04 links to hub only, plus itself
        assert visible_ids == {"hub", "spoke_04"}


# ============================================================
# SCENARIO 5: Entity Lifecycle Mid-Tick
# ============================================================
# Create entities, remove entities, reference dead entities.
#
# What we're hunting:
# - remove_entity + auto_tick that targets the removed entity -> crash?
# - remove_entity + consequence that references the removed entity -> crash?
# - create_entity then immediate traverse to it in same tick
# - create_entity with duplicate id -> ValueError
# - Perception snapshot after entity removal (dangling references?)
# ============================================================


class TestEntityLifecycle:
    """Entity creation, removal, and transformation mid-tick."""

    @staticmethod
    def _build() -> tuple[SceneConfig, StateStore]:
        config = SceneConfig(
            scene=SceneMetaConfig(id="lifecycle", description="Lifecycle"),
            entities=[],
            actions={
                "summon": ActionConfig(
                    description="Create entity",
                    params=[ParamConfig(name="name", type="string")],
                    preconditions=[],
                    effects=[
                        EffectConfig(
                            operator="create_entity",
                            id="summoned",
                            type="construct",
                            properties={"power": 10, "origin": "summon"},
                        ),
                    ],
                    events=[
                        EventConfig(
                            type="summon",
                            detail="$agent summoned $name",
                            ttl=3,
                            scope="global",
                        ),
                    ],
                ),
                "banish": ActionConfig(
                    description="Remove entity",
                    params=[ParamConfig(name="target", type="entity_ref")],
                    preconditions=[],
                    effects=[
                        EffectConfig(
                            operator="remove_entity",
                            target="$target",
                        ),
                    ],
                ),
                "transform": ActionConfig(
                    description="Remove + create (type shift)",
                    params=[ParamConfig(name="target", type="entity_ref")],
                    preconditions=[],
                    effects=[
                        EffectConfig(
                            operator="remove_entity",
                            target="$target",
                        ),
                        EffectConfig(
                            operator="create_entity",
                            id="evolved",
                            type="evolved_construct",
                            properties={"power": 50, "origin": "transformation"},
                        ),
                    ],
                ),
            },
            consequences={
                "doomed_check": ConsequenceConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left="doomed.health",
                            op="<",
                            right=5,
                        ),
                    ],
                    effects=[
                        EffectConfig(
                            operator="emit_event",
                            type="doom",
                            detail="doomed entity dying",
                            ttl=5,
                            scope="global",
                        ),
                    ],
                ),
            },
            auto_tick=[
                AutoTickConfig(
                    description="Doomed entity loses health",
                    effects=[
                        EffectConfig(
                            operator="decrement",
                            target="doomed.health",
                            by=1,
                        ),
                    ],
                ),
            ],
        )
        store = StateStore()
        store.add(
            Entity(
                id="summoner",
                type="agent",
                _data={"mana": 100},
            )
        )
        store.add(
            Entity(
                id="doomed",
                type="construct",
                _data={"health": 10, "power": 5},
            )
        )
        return config, store

    def test_create_entity(self) -> None:
        """Summon creates a new entity."""
        config, store = self._build()
        engine = RulesEngine(config, store, EventLog())

        result = engine.process_action(
            ActionSubmission(
                agent_id="summoner",
                action_type="summon",
                params={"name": "golem"},
            ),
            tick=1,
        )
        assert result.success
        summoned = store.get("summoned")
        assert summoned is not None
        assert summoned.type == "construct"
        assert summoned["power"] == 10

    def test_create_duplicate_id_skips_gracefully(self) -> None:
        """Creating an entity with an existing id logs warning and skips."""
        config, store = self._build()
        engine = RulesEngine(config, store, EventLog())

        # First summon succeeds
        result = engine.process_action(
            ActionSubmission(
                agent_id="summoner",
                action_type="summon",
                params={"name": "first"},
            ),
            tick=1,
        )
        assert result.success
        assert store.get("summoned") is not None

        # Second summon with same id — skips, doesn't crash
        result2 = engine.process_action(
            ActionSubmission(
                agent_id="summoner",
                action_type="summon",
                params={"name": "second"},
            ),
            tick=2,
        )
        assert result2.success  # action itself succeeds, create_entity is a no-op

    def test_banish_removes_entity(self) -> None:
        """Banish removes entity and cleans dangling relationships."""
        config, store = self._build()
        # Add a relationship property pointing to doomed
        store.update_property("summoner", "targets", ["doomed"])
        engine = RulesEngine(config, store, EventLog())

        result = engine.process_action(
            ActionSubmission(
                agent_id="summoner",
                action_type="banish",
                params={"target": "doomed"},
            ),
            tick=1,
        )
        assert result.success
        assert store.get("doomed") is None
        # Stale ref stays in raw properties (no write-time cleanup)
        summoner = store.get("summoner")
        assert summoner is not None
        assert summoner.get("targets") == ["doomed"]
        # relationships_of returns stale refs as-is (pure data read)
        assert relationships_of("summoner", "targets", store) == ["doomed"]

    def test_transform_removes_and_creates(self) -> None:
        """Transform: remove old entity, create new one of different type."""
        config, store = self._build()
        engine = RulesEngine(config, store, EventLog())

        result = engine.process_action(
            ActionSubmission(
                agent_id="summoner",
                action_type="transform",
                params={"target": "doomed"},
            ),
            tick=1,
        )
        assert result.success
        assert store.get("doomed") is None
        evolved = store.get("evolved")
        assert evolved is not None
        assert evolved.type == "evolved_construct"
        assert evolved["power"] == 50
        assert evolved["origin"] == "transformation"

    def test_auto_tick_on_removed_entity_survives(self) -> None:
        """Auto_tick targets 'doomed' which was removed.

        Engine gracefully skips the decrement (logs warning, no crash).
        """
        config, store = self._build()
        queue = ActionQueue()
        engine = TickEngine(config, store, EventLog(), queue)

        # Banish doomed entity
        queue.submit(
            ActionSubmission(
                agent_id="summoner",
                action_type="banish",
                params={"target": "doomed"},
            )
        )
        # This tick: banish runs (actions phase), then auto_tick tries to
        # decrement doomed.health — entity gone, skip gracefully.
        engine.step()  # no crash
        assert store.get("doomed") is None

    def test_consequence_on_removed_entity_survives(self) -> None:
        """Consequence references removed entity. ConsequenceScanner catches
        evaluation errors and logs a warning instead of crashing.

        The consequence trigger tries to read doomed.health,
        which resolves to None after removal. The < comparison returns
        False (safe_compare handles None), so it doesn't fire.
        """
        config, store = self._build()
        # Remove auto_tick to avoid the crash from the test above
        config_no_autotick = SceneConfig(
            scene=config.scene,
            entities=[],
            actions=config.actions,
            consequences=config.consequences,
            auto_tick=[],  # remove the problematic auto_tick
        )
        queue = ActionQueue()
        event_log = EventLog()
        engine = TickEngine(
            config_no_autotick,
            store,
            event_log,
            queue,
        )

        # Banish doomed
        queue.submit(
            ActionSubmission(
                agent_id="summoner",
                action_type="banish",
                params={"target": "doomed"},
            )
        )
        # This should NOT crash -- consequence scanner handles missing entities
        results = engine.step()
        assert results[0].success

        # The consequence should NOT fire (entity gone, path resolves to None)
        doom_events = event_log.get_events(event_type="doom")
        assert len(doom_events) == 0

    def test_perception_after_removal(self) -> None:
        """Perception snapshot excludes removed entities."""
        config, store = self._build()
        config_no_autotick = SceneConfig(
            scene=config.scene,
            entities=[],
            actions=config.actions,
            consequences={},
            auto_tick=[],
        )
        queue = ActionQueue()
        inbox_mgr = InboxManager()
        engine = TickEngine(
            config_no_autotick,
            store,
            EventLog(),
            queue,
            inbox_manager=inbox_mgr,
        )

        # Before removal: doomed visible
        engine.step()
        data = inbox_mgr.get_or_create("summoner").read()
        assert "doomed" in data["current_state"].visible_entities

        # Banish doomed
        queue.submit(
            ActionSubmission(
                agent_id="summoner",
                action_type="banish",
                params={"target": "doomed"},
            )
        )
        engine.step()

        # After removal: doomed gone from snapshot
        data = inbox_mgr.get_or_create("summoner").read()
        assert "doomed" not in data["current_state"].visible_entities
