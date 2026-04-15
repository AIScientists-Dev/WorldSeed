"""Effect operators for list manipulation: list_append, list_remove, list_pop_random."""

from __future__ import annotations

import random
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


def _exec_list_append(
    effect: EffectConfig,
    store: StateStore,
    event_log: EventLog,
    ctx: dict[str, Any],
    tick: int,
) -> None:
    """Append a value to a list property. Creates list if property is None."""
    if effect.target is None:
        return
    entity_id, prop_name = parse_target(effect.target, store, ctx)
    value = resolve(effect.value, store, ctx) if effect.value is not None else None

    entity = get_entity_or_warn(store, entity_id, "list_append")
    if entity is None:
        return

    current = nested_get(entity.data, prop_name)
    if current is None:
        current = []
    elif not isinstance(current, list):
        log.warning("list_append: property is not a list", prop=prop_name, value=current)
        return

    new_list = [*current, value]
    store.update_property(entity_id, prop_name, new_list)


def _exec_list_remove(
    effect: EffectConfig,
    store: StateStore,
    event_log: EventLog,
    ctx: dict[str, Any],
    tick: int,
) -> None:
    """Remove first occurrence of a value from a list property."""
    if effect.target is None:
        return
    entity_id, prop_name = parse_target(effect.target, store, ctx)
    value = resolve(effect.value, store, ctx) if effect.value is not None else None

    entity = get_entity_or_warn(store, entity_id, "list_remove")
    if entity is None:
        return

    current = nested_get(entity.data, prop_name)
    if not isinstance(current, list):
        log.warning("list_remove: property is not a list", prop=prop_name)
        return

    if value not in current:
        log.warning("list_remove: value not in list", value=value, prop=prop_name)
        return

    new_list = list(current)
    new_list.remove(value)
    store.update_property(entity_id, prop_name, new_list)


def _exec_list_pop_random(
    effect: EffectConfig,
    store: StateStore,
    event_log: EventLog,
    ctx: dict[str, Any],
    tick: int,
) -> None:
    """Randomly remove an element from source list and append to target list.

    YAML: { operator: list_pop_random, source: "deck.cards", target: "$agent.hand" }
    """
    if effect.source is None or effect.target is None:
        return

    src_entity_id, src_prop = parse_target(effect.source, store, ctx)
    tgt_entity_id, tgt_prop = parse_target(effect.target, store, ctx)

    src_entity = get_entity_or_warn(store, src_entity_id, "list_pop_random")
    if src_entity is None:
        return
    tgt_entity = get_entity_or_warn(store, tgt_entity_id, "list_pop_random")
    if tgt_entity is None:
        return

    src_list = nested_get(src_entity.data, src_prop)
    if not isinstance(src_list, list) or len(src_list) == 0:
        log.warning("list_pop_random: source is empty or not a list", source=effect.source)
        return

    # Pick random element
    idx = random.randrange(len(src_list))
    picked = src_list[idx]

    # Remove from source
    new_src = list(src_list)
    new_src.pop(idx)
    store.update_property(src_entity_id, src_prop, new_src)

    # Append to target
    tgt_list = nested_get(tgt_entity.data, tgt_prop)
    if tgt_list is None:
        tgt_list = []
    elif not isinstance(tgt_list, list):
        log.warning("list_pop_random: target is not a list", target=effect.target)
        return
    store.update_property(tgt_entity_id, tgt_prop, [*tgt_list, picked])


register_effect("list_append", _exec_list_append)
register_effect("list_remove", _exec_list_remove)
register_effect("list_pop_random", _exec_list_pop_random)
