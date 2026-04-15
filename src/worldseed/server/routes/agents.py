"""Agent routes: register, perceive, act, characters, connect, WS."""

from __future__ import annotations

import secrets
from typing import Any

import structlog
from fastapi import APIRouter, FastAPI, HTTPException, WebSocket

from worldseed.server.models import ActRequest, ActResponse, RegisterRequest
from worldseed.server.routes._shared import (
    _eng,
    _require_agent,
    _resolve_agent,
    agent_tokens,
    tokens,
)
from worldseed.server.websocket import ConnectionManager, handle_ws

log = structlog.get_logger()


def create_agents_router(app: FastAPI, ws_manager: ConnectionManager) -> APIRouter:
    router = APIRouter()

    @router.get("/characters")
    async def characters() -> list[dict[str, Any]]:
        return _eng(app).get_characters()

    @router.post("/register")
    async def register(req: RegisterRequest) -> dict[str, Any]:
        eng = _eng(app)
        reg = eng.registry
        is_new = False

        if req.mode == "claim":
            preset = None
            for a in eng.config.agents:
                if a.id == req.agent_id:
                    preset = a
                    break
            if preset is None:
                raise HTTPException(404, detail=f"Preset agent '{req.agent_id}' not found")
            if reg.is_claimed(req.agent_id):
                profile = eng.get_agent_profile(req.agent_id)
                result_character = dict(profile.character) if profile else dict(preset.character)
            else:
                is_new = True
                props = reg.merge_preset_properties(preset)
                eng.register_agent(
                    agent_id=req.agent_id,
                    properties=props,
                    character=dict(preset.character),
                    omniscient=preset.omniscient,
                    system=preset.system,
                )
                result_character = dict(preset.character)

        elif req.mode == "create":
            if reg.is_preset(req.agent_id):
                raise HTTPException(409, detail=f"'{req.agent_id}' conflicts with preset")
            if reg.is_claimed(req.agent_id):
                profile = reg.get_profile(req.agent_id)
                result_character = dict(profile.character) if profile else {}
            else:
                is_new = True
                if req.template:
                    if req.template not in eng.config.templates:
                        raise HTTPException(
                            404,
                            detail=f"Template '{req.template}' not found",
                        )
                props = reg.merge_create_properties(template_name=req.template)
                eng.register_agent(
                    agent_id=req.agent_id,
                    properties=props,
                    character=dict(req.character),
                )
                result_character = dict(req.character)
        else:
            raise HTTPException(400, detail=f"Invalid mode '{req.mode}'.")

        old_token = agent_tokens.get(req.agent_id)
        if old_token is not None:
            tokens.pop(old_token, None)
        token = secrets.token_urlsafe(32)
        tokens[token] = req.agent_id
        agent_tokens[req.agent_id] = token

        if is_new:
            await ws_manager.send_agent_registered(req.agent_id, result_character, eng.config.scene.id)

        return {
            "token": token,
            "agent_id": req.agent_id,
            "scene": eng.config.scene.id,
            "character": result_character,
        }

    @router.get("/perceive")
    async def perceive(token: str | None = None, agent_id: str | None = None) -> dict[str, Any]:
        eng = _eng(app)
        resolved = _resolve_agent(token, agent_id, tokens)
        _require_agent(eng, resolved)
        p = eng.perceive(resolved)
        result = p.to_dict()
        result["tick"] = eng.tick
        return result

    @router.post("/act", response_model=ActResponse)
    async def act(req: ActRequest) -> ActResponse:
        from worldseed.engine.rules_engine import ActionResult

        eng = _eng(app)
        resolved = _resolve_agent(req.token, req.agent_id, tokens)
        _require_agent(eng, resolved)
        result = eng.submit(resolved, req.action, req.params)
        if isinstance(result, ActionResult):
            # Mechanical action executed immediately
            if not result.success:
                raise HTTPException(422, detail=result.reason)
        elif isinstance(result, str):
            # Queue rejection (e.g., already acted this tick)
            raise HTTPException(429, detail=result)
        # else: None = DM action queued successfully
        if req.think_interval is not None:
            eng.set_think_interval(resolved, req.think_interval)
        return ActResponse(queued=True, tick=eng.tick)

    @router.post("/api/agents/connect")
    async def connect_agents() -> dict[str, Any]:
        """Broadcast send_initial_wakes to all connected gateways.

        Called from dashboard "Connect Agents" button. Sends a single
        {type: "send_initial_wakes"} message to every gateway. Each
        gateway then dispatches initial wake to its agents locally.
        """
        sent = await ws_manager.broadcast({"type": "send_initial_wakes"})
        if sent == 0:
            raise HTTPException(
                503,
                detail="No gateway connected. Start openclaw gateway first.",
            )

        return {"status": "ok", "gateways_notified": sent}

    return router


def register_websocket(app: FastAPI, ws_manager: ConnectionManager) -> None:
    """Register WebSocket endpoint directly on the app (not via APIRouter)."""

    @app.websocket("/ws")
    async def websocket_endpoint(ws: WebSocket) -> None:
        engine = app.state.engine
        if engine is None:
            # Lobby mode: no engine yet. Reject cleanly so gateway retries.
            await ws.accept()
            await ws.send_json({"type": "auth_error", "detail": "world not started yet"})
            await ws.close(code=4003)
            return
        await handle_ws(
            ws,
            engine,
            ws_manager,
            app.state.run_id,
            agents_ready=app.state.agents_ready,
            tick_runner=getattr(app.state, "tick_runner", None),
        )
