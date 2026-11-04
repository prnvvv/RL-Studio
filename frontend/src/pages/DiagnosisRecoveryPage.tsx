import { useCallback, useMemo, useRef, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useSelectedRun } from '../hooks/useSelectedRun'
import { RunContextBar } from '../features/trainingHistory/RunContextBar'
import { RunIncidentsPanel } from '../features/trainingHistory/RunIncidentsPanel'
import { ApplicationShell } from '../components/layout/ApplicationShell'
import { Panel } from '../components/ui/Panel'
import { DefinitionList } from '../components/ui/DefinitionList'
import { ExpandableSection } from '../components/ui/ExpandableSection'
import { StatusBadge } from '../components/ui/StatusBadge'
import { UnavailableState } from '../components/ui/UnavailableState'
import { ErrorState } from '../components/ui/ErrorState'
import { LoadingSkeleton } from '../components/ui/LoadingSkeleton'
import { RecoveryWorkflow, RecoveryStage } from '../features/recovery/RecoveryWorkflow'
import { VerificationResultsPanel } from '../features/verification/VerificationResultsPanel'
import { AnomalyFindingsPanel } from '../features/investigation/AnomalyFindingsPanel'
import { InvestigationPanel } from '../features/investigation/InvestigationPanel'
import { investigateState } from '../features/investigation/investigationState'
import { useServiceQuery, type ServiceQueryState } from '../hooks/useServiceQuery'
import { createVerificationService, type VerificationService } from '../services/verification'
import { createInvestigationService, type InvestigationService } from '../services/investigation'
import { createProvenanceService, type ProvenanceService } from '../services/provenance'
import { createRecoveryService, type RecoveryService } from '../services/recovery'
import { createEvaluationService, type EvaluationService } from '../services/evaluation'
import type { ServiceError } from '../services/types'
import { ProvenanceView } from '../components/simulation/ProvenanceView'
import { RecoveryPanel } from '../features/recovery/RecoveryPanel'
import { createIdempotencyKey } from '../features/recovery/idempotencyKey'
import { EvaluationPanel } from '../features/evaluation/EvaluationPanel'
import type { RecoveryAssessment, Recovery } from '../schemas/recovery'
import { mocksEnabled, MOCK_DATA_LABEL, unwrapMockData, type MockData } from '../mocks'
import type { AnomalyObservation, IncidentRecord } from '../schemas/verification'
import { WarehousePlaybackViewer } from '../components/simulation/WarehousePlaybackViewer'

// Recovery stages are rendered only from a recorded recovery plan (Person 4's
// records). No plan is loaded here, so no stage sequence is assumed.
const recoveryStages: RecoveryStage[] = []

const fallbackIncidentDetails = [
  { id: 'incident-id', label: 'Incident', value: null },
  { id: 'severity', label: 'Severity', value: null },
  { id: 'detection-status', label: 'Detection status', value: null },
  { id: 'diagnosis-status', label: 'Diagnosis status', value: null },
  { id: 'requirement', label: 'Requirement', value: null },
  { id: 'requirement-origin', label: 'Requirement origin', value: null },
  { id: 'requirement-confirmed', label: 'Confirmation state', value: null },
  { id: 'expected', label: 'Expected value', value: null },
  { id: 'actual', label: 'Observed value', value: null },
  { id: 'evidence', label: 'Evidence references', value: null },
  { id: 'run', label: 'Run', value: null },
  { id: 'environment', label: 'Environment version', value: null },
  { id: 'step', label: 'Training step', value: null },
  { id: 'detector', label: 'Detection method', value: null },
]

const recoveryDetails = [
  { id: 'proposed', label: 'Proposed action', value: null },
  { id: 'executed', label: 'Executed action', value: null },
  { id: 'source-checkpoint', label: 'Source checkpoint', value: null },
  { id: 'target-checkpoint', label: 'Target checkpoint', value: null },
  { id: 'preflight', label: 'Compatibility / preflight', value: null },
  { id: 'lineage', label: 'Lineage gaps', value: null },
  { id: 'approval', label: 'Approval state', value: null },
  { id: 'execution', label: 'Execution status', value: null },
  { id: 'evaluation', label: 'Evaluation status', value: null },
]

