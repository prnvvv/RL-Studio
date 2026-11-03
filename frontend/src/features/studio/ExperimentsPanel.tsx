import { useCallback, useEffect, useState } from 'react'
import { LineChart } from '../../components/charts/LineChart'
import type { StudioService } from '../../services/studio'
import { downsample, formatInt, formatNumber, formatPercent } from './format'
import type { StudioState } from './studioStore'
import type { ExperimentSummary, SessionSnapshot } from './studioTypes'

interface Props {
  service: StudioService
  state: StudioState
}

type History =
  | { state: 'loading' }
  | { state: 'ready'; items: ExperimentSummary[] }
  | { state: 'error'; message: string }

/** Current experiment, its checkpoints, and previously recorded experiments. */
export function ExperimentsPanel({ service, state }: Props) {
  const config = state.config
  const [history, setHistory] = useState<History>({ state: 'loading' })
  const [selected, setSelected] = useState<SessionSnapshot | null>(null)
  const [detailError, setDetailError] = useState<string | null>(null)
  const finished = state.status === 'completed' || state.status === 'stopped' || state.status === 'failed'

  const load = useCallback(
    async (signal?: AbortSignal) => {
      const result = await service.listHistory(signal)
      if (signal?.aborted) return
      setHistory(
        result.state === 'ok'
          ? { state: 'ready', items: result.data }
          : { state: 'error', message: result.error.message },
      )
    },
    [service],
  )

  // Reload when a run finishes so it appears in history.
  useEffect(() => {
    const controller = new AbortController()
    void load(controller.signal)
    return () => controller.abort()
  }, [load, finished, state.runId])

  async function inspect(runId: string) {
    setDetailError(null)
    const result = await service.getHistoryRecord(runId)
    if (result.state === 'ok') setSelected(result.data)
    else setDetailError(result.error.message)
  }

  return (
    <div>
      <h3 className="section-title">Current experiment</h3>
      {state.sessionId === null || state.progress === null ? (
        <div className="empty">No session initialized.</div>
      ) : (
        <table className="mini-table">
          <tbody>
            <tr><th>Name</th><td>{state.name}</td></tr>
            <tr><th>Run</th><td>{state.runId}</td></tr>
            <tr><th>Status</th><td>{state.status}</td></tr>
            <tr><th>Agent / environment</th><td>{config?.agent} / {config?.environment}</td></tr>
            <tr><th>Seed</th><td>{String(config?.training.seed ?? '—')}</td></tr>
            <tr><th>Timesteps</th><td>{formatInt(state.progress.timestep)} / {formatInt(state.progress.total_timesteps)}</td></tr>
          </tbody>
        </table>
      )}

      <h3 className="section-title">Checkpoints</h3>
      {state.checkpoints.length === 0 ? (
        <div className="empty">No checkpoints written for this run.</div>
      ) : (
        <table className="mini-table">
          <thead><tr><th>ID</th><th>Timestep</th><th>Reason</th><th>SHA-256</th></tr></thead>
          <tbody>
            {state.checkpoints.map((c) => (
              <tr key={c.checkpoint_id}>
                <td>{c.checkpoint_id}</td><td>{formatInt(c.timestep)}</td><td>{c.reason}</td>
                <td title={c.sha256}>{c.sha256.slice(0, 12)}…</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      <h3 className="section-title">Previous experiments</h3>
      {history.state === 'loading' && <div className="empty">Loading…</div>}
      {history.state === 'error' && <p className="note note--error" role="alert">Could not load experiment history. {history.message}</p>}
      {history.state === 'ready' && history.items.length === 0 && (
        <div className="empty">No finished experiments recorded yet. A record is written when a run completes, stops or fails.</div>
      )}
      {history.state === 'ready' && history.items.length > 0 && (
        <table className="mini-table">
          <thead><tr><th>Name</th><th>Status</th><th>Steps</th><th>Best</th><th>Success</th><th /></tr></thead>
          <tbody>
            {history.items.map((item) => (
              <tr key={item.run_id}>
                <td>{item.name}<br /><span style={{ color: 'var(--text-muted)' }}>{item.run_id}</span></td>
                <td>{item.status}</td>
                <td>{formatInt(item.progress.timestep)}</td>
                <td>{formatNumber(item.progress.best_reward)}</td>
                <td>{formatPercent(item.progress.success_rate)}</td>
                <td><button type="button" className="btn btn--ghost" onClick={() => void inspect(item.run_id)}>Inspect</button></td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
      {detailError && <p className="note note--error" role="alert">Could not load that record. {detailError}</p>}
      {selected && (
        <div style={{ marginTop: 'var(--space-3)' }}>
          <h3 className="section-title">{selected.name} — recorded run (read-only)</h3>
          <LineChart
            title="Recorded reward versus timestep"
            xLabel="Timestep"
            yLabel="Reward"
            height={190}
            series={[
              { id: 'avg', label: 'Moving average (20)', lineStyle: 'solid', emphasis: true, points: downsample(selected.episodes, 300).map((e) => ({ x: e.timestep, y: e.moving_avg_reward })) },
            ]}
          />
          <p className="note">
            Config: {selected.config.agent} on {selected.config.environment}, seed {String(selected.config.training.seed)},{' '}
            {formatInt(selected.progress.timestep)} timesteps, {selected.checkpoints.length} checkpoints.
          </p>
        </div>
      )}
    </div>
  )
}
