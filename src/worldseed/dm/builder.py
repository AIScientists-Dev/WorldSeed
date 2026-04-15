"""DM Context Builder — assembles full world state for DM judgment."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from worldseed.engine.event_log import EventLog
    from worldseed.engine.state_store import StateStore
    from worldseed.models.config_schema import DMConfig, SceneConfig

from worldseed.models.action import ActionSubmission
from worldseed.protocol.dm import DMContext

_RECENT_EVENTS_LOOKBACK = 5

# Default allowed ops for GM resolve — broader than typical action DM
GM_RESOLVE_OPS = [
    "set",
    "increment",
    "decrement",
    "emit_event",
    "create_entity",
    "remove_entity",
]


class DMContextBuilder:
    """Builds DMContext with full world state for DM judgment.

    The DM is omniscient — it sees every entity and recent event.
    No path declarations, no filtering. Everything formatted as
    plain text for LLM comprehension.
    """

    def __init__(
        self,
        store: StateStore,
        event_log: EventLog,
        config: SceneConfig,
    ) -> None:
        self._store = store
        self._event_log = event_log
        self._config = config
        self.language = ""

    def build(self, action: ActionSubmission, dm_config: DMConfig, tick: int) -> DMContext:
        """Build DMContext from full world state + action."""
        # Build target history — what has happened to the target entity
        target = action.params.get("target", "")
        target_history = self._format_target_history(target, tick) if target else ""

        return DMContext(
            action=action,
            world_state=self._format_entities(),
            recent_events=self._format_events(tick),
            target_history=target_history,
            scene_description=self._config.scene.description,
            dm_knowledge=self._config.scene.dm_knowledge,
            hint=dm_config.hint,
            allowed_ops=dm_config.allowed_ops,
            max_effects=dm_config.max_effects,
            language=self.language,
        )

    def build_gm_resolve(
        self,
        text: str,
        tick: int,
        target_entity_id: str | None = None,
    ) -> DMContext:
        """Build DMContext for a GM natural-language resolve command."""
        target_history = ""
        if target_entity_id:
            target_history = self._format_target_history(target_entity_id, tick)

        synthetic_action = ActionSubmission(
            agent_id="gm",
            action_type="gm_resolve",
            params={"command": text},
        )

        return DMContext(
            action=synthetic_action,
            world_state=self._format_entities(),
            recent_events=self._format_events(tick),
            target_history=target_history,
            scene_description=self._config.scene.description,
            hint="",
            allowed_ops=GM_RESOLVE_OPS,
            max_effects=10,
            prompt_mode="gm_resolve",
            language=self.language,
        )

    def _format_entities(self) -> str:
        """Format all entities as readable plain text.

        Groups agents separately from other entities.
        Format per entity:
            entity_id (type):
              key: value
              key: value
        """
        agents: list[str] = []
        others: list[str] = []

        for entity in self._store.all_entities():
            line = f"  {entity.id} ({entity.type}):"
            for k, v in entity.items():
                line += f"\n    {k}: {_format_value(v)}"
            if entity.type == "agent":
                agents.append(line)
            else:
                others.append(line)

        parts: list[str] = []
        if others:
            parts.append("Entities:\n" + "\n".join(others))
        if agents:
            parts.append("Agents:\n" + "\n".join(agents))
        return "\n\n".join(parts)

    def _format_events(self, tick: int) -> str:
        """Format recent events as one-line summaries.

        One line per event: "  [tick N] type (source): detail"
        Chronological order (oldest first).
        """
        since = max(0, tick - _RECENT_EVENTS_LOOKBACK)
        events = self._event_log.get_events(since_tick=since)
        if not events:
            return "  (none)"
        lines: list[str] = []
        for e in events:
            source = f" ({e.source})" if e.source else ""
            lines.append(f"  [tick {e.tick}] {e.type}{source}: {e.detail}")
        return "\n".join(lines)

    def _format_target_history(self, target_id: str, tick: int) -> str:
        """Format recent events involving a specific entity.

        Helps DM understand what has already been done to this entity
        (e.g. "air_filter has been maintained 5 times already").
        """
        all_events = self._event_log.get_events()
        relevant = [e for e in all_events if target_id in e.detail or e.source == target_id]
        if not relevant:
            return ""
        lines = [f"History for {target_id}:"]
        for e in relevant[-10:]:  # last 10 relevant events
            source = f" ({e.source})" if e.source else ""
            lines.append(f"  [tick {e.tick}] {e.type}{source}: {e.detail}")
        return "\n".join(lines)


def _format_value(v: Any) -> str:
    """Format a property value for DM readability."""
    if isinstance(v, dict):
        items = ", ".join(f"{k}: {v2}" for k, v2 in v.items())
        return "{" + items + "}"
    if isinstance(v, list):
        return "[" + ", ".join(str(x) for x in v) + "]"
    return str(v)
