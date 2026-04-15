"""Scene Config loader — YAML loading + Pydantic validation + preset resolution."""

from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import structlog
import yaml

from worldseed.models.config_schema import SceneConfig

log = structlog.get_logger()

# Sentinel to detect "config didn't set this" vs "config set it to empty"
_UNSET = object()


def load_config(path: str | Path) -> SceneConfig:
    """Load and validate a scene config YAML file.

    If ``scene.use`` lists preset names, the corresponding YAML fragments
    are loaded from a ``presets/`` directory and deep-merged before validation.
    """
    path = Path(path)
    with path.open() as f:
        raw = yaml.safe_load(f)
    raw = _resolve_presets(raw, path)
    return SceneConfig.model_validate(raw)


def _resolve_presets(raw: dict[str, Any], config_path: Path, _seen: set[str] | None = None) -> dict[str, Any]:
    """Resolve ``scene.use`` preset imports and deep-merge into *raw*."""
    scene = raw.get("scene")
    if not isinstance(scene, dict):
        return raw

    use_list: list[str] = scene.get("use", [])
    if not use_list:
        return raw

    if _seen is None:
        _seen = set()

    # Load and merge presets left-to-right
    merged: dict[str, Any] = {}
    for name in use_list:
        if name in _seen:
            msg = f"Circular preset reference: {name!r} (chain: {_seen})"
            raise ValueError(msg)
        _seen.add(name)

        preset_path = _find_preset(name, config_path)
        with preset_path.open() as f:
            preset_raw = yaml.safe_load(f) or {}

        # Recursively resolve nested use: in presets
        preset_raw = _resolve_presets(preset_raw, preset_path, _seen)

        # Strip preset's scene metadata (id, description) — only the
        # importing config's scene metadata matters.  Keep dm_knowledge
        # for concatenation.
        preset_scene = preset_raw.pop("scene", None)
        if isinstance(preset_scene, dict):
            dk = preset_scene.get("dm_knowledge")
            if dk:
                preset_raw.setdefault("_dm_knowledge_parts", []).append(dk)

        _deep_merge(merged, preset_raw)

    # Now merge config on top of presets
    # Preserve config's dm_knowledge for concatenation
    config_dk = scene.pop("dm_knowledge", _UNSET)
    preset_dk_parts: list[str] = merged.pop("_dm_knowledge_parts", [])

    _deep_merge(merged, raw)

    # Concatenate dm_knowledge: presets first, then config
    final_dk_parts = preset_dk_parts[:]
    if config_dk is not _UNSET and config_dk:
        final_dk_parts.append(str(config_dk))
    if final_dk_parts:
        merged.setdefault("scene", {})["dm_knowledge"] = "\n".join(final_dk_parts)

    return merged


def _find_preset(name: str, config_path: Path) -> Path:
    """Find a preset YAML file by name.

    Search order:
    1. ``{config_dir}/presets/{name}.yaml`` (relative to the config file)
    2. Built-in presets shipped with the package
    """
    # 1. Relative to config: presets/ subdirectory
    relative = config_path.parent / "presets" / f"{name}.yaml"
    if relative.is_file():
        return relative

    # 2. Built-in presets (in the configs/ directory of the repo)
    # Walk up from config_path to find configs/presets/
    for parent in config_path.parents:
        builtin = parent / "configs" / "presets" / f"{name}.yaml"
        if builtin.is_file():
            return builtin

    msg = f"Preset {name!r} not found. Searched: {relative}, configs/presets/{name}.yaml"
    raise FileNotFoundError(msg)


def _deep_merge(base: dict[str, Any], override: dict[str, Any]) -> None:
    """Deep-merge *override* into *base* in place.

    Merge strategy per config section:
    - dicts (actions, consequences, templates, event_scopes): recursive merge
    - lists (entities, auto_tick, sanity_checks): append
    - perception.hidden_properties: union (deduplicated)
    - perception.visibility: override wins if present
    - perception.wake_summary: override wins if present
    - scalars: override wins
    """
    for key, val in override.items():
        if key not in base:
            base[key] = copy.deepcopy(val)
            continue

        base_val = base[key]

        # Both dicts → recursive merge
        if isinstance(base_val, dict) and isinstance(val, dict):
            # Special: perception needs per-field strategy
            if key == "perception":
                _merge_perception(base_val, val)
            else:
                _deep_merge(base_val, val)
        # Both lists → section-specific
        elif isinstance(base_val, list) and isinstance(val, list):
            if key == "hidden_properties":
                # Union, deduplicated
                seen = set(base_val)
                for item in val:
                    if item not in seen:
                        base_val.append(item)
                        seen.add(item)
            elif key == "entities":
                # Append, dedupe by id (later wins)
                existing_ids = {e["id"]: i for i, e in enumerate(base_val) if isinstance(e, dict)}
                for entity in val:
                    if isinstance(entity, dict) and entity.get("id") in existing_ids:
                        base_val[existing_ids[entity["id"]]] = copy.deepcopy(entity)
                    else:
                        base_val.append(copy.deepcopy(entity))
            else:
                # auto_tick, sanity_checks: append
                base_val.extend(copy.deepcopy(val))
        else:
            # Scalar or type mismatch: override wins
            base[key] = copy.deepcopy(val)


def _merge_perception(base: dict[str, Any], override: dict[str, Any]) -> None:
    """Merge perception section with special rules."""
    for key, val in override.items():
        bv = base.get(key)
        if key == "event_scopes" and isinstance(bv, dict) and isinstance(val, dict):
            _deep_merge(bv, val)
        elif key == "hidden_properties" and isinstance(bv, list) and isinstance(val, list):
            seen = set(bv)
            for item in val:
                if item not in seen:
                    bv.append(item)
                    seen.add(item)
        else:
            # visibility, wake_summary: override wins
            base[key] = copy.deepcopy(val)
