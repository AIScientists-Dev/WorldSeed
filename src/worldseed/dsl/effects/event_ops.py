"""Effect operators for events: emit_event."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from worldseed.dsl.effects._helpers import interpolate, resolve_entity_ref
from worldseed.dsl.effects._registry import register_effect
from worldseed.engine.event_log import EventLog
from worldseed.models.config_schema import EffectConfig
from worldseed.models.event import Event

if TYPE_CHECKING:
    from worldseed.engine.state_store import StateStore


def _exec_emit_event(
    effect: EffectConfig,
    store: StateStore,
    event_log: EventLog,
    ctx: dict[str, Any],
    tick: int,
) -> None:
    """Emit an event to the event log."""
    agent_id = ctx.get("agent_id", "")
    detail = interpolate(effect.detail or "", ctx, store)
    event_type = effect.type or "event"
    ttl = effect.ttl if effect.ttl is not None else 1
    scope = effect.scope or ctx.get("dm_scope") or "global"

    # Resolve event target if specified
    event_target = resolve_entity_ref(effect.event_target, ctx)

    event_log.append(
        Event(
            tick=tick,
            type=event_type,
            source=str(agent_id),
            detail=detail,
            ttl=ttl,
            scope=scope,
            target=event_target,
            push=effect.push,
            highlight=effect.highlight,
        )
    )

    # Persist to stream.jsonl if recorder available in ctx
    recorder = ctx.get("recorder")
    if recorder is not None:
        recorder.record(
            "event",
            tick,
            type=event_type,
            source=str(agent_id),
            detail=detail,
            scope=scope,
            target=event_target or "",
        )


register_effect("emit_event", _exec_emit_event)
