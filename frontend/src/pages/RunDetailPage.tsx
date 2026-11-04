import { useMemo } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { ApplicationShell } from '../components/layout/ApplicationShell'
import { PageHeader } from '../components/layout/PageHeader'
import { StatusBadge } from '../components/ui/StatusBadge'
import { DefinitionList, type DefinitionRow } from '../components/ui/DefinitionList'
import { StaleDataNotice } from '../components/ui/StaleDataNotice'
import { ReportSection } from '../features/report/ReportSection'
import { ProvenanceView } from '../components/simulation/ProvenanceView'
import { WarehousePlaybackViewer } from '../components/simulation/WarehousePlaybackViewer'
import { VerificationResultsPanel } from '../features/verification/VerificationResultsPanel'
import { InvestigationPanel } from '../features/investigation/InvestigationPanel'
import { EvaluationPanel } from '../features/evaluation/EvaluationPanel'
import { useServiceQuery } from '../hooks/useServiceQuery'
import { useRunStatus } from '../hooks/useRunStatus'
import { runLifecycleRows } from '../features/monitoring/runLifecyclePresentation'
import { createProvenanceService, type ProvenanceService } from '../services/provenance'
import { createVerificationService, type VerificationService } from '../services/verification'
import { createInvestigationService, type InvestigationService } from '../services/investigation'
import { createRecoveryService, type RecoveryService } from '../services/recovery'
import { createEvaluationService, type EvaluationService } from '../services/evaluation'
import { createRunService } from '../services/runs'
import type { Recovery } from '../schemas/recovery'

const emptyText = {
  margin: 0,
  fontSize: 'var(--text-xs)',
  color: 'var(--text-secondary)',
  fontFamily: 'var(--font-sans)',
  lineHeight: 1.6,
  maxWidth: '80ch',
} as const

/** Trajectory is always in scope for a run identifier; the viewer self-manages loading. */
function TrajectorySection({ runId }: { runId: string }) {
  return (
    <ReportSection
      title="Visual debugging — Trajectory"
      description="Agent positions come from the run's own recorded replay."
      status={{ kind: 'success' }}
    >
      <WarehousePlaybackViewer runId={runId} />
    </ReportSection>
  )
}

/** Provenance trace is always in scope by run id; impact is only requested once an incident is connected. */
function ProvenanceReportSection({
  runId,
  incidentId,
}: {
  runId: string
  incidentId: string | null
}) {
  return incidentId === null ? (
    <ProvenanceTraceOnlySection runId={runId} />
  ) : (
    <ProvenanceWithImpactSection runId={runId} incidentId={incidentId} />
  )
}

function ProvenanceTraceOnlySection({ runId }: { runId: string }) {
  const services = useMemo(() => createProvenanceService() as ProvenanceService, [])
  const trace = useServiceQuery(() => services.getRunProvenance(runId), [services, runId])
  return (
    <ReportSection
      title="Provenance"
      description="Recorded artifact lineage for this run. Unknown lineage stays unknown and is never reported as unaffected."
      status={{ kind: 'success' }}
    >
      <ProvenanceView trace={trace.state} onReloadTrace={trace.reload} />
    </ReportSection>
  )
}

function ProvenanceWithImpactSection({ runId, incidentId }: { runId: string; incidentId: string }) {
  const services = useMemo(() => createProvenanceService() as ProvenanceService, [])
  const trace = useServiceQuery(() => services.getRunProvenance(runId), [services, runId])
  const impact = useServiceQuery(
    () => services.getIncidentImpact(incidentId),
    [services, incidentId],
  )
  return (
    <ReportSection
      title="Provenance"
      description="Recorded artifact lineage and incident impact. Unknown lineage stays unknown and is never reported as unaffected."
      status={{ kind: 'success' }}
    >
      <ProvenanceView trace={trace.state} impact={impact.state} onReloadTrace={trace.reload} />
    </ReportSection>
  )
}

