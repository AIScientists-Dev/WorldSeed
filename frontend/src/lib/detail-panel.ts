/* WorldSeed — Shared rendering helpers: property extraction, event filtering,
 * agent color, gauge level. Zero hardcoded property names — reads bind config.
 */
import { uiConfig } from './ui-config'
import { hashStr } from './map-layout'
import { humanize } from './helpers'
import type { Entity, WorldEvent } from './types'

const METADATA_KEYS = new Set(['id', 'type', 'constraints', 'description', 'properties'])

export function getSelectedProps(entity: Entity | null): Record<string, unknown> {
  if (!entity) return {}
  const result: Record<string, unknown> = {}
  for (const [k, v] of Object.entries(entity)) {
    if (METADATA_KEYS.has(k)) continue
    result[k] = v
  }
  return result
}

export function getSelectedEvents(events: WorldEvent[], entityId: string, limit: number): WorldEvent[] {
  if (!entityId || !events) return []
  return events
    .filter(e => e.source === entityId || e.target === entityId ||
      (e.detail && e.detail.includes(entityId)))
    .slice(-limit)
}

export function getMainEntry(entity: Entity): { key: string; value: string } {
  const bind = uiConfig.getBind(entity)
  const showProps = bind.show || []
  for (const key of showProps) {
    const val = entity[key]
    if (val != null) return { key, value: `${val}` }
  }
  if (bind.bar) {
    const val = entity[bind.bar]
    if (val != null) return { key: bind.bar, value: `${val}` }
  }
  return { key: '', value: '' }
}

/** First non-null show value from bind.show array. */
export function getShowValue(entity: any, bind: Record<string, any>): unknown {
  const fields: string[] = Array.isArray(bind.show) ? bind.show : []
  for (const f of fields) {
    const v = entity[f]
    if (v != null && v !== '') return v
  }
  return null
}

/** Bar state from bind config. */
export function getBarState(entity: any, bind: Record<string, any>): { barVal: number; barMax: number; hasBar: boolean } {
  const barVal = bind.bar ? Number(entity[bind.bar]) : NaN
  const barMax = bind.bar_max ?? 100
  return { barVal, barMax, hasBar: !isNaN(barVal) }
}

/** Gauge bar percentage, clamped 0-100. */
export function gaugePct(value: number, max: number): number {
  if (max <= 0) return 0
  return Math.max(0, Math.min(100, (value / max) * 100))
}

/** Gauge bar color level based on value/max ratio. Maps to CSS data-level attribute. */
export type GaugeLevel = 'good' | 'warn' | 'crit'

export function gaugeLevel(value: number, max: number): GaugeLevel {
  if (max <= 0) return 'crit'
  const ratio = value / max
  if (ratio > 0.6) return 'good'
  if (ratio > 0.3) return 'warn'
  return 'crit'
}

/** Display name for any entity: bind.label property, falling back to humanized entity ID. */
export function entityLabel(entity: any, bind?: Record<string, any>): string {
  const b = bind || uiConfig.getBind(entity)
  const lp = b.label
  return lp && entity[lp] != null ? humanize(String(entity[lp])) : humanize(entity.id)
}

export function agentColor(agentId: string): string {
  return `hsl(${hashStr(agentId) % 360}, 45%, 62%)`
}
