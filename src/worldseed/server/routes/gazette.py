"""Gazette API — estimate, generate, and retrieve newspaper summaries."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import structlog
from fastapi import APIRouter, FastAPI, HTTPException

from worldseed.paths import run_dir
from worldseed.server.websocket import ConnectionManager

log = structlog.get_logger()


@dataclass
class _PreparedRun:
    """All data needed to generate or estimate a gazette."""

    data: dict[str, Any]
    language: str
    scene_id: str
    assets: dict[str, str]
    context: str
    system_prompt: str
    actual_ticks: int = 0
    actual_agents: int = 0
    dm_model: str = ""
    agents: list[dict[str, Any]] = field(default_factory=list)


def create_gazette_router(app: FastAPI, ws_manager: ConnectionManager) -> APIRouter:
    router = APIRouter()

    _MIN_ACTIONS = 3

    def _run_dir(run_id: str) -> Path:
        d = run_dir(run_id)
        if not d.is_dir():
            raise HTTPException(404, detail=f"Run '{run_id}' not found")
        return d

    def _resolve_dm_model(meta: dict[str, Any]) -> str:
        """Resolve DM model from settings or run meta."""
        model = str((app.state.settings or {}).get("dm_model", ""))
        if model:
            return model
        return str(meta.get("dm_model", ""))

    def _prepare(run_id: str) -> _PreparedRun:
        """Load run data, validate, build context."""
        from worldseed.gazette.assets import discover_assets
        from worldseed.gazette.context import (
            build_context,
            build_system_prompt,
            detect_language,
            load_run_data,
        )

        data = load_run_data(run_id)
        records = data["records"]

        action_count = sum(1 for r in records if r["kind"] == "action")
        if action_count < _MIN_ACTIONS:
            raise HTTPException(
                400,
                detail=(
                    f"Not enough events for a gazette "
                    f"({action_count} actions, need at least "
                    f"{_MIN_ACTIONS}). Run more ticks first."
                ),
            )

        meta = data["meta"]
        language = detect_language(data["config"])
        scene_id = meta["scene_id"]
        assets = discover_assets(scene_id)
        context = build_context(data, language, assets)
        system_prompt = build_system_prompt(language)
        actual_ticks = max((r["tick"] for r in records), default=0)
        actual_agents = len({r["agent_id"] for r in records if r["kind"] == "register"})
        dm_model = _resolve_dm_model(meta)

        config_agents = data["config"].get("agents", [])
        from worldseed.gazette.schema import GazetteAgent

        agents = [
            GazetteAgent(
                id=a["id"],
                identity=a.get("character", {}).get("identity", ""),
                personality=a.get("character", {}).get("personality", ""),
            )
            for a in config_agents
        ]

        return _PreparedRun(
            data=data,
            language=language,
            scene_id=scene_id,
            assets=assets,
            context=context,
            system_prompt=system_prompt,
            actual_ticks=actual_ticks,
            actual_agents=actual_agents,
            dm_model=dm_model,
            agents=[a.model_dump() for a in agents],
        )

    @router.get("/api/runs/{run_id}/gazette")
    async def get_gazette_list(run_id: str) -> dict[str, Any]:
        """List gazettes + cost estimate for generating a new one."""
        _run_dir(run_id)

        from worldseed.gazette.cache import list_gazettes

        gazettes = list_gazettes(run_id)

        # Build estimate — gracefully handle insufficient events
        estimate = None
        no_model = False
        try:
            prep = _prepare(run_id)
            if not prep.dm_model:
                no_model = True
            else:
                from worldseed.gazette.generator import (
                    estimate_tokens,
                )

                estimate = estimate_tokens(prep.context, prep.system_prompt, prep.dm_model)
        except HTTPException as exc:
            if exc.status_code == 400:
                # Not enough events — still return the list
                pass
            else:
                raise
        except Exception:
            # Missing dependencies (litellm, etc.) or other errors — still return the list
            pass

        return {
            "gazettes": gazettes,
            "estimate": estimate,
            "no_model": no_model,
        }

    @router.get("/api/runs/{run_id}/gazette/{gazette_id}")
    async def get_gazette_by_id(run_id: str, gazette_id: str) -> dict[str, Any]:
        """Get a specific gazette by ID."""
        _run_dir(run_id)

        from worldseed.gazette.cache import get_gazette

        result = get_gazette(run_id, gazette_id)
        if result is None:
            raise HTTPException(404, detail=f"Gazette '{gazette_id}' not found")
        return {"gazette": result.model_dump()}

    @router.post("/api/runs/{run_id}/gazette")
    async def post_gazette(run_id: str, req: dict[str, Any] | None = None) -> dict[str, Any]:
        """Generate gazette for a run."""
        _run_dir(run_id)

        # Language: engine setting > request body > default
        language = app.state.settings.get("language", "") or (req or {}).get("language", "English")

        prep = _prepare(run_id)
        if not prep.dm_model:
            raise HTTPException(
                400,
                detail="No DM model configured. Set one in Settings.",
            )

        # Rebuild system prompt with user's chosen language
        from worldseed.gazette.context import build_system_prompt

        system_prompt = build_system_prompt(language)

        log.info(
            "gazette_generating",
            run_id=run_id,
            scene_id=prep.scene_id,
            model=prep.dm_model,
            language=language,
        )

        from worldseed.gazette.generator import generate_gazette

        try:
            gazette, gen_meta = await generate_gazette(prep.context, system_prompt, prep.dm_model)
        except Exception as exc:
            log.error(
                "gazette_generation_failed",
                run_id=run_id,
                exc_info=True,
            )
            raise HTTPException(500, detail=f"Gazette generation failed: {exc}") from exc

        from worldseed.gazette.cache import save
        from worldseed.gazette.schema import GazetteAgent, GazetteResult

        result = GazetteResult(
            run_id=run_id,
            scene_id=prep.scene_id,
            scene_description=prep.data["config"].get("scene", {}).get("description", ""),
            tick_count=prep.actual_ticks,
            language=language,
            generation=gen_meta,
            gazette=gazette,
            agents=[GazetteAgent(**a) for a in prep.agents],
        )
        gazette_id = save(run_id, result)

        log.info(
            "gazette_saved",
            run_id=run_id,
            gazette_id=gazette_id,
            cost_usd=gen_meta.get("cost_usd", 0),
        )

        return {
            "gazette_id": gazette_id,
            "gazette": result.model_dump(),
        }

    return router
