import { ApplicationShell } from '../components/layout/ApplicationShell'
import { Panel } from '../components/ui/Panel'
import { MetricCard } from '../components/ui/MetricCard'
import { UnavailableState } from '../components/ui/UnavailableState'
import { LineChart } from '../components/charts/LineChart'
import { TrainingWorkflow, WorkflowStage } from '../features/training/TrainingWorkflow'

// Workflow stages are known statically. Their *state* is backend-owned and is not
// fabricated here: without a run lifecycle contract every stage reports Unknown/Pending.
const workflowStages: WorkflowStage[] = [
  { id: 'configure', label: 'Configure Environment', state: 'pending' },
  { id: 'train', label: 'Train Agent', state: 'pending' },
  { id: 'faults', label: 'Inject Faults', state: 'pending' },
  { id: 'diagnose', label: 'Detect & Diagnose', state: 'pending' },
  { id: 'recover', label: 'Recover', state: 'pending' },
  { id: 'evaluate', label: 'Evaluate', state: 'pending' },
]

export function TrainingPage() {
  return (
    <ApplicationShell>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-6)' }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', gap: 'var(--space-4)' }}>
          <div>
            <h1
              style={{
                fontSize: 'var(--text-2xl)',
                fontWeight: 600,
                margin: 0,
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-sans)',
              }}
            >
              Training Dashboard
            </h1>
            <p
              style={{
                fontSize: 'var(--text-base)',
                color: 'var(--text-secondary)',
                margin: '4px 0 0 0',
                fontFamily: 'var(--font-sans)',
              }}
            >
              Configure and monitor reinforcement-learning runs
            </p>
          </div>
          <button
            type="button"
            disabled
            title="Requires the training-run creation contract from Person 2"
            style={{
              padding: '8px 16px',
              background: 'var(--text-primary)',
              color: 'var(--bg-primary)',
              border: 'none',
              borderRadius: 'var(--radius-sm)',
              fontSize: 'var(--text-base)',
              fontFamily: 'var(--font-sans)',
              fontWeight: 500,
              cursor: 'not-allowed',
              opacity: 0.5,
            }}
          >
            New Training Run
          </button>
        </div>

        <Panel title="Workflow" description="Six-stage training and recovery lifecycle">
          <TrainingWorkflow stages={workflowStages} />
        </Panel>

        <div
          style={{
            display: 'grid',
            gridTemplateColumns: 'minmax(0, 1fr) 240px',
            gap: 'var(--space-4)',
            alignItems: 'start',
          }}
        >
          <Panel
            title="Reward vs. Training Steps"
            description="Training metric. Separate from held-out evaluation metrics."
          >
            <LineChart
              title="Reward versus training steps"
              series={[]}
              xLabel="Training steps"
              yLabel="Episode reward"
            />
            <div style={{ marginTop: 'var(--space-3)' }}>
              <UnavailableState
                title="No training metrics available"
                description="Series are rendered only from recorded run metrics. No run has been loaded for this view."
                owner="Person 2 — RL engine (metrics contract)"
              />
            </div>
          </Panel>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
            <MetricCard label="Current Reward" value="—" />
            <MetricCard label="Training Step" value="—" />
            <MetricCard label="Episode Length" value="—" />
            <MetricCard label="Success Rate" value="—" />
          </div>
        </div>
      </div>
    </ApplicationShell>
  )
}
