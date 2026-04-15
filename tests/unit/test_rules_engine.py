"""Tests for RulesEngine — integration with bunker config."""

from __future__ import annotations

import pytest

from tests.helpers import CONFIGS_DIR
from worldseed.engine.event_log import EventLog
from worldseed.engine.rules_engine import RulesEngine
from worldseed.engine.state_store import StateStore
from worldseed.models import ActionSubmission
from worldseed.world import WorldEngine


def _make_engine() -> tuple[RulesEngine, StateStore, EventLog]:
    w = WorldEngine(CONFIGS_DIR / "bunker.yaml")
    w.register_from_config()
    engine = RulesEngine(w.config, w.state, w.event_log)
    return engine, w.state, w.event_log


class TestMove:
    def test_valid_move(self) -> None:
        engine, store, event_log = _make_engine()
        action = ActionSubmission(
            agent_id="old_chen",
            action_type="move",
            params={"to": "hallway"},
        )
        result = engine.process_action(action, tick=1)
        assert result.success
        chen = store.get("old_chen")
        assert chen is not None
        assert chen["location"] == "hallway"
        # Event emitted with DEPARTURE location, not destination
        events = event_log.get_events()
        assert len(events) == 1
        assert events[0].type == "move"
        assert events[0].source == "old_chen"

    def test_invalid_move_not_adjacent(self) -> None:
        engine, store, _ = _make_engine()
        action = ActionSubmission(
            agent_id="old_chen",
            action_type="move",
            params={"to": "storage_room"},
        )
        result = engine.process_action(action, tick=1)
        assert not result.success
        assert result.reason  # descriptive error with resolved values
        # State unchanged
        chen = store.get("old_chen")
        assert chen is not None
        assert chen["location"] == "sleeping_quarters"


class TestTake:
    def test_valid_take(self) -> None:
        engine, store, event_log = _make_engine()
        # Move chen to storage_room first
        store.update_property("old_chen", "location", "storage_room")
        action = ActionSubmission(
            agent_id="old_chen",
            action_type="take",
            params={"target": "food_supply", "amount": 3},
        )
        result = engine.process_action(action, tick=1)
        assert result.success
        food = store.get("food_supply")
        assert food is not None
        assert food["quantity"] == 17
        chen = store.get("old_chen")
        assert chen is not None
        assert chen["private_stash"] == 3

    def test_take_insufficient_quantity(self) -> None:
        engine, store, _ = _make_engine()
        store.update_property("old_chen", "location", "storage_room")
        action = ActionSubmission(
            agent_id="old_chen",
            action_type="take",
            params={"target": "food_supply", "amount": 999},
        )
        result = engine.process_action(action, tick=1)
        assert not result.success
        food = store.get("food_supply")
        assert food is not None
        assert food["quantity"] == 20

    def test_take_negative_amount_rejected(self) -> None:
        engine, store, _ = _make_engine()
        store.update_property("old_chen", "location", "storage_room")
        action = ActionSubmission(
            agent_id="old_chen",
            action_type="take",
            params={"target": "food_supply", "amount": -5},
        )
        result = engine.process_action(action, tick=1)
        assert not result.success
        assert "non-negative" in result.reason
        # State unchanged — no resource duplication
        food = store.get("food_supply")
        assert food is not None
        assert food["quantity"] == 20

    def test_take_wrong_location(self) -> None:
        engine, store, _ = _make_engine()
        # chen is in sleeping_quarters, food is in storage_room
        action = ActionSubmission(
            agent_id="old_chen",
            action_type="take",
            params={"target": "food_supply", "amount": 3},
        )
        result = engine.process_action(action, tick=1)
        assert not result.success


class TestSay:
    def test_say_emits_event_no_state_change(self) -> None:
        engine, store, event_log = _make_engine()
        action = ActionSubmission(
            agent_id="old_chen",
            action_type="say",
            params={"message": "hello everyone"},
        )
        result = engine.process_action(action, tick=1)
        assert result.success
        events = event_log.get_events()
        assert len(events) == 1
        assert events[0].type == "say"
        assert "old_chen: hello everyone" in events[0].detail


class TestDmField:
    def test_observe_dm_skipped_sync(self) -> None:
        """Sync process_action skips dm field — no state change, no crash."""
        engine, store, event_log = _make_engine()
        store.update_property("old_chen", "location", "storage_room")
        food_before = store.get("food_supply")
        assert food_before is not None
        qty_before = food_before["quantity"]

        action = ActionSubmission(
            agent_id="old_chen",
            action_type="observe",
            params={"target": "food_supply"},
        )
        result = engine.process_action(action, tick=1)
        assert result.success
        # No state changed (dm field skipped in sync mode)
        assert food_before["quantity"] == qty_before

    def test_attempt_dm_skipped_sync(self) -> None:
        """Sync process_action skips dm field on attempt."""
        engine, store, event_log = _make_engine()
        action = ActionSubmission(
            agent_id="old_chen",
            action_type="attempt",
            params={"description": "fly to the moon"},
        )
        result = engine.process_action(action, tick=1)
        assert result.success

    def test_dm_field_detected_on_action(self) -> None:
        """ActionConfig with dm field is detected by the engine."""
        from worldseed.models.config_schema import (
            ActionConfig,
            DMConfig,
            SceneConfig,
            SceneMetaConfig,
        )

        config = SceneConfig(
            scene=SceneMetaConfig(id="test", description="test"),
            entities=[],
            actions={
                "look": ActionConfig(
                    description="Look around",
                    effects=[],
                    dm=DMConfig(hint="Describe what the agent sees."),
                ),
                "walk": ActionConfig(
                    description="Walk",
                    effects=[],
                ),
            },
        )
        assert config.actions["look"].dm is not None
        assert config.actions["look"].dm.hint == "Describe what the agent sees."
        assert config.actions["walk"].dm is None


