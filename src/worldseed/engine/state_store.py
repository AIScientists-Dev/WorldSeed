"""In-memory State Store — Entity CRUD and queries."""

from __future__ import annotations

from typing import Any

from worldseed.models.entity import Entity


class StateStore:
    """Stores all entities in the world. The single source of truth."""

    def __init__(self) -> None:
        self._entities: dict[str, Entity] = {}
        self._by_type: dict[str, dict[str, Entity]] = {}

    def add(self, entity: Entity) -> None:
        """Add an entity. Raises if id already exists."""
        if entity.id in self._entities:
            raise ValueError(f"Entity '{entity.id}' already exists")
        self._entities[entity.id] = entity
        self._by_type.setdefault(entity.type, {})[entity.id] = entity

    def get(self, entity_id: str) -> Entity | None:
        """Get entity by id, or None if not found."""
        return self._entities.get(entity_id)

    def remove(self, entity_id: str) -> Entity | None:
        """Remove and return entity.

        Stale references in other entities' properties are NOT cleaned.
        This avoids false positives where a non-relationship property
        happens to contain a string matching an entity ID. Preconditions
        should validate target existence if needed.
        """
        entity = self._entities.pop(entity_id, None)
        if entity is not None:
            type_bucket = self._by_type.get(entity.type)
            if type_bucket is not None:
                type_bucket.pop(entity_id, None)
        return entity

    def update_property(
        self,
        entity_id: str,
        prop: str,
        value: Any,
    ) -> tuple[Any, Any] | None:
        """Update a property. Creates it if missing. Returns (old, new) or None.

        Supports nested dot paths: "inventory.food" walks into
        properties["inventory"]["food"], creating intermediate dicts.
        """
        from worldseed.utils.nested import nested_get, nested_set

        entity = self._entities.get(entity_id)
        if entity is None:
            return None
        old_value = nested_get(entity.data, prop)

        # Apply constraints from entity metadata (not game data)
        if entity.constraints and isinstance(value, (int, float)):
            c = entity.constraints.get(prop)
            if isinstance(c, dict):
                if "min" in c:
                    value = max(value, c["min"])
                if "max" in c:
                    value = min(value, c["max"])

        # Prevent IEEE 754 accumulation artifacts from repeated arithmetic.
        # Round floats to 10 decimal places — more than enough precision for
        # game state while eliminating drift like 13.999999999999986 → 14.0.
        if isinstance(value, float):
            value = round(value, 10)

        nested_set(entity.data, prop, value)
        return (old_value, value)

    def query_by_type(self, entity_type: str) -> list[Entity]:
        """Return all entities of a given type. O(1) via secondary index."""
        bucket = self._by_type.get(entity_type)
        return list(bucket.values()) if bucket else []

    def all_entities(self) -> list[Entity]:
        """Return all entities."""
        return list(self._entities.values())
