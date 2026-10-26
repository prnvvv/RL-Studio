import { ApplicationShell } from '../components/layout/ApplicationShell'
import { Panel } from '../components/ui/Panel'
import { DefinitionList } from '../components/ui/DefinitionList'
import { ExpandableSection } from '../components/ui/ExpandableSection'
import { StatusBadge } from '../components/ui/StatusBadge'
import { UnavailableState } from '../components/ui/UnavailableState'
import { RecoveryWorkflow, RecoveryStage } from '../features/recovery/RecoveryWorkflow'

// No incident, evidence package, diagnosis, or recovery plan is connected.
// Nothing below is inferred from metrics: the page states what is missing and
// keeps detection, diagnosis, execution, and evaluation as separate claims.
const recoveryStages: RecoveryStage[] = []

const incidentDetails = [
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

export function DiagnosisRecoveryPage() {
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
                  version. No incident or evidence package is connected, so no finding, hypothesis,
                  or explanation is shown.
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
                  evidence, and limitations appear here when a diagnosis record exists. Model
                  confidence is shown only if the provider or a defined scoring method supplies it,
                  and is labelled as an estimate.
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
                rows={incidentDetails}
                caption="Populated only from a loaded incident record. Missing expectations are never treated as a pass."
              />
            </Panel>
          </div>
        </div>

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
