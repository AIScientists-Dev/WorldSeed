# UI Config Guide

How to decide what goes in a `.ui.json` file. For exact syntax and bind key definitions, read `configs/UI_CONFIG.md`. For copy-paste building blocks, read `frontend/src/lib/ui-fragments.ts`.

## The One Rule

**Every entity type in your scene config must have a matching rule in the UI config. Unmatched entities render as gray fallback badges below the map.**

Without a `.ui.json` file, degraded mode applies: agents → avatar, everything else → card. Production scenes MUST have a `.ui.json`.

## Writing Path

1. Read this guide (decision tree)
2. Read `frontend/src/lib/ui-fragments.ts` (copy-paste fragments with JSDoc)
3. Copy fragments into your `.ui.json`, change `match.type` and property names
4. Run `worldseed validate` to catch mismatches

## Rendering Pipeline

```
entity → match against rules[] (first match wins)
  matched:
    scene: zone/deck    → role: container (large card, other entities placed inside)
    scene: card/gauge   → role: item (small card, needs bind.locate_by to go inside a zone)
    scene: avatar       → role: agent (circular dot, needs bind.locate_by)
    scene: hidden       → not rendered
  unmatched:
    → fallback (gray badge below map)
```

**`bind.locate_by` is a property NAME, not a zone ID** — `"locate_by": "location"` means "read this entity's `location` property to find which zone to place it in." The entity must actually have that property set to a valid zone ID.

An item/agent without `bind.locate_by`, or whose locate resolves to no container, becomes free (placed below the map).

## Deciding Scene Type Per Entity

Ask these questions in order:

1. **Do other entities reference this entity as a location?** (agents have `location: this_entity`, items have location pointing here) → **zone** (container)
2. **Does this entity have `connects_to` and represent a place?** → **zone**
3. **Is this internal state the observer doesn't need to see on the map?** (timers, phase trackers, internal counters, round state) → **hidden**. The stream panel already shows tick progression — duplicating timers on the map is noise.
4. **Does the observer need to see this entity's values at a glance?** (vote tallies, scores, rule statuses, building warnings) → **card** with `show` bindings. Give it `bind.locate_by` pointing to a zone to place it inside, or omit locate to let it float free.
5. **Does this entity have a depletable numeric value?** (health, condition, integrity) → **gauge** (card + progress bar)
6. **Is this an agent?** → **avatar** with `bind.locate_by`

## Deciding What to Show

`bind.show` is a **priority list** — the renderer displays the **first non-null value** from the array, NOT all values. Pick the 1-2 most important properties.

- Don't show everything. If an agent has 10 properties, showing all of them is unreadable
- Properties already visible through other means (location shown by position, type shown by scene type) don't need `show`
- `bind.label` works on zones (zone title) and cards/gauges (replaces entity ID as display name). Falls back to entity ID if null
- `bind.bar`/`bind.bar_max` work on card, gauge, and zone scene types

## State Effects

Use `state_effects` when an entity has discrete states the observer should see visually:

```json
"state_effects": {
  "eliminated=true": "destroyed",
  "status=active": "active",
  "status=repealed": "disabled",
  "condition<20": "damaged"
}
```

Supported operators: `prop=value` (string equality), `prop<N` (numeric less-than), `prop>N` (numeric greater-than). First match wins.

Available presets: `active`, `damaged`, `destroyed`, `locked`, `disabled`, `highlighted`, `warning`.

Use state_effects for meaningful state changes. Don't add state_effects for properties that change continuously (scores, counters) — those are better as `show` values.

**Entity cards only.** State effects are applied to entity cards (card, gauge scene types) via CSS classes. They are NOT applied to agent avatars — agent dots are too small for visual state effects. Do not put `state_effects` in agent rules.

## Events

Events control speech bubbles and one-shot animations on entity cards.

**Principle:** Dialogue-type events → `speech` bubble. Action-type events → `action` bubble. Pivotal moments → add an `effect`.

```json
"events": [
  {"match": "accuse", "bubble": "action", "effect": "flash-red"},
  {"match": "victory", "bubble": "action", "effect": "flash-green"},
  {"match": "talk", "bubble": "speech"},
  {"match": "observe", "bubble": "action"}
]
```

Specific overrides go BEFORE general events (first match wins).

