"""Integration test: poker game flow → verify JSONL stream has correct data."""

import asyncio
import json
from pathlib import Path

import pytest

from worldseed.agent_registry import AgentRegistry
from worldseed.dm.providers.mock import MockDMProvider
from worldseed.engine.action_queue import ActionQueue
from worldseed.engine.event_log import EventLog
from worldseed.engine.state_store import StateStore
from worldseed.engine.tick import TickEngine
from worldseed.models.action import ActionSubmission
from worldseed.models.config_schema import EffectConfig
from worldseed.models.entity import Entity
from worldseed.persistence import RunRecorder
from worldseed.protocol.dm import DMResponse
from worldseed.scene.config import load_config


@pytest.fixture()
def poker_env(tmp_path):
    config = load_config(Path("configs/poker_test.yaml"))
    store = StateStore()
    for e in config.entities:
        store.add(Entity(id=e.id, type=e.type, _data=dict(e.properties)))
    AgentRegistry(config, store).register_from_config()
    event_log = EventLog()
    queue = ActionQueue()

    # Mock DM for showdown — DM only sets winner, engine transfers pot
    dm_response = DMResponse(
        narrative="Shark wins with Ace high.",
        effects=[
            EffectConfig(operator="set", target="table.winner", value="shark"),
            EffectConfig(
                operator="emit_event",
                type="showdown_result",
                detail="Shark wins!",
                ttl=5,
                scope="global",
            ),
        ],
    )
    mock_dm = MockDMProvider(responses={"consequence:showdown": dm_response})

    recorder = RunRecorder(
        run_id="test_poker",
        scene_id="poker_test",
        dm_model="mock",
        config_path=Path("configs/poker_test.yaml"),
    )

    engine = TickEngine(
        config=config,
        store=store,
        event_log=event_log,
        action_queue=queue,
        dm_provider=mock_dm,
        recorder=recorder,
    )
    return {
        "engine": engine,
        "store": store,
        "queue": queue,
        "event_log": event_log,
        "recorder": recorder,
        "mock_dm": mock_dm,
    }


class TestPokerJSONL:
    def test_full_round_jsonl(self, poker_env):
        env = poker_env
        engine = env["engine"]
        store = env["store"]
        queue = env["queue"]
        recorder = env["recorder"]

        def _step() -> None:
            asyncio.run(engine.step_async())

        # T1: dealer deals
        queue.submit(ActionSubmission(agent_id="dealer", action_type="deal_hands", params={}))
        _step()

        # T2: hustler raises
        queue.submit(ActionSubmission(agent_id="hustler", action_type="raise_bet", params={"amount": 50}))
        _step()

        # T3: analyst folds
        queue.submit(ActionSubmission(agent_id="analyst", action_type="fold", params={}))
        _step()

        # T4: shark calls
        queue.submit(ActionSubmission(agent_id="shark", action_type="call", params={}))
        _step()

        # T5: rookie folds
        queue.submit(ActionSubmission(agent_id="rookie", action_type="fold", params={}))
        _step()

        # T6: dealer deals flop
        queue.submit(ActionSubmission(agent_id="dealer", action_type="deal_flop", params={}))
        _step()

        # T7-8: both check
        queue.submit(ActionSubmission(agent_id="shark", action_type="check", params={}))
        _step()
        queue.submit(ActionSubmission(agent_id="hustler", action_type="check", params={}))
        _step()

        # T9: dealer deals turn
        queue.submit(ActionSubmission(agent_id="dealer", action_type="deal_turn", params={}))
        _step()

        # T10-11: both check
        queue.submit(ActionSubmission(agent_id="shark", action_type="check", params={}))
        _step()
        queue.submit(ActionSubmission(agent_id="hustler", action_type="check", params={}))
        _step()

        # T12: dealer deals river
        queue.submit(ActionSubmission(agent_id="dealer", action_type="deal_river", params={}))
        _step()

        # T13-14: both check
        queue.submit(ActionSubmission(agent_id="shark", action_type="check", params={}))
        _step()
        queue.submit(ActionSubmission(agent_id="hustler", action_type="check", params={}))
        _step()

        # T15: dealer starts showdown → DM sets winner
        queue.submit(ActionSubmission(agent_id="dealer", action_type="start_showdown", params={}))
        _step()

        # T16: transfer_showdown_pot consequence fires (reads winner from state)
        _step()

        # Read JSONL stream
        stream_path = recorder.run_dir / "stream.jsonl"
        assert stream_path.exists(), "stream.jsonl should exist"

        lines = stream_path.read_text().strip().splitlines()
        events = [json.loads(line) for line in lines]

        # Verify stream content
        kinds = [e["kind"] for e in events]
        assert "action" in kinds, "Should have action events"

        # Check all actions recorded
        actions = [e for e in events if e["kind"] == "action"]
        action_types = [a["action_type"] for a in actions]
        assert "deal_hands" in action_types
        assert "raise_bet" in action_types
        assert "fold" in action_types
        assert "call" in action_types
        assert "check" in action_types
        assert "deal_flop" in action_types
        assert "deal_turn" in action_types
        assert "deal_river" in action_types
        assert "start_showdown" in action_types

        # All actions should be successful
        failed = [a for a in actions if not a.get("success")]
        assert len(failed) == 0, f"Failed actions: {failed}"

        # Check DM call recorded
        dm_calls = [e for e in events if e["kind"] == "dm_call"]
        assert len(dm_calls) >= 1, "Should have at least 1 DM call (showdown)"

        # Check consequences recorded
        consequences = [e for e in events if e["kind"] == "consequence"]
        # At minimum: skip_folded, wrap_turn, notify_next_player should have fired
        assert len(consequences) > 0, "Should have consequence events"

        # Verify game ended correctly
        assert store.get("table")["phase"] == "round_over"
        assert store.get("table")["pot"] == 0

        print(
            f"\nJSONL: {len(events)} events, {len(actions)} actions, "
            f"{len(dm_calls)} DM calls, {len(consequences)} consequences"
        )
        for e in events:
            k = e.get("kind", "?")
            t = e.get("tick", "?")
            if k == "action":
                print(f"  [{t:>2}] action: {e['agent_id']} → {e['action_type']} {'✓' if e.get('success') else '✗'}")
            elif k == "consequence":
                print(f"  [{t:>2}] consequence: {e['name']}")
            elif k == "dm_call":
                print(f"  [{t:>2}] dm_call: {e.get('action', '')}")
