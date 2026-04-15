"""Shared helpers for effect operators."""

from __future__ import annotations

import re
from typing import TYPE_CHECKING, Any

import structlog

if TYPE_CHECKING:
    from worldseed.engine.state_store import StateStore

from worldseed.dsl.path_resolver import (
    lookup_param,
    resolve_params,
)
from worldseed.dsl.path_resolver import (
    resolve as dsl_resolve,
)
from worldseed.models.entity import Entity

log = structlog.get_logger()


def parse_target(
    target: str,
    store: StateStore,
    ctx: dict[str, Any],
) -> tuple[str, str]:
    """Parse 'entity.key' into (entity_id, prop_dotpath).

    Flat format:  "food_supply.quantity" → ("food_supply", "quantity")

    Uses resolve_params (single source of truth) to resolve ALL
    $param references before splitting. Supports nested property
    paths and embedded $param in any position.
    """
    resolved = resolve_params(target, ctx)
    parts = resolved.split(".")

    first = parts[0]

    if first == "agent":
        entity_id = str(lookup_param("agent", ctx) or "")
    else:
        entity_id = first

    # Everything after entity_id is the property path
    if len(parts) >= 2:
        prop_path = ".".join(parts[1:])
        return (entity_id, prop_path)

    msg = f"Cannot parse target: {target}"
    raise ValueError(msg)


def resolve_entity_ref(
    value: str | None,
    ctx: dict[str, Any],
) -> str | None:
    """Resolve a $param or bare entity_id to an entity_id string.

    Uses lookup_param from path_resolver (single source of truth).
    """
    if value is None:
        return None
    if value.startswith("$"):
        result = lookup_param(value[1:], ctx)
        return str(result) if result is not None else None
    if value == "agent":
        result = lookup_param("agent", ctx)
        return str(result) if result is not None else None
    return value


def get_entity_or_warn(
    store: StateStore,
    entity_id: str,
    operator: str,
) -> Entity | None:
    """Get an entity from store, logging a warning if not found."""
    entity = store.get(entity_id)
    if entity is None:
        log.warning(
            f"{operator}: entity not found",
            entity_id=entity_id,
        )
    return entity


_ENTITY_PATH_RE = re.compile(r"\$(\w+\.\w[\w.]*)")


def interpolate(template: str, ctx: dict[str, Any], store: StateStore | None = None) -> str:
    """Replace $references in a string template.

    First pass: resolve $x.y entity property paths via store (e.g. $entity.votes_received → 5).
    Second pass: resolve remaining $param references ($entity → ID, $agent → ID, $tick → number).

    Order matters: $entity.votes_received must resolve as a whole path before
    $entity alone is replaced with the entity ID.
    """
    result = template

    if store is not None:

        def _resolve_entity_path(m: re.Match[str]) -> str:
            val = dsl_resolve(m.group(1), store, ctx)
            return str(val) if val is not None else m.group(0)

        result = _ENTITY_PATH_RE.sub(_resolve_entity_path, result)

    return resolve_params(result, ctx)
