"""WebSocket endpoint — persistent bidirectional channel for gateways.

A single WebSocket connection serves as a gateway for multiple agents.
Auth once with a gateway token, then perceive/act/wake for any
registered agent flow through the same connection.

Includes application-level ping/pong heartbeat (30s interval).
Server sends {type: "ping"}, client responds {type: "pong"}.
Two missed pongs = dead connection, server closes.

Protocol (JSON messages):

Client -> Server:
  {type: "auth", gateway_token: "..."}
  {type: "register", agent_id: "..."}
  {type: "perceive", request_id: "...", agent_id: "..."}
  {type: "act", request_id: "...", agent_id: "...", action: "...", params: {...}}
  {type: "turn_done", agent_id: "..."}   // agent finished processing wake
  {type: "pong"}

Server -> Client:
  {type: "auth_ok", scene: "...", agents: [{id, character}, ...], run_id: "..."}
  {type: "auth_error", detail: "..."}
  {type: "register_ok", agent_id: "..."}
  {type: "register_error", agent_id: "...", detail: "..."}
  {type: "perception", request_id: "...", agent_id: "...", tick: N, ...}
  {type: "act_ok", request_id: "...", agent_id: "...", tick: N, queued: true}
  {type: "wake", agent_id: "...", reason: "...", perception: {...}}
  {type: "send_initial_wakes"}
  {type: "agent_registered", agent_id: "...", character: {...}, scene: "..."}
  {type: "ping"}
  {type: "error", request_id: "...", detail: "..."}
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog
from fastapi import WebSocket, WebSocketDisconnect

from worldseed.world import WorldEngine

log = structlog.get_logger()

PING_INTERVAL = 30.0  # seconds between pings
PING_TIMEOUT_COUNT = 2  # missed pongs before disconnect


class GatewayConnection:
    """A single authenticated WebSocket connection for a gateway."""

    def __init__(self, ws: WebSocket, gateway_id: str) -> None:
        self.ws = ws
        self.gateway_id = gateway_id
        self.missed_pongs = 0

    async def send(self, msg: dict[str, Any]) -> None:
        """Send a JSON message to the client."""
        await self.ws.send_json(msg)


class ConnectionManager:
    """Manages gateway WebSocket connections.

    Multiple gateways can connect. Each gateway can serve multiple agents.
    Wake signals are broadcast to all connected gateways (the right one
    will have the agent).
    """

    def __init__(self) -> None:
        self._gateways: dict[str, GatewayConnection] = {}

    def add(self, conn: GatewayConnection) -> None:
        """Register a gateway connection. Replaces existing with same ID."""
        old = self._gateways.get(conn.gateway_id)
        if old is not None:
            log.info("ws_gateway_replaced", gateway=conn.gateway_id)
        self._gateways[conn.gateway_id] = conn

    def remove_if_current(self, gateway_id: str, conn: GatewayConnection) -> None:
        """Remove only if the stored connection is the same instance."""
        current = self._gateways.get(gateway_id)
        if current is conn:
            del self._gateways[gateway_id]

    async def send_wake(
        self,
        agent_id: str,
        reason: str,
        perception: dict[str, Any] | None = None,
    ) -> bool:
        """Push a wake signal to all gateways. Returns True if any delivered."""
        delivered = False
        dead: list[tuple[str, GatewayConnection]] = []
        msg: dict[str, Any] = {
            "type": "wake",
            "agent_id": agent_id,
            "reason": reason,
        }
        if perception is not None:
            msg["perception"] = perception
        for gw_id, conn in list(self._gateways.items()):
            try:
                await conn.send(msg)
                delivered = True
            except Exception:
                log.warning("ws_wake_failed", gateway=gw_id, agent=agent_id)
                dead.append((gw_id, conn))
        for gw_id, conn in dead:
            self.remove_if_current(gw_id, conn)
        return delivered

    async def broadcast(self, msg: dict[str, Any]) -> int:
        """Send a message to all connected gateways. Returns count sent."""
        dead: list[tuple[str, GatewayConnection]] = []
        sent = 0
        for gw_id, conn in list(self._gateways.items()):
            try:
                await conn.send(msg)
                sent += 1
            except Exception:
                log.warning("ws_broadcast_failed", gateway=gw_id)
                dead.append((gw_id, conn))
        for gw_id, conn in dead:
            self.remove_if_current(gw_id, conn)
        return sent

    async def send_agent_registered(
        self,
        agent_id: str,
        character: dict[str, Any],
        scene: str,
    ) -> None:
        """Notify all gateways that a new agent was registered."""
        await self.broadcast(
            {
                "type": "agent_registered",
                "agent_id": agent_id,
                "character": character,
                "scene": scene,
            }
        )

    async def send_character_updated(
        self,
        agent_id: str,
        character: dict[str, Any],
    ) -> None:
        """Notify all gateways that an agent's character was updated."""
        await self.broadcast(
            {
                "type": "character_updated",
                "agent_id": agent_id,
                "character": character,
            }
        )


