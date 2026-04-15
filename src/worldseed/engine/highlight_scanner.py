"""Highlight Scanner — config-defined highlight triggers for observer dashboard.

Same trigger logic as ConsequenceScanner but emits highlight events
instead of executing effects. Highlights are admin-scoped events visible
only to the dashboard/narrator, never to regular agents.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from worldseed.dsl.preconditions import evaluate as evaluate_precondition
from worldseed.engine.event_log import EventLog
from worldseed.engine.state_store import StateStore
from worldseed.models.config_schema import (
    HighlightConfig,
    PreconditionConfig,
    SceneConfig,
)
from worldseed.models.event import Event

if TYPE_CHECKING:
    from worldseed.persistence import NullRecorder, RunRecorder

log = structlog.get_logger()


def _references_entity(highlight: HighlightConfig) -> bool:
    """Check if any trigger expression references $entity."""
    return any(_precondition_has_entity(t) for t in highlight.trigger)


def _precondition_has_entity(p: PreconditionConfig) -> bool:
    """Recursively check if a precondition references $entity."""
    for field_val in (p.left, p.right, p.expression):
        if isinstance(field_val, str) and "$entity" in field_val:
            return True
    for child in p.conditions or []:
        if _precondition_has_entity(child):
            return True
    if p.condition is not None and _precondition_has_entity(p.condition):
        return True
    return False


class HighlightScanner:
    """Evaluates config-defined highlight triggers each tick.

    Mirrors ConsequenceScanner's trigger logic (on_change / every_tick,
    entity vs global) but produces highlight events instead of effects.
    """

    def __init__(
        self,
        config: SceneConfig,
        store: StateStore,
        event_log: EventLog,
        recorder: RunRecorder | NullRecorder | None = None,
    ) -> None:
        self._store = store
        self._event_log = event_log
        self._recorder = recorder
        self._previous_state: dict[str, bool] = {}

        # Separate entity vs global highlights
        self._entity_highlights: dict[str, HighlightConfig] = {}
        self._global_highlights: dict[str, HighlightConfig] = {}
        for name, hl in config.highlights.items():
            if _references_entity(hl):
                self._entity_highlights[name] = hl
            else:
                self._global_highlights[name] = hl

    def scan(self, tick: int) -> list[str]:
        """Evaluate all highlight triggers. Returns list of triggered names."""
        triggered: list[str] = []

        base_ctx: dict[str, Any] = {
            "agent_id": "",
            "action_params": {},
            "tick": tick,
        }

        # Prune stale entity keys from _previous_state
        if self._entity_highlights:
            live_ids = {e.id for e in self._store.all_entities()}
            stale = [k for k in self._previous_state if "::" in k and k.split("::")[-1] not in live_ids]
            for k in stale:
                del self._previous_state[k]

        # Global highlights
        for name, hl in self._global_highlights.items():
            if self._eval_and_emit(name, hl, base_ctx, tick):
                triggered.append(name)

        # Entity highlights — run per entity
        if self._entity_highlights:
            for entity in self._store.all_entities():
                entity_ctx = {
                    **base_ctx,
                    "action_params": {"entity": entity.id},
                }
                for name, hl in self._entity_highlights.items():
                    state_key = f"{name}::{entity.id}"
                    if self._eval_and_emit(state_key, hl, entity_ctx, tick):
                        triggered.append(state_key)

        return triggered

    def _eval_and_emit(
        self,
        state_key: str,
        highlight: HighlightConfig,
        ctx: dict[str, Any],
        tick: int,
    ) -> bool:
        """Evaluate trigger and emit highlight event if fired."""
        try:
            current_result = all(evaluate_precondition(t, self._store, ctx) for t in highlight.trigger)
        except Exception:
            log.warning("highlight_eval_failed", name=state_key, exc_info=True)
            current_result = False

        should_fire = False

        if highlight.frequency == "every_tick":
            should_fire = current_result
        else:
            # on_change: fire only on false→true transition
            was_true = self._previous_state.get(state_key, False)
            self._previous_state[state_key] = current_result
            should_fire = current_result and not was_true

        if not should_fire:
            return False

        # Extract base name and entity id for entity highlights
        base_name = state_key.split("::")[0] if "::" in state_key else state_key
        entity_id = state_key.split("::")[-1] if "::" in state_key else ""
        label = highlight.label or base_name
        if entity_id:
            label = f"{entity_id} {label}"

        self._event_log.append(
            Event(
                tick=tick,
                type="highlight",
                source="system",
                detail=label,
                ttl=10,
                scope="admin",
                highlight=True,
            )
        )

        if self._recorder is not None:
            self._recorder.record(
                "highlight",
                tick,
                name=base_name,
                label=label,
                source="config",
            )

        return True
