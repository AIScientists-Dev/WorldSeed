"""Prove the engine is scene-agnostic: a bakery, not a bunker."""

from __future__ import annotations

from worldseed.engine.event_log import EventLog
from worldseed.engine.rules_engine import RulesEngine
from worldseed.engine.state_store import StateStore
from worldseed.models import ActionSubmission, Entity
from worldseed.models.config_schema import (
    ActionConfig,
    EffectConfig,
    EventConfig,
    ParamConfig,
    PreconditionConfig,
    SceneConfig,
    SceneMetaConfig,
)


def _bakery_config() -> SceneConfig:
    """A bakery scene. No bunker, no survival, no combat."""
    return SceneConfig(
        scene=SceneMetaConfig(id="bakery", description="A small bakery"),
        entities=[],  # we'll populate manually
        actions={
            "bake": ActionConfig(
                description="Bake bread using flour",
                params=[
                    ParamConfig(name="item", type="string", required=True),
                ],
                preconditions=[
                    PreconditionConfig(
                        operator="check",
                        left="flour.amount",
                        op=">=",
                        right=1,
                    ),
                ],
                effects=[
                    EffectConfig(
                        operator="decrement",
                        target="flour.amount",
                        by=1,
                    ),
                    EffectConfig(
                        operator="increment",
                        target="bread.count",
                        by=1,
                    ),
                ],
                events=[
                    EventConfig(
                        type="bake",
                        detail="$agent baked $item",
                        ttl=2,
                        scope="same_location",
                    ),
                ],
            ),
            "sell": ActionConfig(
                description="Sell bread to a customer",
                params=[],
                preconditions=[
                    PreconditionConfig(
                        operator="check",
                        left="bread.count",
                        op=">",
                        right=0,
                    ),
                ],
                effects=[
                    EffectConfig(
                        operator="decrement",
                        target="bread.count",
                        by=1,
                    ),
                    EffectConfig(
                        operator="increment",
                        target="$agent.coins",
                        by=5,
                    ),
                ],
                events=[
                    EventConfig(
                        type="sell",
                        detail="$agent sold bread",
                        ttl=1,
                        scope="global",
                    ),
                ],
            ),
        },
    )


def test_bakery_scene() -> None:
    """Completely different scene: bake bread, sell bread."""
    config = _bakery_config()
    store = StateStore()
    event_log = EventLog()

    # Create bakery entities — none of these exist in bunker
    store.add(
        Entity(
            id="kitchen",
            type="space",
            _data={"description": "The kitchen"},
        )
    )
    store.add(
        Entity(
            id="baker",
            type="agent",
            _data={"location": "kitchen", "coins": 0},
        )
    )
    store.add(
        Entity(
            id="flour",
            type="resource",
            _data={"amount": 10, "location": "kitchen"},
        )
    )
    store.add(
        Entity(
            id="bread",
            type="resource",
            _data={"count": 0, "location": "kitchen"},
        )
    )

    engine = RulesEngine(config, store, event_log)

    # Bake bread
    result = engine.process_action(
        ActionSubmission(
            agent_id="baker",
            action_type="bake",
            params={"item": "sourdough"},
        ),
        tick=1,
    )
    assert result.success
    assert store.get("flour")["amount"] == 9  # type: ignore[union-attr]
    assert store.get("bread")["count"] == 1  # type: ignore[union-attr]

    # Event says "baker baked sourdough"
    events = event_log.get_events()
    assert events[0].detail == "baker baked sourdough"
    assert events[0].type == "bake"

    # Sell bread
    result = engine.process_action(
        ActionSubmission(
            agent_id="baker",
            action_type="sell",
        ),
        tick=2,
    )
    assert result.success
    assert store.get("bread")["count"] == 0  # type: ignore[union-attr]
    assert store.get("baker")["coins"] == 5  # type: ignore[union-attr]

    # Can't sell when no bread left
    result = engine.process_action(
        ActionSubmission(
            agent_id="baker",
            action_type="sell",
        ),
        tick=3,
    )
    assert not result.success
    assert result.reason  # descriptive error with resolved values

    # Verify final state
    assert store.get("baker")["coins"] == 5  # type: ignore[union-attr]
