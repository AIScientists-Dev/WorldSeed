"""Server-level routes: SPA serving, /health, /api/inbox, SSE stream.

These endpoints are about the running server, not about run data.
Run data (state, stream, meta) lives in runs.py.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse
from starlette.responses import StreamingResponse

from worldseed.server.routes._shared import (
    _UI_DIR,
    _eng,
    _gateway_status,
    _require_agent,
)
from worldseed.server.websocket import ConnectionManager


def create_dashboard_router(app: FastAPI, ws_manager: ConnectionManager) -> APIRouter:
    router = APIRouter()

    _index = _UI_DIR / "index.html"

    @router.get("/")
    async def dashboard() -> FileResponse:
        return FileResponse(str(_index))

    @router.get("/lobby")
    @router.get("/run/{path:path}")
    @router.get("/demo")
    @router.get("/demo/{path:path}")
    @router.get("/dev/{path:path}")
    async def spa_catchall(path: str = "") -> FileResponse:
        """SPA fallback — all client-side routes serve index.html."""
        return FileResponse(str(_index))

    @router.get("/collage")
    async def collage() -> FileResponse:
        return FileResponse(str(_UI_DIR / "concept-collage.html"))

    @router.get("/health")
    async def health() -> dict[str, Any]:
        engine = app.state.engine
        tr = app.state.tick_runner
        # State: lobby → ready (engine exists, ticks not started) → live → paused
        if engine is None:
            state = "lobby"
        elif tr is None or not tr.running:
            state = "ready" if (tr is None or engine.tick == 0) else "paused"
        else:
            state = "live"
        expected_ids = engine.registry.expected_agent_ids() if engine else set()
        ready_set = app.state.agents_ready & expected_ids
        agents_info = {
            "total": len(expected_ids),
            "ready": sorted(ready_set),
            "pending": sorted(expected_ids - ready_set),
        }
        settings = app.state.settings
        return {
            "status": state,
            "tick": engine.tick if engine else 0,
            "running": tr.running if tr else False,
            "scene": (engine.config.scene.id if engine else None),
            "run_id": app.state.run_id or None,
            "gateway": _gateway_status(app, ws_manager),
            "agents": agents_info,
            "system_agents": engine.get_system_agents() if engine else [],
            "narrator_style": settings.get("narrator_style") if engine else None,
            "narrator_prompt": settings.get("narrator_prompt") if engine else None,
            **({"demo_runs": app.state.demo_runs} if app.state.demo_runs else {}),
        }

    @router.get("/api/inbox")
    async def api_inbox(agent_id: str = "") -> dict[str, Any]:
        eng = _eng(app)
        if not agent_id:
            raise HTTPException(400, detail="agent_id required")
        _require_agent(eng, agent_id)
        data = eng.peek_inbox(agent_id)
        return {
            "agent_id": agent_id,
            "events": [e.to_dict() for e in data["events"]],
            "whispers": [m.to_dict() for m in data["whispers"]],
            "last_perceive_tick": data["last_perceive_tick"],
        }

    @router.get("/api/stream/live")
    async def api_stream_live() -> StreamingResponse:
        """SSE endpoint — real-time stream of all records.

        Sends existing records first (catch-up), then pushes new records
        as they are written by RunRecorder.
        """
        queue: asyncio.Queue[dict[str, Any]] = asyncio.Queue()

        recorder = app.state.engine.recorder if app.state.engine else None
        if recorder is None or not hasattr(recorder, "add_listener"):
            raise HTTPException(503, detail="No active run")

        remove_listener = recorder.add_listener(lambda record: queue.put_nowait(record))

        async def event_stream():  # type: ignore[no-untyped-def]
            try:
                while True:
                    record = await queue.get()
                    line = json.dumps(record, default=str, ensure_ascii=False)
                    yield f"data: {line}\n\n"
            except asyncio.CancelledError:
                pass
            finally:
                remove_listener()

        return StreamingResponse(
            event_stream(),  # type: ignore[no-untyped-call]
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    return router
