import { AlertTriangleIcon, CheckIcon, ScaleIcon, Trash2Icon } from 'lucide-react'
import { useState } from 'react'

import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Input } from '@/components/ui/input'
import { Label } from '@/components/ui/label'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import type { ExtractedCommit, ExtractedRow, Extraction } from '@/lib/api'
import { formatDate, formatEur } from '@/lib/format'
import { cn } from '@/lib/utils'

const PREVIEW_ROWS = 8

type CommitRow = ExtractedCommit['rows'][number]

/** A row as it stands in the review: what was read, and what the user made of it. */
type Decision = { accept: boolean; booked_on: string; amount: string; description: string }

/** The cents of a typed amount, by the same rule the server reads a printed one with: the
 *  decimal separator is whichever of the comma and the dot comes last. */
function centsOf(text: string): number | null {
  const cleaned = text.trim().replace(/[^\d,.-]/g, '')
  if (!cleaned || cleaned === '-') return null
  const comma = cleaned.lastIndexOf(',')
  const dot = cleaned.lastIndexOf('.')
  const normalized = comma > dot ? cleaned.replace(/\./g, '').replace(',', '.') : cleaned.replace(/,/g, '')
  const value = Number(normalized)
  return Number.isFinite(value) ? Math.round(value * 100) : null
}

const euros = (cents: number | null) => (cents === null ? '' : (cents / 100).toFixed(2).replace('.', ','))

function initial(rows: ExtractedRow[]): Record<number, Decision> {
  const decisions: Record<number, Decision> = {}
  rows.forEach((row, index) => {
    if (!row.flags.length) return
    decisions[index] = {
      accept: false,
      booked_on: row.booked_on ?? '',
      amount: euros(row.amount_cents),
      description: row.description,
    }
  })
  return decisions
}

function committed(row: ExtractedRow, decision: Decision | undefined): CommitRow | null {
  const booked_on = decision ? decision.booked_on : row.booked_on
  const amount_cents = decision ? centsOf(decision.amount) : row.amount_cents
  if (!booked_on || amount_cents === null) return null
  return {
    booked_on,
    amount_cents,
    description: (decision ? decision.description : row.description).trim() || row.description,
    counterparty: row.counterparty,
    balance_cents: row.balance_cents,
    page: row.page,
    line: row.line,
  }
}

function Verdict({ extraction }: { extraction: Extraction }) {
  const ok = extraction.reconciliation.status === 'ok'
  return (
    <div
      className={cn(
        'flex items-start gap-2 rounded-xl border px-4 py-3 text-sm',
        ok ? 'bg-card' : 'border-amber-500/40 bg-amber-500/5',
      )}
    >
      {ok ? (
        <ScaleIcon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-primary" />
      ) : (
        <AlertTriangleIcon aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-amber-600 dark:text-amber-500" />
      )}
      <div>
        <p>{extraction.reconciliation.line}</p>
        {extraction.reconciliation.directions_fixed > 0 && (
          <p className="pt-1 text-muted-foreground text-xs">
            The running balance decided the direction of {extraction.reconciliation.directions_fixed} bookings, because
            this layout prints money in and money out in columns that read the same.
          </p>
        )}
        {extraction.errors.map((error) => (
          <p className="pt-1 text-destructive text-xs" key={error}>
            {error}
          </p>
        ))}
      </div>
    </div>
  )
}

/** The review step of an extraction: the flagged rows one by one, then the commit.
 *
 * A row both guards passed is imported without being asked about. A flagged row is dropped
 * unless it is accepted here, and it can be corrected first: the date, the amount and the
 * description are editable, because the printed line is right there next to them.
 */
