"""Action Queue — FIFO queue for agent action submissions."""

from __future__ import annotations

from collections import deque

from worldseed.models.action import ActionSubmission


class ActionQueue:
    """FIFO queue with one-action-per-agent-per-tick enforcement."""

    def __init__(self) -> None:
        self._queue: deque[ActionSubmission] = deque()
        self._acted_this_tick: set[str] = set()

    def submit(self, action: ActionSubmission) -> str | None:
        """Add an action. Returns error string if agent already acted this tick."""
        if action.agent_id in self._acted_this_tick:
            return "You already acted this tick. Wait for the next tick."
        self._acted_this_tick.add(action.agent_id)
        self._queue.append(action)
        return None

    def drain(self) -> list[ActionSubmission]:
        """Remove and return all queued actions. Resets per-tick tracking."""
        actions = list(self._queue)
        self._queue.clear()
        self._acted_this_tick.clear()
        return actions

    def is_empty(self) -> bool:
        """Check if the queue is empty."""
        return len(self._queue) == 0
