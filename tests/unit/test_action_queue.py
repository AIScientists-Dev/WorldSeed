"""Tests for ActionQueue."""

from __future__ import annotations

from worldseed.engine.action_queue import ActionQueue
from worldseed.models import ActionSubmission


class TestActionQueue:
    def test_submit_and_drain_fifo(self) -> None:
        q = ActionQueue()
        a1 = ActionSubmission(agent_id="a", action_type="move")
        a2 = ActionSubmission(agent_id="b", action_type="take")
        a3 = ActionSubmission(agent_id="c", action_type="say")
        q.submit(a1)
        q.submit(a2)
        q.submit(a3)
        result = q.drain()
        assert result == [a1, a2, a3]

    def test_drain_empty(self) -> None:
        q = ActionQueue()
        assert q.drain() == []

    def test_drain_clears(self) -> None:
        q = ActionQueue()
        q.submit(ActionSubmission(agent_id="a", action_type="wait"))
        q.drain()
        assert q.is_empty()
        assert q.drain() == []
