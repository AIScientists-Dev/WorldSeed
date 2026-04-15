import { LS_RIGHT_TAB } from '@/lib/constants'
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useWorldStore } from '@/stores/world'
import { useUIStore, type RightTab } from '@/stores/ui'
import { useEntityEdit } from '@/hooks/useEntityEdit'
import { formatVal } from '@/lib/helpers'
import type { Entity } from '@/lib/types'

export default function GmView() {
  const { t } = useTranslation()
  const entities = useWorldStore(s => s.entities)
  const actionDefs = useWorldStore(s => s.actionDefs)
  const deltas = useWorldStore(s => s.deltas)
  const openEntities = useUIStore(s => s.openEntities)
  const editingProp = useUIStore(s => s.editingProp)
  const savedProp = useUIStore(s => s.savedProp)
  const toggleEntity = useUIStore(s => s.toggleEntity)
  const setUI = useUIStore(s => s.set)
  const { startEditProperty, cancelEditProperty, saveProperty } = useEntityEdit()

  function goBack() {
    setUI({ rightTab: 'stream' as RightTab })
    localStorage.setItem(LS_RIGHT_TAB, 'stream')
  }

  const groupedEntities = useMemo(() => {
    const g: Record<string, Entity[]> = {}
    entities.forEach(e => (g[e.type || 'unknown'] = g[e.type || 'unknown'] || []).push(e))
    const s: Record<string, Entity[]> = {}
    Object.keys(g).sort((a, b) => a === 'agent' ? -1 : b === 'agent' ? 1 : a.localeCompare(b)).forEach(k => { s[k] = g[k] })
    return s
  }, [entities])

  function getDelta(eid: string, key: string) { return deltas[`${eid}:${key}`] || null }

  return (
    <>
      <div className="panel-hdr">
        <button className="map-detail-back" onClick={goBack} title={t('map.backToStream')}>{'\u2190'}</button>
        <span className="panel-label">{t('gm.data')}</span>
      </div>
      <div className="panel-body">
        {Object.keys(actionDefs).length > 0 && (
          <div className="section">
            <div className="section-hdr">{t('gm.actions')}</div>
            <div className="action-bar">
              {Object.entries(actionDefs).map(([name, def]: [string, any]) => (
                <span key={name} className="action-chip" title={def.description}>{name}</span>
              ))}
            </div>
          </div>
        )}
        {Object.entries(groupedEntities).map(([type, group]) => (
          <div key={type}>
            <div className="ent-group-hdr">{type} ({group.length})</div>
            {group.map(e => (
              <div key={e.id} className={`ent-card${e.type === 'agent' ? ' is-agent' : ''}`} onClick={() => toggleEntity(e.id)}>
                <div className="ent-id">{e.id}</div>
                <div className="ent-detail" style={{ display: openEntities[e.id] === false ? 'none' : undefined }}>
                  {Object.entries(e.properties || {}).filter(([k]) => k !== 'relationships' && k !== 'constraints').map(([k, v]) => (
                    <div key={k} className="prop-row">
                      <span className="prop-k">{k}:</span>
                      {editingProp.entity === e.id && editingProp.key === k ? (
                        <input className="prop-edit-input"
                               value={editingProp.value || ''}
                               onChange={ev => useUIStore.setState({ editingProp: { ...editingProp, value: ev.target.value } })}
                               onKeyDown={ev => {
                                 if (ev.key === 'Enter') saveProperty(e.id, k)
                                 if (ev.key === 'Escape') cancelEditProperty()
                               }}
                               onBlur={() => saveProperty(e.id, k)}
                               onClick={ev => ev.stopPropagation()} />
                      ) : (
                        <>
                          <span className="prop-v prop-editable" onClick={ev => { ev.stopPropagation(); startEditProperty(e.id, k, v) }}>{formatVal(v)}</span>
                          {getDelta(e.id, k) && (
                            <span className="delta-marker">({getDelta(e.id, k).text})</span>
                          )}
                          {savedProp.entity === e.id && savedProp.key === k && (
                            <span className="prop-saved">{t('gm.appliesNextTick')}</span>
                          )}
                        </>
                      )}
                    </div>
                  ))}
                  {e.relationships && (e.relationships as any[]).length > 0 && (
                    <div className="rel-row">
                      {(e.relationships as any[]).map((r: any, i: number) => (
                        <span key={i} className="rel-tag">
                          {r.type} {'\u2192'} {r.target}{r.value != null && <> ({r.value})</>}
                        </span>
                      ))}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        ))}
    </div>
    </>
  )
}
