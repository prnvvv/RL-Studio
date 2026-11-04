import { Link } from 'react-router-dom'
import type { SelectedRun } from '../../hooks/useSelectedRun'
import type { TrainingRun } from '../../services/trainingHistory'
import { formatUtcDate, formatUtcTime } from '../../utils/datetime'
import './trainingHistory.css'

const REASON_LABEL: Record<string, string> = {
  natural_completion: 'Completed naturally',
  user_requested_stop: 'Stopped by the user',
  training_failure: 'Training failed',
  unexpected_interruption: 'Interrupted (the backend stopped)',
}

export function reasonLabel(
  run: Pick<TrainingRun, 'termination_reason' | 'status'>,
): string | null {
  if (run.termination_reason !== null)
    return REASON_LABEL[run.termination_reason] ?? run.termination_reason
  return null
}

export function stamp(iso: string | null): string {
  if (iso === null) return 'Not recorded'
  return (
    [formatUtcDate(iso), formatUtcTime(iso)].filter((p): p is string => p !== null).join(' ') ||
    'Not recorded'
  )
}

export function runLabel(run: TrainingRun): string {
  const who = run.agent_name ?? run.algorithm ?? 'Agent'
  const where = run.environment_config_name ?? run.environment_name ?? 'environment'
  const when = run.started_at === null ? '' : ` · ${formatUtcDate(run.started_at) ?? ''}`
  return `${who} on ${where} · ${run.status}${when} · ${run.run_id}`
}

/**
 * The shared "which run is this page about" header: project, selected run, its status, and a switch to any other run
 * of the same project. Everything shown is read from the persisted run record; nothing is guessed. It carries the
 * selection in the URL (`?runId=`), so switching run here changes the page's data without going back to Studio.
 */
export function RunContextBar({
  selected,
  projectName,
}: {
  selected: SelectedRun
  projectName?: string | null
}) {
  const { status, run, runs, projectId } = selected

  if (status === 'no-project') {
    return (
      <section className="th-bar" aria-label="Training run context">
        <p className="th-bar__message">
          No project is open, so there is no training history to show.{' '}
          <Link to="/projects">Open a project</Link>.
        </p>
      </section>
    )
  }
  if (status === 'empty') {
    return (
      <section className="th-bar" aria-label="Training run context">
        <p className="th-bar__message" role="status">
          No training runs yet in this project.{' '}
          <Link to="/studio?view=training">Train an agent in Studio</Link> and its run will be
          available on every page.
        </p>
      </section>
    )
  }
  if (status === 'invalid') {
    return (
      <section className="th-bar" aria-label="Training run context">
        <p className="th-bar__message" role="alert">
          Run <code>{selected.runId}</code> is not available in this project.
        </p>
        <button type="button" className="mon-button" onClick={selected.useLatest}>
          Use the latest run
        </button>
      </section>
    )
  }
  if (status === 'error') {
    return (
      <section className="th-bar" aria-label="Training run context">
        <p className="th-bar__message" role="alert">
          The project&apos;s training history could not be loaded.
        </p>
        <button type="button" className="mon-button" onClick={selected.reload}>
          Retry
        </button>
      </section>
    )
  }

  const reason = run === null ? null : reasonLabel(run)
  const options =
    runs.some((r) => r.run_id === selected.runId) || run === null ? runs : [run, ...runs]
  return (
    <section className="th-bar" aria-label="Training run context">
      <div className="th-bar__field">
        <label htmlFor="th-run-select" className="th-bar__label">
          Training run{projectName ? ` · ${projectName}` : ''}
        </label>
        <select
          id="th-run-select"
          className="th-bar__select"
          value={selected.runId ?? ''}
          disabled={status === 'loading' && run === null}
          onChange={(event) => selected.select(event.target.value)}
        >
          {selected.runId === null ? <option value="">Resolving the latest run…</option> : null}
          {options.map((r) => (
            <option key={r.run_id} value={r.run_id}>
              {runLabel(r)}
            </option>
          ))}
        </select>
      </div>
      {run === null ? (
        <p className="th-bar__message" role="status">
          Loading the run&apos;s recorded data…
        </p>
      ) : (
        <dl className="th-bar__facts">
          <div>
            <dt>Status</dt>
            <dd>
              <span className={`th-status th-status--${run.status}`}>{run.status}</span>
            </dd>
          </div>
          <div>
            <dt>Agent</dt>
            <dd>
              {run.agent_name ?? run.algorithm ?? 'Not recorded'}
              {run.agent_version === null ? '' : ` v${run.agent_version}`}
            </dd>
          </div>
          <div>
            <dt>Environment</dt>
            <dd>{run.environment_config_name ?? run.environment_name ?? 'Not recorded'}</dd>
          </div>
          {run.experiment_name === null ? null : (
            <div>
              <dt>Experiment</dt>
              <dd>{run.experiment_name}</dd>
            </div>
          )}
          <div>
            <dt>Started</dt>
            <dd>{stamp(run.started_at)}</dd>
          </div>
          {reason === null ? null : (
            <div>
              <dt>Ended</dt>
              <dd>{reason}</dd>
            </div>
          )}
        </dl>
      )}
      <Link className="th-bar__link" to={`/projects/${projectId ?? ''}#training-history`}>
        Training history
      </Link>
    </section>
  )
}
