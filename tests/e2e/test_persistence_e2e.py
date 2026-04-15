"""E2E: Verify persistence — stream.jsonl, state_final.json, summary, API."""

from __future__ import annotations

import json
from typing import Any

import pytest


@pytest.mark.asyncio
async def test_stream_has_register_events(e2e_env: dict[str, Any]) -> None:
    """After registering agents, stream.jsonl should contain register events."""
    client = e2e_env["client"]
    recorder = e2e_env["recorder"]

    # Register agents
    for agent_id in ["old_chen", "xiao_li", "doctor_wang"]:
        await client.post("/register", json={"mode": "claim", "agent_id": agent_id})

    # Read stream directly
    stream_path = recorder.run_dir / "stream.jsonl"
    lines = stream_path.read_text().strip().splitlines()
    events = [json.loads(line) for line in lines]

    register_events = [e for e in events if e["kind"] == "register"]
    claimed = [e for e in register_events if e["agent_id"] in {"old_chen", "xiao_li", "doctor_wang"}]
    assert len(claimed) == 3
    assert {e["agent_id"] for e in claimed} == {"old_chen", "xiao_li", "doctor_wang"}


@pytest.mark.asyncio
async def test_stream_has_action_and_event_records(
    e2e_env: dict[str, Any],
) -> None:
    """After act + step, stream has register + action records."""
    client = e2e_env["client"]
    engine = e2e_env["engine"]
    recorder = e2e_env["recorder"]

    r = await client.post("/register", json={"mode": "claim", "agent_id": "old_chen"})
    token = r.json()["token"]

    await client.post(
        "/act",
        json={
            "token": token,
            "action": "say",
            "params": {"message": "test persist"},
        },
    )
    engine.step()

    # Read stream
    stream_path = recorder.run_dir / "stream.jsonl"
    events = [json.loads(line) for line in stream_path.read_text().strip().splitlines()]

    kinds = {e["kind"] for e in events}
    assert "register" in kinds
    assert "action" in kinds

    # Verify action record
    action_records = [e for e in events if e["kind"] == "action"]
    assert any(a["agent_id"] == "old_chen" and a["action_type"] == "say" for a in action_records)


@pytest.mark.asyncio
async def test_stream_has_whisper_record(e2e_env: dict[str, Any]) -> None:
    """GM DM should appear in stream.jsonl."""
    client = e2e_env["client"]
    recorder = e2e_env["recorder"]

    await client.post("/register", json={"mode": "claim", "agent_id": "old_chen"})
    await client.post(
        "/api/whisper",
        json={"agent_id": "old_chen", "message": "Test GM DM"},
    )

    events = [json.loads(line) for line in recorder.run_dir.joinpath("stream.jsonl").read_text().strip().splitlines()]

    whisper_events = [e for e in events if e["kind"] == "whisper"]
    assert len(whisper_events) == 1
    assert whisper_events[0]["agent_id"] == "old_chen"
    assert whisper_events[0]["message"] == "Test GM DM"


@pytest.mark.asyncio
async def test_finalize_produces_all_files(e2e_env: dict[str, Any]) -> None:
    """After full lifecycle + finalize, all persistence files exist."""
    client = e2e_env["client"]
    engine = e2e_env["engine"]
    recorder = e2e_env["recorder"]

    # Register + act + step
    r = await client.post("/register", json={"mode": "claim", "agent_id": "old_chen"})
    token = r.json()["token"]
    await client.post(
        "/act",
        json={"token": token, "action": "say", "params": {"message": "hi"}},
    )
    engine.step()

    # Finalize (normally done by fixture teardown, do it explicitly here)
    recorder.save_final_state([e.to_dict() for e in engine.state.all_entities()])
    recorder.finalize(
        tick_count=engine.tick,
        agent_count=len(engine.get_registered_agents()),
    )

    run_dir = recorder.run_dir

    # meta.json
    meta = json.loads((run_dir / "meta.json").read_text())
    assert meta["tick_count"] >= 1
    assert meta["agent_count"] >= 1
    assert meta["end_time"] is not None

    # config.yaml
    assert (run_dir / "config.yaml").is_file()

    # stream.jsonl
    assert (run_dir / "stream.jsonl").is_file()
    stream_lines = (run_dir / "stream.jsonl").read_text().strip().splitlines()
    assert len(stream_lines) > 0

    # state_final.json
    state = json.loads((run_dir / "state_final.json").read_text())
    assert len(state) > 0
    entity_ids = {e["id"] for e in state}
    assert "old_chen" in entity_ids

    # summary.json
    summary = json.loads((run_dir / "summary.json").read_text())
    assert "counts" in summary
    assert summary["counts"].get("register", 0) >= 1
    assert summary["counts"].get("action", 0) >= 1


@pytest.mark.asyncio
async def test_past_runs_api(e2e_env: dict[str, Any]) -> None:
    """Past-runs API should list the current run."""
    client = e2e_env["client"]
    engine = e2e_env["engine"]
    recorder = e2e_env["recorder"]

    # Register + step to generate some data
    await client.post("/register", json={"mode": "claim", "agent_id": "old_chen"})
    engine.step()

    # Finalize to write summary
    recorder.save_final_state([e.to_dict() for e in engine.state.all_entities()])
    recorder.finalize(engine.tick, len(engine.get_registered_agents()))

    # List runs
    r = await client.get("/api/past-runs")
    assert r.status_code == 200
    runs = r.json()
    assert any(run["run_id"] == "e2e_test" for run in runs)

    # Stream API
    r = await client.get("/api/past-runs/e2e_test/stream")
    assert r.status_code == 200
    data = r.json()
    assert data["run_id"] == "e2e_test"
    assert len(data["events"]) > 0

    # Filter by kind
    r = await client.get("/api/past-runs/e2e_test/stream", params={"kind": "register"})
    events = r.json()["events"]
    assert all(e["kind"] == "register" for e in events)

    # Summary API
    r = await client.get("/api/past-runs/e2e_test/summary")
    assert r.status_code == 200
    summary = r.json()
    assert "counts" in summary
