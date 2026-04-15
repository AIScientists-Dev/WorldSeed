/* WorldSeed — DemoHint: notification dot wrapper for demo mode.
 *
 * Wraps any interactive element. In demo mode, renders a small dot
 * in the top-right corner until the visitor clicks. After click,
 * the dot disappears permanently (for this session).
 *
 * Non-demo mode: renders children unchanged, zero overhead.
 */

import { useCallback, type ReactNode, type MouseEvent } from 'react'
import { useDemoStore, type DemoFeature } from '@/stores/demo'

interface Props {
  feature: DemoFeature
  children: ReactNode
  /** Dot position offset from top-right corner. */
  dotTop?: number
  dotRight?: number
}

export default function DemoHint({ feature, children, dotTop = -2, dotRight = -2 }: Props) {
  const hinted = useDemoStore(s => s.isHinted(feature))

  const handleClick = useCallback((e: MouseEvent) => {
    // Don't prevent default — let the click propagate to the child
    useDemoStore.getState().markDiscovered(feature)
  }, [feature])

  if (!hinted) return <>{children}</>

  return (
    <div className="relative inline-flex" onClick={handleClick}>
      {children}
      <span
        className="absolute pointer-events-none z-10"
        style={{
          top: dotTop,
          right: dotRight,
          width: 7,
          height: 7,
          borderRadius: '50%',
          background: 'var(--amber)',
        }}
      />
    </div>
  )
}
