/* WorldSeed — ZoneCard: a single zone on the collage map.
 *
 * Renders: background image, label, show subtitle, entity items.
 * Agents at bottom in a horizontal row. Each agent: avatar dot + name below.
 * Entity rendering delegated to EntityCard (shared with free entity path).
 */

import { useState, useEffect, useMemo } from 'react'
import { uiConfig } from '@/lib/ui-config'
import { entityPosInZone, entityRotation, zoneColor, hashStr, zoneDensity } from '@/lib/map-layout'
import { humanize } from '@/lib/helpers'
import { measureEntityCardWidth } from '@/lib/subtitle-measure'
import { gaugeLevel, gaugePct, getBarState, getShowValue, entityLabel } from '@/lib/detail-panel'
import EntityCard from './EntityCard'
import AgentRow from './AgentRow'

interface Props {
  zone: any
  agents: any[]
  items: any[]
  selected: boolean
  style: React.CSSProperties
  onSelect: (id: string) => void
}

function ZoneEntities({ items, zoneId, onSelect }: { items: any[]; zoneId: string; onSelect: (id: string) => void }) {
  const pos = (uiConfig.layout || {})[zoneId]
  const zoneArea = (pos?.w || 250) * (pos?.h || 200)
  const maxVisible = Math.max(4, Math.min(14, Math.floor(zoneArea / 4000)))
  const dense = zoneDensity(items.length, zoneId) > 1.5
  const visible = items.slice(0, maxVisible)

  // Measure max card width using pretext — drives positioning step size
  const maxCardW = useMemo(() => {
    if (!visible.length) return 48
    const widths = visible.map(ent => {
      const bind = uiConfig.getBind(ent)
      const displayName = entityLabel(ent, bind)
      return measureEntityCardWidth(displayName, dense)
    })
    return Math.max(...widths)
  }, [visible.map(e => e.id).join(','), dense])

  return (
    <>
      {visible.map((ent: any, ei: number) => (
        <EntityCard
          key={ent.id}
          ent={ent}
          onSelect={onSelect}
          compact={dense}
          style={{ position: 'absolute', zIndex: 2 + (hashStr(ent.id) % 5), ...entityPosInZone(ei, visible.length, zoneId, maxCardW), ...entityRotation(ent.id) }}
        />
      ))}
      {items.length > maxVisible && (
        <div
          className="absolute z-20 top-[7px] right-[6px] font-data text-[10px] font-semibold text-foreground bg-white/90 border border-border rounded px-1.5 py-0.5 shadow-sm cursor-pointer hover:bg-white hover:shadow transition-colors"
          onClick={(e) => { e.stopPropagation(); onSelect(zoneId) }}
        >
          +{items.length - maxVisible}
        </div>
      )}
    </>
  )
}

export default function ZoneCard({ zone, agents, items, selected, style, onSelect }: Props) {
  const label = entityLabel(zone.entity, zone.bind)
  const showValue = getShowValue(zone.entity, zone.bind || {})
  const { barVal, barMax, hasBar } = getBarState(zone.entity, zone.bind || {})
  const imgSrc = uiConfig.vignetteUrl(zone.entity)
  const [imgLoaded, setImgLoaded] = useState(true)
  useEffect(() => { setImgLoaded(true) }, [imgSrc])
  const hasImage = !!imgSrc && imgLoaded

  return (
    <div
      className={`zone-card${selected ? ' map-selected' : ''}`}
      data-entity-id={zone.entity.id}
      style={{ position: 'absolute', cursor: 'pointer', backgroundColor: zoneColor(zone.entity.id), ...style }}
      onClick={() => onSelect(zone.entity.id)}
    >
      {/* Background image + scrim — clipped. On img error, switch to fallback mode. */}
      {imgSrc && imgLoaded && (
        <div className="absolute inset-0 z-0 overflow-hidden rounded-sm">
          <img
            className="zone-bg-img"
            src={imgSrc}
            onError={() => setImgLoaded(false)}
          />
          <div className="zone-scrim" />
        </div>
      )}

      {/* Zone label — dark on warm paper, white on image */}
      <div className={`zone-label${!hasImage ? ' zone-label-flat' : ''}`}>
        {label}
      </div>
      {showValue != null && (
        <div
          className={`zone-subtitle${!hasImage ? ' zone-subtitle-flat' : ''}`}
        >
          {String(showValue)}
        </div>
      )}
      {/* Entity items — cap adapts to zone size, positioning uses measured widths */}
      <ZoneEntities items={items} zoneId={zone.entity.id} onSelect={onSelect} />

      {/* Agents — bottom area, clipped to zone boundary */}
      {agents.length > 0 && (
        <div
          className="absolute left-0 right-0 bottom-[2px] z-10 flex flex-wrap justify-center gap-1.5 overflow-hidden max-h-[50px]"
        >
          {agents.map((agent: any) => (
            <AgentRow key={agent.id} agent={agent} onSelect={onSelect} />
          ))}
        </div>
      )}

      {/* Zone gauge bar — above agent row */}
      {hasBar && (
        <div style={{ position: 'absolute', bottom: agents.length > 0 ? 54 : 6, left: '10%', right: '10%', zIndex: 3 }}>
          <div className="entity-gauge-track">
            <div
              className="entity-gauge-fill"
              data-level={gaugeLevel(barVal, barMax)}
              style={{ width: `${gaugePct(barVal, barMax)}%` }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
