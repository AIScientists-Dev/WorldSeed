"""Unified run data routes — single API for both live and history runs.

Endpoints:
  /api/runs                         — list all past runs
  /api/runs/{run_id}/state          — entity state (live or disk)
  /api/runs/{run_id}/stream         — stream.jsonl records
  /api/runs/{run_id}/meta           — run metadata
  /api/runs/{run_id}/summary        — kind counts + token totals
  /api/runs/{run_id}/config         — scene config YAML
  /api/runs/{run_id}/snapshots      — list available per-tick snapshot ticks
  /api/runs/{run_id}/snapshots/{t}  — entity state at tick t (for replay)
  /api/configs                      — list available scene configs
  /api/runs?agent_id=               — agent session list
  /api/logs?agent_id=&run_id=       — agent session logs
  /api/logs/live?agent_id=&run_id=  — SSE tail of agent session JSONL
  /api/agent-texts?run_id=          — agent text responses
  /api/past-runs                    — alias for /api/runs (backward compat)
  /api/past-runs/{id}/stream        — alias for /api/runs/{id}/stream
  /api/past-runs/{id}/state         — alias for /api/runs/{id}/state
  /api/past-runs/{id}/summary       — alias for /api/runs/{id}/summary
"""

from __future__ import annotations

import asyncio
import json
import os
from pathlib import Path
from typing import Any

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import StreamingResponse

from worldseed.paths import run_dir
from worldseed.server.logs import (
    find_all_sessions,
    read_agent_texts,
    read_session_logs,
    resolve_session_file,
)
from worldseed.server.websocket import ConnectionManager


