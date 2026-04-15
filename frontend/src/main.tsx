import React from 'react'
import ReactDOM from 'react-dom/client'
import { RouterProvider } from 'react-router-dom'
import { initApiErrorHandler } from '@/lib/api'
import { useAppStore } from '@/stores/app'
import { router } from '@/router'
import ErrorBoundary from '@/components/ErrorBoundary'

// i18n — must be imported before any component that uses useTranslation
import '@/i18n'

// Fonts — self-hosted via fontsource, bundled by Vite (no FOUT)
import '@fontsource-variable/ibm-plex-sans'
import '@fontsource/ibm-plex-mono/300.css'
import '@fontsource/ibm-plex-mono/400.css'
import '@fontsource/ibm-plex-mono/500.css'
import '@fontsource/ibm-plex-mono/600.css'
import '@fontsource-variable/bricolage-grotesque'
import '@fontsource-variable/source-serif-4'
import '@fontsource-variable/source-serif-4/wght-italic.css'
import '@fontsource/noto-serif-sc/400.css'
import '@fontsource/noto-serif-sc/600.css'

// Global styles — design tokens first, then component styles
import '@/styles/globals.css'
import '@/styles/layout.css'
import '@/styles/components.css'
import '@/styles/setup.css'
import '@/styles/entities.css'
import '@/styles/events.css'
import '@/styles/stream-panel.css'
import '@/styles/session.css'
import '@/styles/worldview.css'
import '@/styles/motion.css'
import '@/styles/gazette.css'

// Wire API error handler
initApiErrorHandler((msg) => { useAppStore.getState().setError(msg) })

ReactDOM.createRoot(document.getElementById('root')!).render(
  <React.StrictMode>
    <ErrorBoundary>
      <RouterProvider router={router} />
    </ErrorBoundary>
  </React.StrictMode>
)
