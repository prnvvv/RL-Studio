export type WorkflowStageState = 'completed' | 'current' | 'pending' | 'blocked' | 'failed'

export interface WorkflowStage {
  id: string
  label: string
  state: WorkflowStageState
}

const stateSymbol: Record<WorkflowStageState, string> = {
  completed: '✓',
  current: '→',
  pending: '·',
  blocked: '—',
  failed: '!',
}

function stageStyles(state: WorkflowStageState): {
  border: string
  color: string
  background: string
} {
  switch (state) {
    case 'completed':
      return {
        border: '1px solid var(--text-primary)',
        color: 'var(--bg-primary)',
        background: 'var(--text-primary)',
      }
    case 'current':
      return {
        border: '1px solid var(--text-primary)',
        color: 'var(--text-primary)',
        background: 'var(--bg-selected)',
      }
    case 'failed':
      return {
        border: '1px dashed var(--text-primary)',
        color: 'var(--text-primary)',
        background: 'transparent',
      }
    case 'blocked':
      return {
        border: '1px dashed var(--border-primary)',
        color: 'var(--text-muted)',
        background: 'transparent',
      }
    case 'pending':
    default:
      return {
        border: '1px solid var(--border-primary)',
        color: 'var(--text-muted)',
        background: 'transparent',
      }
  }
}

interface TrainingWorkflowProps {
  stages: WorkflowStage[]
}

export function TrainingWorkflow({ stages }: TrainingWorkflowProps) {
  return (
    <ol
      aria-label="Training workflow stages"
      style={{
        display: 'flex',
        alignItems: 'flex-start',
        gap: 0,
        margin: 0,
        padding: 0,
        listStyle: 'none',
        overflowX: 'auto',
      }}
    >
      {stages.map((stage, index) => {
        const styles = stageStyles(stage.state)
        const isLast = index === stages.length - 1
        return (
          <li
            key={stage.id}
            style={{
              display: 'flex',
              alignItems: 'flex-start',
              flex: 1,
              minWidth: '132px',
            }}
          >
            <div
              style={{
                display: 'flex',
                flexDirection: 'column',
                alignItems: 'center',
                gap: 'var(--space-2)',
                flex: 1,
              }}
            >
              <div style={{ display: 'flex', alignItems: 'center', width: '100%' }}>
                <span
                  aria-hidden="true"
                  style={{
                    width: '24px',
                    height: '24px',
                    flexShrink: 0,
                    borderRadius: '50%',
                    display: 'inline-flex',
                    alignItems: 'center',
                    justifyContent: 'center',
                    fontSize: 'var(--text-xs)',
                    fontFamily: 'var(--font-sans)',
                    ...styles,
                  }}
                >
                  {stage.state === 'completed' ? stateSymbol.completed : index + 1}
                </span>
                {!isLast && (
                  <span
                    aria-hidden="true"
                    style={{
                      height: '1px',
                      flex: 1,
                      background: 'var(--border-primary)',
                    }}
                  />
                )}
              </div>
              <div
                style={{
                  display: 'flex',
                  flexDirection: 'column',
                  gap: '2px',
                  paddingRight: 'var(--space-2)',
                }}
              >
                <span
                  style={{
                    fontSize: 'var(--text-sm)',
                    color:
                      stage.state === 'pending' || stage.state === 'blocked'
                        ? 'var(--text-muted)'
                        : 'var(--text-primary)',
                    fontWeight: stage.state === 'current' ? 600 : 400,
                    fontFamily: 'var(--font-sans)',
                  }}
                >
                  {stage.label}
                </span>
                <span
                  style={{
                    fontSize: 'var(--text-xs)',
                    color: 'var(--text-muted)',
                    fontFamily: 'var(--font-sans)',
                  }}
                >
                  {stage.state === 'current'
                    ? 'Current'
                    : stage.state === 'completed'
                      ? 'Completed'
                      : stage.state === 'failed'
                        ? 'Failed'
                        : stage.state === 'blocked'
                          ? 'Blocked'
                          : 'Pending'}
                </span>
              </div>
            </div>
          </li>
        )
      })}
    </ol>
  )
}
