"""Level 4: Smoke test (try each action with each agent)."""

from __future__ import annotations

from typing import Any

from worldseed.engine.state_store import StateStore
from worldseed.models.config_schema import ActionConfig, SceneConfig
from worldseed.scene.populator import populate
from worldseed.scene.validator import SmokeReport


def run_smoke(config: SceneConfig) -> SmokeReport:
    """Check which agents can execute which actions in initial state."""
    from worldseed.dsl.preconditions import evaluate as eval_pre
    from worldseed.models.entity import Entity

    store = StateStore()
    populate(config, store)

    # populate() skips agents (they go through register_agent at runtime).
    # For smoke testing we need them in the store so we can evaluate
    # preconditions against their properties.
    for agent_cfg in config.agents:
        props = dict(agent_cfg.properties) if agent_cfg.properties else {}
        store.add(Entity(id=agent_cfg.id, type="agent", _data=props))

    agents = store.query_by_type("agent")
    report = SmokeReport()

    for action_name, action_cfg in config.actions.items():
        capable: list[str] = []

        if not action_cfg.preconditions:
            # No preconditions = all agents can execute
            capable = [a.id for a in agents]
        else:
            for agent in agents:
                ctx = _build_smoke_ctx(agent, action_cfg, store)
                try:
                    if all(eval_pre(p, store, ctx) for p in action_cfg.preconditions):
                        capable.append(agent.id)
                except Exception:
                    capable.append(agent.id)  # Benefit of the doubt

        report.action_agents[action_name] = capable

    return report


def _build_smoke_ctx(agent: Any, action_cfg: ActionConfig, store: StateStore) -> dict[str, Any]:
    ctx: dict[str, Any] = {
        "agent_id": agent.id,
        "tick": 1,
        "action_params": {},
    }
    for param in action_cfg.params:
        if param.type == "entity_ref":
            # Try connected spaces first (for move-like actions)
            loc = agent.get("location")
            if loc:
                loc_entity = store.get(loc)
                if loc_entity:
                    connects = loc_entity.get("connects_to")
                    if isinstance(connects, list) and connects:
                        ctx["action_params"][param.name] = connects[0]
                    elif isinstance(connects, dict) and connects:
                        ctx["action_params"][param.name] = next(iter(connects))
            # Fallback: first non-self entity
            if param.name not in ctx["action_params"]:
                for e in store.all_entities():
                    if e.id != agent.id:
                        ctx["action_params"][param.name] = e.id
                        break
        elif param.type == "number":
            ctx["action_params"][param.name] = 1
        elif param.type in ("string", "free_text"):
            ctx["action_params"][param.name] = "test"
    return ctx
