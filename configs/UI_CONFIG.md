---

# UI Config Reference

> A `.ui.json` file defines how a world looks. The scene config (`.yaml`) defines what exists and how it behaves; the UI config defines how each entity type renders on the dashboard map view.

## Overview

Every scene can have an optional `{scene_id}.ui.json` file. Without one, degraded mode applies: agents render as avatars, everything else as cards. Production scenes MUST have a `.ui.json`.

Location: `frontend/public/configs/{scene_id}.ui.json`

The UI config system mirrors the engine's zero-hardcode principle: it never assumes entity types are called "space" or properties are called "location". Instead, it uses rules to **bind** arbitrary property names to visual slots.

**Scaffold template:** `configs/UI_SCAFFOLD.jsonc` — annotated template showing all capabilities. Copy it to start a new config.

**Fragments library:** `frontend/src/lib/ui-fragments.ts` — copy-paste building blocks with JSDoc.

## Hardcode Boundary

The UI config system hardcodes visual vocabulary but never hardcodes domain concepts.

| OK to hardcode in code | NOT OK to hardcode |
|---|---|
| Scene types: zone, deck, card, gauge, avatar, hidden, fallback | Entity type names: space, resource, equipment, etc. |
| Bind keys: label, locate_by, connections, show, bar, bar_max, state_effects | Property names: location, connects_to, quantity, condition |
| Roles: container, agent, item, free, hidden | Action names |
| Event effects: shake, flash-red, flash-green, glow, pulse | |
| State presets: active, damaged, destroyed, locked, disabled, highlighted, warning | |

## File Format

```json
{
  "asset_pack": "bunker",
  "event_defaults": { "bubble": "action" },
  "rules": [ ... ],
  "events": [ ... ],
  "layout": { ... }
}
```

### `event_defaults`

Optional. Fallback `bubble` and/or `effect` applied when an event type matches no rule in `events[]`. Without this, unmatched events produce no bubble or animation.

```json
"event_defaults": { "bubble": "action" }
```

With this set, you only need to explicitly list events that are `"speech"` type or have a special `effect`. All other events automatically get an action bubble.

### Inline Rules

All rules and events in `.ui.json` files are inline JSON objects. There are no string references or runtime preset expansion.

**Fragments catalog:** `frontend/src/lib/ui-fragments.ts` contains copy-paste building blocks with JSDoc. Pick a fragment, copy it into your `.ui.json`, change `match.type` and property names to fit your scene.

**Ordering:** First match wins. Place specific overrides (id match) **before** general rules (type match) in the array.

### `asset_pack`

String. References a subdirectory under `frontend/public/assets/scenes/`:

```
frontend/public/assets/scenes/{asset_pack}/
  agents/{agent_id}.png      — Agent portraits (circular crop)
  entities/{entity_id}.png   — Zone background images + entity item images
```

Entity items (card/gauge scene types) also load from `entities/{entity_id}.png`. If the image exists, it renders as a 40×40 thumbnail on the entity card. If it fails to load, the entity name is displayed as fallback text.

Empty string or omitted → no images → fallback rendering only.

### `rules[]`

Ordered list of match → scene type + property bindings. **First matching rule wins**, so put specific rules (id match) before general rules (type match).

```json
{
  "match": { "type": "space" },
  "scene": "zone",
  "bind": {
    "label": "id",
    "connections": "connects_to"
  }
}
```

**`match`** — how to find entities:
- `{"type": "space"}` — all entities where `type == "space"`
- `{"id": "entrance"}` — the entity with `id == "entrance"`
- `{"id": "X", "type": "Y"}` — both must match (AND)

**`scene`** — which scene type to use (see Scene Types below).

**`bind`** — maps UI slots to your config's property names. This is the key mechanism: the UI never hardcodes property names. Instead, bind tells it "the property called X in this config means Y to the renderer."

