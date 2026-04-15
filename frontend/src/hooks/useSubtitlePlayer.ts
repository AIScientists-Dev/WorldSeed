/* WorldSeed — Subtitle player hook: drives advance timing.
 *
 * Subscribes to world/replay/UI stores internally to derive playing/speed/mode.
 * Components that use this hook do NOT need to pass these as props.
 *
 * Does NOT render anything — just drives the subtitle store state machine.
 * Uses usePausableTimer for the advance timer so pause/resume is automatic.
 */

import { useEffect, useCallback } from 'react'
import { useSubtitleStore } from '@/stores/subtitle'
import { useWorldStore, selectIsViewingHistory } from '@/stores/world'
import { useReplayStore } from '@/stores/replay'
import { useUIStore } from '@/stores/ui'
import { usePausableTimer } from '@/hooks/usePausableTimer'
import { SUBTITLE_TIMING } from '@/lib/subtitle-types'

function getLiveSpeedUp(queueDepth: number): number {
  for (const [threshold, multiplier] of SUBTITLE_TIMING.liveSpeedUp) {
    if (queueDepth >= threshold) return multiplier
  }
  return 1.0
}

/**
 * Drive subtitle store advance timing.
 * Derives playing/speed/mode from world + replay + UI stores.
 */
export function useSubtitlePlayer() {
  const worldStatus = useWorldStore(s => s.worldStatus)
  const isViewingHistory = useWorldStore(selectIsViewingHistory)
  const replayActive = useReplayStore(s => s.active)
  const replayPaused = useReplayStore(s => s.paused)
  const replaySpeed = useReplayStore(s => s.speed)
  const liveSpeed = useUIStore(s => s.speed)

  const viewingCurrent = !isViewingHistory
  const playing = replayActive ? !replayPaused : (worldStatus === 'live' && viewingCurrent)
  const speed = replayActive ? replaySpeed : (liveSpeed || 1)
  const mode: 'replay' | 'live' = replayActive ? 'replay' : 'live'

  const store = useSubtitleStore

  const getEffectiveSpeed = useCallback(() => {
    if (mode === 'live') {
      const depth = store.getState().queue.length
      return speed * getLiveSpeedUp(depth)
    }
    return speed
  }, [speed, mode])

  // Pausable advance timer — freezes on pause, resumes with remaining time
  const advanceTimer = usePausableTimer(() => store.getState().advance(), !playing)

  const scheduleAdvance = useCallback((delayMs: number) => {
    advanceTimer.start(delayMs)
  }, [advanceTimer])

  const cueFinished = useCallback(() => {
    const s = getEffectiveSpeed()
    scheduleAdvance(SUBTITLE_TIMING.interCueMs / s)
  }, [getEffectiveSpeed, scheduleAdvance])

  const scheduleChipAdvance = useCallback(() => {
    const s = getEffectiveSpeed()
    scheduleAdvance(SUBTITLE_TIMING.chipHoldMs / s)
  }, [getEffectiveSpeed, scheduleAdvance])

  // Auto-advance when queue has items but nothing is playing
  const queueLength = useSubtitleStore(s => s.queue.length)
  const hasCurrent = useSubtitleStore(s => s.current !== null)

  useEffect(() => {
    if (!playing) return
    if (!hasCurrent && queueLength > 0) {
      store.getState().advance()
    }
  }, [playing, queueLength, hasCurrent])

  return { cueFinished, scheduleChipAdvance, speed, paused: !playing }
}
