import { render, screen, within } from '@testing-library/react'
import { describe, expect, it } from 'vitest'
import { BrainPanel } from './BrainPanel'
import { actionLabels, cellKey, confidence, gridLookup, heatOpacity } from './brainHelpers'
import { CartPole2D } from './renderers/CartPole2D'
import { GridMaze2D } from './renderers/GridMaze2D'
import type { ScenePalette } from './renderers/palette'
import { StudioStore } from './studioStore'
import type { BrainPayload, FramePayload } from './studioTypes'
import { i18n } from '../i18n'
import { I18nextProvider } from 'react-i18next'
import { renderToString } from 'react-dom/server'

const palette: ScenePalette = {
  background: '#000',
  floor: '#111',
  grid: '#222',
  structure: '#555',
  agent: '#fff',
  accent: '#bbb',
  good: '#0f0',
  bad: '#f00',
  text: '#aaa',
}

const frame = (brain?: BrainPayload, extra: Partial<FramePayload> = {}): FramePayload => ({
  timestep: 3,
  episode: 1,
  episode_step: 3,
  action: 1,
  reward: 1,
  episode_reward: 3,
  collision: false,
  disturbance: false,
  done: false,
  state: { x: 0, x_dot: 0, theta: 0, theta_dot: 0, row: 1, col: 1 },
  ...(brain ? { brain } : {}),
  ...extra,
})

describe('brain helpers', () => {
  it('labels actions per environment and falls back to numbers', () => {
    expect(actionLabels('cartpole', 2)).toEqual(['Push left', 'Push right'])
    expect(actionLabels('grid_maze', 4)).toEqual(['Up', 'Down', 'Left', 'Right'])
    expect(actionLabels('mystery', 2)).toEqual(['Action 0', 'Action 1'])
    expect(actionLabels(null, 1)).toEqual(['Action 0'])
  })

  it('reports confidence as the top probability', () => {
    expect(confidence([0.2, 0.7, 0.1])).toBe(0.7)
    expect(confidence([])).toBeNull()
    expect(confidence(undefined)).toBeNull()
  })

  it('keeps a no-preference cell faint and a certain cell strong', () => {
    const faint = heatOpacity([0.25, 0.25, 0.25, 0.25])
    const strong = heatOpacity([1, 0, 0, 0])
    const middling = heatOpacity([0.6, 0.2, 0.1, 0.1])
    expect(faint).toBeCloseTo(0.08)
    expect(strong).toBeCloseTo(0.8)
    expect(middling).toBeGreaterThan(faint)
    expect(middling).toBeLessThan(strong)
  })

  it('indexes grid cells by row and column', () => {
    const lookup = gridLookup([{ row: 2, col: 3, probs: [1, 0, 0, 0], greedy: 0 }])
    expect(lookup.get(cellKey(2, 3))?.greedy).toBe(0)
    expect(gridLookup(undefined).size).toBe(0)
  })
})

describe('BrainPanel', () => {
  it('waits until the backend sends a decision', () => {
    const { unmount } = render(
      <I18nextProvider i18n={i18n}>
        <BrainPanel store={new StudioStore()} renderer="cartpole" />
      </I18nextProvider>
    )
    expect(screen.getByText('Waiting for the first decision…')).toBeInTheDocument()
    unmount()
  })

  it('shows action probabilities and marks the action taken', () => {
    const store = new StudioStore()
    store.applyFrame(frame({ kind: 'probs', probs: [0.25, 0.75], greedy: 1, executed: 1 }))
    render(
      <I18nextProvider i18n={i18n}>
        <BrainPanel store={store} renderer="cartpole" />
      </I18nextProvider>
    )
    const panel = screen.getByRole('status', { name: 'Agent brain' })
    expect(within(panel).getByText('Push right')).toBeInTheDocument()
    expect(within(panel).getByText('75%')).toBeInTheDocument()
    expect(within(panel).getByText('taken')).toBeInTheDocument()
  })

  it('labels DQN output as Q-values and prints the raw numbers', () => {
    const store = new StudioStore()
    store.applyFrame(
      frame({
        kind: 'q',
        q: [1.5, 0.5],
        probs: [0.73, 0.27],
        probs_from: 'softmax(q)',
        greedy: 0,
        executed: 0,
      }),
    )
    render(
      <I18nextProvider i18n={i18n}>
        <BrainPanel store={store} renderer="cartpole" />
      </I18nextProvider>
    )
    expect(screen.getByText('Agent brain · Q-values (softmax)')).toBeInTheDocument()
    expect(screen.getByText(/Q 1\.50 · 73%/)).toBeInTheDocument()
  })

  it('shows the mean and spread of a Gaussian policy', () => {
    const store = new StudioStore()
    store.applyFrame(frame({ kind: 'gaussian', mean: [0.5], std: [0.2], executed: [0.4] }))
    render(
      <I18nextProvider i18n={i18n}>
        <BrainPanel store={store} renderer={null} />
      </I18nextProvider>
    )
    expect(screen.getByText(/μ 0\.500 · σ 0\.200/)).toBeInTheDocument()
  })
})

describe('renderer overlays', () => {
  const scene = { x_limit: 2.4, theta_limit: 0.2, pole_length: 1 }
  const grid = { rows: 2, cols: 2, start: [0, 0], goal: [1, 1], obstacles: [[0, 1]] }

  it('draws no brain graphics until brain data arrives', () => {
    const store = new StudioStore()
    store.applyFrame(frame())
    const { unmount } = render(<CartPole2D scene={scene} store={store} palette={palette} />)
    expect(screen.queryAllByTestId('brain-arrow')).toHaveLength(0)
    unmount()
    render(<GridMaze2D scene={grid} store={store} palette={palette} />)
    expect(screen.queryAllByTestId('brain-cell')).toHaveLength(0)
  })

  it('draws a push arrow per direction sized by probability', () => {
    const store = new StudioStore()
    store.applyFrame(frame({ kind: 'probs', probs: [0.1, 0.9], greedy: 1, executed: 1 }))
    render(<CartPole2D scene={scene} store={store} palette={palette} />)
    const arrows = screen.getAllByTestId('brain-arrow')
    expect(arrows).toHaveLength(2)
    expect(Number(arrows[1].getAttribute('opacity'))).toBeGreaterThan(
      Number(arrows[0].getAttribute('opacity')),
    )
  })

  it('draws one heat cell per free grid cell with the preferred direction', () => {
    const store = new StudioStore()
    store.applyFrame(
      frame({
        kind: 'probs',
        probs: [0.1, 0.7, 0.1, 0.1],
        greedy: 1,
        executed: 1,
        grid: [
          { row: 0, col: 0, probs: [0.1, 0.7, 0.1, 0.1], greedy: 1 },
          { row: 1, col: 0, probs: [0.1, 0.1, 0.1, 0.7], greedy: 3 },
          { row: 1, col: 1, probs: [0.25, 0.25, 0.25, 0.25], greedy: 0 },
        ],
      }),
    )
    render(<GridMaze2D scene={grid} store={store} palette={palette} />)
    const cells = screen.getAllByTestId('brain-cell')
    expect(cells).toHaveLength(3)
    expect(cells[1].querySelector('polygon')?.getAttribute('transform')).toBe('rotate(90)')
    const opacity = (i: number) => Number(cells[i].querySelector('rect')?.getAttribute('opacity'))
    expect(opacity(2)).toBeLessThan(opacity(0))
  })
})
