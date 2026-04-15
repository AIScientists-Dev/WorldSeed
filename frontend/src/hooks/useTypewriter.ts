/* WorldSeed — Typewriter hook: ref-based character-by-character reveal.
 *
 * No state in Zustand (would cause 60fps setState). Uses refs + setTimeout.
 * Punctuation pauses add dramatic rhythm. CJK-safe via spread operator.
 * Supports pause/resume — freezes in place without resetting position.
 *
 * Usage:
 *   const { displayedText, isDone } = useTypewriter(text, { msPerChar: 35, onDone: () => ... })
 */

import { useRef, useEffect, useState, useCallback } from 'react'
import { SUBTITLE_TIMING } from '@/lib/subtitle-types'

const PUNCT_RE = /[。，！？；：、.!?,;:\-—""'']/

interface TypewriterOptions {
  /** Milliseconds per character (before speed multiplier) */
  msPerChar: number
  /** Punctuation pause multiplier */
  punctMultiplier?: number
  /** Speed multiplier (1.0 = normal, 2.0 = 2x faster) */
  speed?: number
  /** Called when all characters have been revealed */
  onDone?: () => void
  /** Whether to run the typewriter (false = show full text immediately) */
  enabled?: boolean
  /** Pause the typewriter in place — freezes reveal without resetting */
  paused?: boolean
}

interface TypewriterResult {
  /** Text to display (partial during animation, full when done) */
  displayedText: string
  /** Whether the typewriter has finished */
  isDone: boolean
  /** Force-complete the typewriter */
  complete: () => void
}

export function useTypewriter(text: string, options: TypewriterOptions): TypewriterResult {
  const {
    msPerChar,
    punctMultiplier = SUBTITLE_TIMING.punctMultiplier,
    speed = 1.0,
    onDone,
    enabled = true,
    paused = false,
  } = options

  const [displayed, setDisplayed] = useState(enabled ? '' : text)
  const [isDone, setIsDone] = useState(!enabled)
  const charsRef = useRef<string[]>([])
  const idxRef = useRef(0)
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null)
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone
  const pausedRef = useRef(paused)
  pausedRef.current = paused

  const complete = useCallback(() => {
    if (timerRef.current) clearTimeout(timerRef.current)
    setDisplayed(text)
    setIsDone(true)
    onDoneRef.current?.()
  }, [text])

  // Shared tick — reads idxRef so it resumes from wherever it stopped
  function tick(effectiveMs: number) {
    if (pausedRef.current) return
    const idx = idxRef.current
    if (idx >= charsRef.current.length) {
      setDisplayed(text)
      setIsDone(true)
      onDoneRef.current?.()
      return
    }
    const ch = charsRef.current[idx]
    idxRef.current = idx + 1
    setDisplayed(prev => prev + ch)
    const delay = PUNCT_RE.test(ch) ? effectiveMs * punctMultiplier : effectiveMs
    timerRef.current = setTimeout(() => tick(effectiveMs), delay)
  }

  // Start/restart on text or config change
  useEffect(() => {
    if (!enabled) {
      setDisplayed(text)
      setIsDone(true)
      return
    }

    charsRef.current = [...text]
    idxRef.current = 0
    setDisplayed('')
    setIsDone(false)

    if (!pausedRef.current) {
      tick(Math.max(5, msPerChar / speed))
    }

    return () => {
      if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null }
    }
  }, [text, msPerChar, speed, punctMultiplier, enabled])

  // Pause: clear timer. Resume: restart tick from current position.
  useEffect(() => {
    if (paused) {
      if (timerRef.current) { clearTimeout(timerRef.current); timerRef.current = null }
    } else if (enabled && idxRef.current > 0 && idxRef.current < charsRef.current.length) {
      tick(Math.max(5, msPerChar / speed))
    }
  }, [paused]) // eslint-disable-line react-hooks/exhaustive-deps

  return { displayedText: displayed, isDone, complete }
}