| Bind Key | Meaning | Example |
|----------|---------|---------|
| `label` | Property to display as the entity's name. On zones, shows as the zone title. On cards/gauges, shows instead of the entity ID. Falls back to entity ID if the property is null. | `"label": "designation"` |
| `locate_by` | Property that holds the container zone ID. The entity's property value must be a valid zone ID. | `"locate_by": "sector"` → reads `entity.sector` to place inside that zone |
| `connections` | Property that holds connected zone IDs (array). Draws dashed lines between zones. | `"connections": "warp_gate"` |
| `show` | Priority list of property names. Displays **first non-null value only**, not all. Works on cards, gauges, agents, and zones (as subtitle below label). On cards/gauges, suppressed when `bar` is present (bar takes visual priority). On zones, both `show` and `bar` can display simultaneously. | `"show": ["oxygen_level", "gravity"]` → shows oxygen if set, else gravity |
| `bar` | Property to render as a progress bar. Works on card, gauge, and zone scene types. | `"bar": "integrity"` |
| `bar_max` | Maximum value for the bar (default: 100) | `"bar_max": 100` |
| `state_effects` | Map of property conditions to visual CSS presets. **Entity cards only** — not applied to agent avatars. Supports `=`, `<`, `>` operators. | See State Effects below |

#### `state_effects`

Maps entity property conditions to visual CSS filter presets. When an entity's property matches a condition, the corresponding CSS class is applied to its card on the map.

```json
"state_effects": {
  "status=destroyed": "destroyed",
  "status=active":    "active",
  "condition<20":     "damaged"
}
```

**Condition formats:**
- `prop=value` — string equality (e.g. `"status=destroyed"`)
- `prop<N` — numeric less-than (e.g. `"condition<20"`)
- `prop>N` — numeric greater-than

**Available presets:**

| Preset | Visual Effect |
|--------|--------------|
| `active` | Brighter, more saturated, subtle glow |
| `damaged` | Desaturated, darkened, warm inset shadow |
| `destroyed` | Grayscale, faded, slightly tilted |
| `locked` | Dimmed, reduced opacity |
| `disabled` | Faint grayscale, very low opacity |
| `highlighted` / `highlight` | Blue accent glow ring |
| `warning` | Warm amber ring, slight desaturation |

First matching condition wins. Presets are generic visual vocabulary — not domain-specific. **Entity cards only** — agent avatars do not render state effects.

### `events[]`

Maps event type names (from scene config actions) to visual bubble styles and optional one-shot animations on entity cards.

```json
{ "match": "say",     "bubble": "speech" }
{ "match": "attempt", "bubble": "action", "effect": "glow" }
{ "match": "destroy", "bubble": "action", "effect": "shake" }
```

**`effect`** (optional) — triggers a one-shot CSS animation on the event's target entity card. Available effects:

| Effect | Animation |
|--------|-----------|
| `shake` | Horizontal shake (0.4s) |
| `flash-red` | Red ring flash outward (0.5s) |
| `flash-green` | Green ring flash outward (0.5s) |
| `glow` | Soft ambient glow pulse (0.6s) |
| `pulse` | Opacity pulse (0.6s) |

### `layout`

Manual pixel positions for container zones. The canvas is a fixed 4000×3000px surface; the camera auto-centers and zooms to fit content on load. Most configs use coordinates in the 0-800 range. Without layout, zones auto-position using a deterministic hash.

```json
{
  "大堂":      { "x": 180, "y": 210, "w": 340, "h": 320 },
  "甲号包间":  { "x": 15,  "y": 100, "w": 220, "h": 220 }
}
```

| Key | Type | Required | Description |
|-----|------|----------|-------------|
| `x`, `y` | number | yes | Top-left corner position (px) |
| `w`, `h` | number | yes | Width and height (px) |
| `rotation` | number | no | Tilt in degrees. ±0.5 to ±2 looks natural. Default: hash-based (~±1.5). **Always set this** — 0 looks rigid. |
| `z` | number | no | Stacking order override. Higher = on top. Default: derived from position (right-lower zones stack on top of upper-left ones). |

**Layout guidelines:**

