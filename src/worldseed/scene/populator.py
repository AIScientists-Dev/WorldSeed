"""Populator — converts SceneConfig world entities into runtime Entity objects.

Only handles world entities (spaces, resources, objects, concepts).
Agents are registered via WorldEngine.register_agent() — same path
for pre-defined (YAML) and external (HTTP /register) agents.
"""

from __future__ import annotations

import copy

from worldseed.engine.state_store import StateStore
from worldseed.models.config_schema import SceneConfig
from worldseed.models.entity import Entity


def populate(config: SceneConfig, store: StateStore) -> None:
    """Populate a StateStore with world entities only.

    Agents are registered via WorldEngine.register_agent().
    Tests that need agents should use WorldEngine, not populate().
    """
    for entity_cfg in config.entities:
        props = copy.deepcopy(dict(entity_cfg.properties))
        constraints = props.pop("constraints", {})
        entity = Entity(
            id=entity_cfg.id,
            type=entity_cfg.type,
            _data=props,
            _constraints=constraints,
        )
        store.add(entity)