const emptyText = {
  margin: 0,
  fontSize: 'var(--text-xs)',
  color: 'var(--text-secondary)',
  fontFamily: 'var(--font-sans)',
  lineHeight: 1.6,
  maxWidth: '80ch',
} as const

const inlineStatus = {
  margin: 0,
  fontSize: 'var(--text-xs)',
  color: 'var(--text-secondary)',
  fontFamily: 'var(--font-sans)',
  lineHeight: 1.6,
} as const

function DiagnosticsGlyph() {
  return (
    <svg
      viewBox="0 0 40 40"
      width="34"
      height="34"
      aria-hidden="true"
      style={{ flexShrink: 0 }}
      fill="none"
      stroke="var(--icon-primary)"
      strokeWidth={1.5}
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="9" y="13" width="22" height="17" rx="4" />
      <path d="M20 13V8" />
      <circle cx="20" cy="6" r="2" />
      <circle cx="15.5" cy="21" r="1.6" fill="var(--icon-primary)" stroke="none" />
      <circle cx="24.5" cy="21" r="1.6" fill="var(--icon-primary)" stroke="none" />
      <path d="M16 26h8" />
      <path d="M5 20v3M35 20v3" />
    </svg>
  )
}

/**
 * The layout shown when no incident is identified in the URL. Nothing is
 * loaded, connected, or inferred: the page states what is missing and keeps
 * detection, diagnosis, execution, and evaluation as separate claims.
 */
function StaticDiagnosisSection() {
  return (
    <div className="split-layout">
      <Panel
        title="AI Diagnosis"
        description="Deterministic verification and recovery validation remain authoritative."
      >
        <div style={{ display: 'flex', alignItems: 'flex-start', gap: 'var(--space-4)' }}>
          <DiagnosticsGlyph />
          <div
            style={{
              display: 'flex',
              flexDirection: 'column',
              gap: 'var(--space-2)',
              minWidth: 0,
            }}
          >
            <StatusBadge label="No incident loaded" tone="quiet" glyph="none" />
            <h3
              style={{
                margin: 0,
                fontSize: 'var(--text-lg)',
                fontWeight: 600,
                color: 'var(--text-primary)',
                fontFamily: 'var(--font-sans)',
              }}
            >
              No root cause available
            </h3>
            <p
              style={{
                margin: 0,
                fontSize: 'var(--text-sm)',
                color: 'var(--text-secondary)',
                fontFamily: 'var(--font-sans)',
                lineHeight: 1.6,
              }}
            >
              The investigator analyses evidence recorded for a specific incident: the violated
              requirement, expected and observed values, and the affected run and environment
              version. No incident or evidence package is connected, so no finding, hypothesis, or
              explanation is shown.
            </p>
          </div>
        </div>

        <div style={{ marginTop: 'var(--space-4)' }}>
          <ExpandableSection
            title="Evidence Used"
            summary="Not available — no evidence package loaded."
          >
            <p style={emptyText}>
              Evidence identifiers, timestamps, sequence numbers, requirement versions, and
              fault-injection metadata appear here once an incident package is loaded.
            </p>
          </ExpandableSection>
          <ExpandableSection
            title="Analysis Details"
            summary="Not available — diagnosis not started."
          >
            <p style={emptyText}>
              Provider, model, prompt and schema versions, alternative explanations, missing
              evidence, and limitations appear here when a diagnosis record exists. Model confidence
              is shown only if the provider or a defined scoring method supplies it, and is labelled
              as an estimate.
            </p>
          </ExpandableSection>
          <ExpandableSection
            title="Recommended Recovery Plan"
            summary="Not available — no plan has been proposed."
          >
            <p style={emptyText}>
              Suggested recovery steps appear here as a proposal. A proposal is not an executed
              action, and no recovery runs without deterministic compatibility validation.
            </p>
          </ExpandableSection>
        </div>
      </Panel>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        <Panel title="Incident">
          <DefinitionList
            rows={fallbackIncidentDetails}
            caption="Populated only from a loaded incident record. Missing expectations are never treated as a pass."
          />
        </Panel>
      </div>
    </div>
  )
}

