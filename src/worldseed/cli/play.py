"""CLI subcommand: worldseed play — one-click dev/test."""

from __future__ import annotations

import argparse
import secrets
import signal
import sys
import threading
import time
from pathlib import Path

import httpx
import structlog
import uvicorn

from worldseed.world import WorldEngine

log = structlog.get_logger()


def _clean_stale_worldseed_sessions(current_run_id: str) -> None:
    """Remove old WorldSeed session entries from OpenClaw's session store.

    Session keys look like ``agent:{id}:worldseed:{run_id}``.
    We keep entries whose run_id matches *current_run_id* (or that
    aren't WorldSeed sessions at all) and drop everything else.
    """
    import json
    import re

    # Scan all agent session stores (main + per-agent slug dirs like ws-*).
    agents_dir = Path.home() / ".openclaw" / "agents"
    if not agents_dir.is_dir():
        return

    ws_pattern = re.compile(r"^agent:.+:worldseed:(.+)$")
    total_removed = 0

    for agent_dir in agents_dir.iterdir():
        store_path = agent_dir / "sessions" / "sessions.json"
        if not store_path.is_file():
            continue
        try:
            store: dict[str, object] = json.loads(store_path.read_text("utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        to_delete = [key for key in store if (m := ws_pattern.match(key)) and m.group(1) != current_run_id]
        if not to_delete:
            continue

        for key in to_delete:
            del store[key]

        try:
            store_path.write_text(json.dumps(store, indent=2), "utf-8")
            total_removed += len(to_delete)
        except OSError:
            pass

    if total_removed:
        log.info("cleaned_stale_worldseed_sessions", removed=total_removed)


def play(args: argparse.Namespace) -> None:
    """One-click dev/test: server + register + budget."""
    from worldseed.connector.websocket import WebSocketConnector
    from worldseed.dm.providers.llm import LiteLLMDMProvider
    from worldseed.persistence import RunRecorder
    from worldseed.scene.config import load_config as _load_config
    from worldseed.server.app import create_app

    config_path = Path(args.config)
    if not config_path.exists():
        log.error("config_not_found", path=str(config_path))
        sys.exit(1)

    dm = LiteLLMDMProvider(
        model=args.dm_model,
        fallback_model=args.dm_fallback,
    )

    # Create run recorder
    run_id = secrets.token_hex(4)
    scene_cfg = _load_config(config_path)
    recorder = RunRecorder(
        run_id=run_id,
        config_path=config_path,
        scene_id=scene_cfg.scene.id,
        dm_model=args.dm_model or "",
        resolved_config=scene_cfg.model_dump(),
    )

    # Language: CLI flag overrides auto-detection
    from worldseed.gazette.context import detect_language

    desc = scene_cfg.scene.description
    detected = detect_language({"scene": {"description": desc}})
    # Only force language instruction for non-English scenes (e.g. zh).
    # English is the default — no need to add "MUST respond in English" to SOUL.
    language = args.language or (detected if detected != "en" else "")

    engine = WorldEngine(
        config_path,
        dm_provider=dm,
        recorder=recorder,
        language=language,
    )
    engine.prepopulate_agents()

    app = create_app(
        engine=engine,
        tick_interval=engine.config.scene.tick_interval,
        run_id=run_id,
        port=args.port,
        auto_start_tick=False,  # tick starts via dashboard or auto after agents connect
    )

    # Wire WebSocket connector
    ws_conn = WebSocketConnector(app.state.ws_manager)
    app.state.tick_runner.connector = ws_conn

    # Budget tracking
    max_dm = args.max_dm_calls
    max_ticks = args.max_ticks
    timeout_min = args.timeout
    start_time = time.monotonic()

    port = args.port
    base_url = f"http://127.0.0.1:{port}"

    # Start uvicorn in a thread
    uvi_config = uvicorn.Config(
        app,
        host="127.0.0.1",
        port=port,
        log_level="warning",
    )
    server = uvicorn.Server(uvi_config)

    server_thread = threading.Thread(
        target=server.run,
        daemon=True,
    )
    server_thread.start()

    # Wait for server to be ready
    for _ in range(30):
        try:
            r = httpx.get(f"{base_url}/health", timeout=1)
            if r.status_code == 200:
                break
        except Exception:
            pass
        time.sleep(0.5)
    else:
        log.error("server_start_timeout")
        sys.exit(1)

    agent_count = len(engine.config.agents)

    log.info(
        "play_started",
        scene=engine.config.scene.id,
        agents=agent_count,
        dm_model=args.dm_model,
        max_ticks=max_ticks,
        max_dm_calls=max_dm,
        timeout_min=timeout_min,
        dashboard=f"http://127.0.0.1:{port}",
    )

    # Clean stale WorldSeed sessions from OpenClaw's session store.
    # Each run creates new session entries (agent:{id}:worldseed:{run_id}).
    # Without cleanup, the store grows unboundedly across runs, causing the
    # gateway to load tens of MB into memory on every agent wake.
    # Must happen BEFORE gateway starts — no concurrent readers.
    _clean_stale_worldseed_sessions(run_id)

    # Auto-start: spawn gateway (via server), send initial wakes, start ticks.
    # Gateway lifecycle is managed entirely by the server (_spawn_gateway),
    # except shutdown cleanup (play.py calls _kill_gateway on exit).
    # play.py only orchestrates the startup sequence via HTTP API.
    def _auto_connect_agents() -> None:
        """Start gateway + ticks, send initial wakes, wait for agents."""
        # Step 1: tick/resume spawns gateway if needed, starts tick loop
        try:
            httpx.post(f"{base_url}/api/tick/resume", timeout=5)
            log.info("tick_resume_ok")
        except Exception:
            log.warning("tick_resume_failed")
            return

        # Step 2: wait for agents to register via plugin (worldseed_register).
        # Ticks auto-start once all preset agents register (maybe_auto_start_ticks).
        expected = len(engine.config.agents)
        for _ in range(120):
            try:
                r = httpx.get(f"{base_url}/health", timeout=2)
                ready = len(r.json().get("agents", {}).get("ready", []))
                if ready >= expected:
                    log.info("all_agents_ready", ready=ready)
                    break
            except Exception:
                pass
            time.sleep(0.5)
        else:
            log.warning("agents_ready_timeout")

    connect_thread = threading.Thread(target=_auto_connect_agents, daemon=True)
    connect_thread.start()

    config_max_ticks = engine.config.scene.max_ticks
    effective_max_ticks = (
        min(t for t in (max_ticks, config_max_ticks) if t is not None) if max_ticks or config_max_ticks else None
    )

    print(f"\n  WorldSeed play: {engine.config.scene.id}")
    print(f"  Run: {run_id} (saved to ~/.worldseed/runs/{run_id})")
    print(f"  Dashboard: http://127.0.0.1:{port}")
    print(f"  Agents: {agent_count}")
    print(f"  DM: {args.dm_model}")
    print(f"  Max ticks: {effective_max_ticks or 'unlimited'}")
    if effective_max_ticks and not max_ticks:
        print(
            f"  ⚠ Will auto-stop after {effective_max_ticks} ticks (default)."
            " Set scene.max_ticks in config or --max-ticks to change."
        )
    if max_dm:
        print(f"  Max DM calls: {max_dm}")
    if timeout_min:
        print(f"  Timeout: {timeout_min}m")
    print("  Press Ctrl+C to stop.\n")

    # Monitor loop — check budget limits
    shutdown = threading.Event()

    def handle_signal(sig: int, frame: object) -> None:
        shutdown.set()

    signal.signal(signal.SIGINT, handle_signal)
    signal.signal(signal.SIGTERM, handle_signal)

    paused = False
    try:
        while not shutdown.is_set():
            shutdown.wait(timeout=5.0)

            if paused:
                continue

            tick = engine.tick
            reason = None
            if max_ticks and tick >= max_ticks:
                reason = f"max_ticks_reached ({tick})"
            elif max_dm and dm.call_count >= max_dm:
                reason = f"max_dm_calls_reached ({dm.call_count})"
            elif timeout_min:
                elapsed = (time.monotonic() - start_time) / 60
                if elapsed >= timeout_min:
                    reason = f"timeout_reached ({round(elapsed, 1)}m)"

            if reason:
                # Pause tick runner — server stays up for dashboard
                log.info("budget_reached_pausing", reason=reason)
                httpx.post(f"{base_url}/api/tick/pause", timeout=2)
                paused = True
                print(f"\n  Paused: {reason}")
                print(f"  Dashboard still live at http://127.0.0.1:{port}")
                print("  Press Ctrl+C to shut down.\n")
    finally:
        print("\n  Shutting down...")
        entities = [e.to_full_dict() for e in engine.state.all_entities()]
        recorder.save_final_state(entities)
        recorder.finalize(
            tick_count=engine.tick,
            agent_count=len(engine.get_registered_agents()),
        )
        server.should_exit = True
        # Kill gateway — server owns the process via app.state.gateway_proc
        from worldseed.server.routes._shared import _kill_gateway

        _kill_gateway(app)
        server_thread.join(timeout=5)
        print("  Done.")
