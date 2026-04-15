"""Tests for Phase 2 tick ordering."""

from __future__ import annotations

from worldseed.engine.action_queue import ActionQueue
from worldseed.engine.event_log import EventLog
from worldseed.engine.inbox import InboxManager
from worldseed.engine.state_store import StateStore
from worldseed.engine.tick import TickEngine
from worldseed.models.config_schema import (
    AutoTickConfig,
    ConsequenceConfig,
    EffectConfig,
    PreconditionConfig,
    SceneConfig,
    SceneMetaConfig,
)
from worldseed.models.entity import Entity


def _bunker_tick_setup() -> tuple[TickEngine, StateStore, EventLog, InboxManager, ActionQueue]:
    """Set up a bunker scenario with tick engine."""
    config = SceneConfig(
        scene=SceneMetaConfig(id="test", description="test"),
        entities=[],
        actions={},
        consequences={
            "scarcity_alert": ConsequenceConfig(
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
            ),
        },
        auto_tick=[
            AutoTickConfig(
                description="Food consumption",
                effects=[
                    EffectConfig(
                        operator="decrement",
                        target="food_supply.quantity",
                        by=2,
                    )
                ],
            ),
        ],
    )
    store = StateStore()
    store.add(
        Entity(
            id="sleeping_quarters",
            type="space",
            _data={
                "description": "Sleeping area",
                "connects_to": ["hallway"],
            },
        )
    )
    store.add(
        Entity(
            id="hallway",
            type="space",
            _data={
                "description": "Corridor",
                "connects_to": ["sleeping_quarters"],
            },
        )
    )
    store.add(
        Entity(
            id="food_supply",
            type="resource",
            _data={
                "quantity": 6,
                "located_in": ["sleeping_quarters"],
            },
        )
    )
    store.add(
        Entity(
            id="agent1",
            type="agent",
            _data={"location": "sleeping_quarters"},
        )
    )

    event_log = EventLog()
    queue = ActionQueue()
    mgr = InboxManager()

    tick_engine = TickEngine(
        config,
        store,
        event_log,
        queue,
        inbox_manager=mgr,
    )
    return tick_engine, store, event_log, mgr, queue


class TestTickPhase2:
    def test_tick_order_consequence_after_auto_tick(self) -> None:
        """auto_tick drops food below 5 -> consequence fires same tick."""
        tick_engine, store, event_log, mgr, _ = _bunker_tick_setup()
        # food=6, auto_tick decrements by 2 -> food=4, consequence fires
        tick_engine.step()
        assert store.get("food_supply")["quantity"] == 4  # type: ignore[union-attr]
        events = event_log.get_events(event_type="scarcity")
        assert len(events) == 1

    def test_tick_order_perceiver_sees_consequence_events(self) -> None:
        """Consequence event delivered to agent inbox."""
        tick_engine, store, event_log, mgr, _ = _bunker_tick_setup()
        tick_engine.step()
        inbox = mgr.get_or_create("agent1")
        data = inbox.read()
        scarcity_events = [e for e in data["events"] if e.type == "scarcity"]
        assert len(scarcity_events) == 1

    def test_tick_order_cleanup_after_perceiver(self) -> None:
        """ttl=0 event visible in perceiver, gone next tick."""
        config = SceneConfig(
            scene=SceneMetaConfig(id="test", description="test"),
            entities=[],
            actions={},
            auto_tick=[
                AutoTickConfig(
                    description="Emit ephemeral event",
                    effects=[
                        EffectConfig(
                            operator="emit_event",
                            type="tick_sound",
                            detail="tick",
                            ttl=0,
                            scope="global",
                        )
                    ],
                ),
            ],
        )
        store = StateStore()
        store.add(
            Entity(
                id="agent1",
                type="agent",
                _data={"location": "room"},
            )
        )
        store.add(
            Entity(
                id="room",
                type="space",
                _data={},
            )
        )
        event_log = EventLog()
        queue = ActionQueue()
        mgr = InboxManager()
        tick_engine = TickEngine(
            config,
            store,
            event_log,
            queue,
            inbox_manager=mgr,
        )
        # Tick 1: event emitted with ttl=0 at tick 1
        tick_engine.step()
        data = mgr.get_or_create("agent1").read()
        # Agent should see the event (perceiver runs before cleanup)
        tick_events = [e for e in data["events"] if e.type == "tick_sound"]
        assert len(tick_events) == 1
        # ttl=0 at tick 1: alive while current_tick <= 1+0=1, so survives tick 1
        # Tick 2: new event emitted, old one cleaned (1+0 < 2)
        tick_engine.step()
        # Only tick 2's event should be in the log now
        events = event_log.get_events(event_type="tick_sound")
        assert len(events) == 1
        assert events[0].tick == 2
