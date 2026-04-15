"""Sanity check runner — executes a config's self-tests.

Each sanity check is a sequence of steps: actions, assertions, and tick advances.
The runner creates a fresh WorldEngine per check (isolation).
"""

from __future__ import annotations

from typing import Any

from worldseed.engine.state_store import StateStore
from worldseed.models.config_schema import SanityCheckConfig, SanityStep, SceneConfig
from worldseed.scene.validator import SanityResult
from worldseed.world import WorldEngine


def run_sanity_check(config: SceneConfig, check: SanityCheckConfig) -> SanityResult:
    """Run one sanity check against a fresh world instance."""
    try:
        engine = WorldEngine(config=config)
        engine.register_from_config()
    except Exception as e:
        return SanityResult(
            name=check.name,
            passed=False,
            failure_step=0,
            failure_detail=f"Failed to create world: {e}",
        )

    # Advance initial ticks if specified
    if check.ticks:
        for _ in range(check.ticks):
            engine.step()

    for i, step in enumerate(check.steps):
        result = _execute_step(engine, step, i)
        if result is not None:
            return SanityResult(
                name=check.name,
                passed=False,
                failure_step=i + 1,
                failure_detail=result,
            )

    return SanityResult(name=check.name, passed=True)


def _execute_step(engine: WorldEngine, step: SanityStep, index: int) -> str | None:
    """Execute one step. Returns None on success, error string on failure."""

    # Tick advance
    if step.ticks is not None:
        for _ in range(step.ticks):
            engine.step()
        return None

    # Assertion
    if step.assertion is not None:
        return _evaluate_assertion(engine.state, step.assertion)

    # Action (possibly repeated)
    if step.agent and step.action:
        from worldseed.engine.rules_engine import ActionResult

        repeat = step.repeat or 1
        for r in range(repeat):
            submit_result = engine.submit(step.agent, step.action, step.params)
            results = engine.step()

            # Mechanical actions return ActionResult from submit();
            # DM actions return None from submit() and appear in step() results.
            if isinstance(submit_result, ActionResult):
                action_result = submit_result
            elif results:
                action_result = results[0]
            else:
                if step.expect == "success":
                    return f"No result for {step.action} (repeat {r + 1})"
                continue

            if step.expect == "success" and not action_result.success:
                reason = action_result.reason or "unknown"
                return f"{step.agent}.{step.action} failed (expected success): {reason}"
            if step.expect == "fail" and action_result.success:
                return f"{step.agent}.{step.action} succeeded (expected failure)"
        return None

    return f"Step {index + 1}: no action, assertion, or ticks specified"


def _evaluate_assertion(store: StateStore, expr: str) -> str | None:
    """Evaluate a simple assertion expression.

    Supports: ==, !=, >, <, >=, <=
    Returns None if assertion passes, error string if it fails.
    """
    # Parse operator (longest first to avoid == matching before >=)
    for op in (">=", "<=", "!=", "==", ">", "<"):
        if op in expr:
            parts = expr.split(op, 1)
            if len(parts) == 2:
                left_expr = parts[0].strip()
                right_expr = parts[1].strip()
                left_val = _resolve_value(store, left_expr)
                right_val = _resolve_value(store, right_expr)
                passed = _compare(left_val, right_val, op)
                if not passed:
                    return (
                        f"Assertion failed: {expr}\n"
                        f"  left:  {left_expr} = {left_val}\n"
                        f"  right: {right_expr} = {right_val}"
                    )
                return None

    return f"Cannot parse assertion: {expr}"


def _resolve_value(store: StateStore, expr: str) -> Any:
    """Resolve a value expression for assertions.

    Uses nested_get for dot-path property access (consistent with engine).
    """
    expr = expr.strip().strip("'\"")

    # Numeric parsing — use canonical implementation
    from worldseed.dsl.functions.helpers import try_numeric

    num = try_numeric(expr)
    if num is not None:
        return num

    # Try boolean
    if expr == "true":
        return True
    if expr == "false":
        return False

    # Try entity.X.Y path (must have at least entity.X.Y)
    if "." in expr:
        parts = expr.split(".")
        entity_id = parts[0]
        entity = store.get(entity_id)
        if entity is None:
            return expr  # Not an entity path, return as literal

        # Walk remaining path using consistent nested traversal
        remaining = ".".join(parts[1:])
        from worldseed.dsl.functions import walk_entity_path

        return walk_entity_path(entity, remaining)

    # Bare string = literal string
    return expr


def _compare(left: Any, right: Any, op: str) -> bool:
    """Compare two values with the given operator."""
    if op == "==":
        return _coerce_eq(left, right)
    if op == "!=":
        return not _coerce_eq(left, right)
    # Numeric comparisons — delegate to canonical implementation
    from worldseed.dsl.preconditions import _safe_compare

    return _safe_compare(left, right, op)


def _coerce_eq(left: Any, right: Any) -> bool:
    """Equality with type coercion for common cases.

    Treats None as 0 for numeric comparisons — consistent with the
    engine's increment/decrement behavior (None property = 0).
    """
    if left == right:
        return True
    if str(left) == str(right):
        return True
    try:
        lf = float(left) if left is not None else 0.0
        rf = float(right) if right is not None else 0.0
        return lf == rf
    except (ValueError, TypeError):
        return False
