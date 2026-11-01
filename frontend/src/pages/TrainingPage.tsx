import { useEffect } from 'react'
import { useLocation } from 'react-router-dom'
import { ApplicationShell } from '../components/layout/ApplicationShell'
import { Panel } from '../components/ui/Panel'
import { MetricCard } from '../components/ui/MetricCard'
import { UnavailableState } from '../components/ui/UnavailableState'
import { LineChart } from '../components/charts/LineChart'
import { TrainingWorkflow, WorkflowStage } from '../features/training/TrainingWorkflow'
import { IntentComposer } from '../features/intent/IntentComposer'
import type { ExtractedRequirementDraft, RequirementDecision } from '../schemas/intent'
import { createIntentRequirementsService, type IntentSubmissionOutcome } from '../services/intentRequirements'

const intentRequirementsService = createIntentRequirementsService()

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
  const location = useLocation()

  // Deep-link support: /training#intent scrolls the intent composer into view.
  // A missing hash (or late hash change) never navigates away from content.
  useEffect(() => {
    if (location.hash === '#intent') {
      // jsdom (and some engines) may not implement scrollIntoView.
      document.getElementById('intent')?.scrollIntoView?.({ block: 'start' })
    }
  }, [location.hash])

  const submitIntent = (text: string): Promise<IntentSubmissionOutcome> =>
    intentRequirementsService.submitIntent(text)

  const decideRequirement = async (draft: ExtractedRequirementDraft, decision: RequirementDecision) => {
    if (draft.requirement_id === null) {
      throw new Error('Draft has no recorded requirement id; it cannot be decided.')
    }
    await intentRequirementsService.decideRequirement(draft.requirement_id, decision)
  }

  return (
    <ApplicationShell>
      <div className="page-stack">
        <div className="page-header">
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

        <Panel
          title="Intent & Requirements"
          description="Describe the intended behaviour; extract and review requirements before training"
        >
          {/* Anchor target for /training#intent deep links. */}
          <span id="intent" />
          <IntentComposer
            onSubmit={submitIntent}
            onDecide={decideRequirement}
          />
        </Panel>

        <Panel title="Workflow" description="Six-stage training and recovery lifecycle">
          <TrainingWorkflow stages={workflowStages} />
        </Panel>

        <div className="split-layout">
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

          <div className="metric-column">
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
