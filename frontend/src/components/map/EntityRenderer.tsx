/* WorldSeed — EntityRenderer: renders any entity by its scene type.
 *
 * Single dispatch point for entity rendering. Both ZoneCard (for items)
 * and MapView (for free entities) use the same component types.
 * Positioning is external — caller provides style prop.
 */

import { uiConfig } from '@/lib/ui-config'
import { entityLabel } from '@/lib/detail-panel'
import EntityCard from './EntityCard'
import AgentRow from './AgentRow'

interface Props {
  entity: any
  onSelect: (id: string) => void
  selected?: boolean
  style?: React.CSSProperties
}

export default function EntityRenderer({ entity, onSelect, selected, style }: Props) {
  const st = uiConfig.getSceneType(entity)

  switch (st.role) {
    case 'agent':
      return (
        <div style={style} className={`cursor-pointer${selected ? ' map-selected' : ''}`}>
          <AgentRow agent={entity} onSelect={onSelect} />
        </div>
      )

    case 'item':
    case 'container':
      return (
        <EntityCard
          ent={entity}
          onSelect={onSelect}
          style={style}
        />
      )

    default:
      return (
        <div
          className={`map-free-entity${selected ? ' map-selected' : ''}`}
          data-entity-id={entity.id}
          style={style}
          onClick={(e) => { e.stopPropagation(); onSelect(entity.id) }}
        >
          {entityLabel(entity)}
        </div>
      )
  }
}
