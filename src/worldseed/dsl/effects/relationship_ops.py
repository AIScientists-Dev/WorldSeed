"""Effect operators for relationships: add_relationship, remove_relationship."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from worldseed.engine.event_log import EventLog
    from worldseed.engine.state_store import StateStore

from worldseed.dsl.effects._helpers import resolve_entity_ref
from worldseed.dsl.effects._registry import register_effect
from worldseed.models.config_schema import EffectConfig
from worldseed.utils.nested import nested_get

log = structlog.get_logger()


def _exec_add_relationship(
    effect: EffectConfig,
    store: StateStore,
    event_log: EventLog,
    ctx: dict[str, Any],
    tick: int,
) -> None:
    """Add or upsert a relationship via properties.

    With value: properties[type] is a dict → {target: value}
    Without value: properties[type] is a list → [target, ...]
    """
    from_id = resolve_entity_ref(effect.from_entity, ctx)
    rel_type = effect.type
    to_id = resolve_entity_ref(effect.to, ctx)
    if from_id is None or rel_type is None or to_id is None:
        return
    entity = store.get(from_id)
    if entity is None:
        log.warning("add_relationship: entity not found", entity_id=from_id)
        return

    if effect.value is not None:
        # Valued: dict storage
        current = nested_get(entity.data, rel_type)
        if not isinstance(current, dict):
            current = {}
        else:
            current = dict(current)  # copy before mutating
        current[to_id] = effect.value
        store.update_property(from_id, rel_type, current)
    else:
        # Simple: list storage
        current = nested_get(entity.data, rel_type)
        if not isinstance(current, list):
            current = []
        if to_id not in current:
            current = [*current, to_id]
        store.update_property(from_id, rel_type, current)

    from worldseed.models.event import Event

    event_log.append(
        Event(
            tick=tick,
            type="relationship_changed",
            source=ctx.get("agent_id", "system"),
            detail=f"Relationship '{rel_type}': {from_id} → {to_id} added",
            ttl=5,
            scope="admin",
            highlight=True,
        )
    )


def _exec_remove_relationship(
    effect: EffectConfig,
    store: StateStore,
    event_log: EventLog,
    ctx: dict[str, Any],
    tick: int,
) -> None:
    """Remove a relationship from properties.

    Dict: deletes key. List: removes item.
    """
    from_id = resolve_entity_ref(effect.from_entity, ctx)
    rel_type = effect.type
    to_id = resolve_entity_ref(effect.to, ctx)
    if from_id is None or rel_type is None or to_id is None:
        return
    entity = store.get(from_id)
    if entity is None:
        return

    current = nested_get(entity.data, rel_type)
    removed = False
    if isinstance(current, dict) and to_id in current:
        current = {k: v for k, v in current.items() if k != to_id}
        store.update_property(from_id, rel_type, current)
        removed = True
    elif isinstance(current, list) and to_id in current:
        store.update_property(from_id, rel_type, [x for x in current if x != to_id])
        removed = True

    if removed:
        from worldseed.models.event import Event

        event_log.append(
            Event(
                tick=tick,
                type="relationship_changed",
                source=ctx.get("agent_id", "system"),
                detail=f"Relationship '{rel_type}': {from_id} → {to_id} removed",
                ttl=5,
                scope="admin",
                highlight=True,
            )
        )


register_effect("add_relationship", _exec_add_relationship)
register_effect("remove_relationship", _exec_remove_relationship)
