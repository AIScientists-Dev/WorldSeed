"""Gazette cache — multiple gazettes per run.

Storage layout:
  ~/.worldseed/runs/{run_id}/gazettes/
    {gazette_id}.json   ← full GazetteResult

gazette_id is a timestamp-based ID: "20260325_014530"
"""

from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import structlog

from worldseed.gazette.schema import GazetteResult
from worldseed.paths import run_dir

log = structlog.get_logger()


def _gazettes_dir(run_id: str) -> Path:
    return run_dir(run_id) / "gazettes"


def _make_id() -> str:
    return datetime.now(tz=UTC).strftime("%Y%m%d_%H%M%S")


def list_gazettes(run_id: str) -> list[dict[str, Any]]:
    """List all gazettes for a run (summary only, newest first)."""
    gdir = _gazettes_dir(run_id)
    if not gdir.is_dir():
        _migrate_legacy(run_id)
        if not gdir.is_dir():
            return []

    results: list[dict[str, Any]] = []
    for f in sorted(gdir.iterdir(), reverse=True):
        if f.suffix != ".json":
            continue
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            gen = data.get("generation", {})
            results.append(
                {
                    "id": f.stem,
                    "edition_title": data.get("gazette", {}).get("edition_title", ""),
                    "language": data.get("language", ""),
                    "model": gen.get("model", ""),
                    "cost_usd": gen.get("cost_usd", 0),
                    "created_at": gen.get("created_at", f.stem),
                }
            )
        except Exception:
            log.warning("gazette_parse_failed", path=str(f))
    return results


def get_gazette(run_id: str, gazette_id: str) -> GazetteResult | None:
    """Read a specific gazette by ID."""
    path = _gazettes_dir(run_id) / f"{gazette_id}.json"
    if not path.is_file():
        return None
    data = json.loads(path.read_text(encoding="utf-8"))
    return GazetteResult(**data)


def get_latest(run_id: str) -> GazetteResult | None:
    """Read the most recent gazette (newest filename = latest)."""
    gdir = _gazettes_dir(run_id)
    if not gdir.is_dir():
        return None
    files = sorted(
        (f for f in gdir.iterdir() if f.suffix == ".json"),
        reverse=True,
    )
    if not files:
        return None
    data = json.loads(files[0].read_text(encoding="utf-8"))
    return GazetteResult(**data)


def save(run_id: str, result: GazetteResult) -> str:
    """Save a gazette and return its ID."""
    gdir = _gazettes_dir(run_id)
    gdir.mkdir(parents=True, exist_ok=True)

    gazette_id = _make_id()
    gen = dict(result.generation)
    gen["created_at"] = gazette_id
    result = result.model_copy(update={"generation": gen})

    path = gdir / f"{gazette_id}.json"
    path.write_text(
        json.dumps(result.model_dump(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    return gazette_id


def _migrate_legacy(run_id: str) -> None:
    """Migrate old single gazette.json to gazettes/ directory."""
    legacy = run_dir(run_id) / "gazette.json"
    if not legacy.is_file():
        return
    try:
        data = json.loads(legacy.read_text(encoding="utf-8"))
        result = GazetteResult(**data)
        save(run_id, result)
        legacy.unlink()
        log.info("gazette_migrated", run_id=run_id)
    except Exception:
        log.warning("gazette_migration_failed", run_id=run_id)
