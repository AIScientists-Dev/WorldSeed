"""DSL function: length(entity.property) — returns length of list/dict/string."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from worldseed.engine.state_store import StateStore

from worldseed.dsl.functions._registry import register_function
from worldseed.dsl.functions.helpers import split_args


def _call_length(
    args_str: str,
    store: StateStore,
    ctx: dict[str, Any],
) -> int:
    """length(entity.property) → length of list, dict, or string. 0 for None."""
    from worldseed.dsl.path_resolver import resolve

    args = split_args(args_str)
    if not args:
        return 0

    val = resolve(args[0].strip(), store, ctx)
    if val is None:
        return 0
    if isinstance(val, (list, dict, str)):
        return len(val)
    return 0


register_function("length", _call_length)