/** Deterministic verification is incident-scoped; absent an incident it is not applicable. */
function VerificationReportSection({ incidentId }: { incidentId: string | null }) {
  if (incidentId === null) {
    return (
      <ReportSection
        title="Verification & Evidence"
        status={{
          kind: 'not_applicable',
          description:
            'No incident is connected to this run. Open this page with ?incidentId=<incident> to display recorded verification results.',
        }}
      />
    )
  }
  return <ConnectedVerificationSection incidentId={incidentId} />
}

function ConnectedVerificationSection({ incidentId }: { incidentId: string }) {
  const services = useMemo(() => createVerificationService() as VerificationService, [])
  const verification = useServiceQuery(
    () => services.getVerificationResult(incidentId),
    [services, incidentId],
  )
  const evidence = useServiceQuery(() => services.listEvidence(incidentId), [services, incidentId])
  return (
    <ReportSection
      title="Verification & Evidence"
      description="Check outcomes are computed against confirmed requirements; not-evaluable scopes are never reported as passes."
      status={{ kind: 'success' }}
    >
      <VerificationResultsPanel
        verification={verification.state}
        evidence={evidence.state}
        onReload={verification.reload}
      />
    </ReportSection>
  )
}

/**
 * AI investigation is incident-scoped. The report view is read-only history,
 * so no `onRequest` handler is supplied — requesting a new analysis stays an
 * explicit action on Diagnosis & Recovery, not something a report page starts.
 */
function InvestigationReportSection({ incidentId }: { incidentId: string | null }) {
  if (incidentId === null) {
    return (
      <ReportSection
        title="AI Investigation"
        status={{
          kind: 'not_applicable',
          description:
            'No incident is connected to this run. Open this page with ?incidentId=<incident> to display a recorded investigation.',
        }}
      />
    )
  }
  return <ConnectedInvestigationSection incidentId={incidentId} />
}

function ConnectedInvestigationSection({ incidentId }: { incidentId: string }) {
  const services = useMemo(() => createInvestigationService() as InvestigationService, [])
  const investigation = useServiceQuery(
    () => services.getInvestigation(incidentId),
    [services, incidentId],
  )
  return (
    <ReportSection
      title="AI Investigation"
      description="An AI-assisted interpretation of recorded evidence, advisory only."
      status={{ kind: 'success' }}
    >
      <InvestigationPanel incidentId={incidentId} investigation={investigation.state} />
    </ReportSection>
  )
}

/** Mapped verbatim from the recorded `Recovery`; no field is derived or guessed. */
function recoveryRecordRows(recovery: Recovery): DefinitionRow[] {
  return [
    { id: 'recovery-id', label: 'Recovery', value: recovery.recovery_id },
    { id: 'status', label: 'Recovery status', value: recovery.recovery_status },
    { id: 'strategy', label: 'Strategy', value: recovery.recovery_strategy },
    { id: 'reason', label: 'Reason', value: recovery.recovery_reason },
    { id: 'source-checkpoint', label: 'Source checkpoint', value: recovery.source_checkpoint_id },
    {
      id: 'recovered-checkpoint',
      label: 'Recovered checkpoint',
      value: recovery.recovered_checkpoint_id,
    },
    {
      id: 'target-environment',
      label: 'Target environment version',
      value: recovery.target_environment_version,
    },
    { id: 'started', label: 'Started at', value: recovery.recovery_started_at },
    { id: 'completed', label: 'Completed at', value: recovery.recovery_completed_at },
    { id: 'failure-reason', label: 'Failure reason', value: recovery.failure_reason },
  ]
}

