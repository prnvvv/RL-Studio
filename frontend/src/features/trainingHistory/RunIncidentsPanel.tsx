import { Link } from 'react-router-dom'
import type { SelectedRun } from '../../hooks/useSelectedRun'
import { stamp } from './RunContextBar'

/**
 * Incidents, diagnosis activity and recovery history recorded for the selected run. An incident is shown only when
 * the backend recorded it: opening Diagnosis for a run that has none shows an empty state, never a manufactured
 * incident. Choosing one focuses it (`?incidentId=`) while keeping the run in the URL.
 */
export function RunIncidentsPanel({
  selected,
  focusedIncidentId,
}: {
  selected: SelectedRun
  focusedIncidentId: string | null
}) {
  const { run, detail } = selected
  if (run === null || detail === null) return null
  const foreign =
    focusedIncidentId !== null && !detail.incidents.some((i) => i.incident_id === focusedIncidentId)
  const to = (incidentId: string) =>
    `/diagnosis-recovery?runId=${encodeURIComponent(run.run_id)}&incidentId=${encodeURIComponent(incidentId)}`

  return (
    <section
      className="th-bar"
      aria-label="Incidents recorded for this run"
      style={{ display: 'block' }}
    >
      <h2 className="th-bar__label">{`Incidents recorded for ${run.run_id}`}</h2>
      {detail.incidents.length === 0 ? (
        <p className="th-bar__message" role="status">
          No incident was recorded for this run, so there is nothing to diagnose or recover. A
          verification that fails against this run records one.
        </p>
      ) : (
        <ul>
          {detail.incidents.map((incident) => (
            <li key={incident.incident_id}>
              <Link
                to={to(incident.incident_id)}
                aria-current={incident.incident_id === focusedIncidentId}
              >
                {incident.incident_id}
              </Link>
              {` · ${incident.status}${incident.severity === null ? '' : ` · ${incident.severity}`}`}
              {` · ${incident.investigations} investigation${incident.investigations === 1 ? '' : 's'}`}
              {` · ${stamp(incident.created_at)}`}
              {incident.summary === null ? '' : ` · ${incident.summary}`}
            </li>
          ))}
        </ul>
      )}
      {foreign ? (
        <p role="alert" className="th-bar__message">
          {`Incident ${focusedIncidentId} is not an incident of this run.`}
        </p>
      ) : null}
      <p className="th-bar__message">
        {detail.recoveries.length === 0
          ? 'No recovery has been planned or executed for this run.'
          : `Recovery history: ${detail.recoveries
              .map(
                (r) =>
                  `${r.recovery_id} (${r.recovery_strategy}, ${r.recovery_status}) for ${r.incident_id}`,
              )
              .join('; ')}`}
      </p>
    </section>
  )
}
