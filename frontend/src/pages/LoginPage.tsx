import { SignIn } from '@clerk/react'

export function LoginPage() {
  return (
    <div
      style={{
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        minHeight: '100vh',
        padding: 'var(--space-4)',
      }}
    >
      <div style={{ maxWidth: '400px', width: '100%' }}>
        <SignIn />
      </div>
    </div>
  )
}