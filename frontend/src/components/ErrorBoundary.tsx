import { Component, type ErrorInfo, type ReactNode } from 'react'
import i18n from '@/i18n'

interface Props {
  children: ReactNode
  /** Optional fallback — defaults to built-in error panel */
  fallback?: ReactNode
}

interface State {
  error: Error | null
}

/**
 * React class-based error boundary.
 * Catches render/lifecycle errors that route errorElement cannot.
 */
export default class ErrorBoundary extends Component<Props, State> {
  state: State = { error: null }

  static getDerivedStateFromError(error: Error): State {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    console.error('[ErrorBoundary]', error, info.componentStack)
  }

  private handleReset = () => {
    this.setState({ error: null })
  }

  render() {
    if (this.state.error) {
      if (this.props.fallback) return this.props.fallback
      return <ErrorPanel error={this.state.error} onReset={this.handleReset} />
    }
    return this.props.children
  }
}

function ErrorPanel({ error, onReset }: { error: Error; onReset: () => void }) {
  return (
    <div style={{
      display: 'flex',
      flexDirection: 'column',
      alignItems: 'center',
      justifyContent: 'center',
      height: '100vh',
      fontFamily: 'var(--font-sans, system-ui, sans-serif)',
      color: 'var(--foreground, #333)',
      background: 'var(--background, #f5f3ee)',
      padding: '2rem',
    }}>
      <h1 style={{
        fontSize: '1.2rem',
        fontWeight: 700,
        marginBottom: '0.5rem',
        letterSpacing: '0.05em',
        textTransform: 'uppercase',
        fontFamily: 'var(--font-display, system-ui)',
      }}>
        {i18n.t('error.somethingWrong')}
      </h1>
      <p style={{
        fontSize: '0.8rem',
        color: 'var(--muted-foreground, #888)',
        maxWidth: '480px',
        textAlign: 'center',
        lineHeight: 1.6,
        fontFamily: 'var(--font-data, monospace)',
      }}>
        {error.message}
      </p>
      {error.stack && (
        <pre style={{
          marginTop: '1rem',
          fontSize: '0.65rem',
          color: 'var(--muted-foreground, #888)',
          maxWidth: '600px',
          maxHeight: '200px',
          overflow: 'auto',
          whiteSpace: 'pre-wrap',
          wordBreak: 'break-word',
          opacity: 0.6,
          fontFamily: 'var(--font-data, monospace)',
        }}>
          {error.stack.split('\n').slice(1, 8).join('\n')}
        </pre>
      )}
      <div style={{ display: 'flex', gap: '0.75rem', marginTop: '1.5rem' }}>
        <button
          onClick={onReset}
          style={{
            padding: '0.5rem 1.5rem',
            fontSize: '0.75rem',
            fontWeight: 600,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            border: '1px solid var(--border, #ccc)',
            background: 'transparent',
            color: 'var(--foreground, #333)',
            cursor: 'pointer',
            borderRadius: '2px',
          }}
        >
          {i18n.t('error.tryAgain')}
        </button>
        <button
          onClick={() => { window.location.href = '/lobby' }}
          style={{
            padding: '0.5rem 1.5rem',
            fontSize: '0.75rem',
            fontWeight: 600,
            letterSpacing: '0.08em',
            textTransform: 'uppercase',
            border: 'none',
            background: 'transparent',
            color: 'var(--muted-foreground, #888)',
            cursor: 'pointer',
          }}
        >
          {i18n.t('error.backToLobby')}
        </button>
      </div>
    </div>
  )
}
