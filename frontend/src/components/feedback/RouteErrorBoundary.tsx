import { Component, ErrorInfo, ReactNode } from 'react'

interface RouteErrorBoundaryProps {
  children: ReactNode
}

interface RouteErrorBoundaryState {
  error: Error | null
}

/**
 * Route-level render-error boundary.
 *
 * Renders a neutral, non-sensitive surface. The error message and stack are
 * never shown to the user; they are logged for local diagnosis only.
 */
export class RouteErrorBoundary extends Component<
  RouteErrorBoundaryProps,
  RouteErrorBoundaryState
> {
  state: RouteErrorBoundaryState = { error: null }

  static getDerivedStateFromError(error: Error): RouteErrorBoundaryState {
    return { error }
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // Local diagnostics only; no user-visible stack trace.
    console.error('Route render failed', error.name, info.componentStack)
  }

  private handleReload = () => {
    window.location.assign('/')
  }

  render() {
    if (this.state.error === null) {
      return this.props.children
    }

    return (
      <div
        role="alert"
        style={{
          minHeight: '100vh',
          display: 'flex',
          flexDirection: 'column',
          alignItems: 'center',
          justifyContent: 'center',
          gap: 'var(--space-3)',
          padding: 'var(--space-8)',
          background: 'var(--bg-primary)',
          color: 'var(--text-primary)',
          fontFamily: 'var(--font-sans)',
          textAlign: 'center',
        }}
      >
        <h1 style={{ margin: 0, fontSize: 'var(--text-xl)', fontWeight: 600 }}>
          This view could not be displayed
        </h1>
        <p
          style={{
            margin: 0,
            fontSize: 'var(--text-base)',
            color: 'var(--text-secondary)',
            maxWidth: '52ch',
          }}
        >
          A rendering error occurred in this page. Recorded backend data has not been changed.
          Return to the overview and retry the action.
        </p>
        <button
          type="button"
          onClick={this.handleReload}
          style={{
            marginTop: 'var(--space-2)',
            padding: '8px 16px',
            background: 'var(--text-primary)',
            color: 'var(--bg-primary)',
            border: 'none',
            borderRadius: 'var(--radius-sm)',
            fontSize: 'var(--text-base)',
            fontFamily: 'var(--font-sans)',
            fontWeight: 500,
            cursor: 'pointer',
          }}
        >
          Return to overview
        </button>
      </div>
    )
  }
}
