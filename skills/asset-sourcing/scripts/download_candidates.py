#!/usr/bin/env python3
"""Download only shortlisted candidates into an existing asset-sourcing bundle."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from search_candidates import Fetcher, _download_candidate, _load_json, _save_json


def _match_key(entity_id: str, source: str, title: str) -> str:
    return f"{entity_id.strip()}::{source.strip().lower()}::{title.strip()}"


def _build_plan_map(plan: dict[str, Any]) -> dict[str, dict[str, Any]]:
    picks = plan.get("picks", {})
    if not isinstance(picks, dict):
        raise ValueError("plan.picks must be an object")
    result: dict[str, dict[str, Any]] = {}
    for entity_id, entries in picks.items():
        if not isinstance(entries, list):
            raise ValueError(f"plan.picks.{entity_id} must be a list")
        for entry in entries:
            if not isinstance(entry, dict):
                raise ValueError(f"plan.picks.{entity_id} entries must be objects")
            source = str(entry.get("source") or "").strip()
            title = str(entry.get("title") or "").strip()
            if not source or not title:
                raise ValueError(f"plan.picks.{entity_id} entries need source and title")
            result[_match_key(entity_id, source, title)] = entry
    return result


def download_shortlist(manifest: dict[str, Any], manifest_path: Path, plan: dict[str, Any]) -> dict[str, Any]:
    bundle_dir = manifest_path.parent
    fetcher = Fetcher()
    plan_map = _build_plan_map(plan)
    candidates = manifest.get("candidates", [])
    if not isinstance(candidates, list):
        raise ValueError("manifest.candidates must be a list")

    downloaded = 0
    skipped = 0
    errors: list[str] = []
    satisfied: set[str] = set()

    counters: dict[tuple[str, str], int] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        entity_id = str(candidate.get("entity_id", "")).strip()
        source = str(candidate.get("source", "")).strip()
        title = str(candidate.get("title", "")).strip()
        match_key = _match_key(entity_id, source, title)
        match = plan_map.get(match_key)
        if match is None:
            continue
        if match_key in satisfied:
            skipped += 1
            continue
        if str(candidate.get("local_image_path", "")).strip():
            satisfied.add(match_key)
            skipped += 1
            continue
        download_url = str(candidate.get("download_url") or candidate.get("image_url") or "").strip()
        if not download_url:
            errors.append(f"{entity_id}::{source}::{title}: no download URL")
            continue
        key = (entity_id, source)
        counters[key] = counters.get(key, 0) + 1
        try:
            local_path, elapsed_ms, content_type = _download_candidate(
                fetcher, bundle_dir, entity_id, source, counters[key], download_url
            )
        except Exception as exc:
            candidate["download_error"] = str(exc)
            errors.append(f"{entity_id}::{source}::{title}: {exc}")
            continue
        candidate["local_image_path"] = local_path
        candidate["latency_download_ms"] = elapsed_ms
        candidate["content_type"] = content_type
        candidate["download_error"] = ""
        satisfied.add(match_key)
        downloaded += 1

    manifest["download_plan"] = {
        "requested": len(plan_map),
        "downloaded": downloaded,
        "already_present": skipped,
        "errors": errors,
    }
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Download shortlisted candidates for an asset-sourcing bundle")
    parser.add_argument("manifest", help="Bundle manifest JSON")
    parser.add_argument("plan", help="JSON file with picks per entity to download")
    parser.add_argument("--output", help="Output manifest JSON; defaults to in-place")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    plan_path = Path(args.plan).resolve()
    output_path = Path(args.output).resolve() if args.output else manifest_path

    manifest = _load_json(manifest_path)
    plan = _load_json(plan_path)
    updated = download_shortlist(manifest, manifest_path, plan)
    _save_json(output_path, updated)
    print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
