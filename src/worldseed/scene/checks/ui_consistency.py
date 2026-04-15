"""UI consistency checks — cross-validate .ui.json against scene config.

Checks that every entity type has a matching UI rule, bind keys reference
real properties, layout entries reference real zones, etc.

Valid scene types and bind keys are defined here with comments pointing to
the canonical source in frontend/src/lib/ui-config.ts.
"""

from __future__ import annotations

import json
import math
import re
from pathlib import Path
from typing import Any

from worldseed.models.config_schema import SceneConfig
from worldseed.scene.validator import ValidationMessage, ValidationResult

# Canonical source: SCENE_TYPES in frontend/src/lib/ui-config.ts
VALID_SCENE_TYPES = {"zone", "deck", "card", "gauge", "avatar", "fallback", "hidden"}

# Canonical source: bind key consumption in EntityCard.tsx, ZoneCard.tsx, AgentRow.tsx, map-layout.ts
VALID_BIND_KEYS = {"label", "locate_by", "connections", "show", "bar", "bar_max", "state_effects"}

# Zone overlap threshold — warn when overlap exceeds this fraction of the smaller zone
MAX_ZONE_OVERLAP_RATIO = 0.25

# Frontend ui config directory
UI_CONFIG_DIR = Path(__file__).resolve().parents[4] / "frontend" / "public" / "configs"


def _load_ui_config(scene_id: str) -> dict[str, Any] | None:
    """Load .ui.json for a scene, return None if not found."""
    path = UI_CONFIG_DIR / f"{scene_id}.ui.json"
    if not path.exists():
        return None
    try:
        data: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
        return data
    except (json.JSONDecodeError, OSError):
        return None


def _rule_matches_type(rule: dict[str, Any], entity_type: str) -> bool:
    """Check if a rule's match condition would match an entity of the given type."""
    match = rule.get("match", {})
    if not isinstance(match, dict):
        return False
    # Empty match {} matches everything
    if not match:
        return True
    # If rule has type constraint, check it
    if "type" in match:
        return bool(match["type"] == entity_type)
    # Rule only matches by id — not a type-level match
    return False


def _rule_matches_entity(rule: dict[str, Any], entity_id: str, entity_type: str) -> bool:
    """Check if a rule would match a specific entity (by id or type)."""
    match = rule.get("match", {})
    if not isinstance(match, dict):
        return False
    if not match:
        return True
    if "id" in match and "type" in match:
        return bool(match["id"] == entity_id and match["type"] == entity_type)
    if "id" in match:
        return bool(match["id"] == entity_id)
    if "type" in match:
        return bool(match["type"] == entity_type)
    return False


