import { ApplicationShell } from '../components/layout/ApplicationShell'
import { Panel } from '../components/ui/Panel'
import { DefinitionList } from '../components/ui/DefinitionList'
import { UnavailableState } from '../components/ui/UnavailableState'
import { WarehouseIllustration } from '../components/illustrations/WarehouseIllustration'

// No environment record has been loaded. Every detail row stays null so the UI
// reports "Not available" instead of inventing a plausible warehouse.
const environmentDetails = [
  { id: 'name', label: 'Environment', value: null },
  { id: 'status', label: 'Status', value: null },
  { id: 'type', label: 'Type', value: null },
  { id: 'agents', label: 'Agents', value: null },
  { id: 'goals', label: 'Goals', value: null },
  { id: 'obstacles', label: 'Obstacles', value: null },
  { id: 'version', label: 'Environment version', value: null },
]

export function EnvironmentsPage() {
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
              Simulation Environment
            </h1>
            <p
              style={{
                fontSize: 'var(--text-base)',
                color: 'var(--text-secondary)',
                margin: '4px 0 0 0',
                fontFamily: 'var(--font-sans)',
              }}
            >
              Configure and inspect the warehouse-navigation environment
            </p>
          </div>
          <div className="action-row">
            <button
              type="button"
              disabled
              title="Unavailable until the environment contract from Person 2 is confirmed"
              style={{
                padding: '7px 14px',
                background: 'var(--bg-panel)',
                color: 'var(--text-muted)',
                border: '1px solid var(--border-primary)',
                borderRadius: 'var(--radius-sm)',
                fontSize: 'var(--text-base)',
                fontFamily: 'var(--font-sans)',
                cursor: 'not-allowed',
              }}
            >
              Reset Environment
            </button>
            <button
              type="button"
              disabled
              title="Unavailable until the environment creation contract from Person 2 is confirmed"
              style={{
                padding: '7px 14px',
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
              New Environment
            </button>
          </div>
        </div>

        <div className="split-layout">
          <Panel
            title="Warehouse Simulation"
            description="Illustration preview. Not a running simulation."
          >
            <figure style={{ margin: 0 }}>
              <WarehouseIllustration />
              <figcaption
                style={{
                  marginTop: 'var(--space-3)',
                  fontSize: 'var(--text-xs)',
                  color: 'var(--text-muted)',
                  fontFamily: 'var(--font-sans)',
                }}
              >
                Illustration preview — shelves, obstacles, robot, goal marker, and route are
                representative, not recorded environment state.
              </figcaption>
            </figure>
            <div
              style={{
                marginTop: 'var(--space-3)',
                borderTop: '1px solid var(--border-secondary)',
                paddingTop: 'var(--space-3)',
              }}
            >
              <UnavailableState
                title="Live simulation state unavailable"
                description="No environment record is connected, so the grid, agent position and trajectory cannot be shown. The illustration above is not simulation output."
                owner="Person 2 — RL engine (environment state contract)"
              />
            </div>
          </Panel>

          <div style={{ display: 'flex', flexDirection: 'column', gap: 'var(--space-4)' }}>
            <Panel title="Environment Details">
              <DefinitionList
                rows={environmentDetails}
                caption="Values are populated only from a loaded environment record."
              />
            </Panel>

            <Panel title="Configuration">
              <UnavailableState
                title="Configuration form unavailable"
                description="Name, type, grid dimensions, start and goal cells, obstacles, step limit, reward and penalty fields are not rendered because their backend contract is unconfirmed."
                owner="Person 2 — RL engine (environment contract)"
              />
            </Panel>
          </div>
        </div>

        <p
          style={{
            margin: 0,
            fontSize: 'var(--text-xs)',
            color: 'var(--text-muted)',
            fontFamily: 'var(--font-sans)',
          }}
        >
          Reset, save, and create actions stay disabled until the corresponding backend operations
          exist and can be validated.
        </p>
      </div>
    </ApplicationShell>
  )
}