/** Build incident-detail rows from a loaded record; absent fields stay null. */
function incidentRows(record: IncidentRecord | null) {
  return [
    { id: 'incident-id', label: 'Incident', value: record ? record.incident_id : null },
    { id: 'severity', label: 'Severity', value: record ? record.severity : null },
    {
      id: 'detection-status',
      label: 'Detection status',
      value: record ? record.detection_status : null,
    },
    {
      id: 'diagnosis-status',
      label: 'Diagnosis status',
      value: record ? record.diagnosis_status : null,
    },
    { id: 'requirement', label: 'Requirement', value: record ? record.requirement_id : null },
    { id: 'requirement-origin', label: 'Requirement origin', value: null },
    { id: 'requirement-confirmed', label: 'Confirmation state', value: null },
    { id: 'expected', label: 'Expected value', value: null },
    { id: 'actual', label: 'Observed value', value: null },
    {
      id: 'evidence',
      label: 'Evidence references',
      value: record && record.evidence_refs.length > 0 ? record.evidence_refs.join(', ') : null,
    },
    { id: 'run', label: 'Run', value: record ? record.run_id : null },
    {
      id: 'environment',
      label: 'Environment version',
      value: record ? record.environment_version : null,
    },
    { id: 'step', label: 'Training step', value: null },
    {
      id: 'detector',
      label: 'Detection method',
      value: record ? record.detector_id : null,
    },
  ]
}

/** Anomaly listing state rendered inside its panel wrapper. */
function AnomalySection({
  anomalies,
}: {
  anomalies: ServiceQueryState<AnomalyObservation[] | MockData<AnomalyObservation[]>>
}) {
  if (anomalies.state === 'loading') {
    return <LoadingSkeleton rows={2} />
  }

  if (anomalies.state === 'error') {
    return (
      <p role="status" style={inlineStatus}>
        Anomaly listings are not available right now: {anomalies.error.message}
      </p>
    )
  }

  const labeled = 'label' in anomalies.data
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-3)' }}>
      {labeled && (
        <div>
          <StatusBadge label={MOCK_DATA_LABEL} tone="quiet" glyph="dot" />
        </div>
      )}
      <AnomalyFindingsPanel anomalies={unwrapMockData(anomalies.data)} />
    </div>
  )
}

/** Request control style, shared with the app's inline buttons. */
const sectionButtonStyle = {
  padding: '6px 14px',
  background: 'var(--bg-input)',
  border: '1px solid var(--border-primary)',
  borderRadius: 'var(--radius-sm)',
  color: 'var(--text-primary)',
  cursor: 'pointer',
  fontFamily: 'var(--font-sans)',
} as const

/**
 * Provenance section: the run's recorded trace plus the incident's recorded
 * impact analysis, fetched from Person 4's live endpoints.
 */
function ProvenanceSection({ runId, incidentId }: { runId: string; incidentId: string }) {
  const services = useMemo(() => createProvenanceService() as ProvenanceService, [])
  const trace = useServiceQuery(() => services.getRunProvenance(runId), [services, runId])
  const impact = useServiceQuery(
    () => services.getIncidentImpact(incidentId),
    [services, incidentId],
  )

  return (
    <Panel
      title="Provenance"
      description="Recorded artifact lineage and incident impact. Unknown lineage stays unknown and is never reported as unaffected."
    >
      <ProvenanceView trace={trace.state} impact={impact.state} onReloadTrace={trace.reload} />
    </Panel>
  )
}

/**
 * Live recovery workflow: a compatibility assessment is requested explicitly,
 * the recorded assessment drives the gated execution request, and the created
 * recovery record is tracked from the response. Nothing is created implicitly.
 */
