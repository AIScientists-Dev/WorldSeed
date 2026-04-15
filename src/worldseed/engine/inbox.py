"""Per-agent Inbox — mailbox for perception delivery."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

MAX_INBOX_EVENTS = 200  # oldest evicted when exceeded
MAX_INBOX_WHISPERS = 50  # oldest evicted when exceeded


@dataclass
class InboxSnapshot:
    """Current world state visible to an agent."""

    self_state: dict[str, Any]
    visible_entities: dict[str, dict[str, Any]]
    visible_agents: dict[str, dict[str, Any]]


@dataclass
class InboxEvent:
    """A world event delivered to an agent's inbox."""

    tick: int
    type: str
    source: str
    detail: str
    push: bool = False

    def to_dict(self) -> dict[str, object]:
        """Serialize to dict."""
        return {
            "tick": self.tick,
            "type": self.type,
            "source": self.source,
            "detail": self.detail,
        }


@dataclass
class InboxWhisper:
    """A directed message to a specific agent."""

    tick: int
    source: str
    detail: str
    type: str

    def to_dict(self) -> dict[str, object]:
        """Serialize to dict."""
        return {
            "tick": self.tick,
            "source": self.source,
            "detail": self.detail,
            "type": self.type,
        }


class Inbox:
    """Per-agent mailbox for perception data."""

    def __init__(self, agent_id: str) -> None:
        self.agent_id = agent_id
        self._current_state: InboxSnapshot | None = None
        self._events: list[InboxEvent] = []
        self._whispers: list[InboxWhisper] = []
        self._last_perceive_tick: int = -1
        self._delivered_event_ids: set[int] = set()  # id() of Event objects

    @property
    def last_perceive_tick(self) -> int:
        """Last tick the Perceiver delivered to this inbox."""
        return self._last_perceive_tick

    @last_perceive_tick.setter
    def last_perceive_tick(self, value: int) -> None:
        self._last_perceive_tick = value

    def update_state(self, snapshot: InboxSnapshot) -> None:
        """Overwrite current state snapshot."""
        self._current_state = snapshot

    def append_event(self, event: InboxEvent) -> None:
        """Add an event to the inbox. Oldest evicted if over cap."""
        self._events.append(event)
        if len(self._events) > MAX_INBOX_EVENTS:
            self._events = self._events[-MAX_INBOX_EVENTS:]

    def append_whisper(self, msg: InboxWhisper) -> None:
        """Add a whisper to the inbox. Oldest evicted if over cap."""
        self._whispers.append(msg)
        if len(self._whispers) > MAX_INBOX_WHISPERS:
            self._whispers = self._whispers[-MAX_INBOX_WHISPERS:]

    def read(self) -> dict[str, Any]:
        """Read inbox contents. Drains events and DMs but keeps state."""
        events = sorted(self._events, key=lambda e: e.tick)
        dms = sorted(self._whispers, key=lambda m: m.tick)
        result: dict[str, Any] = {
            "current_state": self._current_state,
            "events": events,
            "whispers": dms,
        }
        self._events = []
        self._whispers = []
        return result

    def peek(self) -> dict[str, Any]:
        """Peek at inbox contents without draining."""
        return {
            "events": sorted(self._events, key=lambda e: e.tick),
            "whispers": sorted(self._whispers, key=lambda m: m.tick),
            "last_perceive_tick": self._last_perceive_tick,
        }

    def has_whispers(self) -> bool:
        """Check if there are unread whispers."""
        return len(self._whispers) > 0

    def peek_event_types(self) -> list[str]:
        """Return event types without draining."""
        return [e.type for e in self._events]

    def peek_events(self) -> list[InboxEvent]:
        """Return events without draining."""
        return list(self._events)

    def cleanup_expired_events(
        self,
        live_events: set[tuple[int, str, str]],
    ) -> None:
        """Remove events no longer in the live EventLog."""
        self._events = [e for e in self._events if (e.tick, e.type, e.source) in live_events]


class InboxManager:
    """Manages inboxes for all agents."""

    def __init__(self) -> None:
        self._inboxes: dict[str, Inbox] = {}

    def get_or_create(self, agent_id: str) -> Inbox:
        """Get an agent's inbox, creating if needed."""
        if agent_id not in self._inboxes:
            self._inboxes[agent_id] = Inbox(agent_id)
        return self._inboxes[agent_id]

    def all_inboxes(self) -> dict[str, Inbox]:
        """Return all inboxes."""
        return self._inboxes
