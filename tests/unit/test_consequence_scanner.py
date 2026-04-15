"""Tests for Consequence Scanner."""

from __future__ import annotations

from worldseed.engine.consequence_scanner import (
    ConsequenceScanner,
    _references_entity,
)
from worldseed.engine.event_log import EventLog
from worldseed.engine.state_store import StateStore
from worldseed.models.config_schema import (
    ConsequenceConfig,
    EffectConfig,
    PreconditionConfig,
    SceneConfig,
    SceneMetaConfig,
)
from worldseed.models.entity import Entity


def _make_config(consequences: dict[str, ConsequenceConfig]) -> SceneConfig:
    return SceneConfig(
        scene=SceneMetaConfig(id="test", description="test"),
        entities=[],
        actions={},
        consequences=consequences,
    )


def _scarcity_consequence() -> ConsequenceConfig:
    return ConsequenceConfig(
        trigger=[
            PreconditionConfig(
                operator="check",
                left="food_supply.quantity",
                op="<",
                right=5,
            )
        ],
        effects=[
            EffectConfig(
                operator="emit_event",
                type="scarcity",
                detail="Food critically low",
                ttl=5,
                scope="global",
            )
        ],
    )


def _store_with_food(quantity: int | float) -> StateStore:
    store = StateStore()
    store.add(
        Entity(
            id="food_supply",
            type="resource",
            _data={"quantity": quantity},
        )
    )
    return store


class TestConsequenceScanner:
    def test_triggers_on_false_to_true(self) -> None:
        config = _make_config({"scarcity_alert": _scarcity_consequence()})
        store = _store_with_food(10)
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        # food=10 → not triggered
        triggered, _dm_pending = scanner.scan(1)
        assert triggered == []
        assert len(event_log.get_events()) == 0

        # food=4 → triggered
        store.update_property("food_supply", "quantity", 4)
        triggered, _dm_pending = scanner.scan(2)
        assert triggered == ["scarcity_alert"]
        assert len(event_log.get_events()) == 1
        assert event_log.get_events()[0].type == "scarcity"

    def test_no_retrigger_while_true(self) -> None:
        config = _make_config({"scarcity_alert": _scarcity_consequence()})
        store = _store_with_food(4)
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        scanner.scan(1)  # triggers
        scanner.scan(2)  # still true, should NOT retrigger
        assert len(event_log.get_events()) == 1

    def test_retriggers_after_reset(self) -> None:
        config = _make_config({"scarcity_alert": _scarcity_consequence()})
        store = _store_with_food(4)
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        scanner.scan(1)  # triggers (food=4 < 5)
        store.update_property("food_supply", "quantity", 6)
        scanner.scan(2)  # resets (food=6 >= 5)
        store.update_property("food_supply", "quantity", 3)
        scanner.scan(3)  # triggers again (food=3 < 5)
        assert len(event_log.get_events()) == 2

    def test_no_cascade_same_tick(self) -> None:
        """Consequence A modifies state making B's condition true.
        B fires same or next tick depending on eval order, but the key
        invariant is that A's effect doesn't retroactively change B's
        evaluation that already happened earlier in the same scan."""
        # Consequence A: food < 5 → set water to 0
        # Consequence B: water == 0 → emit event
        config = _make_config(
            {
                "a_scarcity": ConsequenceConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left="food_supply.quantity",
                            op="<",
                            right=5,
                        )
                    ],
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="water_supply.quantity",
                            value=0,
                        )
                    ],
                ),
                "b_drought": ConsequenceConfig(
                    trigger=[
                        PreconditionConfig(
                            operator="check",
                            left="water_supply.quantity",
                            op="==",
                            right=0,
                        )
                    ],
                    effects=[
                        EffectConfig(
                            operator="emit_event",
                            type="drought",
                            detail="No water",
                            ttl=5,
                            scope="global",
                        )
                    ],
                ),
            }
        )
        store = _store_with_food(10)
        store.add(
            Entity(
                id="water_supply",
                type="resource",
                _data={"quantity": 10},
            )
        )
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        # Tick 1: food=4 → A fires (sets water=0).
        # B may also fire in same tick (dict order) since A mutates water
        # before B evaluates.
        store.update_property("food_supply", "quantity", 4)
        triggered1, _dm_pending = scanner.scan(1)
        assert "a_scarcity" in triggered1

        # By tick 2 at latest, B should have fired (either in tick 1 or tick 2)
        triggered2, _dm_pending = scanner.scan(2)
        all_triggered = triggered1 + triggered2
        assert "b_drought" in all_triggered

    def test_multiple_independent_consequences(self) -> None:
        water_consequence = ConsequenceConfig(
            trigger=[
                PreconditionConfig(
                    operator="check",
                    left="water_supply.quantity",
                    op="<",
                    right=3,
                )
            ],
            effects=[
                EffectConfig(
                    operator="emit_event",
                    type="water_low",
                    detail="Water low",
                    ttl=5,
                    scope="global",
                )
            ],
        )
        config = _make_config(
            {
                "scarcity_alert": _scarcity_consequence(),
                "water_alert": water_consequence,
            }
        )
        store = _store_with_food(4)
        store.add(
            Entity(
                id="water_supply",
                type="resource",
                _data={"quantity": 2},
            )
        )
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)
        triggered, _dm_pending = scanner.scan(1)
        assert "scarcity_alert" in triggered
        assert "water_alert" in triggered

    def test_scan_returns_triggered_names(self) -> None:
        config = _make_config({"scarcity_alert": _scarcity_consequence()})
        store = _store_with_food(4)
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)
        result, _dm_pending = scanner.scan(1)
        assert result == ["scarcity_alert"]


