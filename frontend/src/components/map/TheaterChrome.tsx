/* WorldSeed — TheaterChrome: immersive theater mode overlay.
 *
 * Orchestrator rendered inside MapView. Composes:
 *   - TheaterControlBar (top-center pill, theater active only)
 *   - Vignette (radial dim at edges, theater active only)
 *
 * The enter button lives in MapToolbar.
 *
 * Z-index layering uses design tokens from motion.css:
 *   --z-overlay (50)  vignette sits just below
 *   --z-theater (55)  controls above overlays
 */

import { PAPER_EASE } from '@/lib/motion'
import { AnimatePresence, motion } from 'motion/react'
import { useTheaterStore } from '@/stores/theater'
import { useCursorIdle } from '@/hooks/useCursorIdle'
import TheaterControlBar from './TheaterControlBar'


export default function TheaterChrome() {
  const active = useTheaterStore(s => s.active)
  const { visible, holdWake, releaseWake } = useCursorIdle(3000, active)

  if (!active) return null

  return (
    <>
      {/* ── Control bar (top-center pill, auto-hides on idle) ── */}
      <AnimatePresence>
        {visible && (
          <motion.div
            key="theater-bar"
            className="absolute top-3 left-1/2 -translate-x-1/2"
            style={{ zIndex: 'var(--z-theater)' }}
            initial={{ opacity: 0, y: -10 }}
            animate={{ opacity: 1, y: 0 }}
            exit={{ opacity: 0, y: -10 }}
            transition={{ duration: 0.25, ease: PAPER_EASE }}
          >
            <TheaterControlBar onMouseEnter={holdWake} onMouseLeave={releaseWake} />
          </motion.div>
        )}
      </AnimatePresence>

      {/* ── Vignette ── */}
      <motion.div
        key="theater-vignette"
        className="absolute inset-0 pointer-events-none"
        style={{
          zIndex: 'var(--z-vignette)',
          background: 'radial-gradient(ellipse 80% 70% at center, transparent 0%, rgba(0,0,0,0.1) 100%)',
        }}
        initial={{ opacity: 0 }}
        animate={{ opacity: 1 }}
        exit={{ opacity: 0 }}
        transition={{ duration: 0.6, ease: PAPER_EASE, delay: 0.15 }}
      />
    </>
  )
}
