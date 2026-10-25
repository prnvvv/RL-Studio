import { useMemo, useState } from 'react'
import { ApplicationShell } from '../components/layout/ApplicationShell'
import { Panel } from '../components/ui/Panel'
import { DataTable, DataTableColumn } from '../components/ui/DataTable'
import { EmptyState } from '../components/ui/EmptyState'
import { FilterBar } from '../components/ui/FilterBar'
import { StatusBadge } from '../components/ui/StatusBadge'
import { UnavailableState } from '../components/ui/UnavailableState'
import { filterRuns, RunSummary } from '../features/reports/runHistory'

// No run-history endpoint is connected, so this is an empty page of records
// rather than example runs. Every column below renders only what a record
// supplies; "Not available" is used for a missing value.
const loadedRuns: RunSummary[] = []

const columns: DataTableColumn<RunSummary>[] = [
  {
    id: 'run-id',
    header: 'Run ID',
    mono: true,
    truncate: true,
    title: (run) => run.id,
    render: (run) => run.id,
  },
  {
    id: 'environment',
    header: 'Environment',
    mono: true,
    truncate: true,
    title: (run) => run.environment ?? undefined,
    render: (run) => run.environment ?? <NotAvailable />,
  },
  {
    id: 'steps',
    header: 'Steps',
    align: 'right',
    render: (run) => run.steps ?? <NotAvailable />,
  },
  {
    id: 'success-rate',
    header: 'Success Rate',
    align: 'right',
    // Rendered exactly as supplied. The unit is not appended here: the metric
    // definition (fraction or percentage) is the backend's to state.
    render: (run) => run.successRate ?? <NotAvailable />,
  },
  {
    id: 'status',
    header: 'Status',
    render: (run) => run.status ?? <NotAvailable />,
  },
  {
    id: 'date',
    header: 'Date',
    mono: true,
    render: (run) => run.date ?? <NotAvailable />,
  },
]

function NotAvailable() {
  return (
    <span
      style={{ fontStyle: 'italic', color: 'var(--text-muted)', fontFamily: 'var(--font-sans)' }}
    >
      Not available
    </span>
  )
}

export function ReportsPage() {
  const [query, setQuery] = useState('')
  const runs = useMemo(() => filterRuns(loadedRuns, query), [query])
  const filterDisabled = loadedRuns.length === 0

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
              Reports
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
              Review historical runs and compare recorded training and evaluation outcomes.
            </p>
          </div>
          <StatusBadge label="No data source" tone="quiet" />
        </div>

        <FilterBar
          label="Filter runs"
          value={query}
          onChange={setQuery}
          onReset={() => setQuery('')}
          placeholder="Run ID, environment, or status"
          summary={`${runs.length} of ${loadedRuns.length} recorded runs shown.`}
          scopeNote="Matches the loaded page only; it is not a server-side query."
          disabled={filterDisabled}
          disabledReason="No run records are loaded, so there is nothing to filter."
        />

        <Panel
          title="Run History"
          description="Recorded runs. Status labels are taken from the backend and are never inferred from metrics."
        >
          <DataTable
            caption="Recorded runs with environment, steps, success rate, backend-reported status, and date."
            columns={columns}
            rows={runs}
            getRowId={(run) => run.id}
            empty={
              <EmptyState
                title="No run records"
                description="Training history appears here once the backend records runs. Nothing on this page is live, historical, or demonstration data while the history source is disconnected."
              />
            }
          />

          <p
            style={{
              margin: 'var(--space-3) 0 0 0',
              fontSize: 'var(--text-xs)',
              color: 'var(--text-muted)',
              fontFamily: 'var(--font-sans)',
            }}
          >
            Final reward and per-row actions are not shown: neither is supported yet, and an action
            that cannot run is never rendered. Export is unavailable until a real export capability
            exists and is tested.
          </p>
        </Panel>

        <Panel
          title="Evaluation Summary"
          description="Baseline versus recovered comparison for a completed evaluation."
        >
          <UnavailableState
            title="No evaluation records"
            description="An evaluation summary shows the evaluation identifier, policy fingerprint, environment version, episode count, seeds, per-metric results, baseline identities, and variability. None of that is available, so no comparison is drawn."
            owner="Person 4 — evaluation records"
          />
        </Panel>
      </div>
    </ApplicationShell>
  )
}