export function ExtractionReview({
  extraction,
  accountName,
  onAccountName,
  onCancel,
  onCommit,
  busy,
}: {
  extraction: Extraction
  accountName: string
  onAccountName: (name: string) => void
  onCancel: () => void
  onCommit: (rows: CommitRow[], dropped: number) => void
  busy: boolean
}) {
  const [decisions, setDecisions] = useState<Record<number, Decision>>(() => initial(extraction.rows))
  const [editing, setEditing] = useState<Record<number, boolean>>({})
  const flagged = extraction.rows.map((row, index) => ({ row, index })).filter(({ row }) => row.flags.length > 0)

  const rows: CommitRow[] = []
  let dropped = 0
  extraction.rows.forEach((row, index) => {
    const decision = decisions[index]
    if (row.flags.length && !decision?.accept) {
      dropped += 1
      return
    }
    const next = committed(row, decision)
    if (next) rows.push(next)
    else dropped += 1
  })

  const set = (index: number, patch: Partial<Decision>) =>
    setDecisions((previous) => ({ ...previous, [index]: { ...previous[index], ...patch } }))

  return (
    <section className="space-y-5 rounded-2xl border bg-card p-5">
      <div className="flex flex-wrap items-center gap-2">
        <h2 className="font-heading font-semibold text-sm">{extraction.file_name}</h2>
        <Badge variant={extraction.layout === 'unknown' ? 'outline' : 'secondary'}>{extraction.layout_label}</Badge>
        <span className="text-muted-foreground text-xs">
          {extraction.pages} page{extraction.pages === 1 ? '' : 's'} · {extraction.rows.length} bookings read
          {extraction.scanned_pages.length > 0 && ` · ${extraction.scanned_pages.length} read as images`}
        </span>
      </div>

      <Verdict extraction={extraction} />

      {flagged.length > 0 && (
        <div className="space-y-2">
          <h3 className="font-medium text-xs">
            {flagged.length} booking{flagged.length === 1 ? '' : 's'} could not be verified. Accept, correct or drop
            each one.
          </h3>
          <div className="rounded-xl border">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead className="w-32">Date</TableHead>
                  <TableHead>Description</TableHead>
                  <TableHead className="w-28 text-right">Amount</TableHead>
                  <TableHead className="w-56">Why</TableHead>
                  <TableHead className="w-44 text-right">Decision</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {flagged.map(({ row, index }) => {
                  const decision = decisions[index]
                  const edit = editing[index] === true
                  return (
                    <TableRow className={decision?.accept ? undefined : 'opacity-60'} key={index}>
                      <TableCell className="tabular-nums">
                        {edit ? (
                          <Input
                            className="h-7 text-xs"
                            onChange={(event) => set(index, { booked_on: event.target.value, accept: true })}
                            placeholder="YYYY-MM-DD"
                            value={decision?.booked_on ?? ''}
                          />
                        ) : (
                          (decision?.booked_on ? formatDate(decision.booked_on) : '—')
                        )}
                      </TableCell>
                      <TableCell className="max-w-[18rem]">
                        {edit ? (
                          <Input
                            className="h-7 text-xs"
                            onChange={(event) => set(index, { description: event.target.value, accept: true })}
                            value={decision?.description ?? ''}
                          />
                        ) : (
                          <>
                            <p className="truncate" title={decision?.description}>
                              {decision?.description}
                            </p>
                            {row.source && (
                              <p className="truncate font-mono text-[11px] text-muted-foreground" title={row.source}>
                                p{row.page}
                                {row.line ? `:${row.line}` : ''} {row.source}
                              </p>
                            )}
                          </>
                        )}
                      </TableCell>
                      <TableCell className="text-right tabular-nums">
                        {edit ? (
                          <Input
                            className="h-7 text-right text-xs"
                            onChange={(event) => set(index, { amount: event.target.value, accept: true })}
                            value={decision?.amount ?? ''}
                          />
                        ) : (
                          formatEur(centsOf(decision?.amount ?? '') ?? 0)
                        )}
                      </TableCell>
                      <TableCell className="text-amber-600 text-xs dark:text-amber-500">{row.reason}</TableCell>
                      <TableCell>
                        <div className="flex items-center justify-end gap-1">
                          <Button
                            className="h-7 px-2 text-xs"
                            onClick={() => set(index, { accept: true })}
                            size="sm"
                            variant={decision?.accept ? 'default' : 'outline'}
                          >
                            <CheckIcon className="size-3" />
                            Accept
                          </Button>
                          <Button
                            className="h-7 px-2 text-xs"
                            onClick={() => setEditing((previous) => ({ ...previous, [index]: !edit }))}
                            size="sm"
                            variant="ghost"
                          >
                            {edit ? 'Done' : 'Edit'}
                          </Button>
                          <Button
                            className="h-7 px-2 text-xs"
                            onClick={() => {
                              set(index, { accept: false })
                              setEditing((previous) => ({ ...previous, [index]: false }))
                            }}
                            size="sm"
                            variant={decision?.accept ? 'ghost' : 'secondary'}
                          >
                            <Trash2Icon className="size-3" />
                            Drop
                          </Button>
                        </div>
                      </TableCell>
                    </TableRow>
                  )
                })}
              </TableBody>
            </Table>
          </div>
        </div>
      )}

      <div className="space-y-2">
        <h3 className="font-medium text-xs">
          First {Math.min(PREVIEW_ROWS, rows.length)} of {rows.length} bookings that would be imported
        </h3>
        <div className="rounded-xl border">
          <Table>
            <TableHeader>
              <TableRow>
                <TableHead className="w-28">Date</TableHead>
                <TableHead>Description</TableHead>
                <TableHead className="text-right">Amount</TableHead>
                <TableHead className="text-right">Balance</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {rows.slice(0, PREVIEW_ROWS).map((row, index) => (
                <TableRow key={`${row.booked_on}-${index}`}>
                  <TableCell className="whitespace-nowrap tabular-nums">{formatDate(row.booked_on)}</TableCell>
                  <TableCell className="max-w-[24rem] truncate" title={row.description}>
                    {row.description}
                  </TableCell>
                  <TableCell
                    className={cn(
                      'whitespace-nowrap text-right tabular-nums',
                      row.amount_cents > 0 ? 'text-primary' : 'text-foreground',
                    )}
                  >
                    {formatEur(row.amount_cents)}
                  </TableCell>
                  <TableCell className="whitespace-nowrap text-right text-muted-foreground tabular-nums">
                    {row.balance_cents === null ? '—' : formatEur(row.balance_cents)}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </div>
      </div>

      <div className="flex flex-wrap items-end justify-between gap-3 border-t pt-4">
        <div className="space-y-1.5">
          <Label className="text-muted-foreground text-xs" htmlFor="extract-account">
            Account
          </Label>
          <Input
            className="w-64"
            id="extract-account"
            onChange={(event) => onAccountName(event.target.value)}
            value={accountName}
          />
        </div>
        <div className="flex items-center gap-2">
          {dropped > 0 && <span className="text-muted-foreground text-xs">{dropped} dropped</span>}
          <Button onClick={onCancel} size="sm" variant="ghost">
            Cancel
          </Button>
          <Button
            disabled={busy || !accountName.trim() || rows.length === 0}
            onClick={() => onCommit(rows, dropped)}
            size="sm"
          >
            Import {rows.length} bookings
          </Button>
        </div>
      </div>
    </section>
  )
}
