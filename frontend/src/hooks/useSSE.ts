/* WorldSeed — SSE hook: EventSource connection to /api/stream/live */
import { useAppStore } from '@/stores/app'
import { useWorldStore, selectIsViewingHistory } from '@/stores/world'
import { useStreamStore } from '@/stores/stream'
import { useReplayStore } from '@/stores/replay'
import { useSubtitleStore } from '@/stores/subtitle'
import { processRecord } from '@/lib/subtitle-measure'

const BASE_RECONNECT_MS = 3000
const MAX_RECONNECT_ATTEMPTS = 8

let eventSource: EventSource | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let connectedRunId: string | null = null
let reconnectAttempts = 0
let connectTick = -1

export function useSSE() {
  function connect() {
    const appStore = useAppStore.getState()
    const worldStore = useWorldStore.getState()

    if (appStore.appMode !== 'dashboard') return
    if (selectIsViewingHistory(worldStore)) return
    if (worldStore.worldStatus === 'lobby') return
    if (eventSource && eventSource.readyState !== EventSource.CLOSED && connectedRunId === worldStore.currentRunId) return

    disconnect()

    try {
      eventSource = new EventSource('/api/stream/live')
      connectedRunId = worldStore.currentRunId

      eventSource.onopen = () => {
        useStreamStore.getState().set({ streamConnected: true })
        reconnectAttempts = 0
        connectTick = useWorldStore.getState().tick
        if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
      }

      eventSource.onmessage = (evt) => {
        try {
          const record = JSON.parse(evt.data)
          const ss = useStreamStore.getState()
          ss.pushRecord(record)
          if (ss.streamRecords.length > 2000) {
            useStreamStore.setState({
              streamRecords: ss.streamRecords.slice(ss.streamRecords.length - 1500),
            })
          }
          const ws = useWorldStore.getState()
          if (record.kind === 'dm_call') {
            useWorldStore.setState({
              tokenCount: ws.tokenCount + (record.tokens_in || 0) + (record.tokens_out || 0),
            })
          }
          if (record.kind === 'action' && record.agent_id) {
            const cur = ws.agentLastAction[record.agent_id] || 0
            if ((record.tick || 0) > cur) {
              useWorldStore.setState({
                agentLastAction: { ...ws.agentLastAction, [record.agent_id]: record.tick },
              })
            }
          }
          // Subtitle: enqueue during live (not replay, not catch-up). Player decides whether to advance.
          if (!useReplayStore.getState().active && (record.tick ?? 0) > connectTick) {
            const cue = processRecord(record, ws.actionDefs)
            if (cue) useSubtitleStore.getState().enqueue(cue)
          }
        } catch { /* skip unparseable */ }
      }

      eventSource.onerror = () => {
        useStreamStore.getState().set({ streamConnected: false })
        if (eventSource) { eventSource.close(); eventSource = null }
        if (!reconnectTimer && reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
          const delay = Math.min(BASE_RECONNECT_MS * Math.pow(2, reconnectAttempts), 30000)
          reconnectAttempts++
          reconnectTimer = setTimeout(() => { reconnectTimer = null; connect() }, delay)
        }
      }
    } catch {
      useStreamStore.getState().set({ streamConnected: false })
    }
  }

  function disconnect() {
    if (eventSource) { eventSource.close(); eventSource = null }
    useStreamStore.getState().set({ streamConnected: false })
    connectedRunId = null
    reconnectAttempts = 0
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
  }

  return { connect, disconnect }
}
