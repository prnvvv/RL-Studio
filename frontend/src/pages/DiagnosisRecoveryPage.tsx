import { ApplicationShell } from '../components/layout/ApplicationShell'

export function DiagnosisRecoveryPage() {
  return (
    <ApplicationShell>
      <div>
        <h1 style={{ fontSize: 'var(--text-2xl)', fontWeight: 600, margin: 0, color: 'var(--text-primary)', fontFamily: 'var(--font-sans)' }}>
          Diagnosis & Recovery
        </h1>
        <p style={{ fontSize: 'var(--text-base)', color: 'var(--text-secondary)', margin: '4px 0 0 0', fontFamily: 'var(--font-sans)' }}>
          AI-assisted incident analysis and recovery workflows
        </p>
      </div>
    </ApplicationShell>
  )
}
