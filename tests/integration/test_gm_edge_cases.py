"""Edge case tests for GM system — pending ops, missing entities."""

from __future__ import annotations

import asyncio
from typing import Any

from worldseed.dm.providers.mock import MockDMProvider
from worldseed.engine.action_queue import ActionQueue
from worldseed.engine.event_log import EventLog
from worldseed.engine.state_store import StateStore
from worldseed.engine.tick import TickEngine
from worldseed.models import Entity
from worldseed.models.config_schema import (
    EffectConfig,
    SceneConfig,
    SceneMetaConfig,
)
from worldseed.protocol.dm import DMContext, DMResponse


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _make_engine(
    dm: Any | None = None,
) -> tuple[TickEngine, StateStore, EventLog]:
    config = SceneConfig(
        scene=SceneMetaConfig(id="test", description="A test world"),
        entities=[],
        actions={},
    )
    store = StateStore()
    store.add(
        Entity(
            id="water",
            type="resource",
            _data={"quantity": 50, "quality": "good"},
        )
    )
    store.add(
        Entity(
            id="agent_a",
            type="agent",
            _data={"hp": 100, "location": "room1"},
        )
    )
    store.add(
        Entity(
            id="crate",
            type="object",
            _data={"weight": 10, "contents": "empty"},
        )
    )
    event_log = EventLog()
    queue = ActionQueue()
    tick = TickEngine(config, store, event_log, queue, dm_provider=dm)
    return tick, store, event_log


# ── Edge Case 1: Multiple entity/set for SAME entity+property ──


class TestMultipleSetSameProperty:
    """Queue multiple entity/set for the same entity + property — does last one win?"""

    def test_last_set_wins_same_property(self) -> None:
        """Three sets on water.quantity: only the last value remains."""
        tick, store, _ = _make_engine()

        tick.pending_ops.enqueue_entity_set("water", "quantity", 100, tick=0)
        tick.pending_ops.enqueue_entity_set("water", "quantity", 200, tick=0)
        tick.pending_ops.enqueue_entity_set("water", "quantity", 999, tick=0)

        tick.step()

        assert store.get("water").get("quantity") == 999

    def test_interleaved_sets_different_properties(self) -> None:
        """Sets on different properties of the same entity are all applied."""
        tick, store, _ = _make_engine()

        tick.pending_ops.enqueue_entity_set("water", "quantity", 200, tick=0)
        tick.pending_ops.enqueue_entity_set("water", "quality", "bad", tick=0)

        tick.step()

        assert store.get("water").get("quantity") == 200
        assert store.get("water").get("quality") == "bad"

    def test_multiple_sets_different_entities_same_property_name(self) -> None:
        """Sets on different entities with same property name are independent."""
        tick, store, _ = _make_engine()

        tick.pending_ops.enqueue_entity_set("water", "quantity", 999, tick=0)
        tick.pending_ops.enqueue_entity_set("crate", "weight", 50, tick=0)

        tick.step()

        assert store.get("water").get("quantity") == 999
        assert store.get("crate").get("weight") == 50


# ── Edge Case 2: entity/remove then entity/set for same entity ──


class TestRemoveThenSet:
    """Queue entity/remove then entity/set for same entity — what happens?"""

    def test_remove_then_set_same_entity(self) -> None:
        """Remove applied first, so set on removed entity is a no-op."""
        tick, store, _ = _make_engine()

        # The drain order in _drain_entity_ops: sets first, then removes.
        # Sets drain first, then removes.
        tick.pending_ops.enqueue_entity_remove("water", tick=0)
        tick.pending_ops.enqueue_entity_set("water", "quantity", 999, tick=0)

        tick.step()

        # Sets drain first, then removes — entity should be gone
        assert store.get("water") is None

    def test_set_then_remove_same_entity(self) -> None:
        """Set first, remove second -> entity gone."""
        tick, store, _ = _make_engine()

        tick.pending_ops.enqueue_entity_set("water", "quantity", 999, tick=0)
        tick.pending_ops.enqueue_entity_remove("water", tick=0)

        tick.step()

        # Sets applied, then remove applied -> entity gone
        assert store.get("water") is None

    def test_remove_nonexistent_entity_is_noop(self) -> None:
        """Removing an entity that doesn't exist should not raise."""
        tick, store, _ = _make_engine()

        tick.pending_ops.enqueue_entity_remove("ghost_entity", tick=0)

        # Should not raise
        tick.step()

        # Other entities unaffected
        assert store.get("water") is not None


