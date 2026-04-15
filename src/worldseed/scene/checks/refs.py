"""Level 2: Static reference checks for scene configs."""

from __future__ import annotations

import re
from collections import deque
from typing import Any

from worldseed.models.config_schema import (
    ActionConfig,
    EffectConfig,
    PreconditionConfig,
    SceneConfig,
)
from worldseed.scene.validator import ValidationMessage, ValidationResult, _suggest_fix


def check_duplicate_ids(config: SceneConfig, result: ValidationResult) -> None:
    seen: set[str] = set()
    for entity in config.entities:
        if entity.id in seen:
            result.add(
                ValidationMessage(
                    level="error",
                    code="E001",
                    summary=f"Duplicate entity ID: '{entity.id}'",
                )
            )
        seen.add(entity.id)


def check_property_refs(
    entity_id: str,
    prop_name: str,
    prop_val: Any,
    entity_ids: set[str],
    result: ValidationResult,
    location_prefix: str,
) -> None:
    """Check a single property value for dangling entity references.

    Only flags references that look like they *should* be entity IDs
    (i.e. the list/dict already contains at least one valid entity ID).
    """
    targets: list[str] = []
    if isinstance(prop_val, list):
        targets = [v for v in prop_val if isinstance(v, str)]
    elif isinstance(prop_val, dict):
        targets = [k for k in prop_val if isinstance(k, str)]
    else:
        return

    if not targets:
        return

    # Only flag if at least one entry IS a valid entity (looks like a ref list)
    has_valid = any(t in entity_ids for t in targets)
    if not has_valid:
        return

    for t in targets:
        if t not in entity_ids:
            result.add(
                ValidationMessage(
                    level="error",
                    code="E002",
                    summary=(f"Entity '{entity_id}' property '{prop_name}' references unknown entity '{t}'"),
                    location=f"{location_prefix}.{prop_name}",
                    suggestion=_suggest_fix(t, entity_ids),
                )
            )


def check_relationship_targets(config: SceneConfig, entity_ids: set[str], result: ValidationResult) -> None:
    """Check that property-based relationships reference valid entity IDs.

    Scans list-valued and dict-valued properties for entity references.
    A property value is treated as a relationship if its entries are
    strings that match known entity IDs (or should match them).
    """
    for entity in config.entities:
        # Check property-based relationships (list of IDs or dict with ID keys)
        for prop_name, prop_val in entity.properties.items():
            check_property_refs(
                entity.id,
                prop_name,
                prop_val,
                entity_ids,
                result,
                location_prefix=f"entities[{entity.id}]",
            )


def check_effect_targets(config: SceneConfig, entity_ids: set[str], result: ValidationResult) -> None:
    all_effects: list[tuple[str, EffectConfig]] = []
    for name, action in config.actions.items():
        for eff in action.effects:
            all_effects.append((f"actions.{name}", eff))
    for name, cons in config.consequences.items():
        for eff in cons.effects:
            all_effects.append((f"consequences.{name}", eff))
    for i, auto in enumerate(config.auto_tick):
        for eff in auto.effects:
            all_effects.append((f"auto_tick[{i}]", eff))

    for location, effect in all_effects:
        check_single_effect(effect, entity_ids, location, result)


def check_single_effect(
    effect: EffectConfig,
    entity_ids: set[str],
    location: str,
    result: ValidationResult,
) -> None:
    if effect.operator == "rotate":
        for field_name, field_val in [
            ("target", effect.target),
            ("sequence", effect.sequence),
            ("skip", effect.skip),
        ]:
            if field_val:
                eid = extract_entity_id(field_val)
                if eid and eid not in entity_ids:
                    result.add(
                        ValidationMessage(
                            level="error",
                            code="E003",
                            summary=(f"rotate {field_name}='{field_val}' references unknown entity '{eid}'"),
                            location=location,
                            suggestion=_suggest_fix(eid, entity_ids),
                        )
                    )

    if effect.operator in ("set", "increment", "decrement") and effect.target:
        eid = extract_entity_id(effect.target)
        if eid and eid not in entity_ids:
            result.add(
                ValidationMessage(
                    level="error",
                    code="E003",
                    summary=(f"Effect target '{effect.target}' references unknown entity '{eid}'"),
                    location=location,
                    suggestion=_suggest_fix(eid, entity_ids),
                )
            )

    if effect.operator == "remove_entity" and effect.target:
        eid = extract_entity_id(effect.target)
        if eid and eid not in entity_ids:
            result.add(
                ValidationMessage(
                    level="hint",
                    code="H001",
                    summary=(f"remove_entity targets '{eid}' which doesn't exist (may be created at runtime)"),
                    location=location,
                )
            )

    if effect.operator in ("add_relationship", "remove_relationship"):
        for field_name, field_val in [("from", effect.from_entity), ("to", effect.to)]:
            if field_val and not field_val.startswith("$"):
                if field_val not in entity_ids:
                    result.add(
                        ValidationMessage(
                            level="error",
                            code="E004",
                            summary=(f"{effect.operator} {field_name}='{field_val}' references unknown entity"),
                            location=location,
                            suggestion=_suggest_fix(field_val, entity_ids),
                        )
                    )


