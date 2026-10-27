interface UnavailableStateProps {
  title: string
  description: string
  owner?: string
}

export function UnavailableState({ title, description, owner }: UnavailableStateProps) {
  return (
    <div
      role="status"
      style={{
        display: 'flex',
        flexDirection: 'column',
        alignItems: 'center',
        justifyContent: 'center',
        gap: 'var(--space-2)',
        padding: 'var(--space-10) var(--space-4)',
        textAlign: 'center',
        color: 'var(--text-secondary)',
        fontFamily: 'var(--font-sans)',
      }}
    >
      <span
        style={{
          display: 'inline-flex',
          alignItems: 'center',
          justifyContent: 'center',
          width: '28px',
          height: '28px',
          border: '1px dashed var(--border-primary)',
          borderRadius: '50%',
          color: 'var(--text-muted)',
          fontSize: 'var(--text-md)',
        }}
        aria-hidden="true"
      >
        ?
      </span>
      <span style={{ fontSize: 'var(--text-base)', color: 'var(--text-primary)' }}>{title}</span>
      <span style={{ fontSize: 'var(--text-sm)', maxWidth: '48ch' }}>{description}</span>
      {owner && (
        <span style={{ fontSize: 'var(--text-xs)', color: 'var(--text-muted)' }}>
          Required from: {owner}
        </span>
      )}
    </div>
  )
}
