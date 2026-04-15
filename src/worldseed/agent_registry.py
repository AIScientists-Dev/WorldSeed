"""Agent Registry — agent lifecycle, profiles, think_interval, character cards."""

from __future__ import annotations

import copy
from typing import TYPE_CHECKING, Any

import structlog

from worldseed.models.config_schema import AgentConfig
from worldseed.models.entity import Entity

if TYPE_CHECKING:
    from worldseed.engine.state_store import StateStore
    from worldseed.models.config_schema import SceneConfig

log = structlog.get_logger()

_DEFAULT_THINK_INTERVAL = 5


class AgentRegistry:
    """Manages agent registration, profiles, and notify pacing."""

    def __init__(self, config: SceneConfig, state: StateStore) -> None:
        self._config = config
        self._state = state
        self._profiles: dict[str, AgentConfig] = {}
        self._claimed: set[str] = set()
        self._think_intervals: dict[str, int] = {}

    # ------------------------------------------------------------------
    # Registration
    # ------------------------------------------------------------------

    def _ensure_entity_and_profile(
        self,
        agent_id: str,
        properties: dict[str, Any] | None = None,
        character: dict[str, Any] | None = None,
        *,
        omniscient: bool = False,
        system: bool = False,
        wake_on_push: bool = True,
    ) -> None:
        """Create entity + profile if not present. Shared by register() and prepopulate."""
        if self._state.get(agent_id) is None:
            props = copy.deepcopy(properties or {})
            constraints = props.pop("constraints", {})
            self._state.add(
                Entity(
                    id=agent_id,
                    type="agent",
                    _data=props,
                    _constraints=constraints,
                )
            )
        self._profiles[agent_id] = AgentConfig(
            id=agent_id,
            character=copy.deepcopy(character) if character else {},
            omniscient=omniscient,
            system=system,
            wake_on_push=wake_on_push,
        )
        self._think_intervals.setdefault(agent_id, _DEFAULT_THINK_INTERVAL)

    def register(
        self,
        agent_id: str,
        properties: dict[str, Any] | None = None,
        character: dict[str, Any] | None = None,
        *,
        omniscient: bool = False,
        system: bool = False,
        wake_on_push: bool = True,
    ) -> None:
        """Register an agent into the world (entity + profile + claimed)."""
        self._ensure_entity_and_profile(
            agent_id,
            properties,
            character,
            omniscient=omniscient,
            system=system,
            wake_on_push=wake_on_push,
        )
        self._claimed.add(agent_id)
        log.info("agent_registered", agent=agent_id)

    def register_from_config(self) -> None:
        """Fully register all preset agents. Used by tests and sanity_runner."""
        for agent_cfg in self._config.agents:
            if self.is_claimed(agent_cfg.id):
                continue
            props = self.merge_preset_properties(agent_cfg)
            self.register(
                agent_id=agent_cfg.id,
                properties=props,
                character=dict(agent_cfg.character),
                omniscient=agent_cfg.omniscient,
                system=agent_cfg.system,
                wake_on_push=agent_cfg.wake_on_push,
            )

    def prepopulate_agents(self) -> None:
        """Create agent entities + profiles for UI/map, without marking claimed."""
        for agent_cfg in self._config.agents:
            if self._state.get(agent_cfg.id) is not None:
                continue
            self._ensure_entity_and_profile(
                agent_cfg.id,
                self.merge_preset_properties(agent_cfg),
                dict(agent_cfg.character),
                omniscient=agent_cfg.omniscient,
                system=agent_cfg.system,
                wake_on_push=agent_cfg.wake_on_push,
            )

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def get_profile(self, agent_id: str) -> AgentConfig | None:
        """Look up an agent's profile."""
        return self._profiles.get(agent_id)

    def get_characters(self) -> list[dict[str, Any]]:
        """List all characters — preset + dynamically registered.

        System agents (narrator, etc.) are excluded.
        """
        preset_ids = {a.id for a in self._config.agents}
        result = []
        for a in self._config.agents:
            if a.system:
                continue
            # Use in-memory profile (may have intro edits), fallback to config
            profile = self._profiles.get(a.id)
            char = dict(profile.character) if profile else dict(a.character)
            result.append(
                {
                    "id": a.id,
                    "character": char,
                    "claimed": a.id in self._claimed,
                }
            )
        # Include dynamically registered agents not in preset config
        for agent_id, profile in self._profiles.items():
            if agent_id not in preset_ids and not profile.system:
                result.append(
                    {
                        "id": agent_id,
                        "character": dict(profile.character),
                        "claimed": True,
                    }
                )
        return result

    def update_character(self, agent_id: str, overrides: dict[str, Any]) -> dict[str, Any]:
        """Update an agent's character card (in-memory only).

        Merges *overrides* into the existing character dict (shallow update).
        Returns the full updated character dict.
        """
        profile = self._profiles.get(agent_id)
        if profile is None:
            msg = f"Agent not registered: {agent_id}"
            raise KeyError(msg)
        profile.character.update(overrides)
        log.info("character_updated", agent=agent_id, keys=list(overrides.keys()))
        return dict(profile.character)

    def get_registered_agents(self) -> list[str]:
        """List all registered agent IDs."""
        return list(self._claimed)

    def get_system_agents(self) -> list[str]:
        """List IDs of all system agents (hidden from normal agents/frontend)."""
        return [aid for aid, profile in self._profiles.items() if profile.system]

    def expected_agent_ids(self) -> set[str]:
        """Non-system preset agent IDs — the set that must register before tick starts."""
        system = {aid for aid, p in self._profiles.items() if p.system}
        return {a.id for a in self._config.agents if a.id not in system}

    def is_claimed(self, agent_id: str) -> bool:
        """Check if an agent_id has been claimed."""
        return agent_id in self._claimed

    def is_preset(self, agent_id: str) -> bool:
        """Check if agent_id is a preset character in config."""
        return any(a.id == agent_id for a in self._config.agents)

    # ------------------------------------------------------------------
    # Think interval (notify pacing)
    # ------------------------------------------------------------------

    def get_think_interval(self, agent_id: str) -> int:
        """Get agent's think interval (ticks between regular notifies)."""
        return self._think_intervals.get(agent_id, _DEFAULT_THINK_INTERVAL)

    def update_think_interval(self, agent_id: str, interval: int) -> None:
        """Update agent's think interval."""
        self._think_intervals[agent_id] = max(1, min(interval, 100))

    # Notify counter tracking lives in TickRunner (server/tick_runner.py),
    # not here. TickRunner owns the tick loop and notify timing.

    # ------------------------------------------------------------------
    # Property merge
    # ------------------------------------------------------------------

    def merge_preset_properties(self, agent_cfg: AgentConfig) -> dict[str, Any]:
        """Merge template + preset properties. Preset overrides template."""
        base: dict[str, Any] = {}
        if agent_cfg.template and agent_cfg.template in self._config.templates:
            base = dict(self._config.templates[agent_cfg.template].properties)
        base.update(agent_cfg.properties)
        return base

    def merge_create_properties(
        self,
        template_name: str | None = None,
    ) -> dict[str, Any]:
        """Merge template + default_spawn for new custom agents.

        Template properties override default_spawn.
        """
        base = dict(self._config.scene.default_spawn)
        if template_name and template_name in self._config.templates:
            template_props = dict(self._config.templates[template_name].properties)
            for k, v in base.items():
                if k not in template_props:
                    template_props[k] = v
            return template_props
        return base