def check_ui_consistency(config: SceneConfig, result: ValidationResult) -> None:
    """Run all UI consistency checks."""
    ui = _load_ui_config(config.scene.id)
    if ui is None:
        result.add(
            ValidationMessage(
                level="warning",
                code="U000",
                summary=f"No .ui.json found for scene '{config.scene.id}'",
                suggestion=f"Create frontend/public/configs/{config.scene.id}.ui.json",
            )
        )
        return

    rules = ui.get("rules", [])
    events = ui.get("events", [])
    layout = ui.get("layout", {})
    event_defaults = ui.get("event_defaults")

    # Collect entity types and their properties
    entity_types: dict[str, list[dict[str, Any]]] = {}
    for e in config.entities:
        entity_types.setdefault(e.type, []).append({"id": e.id, "properties": dict(e.properties)})
    for a in config.agents:
        # Merge template properties so bind checks see the full property set
        merged_props = dict(a.properties)
        if a.template and a.template in config.templates:
            for k, v in config.templates[a.template].properties.items():
                if k not in merged_props:
                    merged_props[k] = v
        entity_types.setdefault("agent", []).append({"id": a.id, "properties": merged_props})

    # Collect zone IDs (entities matched as containers)
    zone_ids: set[str] = set()
    for e in config.entities:
        for rule in rules:
            if not isinstance(rule, dict):
                continue
            if _rule_matches_entity(rule, e.id, e.type):
                scene = rule.get("scene", "")
                if scene in ("zone", "deck"):
                    zone_ids.add(e.id)
                break

    # U001: Entity has no matching UI rule (checks both type and id matches)
    for etype, entities in entity_types.items():
        for ent in entities:
            eid = ent["id"]
            matched = any(isinstance(r, dict) and _rule_matches_entity(r, eid, etype) for r in rules)
            if not matched:
                result.add(
                    ValidationMessage(
                        level="error",
                        code="U001",
                        summary=f"Entity '{eid}' (type={etype}) has no matching UI rule",
                        location="rules[]",
                        suggestion=f"Add a rule with match.type='{etype}' or match.id='{eid}'",
                    )
                )

    # Per-rule checks
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            result.add(
                ValidationMessage(
                    level="error",
                    code="U001",
                    summary=f"rules[{i}] is not an object (string preset references not supported)",
                    location=f"rules[{i}]",
                    suggestion="All rules must be inline JSON objects, not string references",
                )
            )
            continue

        scene = rule.get("scene", "")
        bind = rule.get("bind", {})

        # U004: Unknown scene type
        if scene and scene not in VALID_SCENE_TYPES:
            result.add(
                ValidationMessage(
                    level="error",
                    code="U004",
                    summary=f"Unknown scene type '{scene}'",
                    location=f"rules[{i}]",
                    suggestion=f"Valid types: {', '.join(sorted(VALID_SCENE_TYPES))}",
                )
            )

        # U005: Unknown bind key
        if isinstance(bind, dict):
            for key in bind:
                if key not in VALID_BIND_KEYS:
                    result.add(
                        ValidationMessage(
                            level="warning",
                            code="U005",
                            summary=f"Unknown bind key '{key}'",
                            location=f"rules[{i}].bind",
                            suggestion=f"Valid keys: {', '.join(sorted(VALID_BIND_KEYS))}",
                        )
                    )

        # U002: bind.locate_by references property not on matched entities
        if isinstance(bind, dict) and "locate_by" in bind:
            locate_prop = bind["locate_by"]
            match = rule.get("match", {})
            matched_type = match.get("type", "") if isinstance(match, dict) else ""
            if matched_type and matched_type in entity_types:
                entities_of_type = entity_types[matched_type]
                has_prop = any(locate_prop in e["properties"] for e in entities_of_type)
                if not has_prop:
                    result.add(
                        ValidationMessage(
                            level="warning",
                            code="U002",
                            summary=f"bind.locate_by='{locate_prop}' not found on any {matched_type} entity",
                            location=f"rules[{i}].bind",
                            suggestion="Check property name matches your config entities",
                        )
                    )

        # U003: bind.bar references non-numeric property
        if isinstance(bind, dict) and "bar" in bind:
            bar_prop = bind["bar"]
            match = rule.get("match", {})
            matched_type = match.get("type", "") if isinstance(match, dict) else ""
            if matched_type and matched_type in entity_types:
                for ent in entity_types[matched_type]:
                    val = ent["properties"].get(bar_prop)
                    if val is not None and not isinstance(val, (int, float)):
                        result.add(
                            ValidationMessage(
                                level="warning",
                                code="U003",
                                summary=f"bind.bar='{bar_prop}' is not numeric on {ent['id']}",
                                location=f"rules[{i}].bind",
                            )
                        )
                        break

        # U011: state_effects conditions reference non-existent properties
        if isinstance(bind, dict) and "state_effects" in bind:
            effects = bind["state_effects"]
            if isinstance(effects, dict):
                match = rule.get("match", {})
                matched_type = match.get("type", "") if isinstance(match, dict) else ""
                matched_id = match.get("id", "") if isinstance(match, dict) else ""
                # Get the property set for matched entities
                props: set[str] = set()
                if matched_id:
                    for etype_ents in entity_types.values():
                        for ent in etype_ents:
                            if ent["id"] == matched_id:
                                props = set(ent["properties"].keys())
                elif matched_type and matched_type in entity_types:
                    for ent in entity_types[matched_type]:
                        props |= set(ent["properties"].keys())
                if props:
                    for cond in effects:
                        m = re.match(r"^([a-zA-Z_]\w*)[=<>]", cond)
                        if m:
                            prop_name = m.group(1)
                            if prop_name not in props:
                                msg = f"state_effects '{cond}' references '{prop_name}' not on initial entities"
                                result.add(
                                    ValidationMessage(
                                        level="hint",
                                        code="U011",
                                        summary=msg,
                                        location=f"rules[{i}].bind.state_effects",
                                        suggestion="Check property exists in YAML or is set by effects",
                                    )
                                )
                                break

    # U006: Layout references non-existent zone ID
    all_entity_ids = {e.id for e in config.entities} | {a.id for a in config.agents}
    for zone_id in layout:
        if zone_id not in all_entity_ids:
            result.add(
                ValidationMessage(
                    level="error",
                    code="U006",
                    summary=f"Layout references non-existent entity '{zone_id}'",
                    location=f"layout.{zone_id}",
                )
            )
        elif zone_id not in zone_ids:
            result.add(
                ValidationMessage(
                    level="hint",
                    code="U006",
                    summary=f"Layout entry '{zone_id}' is not matched as a container (zone/deck)",
                    location=f"layout.{zone_id}",
                )
            )

    # U007: No event_defaults set
    if not event_defaults:
        result.add(
            ValidationMessage(
                level="warning",
                code="U007",
                summary="No event_defaults set — unmatched events will have no bubble",
                suggestion='Add "event_defaults": {"bubble": "action"} to the .ui.json',
            )
        )

    # U008: Event match not in action names or consequence/auto_tick emit types
    action_names = {a_name for a_name in config.actions}
    # Also collect emit_event types from consequences and auto_tick
    emit_types: set[str] = set()

    def _collect_emits(effects: list[Any]) -> None:
        for eff in effects:
            op = eff.operator if hasattr(eff, "operator") else eff.get("operator", "")
            if op == "emit_event":
                t = eff.type if hasattr(eff, "type") else eff.get("type", "")
                if t:
                    emit_types.add(t)
            if op == "for_each":
                subs = eff.sub_effects if hasattr(eff, "sub_effects") else eff.get("effects", [])
                if subs:
                    _collect_emits(subs)

    for cons in (config.consequences or {}).values():
        _collect_emits(cons.effects)
    at_tick: Any = config.auto_tick or {}
    at_iter = at_tick.values() if isinstance(at_tick, dict) else at_tick
    for at in at_iter:
        _collect_emits(at.effects)
    known_events = action_names | emit_types
    event_matches = set()
    for ev in events:
        if isinstance(ev, dict) and "match" in ev:
            event_matches.add(ev["match"])
    for match_name in event_matches:
        if match_name not in known_events:
            result.add(
                ValidationMessage(
                    level="hint",
                    code="U008",
                    summary=f"Event '{match_name}' not in actions or consequence emit types",
                    location="events[]",
                )
            )

    # U009: Excessive zone overlap in layout (accounts for rotation visual overflow)
    zone_rects = []
    for zid, pos in layout.items():
        if zid in zone_ids and isinstance(pos, dict):
            # Expand bounds by rotation visual overflow (~sin(angle) * max(w,h)/2)
            rot_rad = abs(pos.get("rotation", 0)) * math.pi / 180
            expand = math.sin(rot_rad) * max(pos.get("w", 250), pos.get("h", 200)) / 2
            zone_rects.append(
                (
                    zid,
                    pos.get("x", 0) - expand,
                    pos.get("y", 0) - expand,
                    pos.get("w", 250) + 2 * expand,
                    pos.get("h", 200) + 2 * expand,
                )
            )
    for i, (id_a, ax, ay, aw, ah) in enumerate(zone_rects):
        for id_b, bx, by, bw, bh in zone_rects[i + 1 :]:
            ox = max(0, min(ax + aw, bx + bw) - max(ax, bx))
            oy = max(0, min(ay + ah, by + bh) - max(ay, by))
            overlap_area = ox * oy
            smaller_area = min(aw * ah, bw * bh)
            if smaller_area > 0 and overlap_area / smaller_area > MAX_ZONE_OVERLAP_RATIO:
                pct = int(overlap_area / smaller_area * 100)
                result.add(
                    ValidationMessage(
                        level="warning",
                        code="U009",
                        summary=f"Zones '{id_a}' and '{id_b}' overlap {pct}% — may hide entities/agents",
                        location="layout",
                        suggestion="Adjust positions so overlap is under 25% of the smaller zone",
                    )
                )

    # U010: state_effects on agent rules (entity-only feature)
    for i, rule in enumerate(rules):
        if not isinstance(rule, dict):
            continue
        match = rule.get("match", {})
        bind = rule.get("bind", {})
        is_agent = isinstance(match, dict) and match.get("type") == "agent"
        has_effects = isinstance(bind, dict) and "state_effects" in bind
        if is_agent and has_effects:
            result.add(
                ValidationMessage(
                    level="warning",
                    code="U010",
                    summary="state_effects on agent rule — not applied to avatars",
                    location=f"rules[{i}].bind.state_effects",
                    suggestion="Remove state_effects from agent rules",
                )
            )
