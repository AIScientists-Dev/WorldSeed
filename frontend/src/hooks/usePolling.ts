/* WorldSeed — Polling hook: unified run data loading + live tick updates */
import { enrichEntities } from '@/lib/types'
import type { Entity } from '@/lib/types'
import { apiFetch } from '@/lib/api'
import { uiConfig } from '@/lib/ui-config'
import { clearAutoLayoutCache } from '@/lib/map-layout'
import { useAppStore } from '@/stores/app'
import { useWorldStore, selectEffectiveRunId } from '@/stores/world'
import { NARRATOR_STYLES } from '@/lib/narrator'
import { useAgentStore } from '@/stores/agent'
import { useStreamStore } from '@/stores/stream'
import { useSubtitleStore } from '@/stores/subtitle'
import { useSSE } from './useSSE'

let runLoaded = ''
let lastLiveTick = -1
let pollCounter = 0


export function usePolling() {
  const sse = useSSE()

  function computeDeltas(newEntities: Entity[]) {
    const ws = useWorldStore.getState()
    const prev = ws.prevEntityState
    const newDeltas = { ...ws.deltas }
    const newPrev: Record<string, any> = {}

    for (const key in newDeltas) {
      if (pollCounter - newDeltas[key].tick > 2) delete newDeltas[key]
    }

    newEntities.forEach(e => {
      const id = e.id
      const props = e.properties || {}
      newPrev[id] = { ...props }
      if (prev[id]) {
        for (const k in props) {
          const oldVal = prev[id][k]
          const newVal = props[k]
          if (typeof newVal === 'number' && typeof oldVal === 'number' && newVal !== oldVal) {
            const diff = newVal - oldVal
            const sign = diff > 0 ? '+' : ''
            const text = sign + (Number.isInteger(diff) ? diff : diff.toFixed(1))
            newDeltas[`${id}:${k}`] = { text, tick: pollCounter }
          }
        }
      }
    })

    useWorldStore.setState({ prevEntityState: newPrev, deltas: newDeltas })
  }

  async function pollHealth() {
    const health = await apiFetch('/health')
    if (!health) return null

    const ws = useWorldStore.getState()
    const updates: any = {
      worldStatus: health.status,
      running: health.running,
    }
    if (!ws.healthChecked) updates.healthChecked = true
    if (health.gateway) updates.gatewayStatus = health.gateway
    if (health.agents) updates.agentsInfo = health.agents
    if (health.system_agents && health.system_agents.join(',') !== ws.systemAgents.join(',')) {
      updates.systemAgents = health.system_agents
    }

    if (health.run_id) {
      useWorldStore.getState().setCurrentRunId(health.run_id)
    } else if (health.status === 'lobby') {
      updates.currentRunId = ''
    }

    if (health.narrator_style != null || health.narrator_prompt != null) {
      const hasCustomPrompt = !health.narrator_style && health.narrator_prompt
      const rawStyle = health.narrator_style || ''
      const isKnown = NARRATOR_STYLES.includes(rawStyle as any)
      const newStyle = hasCustomPrompt ? 'custom' : isKnown ? rawStyle : NARRATOR_STYLES[0]
      const newPrompt = health.narrator_prompt || ''
      if (newStyle !== ws.narratorStyle) updates.narratorStyle = newStyle
      if (newPrompt !== ws.narratorPrompt) updates.narratorPrompt = newPrompt
    }

    const isLive = ws.viewingRunId === (health.run_id || ws.currentRunId) && (health.run_id || ws.currentRunId)
    if (isLive) {
      if (health.scene) updates.scene = health.scene
      updates.tick = health.tick
    }

    useWorldStore.setState(updates)

    if (useAppStore.getState().appMode === 'dashboard') sse.connect()

    return health
  }

  async function loadRunData(runId: string) {
    if (!runId || runLoaded === runId) return
    runLoaded = runId

    useStreamStore.setState({ streamRecords: [] })
    useSubtitleStore.getState().clear()
    clearAutoLayoutCache()
    // Don't clear entities — keep old data visible until new data arrives.
    // Prevents empty map flash during async uiConfig.load().
    useWorldStore.setState({ events: [] })

    const [state, stream, meta] = await Promise.all([
      apiFetch(`/api/runs/${runId}/state`),
      apiFetch(`/api/runs/${runId}/stream`),
      apiFetch(`/api/runs/${runId}/meta`),
    ])

    if (useWorldStore.getState().viewingRunId !== runId) return

    // 1. Set scene + load UI config FIRST (before entities, so map has config ready)
    if (meta?.scene_id) {
      useWorldStore.setState({ scene: meta.scene_id })
      await uiConfig.load(meta.scene_id)
    }

    // 2. Then set entities + characters (map can now render with config)
    if (state?.entities) {
      const enriched = enrichEntities(state.entities)
      const updates: Record<string, any> = {
        entities: enriched,
        actionDefs: state.actions || {},
        tick: state.tick || 0,
      }
      if (state.system_agents) updates.systemAgents = state.system_agents
      useWorldStore.setState(updates)
    }

    if (state?.characters) {
      useWorldStore.setState({ characters: state.characters })
    } else if (stream?.events) {
      const chars: any[] = []
      const seen = new Set<string>()
      stream.events.forEach((e: any) => {
        if (e.kind === 'register' && e.agent_id && !seen.has(e.agent_id)) {
          seen.add(e.agent_id)
          chars.push({ id: e.agent_id, character: e.character || {} })
        }
      })
      if (chars.length) useWorldStore.setState({ characters: chars })
    }

    if (stream?.events) useStreamStore.setState({ streamRecords: stream.events })

    // Don't auto-enqueue subtitle cues for history browsing.
    // Subtitles only play during live (SSE) or explicit replay.

    const textsData = await apiFetch('/api/agent-texts?run_id=' + encodeURIComponent(runId))
    if (textsData?.texts) {
      useStreamStore.setState({ agentTexts: textsData.texts, agentTextsRunId: runId })
    }

    if (!state?.tick && stream?.events?.length) {
      useWorldStore.setState({
        tick: stream.events.reduce((max: number, e: any) => Math.max(max, e.tick || 0), 0),
      })
    }

    if (stream?.events) {
      let tokens = 0
      stream.events.forEach((e: any) => {
        if (e.kind === 'dm_call' || e.kind === 'gm_resolve') {
          tokens += (e.tokens_in || 0) + (e.tokens_out || 0)
        }
      })
      useWorldStore.setState({ tokenCount: tokens })
    }

    if (stream?.events) {
      const ws = useWorldStore.getState()
      const agentIds = new Set(ws.entities.filter(e => e.type === 'agent').map(e => e.id))
      const newLastAction = { ...ws.agentLastAction }
      stream.events.forEach((ev: any) => {
        if (ev.source && ev.type && ev.tick && agentIds.has(ev.source)) {
          const cur = newLastAction[ev.source] || 0
          if (ev.tick > cur) newLastAction[ev.source] = ev.tick
        }
      })
      useWorldStore.setState({ agentLastAction: newLastAction })
    }

    lastLiveTick = useWorldStore.getState().tick
  }

  async function refreshLiveState() {
    const ws = useWorldStore.getState()
    const rid = ws.viewingRunId
    if (!rid || rid !== ws.currentRunId) return
    if (ws.worldStatus === 'lobby') return
    if (ws.tick === lastLiveTick && ws.entities.length > 0) return

    if (ws.tick < lastLiveTick && lastLiveTick > 0) {
      runLoaded = ''
      useWorldStore.getState().resetForNewRun()
      useAgentStore.getState().selectAgent(null)
      useStreamStore.getState().resetForNewRun()
      clearAutoLayoutCache()
      sse.disconnect()
      lastLiveTick = -1
      pollCounter = 0
      return
    }

    lastLiveTick = ws.tick
    pollCounter++

    const state = await apiFetch(`/api/runs/${rid}/state`)
    if (state?.entities) {
      const enriched = enrichEntities(state.entities)
      computeDeltas(enriched)
      useWorldStore.setState({
        entities: enriched,
        actionDefs: state.actions || {},
      })
    }
    if (state?.characters) useWorldStore.setState({ characters: state.characters })
  }

  async function pollWorld() {
    await pollHealth()
    const appStore = useAppStore.getState()
    const ws = useWorldStore.getState()
    if (appStore.appMode !== 'dashboard' || !ws.viewingRunId) return

    await loadRunData(ws.viewingRunId)
    await refreshLiveState()

    const rid = useWorldStore.getState().viewingRunId
    const currentRid = useWorldStore.getState().currentRunId
    if (rid && rid === currentRid) {
      const textsData = await apiFetch('/api/agent-texts?run_id=' + encodeURIComponent(rid))
      if (textsData?.texts) {
        useStreamStore.setState({ agentTexts: textsData.texts, agentTextsRunId: rid })
      }
    }
  }

  async function pollAgentData() {
    const as = useAgentStore.getState()
    const aid = as.selectedAgent
    if (!aid) return

    const ws = useWorldStore.getState()
    const effectiveRunId = selectEffectiveRunId(ws)
    const runParam = effectiveRunId ? '&run_id=' + encodeURIComponent(effectiveRunId) : ''
    const isLive = ws.worldStatus !== 'lobby'

    const [inbox, runs] = await Promise.all([
      isLive ? apiFetch('/api/inbox?agent_id=' + encodeURIComponent(aid)) : null,
      apiFetch('/api/runs?agent_id=' + encodeURIComponent(aid)),
    ])

    if (useAgentStore.getState().selectedAgent !== aid) return

    if (inbox) {
      useAgentStore.setState({
        agentInbox: inbox,
        agentPerception: {
          self_state: inbox.current_state || null,
          nearby_entities: inbox.nearby_entities || inbox.visible_entities || {},
          nearby_agents: inbox.nearby_agents || inbox.visible_agents || {},
          events: inbox.events || [],
          whispers: inbox.whispers || [],
          action_options: inbox.action_options || inbox.available_actions || {},
        },
      })
    }
    if (runs) useAgentStore.setState({ agentRuns: runs.runs || [] })
  }

  return { pollWorld, pollAgentData }
}
