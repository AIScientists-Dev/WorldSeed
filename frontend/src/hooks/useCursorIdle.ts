/* WorldSeed — Cursor idle hook: tracks mouse inactivity.
 *
 * Returns `idle` boolean. After `ms` of no mouse movement, idle becomes true.
 * Mouse move resets the timer. Optionally hides cursor via CSS class when idle
 * (only when `hideCursor` is true — used in theater mode).
 */

import { useState, useEffect, useRef, useCallback } from 'react'

const CURSOR_HIDDEN_CLASS = 'theater-cursor-hidden'

export function useCursorIdle(ms: number, hideCursor = false) {
  const [idle, setIdle] = useState(false)
  const timer = useRef<ReturnType<typeof setTimeout>>(null)
  const hovering = useRef(false)

  const wake = useCallback(() => {
    setIdle(false)
    clearTimeout(timer.current)
    if (!hovering.current) {
      timer.current = setTimeout(() => setIdle(true), ms)
    }
  }, [ms])

  /** Call on mouseenter of interactive elements to prevent hiding while hovered. */
  const holdWake = useCallback(() => {
    hovering.current = true
    clearTimeout(timer.current)
    setIdle(false)
  }, [])

  /** Call on mouseleave to resume idle tracking. */
  const releaseWake = useCallback(() => {
    hovering.current = false
    timer.current = setTimeout(() => setIdle(true), ms)
  }, [ms])

  useEffect(() => {
    document.addEventListener('mousemove', wake)
    wake()
    return () => {
      document.removeEventListener('mousemove', wake)
      clearTimeout(timer.current)
    }
  }, [wake])

  // Cursor hiding
  useEffect(() => {
    if (hideCursor && idle) {
      document.documentElement.classList.add(CURSOR_HIDDEN_CLASS)
    } else {
      document.documentElement.classList.remove(CURSOR_HIDDEN_CLASS)
    }
    return () => document.documentElement.classList.remove(CURSOR_HIDDEN_CLASS)
  }, [hideCursor, idle])

  return { idle, visible: !idle, holdWake, releaseWake }
}
