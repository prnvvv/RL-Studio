/**
 * Recovery plan rendering.
 *
 * The stages come from the backend's plan record, in the order the plan
 * records them. This component never injects the canonical eight stages or
 * infers progress: an empty plan renders the unavailable state instead.
 *
 * Stage state names are a *presentation* vocabulary. Their mapping from the
 * recovery service's canonical states is unconfirmed (TODO T-1406).
 */
export type RecoveryStageState =
  'pending' | 'proposed' | 'executing' | 'completed' | 'failed' | 'blocked' | 'skipped'

export interface RecoveryStage {
  id: string
  label: string
  state: RecoveryStageState
  detail?: string
}

const stateLabel: Record<RecoveryStageState, string> = {
  pending: 'Pending',
  proposed: 'Proposed',
  executing: 'Executing',
  completed: 'Completed',
  failed: 'Failed',
  blocked: 'Blocked',
  skipped: 'Skipped',
}

function stateStyles(state: RecoveryStageState): {
  border: string
  background: string
  color: string
} {
  switch (state) {
    case 'completed':
      return {
        border: '1px solid var(--text-primary)',
        background: 'var(--text-primary)',
        color: 'var(--bg-primary)',
      }
    case 'executing':
      return {
        border: '1px solid var(--text-primary)',
        background: 'var(--bg-selected)',
        color: 'var(--text-primary)',
      }
    case 'failed':
      return {
        border: '1px solid var(--text-primary)',
        background: 'transparent',
        color: 'var(--text-primary)',
      }
    case 'blocked':
    case 'skipped':
      return {
        border: '1px dashed var(--border-primary)',
        background: 'transparent',
        color: 'var(--text-muted)',
      }
    case 'proposed':
      return {
        border: '1px dashed var(--text-primary)',
        background: 'transparent',
        color: 'var(--text-primary)',
      }
    case 'pending':
    default:
      return {
        border: '1px solid var(--border-primary)',
        background: 'transparent',
        color: 'var(--text-muted)',
      }
  }
}

interface RecoveryWorkflowProps {
  stages: RecoveryStage[]
  /** Identifier of the plan the stages belong to, when recorded. */
  planId?: string | null
}

export function RecoveryWorkflow({ stages, planId }: RecoveryWorkflowProps) {
  if (stages.length === 0) {
    return null
  }

  return (
    <div style={{ fontFamily: 'var(--font-sans)' }}>
      {planId ? (
        <p
          style={{
            margin: '0 0 var(--space-3) 0',
            fontSize: 'var(--text-xs)',
            color: 'var(--text-muted)',
            fontFamily: 'var(--font-mono)',
          }}
        >
          Plan {planId}
        </p>
      ) : null}
      <ol
        aria-label="Recovery plan stages"
        style={{
          listStyle: 'none',
          margin: 0,
          padding: 0,
          display: 'flex',
          flexDirection: 'column',
        }}
      >
        {stages.map((stage, index) => {
          const styles = stateStyles(stage.state)
          return (
            <li
              key={stage.id}
              style={{
                display: 'grid',
                gridTemplateColumns: '22px minmax(0, 1fr) auto',
                alignItems: 'start',
                gap: 'var(--space-3)',
                padding: 'var(--space-2) 0',
                borderTop: index === 0 ? 'none' : '1px solid var(--border-secondary)',
              }}
            >
              <span
                aria-hidden="true"
                style={{
                  width: '20px',
                  height: '20px',
                  borderRadius: '50%',
                  display: 'inline-flex',
                  alignItems: 'center',
                  justifyContent: 'center',
                  fontSize: '10px',
                  fontFamily: 'var(--font-mono)',
                  ...styles,
                }}
              >
                {stage.state === 'completed' ? '✓' : index + 1}
              </span>
              <div style={{ display: 'flex', flexDirection: 'column', gap: '2px', minWidth: 0 }}>
                <span style={{ fontSize: 'var(--text-sm)', color: 'var(--text-primary)' }}>
                  {stage.label}
                </span>
                {stage.detail ? (
                  <span
                    style={{
                      fontSize: 'var(--text-xs)',
                      color: 'var(--text-secondary)',
                      overflowWrap: 'anywhere',
                    }}
                  >
                    {stage.detail}
                  </span>
                ) : null}
              </div>
              <span
                style={{
                  fontSize: '10px',
                  textTransform: 'uppercase',
                  letterSpacing: '0.06em',
                  color:
                    stage.state === 'completed' ||
                    stage.state === 'executing' ||
                    stage.state === 'failed'
                      ? 'var(--text-primary)'
                      : 'var(--text-muted)',
                  whiteSpace: 'nowrap',
                }}
              >
                {stateLabel[stage.state]}
              </span>
            </li>
          )
        })}
      </ol>
    </div>
  )
}
