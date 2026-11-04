import { useCallback, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import { useActiveProject } from '../contexts/ActiveProjectContext'
import { useSelectedRun, type SelectedRun } from '../hooks/useSelectedRun'
import { RunContextBar } from '../features/trainingHistory/RunContextBar'
import { ApplicationShell } from '../components/layout/ApplicationShell'
import { Panel } from '../components/ui/Panel'
import { DefinitionList } from '../components/ui/DefinitionList'
import { StatusBadge } from '../components/ui/StatusBadge'
import { LoadingSkeleton } from '../components/ui/LoadingSkeleton'
import { VerificationResultsPanel } from '../features/verification/VerificationResultsPanel'
import { AnomalyFindingsPanel } from '../features/investigation/AnomalyFindingsPanel'
import { AssistantPanel } from '../features/assistant/AssistantPanel'
import { AiDiagnosisPanel } from '../features/diagnosis/AiDiagnosisPanel'
import { IncidentSelector } from '../features/diagnosis/IncidentSelector'
import {
  RecoveryWorkflowPanel,
  checkpointChoices,
} from '../features/diagnosis/RecoveryWorkflowPanel'
import { useServiceQuery, type ServiceQueryState } from '../hooks/useServiceQuery'
import { createVerificationService, type VerificationService } from '../services/verification'
import { createProvenanceService, type ProvenanceService } from '../services/provenance'
import { createDiagnosisService, type RecoveryOption } from '../services/diagnosis'
import { ProvenanceView } from '../components/simulation/ProvenanceView'
import { WarehousePlaybackViewer } from '../components/simulation/WarehousePlaybackViewer'
import { MOCK_DATA_LABEL, unwrapMockData, type MockData } from '../mocks'
import type { AnomalyObservation, IncidentRecord } from '../schemas/verification'
import '../features/selfHealing/selfHealing.css'

/** Incident-detail rows from a loaded record; a field the record lacks stays null (shown as unavailable). */
function incidentRows(record: (IncidentRecord & { requirement?: { source_statement?: string; expected_value?: unknown; comparison_operator?: string | null } | null; summary?: string | null }) | null) {
  const requirement = record?.requirement ?? null
  return [
    { id: 'incident-id', label: 'Incident', value: record ? record.incident_id : null },
    { id: 'severity', label: 'Severity', value: record ? record.severity : null },
    { id: 'summary', label: 'Summary', value: record?.summary ?? null },
    { id: 'detection-status', label: 'Detection status', value: record ? record.detection_status : null },
    { id: 'diagnosis-status', label: 'Diagnosis status', value: record ? record.diagnosis_status : null },
    { id: 'requirement', label: 'Requirement', value: requirement?.source_statement ?? record?.requirement_id ?? null },
    {
      id: 'expected',
      label: 'Expected value',
      value:
        requirement?.expected_value === undefined || requirement?.expected_value === null
          ? null
          : `${requirement.comparison_operator ?? ''} ${String(requirement.expected_value)}`.trim(),
    },
    {
      id: 'evidence',
      label: 'Evidence references',
      value: record && record.evidence_refs.length > 0 ? record.evidence_refs.join(', ') : null,
    },
    { id: 'run', label: 'Run', value: record ? record.run_id : null },
    { id: 'environment', label: 'Environment version', value: record ? record.environment_version : null },
    { id: 'detector', label: 'Detection method', value: record ? record.detector_id : null },
  ]
}

function AnomalySection({
  anomalies,
}: {
  anomalies: ServiceQueryState<AnomalyObservation[] | MockData<AnomalyObservation[]>>
}) {
  if (anomalies.state === 'loading') return <LoadingSkeleton rows={2} />
  if (anomalies.state === 'error') {
    return (
      <p role="status" className="sh-muted">
        Anomaly listings are not available right now: {anomalies.error.message}
      </p>
    )
  }
  const labeled = 'label' in anomalies.data
  return (
    <div className="sh-stack">
      {labeled ? <StatusBadge label={MOCK_DATA_LABEL} tone="quiet" glyph="dot" /> : null}
      <AnomalyFindingsPanel anomalies={unwrapMockData(anomalies.data)} />
    </div>
  )
}

function ProvenanceSection({ runId, incidentId }: { runId: string; incidentId: string }) {
  const services = useMemo(() => createProvenanceService() as ProvenanceService, [])
  const trace = useServiceQuery(() => services.getRunProvenance(runId), [services, runId])
  const impact = useServiceQuery(() => services.getIncidentImpact(incidentId), [services, incidentId])
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
 * Everything about one selected incident: the deterministic verification that opened it, its recorded evidence and
 * lineage, the advisory AI diagnosis, and the authorized recovery workflow. Each is its own claim and is labelled so.
 */
function IncidentWorkspace({
  incidentId,
  selected,
  onChanged,
}: {
  incidentId: string
  selected: SelectedRun
  onChanged: () => void
}) {
  const services = useMemo(() => createVerificationService() as VerificationService, [])
  const incident = useServiceQuery(() => services.getIncident(incidentId), [services, incidentId])
  const verification = useServiceQuery(() => services.getVerificationResult(incidentId), [services, incidentId])
  const evidence = useServiceQuery(() => services.listEvidence(incidentId), [services, incidentId])
  const anomalies = useServiceQuery(() => services.listAnomalies(incidentId), [services, incidentId])
  const [suggested, setSuggested] = useState<string | null>(null)

  const record = incident.state.state === 'ok' ? unwrapMockData(incident.state.data) : null
  const detail = selected.detail
  const checkpoints = useMemo(() => checkpointChoices(detail?.checkpoints ?? []), [detail])
  const existing = useMemo(
    () => (detail?.recoveries ?? []).filter((r) => r.incident_id === incidentId),
    [detail, incidentId],
  )
  const useOption = useCallback((option: RecoveryOption) => {
    setSuggested(option.target_checkpoint_id)
    document.getElementById('recovery-workflow')?.scrollIntoView?.({ behavior: 'smooth' })
  }, [])

  return (
    <div className="sh-stack">
      <div className="split-layout">
        <Panel
          title="Deterministic verification"
          description="Outcomes are computed against the confirmed requirement. This is what opened the incident; the AI never decides it."
        >
          <VerificationResultsPanel
            verification={verification.state}
            evidence={evidence.state}
            onReload={verification.reload}
          />
        </Panel>
        <div className="sh-stack">
          <Panel title="Incident">
            <DefinitionList
              rows={incidentRows(record as Parameters<typeof incidentRows>[0])}
              caption="Populated only from the persisted incident record. Fields it does not carry stay unavailable."
            />
            {incident.state.state === 'loading' ? (
              <p role="status" className="sh-muted">
                Loading incident record…
              </p>
            ) : null}
            {incident.state.state === 'error' ? (
              <p role="alert" className="sh-note sh-note--alert">
                The incident record could not be loaded: {incident.state.error.detail ?? incident.state.error.message}
              </p>
            ) : null}
          </Panel>
          <Panel
            title="Anomaly findings"
            description="Detector signals only. Deterministic verification remains authoritative."
          >
            <AnomalySection anomalies={anomalies.state} />
          </Panel>
        </div>
      </div>

      {record?.run_id ? <ProvenanceSection runId={record.run_id} incidentId={incidentId} /> : null}

      {selected.run?.environment_name === 'warehouse' && record?.run_id ? (
        <Panel
          title="Recorded trajectory"
          description="Agent positions come from the run's own recorded replay."
        >
          <WarehousePlaybackViewer runId={record.run_id} />
        </Panel>
      ) : null}

      <Panel
        title="AI diagnosis and recovery plan"
        description="Advisory analysis of this incident's recorded evidence, through the Meta Model API. Inferences are labelled as such."
      >
        <AiDiagnosisPanel incidentId={incidentId} onUseOption={useOption} />
      </Panel>

      <div id="recovery-workflow">
        <Panel
          title="Recovery"
          description="Recommended, authorized, executed and verified are four separate states, shown separately."
        >
          <RecoveryWorkflowPanel
            incidentId={incidentId}
            checkpoints={checkpoints}
            suggestedCheckpointId={suggested}
            existing={existing}
            onChanged={() => {
              selected.reload()
              onChanged()
            }}
          />
        </Panel>
      </div>
    </div>
  )
}

export function DiagnosisRecoveryPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const { activeProjectId } = useActiveProject()
  const selected = useSelectedRun()
  const incidentParam = searchParams.get('incidentId')
  const incidentId = incidentParam !== null && incidentParam.trim() !== '' ? incidentParam : null
  const diagnosis = useMemo(() => createDiagnosisService(), [])
  const runId = selected.run?.run_id ?? null
  const incidents = useServiceQuery(
    () => (runId === null ? Promise.resolve({ state: 'ok' as const, data: [] }) : diagnosis.listIncidents(runId)),
    [diagnosis, runId],
  )

  const selectIncident = useCallback(
    (id: string | null) => {
      const next = new URLSearchParams(searchParams)
      if (id === null) next.delete('incidentId')
      else next.set('incidentId', id)
      setSearchParams(next, { replace: false })
    },
    [searchParams, setSearchParams],
  )

  const list = incidents.state.state === 'ok' ? incidents.state.data : null
  // An incident id in the URL that does not belong to the selected run's list is not trusted as "selected".
  const focused = incidentId !== null && list !== null && list.some((i) => i.incident_id === incidentId) ? incidentId : null
  const reloadAll = () => incidents.reload()

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
              Ask the assistant anything, investigate recorded incidents with AI, and recover under your
              authorization, validated by a real evaluation.
            </p>
          </div>
          <StatusBadge label="Advisory analysis" tone="quiet" glyph="query" />
        </div>

        <RunContextBar selected={selected} />

        <Panel
          title="AI assistant"
          description="Always available: it does not need an incident. It uses this project's recorded data when you ask about it."
        >
          <AssistantPanel projectId={activeProjectId} runId={runId} incidentId={focused} />
        </Panel>

        <Panel
          title="Incidents"
          description="Incidents recorded for the selected run when a confirmed requirement failed final verification."
        >
          <IncidentSelector
            runId={runId}
            incidents={list}
            error={incidents.state.state === 'error' ? incidents.state.error : null}
            selectedId={focused}
            onSelect={selectIncident}
          />
        </Panel>

        {focused !== null ? (
          <IncidentWorkspace incidentId={focused} selected={selected} onChanged={reloadAll} />
        ) : (
          <p className="sh-note">
            Select an incident above to see its verification evidence, run an AI diagnosis, generate a recovery
            plan and review recovery. A detected incident, a suspected cause and a validated conclusion are
            separate claims, and recovery is reported successful only after an evaluation meets its acceptance
            criteria.
          </p>
        )}
      </div>
    </ApplicationShell>
  )
}
