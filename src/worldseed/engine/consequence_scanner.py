"""Consequence Scanner — on_change and every_tick trigger detection."""

from __future__ import annotations

from typing import Any

import structlog

from worldseed.dsl.effects import execute as execute_effect
from worldseed.dsl.preconditions import evaluate as evaluate_precondition
from worldseed.engine.event_log import EventLog
from worldseed.engine.state_store import StateStore
from worldseed.models.config_schema import (
    ConsequenceConfig,
    PreconditionConfig,
    SceneConfig,
)

log = structlog.get_logger()


def _references_entity(consequence: ConsequenceConfig) -> bool:
    """Check if any trigger expression in a consequence references $entity."""
    return any(_precondition_has_entity(t) for t in consequence.trigger)


def _precondition_has_entity(p: PreconditionConfig) -> bool:
    """Recursively check if a precondition references $entity."""
    # Check string fields that may contain DSL expressions
    for field_val in (p.left, p.right, p.expression):
        if isinstance(field_val, str) and "$entity" in field_val:
            return True
    # Recurse into nested conditions
    if p.condition is not None and _precondition_has_entity(p.condition):
        return True
    if p.conditions:
        if any(_precondition_has_entity(c) for c in p.conditions):
            return True
    return False


class ConsequenceScanner:
    """Evaluates consequence triggers and executes effects on state change."""

    def __init__(
        self,
        config: SceneConfig,
        store: StateStore,
        event_log: EventLog,
        recorder: Any = None,
    ) -> None:
        self._config = config
        self._store = store
        self._event_log = event_log
        self._recorder = recorder
        self._previous_state: dict[str, bool] = {}

        # Cache entity-referencing classification (config never changes)
        self._entity_consequences: dict[str, ConsequenceConfig] = {}
        self._global_consequences: dict[str, ConsequenceConfig] = {}
        for name, consequence in config.consequences.items():
            if _references_entity(consequence):
                self._entity_consequences[name] = consequence
            else:
                self._global_consequences[name] = consequence

    # Max re-scan passes per tick. Consequences cascade: A fires → changes state
    # → B triggers in next pass. This caps the chain length to prevent infinite
    # loops (e.g., A triggers B triggers A). 10 passes supports chains up to
    # 10 deep, which covers any realistic config. If hit, a warning is logged.
    _MAX_SCAN_PASSES = 10

    def scan(self, tick: int) -> tuple[list[str], list[dict[str, Any]]]:
        """Scan all consequences, re-scanning until stable.

        Consequences can cascade: A fires → changes state → B now triggers.
        We re-scan until a full pass produces no new firings (stable state),
        or until _MAX_SCAN_PASSES to prevent infinite loops.

        Returns:
            (triggered_names, dm_pending_list)
            - triggered_names: names of consequences that fired (across all passes)
            - dm_pending_list: consequence DM calls to resolve asynchronously
        """
        # Prune stale entity keys from _previous_state
        live_ids = {e.id for e in self._store.all_entities()}
        stale = [k for k in self._previous_state if "::" in k and k.split("::")[-1] not in live_ids]
        for k in stale:
            del self._previous_state[k]

        all_triggered: list[str] = []
        all_dm_pending: list[dict[str, Any]] = []
        ctx: dict[str, Any] = {
            "agent_id": "",
            "action_params": {},
            "tick": tick,
            "event_log": self._event_log,
            "recorder": self._recorder,
        }

        # Pass 0: run ALL consequences (every_tick + on_change)
        # Pass 1+: re-scan only on_change consequences (cascading reactions)
        # every_tick fires once per tick, on_change re-scans until stable.
        for pass_num in range(self._MAX_SCAN_PASSES):
            pass_triggered: list[str] = []
            pass_dm: list[dict[str, Any]] = []

            for name, consequence in self._entity_consequences.items():
                # Skip every_tick after first pass
                if pass_num > 0 and consequence.frequency == "every_tick":
                    continue
                fired, pending = self._scan_entity_consequence(name, consequence, ctx, tick)
                if fired:
                    pass_triggered.append(name)
                pass_dm.extend(pending)

            for name, consequence in self._global_consequences.items():
                if pass_num > 0 and consequence.frequency == "every_tick":
                    continue
                fired, pending = self._scan_global_consequence(name, consequence, ctx, tick)
                if fired:
                    pass_triggered.append(name)
                pass_dm.extend(pending)

            all_triggered.extend(pass_triggered)
            all_dm_pending.extend(pass_dm)

            if not pass_triggered:
                break  # stable — no consequence fired this pass

            if pass_num == self._MAX_SCAN_PASSES - 1:
                log.warning(
                    "consequence_scan_max_passes",
                    passes=self._MAX_SCAN_PASSES,
                    still_firing=pass_triggered,
                )

        return all_triggered, all_dm_pending

    def _eval_and_fire(
        self,
        state_key: str,
        consequence: ConsequenceConfig,
        ctx: dict[str, Any],
        tick: int,
    ) -> tuple[bool, dict[str, Any] | None]:
        """Evaluate triggers and fire effects based on frequency mode.

        on_change:  fire once on false→true transition.
        every_tick: fire every tick while condition is true.

        Returns (fired, dm_pending_info_or_None).
        """
        try:
            current_result = all(evaluate_precondition(t, self._store, ctx) for t in consequence.trigger)
        except Exception:
            log.warning("consequence_eval_failed", name=state_key, exc_info=True)
            current_result = False

        should_fire = False

        if consequence.frequency == "every_tick":
            should_fire = current_result
        else:
            # on_change: fire only on false→true transition
            was_true = self._previous_state.get(state_key, False)
            self._previous_state[state_key] = current_result
            should_fire = current_result and not was_true

        if not should_fire:
            return False, None

        # Execute deterministic effects
        for effect in consequence.effects:
            execute_effect(effect, self._store, self._event_log, ctx, tick)
        self._record_consequence(state_key, ctx, tick)

        # Queue DM call if consequence has dm config
        dm_pending = None
        if consequence.dm is not None:
            dm_pending = {
                "consequence_name": state_key,
                "dm_config": consequence.dm,
                "ctx": dict(ctx),
                "tick": tick,
            }

        return True, dm_pending

    def _record_consequence(
        self,
        name: str,
        ctx: dict[str, Any],
        tick: int,
    ) -> None:
        """Record consequence firing to stream for dashboard/replay."""
        if self._recorder is None:
            return
        # Consequence record is metadata only — narrative content lives in
        # the event record produced by the consequence's emit_event effect.
        self._recorder.record(
            "consequence",
            tick,
            name=name,
            detail=f"[{name}]",
        )

    def _scan_global_consequence(
        self,
        name: str,
        consequence: ConsequenceConfig,
        ctx: dict[str, Any],
        tick: int,
    ) -> tuple[bool, list[dict[str, Any]]]:
        """Evaluate a non-entity consequence once."""
        fired, dm_info = self._eval_and_fire(name, consequence, ctx, tick)
        pending = [dm_info] if dm_info is not None else []
        return fired, pending

    def _scan_entity_consequence(
        self,
        name: str,
        consequence: ConsequenceConfig,
        base_ctx: dict[str, Any],
        tick: int,
    ) -> tuple[bool, list[dict[str, Any]]]:
        """Evaluate a $entity-referencing consequence per entity."""
        fired = False
        dm_pending: list[dict[str, Any]] = []
        for entity in self._store.all_entities():
            entity_ctx = {
                **base_ctx,
                "action_params": {
                    **base_ctx.get("action_params", {}),
                    "entity": entity.id,
                },
            }
            state_key = f"{name}::{entity.id}"
            entity_fired, dm_info = self._eval_and_fire(state_key, consequence, entity_ctx, tick)
            if entity_fired:
                fired = True
            if dm_info is not None:
                dm_pending.append(dm_info)

        return fired, dm_pending
