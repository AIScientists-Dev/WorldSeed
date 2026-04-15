/* WorldSeed — EntityCard: renders a single entity item on the map.
 *
 * Handles: asset image, fallback text, gauge bar, state effects, value display.
 * Text is pre-measured with pretext and truncated to card width.
 * Click → detail panel shows full properties.
 * Positioning is external — caller provides style prop.
 */

import { useState, useCallback, useMemo } from 'react'
import { uiConfig } from '@/lib/ui-config'
import { matchStateEffect } from '@/lib/state-effects'
import { getMainEntry, gaugeLevel, gaugePct, getBarState, entityLabel } from '@/lib/detail-panel'
import { humanize } from '@/lib/helpers'
import { truncateEntityText } from '@/lib/subtitle-measure'

// ── Helpers ──────────────────────────────────────────────

function entityStateClass(entity: any, bind: Record<string, any>): string {
  const effects = bind.state_effects
  if (!effects) return ''
  const preset = matchStateEffect(entity, effects)
  return preset ? `entity-state-${preset}` : ''
}

// ── EntityCard ───────────────────────────────────────────

interface Props {
  ent: any
  onSelect: (id: string) => void
  style?: React.CSSProperties
  compact?: boolean
}

export default function EntityCard({ ent, onSelect, style, compact }: Props) {
  const assetUrl = uiConfig.assetUrl(ent)
  const bind = uiConfig.getBind(ent)
  const stateClass = entityStateClass(ent, bind)
  const { barVal, barMax, hasBar } = getBarState(ent, bind)
  const { value: mainValue } = getMainEntry(ent)
  const showValue = mainValue && !hasBar
  const displayValue = showValue
    ? (isFinite(Number(mainValue)) ? mainValue : humanize(mainValue))
    : ''
  const [imgFailed, setImgFailed] = useState(false)
  const hasImg = !!assetUrl && !imgFailed
  const onImgError = useCallback(() => setImgFailed(true), [])
  const name = entityLabel(ent, bind)
  const truncName = useMemo(() => !hasImg ? truncateEntityText(name, 'fallback', compact).text : name, [hasImg, name, compact])
  const truncValue = useMemo(() => displayValue ? truncateEntityText(displayValue, 'value', compact).text : '', [displayValue, compact])

  return (
    <div
      className={`entity-card${compact ? ' entity-card-compact' : ''}${stateClass ? ` ${stateClass}` : ''}`}
      data-entity-id={ent.id}
      style={style}
      onClick={(e) => { e.stopPropagation(); onSelect(ent.id) }}
    >
      {hasImg && <img className="entity-card-img" src={assetUrl} alt={name} onError={onImgError} />}
      {hasImg && <div className="entity-card-label">{name}</div>}
      {!hasImg && <div className="entity-card-fallback">{truncName}</div>}
      {truncValue && <div className="entity-card-value">{truncValue}</div>}
      {hasBar && (
        <div className="entity-gauge-track">
          <div
            className="entity-gauge-fill"
            data-level={gaugeLevel(barVal, barMax)}
            style={{ width: `${gaugePct(barVal, barMax)}%` }}
          />
        </div>
      )}
    </div>
  )
}
