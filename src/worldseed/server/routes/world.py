"""World lifecycle routes: /api/world/start, /api/world/stop, /api/world/resume."""

from __future__ import annotations

import secrets
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, FastAPI, HTTPException

from worldseed.server.routes._shared import (
    _kill_gateway,
    _spawn_gateway,
    agent_tokens,
    tokens,
)
from worldseed.server.tick_runner import TickRunner
from worldseed.server.websocket import ConnectionManager
from worldseed.world import WorldEngine

log = structlog.get_logger()


def create_world_router(app: FastAPI, ws_manager: ConnectionManager) -> APIRouter:
    router = APIRouter()

    @router.post("/api/world/start")
    async def world_start(req: dict[str, Any]) -> dict[str, Any]:
        """Start a world from the dashboard Setup page."""
        if app.state.engine is not None:
            raise HTTPException(409, detail="World already running. Stop first.")

        config_path = Path(req.get("config_path", ""))
        if not config_path.exists():
            raise HTTPException(404, detail=f"Config not found: {config_path}")

        dm_model = req.get("dm_model", "")
        dm_fallback = req.get("dm_fallback", "")
        tick_interval = float(req.get("tick_interval", 1.0))

        # Store settings
        app.state.settings.update(
            {
                "dm_model": dm_model,
                "dm_fallback": dm_fallback,
                "max_ticks": req.get("max_ticks"),
                "timeout_min": req.get("timeout_min"),
                "max_dm_calls": req.get("max_dm_calls"),
                "tick_interval": tick_interval,
            }
        )

        # Create engine
        from worldseed.persistence import RunRecorder
        from worldseed.scene.config import load_config

        run_id = secrets.token_hex(4)
        scene_cfg = load_config(config_path)

        # Narrator style/prompt from dashboard → set on config + settings for engine
        narrator_style = req.get("narrator_style", "") or None
        narrator_prompt = req.get("narrator_prompt", "") or None
        app.state.settings["narrator_style"] = narrator_style or ""
        app.state.settings["narrator_prompt"] = narrator_prompt or ""
        if narrator_prompt or narrator_style:
            from worldseed.models.config_schema import NarratorConfig

            if narrator_prompt:
                scene_cfg.narrator = NarratorConfig(prompt=narrator_prompt)
            elif narrator_style:
                try:
                    scene_cfg.narrator = NarratorConfig(style=narrator_style)
                except Exception:
                    # Style may be invalid (e.g. legacy "chapter") — use default
                    scene_cfg.narrator = NarratorConfig()
        recorder = RunRecorder(
            run_id=run_id,
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
                fallback_model=dm_fallback or None,
            )

        # Language: request > auto-detect from scene description
        from worldseed.gazette.context import detect_language

        language = req.get("language", "") or detect_language({"scene": {"description": scene_cfg.scene.description}})
        app.state.settings["language"] = language

        engine = WorldEngine(
            dm_provider=dm_provider,
            config=scene_cfg,
            recorder=recorder,
            language=language,
        )

        # Create tick runner + wire WebSocket connector
        from worldseed.connector.websocket import WebSocketConnector

        tr = TickRunner(engine, interval=tick_interval)
        ws_conn = WebSocketConnector(ws_manager)
        tr.connector = ws_conn

        app.state.engine = engine
        app.state.tick_runner = tr
        app.state.run_id = run_id

        engine.prepopulate_agents()

        # Write initial state to disk (API always reads from disk)
        engine.save_state()

        # Reset agent readiness tracking
        app.state.agents_ready = set()
        app.state.initial_wakes_sent = False  # Reset for new world

        # Do NOT spawn gateway or send wakes yet — wait for tick resume
        # (intro page edits characters before world actually runs)

        log.info(
            "world_started",
            scene=scene_cfg.scene.id,
            run_id=run_id,
            agents=len(scene_cfg.agents),
            dm_model=dm_model,
        )

        return {
            "run_id": run_id,
            "scene_id": scene_cfg.scene.id,
            "agents": len(scene_cfg.agents),
            "tick_interval": tick_interval,
        }

    @router.post("/api/world/stop")
    async def world_stop() -> dict[str, Any]:
        """Stop the current world, save data, return to lobby."""
        engine = app.state.engine
        if engine is None:
            raise HTTPException(400, detail="No world running")

        tr = app.state.tick_runner
        if tr:
            await tr.stop()

        # Save state for potential resume, then finalize
        engine.save_state()
        engine.recorder.update_status("stopped")
        engine.recorder.save_final_state([e.to_full_dict() for e in engine.state.all_entities()])
        engine.recorder.finalize(engine.tick, len(engine.get_registered_agents()))

        run_id = app.state.run_id
        app.state.engine = None
        app.state.tick_runner = None
        app.state.run_id = ""

        tokens.clear()
        agent_tokens.clear()
        app.state.agents_ready = set()

        # Kill gateway
        _kill_gateway(app)

        log.info("world_stopped", run_id=run_id)
        return {"stopped": True, "run_id": run_id}

    @router.post("/api/world/resume")
    async def world_resume(req: dict[str, Any]) -> dict[str, Any]:
        """Resume a previously stopped run."""
        if app.state.engine is not None:
            raise HTTPException(409, detail="World already running. Stop first.")

        resume_run_id = req.get("run_id", "")
        if not resume_run_id:
            raise HTTPException(400, detail="run_id is required")

        from worldseed.persistence import RunRecorder, load_run

        run_data = load_run(resume_run_id)
        if run_data is None:
            raise HTTPException(404, detail=f"Run '{resume_run_id}' not found or has no saved state")

        config_path = run_data["config_path"]
        if config_path is None:
            raise HTTPException(400, detail="Run has no saved config")

        meta = run_data["meta"]
        dm_model = meta.get("dm_model", "")

        # Store settings
        app.state.settings["dm_model"] = dm_model
        app.state.settings["dm_fallback"] = ""

        # Create recorder (appends to existing stream.jsonl)
        # Resume: config already saved from original start, no need to re-resolve
        recorder = RunRecorder(
            run_id=resume_run_id,
            config_path=config_path,
            scene_id=meta.get("scene_id", ""),
            dm_model=dm_model,
        )

        dm_provider = None
        if dm_model:
            from worldseed.dm.providers.llm import LiteLLMDMProvider

            dm_provider = LiteLLMDMProvider(
                model=dm_model,
                fallback_model=app.state.settings.get("dm_fallback") or None,
            )

        # Resolve language from settings
        language = app.state.settings.get("language", "")

        engine = WorldEngine(
            config_path,
            dm_provider=dm_provider,
            recorder=recorder,
            language=language,
        )

        # Restore state from saved data
        engine.load_state(run_data["state"], run_data["tick"], characters=run_data.get("characters"))

        # Wire tick runner + connector
        from worldseed.connector.websocket import WebSocketConnector

        tick_interval = app.state.settings.get("tick_interval", 5.0)
        tr = TickRunner(engine, interval=tick_interval)
        tr.connector = WebSocketConnector(ws_manager)

        app.state.engine = engine
        app.state.tick_runner = tr
        app.state.run_id = resume_run_id
        app.state.agents_ready = set()
        app.state.initial_wakes_sent = False

        # Notify gateway of world switch — same payload as auth_ok
        from worldseed.server.routes._shared import build_gateway_payload

        payload = build_gateway_payload(engine, resume_run_id)
        payload["type"] = "run_switched"
        gw_connected = await ws_manager.broadcast(payload)
        if gw_connected == 0:
            _spawn_gateway(app)

        recorder.update_status("running")
        recorder.record("run_resumed", run_data["tick"], prev_tick=run_data["tick"])

        log.info(
            "world_resumed",
            run_id=resume_run_id,
            scene_id=meta.get("scene_id"),
            tick=run_data["tick"],
            entities=len(run_data["state"]),
        )

        return {
            "run_id": resume_run_id,
            "scene_id": meta.get("scene_id", ""),
            "tick": run_data["tick"],
            "agents": len(engine.config.agents),
        }

    return router
