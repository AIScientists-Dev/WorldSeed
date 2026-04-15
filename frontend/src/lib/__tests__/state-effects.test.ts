/* State effects tests -- shared condition matching for EntityCard + AgentRow */

import { describe, it, expect } from 'vitest'
import { matchStateEffect } from '../state-effects'

describe('matchStateEffect', () => {
  it('matches equality condition', () => {
    const effects = { 'status=destroyed': 'destroyed', 'status=active': 'active' }
    expect(matchStateEffect({ status: 'destroyed' }, effects)).toBe('destroyed')
    expect(matchStateEffect({ status: 'active' }, effects)).toBe('active')
    expect(matchStateEffect({ status: 'idle' }, effects)).toBeNull()
  })

  it('matches less-than condition', () => {
    const effects = { 'condition<20': 'damaged' }
    expect(matchStateEffect({ condition: 10 }, effects)).toBe('damaged')
    expect(matchStateEffect({ condition: 20 }, effects)).toBeNull()
    expect(matchStateEffect({ condition: 50 }, effects)).toBeNull()
  })

  it('matches greater-than condition', () => {
    const effects = { 'health>80': 'highlighted' }
    expect(matchStateEffect({ health: 90 }, effects)).toBe('highlighted')
    expect(matchStateEffect({ health: 80 }, effects)).toBeNull()
    expect(matchStateEffect({ health: 50 }, effects)).toBeNull()
  })

  it('first match wins', () => {
    const effects = {
      'status=destroyed': 'destroyed',
      'condition<20': 'damaged',
    }
    expect(matchStateEffect({ status: 'destroyed', condition: 10 }, effects)).toBe('destroyed')
  })

  it('returns null for empty effects', () => {
    expect(matchStateEffect({ status: 'active' }, {})).toBeNull()
  })

  it('handles missing property gracefully', () => {
    const effects = { 'condition<20': 'damaged' }
    expect(matchStateEffect({}, effects)).toBeNull()
  })

  it('handles string numbers in equality', () => {
    const effects = { 'alive=false': 'destroyed' }
    expect(matchStateEffect({ alive: false }, effects)).toBe('destroyed')
  })
})
