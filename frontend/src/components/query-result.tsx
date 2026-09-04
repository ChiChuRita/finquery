import type { ReactNode } from 'react'

import { MessageResponse } from '@/components/ai-elements/message'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { QueryValue } from '@/lib/api'

// Euro figures keep both decimals, counts and years stay bare.
const decimals = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const integers = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 0 })

/** "1 row" or "12 rows", the label every result carries. */
export const rowLabel = (count: number) => (count === 1 ? '1 row' : `${count} rows`)

function value(cell: QueryValue, fractional: boolean) {
  if (cell === null) return '—'
  if (typeof cell === 'number') return fractional ? decimals.format(cell) : integers.format(cell)
  if (typeof cell === 'boolean') return String(cell)
  return cell
}

/** A column with one fractional value is money: every value in it keeps both decimals. */
function fractionalColumns(columns: string[], rows: Record<string, QueryValue>[]): Set<string> {
  const fractional = new Set<string>()
  for (const row of rows) {
    for (const column of columns) {
      const cell = row[column]
      if (typeof cell === 'number' && !Number.isInteger(cell)) fractional.add(column)
    }
  }
  return fractional
}

/** One labelled block of a tool step. */
export function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <h4 className="font-medium text-muted-foreground text-xs uppercase tracking-wide">{label}</h4>
      {children}
    </div>
  )
}

export function ErrorSection({ message }: { message: string }) {
  return (
    <Section label="Error">
      <p className="rounded-md bg-destructive/10 px-3 py-2 text-destructive text-sm">{message}</p>
    </Section>
  )
}

/** The statement that ran, through the app's one markdown code renderer. */
export function SqlSection({ sql }: { sql: string }) {
  return (
    <Section label="SQL that ran">
      <MessageResponse className="text-sm">{'```sql\n' + sql + '\n```'}</MessageResponse>
    </Section>
  )
}

/** The rows behind a number or a chart, scrollable and header-sticky. */
export function RowsTable({ columns, rows }: { columns: string[]; rows: Record<string, QueryValue>[] }) {
  const fractional = fractionalColumns(columns, rows)
  if (rows.length === 0) return <p className="text-muted-foreground text-sm">No row matched.</p>
  return (
    <div className="max-h-80 overflow-auto rounded-md border">
      <Table>
        <TableHeader className="sticky top-0 bg-muted/80 backdrop-blur">
          <TableRow>
            {columns.map((column) => (
              <TableHead className="whitespace-nowrap font-mono text-xs" key={column}>
                {column}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {rows.map((row, index) => (
            // The rows have no key of their own: a result is a value, not a list of entities.
            // oxlint-disable-next-line eslint(no-array-index-key)
            <TableRow key={index}>
              {columns.map((column) => (
                <TableCell className="whitespace-nowrap tabular-nums" key={column}>
                  {value(row[column] ?? null, fractional.has(column))}
                </TableCell>
              ))}
            </TableRow>
          ))}
        </TableBody>
      </Table>
    </div>
  )
}
