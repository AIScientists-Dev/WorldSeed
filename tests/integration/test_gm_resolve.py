"""Tests for GM resolve — natural language command → DM → effects."""

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
from worldseed.protocol.dm import DMResponse


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _make_engine(
    dm: MockDMProvider,
) -> tuple[TickEngine, StateStore, EventLog]:
    config = SceneConfig(
        scene=SceneMetaConfig(id="test", description="A test world"),
        entities=[],
        actions={},
    )
    store = StateStore()
    store.add(Entity(id="water", type="resource", _data={"quantity": 50}))
    store.add(Entity(id="agent_a", type="agent", _data={"hp": 100}))
    event_log = EventLog()
    queue = ActionQueue()
    tick = TickEngine(config, store, event_log, queue, dm_provider=dm)
    return tick, store, event_log


class TestGMResolveQueue:
    """Queue mechanics — enqueue, drain, request_id."""

    def test_enqueue_returns_request_id(self) -> None:
        dm = MockDMProvider()
        tick, store, _ = _make_engine(dm)
        req_id = tick.pending_ops.enqueue_gm_resolve("water +100", tick=0)
        assert isinstance(req_id, str)
        assert len(req_id) == 8

    def test_drain_returns_all_pending(self) -> None:
        dm = MockDMProvider()
        tick, store, _ = _make_engine(dm)
        tick.pending_ops.enqueue_gm_resolve("water +100", tick=0)
        tick.pending_ops.enqueue_gm_resolve("hp -10", tick=0)
        items = tick.pending_ops.drain_gm_resolves()
        assert len(items) == 2
        assert items[0].text == "water +100"
        assert items[1].text == "hp -10"

    def test_drain_clears_queue(self) -> None:
        dm = MockDMProvider()
        tick, store, _ = _make_engine(dm)
        tick.pending_ops.enqueue_gm_resolve("test", tick=0)
        tick.pending_ops.drain_gm_resolves()
        assert tick.pending_ops.drain_gm_resolves() == []


class TestGMResolveExecution:
    """Full flow — queue → tick → DM called → effects applied."""

    def test_gm_resolve_applies_effects(self) -> None:
        """GM command 'add 100 water' → DM returns increment → quantity changes."""
        dm = MockDMProvider(
            responses={
                "gm_resolve": DMResponse(
                    narrative="Water supply increased by 100.",
                    effects=[
                        EffectConfig(
                            operator="increment",
                            target="water.quantity",
                            value=100,
                        ),
                    ],
                ),
            }
        )
        tick, store, event_log = _make_engine(dm)

        # Queue the command
        tick.pending_ops.enqueue_gm_resolve("add 100 water", tick=0)

        # Step — should drain and apply
        _run(tick.step_async())

        assert store.get("water").get("quantity") == 150
        assert dm.call_count == 1

    def test_gm_resolve_emits_admin_event(self) -> None:
        """GM resolve narrative appears as admin-scoped event."""
        dm = MockDMProvider(
            responses={
                "gm_resolve": DMResponse(
                    narrative="Water increased.",
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
        tick.pending_ops.enqueue_gm_resolve("water +10", tick=0)
        _run(tick.step_async())

        events = event_log.get_events()
        gm_events = [e for e in events if e.type == "gm_resolve"]
        assert len(gm_events) == 1
        assert gm_events[0].scope == "admin"
        assert gm_events[0].source == "gm"

    def test_gm_resolve_prompt_mode(self) -> None:
        """DM receives gm_resolve prompt mode."""
        dm = MockDMProvider()
        tick, store, event_log = _make_engine(dm)
        tick.pending_ops.enqueue_gm_resolve("test command", tick=0)
        _run(tick.step_async())

        assert dm.last_context is not None
        assert dm.last_context.prompt_mode == "gm_resolve"
        assert dm.last_context.action.action_type == "gm_resolve"
        assert dm.last_context.action.params["command"] == "test command"

    def test_gm_resolve_with_target_entity(self) -> None:
        """Target entity populates target_history in DM context."""
        dm = MockDMProvider()
        tick, store, event_log = _make_engine(dm)
        tick.pending_ops.enqueue_gm_resolve("fix it", tick=0, target_entity_id="water")
        _run(tick.step_async())

        assert dm.last_context is not None
        # target_history is populated (may be empty string if no events)
        assert dm.last_context.action.params["command"] == "fix it"

    def test_no_dm_provider_skips_resolve(self) -> None:
        """Without DM provider, pending resolves are silently drained."""
        config = SceneConfig(
            scene=SceneMetaConfig(id="test", description="A test world"),
            entities=[],
            actions={},
        )
        store = StateStore()
        store.add(Entity(id="water", type="resource", _data={"quantity": 50}))
        event_log = EventLog()
        queue = ActionQueue()
        tick = TickEngine(config, store, event_log, queue)  # no dm_provider

        tick.pending_ops.enqueue_gm_resolve("water +100", tick=0)
        _run(tick.step_async())

        # No change — resolve was skipped
        assert store.get("water").get("quantity") == 50

    def test_multiple_resolves_sequential(self) -> None:
        """Multiple GM resolves in same tick execute sequentially."""
        call_order: list[str] = []

        class OrderTrackingDM:
            async def judge(self, context: DMContext) -> DMResponse:
                cmd = context.action.params["command"]
                call_order.append(cmd)
                if cmd == "first":
                    return DMResponse(
                        narrative="First done.",
                        effects=[
                            EffectConfig(
                                operator="set",
                                target="water.quantity",
                                value=200,
                            ),
                        ],
                    )
                return DMResponse(
                    narrative="Second done.",
                    effects=[
                        EffectConfig(
                            operator="increment",
                            target="water.quantity",
                            value=50,
                        ),
                    ],
                )

        from worldseed.protocol.dm import DMContext

        dm = OrderTrackingDM()
        config = SceneConfig(
            scene=SceneMetaConfig(id="test", description="test"),
            entities=[],
            actions={},
        )
        store = StateStore()
        store.add(Entity(id="water", type="resource", _data={"quantity": 50}))
        event_log = EventLog()
        queue = ActionQueue()
        tick = TickEngine(config, store, event_log, queue, dm_provider=dm)  # type: ignore[arg-type]

        tick.pending_ops.enqueue_gm_resolve("first", tick=0)
        tick.pending_ops.enqueue_gm_resolve("second", tick=0)
        _run(tick.step_async())

        assert call_order == ["first", "second"]
        # first sets to 200, second increments by 50
        assert store.get("water").get("quantity") == 250
