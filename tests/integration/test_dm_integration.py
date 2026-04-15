"""Tests for DM integration with RulesEngine — diverse schemas."""

from __future__ import annotations

import asyncio
from typing import Any

from worldseed.dm.providers.mock import (
    FailingMockDMProvider,
    MockDMProvider,
)
from worldseed.engine.action_queue import ActionQueue
from worldseed.engine.event_log import EventLog
from worldseed.engine.inbox import InboxManager
from worldseed.engine.state_store import StateStore
from worldseed.engine.tick import TickEngine
from worldseed.models import ActionSubmission, Entity
from worldseed.models.config_schema import (
    ActionConfig,
    DMConfig,
    EffectConfig,
    SceneConfig,
    SceneMetaConfig,
)
from worldseed.protocol.dm import DMResponse


def _run(coro: Any) -> Any:
    return asyncio.run(coro)


def _bunker_engine(
    dm: MockDMProvider | FailingMockDMProvider,
) -> tuple[TickEngine, StateStore, EventLog, ActionQueue, InboxManager]:
    config = SceneConfig(
        scene=SceneMetaConfig(id="bunker", description="A doomsday bunker"),
        entities=[],
        actions={
            "observe": ActionConfig(
                description="Look closely",
                effects=[],
                dm=DMConfig(
                    hint="Judge based on physical plausibility",
                    allowed_ops=["set", "increment", "decrement", "emit_event"],
                    max_effects=5,
                ),
            ),
            "move": ActionConfig(
                description="Move somewhere",
                effects=[],
            ),
        },
    )
    store = StateStore()
    store.add(
        Entity(
            id="old_chen",
            type="agent",
            _data={"location": "storage", "hp": 100},
        )
    )
    store.add(
        Entity(
            id="food",
            type="resource",
            _data={"quantity": 20},
        )
    )
    event_log = EventLog()
    queue = ActionQueue()
    inbox_manager = InboxManager()
    tick = TickEngine(
        config,
        store,
        event_log,
        queue,
        inbox_manager=inbox_manager,
        dm_provider=dm,
    )
    return tick, store, event_log, queue, inbox_manager


def _bakery_engine(
    dm: MockDMProvider,
) -> tuple[TickEngine, StateStore, EventLog, ActionQueue, InboxManager]:
    """Bakery scene — no 'location', uses 'skill'."""
    config = SceneConfig(
        scene=SceneMetaConfig(id="bakery", description="A small bakery"),
        entities=[],
        actions={
            "attempt": ActionConfig(
                description="Try anything",
                effects=[],
                dm=DMConfig(hint="Judge baking outcomes"),
            ),
        },
    )
    store = StateStore()
    store.add(
        Entity(
            id="baker",
            type="agent",
            _data={"skill": 80},
        )
    )
    store.add(
        Entity(
            id="flour",
            type="ingredient",
            _data={"amount": 10},
        )
    )
    event_log = EventLog()
    queue = ActionQueue()
    inbox_manager = InboxManager()
    tick = TickEngine(
        config,
        store,
        event_log,
        queue,
        inbox_manager=inbox_manager,
        dm_provider=dm,
    )
    return tick, store, event_log, queue, inbox_manager


def _forum_engine(
    dm: MockDMProvider,
) -> tuple[TickEngine, StateStore, EventLog, ActionQueue, InboxManager]:
    """Forum scene — no spatial concept."""
    config = SceneConfig(
        scene=SceneMetaConfig(
            id="forum",
            description="An internet forum",
        ),
        entities=[],
        actions={
            "attempt": ActionConfig(
                description="Try anything",
                effects=[],
                dm=DMConfig(hint="Judge forum moderation outcomes"),
            ),
        },
    )
    store = StateStore()
    store.add(
        Entity(
            id="moderator",
            type="agent",
            _data={"reputation": 500},
        )
    )
    event_log = EventLog()
    queue = ActionQueue()
    inbox_manager = InboxManager()
    tick = TickEngine(
        config,
        store,
        event_log,
        queue,
        inbox_manager=inbox_manager,
        dm_provider=dm,
    )
    return tick, store, event_log, queue, inbox_manager


