import { ReactNode } from 'react'

export interface DataTableColumn<Row> {
  id: string
  header: string
  render: (row: Row) => ReactNode
  /** Numeric columns align right so digits line up between rows. */
  align?: 'left' | 'right'
  /** Identifiers and timestamps use the monospace face. */
  mono?: boolean
  /**
   * Visually clips long values instead of letting one cell widen the table.
   * The full text stays in the DOM, so assistive technology still reads it.
   */
  truncate?: boolean
  /** Optional full value for the hover tooltip of a truncated cell. */
  title?: (row: Row) => string | undefined
}

interface DataTableProps<Row> {
  /** Accessible table name. Rendered visually hidden; the panel shows the title. */
  caption: string
  columns: DataTableColumn<Row>[]
  rows: Row[]
  getRowId: (row: Row) => string
  /** Rendered inside the table body when there are no rows, keeping headers visible. */
  empty: ReactNode
}

/**
 * Dense, read-only table.
 *
 * Sorting and filtering controls are intentionally absent: no sortable or
 * queryable backend contract exists yet, and an inert header affordance would
 * imply an operation that cannot happen.
 */
export function DataTable<Row>({ caption, columns, rows, getRowId, empty }: DataTableProps<Row>) {
  return (
    <div style={{ overflowX: 'auto' }}>
      <table
        style={{
          width: '100%',
          borderCollapse: 'collapse',
          fontFamily: 'var(--font-sans)',
          tableLayout: 'auto',
        }}
      >
        <caption className="visually-hidden">{caption}</caption>
        <thead>
          <tr>
            {columns.map((column) => (
              <th
                key={column.id}
                scope="col"
                style={{
                  padding: 'var(--space-2) var(--space-3)',
                  borderBottom: '1px solid var(--border-primary)',
                  textAlign: column.align === 'right' ? 'right' : 'left',
                  fontSize: '10px',
                  fontWeight: 600,
                  letterSpacing: '0.06em',
                  textTransform: 'uppercase',
                  color: 'var(--text-muted)',
                  whiteSpace: 'nowrap',
                }}
              >
                {column.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.length === 0 ? (
            <tr>
              <td colSpan={columns.length} style={{ padding: 0 }}>
                {empty}
              </td>
            </tr>
          ) : (
            rows.map((row) => (
              <tr key={getRowId(row)}>
                {columns.map((column) => (
                  <td
                    key={column.id}
                    style={{
                      padding: 'var(--space-2) var(--space-3)',
                      borderBottom: '1px solid var(--border-secondary)',
                      textAlign: column.align === 'right' ? 'right' : 'left',
                      fontSize: 'var(--text-sm)',
                      color: 'var(--text-primary)',
                      fontFamily: column.mono ? 'var(--font-mono)' : 'var(--font-sans)',
                      fontVariantNumeric: column.align === 'right' ? 'tabular-nums' : 'normal',
                      verticalAlign: 'top',
                      ...(column.truncate
                        ? {
                            maxWidth: '20ch',
                            overflow: 'hidden',
                            textOverflow: 'ellipsis',
                            whiteSpace: 'nowrap',
                          }
                        : null),
                    }}
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
