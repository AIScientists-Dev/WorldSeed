/* WorldSeed — Map detail panel (right sidebar).
 * Dispatches between agent view and entity view based on entity type.
 * For agents: manages tabs (Overview/Session) and pinned GM input.
 */
import { useMemo, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useWorldStore } from '@/stores/world'
import { useAgentStore } from '@/stores/agent'
import { useEntities } from '@/hooks/useWorldState'
import { uiConfig } from '@/lib/ui-config'
import { getSelectedProps, getSelectedEvents, gaugeLevel, gaugePct, entityLabel } from '@/lib/detail-panel'
import { AutoScrollPanel } from '@/components/ui/auto-scroll'
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '@/components/ui/collapsible'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { ScrollArea } from '@/components/ui/scroll-area'
import { SortAscending, Clock } from '@phosphor-icons/react'
import { computeMapData } from '@/lib/map-layout'
import { humanize } from '@/lib/helpers'
import AgentDetailPanel from './AgentDetailPanel'
import PropValue from './PropValue'

interface Props {
  selectedId: string | null
  onSelect: (id: string) => void
  onDeselect: () => void
}

export default function MapDetailPanel({ selectedId, onSelect, onDeselect }: Props) {
  const { t } = useTranslation()
  const entities = useEntities()
  const events = useWorldStore(s => s.events)
  const viewingRunId = useWorldStore(s => s.viewingRunId)
  const agentLogs = useAgentStore(s => s.agentLogs)
  const [agentTab, setAgentTab] = useState<'overview' | 'session'>('overview')
  const [navStack, setNavStack] = useState<string[]>([])
  const [lastDrillTarget, setLastDrillTarget] = useState<string | null>(null)

  // Reset navStack when selection changes externally (not via drillIn)
  if (selectedId && selectedId !== lastDrillTarget && navStack.length > 0) {
    setNavStack([])
    setLastDrillTarget(null)
  }

  const drillIn = useCallback((itemId: string) => {
    if (selectedId) setNavStack(prev => [...prev, selectedId])
    setLastDrillTarget(itemId)
    onSelect(itemId)
  }, [selectedId, onSelect])

  const goBack = useCallback(() => {
    if (navStack.length > 0) {
      const prev = navStack[navStack.length - 1]
      setNavStack(s => s.slice(0, -1))
      onSelect(prev)
    } else {
      onDeselect()
    }
  }, [navStack, onSelect, onDeselect])

  const entity = useMemo(
    () => selectedId ? entities.find(e => e.id === selectedId) || null : null,
    [selectedId, entities],
  )

  const isAgent = entity?.type === 'agent'
  const art = useMemo(() => entity ? uiConfig.assetUrl(entity) : '', [entity])

  // --- Entity-only data (skip computation for agents) ---
  const entityProps = useMemo(() => isAgent ? {} : getSelectedProps(entity), [entity, isAgent])
  const selectedEvents = useMemo(
    () => isAgent ? [] : getSelectedEvents(events, selectedId || '', 20),
    [events, selectedId, isAgent],
  )
  const contains = useMemo(() => {
    if (!selectedId || isAgent) return []
    const mapData = computeMapData(entities)
    const result: any[] = []
    for (const [zoneId, ents] of Object.entries(mapData.items)) {
      if (zoneId === selectedId) result.push(...(ents as any[]))
    }
    return [...result, ...(mapData.agents[selectedId] || [])]
  }, [selectedId, entities, isAgent])

  // --- Agent view ---
  if (isAgent) {
    return (
      <div className="panel detail-panel">
        {/* Header */}
        <div className="panel-hdr">
          <button className="map-detail-back" onClick={goBack} title={t('map.backToStream')}>{'\u2190'}</button>
          <span className="panel-label">{humanize(selectedId || '')}</span>
          <span className="map-detail-type">{entity!.type}</span>
        </div>

        {/* Tab bar — fixed, does not scroll */}
        <div className="agent-tab-bar">
          <button
            className={`agent-tab${agentTab === 'overview' ? ' is-active' : ''}`}
            onClick={() => setAgentTab('overview')}>
            {t('map.overview')}
          </button>
          <button
            className={`agent-tab${agentTab === 'session' ? ' is-active' : ''}`}
            onClick={() => setAgentTab('session')}>
            {t('map.session')}
            {viewingRunId && <span className="agent-tab-run-id">({viewingRunId.slice(0, 6)})</span>}
          </button>
        </div>

        {/* Scrollable body — session tab auto-scrolls to bottom */}
        {agentTab === 'session' ? (
          <AutoScrollPanel className="panel-body map-detail-body" scrollViewClassName="panel-body-inner" dep={agentLogs}>
            <AgentDetailPanel agentId={selectedId!} tab="session" />
          </AutoScrollPanel>
        ) : (
          <div className="panel-body map-detail-body">
            {art && (
              <div key={'art-' + selectedId} className="map-detail-art-wrap">
                <img src={art} className="detail-art" onError={(e) => { (e.currentTarget as HTMLElement).style.display = 'none' }} />
              </div>
            )}
            <AgentDetailPanel agentId={selectedId!} tab="overview" />
          </div>
        )}

      </div>
    )
  }

  // --- Non-agent entity ---
  // Uses same section/prop-row pattern as AgentDetailPanel for consistency
  const bind = entity ? uiConfig.getBind(entity) : {} as Record<string, any>
  const barProp: string = bind.bar || ''
  const barMax: number = bind.bar_max ?? 100

  return (
    <div className="panel detail-panel">
      <div className="panel-hdr">
        <button className="map-detail-back" onClick={goBack} title={t('map.backToStream')}>{'\u2190'}</button>
        <span className="panel-label">{entity ? entityLabel(entity) : humanize(selectedId || '')}</span>
        {entity && <Badge variant="outline" className="ml-auto font-mono text-[10px] uppercase tracking-widest">{entity.type}</Badge>}
      </div>
      <div className="panel-body">
        {/* Art */}
        {art && (
          <div className="px-4 pt-3">
            <img src={art} className="detail-art w-full" onError={(e) => { (e.currentTarget as HTMLElement).style.display = 'none' }} />
          </div>
        )}

        {/* Contains — first, since this is the main reason to click a zone */}
        {contains.length > 0 && (
          <ContainsSection items={contains} onSelect={drillIn} t={t} />
        )}

        {/* Properties */}
        {Object.keys(entityProps).length > 0 && (
          <Collapsible defaultOpen>
            <div className="section">
              <CollapsibleTrigger asChild>
                <div className="section-hdr cursor-pointer">
                  {t('map.properties')}
                </div>
              </CollapsibleTrigger>
              <CollapsibleContent>
                {Object.entries(entityProps).map(([key, val]) => {
                  if (barProp && key === barProp) {
                    const num = Number(val)
                    const pct = isNaN(num) ? 0 : gaugePct(num, barMax)
                    const level = gaugeLevel(num, barMax)
                    return (
                      <div key={key} className="mb-1.5">
                        <div className="prop-row">
                          <span className="prop-k">{key}:</span>{' '}
                          <span className="prop-v">{num} / {barMax}</span>
                        </div>
                        <div className="entity-gauge-track mt-1" style={{ height: 6 }}>
                          <div className="entity-gauge-fill" data-level={level} style={{ width: `${pct}%` }} />
                        </div>
                      </div>
                    )
                  }
                  return (
                    <div key={key} className="prop-row">
                      <span className="prop-k">{key}:</span>{' '}
                      <PropValue val={val} entities={entities} onSelect={onSelect} />
                    </div>
                  )
                })}
              </CollapsibleContent>
            </div>
          </Collapsible>
        )}

        {/* Recent Events — only shows when events reference this entity */}
        {selectedEvents.length > 0 && (
          <Collapsible defaultOpen>
            <div className="section">
              <CollapsibleTrigger asChild>
                <div className="section-hdr cursor-pointer">
                  {t('map.recentEvents')}
                  <span className="section-count">{selectedEvents.length}</span>
                </div>
              </CollapsibleTrigger>
              <CollapsibleContent>
                {selectedEvents.map((evt: any, i: number) => (
                  <div key={i} className="py-1 border-b border-border text-xs text-foreground">
                    <span className="font-mono text-[10px] opacity-40">[{evt.tick}]</span> {evt.detail}
                  </div>
                ))}
              </CollapsibleContent>
            </div>
          </Collapsible>
        )}

      </div>
    </div>
  )
}

