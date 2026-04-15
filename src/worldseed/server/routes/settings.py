"""Settings routes: GET /api/settings, PATCH /api/settings, GET /api/models."""

from __future__ import annotations

import os
from typing import Any

import structlog
from fastapi import APIRouter, FastAPI

from worldseed.server.websocket import ConnectionManager

log = structlog.get_logger()

DEFAULT_DM_MODEL = ""


def _get_default_dm_model() -> str:
    """Return default DM model from env or built-in fallback."""
    return os.environ.get("WORLDSEED_DM_MODEL", DEFAULT_DM_MODEL)


def _get_available_models() -> dict[str, Any]:
    """Query LiteLLM for models available with the user's API keys.

    Returns models grouped by provider, filtered to chat models
    that support function calling (required by Instructor/DM).
    """
    try:
        import litellm
    except ImportError:
        return {"providers": [], "default": _get_default_dm_model()}

    # Query actual provider APIs for their current model catalogs.
    # This returns only models each provider currently serves —
    # no deprecated models, no need for hardcoded filters or dedup.
    try:
        valid = litellm.get_valid_models(check_provider_endpoint=True)
    except Exception:
        log.warning("litellm_get_valid_models_failed", exc_info=True)
        return {"providers": [], "default": _get_default_dm_model()}

    providers: dict[str, list[dict[str, Any]]] = {}
    for model_id in sorted(valid):
        if not litellm.supports_function_calling(model=model_id):
            continue
        provider = model_id.split("/")[0] if "/" in model_id else "openai"
        providers.setdefault(provider, []).append({"id": model_id})

    result = [{"provider": p, "models": models} for p, models in providers.items()]

    return {"providers": result, "default": _get_default_dm_model()}


def create_settings_router(app: FastAPI, ws_manager: ConnectionManager) -> APIRouter:
    router = APIRouter()

    @router.get("/api/settings")
    async def get_settings() -> dict[str, Any]:
        """Get current settings."""
        engine = app.state.engine
        return {
            "settings": app.state.settings,
            "running": engine is not None,
            "scene_id": (engine.config.scene.id if engine else None),
            "run_id": app.state.run_id,
            "tick": engine.tick if engine else 0,
        }

    @router.patch("/api/settings")
    async def update_settings(req: dict[str, Any]) -> dict[str, Any]:
        """Update settings. Hot settings apply immediately."""
        tr = app.state.tick_runner
        changed: list[str] = []

        # Hot settings (immediate, no restart)
        if "tick_interval" in req and tr:
            tr.set_interval(float(req["tick_interval"]))
            app.state.settings["tick_interval"] = req["tick_interval"]
            changed.append("tick_interval")

        if "max_ticks" in req:
            app.state.settings["max_ticks"] = req["max_ticks"]
            changed.append("max_ticks")

        if "timeout_min" in req:
            app.state.settings["timeout_min"] = req["timeout_min"]
            changed.append("timeout_min")

        if "max_dm_calls" in req:
            app.state.settings["max_dm_calls"] = req["max_dm_calls"]
            changed.append("max_dm_calls")

        if "language" in req:
            lang = req["language"]
            app.state.settings["language"] = lang
            engine = app.state.engine
            if engine is not None:
                engine.set_language(lang)
            changed.append("language")

        if "narrator_style" in req or "narrator_prompt" in req:
            engine = app.state.engine
            if engine is not None:
                engine.set_narrator_style(
                    style=req.get("narrator_style"),
                    prompt=req.get("narrator_prompt"),
                )
            if "narrator_style" in req:
                app.state.settings["narrator_style"] = req["narrator_style"]
            if "narrator_prompt" in req:
                app.state.settings["narrator_prompt"] = req["narrator_prompt"]
            changed.append("narrator_style")

        # Warm settings (need world restart)
        warm_keys = {"dm_model", "dm_fallback", "config_path"}
        warm_changed = warm_keys & set(req.keys())
        if warm_changed:
            for k in warm_changed:
                app.state.settings[k] = req[k]
                changed.append(k)

        return {"changed": changed, "settings": app.state.settings}

    @router.get("/api/models")
    async def list_models() -> dict[str, Any]:
        """Return available DM models based on configured API keys."""
        return _get_available_models()

    return router