class TestDMResolveBunker:
    def test_observe_applies_effects(self) -> None:
        dm = MockDMProvider(
            responses={
                "observe": DMResponse(
                    narrative="The food is running low.",
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="old_chen.hp",
                            value=90,
                        )
                    ],
                )
            }
        )
        tick, store, event_log, queue, inbox_manager = _bunker_engine(dm)
        queue.submit(
            ActionSubmission(
                agent_id="old_chen",
                action_type="observe",
                params={"target": "food"},
            )
        )

        async def _test() -> None:
            await tick.step_async()

        _run(_test())

        assert store.get("old_chen") is not None
        assert store.get("old_chen")["hp"] == 90  # type: ignore[union-attr]
        assert dm.call_count == 1

    def test_narrative_becomes_whisper(self) -> None:
        dm = MockDMProvider(
            responses={
                "observe": DMResponse(
                    narrative="You see something alarming.",
                )
            }
        )
        tick, store, event_log, queue, inbox_manager = _bunker_engine(dm)
        queue.submit(
            ActionSubmission(
                agent_id="old_chen",
                action_type="observe",
                params={"target": "food"},
            )
        )
        _run(tick.step_async())

        inbox = inbox_manager.get_or_create("old_chen")
        data = inbox.read()
        dm_msgs = [m for m in data["whispers"] if m.type == "dm_narrative"]
        assert len(dm_msgs) == 1
        assert "alarming" in dm_msgs[0].detail
        assert dm_msgs[0].source == "dm"


class TestDMResolveBakery:
    def test_attempt_in_bakery(self) -> None:
        dm = MockDMProvider(
            responses={
                "attempt": DMResponse(
                    narrative="Baker invents a new recipe!",
                    effects=[
                        EffectConfig(
                            operator="increment",
                            target="baker.skill",
                            by=5,
                        )
                    ],
                )
            }
        )
        tick, store, _, queue, _ = _bakery_engine(dm)
        queue.submit(
            ActionSubmission(
                agent_id="baker",
                action_type="attempt",
                params={"description": "invent recipe"},
            )
        )
        _run(tick.step_async())

        assert store.get("baker") is not None
        assert store.get("baker")["skill"] == 85  # type: ignore[union-attr]

    def test_dm_context_has_world_state(self) -> None:
        dm = MockDMProvider()
        tick, _, _, queue, _ = _bakery_engine(dm)
        queue.submit(
            ActionSubmission(
                agent_id="baker",
                action_type="attempt",
                params={},
            )
        )
        _run(tick.step_async())

        assert dm.last_context is not None
        # New format: world_state is plain text containing all entities
        assert "baker (agent):" in dm.last_context.world_state
        assert "skill: 80" in dm.last_context.world_state
        assert "flour (ingredient):" in dm.last_context.world_state


class TestDMResolveForum:
    def test_attempt_in_forum(self) -> None:
        dm = MockDMProvider(
            responses={
                "attempt": DMResponse(
                    narrative="The post is removed.",
                    effects=[
                        EffectConfig(
                            operator="set",
                            target=("moderator.reputation"),
                            value=510,
                        )
                    ],
                )
            }
        )
        tick, store, _, queue, _ = _forum_engine(dm)
        queue.submit(
            ActionSubmission(
                agent_id="moderator",
                action_type="attempt",
                params={"description": "ban spammer"},
            )
        )
        _run(tick.step_async())

        assert store.get("moderator") is not None
        assert store.get("moderator")["reputation"] == 510  # type: ignore[union-attr]


class TestDMValidation:
    def test_invalid_effect_rejected(self) -> None:
        dm = MockDMProvider(
            responses={
                "observe": DMResponse(
                    narrative="Something happens.",
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="phantom.x",
                            value=1,
                        )
                    ],
                )
            }
        )
        tick, store, event_log, queue, inbox_manager = _bunker_engine(dm)
        queue.submit(
            ActionSubmission(
                agent_id="old_chen",
                action_type="observe",
                params={"target": "food"},
            )
        )
        _run(tick.step_async())

        # Effect targeting nonexistent "phantom" is rejected
        assert store.get("phantom") is None
        # DM was called (may retry on validation failure)
        assert dm.call_count >= 1
        # Fallback narrative delivered as whisper
        inbox = inbox_manager.get_or_create("old_chen")
        data = inbox.read()
        dm_msgs = [m for m in data["whispers"] if m.type == "dm_narrative"]
        assert len(dm_msgs) == 1
        assert dm_msgs[0].detail  # narrative preserved even when effects rejected

    def test_batch_with_invalid_effect_rejected(self) -> None:
        """If any DM effect targets a nonexistent entity, entire batch is rejected."""
        dm = MockDMProvider(
            responses={
                "observe": DMResponse(
                    narrative="Mixed results.",
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="old_chen.hp",
                            value=50,
                        ),
                        EffectConfig(
                            operator="set",
                            target="ghost.x",
                            value=1,
                        ),
                        EffectConfig(
                            operator="set",
                            target="food.quantity",
                            value=15,
                        ),
                    ],
                )
            }
        )
        tick, store, event_log, queue, inbox_manager = _bunker_engine(dm)
        queue.submit(
            ActionSubmission(
                agent_id="old_chen",
                action_type="observe",
                params={"target": "food"},
            )
        )
        _run(tick.step_async())

        # All-or-nothing: entire batch rejected because "ghost" doesn't exist
        assert store.get("old_chen")["hp"] == 100  # type: ignore[union-attr]
        assert store.get("food")["quantity"] == 20  # type: ignore[union-attr]
        assert store.get("ghost") is None
        # Fallback narrative delivered as whisper
        inbox = inbox_manager.get_or_create("old_chen")
        data = inbox.read()
        dm_msgs = [m for m in data["whispers"] if m.type == "dm_narrative"]
        assert len(dm_msgs) == 1
        assert dm_msgs[0].detail  # narrative preserved even when effects rejected


