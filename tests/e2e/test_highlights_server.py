"""Server-level e2e test for highlights.

Verifies that highlight records appear in the /api/runs/{run_id}/stream
endpoint, exercising the full pipeline: engine → recorder → API.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

from worldseed.models.config_schema import SceneConfig
from worldseed.persistence import RunRecorder
from worldseed.server.app import create_app
from worldseed.world import WorldEngine


def _build_config() -> dict:
    return {
        "scene": {
            "id": "highlight_e2e",
            "description": "Highlight server test",
        },
        "entities": [
            {
                "id": "food",
                "type": "resource",
                "properties": {"quantity": 5},
            },
        ],
        "templates": {
            "person": {"properties": {"alive": True}},
        },
        "agents": [
            {"id": "alice", "template": "person", "character": {}},
            {"id": "bob", "template": "person", "character": {}},
            {
                "id": "narrator",
                "template": "person",
                "omniscient": True,
                "character": {},
            },
        ],
        "actions": {
            "eat": {
                "description": "Eat food",
                "params": [
                    {"name": "amount", "type": "number"},
                ],
                "preconditions": [
                    {
                        "operator": "check",
                        "left": "food.quantity",
                        "op": ">=",
                        "right": "$amount",
                    },
                ],
                "effects": [
                    {
                        "operator": "decrement",
                        "target": "food.quantity",
                        "by": "$amount",
                        "min": 0,
                    },
                ],
                "events": [
                    {
                        "type": "ate",
                        "detail": "$agent ate $amount food",
                        "ttl": 3,
                        "scope": "global",
                    },
                ],
            },
            "build": {
                "description": "Build a structure",
                "params": [],
                "preconditions": [],
                "effects": [
                    {
                        "operator": "create_entity",
                        "id": "wall",
                        "type": "structure",
                        "properties": {"hp": 10},
                    },
                ],
                "events": [
                    {
                        "type": "built",
                        "detail": "$agent built a wall",
                        "ttl": 3,
                        "scope": "global",
                    },
                ],
            },
        },
        "highlights": {
            "food_crisis": {
                "trigger": [
                    {
                        "operator": "check",
                        "left": "food.quantity",
                        "op": "<=",
                        "right": 2,
                    },
                ],
                "label": "Food supply critically low!",
            },
        },
        "perception": {
            "visibility": [],
            "hidden_properties": [],
            "event_scopes": {},
        },
    }


@pytest_asyncio.fixture
async def highlight_env(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> Any:
    """Server env with highlight-enabled config."""
    monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))

    run_id = "highlight_e2e"
    config = SceneConfig.model_validate(_build_config())

    recorder = RunRecorder(
        run_id=run_id,
        config_path=None,
        scene_id="highlight_e2e",
        dm_model="none",
    )
    engine = WorldEngine(config=config, recorder=recorder)
    engine.register_from_config()

    app = create_app(
        engine,
        tick_interval=0,
        run_id=run_id,
    )

    transport = ASGITransport(app=app)
    async with AsyncClient(
        transport=transport,
        base_url="http://test",
    ) as client:
        yield {
            "client": client,
            "engine": engine,
            "recorder": recorder,
            "run_id": run_id,
        }

    recorder.save_final_state(
        [e.to_dict() for e in engine.state.all_entities()],
    )
    recorder.finalize(
        tick_count=engine.tick,
        agent_count=len(engine.get_registered_agents()),
    )


@pytest.mark.asyncio
async def test_highlights_in_stream_api(
    highlight_env: dict[str, Any],
) -> None:
    """All 3 highlight layers appear in /api/runs/{run_id}/stream."""
    client = highlight_env["client"]
    engine = highlight_env["engine"]
    run_id = highlight_env["run_id"]

    # Layer 2: action rejected
    engine.submit("bob", "eat", {"amount": 999})

    # Layer 2: entity created
    engine.submit("alice", "build", {})

    # Layer 1 + Layer 2: eat food down, triggers config highlight
    engine.submit("alice", "eat", {"amount": 4})  # food = 1
    engine.step()

    # Query stream API for highlights
    r = await client.get(
        f"/api/runs/{run_id}/stream",
        params={"kind": "highlight"},
    )
    assert r.status_code == 200

    events = r.json()["events"]
    sources = {e.get("source") for e in events}

    # Layer 1: config trigger
    assert "config" in sources

    # Layer 2: engine events
    assert "action_rejected" in sources
    assert "entity_created" in sources

    # All have labels
    for e in events:
        assert "label" in e
        assert e["label"]


@pytest.mark.asyncio
async def test_highlights_mixed_with_other_stream_kinds(
    highlight_env: dict[str, Any],
) -> None:
    """Highlights coexist with action/register records in stream."""
    client = highlight_env["client"]
    engine = highlight_env["engine"]
    run_id = highlight_env["run_id"]

    engine.submit("alice", "eat", {"amount": 4})
    engine.step()

    # Get all stream records
    r = await client.get(f"/api/runs/{run_id}/stream")
    assert r.status_code == 200

    events = r.json()["events"]
    kinds = {e["kind"] for e in events}

    assert "register" in kinds
    assert "action" in kinds
    assert "highlight" in kinds


@pytest.mark.asyncio
async def test_admin_scoped_highlights_invisible_to_narrator(
    highlight_env: dict[str, Any],
) -> None:
    """Admin-scoped highlight events are NOT visible to any agent, including narrator.

    Highlights (action_rejected, highlight) use scope='admin' which is
    dashboard-only. Even omniscient agents should not perceive them.
    They appear in the stream (dashboard view) but not in agent inboxes.
    """
    client = highlight_env["client"]
    engine = highlight_env["engine"]

    engine.submit("bob", "eat", {"amount": 999})  # rejected
    engine.submit("alice", "eat", {"amount": 4})  # food crisis
    engine.step()

    # Get narrator's inbox via API
    r = await client.get(
        "/api/inbox",
        params={"agent_id": "narrator"},
    )
    assert r.status_code == 200

    data = r.json()
    event_types = {e["type"] for e in data.get("events", [])}

    # Admin-scoped events should NOT appear in any agent's inbox
    assert "action_rejected" not in event_types
    assert "highlight" not in event_types

    # But the narrator should still see normal global events (e.g. "ate")
    assert "ate" in event_types
