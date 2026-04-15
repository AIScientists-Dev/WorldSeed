/* WorldSeed — Agent detail content for the right sidebar.
 * Pure renderer — receives `tab` prop, renders the matching content.
 * Layout (tabs, GM footer) is managed by MapDetailPanel.
 * Data source: agentStore (populated by pollAgentData in usePolling).
 */
import { useMemo } from 'react'
import { useTranslation } from 'react-i18next'
import { useAgentStore } from '@/stores/agent'
import { useWorldStore } from '@/stores/world'
import { formatVal, buildRawLogHtml } from '@/lib/helpers'
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '@/components/ui/collapsible'
import PropValue from './PropValue'

interface Props {
  agentId: string
  tab: 'overview' | 'session'
}

export default function AgentDetailPanel({ agentId, tab }: Props) {
  const { t } = useTranslation()
  const agentCharacter = useAgentStore(s => s.agentCharacter)
  const agentPerception = useAgentStore(s => s.agentPerception)
  const agentInbox = useAgentStore(s => s.agentInbox)
  const agentLogs = useAgentStore(s => s.agentLogs)
  const agentLoading = useAgentStore(s => s.agentLoading)
  const entities = useWorldStore(s => s.entities)

  // --- Derived values ---

  const agentSelf = agentPerception?.self_state || null

  const agentVisibleList = useMemo(() => {
    if (!agentPerception) return []
    const list: { id: string; kind: string; props: string }[] = []
    const fmt = (p: unknown) => {
      if (!p || typeof p !== 'object') return ''
      return Object.entries(p as Record<string, unknown>)
        .map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`)
        .join(', ')
    }
    for (const [id, p] of Object.entries(agentPerception.nearby_agents || agentPerception.visible_agents || {}))
      list.push({ id, kind: 'agent', props: fmt(p) })
    for (const [id, p] of Object.entries(agentPerception.nearby_entities || agentPerception.visible_entities || {}))
      list.push({ id, kind: 'entity', props: fmt(p) })
    return list
  }, [agentPerception])

  const agentHiddenEntities = useMemo(() => {
    if (!agentPerception) return []
    const vis = new Set(agentVisibleList.map(v => v.id))
    return entities.filter(e => e.id !== agentId && !vis.has(e.id))
  }, [agentPerception, agentId, agentVisibleList, entities])

  const agentWhispers = agentInbox?.whispers || []
  const agentEvts = agentInbox?.events || []
  const agentInboxTotal = agentWhispers.length + agentEvts.length

  const rawLogHtml = useMemo(
    () => agentLogs?.messages ? buildRawLogHtml(agentLogs.messages) : '',
    [agentLogs],
  )

  // --- Render ---

  if (agentLoading) return <div className="empty">{t('agent.loading')}</div>

  if (tab === 'session') {
    return rawLogHtml
      ? <div dangerouslySetInnerHTML={{ __html: rawLogHtml }}></div>
      : <div className="empty">{t('agent.noSessionData')}</div>
  }

  // --- Overview tab ---
  return (
    <>
      {agentCharacter && (
        <div className="section">
          <div className="section-hdr">{t('agent.character')}</div>
          {Object.entries(agentCharacter).map(([k, v]: [string, any]) => (
            <div key={k} className="char-field">
              <span className="char-key">{k}:</span>
              <span className="char-val"><PropValue val={v} /></span>
            </div>
          ))}
        </div>
      )}

      {agentSelf && (
        <div className="section">
          <div className="section-hdr">{t('agent.selfState')}</div>
          {Object.entries(agentSelf).map(([k, v]: [string, any]) => (
            <div key={k} className="prop-row">
              <span className="prop-k">{k}:</span>
              <span className="prop-v">{formatVal(v)}</span>
            </div>
          ))}
        </div>
      )}

      <Collapsible>
        <div className="section">
          <CollapsibleTrigger asChild>
            <div className="section-hdr" style={{ cursor: 'pointer' }}>
              {t('agent.visible')}
              <span className="section-count">{agentVisibleList.length}</span>
            </div>
          </CollapsibleTrigger>
          <CollapsibleContent>
            {!agentVisibleList.length && <div className="text-muted pad-sm">{t('agent.nothingVisible')}</div>}
            {agentVisibleList.map(item => (
              <div key={item.id} className="vis-entity">
                <span className="vis-id">{item.id}</span>
                <span className="vis-type">({item.kind})</span>
                {item.props && <div className="vis-props">{item.props}</div>}
              </div>
            ))}
            {agentHiddenEntities.length > 0 && (
              <div className="hidden-section">
                <div className="section-hdr hidden-hdr">{t('agent.hiddenFromAgent')}</div>
                {agentHiddenEntities.map(e => (
                  <div key={e.id} className="vis-hidden">{e.id} ({e.type})</div>
                ))}
              </div>
            )}
          </CollapsibleContent>
        </div>
      </Collapsible>

      <Collapsible>
        <div className="section">
          <CollapsibleTrigger asChild>
            <div className="section-hdr" style={{ cursor: 'pointer' }}>
              {t('agent.inbox')}
              {agentInboxTotal > 0 && <span className="section-count">{agentInboxTotal}</span>}
            </div>
          </CollapsibleTrigger>
          <CollapsibleContent>
            {!agentInboxTotal && <div className="text-muted pad-sm">{t('agent.empty')}</div>}
            {agentWhispers.map((m: any, i: number) => (
              <div key={'dm' + i} className={`inbox-item is-whisper${m._pending ? ' opacity-50' : ''}`}>
                <span className="inbox-tick">t{m.tick}</span>
                <span className={`inbox-src${m.source === 'gm' ? ' gm' : ''}`}>{m.source}</span>:
                {' '}{m.detail}
              </div>
            ))}
            {agentEvts.map((e: any, i: number) => (
              <div key={'ev' + i} className="inbox-item is-evt">
                <span className="inbox-tick">t{e.tick}</span>
                <span className="inbox-src">{e.source}</span>
                {' '}{e.type}: {e.detail}
              </div>
            ))}
          </CollapsibleContent>
        </div>
      </Collapsible>
    </>
  )
}
