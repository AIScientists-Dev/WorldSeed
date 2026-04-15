import { useState, useMemo, useRef, useEffect } from 'react'
import { useTranslation } from 'react-i18next'
import { AutoScrollPanel } from '@/components/ui/auto-scroll'
import { useStreamStore, computeStreamFilteredRecords, computeStreamGroups } from '@/stores/stream'
import type { StreamSubFilter } from '@/stores/stream'
import { useWorldStore } from '@/stores/world'
import { useReplayStore } from '@/stores/replay'
import { useUIStore } from '@/stores/ui'
import { recClass, formatEffect, formatParams, hasFreeText, extractFreeText } from '@/lib/stream-format'
import { cn } from '@/lib/utils'
import { Collapsible, CollapsibleTrigger, CollapsibleContent } from '@/components/ui/collapsible'

export default function StreamPanel() {
  const { t } = useTranslation()

  const streamRecords = useStreamStore(s => s.streamRecords)
  const streamKindFilter = useStreamStore(s => s.streamKindFilter)
  const streamSubFilter = useStreamStore(s => s.streamSubFilter)
  const streamHiddenKinds = useStreamStore(s => s.streamHiddenKinds)
  const streamAgentFilter = useStreamStore(s => s.streamAgentFilter)
  const agentTexts = useStreamStore(s => s.agentTexts)
  const setSubFilter = useStreamStore(s => s.setSubFilter)

  const events = useWorldStore(s => s.events)
  const actionDefs = useWorldStore(s => s.actionDefs)
  const systemAgents = useWorldStore(s => s.systemAgents)
  const agentsInfo = useWorldStore(s => s.agentsInfo)
  const eventFilter = useUIStore(s => s.eventFilter)

  const filteredRecords = useMemo(
    () => computeStreamFilteredRecords(streamRecords, streamKindFilter, agentTexts, 'all', streamAgentFilter, streamHiddenKinds, streamSubFilter, systemAgents),
    [streamRecords, streamKindFilter, agentTexts, streamAgentFilter, streamHiddenKinds, streamSubFilter, systemAgents],
  )
  const streamGroups = useMemo(() => computeStreamGroups(filteredRecords), [filteredRecords])
  const hasTicked = streamGroups.some(g => g.tick > 0)

  const replayActive = useReplayStore(s => s.active)
  const replayTick = useReplayStore(s => s.tick)

  const filteredEvents = useMemo(() => {
    return eventFilter ? events.filter(e => e.type === eventFilter) : events
  }, [events, eventFilter])

  // Find the nearest stream tick <= replayTick (stream ticks are sparse)
  const activeStreamTick = useMemo(() => {
    if (!replayActive || !streamGroups.length) return -1
    let best = streamGroups[0].tick
    for (const g of streamGroups) {
      if (g.tick <= replayTick) best = g.tick
      else break
    }
    return best
  }, [replayActive, replayTick, streamGroups])

  // Auto-scroll to active stream tick
  const tickRefs = useRef<Record<number, HTMLDivElement | null>>({})
  useEffect(() => {
    if (activeStreamTick < 0) return
    const el = tickRefs.current[activeStreamTick]
    if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' })
  }, [activeStreamTick])

  // Local expanded state for agent_text records (React can't mutate store objects)
  const [expandedTexts, setExpandedTexts] = useState<Set<string>>(new Set())
  function toggleExpanded(key: string) {
    setExpandedTexts(prev => {
      const next = new Set(prev)
      if (next.has(key)) next.delete(key); else next.add(key)
      return next
    })
  }

  function renderRecord(rec: any, ri: number, groupTick: number) {
    const expandKey = `${groupTick}:${ri}`
    const isExpanded = expandedTexts.has(expandKey)
    const actionType = rec.action_type || rec.action || ''

    if (rec.kind === 'action' && rec.highlight) {
      const title = rec.params?.title || ''
      const tldr = rec.params?.tldr || ''
      const body = rec.params?.body || rec.params?.summary || rec.params?.message || extractFreeText(actionDefs, actionType, rec.params || {}) || ''
      if (!title && !body) return null
      return (
        <div key={ri} className="stream-record stream-highlight">
          {title && <div className="stream-highlight-title">{title}</div>}
          {tldr && <div className="stream-highlight-tldr">{tldr}</div>}
          {body && (
            <Collapsible>
              <CollapsibleTrigger className="stream-highlight-expand">
                {t('stream.readMore', { defaultValue: 'Read more' })}
              </CollapsibleTrigger>
              <CollapsibleContent>
                <div className="stream-highlight-label">{body}</div>
              </CollapsibleContent>
            </Collapsible>
          )}
        </div>
      )
    }

    if (rec.kind === 'action' && hasFreeText(actionDefs, actionType)) {
      const freeText = extractFreeText(actionDefs, actionType, rec.params || {})
      const params = formatParams(rec.params, actionDefs, actionType)
      return (
        <div key={ri} className={cn(recClass(rec), 'is-speech')}>
          <div className="stream-dialogue">
            <span className="stream-rec-agent">{rec.agent_id}</span>
            <span className="stream-action-label">{actionType}</span>
            {params && <span className="stream-compact-params">{params}</span>}
            {rec.success === false && <span className="stream-rec-badge fail">{t('stream.fail')}</span>}
          </div>
          {freeText && <div className="stream-dialogue-text">"{freeText}"</div>}
          {rec.success === false && rec.reason && <div className="stream-fail-reason">{rec.reason}</div>}
        </div>
      )
    }

    if (rec.kind === 'action') {
      const params = formatParams(rec.params, actionDefs, actionType)
      return (
        <div key={ri} className={recClass(rec)}>
          <div className="stream-compact">
            <span className="stream-rec-agent">{rec.agent_id}</span>
            <span className="stream-action-label">{actionType}</span>
            {params && <span className="stream-compact-params">{params}</span>}
            <span className={`stream-rec-badge ${rec.success !== false ? 'success' : 'fail'}`}>
              {rec.success !== false ? '' : 'FAIL'}
            </span>
          </div>
          {rec.success === false && rec.reason && <div className="stream-fail-reason">{rec.reason}</div>}
        </div>
      )
    }

    if (rec.kind === 'dm_call' || rec.kind === 'gm_resolve') {
      const showDmDetails = streamSubFilter === 'all'
      return (
        <div key={ri} className={recClass(rec)}>
          <div className="stream-compact">
            <span className="stream-dm-tag">{t('stream.dm')}</span>
            <span className="stream-rec-agent">{rec.agent_id || t('stream.user')}</span>
            <span className="stream-action-label">{rec.action || rec.text}</span>
            {rec.params?.target && <span className="stream-rec-target">{rec.params.target}</span>}
          </div>
          {rec.narrative && <div className="stream-dm-narrative">{rec.narrative}</div>}
          {showDmDetails && rec.effects && rec.effects.length > 0 && (
            <ul className="stream-dm-effects">
              {rec.effects.map((eff: any, ei: number) => <li key={ei}>{formatEffect(eff)}</li>)}
            </ul>
          )}
          {showDmDetails && (
            <div className="stream-dm-meta">
              {(rec.tokens_in || 0)}+{(rec.tokens_out || 0)} {t('stream.tokens')}
              {rec.elapsed_s && <>{' \u00B7 '}{rec.elapsed_s}s</>}
            </div>
          )}
        </div>
      )
    }

    if (rec.kind === 'event' || rec.kind === 'consequence') {
      const displayText = rec.detail || (rec as any).name || ''
      if (!displayText) return null
      const eventType = rec.type || ''
      const isActionEcho = !!actionDefs[eventType]
      const isSpeechEvent = isActionEcho && hasFreeText(actionDefs, eventType)

      if (isSpeechEvent) {
        return (
          <div key={ri} className={cn(recClass(rec), 'is-speech')}>
            <div className="stream-dialogue">
              <span className="stream-rec-agent">{rec.source || ''}</span>
              <span className="stream-action-label">{eventType}</span>
            </div>
            <div className="stream-dialogue-text">{displayText}</div>
          </div>
        )
      }

      return (
        <div key={ri} className={recClass(rec)}>
          <div className="stream-event-line">
            <span className="stream-event-detail">{displayText}</span>
            {rec.scope && streamSubFilter === 'all' && <span className="stream-event-scope">[{rec.scope}]</span>}
          </div>
        </div>
      )
    }

    if (rec.kind === 'register') {
      return (
        <div key={ri} className={recClass(rec)}>
          <div className="stream-compact stream-meta-line">
            <span className="stream-rec-agent">{rec.agent_id}</span>
            <span className="stream-meta-text">{t('stream.joined')}</span>
          </div>
        </div>
      )
    }

    if (rec.kind === 'agent_text') {
      const text = rec.text || ''
      const displayText = isExpanded ? text : (text.length > 300 ? text.slice(0, 300) + '...' : text)
      return (
        <div key={ri} className={recClass(rec)}>
          <div className="stream-agent-text-head">
            <span className="stream-rec-agent">{rec.agent_id}</span>
          </div>
          <div className="stream-agent-text-body" onClick={() => toggleExpanded(expandKey)}>
            {displayText}
          </div>
          {isExpanded && rec.tool_calls && rec.tool_calls.length > 0 && (
            <div className="stream-agent-text-tools">
              {rec.tool_calls.map((tc: any, ti: number) => (
                <div key={ti} className="stream-agent-tc">
                  {tc.action} {Object.entries(tc.params || {}).map(([k, v]) => k + ': ' + v).join(', ')}
                </div>
              ))}
            </div>
          )}
        </div>
      )
    }

    if (rec.kind === 'highlight') {
      if (!rec.label) return null
      return (
        <div key={ri} className={recClass(rec)}>
          <div className="stream-highlight-label">{rec.label}</div>
        </div>
      )
    }

    if (rec.kind === 'whisper') {
      return (
        <div key={ri} className={recClass(rec)}>
          <div className="stream-compact">
            <span className="stream-whisper-tag">{t('stream.whisper')}</span>
            <span className="stream-rec-agent">{rec.agent_id}</span>
          </div>
          <div className="stream-whisper-text">{rec.message}</div>
        </div>
      )
    }

    if (rec.kind === 'gm_set' || rec.kind === 'gm_set_queued') {
      return (
        <div key={ri} className={recClass(rec)}>
          <div className="stream-compact">
            <span className="stream-whisper-tag">{t('stream.whisper')}</span>
            <span className="stream-rec-agent">{rec.entity_id}</span>
            <span className="stream-event-detail">{rec.property}: {rec.old} {'\u2192'} {rec.new}</span>
            {rec.kind === 'gm_set_queued' && <span className="stream-meta-text">{t('stream.nextTick')}</span>}
          </div>
        </div>
      )
    }

    if (rec.kind === 'gm_remove' || rec.kind === 'gm_remove_queued') {
      return (
        <div key={ri} className={recClass(rec)}>
          <div className="stream-compact">
            <span className="stream-whisper-tag">{t('stream.whisper')}</span>
            <span className="stream-meta-text">{t('stream.remove')}</span>
            <span className="stream-rec-agent">{rec.entity_id}</span>
            {rec.kind === 'gm_remove_queued' && <span className="stream-meta-text">{t('stream.nextTick')}</span>}
          </div>
        </div>
      )
    }

    if (rec.kind === 'gm_resolve_queued') {
      return (
        <div key={ri} className={recClass(rec)}>
          <div className="stream-compact">
            <span className="stream-whisper-tag">{t('stream.whisper')}</span>
            <span className="stream-event-detail">{rec.text}</span>
            <span className="stream-meta-text">{t('stream.nextTick')}</span>
          </div>
        </div>
      )
    }

    if (rec.kind === 'perceive') {
      return (
        <div key={ri} className={recClass(rec)}>
          <div className="stream-compact stream-meta-line">
            <span className="stream-rec-agent">{rec.agent_id}</span>
            <span className="stream-meta-text">
              {t('stream.perceive')} {(rec.visible_agent_ids || []).length}a{' '}
              {(rec.visible_entity_ids || []).length}e{' '}
              {rec.events_delivered || 0}ev
            </span>
          </div>
        </div>
      )
    }

    if (rec.kind === 'wakeup') {
      return (
        <div key={ri} className={recClass(rec)}>
          <div className="stream-compact stream-meta-line">
            <span className="stream-rec-agent">{rec.agent_id}</span>
            <span className="stream-meta-text">{t('stream.wake')} {rec.reason}</span>
          </div>
        </div>
      )
    }

    // Unknown
    return (
      <div key={ri} className={recClass(rec)}>
        <div className="stream-compact stream-meta-line">
          <span className="stream-meta-text">{rec.kind}</span>
          {rec.agent_id && <span className="stream-rec-agent">{rec.agent_id}</span>}
        </div>
      </div>
    )
  }

  return (
    <div className="panel flex flex-col">
      {/* ── Stream body ─────────────────────────────── */}
      <AutoScrollPanel className="panel-body flex-1" scrollViewClassName="panel-body-inner" dep={`${streamRecords.length}:${streamSubFilter}`}>
        {!streamRecords.length ? (
          <div>
            {!filteredEvents.length && (
              <p className="py-8 text-center text-xs text-muted-foreground/50 tracking-wider uppercase" style={{ fontFamily: 'var(--font-data)' }}>
                {agentsInfo.total > 0 && agentsInfo.pending.length > 0
                  ? t('stream.awaitingAgents', { ready: agentsInfo.ready.length, total: agentsInfo.total })
                  : t('stream.awaitingEvents')}
              </p>
            )}
            {filteredEvents.map((ev, i) => (
              <div key={i} className="evt-row">
                <span className="evt-tick">t{ev.tick}</span>
                <span className="evt-src">{ev.source}</span>
                <span className="evt-type">{ev.type}</span>
                <span className="evt-msg">{ev.detail}</span>
              </div>
            ))}
          </div>
        ) : (
          <>
            {/* Sub-filter: digest / story / all */}
            <div className="flex border-b border-border/30 mb-2.5">
              {([['digest', t('stream.digest')], ['story', t('stream.story')], ['all', t('stream.all')]] as [StreamSubFilter, string][]).map(([val, label]) => (
                <button
                  key={val}
                  onClick={() => setSubFilter(val)}
                  className={cn(
                    'flex-1 py-2.5 font-mono text-[11px] uppercase tracking-wider text-center transition-colors duration-100 cursor-pointer select-none',
                    streamSubFilter === val
                      ? 'text-foreground font-semibold'
                      : 'text-muted-foreground/60 hover:text-muted-foreground font-normal',
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            {streamGroups.map((group) => {
              const isCollapsible = group.tick === 0 && streamSubFilter !== 'all'
              const cls = cn('stream-tick-group', group.tick === activeStreamTick && 'stream-tick-active', replayActive && group.tick > replayTick && 'opacity-30')
              const tick0Label = group.tick === 0 && agentsInfo.pending.length > 0
                ? t('stream.awaitingAgents', { ready: agentsInfo.ready.length, total: agentsInfo.total })
                : t('stream.tick', { number: group.tick })
              return isCollapsible ? (
                <Collapsible key={'t' + group.tick + (hasTicked ? '-done' : '')} defaultOpen={!hasTicked} asChild>
                  <div className={cls} ref={el => { tickRefs.current[group.tick] = el }}>
                    <CollapsibleTrigger asChild>
                      <div className="stream-tick-header cursor-pointer select-none">
                        <span className="stream-tick-label">{tick0Label}</span>
                      </div>
                    </CollapsibleTrigger>
                    <CollapsibleContent>
                      {group.records.map((rec, ri) => renderRecord(rec, ri, group.tick))}
                    </CollapsibleContent>
                  </div>
                </Collapsible>
              ) : (
                <div key={'t' + group.tick} className={cls} ref={el => { tickRefs.current[group.tick] = el }}>
                  <div className="stream-tick-header">
                    <span className="stream-tick-label">{t('stream.tick', { number: group.tick })}</span>
                  </div>
                  {group.records.map((rec, ri) => renderRecord(rec, ri, group.tick))}
                </div>
              )
            })}
          </>
        )}
      </AutoScrollPanel>
    </div>
  )
}
