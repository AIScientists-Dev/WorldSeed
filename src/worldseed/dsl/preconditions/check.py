"""Precondition operator: check (comparison)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from worldseed.engine.state_store import StateStore

from worldseed.dsl.path_resolver import resolve
from worldseed.dsl.preconditions._registry import register_precondition
from worldseed.models.config_schema import PreconditionConfig


def _safe_compare(left: Any, right: Any, op: str) -> bool:
    """Numeric comparison that returns False on None/type errors."""
    if left is None or right is None:
        return False
    try:
        lf = float(left)
        rf = float(right)
    except (ValueError, TypeError):
        return False
    match op:
        case ">":
            return lf > rf
        case "<":
            return lf < rf
        case ">=":
            return lf >= rf
        case "<=":
            return lf <= rf
        case _:
            return False


def _eval_check(
    p: PreconditionConfig,
    store: StateStore,
    ctx: dict[str, Any],
) -> bool:
    """Evaluate check: left op right."""
    left_val = resolve(p.left, store, ctx) if p.left is not None else None
    right_val = resolve(p.right, store, ctx) if p.right is not None else None

    match p.op:
        case "==":
            return left_val == right_val
        case "!=":
            return left_val != right_val
        case ">":
            return _safe_compare(left_val, right_val, ">")
        case "<":
            return _safe_compare(left_val, right_val, "<")
        case ">=":
            return _safe_compare(left_val, right_val, ">=")
        case "<=":
            return _safe_compare(left_val, right_val, "<=")
        case "in":
            if not isinstance(right_val, list):
                return False
            return left_val in right_val
        case "contains":
            if not isinstance(left_val, list):
                return False
            return right_val in left_val
        case _:
            msg = f"Unknown comparison op: {p.op}"
            raise ValueError(msg)


register_precondition("check", _eval_check)