function RecoveryWorkflowSection({
  incidentId,
  recoveryService,
}: {
  incidentId: string
  recoveryService: RecoveryService
}) {
  const [assessment, setAssessment] = useState<ServiceQueryState<RecoveryAssessment> | null>(null)
  const [recoveryRecord, setRecoveryRecord] = useState<ServiceQueryState<Recovery> | null>(null)
  const [requestPending, setRequestPending] = useState(false)
  const [requestError, setRequestError] = useState<ServiceError | null>(null)
  // One key per assessment intent; reused if the same request is retried.
  const idempotencyRef = useRef<string | null>(null)

  const handleRequestAssessment = useCallback(async () => {
    if (requestPending) return
    if (!idempotencyRef.current) idempotencyRef.current = createIdempotencyKey()
    setRequestPending(true)
    setRequestError(null)
    const result = await recoveryService.createAssessment(incidentId, {
      idempotency_key: idempotencyRef.current,
    })
    if (result.state === 'error') {
      setRequestError(result.error)
    } else {
      setAssessment({ state: 'ok', data: result.data })
    }
    setRequestPending(false)
  }, [requestPending, recoveryService, incidentId])

  return (
    <Panel
      title="Recovery workflow"
      description="Eligibility and compatibility are computed by the recovery service; the backend remains authoritative."
    >
      <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
        <p style={emptyText}>
          Requesting a compatibility assessment is an explicit, idempotent request. The backend
          computes eligibility and compatibility itself; the frontend cannot declare an eligible
          assessment into existence.
        </p>
        <div>
          <button
            type="button"
            style={sectionButtonStyle}
            onClick={handleRequestAssessment}
            disabled={requestPending}
          >
            Request compatibility assessment
          </button>
        </div>
        {requestPending && (
          <p role="status" style={inlineStatus}>
            Assessment request in flight…
          </p>
        )}
        {requestError && (
          <p role="alert" style={inlineStatus}>
            The assessment request could not be completed: {requestError.message}
          </p>
        )}
        <RecoveryPanel
          incidentId={incidentId}
          service={recoveryService}
          assessment={assessment ?? undefined}
          recovery={recoveryRecord ?? undefined}
          onRequested={(record) => setRecoveryRecord({ state: 'ok', data: record })}
        />
      </div>
    </Panel>
  )
}

/** The recorded evaluation section, fetched only when a record id is connected. */
function EvaluationRecordSection({
  incidentId,
  evaluationId,
  evaluationService,
}: {
  incidentId: string
  evaluationId: string
  evaluationService: EvaluationService
}) {
  const evaluation = useServiceQuery(
    () => evaluationService.getEvaluation(incidentId, evaluationId),
    [evaluationService, incidentId, evaluationId],
  )
  return <EvaluationPanel evaluation={evaluation.state} onReload={evaluation.reload} />
}

/**
 * Evaluation display. There is no evaluation-list endpoint, so a record is
 * shown only when its identifier is explicitly connected via the URL; nothing
 * is inferred from the recovery status.
 */
function EvaluationSection({
  incidentId,
  evaluationId,
  evaluationService,
}: {
  incidentId: string
  evaluationId: string | null
  evaluationService: EvaluationService
}) {
  return (
    <Panel
      title="Evaluation"
      description="Recovery success exists only through the recorded evaluation's acceptance outcome."
    >
      {evaluationId === null ? (
        <p style={emptyText}>
          No evaluation record is connected to this view. Open this page with
          ?incidentId=&lt;incident&gt;&amp;evaluationId=&lt;record&gt; to display a recorded
          evaluation. Without it, recovery success is not established and nothing is computed to
          fill the gap.
        </p>
      ) : (
        <EvaluationRecordSection
          incidentId={incidentId}
          evaluationId={evaluationId}
          evaluationService={evaluationService}
        />
      )}
    </Panel>
  )
}

/**
 * Live incident workspace: all four panels are driven by the domain services.
 * Detection (deterministic verification), statistical signals (anomalies), and
 * the advisory AI investigation remain separate sections, and no investigator
 * analysis is requested implicitly.
 */
