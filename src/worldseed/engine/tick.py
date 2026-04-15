"""Tick Engine — main loop orchestration."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

from worldseed.engine.action_queue import ActionQueue
from worldseed.engine.consequence_scanner import ConsequenceScanner
from worldseed.engine.event_log import EventLog
from worldseed.engine.inbox import InboxManager, InboxWhisper
from worldseed.engine.pending_ops import PendingOpsQueue
from worldseed.engine.perceiver import Perceiver
from worldseed.engine.rules_engine import ActionResult, RulesEngine
from worldseed.engine.state_store import StateStore
from worldseed.models.config_schema import SceneConfig

if TYPE_CHECKING:
    from worldseed.agent_registry import AgentRegistry
    from worldseed.dm.providers.base import DMProvider
    from worldseed.persistence import NullRecorder, RunRecorder


MAX_DM_CALLS_PER_TICK = 10  # rate limit: max parallel DM calls per tick


class TickEngine:
    """Orchestrates one tick: actions, auto_tick, consequence, perceiver, cleanup."""

    def __init__(
        self,
        config: SceneConfig,
        store: StateStore,
        event_log: EventLog,
        action_queue: ActionQueue,
        inbox_manager: InboxManager | None = None,
        dm_provider: DMProvider | None = None,
        recorder: RunRecorder | NullRecorder | None = None,
        registry: AgentRegistry | None = None,
    ) -> None:
        self._config = config
        self._store = store
        self._event_log = event_log
        self._queue = action_queue
        self._tick: int = 0
        self._recorder = recorder
        self._registry = registry
        self._recorded_highlight_ids: set[int] = set()
        self._max_dm_calls = config.scene.max_dm_calls
        self._dm_call_count: int = 0
        self._dm_provider = dm_provider
        self._pending_ops = PendingOpsQueue()

        # Build DM components if provider given
        dm_builder = None
        if dm_provider is not None:
            from worldseed.dm.builder import DMContextBuilder

            dm_builder = DMContextBuilder(
                store,
                event_log,
                config,
            )

        # Phase 2 components
        self._inbox_manager = inbox_manager

        self._dm_builder = dm_builder
        self._rules = RulesEngine(
            config,
            store,
            event_log,
            dm_provider=dm_provider,
            dm_builder=dm_builder,
            recorder=recorder,
            inbox_manager=inbox_manager,
        )
        self._consequence_scanner = ConsequenceScanner(config, store, event_log, recorder=recorder)
        from worldseed.engine.highlight_scanner import HighlightScanner

        self._highlight_scanner = HighlightScanner(
            config,
            store,
            event_log,
            recorder=recorder,
        )
        self._perceiver: Perceiver | None = None
        if inbox_manager is not None:
            perception = config.perception
            self._perceiver = Perceiver(store, event_log, inbox_manager, perception, registry=registry)

    @property
    def tick(self) -> int:
        """Current tick number."""
        return self._tick

    @property
    def dm_call_count(self) -> int:
        """Total DM calls made since engine start."""
        return self._dm_call_count

    @property
    def perceiver(self) -> Perceiver | None:
        """The perceiver instance (if available)."""
        return self._perceiver

    @property
    def pending_ops(self) -> PendingOpsQueue:
        """The pending GM operations queue."""
        return self._pending_ops

    def step(self) -> list[ActionResult]:
        """Process one tick (sync — DM calls skipped)."""
        self._tick += 1

        # 0. Apply queued GM state mutations (tick boundary)
        self._drain_entity_ops()

        # 1. Drain action queue
        actions = self._queue.drain()

        # 2. Process each action
        results = [self._rules.process_action(a, self._tick) for a in actions]

        self._record_results(results)
        # Consequence DM pending ignored in sync mode
        self._post_actions(self._tick)
        return results

    async def step_async(self) -> list[ActionResult]:
        """Process one tick with async DM support.

        Three phases:
          1. All mechanical effects (sequential, fast)
          2. All DM calls (parallel — same tick snapshot)
          3. DM results applied (sequential — causal order)
        """
        self._tick += 1

        # Phase 0: apply queued GM state mutations (tick boundary)
        self._drain_entity_ops()

        actions = self._queue.drain()

        # Phase 1: mechanical effects + validate (sequential, <1ms each)
        dm_pending: list[tuple[ActionResult, dict[str, Any]]] = []
        results: list[ActionResult] = []
        for action in actions:
            result, dm_info = await self._rules.process_mechanical(
                action,
                self._tick,
            )
            results.append(result)
            if dm_info is not None:
                dm_pending.append((result, dm_info))

        # Phase 2: DM calls — group by location to avoid conflicts
        if dm_pending:
            import asyncio
            from collections import defaultdict

            to_resolve = dm_pending[:MAX_DM_CALLS_PER_TICK]
            overflow = dm_pending[MAX_DM_CALLS_PER_TICK:]

            if overflow:
                from structlog import get_logger

                get_logger().warning(
                    "dm_rate_limited",
                    total=len(dm_pending),
                    resolved=len(to_resolve),
                    deferred=len(overflow),
                )
                for _, info in overflow:
                    self._rules.emit_fallback_narrative(
                        info["action"].agent_id,
                        self._tick,
                    )

            # Budget enforcement: skip DM if total calls exceed max_dm_calls
            if self._max_dm_calls is not None:
                budget_remaining = self._max_dm_calls - self._dm_call_count
                if budget_remaining <= 0:
                    for _, info in to_resolve:
                        self._rules.emit_fallback_narrative(
                            info["action"].agent_id,
                            self._tick,
                        )
                    to_resolve = []
                elif budget_remaining < len(to_resolve):
                    # Partial budget — resolve some, fallback rest
                    budget_overflow = to_resolve[budget_remaining:]
                    to_resolve = to_resolve[:budget_remaining]
                    for _, info in budget_overflow:
                        self._rules.emit_fallback_narrative(
                            info["action"].agent_id,
                            self._tick,
                        )

            if to_resolve:
                # Group DM actions by explicit target entity.
                # Same target → sequential (DM sees each result before next).
                # No target or unique target → parallel (independent).
                by_target: dict[str, list[dict[str, Any]]] = defaultdict(list)
                for _, info in to_resolve:
                    target = info["action"].params.get("target", "")
                    if not target:
                        target = f"_agent:{info['action'].agent_id}"
                    by_target[target].append(info)

                async def _resolve_group(infos: list[dict[str, Any]]) -> None:
                    for info in infos:
                        await self._rules.resolve_dm_async(info)
                        self._dm_call_count += 1

                dm_tasks = [_resolve_group(infos) for infos in by_target.values()]
                await asyncio.gather(*dm_tasks)

        # Phase 3: GM resolve commands (sequential, at tick boundary)
        await self._drain_gm_resolves()

        self._record_results(results)
        consequence_dm_pending = self._post_actions(self._tick)

        # Phase 4: Resolve consequence DM calls (if any)
        if consequence_dm_pending and self._dm_provider and self._dm_builder:
            await self._resolve_consequence_dm(consequence_dm_pending)

        return results

    async def _resolve_consequence_dm(self, pending: list[dict[str, Any]]) -> None:
        """Resolve DM calls triggered by consequences."""

        from worldseed.engine.dm_resolver import resolve_consequence_dm

        # Budget enforcement
        if self._max_dm_calls is not None:
            budget = self._max_dm_calls - self._dm_call_count
            if budget <= 0:
                return
            pending = pending[:budget]

        async def _resolve_one(info: dict[str, Any]) -> None:
            assert self._dm_provider is not None
            assert self._dm_builder is not None
            await resolve_consequence_dm(
                consequence_name=info["consequence_name"],
                dm_config=info["dm_config"],
                ctx=info["ctx"],
                tick=info["tick"],
                dm_provider=self._dm_provider,
                dm_builder=self._dm_builder,
                store=self._store,
                event_log=self._event_log,
                recorder=self._recorder,
            )
            self._dm_call_count += 1

        # Run consequence DM calls sequentially (they may cascade)
        for info in pending:
            await _resolve_one(info)

    def _drain_entity_ops(self) -> None:
        """Apply queued entity set/remove operations at tick boundary."""
        for op in self._pending_ops.drain_entity_sets():
            entity = self._store.get(op.entity_id)
            if entity is not None:
                old = entity.get(op.property)
                self._store.update_property(op.entity_id, op.property, op.value)
                if self._recorder is not None:
                    self._recorder.record(
                        "gm_set",
                        self._tick,
                        entity_id=op.entity_id,
                        property=op.property,
                        old=old,
                        new=op.value,
                    )

        for rm in self._pending_ops.drain_entity_removes():
            if self._store.get(rm.entity_id) is not None:
                self._store.remove(rm.entity_id)
                if self._recorder is not None:
                    self._recorder.record("gm_remove", self._tick, entity_id=rm.entity_id)

    async def _drain_gm_resolves(self) -> None:
        """Process pending GM resolve commands."""
        pending = self._pending_ops.drain_gm_resolves()
        if not pending or self._dm_provider is None or self._dm_builder is None:
            return

        from worldseed.engine.dm_resolver import resolve_gm_command

        for op in pending:
            await resolve_gm_command(
                text=op.text,
                tick=self._tick,
                dm_provider=self._dm_provider,
                dm_builder=self._dm_builder,
                store=self._store,
                event_log=self._event_log,
                recorder=self._recorder,
                target_entity_id=op.target_entity_id,
                request_id=op.request_id,
            )

    def _record_results(self, results: list[ActionResult]) -> None:
        """Record action results + notify failures to agent inbox."""
        for result in results:
            if self._recorder is not None:
                action_cfg = self._config.actions.get(
                    result.action.action_type,
                )
                rec_kwargs: dict[str, Any] = {
                    "agent_id": result.action.agent_id,
                    "action_type": result.action.action_type,
                    "params": result.action.params,
                    "success": result.success,
                    "reason": result.reason,
                }
                if result.success and action_cfg is not None and action_cfg.highlight:
                    rec_kwargs["highlight"] = True
                self._recorder.record(
                    "action",
                    self._tick,
                    **rec_kwargs,
                )
            # Emit highlight event for action rejections
            if not result.success and self._event_log is not None:
                from worldseed.models.event import Event

                self._event_log.append(
                    Event(
                        tick=self._tick,
                        type="action_rejected",
                        source=result.action.agent_id,
                        detail=(
                            f"{result.action.agent_id} tried '{result.action.action_type}' but failed: {result.reason}"
                        ),
                        ttl=5,
                        scope="admin",
                        highlight=True,
                    )
                )
            if not result.success and self._inbox_manager is not None:
                inbox = self._inbox_manager.get_or_create(result.action.agent_id)
                inbox.append_whisper(
                    InboxWhisper(
                        tick=self._tick,
                        source="system",
                        detail=(f"Your '{result.action.action_type}' action failed: {result.reason}"),
                        type="action_failed",
                    )
                )

    def _post_actions(self, tick: int) -> list[dict[str, Any]]:
        """Steps 3-7: auto_tick, consequence, perceiver, cleanup, persist.

        Returns any consequence DM pending calls (resolved in step_async).
        """
        # Clear per-tick dedup set.  id() of Event objects can be reused
        # after GC, and the set would grow unbounded otherwise.
        self._recorded_highlight_ids.clear()

        # 3. Run auto_tick effects
        self._rules.process_auto_tick(tick)

        # 4. Consequence scan
        _triggered, consequence_dm_pending = self._consequence_scanner.scan(tick)

        # 4b. Highlight scan (config-defined triggers)
        # Layer 1 highlights record themselves via scanner's recorder.
        self._highlight_scanner.scan(tick)

        # 4c. Record Layer 2 engine highlights to stream.jsonl.
        # These were emitted to EventLog by DSL effects (entity_ops,
        # relationship_ops) and _record_results, but those code paths
        # don't have recorder access. Flush them here.
        if self._recorder is not None:
            for event in self._event_log.get_events(since_tick=tick):
                eid = id(event)
                if event.highlight and event.type != "highlight" and eid not in self._recorded_highlight_ids:
                    self._recorded_highlight_ids.add(eid)
                    self._recorder.record(
                        "highlight",
                        tick,
                        label=event.detail,
                        source=event.type,
                    )

        # 5. Perceiver delivers to inboxes
        if self._perceiver is not None:
            self._perceiver.deliver(tick)

        # 6. Cleanup expired events from EventLog
        self._event_log.cleanup(tick)

        # 7. Persist state to disk (atomic write — API reads from disk only)
        if self._recorder is not None:
            system_ids = set(self._registry.get_system_agents()) if self._registry else set()
            entities = [e.to_full_dict() for e in self._store.all_entities() if e.id not in system_ids]
            characters = {}
            if self._registry is not None:
                characters = {
                    aid: copy.deepcopy(profile.character)
                    for aid, profile in self._registry._profiles.items()
                    if profile.character
                }
            self._recorder.save_state(entities, tick, characters=characters)

        return consequence_dm_pending
