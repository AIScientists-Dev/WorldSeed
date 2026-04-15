/* WorldSeed — Overlay layout: pure-math positioning for bubbles.
 *
 * Pretext philosophy: measure once (subtitle-measure.ts), layout many times
 * (this file). Zero DOM queries. Same input = same output.
 *
 * Pipeline: entities + zone layout → agent anchors → bubble positions (with dodge + clamp).
 */

import type { MeasuredCue } from './subtitle-types'
import type { MapData } from './map-layout'
import { hashStr, autoLayoutRect } from './map-layout'

// ── Types ──

export interface AgentAnchor {
  agentId: string
  /** Center X of agent dot in map-canvas coordinates */
  cx: number
  /** Top Y of agent dot in map-canvas coordinates */
  topY: number
}

interface Rect {
  x: number
  y: number
  w: number
  h: number
}

// ── Chrome constants — must match OverlayBubble.tsx CSS exactly ──

const DOT = 30 // .agent-dot width (worldview.css)
const DOT_GAP = 6     // gap-1.5
const BOTTOM_PAD = 2  // style={{ bottom: 2 }}

export const BUBBLE_CHROME = {
  avatarW: 28,  // h-7 w-7
  gap: 8,       // gap-2
  padX: 12,     // px-3
  padY: 6,      // py-1.5
  nameH: 21,    // badge: 10px*1.25 lh ≈ 13px + 4px pad (py-0.5) + 4px margin (mb-1)
  margin: 6,    // gap between bubble bottom and agent dot top
} as const

// ── Agent anchor computation (pure math from zone layout) ──

export function computeAgentAnchors(
  mapData: MapData,
  layout: Record<string, any>,
): AgentAnchor[] {
  const anchors: AgentAnchor[] = []

  for (let zi = 0; zi < mapData.zones.length; zi++) {
    const zone = mapData.zones[zi]
    const agents = mapData.agents[zone.entity.id] || []
    if (agents.length === 0) continue

    // Use explicit layout or auto-layout fallback
    const pos = layout[zone.entity.id]
    let zoneX: number, zoneY: number, zoneW: number, zoneH: number, rotation: number
    if (pos) {
      zoneX = pos.x || 0
      zoneY = pos.y || 0
      zoneW = pos.w || 250
      zoneH = pos.h || 200
      rotation = pos.rotation ?? ((hashStr(zone.entity.id) % 7) - 3) * 0.5
    } else {
      const r = autoLayoutRect(zone.entity.id, zi)
      zoneX = r.x; zoneY = r.y; zoneW = r.w; zoneH = r.h; rotation = r.rotation
    }
    const rad = rotation * Math.PI / 180
    const zoneCx = zoneX + zoneW / 2
    const zoneCy = zoneY + zoneH / 2

    const agentsPerRow = Math.max(1, Math.floor((zoneW + DOT_GAP) / (DOT + DOT_GAP)))

    for (let i = 0; i < agents.length; i++) {
      const row = Math.floor(i / agentsPerRow)
      const col = i % agentsPerRow
      const colsInRow = Math.min(agentsPerRow, agents.length - row * agentsPerRow)
      const rowW = colsInRow * DOT + (colsInRow - 1) * DOT_GAP
      const rowStartX = zoneX + (zoneW - rowW) / 2

      // Position in unrotated zone space.
      // CSS flex-wrap stacks rows top-down within the bottom-anchored container.
      // Row 0 is furthest from zone bottom (highest), row N is nearest.
      const totalRows = Math.ceil(agents.length / agentsPerRow)
      const containerH = totalRows * DOT + (totalRows - 1) * DOT_GAP
      let cx = rowStartX + col * (DOT + DOT_GAP) + DOT / 2
      let topY = zoneY + zoneH - BOTTOM_PAD - containerH + row * (DOT + DOT_GAP)

      // Apply zone rotation around zone center
      if (Math.abs(rotation) > 0.01) {
        const rx = cx - zoneCx
        const ry = topY - zoneCy
        cx = zoneCx + rx * Math.cos(rad) - ry * Math.sin(rad)
        topY = zoneCy + rx * Math.sin(rad) + ry * Math.cos(rad)
      }

      anchors.push({ agentId: agents[i].id, cx, topY })
    }
  }

  return anchors
}