// ── Contains section ─────────────────────────────────────

type SortMode = 'time' | 'name'

function entitySeq(ent: any): number {
  const m = String(ent.id).match(/\d+/)
  return m ? Number(m[0]) : 0
}

function ContainsSection({ items, onSelect, t }: { items: any[]; onSelect: (id: string) => void; t: (k: string) => string }) {
  const [sort, setSort] = useState<SortMode>('time')

  const sorted = useMemo(() => {
    const copy = [...items]
    if (sort === 'name') copy.sort((a, b) => entityLabel(a).localeCompare(entityLabel(b)))
    else copy.sort((a, b) => entitySeq(a) - entitySeq(b))
    return copy
  }, [items, sort])

  const showSort = items.length > 3

  return (
    <div className="section">
      <div className="flex items-center justify-between mb-1.5">
        <span className="text-[11px] font-data text-muted-foreground tracking-wide">
          {items.length} {items.length === 1 ? 'item' : 'items'}
        </span>
        {showSort && (
          <div className="flex gap-0.5">
            <Button
              variant={sort === 'time' ? 'secondary' : 'ghost'}
              size="sm"
              className="h-5 px-1.5 text-[9px]"
              onClick={() => setSort('time')}
            >
              <Clock size={10} className="mr-0.5" />{t('map.sortTime')}
            </Button>
            <Button
              variant={sort === 'name' ? 'secondary' : 'ghost'}
              size="sm"
              className="h-5 px-1.5 text-[9px]"
              onClick={() => setSort('name')}
            >
              <SortAscending size={10} className="mr-0.5" />{t('map.sortName')}
            </Button>
          </div>
        )}
      </div>
      <div className="max-h-[50vh] overflow-auto">
        <ScrollArea className="h-full">
          {sorted.map((ent: any) => {
            const label = entityLabel(ent)
            return (
              <div
                key={ent.id}
                className="py-1.5 px-1.5 cursor-pointer rounded hover:bg-muted/50 transition-colors"
                onClick={() => onSelect(ent.id)}
              >
                <div className="text-xs text-foreground leading-snug">{label}</div>
                {label !== humanize(ent.id) && <div className="text-[10px] text-muted-foreground font-data mt-0.5">{ent.id}</div>}
              </div>
            )
          })}
        </ScrollArea>
      </div>
    </div>
  )
}