**`event_defaults` is effectively mandatory.** Set `"event_defaults": {"bubble": "action"}` so unmatched events get an action bubble — then you only need to explicitly list speech-type events and events with special effects.

Available effects: `shake`, `flash-red`, `flash-green`, `glow`, `pulse`.

**Guideline:** Effects on highlight actions (the ones with `highlight: true` in scene config) should be visually distinct — `flash-red` for irreversible/high-stakes, `flash-green` for resolutions/victories, `glow` for commitments.

## Layout

Manual zone positions. Canvas auto-sizes (min 1000x800, expands to fit). Most configs use coordinates in the 0-800 range. Zones without layout auto-position via hash.

```json
"layout": {
  "zone_id": {"x": 180, "y": 210, "w": 340, "h": 320, "rotation": -1.5}
}
```

**Collage principles:**
- Overlap 10-20% between adjacent zones
- Vary sizes — one large focal zone, smaller supporting zones
- Stagger positions — don't align to grid
- rotation ±0.5 to ±2 (0 looks rigid)
- Leave 30-50% empty space

**Single-zone scenes** (jury room, meeting room, negotiation table): one large zone centered, all agents and cards inside it. The zone is a visual container, not a spatial mechanic.

**Multi-zone scenes** (apartment, office building, territories): position zones to reflect spatial relationships. Connected zones should be near each other.

## Fragments Catalog

`frontend/src/lib/ui-fragments.ts` contains named building blocks organized by visual role:

| Fragment | Scene | Use For |
|----------|-------|---------|
| `FRAG_ZONE_CONTAINER` | zone | Rooms, areas with connections |
| `FRAG_ZONE_WITH_SHOW` | zone | Territories, boards (no connections) |
| `FRAG_LOCATED_AVATAR` | avatar | Agents that move between zones |
| `FRAG_GLOBAL_AVATAR` | avatar | Agents in non-spatial scenes |
| `FRAG_LOCATED_CARD` | card | Items placed in a zone |
| `FRAG_LOCATED_CARD_WITH_QUANTITY` | card | Resources with quantity |
| `FRAG_FREE_CARD` | card | Abstract items (no zone) |
| `FRAG_GAUGE_WITH_BAR` | gauge | Equipment with depletable value |
| `FRAG_HIDDEN` | hidden | Internal state |

Event fragments: `FRAG_EVT_DIALOGUE`, `FRAG_EVT_ACTIONS`, `FRAG_EVT_ALERTS`, `FRAG_EVT_COMBAT`, `FRAG_EVT_SOCIAL`, `FRAG_EVT_TRADE`, `FRAG_EVT_LIFECYCLE`.

## Common Mistakes

1. **Forgetting custom entity types.** You add `type: rule` or `type: territory` to the scene config but don't add a matching UI rule. They render as gray badges. `worldseed validate` catches this (U001).

2. **Not hiding internal trackers.** Timer entities, game phase trackers, accusation records — if the observer doesn't need to see them on the map, hide them. The stream panel shows everything.

3. **Missing locate_by on items.** A card without `bind.locate_by` has no zone to go into. It renders as a free entity below the map. If you want it inside a zone, set locate_by to the property name holding the zone ID.

4. **No event_defaults.** Without `event_defaults: {"bubble": "action"}`, events that don't match any event rule produce no bubble at all — actions happen silently on the map.

5. **Confusing locate_by value.** `"locate_by": "location"` means "read the `location` property" — NOT "place in the zone called location." The entity must have `location: some_zone_id` in its properties.

6. **Items carried by agents disappear from map.** When an agent picks up an item (sets `holder` but the item's `location` becomes null or changes), the item's `locate_by` can't resolve to a zone, so it drops to the free row below the map. This is expected — carried items are tracked in the agent's properties, not on the map.

7. **state_effects referencing non-existent properties.** Every property name in state_effects conditions (e.g., `"health<30"`) must exist on the matched entities — either defined in the YAML entity properties, in the agent template, or set by effects/consequences during gameplay. If the property never exists, the condition never triggers and the visual effect is dead. Check your YAML before adding state_effects.

8. **Sanity check `expect` values.** Only two values are valid: `success` and `fail`. Not "failure", not "error" — literally `success` or `fail`.
