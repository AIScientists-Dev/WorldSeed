"""Run Recorder — event-sourcing persistence to ~/.worldseed/runs/{run_id}/.

Each server run saves:
  meta.json       — scene_id, dm_model, start_time, end_time, tick_count, agent_count
  config.yaml     — copy of scene config used
  stream.jsonl    — single append-only event stream (source of truth)
  state_final.json — world state snapshot at shutdown
  summary.json    — kind counts + token totals (written at finalize)

stream.jsonl event kinds:
  event             — world event (from EventLog)
  action            — submitted action + result
  dm_call           — DM judgment with tokens, effects, narrative
  perceive          — what agent saw (entity IDs, counts)
  register          — agent registration
  wakeup            — agent wake signal
  whisper           — whisper message to agent
  gm_set_queued     — GM entity property set queued
  gm_remove_queued  — GM entity removal queued
  gm_set            — GM entity property set applied
  gm_remove         — GM entity removal applied
  gm_resolve_queued — GM natural-language resolve command queued
  gm_resolve        — GM resolve DM judgment with tokens, effects, narrative

All writes are fire-and-forget — they never block the tick loop.
"""

from __future__ import annotations

import json
import shutil
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from worldseed.paths import run_dir, runs_dir

log = structlog.get_logger()


def _json_line(obj: dict[str, Any]) -> str:
    """Serialize a dict to a single JSON line."""
    return json.dumps(obj, default=str, ensure_ascii=False)


