"""Tests for the RunRecorder persistence module (event-sourcing stream)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from tests.helpers import CONFIGS_DIR, read_snapshot
from worldseed.persistence import NullRecorder, RunRecorder, list_runs


@pytest.fixture
def recorder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> RunRecorder:
    """Create a RunRecorder that writes to a temp directory."""
    monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))

    config_path = tmp_path / "test_config.yaml"
    config_path.write_text("scene:\n  id: test_scene\n")

    return RunRecorder(
        run_id="abc12345",
        config_path=config_path,
        scene_id="test_scene",
        dm_model="test/model",
    )


def _read_stream(recorder: RunRecorder) -> list[dict]:
    """Read all events from stream.jsonl."""
    path = recorder.run_dir / "stream.jsonl"
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


class TestRunRecorder:
    def test_creates_run_directory(self, recorder: RunRecorder) -> None:
        assert recorder.run_dir.is_dir()

    def test_meta_json_written(self, recorder: RunRecorder) -> None:
        meta_path = recorder.run_dir / "meta.json"
        assert meta_path.is_file()
        meta = json.loads(meta_path.read_text())
        assert meta["run_id"] == "abc12345"
        assert meta["scene_id"] == "test_scene"
        assert meta["dm_model"] == "test/model"
        assert meta["end_time"] is None
        assert meta["tick_count"] == 0

    def test_config_copied(self, recorder: RunRecorder) -> None:
        config_copy = recorder.run_dir / "config.yaml"
        assert config_copy.is_file()
        assert "test_scene" in config_copy.read_text()

    def test_record_event(self, recorder: RunRecorder) -> None:
        recorder.record("event", 1, type="test", source="agent_a", detail="did stuff")
        recorder.record("event", 2, type="test2", source="agent_b", detail="more stuff")
        events = _read_stream(recorder)
        assert len(events) == 2
        assert events[0]["kind"] == "event"
        assert events[0]["tick"] == 1
        assert events[0]["type"] == "test"
        assert "ts" in events[0]

    def test_record_action(self, recorder: RunRecorder) -> None:
        recorder.record(
            "action",
            1,
            agent_id="a1",
            action_type="scavenge",
            params={},
            success=True,
            reason="",
        )
        events = _read_stream(recorder)
        assert len(events) == 1
        assert events[0]["kind"] == "action"
        assert events[0]["agent_id"] == "a1"
        assert events[0]["success"] is True

    def test_record_dm_call(self, recorder: RunRecorder) -> None:
        recorder.record(
            "dm_call",
            3,
            action="negotiate",
            agent_id="a1",
            hint="judge outcome",
            effects=[{"operator": "set", "target": "a1.stress", "value": 50}],
            narrative="The negotiation was tense.",
            tokens_in=100,
            tokens_out=50,
            elapsed_s=1.23,
        )
        events = _read_stream(recorder)
        assert len(events) == 1
        assert events[0]["kind"] == "dm_call"
        assert events[0]["tokens_in"] == 100
        assert events[0]["tokens_out"] == 50
        assert events[0]["elapsed_s"] == 1.23
        assert "ts" in events[0]

    def test_record_perceive(self, recorder: RunRecorder) -> None:
        recorder.record(
            "perceive",
            5,
            agent_id="a1",
            visible_agent_ids=["a2", "a3"],
            visible_entity_ids=["door_1"],
            events_delivered=3,
        )
        events = _read_stream(recorder)
        assert len(events) == 1
        assert events[0]["kind"] == "perceive"
        assert events[0]["agent_id"] == "a1"
        assert events[0]["visible_agent_ids"] == ["a2", "a3"]

    def test_record_register(self, recorder: RunRecorder) -> None:
        recorder.record("register", 0, agent_id="newcomer")
        events = _read_stream(recorder)
        assert events[0]["kind"] == "register"
        assert events[0]["agent_id"] == "newcomer"

    def test_record_wakeup(self, recorder: RunRecorder) -> None:
        recorder.record("wakeup", 10, agent_id="a1", reason="urgent: new_events")
        events = _read_stream(recorder)
        assert events[0]["kind"] == "wakeup"
        assert events[0]["reason"] == "urgent: new_events"

    def test_record_whisper(self, recorder: RunRecorder) -> None:
        recorder.record("whisper", 5, agent_id="a1", message="The ceiling cracks.")
        events = _read_stream(recorder)
        assert events[0]["kind"] == "whisper"
        assert events[0]["message"] == "The ceiling cracks."

    def test_all_kinds_in_one_stream(self, recorder: RunRecorder) -> None:
        """All event kinds go to the same stream.jsonl in order."""
        recorder.record("event", 1, type="test")
        recorder.record("action", 1, agent_id="a1", success=True)
        recorder.record("dm_call", 1, narrative="ok", tokens_in=10, tokens_out=5)
        recorder.record("perceive", 1, agent_id="a1")
        recorder.record("register", 0, agent_id="a1")
        recorder.record("wakeup", 1, agent_id="a1", reason="regular")
        recorder.record("whisper", 1, agent_id="a1", message="hi")

        events = _read_stream(recorder)
        assert len(events) == 7
        kinds = [e["kind"] for e in events]
        assert kinds == [
            "event",
            "action",
            "dm_call",
            "perceive",
            "register",
            "wakeup",
            "whisper",
        ]

    def test_save_final_state(self, recorder: RunRecorder) -> None:
        entities = [
            {"id": "e1", "type": "agent", "stress": 50},
            {"id": "e2", "type": "resource", "quantity": 10},
        ]
        recorder.save_final_state(entities)
        state_path = recorder.run_dir / "state_final.json"
        loaded = json.loads(state_path.read_text())
        assert len(loaded) == 2
        assert loaded[0]["id"] == "e1"

    def test_finalize(self, recorder: RunRecorder) -> None:
        recorder.record("event", 1, type="test")
        recorder.record("dm_call", 2, tokens_in=100, tokens_out=50)
        recorder.finalize(tick_count=42, agent_count=5)

        meta = json.loads((recorder.run_dir / "meta.json").read_text())
        assert meta["tick_count"] == 42
        assert meta["agent_count"] == 5
        assert meta["end_time"] is not None

        # summary.json should exist with kind counts and token totals
        summary = json.loads((recorder.run_dir / "summary.json").read_text())
        assert summary["counts"]["event"] == 1
        assert summary["counts"]["dm_call"] == 1
        assert summary["total_tokens_in"] == 100
        assert summary["total_tokens_out"] == 50


class TestSnapshots:
    def test_snapshots_dir_created(self, recorder: RunRecorder) -> None:
        assert (recorder.run_dir / "snapshots").is_dir()

    def test_save_state_writes_snapshot(self, recorder: RunRecorder) -> None:
        entities = [
            {"id": "a1", "type": "agent", "location": "kitchen"},
            {"id": "food", "type": "resource", "quantity": 20},
        ]
        recorder.save_state(entities, tick=0)
        snap_path = recorder.run_dir / "snapshots" / "0.json"
        assert snap_path.is_file()
        loaded = read_snapshot(snap_path)
        assert len(loaded) == 2
        assert loaded[0]["id"] == "a1"
        assert loaded[0]["location"] == "kitchen"

    def test_multiple_ticks_create_multiple_snapshots(self, recorder: RunRecorder) -> None:
        for tick in range(5):
            entities = [{"id": "a1", "type": "agent", "health": 100 - tick * 10}]
            recorder.save_state(entities, tick=tick)

        snap_dir = recorder.run_dir / "snapshots"
        files = sorted(f.name for f in snap_dir.glob("*.json"))
        assert files == ["0.json", "1.json", "2.json", "3.json", "4.json"]

        # Verify content changes per tick
        tick0 = read_snapshot(snap_dir / "0.json")
        tick4 = read_snapshot(snap_dir / "4.json")
        assert tick0[0]["health"] == 100
        assert tick4[0]["health"] == 60

    def test_save_state_still_writes_state_json(self, recorder: RunRecorder) -> None:
        """Snapshot addition must not break the existing state.json behavior."""
        entities = [{"id": "a1", "type": "agent"}]
        recorder.save_state(entities, tick=3)
        state_path = recorder.run_dir / "state.json"
        assert state_path.is_file()
        loaded = read_snapshot(state_path)
        assert loaded[0]["id"] == "a1"

    def test_save_state_writes_tick_file(self, recorder: RunRecorder) -> None:
        recorder.save_state([{"id": "a1", "type": "agent"}], tick=7)
        tick_path = recorder.run_dir / "tick"
        assert tick_path.read_text().strip() == "7"


class TestNullRecorder:
    def test_all_methods_are_noop(self) -> None:
        """NullRecorder should not raise on any method call."""
        nr = NullRecorder()
        nr.record("event", 1, type="test")
        nr.record("action", 1, agent_id="a1")
        nr.record("dm_call", 1, tokens_in=0, tokens_out=0)
        nr.record("perceive", 1, agent_id="a1")
        nr.save_final_state([])
        nr.finalize(0, 0)


class TestListRuns:
    def test_list_runs_empty(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))
        assert list_runs() == []

    def test_list_runs_finds_runs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))

        for rid, scene in [("run1", "bunker"), ("run2", "market")]:
            d = tmp_path / ".worldseed" / "runs" / rid
            d.mkdir(parents=True)
            meta = {
                "run_id": rid,
                "scene_id": scene,
                "start_time": "2026-03-17T10:00:00+00:00",
                "tick_count": 10 if rid == "run1" else 20,
                "agent_count": 3,
            }
            (d / "meta.json").write_text(json.dumps(meta))
            # stream.jsonl with dm_call events
            (d / "stream.jsonl").write_text(
                '{"kind":"dm_call","tick":1,"ts":"x"}\n'
                '{"kind":"dm_call","tick":2,"ts":"x"}\n'
                '{"kind":"event","tick":1,"ts":"x"}\n'
            )

        runs = list_runs()
        assert len(runs) == 2
        scenes = {r["scene_id"] for r in runs}
        assert scenes == {"bunker", "market"}
        for r in runs:
            assert r["dm_calls"] == 2  # only dm_call kind counted

    def test_list_runs_legacy_dm_calls_jsonl(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Old runs with dm_calls.jsonl (no stream.jsonl) still work."""
        monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))

        d = tmp_path / ".worldseed" / "runs" / "old_run"
        d.mkdir(parents=True)
        (d / "meta.json").write_text(
            json.dumps(
                {
                    "run_id": "old_run",
                    "scene_id": "legacy",
                    "start_time": "2026-01-01T00:00:00+00:00",
                }
            )
        )
        (d / "dm_calls.jsonl").write_text('{"x":1}\n{"x":2}\n')

        runs = list_runs()
        assert len(runs) == 1
        assert runs[0]["dm_calls"] == 2


