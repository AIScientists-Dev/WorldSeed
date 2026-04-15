"""Effect operator: for_each — iterate matching entities and apply sub-effects."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from worldseed.engine.state_store import StateStore

from worldseed.dsl.effects._registry import register_effect
from worldseed.dsl.functions.aggregation import _filter_entities
from worldseed.engine.event_log import EventLog
from worldseed.models.config_schema import EffectConfig

log = structlog.get_logger()


def _exec_for_each(
    effect: EffectConfig,
    store: StateStore,
    event_log: EventLog,
    ctx: dict[str, Any],
    tick: int,
) -> None:
    """Iterate entities matching criteria and apply sub-effects to each.

    YAML:
        - operator: for_each
          match: { type: agent }
          where: "folded == false"
          effects:
            - { operator: set, target: "$entity.acted", value: false }

    $entity in sub-effects resolves to the current entity's ID.
    """
    from worldseed.dsl.effects import execute

    match_filter = effect.match
    where_filter = effect.where
    sub_effects = effect.sub_effects

    if not match_filter or not sub_effects:
        log.warning("for_each: missing match or effects")
        return

    # Get matching entity type
    entity_type = match_filter.get("type")
    if entity_type is None:
        log.warning("for_each: match must include 'type'")
        return

    # Query entities by type, then filter
    matched: list[object] = list(store.query_by_type(entity_type))

    # Apply additional match filters (property checks beyond type)
    extra_filters = {k: v for k, v in match_filter.items() if k != "type"}
    if extra_filters:
        where_parts = [f"{k} == {v}" for k, v in extra_filters.items()]
        where_expr = " AND ".join(where_parts)
        matched = _filter_entities(matched, where_expr, store, ctx)

    # Apply where filter
    if where_filter:
        matched = _filter_entities(matched, where_filter, store, ctx)

    # Apply sub-effects to each matching entity
    for entity in matched:
        entity_ctx = {
            **ctx,
            "action_params": {
                **ctx.get("action_params", {}),
                "entity": getattr(entity, "id", ""),
            },
        }
        for sub_effect in sub_effects:
            execute(sub_effect, store, event_log, entity_ctx, tick)


register_effect("for_each", _exec_for_each)
