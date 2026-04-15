#!/usr/bin/env python3
"""Initialize an asset-sourcing working bundle from a fixture."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


def _load_fixture(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Fixture root must be an object")
    if "scene_id" not in data or "entities" not in data:
        raise ValueError("Fixture must contain 'scene_id' and 'entities'")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize an asset-sourcing bundle")
    parser.add_argument("output_dir", help="Bundle directory, e.g. tmp/asset-sourcing/my-scene")
    parser.add_argument("--fixture", required=True, help="Fixture JSON with scene_id, premise, and entities")
    args = parser.parse_args()

    fixture_path = Path(args.fixture).resolve()
    output_dir = Path(args.output_dir).resolve()
    fixture = _load_fixture(fixture_path)

    output_dir.mkdir(parents=True, exist_ok=True)
    images_dir = output_dir / "images"
    images_dir.mkdir(exist_ok=True)

    entities = fixture.get("entities", [])
    if isinstance(entities, list):
        for entity in entities:
            if isinstance(entity, dict) and entity.get("id"):
                (images_dir / str(entity["id"])).mkdir(exist_ok=True)

    manifest = {
        "scene_id": fixture.get("scene_id", output_dir.name),
        "premise": fixture.get("premise", ""),
        "entities": entities,
        "recommendation_mode": "unreviewed",
        "search_runs": [],
        "candidates": [],
    }
    manifest_path = output_dir / "manifest.json"
    manifest_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")
    print(f"initialized {output_dir}")
    print(f"wrote {manifest_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
