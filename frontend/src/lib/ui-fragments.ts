/* WorldSeed — UI Config Fragments: copy-paste building blocks for .ui.json files.
 *
 * NOT imported by runtime code. This file is a reference catalog for AI and humans
 * writing .ui.json configs. Each fragment is a valid UIRule or UIEventStyle[] with
 * JSDoc explaining when to use it and what properties it assumes.
 *
 * Fragments are named by VISUAL ROLE, not entity type. "FRAG_ZONE_CONTAINER" means
 * "renders as a zone container" — change match.type to whatever your scene calls its
 * spatial entities (space, room, deck, territory, etc.).
 *
 * Usage path: read this file → pick fragments → copy into .ui.json → change match.type
 * and property names to fit your scene config.
 */

import type { UIRule, UIEventStyle } from './ui-config'

// ── Container fragments (zone/deck) ──────────────────────

/** Zone container with label and connection lines.
 *  Use for: rooms, areas, regions, decks — any entity that other entities locate INTO.
 *  Assumes: entity has `connects_to` array prop for zone connections.
 *  Change: match.type to your zone type, bind.connections to your connection prop name. */
export const FRAG_ZONE_CONTAINER: UIRule = {
  match: { type: 'space' },
  scene: 'zone',
  bind: { label: 'id', connections: 'connects_to' },
}

/** Zone container with show values (no connections).
 *  Use for: territories, boards, categories — containers that don't connect to each other.
 *  Change: match.type, bind.show to properties worth displaying. */
export const FRAG_ZONE_WITH_SHOW: UIRule = {
  match: { type: 'territory' },
  scene: 'zone',
  bind: { label: 'id', show: ['controlled_by'] },
}

// ── Agent fragments (avatar) ─────────────────────────────

/** Agent avatar placed inside a zone via locate_by.
 *  Use for: agents that move between zones. Most common agent fragment.
 *  Assumes: agent has `location` prop holding the zone ID they're in.
 *  Change: bind.locate_by to your scene's location property name. */
export const FRAG_LOCATED_AVATAR: UIRule = {
  match: { type: 'agent' },
  scene: 'avatar',
  bind: { locate_by: 'location' },
}

/** Agent avatar without zone placement (free-floating).
 *  Use for: agents in non-spatial scenes (forums, debates) where there are no zones,
 *  or agents who see everything and don't have a location. */
export const FRAG_GLOBAL_AVATAR: UIRule = {
  match: { type: 'agent' },
  scene: 'avatar',
}

// ── Item fragments (card) ────────────────────────────────

/** Card placed inside a zone.
 *  Use for: items, props, documents — anything small placed in a location.
 *  Assumes: entity has `location` prop holding zone ID.
 *  Change: bind.locate_by to your location prop, optionally add bind.show. */
export const FRAG_LOCATED_CARD: UIRule = {
  match: { type: 'item' },
  scene: 'card',
  bind: { locate_by: 'location' },
}

/** Card with quantity display.
 *  Use for: resources, supplies, stocks — items with a numeric amount.
 *  bind.label replaces entity ID as display name (e.g., show company name instead of stock_tsmc).
 *  Change: bind.show to the property names you want visible, bind.label to a display property. */
export const FRAG_LOCATED_CARD_WITH_QUANTITY: UIRule = {
  match: { type: 'resource' },
  scene: 'card',
  bind: { locate_by: 'location', show: ['quantity'], label: 'name' },
}

/** Card with multiple show values (no locate — free-floating).
 *  Use for: concepts, proposals, threads — abstract items not placed in a zone.
 *  Change: bind.show to relevant property names. */
export const FRAG_FREE_CARD: UIRule = {
  match: { type: 'concept' },
  scene: 'card',
  bind: { show: ['status', 'proposed_by'] },
}

// ── Gauge fragments (card + progress bar) ────────────────

/** Gauge card with progress bar and state effects.
 *  Use for: equipment, mechanisms, structures — entities with a depletable numeric value.
 *  Assumes: entity has `condition` (or similar) numeric prop and `status` string prop.
 *  Change: bind.bar to your numeric prop, bind.bar_max if not 100,
 *  state_effects conditions to your prop names. */
export const FRAG_GAUGE_WITH_BAR: UIRule = {
  match: { type: 'equipment' },
  scene: 'gauge',
  bind: {
    locate_by: 'location',
    bar: 'condition',
    bar_max: 100,
    show: ['status'],
    state_effects: {
      'status=destroyed': 'destroyed',
      'status=active': 'active',
      'condition<20': 'damaged',
    },
  },
}

// ── Hidden fragments ─────────────────────────────────────

/** Hidden entity — exists in world state but not rendered on map.
 *  Use for: game_state, timers, phase trackers, internal counters.
 *  The stream panel already shows tick progression — no need to duplicate. */
