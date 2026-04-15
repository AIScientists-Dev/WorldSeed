/* UI Config tests — core functionality: findRule, getBind, getSceneName, event_defaults */

import { describe, it, expect, beforeEach } from 'vitest'
import { uiConfig } from '../ui-config'

function reset() {
  uiConfig.rules = []
  uiConfig.events = []
  uiConfig.eventDefaults = {}
  uiConfig.layout = {}
  uiConfig.assetPack = ''
  uiConfig.loaded = false
}

describe('findRule', () => {
  beforeEach(reset)

  it('first match wins', () => {
    uiConfig.rules = [
      { match: { id: 'entrance' }, scene: 'zone', bind: { bar: 'seal' } },
      { match: { type: 'space' }, scene: 'zone', bind: { label: 'id' } },
    ]
    expect(uiConfig.findRule({ id: 'entrance', type: 'space' }).bind?.bar).toBe('seal')
    expect(uiConfig.findRule({ id: 'hallway', type: 'space' }).bind?.label).toBe('id')
  })

  it('no match returns empty', () => {
    uiConfig.rules = [{ match: { type: 'space' }, scene: 'zone' }]
    expect(uiConfig.findRule({ id: 'x', type: 'unknown' })).toEqual({})
  })
})

describe('getBind', () => {
  beforeEach(reset)

  it('returns bind from matched rule', () => {
    uiConfig.rules = [{ match: { type: 'agent' }, scene: 'avatar', bind: { locate_by: 'sector' } }]
    expect(uiConfig.getBind({ type: 'agent' })).toEqual({ locate_by: 'sector' })
  })

  it('returns empty when no rule matches', () => {
    uiConfig.rules = [{ match: { type: 'space' }, scene: 'zone' }]
    expect(uiConfig.getBind({ type: 'unknown' })).toEqual({})
  })
})

describe('getSceneName', () => {
  beforeEach(reset)

  it('returns scene from matched rule', () => {
    uiConfig.rules = [{ match: { type: 'space' }, scene: 'zone' }]
    expect(uiConfig.getSceneName({ type: 'space' })).toBe('zone')
  })

  it('returns fallback when no rule matches', () => {
    uiConfig.rules = [{ match: { type: 'space' }, scene: 'zone' }]
    expect(uiConfig.getSceneName({ type: 'unknown' })).toBe('fallback')
  })
})

describe('event_defaults', () => {
  beforeEach(reset)

  it('unmatched event falls back to default', () => {
    uiConfig.eventDefaults = { bubble: 'action' }
    expect(uiConfig.getEventStyle('anything')).toBe('action')
  })

  it('matched event inherits missing fields from default', () => {
    uiConfig.events = [{ match: 'code', effect: 'glow' } as any]
    uiConfig.eventDefaults = { bubble: 'action' }
    expect(uiConfig.getEventStyle('code')).toBe('action')
    expect(uiConfig.getEventEffect('code')).toBe('glow')
  })

  it('explicit fields override default', () => {
    uiConfig.events = [{ match: 'say', bubble: 'speech', effect: 'pulse' }]
    uiConfig.eventDefaults = { bubble: 'action', effect: 'glow' }
    expect(uiConfig.getEventStyle('say')).toBe('speech')
    expect(uiConfig.getEventEffect('say')).toBe('pulse')
  })

  it('no defaults = empty string', () => {
    uiConfig.events = [{ match: 'say', bubble: 'speech' }]
    expect(uiConfig.getEventStyle('unknown')).toBe('')
    expect(uiConfig.getEventEffect('say')).toBe('')
  })
})
