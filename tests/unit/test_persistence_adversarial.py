"""Adversarial tests for the RunRecorder persistence module (event-sourcing stream).

Attacks:
1.  Two RunRecorders with same run_id — file collision?
2.  RunRecorder with no records — stream.jsonl still created?
3.  finalize() called twice — crash?
4.  record() with non-serializable data — crash or skip?
5.  state_final.json with 1000 entities — large data
6.  stream.jsonl grows to 10000 lines — performance?
7.  Run directory permissions — what if ~/.worldseed doesn't exist?
8.  list_runs with corrupted meta.json — crash or skip?
9.  NullRecorder — all methods are truly no-ops?
10. Concurrent writes from parallel threads — safe?
"""

from __future__ import annotations

import json
import stat
import threading
import time
from pathlib import Path
from typing import Any

import pytest

from worldseed.persistence import NullRecorder, RunRecorder, list_runs

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_recorder(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, run_id: str = "adv_test") -> RunRecorder:
    monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))
    config_path = tmp_path / "test_config.yaml"
    config_path.write_text("scene:\n  id: test_scene\n")
    return RunRecorder(
        run_id=run_id,
        config_path=config_path,
        scene_id="test_scene",
        dm_model="test/model",
    )


def _read_stream(recorder: RunRecorder) -> list[dict]:
    path = recorder.run_dir / "stream.jsonl"
    if not path.is_file():
        return []
    lines = path.read_text(encoding="utf-8").strip().splitlines()
    return [json.loads(line) for line in lines if line.strip()]


# ===========================================================================
# Attack 1: Two RunRecorders with same run_id — file collision?
# ===========================================================================


