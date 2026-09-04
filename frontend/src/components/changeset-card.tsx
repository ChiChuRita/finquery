import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  ArrowRightIcon,
  CheckIcon,
  ClockAlertIcon,
  LayersIcon,
  PencilIcon,
  ScissorsIcon,
  TagsIcon,
  Trash2Icon,
  UndoIcon,
  XIcon,
} from 'lucide-react'

import { Shimmer } from '@/components/ai-elements/shimmer'
import { Badge } from '@/components/ui/badge'
import { Button } from '@/components/ui/button'
import { Spinner } from '@/components/ui/spinner'
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table'
import {
  applyChangeset,
  changesetQuery,
  discardChangeset,
  undoChangeset,
  type Changeset,
  type ChangesetField,
  type ChangesetKind,
  type ChangesetRow,
  type ChangesetToolPart,
} from '@/lib/api'
import { formatEur } from '@/lib/format'
import { cn } from '@/lib/utils'
import { useWorkspace } from '@/lib/workspace'

const KIND_ICON: Record<ChangesetKind, typeof PencilIcon> = {
  recategorize: TagsIcon,
  split: ScissorsIcon,
  edit: PencilIcon,
  delete: Trash2Icon,
  taxonomy: LayersIcon,
}

const KIND_LABEL: Record<ChangesetKind, string> = {
  recategorize: 'Recategorize',
  split: 'Split',
  edit: 'Edit',
  delete: 'Delete',
  taxonomy: 'Categories',
}

const FIELD_LABEL: Record<ChangesetField, string> = {
  date: 'Date',
  description: 'Description',
  amount: 'Amount',
  category: 'Category',
  subcategory: 'Subcategory',
}

/** The absence of a category has a name, and it is not an empty cell. */
const NEEDS_REVIEW = 'Needs review'

function display(field: ChangesetField, value: string | null | undefined) {
  if (value === null || value === undefined) return field === 'category' ? NEEDS_REVIEW : '—'
  // The preview carries plain decimals; the euro sign is a display decision.
  return field === 'amount' ? formatEur(Math.round(Number(value) * 100)) : value
}

function statusLabel(changeset: Changeset) {
  switch (changeset.status) {
    case 'proposed':
      return 'Waiting for you'
    case 'applied':
      return 'Applied'
    case 'discarded':
      // An undone edit was applied once, which is what tells it from a discarded proposal.
      return changeset.applied_at ? 'Reverted' : 'Discarded'
    case 'stale':
      return 'Out of date'
    case 'superseded':
      return 'Replaced by a newer proposal'
  }
}

function StatusBadge({ changeset }: { changeset: Changeset }) {
  const applied = changeset.status === 'applied'
  return (
    <Badge
      className={cn(
        'shrink-0 gap-1.5',
        applied && 'border-transparent bg-emerald-500/10 text-emerald-700 dark:text-emerald-400',
      )}
      variant={changeset.status === 'proposed' ? 'outline' : 'secondary'}
    >
      {applied && <CheckIcon className="size-3" />}
      {changeset.status === 'stale' && <ClockAlertIcon className="size-3" />}
      {statusLabel(changeset)}
    </Badge>
  )
}

function Cell({
  field,
  before,
  after,
  gone,
  struck,
  added,
}: {
  field: ChangesetField
  before: string | null | undefined
  after: string | null | undefined
  /** The row does not survive: deleted, or replaced by the legs of a split. */
  gone: boolean
  /** Only a delete crosses a row out. A split keeps the booking, it just stops counting. */
  struck: boolean
  added: boolean
}) {
  if (gone)
    return <span className={cn('text-muted-foreground', struck && 'line-through')}>{display(field, before)}</span>
  if (added) return <span>{display(field, after)}</span>
  if (before === after) return <span className="text-muted-foreground">{display(field, before)}</span>
  return (
    <span className="inline-flex items-center gap-1.5">
      <span className="text-muted-foreground line-through">{display(field, before)}</span>
      <ArrowRightIcon aria-hidden="true" className="size-3 shrink-0 text-muted-foreground" />
      <span className="font-medium">{display(field, after)}</span>
    </span>
  )
}

/** An undone change ran and was taken back, so the arrow turns around: the value on the right
 *  is the one the booking carries again. */
const reverted = (changeset: Changeset) => changeset.status === 'discarded' && changeset.applied_at !== null

const asShown = (row: ChangesetRow, flip: boolean): ChangesetRow =>
  flip ? { ...row, before: row.after, after: row.before } : row

/** The exact rows the changeset touches, as they are now and as they would be. */
export function ChangesetTable({ changeset }: { changeset: Changeset }) {
  const flip = reverted(changeset)
  return (
    <div className="max-h-80 overflow-auto rounded-md border">
      <Table>
        <TableHeader className="sticky top-0 bg-muted/80 backdrop-blur">
          <TableRow>
            {changeset.fields.map((field) => (
              <TableHead className="whitespace-nowrap text-xs" key={field}>
                {FIELD_LABEL[field]}
              </TableHead>
            ))}
          </TableRow>
        </TableHeader>
        <TableBody>
          {changeset.rows.map((original, index) => {
            const row = asShown(original, flip)
            return (
              // A preview row is a value, not an entity: a new leg of a split has no id yet.
              // oxlint-disable-next-line eslint(no-array-index-key)
              <TableRow key={row.id ?? `new-${index}`}>
                {changeset.fields.map((field) => (
                  <TableCell
                    className={cn('whitespace-nowrap text-xs', field === 'amount' && 'text-right tabular-nums')}
                    key={field}
                  >
                    <Cell
                      added={row.before === null}
                      after={row.after?.[field]}
                      before={row.before?.[field]}
                      field={field}
                      gone={row.after === null && row.before !== null}
                      struck={changeset.kind === 'delete' && !flip}
                    />
                  </TableCell>
                ))}
              </TableRow>
            )
          })}
        </TableBody>
      </Table>
    </div>
  )
}

