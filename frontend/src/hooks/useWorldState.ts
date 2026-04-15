/* WorldSeed — Bridge hooks: replay-aware selectors for world state.
 *
 * Components use these instead of reading worldStore directly.
 * When replay is active, returns replay state. Otherwise, live state.
 * Live polling/SSE continue unaffected — worldStore is never touched.
 */

import { useWorldStore } from '@/stores/world'
import { useReplayStore } from '@/stores/replay'
import type { Entity } from '@/lib/types'

export function useEntities(): Entity[] {
  const active = useReplayStore(s => s.active)
  const replayEntities = useReplayStore(s => s.entities)
  const liveEntities = useWorldStore(s => s.entities)
  return active ? replayEntities : liveEntities
}

export function useTick(): number {
  const active = useReplayStore(s => s.active)
  const replayTick = useReplayStore(s => s.tick)
  const liveTick = useWorldStore(s => s.tick)
  return active ? replayTick : liveTick
}
