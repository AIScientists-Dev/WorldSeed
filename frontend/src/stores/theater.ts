/* WorldSeed — Theater store: immersive fullscreen map viewing mode.
 *
 * When active, the map viewport is promoted to position: fixed (fullscreen)
 * with a backdrop overlay dimming the dashboard beneath.
 */

import { create } from 'zustand'
import { useWorldStore, selectIsViewingHistory } from '@/stores/world'
import { useReplayStore } from '@/stores/replay'

interface TheaterState {
  active: boolean
  enter: () => void
  exit: () => void
}

export const useTheaterStore = create<TheaterState>((set) => ({
  active: false,
  enter: () => {
    set({ active: true })
    // Auto-start replay when entering theater on a historical run
    const ws = useWorldStore.getState()
    const rs = useReplayStore.getState()
    const isHistory = selectIsViewingHistory(ws)
    if (isHistory && !rs.active) {
      rs.start(ws.viewingRunId)
    }
  },
  exit: () => set({ active: false }),
}))
