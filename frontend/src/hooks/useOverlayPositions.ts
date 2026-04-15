/* WorldSeed — Overlay positions hook.
 *
 * Single hook that computes all bubble positions from:
 *   - entities (agent locations in zones)
 *   - subtitle store (current + fading cues)
 *   - zone layout config
 *
 * Returns a stable Map<cueId, {x, y}> via useMemo.
 * Pure computation — no DOM queries.
 */

import { useMemo } from 'react'
import { useSubtitleStore } from '@/stores/subtitle'
import { useEntities } from '@/hooks/useWorldState'
import { uiConfig } from '@/lib/ui-config'
import { computeMapData } from '@/lib/map-layout'
import { computeAgentAnchors, computeOverlayLayout } from '@/lib/overlay-layout'
import type { MeasuredCue } from '@/lib/subtitle-types'

export function useOverlayPositions() {
  const entities = useEntities()
  const current = useSubtitleStore(s => s.current)
  const fading = useSubtitleStore(s => s.fading)

  // Collect non-narrative cues
  const activeCues = useMemo(() => {
    const result: Array<{ cue: MeasuredCue; status: 'current' | 'fading' }> = []
    for (const f of fading) {
      if (f.kind !== 'narrative') result.push({ cue: f, status: 'fading' })
    }
    if (current && current.kind !== 'narrative') {
      result.push({ cue: current, status: 'current' })
    }
    return result
  }, [current, fading])

  // Compute agent anchors from config data (pure math)
  const anchors = useMemo(() => {
    const mapData = computeMapData(entities)
    return computeAgentAnchors(mapData, uiConfig.layout || {})
  }, [entities])

  // Compute positions (dodge + clamp)
  // Canvas bounds from zone layout — recompute when entities change (layout may load async)
  const CANVAS_MIN_W = 1000
  const CANVAS_MIN_H = 800
  const CANVAS_PAD = 200
  const canvasBounds = useMemo(() => {
    const layout = uiConfig.layout || {}
    let maxW = CANVAS_MIN_W, maxH = CANVAS_MIN_H
    for (const key of Object.keys(layout)) {
      const pos = layout[key]
      if (!pos) continue
      maxW = Math.max(maxW, (pos.x || 0) + (pos.w || 0) + CANVAS_PAD)
      maxH = Math.max(maxH, (pos.y || 0) + (pos.h || 0) + CANVAS_PAD)
    }
    return { w: maxW, h: maxH }
  }, [entities.length]) // recompute when entity count changes (proxy for config load)

  const positions = useMemo(
    () => computeOverlayLayout(activeCues, anchors, canvasBounds),
    [activeCues, anchors, canvasBounds],
  )

  return { positions, activeCues }
}
