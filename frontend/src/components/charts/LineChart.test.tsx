import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LineChart } from './LineChart'

describe('LineChart', () => {
  it('renders an explicit empty state when no series data exists', () => {
    render(
      <LineChart
        title="Reward versus training steps"
        series={[]}
        xLabel="Training steps"
        yLabel="Episode reward"
      />,
    )

    expect(screen.getByRole('img', { name: /no data recorded/i })).toBeInTheDocument()
  })

  it('renders one legend entry per series and an accessible label', () => {
    render(
      <LineChart
        title="Reward versus training steps"
        series={[
          { id: 'current', label: 'Current Run', lineStyle: 'solid', emphasis: true, points: [{ x: 1, y: 2 }, { x: 2, y: 4 }] },
          { id: 'baseline', label: 'Healthy Baseline', lineStyle: 'dashed', points: [{ x: 1, y: 3 }, { x: 2, y: 5 }] },
        ]}
        markers={[{ x: 2, label: 'Fault injected' }]}
        xLabel="Training steps"
        yLabel="Episode reward"
      />,
    )

    expect(screen.getByRole('img', { name: /Current Run: 2 points/ })).toBeInTheDocument()
    expect(screen.getByText('Current Run')).toBeInTheDocument()
    expect(screen.getByText('Healthy Baseline')).toBeInTheDocument()
    expect(screen.getByText('Fault injected')).toBeInTheDocument()
    expect(screen.getByText('Training steps')).toBeInTheDocument()
    expect(screen.getByText('Episode reward')).toBeInTheDocument()
  })
})
