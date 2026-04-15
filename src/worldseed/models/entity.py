"""Entity — a world object with dynamic key-value properties.

Flat dict-like access: entity["stress"], entity.get("location").
Reserved keys 'id' and 'type' are immutable metadata.
All other keys are world state, stored in entity.data dict.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class Entity:
    """A world object: agent, space, resource, object, or concept.

    Access properties: entity["stress"], entity.get("key").
    Raw dict: entity.data  (game state — visible in perception)
    Metadata: entity.id, entity.type (immutable, not in data dict).
    Constraints: entity.constraints (enforcement metadata — engine only).

    Agent identity (character card) is in AgentRegistry, not here.
    """

    id: str
    type: str
    _data: dict[str, Any] = field(default_factory=dict)
    _constraints: dict[str, Any] = field(default_factory=dict)

    def __init__(
        self,
        id: str,
        type: str,
        _data: dict[str, Any] | None = None,
        _constraints: dict[str, Any] | None = None,
    ) -> None:
        self.id = id
        self.type = type
        self._data = _data if _data is not None else {}
        self._constraints = _constraints if _constraints is not None else {}

    def __getitem__(self, key: str) -> Any:
        return self._data[key]

    def __setitem__(self, key: str, value: Any) -> None:
        self._data[key] = value

    def __contains__(self, key: object) -> bool:
        return key in self._data

    def get(self, key: str, default: Any = None) -> Any:
        """Get a property value, or default if missing."""
        return self._data.get(key, default)

    def items(self) -> list[tuple[str, Any]]:
        """All (key, value) pairs."""
        return list(self._data.items())

    def keys(self) -> list[str]:
        """All property keys."""
        return list(self._data.keys())

    def to_dict(self) -> dict[str, Any]:
        """Game data for API / perception / DM context. No engine metadata."""
        return {**self._data, "id": self.id, "type": self.type}

    def to_full_dict(self) -> dict[str, Any]:
        """Full data including engine metadata, for persistence."""
        d = self.to_dict()
        if self._constraints:
            d["constraints"] = self._constraints
        return d

    @property
    def data(self) -> dict[str, Any]:
        """Raw property dict (for deepcopy, nested_get)."""
        return self._data

    @data.setter
    def data(self, value: dict[str, Any]) -> None:
        self._data = value

    @property
    def constraints(self) -> dict[str, Any]:
        """Enforcement metadata (min/max). Engine-only, not in perception."""
        return self._constraints

    @constraints.setter
    def constraints(self, value: dict[str, Any]) -> None:
        self._constraints = value
