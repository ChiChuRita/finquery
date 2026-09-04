import type { ReactNode } from 'react'

import { MessageResponse } from '@/components/ai-elements/message'
import { Tool, ToolContent, ToolHeader } from '@/components/ai-elements/tool'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { QueryToolOutput, QueryToolPart, QueryValue } from '@/lib/api'

// Euro figures keep both decimals, counts and years stay bare.
const decimals = new Intl.NumberFormat('de-DE', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
const integers = new Intl.NumberFormat('de-DE', { maximumFractionDigits: 0 })

const rows = (count: number) => (count === 1 ? '1 row' : `${count} rows`)

function value(cell: QueryValue, fractional: boolean) {
  if (cell === null) return '—'
  if (typeof cell === 'number') return fractional ? decimals.format(cell) : integers.format(cell)
  if (typeof cell === 'boolean') return String(cell)
  return cell
}

/** A column with one fractional value is money: every value in it keeps both decimals. */
function fractionalColumns(output: QueryToolOutput): Set<string> {
  const columns = new Set<string>()
  for (const row of output.rows) {
    for (const column of output.columns) {
      const cell = row[column]
      if (typeof cell === 'number' && !Number.isInteger(cell)) columns.add(column)
    }
  }
  return columns
}

function title(part: QueryToolPart) {
  if (part.state === 'output-error') return 'Query failed'
  if (part.state !== 'output-available') return 'Querying your transactions'
  return part.output.error ? 'Query refused' : `Query · ${rows(part.output.row_count)}`
}

function Section({ label, children }: { label: string; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <h4 className="font-medium text-muted-foreground text-xs uppercase tracking-wide">{label}</h4>
      {children}
    </div>
  )
}

function Result({ output, hints }: { output: QueryToolOutput; hints?: string | null }) {
  const fractional = fractionalColumns(output)
  return (
    <>
      <Section label="Request">
        <p className="text-sm">{output.request}</p>
        {hints && <p className="text-muted-foreground text-sm">Hints: {hints}</p>}
      </Section>
      {output.sql && (
        <Section label="SQL that ran">
          <MessageResponse className="text-sm">{'```sql\n' + output.sql + '\n```'}</MessageResponse>
        </Section>
      )}
      {output.error ? (
        <Section label="Error">
          <p className="rounded-md bg-destructive/10 px-3 py-2 text-destructive text-sm">{output.error}</p>
        </Section>
      ) : (
        <Section label={`Result · ${rows(output.row_count)}`}>
          {output.row_count === 0 ? (
            <p className="text-muted-foreground text-sm">No row matched.</p>
          ) : (
            <div className="max-h-80 overflow-auto rounded-md border">
              <Table>
                <TableHeader className="sticky top-0 bg-muted/80 backdrop-blur">
                  <TableRow>
                    {output.columns.map((column) => (
                      <TableHead className="whitespace-nowrap font-mono text-xs" key={column}>
                        {column}
                      </TableHead>
                    ))}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {output.rows.map((row, index) => (
                    // The rows have no key of their own: a result is a value, not a list of entities.
                    // oxlint-disable-next-line eslint(no-array-index-key)
                    <TableRow key={index}>
                      {output.columns.map((column) => (
                        <TableCell className="whitespace-nowrap tabular-nums" key={column}>
                          {value(row[column] ?? null, fractional.has(column))}
                        </TableCell>
                      ))}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          )}
        </Section>
      )}
    </>
  )
}

/** One executed query in the transcript: the request, the SQL, the row count and the rows. */
export function QueryToolStep({ part }: { part: QueryToolPart }) {
  return (
    <Tool className="mb-0 w-full">
      <ToolHeader state={part.state} title={title(part)} type="tool-query" />
      <ToolContent>
        {part.state === 'output-available' ? (
          <Result hints={part.input?.hints} output={part.output} />
        ) : (
          <>
            <Section label="Request">
              <p className="text-sm">{part.input?.request ?? 'Writing the query...'}</p>
            </Section>
            {part.state === 'output-error' && (
              <Section label="Error">
                <p className="rounded-md bg-destructive/10 px-3 py-2 text-destructive text-sm">{part.errorText}</p>
              </Section>
            )}
          </>
        )}
      </ToolContent>
    </Tool>
  )
}
