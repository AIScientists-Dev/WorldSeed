#!/usr/bin/env python3
"""Render a compact, selectable HTML review page from an asset-sourcing manifest."""

from __future__ import annotations

import html
import json
import sys
from pathlib import Path
from typing import Any


FIT_ORDER = {"exact": 0, "adjacent": 1, "vibe": 2, "miss": 3}
FIT_LABELS = {
    "exact": "Best match",
    "adjacent": "Alt",
    "vibe": "Vibe",
    "miss": "Miss",
}

SOURCE_LABELS = {
    "met": "The Met",
    "aic": "Art Institute of Chicago",
    "cleveland": "Cleveland Museum of Art",
    "vam": "V&A",
    "wellcome": "Wellcome Collection",
    "ycba": "Yale Center for British Art",
    "walters": "Walters Art Museum",
    "wikimedia": "Wikimedia Commons",
    "nasa": "NASA",
    "openverse": "Openverse",
}

TRUSTED_RECOMMENDATION_MODES = {
    "agent-visual-review",
    "human-reviewed",
    "visual-reviewed",
}


def _load_manifest(path: Path) -> dict[str, Any]:
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("Manifest root must be an object")
    if "entities" not in data or "candidates" not in data:
        raise ValueError("Manifest must contain 'entities' and 'candidates'")
    return data


def _esc(value: Any) -> str:
    return html.escape(str(value or ""))


def _entity_map(entities: list[dict[str, Any]]) -> dict[str, dict[str, Any]]:
    return {
        str(entity.get("id", "")).strip(): entity
        for entity in entities
        if isinstance(entity, dict) and str(entity.get("id", "")).strip()
    }


def _candidate_fit_label(item: dict[str, Any]) -> str:
    return str(
        item.get("review_fit_label")
        or item.get("search_fit_label")
        or item.get("fit_label")
        or ""
    ).lower()


def _sort_key(item: dict[str, Any], *, trust_recommendations: bool) -> tuple[int, int, int, str, str]:
    rank = item.get("recommended_rank")
    rank_order = rank if trust_recommendations and isinstance(rank, int) else 99
    local_order = 0 if str(item.get("local_image_path", "")).strip() else 1
    return (
        rank_order,
        local_order,
        FIT_ORDER.get(_candidate_fit_label(item), 99),
        str(item.get("source", "")),
        str(item.get("title", "")),
    )


def _group_candidates(
    candidates: list[dict[str, Any]], *, trust_recommendations: bool
) -> dict[str, list[dict[str, Any]]]:
    grouped: dict[str, list[dict[str, Any]]] = {}
    for candidate in candidates:
        if not isinstance(candidate, dict):
            continue
        entity_id = str(candidate.get("entity_id", "")).strip()
        if not entity_id:
            continue
        grouped.setdefault(entity_id, []).append(candidate)

    for items in grouped.values():
        items.sort(key=lambda item: _sort_key(item, trust_recommendations=trust_recommendations))
    return grouped


def _img_src(candidate: dict[str, Any], manifest_path: Path) -> str:
    local_path = str(candidate.get("local_image_path", "")).strip()
    if local_path:
        try:
            return Path(local_path).resolve().relative_to(manifest_path.parent.resolve()).as_posix()
        except Exception:
            try:
                return Path(local_path).resolve().relative_to(Path.cwd().resolve()).as_posix()
            except Exception:
                return Path(local_path).as_posix()
    return str(candidate.get("image_url", "")).strip()


def _fit_text(candidate: dict[str, Any]) -> str:
    return FIT_LABELS.get(_candidate_fit_label(candidate), "Candidate")


def _source_label(candidate: dict[str, Any]) -> str:
    source = str(candidate.get("source", "")).strip().lower()
    return SOURCE_LABELS.get(source, source or "Source")


def _find_description(value: Any) -> str:
    if isinstance(value, dict):
        priority = (
            "description",
            "caption",
            "summary",
            "credit",
            "creditline",
            "text",
            "snippet",
            "label",
            "alt",
        )
        for key in priority:
            raw = value.get(key)
            if isinstance(raw, str) and raw.strip():
                return raw.strip()
        for raw in value.values():
            text = _find_description(raw)
            if text:
                return text
    if isinstance(value, list):
        for item in value:
            text = _find_description(item)
            if text:
                return text
    return ""