export const FRAG_HIDDEN: UIRule = {
  match: { type: 'game_state' },
  scene: 'hidden',
}

// ── Event fragments ──────────────────────────────────────

/** Dialogue events — spoken communication.
 *  Covers: talk, say, shout, whisper, announce, directed_talk. */
export const FRAG_EVT_DIALOGUE: UIEventStyle[] = [
  { match: 'talk', bubble: 'speech' },
  { match: 'say', bubble: 'speech' },
  { match: 'shout', bubble: 'speech', effect: 'pulse' },
  { match: 'whisper', bubble: 'speech' },
  { match: 'announce', bubble: 'speech' },
  { match: 'directed_talk', bubble: 'speech' },
]

/** Action events — physical actions.
 *  Covers: attempt, observe, move, search. */
export const FRAG_EVT_ACTIONS: UIEventStyle[] = [
  { match: 'attempt', bubble: 'action', effect: 'glow' },
  { match: 'observe', bubble: 'action' },
  { match: 'move', bubble: 'action' },
  { match: 'search', bubble: 'action', effect: 'shake' },
]

/** Alert events — alarms and warnings.
 *  Covers: alarm, catastrophe, warning. */
export const FRAG_EVT_ALERTS: UIEventStyle[] = [
  { match: 'alarm', bubble: 'action', effect: 'flash-red' },
  { match: 'catastrophe', bubble: 'action', effect: 'flash-red' },
  { match: 'warning', bubble: 'action', effect: 'pulse' },
]

/** Combat events.
 *  Covers: attack, defend, dodge, block, kill, heal, damage. */
export const FRAG_EVT_COMBAT: UIEventStyle[] = [
  { match: 'attack', bubble: 'action', effect: 'shake' },
  { match: 'defend', bubble: 'action' },
  { match: 'dodge', bubble: 'action', effect: 'glow' },
  { match: 'block', bubble: 'action' },
  { match: 'kill', bubble: 'action', effect: 'flash-red' },
  { match: 'heal', bubble: 'action', effect: 'flash-green' },
  { match: 'damage', bubble: 'action', effect: 'flash-red' },
]

/** Social events.
 *  Covers: accuse, confront, persuade, greet, threaten, compliment. */
export const FRAG_EVT_SOCIAL: UIEventStyle[] = [
  { match: 'accuse', bubble: 'action', effect: 'flash-red' },
  { match: 'confront', bubble: 'action', effect: 'shake' },
  { match: 'persuade', bubble: 'action', effect: 'glow' },
  { match: 'greet', bubble: 'speech' },
  { match: 'threaten', bubble: 'speech', effect: 'pulse' },
  { match: 'compliment', bubble: 'speech', effect: 'glow' },
]

/** Trade events.
 *  Covers: buy, sell, trade, give, take, steal. */
export const FRAG_EVT_TRADE: UIEventStyle[] = [
  { match: 'buy', bubble: 'action', effect: 'glow' },
  { match: 'sell', bubble: 'action' },
  { match: 'trade', bubble: 'action', effect: 'glow' },
  { match: 'give', bubble: 'action' },
  { match: 'take', bubble: 'action' },
  { match: 'steal', bubble: 'action', effect: 'shake' },
]

/** Lifecycle events — entity creation/destruction.
 *  Covers: spawn, eliminate, transform, expire, die. */
export const FRAG_EVT_LIFECYCLE: UIEventStyle[] = [
  { match: 'spawn', bubble: 'action', effect: 'flash-green' },
  { match: 'eliminate', bubble: 'action', effect: 'flash-red' },
  { match: 'transform', bubble: 'action', effect: 'glow' },
  { match: 'expire', bubble: 'action', effect: 'pulse' },
  { match: 'die', bubble: 'action', effect: 'flash-red' },
]

// ── Index ────────────────────────────────────────────────

/** All rule fragments indexed by name — for tooling and validation. */
export const RULE_FRAGMENTS: Record<string, UIRule> = {
  FRAG_ZONE_CONTAINER,
  FRAG_ZONE_WITH_SHOW,
  FRAG_LOCATED_AVATAR,
  FRAG_GLOBAL_AVATAR,
  FRAG_LOCATED_CARD,
  FRAG_LOCATED_CARD_WITH_QUANTITY,
  FRAG_FREE_CARD,
  FRAG_GAUGE_WITH_BAR,
  FRAG_HIDDEN,
}

/** All event fragments indexed by name — for tooling and validation. */
export const EVENT_FRAGMENTS: Record<string, UIEventStyle[]> = {
  FRAG_EVT_DIALOGUE,
  FRAG_EVT_ACTIONS,
  FRAG_EVT_ALERTS,
  FRAG_EVT_COMBAT,
  FRAG_EVT_SOCIAL,
  FRAG_EVT_TRADE,
  FRAG_EVT_LIFECYCLE,
}
