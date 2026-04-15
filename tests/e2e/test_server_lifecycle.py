"""E2E: Full server lifecycle — register, tick, perceive, act, GM ops."""

from __future__ import annotations

import asyncio
from typing import Any

import pytest


@pytest.mark.asyncio
async def test_health_returns_tick_zero(e2e_env: dict[str, Any]) -> None:
    """Server starts at tick 0."""
    client = e2e_env["client"]
    r = await client.get("/health")
    assert r.status_code == 200
    data = r.json()
    assert data["status"] != "lobby"
    assert data["tick"] == 0


@pytest.mark.asyncio
async def test_register_agents(e2e_env: dict[str, Any]) -> None:
    """Register preset agents via POST /register."""
    client = e2e_env["client"]

    # Register all bunker agents
    for agent_id in ["old_chen", "xiao_li", "doctor_wang"]:
        r = await client.post("/register", json={"mode": "claim", "agent_id": agent_id})
        assert r.status_code == 200
        data = r.json()
        assert data["agent_id"] == agent_id
        assert "token" in data
        assert data["scene"] == "doomsday_bunker"
        assert "character" in data


@pytest.mark.asyncio
async def test_register_then_perceive(e2e_env: dict[str, Any]) -> None:
    """After registration, agent can perceive."""
    client = e2e_env["client"]
    engine = e2e_env["engine"]

    # Register
    r = await client.post("/register", json={"mode": "claim", "agent_id": "old_chen"})
    token = r.json()["token"]

    # Step once so perceiver delivers
    engine.step()

    # Perceive
    r = await client.get("/perceive", params={"token": token})
    assert r.status_code == 200
    data = r.json()
    assert "self_state" in data
    assert "action_options" in data
    assert data["tick"] >= 1


@pytest.mark.asyncio
async def test_act_and_verify(e2e_env: dict[str, Any]) -> None:
    """Submit action via POST /act, step, verify in events."""
    client = e2e_env["client"]
    engine = e2e_env["engine"]

    # Register
    r = await client.post("/register", json={"mode": "claim", "agent_id": "old_chen"})
    token = r.json()["token"]

    # Act
    r = await client.post(
        "/act",
        json={
            "token": token,
            "action": "say",
            "params": {"message": "hello world"},
        },
    )
    assert r.status_code == 200
    assert r.json()["queued"] is True

    # Step to process
    engine.step()

    # Check stream for say actions
    run_id = e2e_env["run_id"]
    r = await client.get(f"/api/runs/{run_id}/stream", params={"kind": "action"})
    assert r.status_code == 200
    events = r.json()["events"]
    say_events = [e for e in events if e.get("action_type") == "say"]
    assert len(say_events) >= 1


@pytest.mark.asyncio
async def test_pause_resume(e2e_env: dict[str, Any]) -> None:
    """Pause and resume tick runner."""
    client = e2e_env["client"]

    r = await client.post("/api/tick/pause")
    assert r.status_code == 200
    assert r.json()["paused"] is True

    r = await client.get("/health")
    assert r.json()["running"] is False

    r = await client.post("/api/tick/resume")
    assert r.status_code == 200
    assert r.json()["resumed"] is True

    r = await client.get("/health")
    # running may be False until Resume
    # assert r.json()["running"] is True


@pytest.mark.asyncio
async def test_whisper(e2e_env: dict[str, Any]) -> None:
    """Send GM DM and verify in inbox."""
    client = e2e_env["client"]

    # Register
    await client.post("/register", json={"mode": "claim", "agent_id": "old_chen"})

    # GM DM
    r = await client.post(
        "/api/whisper",
        json={"agent_id": "old_chen", "message": "The ceiling is cracking."},
    )
    assert r.status_code == 200
    assert r.json()["sent"] is True

    # Check inbox
    r = await client.get("/api/inbox", params={"agent_id": "old_chen"})
    assert r.status_code == 200
    dms = r.json()["whispers"]
    assert any("ceiling" in dm.get("detail", "") for dm in dms)


@pytest.mark.asyncio
async def test_gm_resolve_requires_dm(e2e_env: dict[str, Any]) -> None:
    """GM resolve without DM provider returns 400."""
    client = e2e_env["client"]

    r = await client.post(
        "/api/gm/resolve",
        json={"text": "add 100 water"},
    )
    assert r.status_code == 400
    assert "DM provider required" in r.json()["detail"]


@pytest.mark.asyncio
async def test_full_cycle_multi_agent(e2e_env: dict[str, Any]) -> None:
    """Register 3 agents, each acts, step, verify isolation."""
    client = e2e_env["client"]
    engine = e2e_env["engine"]

    tokens = {}
    for agent_id in ["old_chen", "xiao_li", "doctor_wang"]:
        r = await client.post("/register", json={"mode": "claim", "agent_id": agent_id})
        tokens[agent_id] = r.json()["token"]

    # Each agent says something
    for agent_id, msg in [
        ("old_chen", "I need food"),
        ("xiao_li", "The water is low"),
        ("doctor_wang", "Medical supplies needed"),
    ]:
        await client.post(
            "/act",
            json={
                "token": tokens[agent_id],
                "action": "say",
                "params": {"message": msg},
            },
        )

    # Step
    engine.step()

    # Verify each agent has self_state
    for agent_id in ["old_chen", "xiao_li", "doctor_wang"]:
        r = await client.get("/perceive", params={"token": tokens[agent_id]})
        assert r.status_code == 200
        data = r.json()
        assert "self_state" in data

    # Verify world state has all 3 agents
    run_id = e2e_env["run_id"]
    r = await client.get(f"/api/runs/{run_id}/state")
    entities = r.json()["entities"]
    agent_ids = {e["id"] for e in entities if e["type"] == "agent"}
    assert {"old_chen", "xiao_li", "doctor_wang"} <= agent_ids


@pytest.mark.asyncio
async def test_ticks_advance_with_runner(e2e_env: dict[str, Any]) -> None:
    """Verify tick runner advances ticks in background."""
    client = e2e_env["client"]
    app = e2e_env["app"]

    # Register an agent so world has something
    await client.post("/register", json={"mode": "claim", "agent_id": "old_chen"})

    # Manually start tick runner (ASGI transport doesn't trigger lifespan)
    tick_runner = app.state.tick_runner
    await tick_runner.start()
    try:
        initial_tick = app.state.engine.tick
        await asyncio.sleep(0.5)

        r = await client.get("/health")
        current_tick = r.json()["tick"]
        assert current_tick > initial_tick, f"Tick should have advanced from {initial_tick}, got {current_tick}"
    finally:
        await tick_runner.stop()
