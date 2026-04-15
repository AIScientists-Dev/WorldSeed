import { useRef, useEffect, useMemo, useState, useCallback } from 'react'
import { useTranslation } from 'react-i18next'
import { useAgentStore } from '@/stores/agent'
import { useWorldStore } from '@/stores/world'
import { useUIStore } from '@/stores/ui'
import { useCommands } from '@/hooks/useCommands'
import { usePanelResize } from '@/hooks/usePanelResize'
import { formatVal, buildRawLogHtml } from '@/lib/helpers'
import { LS_THINKING_W } from '@/lib/constants'
import { PaperPlaneTilt, BellRinging } from '@phosphor-icons/react'

export default function AgentView() {
  const { t } = useTranslation()
  const selectedAgent = useAgentStore(s => s.selectedAgent)
  const agentLoading = useAgentStore(s => s.agentLoading)
  const agentCharacter = useAgentStore(s => s.agentCharacter)
  const agentPerception = useAgentStore(s => s.agentPerception)
  const agentInbox = useAgentStore(s => s.agentInbox)
  const agentLogs = useAgentStore(s => s.agentLogs)
  const entities = useWorldStore(s => s.entities)
  const viewingRunId = useWorldStore(s => s.viewingRunId)
  const whisperText = useUIStore(s => s.whisperText)
  const gmFeedback = useUIStore(s => s.gmFeedback)
  const { cmdWhisper, cmdGmNotify } = useCommands()

  const [wakeSent, setWakeSent] = useState(false)
  const handleWake = useCallback(async (id: string) => {
    const ok = await cmdGmNotify(id)
    if (ok) {
      setWakeSent(true)
      setTimeout(() => setWakeSent(false), 1500)
    }
  }, [cmdGmNotify])
  const { makeDragHandler } = usePanelResize()

  const thinkingPanel = useRef<HTMLDivElement>(null)
  const startResizeV = useMemo(
    () => makeDragHandler(() => thinkingPanel.current, 'x', LS_THINKING_W, 200, 0.7),
    [makeDragHandler],
  )

  // Derived values
  const agentSelf = agentPerception?.self_state || null
  const agentVisibleList = useMemo(() => {
    if (!agentPerception) return []
    const list: any[] = []
    const fmt = (p: any) => p && typeof p === 'object' ? Object.entries(p).map(([k, v]) => `${k}: ${typeof v === 'object' ? JSON.stringify(v) : v}`).join(', ') : ''
    Object.entries(agentPerception.nearby_agents || agentPerception.visible_agents || {}).forEach(([id, p]) => list.push({ id, kind: 'agent', props: fmt(p) }))
    Object.entries(agentPerception.nearby_entities || agentPerception.visible_entities || {}).forEach(([id, p]) => list.push({ id, kind: 'entity', props: fmt(p) }))
    return list
  }, [agentPerception])

  const agentHiddenEntities = useMemo(() => {
    if (!agentPerception || !selectedAgent) return []
    const vis = new Set(agentVisibleList.map(v => v.id))
    return entities.filter(e => e.id !== selectedAgent && !vis.has(e.id))
  }, [agentPerception, selectedAgent, agentVisibleList, entities])

  const agentWhispers = agentInbox?.whispers || []
  const agentEvents = agentInbox?.events || []
  const agentInboxTotal = agentWhispers.length + agentEvents.length

  const rawLogHtml = useMemo(
    () => agentLogs?.messages ? buildRawLogHtml(agentLogs.messages) : '',
    [agentLogs],
  )

  // Restore panel width from localStorage
  useEffect(() => {
    if (thinkingPanel.current) {
      const w = localStorage.getItem(LS_THINKING_W)
      if (w) { thinkingPanel.current.style.flex = 'none'; thinkingPanel.current.style.width = w }
    }
  }, [])

  return (
    <>
      {/* Left: World Data */}
      <div className="panel">
        <div className="panel-hdr">
          <span className="panel-label">{selectedAgent}</span>
        </div>
        <div className="panel-body">
          {agentLoading ? (
            <div className="empty">{t('agent.loading')}</div>
          ) : (
            <>
              {agentCharacter && (
                <div className="section">
                  <div className="section-hdr">{t('agent.character')}</div>
                  {Object.entries(agentCharacter).map(([k, v]: [string, any]) => (
                    <div key={k} className="char-field">
                      <span className="char-key">{k}:</span>
                      <span className="char-val">{Array.isArray(v) ? v.join(', ') : (typeof v === 'object' && v !== null ? JSON.stringify(v) : String(v))}</span>
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

              <div className="section">
                <div className="section-hdr">{t('agent.visible')}</div>
                {!agentVisibleList.length && <div className="text-muted pad-sm">{t('agent.nothingVisible')}</div>}
                {agentVisibleList.map((item: any) => (
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
              </div>

              <div className="section">
                <div className="section-hdr">
                  {t('agent.inbox')}
                  {agentInboxTotal > 0 && <span className="section-count">{agentInboxTotal}</span>}
                </div>
                {!agentInboxTotal && <div className="text-muted pad-sm">{t('agent.empty')}</div>}
                {agentWhispers.map((m: any, i: number) => (
                  <div key={'dm' + i} className={`inbox-item is-whisper${m._pending ? ' opacity-50' : ''}`}>
                    <span className="inbox-tick">t{m.tick}</span>
                    <span className={`inbox-src${m.source === 'gm' ? ' gm' : ''}`}>{m.source}</span>:
                    {' '}{m.detail}
                  </div>
                ))}
                {agentEvents.map((e: any, i: number) => (
                  <div key={'ev' + i} className="inbox-item is-evt">
                    <span className="inbox-tick">t{e.tick}</span>
                    <span className="inbox-src">{e.source}</span>
                    {' '}{e.type}: {e.detail}
                  </div>
                ))}
              </div>

              <div className="section whisper-controls">
                <div className="section-hdr">{t('agent.whisper')}</div>
                <div className="whisper-row">
                  <input className="whisper-input"
                         value={whisperText}
                         onChange={e => useUIStore.setState({ whisperText: e.target.value })}
                         placeholder={t('agent.whisperPlaceholder')}
                         onKeyDown={e => { if (e.key === 'Enter' && selectedAgent) cmdWhisper(selectedAgent) }} />
                  <button className="btn-sm" onClick={() => selectedAgent && cmdWhisper(selectedAgent)} title={t('agent.sendWhisper')}><PaperPlaneTilt size={14} /></button>
                  <button className="btn-sm" disabled={wakeSent} onClick={() => selectedAgent && handleWake(selectedAgent)} title={t('agent.wakeAgent')}><BellRinging size={14} className={wakeSent ? 'text-sage' : ''} /></button>
                </div>
                {gmFeedback && <div className="whisper-feedback">{gmFeedback}</div>}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Vertical resize handle */}
      <div className="resize-handle-v" onMouseDown={startResizeV}></div>

      {/* Right: Session */}
      <div className="panel panel-thinking" ref={thinkingPanel}>
        <div className="panel-hdr">
          <span className="panel-label">{selectedAgent} {'\u2014'} {t('agent.session')} ({viewingRunId.slice(0, 8)})</span>
        </div>
        <div className="panel-body">
          {agentLoading ? (
            <div className="empty">{t('agent.loading')}</div>
          ) : rawLogHtml ? (
            <div dangerouslySetInnerHTML={{ __html: rawLogHtml }}></div>
          ) : (
            <div className="empty">{t('agent.noSessionData')}</div>
          )}
        </div>
      </div>
    </>
  )
}