/** What a changeset would do: the sentence, the caveat and the rows. Shared with Settings. */
export function ChangesetEffect({ changeset }: { changeset: Changeset }) {
  return (
    <div className="space-y-2">
      <p className="text-sm">{changeset.summary}</p>
      {changeset.note && <p className="text-muted-foreground text-xs">{changeset.note}</p>}
      {changeset.rows.length > 0 ? (
        <ChangesetTable changeset={changeset} />
      ) : (
        <p className="text-muted-foreground text-xs">No existing booking is affected.</p>
      )}
    </div>
  )
}

function CardShell({ changeset, children }: { changeset: Changeset; children?: React.ReactNode }) {
  const Icon = KIND_ICON[changeset.kind]
  return (
    <div className="not-prose w-full overflow-hidden rounded-md border">
      <div className="flex flex-wrap items-center justify-between gap-2 border-b bg-muted/30 px-3 py-2">
        <div className="flex min-w-0 items-center gap-2">
          <Icon aria-hidden="true" className="size-4 shrink-0 text-muted-foreground" />
          <span className="truncate font-medium text-sm">{changeset.title}</span>
          <Badge className="shrink-0" variant="outline">
            {KIND_LABEL[changeset.kind]}
          </Badge>
        </div>
        <StatusBadge changeset={changeset} />
      </div>
      <div className="space-y-3 p-3">
        <ChangesetEffect changeset={changeset} />
        {children}
      </div>
    </div>
  )
}

/** One proposal in the transcript, with the buttons that run it.
 *
 * Exported because a changeset does not only arrive as its own tool call: a receipt that
 * matches a booking is proposed inside the `import_file` step, and it has to read and behave
 * exactly like every other proposal.
 */
export function ChangesetProposal({ preview }: { preview: Changeset }) {
  const { profile } = useWorkspace()
  const queryClient = useQueryClient()
  // The tool output is the preview; the server owns the status, so a reload shows it too.
  const { data } = useQuery(changesetQuery(profile?.id, preview.id))
  const changeset = data ?? preview

  const act = useMutation({
    mutationFn: (action: (profileId: string, id: string) => Promise<Changeset>) => {
      if (!profile) throw new Error('No profile is active yet.')
      return action(profile.id, changeset.id)
    },
    onSuccess: async (next) => {
      queryClient.setQueryData(changesetQuery(profile?.id, changeset.id).queryKey, next)
      // The rows moved, so the transactions page and every category picker are stale.
      await queryClient.invalidateQueries({ queryKey: ['transactions'] })
      await queryClient.invalidateQueries({ queryKey: ['categories'] })
    },
    // A refused apply is usually a refused apply for a reason the server just recorded (the
    // rows moved), so the card asks it again rather than keeping the buttons it cannot use.
    onError: () => queryClient.invalidateQueries(changesetQuery(profile?.id, changeset.id)),
  })

  const busy = act.isPending
  return (
    <CardShell changeset={changeset}>
      <div className="flex flex-wrap items-center gap-2">
        {changeset.status === 'proposed' && (
          <>
            <Button disabled={busy} onClick={() => act.mutate(applyChangeset)} size="sm">
              {busy ? <Spinner /> : <CheckIcon />}
              Apply
            </Button>
            <Button disabled={busy} onClick={() => act.mutate(discardChangeset)} size="sm" variant="outline">
              <XIcon />
              Discard
            </Button>
          </>
        )}
        {changeset.undoable && (
          <Button disabled={busy} onClick={() => act.mutate(undoChangeset)} size="sm" variant="outline">
            {busy ? <Spinner /> : <UndoIcon />}
            Undo
          </Button>
        )}
        {changeset.status === 'stale' && (
          <p className="text-muted-foreground text-xs">
            Those bookings changed after this preview was made. Ask again for a fresh proposal.
          </p>
        )}
        {act.error && changeset.status === 'proposed' && (
          <p className="text-destructive text-xs" role="alert">
            {act.error.message}
          </p>
        )}
      </div>
    </CardShell>
  )
}

export function ChangesetCard({ part }: { part: ChangesetToolPart }) {
  if (part.state === 'output-available') return <ChangesetProposal preview={part.output} />
  if (part.state === 'output-error') {
    return (
      <div className="not-prose w-full rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2">
        <p className="font-medium text-sm">{part.input?.title ?? 'That change was refused'}</p>
        <p className="pt-1 text-destructive text-xs">{part.errorText}</p>
      </div>
    )
  }
  return (
    <div className="not-prose w-full rounded-md border px-3 py-2">
      <Shimmer className="text-sm" duration={1.5}>
        {part.input?.title ?? 'Working out the change...'}
      </Shimmer>
    </div>
  )
}
