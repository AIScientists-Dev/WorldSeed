"""DSL effect executor — registry-based dispatcher.

To add a new effect operator:
1. Create a handler function with signature:
   def _exec_foo(effect, store, event_log, ctx, tick) -> None
2. Call register_effect("name", handler) at module level
That's it. No other files need changes.

ALL handlers use the same signature: (effect, store, event_log, ctx, tick).
Handlers that don't need all args simply ignore them.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from worldseed.engine.state_store import StateStore

import worldseed.dsl.effects.entity_ops  # noqa: F401
import worldseed.dsl.effects.event_ops  # noqa: F401
import worldseed.dsl.effects.for_each_ops  # noqa: F401
import worldseed.dsl.effects.list_ops  # noqa: F401
import worldseed.dsl.effects.relationship_ops  # noqa: F401
import worldseed.dsl.effects.rotate_ops  # noqa: F401
import worldseed.dsl.effects.state_ops  # noqa: F401
from worldseed.dsl.effects._helpers import parse_target  # noqa: F401
from worldseed.dsl.effects._registry import (
    get_all_effect_operators,
    get_effect_handler,
    register_effect,
)
from worldseed.engine.event_log import EventLog
from worldseed.models.config_schema import EffectConfig


def execute(
    effect: EffectConfig,
    store: StateStore,
    event_log: EventLog,
    ctx: dict[str, Any],
    tick: int,
) -> None:
    """Execute a DSL effect operator via registry lookup.

    All handlers receive the same args: (effect, store, event_log, ctx, tick).
    No special-casing per operator.

    If the effect has a ``when`` clause (a PreconditionConfig), the effect
    is skipped when the condition evaluates to false.
    """
    if effect.when is not None:
        from worldseed.dsl.preconditions import evaluate as eval_pre

        if not eval_pre(effect.when, store, ctx):
            return

    handler = get_effect_handler(effect.operator)
    if handler is None:
        msg = f"Unknown effect operator: {effect.operator}"
        raise ValueError(msg)
    handler(effect, store, event_log, ctx, tick)


__all__ = [
    "execute",
    "get_all_effect_operators",
    "get_effect_handler",
    "parse_target",
    "register_effect",
]
