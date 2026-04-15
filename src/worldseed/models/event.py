"""Event dataclass — things that happened in the world."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Event:
    """An ephemeral record of something that happened."""

    tick: int
    type: str  # free string, defined per scene
    source: str  # entity_id of actor
    detail: str  # what happened
    ttl: int | str  # ticks until expiry, or "permanent"
    scope: str  # free string, defined per scene ("global", "target_only", etc.)
    target: str | None = None  # target agent for directed events
    push: bool = False  # wake agents immediately
    highlight: bool = False  # mark as important for observer dashboard

    def to_dict(self) -> dict[str, object]:
        """Serialize to dict. Single source of truth for event serialization."""
        d: dict[str, object] = {
            "tick": self.tick,
            "type": self.type,
            "source": self.source,
            "detail": self.detail,
            "scope": self.scope,
        }
        if self.highlight:
            d["highlight"] = True
        return d

    def __post_init__(self) -> None:
        if isinstance(self.ttl, str) and self.ttl != "permanent":
            msg = f"Event ttl must be non-negative int or 'permanent', got '{self.ttl}'"
            raise ValueError(msg)
        if isinstance(self.ttl, int) and self.ttl < 0:
            msg = f"Event ttl must be non-negative, got {self.ttl}"
            raise ValueError(msg)
