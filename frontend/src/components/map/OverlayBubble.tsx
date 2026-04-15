/* WorldSeed — OverlayBubble: single bubble component for chip + speech.
 *
 * Rendered by OverlayCanvas at pre-computed {x, y} positions.
 * Position is absolute in map-canvas space. No CSS parent positioning.
 * Animation: opacity only (no y displacement = no flash).
 */

import { useEffect, useRef } from 'react'
import { motion } from 'motion/react'
import { useTypewriter } from '@/hooks/useTypewriter'
import { usePausableTimer } from '@/hooks/usePausableTimer'
import { uiConfig } from '@/lib/ui-config'
import { humanize } from '@/lib/helpers'
import { agentColor } from '@/lib/detail-panel'
import { SUBTITLE_TIMING, speechMsPerChar, narrativeMsPerChar } from '@/lib/subtitle-types'
import type { MeasuredCue } from '@/lib/subtitle-types'
import type { Entity } from '@/lib/types'
import { PAPER_EASE } from '@/lib/motion'
import TypewriterText from './TypewriterText'

interface Props {
  cue: MeasuredCue
  position: { x: number; y: number }
  status: 'current' | 'fading'
  speed: number
  paused: boolean
  entity: Entity | undefined
  onChipReady: () => void
  onSpeechDone: () => void
}

export default function OverlayBubble({ cue, position, status, speed, paused, entity, onChipReady, onSpeechDone }: Props) {
  const avatarUrl = entity ? uiConfig.avatarUrl(entity) : undefined
  const initial = humanize(cue.agentId).charAt(0)
  const color = agentColor(cue.agentId)
  const hasTypewriter = cue.kind === 'speech' || cue.kind === 'description'
  const isChip = cue.kind === 'action'
  const displayPrefix = cue.kind === 'speech' ? '\u201C' : ''
  const displaySuffix = cue.kind === 'speech' ? '\u201D' : ''
  const fullDisplayText = `${displayPrefix}${cue.displayText}${displaySuffix}`

  const holdTimer = usePausableTimer(onSpeechDone, paused)

  const { displayedText, isDone } = useTypewriter(fullDisplayText, {
    msPerChar: cue.kind === 'description'
      ? narrativeMsPerChar(fullDisplayText)
      : speechMsPerChar(fullDisplayText),
    speed,
    paused,
    onDone: () => {
      const holdMs = (cue.kind === 'description' ? SUBTITLE_TIMING.narrativeHoldMs : SUBTITLE_TIMING.speechHoldMs) / speed
      holdTimer.start(holdMs)
    },
    enabled: hasTypewriter && status === 'current',
  })

  // Chip: signal player on mount
  const chipScheduled = useRef(false)
  useEffect(() => {
    if (isChip && status === 'current' && !chipScheduled.current) {
      chipScheduled.current = true
      onChipReady()
    }
  }, [isChip, status, onChipReady])

  return (
    <motion.div
      className="pointer-events-auto absolute"
      style={{ left: position.x, top: position.y, zIndex: hasTypewriter ? 52 : 51 }}
      initial={{ opacity: 0 }}
      animate={{ opacity: status === 'fading' ? 0 : 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: hasTypewriter ? 0.4 : 0.25, ease: PAPER_EASE }}
    >
      <div className="flex items-start gap-2">

        <div
          className="shrink-0 h-7 w-7 rounded-full overflow-hidden border-2 border-white/80 shadow-sm"
          style={{ background: color }}
        >
          {avatarUrl ? (
            <img src={avatarUrl} alt={humanize(cue.agentId)} className="h-full w-full object-cover"
                 onError={(e) => { (e.currentTarget as HTMLElement).style.display = 'none' }} />
          ) : (
            <div className="h-full w-full flex items-center justify-center text-[10px] font-bold text-white/90">
              {initial}
            </div>
          )}
        </div>

        <div className="min-w-0">

          <div className="inline-block rounded px-1.5 py-0.5 mb-1 text-[10px] font-semibold uppercase tracking-wider backdrop-blur-sm"
               style={{ fontFamily: 'var(--font-display)', color: '#1F2937', background: 'rgba(255,255,255,0.85)' }}>
            {humanize(cue.agentId)}
          </div>

          {/* Text — width from pretext shrink-wrap, height from invisible placeholder */}
          <div
            className="rounded-lg border px-3 py-1.5 shadow-sm backdrop-blur-sm"
            style={{
              boxSizing: 'content-box',
              background: 'rgba(255,255,255,0.95)',
              borderColor: 'rgba(209,213,219,0.6)',
              width: cue.textW,
            }}
          >
            {hasTypewriter ? (
              <TypewriterText
                fullText={fullDisplayText}
                displayedText={displayedText}
                isDone={isDone}
                className={`text-[13px] leading-snug ${cue.kind === 'description' ? 'italic' : ''}`}
                style={{ fontFamily: 'var(--font-narrative)', color: 'rgba(17,24,39,0.9)' }}
              />
            ) : (
              <div className="text-[12px] leading-snug" style={{ fontFamily: 'var(--font-sans)', color: '#4B5563' }}>
                {cue.displayText}
              </div>
            )}
          </div>
        </div>
      </div>
    </motion.div>
  )
}
