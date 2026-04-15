/* WorldSeed — Pausable timer hook.
 *
 * setTimeout that freezes on pause and resumes with remaining time.
 * Used by OverlayBubble and NarrativeBar for hold timers.
 */

import { useRef, useEffect, useCallback } from 'react'

/**
 * Returns `start(ms)` — a pausable setTimeout.
 * Timer freezes when `paused` becomes true, resumes remaining time when false.
 * Only one timer active at a time (calling start again replaces previous).
 */
export function usePausableTimer(onFire: () => void, paused: boolean) {
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const startedAt = useRef(0)
  const remaining = useRef(0)
  const activeRef = useRef(false)
  const onFireRef = useRef(onFire)
  onFireRef.current = onFire
  const pausedRef = useRef(paused)
  pausedRef.current = paused

  const clear = useCallback(() => {
    if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null }
    activeRef.current = false
    remaining.current = 0
  }, [])

  const schedule = useCallback((ms: number) => {
    if (timerRef.current) clearTimeout(timerRef.current)
    remaining.current = ms
    startedAt.current = Date.now()
    activeRef.current = true
    timerRef.current = setTimeout(() => {
      timerRef.current = null
      activeRef.current = false
      remaining.current = 0
      onFireRef.current()
    }, ms)
  }, [])

  const start = useCallback((ms: number) => {
    if (pausedRef.current) {
      remaining.current = ms
      activeRef.current = true
    } else {
      schedule(ms)
    }
  }, [schedule])

  // Pause/resume
  useEffect(() => {
    if (!activeRef.current) return
    if (paused) {
      if (timerRef.current) {
        clearTimeout(timerRef.current)
        timerRef.current = null
        remaining.current = Math.max(0, remaining.current - (Date.now() - startedAt.current))
      }
    } else if (remaining.current > 0) {
      schedule(remaining.current)
    }
  }, [paused, schedule])

  // Cleanup
  useEffect(() => {
    return () => { if (timerRef.current) clearTimeout(timerRef.current) }
  }, [])

  return { start, clear }
}
