import { useCallback, useEffect } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import { ApplicationShell } from '../components/layout/ApplicationShell'
import { Panel } from '../components/ui/Panel'
import { MetricCard } from '../components/ui/MetricCard'
import { EmptyState } from '../components/ui/EmptyState'
import { UnavailableState } from '../components/ui/UnavailableState'
import { LineChart } from '../components/charts/LineChart'
import { TrainingWorkflow, WorkflowStage } from '../features/training/TrainingWorkflow'
import { RunControls } from '../features/training/RunControls'
import { IntentComposer } from '../features/intent/IntentComposer'
import { RunScopeField } from '../features/monitoring/RunScopeField'
import { RunLifecycleStatus } from '../features/monitoring/RunLifecycleStatus'
import type { ExtractedRequirementDraft, RequirementDecision } from '../schemas/intent'
import {
  createIntentRequirementsService,
  type IntentSubmissionOutcome,
} from '../services/intentRequirements'
import { createRunService } from '../services/runs'
import { useRunStatus } from '../hooks/useRunStatus'

const intentRequirementsService = createIntentRequirementsService()
const runService = createRunService()

// Id of the run scope form, so the header action can move focus to it instead
// of pretending a run-creation flow exists.
const RUN_SCOPE_FORM_ID = 'run-scope-form'

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

/**
 * Run-scoped lifecycle, start, and stop for the selected run.
 *
 * The lifecycle always comes from the status endpoint; the controls' own
 * acknowledgements are never adopted as the run's state.
 */
function TrainingRunScope({ runId }: { runId: string }) {
  const status = useRunStatus(runId, runService)
  const lifecycle = status.state.state === 'loading' ? null : status.state.data

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <RunLifecycleStatus
        state={status.state}
        snapshotAsOf={status.lastUpdated}
        onRefresh={status.reload}
      />
      <RunControls
        key={runId}
        runId={runId}
        lifecycle={lifecycle}
        service={runService}
        onAcknowledged={() => status.reload()}
      />
      <p
        style={{
          margin: 0,
          fontSize: 'var(--text-xs)',
          color: 'var(--text-muted)',
          fontFamily: 'var(--font-sans)',
        }}
      >
        <Link
          to={`/monitoring?runId=${encodeURIComponent(runId)}`}
          style={{ color: 'var(--text-secondary)' }}
        >
          Open live monitoring for this run
        </Link>
      </p>
    </div>
  )
}

export function TrainingPage() {
  const location = useLocation()
  const [searchParams, setSearchParams] = useSearchParams()
  const runParam = searchParams.get('runId')
  const runId = runParam !== null && runParam.trim() !== '' ? runParam : null

  // Deep-link support: /training#intent scrolls the intent composer into view.
  // A missing hash (or late hash change) never navigates away from content.
  useEffect(() => {
    if (location.hash === '#intent') {
      // jsdom (and some engines) may not implement scrollIntoView.
      document.getElementById('intent')?.scrollIntoView?.({ block: 'start' })
    }
  }, [location.hash])

  const focusRunScope = useCallback(() => {
    const form = document.getElementById(RUN_SCOPE_FORM_ID)
    form?.scrollIntoView?.({ block: 'center' })
    form?.querySelector('input')?.focus()
  }, [])

  const submitIntent = (text: string): Promise<IntentSubmissionOutcome> =>
    intentRequirementsService.submitIntent(text)

  const decideRequirement = async (
    draft: ExtractedRequirementDraft,
    decision: RequirementDecision,
  ) => {
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
            onClick={focusRunScope}
            title="Enter a run identifier in the Run lifecycle panel below. The backend has no separate run-creation endpoint."
            style={{
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
            New Training Run
          </button>
        </div>

        <Panel
          title="Run lifecycle"
          description="Lifecycle state is read from the run status endpoint. Run identifiers are supplied by the caller because the backend has no run-creation endpoint yet."
        >
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            <RunScopeField
              formId={RUN_SCOPE_FORM_ID}
              value={runId ?? ''}
              onSubmit={(nextRunId) => setSearchParams({ runId: nextRunId })}
              label="Run identifier"
              hint="Scopes this page to one run. Start and stop requests are sent for this identifier."
            />
            {runId === null ? (
              <EmptyState
                title="No run selected"
                description="Enter a run identifier to read its recorded lifecycle. Nothing is assumed about a run until the status endpoint reports it."
              />
            ) : (
              <TrainingRunScope runId={runId} />
            )}
          </div>
        </Panel>

        <Panel
          title="Intent & Requirements"
          description="Describe the intended behaviour; extract and review requirements before training"
        >
          {/* Anchor target for /training#intent deep links. */}
          <span id="intent" />
          <IntentComposer onSubmit={submitIntent} onDecide={decideRequirement} />
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
