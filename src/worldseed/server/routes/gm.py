"""GM routes — narrative (dm, notify) and admin (entity, tick, reload)."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, FastAPI, HTTPException

from worldseed.server.models import (
    ConfigReloadRequest,
    EntityRemoveRequest,
    EntitySetRequest,
    GMResolveRequest,
    NotifyRequest,
    TickIntervalRequest,
    WhisperRequest,
)
from worldseed.server.routes._shared import (
    _eng,
    _require_agent,
    agent_tokens,
    tokens,
)
from worldseed.server.tick_runner import TickRunner
from worldseed.server.websocket import ConnectionManager
from worldseed.world import WorldEngine

log = structlog.get_logger()


def create_gm_router(app: FastAPI, ws_manager: ConnectionManager) -> APIRouter:
    router = APIRouter()

    @router.post("/api/entity/set")
    async def entity_set(req: EntitySetRequest) -> dict[str, Any]:
        eng = _eng(app)
        entity = eng.state.get(req.entity_id)
        if entity is None:
            raise HTTPException(404, detail=f"Entity '{req.entity_id}' not found")
        old = entity.get(req.property)
        eng.queue_entity_set(req.entity_id, req.property, req.value)
        eng.recorder.record(
            "gm_set_queued",
            eng.tick,
            entity_id=req.entity_id,
            property=req.property,
            old=old,
            new=req.value,
        )
        return {
            "entity_id": req.entity_id,
            "property": req.property,
            "old": old,
            "new": req.value,
            "tick": eng.tick,
        }

    @router.post("/api/entity/remove")
    async def entity_remove(req: EntityRemoveRequest) -> dict[str, Any]:
        eng = _eng(app)
        entity = eng.state.get(req.entity_id)
        if entity is None:
            raise HTTPException(404, detail=f"Entity '{req.entity_id}' not found")
        eng.queue_entity_remove(req.entity_id)
        eng.recorder.record("gm_remove_queued", eng.tick, entity_id=req.entity_id)
        return {
            "queued": True,
            "entity_id": req.entity_id,
            "tick": eng.tick,
        }

    @router.post("/api/tick/step")
    async def tick_step() -> dict[str, Any]:
        tr = app.state.tick_runner
        if tr and tr.running:
            raise HTTPException(400, detail="Pause first")
        eng = _eng(app)
        results = await eng.step_async()
        # Also evaluate wakeup + notify (same as tick_runner._loop does)
        from worldseed.server.tick_runner import evaluate_and_notify

        tr = app.state.tick_runner
        if tr and tr.connector:
            await evaluate_and_notify(
                eng,
                tr.connector,
                tr._ticks_since_notify,
            )
        return {"tick": eng.tick, "actions_processed": len(results)}

    @router.patch("/api/tick/interval")
    async def tick_interval_set(req: TickIntervalRequest) -> dict[str, Any]:
        if req.interval <= 0:
            raise HTTPException(400, detail="Interval must be positive")
        tr = app.state.tick_runner
        if tr:
            tr.set_interval(req.interval)
        app.state.settings["tick_interval"] = req.interval
        return {"interval": req.interval, "tick": _eng(app).tick}

    @router.post("/api/tick/pause")
    async def tick_pause() -> dict[str, Any]:
        tr = app.state.tick_runner
        if tr:
            await tr.stop()
        await ws_manager.broadcast({"type": "sleep"})
        return {"paused": True, "tick": _eng(app).tick}

    @router.post("/api/tick/resume")
    async def tick_resume() -> dict[str, Any]:
        engine = _eng(app)
        tr = app.state.tick_runner

        # Spawn gateway if not already running (deferred from world/start)
        from worldseed.server.routes._shared import _spawn_gateway

        gw_proc = getattr(app.state, "gateway_proc", None)
        if gw_proc is None or gw_proc.poll() is not None:
            _spawn_gateway(app)

        if tr:
            # Send initial wakes ONCE so agents start reading files + registering.
            # Only on the first resume — subsequent pause/resume cycles don't re-send.
            if tr.connector is not None and not app.state.initial_wakes_sent:
                import asyncio

                app.state.initial_wakes_sent = True

                async def _initial_wake() -> None:
                    for _ in range(60):
                        if len(ws_manager._gateways) > 0:
                            break
                        await asyncio.sleep(0.5)
                    else:
                        log.warning("gateway_connect_timeout")
                        return
                    await asyncio.sleep(1.0)
                    # Use config agent IDs — agents may not be registered in engine yet
                    # (they register themselves via plugin worldseed_register).
                    agents = [a.id for a in engine.config.agents]
                    log.info("_initial_wake_sending", agents=agents)
                    for aid in agents:
                        try:
                            await tr.connector.notify(aid, "initial")
                            tr.busy.mark_busy(aid)
                        except Exception:
                            log.warning("initial_wake_failed", agent=aid)

                app.state._initial_wake_task = asyncio.create_task(_initial_wake(), name="initial_wake")

        # Start ticks only if all agents already registered (pause/resume).
        # First launch: ticks auto-start via maybe_auto_start_ticks in _handle_register.
        from worldseed.server.routes._shared import maybe_auto_start_ticks

        await maybe_auto_start_ticks(engine, tr, app.state.agents_ready)
        return {"resumed": True, "tick": engine.tick}

    @router.post("/api/notify")
    async def notify(req: NotifyRequest) -> dict[str, Any]:
        tr = app.state.tick_runner
        if tr is None or tr.connector is None:
            raise HTTPException(400, detail="No connector configured")
        await tr.request_immediate_notify()
        return {"notified": True, "agent_id": req.agent_id}

    @router.post("/api/whisper")
    async def whisper(req: WhisperRequest) -> dict[str, Any]:
        eng = _eng(app)
        _require_agent(eng, req.agent_id)
        eng.send_whisper(req.agent_id, "gm", req.message, "whisper")
        eng.recorder.record(
            "whisper",
            eng.tick,
            agent_id=req.agent_id,
            message=req.message,
        )
        notified = False
        tr = app.state.tick_runner
        if tr and tr.connector is not None:
            failed = await tr.request_immediate_notify()
            notified = req.agent_id not in failed
        return {
            "sent": True,
            "notified": notified,
            "agent_id": req.agent_id,
            "tick": eng.tick,
        }

    @router.post("/api/gm/resolve")
    async def gm_resolve(req: GMResolveRequest) -> dict[str, Any]:
        """Queue a GM natural-language command for DM resolution."""
        eng = _eng(app)
        if not eng.has_dm:
            raise HTTPException(400, detail="DM provider required for gm/resolve")
        request_id = eng.queue_gm_resolve(req.text, req.target_entity_id)
        eng.recorder.record(
            "gm_resolve_queued",
            eng.tick,
            request_id=request_id,
            text=req.text,
            target_entity_id=req.target_entity_id,
        )
        return {
            "queued": True,
            "request_id": request_id,
            "tick": eng.tick,
        }

    @router.post("/api/config/reload")
    async def config_reload(
        req: ConfigReloadRequest,
    ) -> dict[str, Any]:
        """Hot-reload a new scene config. Creates new run."""
        import secrets as _secrets

        from worldseed.persistence import RunRecorder
        from worldseed.scene.config import load_config

        config_path = Path(req.config_path)
        if not config_path.exists():
            raise HTTPException(404, detail=f"Config not found: {req.config_path}")

        # Finalize current run if running
        eng = app.state.engine
        if eng is not None:
            eng.recorder.save_final_state([e.to_full_dict() for e in eng.state.all_entities()])
            eng.recorder.finalize(eng.tick, len(eng.get_registered_agents()))

        tr = app.state.tick_runner
        if tr:
            await tr.stop()

        new_run_id = _secrets.token_hex(4)
        scene_cfg = load_config(config_path)
        dm_model = app.state.settings.get("dm_model", "")
        new_recorder = RunRecorder(
            run_id=new_run_id,
            config_path=config_path,
            scene_id=scene_cfg.scene.id,
            dm_model=dm_model,
            resolved_config=scene_cfg.model_dump(),
        )

        dm_provider = None
        if dm_model:
            from worldseed.dm.providers.llm import LiteLLMDMProvider

            dm_provider = LiteLLMDMProvider(
                model=dm_model,
                fallback_model=app.state.settings.get("dm_fallback") or None,
            )

        new_engine = WorldEngine(config_path, dm_provider=dm_provider, recorder=new_recorder)
        new_engine.prepopulate_agents()

        new_tr = TickRunner(
            new_engine,
            interval=app.state.settings.get("tick_interval", 1.0),
        )
        from worldseed.connector.websocket import WebSocketConnector as _WSC

        new_tr.connector = _WSC(ws_manager)
        app.state.engine = new_engine
        app.state.tick_runner = new_tr
        app.state.run_id = new_run_id

        tokens.clear()
        agent_tokens.clear()
        app.state.agents_ready = set()
        app.state.initial_wakes_sent = False

        await new_tr.start()

        return {
            "run_id": new_run_id,
            "scene_id": scene_cfg.scene.id,
            "agents": len(new_engine.config.agents),
        }

    return router
