"""DSL precondition evaluator — registry-based dispatcher.

To add a new precondition operator:
1. Create a handler function in an appropriate .py file
2. Call register_precondition("name", handler) at module level
That's it.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from worldseed.engine.state_store import StateStore

# Import operator modules to trigger registration
import worldseed.dsl.preconditions.check  # noqa: F401
import worldseed.dsl.preconditions.logic  # noqa: F401
from worldseed.dsl.preconditions._registry import (
    get_all_precondition_operators,
    get_precondition_handler,
    register_precondition,
)

# Re-export _safe_compare for backward compat (sanity_runner imports it)
from worldseed.dsl.preconditions.check import _safe_compare  # noqa: F401
from worldseed.models.config_schema import PreconditionConfig


def evaluate(
    precondition: PreconditionConfig,
    store: StateStore,
    ctx: dict[str, Any],
) -> bool:
    """Evaluate a precondition, dispatching by operator."""
    handler = get_precondition_handler(precondition.operator)
    if handler is None:
        msg = f"Unknown precondition: {precondition.operator}"
        raise ValueError(msg)
    return handler(precondition, store, ctx)


__all__ = [
    "evaluate",
    "get_all_precondition_operators",
    "register_precondition",
    "_safe_compare",
]
