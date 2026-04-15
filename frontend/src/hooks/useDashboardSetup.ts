/* WorldSeed — Shared dashboard setup hook.
 *
 * Encapsulates polling, SSE, agent sync, panel resize, and keyboard handlers.
 * Used by both DashboardPage (product) and DemoDashboard (demo).
 */

import { useEffect, useMemo, useRef, useState } from 'react'
import { useWorldStore, selectEffectiveRunId } from '@/stores/world'
import { useAgentStore } from '@/stores/agent'
import { useTheaterStore } from '@/stores/theater'
import { useEntities } from '@/hooks/useWorldState'
import { usePolling } from '@/hooks/usePolling'
import { useSSE } from '@/hooks/useSSE'
import { useSessionSSE } from '@/hooks/useSessionSSE'
import { usePanelResize } from '@/hooks/usePanelResize'
import { apiFetch } from '@/lib/api'
import { POLL_WORLD_INTERVAL_MS, POLL_AGENT_INTERVAL_MS, LS_THINKING_W } from '@/lib/constants'

export function useDashboardSetup() {
  const entities = useEntities()
  const selectedAgent = useAgentStore(s => s.selectedAgent)

  const { pollWorld, pollAgentData } = usePolling()
  const sse = useSSE()
  const sessionSSE = useSessionSSE()

  const [mapSelectedId, setMapSelectedId] = useState<string | null>(
    () => useAgentStore.getState().selectedAgent,
  )
  const mountedRef = useRef(false)
  const rightPanelRef = useRef<HTMLDivElement>(null)
  const { makeDragHandler } = usePanelResize()
  const startResizeRight = useMemo(
    () => makeDragHandler(() => rightPanelRef.current, 'x', LS_THINKING_W, 260, 0.6),
    [makeDragHandler],
  )

  useEffect(() => {
    if (mountedRef.current) return
    mountedRef.current = true

    let pollTimer: ReturnType<typeof setInterval> | undefined
    let agentPollTimer: ReturnType<typeof setInterval> | undefined

    ;(async () => {
      const [, pastRuns] = await Promise.all([
        pollWorld(),
        apiFetch('/api/past-runs'),
      ])
      if (pastRuns) useWorldStore.setState({ pastRunsList: pastRuns })

      const ws = useWorldStore.getState()
      if (!ws.scene && ws.viewingRunId) {
        const run = pastRuns?.find((r: any) => r.run_id === ws.viewingRunId)
        if (run?.scene_id) useWorldStore.setState({ scene: run.scene_id })
      }

      const as = useAgentStore.getState()
      if (as.selectedAgent) {
        useAgentStore.setState({ agentLoading: true })
        const ch = ws.characters.find(c => c.id === as.selectedAgent)
        useAgentStore.setState({ agentCharacter: ch?.character || null })
        await pollAgentData()
        useAgentStore.setState({ agentLoading: false })

        const runId = selectEffectiveRunId(ws)
        if (runId) sessionSSE.connect(as.selectedAgent, runId)
      }

      // Guard: if unmounted during async work, don't start intervals
      if (!mountedRef.current) return

      pollTimer = setInterval(pollWorld, POLL_WORLD_INTERVAL_MS)
      agentPollTimer = setInterval(pollAgentData, POLL_AGENT_INTERVAL_MS)
    })()

    return () => {
      mountedRef.current = false
      clearInterval(pollTimer)
      clearInterval(agentPollTimer)
      sse.disconnect()
      sessionSSE.disconnect()
    }
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    const entity = mapSelectedId ? entities.find(e => e.id === mapSelectedId) : null
    if (entity?.type === 'agent') {
      if (useAgentStore.getState().selectedAgent !== mapSelectedId) {
        useAgentStore.getState().selectAgent(mapSelectedId!)
      }
    } else if (useAgentStore.getState().selectedAgent) {
      useAgentStore.getState().selectAgent(null)
    }
  }, [mapSelectedId, entities])

  const viewingRunId = useWorldStore(s => s.viewingRunId)
  const prevRunId = useRef(viewingRunId)
  useEffect(() => {
    if (viewingRunId && viewingRunId !== prevRunId.current) {
      prevRunId.current = viewingRunId
      pollWorld()
    }
  }, [viewingRunId]) // eslint-disable-line react-hooks/exhaustive-deps

  const prevAgent = useRef(selectedAgent)
  useEffect(() => {
    if (selectedAgent === prevAgent.current) return
    prevAgent.current = selectedAgent

    if (!selectedAgent) {
      sessionSSE.disconnect()
      return
    }

    const ws = useWorldStore.getState()
    const ch = ws.characters.find(c => c.id === selectedAgent)
    useAgentStore.setState({ agentCharacter: ch?.character || null, agentLoading: true })
    pollAgentData().then(() => {
      useAgentStore.setState({ agentLoading: false })
    })

    const runId = selectEffectiveRunId(ws)
    if (runId) sessionSSE.connect(selectedAgent, runId)
  }, [selectedAgent, pollAgentData]) // eslint-disable-line react-hooks/exhaustive-deps

  useEffect(() => {
    if (rightPanelRef.current) {
      const w = localStorage.getItem(LS_THINKING_W)
      if (w) { rightPanelRef.current.style.flex = 'none'; rightPanelRef.current.style.width = w }
    }
  }, [])

  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape' && useTheaterStore.getState().active) {
        useTheaterStore.getState().exit()
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [])

  return {
    entities,
    mapSelectedId,
    setMapSelectedId,
    rightPanelRef,
    startResizeRight,
  }
}