function IncidentWorkspace({
  incidentId,
  evaluationId,
}: {
  incidentId: string
  evaluationId: string | null
}) {
  const services = useMemo(
    () =>
      ({
        verification: createVerificationService() as VerificationService,
        investigation: createInvestigationService() as InvestigationService,
        recovery: createRecoveryService() as RecoveryService,
        evaluation: createEvaluationService() as EvaluationService,
      }) as const,
    [],
  )

  const incident = useServiceQuery(
    () => services.verification.getIncident(incidentId),
    [services, incidentId],
  )
  const verification = useServiceQuery(
    () => services.verification.getVerificationResult(incidentId),
    [services, incidentId],
  )
  const evidence = useServiceQuery(
    () => services.verification.listEvidence(incidentId),
    [services, incidentId],
  )
  const anomalies = useServiceQuery(
    () => services.verification.listAnomalies(incidentId),
    [services, incidentId],
  )
  const investigation = useServiceQuery(
    () => services.investigation.getInvestigation(incidentId),
    [services, incidentId],
  )

  const [requestPending, setRequestPending] = useState(false)
  const [requestError, setRequestError] = useState<ServiceError | null>(null)
  // `reload` is a stable callback; destructuring keeps the request handler's
  // dependency list meaningful to both the linter and readers.
  const { reload: reloadInvestigation } = investigation

  // Explicit user action only: the panel's request button is the trigger,
  // duplicates are prevented while one request is in flight, and failures are
  // surfaced as an error next to the panel instead of being silently retried.
  const handleRequestInvestigation = useCallback(async () => {
    if (requestPending) return
    setRequestPending(true)
    setRequestError(null)
    const result = await services.investigation.requestInvestigation(incidentId)
    if (result.state === 'error') {
      setRequestError(result.error)
    } else {
      reloadInvestigation()
    }
    setRequestPending(false)
  }, [requestPending, services, incidentId, reloadInvestigation])

  const incidentState = incident.state
  const incidentRecord = incidentState.state === 'ok' ? unwrapMockData(incidentState.data) : null
  const investigationBadgeState = investigateState(investigation.state)

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
      <div className="split-layout">
        <Panel
          title="Deterministic verification"
          description="Check outcomes are computed against confirmed requirements; not-evaluable scopes are never reported as passes."
        >
          <VerificationResultsPanel
            verification={verification.state}
            evidence={evidence.state}
            onReload={verification.reload}
          />
        </Panel>

        <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
          <Panel title="Incident">
            <DefinitionList
              rows={incidentRows(incidentRecord)}
              caption="Populated only from the loaded incident record. Fields the record does not carry stay unavailable."
            />
            {incidentState.state === 'loading' && (
              <p role="status" style={{ ...inlineStatus, marginTop: 'var(--space-2)' }}>
                Loading incident record…
              </p>
            )}
            {incidentState.state === 'error' && (
              <p role="status" style={{ ...inlineStatus, marginTop: 'var(--space-2)' }}>
                Incident record could not be loaded: {incidentState.error.message}
              </p>
            )}
          </Panel>

          <Panel
            title="Anomaly findings"
            description="Detector signals only — deterministic verification above remains authoritative."
          >
            <AnomalySection anomalies={anomalies.state} />
          </Panel>
        </div>
      </div>

      <Panel
        title="Recorded trajectory"
        description="Agent positions come from the run's own recorded replay; the incident's evidence events are the only annotated fault markers."
      >
        {incidentRecord?.run_id ? (
          <WarehousePlaybackViewer runId={incidentRecord.run_id} />
        ) : (
          <p style={emptyText}>
            {incidentState.state === 'loading'
              ? 'Loading the incident record…'
              : 'The loaded incident record does not identify a run, so no trajectory can be loaded. The run identifier must come from the record; it is never inferred from evidence text.'}
          </p>
        )}
      </Panel>

      {incidentRecord?.run_id ? (
        <ProvenanceSection runId={incidentRecord.run_id} incidentId={incidentId} />
      ) : incidentState.state === 'ok' ? (
        <Panel
          title="Provenance"
          description="Recorded artifact lineage and incident impact. Unknown lineage stays unknown and is never reported as unaffected."
        >
          <p style={emptyText}>
            The loaded incident record does not identify a run, so no provenance trace is requested.
            A trace is only fetched for the run identifier the record names.
          </p>
        </Panel>
      ) : null}

      <Panel
        title="AI Diagnosis"
        description="The analysis is an AI-assisted interpretation of recorded evidence and is advisory."
      >
        {requestError && (
          <ErrorState
            title="The investigation request could not be completed"
            description={requestError.message}
          />
        )}
        <InvestigationPanel
          incidentId={incidentId}
          investigation={investigation.state}
          onRequest={handleRequestInvestigation}
          requestPending={requestPending}
        />
        {investigationBadgeState === 'no_record' && (
          <p style={{ ...emptyText, marginTop: 'var(--space-2)' }}>
            Requesting an analysis is explicit and per-incident; nothing requests it automatically.
            A hypothesis from the investigator is not a confirmed root cause and cannot authorise a
            recovery action.
          </p>
        )}
      </Panel>

      <RecoveryWorkflowSection incidentId={incidentId} recoveryService={services.recovery} />
      <EvaluationSection
        incidentId={incidentId}
        evaluationId={evaluationId}
        evaluationService={services.evaluation}
      />
    </div>
  )
}

