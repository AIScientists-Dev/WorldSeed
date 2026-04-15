"""Effect operators for entity lifecycle: create_entity, remove_entity."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from worldseed.engine.event_log import EventLog
    from worldseed.engine.state_store import StateStore

from worldseed.dsl.effects._helpers import resolve_entity_ref
from worldseed.dsl.effects._registry import register_effect
from worldseed.dsl.path_resolver import resolve_params
from worldseed.models.config_schema import EffectConfig
from worldseed.models.entity import Entity

log = structlog.get_logger()


def _exec_create_entity(
    effect: EffectConfig,
    store: StateStore,
    event_log: EventLog,
    ctx: dict[str, Any],
    tick: int,
) -> None:
    """Create a new entity. Resolves $param in id, type, and property values."""
    if effect.id is None or effect.type is None:
        return

    entity_id = resolve_params(effect.id, ctx)
    entity_type = resolve_params(effect.type, ctx)

    # Resolve $param in property values
    props: dict[str, Any] = {}
    for k, v in (effect.properties or {}).items():
        if isinstance(v, str):
            props[k] = resolve_params(v, ctx)
        else:
            props[k] = v

    if store.get(entity_id) is not None:
        log.warning("create_entity: duplicate id", entity_id=entity_id)
        return
    entity = Entity(
        id=entity_id,
        type=entity_type,
        _data=props,
    )
    store.add(entity)

    from worldseed.models.event import Event

    event_log.append(
        Event(
            tick=tick,
            type="entity_created",
            source=ctx.get("agent_id", "system"),
            detail=f"Entity '{entity_id}' (type: {entity_type}) created",
            ttl=5,
            scope="admin",
            highlight=True,
        )
    )


def _exec_remove_entity(
    effect: EffectConfig,
    store: StateStore,
    event_log: EventLog,
    ctx: dict[str, Any],
    tick: int,
) -> None:
    """Remove an entity and clean dangling relationships."""
    target = resolve_entity_ref(effect.target, ctx)
    if target is None:
        return
    if store.get(target) is None:
        return

    store.remove(target)

    from worldseed.models.event import Event

    event_log.append(
        Event(
            tick=tick,
            type="entity_removed",
            source=ctx.get("agent_id", "system"),
            detail=f"Entity '{target}' removed",
            ttl=5,
            scope="admin",
            highlight=True,
        )
    )


register_effect("create_entity", _exec_create_entity)
register_effect("remove_entity", _exec_remove_entity)
