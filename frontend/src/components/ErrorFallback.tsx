import { useRouteError, isRouteErrorResponse, useNavigate } from 'react-router-dom'
import { useTranslation } from 'react-i18next'

export default function ErrorFallback() {
  const { t } = useTranslation()
  const error = useRouteError()
  const navigate = useNavigate()

  let title = t('error.somethingWrong')
  let detail = t('error.unexpected')

  if (isRouteErrorResponse(error)) {
    title = `${error.status} ${error.statusText}`
    detail = error.data?.message || error.data || ''
  } else if (error instanceof Error) {
    title = error.name
    detail = error.message
  }

  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100vh',
      fontFamily: 'var(--font-sans, system-ui, sans-serif)',
      color: 'var(--text, #333)',
      background: 'var(--bg-void, #f5f3ee)',
      padding: '2rem',
    }}>
      <h1 style={{ fontSize: '1.2rem', fontWeight: 700, marginBottom: '0.5rem', letterSpacing: '0.05em', textTransform: 'uppercase' }}>
        {title}
      </h1>
      <p style={{ fontSize: '0.85rem', color: 'var(--text-muted, #888)', maxWidth: '400px', textAlign: 'center', lineHeight: 1.5 }}>
        {detail}
      </p>
      <button
        onClick={() => navigate('/lobby')}
        style={{
          marginTop: '1.5rem',
          padding: '0.5rem 1.5rem',
          fontSize: '0.75rem',
          fontWeight: 600,
          letterSpacing: '0.08em',
          textTransform: 'uppercase',
          border: '1px solid var(--border, #ccc)',
          background: 'transparent',
          color: 'var(--text, #333)',
          cursor: 'pointer',
          borderRadius: '2px',
        }}
      >
        {t('error.backToLobby')}
      </button>
    </div>
  )
}