def extract_entity_id(target: str) -> str | None:
    if target.startswith("$") or target.startswith("agent."):
        return None
    return target.split(".")[0]


def check_agent_locations(config: SceneConfig, entity_ids: set[str], result: ValidationResult) -> None:
    space_ids = {e.id for e in config.entities if e.type == "space"}
    if not space_ids:
        return
    for agent in config.agents:
        loc = agent.properties.get("location")
        if loc is None:
            continue
        if loc not in entity_ids:
            result.add(
                ValidationMessage(
                    level="error",
                    code="E005",
                    summary=(f"Agent '{agent.id}' has location '{loc}' but no entity with that ID exists"),
                    location=f"agents[{agent.id}].location",
                    suggestion=_suggest_fix(loc, entity_ids),
                )
            )
        elif loc not in space_ids:
            etype = next((e.type for e in config.entities if e.id == loc), "?")
            result.add(
                ValidationMessage(
                    level="warning",
                    code="W001",
                    summary=(f"Agent '{agent.id}' location '{loc}' is type '{etype}', not 'space'"),
                    location=f"agents[{agent.id}].location",
                )
            )


def check_event_scopes(config: SceneConfig, result: ValidationResult) -> None:
    builtin = {"global", "target_only"}
    declared = set(config.perception.event_scopes.keys())
    valid = builtin | declared

    for name, action in config.actions.items():
        for ev in action.events:
            if ev.scope not in valid:
                result.add(
                    ValidationMessage(
                        level="hint",
                        code="H002",
                        summary=(f"Action '{name}' uses undeclared scope '{ev.scope}' (will default to global)"),
                        location=f"actions.{name}.events",
                    )
                )


def check_action_params(config: SceneConfig, result: ValidationResult) -> None:
    for name, action in config.actions.items():
        param_names = {p.name for p in action.params}
        param_names.update(("agent", "tick"))
        refs = collect_dollar_refs_action(action)
        for ref in refs:
            if ref not in param_names:
                result.add(
                    ValidationMessage(
                        level="warning",
                        code="W002",
                        summary=(
                            f"Action '{name}' references '${ref}' "
                            f"but params declares: "
                            f"{sorted(param_names - {'agent', 'tick'})}"
                        ),
                        location=f"actions.{name}",
                    )
                )


def collect_dollar_refs_action(action: ActionConfig) -> set[str]:
    refs: set[str] = set()
    for p in action.preconditions:
        collect_refs_precondition(p, refs)
    for e in action.effects:
        collect_refs_effect(e, refs)
    for ev in action.events:
        collect_refs_str(ev.detail, refs)
    return refs


def collect_refs_precondition(p: PreconditionConfig, refs: set[str]) -> None:
    if p.left is not None:
        collect_refs_str(str(p.left), refs)
    if p.right is not None:
        collect_refs_str(str(p.right), refs)
    if p.condition is not None:
        collect_refs_precondition(p.condition, refs)
    for c in p.conditions or []:
        collect_refs_precondition(c, refs)


def collect_refs_effect(e: EffectConfig, refs: set[str]) -> None:
    fields = [
        e.target,
        e.value,
        e.by,
        e.detail,
        e.from_entity,
        e.to,
        e.sequence,
        e.skip,
        e.source,
        e.event_target,
    ]
    for val in fields:
        if val is not None:
            collect_refs_str(str(val), refs)
    if e.sub_effects:
        for sub in e.sub_effects:
            collect_refs_effect(sub, refs)
    if e.when is not None:
        collect_refs_precondition(e.when, refs)


def collect_refs_str(s: str, refs: set[str]) -> None:
    for match in re.finditer(r"\$(\w+)", s):
        refs.add(match.group(1))


def check_graph_connectivity(config: SceneConfig, result: ValidationResult) -> None:
    spaces = {e.id for e in config.entities if e.type == "space"}
    if len(spaces) <= 1:
        return

    adj: dict[str, set[str]] = {s: set() for s in spaces}
    for entity in config.entities:
        if entity.id not in spaces:
            continue
        connects = entity.properties.get("connects_to", [])
        if isinstance(connects, list):
            for target in connects:
                if isinstance(target, str) and target in spaces:
                    adj[entity.id].add(target)
        elif isinstance(connects, dict):
            for target in connects:
                if isinstance(target, str) and target in spaces:
                    adj[entity.id].add(target)

    agent_locs: set[str] = set()
    for agent in config.agents:
        loc = agent.properties.get("location")
        if loc and loc in spaces:
            agent_locs.add(loc)

    if not agent_locs:
        return

    start = next(iter(agent_locs))
    reachable = bfs(start, adj)
    unreachable = spaces - reachable
    if unreachable:
        result.add(
            ValidationMessage(
                level="warning",
                code="W003",
                summary=(f"Unreachable spaces from '{start}': {sorted(unreachable)}"),
            )
        )

    for agent in config.agents:
        loc = agent.properties.get("location")
        if loc and loc in spaces:
            r = bfs(loc, adj)
            if len(r) == 1 and len(spaces) > 1:
                result.add(
                    ValidationMessage(
                        level="hint",
                        code="H003",
                        summary=(f"Agent '{agent.id}' at '{loc}' has no outgoing connections"),
                    )
                )


