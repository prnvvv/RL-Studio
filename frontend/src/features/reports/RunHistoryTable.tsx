import type { ReactNode } from 'react'
import type { DataTableColumn } from '../../components/ui/DataTable'

interface RunHistoryTableProps<Row> {
  /** Accessible table name (visually hidden; the panel shows the title). */
  caption: string
  columns: DataTableColumn<Row>[]
  rows: Row[]
  getRowId: (row: Row) => string
  /** Rendered inside the table body when there are no rows, keeping the headers visible. */
  empty: ReactNode
}

/**
 * Read-only run table: the same columns, truncation rules and empty-row behaviour as the shared `DataTable`, drawn with
 * the Reports/Monitoring card styling (small uppercase headers, hairline dividers, row hover, monospace identifiers,
 * right-aligned numerics). There is no sorting: no sortable backend contract exists, and an inert header affordance
 * would imply an operation that cannot happen.
 */
export function RunHistoryTable<Row>({
  caption,
  columns,
  rows,
  getRowId,
  empty,
}: RunHistoryTableProps<Row>) {
  const cellClass = (column: DataTableColumn<Row>) =>
    [
      column.align === 'right' ? 'rp-num' : '',
      column.mono ? 'rp-mono' : '',
      column.truncate ? 'rp-clip' : '',
    ]
      .filter(Boolean)
      .join(' ')

  return (
    <div className="rp-table-wrap">
      <table className="rp-table">
        <caption className="visually-hidden">{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.id}
                scope="col"
                className={column.align === 'right' ? 'rp-num' : undefined}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="rp-empty-cell">
                {empty}
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr key={getRowId(row)}>
                {columns.map((column) => (
                  <td
                    key={column.id}
                    className={cellClass(column) || undefined}
                    title={column.truncate ? column.title?.(row) : undefined}
                  >
                    {column.render(row)}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  )
}