/** Recovery records are addressed by incident and recovery id together; neither alone is enough. */
function RecoveryReportSection({
  incidentId,
  recoveryId,
}: {
  incidentId: string | null
  recoveryId: string | null
}) {
  if (incidentId === null || recoveryId === null) {
    return (
      <ReportSection
        title="Recovery"
        description="Proposed and executed actions are tracked separately from this record."
        status={{
          kind: 'not_applicable',
          description:
            'No recovery record is connected to this view. Open this page with ?incidentId=<incident>&recoveryId=<record> to display a recorded recovery.',
        }}
      />
    )
  }
  return <ConnectedRecoverySection incidentId={incidentId} recoveryId={recoveryId} />
}

function ConnectedRecoverySection({
  incidentId,
  recoveryId,
}: {
  incidentId: string
  recoveryId: string
}) {
  const services = useMemo(() => createRecoveryService() as RecoveryService, [])
  const recovery = useServiceQuery(
    () => services.getRecovery(incidentId, recoveryId),
    [services, incidentId, recoveryId],
  )
  const query = recovery.state

  if (query.state === 'loading') {
    return <ReportSection title="Recovery" status={{ kind: 'pending' }} />
  }

  if (query.state === 'error') {
    if (query.data === null) {
      return (
        <ReportSection
          title="Recovery"
          status={{ kind: 'failed', description: query.error.message, onRetry: recovery.reload }}
        />
      )
    }
    return (
      <ReportSection title="Recovery" status={{ kind: 'success' }}>
        <StaleDataNotice subject="Recovery record" />
        <div style={{ marginTop: 'var(--space-3)' }}>
          <DefinitionList
            rows={recoveryRecordRows(query.data)}
            caption="Execution completing is not evidence that recovery succeeded; see Evaluation."
          />
        </div>
      </ReportSection>
    )
  }

  return (
    <ReportSection title="Recovery" status={{ kind: 'success' }}>
      <DefinitionList
        rows={recoveryRecordRows(query.data)}
        caption="Execution completing is not evidence that recovery succeeded; see Evaluation."
      />
    </ReportSection>
  )
}

/** Evaluation records are addressed by incident and evaluation id together; neither alone is enough. */
function EvaluationReportSection({
  incidentId,
  evaluationId,
}: {
  incidentId: string | null
  evaluationId: string | null
}) {
  if (incidentId === null || evaluationId === null) {
    return (
      <ReportSection
        title="Evaluation"
        description="Recovery success exists only through the recorded evaluation's acceptance outcome."
        status={{
          kind: 'not_applicable',
          description:
            'No evaluation record is connected to this view. Open this page with ?incidentId=<incident>&evaluationId=<record> to display a recorded evaluation.',
        }}
      />
    )
  }
  return <ConnectedEvaluationSection incidentId={incidentId} evaluationId={evaluationId} />
}

function ConnectedEvaluationSection({
  incidentId,
  evaluationId,
}: {
  incidentId: string
  evaluationId: string
}) {
  const services = useMemo(() => createEvaluationService() as EvaluationService, [])
  const evaluation = useServiceQuery(
    () => services.getEvaluation(incidentId, evaluationId),
    [services, incidentId, evaluationId],
  )
  return (
    <ReportSection
      title="Evaluation"
      description="Recovery success exists only through the recorded evaluation's acceptance outcome."
      status={{ kind: 'success' }}
    >
      <EvaluationPanel evaluation={evaluation.state} onReload={evaluation.reload} />
    </ReportSection>
  )
}

/**
 * The requirements list has no run-scoping parameter today: it returns every
 * recorded requirement, not the subset confirmed for this specific run.
 * Showing it here would misattribute other runs' requirements to this one,
 * so the section stays an honest capability gap rather than an approximation.
 */
function IntentRequirementsReportSection() {
  return (
    <ReportSection
      title="Intent & Requirements"
      description="Confirmed and rejected requirements recorded for this run."
      status={{
        kind: 'unavailable',
        description:
          "The requirements list is not yet scoped by run: the backend endpoint returns every recorded requirement rather than the subset confirmed for this specific run, so it cannot be shown here without misattributing other runs' requirements to this one.",
        owner: 'Person 3 — run-scoped requirements contract',
      }}
    />
  )
}

