"""Intro routes — data for the intro page + character/property editing."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from pydantic import BaseModel

from worldseed.server.routes._shared import _eng, build_intro_data
from worldseed.server.websocket import ConnectionManager


class CharacterUpdateRequest(BaseModel):
    overrides: dict[str, Any]


class PropertyUpdateRequest(BaseModel):
    updates: dict[str, Any]


def create_intro_router(app: FastAPI, ws_manager: ConnectionManager) -> APIRouter:
    router = APIRouter()

    @router.get("/api/intro")
    async def intro_data() -> dict[str, Any]:
        """Return all data needed by the intro page."""
        return build_intro_data(_eng(app))

    @router.patch("/api/agents/{agent_id}/character")
    async def update_agent_character(
        agent_id: str,
        req: CharacterUpdateRequest,
    ) -> dict[str, Any]:
        """Update an agent's character card."""
        engine = _eng(app)
        try:
            updated = engine.update_character(agent_id, req.overrides)
        except KeyError:
            raise HTTPException(404, detail=f"Agent not found: {agent_id}")
        engine.save_state()
        # Notify gateway to rewrite SOUL.md with updated character
        await ws_manager.send_character_updated(agent_id, updated)
        return {"id": agent_id, "character": updated}

    @router.patch("/api/agents/{agent_id}/properties")
    async def update_agent_properties(
        agent_id: str,
        req: PropertyUpdateRequest,
    ) -> dict[str, Any]:
        """Update an agent's world-state properties."""
        engine = _eng(app)
        entity = engine.state.get(agent_id)
        if entity is None:
            raise HTTPException(404, detail=f"Agent not found: {agent_id}")
        for prop, value in req.updates.items():
            engine.state.update_property(agent_id, prop, value)
        engine.save_state()
        return {"id": agent_id, "properties": dict(entity.data)}

    @router.patch("/api/entities/{entity_id}/properties")
    async def update_entity_properties(
        entity_id: str,
        req: PropertyUpdateRequest,
    ) -> dict[str, Any]:
        """Update a non-agent entity's properties."""
        engine = _eng(app)
        entity = engine.state.get(entity_id)
        if entity is None:
            raise HTTPException(404, detail=f"Entity not found: {entity_id}")
        for prop, value in req.updates.items():
            engine.state.update_property(entity_id, prop, value)
        engine.save_state()
        return {"id": entity_id, "properties": dict(entity.data)}

    return router