# ── Edge Case 3: entity/set for non-existent entity ──


class TestSetNonExistentEntity:
    """Queue entity/set for an entity that doesn't exist."""

    def test_set_nonexistent_entity_silently_skips(self) -> None:
        """Setting a property on a missing entity should silently skip (no crash)."""
        tick, store, _ = _make_engine()

        tick.pending_ops.enqueue_entity_set("does_not_exist", "foo", 42, tick=0)

        # Should not raise
        tick.step()

        # Entity was never created
        assert store.get("does_not_exist") is None

    def test_set_nonexistent_does_not_affect_others(self) -> None:
        """A failed set on a missing entity should not affect other pending ops."""
        tick, store, _ = _make_engine()

        tick.pending_ops.enqueue_entity_set("does_not_exist", "foo", 42, tick=0)
        tick.pending_ops.enqueue_entity_set("water", "quantity", 200, tick=0)

        tick.step()

        assert store.get("water").get("quantity") == 200


# ── Edge Case 4: GM resolve with empty text ──


class TestGMResolveEmptyText:
    """GM resolve with empty text — does it crash, skip, or pass through to DM?"""

    def test_empty_text_still_calls_dm(self) -> None:
        """Empty text is passed to DM (no early abort in the code)."""
        dm = MockDMProvider()
        tick, store, event_log = _make_engine(dm)

        tick.pending_ops.enqueue_gm_resolve("", tick=0)
        _run(tick.step_async())

        # DM was called (the code doesn't filter empty text)
        assert dm.call_count == 1
        assert dm.last_context.action.params["command"] == ""

    def test_whitespace_only_text_calls_dm(self) -> None:
        """Whitespace-only text is also passed through."""
        dm = MockDMProvider()
        tick, store, event_log = _make_engine(dm)

        tick.pending_ops.enqueue_gm_resolve("   ", tick=0)
        _run(tick.step_async())

        assert dm.call_count == 1


# ── Edge Case 5: DM effects target entity removed by pending entity/remove ──


class TestDMEffectsOnRemovedEntity:
    """GM resolve effects targeting an entity removed in same tick."""

    def test_dm_effects_on_removed_entity(self) -> None:
        """Pending remove runs at tick start. DM resolve runs later.
        DM returns effects targeting the removed entity -> validation should fail."""
        # DM returns an effect targeting "water" — but water was removed
        dm = MockDMProvider(
            responses={
                "gm_resolve": DMResponse(
                    narrative="Increased water.",
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="water.quantity",
                            value=999,
                        ),
                    ],
                ),
            }
        )
        tick, store, event_log = _make_engine(dm)

        # Queue remove of water AND a gm_resolve that targets water
        tick.pending_ops.enqueue_entity_remove("water", tick=0)
        tick.pending_ops.enqueue_gm_resolve("increase water", tick=0)

        _run(tick.step_async())

        # Water should be gone (removed at tick start)
        assert store.get("water") is None

        # DM was called, but validation should fail because "water" no longer exists
        # The validate_dm_effects checks entity existence for "set" operator
        assert dm.call_count >= 1

        # Check for failure event in log
        events = event_log.get_events()
        fail_events = [e for e in events if e.type == "gm_resolve_failed"]
        # If validation fails, a gm_resolve_failed event is emitted
        assert len(fail_events) == 1

    def test_dm_effects_on_entity_removed_then_recreated(self) -> None:
        """Edge: entity removed, then DM recreates it and sets a property.

        First resolve creates entity "water" back.
        Second resolve sets water.quantity — this succeeds because resolves
        are sequential and the second DM call sees the recreated entity.
        """
        call_count = 0

        class SequentialDM:
            async def judge(self, context: DMContext) -> DMResponse:
                nonlocal call_count
                call_count += 1
                if call_count == 1:
                    # First resolve: create entity "water" back
                    return DMResponse(
                        narrative="Recreated water.",
                        effects=[
                            EffectConfig(
                                operator="create_entity",
                                id="water",
                                type="resource",
                                properties={"quantity": 0},
                            ),
                        ],
                    )
                else:
                    # Second resolve: set on recreated water
                    return DMResponse(
                        narrative="Set water.",
                        effects=[
                            EffectConfig(
                                operator="set",
                                target="water.quantity",
                                value=500,
                            ),
                        ],
                    )

        dm = SequentialDM()
        tick, store, event_log = _make_engine(dm)

        # Remove water, then two gm_resolves: recreate + set
        tick.pending_ops.enqueue_entity_remove("water", tick=0)
        tick.pending_ops.enqueue_gm_resolve("recreate water", tick=0)
        tick.pending_ops.enqueue_gm_resolve("set water quantity", tick=0)

        _run(tick.step_async())

        # Water should exist again with quantity=500
        water = store.get("water")
        assert water is not None
        assert water.get("quantity") == 500