- **Overlap is OK.** Zones are collage cards — 10-20% overlap between adjacent zones looks natural. Hover lifts a zone to the top. Each zone's label is at top-center and stays visible when partially covered.
- **Group related zones.** Place connected zones near each other (connection lines are drawn between them). Leave wider gaps between unrelated clusters.
- **Vary sizes.** One large focal zone (300-400px wide), a few medium (200-280px), and smaller supporting zones. Uniform sizes look like a grid, not a collage.
- **Stagger, don't align.** Offset zones vertically — avoid placing them on the same y coordinate. Slight diagonal arrangements feel more organic.
- **Leave breathing room.** Don't fill the entire canvas. 30-50% empty space makes the layout feel curated, not cluttered.
- **Stacking order** is automatic: zones lower-right on the canvas stack on top of upper-left ones. Use `z` to override when needed.

## Scene Types

Built-in registry. Each scene type has a **role** (how it's categorized) and a **CSS class** (how it renders).

| Scene Type | Role | Renders As | Use For |
|-----------|------|------------|---------|
| `zone` | container | Large card with background image, scrim gradient, label | Rooms, areas, regions |
| `deck` | container | Same as zone | Ship decks, floors (alias for zone with different naming) |
| `card` | item | Paper cutout card with asset image (or name fallback) + label + values | Items, props, resources |
| `gauge` | item | Same as card + progress bar from `bind.bar` | Items with a numeric health/condition value |
| `avatar` | agent | Circular portrait dot with name label below | Agents |
| `hidden` | hidden | Not rendered | Internal state (timers, phase trackers, game state) |
| `fallback` | free | Plain badge with entity ID | Unmatched entities |

### Roles

- **container** — Rendered as a zone on the map canvas. Other entities and agents are placed *inside* it based on their `locate_by` binding.
- **item** — Small card placed inside its container zone (resolved via `bind.locate_by`).
- **agent** — Circular dot placed inside its container zone (resolved via `bind.locate_by`).
- **hidden** — Skipped entirely during map rendering. Entity exists in world state but has no visual presence.
- **free** — No container. Placed below the map zones in a flat row.

### Adding a New Scene Type

When the built-in 7 types don't cover your needs (e.g. you want a `timeline`, `network-node`, `meter`), add a new one:

**1.** Register in `frontend/src/lib/ui-config.ts` — add to `SCENE_TYPES`:

```typescript
export const SCENE_TYPES: Record<string, SceneType> = {
  // ... existing types ...
  timeline: { role: 'item', css: 'timeline-card', assetDir: 'entities' },
}
```

**2.** Add CSS in `frontend/src/styles/worldview.css`:

```css
.timeline-card {
  /* your rendering styles */
}
```

**3.** Add rendering logic in `frontend/src/components/map/ZoneCard.tsx` — handle the new scene type, reading bound properties via `uiConfig.getBind(entity)`.

The rule matching and bind system work automatically for any registered scene type. No other code changes needed.

## Examples

### Spatial scene (bunker)

Entities have `type: "space"`, use `location` for placement, `connects_to` for connections:

```json
{
  "asset_pack": "bunker",
  "rules": [
    { "match": {"type": "space"},     "scene": "zone",   "bind": {"label": "id", "connections": "connects_to"} },
    { "match": {"type": "resource"},  "scene": "card",   "bind": {"locate_by": "location", "show": ["quantity"]} },
    { "match": {"type": "equipment"}, "scene": "gauge",  "bind": {"locate_by": "location", "bar": "condition", "bar_max": 100, "state_effects": {"status=destroyed": "destroyed", "condition<20": "damaged"}} },
    { "match": {"type": "agent"},     "scene": "avatar", "bind": {"locate_by": "location"} }
  ],
  "layout": {
    "storage_room": { "x": 30, "y": 60, "w": 310, "h": 280 },
    "hallway":      { "x": 300, "y": 40, "w": 320, "h": 210 }
  }
}
```

### Spatial scene with different property names (starship)

Same visual structure, completely different property names — `deck` instead of `space`, `sector` instead of `location`, `warp_gate` instead of `connects_to`. **Zero code changes:**

```json
{
  "rules": [
    { "match": {"type": "deck"},       "scene": "deck",   "bind": {"label": "designation", "connections": "warp_gate", "show": ["oxygen_level"]} },
    { "match": {"type": "equipment"},  "scene": "gauge",  "bind": {"locate_by": "installed_in", "bar": "integrity", "bar_max": 100} },
    { "match": {"type": "agent"},      "scene": "avatar", "bind": {"locate_by": "sector"} }
  ]
}
```

### Non-spatial scene (forum)

Boards are zones (containers), threads locate into boards. No `connections` — boards are independent categories, not linked spaces. Agents have no location (they see everything):

```json
{
  "rules": [
    { "match": {"type": "board"},  "scene": "zone",   "bind": {"label": "topic"} },
    { "match": {"type": "thread"}, "scene": "card",   "bind": {"locate_by": "board", "show": ["author", "reply_count", "score"]} },
    { "match": {"type": "agent"},  "scene": "avatar" }
  ],
  "layout": {
    "general_board":   { "x": 60,  "y": 80,  "w": 320, "h": 300 },
    "off_topic_board": { "x": 340, "y": 140, "w": 280, "h": 260 }
  }
}
```

Boards as zones means threads appear *inside* their parent board on the map. No `connections` and no agent `locate` — zones don't require either.

## Fallback Behavior

| Condition | Result |
|-----------|--------|
| No `.ui.json` file exists | Degraded mode: agents → avatar (with `locate_by: "location"`), everything else → card. Events default to action bubble. Production scenes MUST have .ui.json. |
| Entity matches no rule | Uses `fallback` scene type (gray badge below map) |
| `asset_pack` is empty | No images, zones show solid background color |
| Entity item image missing or fails to load | Entity name displayed as fallback text (serif font) |
| Zone/agent image missing or fails to load | `<img>` hidden, underlying color/circle visible |
| No `layout` entry for a zone | Auto-positioned using deterministic hash (stable across reloads) |

## Key Source Files

| File | Purpose |
|------|---------|
| `frontend/src/lib/ui-config.ts` | Config loader, rule matcher, scene type registry, asset URL builders |
| `frontend/src/lib/ui-fragments.ts` | Copy-paste building blocks for .ui.json (not imported at runtime) |
| `frontend/src/lib/state-effects.ts` | Shared state_effects condition parser (=, <, > operators) |
| `frontend/src/lib/map-layout.ts` | Entity categorization, collage positioning, connection lines |
| `frontend/src/components/map/MapView.tsx` | Map canvas — zones, entities, agents, event animations |
| `frontend/src/components/map/ZoneCard.tsx` | Zone rendering — entity cards, agent row, gauge bars, state effects |
| `frontend/src/components/map/EntityCard.tsx` | Entity card rendering — image, gauge bar, state effects, values |
| `frontend/src/components/map/AgentRow.tsx` | Agent avatar rendering — portrait, state effects |
| `frontend/src/styles/worldview.css` | Zone card, entity card, agent dot, connection line CSS |
| `frontend/src/lib/detail-panel.ts` | Property extraction for detail view |
| `src/worldseed/scene/checks/ui_consistency.py` | UI validation checks (U001-U008) |

## Extension Checklist

When adding a new scene type, bind key, or state effect preset, update ALL of these:

| Change | Files to update |
|--------|----------------|
| New scene type | `ui-config.ts` SCENE_TYPES, `ui_consistency.py` VALID_SCENE_TYPES, `ui-fragments.ts` (add fragment), `UI_CONFIG.md` Scene Types table, `UI_SCAFFOLD.jsonc` |
| New bind key | `EntityCard.tsx` / `ZoneCard.tsx` / `AgentRow.tsx` (consume it), `ui_consistency.py` VALID_BIND_KEYS, `ui-fragments.ts` (use in fragments), `UI_CONFIG.md` bind key table |
| New state effect preset | `worldview.css` (CSS class), `UI_CONFIG.md` state_effects table, `UI_SCAFFOLD.jsonc` |
| New event effect | `worldview.css` (CSS animation), `ui-fragments.ts` (use in event fragments), `UI_CONFIG.md` effects table |

Run `npx vitest run src/lib/__tests__/ui-fragments.test.ts` after changes — it validates fragments against SCENE_TYPES and bind keys.
