import { SignIn } from '@clerk/react'
import { TopNavigation } from '../components/layout/TopNavigation'

export function LoginPage() {
  return (
    <>
      <TopNavigation />
      <div
        style={{
          display: 'flex',
          alignItems: 'center',
          justifyContent: 'center',
          minHeight: 'calc(100vh - 56px)',
          padding: 'var(--space-4)',
        }}
      >
        <div style={{ maxWidth: '400px', width: '100%' }}>
          <SignIn />
        </div>
      </div>
    </>
  )
}