async def _ping_loop(conn: GatewayConnection) -> None:
    """Send periodic pings. Cancels when connection dies."""
    while True:
        await asyncio.sleep(PING_INTERVAL)
        if conn.missed_pongs >= PING_TIMEOUT_COUNT:
            log.warning(
                "ws_ping_timeout",
                gateway=conn.gateway_id,
                missed=conn.missed_pongs,
            )
            try:
                await conn.ws.close(code=4008)
            except Exception:
                pass
            return
        try:
            await conn.send({"type": "ping"})
            conn.missed_pongs += 1
        except Exception:
            return


async def handle_ws(
    ws: WebSocket,
    engine: WorldEngine,
    manager: ConnectionManager,
    run_id: str = "",
    agents_ready: set[str] | None = None,
    tick_runner: Any | None = None,
) -> None:
    """Handle one WebSocket connection lifecycle."""
    from worldseed.server.routes._shared import DEFAULT_GATEWAY_TOKEN

    await ws.accept()

    # Phase 1: Auth — first message must be auth with gateway_token
    gateway_id: str | None = None
    conn: GatewayConnection | None = None
    try:
        raw = await ws.receive_text()
        msg = json.loads(raw)

        if msg.get("type") != "auth":
            err = {"type": "auth_error", "detail": "first message must be auth"}
            await ws.send_json(err)
            await ws.close(code=4001)
            return

        token = msg.get("gateway_token", "")
        if token != DEFAULT_GATEWAY_TOKEN:
            err = {"type": "auth_error", "detail": "invalid gateway token"}
            await ws.send_json(err)
            await ws.close(code=4001)
            return

        from worldseed.server.routes._shared import build_gateway_payload

        gateway_id = f"gw_{id(ws)}"
        payload = build_gateway_payload(engine, run_id)
        payload["type"] = "auth_ok"
        await ws.send_json(payload)

        conn = GatewayConnection(ws, gateway_id)
        manager.add(conn)
        log.info("ws_gateway_authenticated", gateway=gateway_id)

        # Initial wakes are NOT sent here. They are sent by:
        # - tick_resume (gm.py) when ticks start
        # - /api/agents/connect when dashboard triggers connection
        # - run_switched handler for resume
        # Sending wakes from auth_ok caused duplicates with every other source.

    except (json.JSONDecodeError, WebSocketDisconnect):
        return

    # Start ping loop
    ping_task = asyncio.create_task(_ping_loop(conn))

    # Phase 2: Message loop
    try:
        async for raw in ws.iter_text():
            try:
                msg = json.loads(raw)
            except json.JSONDecodeError:
                await ws.send_json({"type": "error", "detail": "invalid JSON"})
                continue

            msg_type = msg.get("type")
            request_id = msg.get("request_id")
            agent_id = msg.get("agent_id")

            if msg_type == "pong":
                conn.missed_pongs = 0
            elif msg_type == "register":
                await _handle_register(ws, engine, msg, manager, agents_ready, tick_runner)
            elif msg_type == "turn_done":
                # Agent finished processing a wake (acted or chose not to)
                if agent_id and tick_runner is not None:
                    tick_runner.busy.clear_busy(agent_id)
                    log.debug("turn_done", agent=agent_id)
            elif msg_type in ("perceive", "act", "narrate"):
                if not agent_id:
                    await ws.send_json(
                        {
                            "type": "error",
                            "request_id": request_id,
                            "detail": "agent_id is required",
                        }
                    )
                    continue
                if msg_type == "perceive":
                    if agents_ready is not None:
                        agents_ready.add(agent_id)
                    await _handle_perceive(ws, engine, agent_id, request_id)
                elif msg_type == "narrate":
                    await _handle_narrate(ws, engine, agent_id, request_id, msg)
                else:
                    await _handle_act(ws, engine, agent_id, request_id, msg)
            else:
                await ws.send_json(
                    {
                        "type": "error",
                        "request_id": request_id,
                        "detail": f"unknown message type: {msg_type}",
                    }
                )

    except WebSocketDisconnect:
        pass
    finally:
        ping_task.cancel()
        if conn is not None:
            manager.remove_if_current(gateway_id, conn)
        log.info("ws_gateway_disconnected", gateway=gateway_id)


