import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { LiveStatsPanel, LiveStatRow } from './LiveStatsPanel'

const rows: LiveStatRow[] = [
  { id: 'episode', label: 'Episode', kind: 'episode', value: '128' },
  { id: 'success', label: 'Success Rate', kind: 'success', value: '92.5', unit: '%' },
  { id: 'reward', label: 'Average Reward', kind: 'reward', value: null },
]

describe('LiveStatsPanel', () => {
  it('renders recorded values with units and marks missing values explicitly', () => {
    render(<LiveStatsPanel rows={rows} />)

    expect(screen.getByText('Episode')).toBeInTheDocument()
    expect(screen.getByText('128')).toBeInTheDocument()
    expect(screen.getByText('92.5')).toBeInTheDocument()
    expect(screen.getByText('%')).toBeInTheDocument()
    expect(screen.getByText('Not available')).toBeInTheDocument()
  })

  it('never substitutes zero for a missing statistic', () => {
    render(
      <LiveStatsPanel rows={[{ id: 'steps', label: 'Total Steps', kind: 'steps', value: null }]} />,
    )

    expect(screen.queryByText('0')).not.toBeInTheDocument()
    expect(screen.queryByText('—')).not.toBeInTheDocument()
  })
})
