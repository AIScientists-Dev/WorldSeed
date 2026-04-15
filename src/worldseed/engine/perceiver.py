"""Perceiver — DSL-based visibility filtering and inbox delivery."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

import structlog

from worldseed.dsl.preconditions import evaluate as evaluate_precondition
from worldseed.engine.inbox import (
    InboxEvent,
    InboxManager,
    InboxSnapshot,
    InboxWhisper,
)

if TYPE_CHECKING:
    from worldseed.agent_registry import AgentRegistry
    from worldseed.engine.event_log import EventLog
    from worldseed.engine.state_store import StateStore
    from worldseed.models.config_schema import PerceptionConfig, PreconditionConfig
    from worldseed.models.event import Event

log = structlog.get_logger()


class Perceiver:
    """Filters world state and events per agent, delivers to inboxes.

    Visibility and event scope are determined by DSL expressions from
    Scene Config. The Perceiver does not hardcode any property names,
    relationship types, or entity types. "agent" is the only built-in
    concept. "global" and "target_only" are the only built-in scopes.
    """

    def __init__(
        self,
        store: StateStore,
        event_log: EventLog,
        inbox_manager: InboxManager,
        perception: PerceptionConfig,
        registry: AgentRegistry | None = None,
    ) -> None:
        self._store = store
        self._event_log = event_log
        self._inbox_manager = inbox_manager
        self._visibility_rules = perception.visibility
        self._event_scopes = perception.event_scopes
        self._hidden_properties = set(perception.hidden_properties)
        self._registry = registry

    def deliver(self, tick: int) -> None:
        """Deliver perception to all agents."""
        agents = self._store.query_by_type("agent")
        all_entities = self._store.all_entities()

        # Compute live event IDs once (for pruning delivered_ids).
        # Hoisted out of per-agent loop to avoid O(agents) full scans.
        live_ids = {id(e) for e in self._event_log.get_events()}

        for agent in agents:
            inbox = self._inbox_manager.get_or_create(agent.id)
            omniscient = self._is_omniscient(agent.id)

            # 1. Build and deliver snapshot
            snapshot = self._build_snapshot(agent, tick, all_entities, omniscient)
            inbox.update_state(snapshot)

            # 2. Filter and deliver events
            since = max(0, inbox.last_perceive_tick)
            events = self._event_log.get_events(since_tick=since)

            for event in events:
                eid = id(event)
                if eid in inbox._delivered_event_ids:
                    continue

                # Admin-scoped events are dashboard-only — no agent ever sees
                # them, not even omniscient ones.
                if event.scope == "admin":
                    continue

                # System agents (e.g. narrator) skip their own events to avoid
                # self-referencing — they track progress via properties instead.
                if event.source == agent.id and self._is_system(agent.id):
                    inbox._delivered_event_ids.add(eid)
                    continue

                if omniscient or self._agent_can_perceive_event(agent, event, tick):
                    ev_source = "" if "source" in self._hidden_properties else event.source
                    inbox.append_event(
                        InboxEvent(
                            tick=event.tick,
                            type=event.type,
                            source=ev_source,
                            detail=event.detail,
                            push=getattr(event, "push", False),
                        )
                    )

                if event.target == agent.id:
                    inbox.append_whisper(
                        InboxWhisper(
                            tick=event.tick,
                            source=event.source,
                            detail=event.detail,
                            type=event.type,
                        )
                    )

                inbox._delivered_event_ids.add(eid)

            # Prune delivered IDs for expired events
            inbox._delivered_event_ids &= live_ids

            inbox.last_perceive_tick = tick

            # Perceive records removed from stream — too noisy (tick × agents).
            # Perception data is in wakeup records instead.

    def _build_snapshot(
        self,
        agent: Any,
        tick: int,
        all_entities: list[Any],
        omniscient: bool = False,
    ) -> InboxSnapshot:
        """Build a perception snapshot for an agent."""
        self_state = dict(agent.data)

        visible_entities: dict[str, dict[str, Any]] = {}
        visible_agents: dict[str, dict[str, Any]] = {}

        # Reuse ctx, mutate only the entity field per iteration
        ctx = self._build_ctx(
            agent.id,
            tick,
            observer=agent.id,
            entity="",
        )
        for entity in all_entities:
            if entity.id == agent.id:
                continue
            # Hide system agents from non-system observers
            if entity.type == "agent" and self._is_system(entity.id) and not self._is_system(agent.id):
                continue
            if not omniscient:
                ctx["action_params"]["entity"] = entity.id
                if not self._all_rules_pass(
                    self._visibility_rules,
                    ctx,
                    "visibility_rule_eval_failed",
                    observer=agent.id,
                    entity=entity.id,
                ):
                    continue
            if omniscient:
                props = dict(entity.data)
            else:
                props = self._filter_hidden(dict(entity.data))
            if entity.type == "agent":
                visible_agents[entity.id] = props
            else:
                visible_entities[entity.id] = props

        return InboxSnapshot(
            self_state=self_state,
            visible_entities=visible_entities,
            visible_agents=visible_agents,
        )

    def build_agent_view(
        self,
        agent_id: str,
        tick: int,
    ) -> dict[str, Any]:
        """Build a real-time world view for an agent (read-only, no side effects).

        Returns self_state, visible_entities, visible_agents, and
        filtered events. Used by dashboard inspector and enum resolution.
        """
        agent = self._store.get(agent_id)
        if agent is None:
            return {
                "self_state": {},
                "visible_entities": {},
                "visible_agents": {},
                "events": [],
            }
        all_entities = self._store.all_entities()
        omniscient = self._is_omniscient(agent_id)
        snap = self._build_snapshot(agent, tick, all_entities, omniscient)

        # Filter events visible to this agent
        events = self._event_log.get_events()
        visible_events = [e.to_dict() for e in events if omniscient or self._agent_can_perceive_event(agent, e, tick)]

        return {
            "self_state": dict(snap.self_state),
            "visible_entities": dict(snap.visible_entities),
            "visible_agents": dict(snap.visible_agents),
            "events": visible_events,
        }

    def _agent_can_perceive_event(
        self,
        agent: Any,
        event: Event,
        tick: int,
    ) -> bool:
        """Check if an agent can perceive an event based on scope.

        Built-in scopes:
          "global" — all agents receive
          "target_only" — only event.target receives
          "admin" — no agents receive (dashboard/GM-view only)
        Custom scopes: evaluated via DSL rules from config.event_scopes
        Undeclared scopes: default to global (deliver to all).
        """
        match event.scope:
            case "admin":
                return False
            case "global":
                return True
            case "target_only":
                return bool(event.target == agent.id)
            case _:
                scope_config = self._event_scopes.get(event.scope)
                if scope_config is None or not scope_config.rules:
                    return True  # undeclared scope = global
                ctx = self._build_ctx(
                    agent.id,
                    tick,
                    observer=agent.id,
                    event_source=event.source,
                )
                return self._all_rules_pass(
                    scope_config.rules,
                    ctx,
                    "event_scope_rule_eval_failed",
                    agent=agent.id,
                    scope=event.scope,
                )

    def _is_omniscient(self, agent_id: str) -> bool:
        """Check if agent has omniscient flag in its AgentConfig."""
        if self._registry is None:
            return False
        profile = self._registry.get_profile(agent_id)
        return profile is not None and profile.omniscient

    def _is_system(self, agent_id: str) -> bool:
        """Check if agent is a system agent (hidden from other agents)."""
        if self._registry is None:
            return False
        profile = self._registry.get_profile(agent_id)
        return profile is not None and profile.system

    # -- shared helpers --

    @staticmethod
    def _build_ctx(
        agent_id: str,
        tick: int,
        **params: Any,
    ) -> dict[str, Any]:
        """Build a DSL evaluation context."""
        return {
            "agent_id": agent_id,
            "action_params": params,
            "tick": tick,
        }

    def _all_rules_pass(
        self,
        rules: list[PreconditionConfig],
        ctx: dict[str, Any],
        error_label: str,
        **log_kwargs: Any,
    ) -> bool:
        """Evaluate a list of DSL rules. All must pass."""
        if not rules:
            return True
        for rule in rules:
            try:
                if not evaluate_precondition(rule, self._store, ctx):
                    return False
            except Exception:
                log.error(error_label, exc_info=True, **log_kwargs)
                return False
        return True

    def _filter_hidden(
        self,
        properties: dict[str, Any],
    ) -> dict[str, Any]:
        """Filter out hidden properties."""
        return {k: v for k, v in properties.items() if k not in self._hidden_properties}