export function DiagnosisRecoveryPage() {
  const [searchParams] = useSearchParams()
  const selected = useSelectedRun()
  const incidentParam = searchParams.get('incidentId')
  const incidentId = incidentParam !== null && incidentParam.trim() !== '' ? incidentParam : null
  const evaluationParam = searchParams.get('evaluationId')
  const evaluationId =
    evaluationParam !== null && evaluationParam.trim() !== '' ? evaluationParam : null

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
              Diagnosis &amp; Recovery
            </h1>
            <p
              style={{
                fontSize: 'var(--text-base)',
                color: 'var(--text-secondary)',
                margin: '4px 0 0 0',
                fontFamily: 'var(--font-sans)',
                maxWidth: '78ch',
              }}
            >
              AI-assisted interpretation of recorded evidence, incident investigation, and validated
              recovery workflows.
            </p>
          </div>
          <StatusBadge label="Advisory analysis" tone="quiet" glyph="query" />
        </div>

        <RunContextBar selected={selected} />
        <RunIncidentsPanel selected={selected} focusedIncidentId={incidentId} />

        <p
          style={{
            margin: 0,
            padding: 'var(--space-2) var(--space-3)',
            border: '1px dashed var(--border-primary)',
            borderRadius: 'var(--radius-sm)',
            fontSize: 'var(--text-xs)',
            color: 'var(--text-secondary)',
            fontFamily: 'var(--font-sans)',
            maxWidth: '96ch',
          }}
        >
          A diagnosis is an interpretation of recorded evidence, not a proof of cause. A detected
          incident, a suspected cause, and a validated conclusion are separate claims and are
          labelled separately. Recovery is only reported as successful once its evaluation meets the
          configured acceptance criteria.
        </p>

        <p style={inlineStatus}>
          {incidentId
            ? `Focused incident: ${incidentId}.`
            : 'No incident is focused. Load an incident by opening this page with ?incidentId=<incident identifier>.'}
          {!incidentId && mocksEnabled()
            ? ' In sample-data mode the demo incident is inc_demo_warehouse_reward_scale.'
            : ''}
        </p>

        {incidentId ? (
          <IncidentWorkspace incidentId={incidentId} evaluationId={evaluationId} />
        ) : (
          <StaticDiagnosisSection />
        )}

        <Panel title="Recovery" description="Proposed and executed actions are tracked separately.">
          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            {recoveryStages.length > 0 ? (
              <RecoveryWorkflow stages={recoveryStages} planId={null} />
            ) : (
              <UnavailableState
                title="No recovery plan"
                description="Plan stages are rendered from the recorded plan, in the order the plan records them. No plan exists for this scope, so no stage sequence is assumed."
                owner="Person 4 — recovery records"
              />
            )}

            <div
              style={{
                borderTop: '1px solid var(--border-secondary)',
                paddingTop: 'var(--space-4)',
              }}
            >
              <DefinitionList
                rows={recoveryDetails}
                caption="Checkpoint compatibility, lineage gaps, and approval state must be reported by the recovery service before any action can be requested."
              />
            </div>

            <p style={emptyText}>
              Execution completing is not evidence that recovery succeeded. A recovery is reported
              as successful only when the evaluation record meets the configured acceptance
              criteria; otherwise the result is failed or inconclusive.
            </p>

            <p style={emptyText}>
              Restoring a checkpoint, discarding incompatible pending experience, collecting fresh
              experience, and re-evaluating are available only after an incident identifies a
              compatible target and the preflight checks report a result. No recovery action is
              offered while those records are absent.
            </p>
          </div>
        </Panel>
      </div>
    </ApplicationShell>
  )
}
