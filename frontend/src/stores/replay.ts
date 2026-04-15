/* WorldSeed — Replay store: independent playback of per-tick snapshots.
 *
 * Replay is a layer on top of normal operation. It NEVER touches worldStore.
 * Live polling/SSE continues unaffected during replay.
 *
 * Data flow:
 *   start(runId) → fetch snapshot list → fetch tick 0 snapshot → active=true
 *   rAF loop → advance tick → fetch next snapshot → set entities
 *   stop() → active=false → components read live worldStore again
 *
 * Smart pacing:
 *   Content ticks are held by subtitleBusy (subtitle system controls timing).
 *   Empty ticks use a short minimum delay (EMPTY_TICK_MS).
 *   A fetching flag prevents overlapping async fetches.
 */

import { create } from 'zustand'
import { apiFetch } from '@/lib/api'
import { enrichEntities } from '@/lib/types'
import type { Entity } from '@/lib/types'
import { useSubtitleStore } from '@/stores/subtitle'
import { enqueueCuesForTick, enqueueCuesForRange } from '@/lib/subtitle-enqueue'

interface ReplayState {
  active: boolean
  paused: boolean
  tick: number
  totalTicks: number
  speed: number // ticks per second
  entities: Entity[]
  availableTicks: number[]
  /** O(1) tick → index lookup, built once on start. */
  tickIndexMap: Map<number, number>
  runId: string
  loading: boolean
}

interface ReplayActions {
  start: (runId: string) => Promise<void>
  stop: () => void
  pause: () => void
  resume: () => void
  stepForward: () => void
  stepBack: () => void
  setSpeed: (speed: number) => void
  seekTo: (targetTick: number) => void
}

// --- rAF playback loop (module-level, outside React) ---

/** Minimum dwell time for empty ticks (ms). Content ticks are held by subtitleBusy. */
const EMPTY_TICK_MS = 200

let rafId: number | null = null
let lastTime = 0
let accumulated = 0
let fetching = false

function stopLoop() {
  if (rafId !== null) {
    cancelAnimationFrame(rafId)
    rafId = null
  }
  accumulated = 0
  fetching = false
}

/** Shared: pause, fetch snapshot, set tick, optionally enqueue cues. */
function goToTick(
  get: () => ReplayState & ReplayActions,
  set: (partial: Partial<ReplayState>) => void,
  targetTick: number,
  enqueueCues: boolean,
): void {
  const { runId } = get()
  set({ paused: true })
  fetchSnapshot(runId, targetTick).then(entities => {
    if (!entities) return
    if (!useReplayStore.getState().active) return
    set({ tick: targetTick, entities })
    if (enqueueCues) enqueueCuesForTick(targetTick)
  })
}

async function fetchSnapshot(runId: string, tick: number): Promise<Entity[] | null> {
  const data = await apiFetch(`/api/runs/${runId}/snapshots/${tick}`)
  if (!data?.entities) return null
  return enrichEntities(data.entities)
}

function startLoop() {
  stopLoop()
  lastTime = performance.now()
  accumulated = 0

  function frame(now: number) {
    const state = useReplayStore.getState()
    if (!state.active || state.paused) {
      rafId = null
      return
    }

    const delta = Math.min(now - lastTime, 500) // cap to prevent jumps after tab switch
    lastTime = now
    accumulated += delta

    const sub = useSubtitleStore.getState()
    const subtitleBusy = sub.current !== null || sub.queue.length > 0
    const tickDuration = EMPTY_TICK_MS / state.speed

    if (accumulated >= tickDuration && !subtitleBusy && !fetching) {
      accumulated = 0

      const nextIndex = (state.tickIndexMap.get(state.tick) ?? -1) + 1
      if (nextIndex >= state.availableTicks.length) {
        useReplayStore.setState({ paused: true })
        rafId = null
        return
      }

      const prevTick = state.tick
      const nextTick = state.availableTicks[nextIndex]
      fetching = true
      fetchSnapshot(state.runId, nextTick)
        .then(entities => {
          if (!entities) return
          if (!useReplayStore.getState().active) return
          useReplayStore.setState({ tick: nextTick, entities })
          enqueueCuesForRange(prevTick + 1, nextTick)
        })
        .finally(() => { fetching = false })
    }

    rafId = requestAnimationFrame(frame)
  }

  rafId = requestAnimationFrame(frame)
}

export const useReplayStore = create<ReplayState & ReplayActions>()((set, get) => ({
  active: false,
  paused: false,
  tick: 0,
  totalTicks: 0,
  speed: 1, // 1x = 2s per tick
  entities: [],
  availableTicks: [],
  tickIndexMap: new Map(),
  runId: '',
  loading: false,

  start: async (runId: string) => {
    set({ loading: true })

    const listData = await apiFetch(`/api/runs/${runId}/snapshots`)
    const ticks: number[] = listData?.ticks || []
    if (ticks.length === 0) {
      set({ loading: false })
      return
    }

    const entities = await fetchSnapshot(runId, ticks[0])
    if (!entities) {
      set({ loading: false })
      return
    }

    set({
      active: true,
      paused: false,
      tick: ticks[0],
      totalTicks: ticks[ticks.length - 1],
      speed: get().speed,
      entities,
      availableTicks: ticks,
      tickIndexMap: new Map(ticks.map((t, i) => [t, i])),
      runId,
      loading: false,
    })

    enqueueCuesForRange(0, ticks[0])
    startLoop()
  },

  stop: () => {
    stopLoop()
    useSubtitleStore.getState().clear()
    set({
      active: false,
      paused: false,
      tick: 0,
      entities: [],
      availableTicks: [],
      tickIndexMap: new Map(),
      runId: '',
    })
  },

  pause: () => {
    set({ paused: true })
  },

  resume: () => {
    set({ paused: false })
    startLoop()
  },

  stepForward: () => {
    const { availableTicks, tick, active } = get()
    if (!active) return
    const idx = get().tickIndexMap.get(tick) ?? -1
    if (idx >= availableTicks.length - 1) return
    goToTick(get, set, availableTicks[idx + 1], true)
  },

  stepBack: () => {
    const { availableTicks, tick, active } = get()
    if (!active) return
    const idx = get().tickIndexMap.get(tick) ?? -1
    if (idx <= 0) return
    goToTick(get, set, availableTicks[idx - 1], true)
  },

  setSpeed: (speed: number) => {
    set({ speed })
  },

  seekTo: (targetTick: number) => {
    const { availableTicks, active } = get()
    if (!active) return
    useSubtitleStore.getState().clear()
    let best = availableTicks[0]
    for (const t of availableTicks) {
      if (t <= targetTick) best = t
      else break
    }
    goToTick(get, set, best, false)
  },
}))
