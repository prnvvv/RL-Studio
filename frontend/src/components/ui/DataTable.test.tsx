import { describe, expect, it } from 'vitest'
import { render, screen, within } from '@testing-library/react'
import { DataTable, DataTableColumn } from './DataTable'

interface Row {
  id: string
  name: string
  value: string | null
}

const columns: DataTableColumn<Row>[] = [
  { id: 'id', header: 'Run ID', mono: true, render: (row) => row.id },
  { id: 'name', header: 'Environment', render: (row) => row.name },
  {
    id: 'value',
    header: 'Steps',
    align: 'right',
    render: (row) => row.value ?? 'Not available',
  },
]

const rows: Row[] = [
  { id: 'run_0002', name: 'warehouse_v1', value: '12000' },
  { id: 'run_0001', name: 'cartpole_v1', value: null },
]

describe('DataTable', () => {
  it('renders a semantic table with scoped column headers and a hidden caption', () => {
    render(
      <DataTable
        caption="Recorded runs"
        columns={columns}
        rows={rows}
        getRowId={(row) => row.id}
        empty={null}
      />,
    )

    const table = screen.getByRole('table', { name: 'Recorded runs' })
    const headers = within(table).getAllByRole('columnheader')
    expect(headers.map((header) => header.textContent)).toEqual(['Run ID', 'Environment', 'Steps'])
    headers.forEach((header) => expect(header).toHaveAttribute('scope', 'col'))
  })

  it('preserves the supplied row order rather than re-sorting', () => {
    render(
      <DataTable
        caption="Recorded runs"
        columns={columns}
        rows={rows}
        getRowId={(row) => row.id}
        empty={null}
      />,
    )

    const bodyRows = within(screen.getByRole('table')).getAllByRole('row').slice(1)
    expect(bodyRows[0]).toHaveTextContent('run_0002')
    expect(bodyRows[1]).toHaveTextContent('run_0001')
  })

  it('renders the empty content inside the table body so headers stay visible', () => {
    render(
      <DataTable
        caption="Recorded runs"
        columns={columns}
        rows={[]}
        getRowId={(row) => row.id}
        empty={<span>No run records</span>}
      />,
    )

    expect(screen.getByText('No run records')).toBeInTheDocument()
    expect(screen.getAllByRole('columnheader')).toHaveLength(3)
    // Only the header row and the single empty cell row exist.
    expect(screen.getAllByRole('row')).toHaveLength(2)
    expect(screen.getAllByRole('cell')).toHaveLength(1)
  })

  it('offers no sort or filter affordance, since neither is supported', () => {
    render(
      <DataTable
        caption="Recorded runs"
        columns={columns}
        rows={rows}
        getRowId={(row) => row.id}
        empty={null}
      />,
    )

    expect(screen.queryAllByRole('button')).toHaveLength(0)
    expect(screen.queryByRole('searchbox')).not.toBeInTheDocument()
  })
})