def create_runs_router(app: FastAPI, ws_manager: ConnectionManager) -> APIRouter:
    router = APIRouter()

    def _run_dir(run_id: str) -> Path:
        return run_dir(run_id)

    def _oc_dir() -> str:
        return app.state.settings.get("openclaw_dir", "") or ""

    # ── Run list ──────────────────────────────────────────

    @router.get("/api/runs")
    async def api_runs_list(agent_id: str = "") -> Any:
        """List runs. If agent_id given, returns that agent's sessions."""
        if agent_id:
            return {
                "agent_id": agent_id,
                "runs": [
                    {"run_id": s["run_id"], "updated_at": s["updated_at"]}
                    for s in find_all_sessions(
                        agent_id,
                        openclaw_dir=_oc_dir(),
                    )
                ],
            }
        from worldseed.persistence import list_runs

        return list_runs()

    @router.get("/api/past-runs")
    async def api_past_runs_compat() -> list[dict[str, Any]]:
        """Backward-compatible alias for /api/runs."""
        from worldseed.persistence import list_runs

        return list_runs()

    # ── Per-run endpoints ─────────────────────────────────

    def _read_entities(run_dir: Path) -> tuple[list[dict[str, Any]], int] | None:
        """Read entities + tick from state files on disk."""
        from worldseed.models.entity import Entity

        for name in ("state.json", "state_final.json"):
            path = run_dir / name
            if not path.is_file():
                continue
            raw = json.loads(path.read_text(encoding="utf-8"))
            # Backward compat: old format is bare list, new is {entities, characters}
            entity_list = raw.get("entities", raw) if isinstance(raw, dict) else raw
            entities = []
            for e_dict in entity_list:
                d = dict(e_dict)
                eid = d.pop("id")
                etype = d.pop("type")
                d.pop("constraints", None)
                entity = Entity(id=eid, type=etype, _data=d)
                entities.append(entity.to_dict())

            tick = 0
            tick_path = run_dir / "tick"
            if tick_path.is_file():
                try:
                    tick = int(tick_path.read_text().strip())
                except (ValueError, OSError):
                    pass
            return entities, tick
        return None

    def _entities_from_config(run_dir: Path) -> list[dict[str, Any]]:
        """Build initial entities from config.yaml (fallback when no state)."""
        import yaml

        from worldseed.models.entity import Entity

        config_path = run_dir / "config.yaml"
        if not config_path.is_file():
            return []
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        entities = []
        for e_dict in config.get("entities", []):
            d = dict(e_dict)
            eid = d.pop("id")
            etype = d.pop("type")
            d.pop("constraints", None)
            # Flatten nested properties dict
            props = d.pop("properties", {})
            if isinstance(props, dict):
                d.update(props)
            entity = Entity(id=eid, type=etype, _data=d)
            entities.append(entity.to_dict())
        # Merge template properties into agents
        templates = config.get("templates", {})
        for a_dict in config.get("agents", []):
            d = dict(a_dict)
            eid = d.pop("id")
            d.pop("character", None)
            tpl_name = d.pop("template", None)
            d.pop("templates", None)
            # Apply template properties as defaults
            if tpl_name and tpl_name in templates:
                tpl = templates[tpl_name]
                tpl_props = tpl.get("properties", {}) if isinstance(tpl, dict) else {}
                for k, v in tpl_props.items():
                    if k not in d.get("properties", {}):
                        d.setdefault("properties", {})[k] = v
            # Flatten properties into d for Entity constructor
            props = d.pop("properties", {})
            d.update(props)
            entity = Entity(id=eid, type="agent", _data=d)
            entities.append(entity.to_dict())
        return entities

    def _system_agent_ids(run_dir: Path, config: dict[str, Any] | None = None) -> set[str]:
        """Get system agent IDs from saved config or live engine.

        For live runs, delegates to engine.registry. For historical runs,
        reads config.yaml to find agents with system: true, plus 'narrator'
        if the config has a narrator setting. Pass pre-parsed config to avoid
        re-reading the file.
        """
        import yaml

        engine = app.state.engine
        if engine:
            return set(engine.registry.get_system_agents())

        if config is None:
            config_path = run_dir / "config.yaml"
            if not config_path.is_file():
                return set()
            config = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        ids: set[str] = set()
        for a in config.get("agents", []):
            if a.get("system"):
                ids.add(a["id"])
        # Narrator is a system agent auto-created by _setup_narrator
        if config.get("narrator"):
            ids.add("narrator")
        return ids

    def _config_extras(run_dir: Path) -> tuple[dict[str, Any], list[dict[str, Any]]]:
        """Parse action defs + characters from config.yaml."""
        import yaml

        config_path = run_dir / "config.yaml"
        if not config_path.is_file():
            return {}, []
        config = yaml.safe_load(config_path.read_text(encoding="utf-8"))

        actions = {}
        for name, a in (config.get("actions") or {}).items():
            actions[name] = {
                "description": a.get("description", ""),
                "params": [
                    {
                        "name": p["name"],
                        "type": p.get("type", ""),
                        "required": p.get("required", False),
                    }
                    for p in a.get("params", [])
                ],
                "events": [
                    {
                        "type": e.get("type", ""),
                        "scope": e.get("scope", "global"),
                    }
                    for e in a.get("events", [])
                ],
            }

        # Determine claimed status from stream.jsonl register records
        claimed_ids: set[str] = set()
        stream_path = run_dir / "stream.jsonl"
        if stream_path.is_file():
            for line in stream_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    rec = json.loads(line)
                    if rec.get("kind") == "register":
                        claimed_ids.add(rec["agent_id"])
                except (json.JSONDecodeError, KeyError):
                    pass

        characters = [
            {
                "id": a["id"],
                "character": a.get("character", {}),
                "claimed": a["id"] in claimed_ids,
            }
            for a in config.get("agents", [])
            if "character" in a
        ]

        # Apply resolved characters from state.json (includes intro edits)
        state_path = run_dir / "state.json"
        if state_path.is_file():
            try:
                state_raw = json.loads(state_path.read_text(encoding="utf-8"))
                if isinstance(state_raw, dict):
                    saved_chars = state_raw.get("characters", {})
                    for entry in characters:
                        if entry["id"] in saved_chars:
                            entry["character"] = saved_chars[entry["id"]]
            except (json.JSONDecodeError, KeyError):
                pass

        return actions, characters

    @router.get("/api/runs/{run_id}/state")
    async def api_run_state(run_id: str) -> dict[str, Any]:
        """Entity state — always reads from disk (single source of truth)."""
        run_dir = _run_dir(run_id)

        # Try state files first (written atomically every tick)
        result = _read_entities(run_dir)
        if result is not None:
            entities, tick = result
        else:
            # Fallback: build initial state from config.yaml
            entities = _entities_from_config(run_dir)
            if not entities:
                raise HTTPException(404, detail="Run state not found")
            tick = 0

        actions, characters = _config_extras(run_dir)

        # If this is the live run, use in-memory characters (includes intro edits)
        engine = app.state.engine
        if engine is not None and app.state.run_id == run_id:
            live_chars = engine.get_characters()
            if live_chars:
                characters = live_chars

        # Filter out system agents from entities
        system_ids = _system_agent_ids(run_dir)
        entities = [e for e in entities if e.get("id") not in system_ids]

        return {
            "run_id": run_id,
            "tick": tick,
            "entities": entities,
            "actions": actions,
            "characters": characters,
            "system_agents": sorted(system_ids),
        }

    @router.get("/api/runs/{run_id}/stream")
    async def api_run_stream(
        run_id: str,
        kind: str = "",
        agent_id: str = "",
        limit: int = 5000,
    ) -> dict[str, Any]:
        """Stream records from stream.jsonl."""
        run_dir = _run_dir(run_id)
        stream_path = run_dir / "stream.jsonl"
        if not stream_path.is_file():
            raise HTTPException(404, detail="Run not found")
        # Compute system agent IDs once before the loop
        system_ids = _system_agent_ids(run_dir)
        events: list[dict[str, Any]] = []
        for line in stream_path.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if kind and obj.get("kind") != kind:
                continue
            if agent_id and obj.get("agent_id") != agent_id:
                continue
            # Hide system agent records (except highlights) from stream
            if obj.get("agent_id") in system_ids and obj.get("kind") != "highlight" and not obj.get("highlight"):
                continue
            events.append(obj)
            if len(events) >= limit:
                break
        return {"run_id": run_id, "events": events}

    @router.get("/api/runs/{run_id}/meta")
    async def api_run_meta(run_id: str) -> dict[str, Any]:
        """Run metadata — scene_id, dm_model, timestamps, counts."""
        run_dir = _run_dir(run_id)
        meta_path = run_dir / "meta.json"
        if not meta_path.is_file():
            raise HTTPException(404, detail="Run not found")
        result: dict[str, Any] = json.loads(meta_path.read_text(encoding="utf-8"))
        return result

    @router.get("/api/runs/{run_id}/summary")
    async def api_run_summary(run_id: str) -> dict[str, Any]:
        """Kind counts + token totals."""
        run_dir = _run_dir(run_id)
        summary_path = run_dir / "summary.json"
        if not summary_path.is_file():
            raise HTTPException(404, detail="Run or summary not found")
        result: dict[str, Any] = json.loads(summary_path.read_text(encoding="utf-8"))
        return result

    @router.get("/api/runs/{run_id}/intro")
    async def api_run_intro(run_id: str) -> dict[str, Any]:
        """Intro page data for any run (live or historical).

        Returns scene metadata, non-agent entities, and agent characters.
        For the live run, uses in-memory engine data; otherwise reads from disk.
        """
        import yaml

        # Check if this is the live run with an active engine
        engine = app.state.engine
        is_live = engine is not None and getattr(app.state, "run_id", "") == run_id

        if is_live:
            from worldseed.server.routes._shared import build_intro_data

            data = build_intro_data(engine)
            return {"run_id": run_id, "is_live": True, **data}

        # Disk path — reconstruct from saved run data
        run_dir = _run_dir(run_id)
        config_path = run_dir / "config.yaml"
        if not config_path.is_file():
            raise HTTPException(404, detail="Run not found")

        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        scene = {"id": raw.get("scene", {}).get("id", ""), "description": raw.get("scene", {}).get("description", "")}

        # Entities from config — copy all top-level fields, then merge template + properties
        entities = []
        templates = raw.get("templates", {})
        for e_dict in raw.get("entities", []):
            entry: dict[str, Any] = dict(e_dict)
            entry.pop("properties", None)
            tmpl = templates.get(e_dict.get("type", ""), {})
            for k, v in tmpl.get("properties", {}).items():
                entry[k] = v
            for k, v in e_dict.get("properties", {}).items():
                entry[k] = v
            entities.append(entry)

        # Agents with characters — prefer state.json (includes intro edits), fallback to config
        system_ids = _system_agent_ids(run_dir, config=raw)
        state_chars: dict[str, Any] = {}
        state_path = run_dir / "state.json"
        if state_path.is_file():
            try:
                state_raw = json.loads(state_path.read_text(encoding="utf-8"))
                if isinstance(state_raw, dict):
                    state_chars = state_raw.get("characters", {})
            except (json.JSONDecodeError, KeyError):
                pass

        agents = []
        for a_dict in raw.get("agents", []):
            aid = a_dict["id"]
            if aid in system_ids:
                continue
            # Merge template + agent properties
            tmpl = templates.get(a_dict.get("type", "agent"), {})
            props: dict[str, Any] = {}
            for k, v in tmpl.get("properties", {}).items():
                props[k] = v
            for k, v in a_dict.get("properties", {}).items():
                props[k] = v
            agents.append(
                {
                    "id": aid,
                    "character": state_chars.get(aid, a_dict.get("character", {})),
                    "properties": props,
                }
            )

        return {"run_id": run_id, "is_live": False, "scene": scene, "entities": entities, "agents": agents}

    @router.get("/api/runs/{run_id}/config")
    async def api_run_config(run_id: str) -> dict[str, Any]:
        """Scene config YAML used for this run."""
        import yaml

        run_dir = _run_dir(run_id)
        config_path = run_dir / "config.yaml"
        if not config_path.is_file():
            raise HTTPException(404, detail="Run or config not found")
        raw = yaml.safe_load(config_path.read_text(encoding="utf-8"))
        return {"run_id": run_id, "config": raw}

    # ── Per-tick snapshots (for replay) ──────────────────

    @router.get("/api/runs/{run_id}/snapshots")
    async def api_run_snapshots_list(run_id: str) -> dict[str, Any]:
        """List available per-tick snapshot numbers."""
        snap_dir = _run_dir(run_id) / "snapshots"
        if not snap_dir.is_dir():
            return {"run_id": run_id, "ticks": []}
        ticks = sorted(int(f.stem) for f in snap_dir.glob("*.json") if f.stem.isdigit())
        return {"run_id": run_id, "ticks": ticks}

    @router.get("/api/runs/{run_id}/snapshots/{tick}")
    async def api_run_snapshot_at_tick(run_id: str, tick: int) -> dict[str, Any]:
        """Entity state at a specific tick."""
        snap_path = _run_dir(run_id) / "snapshots" / f"{tick}.json"
        if not snap_path.is_file():
            raise HTTPException(404, detail=f"Snapshot at tick {tick} not found")
        raw = json.loads(snap_path.read_text(encoding="utf-8"))
        entities = raw.get("entities", raw) if isinstance(raw, dict) else raw
        return {"run_id": run_id, "tick": tick, "entities": entities}

    # ── Backward-compatible aliases for /api/past-runs/{id}/... ──

    @router.get("/api/past-runs/{run_id}/stream")
    async def api_past_run_stream_compat(
        run_id: str,
        kind: str = "",
        agent_id: str = "",
        limit: int = 5000,
    ) -> dict[str, Any]:
        return await api_run_stream(run_id, kind, agent_id, limit)

    @router.get("/api/past-runs/{run_id}/state")
    async def api_past_run_state_compat(run_id: str) -> dict[str, Any]:
        return await api_run_state(run_id)

    @router.get("/api/past-runs/{run_id}/summary")
    async def api_past_run_summary_compat(run_id: str) -> dict[str, Any]:
        return await api_run_summary(run_id)

    @router.get("/api/past-runs/{run_id}/meta")
    async def api_past_run_meta_compat(run_id: str) -> dict[str, Any]:
        return await api_run_meta(run_id)

    @router.get("/api/past-runs/{run_id}/config")
    async def api_past_run_config_compat(run_id: str) -> dict[str, Any]:
        return await api_run_config(run_id)

    # ── Configs + Logs ────────────────────────────────────

    @router.get("/api/configs")
    async def list_configs() -> list[dict[str, str]]:
        """List available scene config files."""
        configs_dir = Path(__file__).parent.parent.parent.parent.parent / "configs"
        if not configs_dir.is_dir():
            return []
        return [{"name": f.name, "path": str(f)} for f in sorted(configs_dir.glob("*.yaml"))]

    @router.get("/api/logs")
    async def api_logs(
        agent_id: str = "",
        run_id: str = "",
        limit: int = 0,
    ) -> dict[str, Any]:
        if not agent_id:
            raise HTTPException(400, detail="agent_id required")
        messages = read_session_logs(
            agent_id,
            run_id=run_id or None,
            limit=limit,
            openclaw_dir=_oc_dir(),
        )
        return {"agent_id": agent_id, "run_id": run_id, "messages": messages}

    @router.get("/api/logs/live")
    async def api_logs_live(
        agent_id: str = "",
        run_id: str = "",
    ) -> StreamingResponse:
        """SSE endpoint — tail an agent's OpenClaw session JSONL.

        Phase 1: send all existing lines (catch-up).
        Phase 2: stat() the file every ~1s, push new lines as they appear.
        """
        if not agent_id or not run_id:
            raise HTTPException(400, detail="agent_id and run_id required")

        session_file = resolve_session_file(agent_id, run_id, openclaw_dir=_oc_dir())

        async def event_stream():  # type: ignore[no-untyped-def]
            offset = 0

            # If file doesn't exist yet, wait for it (agent may not have started)
            fpath = session_file
            if fpath is None:
                for _ in range(60):  # wait up to 60s
                    await asyncio.sleep(1)
                    fpath = resolve_session_file(agent_id, run_id, openclaw_dir=_oc_dir())
                    if fpath is not None:
                        break
                if fpath is None:
                    return

            # Phase 1: catch-up — send all existing content
            try:
                content = fpath.read_text(encoding="utf-8", errors="replace")
                for line in content.splitlines():
                    line = line.strip()
                    if line:
                        yield f"data: {line}\n\n"
                offset = fpath.stat().st_size
            except OSError:
                pass

            # Phase 2: tail — check for new bytes every ~1s
            try:
                while True:
                    await asyncio.sleep(1)
                    try:
                        size = os.path.getsize(fpath)
                    except OSError:
                        continue
                    if size <= offset:
                        continue
                    try:
                        with open(fpath, encoding="utf-8", errors="replace") as f:
                            f.seek(offset)
                            new_data = f.read()
                            offset = f.tell()
                        for line in new_data.splitlines():
                            line = line.strip()
                            if line:
                                yield f"data: {line}\n\n"
                    except OSError:
                        continue
            except asyncio.CancelledError:
                pass

        return StreamingResponse(
            event_stream(),  # type: ignore[no-untyped-call]
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
        )

    @router.get("/api/agent-texts")
    async def api_agent_texts(run_id: str = "") -> dict[str, Any]:
        """All agents' text responses for a run (from OpenClaw session logs)."""
        if not run_id:
            raise HTTPException(400, detail="run_id required")
        texts = read_agent_texts(run_id, openclaw_dir=_oc_dir())
        return {"run_id": run_id, "texts": texts}

    return router
