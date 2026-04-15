# Review Output

The skill should produce a local review bundle:

```text
tmp/asset-sourcing/{scene_id}/
  manifest.json
  review.html
  images/{entity_id}/...
  visual-review.json
```

## Manifest Shape

Recommended object:

```json
{
  "scene_id": "midnight-salon-archive",
  "premise": "Historical-dreamlike salon and archive scene.",
  "entities": [
    {"id": "salon", "label": "Salon", "role": "zone"}
  ],
  "candidates": [
    {
      "entity_id": "salon",
      "source": "met",
      "query_type": "literal",
      "query": "salon interior",
      "query_round": 1,
      "source_tier": "default",
      "latency_search_ms": 1200,
      "latency_hydration_ms": 950,
      "title": "Sample Title",
      "creator": "Artist Name",
      "source_url": "https://example.com/object",
      "image_url": "https://example.com/image.jpg",
      "local_image_path": "images/salon/met_1.jpg",
      "rights_text": "Public Domain",
      "search_fit_label": "adjacent",
      "search_fit_note": "Metadata suggests an interior-like room.",
      "image_verification_note": "Visually checked: reads clearly as a salon-like interior.",
      "recommended_rank": 1,
      "recommendation_reason": "Assigned after visual review."
    }
  ]
}
```

## HTML Requirements

The review page should be entity-first:
- one section per entity
- candidates from different sources shown together
- recommendation rank visible only when it comes from a trusted visual review pass
- cards should read like real works, not AI recommendation blurbs
- the page should support click-to-select, one card per entity

Each card should show:
- image
- source / institution
- title
- creator / date when available
- short factual work context when available

The selection footer should:
- stay compact by default
- support `Copy picks`
- support `Download picks.json`
- export a minimal picks object per entity containing only:
  - `title`
  - `source`

## Selection Standard

The point of the review page is:
- AI searches and narrows
- human previews and chooses
- top picks are only valid after image verification, not metadata match alone
- reviewed picks should also respect scene-level coherence and avoid obviously unsettling imagery unless requested

If the manifest has no trusted visual-review recommendations, the HTML should behave as an unranked picker:
- show the first few candidates in the main slots
- do not pretend there is a Top 1/2/3
- let the human or reviewing agent choose directly

Search-stage metadata labels are recall hints only:
- `search_fit_label`
- `search_fit_note`

Trusted review-stage fields are separate:
- `recommended_rank`
- `recommendation_reason`
- `image_verification_note`
- optional `review_fit_label`

Shortlist/download stage should also be explicit:
- `download-plan.json` is a shortlist for local image fetch
- it is not the same as `visual-review.json`
- it only says which candidates are worth downloading locally

Do not treat `exact` as the only success condition. The best candidate may be `adjacent` or `vibe` if it reads clearly in the scene.

## Rendering

To persist trusted picks after visual review, create a review JSON:

```json
{
  "reviewer": "agent-name",
  "picks": {
    "singer": [
      {
        "source": "wikimedia",
        "title": "Example Title",
        "reason": "Reads clearly as a singer performing on stage.",
        "image_verification_note": "Verified from the downloaded image, not metadata."
      }
    ]
  }
}
```

Apply it:

```bash
python3 skills/asset-sourcing/scripts/apply_visual_review.py \
  tmp/asset-sourcing/{scene_id}/manifest.json \
  tmp/asset-sourcing/{scene_id}/visual-review.json
```

Use the bundled renderer:

```bash
python3 skills/asset-sourcing/scripts/render_review.py \
  tmp/asset-sourcing/{scene_id}/manifest.json \
  tmp/asset-sourcing/{scene_id}/review.html
```

To populate local images after cheap recall, create a small download plan and run:

```bash
python3 skills/asset-sourcing/scripts/download_candidates.py \
  tmp/asset-sourcing/{scene_id}/manifest.json \
  tmp/asset-sourcing/{scene_id}/download-plan.json
```

Suggested download plan shape:

```json
{
  "picks": {
    "singer": [
      {"source": "openverse", "title": "Street singer, portrait"},
      {"source": "wellcome", "title": "Singer in Costume"}
    ]
  }
}
```

Meaning:
- these are the candidates worth downloading locally
- they are still not trusted final picks
- only `visual-review.json` can assign `Top 1/2/3`
