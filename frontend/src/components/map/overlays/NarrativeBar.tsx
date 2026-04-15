/* WorldSeed — NarrativeBar: DM narrative cinematic subtitle.
 *
 * RPG dialogue box pattern:
 *   Phase 1: dark bar slides up + fades in (400ms)
 *   Phase 2: pause (350ms) — let eyes find the bar
 *   Phase 3: typewriter reveals text (60ms/char, punctuation pauses)
 *   Phase 4: hold (1200ms) — reading time
 *
 * Hover pauses the hold timer (keeps bar visible while mouse is over it).
 * Reads from subtitle store (current cue where kind === 'narrative').
 *
 * Narrator highlights do NOT go through this component.
 * They have their own dedicated render path: ChronicleBar.
 */

import { useState, useRef, useEffect, useCallback } from 'react'
import { motion, AnimatePresence } from 'motion/react'
import { useSubtitleStore } from '@/stores/subtitle'
import { useTypewriter } from '@/hooks/useTypewriter'
import { usePausableTimer } from '@/hooks/usePausableTimer'
import { SUBTITLE_TIMING, narrativeMsPerChar } from '@/lib/subtitle-types'
import type { MeasuredCue } from '@/lib/subtitle-types'
import { PAPER_EASE } from '@/lib/motion'
import TypewriterText from '../TypewriterText'

interface NarrativeBarProps {
  onDone: () => void
  speed: number
  paused: boolean
}

function NarrativeContent({ cue, speed, paused, onDone }: { cue: MeasuredCue; speed: number; paused: boolean; onDone: () => void }) {
  const [phase, setPhase] = useState<'waiting' | 'typing' | 'hold'>('waiting')
  const hovered = useRef(false)
  const onDoneRef = useRef(onDone)
  onDoneRef.current = onDone

  // Phase transition: waiting → typing (pausable)
  const phaseTimer = usePausableTimer(
    () => setPhase('typing'),
    paused,
  )
  useEffect(() => {
    const delay = (SUBTITLE_TIMING.narrativeBarAppearMs + SUBTITLE_TIMING.narrativePauseMs) / speed
    phaseTimer.start(delay)
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Hold timer (pausable) — also respects hover
  const holdTimer = usePausableTimer(
    () => { if (!hovered.current) onDoneRef.current() },
    paused,
  )

  // Typewriter
  const { displayedText, isDone } = useTypewriter(cue.displayText, {
    msPerChar: narrativeMsPerChar(cue.displayText),
    speed,
    paused,
    onDone: () => {
      setPhase('hold')
      holdTimer.start(SUBTITLE_TIMING.narrativeHoldMs / speed)
    },
    enabled: phase === 'typing' || phase === 'hold',
  })

  // Hover hold
  const onMouseEnter = useCallback(() => {
    hovered.current = true
    holdTimer.clear()
  }, [holdTimer])

  const onMouseLeave = useCallback(() => {
    hovered.current = false
    if (phase === 'hold' && isDone) {
      holdTimer.start(SUBTITLE_TIMING.narrativeMouseLeaveMs)
    }
  }, [phase, isDone, holdTimer])

  return (
    <motion.div
      className="pointer-events-auto"
      onMouseEnter={onMouseEnter}
      onMouseLeave={onMouseLeave}
      initial={{ opacity: 0, y: 16 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, y: -10 }}
      transition={{ duration: 0.4, ease: PAPER_EASE }}
    >
      <div
        className="rounded-lg px-5 py-3 backdrop-blur-sm max-w-[520px]"
        style={{
          background: 'rgba(0,0,0,0.72)',
          minWidth: Math.min(cue.textW, 520),
        }}
      >
        <TypewriterText
          fullText={cue.displayText}
          displayedText={phase === 'waiting' ? '' : displayedText}
          isDone={phase === 'waiting' ? true : isDone}
          className="text-[15px] leading-relaxed italic text-left"
          style={{ fontFamily: 'var(--font-narrative)', color: 'rgba(255,255,255,0.93)' }}
        />
      </div>
    </motion.div>
  )
}

export default function NarrativeBar({ onDone, speed, paused }: NarrativeBarProps) {
  const current = useSubtitleStore(s => s.current)
  const narrative = current?.kind === 'narrative' ? current : null

  return (
    <div className="absolute bottom-6 left-1/2 -translate-x-1/2 pointer-events-none z-50">
      <AnimatePresence mode="wait">
        {narrative && (
          <NarrativeContent key={narrative.id} cue={narrative} speed={speed} paused={paused} onDone={onDone} />
        )}
      </AnimatePresence>
    </div>
  )
}