class TestAutoTick:
    def test_food_consumption(self) -> None:
        engine, store, _ = _make_engine()
        food = store.get("food_supply")
        assert food is not None
        initial = food["quantity"]
        engine.process_auto_tick(tick=1)
        # 3 agents * 0.1 = 0.3 consumed (narrator excluded via _system)
        assert food["quantity"] == pytest.approx(
            initial - 0.3,
        )

    def test_water_consumption(self) -> None:
        engine, store, _ = _make_engine()
        water = store.get("water_supply")
        assert water is not None
        initial = water["quantity"]
        engine.process_auto_tick(tick=1)
        # 3 agents * 0.05 = 0.15 consumed (narrator excluded via _system)
        assert water["quantity"] == pytest.approx(
            initial - 0.15,
        )


class TestMultiAgent:
    def test_two_agents_same_tick(self) -> None:
        engine, store, event_log = _make_engine()
        # Both agents move in the same tick
        a1 = ActionSubmission(
            agent_id="old_chen",
            action_type="move",
            params={"to": "hallway"},
        )
        a2 = ActionSubmission(
            agent_id="xiao_li",
            action_type="move",
            params={"to": "hallway"},
        )
        r1 = engine.process_action(a1, tick=1)
        r2 = engine.process_action(a2, tick=1)
        assert r1.success
        assert r2.success
        chen = store.get("old_chen")
        li = store.get("xiao_li")
        assert chen is not None and li is not None
        assert chen["location"] == "hallway"
        assert li["location"] == "hallway"


class TestAutoTickCondition:
    def test_auto_tick_condition_true(self) -> None:
        """When condition is met, effects run."""
        from worldseed.models.config_schema import (
            AutoTickConfig,
            EffectConfig,
            PreconditionConfig,
            SceneConfig,
            SceneMetaConfig,
        )
        from worldseed.models.entity import Entity

        config = SceneConfig(
            scene=SceneMetaConfig(id="test", description="test"),
            entities=[],
            actions={},
            auto_tick=[
                AutoTickConfig(
                    description="Conditional decrement",
                    effects=[
                        EffectConfig(
                            operator="decrement",
                            target="food.quantity",
                            by=1,
                        )
                    ],
                    condition=[
                        PreconditionConfig(
                            operator="check",
                            left="food.quantity",
                            op=">",
                            right=5,
                        )
                    ],
                ),
            ],
        )
        store = StateStore()
        store.add(Entity(id="food", type="resource", _data={"quantity": 10}))
        engine = RulesEngine(config, store, EventLog())
        engine.process_auto_tick(1)
        assert store.get("food")["quantity"] == 9  # type: ignore[union-attr]

    def test_auto_tick_condition_false(self) -> None:
        """When condition is not met, effects skip."""
        from worldseed.models.config_schema import (
            AutoTickConfig,
            EffectConfig,
            PreconditionConfig,
            SceneConfig,
            SceneMetaConfig,
        )
        from worldseed.models.entity import Entity

        config = SceneConfig(
            scene=SceneMetaConfig(id="test", description="test"),
            entities=[],
            actions={},
            auto_tick=[
                AutoTickConfig(
                    description="Conditional decrement",
                    effects=[
                        EffectConfig(
                            operator="decrement",
                            target="food.quantity",
                            by=1,
                        )
                    ],
                    condition=[
                        PreconditionConfig(
                            operator="check",
                            left="food.quantity",
                            op=">",
                            right=15,
                        )
                    ],
                ),
            ],
        )
        store = StateStore()
        store.add(Entity(id="food", type="resource", _data={"quantity": 10}))
        engine = RulesEngine(config, store, EventLog())
        engine.process_auto_tick(1)
        assert store.get("food")["quantity"] == 10  # type: ignore[union-attr]

    def test_auto_tick_mixed(self) -> None:
        """Unconditional always runs, conditional only when true."""
        from worldseed.models.config_schema import (
            AutoTickConfig,
            EffectConfig,
            PreconditionConfig,
            SceneConfig,
            SceneMetaConfig,
        )
        from worldseed.models.entity import Entity

        config = SceneConfig(
            scene=SceneMetaConfig(id="test", description="test"),
            entities=[],
            actions={},
            auto_tick=[
                AutoTickConfig(
                    description="Always runs",
                    effects=[
                        EffectConfig(
                            operator="decrement",
                            target="food.quantity",
                            by=1,
                        )
                    ],
                ),
                AutoTickConfig(
                    description="Only when food > 15",
                    effects=[
                        EffectConfig(
                            operator="decrement",
                            target="food.quantity",
                            by=100,
                        )
                    ],
                    condition=[
                        PreconditionConfig(
                            operator="check",
                            left="food.quantity",
                            op=">",
                            right=15,
                        )
                    ],
                ),
            ],
        )
        store = StateStore()
        store.add(Entity(id="food", type="resource", _data={"quantity": 10}))
        engine = RulesEngine(config, store, EventLog())
        engine.process_auto_tick(1)
        # Only the unconditional one ran (-1), conditional skipped (-100)
        assert store.get("food")["quantity"] == 9  # type: ignore[union-attr]


class TestUnknownAction:
    def test_unknown_type_rejected(self) -> None:
        engine, _, _ = _make_engine()
        action = ActionSubmission(
            agent_id="old_chen",
            action_type="fly",
        )
        result = engine.process_action(action, tick=1)
        assert not result.success
        assert "Unknown action" in result.reason