class TestDMRetry:
    def test_retry_on_failure(self) -> None:
        dm = FailingMockDMProvider(
            fail_count=1,
            success_response=DMResponse(
                narrative="Recovered.",
                effects=[
                    EffectConfig(
                        operator="set",
                        target="old_chen.hp",
                        value=75,
                    )
                ],
            ),
        )
        tick, store, _, queue, _ = _bunker_engine(dm)
        queue.submit(
            ActionSubmission(
                agent_id="old_chen",
                action_type="observe",
                params={"target": "food"},
            )
        )
        _run(tick.step_async())

        assert store.get("old_chen")["hp"] == 75  # type: ignore[union-attr]
        assert dm.call_count == 2  # 1 fail + 1 success

    def test_retry_exhausted_fallback(self) -> None:
        dm = FailingMockDMProvider(
            fail_count=5,
            success_response=DMResponse(narrative="ok"),
        )
        tick, store, event_log, queue, inbox_manager = _bunker_engine(dm)
        queue.submit(
            ActionSubmission(
                agent_id="old_chen",
                action_type="observe",
                params={"target": "food"},
            )
        )
        _run(tick.step_async())

        # State unchanged (fallback = narrative-only)
        assert store.get("old_chen")["hp"] == 100  # type: ignore[union-attr]
        # Fallback narrative delivered as whisper
        inbox = inbox_manager.get_or_create("old_chen")
        data = inbox.read()
        dm_msgs = [m for m in data["whispers"] if m.type == "dm_narrative"]
        assert len(dm_msgs) == 1
        assert dm_msgs[0].detail  # narrative preserved even when effects rejected


class TestDMAllowedOps:
    def test_allowed_ops_rejection(self) -> None:
        """DM effects with operators not in allowed_ops are rejected."""
        dm = MockDMProvider(
            responses={
                "observe": DMResponse(
                    narrative="Creating something new.",
                    effects=[
                        EffectConfig(
                            operator="create_entity",
                            id="new_thing",
                            type="object",
                            properties={"x": 1},
                        )
                    ],
                )
            }
        )
        # Default allowed_ops: set, increment, decrement, emit_event
        # create_entity is NOT in there
        tick, store, event_log, queue, inbox_manager = _bunker_engine(dm)
        queue.submit(
            ActionSubmission(
                agent_id="old_chen",
                action_type="observe",
                params={"target": "food"},
            )
        )
        _run(tick.step_async())

        # create_entity not allowed — batch rejected
        assert store.get("new_thing") is None
        # Fallback narrative delivered as whisper
        inbox = inbox_manager.get_or_create("old_chen")
        data = inbox.read()
        dm_msgs = [m for m in data["whispers"] if m.type == "dm_narrative"]
        assert len(dm_msgs) == 1
        assert dm_msgs[0].detail  # narrative preserved even when effects rejected


class TestDMMaxEffects:
    def test_max_effects_rejection(self) -> None:
        """DM returning more effects than max_effects is rejected."""
        dm = MockDMProvider(
            responses={
                "attempt": DMResponse(
                    narrative="So much happened!",
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="moderator.reputation",
                            value=i * 100,
                        )
                        for i in range(10)
                    ],
                )
            }
        )
        # Default max_effects is 5
        tick, store, event_log, queue, inbox_manager = _forum_engine(dm)
        queue.submit(
            ActionSubmission(
                agent_id="moderator",
                action_type="attempt",
                params={"description": "do many things"},
            )
        )
        _run(tick.step_async())

        # Too many effects — batch rejected, state unchanged
        assert store.get("moderator")["reputation"] == 500  # type: ignore[union-attr]
        # Fallback narrative delivered as whisper
        inbox = inbox_manager.get_or_create("moderator")
        data = inbox.read()
        dm_msgs = [m for m in data["whispers"] if m.type == "dm_narrative"]
        assert len(dm_msgs) == 1
        assert dm_msgs[0].detail  # narrative preserved even when effects rejected


