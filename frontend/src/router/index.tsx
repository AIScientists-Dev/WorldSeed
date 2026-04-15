import { createBrowserRouter, Navigate, useRouteError } from 'react-router-dom'
import type { LoaderFunctionArgs } from 'react-router-dom'
import i18n from '@/i18n'
import App from '@/App'
import LobbyPage from '@/components/lobby/LobbyPage'
import LoadingPage from '@/components/LoadingPage'
import DashboardPage from '@/components/dashboard/DashboardPage'
import MapView from '@/components/map/MapView'
import AgentView from '@/components/agent/AgentView'
import ErrorFallback from '@/components/ErrorFallback'
import GazetteView from '@/components/gazette/GazetteView'
import IntroPage from '@/components/intro/IntroPage'
import DemoEntry from '@/components/demo/DemoEntry'
import DemoLayout from '@/components/demo/DemoLayout'
import DemoIntroPage from '@/components/demo/DemoIntroPage'
import DemoHeader from '@/components/demo/DemoHeader'
import { useAgentStore } from '@/stores/agent'
import { useWorldStore } from '@/stores/world'
import { useDemoStore } from '@/stores/demo'

function ViewError() {
  const error = useRouteError()
  const msg = error instanceof Error ? error.message : 'Unknown error'
  const stack = error instanceof Error ? error.stack?.split('\n').slice(1, 5).join('\n') : ''
  return (
    <div style={{ padding: '2rem', color: 'var(--muted-foreground, #888)', fontSize: '0.85rem' }}>
      <p style={{
        fontWeight: 700,
        marginBottom: '0.5rem',
        letterSpacing: '0.05em',
        textTransform: 'uppercase',
        fontSize: '0.8rem',
        fontFamily: 'var(--font-display, system-ui)',
        color: 'var(--foreground, #333)',
      }}>
        {i18n.t('error.viewFailed')}
      </p>
      <p style={{
        fontFamily: 'var(--font-data, monospace)',
        fontSize: '0.75rem',
        opacity: 0.8,
        marginBottom: '0.75rem',
      }}>
        {msg}
      </p>
      {stack && (
        <pre style={{
          fontSize: '0.6rem',
          opacity: 0.5,
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          maxWidth: '500px',
          fontFamily: 'var(--font-data, monospace)',
        }}>
          {stack}
        </pre>
      )}
    </div>
  )
}

const agentLoader = ({ params }: LoaderFunctionArgs) => {
  const aid = params.agentId
  if (aid && useAgentStore.getState().selectedAgent !== aid) {
    useAgentStore.getState().selectAgent(aid)
  }
  return null
}

const mapLoader = () => {
  if (useAgentStore.getState().selectedAgent) {
    useAgentStore.getState().selectAgent(null)
  }
  return null
}

export const router = createBrowserRouter([
  {
    element: <App />,
    errorElement: <ErrorFallback />,
    children: [
      { path: '/', element: <Navigate to="/lobby" replace /> },
      { path: '/lobby', element: <LobbyPage /> },
      { path: '/loading', element: <LoadingPage /> },

      /* ── Demo route tree (self-contained, no product coupling) ── */
      {
        path: '/demo',
        children: [
          { index: true, element: <DemoEntry /> },
          {
            element: <DemoLayout />,
            loader: () => {
              const runId = useDemoStore.getState().runId
              if (runId) useWorldStore.setState({ viewingRunId: runId })
              return null
            },
            children: [
              { path: 'intro', element: <DemoIntroPage /> },
              {
                element: <DashboardPage header={<DemoHeader />} />,
                children: [
                  { path: 'map', element: <MapView />, errorElement: <ViewError />, loader: mapLoader },
                  { path: 'agent/:agentId', element: <AgentView />, errorElement: <ViewError />, loader: agentLoader },
                ],
              },
            ],
          },
        ],
      },

      /* ── Product routes ── */
      { path: '/run/:runId/intro', element: <IntroPage /> },
      { path: '/run/:runId/gazette', element: <GazetteView /> },
      {
        path: '/run/:runId',
        element: <DashboardPage />,
        loader: ({ params }: LoaderFunctionArgs) => {
          if (params.runId) useWorldStore.setState({ viewingRunId: params.runId })
          return null
        },
        children: [
          { index: true, element: <Navigate to="map" replace /> },
          { path: 'map', element: <MapView />, errorElement: <ViewError />, loader: mapLoader },
          { path: 'agent', element: <Navigate to="../map" replace /> },
          { path: 'agent/:agentId', element: <AgentView />, errorElement: <ViewError />, loader: agentLoader },
        ],
      },
    ],
  },
])
