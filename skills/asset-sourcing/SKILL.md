---
name: asset-sourcing
description: Source image candidates for a brand-new WorldSeed scene, let an AI visually review them, and generate a local review HTML for human selection.
---

# Asset Sourcing

Use this skill when a user wants image candidates for a new or existing WorldSeed scene and the goal is to build a reviewable asset board, not auto-pick final assets.

## Goal

Produce a local review bundle:
- candidate metadata
- selectively downloaded review-size candidate images
- a structured `manifest.json`
- an entity-first `review.html`
- a minimal selected-picks export from the HTML picker

Default bundle:

```text
tmp/asset-sourcing/{scene_id}/
  manifest.json
  review.html
  images/{entity_id}/...
```

This skill is standalone. It stops at a reviewable bundle and selected picks. Import into a scene should happen later as a separate step.

## Supported Sources

Default sources:
- `openverse`
- `aic`
- `cleveland`
- `vam`
- `wellcome`
- `ycba`
- `met`

Optional sources:
- `wikimedia`
- `walters`
- `nasa`

Read `references/source-catalog.md` before using a source you have not used recently.

## Execution Rules

- Use supported sources only.
- Treat sourcing as entity-grounded, not exact-illustration-only. `exact`, `adjacent`, and `vibe` can all be usable.
- Do not stop after one keyword search.
- Let the AI choose keywords and source order per entity.
- Search only the sources that are justified for the current entity.
- Search different sources in parallel when useful.
- Start with likely fast sources and widen only when needed.
- Treat `met` as a later pass, not a universal first call.
- Only use optional sources when they are justified:
  - `wikimedia` for known motifs, named figures, or coverage gaps
  - `walters` for watches, keys, portraits, and manuscript-adjacent objects
  - `nasa` for cosmic or scientific entities only
- Preserve source URLs, image URLs, and rights text in the manifest.
- Search first. Download only shortlisted candidates by default.
- Treat metadata as recall only. Final retention and top picks must be image-verified.
- Reject obvious homonym and name-collision matches when the image subject is wrong, even if the title contains the entity token.
- Prefer a visually coherent set across entities. When multiple candidates are equally valid, favor the ones that fit the scene's overall medium, period, and mood.
- Avoid obvious horror, gore, medical shock, body horror, or otherwise unsettling imagery unless the user explicitly wants that tone.
- Do not auto-pick final assets. The default output is a candidate board for agent/human review in HTML.

## Workflow

### 1. Define the scene and entities

The input scene JSON must contain:
- `scene_id`
- optional `premise`
- `entities`

Each entity must contain:
- `id`
- `label`
- `role`

Initialize a bundle with:

```bash
python3 skills/asset-sourcing/scripts/init_bundle.py \
  tmp/asset-sourcing/{scene_id} \
  --fixture tmp/asset-sourcing/{scene_id}/scene.json
```

### 2. Generate queries and choose sources

For each entity, start with:
- one `literal` query
- one `related` query
- one `vibe` query

Useful defaults:
- `zone`
  - `literal`: `{label} interior`
  - `related`: `{label} room`
  - `vibe`: `{label} painting`
- `agent`
  - `literal`: `{label} portrait`
  - `related`: `{label} figure`
  - `vibe`: `{label} painting`
- `item`
  - `literal`: `{label}`
  - `related`: `{label} still life`
  - `vibe`: `{label} object`
- `symbolic`
  - `literal`: `{label}`
  - `related`: `{label} illustration`
  - `vibe`: `{label} print`

Rewrite rules:
- shorten weak queries to one or two strong nouns
- remove decorative adjectives before adding more
- add a medium hint like `portrait`, `interior`, `still life`, `illustration`, or `engraving`
- for symbolic entities, accept clear stand-ins but reject person-name homonyms unless the image proves the match

Source strategy:
- `zone`: start with `openverse`, `aic`, `cleveland`; widen with `vam`, `ycba`, then `met`
- `agent`: start with `openverse`, `aic`, `wellcome`; widen with `ycba`, then `met`
- `item`: start with `openverse`, `aic`, `cleveland`; use `walters` when objects/manuscripts fit; widen with `met`
- `symbolic`: start with `openverse`; use `wikimedia` for motifs and `nasa` for celestial/scientific entities

### 3. Search adaptively

For each entity:
- choose the most likely 1-3 sources first
- search those sources in parallel when useful
- inspect the returned candidates, not metadata alone
- if the batch is weak or misleading, rewrite the query and try again
- widen source coverage only when needed
- stop when the entity has enough usable candidates or the search budget is exhausted

