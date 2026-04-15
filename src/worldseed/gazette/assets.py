"""Asset discovery for gazette images."""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

import structlog

log = structlog.get_logger()

_IMG_EXTS = {".png", ".jpg", ".jpeg", ".webp"}


@lru_cache(maxsize=1)
def _project_root() -> Path:
    """Walk up from this file to find the project root."""
    p = Path(__file__).resolve().parent
    while p != p.parent:
        if (p / "pyproject.toml").exists():
            return p
        p = p.parent
    return Path(__file__).resolve().parent.parent.parent.parent


def _load_asset_pack(scene_id: str) -> str:
    """Read asset_pack from the scene's ui.json config."""
    ui_path = _project_root() / "frontend" / "public" / "configs" / f"{scene_id}.ui.json"
    if not ui_path.exists():
        return ""
    try:
        data = json.loads(ui_path.read_text(encoding="utf-8"))
        return str(data.get("asset_pack", ""))
    except Exception:
        log.warning("asset_pack_load_failed", scene_id=scene_id)
        return ""


def discover_assets(scene_id: str) -> dict[str, str]:
    """Find available image assets for a scene.

    Returns {slot: url_path} where slot is like "agents/<agent_id>"
    and url_path is like "/assets/scenes/<asset_pack>/agents/<agent_id>.png".
    """
    asset_pack = _load_asset_pack(scene_id)
    if not asset_pack:
        return {}

    scene_dir = _project_root() / "frontend" / "public" / "assets" / "scenes" / asset_pack
    if not scene_dir.is_dir():
        return {}

    assets: dict[str, str] = {}

    # Scene-level images
    for f in sorted(scene_dir.iterdir()):
        if f.is_file() and f.suffix.lower() in _IMG_EXTS:
            assets[f"scene/{f.stem}"] = f"/assets/scenes/{asset_pack}/{f.name}"

    # Agent and entity subdirectories
    for subdir in ("agents", "entities"):
        sub = scene_dir / subdir
        if sub.is_dir():
            for f in sorted(sub.iterdir()):
                if f.suffix.lower() in _IMG_EXTS:
                    assets[f"{subdir}/{f.stem}"] = f"/assets/scenes/{asset_pack}/{subdir}/{f.name}"

    return assets