class TestDMAtomicRollback:
    def test_atomic_rollback(self) -> None:
        """If one effect in batch is invalid, none are applied."""
        dm = MockDMProvider(
            responses={
                "observe": DMResponse(
                    narrative="Something explosive.",
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="old_chen.hp",
                            value=1,
                        ),
                        # This will fail validation (nonexistent entity)
                        EffectConfig(
                            operator="set",
                            target="nonexistent.x",
                            value=99,
                        ),
                    ],
                )
            }
        )
        tick, store, event_log, queue, inbox_manager = _bunker_engine(dm)
        original_hp = store.get("old_chen")["hp"]  # type: ignore[union-attr]
        queue.submit(
            ActionSubmission(
                agent_id="old_chen",
                action_type="observe",
                params={"target": "food"},
            )
        )
        _run(tick.step_async())

        # Batch rejected atomically — hp unchanged
        assert store.get("old_chen")["hp"] == original_hp  # type: ignore[union-attr]
        # Fallback narrative delivered as whisper
        inbox = inbox_manager.get_or_create("old_chen")
        data = inbox.read()
        dm_msgs = [m for m in data["whispers"] if m.type == "dm_narrative"]
        assert len(dm_msgs) == 1
        assert dm_msgs[0].detail  # narrative preserved even when effects rejected


class TestDMNarrativeScope:
    def test_narrative_delivered_as_whisper(self) -> None:
        """DM narrative delivered as whisper to the acting agent."""
        dm = MockDMProvider(
            responses={
                "observe": DMResponse(
                    narrative="A loud bang.",
                )
            }
        )
        tick, store, event_log, queue, inbox_manager = _bunker_engine(dm)
        queue.submit(
            ActionSubmission(
                agent_id="old_chen",
                action_type="observe",
                params={"target": "food"},
            )
        )
        _run(tick.step_async())

        # DM narrative goes to actor's inbox as whisper, not broadcast event
        inbox = inbox_manager.get_or_create("old_chen")
        data = inbox.read()
        dm_msgs = [m for m in data["whispers"] if m.type == "dm_narrative"]
        assert len(dm_msgs) == 1
        assert "bang" in dm_msgs[0].detail
        # No dm_narrative events in event log
        dm_events = [e for e in event_log.get_events() if e.type == "dm_narrative"]
        assert len(dm_events) == 0


class TestDMBackwardCompat:
    def test_sync_no_dm_provider(self) -> None:
        """Sync process_action with dm: config but no provider — DM skipped."""
        config = SceneConfig(
            scene=SceneMetaConfig(id="t", description="t"),
            entities=[],
            actions={
                "observe": ActionConfig(
                    description="Look",
                    effects=[],
                    dm=DMConfig(hint="test"),
                ),
            },
        )
        store = StateStore()
        store.add(Entity(id="a", type="agent", _data={}))
        queue = ActionQueue()
        tick = TickEngine(
            config,
            store,
            EventLog(),
            queue,
        )
        queue.submit(ActionSubmission(agent_id="a", action_type="observe"))
        # Sync step — no DM provider, dm resolution not attempted
        results = tick.step()
        assert len(results) == 1
        assert results[0].success


class TestMechanicalEffectsBeforeDM:
    def test_effects_run_before_dm(self) -> None:
        """Mechanical effects execute before DM is called."""
        dm = MockDMProvider(
            responses={
                "inspect": DMResponse(
                    narrative="You notice something.",
                )
            }
        )
        config = SceneConfig(
            scene=SceneMetaConfig(id="t", description="t"),
            entities=[],
            actions={
                "inspect": ActionConfig(
                    description="Inspect and set flag",
                    effects=[
                        EffectConfig(
                            operator="set",
                            target="agent_a.inspected",
                            value=True,
                        )
                    ],
                    dm=DMConfig(hint="Judge the inspection."),
                ),
            },
        )
        store = StateStore()
        store.add(
            Entity(
                id="agent_a",
                type="agent",
                _data={"inspected": False},
            )
        )
        event_log = EventLog()
        queue = ActionQueue()
        inbox_manager = InboxManager()
        tick = TickEngine(
            config,
            store,
            event_log,
            queue,
            inbox_manager=inbox_manager,
            dm_provider=dm,
        )
        queue.submit(
            ActionSubmission(
                agent_id="agent_a",
                action_type="inspect",
            )
        )
        _run(tick.step_async())

        # Mechanical effect ran
        assert store.get("agent_a")["inspected"] is True  # type: ignore[union-attr]
        # DM was also called
        assert dm.call_count == 1
        inbox = inbox_manager.get_or_create("agent_a")
        data = inbox.read()
        dm_msgs = [m for m in data["whispers"] if m.type == "dm_narrative"]
        assert len(dm_msgs) == 1
