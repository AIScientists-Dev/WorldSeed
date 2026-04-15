"""Generic test helpers — config-driven, zero hardcode.

All test data is extracted dynamically from SceneConfig.
No scene-specific strings (entity names, action names, property names) appear here.
Works for any config in configs/.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from worldseed.dm.providers.mock import MockDMProvider
from worldseed.models.config_schema import SceneConfig
from worldseed.scene.config import load_config
from worldseed.world import WorldEngine

CONFIGS_DIR = Path(__file__).parent.parent / "configs"

# Chaos configs are intentionally degenerate (empty worlds, feedback loops).
# They test engine robustness but don't have standard entity/agent structure.
CHAOS_PREFIX = "chaos_"


def all_config_paths() -> list[Path]:
    """Return all YAML config paths in configs/."""
    return sorted(CONFIGS_DIR.glob("*.yaml"))


def standard_config_paths() -> list[Path]:
    """Return non-chaos config paths (have agents + entities + actions)."""
    return [p for p in all_config_paths() if not p.stem.startswith(CHAOS_PREFIX)]


def load_any_config(path: Path) -> SceneConfig:
    """Load a scene config from path."""
    return load_config(path)


def make_world(config_path: Path, *, register_agents: bool = True) -> WorldEngine:
    """Create a WorldEngine with mock DM, optionally registering all agents."""
    engine = WorldEngine(config_path=config_path, dm_provider=MockDMProvider())
    if register_agents:
        engine.register_from_config()
    return engine


class ConfigIntrospector:
    """Extract test-relevant data from any SceneConfig.

    Zero hardcoding: all names, types, properties are read from config.
    """

    def __init__(self, config: SceneConfig) -> None:
        self.config = config

    @property
    def scene_id(self) -> str:
        return self.config.scene.id

    @property
    def entity_ids(self) -> list[str]:
        return [e.id for e in self.config.entities]

    @property
    def agent_ids(self) -> list[str]:
        return [a.id for a in self.config.agents]

    @property
    def action_names(self) -> list[str]:
        return list(self.config.actions.keys())

    @property
    def hidden_properties(self) -> list[str]:
        return list(self.config.perception.hidden_properties)

    @property
    def entity_types(self) -> set[str]:
        return {e.type for e in self.config.entities}

    def entities_with_constraints(self) -> list[dict[str, Any]]:
        """Return entities that have constraints defined in config."""
        result = []
        for e in self.config.entities:
            constraints = e.properties.get("constraints")
            if constraints and isinstance(constraints, dict):
                result.append(
                    {
                        "id": e.id,
                        "type": e.type,
                        "constraints": constraints,
                        "properties": {k: v for k, v in e.properties.items() if k != "constraints"},
                    }
                )
        return result

    def agents_with_hidden_props(self) -> list[dict[str, Any]]:
        """Return agents that have hidden properties set in config."""
        hidden = set(self.config.perception.hidden_properties)
        if not hidden:
            return []
        result = []
        for a in self.config.agents:
            found = {k: v for k, v in a.properties.items() if k in hidden}
            if found:
                result.append({"id": a.id, "hidden": found})
        return result

    def actions_with_params(self) -> list[dict[str, Any]]:
        """Return actions that have required params."""
        result = []
        for name, act in self.config.actions.items():
            params = [{"name": p.name, "type": p.type, "required": p.required} for p in act.params if p.required]
            if params:
                result.append({"name": name, "params": params})
        return result

    def paramless_actions(self) -> list[str]:
        """Return action names that have no required params (safe to submit)."""
        result = []
        for name, act in self.config.actions.items():
            if not any(p.required for p in act.params):
                result.append(name)
        return result

    def has_consequences(self) -> bool:
        return bool(self.config.consequences)

    def has_auto_tick(self) -> bool:
        return bool(self.config.auto_tick)


def read_snapshot(path: Path) -> list[dict[str, Any]]:
    """Read a snapshot/state JSON file. Handles both wrapped and flat formats."""
    data = json.loads(path.read_text())
    if isinstance(data, dict) and "entities" in data:
        return data["entities"]
    return data


def assert_no_metadata_leak(data: Any, path: str = "") -> None:
    """Assert no engine metadata (constraints) leaks into perception data.

    Recursively checks all nested dicts. Fails with descriptive message.
    """
    if isinstance(data, dict):
        assert "constraints" not in data, f"Engine metadata 'constraints' found at {path or 'root'}"
        # _constraints is internal — never in serialized data
        assert "_constraints" not in data, f"Internal field '_constraints' found at {path or 'root'}"
        for key, value in data.items():
            assert_no_metadata_leak(value, f"{path}.{key}" if path else key)
    elif isinstance(data, list):
        for i, item in enumerate(data):
            assert_no_metadata_leak(item, f"{path}[{i}]")


def assert_hidden_not_visible(
    perception: dict[str, Any],
    hidden_properties: list[str],
) -> None:
    """Assert hidden properties don't leak into OTHER entities' perception.

    Design: agents CAN see their own hidden properties (self_state),
    but hidden properties must NOT appear in nearby_entities or nearby_agents.
    """
    hidden = set(hidden_properties)
    if not hidden:
        return

    # self_state is intentionally NOT checked — agents see their own hidden props

    # Check nearby_entities (support both old and new field names)
    entities = perception.get("nearby_entities", perception.get("visible_entities", {}))
    for eid, eprops in entities.items():
        for prop in hidden:
            assert prop not in eprops, f"Hidden property '{prop}' visible in entity '{eid}'"

    # Check nearby_agents (support both old and new field names)
    agents = perception.get("nearby_agents", perception.get("visible_agents", {}))
    for aid, aprops in agents.items():
        for prop in hidden:
            assert prop not in aprops, f"Hidden property '{prop}' visible in agent '{aid}'"