def check_auto_tick_emit_event(config: SceneConfig, result: ValidationResult) -> None:
    """Warn if any auto_tick effect uses emit_event (fires every tick)."""
    for auto in config.auto_tick:
        for effect in auto.effects:
            if effect.operator == "emit_event":
                result.add(
                    ValidationMessage(
                        level="warning",
                        code="W004",
                        summary=("auto_tick emits events every tick — use consequences instead"),
                        location=f"auto_tick[{auto.description}]",
                    )
                )


_KNOWN_DSL_FUNCTIONS = {
    "relationships_of",
    "count",
    "sum",
    "max_by",
    "event",
    "length",
    "random",
}
_RELATIONSHIPS_OF_RE = re.compile(r"^relationships_of\(\s*(\$[\w.]+)\s*,\s*type\s*=\s*(\w+)\s*\)$")


def check_enum_from(
    config: SceneConfig,
    result: ValidationResult,
) -> None:
    """Validate enum_from expressions on action params.

    Checks:
      1. Syntax is recognized (built-in $visible, or DSL function call)
      2. $agent.X references — X exists on at least one agent's properties
      3. type=Y references — Y exists as a property on at least one entity
    """
    # Collect all property names across all entities and agents
    all_entity_props: set[str] = set()
    for e in config.entities:
        all_entity_props.update(e.properties.keys())

    all_agent_props: set[str] = set()
    for a in config.agents:
        all_agent_props.update(a.properties.keys())
    # Include template properties (agents inherit these at registration)
    for t in config.templates.values():
        all_agent_props.update(t.properties.keys())
    # Include default_spawn properties
    all_agent_props.update(config.scene.default_spawn.keys())

    for action_name, action in config.actions.items():
        for p in action.params:
            if not p.enum_from:
                continue

            expr = p.enum_from.strip()

            # Built-in: $visible
            if expr == "$visible":
                continue

            # relationships_of($agent.X, type=Y)
            m = _RELATIONSHIPS_OF_RE.match(expr)
            if m:
                agent_path = m.group(1)  # e.g. $agent.location
                rel_type = m.group(2)  # e.g. connects_to

                # Validate $agent.X — X should exist on agents
                if agent_path.startswith("$agent."):
                    prop_name = agent_path.split(".", 1)[1]
                    if prop_name not in all_agent_props:
                        close = _suggest_fix(prop_name, all_agent_props)
                        result.add(
                            ValidationMessage(
                                level="warning",
                                code="W005",
                                summary=(
                                    f"Action '{action_name}' param '{p.name}': "
                                    f"enum_from references '$agent.{prop_name}' "
                                    f"but no agent has property '{prop_name}'"
                                ),
                                location=f"actions.{action_name}.params.{p.name}",
                                suggestion=close,
                            )
                        )

                # Validate type=Y — Y should exist as a property on entities
                if rel_type not in all_entity_props and rel_type not in all_agent_props:
                    result.add(
                        ValidationMessage(
                            level="warning",
                            code="W006",
                            summary=(
                                f"Action '{action_name}' param '{p.name}': "
                                f"enum_from references type='{rel_type}' "
                                f"but no entity has property '{rel_type}'"
                            ),
                            location=f"actions.{action_name}.params.{p.name}",
                        )
                    )
                continue

            # Check for other known DSL function patterns
            func_match = re.match(r"^(\w+)\(", expr)
            if func_match:
                func_name = func_match.group(1)
                if func_name not in _KNOWN_DSL_FUNCTIONS:
                    result.add(
                        ValidationMessage(
                            level="warning",
                            code="W007",
                            summary=(
                                f"Action '{action_name}' param '{p.name}': "
                                f"enum_from uses unknown function '{func_name}'"
                            ),
                            location=f"actions.{action_name}.params.{p.name}",
                        )
                    )
                continue

            # Unrecognized expression syntax
            result.add(
                ValidationMessage(
                    level="warning",
                    code="W008",
                    summary=(f"Action '{action_name}' param '{p.name}': unrecognized enum_from expression: '{expr}'"),
                    location=f"actions.{action_name}.params.{p.name}",
                )
            )


def bfs(start: str, adj: dict[str, set[str]]) -> set[str]:
    visited: set[str] = set()
    queue: deque[str] = deque([start])
    while queue:
        node = queue.popleft()
        if node in visited:
            continue
        visited.add(node)
        for n in adj.get(node, set()):
            if n not in visited:
                queue.append(n)
    return visited
