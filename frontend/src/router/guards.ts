/* WorldSeed — Route guards as a React hook */
import { useEffect, useRef } from 'react'
import { useLocation, useNavigate, useParams } from 'react-router-dom'
import { useAppStore } from '@/stores/app'
import { useWorldStore } from '@/stores/world'
import { useLobbyStore } from '@/stores/lobby'
import { apiFetch } from '@/lib/api'

let initialCheckDone = false

export function useRouteGuards() {
  const location = useLocation()
  const navigate = useNavigate()
  const params = useParams()
  const initialCheckRef = useRef(false)

  // First load: check server health
  useEffect(() => {
    if (initialCheckRef.current) return
    initialCheckRef.current = true

    ;(async () => {
      if (initialCheckDone) return
      initialCheckDone = true

      const [health, configs] = await Promise.all([
        apiFetch('/health'),
        apiFetch('/api/configs'),
      ])
      if (configs) useLobbyStore.setState({ configs })
      if (!health) return

      const ws = useWorldStore.getState()
      useWorldStore.setState({
        healthChecked: true,
        tick: health.tick,
        running: health.running,
        worldStatus: health.status,
        scene: health.scene,
        gatewayStatus: health.gateway || ws.gatewayStatus,
        agentsInfo: health.agents || ws.agentsInfo,
      })

      if (health.run_id) {
        useWorldStore.getState().setCurrentRunId(health.run_id)
        // Only set viewingRunId if user isn't already viewing a specific run
        if (!params.runId) {
          useWorldStore.setState({ viewingRunId: health.run_id })
        }
      }

      // No automatic redirects — user stays on whatever URL they navigated to.
      // They can use the run selector to switch runs manually.
    })()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  // Sync appMode from route
  useEffect(() => {
    const path = location.pathname
    let mode: 'loading' | 'lobby' | 'dashboard' = 'loading'
    if (path === '/lobby') mode = 'lobby'
    else if (path === '/loading') mode = 'loading'
    else if (path.startsWith('/run/') || path.startsWith('/demo/')) mode = 'dashboard'

    if (useAppStore.getState().appMode !== mode) {
      useAppStore.setState({ appMode: mode })
    }
  }, [location.pathname])

}
