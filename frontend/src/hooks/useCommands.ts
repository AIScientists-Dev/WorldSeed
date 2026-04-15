/* WorldSeed — GM commands hook
 *
 * Feedback architecture (three layers):
 *   Layer 1 — State is the feedback: no toast for actions whose result is
 *             visible in the UI (pause → header status, stop → navigation).
 *   Layer 2 — Inline feedback: optimistic updates, transient button states,
 *             gmFeedback string for direct actions.
 *   Layer 3 — Toast: only errors + rare async admin operations.
 */
import { apiFetch, apiPost, apiPatch } from '@/lib/api'
import { useUIStore } from '@/stores/ui'
import { useWorldStore } from '@/stores/world'
import { useAgentStore } from '@/stores/agent'
import { useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'
import { toast } from 'sonner'

export function useCommands() {
  const navigate = useNavigate()
  const { t } = useTranslation()

  // ── Layer 1: state-is-feedback (no success toast) ──────────────

  async function cmdPause() {
    const r = await apiPost('/api/tick/pause', {})
    if (r.ok) {
      useWorldStore.setState({ worldStatus: 'paused' })
    } else {
      toast.error(r.data.detail || 'Failed to pause.')
    }
  }

  async function cmdResume() {
    const r = await apiPost('/api/tick/resume', {})
    if (r.ok) {
      useWorldStore.setState({ worldStatus: 'live' })
    } else {
      toast.error(r.data.detail || 'Failed to resume.')
    }
  }

  async function cmdStep() {
    const r = await apiPost('/api/tick/step', {})
    if (r.ok) {
      useWorldStore.setState({ worldStatus: 'paused', tick: r.data.tick })
    } else {
      toast.error(r.data.detail || 'Failed to step.')
    }
    return r
  }

  async function cmdStop() {
    const r = await apiPost('/api/world/stop', {})
    if (r.ok) {
      useUIStore.setState({ showSettings: false })
      navigate('/lobby')
    } else {
      toast.error('Failed to stop: ' + (r.data.detail || 'error'))
    }
  }

  async function cmdLoadRun(runId: string) {
    if (!runId) return
    const r = await apiPost('/api/world/resume', { run_id: runId })
    if (r.ok) {
      const newRunId = r.data.run_id || runId
      useWorldStore.getState().setCurrentRunId(newRunId)
      useWorldStore.setState({ viewingRunId: newRunId })
      navigate(`/run/${newRunId}/map`)
    } else {
      toast.error('Load failed: ' + (r.data.detail || 'error'))
    }
  }

  // ── Layer 2: inline feedback ───────────────────────────────────

  /** Send whisper with optimistic inbox update. Returns { ok, notified }. */
  async function cmdWhisper(agentId: string): Promise<{ ok: boolean; notified: boolean }> {
    const ui = useUIStore.getState()
    const msg = ui.whisperText.trim()
    if (!msg || !agentId) return { ok: false, notified: false }

    // Optimistic: clear input + inject message into inbox immediately
    useUIStore.setState({ whisperText: '' })
    const as = useAgentStore.getState()
    const prevInbox = as.agentInbox
    const optimisticDm = {
      tick: useWorldStore.getState().tick,
      source: 'gm',
      detail: msg,
      type: 'whisper',
      _pending: true,
    }
    if (prevInbox) {
      useAgentStore.setState({
        agentInbox: {
          ...prevInbox,
          whispers: [...(prevInbox.whispers || []), optimisticDm],
        },
      })
    }

    const r = await apiPost('/api/whisper', { agent_id: agentId, message: msg })
    if (r.ok) {
      // Refresh inbox immediately so the real message replaces the optimistic one
      const inbox = await apiFetch('/api/inbox?agent_id=' + encodeURIComponent(agentId))
      if (inbox) useAgentStore.setState({ agentInbox: inbox })
      return { ok: true, notified: !!r.data.notified }
    } else {
      // Rollback: restore inbox + put text back in input
      if (prevInbox) useAgentStore.setState({ agentInbox: prevInbox })
      useUIStore.setState({ whisperText: msg })
      return { ok: false, notified: false }
    }
  }

  /** Wake agent. Returns true/false so button can show transient state. */
  async function cmdGmNotify(agentId: string): Promise<boolean> {
    if (!agentId) return false
    const r = await apiPost('/api/notify', { agent_id: agentId })
    if (!r.ok) toast.error(`Failed: ${r.data.detail || 'error'}`)
    return r.ok
  }

  /** GM resolve — uses inline gmFeedback instead of toast. */
  async function cmdGmResolve() {
    const ui = useUIStore.getState()
    const text = ui.gmResolveText.trim()
    if (!text) return
    useUIStore.setState({ gmResolveText: '' })
    const r = await apiPost('/api/gm/resolve', { text })
    if (r.ok) {
      useUIStore.getState().showFeedbackMsg(t('gm.willApply'))
    } else {
      useUIStore.getState().showFeedbackMsg(t('gm.noActiveWorld'))
    }
  }

  // ── Layer 3: toast for async admin ops ─────────────────────────

  async function cmdConnectAgents() {
    const r = await apiPost('/api/agents/connect', {})
    if (r.ok) {
      const n = r.data.gateways_notified || 0
      toast.success(`Wakes sent to ${n} gateway${n !== 1 ? 's' : ''}.`)
    } else {
      toast.error('Connect failed: ' + (r.data.detail || 'error'))
    }
  }

  async function cmdGatewayRestart() {
    const r = await apiPost('/api/gateway/restart', {})
    if (r.ok) toast.success('Gateway restarted.')
    else toast.error(r.data.detail || 'Failed to restart gateway.')
  }

  async function onSpeedChange(event: any) {
    const spd = parseFloat(event.target.value)
    const ui = useUIStore.getState()
    useUIStore.setState({ speed: spd })
    const newInterval = ui.baseInterval / spd
    await apiPatch('/api/tick/interval', { interval: newInterval })
  }

  return {
    cmdPause, cmdResume, cmdStep, cmdStop,
    cmdConnectAgents, cmdGatewayRestart, onSpeedChange,
    cmdWhisper, cmdGmNotify, cmdGmResolve, cmdLoadRun,
  }
}
