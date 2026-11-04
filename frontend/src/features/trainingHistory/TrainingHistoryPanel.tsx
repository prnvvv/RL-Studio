import { useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  createTrainingHistoryService,
  type NamedEntity,
  type RunComparison,
  type RunPage,
  type TrainingHistoryService,
  type TrainingRun,
} from '../../services/trainingHistory'
import { reasonLabel, stamp } from './RunContextBar'
import './trainingHistory.css'

const PAGE_SIZE = 20
const STATUSES = ['running', 'paused', 'stopping', 'completed', 'stopped', 'failed', 'interrupted']

function NA() {
  return <span className="th-na">Not recorded</span>
}

function seconds(value: number | null): string | null {
  if (value === null) return null
  if (value < 60) return `${value.toFixed(1)} s`
  return `${Math.floor(value / 60)} min ${Math.round(value % 60)} s`
}

function reward(run: TrainingRun): string | null {
  const value = run.final_metrics.mean_reward
  return typeof value === 'number' ? value.toFixed(2) : null
}

function runLinks(projectId: string, runId: string) {
  const id = encodeURIComponent(runId)
  return [
    ['Monitoring', `/monitoring?runId=${id}`],
    ['Reports', `/reports?runId=${id}`],
    ['Diagnosis', `/diagnosis-recovery?runId=${id}`],
    ['Verification', `/projects/${projectId}?runId=${id}#verification`],
  ] as const
}

function useEntities(
  projectId: string,
  api: TrainingHistoryService,
): { agents: NamedEntity[]; environments: NamedEntity[]; experiments: NamedEntity[] } {
  const [state, setState] = useState({
    agents: [] as NamedEntity[],
    environments: [] as NamedEntity[],
    experiments: [] as NamedEntity[],
  })
  useEffect(() => {
    const controller = new AbortController()
    void Promise.all([
      api.listAgents(projectId, controller.signal),
      api.listEnvironments(projectId, controller.signal),
      api.listExperiments(projectId, controller.signal),
    ]).then(([a, e, x]) => {
      if (controller.signal.aborted) return
      setState({
        agents: a.state === 'ok' ? a.data : [],
        environments: e.state === 'ok' ? e.data : [],
        experiments: x.state === 'ok' ? x.data : [],
      })
    })
    return () => controller.abort()
  }, [api, projectId])
  return state
}

/**
 * The project's whole training history, read from the persisted run catalog: filter by agent, environment, experiment
 * and status, search, sort and page through it, open any run in Monitoring, Reports, Diagnosis or Verification, and
 * compare runs when the comparison is meaningful. Only recorded values are shown; a missing value says so.
 */
