"""Effect operators for state manipulation: set, increment, decrement."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from worldseed.engine.event_log import EventLog
    from worldseed.engine.state_store import StateStore

from worldseed.dsl.effects._helpers import get_entity_or_warn, parse_target
from worldseed.dsl.effects._registry import register_effect
from worldseed.dsl.path_resolver import resolve
from worldseed.models.config_schema import EffectConfig
from worldseed.utils.nested import nested_get

log = structlog.get_logger()


def _exec_set(
    effect: EffectConfig,
    store: StateStore,
    event_log: EventLog,
    ctx: dict[str, Any],
    tick: int,
) -> None:
    """Set a property value."""
    if effect.target is None:
        return
    entity_id, prop_name = parse_target(effect.target, store, ctx)
    value = resolve(effect.value, store, ctx) if effect.value is not None else None

    entity = get_entity_or_warn(store, entity_id, "set")
    if entity is None:
        return

    result = store.update_property(entity_id, prop_name, value)
    old_value = result[0] if result else None
    if old_value != value:
        log.debug(
            "property_changed",
            entity=entity_id,
            prop=prop_name,
            old=old_value,
            new=value,
        )


def _exec_delta(
    effect: EffectConfig,
    store: StateStore,
    event_log: EventLog,
    ctx: dict[str, Any],
    tick: int,
    sign: int,
) -> None:
    """Increment (sign=+1) or decrement (sign=-1) a numeric property."""
    op_name = "increment" if sign > 0 else "decrement"
    if effect.target is None:
        return
    entity_id, prop_name = parse_target(effect.target, store, ctx)

    # DM effects may use 'value' instead of 'by' — accept both
    raw_by = effect.by if effect.by is not None else effect.value
    by_val = resolve(raw_by, store, ctx) if raw_by is not None else 0
    try:
        by_num = float(by_val) if by_val is not None else 0.0
    except (ValueError, TypeError):
        log.warning(f"{op_name}: non-numeric 'by' value", by=by_val)
        return

    entity = get_entity_or_warn(store, entity_id, op_name)
    if entity is None:
        return

    old_value = nested_get(entity.data, prop_name)
    try:
        old_num = float(old_value) if old_value is not None else 0.0
    except (ValueError, TypeError):
        log.warning(
            f"{op_name}: non-numeric property",
            prop=prop_name,
            value=old_value,
        )
        return
    new_value = old_num + sign * by_num

    # Optional min/max clamp
    if effect.min is not None and new_value < effect.min:
        new_value = effect.min
    if effect.max is not None and new_value > effect.max:
        new_value = effect.max

    # Preserve int type when possible
    if isinstance(old_value, int) and isinstance(by_val, int):
        new_value_stored: int | float = int(new_value)
    else:
        new_value_stored = new_value

    store.update_property(entity_id, prop_name, new_value_stored)
    if old_value != new_value_stored:
        log.debug(
            "property_changed",
            entity=entity_id,
            prop=prop_name,
            old=old_value,
            new=new_value_stored,
        )


def _exec_increment(
    effect: EffectConfig,
    store: StateStore,
    event_log: EventLog,
    ctx: dict[str, Any],
    tick: int,
) -> None:
    """Increment a numeric property."""
    _exec_delta(effect, store, event_log, ctx, tick, sign=+1)


def _exec_decrement(
    effect: EffectConfig,
    store: StateStore,
    event_log: EventLog,
    ctx: dict[str, Any],
    tick: int,
) -> None:
    """Decrement a numeric property."""
    _exec_delta(effect, store, event_log, ctx, tick, sign=-1)


register_effect("set", _exec_set)
register_effect("increment", _exec_increment)
register_effect("decrement", _exec_decrement)
