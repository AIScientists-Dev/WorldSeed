"""Precondition operators: exists, not, all, any."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from worldseed.engine.state_store import StateStore

from worldseed.dsl.path_resolver import resolve
from worldseed.dsl.preconditions._registry import register_precondition
from worldseed.models.config_schema import PreconditionConfig


def _eval_exists(
    p: PreconditionConfig,
    store: StateStore,
    ctx: dict[str, Any],
) -> bool:
    """Check if expression resolves to a truthy value."""
    if p.expression is None:
        return False
    result = resolve(p.expression, store, ctx)
    if result is None:
        return False
    if isinstance(result, (list, str)) and len(result) == 0:
        return False
    return bool(result)


def _eval_not(
    p: PreconditionConfig,
    store: StateStore,
    ctx: dict[str, Any],
) -> bool:
    """Negate a nested condition."""
    # Import here to avoid circular — evaluate is in __init__
    from worldseed.dsl.preconditions import evaluate

    if p.condition is not None:
        return not evaluate(p.condition, store, ctx)
    if p.conditions and len(p.conditions) == 1:
        return not evaluate(p.conditions[0], store, ctx)
    return False


def _eval_all(
    p: PreconditionConfig,
    store: StateStore,
    ctx: dict[str, Any],
) -> bool:
    """All conditions must be true (AND). Empty = True."""
    from worldseed.dsl.preconditions import evaluate

    if not p.conditions:
        return True
    return all(evaluate(c, store, ctx) for c in p.conditions)


def _eval_any(
    p: PreconditionConfig,
    store: StateStore,
    ctx: dict[str, Any],
) -> bool:
    """At least one condition must be true (OR). Empty = False."""
    from worldseed.dsl.preconditions import evaluate

    if not p.conditions:
        return False
    return any(evaluate(c, store, ctx) for c in p.conditions)


register_precondition("exists", _eval_exists)
register_precondition("not", _eval_not)
register_precondition("all", _eval_all)
register_precondition("any", _eval_any)
