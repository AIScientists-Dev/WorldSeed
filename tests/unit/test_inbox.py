"""Tests for Inbox data structure."""

from __future__ import annotations

from worldseed.engine.inbox import (
    Inbox,
    InboxEvent,
    InboxManager,
    InboxSnapshot,
    InboxWhisper,
)


class TestInbox:
    def test_inbox_update_state_overwrites(self) -> None:
        inbox = Inbox("agent1")
        snap1 = InboxSnapshot(self_state={"hp": 10}, visible_entities={}, visible_agents={})
        snap2 = InboxSnapshot(self_state={"hp": 5}, visible_entities={}, visible_agents={})
        inbox.update_state(snap1)
        inbox.update_state(snap2)
        result = inbox.read()
        assert result["current_state"].self_state == {"hp": 5}

    def test_inbox_events_accumulate(self) -> None:
        inbox = Inbox("agent1")
        for i in range(3):
            inbox.append_event(InboxEvent(tick=i, type="move", source="a", detail=f"ev{i}"))
        result = inbox.read()
        assert len(result["events"]) == 3
        result2 = inbox.read()
        assert len(result2["events"]) == 0

    def test_inbox_whispers_persist_until_read(self) -> None:
        inbox = Inbox("agent1")
        inbox.append_whisper(InboxWhisper(tick=1, source="b", detail="hi", type="say"))
        inbox.append_whisper(InboxWhisper(tick=2, source="c", detail="hey", type="say"))
        result = inbox.read()
        assert len(result["whispers"]) == 2
        result2 = inbox.read()
        assert len(result2["whispers"]) == 0

    def test_inbox_events_sorted_by_tick(self) -> None:
        inbox = Inbox("agent1")
        inbox.append_event(InboxEvent(tick=5, type="a", source="x", detail=""))
        inbox.append_event(InboxEvent(tick=3, type="b", source="x", detail=""))
        inbox.append_event(InboxEvent(tick=7, type="c", source="x", detail=""))
        result = inbox.read()
        ticks = [e.tick for e in result["events"]]
        assert ticks == [3, 5, 7]

    def test_inbox_read_drains_events_and_dms_but_keeps_state(self) -> None:
        inbox = Inbox("agent1")
        snap = InboxSnapshot(self_state={"hp": 10}, visible_entities={}, visible_agents={})
        inbox.update_state(snap)
        inbox.append_event(InboxEvent(tick=1, type="a", source="x", detail=""))
        inbox.append_whisper(InboxWhisper(tick=1, source="b", detail="hi", type="say"))
        inbox.read()
        result = inbox.read()
        assert len(result["events"]) == 0
        assert len(result["whispers"]) == 0
        assert result["current_state"] is not None
        assert result["current_state"].self_state == {"hp": 10}

    def test_inbox_has_whispers(self) -> None:
        inbox = Inbox("agent1")
        assert inbox.has_whispers() is False
        inbox.append_whisper(InboxWhisper(tick=1, source="b", detail="hi", type="say"))
        assert inbox.has_whispers() is True
        inbox.read()
        assert inbox.has_whispers() is False

    def test_inbox_peek_event_types(self) -> None:
        inbox = Inbox("agent1")
        inbox.append_event(InboxEvent(tick=1, type="move", source="x", detail=""))
        inbox.append_event(InboxEvent(tick=2, type="say", source="x", detail=""))
        types = inbox.peek_event_types()
        assert types == ["move", "say"]
        # Verify no drain
        assert len(inbox.peek_event_types()) == 2

    def test_inbox_cleanup_expired_events(self) -> None:
        inbox = Inbox("agent1")
        inbox.append_event(InboxEvent(tick=1, type="move", source="a", detail=""))
        inbox.append_event(InboxEvent(tick=2, type="say", source="b", detail=""))
        inbox.append_event(InboxEvent(tick=3, type="take", source="c", detail=""))
        # Only keep tick=2 say event
        live = {(2, "say", "b")}
        inbox.cleanup_expired_events(live)
        result = inbox.read()
        assert len(result["events"]) == 1
        assert result["events"][0].type == "say"


class TestInboxManager:
    def test_inbox_manager_get_or_create(self) -> None:
        mgr = InboxManager()
        inbox1 = mgr.get_or_create("agent1")
        inbox2 = mgr.get_or_create("agent1")
        assert inbox1 is inbox2
        inbox3 = mgr.get_or_create("agent2")
        assert inbox3 is not inbox1