def _compact_text(value: str, *, limit: int = 120) -> str:
    text = " ".join(value.split())
    if len(text) <= limit:
        return text
    cutoff = text.rfind(" ", 0, limit)
    if cutoff < max(30, limit // 2):
        cutoff = limit
    return text[:cutoff].rstrip(" ,;:") + "..."


def _work_meta(candidate: dict[str, Any]) -> str:
    creator = str(candidate.get("creator", "")).strip()
    date = str(candidate.get("date", "")).strip()
    if creator and creator.lower() != "unknown" and date:
        return f"{creator}, {date}"
    if creator and creator.lower() != "unknown":
        return creator
    if date:
        return date
    return ""


def _work_description(candidate: dict[str, Any]) -> str:
    extra = candidate.get("extra")
    if isinstance(extra, (dict, list)):
        text = _find_description(extra)
        if text:
            return _compact_text(text)
    return ""


def _card(
    entity_id: str,
    candidate: dict[str, Any],
    *,
    manifest_path: Path,
    extra_class: str = "",
    show_rank: bool = False,
    show_fit: bool = False,
) -> str:
    image_src = _img_src(candidate, manifest_path)
    title = _esc(candidate.get("title", "Untitled"))
    source_meta = _esc(_source_label(candidate))
    work_meta = _esc(_work_meta(candidate))
    description = _esc(_work_description(candidate))
    rank = candidate.get("recommended_rank")
    rank_badge = (
        f'<span class="rank-badge">Top {rank}</span>'
        if show_rank and isinstance(rank, int)
        else ""
    )
    source_url = _esc(candidate.get("source_url", ""))
    link_html = (
        f'<a class="source-link" href="{source_url}" target="_blank" rel="noreferrer" onclick="event.stopPropagation()">View source</a>'
        if source_url
        else ""
    )
    candidate_id = _esc(f"{entity_id}::{candidate.get('source','')}::{candidate.get('title','')}")
    payload = {
        "title": str(candidate.get("title", "")),
        "source": str(candidate.get("source", "")),
    }
    payload_json = _esc(json.dumps(payload, ensure_ascii=True))
    image_html = (
        f'<img src="{_esc(image_src)}" loading="lazy" alt="{title}">'
        if image_src
        else '<div class="img-missing">No image</div>'
    )
    meta_html = f'<p class="meta-line">{work_meta}</p>' if work_meta else ""
    summary_html = f'<p class="summary">{description}</p>' if description else ""

    return f"""
    <article class="card {extra_class}" data-entity-id="{_esc(entity_id)}" data-candidate-id="{candidate_id}" data-payload="{payload_json}">
      <button class="card-button" type="button" aria-label="Select {title}">
        <div class="image-wrap">
          {image_html}
          {rank_badge}
        </div>
        <div class="card-body">
          <div class="card-topline">
            <span class="eyebrow">{source_meta}</span>
            {"<span class=\"fit-chip fit-" + _esc(_candidate_fit_label(candidate) or "unknown") + "\">" + _esc(_fit_text(candidate)) + "</span>" if show_fit else ""}
          </div>
          <div class="caption-block">
            <h3>{title}</h3>
            {meta_html}
            {summary_html}
          </div>
        </div>
      </button>
      {link_html}
    </article>
    """


def _entity_section(
    entity: dict[str, Any],
    candidates: list[dict[str, Any]],
    *,
    manifest_path: Path,
    trust_recommendations: bool,
) -> str:
    label = _esc(entity.get("label", entity.get("id", "")))
    entity_id = str(entity.get("id", "")).strip()
    role = _esc(entity.get("role", ""))
    visible = [
        candidate
        for candidate in candidates
        if (
            (trust_recommendations and isinstance(candidate.get("recommended_rank"), int))
            or _candidate_fit_label(candidate) != "miss"
        )
        and (candidate.get("local_image_path") or candidate.get("image_url"))
    ]

    top_html = ""
    more_html = ""
    shown_count = len(visible)
    primary = visible[:3]
    more = visible[3:]
    shown_count = len(primary)

    top_html = "\n".join(
        _card(
            entity_id,
            candidate,
            manifest_path=manifest_path,
            extra_class="top" if trust_recommendations and isinstance(candidate.get("recommended_rank"), int) else "option",
            show_rank=trust_recommendations and isinstance(candidate.get("recommended_rank"), int),
            show_fit=False,
        )
        for candidate in primary
    )
    if not top_html:
        top_html = '<div class="empty">No usable candidates yet.</div>'

    if more:
        extra_cards = "\n".join(
            _card(entity_id, candidate, manifest_path=manifest_path, extra_class="option", show_rank=False, show_fit=False) for candidate in more
        )
        more_html = f"""
        <details class="more-options">
          <summary>More options ({len(more)})</summary>
          <div class="option-grid">
            {extra_cards}
          </div>
        </details>
        """

    return f"""
    <section class="entity" id="{_esc(entity_id)}">
      <header class="entity-head">
        <div class="entity-meta">
          <div class="entity-role">{role}</div>
          <h2>{label}</h2>
        </div>
        <div class="entity-stats">{shown_count} shown</div>
      </header>
      <div class="top-grid">
        {top_html}
      </div>
      {more_html}
    </section>
    """


def render(manifest: dict[str, Any], manifest_path: Path) -> str:
    scene_id = _esc(manifest.get("scene_id", "asset-sourcing-review"))
    premise = _esc(manifest.get("premise", ""))
    recommendation_mode = str(manifest.get("recommendation_mode", "")).strip().lower()
    trust_recommendations = recommendation_mode in TRUSTED_RECOMMENDATION_MODES
    entities = manifest.get("entities", [])
    candidates = manifest.get("candidates", [])
    entity_lookup = _entity_map(entities if isinstance(entities, list) else [])
    grouped = _group_candidates(
        candidates if isinstance(candidates, list) else [],
        trust_recommendations=trust_recommendations,
    )
    total_recommended = sum(
        1
        for entity_id in entity_lookup
        for candidate in grouped.get(entity_id, [])
        if trust_recommendations and isinstance(candidate.get("recommended_rank"), int)
    )

    sections = []
    for entity_id, entity in entity_lookup.items():
        sections.append(
            _entity_section(
                entity,
                grouped.get(entity_id, []),
                manifest_path=manifest_path,
                trust_recommendations=trust_recommendations,
            )
        )

    return f"""<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{scene_id} review</title>
  <style>
    :root {{
      --bg: #fafaf9;
      --surface: #ffffff;
      --surface-muted: #f5f5f4;
      --ink: #111827;
      --muted: #6b7280;
      --line: #d1d5db;
      --accent: #1d4ed8;
      --accent-soft: rgba(29, 78, 216, 0.08);
      --exact: #0f766e;
      --adjacent: #1d4ed8;
      --vibe: #d97706;
      --shadow: 0 10px 24px rgba(17, 24, 39, 0.06);
      --shadow-strong: 0 12px 28px rgba(17, 24, 39, 0.11);
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      color: var(--ink);
      font: 15px/1.5 "IBM Plex Sans Variable", "IBM Plex Sans", ui-sans-serif, system-ui, sans-serif;
      background: linear-gradient(180deg, #fcfcfb 0%, #f5f5f4 100%);
    }}
    .page {{
      max-width: 1440px;
      margin: 0 auto;
      padding: 12px 12px 110px;
      display: grid;
      gap: 12px;
    }}
    .panel {{
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.98);
      border-radius: 16px;
      box-shadow: var(--shadow);
    }}
    .masthead {{
      padding: 14px 16px;
    }}
    .kicker {{
      color: var(--accent);
      font: 11px/1.2 "IBM Plex Mono", ui-monospace, monospace;
      text-transform: uppercase;
      letter-spacing: 0.16em;
      margin-bottom: 8px;
    }}
    .masthead-top {{
      display: flex;
      justify-content: space-between;
      align-items: end;
      gap: 12px;
    }}
    .masthead h1 {{
      margin: 0;
      font: 650 28px/1.02 "Bricolage Grotesque Variable", "Bricolage Grotesque", "IBM Plex Sans", sans-serif;
    }}
    .masthead p {{
      margin: 6px 0 0;
      color: var(--muted);
      font-size: 13px;
      max-width: 78ch;
    }}
    .masthead-stats {{
      color: var(--muted);
      font: 11px/1.2 "IBM Plex Mono", ui-monospace, monospace;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      white-space: nowrap;
    }}
    .content {{
      display: grid;
      gap: 12px;
    }}
    .entity {{
      padding: 12px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.98);
      border-radius: 18px;
      box-shadow: var(--shadow);
    }}
    .entity-head {{
      display: flex;
      justify-content: space-between;
      align-items: baseline;
      gap: 12px;
      margin-bottom: 10px;
    }}
    .entity-role {{
      color: var(--accent);
      font: 11px/1.2 "IBM Plex Mono", ui-monospace, monospace;
      text-transform: uppercase;
      letter-spacing: 0.12em;
      margin-bottom: 4px;
    }}
    .entity h2 {{
      margin: 0;
      font: 650 22px/1.05 "Bricolage Grotesque Variable", "Bricolage Grotesque", "IBM Plex Sans", sans-serif;
    }}
    .entity-stats {{
      color: var(--muted);
      font: 11px/1.2 "IBM Plex Mono", ui-monospace, monospace;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .top-grid {{
      display: grid;
      grid-template-columns: repeat(3, minmax(240px, 1fr));
      gap: 12px;
    }}
    .option-grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
      gap: 10px;
      margin-top: 10px;
    }}
    .card {{
      border: 1px solid var(--line);
      border-radius: 16px;
      background: var(--surface);
      overflow: hidden;
      box-shadow: 0 1px 0 rgba(17, 24, 39, 0.02);
    }}
    .card.selected {{
      border-color: var(--accent);
      box-shadow: var(--shadow-strong);
      outline: 2px solid rgba(29, 78, 216, 0.24);
      outline-offset: -2px;
    }}
    .card.selected .card-body {{
      background: rgba(29, 78, 216, 0.05);
    }}
    .card-button {{
      width: 100%;
      border: 0;
      background: transparent;
      padding: 0;
      text-align: left;
      cursor: pointer;
      color: inherit;
      font: inherit;
    }}
    .image-wrap {{
      position: relative;
      aspect-ratio: 4 / 3;
      background: #e5e7eb;
      overflow: hidden;
      border-bottom: 1px solid var(--line);
    }}
    .image-wrap img {{
      width: 100%;
      height: 100%;
      object-fit: cover;
      display: block;
    }}
    .img-missing {{
      display: flex;
      align-items: center;
      justify-content: center;
      height: 100%;
      color: var(--muted);
      font-size: 13px;
    }}
    .rank-badge {{
      position: absolute;
      top: 10px;
      left: 10px;
      padding: 6px 8px;
      background: rgba(17, 24, 39, 0.9);
      color: white;
      border-radius: 999px;
      font: 10px/1 "IBM Plex Mono", ui-monospace, monospace;
      letter-spacing: 0.08em;
      text-transform: uppercase;
    }}
    .card-body {{
      padding: 0;
      background: #fbfbfa;
    }}
    .card-topline {{
      display: flex;
      justify-content: space-between;
      align-items: start;
      gap: 8px;
      padding: 9px 10px 0;
    }}
    .eyebrow {{
      color: #4b5563;
      font: 10px/1.35 "IBM Plex Mono", ui-monospace, monospace;
      text-transform: uppercase;
      letter-spacing: 0.06em;
    }}
    .fit-chip {{
      flex: 0 0 auto;
      display: inline-flex;
      align-items: center;
      padding: 4px 7px;
      border-radius: 999px;
      font: 10px/1 "IBM Plex Mono", ui-monospace, monospace;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .fit-exact {{ background: rgba(15, 118, 110, 0.10); color: var(--exact); }}
    .fit-adjacent {{ background: rgba(29, 78, 216, 0.10); color: var(--adjacent); }}
    .fit-vibe {{ background: rgba(217, 119, 6, 0.10); color: var(--vibe); }}
    .fit-miss {{ background: rgba(107, 114, 128, 0.10); color: var(--muted); }}
    .caption-block {{
      padding: 8px 10px 10px;
    }}
    .card h3 {{
      margin: 0;
      font: 650 15px/1.2 "Bricolage Grotesque Variable", "Bricolage Grotesque", "IBM Plex Sans", sans-serif;
      display: -webkit-box;
      -webkit-line-clamp: 2;
      -webkit-box-orient: vertical;
      overflow: hidden;
    }}
    .meta-line {{
      margin: 6px 0 0;
      color: #374151;
      font-size: 12px;
      font-weight: 500;
    }}
    .summary {{
      margin: 7px 0 0;
      color: #4b5563;
      font-size: 12px;
      line-height: 1.5;
    }}
    .source-link {{
      display: inline-block;
      margin: 0 10px 10px;
      color: var(--accent);
      text-decoration: none;
      font: 10px/1.2 "IBM Plex Mono", ui-monospace, monospace;
      text-transform: uppercase;
      letter-spacing: 0.08em;
    }}
    .more-options {{
      margin-top: 10px;
      border-top: 1px solid var(--line);
      padding-top: 10px;
    }}
    .more-options summary {{
      cursor: pointer;
      color: var(--accent);
      font: 11px/1.2 "IBM Plex Mono", ui-monospace, monospace;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      list-style: none;
    }}
    .more-options summary::-webkit-details-marker {{ display: none; }}
    .empty {{
      border: 1px dashed var(--line);
      background: var(--surface-muted);
      border-radius: 16px;
      min-height: 180px;
      display: flex;
      align-items: center;
      justify-content: center;
      color: var(--muted);
      text-align: center;
      padding: 20px;
    }}
    .selection-bar {{
      position: fixed;
      left: 12px;
      right: 12px;
      bottom: 12px;
      z-index: 20;
      display: grid;
      gap: 10px;
      padding: 12px;
      border: 1px solid var(--line);
      background: rgba(255, 255, 255, 0.98);
      border-radius: 16px;
      box-shadow: 0 18px 40px rgba(17, 24, 39, 0.16);
    }}
    .selection-bar.is-collapsed {{
      gap: 0;
    }}
    .selection-top {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
    }}
    .selection-status {{
      font: 11px/1.2 "IBM Plex Mono", ui-monospace, monospace;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--muted);
    }}
    .selection-actions {{
      display: flex;
      gap: 8px;
      flex-wrap: wrap;
    }}
    .selection-actions button {{
      border: 1px solid var(--line);
      background: var(--surface);
      color: var(--ink);
      padding: 8px 10px;
      border-radius: 12px;
      font: 11px/1.2 "IBM Plex Mono", ui-monospace, monospace;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      cursor: pointer;
    }}
    .selection-actions button.primary {{
      background: var(--accent);
      color: white;
      border-color: var(--accent);
    }}
    .selection-actions button.secondary {{
      background: var(--accent-soft);
      color: var(--accent);
      border-color: rgba(29, 78, 216, 0.18);
    }}
    .selection-body {{
      display: none;
    }}
    .selection-bar.is-open .selection-body {{
      display: block;
    }}
    .selection-output {{
      width: 100%;
      min-height: 92px;
      border: 1px solid var(--line);
      border-radius: 12px;
      background: var(--surface-muted);
      padding: 10px;
      font: 12px/1.5 "IBM Plex Mono", ui-monospace, monospace;
      color: var(--ink);
      resize: vertical;
    }}
    @media (max-width: 1100px) {{
      .top-grid {{
        grid-template-columns: repeat(2, minmax(0, 1fr));
      }}
    }}
    @media (max-width: 760px) {{
      .page {{
        padding-left: 10px;
        padding-right: 10px;
      }}
      .masthead-top, .entity-head, .selection-top {{
        flex-direction: column;
        align-items: start;
      }}
      .top-grid, .option-grid {{
        grid-template-columns: 1fr;
      }}
      .selection-bar {{
        left: 10px;
        right: 10px;
        bottom: 10px;
      }}
    }}
  </style>
</head>
<body>
  <div class="page">
    <section class="panel masthead">
      <div class="kicker">WorldSeed Asset Review</div>
      <div class="masthead-top">
        <div>
          <h1>{scene_id}</h1>
          <p>{premise}</p>
          <p>{"Top badges come only from visual review." if trust_recommendations else "No automatic top picks are shown. Review the images and select manually."}</p>
        </div>
        <div class="masthead-stats">{len(entity_lookup)} entities · {total_recommended} trusted picks</div>
      </div>
    </section>
    <main class="content">
      {''.join(sections)}
    </main>
  </div>

  <section class="selection-bar is-collapsed" id="selection-bar" aria-live="polite">
    <div class="selection-top">
      <div class="selection-status"><span id="selection-count">0</span> / {len(entity_lookup)} selected</div>
      <div class="selection-actions">
        <button class="primary" type="button" id="copy-picks">Copy picks</button>
        <button class="secondary" type="button" id="toggle-picks">Show picks</button>
        <button type="button" id="download-picks">Download picks.json</button>
        <button type="button" id="clear-picks">Clear</button>
      </div>
    </div>
    <div class="selection-body" id="selection-body">
      <textarea id="selection-output" class="selection-output" spellcheck="false" placeholder="Choose cards, then copy or download your picks."></textarea>
    </div>
  </section>

  <script>
    const cards = Array.from(document.querySelectorAll('.card'));
    const bar = document.getElementById('selection-bar');
    const output = document.getElementById('selection-output');
    const countEl = document.getElementById('selection-count');
    const toggleButton = document.getElementById('toggle-picks');
    const copyButton = document.getElementById('copy-picks');
    const downloadButton = document.getElementById('download-picks');
    const clearButton = document.getElementById('clear-picks');
    const selections = new Map();

    function renderSelections() {{
      const result = {{}};
      selections.forEach((value, key) => {{
        result[key] = value;
      }});
      const json = JSON.stringify(result, null, 2);
      output.value = json === '{{}}' ? '' : json;
      countEl.textContent = String(selections.size);
    }}

    function setExpanded(expanded) {{
      bar.classList.toggle('is-open', expanded);
      bar.classList.toggle('is-collapsed', !expanded);
      toggleButton.textContent = expanded ? 'Hide picks' : 'Show picks';
    }}

    function selectCard(card) {{
      const entityId = card.dataset.entityId;
      const payload = JSON.parse(card.dataset.payload || '{{}}');
      document.querySelectorAll(`.card[data-entity-id="${{CSS.escape(entityId)}}"]`).forEach((node) => {{
        node.classList.remove('selected');
      }});
      card.classList.add('selected');
      selections.set(entityId, payload);
      renderSelections();
    }}

    cards.forEach((card) => {{
      const button = card.querySelector('.card-button');
      if (button) {{
        button.addEventListener('click', () => selectCard(card));
      }}
    }});

    toggleButton.addEventListener('click', () => {{
      setExpanded(!bar.classList.contains('is-open'));
    }});

    copyButton.addEventListener('click', async () => {{
      renderSelections();
      if (!output.value) return;
      try {{
        await navigator.clipboard.writeText(output.value);
        copyButton.textContent = 'Copied';
        window.setTimeout(() => {{
          copyButton.textContent = 'Copy picks';
        }}, 1200);
      }} catch (_err) {{
        output.focus();
        output.select();
      }}
    }});

    downloadButton.addEventListener('click', () => {{
      renderSelections();
      const blob = new Blob([output.value || '{{}}'], {{ type: 'application/json' }});
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'picks.json';
      document.body.appendChild(link);
      link.click();
      link.remove();
      URL.revokeObjectURL(url);
    }});

    clearButton.addEventListener('click', () => {{
      selections.clear();
      cards.forEach((card) => card.classList.remove('selected'));
      renderSelections();
    }});

    setExpanded(false);
    renderSelections();
  </script>
</body>
</html>
"""


def main() -> int:
    if len(sys.argv) != 3:
        print("Usage: render_review.py <manifest.json> <output.html>", file=sys.stderr)
        return 2

    manifest_path = Path(sys.argv[1]).resolve()
    output_path = Path(sys.argv[2]).resolve()
    manifest = _load_manifest(manifest_path)
    html_text = render(manifest, manifest_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(html_text, encoding="utf-8")
    print(f"wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
