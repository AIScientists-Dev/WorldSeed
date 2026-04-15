/* WorldSeed — Demo entry point (/demo).
 *
 * Shows DemoWelcome (language selection), resolves the matching
 * demo run ID from /health, stores it, then navigates to /demo/intro.
 */

import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useDemoStore } from '@/stores/demo'
import { apiFetch } from '@/lib/api'
import DemoWelcome from '@/components/intro/DemoWelcome'

export default function DemoEntry() {
  const navigate = useNavigate()
  const [demoRuns, setDemoRuns] = useState<Record<string, string> | null>(null)
  const fetched = useRef(false)

  useEffect(() => {
    if (fetched.current) return
    fetched.current = true
    useDemoStore.getState().activate()
    apiFetch('/health').then(h => {
      if (h?.demo_runs && Object.keys(h.demo_runs).length > 0) {
        setDemoRuns(h.demo_runs)
      } else {
        navigate('/lobby', { replace: true })
      }
    })
  }, [])

  function onLangSelected(lang: string) {
    if (!demoRuns) return
    const runId = demoRuns[lang] || demoRuns['en'] || demoRuns['default'] || Object.values(demoRuns)[0]
    if (runId) {
      useDemoStore.getState().setRunId(runId)
      navigate('/demo/intro')
    }
  }

  if (!demoRuns) return null

  return <DemoWelcome onSelect={onLangSelected} />
}
