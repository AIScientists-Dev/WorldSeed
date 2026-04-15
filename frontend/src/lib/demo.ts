/* WorldSeed — Demo ambient playback
 *
 * Drip-feeds historical speech/whisper/signal events as subtitle cues
 * on top of the final run state. Agents stay in place — no replay,
 * no state changes. The world feels alive while the visitor explores.
 *
 * Public API:
 *   useDemoAmbient() — hook for DashboardPage
 *
 * Demo mode detection is handled by useDemoStore (stores/demo.ts).
 */

import { useEffect, useRef } from 'react'
import { useDemoStore } from '@/stores/demo'
import { useWorldStore } from '@/stores/world'
import { useStreamStore } from '@/stores/stream'
import { useSubtitleStore } from '@/stores/subtitle'
import { processRecord } from '@/lib/subtitle-measure'
import type { MeasuredCue } from '@/lib/subtitle-types'

/** Event types worth showing as ambient bubbles. */
const AMBIENT_TYPES = new Set(['say', 'whisper', 'signal', 'accuse', 'observe'])

/** Interval between ambient cues (ms). */
const AMBIENT_INTERVAL_MS = 4000

/** Only use events from the last N ticks to avoid timeline contradictions. */
const RECENT_TICK_WINDOW = 15

function collectAmbientCues(): MeasuredCue[] {
  const records = useStreamStore.getState().streamRecords
  const actionDefs = useWorldStore.getState().actionDefs
  if (records.length === 0) return []

  // Records are sorted by tick — scan backwards and break early
  const maxTick = records[records.length - 1].tick ?? 0
  const minTick = Math.max(0, maxTick - RECENT_TICK_WINDOW)

  const cues: MeasuredCue[] = []
  for (let i = records.length - 1; i >= 0; i--) {
    const record = records[i]
    if ((record.tick ?? 0) < minTick) break
    if (record.kind !== 'event') continue
    if (!AMBIENT_TYPES.has(record.type ?? '')) continue
    const cue = processRecord(record, actionDefs)
    if (cue) cues.push(cue)
  }
  cues.reverse()
  return cues
}

export function useDemoAmbient() {
  const active = useDemoStore(s => s.active)
  const started = useRef(false)
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null)

  useEffect(() => {
    if (!active || started.current) return

    function tryStart() {
      if (started.current) return
      if (useWorldStore.getState().entities.length === 0) return
      if (useStreamStore.getState().streamRecords.length === 0) return

      started.current = true
      cleanup()

      const cues = collectAmbientCues()
      if (cues.length === 0) return

      let idx = 0

      setTimeout(() => {
        useSubtitleStore.getState().enqueue(cues[idx])
        idx = (idx + 1) % cues.length

        timerRef.current = setInterval(() => {
          const sub = useSubtitleStore.getState()
          if (sub.queue.length < 2) {
            useSubtitleStore.getState().enqueue(cues[idx])
            idx = (idx + 1) % cues.length
          }
        }, AMBIENT_INTERVAL_MS)
      }, 1500)
    }

    const unsubs = [
      useWorldStore.subscribe(tryStart),
      useStreamStore.subscribe(tryStart),
    ]
    function cleanup() { unsubs.forEach(fn => fn()) }

    tryStart()

    return () => {
      cleanup()
      if (timerRef.current) clearInterval(timerRef.current)
    }
  }, [active])
}
