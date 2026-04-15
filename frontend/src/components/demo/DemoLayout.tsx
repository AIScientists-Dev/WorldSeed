/* WorldSeed — Demo layout: gateway for all /demo/* sub-routes.
 *
 * Redirects to /demo if no runId (language not selected yet).
 * viewingRunId is set by the route loader, not here.
 */

import { useEffect } from 'react'
import { Outlet, useNavigate } from 'react-router-dom'
import { useDemoStore } from '@/stores/demo'

export default function DemoLayout() {
  const runId = useDemoStore(s => s.runId)
  const navigate = useNavigate()

  useEffect(() => {
    if (!runId) navigate('/demo', { replace: true })
  }, [runId, navigate])

  if (!runId) return null
  return <Outlet />
}
