"""ActionSubmission dataclass — what agents submit to the action queue."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class ActionSubmission:
    """An action submitted by an agent to the Action Queue."""

    agent_id: str
    action_type: str  # matches action name in scene config
    params: dict[str, Any] = field(default_factory=dict)
    tick_submitted: int = 0
