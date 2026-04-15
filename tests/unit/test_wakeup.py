"""Tests for push-based Wakeup evaluation."""

from __future__ import annotations

from worldseed.engine.inbox import (
    Inbox,
    InboxEvent,
    InboxManager,
    InboxWhisper,
)
from worldseed.engine.wakeup import WakeupEvaluator


def _push_event(tick: int = 1, etype: str = "shout") -> InboxEvent:
    return InboxEvent(
        tick=tick,
        type=etype,
        source="x",
        detail="",
        push=True,
    )


def _event(tick: int = 1, etype: str = "move") -> InboxEvent:
    return InboxEvent(tick=tick, type=etype, source="x", detail="")


class TestWakeup:
    def test_push_event_triggers_wake(self) -> None:
        evaluator = WakeupEvaluator()
        inbox = Inbox("agent1")
        inbox.append_event(_push_event(etype="shout"))
        result = evaluator.evaluate(inbox)
        assert result.should_wake is True
        assert "shout" in result.reason

    def test_non_push_event_no_wake(self) -> None:
        evaluator = WakeupEvaluator()
        inbox = Inbox("agent1")
        inbox.append_event(_event(etype="move"))
        result = evaluator.evaluate(inbox)
        assert result.should_wake is False

    def test_whisper_wakes(self) -> None:
        evaluator = WakeupEvaluator()
        inbox = Inbox("agent1")
        inbox.append_whisper(
            InboxWhisper(
                tick=1,
                source="b",
                detail="hi",
                type="say",
            )
        )
        result = evaluator.evaluate(inbox)
        assert result.should_wake is True
        assert result.reason == "whisper"

    def test_no_trigger(self) -> None:
        evaluator = WakeupEvaluator()
        inbox = Inbox("agent1")
        inbox.append_event(_event(etype="say"))
        result = evaluator.evaluate(inbox)
        assert result.should_wake is False

    def test_dm_wakes_even_with_non_push_events(self) -> None:
        evaluator = WakeupEvaluator()
        inbox = Inbox("agent1")
        inbox.append_event(_event(etype="move"))
        inbox.append_whisper(
            InboxWhisper(
                tick=1,
                source="b",
                detail="hi",
                type="say",
            )
        )
        result = evaluator.evaluate(inbox)
        assert result.should_wake is True
        assert result.reason == "whisper"

    def test_empty_inbox(self) -> None:
        evaluator = WakeupEvaluator()
        inbox = Inbox("agent1")
        result = evaluator.evaluate(inbox)
        assert result.should_wake is False

    def test_mixed_push_and_non_push(self) -> None:
        evaluator = WakeupEvaluator()
        inbox = Inbox("agent1")
        inbox.append_event(_event(tick=1, etype="move"))
        inbox.append_event(_push_event(tick=2, etype="shout"))
        inbox.append_event(_event(tick=3, etype="say"))
        result = evaluator.evaluate(inbox)
        assert result.should_wake is True
        assert "shout" in result.reason

    def test_evaluate_all(self) -> None:
        evaluator = WakeupEvaluator()
        mgr = InboxManager()
        inbox1 = mgr.get_or_create("agent1")
        inbox1.append_event(_push_event(etype="shout"))
        inbox2 = mgr.get_or_create("agent2")
        inbox2.append_event(_event(etype="move"))
        results = evaluator.evaluate_all(mgr)
        assert len(results) == 2
        wake_map = {r.agent_id: r.should_wake for r in results}
        assert wake_map["agent1"] is True
        assert wake_map["agent2"] is False
