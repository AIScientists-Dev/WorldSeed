"""Pending operations queue — tick-boundary queuing for GM state mutations."""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass
from typing import Any
from uuid import uuid4


@dataclass
class PendingEntitySet:
    """A GM entity property change waiting for tick boundary."""

    entity_id: str
    property: str
    value: Any
    tick_submitted: int


@dataclass
class PendingEntityRemove:
    """A GM entity removal waiting for tick boundary."""

    entity_id: str
    tick_submitted: int


@dataclass
class PendingGMResolve:
    """A GM natural-language command waiting for DM resolution."""

    text: str
    target_entity_id: str | None
    tick_submitted: int
    request_id: str


class PendingOpsQueue:
    """Queue for GM operations that must execute at tick boundaries."""

    def __init__(self) -> None:
        self._entity_sets: deque[PendingEntitySet] = deque()
        self._entity_removes: deque[PendingEntityRemove] = deque()
        self._gm_resolves: deque[PendingGMResolve] = deque()

    def enqueue_entity_set(self, entity_id: str, prop: str, value: Any, tick: int) -> None:
        """Enqueue a property change."""
        self._entity_sets.append(PendingEntitySet(entity_id=entity_id, property=prop, value=value, tick_submitted=tick))

    def enqueue_entity_remove(self, entity_id: str, tick: int) -> None:
        """Enqueue an entity removal."""
        self._entity_removes.append(PendingEntityRemove(entity_id=entity_id, tick_submitted=tick))

    def enqueue_gm_resolve(
        self,
        text: str,
        tick: int,
        target_entity_id: str | None = None,
    ) -> str:
        """Enqueue a GM resolve command. Returns request_id."""
        request_id = uuid4().hex[:8]
        self._gm_resolves.append(
            PendingGMResolve(
                text=text,
                target_entity_id=target_entity_id,
                tick_submitted=tick,
                request_id=request_id,
            )
        )
        return request_id

    def drain_entity_sets(self) -> list[PendingEntitySet]:
        """Drain all pending entity set operations."""
        items = list(self._entity_sets)
        self._entity_sets.clear()
        return items

    def drain_entity_removes(self) -> list[PendingEntityRemove]:
        """Drain all pending entity remove operations."""
        items = list(self._entity_removes)
        self._entity_removes.clear()
        return items

    def drain_gm_resolves(self) -> list[PendingGMResolve]:
        """Drain all pending GM resolve commands."""
        items = list(self._gm_resolves)
        self._gm_resolves.clear()
        return items

    def has_pending(self) -> bool:
        """Check if there are any pending operations."""
        return bool(self._entity_sets or self._entity_removes or self._gm_resolves)
