/* WorldSeed — Map layout: collage-style positioning, entity categorization.
 * Scene type driven — zero hardcoded entity types or property names.
 */
import { uiConfig } from './ui-config'

/** Base z-index for zone cards. Read from CSS --z-card-base at module init. */
const Z_CARD_BASE = parseInt(getComputedStyle(document.documentElement).getPropertyValue('--z-card-base')) || 5

// ── Deterministic hash for stable random values ──

export function hashStr(s: string): number {
  let h = 0
  for (let i = 0; i < s.length; i++) {
    h = ((h << 5) - h) + s.charCodeAt(i)
    h |= 0
  }
  return Math.abs(h)
}

// ── Map data computation ──

export interface MapData {
  zones: { entity: any; bind: any }[]
  items: Record<string, any[]>
  agents: Record<string, any[]>
  free: any[]
}

export function computeMapData(entities: any[]): MapData {
  const zones: MapData['zones'] = []
  const items: MapData['items'] = {}
  const agents: MapData['agents'] = {}
  const free: any[] = []

  for (const e of entities) {
    const bind = uiConfig.getBind(e)
    const st = uiConfig.getSceneType(e)

    if (st.role === 'hidden') continue

    if (st.role === 'container') {
      zones.push({ entity: e, bind })
    } else if (st.role === 'agent') {
      const zoneId = resolveLocation(e, bind.locate_by)
      if (zoneId) {
        (agents[zoneId] = agents[zoneId] || []).push(e)
      } else {
        free.push(e)
      }
    } else if (bind.locate_by) {
      const zoneId = resolveLocation(e, bind.locate_by)
      if (zoneId) {
        (items[zoneId] = items[zoneId] || []).push(e)
      } else {
        free.push(e)
      }
    } else {
      free.push(e)
    }
  }

  return { zones, items, agents, free }
}

export function resolveLocation(entity: any, locateProp: string): string {
  if (!locateProp) return ''
  const val = entity[locateProp]
  if (Array.isArray(val) && val.length > 0) return String(val[0])
  if (typeof val === 'string' && val) return val
  return ''
}

// ── Collage style: position + rotation + z-index ──

export function collageStyle(entityId: string, layout: Record<string, any>, index: number): Record<string, any> {
  const pos = layout[entityId]
  const h = hashStr(entityId)
  const rotation = pos?.rotation ?? ((h % 7) - 3) * 0.5

  if (!pos) return autoLayoutStyle(entityId, index)

  // z-index: config override (pos.z), or Z-reading order (right-lower = on top)
  const zIndex = pos.z ?? (Z_CARD_BASE + Math.round(((pos.x || 0) + (pos.y || 0)) / 80))

  return {
    position: 'absolute',
    left: (pos.x || 0) + 'px',
    top: (pos.y || 0) + 'px',
    width: (pos.w || 250) + 'px',
    height: (pos.h || 200) + 'px',
    rotate: `${rotation}deg`,
    zIndex,
  }
}

// ── Auto-layout: when no layout config ──

/** Auto-layout positions for zones without explicit layout entries.
 *  Arranged in a 3-column staggered grid with max ~15% overlap. */
export const AUTO_LAYOUT_POSITIONS = [
  { x: 60,  y: 40,  w: 260, h: 220 },
  { x: 360, y: 30,  w: 240, h: 200 },
  { x: 640, y: 50,  w: 230, h: 210 },
  { x: 160, y: 290, w: 250, h: 220 },
  { x: 450, y: 270, w: 240, h: 230 },
  { x: 720, y: 300, w: 210, h: 190 },
  { x: 60,  y: 530, w: 230, h: 190 },
  { x: 360, y: 510, w: 250, h: 200 },
]

let _autoLayoutCache: Record<string, any> = {}

/** Clear auto-layout cache — call when switching runs to prevent stale positions. */
export function clearAutoLayoutCache(): void {
  _autoLayoutCache = {}
}

/** Pure numeric auto-layout rect for a zone. Shared by autoLayoutStyle + overlay-layout. */
export function autoLayoutRect(entityId: string, index: number): { x: number; y: number; w: number; h: number; rotation: number } {
  const safeIndex = ((index % AUTO_LAYOUT_POSITIONS.length) + AUTO_LAYOUT_POSITIONS.length) % AUTO_LAYOUT_POSITIONS.length
  const pos = AUTO_LAYOUT_POSITIONS[safeIndex]
  const h = hashStr(entityId)
  const jx = ((h * 13) % 30) - 15
  const jy = ((h * 17) % 20) - 10
  return { x: pos.x + jx, y: pos.y + jy, w: pos.w, h: pos.h, rotation: ((h % 7) - 3) * 0.5 }
}

export function autoLayoutStyle(entityId: string, index: number): Record<string, any> {
  if (_autoLayoutCache[entityId]) return _autoLayoutCache[entityId]

  const r = autoLayoutRect(entityId, index)

  const style = {
    position: 'absolute',
    left: r.x + 'px',
    top: r.y + 'px',
    width: r.w + 'px',
    height: r.h + 'px',
    rotate: `${r.rotation}deg`,
    zIndex: Z_CARD_BASE + Math.round((r.x + r.y) / 80),
  }

  _autoLayoutCache[entityId] = style
  return style
}

