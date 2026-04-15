/* WorldSeed — PropValue: recursive value renderer for detail panels.
 *
 * Renders any value type with smart layout:
 *   null → —, boolean → yes/no, array → comma-separated,
 *   object → sub-keys each on own line (recursive), string entity ref → clickable.
 * Used by both entity detail and agent detail panels.
 */

import { formatVal, humanize } from '@/lib/helpers'

interface Props {
  val: unknown
  entities?: any[]
  onSelect?: (id: string) => void
}

export default function PropValue({ val, entities = [], onSelect }: Props) {
  if (val == null) return <span className="prop-v">{'\u2014'}</span>

  if (typeof val === 'boolean') return <span className="prop-v">{val ? 'yes' : 'no'}</span>

  if (typeof val === 'number') return <span className="prop-v">{val}</span>

  if (Array.isArray(val)) {
    if (val.length === 0) return <span className="prop-v">{'\u2014'}</span>
    return (
      <span className="prop-v">
        {val.map((item, i) => {
          const isRef = onSelect && typeof item === 'string' && entities.some((e: any) => e.id === item)
          return (
            <span key={i}>
              {i > 0 && ', '}
              {isRef
                ? <span className="cursor-pointer underline decoration-border" onClick={() => onSelect(item)}>{humanize(item)}</span>
                : <>{formatVal(item)}</>
              }
            </span>
          )
        })}
      </span>
    )
  }

  if (typeof val === 'object') {
    const entries = Object.entries(val as Record<string, unknown>)
    if (entries.length === 0) return <span className="prop-v">{'\u2014'}</span>
    return (
      <div className="pl-3 mt-0.5">
        {entries.map(([k, v]) => (
          <div key={k} className="prop-row">
            <span className="prop-k">{k}:</span>{' '}
            <PropValue val={v} entities={entities} onSelect={onSelect} />
          </div>
        ))}
      </div>
    )
  }

  if (onSelect && typeof val === 'string' && entities.some((e: any) => e.id === val)) {
    return <span className="prop-v cursor-pointer underline decoration-border" onClick={() => onSelect(val)}>{humanize(val)}</span>
  }

  return <span className="prop-v">{String(val)}</span>
}
