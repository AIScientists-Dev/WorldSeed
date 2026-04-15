"""DSL path resolver — resolves expressions to values."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from worldseed.engine.state_store import StateStore

from worldseed.dsl.functions._registry import get_function_handler
from worldseed.dsl.functions.helpers import try_numeric, walk_entity_path

log = structlog.get_logger()

_PARAM_RE = re.compile(r"\$(\w+)")

# Arithmetic operators in precedence order (lowest first = split first).
# Two-char operators must come before single-char to avoid partial matches.
_ARITH_PRECEDENCE: list[list[str]] = [
    ["+", "-"],  # additive (lowest precedence, split first)
    ["*", "//", "%"],  # multiplicative (higher precedence)
]


def lookup_param(name: str, ctx: dict[str, Any]) -> Any:
    """Resolve a single $param name to its value.

    This is the SINGLE SOURCE OF TRUTH for $param resolution.
    All other code should call this instead of reimplementing.

    Handles: $agent, $tick, bare "agent", and action_params.
    """
    if name == "agent":
        return ctx.get("agent_id")
    if name == "tick":
        return ctx.get("tick")
    if name == "seq":
        return ctx.get("seq")
    return ctx.get("action_params", {}).get(name)


def resolve_params(expr: str, ctx: dict[str, Any]) -> str:
    """Replace ALL $param references in a string before further processing.

    Handles:
      "$agent"         → agent_id (full segment)
      "$resource"      → action_params["resource"] (full segment)
      "votes_$choice"  → "votes_agree" (embedded in segment)

    This runs BEFORE path splitting, so middle-segment $ works:
      "$agent.inventory.$resource"
      → "old_chen.inventory.food"
    """

    def replacer(m: re.Match[str]) -> str:
        val = lookup_param(m.group(1), ctx)
        return str(val) if val is not None else m.group(0)

    return _PARAM_RE.sub(replacer, expr)


def resolve(
    expr: str | int | float,
    store: StateStore,
    ctx: dict[str, Any],
) -> Any:
    """Resolve a DSL expression to a value.

    Handles:
    - Numeric/non-string pass-through
    - "$agent", "$to", "$amount" (param references)
    - "$agent.location" (property paths)
    - "food_supply.quantity" (entity paths)
    - "relationships_of(...)" (function calls)
    - "2 + 3 * count(type=agent)" (arithmetic with +, -, *, //, %)
    - "random(1, 6)" (DSL functions via registry)
    """
    if not isinstance(expr, str):
        return expr

    expr = expr.strip()

    # Try numeric literal
    num = try_numeric(expr)
    if num is not None:
        return num

    # Arithmetic: "A + B", "A * B", "A % B", etc.
    if _is_arithmetic(expr):
        return _resolve_arithmetic(expr, store, ctx)

    # Function call: "relationships_of(...)", "count(...)", "random(...)"
    if "(" in expr and not expr.startswith("$"):
        return _resolve_function(expr, store, ctx)

    # Property path: "$agent.properties.location" or
    # "food_supply.properties.quantity"
    if "." in expr:
        return _resolve_path(expr, store, ctx)

    # Simple reference: "$agent", "$to", "$amount"
    if expr.startswith("$"):
        return lookup_param(expr.lstrip("$"), ctx)

    # Bare string — could be an entity id or a literal
    return expr


def _resolve_path(
    expr: str,
    store: StateStore,
    ctx: dict[str, Any],
) -> Any:
    """Resolve a dot path like $agent.location."""
    resolved = resolve_params(expr, ctx)

    parts = resolved.split(".")
    first = parts[0]

    if first == "agent":
        entity_id = str(ctx.get("agent_id", ""))
    elif first == "entity":
        # Consequence scanner puts entity in action_params.entity
        entity_id = str(ctx.get("action_params", {}).get("entity", ctx.get("entity_id", "")))
    else:
        entity_id = first

    if not entity_id:
        return None

    entity = store.get(entity_id)
    if entity is None:
        return None

    remaining = ".".join(parts[1:])
    if not remaining:
        return entity
    return walk_entity_path(entity, remaining)


def _resolve_function(
    expr: str,
    store: StateStore,
    ctx: dict[str, Any],
) -> Any:
    """Resolve a function call via the function registry."""
    match = re.match(r"(\w+)\((.+)\)$", expr, re.DOTALL)
    if not match:
        return expr
    func_name = match.group(1)
    args_str = match.group(2)

    handler = get_function_handler(func_name)
    if handler is not None:
        return handler(args_str, store, ctx)
    return expr


def _is_arithmetic(expr: str) -> bool:
    """Check if expression contains a top-level arithmetic operator.

    Scans for +, -, *, //, % outside of function parens.
    Handles: // as two-char op, unary minus (leading -) is NOT arithmetic.
    """
    depth = 0
    i = 0
    length = len(expr)
    while i < length:
        char = expr[i]
        if char == "(":
            depth += 1
        elif char == ")":
            depth -= 1
        elif depth == 0:
            # Check // first (two-char)
            if char == "/" and i + 1 < length and expr[i + 1] == "/":
                return True
            # Check single-char operators
            if char in ("+", "*", "%"):
                return True
            # - is arithmetic only if both sides look like numeric/variable
            # expressions, not plain text like "小马-新人" or "agent-1"
            if char == "-" and i > 0 and expr[:i].strip():
                left_part = expr[:i].rstrip()
                right_part = expr[i + 1 :].lstrip()
                left_is_expr = (
                    left_part[-1:].isdigit() or left_part.endswith(")") or "." in left_part or "$" in left_part
                )
                right_is_expr = (
                    right_part[:1].isdigit()
                    or right_part.startswith("$")
                    or right_part.startswith("(")
                    or "." in right_part
                )
                if left_is_expr and right_is_expr:
                    return True
        i += 1
    return False


def _resolve_arithmetic(
    expr: str,
    store: StateStore,
    ctx: dict[str, Any],
) -> float:
    """Resolve arithmetic expressions with proper precedence.

    Precedence (lowest first): +, - then *, //, %
    Scans right-to-left for left-associativity at each precedence level.
    """
    # Try each precedence level, lowest first
    for op_group in _ARITH_PRECEDENCE:
        # Scan right-to-left at depth 0 to find rightmost operator
        # (rightmost at lowest precedence = correct left-associativity)
        depth = 0
        best_pos = -1
        best_op_len = 0
        i = len(expr) - 1
        while i >= 0:
            char = expr[i]
            if char == ")":
                depth += 1
            elif char == "(":
                depth -= 1
            elif depth == 0:
                for op in op_group:
                    op_len = len(op)
                    if expr[i : i + op_len] == op:
                        # Skip unary minus at start
                        if op == "-" and i == 0:
                            continue
                        # Skip - that's actually unary (nothing meaningful before it)
                        if op == "-" and not expr[:i].strip():
                            continue
                        best_pos = i
                        best_op_len = op_len
                        break
                if best_pos >= 0:
                    break
            i -= 1

        if best_pos >= 0:
            left_expr = expr[:best_pos].strip()
            right_expr = expr[best_pos + best_op_len :].strip()
            op_str = expr[best_pos : best_pos + best_op_len]

            left_val = resolve(left_expr, store, ctx)
            right_val = resolve(right_expr, store, ctx)
            try:
                left_num = float(left_val) if left_val is not None else 0.0
                right_num = float(right_val) if right_val is not None else 0.0
            except (ValueError, TypeError):
                return 0.0

            if op_str == "+":
                return left_num + right_num
            elif op_str == "-":
                return left_num - right_num
            elif op_str == "*":
                return left_num * right_num
            elif op_str == "//":
                if right_num == 0:
                    log.warning("arithmetic: floor division by zero", expr=expr)
                    return 0.0
                return float(int(left_num // right_num))
            elif op_str == "%":
                if right_num == 0:
                    log.warning("arithmetic: modulo by zero", expr=expr)
                    return 0.0
                return float(left_num % right_num)

    return 0.0