/** Run lifecycle, reused from Phase 5's polling hook; no live metrics or event timeline here. */
function TrainingMonitoringReportSection({ runId }: { runId: string }) {
  const runService = useMemo(() => createRunService(), [])
  const polling = useRunStatus(runId, runService)
  const query = polling.state
  const caption =
    'Live training metrics and the live event timeline are not shown on this static report; see Monitoring for the live view.'

  if (query.state === 'loading') {
    return <ReportSection title="Training & Monitoring" status={{ kind: 'pending' }} />
  }

  if (query.state === 'error') {
    if (query.data === null) {
      return (
        <ReportSection
          title="Training & Monitoring"
          status={{ kind: 'failed', description: query.error.message, onRetry: polling.reload }}
        />
      )
    }
    return (
      <ReportSection title="Training & Monitoring" status={{ kind: 'success' }}>
        <StaleDataNotice subject="Run lifecycle" />
        <div style={{ marginTop: 'var(--space-3)' }}>
          <DefinitionList
            rows={runLifecycleRows(query.data, polling.lastUpdated)}
            caption={caption}
          />
        </div>
      </ReportSection>
    )
  }

  return (
    <ReportSection title="Training & Monitoring" status={{ kind: 'success' }}>
      <DefinitionList rows={runLifecycleRows(query.data, polling.lastUpdated)} caption={caption} />
    </ReportSection>
  )
}

function nonEmptyParam(searchParams: URLSearchParams, key: string): string | null {
  const value = searchParams.get(key)
  return value !== null && value.trim() !== '' ? value : null
}

/**
 * Unified diagnostic report for one run (Phase 6). Every section loads
 * independently from the others; `runId` comes from the path, and
 * `incidentId`/`evaluationId`/`recoveryId` stay query params so the page
 * renders deterministically — and is shareable — from the URL alone.
 */
export function RunDetailPage() {
  const { runId: rawRunId } = useParams<{ runId: string }>()
  const [searchParams] = useSearchParams()
  const incidentId = nonEmptyParam(searchParams, 'incidentId')
  const evaluationId = nonEmptyParam(searchParams, 'evaluationId')
  const recoveryId = nonEmptyParam(searchParams, 'recoveryId')

  if (!rawRunId) {
    return (
      <ApplicationShell>
        <div className="page-stack">
          <p style={emptyText}>No run identifier was supplied in the URL.</p>
        </div>
      </ApplicationShell>
    )
  }
  const runId = rawRunId

  return (
    <ApplicationShell>
      <div className="page-stack">
        <PageHeader
          eyebrow="Run report"
          title={
            <>
              Run <span style={{ fontFamily: 'var(--font-mono)', fontSize: '0.7em' }}>{runId}</span>
            </>
          }
          description="Unified diagnostic report: every section loads independently, so one section's gap or failure never blocks the rest."
          actions={
            <StatusBadge
              label={incidentId ? 'Incident connected' : 'No incident connected'}
              tone="quiet"
              glyph={incidentId ? 'dot' : 'none'}
            />
          }
        />

        <p style={emptyText}>
          <Link to="/reports">Back to Reports</Link>
          {incidentId
            ? ` · Focused incident: ${incidentId}.`
            : ' · No incident is connected. Add ?incidentId=<incident> to the URL to connect one.'}
        </p>

        <TrainingMonitoringReportSection runId={runId} />
        <TrajectorySection runId={runId} />
        <ProvenanceReportSection runId={runId} incidentId={incidentId} />
        <IntentRequirementsReportSection />
        <VerificationReportSection incidentId={incidentId} />
        <InvestigationReportSection incidentId={incidentId} />
        <RecoveryReportSection incidentId={incidentId} recoveryId={recoveryId} />
        <EvaluationReportSection incidentId={incidentId} evaluationId={evaluationId} />
      </div>
    </ApplicationShell>
  )
}
