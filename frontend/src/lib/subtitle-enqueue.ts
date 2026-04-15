/* WorldSeed — Subtitle enqueue helper.
 *
 * Shared logic for enqueuing subtitle cues from stream records.
 * Used by replay (per-tick advance) and start.
 *
 * Accepts a tick range to avoid skipping events between snapshot ticks.
 * Uses binary search since streamRecords are ordered by tick.
 */

import { useStreamStore } from '@/stores/stream'
import { useWorldStore } from '@/stores/world'
import { useSubtitleStore } from '@/stores/subtitle'
import { processRecord } from './subtitle-measure'

/** Find the first index where record.tick >= target using binary search. */
function lowerBound(records: { tick?: number }[], target: number): number {
  let lo = 0, hi = records.length
  while (lo < hi) {
    const mid = (lo + hi) >>> 1
    if ((records[mid].tick ?? -1) < target) lo = mid + 1
    else hi = mid
  }
  return lo
}

/** Enqueue subtitle cues for all records in a tick range (inclusive). */
export function enqueueCuesForRange(fromTick: number, toTick: number): void {
  const records = useStreamStore.getState().streamRecords
  const actionDefs = useWorldStore.getState().actionDefs
  const start = lowerBound(records, fromTick)
  for (let i = start; i < records.length; i++) {
    const t = records[i].tick ?? -1
    if (t > toTick) break
    const cue = processRecord(records[i], actionDefs)
    if (cue) useSubtitleStore.getState().enqueue(cue)
  }
}

/** Enqueue subtitle cues for a single tick. */
export function enqueueCuesForTick(tick: number): void {
  enqueueCuesForRange(tick, tick)
}
