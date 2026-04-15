"""Protocol data structures for Agent communication.

Pure data — zero logic, zero side effects.
These are the contracts between the world and any agent.

Layer 2 — HTTP API (server/app.py):
  POST /register { agent_id } → { token }
  GET  /perceive?token=xxx   → perception (instant return)
  POST /act { token, action, params } → { queued }
  Server is passive — instant returns, no waiting, no push.

Layer 3 — Connector (connector/):
  base.py      — ConnectorProvider protocol (notify + close)
  websocket.py — push wake via WebSocket to OpenClaw gateway
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AgentPerception:
    """What an agent can see — typed version of Inbox.read()."""

    self_state: dict[str, Any]
    nearby_entities: dict[str, dict[str, Any]]
    nearby_agents: dict[str, dict[str, Any]]
    events: list[dict[str, Any]]
    whispers: list[dict[str, Any]]
    action_options: dict[str, dict[str, Any]] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to a plain dict. Single source of truth for REST + WS."""
        return {
            "self_state": self.self_state,
            "nearby_entities": self.nearby_entities,
            "nearby_agents": self.nearby_agents,
            "events": self.events,
            "whispers": self.whispers,
            "action_options": self.action_options,
        }


def _filter_description(
    entities: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    """Remove 'description' field from entity property dicts."""
    return {eid: {k: v for k, v in props.items() if k != "description"} for eid, props in entities.items()}


def build_perception(
    inbox_data: dict[str, Any],
    action_options: dict[str, dict[str, Any]],
) -> AgentPerception:
    """Convert Inbox.read() output to AgentPerception.

    Single source of truth — used by both server/app.py
    and agent/runner.py. Change the serialization here,
    it updates everywhere.
    """
    state = inbox_data.get("current_state")
    raw_entities = dict(state.visible_entities) if state else {}
    return AgentPerception(
        self_state=(dict(state.self_state) if state else {}),
        nearby_entities=_filter_description(raw_entities),
        nearby_agents=(dict(state.visible_agents) if state else {}),
        events=[e.to_dict() for e in inbox_data.get("events", [])],
        whispers=[m.to_dict() for m in inbox_data.get("whispers", [])],
        action_options=action_options,
    )


@dataclass
class AgentAction:
    """What an agent decides to do."""

    thought: str
    action_type: str
    params: dict[str, Any] = field(default_factory=dict)
    think_interval: int = 5
    warning: str | None = None  # set when action was converted (e.g. unknown → attempt)
