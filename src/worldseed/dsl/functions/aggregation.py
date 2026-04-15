"""DSL functions: count, sum, max_by with compound WHERE support."""

from __future__ import annotations

from collections.abc import Sequence
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from worldseed.engine.state_store import StateStore

from worldseed.dsl.functions._registry import register_function
from worldseed.dsl.functions.helpers import parse_kwargs, walk_entity_path


def _filter_entities(
    entities: Sequence[object],
    where: str,
    store: Any | None = None,
    ctx: dict[str, Any] | None = None,
) -> list[object]:
    """Filter entities by a WHERE clause. Pre-resolves RHS values once."""
    parsed = _parse_conditions(where, store, ctx)
    return [e for e in entities if all(_matches_parsed(e, left, op, rhs) for left, op, rhs in parsed)]


def _exclude_system(entities: Sequence[Any]) -> list[Any]:
    """Exclude system entities (e.g. narrator) from DSL queries."""
    return [e for e in entities if not getattr(e, "_data", {}).get("_system")]


def count(
    store: StateStore,
    entity_type: str,
    where: str | None = None,
    ctx: dict[str, Any] | None = None,
) -> int:
    """Count entities matching type and optional where condition."""
    entities = _exclude_system(store.query_by_type(entity_type))
    if where is None:
        return len(entities)
    return len(_filter_entities(entities, where, store, ctx))


def sum_property(
    store: StateStore,
    entity_type: str,
    prop: str,
    where: str | None = None,
    ctx: dict[str, Any] | None = None,
) -> float:
    """Sum a property across entities matching type and optional where."""
    matched: Sequence[object] = _exclude_system(store.query_by_type(entity_type))
    if where is not None:
        matched = _filter_entities(matched, where, store, ctx)
    total = 0.0
    for e in matched:
        val = walk_entity_path(e, prop)
        if val is not None:
            try:
                total += float(val)  # type: ignore[arg-type]
            except (ValueError, TypeError):
                pass
    return total


def _is_dsl_expression(val: str) -> bool:
    """Check if a string looks like a DSL expression (not a bare literal).

    Requires $ prefix (param/path), ( (function call), or dotted path
    where the first segment looks like an identifier (not a version number).
    """
    if val.startswith("$") or "(" in val:
        return True
    if "." in val:
        first = val.split(".", 1)[0]
        return first.isidentifier()
    return False


def _resolve_rhs(
    right_val: str,
    store: Any | None,
    ctx: dict[str, Any] | None,
) -> str:
    """Resolve a right-hand-side value once, outside the entity loop."""
    if store is not None and _is_dsl_expression(right_val):
        from worldseed.dsl.path_resolver import resolve

        resolved = resolve(right_val, store, ctx or {})
        return str(resolved) if resolved is not None else right_val
    return right_val


def _parse_conditions(
    where: str,
    store: Any | None = None,
    ctx: dict[str, Any] | None = None,
) -> list[tuple[str, str, str]]:
    """Parse WHERE string into (left_path, op, resolved_rhs) tuples.

    RHS values are resolved once here, not per-entity.
    """
    parsed: list[tuple[str, str, str]] = []
    for cond in where.split(" AND "):
        cond = cond.strip()
        # Try spaced operators first (unambiguous), then bare operators as fallback.
        for op_str in (" != ", " == ", "!=", "=="):
            if op_str in cond:
                left_path, right_val = cond.split(op_str, 1)
                left_path = left_path.strip()
                right_val = right_val.strip().strip("'\"")
                resolved = _resolve_rhs(right_val, store, ctx)
                parsed.append((left_path, op_str.strip(), resolved))
                break
    return parsed


def _matches_where(
    entity: object,
    where: str,
    store: Any | None = None,
    ctx: dict[str, Any] | None = None,
) -> bool:
    """Evaluate a where condition against an entity.

    Supports compound conditions with AND:
        "location == town AND infected == true"

    If store is provided, right-hand values are resolved via path_resolver.
    """
    parsed = _parse_conditions(where, store, ctx)
    return all(_matches_parsed(entity, left, op, rhs) for left, op, rhs in parsed)


def _matches_parsed(entity: object, left_path: str, op: str, resolved_rhs: str) -> bool:
    """Evaluate a single parsed condition against an entity."""
    val = walk_entity_path(entity, left_path)
    val_str = str(val).lower() if val is not None else ""
    right_str = resolved_rhs.lower()

    if op == "==":
        return val_str == right_str if val is not None else False
    return val_str != right_str if val is not None else True


def _call_count(
    args_str: str,
    store: StateStore,
    ctx: dict[str, Any],
) -> int:
    """Parse and call count(type=X, where=...)."""
    kw = parse_kwargs(args_str)
    entity_type = kw.get("type")
    if entity_type is None:
        return 0
    return count(store, entity_type, kw.get("where"), ctx)


def _call_sum(
    args_str: str,
    store: StateStore,
    ctx: dict[str, Any],
) -> float:
    """sum(type=X, property=Y, where=...) → total across matching entities."""
    kw = parse_kwargs(args_str)
    entity_type = kw.get("type")
    prop = kw.get("property")
    if entity_type is None or prop is None:
        return 0.0
    return sum_property(store, entity_type, prop, kw.get("where"), ctx)


def _call_max_by(
    args_str: str,
    store: StateStore,
    ctx: dict[str, Any],
) -> str:
    """max_by(type=X, property=Y, where=...) → entity ID with highest Y.

    Returns "" if no matching entities or all values are None.
    Returns "" if there's a tie for the maximum (no unique winner).
    """
    kw = parse_kwargs(args_str)
    entity_type = kw.get("type")
    prop = kw.get("property")
    if entity_type is None or prop is None:
        return ""

    matched: Sequence[object] = _exclude_system(store.query_by_type(entity_type))
    where = kw.get("where")
    if where is not None:
        matched = _filter_entities(matched, where, store, ctx)

    if not matched:
        return ""

    best_id = ""
    best_val: float | None = None
    tie = False

    for e in matched:
        val = walk_entity_path(e, prop)
        if val is None:
            continue
        try:
            num = float(val)  # type: ignore[arg-type]
        except (ValueError, TypeError):
            continue

        if best_val is None or num > best_val:
            best_val = num
            best_id = getattr(e, "id", "")
            tie = False
        elif num == best_val:
            tie = True

    return "" if tie else best_id


register_function("count", _call_count)
register_function("sum", _call_sum)
register_function("max_by", _call_max_by)
