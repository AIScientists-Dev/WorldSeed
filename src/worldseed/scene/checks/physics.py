"""Level 3: Physics simulation (N ticks, no agents)."""

from __future__ import annotations

from typing import Any

from worldseed.models.config_schema import SceneConfig
from worldseed.scene.populator import populate
from worldseed.scene.validator import PhysicsReport


def run_physics(config: SceneConfig, ticks: int) -> PhysicsReport:
    """Simulate auto_tick + consequences for N ticks with no agent input."""
    from worldseed.dsl.effects import execute as exec_effect
    from worldseed.dsl.preconditions import evaluate as eval_pre
    from worldseed.engine.event_log import EventLog
    from worldseed.engine.state_store import StateStore
    from worldseed.utils.nested import nested_get

    store = StateStore()
    populate(config, store)
    event_log = EventLog()

    report = PhysicsReport(ticks=ticks)

    # Snapshot initial numeric properties
    numeric_props: dict[str, str] = {}  # "entity.prop" -> entity_id
    for entity in store.all_entities():
        for k, v in entity.items():
            if isinstance(v, (int, float)):
                key = f"{entity.id}.{k}"
                numeric_props[key] = entity.id
                report.trajectories[key] = [float(v)]

    consequence_triggered: set[str] = set()
    ctx: dict[str, Any] = {
        "agent_id": "",
        "tick": 0,
        "action_params": {},
        "event_log": event_log,
    }

    for tick in range(1, ticks + 1):
        ctx["tick"] = tick

        # Run auto_tick
        for auto in config.auto_tick:
            if auto.condition:
                try:
                    if not all(eval_pre(c, store, ctx) for c in auto.condition):
                        continue
                except Exception:
                    continue
            for eff in auto.effects:
                try:
                    exec_effect(eff, store, event_log, ctx, tick=tick)
                except Exception:
                    pass

        # Run consequence triggers (check only)
        for cname, cons in config.consequences.items():
            try:
                triggered = all(eval_pre(t, store, ctx) for t in cons.trigger)
                if triggered:
                    consequence_triggered.add(cname)
            except Exception:
                pass

        # Record trajectories (using nested_get for nested properties)
        for key in numeric_props:
            eid, prop = key.split(".", 1)
            ent = store.get(eid)
            if ent:
                val = nested_get(ent.data, prop)
                if isinstance(val, (int, float)):
                    report.trajectories[key].append(float(val))
                else:
                    report.trajectories[key].append(0.0)
            else:
                report.trajectories[key].append(0.0)

        event_log.cleanup(tick)

    report.consequences_triggered = sorted(consequence_triggered)
    report.consequences_never_triggered = sorted(set(config.consequences.keys()) - consequence_triggered)

    return report
