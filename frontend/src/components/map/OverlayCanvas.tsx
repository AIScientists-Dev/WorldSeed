/* WorldSeed — OverlayCanvas: renders all bubbles at pre-computed positions.
 *
 * Single overlay layer inside map-canvas, above zones.
 * Positions from useOverlayPositions (pure math, no DOM queries).
 * Entities looked up once here and passed to OverlayBubble as props.
 */

import { useMemo } from 'react'
import { AnimatePresence } from 'motion/react'
import { useEntities } from '@/hooks/useWorldState'
import { useOverlayPositions } from '@/hooks/useOverlayPositions'
import type { Entity } from '@/lib/types'
import OverlayBubble from './OverlayBubble'

interface Props {
  onChipReady: () => void
  onSpeechDone: () => void
  speed: number
  paused: boolean
}

export default function OverlayCanvas({ onChipReady, onSpeechDone, speed, paused }: Props) {
  const { positions, activeCues } = useOverlayPositions()
  const entities = useEntities()

  const entityMap = useMemo(() => {
    const map = new Map<string, Entity>()
    for (const e of entities) map.set(e.id, e)
    return map
  }, [entities])

  return (
    <div data-overlay-canvas className="absolute inset-0 pointer-events-none" style={{ zIndex: 'var(--z-overlay)' }}>
      <AnimatePresence>
        {activeCues.map(({ cue, status }) => {
          const pos = positions.get(cue.id)
          if (!pos) return null
          return (
            <OverlayBubble
              key={cue.id}
              cue={cue}
              position={pos}
              status={status}
              speed={speed}
              paused={paused}
              entity={entityMap.get(cue.agentId)}
              onChipReady={onChipReady}
              onSpeechDone={onSpeechDone}
            />
          )
        })}
      </AnimatePresence>
    </div>
  )
}
