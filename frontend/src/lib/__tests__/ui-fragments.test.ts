/* UI Fragments tests — ensures fragments stay accurate against rendering code. */

import { describe, it, expect } from 'vitest'
import { SCENE_TYPES } from '../ui-config'
import { RULE_FRAGMENTS, EVENT_FRAGMENTS } from '../ui-fragments'

const VALID_SCENE_NAMES = new Set(Object.keys(SCENE_TYPES))
const VALID_BIND_KEYS = new Set(['label', 'locate_by', 'connections', 'show', 'bar', 'bar_max', 'state_effects'])
const VALID_BUBBLES = new Set(['speech', 'action'])
const VALID_EFFECTS = new Set(['shake', 'flash-red', 'flash-green', 'glow', 'pulse'])

describe('rule fragments', () => {
  it('all have valid scene types', () => {
    for (const [name, frag] of Object.entries(RULE_FRAGMENTS)) {
      if (frag.scene) {
        expect(VALID_SCENE_NAMES.has(frag.scene), `${name}.scene="${frag.scene}" not in SCENE_TYPES`).toBe(true)
      }
    }
  })

  it('all bind keys are recognized', () => {
    for (const [name, frag] of Object.entries(RULE_FRAGMENTS)) {
      if (frag.bind) {
        for (const key of Object.keys(frag.bind)) {
          expect(VALID_BIND_KEYS.has(key), `${name}.bind.${key} not a known bind key`).toBe(true)
        }
      }
    }
  })

  it('container fragments have scene zone or deck', () => {
    const containers = ['FRAG_ZONE_CONTAINER', 'FRAG_ZONE_WITH_SHOW']
    for (const name of containers) {
      const frag = RULE_FRAGMENTS[name]
      expect(['zone', 'deck']).toContain(frag.scene)
    }
  })

  it('avatar fragments have scene avatar', () => {
    const avatars = ['FRAG_LOCATED_AVATAR', 'FRAG_GLOBAL_AVATAR']
    for (const name of avatars) {
      expect(RULE_FRAGMENTS[name].scene).toBe('avatar')
    }
  })

  it('located fragments have locate_by', () => {
    const located = ['FRAG_LOCATED_AVATAR', 'FRAG_LOCATED_CARD', 'FRAG_LOCATED_CARD_WITH_QUANTITY', 'FRAG_GAUGE_WITH_BAR']
    for (const name of located) {
      expect(RULE_FRAGMENTS[name].bind?.locate_by, `${name} missing locate_by`).toBeTruthy()
    }
  })
})

describe('event fragments', () => {
  it('all have valid bubble types', () => {
    for (const [name, events] of Object.entries(EVENT_FRAGMENTS)) {
      for (const ev of events) {
        if (ev.bubble) {
          expect(VALID_BUBBLES.has(ev.bubble), `${name} event "${ev.match}" bubble="${ev.bubble}" invalid`).toBe(true)
        }
      }
    }
  })

  it('all effects are valid', () => {
    for (const [name, events] of Object.entries(EVENT_FRAGMENTS)) {
      for (const ev of events) {
        if (ev.effect) {
          expect(VALID_EFFECTS.has(ev.effect), `${name} event "${ev.match}" effect="${ev.effect}" invalid`).toBe(true)
        }
      }
    }
  })

  it('all events have a match string', () => {
    for (const [name, events] of Object.entries(EVENT_FRAGMENTS)) {
      for (const ev of events) {
        expect(ev.match, `${name} has event without match`).toBeTruthy()
      }
    }
  })
})