class TestRecorderIntegration:
    """Test that the recorder integrates with WorldEngine correctly."""

    def test_engine_with_null_recorder(self) -> None:
        """WorldEngine works fine without a recorder (NullRecorder default)."""
        from worldseed.world import WorldEngine

        configs_dir = CONFIGS_DIR
        engine = WorldEngine(configs_dir / "minimal.yaml")
        assert isinstance(engine.recorder, NullRecorder)
        engine.register_from_config()
        engine.step()

    def test_engine_with_recorder(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """WorldEngine with RunRecorder records to stream.jsonl."""
        monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))

        from worldseed.world import WorldEngine

        configs_dir = CONFIGS_DIR
        config_path = configs_dir / "bunker.yaml"

        recorder = RunRecorder(
            run_id="test_run",
            config_path=config_path,
            scene_id="bunker",
            dm_model="none",
        )

        engine = WorldEngine(config_path, recorder=recorder)
        engine.register_from_config()

        # Submit an action and step
        engine.submit("old_chen", "say", {"message": "hello"})
        engine.step()

        # Check files
        run_dir = recorder.run_dir
        assert (run_dir / "meta.json").is_file()
        assert (run_dir / "config.yaml").is_file()

        # stream.jsonl should have events
        stream_path = run_dir / "stream.jsonl"
        assert stream_path.is_file()
        events = _read_stream(recorder)
        assert len(events) > 0

        # Should have register and action records
        # (perceive and event are no longer written to stream)
        kinds = {e["kind"] for e in events}
        assert "register" in kinds
        assert "action" in kinds

        # Find the action record
        action_records = [e for e in events if e["kind"] == "action"]
        assert len(action_records) >= 1
        assert action_records[0]["agent_id"] == "old_chen"
        assert action_records[0]["action_type"] == "say"

        # save_final_state + finalize
        recorder.save_final_state([e.to_dict() for e in engine.state.all_entities()])
        recorder.finalize(
            tick_count=1,
            agent_count=len(engine.get_registered_agents()),
        )

        meta = json.loads((run_dir / "meta.json").read_text())
        assert meta["tick_count"] == 1
        assert meta["agent_count"] > 0

        # state_final.json should have entities
        state = json.loads((run_dir / "state_final.json").read_text())
        assert len(state) > 0

        # summary.json should exist
        summary = json.loads((run_dir / "summary.json").read_text())
        assert "counts" in summary

    def test_engine_ticks_produce_snapshots(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Each engine tick writes a per-tick snapshot file."""
        monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))

        from worldseed.world import WorldEngine

        configs_dir = CONFIGS_DIR

        recorder = RunRecorder(
            run_id="snap_test",
            config_path=configs_dir / "bunker.yaml",
            scene_id="bunker",
            dm_model="none",
        )

        engine = WorldEngine(configs_dir / "bunker.yaml", recorder=recorder)
        engine.register_from_config()
        engine.save_state()  # tick 0 snapshot

        # Step 3 ticks
        for _ in range(3):
            engine.step()

        snap_dir = recorder.run_dir / "snapshots"
        files = sorted(int(f.stem) for f in snap_dir.glob("*.json"))
        assert files == [0, 1, 2, 3]

        # Tick 0 should have initial entities
        tick0 = read_snapshot(snap_dir / "0.json")
        assert len(tick0) > 0
        agent_ids = {e["id"] for e in tick0 if e.get("type") == "agent"}
        assert "old_chen" in agent_ids

        # Tick 3 should reflect auto_tick changes (bunker decays resources)
        tick3 = read_snapshot(snap_dir / "3.json")
        tick0_food = next(e for e in tick0 if e["id"] == "food_supply")
        tick3_food = next(e for e in tick3 if e["id"] == "food_supply")
        # Food should have decreased (bunker auto_tick decrements by 1/tick)
        assert tick3_food["quantity"] < tick0_food["quantity"]
