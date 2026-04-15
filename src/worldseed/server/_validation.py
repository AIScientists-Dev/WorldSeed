"""Shared validation helpers for REST and WebSocket handlers."""

from __future__ import annotations

from worldseed.world import WorldEngine


def validate_agent(engine: WorldEngine, agent_id: str) -> str | None:
    """Check agent exists. Returns error message or None if valid."""
    entity = engine.state.get(agent_id)
    if entity is None or entity.type != "agent":
        return f"agent '{agent_id}' not found"
    return None
