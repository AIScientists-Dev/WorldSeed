"""Mock connector — records notifications for testing."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class NotifyRecord:
    """A recorded notification call."""

    agent_id: str
    reason: str
    perception: dict[str, Any] | None = field(default=None, repr=False)


class MockConnector:
    """Records notification calls instead of sending HTTP requests."""

    def __init__(self) -> None:
        self.notifications: list[NotifyRecord] = []

    async def notify(self, agent_id: str, reason: str, perception: dict[str, Any] | None = None) -> None:
        """Record the notification."""
        self.notifications.append(NotifyRecord(agent_id=agent_id, reason=reason, perception=perception))

    async def close(self) -> None:
        """Nothing to clean up."""