async def _handle_register(
    ws: WebSocket,
    engine: WorldEngine,
    msg: dict[str, Any],
    manager: ConnectionManager,
    agents_ready: set[str] | None = None,
    tick_runner: Any | None = None,
) -> None:
    """Handle agent self-registration via WebSocket.

    Gateway sends {type: "register", agent_id: "..."} after writing
    SOUL.md/WORLD.md/SKILL.md and the agent's initial wake.
    Server claims the preset agent.
    """
    agent_id = msg.get("agent_id")
    if not agent_id:
        await ws.send_json(
            {
                "type": "register_error",
                "request_id": msg.get("request_id"),
                "agent_id": "",
                "detail": "agent_id is required",
            }
        )
        return

    if not engine.registry.is_claimed(agent_id):
        # Find preset agent in config
        preset = None
        for a in engine.config.agents:
            if a.id == agent_id:
                preset = a
                break

        if preset is None:
            await ws.send_json(
                {
                    "type": "register_error",
                    "request_id": msg.get("request_id"),
                    "agent_id": agent_id,
                    "detail": f"Unknown preset: {agent_id}",
                }
            )
            return

        props = engine.registry.merge_preset_properties(preset)
        engine.register_agent(
            agent_id,
            props,
            dict(preset.character),
            omniscient=preset.omniscient,
            system=preset.system,
        )

    await ws.send_json(
        {
            "type": "register_ok",
            "request_id": msg.get("request_id"),
            "agent_id": agent_id,
        }
    )

    # Notify all gateways about the registration — use registry profile
    # (includes intro edits), not preset config.
    profile = engine.get_agent_profile(agent_id)
    char = dict(profile.character) if profile else {}
    await manager.send_agent_registered(agent_id, char, engine.config.scene.id)

    # Mark agent as ready and check if all preset agents are now connected
    if agents_ready is not None:
        agents_ready.add(agent_id)
        from worldseed.server.routes._shared import maybe_auto_start_ticks

        await maybe_auto_start_ticks(engine, tick_runner, agents_ready)


async def _require_ws_agent(
    ws: WebSocket,
    engine: WorldEngine,
    agent_id: str,
    request_id: str | None,
) -> bool:
    """Validate agent exists. Sends error and returns False if not."""
    from worldseed.server._validation import validate_agent

    err = validate_agent(engine, agent_id)
    if err:
        await ws.send_json({"type": "error", "request_id": request_id, "detail": err})
        return False
    return True


