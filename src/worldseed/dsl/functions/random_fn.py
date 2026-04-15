"""DSL function: random(min, max)."""

from __future__ import annotations

import random
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from worldseed.engine.state_store import StateStore

from worldseed.dsl.functions._registry import register_function
from worldseed.dsl.functions.helpers import split_args


def _call_random(
    args_str: str,
    store: StateStore,
    ctx: dict[str, Any],
) -> int:
    """random(min, max) → random integer in [min, max] inclusive."""
    from worldseed.dsl.path_resolver import resolve

    parts = split_args(args_str)
    if len(parts) < 2:
        return 0
    min_val = resolve(parts[0].strip(), store, ctx)
    max_val = resolve(parts[1].strip(), store, ctx)
    try:
        return random.randint(int(min_val), int(max_val))
    except (ValueError, TypeError):
        return 0


register_function("random", _call_random)
