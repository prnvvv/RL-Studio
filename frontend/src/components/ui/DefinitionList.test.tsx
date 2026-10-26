import { describe, expect, it } from 'vitest'
import { render, screen } from '@testing-library/react'
import { DefinitionList, DefinitionRow } from './DefinitionList'

const rows: DefinitionRow[] = [
  { id: 'name', label: 'Environment', value: 'warehouse-navigation' },
  { id: 'version', label: 'Environment version', value: null },
]

describe('DefinitionList', () => {
  it('renders provided values and an explicit state for missing values', () => {
    render(<DefinitionList rows={rows} caption="Values are populated only from a loaded record." />)

    expect(screen.getByText('Environment')).toBeInTheDocument()
    expect(screen.getByText('warehouse-navigation')).toBeInTheDocument()

    expect(screen.getByText('Environment version')).toBeInTheDocument()
    expect(screen.getByText('Not available')).toBeInTheDocument()
    expect(screen.getByText('Values are populated only from a loaded record.')).toBeInTheDocument()
  })

  it('does not substitute a zero or dash for a missing value', () => {
    render(<DefinitionList rows={[{ id: 'steps', label: 'Total steps', value: null }]} />)

    expect(screen.queryByText('0')).not.toBeInTheDocument()
    expect(screen.queryByText('—')).not.toBeInTheDocument()
  })
})
