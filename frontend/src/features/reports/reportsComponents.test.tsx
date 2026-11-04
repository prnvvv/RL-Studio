import { fireEvent, render, screen, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { describe, expect, it, vi } from 'vitest'
import type { DataTableColumn } from '../../components/ui/DataTable'
import { RunFilter } from './RunFilter'
import { RunHistoryTable } from './RunHistoryTable'

// Test-only rows: the Reports page itself never renders sample runs.
interface Row {
  id: string
  env: string | null
  steps: number
  status: string | null
}

const rows: Row[] = [
  { id: 'run_alpha', env: 'cartpole', steps: 1200, status: 'completed' },
  {
    id: 'a-very-long-run-identifier-that-must-not-break-the-layout',
    env: null,
    steps: 45,
    status: null,
  },
]

const columns: DataTableColumn<Row>[] = [
  {
    id: 'id',
    header: 'Run ID',
    mono: true,
    truncate: true,
    title: (r) => r.id,
    render: (r) => r.id,
  },
  { id: 'env', header: 'Environment', render: (r) => r.env ?? 'Not available' },
  { id: 'steps', header: 'Steps', align: 'right', render: (r) => r.steps },
  { id: 'status', header: 'Status', render: (r) => r.status ?? 'Not available' },
]

function table(data: Row[]) {
  return render(
    <MemoryRouter>
      <RunHistoryTable
        caption="Runs"
        columns={columns}
        rows={data}
        getRowId={(r) => r.id}
        empty={<p>nothing here</p>}
      />
    </MemoryRouter>,
  )
}

describe('RunHistoryTable', () => {
  it('renders headers and populated rows with monospace ids and right-aligned numbers', () => {
    table(rows)
    expect(screen.getAllByRole('columnheader').map((h) => h.textContent)).toEqual([
      'Run ID',
      'Environment',
      'Steps',
      'Status',
    ])
    const first = screen.getAllByRole('row')[1]
    const cells = within(first).getAllByRole('cell')
    expect(cells[0]).toHaveClass('rp-mono', 'rp-clip')
    expect(cells[2]).toHaveClass('rp-num')
    expect(screen.getAllByRole('columnheader')[2]).toHaveClass('rp-num')
  })

  it('clips long identifiers visually but keeps the full text and a tooltip', () => {
    table(rows)
    const long = 'a-very-long-run-identifier-that-must-not-break-the-layout'
    const cell = screen.getByText(long).closest('td')
    expect(cell).toHaveClass('rp-clip')
    expect(cell).toHaveAttribute('title', long)
  })

  it('shows the supplied empty state inside the body while keeping the headers', () => {
    table([])
    expect(screen.getAllByRole('columnheader')).toHaveLength(4)
    expect(screen.getByText('nothing here')).toBeInTheDocument()
    expect(screen.getAllByRole('row')).toHaveLength(2)
  })

  it('has no sort or action controls', () => {
    table(rows)
    expect(screen.queryAllByRole('button')).toHaveLength(0)
  })
})

describe('RunFilter', () => {
  const base = {
    label: 'Filter runs',
    onChange: vi.fn(),
    onReset: vi.fn(),
    summary: '1 of 2 shown.',
  }

  it('is a labelled search with a polite status', () => {
    render(<RunFilter {...base} value="" />)
    expect(screen.getByRole('search', { name: 'Filter runs controls' })).toBeInTheDocument()
    expect(screen.getByLabelText('Filter runs')).toHaveAttribute('type', 'search')
    expect(screen.getByRole('status', { name: 'Filter results' })).toHaveTextContent(
      '1 of 2 shown.',
    )
  })

  it('reports changes and offers a clear action only when there is a query', () => {
    const onChange = vi.fn()
    const onReset = vi.fn()
    const { rerender } = render(
      <RunFilter {...base} onChange={onChange} onReset={onReset} value="" />,
    )
    expect(screen.queryByRole('button', { name: 'Clear filter' })).not.toBeInTheDocument()
    fireEvent.change(screen.getByLabelText('Filter runs'), { target: { value: 'cart' } })
    expect(onChange).toHaveBeenCalledWith('cart')
    rerender(
      <RunFilter
        {...base}
        onChange={onChange}
        onReset={onReset}
        value="cart"
        scopeNote="Loaded page only."
      />,
    )
    fireEvent.click(screen.getByRole('button', { name: 'Clear filter' }))
    expect(onReset).toHaveBeenCalled()
    expect(screen.getByRole('status', { name: 'Filter results' })).toHaveTextContent(
      'Loaded page only.',
    )
  })

  it('is disabled with a stated reason, and refuses to be disabled without one', () => {
    render(<RunFilter {...base} value="" disabled disabledReason="Nothing to filter." />)
    expect(screen.getByLabelText('Filter runs')).toBeDisabled()
    expect(screen.getByRole('status', { name: 'Filter results' })).toHaveTextContent(
      'Nothing to filter.',
    )
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<RunFilter {...base} value="" disabled />)).toThrow(/disabledReason/)
    spy.mockRestore()
  })
})
