import { actionLabels } from './brainHelpers'
import { useFrameSnapshot } from './useFrameSnapshot'
import type { StudioStore } from './studioStore'

interface Props {
  store: StudioStore
  renderer: string | null
}

/**
 * Live readout of the policy's current decision. Values come straight from the
 * backend (`frame.brain`); the bars are the action probabilities, and for DQN the
 * softmax of the Q-values with the raw Q-values printed alongside.
 */
export function BrainPanel({ store, renderer }: Props) {
  const frame = useFrameSnapshot(store)
  const brain = frame?.brain

  if (!brain) {
    return (
      <div className="brain-panel" role="status">
        <strong>Agent brain</strong>
        <span className="brain-panel__empty">Waiting for the first decision…</span>
      </div>
    )
  }

  if (brain.kind === 'gaussian') {
    return (
      <div className="brain-panel" role="status" aria-label="Agent brain">
        <strong>Agent brain · Gaussian policy</strong>
        {(brain.mean ?? []).map((mean, i) => (
          <div key={i} className="brain-panel__row">
            <span>Action {i}</span>
            <span>
              μ {mean.toFixed(3)} · σ {(brain.std?.[i] ?? 0).toFixed(3)}
            </span>
          </div>
        ))}
      </div>
    )
  }

  const probs = brain.probs ?? []
  const labels = actionLabels(renderer, probs.length)
  const title =
    brain.kind === 'q' ? 'Agent brain · Q-values (softmax)' : 'Agent brain · action probabilities'
  return (
    <div className="brain-panel" role="status" aria-label="Agent brain">
      <strong>{title}</strong>
      {probs.map((p, i) => (
        <div key={i} className="brain-panel__row" data-greedy={brain.greedy === i || undefined}>
          <span>{labels[i]}</span>
          <span className="brain-panel__bar" aria-hidden="true">
            <span style={{ width: `${Math.round(p * 100)}%` }} />
          </span>
          <span className="brain-panel__value">
            {brain.kind === 'q' && brain.q ? `Q ${brain.q[i].toFixed(2)} · ` : ''}
            {(p * 100).toFixed(0)}%
          </span>
          {brain.executed === i && <span className="chip">taken</span>}
        </div>
      ))}
    </div>
  )
}