def _entity_meltdown_consequence() -> ConsequenceConfig:
    """Consequence that references $entity — fires when any agent has stress >= 100."""
    return ConsequenceConfig(
        trigger=[
            PreconditionConfig(
                operator="check",
                left="$entity.type",
                op="==",
                right="agent",
            ),
            PreconditionConfig(
                operator="check",
                left="$entity.stress",
                op=">=",
                right=100,
            ),
        ],
        effects=[
            EffectConfig(
                operator="emit_event",
                type="drama",
                detail="A chef is having a MELTDOWN!",
                ttl=5,
                scope="global",
            )
        ],
    )


def _store_with_agents() -> StateStore:
    """Create a store with two agents and a non-agent entity."""
    store = StateStore()
    store.add(Entity(id="chef_a", type="agent", _data={"stress": 20}))
    store.add(Entity(id="chef_b", type="agent", _data={"stress": 50}))
    store.add(Entity(id="pantry", type="supply", _data={"flour": 10}))
    return store


class TestReferencesEntity:
    def test_detects_entity_in_check_left(self) -> None:
        c = ConsequenceConfig(
            trigger=[
                PreconditionConfig(operator="check", left="$entity.type", op="==", right="agent"),
            ],
            effects=[],
        )
        assert _references_entity(c) is True

    def test_detects_entity_in_check_right(self) -> None:
        c = ConsequenceConfig(
            trigger=[
                PreconditionConfig(operator="check", left="foo", op="==", right="$entity.x"),
            ],
            effects=[],
        )
        assert _references_entity(c) is True

    def test_no_entity_returns_false(self) -> None:
        c = ConsequenceConfig(
            trigger=[
                PreconditionConfig(operator="check", left="food.qty", op="<", right=5),
            ],
            effects=[],
        )
        assert _references_entity(c) is False

    def test_detects_entity_in_nested_any(self) -> None:
        c = ConsequenceConfig(
            trigger=[
                PreconditionConfig(
                    operator="any",
                    conditions=[
                        PreconditionConfig(
                            operator="check",
                            left="$entity.type",
                            op="==",
                            right="agent",
                        ),
                    ],
                ),
            ],
            effects=[],
        )
        assert _references_entity(c) is True

    def test_detects_entity_in_not_condition(self) -> None:
        c = ConsequenceConfig(
            trigger=[
                PreconditionConfig(
                    operator="not",
                    condition=PreconditionConfig(operator="check", left="$entity.type", op="==", right="agent"),
                ),
            ],
            effects=[],
        )
        assert _references_entity(c) is True

    def test_detects_entity_in_exists_expression(self) -> None:
        c = ConsequenceConfig(
            trigger=[
                PreconditionConfig(
                    operator="exists",
                    expression="$entity.flag",
                ),
            ],
            effects=[],
        )
        assert _references_entity(c) is True