class TestDuplicateRunId:
    """Two recorders sharing the same run_id write to the same directory.
    The second one must NOT crash on init. Both must be able to record."""

    def test_two_recorders_same_run_id(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))
        config = tmp_path / "cfg.yaml"
        config.write_text("x: 1\n")

        r1 = RunRecorder("dup_run", config, "s1", "m1")
        r2 = RunRecorder("dup_run", config, "s2", "m2")

        assert r1.run_dir == r2.run_dir

        # r2 init overwrites meta.json
        meta = json.loads((r1.run_dir / "meta.json").read_text())
        assert meta["scene_id"] == "s2"

        # Both can write — they append to the same stream
        r1.record("event", 1, source="r1")
        r2.record("event", 2, source="r2")

        events = _read_stream(r1)
        assert len(events) == 2
        sources = {e["source"] for e in events}
        assert sources == {"r1", "r2"}

        r1.finalize(10, 2)
        r2.finalize(20, 4)

        meta = json.loads((r1.run_dir / "meta.json").read_text())
        assert meta["tick_count"] == 20

    def test_interleaved_writes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Interleaved writes from two recorders produce valid JSONL."""
        monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))
        config = tmp_path / "cfg.yaml"
        config.write_text("x: 1\n")

        r1 = RunRecorder("interleave", config, "s1", "m1")
        r2 = RunRecorder("interleave", config, "s1", "m1")

        for i in range(50):
            r1.record("event", i, src="r1")
            r2.record("event", i, src="r2")

        events = _read_stream(r1)
        assert len(events) == 100
        for e in events:
            assert e["kind"] == "event"

        r1.finalize(0, 0)
        r2.finalize(0, 0)


# ===========================================================================
# Attack 2: Empty records — stream.jsonl still created?
# ===========================================================================


class TestEmptyRecords:
    def test_no_records_stream_exists(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Even with zero records, stream.jsonl should exist (opened on init)."""
        rec = _make_recorder(tmp_path, monkeypatch, "empty_run")
        rec.finalize(0, 0)

        stream = rec.run_dir / "stream.jsonl"
        assert stream.is_file()
        assert stream.read_text() == ""

    def test_empty_record(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Recording with minimal args produces valid JSON."""
        rec = _make_recorder(tmp_path, monkeypatch, "empty_rec")
        rec.record("event", 0)
        events = _read_stream(rec)
        assert len(events) == 1
        assert events[0]["kind"] == "event"
        assert events[0]["tick"] == 0
        rec.finalize(0, 0)


# ===========================================================================
# Attack 3: finalize() called twice — crash?
# ===========================================================================


class TestDoubleFinalize:
    def test_finalize_twice_no_crash(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        rec = _make_recorder(tmp_path, monkeypatch, "double_fin")
        rec.record("event", 1, type="test")
        rec.finalize(5, 2)
        rec.finalize(10, 3)

        meta = json.loads((rec.run_dir / "meta.json").read_text())
        assert meta["tick_count"] == 10

    def test_write_after_finalize(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Writing after finalize — stream closed, should not crash."""
        rec = _make_recorder(tmp_path, monkeypatch, "write_after_fin")
        rec.finalize(1, 1)
        # These should not raise thanks to try/except in record()
        rec.record("event", 99, type="test")
        rec.record("action", 99, agent_id="a1")
        rec.record("dm_call", 99, tokens_in=0, tokens_out=0)


# ===========================================================================
# Attack 4: Non-serializable data — crash or skip?
# ===========================================================================


class TestNonSerializable:
    def test_non_serializable_event(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """json.dumps with default=str should handle most types."""
        rec = _make_recorder(tmp_path, monkeypatch, "nonserial")
        rec.record("event", 1, data={1, 2, 3})
        events = _read_stream(rec)
        assert len(events) == 1
        assert "data" in events[0]
        rec.finalize(0, 0)

    def test_bytes_value(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Bytes should be stringified by default=str."""
        rec = _make_recorder(tmp_path, monkeypatch, "bytes_val")
        rec.record("event", 1, payload=b"\x00\x01\x02")
        events = _read_stream(rec)
        assert isinstance(events[0]["payload"], str)
        rec.finalize(0, 0)

    def test_circular_reference(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Circular reference cannot be serialized. record() catches the error."""
        rec = _make_recorder(tmp_path, monkeypatch, "circular")
        d: dict[str, Any] = {"a": 1}
        d["ref"] = d  # circular!

        # Should not raise
        rec.record("event", 1, **d)

        # Write failed, stream should be empty
        content = (rec.run_dir / "stream.jsonl").read_text()
        assert content.strip() == ""
        rec.finalize(0, 0)

    def test_lambda_value(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Lambda gets stringified by default=str."""
        rec = _make_recorder(tmp_path, monkeypatch, "lambda_val")
        rec.record("event", 1, fn=lambda x: x)
        events = _read_stream(rec)
        assert "lambda" in events[0]["fn"].lower()
        rec.finalize(0, 0)


# ===========================================================================
# Attack 5: state_final.json with 1000 entities — large data
# ===========================================================================


class TestLargeState:
    def test_1000_entities(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        rec = _make_recorder(tmp_path, monkeypatch, "large_state")
        entities = [
            {
                "id": f"entity_{i}",
                "type": "agent" if i % 3 == 0 else "resource",
                "health": 100 - i % 100,
                "inventory": list(range(20)),
                "nested": {"level1": {"level2": {"val": i}}},
            }
            for i in range(1000)
        ]
        rec.save_final_state(entities)

        state_path = rec.run_dir / "state_final.json"
        loaded = json.loads(state_path.read_text())
        assert len(loaded) == 1000
        assert loaded[999]["id"] == "entity_999"
        assert state_path.stat().st_size < 5 * 1024 * 1024
        rec.finalize(0, 0)

    def test_empty_state(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        rec = _make_recorder(tmp_path, monkeypatch, "empty_state")
        rec.save_final_state([])
        loaded = json.loads((rec.run_dir / "state_final.json").read_text())
        assert loaded == []
        rec.finalize(0, 0)


# ===========================================================================
# Attack 6: stream.jsonl grows to 10000 lines — performance
# ===========================================================================


class TestLargeStream:
    def test_10000_events_performance(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        rec = _make_recorder(tmp_path, monkeypatch, "perf_run")

        start = time.monotonic()
        for i in range(10000):
            rec.record("event", i, type="test", data={"x": i, "y": i * 2})
        elapsed = time.monotonic() - start

        assert elapsed < 10.0, f"10000 writes took {elapsed:.2f}s"

        events = _read_stream(rec)
        assert len(events) == 10000
        assert events[0]["tick"] == 0
        assert events[-1]["tick"] == 9999
        rec.finalize(10000, 0)

    def test_mixed_kinds(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Write multiple kinds — all go to the same stream."""
        rec = _make_recorder(tmp_path, monkeypatch, "mixed_kinds")

        for i in range(2500):
            rec.record("event", i, type="test")
            rec.record("action", i, agent_id=f"a{i % 10}", success=True)
            rec.record("dm_call", i, tokens_in=i, tokens_out=i)
            rec.record("perceive", i, agent_id=f"a{i % 10}")

        events = _read_stream(rec)
        assert len(events) == 10000

        # Count by kind
        counts: dict[str, int] = {}
        for e in events:
            counts[e["kind"]] = counts.get(e["kind"], 0) + 1
        assert counts == {
            "event": 2500,
            "action": 2500,
            "dm_call": 2500,
            "perceive": 2500,
        }

        rec.finalize(2500, 10)

        # Verify summary.json
        summary = json.loads((rec.run_dir / "summary.json").read_text())
        assert summary["counts"]["dm_call"] == 2500


# ===========================================================================
# Attack 7: Run directory permissions — ~/.worldseed doesn't exist
# ===========================================================================


class TestDirectoryCreation:
    def test_creates_nested_directories(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))
        assert not (tmp_path / ".worldseed").exists()

        config = tmp_path / "cfg.yaml"
        config.write_text("x: 1\n")
        rec = RunRecorder("fresh_run", config, "s1", "m1")

        assert rec.run_dir.is_dir()
        assert (tmp_path / ".worldseed" / "runs" / "fresh_run").is_dir()
        rec.finalize(0, 0)

    def test_no_config_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))
        rec = RunRecorder("no_cfg", None, "s1", "m1")
        assert not (rec.run_dir / "config.yaml").exists()
        rec.finalize(0, 0)

    def test_nonexistent_config_path(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))
        fake_path = tmp_path / "does_not_exist.yaml"
        rec = RunRecorder("bad_cfg", fake_path, "s1", "m1")
        assert not (rec.run_dir / "config.yaml").exists()
        rec.finalize(0, 0)

    def test_read_only_state_file(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """If state_final.json is read-only, save_final_state should not crash."""
        rec = _make_recorder(tmp_path, monkeypatch, "readonly")

        state_path = rec.run_dir / "state_final.json"
        state_path.write_text("[]")
        state_path.chmod(stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)

        try:
            rec.save_final_state([{"id": "e1"}])
        finally:
            state_path.chmod(stat.S_IRWXU)

        rec.finalize(0, 0)


# ===========================================================================
# Attack 8: list_runs with corrupted meta.json — crash or skip?
# ===========================================================================


class TestCorruptedListRuns:
    def test_corrupted_meta_json_skipped(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))
        runs_dir = tmp_path / ".worldseed" / "runs"

        # Good run
        good = runs_dir / "good_run"
        good.mkdir(parents=True)
        (good / "meta.json").write_text(
            json.dumps(
                {
                    "run_id": "good_run",
                    "scene_id": "test",
                    "start_time": "2026-03-17T10:00:00+00:00",
                    "tick_count": 5,
                    "agent_count": 2,
                }
            )
        )

        # Corrupted run
        bad = runs_dir / "bad_run"
        bad.mkdir(parents=True)
        (bad / "meta.json").write_text("{invalid json!!!")

        # Empty meta
        empty = runs_dir / "empty_run"
        empty.mkdir(parents=True)
        (empty / "meta.json").write_text("")

        results = list_runs()
        assert len(results) == 1
        assert results[0]["run_id"] == "good_run"

    def test_missing_meta_json(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))
        runs_dir = tmp_path / ".worldseed" / "runs"
        (runs_dir / "no_meta_run").mkdir(parents=True)
        assert list_runs() == []

    def test_meta_json_missing_fields(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))
        runs_dir = tmp_path / ".worldseed" / "runs"
        sparse = runs_dir / "sparse_run"
        sparse.mkdir(parents=True)
        (sparse / "meta.json").write_text("{}")

        results = list_runs()
        assert len(results) == 1
        assert results[0]["run_id"] == "sparse_run"
        assert results[0]["scene_id"] == "?"

    def test_non_directory_in_runs(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))
        runs_dir = tmp_path / ".worldseed" / "runs"
        runs_dir.mkdir(parents=True)
        (runs_dir / "stray_file.txt").write_text("not a run")
        assert list_runs() == []

    def test_corrupted_stream_jsonl(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Corrupted stream.jsonl lines should be skipped in dm_call counting."""
        monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))
        runs_dir = tmp_path / ".worldseed" / "runs"

        d = runs_dir / "with_bad_stream"
        d.mkdir(parents=True)
        (d / "meta.json").write_text(
            json.dumps(
                {
                    "run_id": "with_bad_stream",
                    "scene_id": "test",
                    "start_time": "2026-03-17T10:00:00+00:00",
                }
            )
        )
        (d / "stream.jsonl").write_text(
            'garbage line\n{"kind":"dm_call","tick":1}\n{"kind":"event","tick":2}\nmore garbage\n'
        )

        results = list_runs()
        assert len(results) == 1
        assert results[0]["dm_calls"] == 1


# ===========================================================================
# Attack 9: NullRecorder — all methods truly no-ops
# ===========================================================================


class TestNullRecorderAdversarial:
    def test_run_dir_is_dev_null(self) -> None:
        nr = NullRecorder()
        assert nr.run_dir == Path("/dev/null")

    def test_no_files_created(self, tmp_path: Path) -> None:
        nr = NullRecorder()
        before = set(tmp_path.rglob("*"))
        nr.record("event", 1, type="test")
        nr.record("action", 1, agent_id="a1")
        nr.record("dm_call", 1, tokens_in=100, tokens_out=50)
        nr.record("perceive", 1, agent_id="a1")
        nr.save_final_state([{"id": "e1", "type": "agent"}])
        nr.finalize(100, 10)
        after = set(tmp_path.rglob("*"))
        assert before == after

    def test_accepts_any_data(self) -> None:
        nr = NullRecorder()
        nr.record("event", 1, data="test")
        nr.record("action", 1)
        nr.record("dm_call", 1, tokens_in=0, tokens_out=0)
        nr.record("perceive", 0, agent_id="")
        nr.save_final_state([])
        nr.finalize(0, 0)
        nr.finalize(999999, 999999)

    def test_null_recorder_has_same_interface(self) -> None:
        """NullRecorder must have all public methods of RunRecorder."""
        run_methods = {m for m in dir(RunRecorder) if not m.startswith("_") and callable(getattr(RunRecorder, m))}
        null_methods = {m for m in dir(NullRecorder) if not m.startswith("_") and callable(getattr(NullRecorder, m))}
        missing = run_methods - null_methods
        assert missing == set(), f"NullRecorder missing methods: {missing}"


# ===========================================================================
# Attack 10: Concurrent writes from parallel threads — safe?
# ===========================================================================


class TestConcurrentWrites:
    def test_concurrent_stream_writes(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Multiple threads writing to stream simultaneously must not crash."""
        rec = _make_recorder(tmp_path, monkeypatch, "concurrent")
        n_threads = 8
        n_writes = 500
        errors: list[str] = []

        def writer(thread_id: int) -> None:
            try:
                for i in range(n_writes):
                    rec.record("event", i, thread=thread_id)
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")

        threads = [threading.Thread(target=writer, args=(t,)) for t in range(n_threads)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == [], f"Concurrent write errors: {errors}"

        stream_path = rec.run_dir / "stream.jsonl"
        lines = stream_path.read_text().strip().splitlines()

        valid = 0
        for line in lines:
            try:
                json.loads(line)
                valid += 1
            except json.JSONDecodeError:
                pass

        expected = n_threads * n_writes
        assert len(lines) >= expected * 0.95, f"Expected ~{expected} lines, got {len(lines)}"
        rec.finalize(0, 0)

    def test_concurrent_mixed_operations(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Different kinds written concurrently — all go to one stream."""
        rec = _make_recorder(tmp_path, monkeypatch, "conc_mixed")
        n_writes = 200
        errors: list[str] = []

        def event_writer() -> None:
            try:
                for i in range(n_writes):
                    rec.record("event", i, type="test")
            except Exception as e:
                errors.append(f"events: {e}")

        def action_writer() -> None:
            try:
                for i in range(n_writes):
                    rec.record("action", i, agent_id="a1", success=True)
            except Exception as e:
                errors.append(f"actions: {e}")

        def dm_writer() -> None:
            try:
                for i in range(n_writes):
                    rec.record("dm_call", i, tokens_in=i, tokens_out=i)
            except Exception as e:
                errors.append(f"dm: {e}")

        def perceive_writer() -> None:
            try:
                for i in range(n_writes):
                    rec.record("perceive", i, agent_id=f"a{i % 10}")
            except Exception as e:
                errors.append(f"perceive: {e}")

        threads = [
            threading.Thread(target=event_writer),
            threading.Thread(target=action_writer),
            threading.Thread(target=dm_writer),
            threading.Thread(target=perceive_writer),
        ]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == [], f"Mixed concurrent errors: {errors}"

        # All 800 records should be in one stream
        events = _read_stream(rec)
        # May be slightly less due to interleaving, but all should be there
        assert len(events) >= n_writes * 4 * 0.95
        rec.finalize(0, 0)

    def test_concurrent_save_final_state(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Multiple threads calling save_final_state — last write wins."""
        rec = _make_recorder(tmp_path, monkeypatch, "conc_state")
        errors: list[str] = []

        def state_writer(thread_id: int) -> None:
            try:
                for i in range(50):
                    rec.save_final_state([{"id": f"t{thread_id}_i{i}", "type": "agent"}])
            except Exception as e:
                errors.append(f"Thread {thread_id}: {e}")

        threads = [threading.Thread(target=state_writer, args=(t,)) for t in range(4)]
        for t in threads:
            t.start()
        for t in threads:
            t.join(timeout=30)

        assert errors == []
        state = json.loads((rec.run_dir / "state_final.json").read_text())
        assert len(state) == 1
        rec.finalize(0, 0)


# ===========================================================================
# Bonus: Edge cases
# ===========================================================================


class TestEdgeCases:
    def test_special_characters_in_run_id(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("WORLDSEED_HOME", str(tmp_path / ".worldseed"))
        config = tmp_path / "cfg.yaml"
        config.write_text("x: 1\n")

        rec = RunRecorder("run-with_dots.and-dashes", config, "s1", "m1")
        rec.record("event", 1, ok=True)
        rec.finalize(0, 0)
        assert rec.run_dir.is_dir()

    def test_unicode_in_events(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        rec = _make_recorder(tmp_path, monkeypatch, "unicode")
        rec.record("event", 1, msg="Hello 世界! 🌍 Привет мир")
        events = _read_stream(rec)
        assert "世界" in events[0]["msg"]
        assert "🌍" in events[0]["msg"]
        rec.finalize(0, 0)

    def test_very_large_single_event(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        rec = _make_recorder(tmp_path, monkeypatch, "huge_event")
        rec.record("event", 1, payload="x" * 1_000_000)
        events = _read_stream(rec)
        assert len(events[0]["payload"]) == 1_000_000
        rec.finalize(0, 0)

    def test_deeply_nested_state(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        rec = _make_recorder(tmp_path, monkeypatch, "deep_nest")
        d: dict[str, Any] = {"val": "leaf"}
        for i in range(50):
            d = {"level": i, "child": d}
        rec.save_final_state([{"id": "nested", "data": d}])

        state = json.loads((rec.run_dir / "state_final.json").read_text())
        node = state[0]["data"]
        for _ in range(50):
            node = node["child"]
        assert node["val"] == "leaf"
        rec.finalize(0, 0)

    def test_summary_token_totals(self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """summary.json should correctly sum token counts from dm_call events."""
        rec = _make_recorder(tmp_path, monkeypatch, "token_sum")
        rec.record("dm_call", 1, tokens_in=100, tokens_out=50)
        rec.record("dm_call", 2, tokens_in=200, tokens_out=80)
        rec.record("dm_call", 3, tokens_in=150, tokens_out=60)
        rec.record("event", 1, type="test")  # not a dm_call
        rec.finalize(3, 1)

        summary = json.loads((rec.run_dir / "summary.json").read_text())
        assert summary["total_tokens_in"] == 450
        assert summary["total_tokens_out"] == 190
        assert summary["counts"]["dm_call"] == 3
        assert summary["counts"]["event"] == 1