// ── Bubble dimensions from pretext measurements ──

export function bubbleSize(cue: MeasuredCue): { w: number; h: number } {
  const textContainerW = cue.textW + BUBBLE_CHROME.padX * 2
  return {
    w: BUBBLE_CHROME.avatarW + BUBBLE_CHROME.gap + textContainerW,
    h: BUBBLE_CHROME.nameH + cue.textH + BUBBLE_CHROME.padY * 2,
  }
}

// ── Layout: position all bubbles with dodge + clamp ──

const DODGE_GAP = 4

function overlaps(a: Rect, b: Rect): boolean {
  return a.x < b.x + b.w + DODGE_GAP && a.x + a.w + DODGE_GAP > b.x
      && a.y < b.y + b.h + DODGE_GAP && a.y + a.h + DODGE_GAP > b.y
}

function clamp(r: Rect, bounds: Rect): Rect {
  return {
    x: Math.max(bounds.x + DODGE_GAP, Math.min(r.x, bounds.x + bounds.w - r.w - DODGE_GAP)),
    y: Math.max(bounds.y + DODGE_GAP, Math.min(r.y, bounds.y + bounds.h - r.h - DODGE_GAP)),
    w: r.w,
    h: r.h,
  }
}

export function computeOverlayLayout(
  cues: Array<{ cue: MeasuredCue; status: 'current' | 'fading' }>,
  anchors: AgentAnchor[],
  canvasBounds: { w: number; h: number },
): Map<string, { x: number; y: number }> {
  const anchorMap = new Map(anchors.map(a => [a.agentId, a]))
  const bounds: Rect = { x: 0, y: 0, w: canvasBounds.w, h: canvasBounds.h }
  const placed: Rect[] = []
  const result = new Map<string, { x: number; y: number }>()

  // Group cues by agent, then stack per-agent (newest at bottom, closest to dot)
  const byAgent = new Map<string, typeof cues>()
  for (const entry of cues) {
    const list = byAgent.get(entry.cue.agentId) || []
    list.push(entry)
    byAgent.set(entry.cue.agentId, list)
  }

  // Process agents sorted by anchor cx for deterministic dodge
  const sortedAgents = [...byAgent.keys()].sort((a, b) => {
    const aa = anchorMap.get(a)
    const ab = anchorMap.get(b)
    return (aa?.cx ?? 0) - (ab?.cx ?? 0)
  })

  for (const agentId of sortedAgents) {
    const anchor = anchorMap.get(agentId)
    const agentCues = byAgent.get(agentId)!
    // Agents without an anchor (not in any zone) stack at bottom of canvas
    let stackY = anchor ? anchor.topY - BUBBLE_CHROME.margin : canvasBounds.h - BUBBLE_CHROME.margin - DOT

    for (const entry of agentCues) {
      const size = bubbleSize(entry.cue)
      const baseX = anchor ? anchor.cx - size.w / 2 : DODGE_GAP
      stackY -= size.h

      let rect: Rect = { x: baseX, y: stackY, w: size.w, h: size.h }
      rect = clamp(rect, bounds)

      // Dodge: if overlapping with any placed rect, try shifting
      if (placed.some(p => overlaps(rect, p))) {
        // Try right
        const rightRect = clamp({ ...rect, x: rect.x + size.w + DODGE_GAP }, bounds)
        if (!placed.some(p => overlaps(rightRect, p))) {
          rect = rightRect
        } else {
          // Try left
          const leftRect = clamp({ ...rect, x: rect.x - size.w - DODGE_GAP }, bounds)
          if (!placed.some(p => overlaps(leftRect, p))) {
            rect = leftRect
          } else {
            // Push up
            let pushY = rect.y
            for (const p of placed) {
              if (overlaps({ ...rect, y: pushY }, p)) {
                pushY = Math.min(pushY, p.y - size.h - DODGE_GAP)
              }
            }
            rect = clamp({ ...rect, y: pushY }, bounds)
          }
        }
      }

      placed.push(rect)
      result.set(entry.cue.id, { x: rect.x, y: rect.y })
      stackY = rect.y - DODGE_GAP
    }
  }

  return result
}