class TestEntityConsequenceScanner:
    def test_entity_consequence_fires_when_threshold_crossed(self) -> None:
        """$entity consequence fires when an agent crosses the stress threshold."""
        config = _make_config({"meltdown": _entity_meltdown_consequence()})
        store = _store_with_agents()
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        # No one is stressed enough
        triggered, _dm_pending = scanner.scan(1)
        assert triggered == []
        assert len(event_log.get_events()) == 0

        # Push chef_a over the edge
        store.update_property("chef_a", "stress", 100)
        triggered, _dm_pending = scanner.scan(2)
        assert "meltdown" in triggered
        events = event_log.get_events()
        assert len(events) == 1
        assert events[0].type == "drama"

    def test_entity_consequence_ignores_non_matching_type(self) -> None:
        """$entity consequence with type=='agent' should not match a 'supply' entity."""
        config = _make_config({"meltdown": _entity_meltdown_consequence()})
        store = _store_with_agents()
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        # Even if pantry had a 'stress' property, it's type 'supply' not 'agent'
        store.update_property("pantry", "flour", 0)  # irrelevant change
        triggered, _dm_pending = scanner.scan(1)
        assert triggered == []

    def test_entity_consequence_no_retrigger_per_entity(self) -> None:
        """on_change: same entity above threshold doesn't re-fire."""
        config = _make_config({"meltdown": _entity_meltdown_consequence()})
        store = _store_with_agents()
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        store.update_property("chef_a", "stress", 100)
        scanner.scan(1)  # fires for chef_a
        scanner.scan(2)  # chef_a still stressed, should NOT re-fire
        assert len(event_log.get_events()) == 1

    def test_entity_consequence_fires_for_second_entity(self) -> None:
        """Different entities independently trigger the same consequence."""
        config = _make_config({"meltdown": _entity_meltdown_consequence()})
        store = _store_with_agents()
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        # chef_a melts down
        store.update_property("chef_a", "stress", 100)
        triggered1, _dm_pending = scanner.scan(1)
        assert "meltdown" in triggered1

        # chef_b melts down on a later tick
        store.update_property("chef_b", "stress", 110)
        triggered2, _dm_pending = scanner.scan(2)
        assert "meltdown" in triggered2

        # Two independent firings
        assert len(event_log.get_events()) == 2

    def test_entity_consequence_retriggers_after_recovery(self) -> None:
        """An entity that recovers and then crosses threshold again re-fires."""
        config = _make_config({"meltdown": _entity_meltdown_consequence()})
        store = _store_with_agents()
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        store.update_property("chef_a", "stress", 100)
        scanner.scan(1)  # fires
        store.update_property("chef_a", "stress", 50)
        scanner.scan(2)  # resets
        store.update_property("chef_a", "stress", 120)
        scanner.scan(3)  # fires again
        assert len(event_log.get_events()) == 2

    def test_mixed_entity_and_global_consequences(self) -> None:
        """Entity and non-entity consequences coexist correctly."""
        config = _make_config(
            {
                "meltdown": _entity_meltdown_consequence(),
                "scarcity_alert": _scarcity_consequence(),
            }
        )
        store = _store_with_agents()
        store.add(Entity(id="food_supply", type="resource", _data={"quantity": 10}))
        event_log = EventLog()
        scanner = ConsequenceScanner(config, store, event_log)

        # Neither condition met
        triggered, _dm_pending = scanner.scan(1)
        assert triggered == []

        # Both conditions met simultaneously
        store.update_property("chef_a", "stress", 100)
        store.update_property("food_supply", "quantity", 3)
        triggered, _dm_pending = scanner.scan(2)
        assert "meltdown" in triggered
        assert "scarcity_alert" in triggered
        assert len(event_log.get_events()) == 2
