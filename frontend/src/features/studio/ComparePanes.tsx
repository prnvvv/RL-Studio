import { leaderOf } from './battle'
import { SimulationViewport } from './SimulationViewport'
import type { ViewMode } from './ControlToolbar'
import type { StudioState, StudioStore } from './studioStore'

interface Props {
  storeA: StudioStore
  storeB: StudioStore
  stateA: StudioState
  stateB: StudioState
  rendererKey: string | null
  environmentName: string | null
  viewMode: ViewMode
  cameraResetNonce: number
}

/** Two simulation viewports side by side: Session A on the left, Session B on the right. */
export function ComparePanes({
  storeA,
  storeB,
  stateA,
  stateB,
  rendererKey,
  environmentName,
  viewMode,
  cameraResetNonce,
}: Props) {
  const leader = leaderOf(stateA.progress, stateB.progress)
  const panes = [
    { side: 'a' as const, store: storeA, state: stateA },
    { side: 'b' as const, store: storeB, state: stateB },
  ]
  return (
    <div className="compare-panes" role="group" aria-label="Side-by-side comparison">
      {panes.map(({ side, store, state }) => (
        <section key={side} className="compare-pane" aria-label={`Session ${side.toUpperCase()}`}>
          <header className="compare-pane__label">
            <strong>{side.toUpperCase()}</strong>
            <span>{state.config?.agent ?? '—'}</span>
            <span className="chip">{state.status ?? 'no session'}</span>
            {leader === side && <span className="chip chip--lead">leading</span>}
          </header>
          <SimulationViewport
            store={store}
            rendererKey={rendererKey}
            scene={state.scene}
            environmentName={environmentName}
            status={state.status}
            preview={false}
            cameraResetNonce={cameraResetNonce}
            viewMode={viewMode}
          />
        </section>
      ))}
    </div>
  )
}
