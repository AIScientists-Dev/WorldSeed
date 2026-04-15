"""Rules Engine — processes actions and auto_tick effects."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

import structlog

from worldseed.dsl.effects import execute as execute_effect
from worldseed.dsl.preconditions import evaluate as evaluate_precondition
from worldseed.engine.event_log import EventLog
from worldseed.engine.state_store import StateStore
from worldseed.models.action import ActionSubmission
from worldseed.models.config_schema import EffectConfig, PreconditionConfig, SceneConfig

if TYPE_CHECKING:
    from worldseed.dm.builder import DMContextBuilder
    from worldseed.dm.providers.base import DMProvider
    from worldseed.engine.inbox import InboxManager
    from worldseed.persistence import NullRecorder, RunRecorder

log = structlog.get_logger()


@dataclass
class ActionResult:
    """Result of processing an action."""

    success: bool
    action: ActionSubmission
    reason: str = ""


class RulesEngine:
    """Processes actions against scene config rules."""

    def __init__(
        self,
        config: SceneConfig,
        store: StateStore,
        event_log: EventLog,
        dm_provider: DMProvider | None = None,
        dm_builder: DMContextBuilder | None = None,
        recorder: RunRecorder | NullRecorder | None = None,
        inbox_manager: InboxManager | None = None,
    ) -> None:
        self._config = config
        self._store = store
        self._event_log = event_log
        self._dm_provider = dm_provider
        self._dm_builder = dm_builder
        self._recorder = recorder
        self._inbox_manager = inbox_manager
        self._action_seq: int = 0

    def _validate_action(
        self,
        action: ActionSubmission,
        tick: int,
    ) -> tuple[ActionResult | None, dict[str, Any] | None]:
        """Shared validation: lookup, context, params, preconditions.

        Returns (error_result, None) on failure,
        or (None, ctx) on success.
        """
        action_config = self._config.actions.get(action.action_type)
        if action_config is None:
            return (
                ActionResult(
                    success=False,
                    action=action,
                    reason=f"Unknown action: {action.action_type}",
                ),
                None,
            )

        self._action_seq += 1
        ctx: dict[str, Any] = {
            "agent_id": action.agent_id,
            "action_params": action.params,
            "tick": tick,
            "seq": self._action_seq,
            "event_log": self._event_log,
            "recorder": self._recorder,
        }

        # Check available_to — reject if agent doesn't match visibility filter
        if action_config.available_to is not None:
            if not all(evaluate_precondition(p, self._store, ctx) for p in action_config.available_to):
                return (
                    ActionResult(
                        success=False,
                        action=action,
                        reason=f"Action '{action.action_type}' is not available to you",
                    ),
                    None,
                )

        # Validate number params are non-negative
        for param_def in action_config.params:
            if param_def.type == "number":
                val = action.params.get(param_def.name)
                if val is not None and isinstance(val, (int, float)) and val < 0:
                    return (
                        ActionResult(
                            success=False,
                            action=action,
                            reason=(f"Param '{param_def.name}' must be non-negative, got {val}"),
                        ),
                        None,
                    )

        # Evaluate preconditions (all must pass)
        for precond in action_config.preconditions:
            if not evaluate_precondition(precond, self._store, ctx):
                reason = _describe_precondition_failure(precond, self._store, ctx)
                return (
                    ActionResult(success=False, action=action, reason=reason),
                    None,
                )

        return None, ctx

    def _execute_events(
        self,
        action: ActionSubmission,
        ctx: dict[str, Any],
        tick: int,
    ) -> None:
        """Execute events syntactic sugar for an action."""
        action_config = self._config.actions[action.action_type]
        for event_cfg in action_config.events:
            emit = EffectConfig(
                operator="emit_event",
                type=event_cfg.type,
                detail=event_cfg.detail,
                ttl=event_cfg.ttl,
                scope=event_cfg.scope,
                event_target=event_cfg.target,
                push=event_cfg.push,
                highlight=event_cfg.highlight,
            )
            execute_effect(emit, self._store, self._event_log, ctx, tick)

    def process_action(
        self,
        action: ActionSubmission,
        tick: int,
    ) -> ActionResult:
        """Process a single action (sync — dm field skipped)."""
        error, ctx = self._validate_action(action, tick)
        if error is not None or ctx is None:
            return error or ActionResult(success=False, action=action)

        action_config = self._config.actions[action.action_type]

        # Events before effects: observers see events based on pre-effect state.
        # e.g. move events are visible to departure-location observers.
        self._execute_events(action, ctx, tick)

        for effect in action_config.effects:
            execute_effect(effect, self._store, self._event_log, ctx, tick)

        if action_config.dm is not None:
            log.warning("dm_skipped_sync_mode", action=action.action_type)

        return ActionResult(success=True, action=action)

    async def process_mechanical(
        self,
        action: ActionSubmission,
        tick: int,
    ) -> tuple[ActionResult, dict[str, Any] | None]:
        """Phase 1: validate + execute mechanical effects + events.

        Returns (result, dm_info). dm_info is non-None if this action
        needs DM resolution (passed to resolve_dm_async in Phase 2).
        """
        error, ctx = self._validate_action(action, tick)
        if error is not None or ctx is None:
            return error or ActionResult(success=False, action=action), None

        action_config = self._config.actions[action.action_type]

        # Events before effects: observers see events based on pre-effect state.
        self._execute_events(action, ctx, tick)

        for effect in action_config.effects:
            execute_effect(effect, self._store, self._event_log, ctx, tick)

        dm_info = None
        if action_config.dm is not None:
            dm_info = {
                "action": action,
                "dm_config": action_config.dm,
                "ctx": ctx,
                "tick": tick,
            }

        return ActionResult(success=True, action=action), dm_info

    async def resolve_dm_async(self, dm_info: dict[str, Any]) -> None:
        """Phase 2: resolve DM judgment (called in parallel)."""
        from worldseed.engine.dm_resolver import resolve_dm

        if self._dm_provider is None or self._dm_builder is None:
            log.warning(
                "dm_skipped_no_provider",
                action=dm_info["action"].action_type,
            )
            # Emit admin event so dashboard shows why action was skipped
            from worldseed.models.event import Event

            self._event_log.append(
                Event(
                    tick=dm_info["tick"],
                    source="system",
                    detail=(
                        f"Action '{dm_info['action'].action_type}' skipped: "
                        "no DM model configured. "
                        "Set a DM model in lobby or CLI."
                    ),
                    type="dm_skipped",
                    scope="admin",
                    ttl=1,
                )
            )
            return

        await resolve_dm(
            action=dm_info["action"],
            dm_config=dm_info["dm_config"],
            ctx=dm_info["ctx"],
            tick=dm_info["tick"],
            dm_provider=self._dm_provider,
            dm_builder=self._dm_builder,
            store=self._store,
            event_log=self._event_log,
            recorder=self._recorder,
            inbox_manager=self._inbox_manager,
        )

    def emit_fallback_narrative(
        self,
        agent_id: str,
        tick: int,
    ) -> None:
        """Emit fallback narrative when DM fails."""
        from worldseed.engine.dm_resolver import emit_fallback_narrative

        emit_fallback_narrative(
            agent_id,
            tick,
            inbox_manager=self._inbox_manager,
        )

    def process_auto_tick(self, tick: int) -> None:
        """Execute all auto_tick effects."""
        ctx: dict[str, Any] = {
            "agent_id": "",
            "action_params": {},
            "tick": tick,
            "event_log": self._event_log,
            "recorder": self._recorder,
        }
        for auto in self._config.auto_tick:
            if auto.condition is not None:
                if not all(evaluate_precondition(c, self._store, ctx) for c in auto.condition):
                    continue
            for effect in auto.effects:
                execute_effect(effect, self._store, self._event_log, ctx, tick)


def _describe_precondition_failure(
    precond: PreconditionConfig,
    store: StateStore,
    ctx: dict[str, Any],
) -> str:
    """Build human-readable reason from failed precondition with resolved values."""
    from worldseed.dsl.path_resolver import resolve

    try:
        left_raw = precond.left
        right_raw = precond.right
        op = precond.op

        if left_raw is not None and right_raw is not None and op:
            left_val = resolve(left_raw, store, ctx)
            right_val = resolve(right_raw, store, ctx)
            return f"{left_raw}={left_val} {op} {right_raw}={right_val}"

        if precond.operator == "any" and precond.conditions:
            return "No condition matched (all alternatives failed)"

        return "Precondition failed"
    except Exception:
        return "Precondition failed"