Before final retention:
- look at the image, not just the title, filename, or source page metadata
- if the image subject is wrong, mark it `miss` or drop it
- for `symbolic`, `item`, and animal-like entities, treat person-name homonyms as likely false positives until the image proves otherwise
- reject candidates that break the scene's tone even if they are semantically correct
- prefer candidate sets that feel stylistically compatible with each other, not just individually plausible

Default target:
- `4-8` usable candidates overall per entity
- visual recommendations are optional and should only be added after image review

### 4. Retain and rank

For each retained candidate, capture:
- source
- entity ID
- query type
- exact query string
- title
- creator
- source page URL
- image URL
- local image path
- rights text
- `search_fit_label`
- `search_fit_note`
- `source_tier`
- `query_round`
- optional image-verification note when a candidate needed manual disambiguation
- optional `recommended_rank` and `recommendation_reason` only after agent/human visual review

### 5. Search one source and append candidates

`search_candidates.py` is a thin helper, not a full scene runner. It should be called once per `entity + source + query`.

By default it performs cheap recall and appends metadata without downloading images.

Save downloaded images under:

```text
tmp/asset-sourcing/{scene_id}/images/{entity_id}/
```

Example:

```bash
python3 skills/asset-sourcing/scripts/search_candidates.py \
  --manifest tmp/asset-sourcing/{scene_id}/manifest.json \
  --entity-id singer \
  --source openverse \
  --query 'singer portrait' \
  --query-type related \
  --query-round 1 \
  --source-tier default
```

The AI should decide:
- which source calls to make
- which queries to use
- when to stop widening search

### 6. Download only the shortlist

After cheap recall, write a shortlist JSON:

```json
{
  "picks": {
    "singer": [
      {"source": "openverse", "title": "Street singer, portrait"}
    ]
  }
}
```

Then download only those candidates:

```bash
python3 skills/asset-sourcing/scripts/download_candidates.py \
  tmp/asset-sourcing/{scene_id}/manifest.json \
  tmp/asset-sourcing/{scene_id}/download-plan.json
```

### 7. Render the review HTML

Run:

```bash
python3 skills/asset-sourcing/scripts/render_review.py \
  tmp/asset-sourcing/{scene_id}/manifest.json \
  tmp/asset-sourcing/{scene_id}/review.html
```

The review page is the main product. It should let a human quickly scan the strongest reviewed picks, open more options only when needed, and choose final assets.

The current picker behavior is:
- one long scroll page
- one section per entity
- reviewed picks appear first with `Top 1/2/3` only when the manifest contains trusted visual-review recommendations
- if there are no reviewed picks yet, the first few candidates still appear in the same slot, but without `Top` badges
- no metadata-fit language should drive the unreviewed UI
- click one card per entity to select it
- export a minimal picks object with:
  - `title`
  - `source`

### 8. Apply visual review recommendations

If an agent or human has visually reviewed the downloaded images and chosen ranked picks, write them back into the manifest before the final render.

Review file shape:

```json
{
  "reviewer": "agent-name",
  "picks": {
    "raven": [
      {"source": "wikimedia", "title": "Kalila and Dimna - The Owls and the raven", "reason": "Only candidate that clearly reads as a raven scene."}
    ]
  }
}
```

Apply it with:

```bash
python3 skills/asset-sourcing/scripts/apply_visual_review.py \
  tmp/asset-sourcing/{scene_id}/manifest.json \
  tmp/asset-sourcing/{scene_id}/visual-review.json
```

Then rerender:

```bash
python3 skills/asset-sourcing/scripts/render_review.py \
  tmp/asset-sourcing/{scene_id}/manifest.json \
  tmp/asset-sourcing/{scene_id}/review.html
```

## What the AI Should Do

When this skill is active, the AI should:
- read the scene and entities
- choose queries and sources per entity
- run independent source searches in parallel when useful
- rewrite weak queries
- visually inspect candidates before treating them as top picks
- compare candidates across sources
- emit a reviewable local bundle
- only write `recommended_rank` after actual image review

The AI should not:
- use unsupported sources by default
- stop after a single keyword
- exhaust every source for every entity by default
- trust metadata alone
- keep a candidate whose image subject is wrong just because the title matches
- choose final assets without human review

## References

- `references/source-catalog.md` — supported source list and exact usage patterns
- `references/review-output.md` — bundle and manifest contract