async def _handle_perceive(
    ws: WebSocket,
    engine: WorldEngine,
    agent_id: str,
    request_id: str | None,
) -> None:
    """Handle a perceive request for a specific agent."""
    if not await _require_ws_agent(ws, engine, agent_id, request_id):
        return
    try:
        p = engine.perceive(agent_id)
    except Exception as exc:
        await ws.send_json({"type": "error", "request_id": request_id, "detail": str(exc)})
        return
    result = p.to_dict()
    result["type"] = "perception"
    result["request_id"] = request_id
    result["agent_id"] = agent_id
    result["tick"] = engine.tick
    await ws.send_json(result)


async def _handle_act(
    ws: WebSocket,
    engine: WorldEngine,
    agent_id: str,
    request_id: str | None,
    msg: dict[str, Any],
) -> None:
    """Handle an act request for a specific agent."""
    if not await _require_ws_agent(ws, engine, agent_id, request_id):
        return

    action = msg.get("action")
    params = msg.get("params", {})

    # Flat-param fallback: extract top-level keys as params
    if not params:
        known = {
            "type",
            "request_id",
            "agent_id",
            "action",
            "params",
            "think_interval",
        }
        params = {k: v for k, v in msg.items() if k not in known}

    if not action:
        await ws.send_json(
            {
                "type": "error",
                "request_id": request_id,
                "detail": "action is required",
            }
        )
        return

    think_interval = msg.get("think_interval")

    try:
        result = engine.submit(agent_id, action, params)
    except ValueError as exc:
        await ws.send_json(
            {
                "type": "act_error",
                "request_id": request_id,
                "agent_id": agent_id,
                "detail": str(exc),
            }
        )
        return
    except Exception as exc:
        await ws.send_json({"type": "error", "request_id": request_id, "detail": str(exc)})
        return

    if think_interval is not None:
        try:
            engine.set_think_interval(agent_id, int(think_interval))
        except (ValueError, TypeError):
            log.warning(
                "ws_invalid_think_interval",
                agent=agent_id,
                value=think_interval,
            )

    from worldseed.engine.rules_engine import ActionResult

    if isinstance(result, ActionResult):
        # Mechanical action — executed immediately
        log.info("ws_action_executed", agent=agent_id, action=action, success=result.success)
        if result.success:
            await ws.send_json(
                {
                    "type": "act_ok",
                    "request_id": request_id,
                    "agent_id": agent_id,
                    "executed": True,
                    "tick": engine.tick,
                }
            )
        else:
            await ws.send_json(
                {
                    "type": "act_error",
                    "request_id": request_id,
                    "agent_id": agent_id,
                    "detail": result.reason,
                }
            )
    elif isinstance(result, str):
        # Queue rejection (e.g., already acted this tick)
        await ws.send_json(
            {
                "type": "act_error",
                "request_id": request_id,
                "agent_id": agent_id,
                "detail": result,
            }
        )
    else:
        # DM action — queued for next tick
        log.info("ws_action_queued", agent=agent_id, action=action)
        await ws.send_json(
            {
                "type": "act_ok",
                "request_id": request_id,
                "agent_id": agent_id,
                "queued": True,
                "tick": engine.tick,
            }
        )


async def _handle_narrate(
    ws: WebSocket,
    engine: WorldEngine,
    agent_id: str,
    request_id: str | None,
    msg: dict[str, Any],
) -> None:
    """Handle narrator chapter submission — bypasses action pipeline."""
    if agent_id != "narrator":
        await ws.send_json(
            {"type": "narrate_error", "request_id": request_id, "detail": "Only narrator can narrate"}
        )
        return
    params = {
        "title": msg.get("title", ""),
        "tldr": msg.get("tldr", ""),
        "body": msg.get("body", ""),
        "asides": msg.get("asides", ""),
        "whisper_options": msg.get("whisper_options", ""),
    }
    chapter = engine.record_narration(params)
    if isinstance(chapter, str):
        await ws.send_json({"type": "narrate_error", "request_id": request_id, "detail": chapter})
    else:
        await ws.send_json(
            {"type": "narrate_ok", "request_id": request_id, "chapter": chapter, "tick": engine.tick}
        )
