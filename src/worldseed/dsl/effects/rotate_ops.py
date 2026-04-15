"""Effect operator: rotate — advance a property to the next value in a sequence.

YAML usage:
    - operator: rotate
      target: "game.active_role"
      sequence: "game.role_order"
      skip: "game.dead_roles"       # optional: values to skip
      value: "$agent.id"            # optional: start from this position
"""

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


def _exec_rotate(
    effect: EffectConfig,
    store: StateStore,
    event_log: EventLog,
    ctx: dict[str, Any],
    tick: int,
) -> None:
    """Advance a property to the next value in a sequence.

    Finds the current value in the sequence list, moves to the next entry
    (wrapping around), and skips any values present in the skip list.
    """
    if effect.target is None or effect.sequence is None:
        log.warning("rotate: missing target or sequence")
        return

    # --- Resolve target property ---
    tgt_entity_id, tgt_prop = parse_target(effect.target, store, ctx)
    tgt_entity = get_entity_or_warn(store, tgt_entity_id, "rotate")
    if tgt_entity is None:
        return

    # --- Resolve sequence list ---
    seq_entity_id, seq_prop = parse_target(effect.sequence, store, ctx)
    seq_entity = get_entity_or_warn(store, seq_entity_id, "rotate")
    if seq_entity is None:
        return

    sequence = nested_get(seq_entity.data, seq_prop)
    if not isinstance(sequence, list) or len(sequence) == 0:
        log.warning(
            "rotate: sequence is empty or not a list",
            sequence=effect.sequence,
            value=sequence,
        )
        return

    # --- Resolve skip list (optional) ---
    skip_set: set[Any] = set()
    if effect.skip is not None:
        skip_entity_id, skip_prop = parse_target(effect.skip, store, ctx)
        skip_entity = get_entity_or_warn(store, skip_entity_id, "rotate")
        if skip_entity is not None:
            skip_list = nested_get(skip_entity.data, skip_prop)
            if isinstance(skip_list, list):
                try:
                    skip_set = set(skip_list)
                except TypeError:
                    log.warning("rotate: skip list contains unhashable values")
                    skip_set = set()

    # --- Determine current value ---
    if effect.value is not None:
        current = resolve(effect.value, store, ctx)
    else:
        current = nested_get(tgt_entity.data, tgt_prop)

    # --- Find position and advance ---
    try:
        idx = sequence.index(current)
    except ValueError:
        # Current value not in sequence — start from before the first element
        idx = -1

    for step in range(1, len(sequence) + 1):
        next_idx = (idx + step) % len(sequence)
        candidate = sequence[next_idx]
        if candidate not in skip_set:
            store.update_property(tgt_entity_id, tgt_prop, candidate)
            log.debug(
                "rotate_advanced",
                entity=tgt_entity_id,
                prop=tgt_prop,
                old=current,
                new=candidate,
            )
            return

    # All entries in skip list — nowhere to go
    log.warning(
        "rotate: all sequence entries are skipped",
        sequence=effect.sequence,
        skip=effect.skip,
    )


register_effect("rotate", _exec_rotate)
