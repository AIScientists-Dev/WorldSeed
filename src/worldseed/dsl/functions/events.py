"""DSL function: event(type=X)."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from worldseed.engine.state_store import StateStore

from worldseed.dsl.functions._registry import register_function
from worldseed.dsl.functions.helpers import parse_kwargs


def _call_event(
    args_str: str,
    store: StateStore,
    ctx: dict[str, Any],
) -> list[dict[str, Any]]:
    """event(type=X) → list of matching events from EventLog."""
    event_log = ctx.get("event_log")
    if event_log is None:
        return []

    kw = parse_kwargs(args_str)
    event_type = kw.get("type")
    if event_type is None:
        return []

    events = event_log.get_events(event_type=event_type)
    return [e.to_dict() for e in events]


register_function("event", _call_event)
