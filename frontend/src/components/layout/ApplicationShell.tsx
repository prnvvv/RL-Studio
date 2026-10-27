import { ReactNode } from 'react'
import { TopNavigation } from './TopNavigation'

interface ApplicationShellProps {
  children: ReactNode
}

export function ApplicationShell({ children }: ApplicationShellProps) {
  return (
    <div style={{ minHeight: '100vh', background: 'var(--bg-primary)' }}>
      <TopNavigation />
      <main style={{ padding: 'var(--space-6)', maxWidth: '1400px', margin: '0 auto' }}>
        {children}
      </main>
    </div>
  )
}
