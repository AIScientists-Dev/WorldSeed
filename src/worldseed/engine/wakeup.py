"""Wakeup evaluation — push-based wake from inbox events."""

from __future__ import annotations

from dataclasses import dataclass

from worldseed.engine.inbox import Inbox, InboxManager


@dataclass
class WakeupResult:
    """Result of wakeup evaluation for an agent."""

    agent_id: str
    should_wake: bool
    reason: str = ""


class WakeupEvaluator:
    """Evaluates whether agents should wake based on inbox contents.

    Two triggers:
    1. Inbox contains an event with push=True (from another agent)
    2. Inbox contains a whisper

    Self-caused events are skipped — agent shouldn't wake for its own actions.
    Wake rhythm is controlled by think_interval. OpenClaw collect mode
    handles message queuing on the gateway side.
    """

    def evaluate(self, inbox: Inbox) -> WakeupResult:
        """Evaluate whether an agent should wake."""
        for event in inbox.peek_events():
            if event.source == inbox.agent_id:
                continue
            if event.push:
                return WakeupResult(
                    agent_id=inbox.agent_id,
                    should_wake=True,
                    reason=f"{event.source} {event.type}: {event.detail[:60]}",
                )

        if inbox.has_whispers():
            return WakeupResult(
                agent_id=inbox.agent_id,
                should_wake=True,
                reason="whisper",
            )

        return WakeupResult(
            agent_id=inbox.agent_id,
            should_wake=False,
        )

    def evaluate_all(self, inbox_manager: InboxManager) -> list[WakeupResult]:
        """Evaluate wakeup for all agents."""
        return [self.evaluate(inbox) for inbox in inbox_manager.all_inboxes().values()]
