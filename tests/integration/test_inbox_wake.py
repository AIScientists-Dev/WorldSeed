"""Test: Inbox/Wake — message content, drain behavior.

Inbox: per-agent mailbox. Wake: notification with perception.
Tests verify:
  - Inbox read() drains events/DMs but keeps state
  - peek() is non-destructive

ZERO HARDCODE: Uses config-driven helpers.
"""

from __future__ import annotations

from worldseed.engine.inbox import (
    Inbox,
    InboxEvent,
    InboxManager,
    InboxSnapshot,
    InboxWhisper,
)


class TestInboxReadDrain:
    """read() drains events/DMs, keeps state."""

    def test_read_returns_events_and_dms(self) -> None:
        inbox = Inbox("agent_1")
        inbox.update_state(
            InboxSnapshot(
                self_state={"prop_a": "val_a"},
                visible_entities={},
                visible_agents={},
            )
        )
        inbox.append_event(InboxEvent(tick=1, type="action_a", source="x", detail="y"))
        inbox.append_whisper(InboxWhisper(tick=1, source="s", detail="d", type="dm"))

        data = inbox.read()
        assert len(data["events"]) == 1
        assert len(data["whispers"]) == 1
        assert data["current_state"] is not None

    def test_read_drains_events_and_dms(self) -> None:
        inbox = Inbox("agent_1")
        inbox.append_event(InboxEvent(tick=1, type="action_a", source="x", detail="y"))
        inbox.append_whisper(InboxWhisper(tick=1, source="s", detail="d", type="dm"))

        inbox.read()  # drain

        data2 = inbox.read()
        assert len(data2["events"]) == 0
        assert len(data2["whispers"]) == 0

    def test_read_keeps_state_snapshot(self) -> None:
        inbox = Inbox("agent_1")
        inbox.update_state(
            InboxSnapshot(
                self_state={"prop_a": "val_a"},
                visible_entities={"resource_1": {"count": 10}},
                visible_agents={},
            )
        )

        inbox.read()  # drain events

        data = inbox.read()
        assert data["current_state"] is not None
        assert data["current_state"].self_state["prop_a"] == "val_a"

    def test_peek_is_nondestructive(self) -> None:
        inbox = Inbox("agent_1")
        inbox.append_event(InboxEvent(tick=1, type="e", source="s", detail="d"))

        peek1 = inbox.peek()
        assert len(peek1["events"]) == 1

        peek2 = inbox.peek()
        assert len(peek2["events"]) == 1  # still there


class TestInboxEviction:
    """Inbox caps prevent unbounded growth."""

    def test_events_evict_oldest_when_over_cap(self) -> None:
        from worldseed.engine.inbox import MAX_INBOX_EVENTS

        inbox = Inbox("agent_1")
        for i in range(MAX_INBOX_EVENTS + 50):
            inbox.append_event(InboxEvent(tick=i, type="e", source="s", detail=f"evt_{i}"))

        peek = inbox.peek()
        assert len(peek["events"]) == MAX_INBOX_EVENTS
        earliest = min(e.tick for e in peek["events"])
        assert earliest == 50, f"Expected oldest at tick 50, got {earliest}"

    def test_dms_evict_oldest_when_over_cap(self) -> None:
        from worldseed.engine.inbox import MAX_INBOX_WHISPERS

        inbox = Inbox("agent_1")
        for i in range(MAX_INBOX_WHISPERS + 10):
            inbox.append_whisper(InboxWhisper(tick=i, source="s", detail=f"dm_{i}", type="t"))

        peek = inbox.peek()
        assert len(peek["whispers"]) == MAX_INBOX_WHISPERS
        earliest = min(m.tick for m in peek["whispers"])
        assert earliest == 10

    def test_within_cap_no_eviction(self) -> None:
        from worldseed.engine.inbox import MAX_INBOX_EVENTS

        inbox = Inbox("agent_1")
        count = min(5, MAX_INBOX_EVENTS)
        for i in range(count):
            inbox.append_event(InboxEvent(tick=i, type="e", source="s", detail="d"))

        assert len(inbox.peek()["events"]) == count

    def test_read_drains_then_cap_resets(self) -> None:
        """After read() drains, new events start fresh."""
        from worldseed.engine.inbox import MAX_INBOX_EVENTS

        inbox = Inbox("agent_1")
        for i in range(MAX_INBOX_EVENTS):
            inbox.append_event(InboxEvent(tick=i, type="e", source="s", detail="d"))

        inbox.read()  # drain
        assert len(inbox.peek()["events"]) == 0

        inbox.append_event(InboxEvent(tick=999, type="e", source="s", detail="d"))
        assert len(inbox.peek()["events"]) == 1


class TestInboxManager:
    def test_get_or_create_idempotent(self) -> None:
        mgr = InboxManager()
        inbox1 = mgr.get_or_create("agent_a")
        inbox2 = mgr.get_or_create("agent_a")
        assert inbox1 is inbox2

    def test_separate_inboxes(self) -> None:
        mgr = InboxManager()
        a = mgr.get_or_create("agent_a")
        b = mgr.get_or_create("agent_b")
        a.append_event(InboxEvent(tick=1, type="e", source="s", detail="d"))
        assert len(b.peek()["events"]) == 0
