/* WorldSeed — Subtitle store: cue queue + playback state machine.
 *
 * Pure synchronous state — no timers, no DOM, no pretext.
 * Timing is driven by useSubtitlePlayer hook.
 *
 * State machine:
 *   enqueue → queue grows
 *   advance → queue[0] becomes current, old current moves to fading
 *   dismiss → fading item removed
 *   clear   → everything reset
 */

import { create } from 'zustand'
import type { MeasuredCue } from '@/lib/subtitle-types'

interface SubtitleState {
  queue: MeasuredCue[]
  current: MeasuredCue | null
  fading: MeasuredCue[]
}

interface SubtitleActions {
  /** Add a cue to the end of the queue. */
  enqueue: (cue: MeasuredCue) => void
  /** Advance: current → fading, queue[0] → current. */
  advance: () => void
  /** Remove a specific cue from fading (after fade-out animation). */
  dismiss: (id: string) => void
  /** Reset everything. */
  clear: () => void
}

const MAX_FADING = 2
const MAX_QUEUE = 20 // safety cap — never let queue explode

/** Dedup key: same tick + agent + action + display text = duplicate */
function cueKey(c: MeasuredCue): string {
  return `${c.tick}:${c.agentId}:${c.actionType}:${c.displayText}`
}

export const useSubtitleStore = create<SubtitleState & SubtitleActions>()((set) => ({
  queue: [],
  current: null,
  fading: [],

  enqueue: (cue) => {
    set(s => {
      const key = cueKey(cue)
      if (s.current && cueKey(s.current) === key) return s
      if (s.queue.some(q => cueKey(q) === key)) return s
      const queue = s.queue.length >= MAX_QUEUE
        ? [...s.queue.slice(s.queue.length - MAX_QUEUE + 1), cue]
        : [...s.queue, cue]
      return { queue }
    })
  },

  advance: () => {
    set(s => {
      const next = s.queue[0] || null
      const queue = s.queue.slice(1)

      let fading = s.fading
      if (s.current) {
        fading = [...fading, s.current]
        // Cap fading list — oldest get dropped
        if (fading.length > MAX_FADING) {
          fading = fading.slice(fading.length - MAX_FADING)
        }
      }

      return { queue, current: next, fading }
    })
  },

  dismiss: (id) => {
    set(s => ({ fading: s.fading.filter(c => c.id !== id) }))
  },

  clear: () => {
    set({ queue: [], current: null, fading: [] })
  },
}))
