/* WorldSeed — Demo mode store
 *
 * Centralized state for the hosted demo experience.
 * Activated by /demo route or sessionStorage.
 *
 * Tracks selected run ID, language choice, and discovered features.
 * DemoHint component reads this store to show/hide notification dots.
 */

import { create } from 'zustand'

export type DemoFeature =
  | 'gazette'
  | 'theater'
  | 'chronicle'
  | 'gm-pill'
  | 'agent'

const SS_KEY = 'worldseed_demo'
const SS_RUN = 'worldseed_demo_run'

interface DemoState {
  /** Demo mode is active. */
  active: boolean
  /** Selected demo run ID (set by DemoEntry after language selection). */
  runId: string
  /** Features the visitor has clicked / discovered. */
  discovered: Set<DemoFeature>
  /** Activate demo mode (persists for tab lifetime). */
  activate: () => void
  /** Set the resolved demo run ID. */
  setRunId: (id: string) => void
  /** Mark a feature as discovered — dot disappears. */
  markDiscovered: (feature: DemoFeature) => void
  /** True if demo is active AND feature hasn't been discovered yet. */
  isHinted: (feature: DemoFeature) => boolean
}

function readDemoFlag(): boolean {
  if (typeof window === 'undefined') return false
  return sessionStorage.getItem(SS_KEY) === '1'
}

function readDemoRunId(): string {
  if (typeof window === 'undefined') return ''
  return sessionStorage.getItem(SS_RUN) || ''
}

export const useDemoStore = create<DemoState>()((set, get) => ({
  active: readDemoFlag(),
  runId: readDemoRunId(),
  discovered: new Set(),

  activate: () => {
    sessionStorage.setItem(SS_KEY, '1')
    set({ active: true })
  },

  setRunId: (id: string) => {
    sessionStorage.setItem(SS_RUN, id)
    set({ runId: id })
  },

  markDiscovered: (feature) => {
    set(s => {
      if (s.discovered.has(feature)) return s
      const next = new Set(s.discovered)
      next.add(feature)
      return { discovered: next }
    })
  },

  isHinted: (feature) => {
    const s = get()
    return s.active && !s.discovered.has(feature)
  },
}))