# ── Edge Case 6: Multiple gm_resolve — sequential ──


class TestMultipleGMResolvesSequential:
    """Multiple gm_resolve commands in same tick execute sequentially."""

    def test_second_resolve_sees_first_resolve_changes(self) -> None:
        """Second GM resolve can observe state changes made by first."""
        observed_quantities: list[Any] = []

        class InspectingDM:
            def __init__(self, store: StateStore) -> None:
                self._store = store

            async def judge(self, context: DMContext) -> DMResponse:
                # Record what quantity the store has at call time
                water = self._store.get("water")
                observed_quantities.append(water.get("quantity") if water else None)
                cmd = context.action.params["command"]
                if cmd == "double water":
                    return DMResponse(
                        narrative="Doubled water.",
                        effects=[
                            EffectConfig(
                                operator="set",
                                target="water.quantity",
                                value=100,  # 50 -> 100
                            ),
                        ],
                    )
                return DMResponse(
                    narrative="Incremented water.",
                    effects=[
                        EffectConfig(
                            operator="increment",
                            target="water.quantity",
                            value=50,
                        ),
                    ],
                )

        config = SceneConfig(
            scene=SceneMetaConfig(id="test", description="test"),
            entities=[],
            actions={},
        )
        store = StateStore()
        store.add(Entity(id="water", type="resource", _data={"quantity": 50}))
        event_log = EventLog()
        queue = ActionQueue()
        dm = InspectingDM(store)
        tick = TickEngine(config, store, event_log, queue, dm_provider=dm)  # type: ignore[arg-type]

        tick.pending_ops.enqueue_gm_resolve("double water", tick=0)
        tick.pending_ops.enqueue_gm_resolve("increment water", tick=0)

        _run(tick.step_async())

        # First call sees original quantity (50)
        assert observed_quantities[0] == 50
        # Second call sees quantity after first resolve applied (100)
        assert observed_quantities[1] == 100
        # Final: 100 + 50 = 150
        assert store.get("water").get("quantity") == 150

    def test_three_sequential_resolves(self) -> None:
        """Three resolves each increment, final state reflects all three."""
        dm = MockDMProvider(
            responses={
                "gm_resolve": DMResponse(
                    narrative="Incremented.",
                    effects=[
                        EffectConfig(
                            operator="increment",
                            target="water.quantity",
                            value=10,
                        ),
                    ],
                ),
            }
        )
        tick, store, event_log = _make_engine(dm)

        tick.pending_ops.enqueue_gm_resolve("inc1", tick=0)
        tick.pending_ops.enqueue_gm_resolve("inc2", tick=0)
        tick.pending_ops.enqueue_gm_resolve("inc3", tick=0)

        _run(tick.step_async())

        # 50 + 10 + 10 + 10 = 80
        assert store.get("water").get("quantity") == 80
        assert dm.call_count == 3
