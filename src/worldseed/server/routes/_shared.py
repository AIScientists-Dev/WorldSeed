"""Shared helpers and state for route modules."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path
from typing import Any

import structlog
from fastapi import FastAPI, HTTPException

from worldseed.server._validation import validate_agent
from worldseed.server.websocket import ConnectionManager
from worldseed.world import WorldEngine

log = structlog.get_logger()

_PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent
_UI_DIR = _PROJECT_ROOT / "frontend" / "dist"

DEFAULT_GATEWAY_TOKEN = "worldseed-gw-token"

# Shared mutable state — token maps shared across all route files
tokens: dict[str, str] = {}
agent_tokens: dict[str, str] = {}


def build_gateway_payload(engine: WorldEngine, run_id: str) -> dict[str, Any]:
    """Build the gateway world payload — single source of truth.

    Used by both auth_ok (websocket.py) and run_switched (world.py).
    Same payload structure, same agent/config assembly logic.
    """
    agents: list[dict[str, Any]] = []
    preset_ids: set[str] = set()
    for agent_cfg in engine.config.agents:
        preset_ids.add(agent_cfg.id)
        profile = engine.get_agent_profile(agent_cfg.id)
        char = dict(profile.character) if profile else dict(agent_cfg.character)
        is_system = profile.system if profile else agent_cfg.system
        agents.append({"id": agent_cfg.id, "character": char, "system": is_system})
    for aid in engine.get_registered_agents():
        if aid not in preset_ids:
            profile = engine.get_agent_profile(aid)
            is_system = profile.system if profile else False
            agents.append({"id": aid, "character": dict(profile.character) if profile else {}, "system": is_system})

    import yaml

    # Compute expensive data ONCE, then derive per-agent variants
    stripped = engine.load_stripped_config()
    shared_catalog = engine.action_catalog()
    public_yaml = yaml.dump(stripped, default_flow_style=False, allow_unicode=True, sort_keys=False)

    per_agent_configs: dict[str, str] = {}
    per_agent_catalogs: dict[str, dict[str, dict[str, Any]]] = {}
    for agent_entry in agents:
        aid_str = str(agent_entry["id"])
        if engine.state.get(aid_str) is not None:
            available = engine.actions_available_to(aid_str)
            all_actions = stripped.get("actions", {})
            agent_raw = {**stripped, "actions": {n: d for n, d in all_actions.items() if n in available}}
            per_agent_configs[aid_str] = yaml.dump(
                agent_raw,
                default_flow_style=False,
                allow_unicode=True,
                sort_keys=False,
            )
            per_agent_catalogs[aid_str] = {n: info for n, info in shared_catalog.items() if n in available}
        else:
            per_agent_configs[aid_str] = public_yaml
            per_agent_catalogs[aid_str] = shared_catalog

    wake_cfg = engine.config.perception.wake_summary
    return {
        "scene": engine.config.scene.id,
        "scene_description": engine.config.scene.description or "",
        "action_catalog": shared_catalog,
        "per_agent_catalogs": per_agent_catalogs,
        "agents": agents,
        "public_config": public_yaml,
        "per_agent_configs": per_agent_configs,
        "run_id": run_id,
        "language": engine.language,
        "wake_summary": {
            "self_fields": wake_cfg.self_fields,
            "entities": wake_cfg.entities,
            "entity_types": wake_cfg.entity_types,
            "agent_fields": wake_cfg.agent_fields,
        },
    }


def _eng(app: FastAPI) -> WorldEngine:
    """Get current engine or raise 503."""
    engine = app.state.engine
    if engine is None:
        raise HTTPException(503, detail="World not started")
    result: WorldEngine = engine
    return result


def _require_agent(engine: WorldEngine, agent_id: str) -> None:
    err = validate_agent(engine, agent_id)
    if err:
        raise HTTPException(404, detail=err)


def _resolve_agent(token: str | None, agent_id: str | None, tkns: dict[str, str]) -> str:
    if token is not None:
        resolved = tkns.get(token)
        if resolved is None:
            raise HTTPException(401, detail="Invalid token")
        return resolved
    if agent_id is not None:
        return agent_id
    raise HTTPException(400, detail="Provide token or agent_id")


def _update_openclaw_config(port: int) -> None:
    """Update openclaw config so the WorldSeed plugin connects to the right port.

    Writes two sections:
    - plugins.entries.worldseed — plugin config (serverUrl, gatewayToken)
    - channels.worldseed — channel activation (required by OpenClaw >=2026.4.8)
    """
    import json

    cfg_path = Path.home() / ".openclaw" / "openclaw.json"
    if not cfg_path.exists():
        return
    try:
        raw = cfg_path.read_text()
        cfg = json.loads(raw)
        target_url = f"ws://localhost:{port}/ws"

        # Plugin entry
        ws_entry = cfg.setdefault("plugins", {}).setdefault("entries", {}).setdefault("worldseed", {})
        ws_config = ws_entry.setdefault("config", {})
        ws_entry["enabled"] = True
        ws_config["serverUrl"] = target_url
        ws_config["gatewayToken"] = DEFAULT_GATEWAY_TOKEN

        # Channel activation (gateway won't start the channel without this)
        ch = cfg.setdefault("channels", {}).setdefault("worldseed", {})
        ch["enabled"] = True
        ch.setdefault("accounts", {}).setdefault("default", {}).update(
            {"serverUrl": target_url, "gatewayToken": DEFAULT_GATEWAY_TOKEN}
        )

        cfg_path.write_text(json.dumps(cfg, indent=4))
    except Exception:
        log.warning("openclaw_config_update_failed")


def _spawn_gateway(app: FastAPI) -> None:
    """Spawn openclaw gateway as a subprocess."""
    _kill_gateway(app)
    # Close previous log handle if stored (prevents file handle leaks on re-spawn)
    old_handle = getattr(app.state, "_gw_log_handle", None)
    if old_handle is not None:
        try:
            old_handle.close()
        except OSError:
            pass
        app.state._gw_log_handle = None
    try:
        gw_log = Path("/tmp/worldseed-logs/gateway.log")
        gw_log.parent.mkdir(parents=True, exist_ok=True)
        gw_out = open(gw_log, "a")  # noqa: SIM115
        app.state._gw_log_handle = gw_out
        port = app.state.port
        # Update openclaw config to match current port (survives manual restarts)
        _update_openclaw_config(port)
        # Pass via env for immediate use
        env = {**os.environ, "WORLDSEED_URL": f"ws://localhost:{port}/ws", "WORLDSEED_TOKEN": DEFAULT_GATEWAY_TOKEN}
        proc = subprocess.Popen(
            ["openclaw", "gateway"],
            stdout=gw_out,
            stderr=gw_out,
            env=env,
        )
        app.state.gateway_proc = proc
        log.info("gateway_spawned", pid=proc.pid)
    except FileNotFoundError:
        log.warning(
            "gateway_not_found",
            msg="openclaw not installed. Install: npm install -g openclaw@latest",
        )
        app.state.gateway_proc = None


def _kill_gateway(app: FastAPI) -> None:
    """Kill the gateway subprocess if running (ours + any external)."""
    # Kill our subprocess
    proc = getattr(app.state, "gateway_proc", None)
    if proc is not None and proc.poll() is None:
        proc.terminate()
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
        log.info("gateway_killed", pid=proc.pid)
    app.state.gateway_proc = None
    # Stop any externally-running gateway (graceful → force)
    try:
        subprocess.run(
            ["openclaw", "gateway", "stop"],
            capture_output=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    # Unload launchd agent if present (prevents auto-respawn)
    uid = os.getuid()
    try:
        subprocess.run(
            ["launchctl", "bootout", f"gui/{uid}", "com.openclaw.gateway"],
            capture_output=True,
            timeout=5,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    # Force kill if still alive
    try:
        subprocess.run(
            ["pkill", "-f", "openclaw-gateway"],
            capture_output=True,
            timeout=3,
        )
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass
    log.info("gateway_cleanup_done")


async def maybe_auto_start_ticks(
    engine: WorldEngine,
    tick_runner: Any,
    agents_ready: set[str],
) -> bool:
    """Start ticks if all preset (non-system) agents are ready.

    Returns True if ticks were started, False otherwise.
    Called by websocket._handle_register for auto-start when last agent registers.
    """
    if tick_runner is None or tick_runner.running:
        return False
    expected = engine.registry.expected_agent_ids()
    if expected <= agents_ready:
        log.info(
            "all_agents_ready",
            ready=sorted(agents_ready),
            msg="All preset agents registered — auto-starting ticks",
        )
        await tick_runner.start()
        return True
    return False


def build_intro_data(engine: WorldEngine) -> dict[str, Any]:
    """Build intro page data from a live engine. Used by /api/intro and /api/runs/{id}/intro."""
    cfg = engine.config
    scene = {"id": cfg.scene.id, "description": cfg.scene.description}
    entities = [e.to_full_dict() for e in engine.state.all_entities() if e.type != "agent"]
    agents = []
    for agent_cfg in cfg.agents:
        if agent_cfg.system:
            continue
        profile = engine.get_agent_profile(agent_cfg.id)
        entity = engine.state.get(agent_cfg.id)
        if profile is None or entity is None:
            continue
        agents.append(
            {
                "id": agent_cfg.id,
                "character": dict(profile.character),
                "properties": dict(entity.data),
            }
        )
    return {"scene": scene, "entities": entities, "agents": agents}


def _gateway_status(app: FastAPI, ws_manager: ConnectionManager) -> dict[str, Any]:
    """Get gateway process and connection status."""
    proc = getattr(app.state, "gateway_proc", None)
    proc_alive = proc is not None and proc.poll() is None
    ws_count = len(ws_manager._gateways) if hasattr(ws_manager, "_gateways") else 0
    return {
        "process_alive": proc_alive,
        "pid": proc.pid if proc is not None and proc_alive else None,
        "ws_connections": ws_count,
        "connected": ws_count > 0,
    }
