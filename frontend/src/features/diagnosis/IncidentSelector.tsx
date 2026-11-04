import { StatusBadge } from '../../components/ui/StatusBadge'
import type { IncidentListItem } from '../../services/diagnosis'
import type { ServiceError } from '../../services/types'
import { formatUtcDate } from '../../utils/datetime'
import '../selfHealing/selfHealing.css'

interface IncidentSelectorProps {
  runId: string | null
  incidents: IncidentListItem[] | null
  error: ServiceError | null
  selectedId: string | null
  onSelect: (incidentId: string | null) => void
}

/**
 * Chooses which recorded incident the page investigates. Incidents are the run's own persisted records (opened by a
 * failing final verification); an incident id never has to be typed. With none, the page still works: the assistant
 * is available and the empty state says how an incident arises.
 */
export function IncidentSelector({
  runId,
  incidents,
  error,
  selectedId,
  onSelect,
}: IncidentSelectorProps) {
  if (runId === null) {
    return (
      <div className="sh-empty" role="status">
        <span className="sh-empty__title">No run selected</span>
        <p className="sh-muted">
          Incidents belong to a training run. Pick a run above to see its incidents. The assistant
          below works without one.
        </p>
      </div>
    )
  }
  if (error) {
    return (
      <p role="alert" className="sh-note sh-note--alert">
        Incidents could not be loaded: {error.detail ?? error.message}
      </p>
    )
  }
  if (incidents === null) {
    return (
      <p role="status" className="sh-muted">
        Loading this run&apos;s incidents…
      </p>
    )
  }
  if (incidents.length === 0) {
    return (
      <div className="sh-empty" role="status">
        <span className="sh-empty__title">No incidents for this run</span>
        <p className="sh-muted">
          An incident is recorded when a confirmed requirement fails final deterministic
          verification against this run. None has, so there is nothing to diagnose or recover. You
          can still ask the assistant questions, or add and verify a requirement from the project
          workspace.
        </p>
      </div>
    )
  }
  return (
    <div className="sh-stack" role="radiogroup" aria-label="Incidents for this run">
      {incidents.map((incident) => {
        const selected = incident.incident_id === selectedId
        return (
          <label
            key={incident.incident_id}
            className={`sh-card${selected ? ' sh-card--selected' : ''}`}
            style={{ cursor: 'pointer' }}
          >
            <div className="sh-card__head">
              <div className="sh-row">
                <input
                  type="radio"
                  name="incident"
                  checked={selected}
                  onChange={() => onSelect(incident.incident_id)}
                  aria-label={`Incident ${incident.incident_id}`}
                />
                <span className="sh-mono">{incident.incident_id}</span>
              </div>
              <div className="sh-row">
                {incident.severity ? (
                  <StatusBadge
                    label={`severity ${incident.severity}`}
                    tone="neutral"
                    glyph="none"
                  />
                ) : null}
                <StatusBadge label={incident.status} tone="quiet" glyph="none" />
              </div>
            </div>
            <p className="sh-text">{incident.summary ?? 'No summary was recorded.'}</p>
            <span className="sh-muted">Recorded {formatUtcDate(incident.created_at)}</span>
          </label>
        )
      })}
      {selectedId !== null ? (
        <div>
          <button type="button" className="sh-btn" onClick={() => onSelect(null)}>
            Clear selection
          </button>
        </div>
      ) : null}
    </div>
  )
}