class RunRecorder:
    """Records run data to ~/.worldseed/runs/{run_id}/."""

    def __init__(
        self,
        run_id: str,
        config_path: Path | None,
        scene_id: str,
        dm_model: str,
        resolved_config: dict[str, Any] | None = None,
    ) -> None:
        self._run_id = run_id
        self._listeners: list[Any] = []
        self._dir = run_dir(run_id)
        self._dir.mkdir(parents=True, exist_ok=True)
        self._snapshots_dir = self._dir / "snapshots"
        self._snapshots_dir.mkdir(exist_ok=True)

        # Save config: prefer resolved (presets expanded) over raw copy.
        # Resolved config ensures past runs have complete action defs
        # even when preset files aren't available at replay time.
        dest = self._dir / "config.yaml"
        if resolved_config is not None:
            import yaml

            dumped = yaml.dump(resolved_config, default_flow_style=False, allow_unicode=True)
            dest.write_text(dumped, encoding="utf-8")
        elif config_path is not None and config_path.is_file():
            if config_path.resolve() != dest.resolve():
                shutil.copy2(config_path, dest)

        # Write initial meta.json
        self._meta: dict[str, Any] = {
            "run_id": run_id,
            "scene_id": scene_id,
            "dm_model": dm_model,
            "status": "running",
            "start_time": datetime.now(UTC).isoformat(),
            "end_time": None,
            "tick_count": 0,
            "agent_count": 0,
        }
        self._write_meta()

        # Single append-only stream
        self._stream_f = open(  # noqa: SIM115
            self._dir / "stream.jsonl", "a", encoding="utf-8"
        )

    @property
    def run_dir(self) -> Path:
        """Directory where run data is stored."""
        return self._dir

    def _write_meta(self) -> None:
        """Write meta.json."""
        try:
            path = self._dir / "meta.json"
            path.write_text(
                json.dumps(self._meta, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            log.warning("persistence_meta_write_failed", exc_info=True)

    def add_listener(self, callback: Any) -> Callable[[], None]:
        """Register a callback for new stream records (SSE push).

        Returns a remove function that unregisters the listener.
        """
        self._listeners.append(callback)

        def remove() -> None:
            try:
                self._listeners.remove(callback)
            except ValueError:
                pass

        return remove

    def record(self, kind: str, tick: int, **data: Any) -> None:
        """Append a typed event to stream.jsonl.

        kind: event type discriminator (event, action, dm_call, etc.)
        tick: current engine tick
        **data: payload for this event kind
        """
        try:
            record = {
                "kind": kind,
                "tick": tick,
                "ts": datetime.now(UTC).isoformat(),
                **data,
            }
            line = _json_line(record)
            self._stream_f.write(line + "\n")
            self._stream_f.flush()
            # Notify SSE listeners
            dead: list[Any] = []
            for listener in self._listeners:
                try:
                    listener(record)
                except Exception:
                    log.warning("sse_listener_failed", exc_info=True)
                    dead.append(listener)
            for d in dead:
                try:
                    self._listeners.remove(d)
                except ValueError:
                    pass
        except Exception:
            log.warning("persistence_write_failed", exc_info=True)

    def save_state(
        self,
        entities: list[dict[str, Any]],
        tick: int,
        *,
        characters: dict[str, dict[str, Any]] | None = None,
    ) -> None:
        """Write state.json + tick file + per-tick snapshot.

        Called every tick. The API always reads state from disk.
        Per-tick snapshots enable frontend replay.
        state.json contains entities + resolved characters.
        """
        try:
            state_data: dict[str, Any] = {"entities": entities}
            if characters:
                state_data["characters"] = characters
            entity_json = json.dumps(state_data, default=str, ensure_ascii=False)

            # Latest state (existing behavior — API reads this)
            state_path = self._dir / "state.json"
            tmp = state_path.with_suffix(".tmp")
            tmp.write_text(entity_json, encoding="utf-8")
            tmp.replace(state_path)

            tick_path = self._dir / "tick"
            tick_path.write_text(str(tick), encoding="utf-8")

            # Per-tick snapshot (for replay)
            snapshot_path = self._snapshots_dir / f"{tick}.json"
            snapshot_path.write_text(entity_json, encoding="utf-8")
        except Exception:
            log.warning("persistence_state_write_failed", exc_info=True)

    def save_counters(self, **counters: Any) -> None:
        """Write engine counters (dm_call_count, etc.) for resume."""
        try:
            path = self._dir / "counters.json"
            path.write_text(
                json.dumps(counters, indent=2),
                encoding="utf-8",
            )
        except Exception:
            log.warning("persistence_counters_write_failed", exc_info=True)

    def load_counters(self) -> dict[str, Any]:
        """Read engine counters from disk. Returns empty dict if not found."""
        try:
            path = self._dir / "counters.json"
            if path.is_file():
                return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
        except Exception:
            log.warning("persistence_counters_read_failed", exc_info=True)
        return {}

    def save_transient(self, data: dict[str, Any]) -> None:
        """Write transient engine state for resume.

        Captures in-memory state that would otherwise be lost:
        - inbox: per-agent pending events and DMs
        - action_queue: pending actions waiting for next tick
        - think_intervals: per-agent wake frequency
        - recent_events: EventLog events for DM context
        """
        try:
            path = self._dir / "transient.json"
            path.write_text(
                json.dumps(data, default=str, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            log.info("transient_saved", run_id=self._run_id)
        except Exception:
            log.warning("persistence_transient_write_failed", exc_info=True)

    def load_transient(self) -> dict[str, Any]:
        """Read transient state from disk. Returns empty dict if not found."""
        try:
            path = self._dir / "transient.json"
            if path.is_file():
                return json.loads(path.read_text(encoding="utf-8"))  # type: ignore[no-any-return]
        except Exception:
            log.warning("persistence_transient_read_failed", exc_info=True)
        return {}

    def save_final_state(self, entities: list[dict[str, Any]]) -> None:
        """Write state_final.json — called once at shutdown."""
        try:
            path = self._dir / "state_final.json"
            path.write_text(
                json.dumps(entities, default=str, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
        except Exception:
            log.warning("persistence_state_write_failed", exc_info=True)

    def update_status(self, status: str) -> None:
        """Update run status in meta.json (running, paused, stopped)."""
        self._meta["status"] = status
        self._write_meta()
        log.info("run_status_changed", run_id=self._run_id, status=status)

    def finalize(self, tick_count: int, agent_count: int) -> None:
        """Update meta.json with end stats, close stream, write summary."""
        self._meta["end_time"] = datetime.now(UTC).isoformat()
        self._meta["tick_count"] = tick_count
        self._meta["agent_count"] = agent_count
        self._write_meta()

        # Close stream
        try:
            self._stream_f.close()
        except Exception:
            pass

        # Write summary.json from stream
        self._write_summary()

        log.info(
            "run_finalized",
            run_id=self._run_id,
            tick_count=tick_count,
            agent_count=agent_count,
            dir=str(self._dir),
        )

    def _write_summary(self) -> None:
        """Parse stream.jsonl and write summary.json."""
        counts: dict[str, int] = {}
        total_tokens_in = 0
        total_tokens_out = 0

        stream_path = self._dir / "stream.jsonl"
        try:
            for line in stream_path.read_text(encoding="utf-8").splitlines():
                line = line.strip()
                if not line:
                    continue
                try:
                    obj = json.loads(line)
                    k = obj.get("kind", "unknown")
                    counts[k] = counts.get(k, 0) + 1
                    if k in ("dm_call", "gm_resolve"):
                        total_tokens_in += obj.get("tokens_in", 0)
                        total_tokens_out += obj.get("tokens_out", 0)
                except json.JSONDecodeError:
                    counts["_corrupt"] = counts.get("_corrupt", 0) + 1
        except OSError:
            pass

        try:
            summary_path = self._dir / "summary.json"
            summary_path.write_text(
                json.dumps(
                    {
                        "counts": counts,
                        "total_tokens_in": total_tokens_in,
                        "total_tokens_out": total_tokens_out,
                    },
                    indent=2,
                    ensure_ascii=False,
                ),
                encoding="utf-8",
            )
        except Exception:
            log.warning("persistence_summary_write_failed", exc_info=True)


class NullRecorder:
    """No-op recorder for tests and contexts where persistence is disabled."""

    @property
    def run_dir(self) -> Path:
        return Path("/dev/null")

    def add_listener(self, callback: Any) -> Callable[[], None]:
        return lambda: None

    def record(self, kind: str, tick: int, **data: Any) -> None:
        pass

    def save_state(self, entities: list[dict[str, Any]], tick: int, **_: Any) -> None:
        pass

    def save_counters(self, **counters: Any) -> None:
        pass

    def load_counters(self) -> dict[str, Any]:
        return {}

    def save_transient(self, data: dict[str, Any]) -> None:
        pass

    def load_transient(self) -> dict[str, Any]:
        return {}

    def update_status(self, status: str) -> None:
        pass

    def save_final_state(self, entities: list[dict[str, Any]]) -> None:
        pass

    def finalize(self, tick_count: int, agent_count: int) -> None:
        pass


def list_runs() -> list[dict[str, Any]]:
    """List all past runs from the runs directory."""
    _runs_dir = runs_dir()
    if not _runs_dir.is_dir():
        return []

    results: list[dict[str, Any]] = []
    for entry in _runs_dir.iterdir():
        if not entry.is_dir():
            continue
        meta_path = entry / "meta.json"
        if not meta_path.is_file():
            continue
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            continue

        # Count DM calls from stream.jsonl (or legacy dm_calls.jsonl)
        dm_count = 0
        stream_path = entry / "stream.jsonl"
        dm_path = entry / "dm_calls.jsonl"
        if stream_path.is_file():
            try:
                for line in stream_path.read_text(encoding="utf-8").splitlines():
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        if json.loads(line).get("kind") == "dm_call":
                            dm_count += 1
                    except json.JSONDecodeError:
                        pass
            except OSError:
                pass
        elif dm_path.is_file():
            # Legacy: old runs with separate dm_calls.jsonl
            try:
                dm_count = sum(1 for line in dm_path.read_text(encoding="utf-8").splitlines() if line.strip())
            except OSError:
                pass

        results.append(
            {
                "run_id": meta.get("run_id", entry.name),
                "scene_id": meta.get("scene_id", "?"),
                "start_time": meta.get("start_time", "?"),
                "tick_count": meta.get("tick_count", 0),
                "agent_count": meta.get("agent_count", 0),
                "dm_calls": dm_count,
            }
        )

    # Sort newest first
    results.sort(key=lambda r: r["start_time"], reverse=True)
    return results


def load_run(run_id: str) -> dict[str, Any] | None:
    """Load a saved run's state for resuming.

    Returns {meta, state, tick, config_path} or None if not found.
    """
    _run_dir = run_dir(run_id)
    if not _run_dir.is_dir():
        log.warning("load_run_not_found", run_id=run_id)
        return None

    # meta.json
    meta_path = _run_dir / "meta.json"
    if not meta_path.is_file():
        log.warning("load_run_no_meta", run_id=run_id)
        return None
    try:
        meta = json.loads(meta_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        log.warning("load_run_meta_corrupt", run_id=run_id)
        return None

    # state.json (saved world state)
    state_path = _run_dir / "state.json"
    if not state_path.is_file():
        log.warning("load_run_no_state", run_id=run_id)
        return None
    try:
        state_raw = json.loads(state_path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        log.warning("load_run_state_corrupt", run_id=run_id)
        return None

    # Backward compat: old format is bare list, new format is {entities, characters}
    if isinstance(state_raw, list):
        entities = state_raw
        characters: dict[str, Any] = {}
    else:
        entities = state_raw.get("entities", [])
        characters = state_raw.get("characters", {})

    # tick
    tick_path = _run_dir / "tick"
    tick = 0
    if tick_path.is_file():
        try:
            tick = int(tick_path.read_text(encoding="utf-8").strip())
        except (ValueError, OSError):
            pass

    # config.yaml path
    config_path = _run_dir / "config.yaml"

    log.info(
        "run_loaded",
        run_id=run_id,
        scene_id=meta.get("scene_id"),
        tick=tick,
        entities=len(entities),
    )

    return {
        "meta": meta,
        "state": entities,
        "characters": characters,
        "tick": tick,
        "config_path": config_path if config_path.is_file() else None,
        "run_dir": _run_dir,
    }