export function TrainingHistoryPanel({
  projectId,
  selectedRunId,
  service,
}: {
  projectId: string
  selectedRunId?: string | null
  service?: TrainingHistoryService
}) {
  const api = useMemo(() => service ?? createTrainingHistoryService(), [service])
  const { agents, environments, experiments } = useEntities(projectId, api)
  const [agentId, setAgentId] = useState('')
  const [environmentId, setEnvironmentId] = useState('')
  const [experimentId, setExperimentId] = useState('')
  const [status, setStatus] = useState('')
  const [search, setSearch] = useState('')
  const [sort, setSort] = useState<'recent' | 'oldest' | 'timesteps'>('recent')
  const [offset, setOffset] = useState(0)
  const [page, setPage] = useState<RunPage | null>(null)
  const [failed, setFailed] = useState(false)
  const [picked, setPicked] = useState<string[]>([])
  const [comparison, setComparison] = useState<RunComparison | null>(null)
  const [nonce, setNonce] = useState(0)

  useEffect(() => {
    const controller = new AbortController()
    void api
      .listRuns(
        projectId,
        {
          agentId: agentId || undefined,
          environmentConfigId: environmentId || undefined,
          experimentId: experimentId || undefined,
          status: status || undefined,
          q: search,
          sort,
          limit: PAGE_SIZE,
          offset,
        },
        controller.signal,
      )
      .then((result) => {
        if (controller.signal.aborted) return
        if (result.state === 'ok') {
          setPage(result.data)
          setFailed(false)
        } else {
          setFailed(true)
        }
      })
    return () => controller.abort()
  }, [api, projectId, agentId, environmentId, experimentId, status, search, sort, offset, nonce])

  // A run that is still active keeps changing: refresh only then, never for finished history.
  const anyActive = page?.items.some((r) => r.active) === true
  useEffect(() => {
    if (!anyActive) return
    const timer = setInterval(() => setNonce((n) => n + 1), 4000)
    return () => clearInterval(timer)
  }, [anyActive])

  const change = (apply: () => void) => () => {
    apply()
    setOffset(0)
  }

  async function compare() {
    const result = await api.compare(projectId, picked)
    setComparison(result.state === 'ok' ? result.data : null)
  }

  const items = page?.items ?? []
  const total = page?.total ?? 0
  const filtered =
    agentId !== '' ||
    environmentId !== '' ||
    experimentId !== '' ||
    status !== '' ||
    search.trim() !== ''

  return (
    <div id="training-history">
      <div className="th-filters" role="search" aria-label="Filter training runs">
        <label>
          Agent
          <select value={agentId} onChange={(e) => change(() => setAgentId(e.target.value))()}>
            <option value="">All agents</option>
            {agents.map((a) => (
              <option key={a.id} value={a.id}>{`${a.name} (v${a.version})`}</option>
            ))}
          </select>
        </label>
        <label>
          Environment
          <select
            value={environmentId}
            onChange={(e) => change(() => setEnvironmentId(e.target.value))()}
          >
            <option value="">All environments</option>
            {environments.map((e) => (
              <option key={e.id} value={e.id}>
                {e.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Experiment
          <select
            value={experimentId}
            onChange={(e) => change(() => setExperimentId(e.target.value))()}
          >
            <option value="">All experiments</option>
            {experiments.map((x) => (
              <option key={x.id} value={x.id}>
                {x.name}
              </option>
            ))}
          </select>
        </label>
        <label>
          Status
          <select value={status} onChange={(e) => change(() => setStatus(e.target.value))()}>
            <option value="">Any status</option>
            {STATUSES.map((s) => (
              <option key={s} value={s}>
                {s}
              </option>
            ))}
          </select>
        </label>
        <label>
          Search
          <input
            type="search"
            value={search}
            placeholder="Run or agent name"
            onChange={(e) => change(() => setSearch(e.target.value))()}
          />
        </label>
        <label>
          Sort
          <select
            value={sort}
            onChange={(e) => change(() => setSort(e.target.value as typeof sort))()}
          >
            <option value="recent">Most recent</option>
            <option value="oldest">Oldest first</option>
            <option value="timesteps">Most timesteps</option>
          </select>
        </label>
      </div>

      {failed ? (
        <p role="alert" className="th-compare">
          The training history could not be loaded.{' '}
          <button type="button" className="mon-button" onClick={() => setNonce((n) => n + 1)}>
            Retry
          </button>
        </p>
      ) : page === null ? (
        <p role="status" className="th-compare">
          Loading training history…
        </p>
      ) : items.length === 0 ? (
        <p role="status" className="th-compare">
          {filtered
            ? 'No training runs match these filters.'
            : 'No training runs yet. Train an agent in Studio and it will appear here with its full history.'}
        </p>
      ) : (
        <div className="th-table-wrap">
          <table className="th-table">
            <caption className="visually-hidden">Training runs of this project</caption>
            <thead>
              <tr>
                <th scope="col">Compare</th>
                <th scope="col">Run</th>
                <th scope="col">Agent</th>
                <th scope="col">Environment</th>
                <th scope="col">Experiment</th>
                <th scope="col">Status</th>
                <th scope="col">Started</th>
                <th scope="col">Duration</th>
                <th scope="col">Algorithm</th>
                <th scope="col">Timesteps</th>
                <th scope="col">Episodes</th>
                <th scope="col">Mean reward</th>
                <th scope="col">Ended</th>
                <th scope="col">Open in</th>
              </tr>
            </thead>
            <tbody>
              {items.map((run) => (
                <tr key={run.run_id} aria-selected={run.run_id === selectedRunId}>
                  <td>
                    <input
                      type="checkbox"
                      aria-label={`Compare ${run.run_id}`}
                      checked={picked.includes(run.run_id)}
                      onChange={(e) =>
                        setPicked((cur) =>
                          e.target.checked
                            ? [...cur, run.run_id].slice(-4)
                            : cur.filter((id) => id !== run.run_id),
                        )
                      }
                    />
                  </td>
                  <td className="th-mono">{run.run_id}</td>
                  <td>
                    {run.agent_name ?? <NA />}
                    {run.agent_version === null ? '' : ` v${run.agent_version}`}
                  </td>
                  <td>{run.environment_config_name ?? run.environment_name ?? <NA />}</td>
                  <td>{run.experiment_name ?? '—'}</td>
                  <td>
                    <span className={`th-status th-status--${run.status}`}>{run.status}</span>
                  </td>
                  <td>{stamp(run.started_at)}</td>
                  <td>{seconds(run.duration_seconds) ?? <NA />}</td>
                  <td>{run.algorithm ?? <NA />}</td>
                  <td className="th-num">{run.total_timesteps ?? <NA />}</td>
                  <td className="th-num">{run.total_episodes ?? <NA />}</td>
                  <td className="th-num">{reward(run) ?? <NA />}</td>
                  <td>{reasonLabel(run) ?? (run.active ? 'In progress' : <NA />)}</td>
                  <td>
                    <span className="th-actions">
                      {runLinks(projectId, run.run_id).map(([label, to]) => (
                        <Link key={label} to={to}>
                          {label}
                        </Link>
                      ))}
                    </span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {total > PAGE_SIZE ? (
        <div className="th-pager">
          <button
            type="button"
            className="mon-button"
            disabled={offset === 0}
            onClick={() => setOffset(Math.max(0, offset - PAGE_SIZE))}
          >
            Previous
          </button>
          <span>{`${offset + 1}–${Math.min(total, offset + PAGE_SIZE)} of ${total}`}</span>
          <button
            type="button"
            className="mon-button"
            disabled={offset + PAGE_SIZE >= total}
            onClick={() => setOffset(offset + PAGE_SIZE)}
          >
            Next
          </button>
        </div>
      ) : null}

      <div className="th-compare">
        <button
          type="button"
          className="mon-button"
          disabled={picked.length < 2}
          onClick={() => void compare()}
        >
          Compare selected runs
        </button>
        {picked.length < 2 ? <span> Select at least two runs to compare them.</span> : null}
        {comparison === null ? null : comparison.comparable ? (
          <ul aria-label="Run comparison">
            {comparison.runs.map((r) => (
              <li key={r.run_id}>
                {`${r.run_id}: mean reward ${reward(r) ?? 'not recorded'}, ${r.total_timesteps ?? 0} timesteps`}
              </li>
            ))}
          </ul>
        ) : (
          <p role="status">{`These runs cannot be compared: ${comparison.reasons.join('; ')}.`}</p>
        )}
      </div>
    </div>
  )
}
