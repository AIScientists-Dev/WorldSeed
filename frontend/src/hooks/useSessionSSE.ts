/* WorldSeed — SSE hook for agent session logs (tail of OpenClaw JSONL).
 *
 * Connects to /api/logs/live?agent_id=X&run_id=Y when an agent is selected.
 * Replaces the old polling approach — data arrives in real-time via SSE.
 *
 * Lifecycle: call connect(agentId, runId) when selecting an agent,
 *            call disconnect() when deselecting or unmounting.
 */
import { useAgentStore } from '@/stores/agent'

const BASE_RECONNECT_MS = 3000
const MAX_RECONNECT_ATTEMPTS = 8
const BATCH_FLUSH_MS = 100  // buffer SSE messages and flush every 100ms

let eventSource: EventSource | null = null
let reconnectTimer: ReturnType<typeof setTimeout> | null = null
let reconnectAttempts = 0
let connectedKey = ''  // "agentId:runId" to avoid duplicate connections
let pendingMessages: any[] = []
let flushTimer: ReturnType<typeof setTimeout> | null = null

/** Parse a raw JSONL line from OpenClaw session file into a message object. */
function parseLine(raw: string): any | null {
  try {
    const obj = JSON.parse(raw)
    if (obj.type === 'message') return obj.message || obj
    if (obj.type === 'toolResult') return { role: 'tool', content: obj.content || '' }
    return null
  } catch {
    return null
  }
}

export function useSessionSSE() {
  function connect(agentId: string, runId: string) {
    if (!agentId || !runId) return

    const key = `${agentId}:${runId}`
    if (eventSource && eventSource.readyState !== EventSource.CLOSED && connectedKey === key) return

    disconnect()
    connectedKey = key

    // Reset logs before connecting (fresh start for this agent+run)
    useAgentStore.setState({ agentLogs: { agent_id: agentId, run_id: runId, messages: [] } })

    const url = `/api/logs/live?agent_id=${encodeURIComponent(agentId)}&run_id=${encodeURIComponent(runId)}`

    try {
      eventSource = new EventSource(url)

      eventSource.onopen = () => {
        reconnectAttempts = 0
        if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
      }

      eventSource.onmessage = (evt) => {
        const msg = parseLine(evt.data)
        if (!msg) return

        // Only update if still viewing the same agent
        const as = useAgentStore.getState()
        if (as.selectedAgent !== agentId) { disconnect(); return }

        // Buffer messages and flush periodically to avoid O(n²) array spreads
        pendingMessages.push(msg)
        if (!flushTimer) {
          flushTimer = setTimeout(() => {
            flushTimer = null
            if (!pendingMessages.length) return
            const batch = pendingMessages
            pendingMessages = []
            const st = useAgentStore.getState()
            const prev = st.agentLogs?.messages || []
            useAgentStore.setState({
              agentLogs: {
                agent_id: agentId,
                run_id: runId,
                messages: [...prev, ...batch],
              },
            })
          }, BATCH_FLUSH_MS)
        }
      }

      eventSource.onerror = () => {
        if (eventSource) { eventSource.close(); eventSource = null }
        if (!reconnectTimer && reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
          const delay = Math.min(BASE_RECONNECT_MS * Math.pow(2, reconnectAttempts), 30000)
          reconnectAttempts++
          reconnectTimer = setTimeout(() => {
            reconnectTimer = null
            // Re-check if still relevant before reconnecting
            const as = useAgentStore.getState()
            if (as.selectedAgent === agentId) connect(agentId, runId)
          }, delay)
        }
      }
    } catch {
      // Connection failed — will retry via reconnect logic
    }
  }

  function disconnect() {
    if (eventSource) { eventSource.close(); eventSource = null }
    connectedKey = ''
    reconnectAttempts = 0
    if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
    if (flushTimer) { clearTimeout(flushTimer); flushTimer = null }
    pendingMessages = []
  }

  return { connect, disconnect }
}