// ── Zone color — warm paper tones for imageless zones ──
// Collage art: zones are colored paper scraps, not digital blocks.
// Single warm secondary tone per collage-art-ui 7.1 (60-30-10 rule).

export function zoneColor(_id: string): string {
  return '#E9E5DD'
}

// ── Entity position inside a zone ──

/** Density = items per 10,000 px² of zone area. Drives layout compactness. */
export function zoneDensity(totalEntities: number, zoneId: string): number {
  const pos = (uiConfig.layout || {})[zoneId]
  const w = pos ? pos.w : 250
  const h = pos ? pos.h : 200
  return totalEntities / (w * h / 10000)
}

export function entityPosInZone(
  entityIndex: number, totalEntities: number, zoneId: string, maxCardW?: number,
): { left: string; top: string } {
  const pos = (uiConfig.layout || {})[zoneId]
  const w = pos ? pos.w : 250
  const h = pos ? pos.h : 200
  const margin = 10
  const topPad = 28
  const agentPad = 54
  const usableW = w - margin * 2
  const usableH = h - topPad - agentPad

  // Use measured card width if provided, otherwise estimate
  const cardW = maxCardW || 48
  // Step = card width + minimum gap. Wider gap prevents visual crowding.
  const minStep = cardW + 12
  const cols = Math.max(1, Math.floor(usableW / minStep))
  const rows = Math.ceil(totalEntities / cols)
  const col = entityIndex % cols
  const row = Math.floor(entityIndex / cols)
  const stepX = usableW / Math.max(1, cols)
  const stepY = Math.min(44, usableH / Math.max(1, rows))

  // Jitter: max half of the gap between cards (capped at 8px)
  const seed = hashStr(zoneId + ':' + entityIndex)
  const gap = Math.max(0, stepX - cardW)
  const maxJitterX = Math.round(Math.min(gap * 0.5, 8))
  const maxJitterY = Math.round(Math.min(stepY * 0.2, 6))
  const jx = maxJitterX > 0 ? ((seed * 7) % (maxJitterX * 2 + 1)) - maxJitterX : 0
  const jy = maxJitterY > 0 ? ((seed * 11) % (maxJitterY * 2 + 1)) - maxJitterY : 0
  const x = margin + col * stepX + (stepX - cardW) * 0.5 + jx
  const y = topPad + row * stepY + jy

  return {
    left: Math.max(margin, Math.min(w - cardW - margin, x)) + 'px',
    top: Math.max(topPad, Math.min(h - agentPad - 10, y)) + 'px',
  }
}

// ── Entity rotation (tertiary tier: ±3deg) ──

export function entityRotation(entityId: string): { rotate: string } {
  const h = hashStr(entityId)
  const deg = ((h % 9) - 4) * 0.7
  return { rotate: `${deg}deg` }
}

// ── Free entity positioning ──

export function freeStyle(index: number, maxZoneBottom: number): Record<string, any> {
  const col = index % 5
  const row = Math.floor(index / 5)
  return {
    position: 'absolute',
    left: (50 + col * 160) + 'px',
    top: (maxZoneBottom + 30 + row * 60) + 'px',
  }
}

export function getMaxZoneBottom(layout: Record<string, any>): number {
  let max = 0
  for (const pos of Object.values(layout || {})) {
    max = Math.max(max, (pos.y || 0) + (pos.h || 0))
  }
  // Fallback: max bottom of auto-layout positions
  if (!max) {
    for (const ap of AUTO_LAYOUT_POSITIONS) {
      max = Math.max(max, ap.y + ap.h)
    }
  }
  return max
}

// ── Connection lines ──

export function computeConnections(zones: { entity: any; bind: any }[], layout: Record<string, any>): { x1: number; y1: number; x2: number; y2: number }[] {
  const connections: { x1: number; y1: number; x2: number; y2: number }[] = []
  const centers: Record<string, { x: number; y: number }> = {}

  for (let i = 0; i < zones.length; i++) {
    const z = zones[i]
    const pos = layout?.[z.entity.id]
    if (pos) {
      centers[z.entity.id] = {
        x: (pos.x || 0) + (pos.w || 0) / 2,
        y: (pos.y || 0) + (pos.h || 0) / 2,
      }
    } else {
      const r = autoLayoutRect(z.entity.id, i)
      centers[z.entity.id] = { x: r.x + r.w / 2, y: r.y + r.h / 2 }
    }
  }

  const drawn: Record<string, boolean> = {}
  for (const z of zones) {
    const connProp = z.bind.connections
    if (!connProp) continue
    const targets = z.entity[connProp]
    if (!Array.isArray(targets)) continue

    for (const tid of targets) {
      const key = [z.entity.id, tid].sort().join('--')
      if (drawn[key]) continue
      drawn[key] = true
      if (centers[z.entity.id] && centers[tid]) {
        connections.push({
          x1: centers[z.entity.id].x, y1: centers[z.entity.id].y,
          x2: centers[tid].x, y2: centers[tid].y,
        })
      }
    }
  }
  return connections
}
