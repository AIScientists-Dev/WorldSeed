#!/usr/bin/env python3
"""Apply agent/human visual review rankings to an asset-sourcing manifest."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any


TRUSTED_MODE = "agent-visual-review"


def _load_json(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"{path} must contain a JSON object")
    return data


def _save_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=True) + "\n", encoding="utf-8")


def _candidate_key(candidate: dict[str, Any]) -> str:
    entity_id = str(candidate.get("entity_id", "")).strip()
    source = str(candidate.get("source", "")).strip()
    title = str(candidate.get("title", "")).strip()
    return f"{entity_id}::{source}::{title}"


def apply_visual_review(
    manifest: dict[str, Any], review: dict[str, Any], reviewer: str | None = None
) -> dict[str, Any]:
    candidates = manifest.get("candidates", [])
    if not isinstance(candidates, list):
        raise ValueError("manifest.candidates must be a list")

    by_key: dict[str, dict[str, Any]] = {}
    for candidate in candidates:
        if isinstance(candidate, dict):
            candidate.pop("recommended_rank", None)
            candidate.pop("recommendation_reason", None)
            candidate.pop("image_verification_note", None)
            by_key[_candidate_key(candidate)] = candidate

    picks = review.get("picks", {})
    if not isinstance(picks, dict):
        raise ValueError("review.picks must be an object")

    for entity_id, entries in picks.items():
        if not isinstance(entries, list):
            raise ValueError(f"review.picks.{entity_id} must be a list")
        for index, entry in enumerate(entries, start=1):
            if not isinstance(entry, dict):
                raise ValueError(f"review.picks.{entity_id}[{index - 1}] must be an object")
            source = str(entry.get("source", "")).strip()
            title = str(entry.get("title", "")).strip()
            if not source or not title:
                raise ValueError(f"review.picks.{entity_id}[{index - 1}] needs source and title")
            key = f"{entity_id}::{source}::{title}"
            candidate = by_key.get(key)
            if candidate is None:
                raise ValueError(f"review pick did not match a manifest candidate: {key}")
            candidate["recommended_rank"] = index
            candidate["recommendation_reason"] = str(
                entry.get("reason")
                or entry.get("recommendation_reason")
                or f"Assigned after visual review by {reviewer or 'reviewer'}."
            ).strip()
            note = str(
                entry.get("image_verification_note")
                or entry.get("visual_note")
                or entry.get("note")
                or ""
            ).strip()
            if note:
                candidate["image_verification_note"] = note

    manifest["recommendation_mode"] = TRUSTED_MODE
    manifest["reviewer"] = reviewer or str(review.get("reviewer") or "").strip()
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description="Apply visual-review rankings to a manifest")
    parser.add_argument("manifest", help="Input manifest JSON")
    parser.add_argument("review", help="Visual review JSON with picks per entity")
    parser.add_argument("--output", help="Output manifest JSON; defaults to in-place")
    parser.add_argument("--reviewer", help="Reviewer label to persist in the manifest")
    args = parser.parse_args()

    manifest_path = Path(args.manifest).resolve()
    review_path = Path(args.review).resolve()
    output_path = Path(args.output).resolve() if args.output else manifest_path

    manifest = _load_json(manifest_path)
    review = _load_json(review_path)
    updated = apply_visual_review(manifest, review, reviewer=args.reviewer)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _save_json(output_path, updated)
    print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
