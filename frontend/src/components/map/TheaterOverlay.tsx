/* WorldSeed — TheaterOverlay: backdrop that dims dashboard chrome in theater mode.
 *
 * Rendered via portal to document.body. Sits behind the promoted map-viewport
 * (z-theater-backdrop < z-theater-viewport) to dim sidebar, header, and right panel.
 */

import { createPortal } from 'react-dom'
import { PAPER_EASE } from '@/lib/motion'
import { motion } from 'motion/react'


export default function TheaterOverlay() {
  return createPortal(
    <motion.div
      className="fixed inset-0 bg-black/50"
      style={{ zIndex: 'var(--z-theater-backdrop)' }}
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      exit={{ opacity: 0 }}
      transition={{ duration: 0.3, ease: PAPER_EASE }}
    />,
    document.body,
  )
}
