"""DSL functions: relationships_of, relationship_value."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from worldseed.engine.state_store import StateStore

from worldseed.dsl.functions._registry import register_function
from worldseed.dsl.functions.helpers import parse_kwargs, split_args
from worldseed.utils.nested import nested_get


def relationships_of(
    entity_id: str,
    rel_type: str,
    store: StateStore,
) -> list[str]:
    """Return target IDs from a relationship property."""
    entity = store.get(entity_id)
    if entity is None:
        return []

    prop = nested_get(entity.data, rel_type)
    if prop is None:
        return []
    if isinstance(prop, list):
        return [str(x) for x in prop]
    if isinstance(prop, dict):
        return list(prop.keys())
    return []


def relationship_value(
    entity_id: str,
    rel_type: str,
    target: str,
    store: StateStore,
) -> object:
    """Get a specific relationship target's value, or check membership."""
    entity = store.get(entity_id)
    if entity is None:
        return None

    prop = nested_get(entity.data, rel_type)
    if prop is None:
        return None
    if isinstance(prop, dict):
        return prop.get(target)
    if isinstance(prop, list):
        return target in prop
    return None


def _call_relationships_of(
    args_str: str,
    store: StateStore,
    ctx: dict[str, Any],
) -> list[str] | object:
    """Parse and call relationships_of(entity_path, type=X[, to=Y[, value]])."""
    from worldseed.dsl.path_resolver import resolve

    kw = parse_kwargs(args_str)
    first_arg = split_args(args_str)[0].strip() if args_str else ""
    rel_type = kw.get("type")
    if not first_arg or not rel_type:
        return []

    entity_id = resolve(first_arg, store, ctx)
    if not isinstance(entity_id, str):
        return []

    to_target = kw.get("to")

    if to_target is not None:
        resolved_to = resolve(to_target, store, ctx)
        if not isinstance(resolved_to, str):
            return []

        args = split_args(args_str)
        want_value = any(a.strip() == "value" for a in args)

        val = relationship_value(entity_id, rel_type, resolved_to, store)
        if want_value:
            return val
        if val is True or (val is not None and val is not False):
            return [resolved_to]
        return []

    return relationships_of(entity_id, rel_type, store)


register_function("relationships_of", _call_relationships_of)
